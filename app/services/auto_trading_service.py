"""
자동매매 서비스
- 매수 추천 종목 자동 매수
- 보유 종목 자동 매도 (손절/익절)
- 자동매매 설정 관리
- 백테스팅
"""

import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging
from app.db.mongodb import get_db
from app.services.stock_recommendation_service import StockRecommendationService
from app.services.balance_service import (
    get_overseas_balance,
    order_overseas_stock,
    inquire_psamount,
    get_current_price,
    get_overseas_order_possible_amount
)
from app.core.config import settings

logger = logging.getLogger(__name__)


class AutoTradingService:
    """자동매매 서비스 클래스"""
    
    def __init__(self):
        self.stock_service = StockRecommendationService()
        self.default_config = {
            "enabled": False,
            "min_composite_score": 2.0,  # 최소 종합 점수 (기존 70점에서 실제 점수 분포 2~3점에 맞춰 하향 조정)
            "max_stocks_to_buy": 5,  # 최대 매수 종목 수
            "max_amount_per_stock": 10000.0,  # 종목당 최대 매수 금액 (USD)
            "stop_loss_percent": -7.0,  # 손절 기준 (%)
            "take_profit_percent": 5.0,  # 익절 기준 (%)
            "use_sentiment": True,  # 감정 분석 사용 여부
            "min_sentiment_score": 0.15,  # 최소 감정 점수
            "order_type": "00",  # 주문 구분 (00: 지정가)
            "allow_buy_existing_stocks": True,  # 보유 중인 종목도 매수 허용 여부
        }
    
    def get_auto_trading_config(self) -> Dict:
        """자동매매 설정 조회 (MongoDB trading_configs 컬렉션)"""
        try:
            db = get_db()
            if db is None:
                logger.error("MongoDB 연결 실패")
                return self.default_config
            
            # 최신 설정 조회
            config = db.trading_configs.find_one(
                {},
                sort=[("created_at", -1)]
            )
            
            if config:
                # ObjectId를 문자열로 변환
                config["_id"] = str(config["_id"])
                return config
            
            # 설정이 없으면 기본값 생성
            return self._create_default_config()
        
        except Exception as e:
            logger.error(f"자동매매 설정 조회 중 오류: {str(e)}")
            return self.default_config
    
    def _create_default_config(self) -> Dict:
        """기본 설정 생성 (MongoDB trading_configs 컬렉션)"""
        try:
            db = get_db()
            if db is None:
                logger.error("MongoDB 연결 실패")
                return self.default_config
            
            config = {
                **self.default_config,
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }
            result = db.trading_configs.insert_one(config)
            config["_id"] = str(result.inserted_id)
            return config
        except Exception as e:
            logger.error(f"기본 설정 생성 중 오류: {str(e)}")
            return self.default_config
    
    def update_auto_trading_config(self, config: Dict) -> Dict:
        """자동매매 설정 업데이트 (MongoDB trading_configs 컬렉션)"""
        try:
            db = get_db()
            if db is None:
                logger.error("MongoDB 연결 실패")
                return {"success": False, "error": "MongoDB 연결 실패"}
            
            current_config = self.get_auto_trading_config()
            
            # 설정 업데이트
            updated_config = {**current_config, **config, "updated_at": datetime.now()}
            
            # _id 필드 제거 (업데이트 시 _id는 변경 불가)
            config_id = updated_config.pop("_id", None)
            
            if config_id:
                # 기존 설정 업데이트
                from bson import ObjectId
                db.trading_configs.update_one(
                    {"_id": ObjectId(config_id)},
                    {"$set": updated_config}
                )
                updated_config["_id"] = config_id
            else:
                # 새로운 설정 생성
                updated_config["created_at"] = datetime.now()
                result = db.trading_configs.insert_one(updated_config)
                updated_config["_id"] = str(result.inserted_id)
            
            return {"success": True, "config": updated_config}
        
        except Exception as e:
            logger.error(f"자동매매 설정 업데이트 중 오류: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def get_buy_candidates(self, config: Optional[Dict] = None) -> List[Dict]:
        """매수 추천 종목 조회"""
        if config is None:
            config = self.get_auto_trading_config()
        
        try:
            # 2. 매수 추천 종목 조회 (통합 분석 결과 사용)
            recommendations = self.stock_service.get_combined_recommendations_with_technical_and_sentiment(
                send_slack_notification=False
            )
            
            candidates = []
            if recommendations and recommendations.get("results"):
                # MongoDB에서 사용자별 레버리지 설정 조회
                user_leverage_map = {}
                db = None
                try:
                    from app.infrastructure.database.mongodb_client import get_mongodb_database
                    db = get_mongodb_database()
                    if db is not None:
                        # TODO: 실제 사용자 ID를 문맥에서 가져와야 함. 현재는 기본값 'lian' 사용
                        user_id = 'lian'
                        user = db.users.find_one({"user_id": user_id})
                        if user and user.get("stocks"):
                            for stock in user.get("stocks", []):
                                ticker = stock.get("ticker")
                                if ticker:
                                    user_leverage_map[ticker] = {
                                        "use_leverage": stock.get("use_leverage", False)
                                        # leverage_ticker는 stocks 컬렉션에서 조회
                                    }
                except Exception as e:
                    logger.error(f"레버리지 설정 조회 실패: {str(e)}")

                for stock in recommendations["results"]:
                    # 종합 점수 필터링
                    if stock.get("composite_score", 0) < config.get("min_composite_score", 2.0):
                        continue
                    
                    # 레버리지 설정 적용 (leverage_ticker는 stocks 컬렉션에서 조회)
                    original_ticker = stock.get("ticker")
                    actual_ticker = original_ticker
                    is_leverage = False
                    
                    if original_ticker in user_leverage_map and user_leverage_map[original_ticker]["use_leverage"]:
                        # stocks 컬렉션에서 레버리지 티커 조회
                        if db is not None:
                            stock_doc = db.stocks.find_one({"ticker": original_ticker})
                            if stock_doc and stock_doc.get("leverage_ticker"):
                                actual_ticker = stock_doc["leverage_ticker"]
                                is_leverage = True
                                stock["original_ticker"] = original_ticker
                                stock["note"] = "사용자 설정에 의해 레버리지 티커 적용됨"
                    
                    stock["ticker"] = actual_ticker
                    stock["is_leverage"] = is_leverage
                    
                    # 감정 분석 필터링 (설정이 활성화된 경우)
                    if config.get("use_sentiment", False):
                        sentiment_score = stock.get("sentiment_score")
                        min_sentiment = config.get("min_sentiment_score", -0.2)
                        
                        # 감정 점수가 없거나 기준 미달이면 제외
                        if sentiment_score is None or sentiment_score < min_sentiment:
                            continue
                    
                    candidates.append(stock)
                
                # 종합 점수 기준 정렬 (높은 순)
                candidates.sort(key=lambda x: x.get("composite_score", 0), reverse=True)

                # 최대 매수 종목 수 제한
                max_stocks = config.get("max_stocks_to_buy", 5)
                candidates = candidates[:max_stocks]
            
            return candidates
        
        except Exception as e:
            logger.error(f"매수 후보 조회 중 오류: {str(e)}")
            return []
    
    def calculate_buy_quantity(self, ticker: str, exchange_code: str, target_price: float, 
                               max_amount: float) -> Dict:
        """매수 가능 수량 계산"""
        try:
            # 매수가능금액 조회
            params = {
                "CANO": settings.KIS_CANO,
                "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
                "OVRS_EXCG_CD": exchange_code,
                "ITEM_CD": ticker,
                "OVRS_ORD_UNPR": str(target_price)
            }
            
            result = inquire_psamount(params)
            
            if result.get("rt_cd") != "0":
                return {"success": False, "error": result.get("msg1", "조회 실패")}
            
            # 매수 가능 금액 확인
            output = result.get("output", {})
            try:
                max_buy_amount = float(output.get("max_ord_psbl_amt") or 0)
            except ValueError:
                max_buy_amount = 0.0
            
            # 설정된 최대 금액과 비교하여 더 작은 값 사용
            actual_max_amount = min(max_buy_amount, max_amount)
            
            # 수량 계산
            quantity = int(actual_max_amount / target_price)
            
            return {
                "success": True,
                "quantity": quantity,
                "estimated_amount": quantity * target_price,
                "max_available": max_buy_amount
            }
        
        except Exception as e:
            logger.error(f"매수 수량 계산 중 오류: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def execute_auto_buy(self, dry_run: bool = False) -> Dict:
        """자동 매수 실행"""
        try:
            # 설정 확인
            config = self.get_auto_trading_config()
            
            if not config.get("enabled", False):
                return {"success": False, "error": "자동매매가 비활성화되어 있습니다"}
            
            # 매수 후보 조회
            candidates = self.get_buy_candidates(config)
            
            if not candidates:
                return {"success": True, "message": "매수할 종목이 없습니다", "orders": []}
            
            # 현재 보유 종목 확인
            balance_result = get_overseas_balance()
            holding_tickers = set()
            if balance_result.get("rt_cd") == "0" and "output1" in balance_result:
                holding_tickers = {item.get("ovrs_pdno") for item in balance_result["output1"]}
            
            orders = []
            max_amount = config.get("max_amount_per_stock", 10000.0)
            
            for candidate in candidates:
                ticker = candidate.get("ticker")
                
                # 이미 보유 중인 종목은 스킵
                # if ticker in holding_tickers:
                #     logger.info(f"{ticker} - 이미 보유 중, 스킵")
                #     continue
                
                # 현재가 조회 (여러 거래소 시도)
                exchanges = ["NAS", "AMS", "NYS"]
                price_result = None
                
                # 기본 거래소를 맨 앞으로
                default_exchange = self._get_exchange_code(ticker).replace("D", "S")
                if default_exchange in exchanges:
                    exchanges.remove(default_exchange)
                    exchanges.insert(0, default_exchange)
                
                for exchange in exchanges:
                    temp_result = get_current_price({
                        "EXCD": exchange,
                        "SYMB": ticker
                    })
                    
                    # 데이터가 있는지 확인 (last나 base가 있어야 함)
                    output = temp_result.get("output", {})
                    if temp_result.get("rt_cd") == "0" and (output.get("last") or output.get("base")):
                        price_result = temp_result
                        if exchange != default_exchange:
                            logger.info(f"{ticker} - 거래소 변경 발견: {default_exchange} -> {exchange}")
                        break
                    
                    # 마지막 시도였으면 결과 저장
                    if exchange == exchanges[-1]:
                        price_result = temp_result

                if not price_result or price_result.get("rt_cd") != "0":
                    logger.error(f"{ticker} - 현재가 조회 실패")
                    # 실시간 조회 실패 시 추천 당시 가격 사용 시도
                
                # 데이터가 없는 경우 (rt_cd는 0이지만 output이 비어있는 경우 포함)
                if current_price <= 0:
                    # 현재가가 0이거나 비어있는 경우 전일 종가(base) 확인
                    try:
                        base_price = float(price_result.get("output", {}).get("base") or 0)
                        if base_price > 0:
                            current_price = base_price
                            logger.warning(f"{ticker} - 현재가 조회 불가(0.0), 전일 종가({base_price})로 대체합니다.")
                        else:
                            # 전일 종가도 없는 경우 추천 데이터의 last_price 또는 predicted_price 사용
                            logger.warning(f"{ticker} - API 가격 정보 없음. 추천 데이터의 대체 가격 확인 중...")
                            
                            cached_last_price = float(candidate.get("last_price") or 0)
                            predicted_price = float(candidate.get("predicted_price") or 0)
                            
                            if cached_last_price > 0:
                                current_price = cached_last_price
                                logger.warning(f"{ticker} - 추천 당시 가격({current_price})을 사용하여 주문 진행")
                            elif predicted_price > 0:
                                current_price = predicted_price
                                logger.warning(f"{ticker} - AI 예측 가격({current_price})을 사용하여 주문 진행")
                            else:
                                logger.error(f"{ticker} - 유효하지 않은 가격: {current_price}, 대체 가격도 없음 (API 응답: {price_result})")
                                continue
                    except ValueError:
                         logger.error(f"{ticker} - 유효하지 않은 가격: {current_price} (API 응답: {price_result})")
                         continue
                
                # 매수 수량 계산
                quantity_result = self.calculate_buy_quantity(
                    ticker, exchange_code, current_price, max_amount
                )
                
                if not quantity_result.get("success") or quantity_result.get("quantity", 0) <= 0:
                    logger.warning(f"{ticker} - 매수 가능 수량 없음")
                    continue
                
                quantity = quantity_result["quantity"]
                
                # Dry run 모드
                if dry_run:
                    orders.append({
                        "ticker": ticker,
                        "stock_name": candidate.get("stock_name"),
                        "price": current_price,
                        "quantity": quantity,
                        "estimated_amount": quantity * current_price,
                        "composite_score": candidate.get("composite_score"),
                        "status": "dry_run"
                    })
                    continue
                
                # 실제 주문 실행
                order_data = {
                    "CANO": settings.KIS_CANO,
                    "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
                    "PDNO": ticker,
                    "OVRS_EXCG_CD": exchange_code,
                    "ORD_QTY": str(quantity),
                    "OVRS_ORD_UNPR": str(current_price),
                    "is_buy": True,
                    "ORD_DVSN": config.get("order_type", "00"),
                    "stock_name": candidate.get("stock_name")  # 종목명 추가
                }
                
                order_result = order_overseas_stock(order_data)
                
                order_info = {
                    "ticker": ticker,
                    "stock_name": candidate.get("stock_name"),
                    "price": current_price,
                    "quantity": quantity,
                    "estimated_amount": quantity * current_price,
                    "composite_score": candidate.get("composite_score"),
                    "status": "success" if order_result.get("rt_cd") == "0" else "failed",
                    "order_result": order_result
                }
                
                orders.append(order_info)
                
                # 주문 기록 저장
                self._save_order_log(order_info, "buy")
                
                # API Rate Limit 방지를 위한 대기
                time.sleep(0.5)
            
            return {
                "success": True,
                "message": f"{len(orders)}개 종목 주문 완료",
                "orders": orders,
                "config": config
            }
        
        except Exception as e:
            logger.error(f"자동 매수 실행 중 오류: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {"success": False, "error": str(e)}
    
    def execute_auto_sell(self, dry_run: bool = False) -> Dict:
        """자동 매도 실행 (손절/익절)"""
        try:
            # 설정 확인
            config = self.get_auto_trading_config()
            
            if not config.get("enabled", False):
                return {"success": False, "error": "자동매매가 비활성화되어 있습니다"}
            
            # 매도 대상 조회
            sell_result = self.stock_service.get_stocks_to_sell()
            candidates = sell_result.get("sell_candidates", [])
            
            if not candidates:
                return {"success": True, "message": "매도할 종목이 없습니다", "orders": []}
            
            orders = []
            
            for candidate in candidates:
                ticker = candidate.get("ticker")
                quantity = candidate.get("quantity")
                current_price = candidate.get("current_price")
                exchange_code = candidate.get("exchange_code")
                
                # Dry run 모드
                if dry_run:
                    orders.append({
                        "ticker": ticker,
                        "stock_name": candidate.get("stock_name"),
                        "price": current_price,
                        "quantity": quantity,
                        "price_change_percent": candidate.get("price_change_percent"),
                        "sell_reasons": candidate.get("sell_reasons"),
                        "status": "dry_run"
                    })
                    continue
                
                # 실제 매도 주문 실행
                order_data = {
                    "CANO": settings.KIS_CANO,
                    "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
                    "PDNO": ticker,
                    "OVRS_EXCG_CD": exchange_code,
                    "ORD_QTY": str(quantity),
                    "OVRS_ORD_UNPR": str(current_price),
                    "is_buy": False,  # 매도
                    "ORD_DVSN": config.get("order_type", "00"),
                    "stock_name": candidate.get("stock_name")  # 종목명 추가
                }
                
                order_result = order_overseas_stock(order_data)
                
                order_info = {
                    "ticker": ticker,
                    "stock_name": candidate.get("stock_name"),
                    "price": current_price,
                    "quantity": quantity,
                    "price_change_percent": candidate.get("price_change_percent"),
                    "sell_reasons": candidate.get("sell_reasons"),
                    "status": "success" if order_result.get("rt_cd") == "0" else "failed",
                    "order_result": order_result
                }
                
                orders.append(order_info)
                
                # 주문 기록 저장
                self._save_order_log(order_info, "sell")
                
                # API Rate Limit 방지를 위한 대기
                time.sleep(0.5)
            
            return {
                "success": True,
                "message": f"{len(orders)}개 종목 매도 완료",
                "orders": orders,
                "config": config
            }
        
        except Exception as e:
            logger.error(f"자동 매도 실행 중 오류: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {"success": False, "error": str(e)}
    
    def get_auto_trading_status(self) -> Dict:
        """자동매매 상태 조회"""
        try:
            config = self.get_auto_trading_config()
            
            # 보유 종목 정보
            balance_result = get_overseas_balance()
            holdings = []
            total_value = 0.0
            
            if balance_result.get("rt_cd") == "0" and "output1" in balance_result:
                holdings = balance_result["output1"]
                for item in holdings:
                    # 평가 금액 계산
                    try:
                        quantity = float(item.get("ovrs_cblc_qty") or 0)
                        current_price = float(item.get("now_pric2") or 0)
                    except ValueError:
                        continue
                    total_value += quantity * current_price
            
            # 현금 잔고 조회 (매수가능금액 API 사용 - TTTS3007R)
            available_cash = 0.0
            try:
                # 매수가능금액 API 사용 (ovrs_ord_psbl_amt: 해외주문가능금액)
                order_psbl_result = get_overseas_order_possible_amount("NASD", "AAPL")
                if order_psbl_result.get("rt_cd") == "0":
                    output = order_psbl_result.get("output", {})
                    if output:
                        # ovrs_ord_psbl_amt: 해외주문가능금액 (실제 사용 가능한 전체 금액)
                        cash_str = output.get("ovrs_ord_psbl_amt") or "0"
                        if cash_str and cash_str != "0":
                            try:
                                available_cash = float(cash_str)
                                logger.info(f"매수가능금액 API에서 현금 잔고 조회 성공: ${available_cash:,.2f}")
                            except (ValueError, TypeError):
                                logger.warning(f"매수가능금액 API에서 현금 잔고 변환 실패: {cash_str}")
            except Exception as e:
                logger.warning(f"현금 잔고 조회 중 오류: {str(e)}", exc_info=True)
            
            # 최근 주문 내역
            recent_orders = self._get_recent_orders(days=7)
            
            # 매수/매도 후보
            buy_candidates = self.get_buy_candidates(config)
            sell_result = self.stock_service.get_stocks_to_sell()
            sell_candidates = sell_result.get("sell_candidates", [])
            
            return {
                "config": config,
                "holdings": {
                    "count": len(holdings),
                    "total_value": total_value,
                    "items": holdings
                },
                "available_cash": available_cash,
                "candidates": {
                    "buy": {
                        "count": len(buy_candidates),
                        "items": buy_candidates
                    },
                    "sell": {
                        "count": len(sell_candidates),
                        "items": sell_candidates
                    }
                },
                "recent_orders": recent_orders
            }
        
        except Exception as e:
            logger.error(f"자동매매 상태 조회 중 오류: {str(e)}")
            return {"error": str(e)}
    
    def _save_order_log(self, order_info: Dict, order_type: str):
        """주문 기록 저장 (MongoDB trading_logs 컬렉션)"""
        try:
            db = get_db()
            if db is None:
                logger.error("MongoDB 연결 실패 - 주문 기록 저장 불가")
                return
            
            log_data = {
                "order_type": order_type,
                "ticker": order_info.get("ticker"),
                "stock_name": order_info.get("stock_name"),
                "price": order_info.get("price"),
                "quantity": order_info.get("quantity"),
                "status": order_info.get("status"),
                "composite_score": order_info.get("composite_score"),
                "price_change_percent": order_info.get("price_change_percent"),
                "sell_reasons": order_info.get("sell_reasons"),
                "order_result": order_info.get("order_result"),
                "created_at": datetime.now()
            }
            
            db.trading_logs.insert_one(log_data)
        
        except Exception as e:
            logger.error(f"주문 기록 저장 중 오류: {str(e)}")
    
    def _get_recent_orders(self, days: int = 7) -> List[Dict]:
        """최근 주문 내역 조회 (MongoDB trading_logs 컬렉션)"""
        try:
            db = get_db()
            if db is None:
                logger.error("MongoDB 연결 실패")
                return []
            
            start_date = datetime.now() - timedelta(days=days)
            
            cursor = db.trading_logs.find(
                {"created_at": {"$gte": start_date}}
            ).sort("created_at", -1)
            
            orders = []
            for doc in cursor:
                doc["_id"] = str(doc["_id"])
                # datetime을 ISO 문자열로 변환 (API 응답 호환성)
                if isinstance(doc.get("created_at"), datetime):
                    doc["created_at"] = doc["created_at"].isoformat()
                orders.append(doc)
            
            return orders
        
        except Exception as e:
            logger.error(f"최근 주문 내역 조회 중 오류: {str(e)}")
            return []
    
    def _get_exchange_code(self, ticker: str) -> str:
        """티커로 거래소 코드 반환"""
        # 간단한 로직: 대부분의 미국 주식은 NASD (나스닥) 또는 NYSE
        # 실제로는 ticker_mapping 테이블에서 가져와야 함
        # 일단 기본값으로 NASD 반환
        return "NASD"
    
    def run_backtest(self, start_date: str, end_date: str, initial_capital: float = 100000.0) -> Dict:
        """백테스팅 실행"""
        # TODO: 백테스팅 로직 구현
        # 과거 데이터를 기반으로 자동매매 전략 시뮬레이션
        return {
            "success": False,
            "message": "백테스팅 기능은 아직 구현되지 않았습니다"
        }

