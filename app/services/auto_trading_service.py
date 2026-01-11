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
from app.core.enums import OrderStatus, OrderType
from app.infrastructure.database.mongodb_client import get_mongodb_database
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
            "max_portfolio_weight_per_stock": 20.0,  # 단일 종목 최대 투자 비중 (%)
            "stop_loss_percent": -7.0,  # 손절 기준 (%)
            "take_profit_percent": 5.0,  # 익절 기준 (%)
            "use_sentiment": True,  # 감정 분석 사용 여부
            "min_sentiment_score": 0.15,  # 최소 감정 점수
            "order_type": OrderType.LIMIT.value,  # 주문 구분 (00: 지정가)
            "allow_buy_existing_stocks": True,  # 보유 중인 종목도 매수 허용 여부
            # 트레일링 스톱 설정
            "trailing_stop_enabled": False,  # 트레일링 스톱 활성화 여부
            "trailing_stop_distance_percent": 5.0,  # 일반 종목 트레일링 거리 (%)
            "leveraged_trailing_stop_distance_percent": 7.0,  # 레버리지 종목 트레일링 거리 (%)
            "trailing_stop_min_profit_percent": 3.0,  # 일반 종목 최소 수익률 (%)
            "leveraged_trailing_stop_min_profit_percent": 5.0,  # 레버리지 종목 최소 수익률 (%)
        }
    
    def get_auto_trading_config(self, user_id: Optional[str] = None) -> Dict:
        """
        자동매매 설정 조회 (users 컬렉션의 trading_config 필드)
        
        Args:
            user_id: 사용자 ID. None이면 기본 사용자 ID 사용
        
        Returns:
            자동매매 설정 딕셔너리
        """
        try:
            from app.utils.user_context import get_current_user_id
            if user_id is None:
                user_id = get_current_user_id()
            
            db = get_mongodb_database()
            if db is None:
                logger.error("MongoDB 연결 실패")
                return self.default_config
            
            # users 컬렉션에서 사용자 정보 조회
            user = db.users.find_one({"user_id": user_id})
            
            if user and user.get("trading_config"):
                # trading_config가 있으면 반환 (ObjectId 제거)
                config = user["trading_config"]
                config["user_id"] = user_id  # user_id 추가
                return config
            
            # 설정이 없으면 기본값 생성
            return self._create_default_config(user_id)
        
        except Exception as e:
            logger.error(f"자동매매 설정 조회 중 오류: {str(e)}")
            return self.default_config
    
    def _create_default_config(self, user_id: Optional[str] = None) -> Dict:
        """
        기본 설정 생성 (users 컬렉션의 trading_config 필드)
        
        Args:
            user_id: 사용자 ID. None이면 기본 사용자 ID 사용
        
        Returns:
            기본 설정 딕셔너리
        """
        try:
            from app.utils.user_context import get_current_user_id
            if user_id is None:
                user_id = get_current_user_id()
            
            db = get_mongodb_database()
            if db is None:
                logger.error("MongoDB 연결 실패")
                return self.default_config
            
            config = {
                **self.default_config,
                "updated_at": datetime.now()
            }
            
            # users 컬렉션에 trading_config 필드 업데이트
            update_result = db.users.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "trading_config": config,
                        "updated_at": datetime.now()
                    }
                },
                upsert=False  # 사용자가 없으면 생성하지 않음
            )
            
            if update_result.modified_count > 0:
                logger.info(f"사용자별 기본 설정 생성: user_id={user_id}")
            else:
                logger.warning(f"사용자 '{user_id}'를 찾을 수 없어 기본 설정을 생성하지 못했습니다. 기본값을 반환합니다.")
            
            config["user_id"] = user_id  # 반환용으로 user_id 추가
            return config
        except Exception as e:
            logger.error(f"기본 설정 생성 중 오류: {str(e)}")
            return self.default_config
    
    def update_auto_trading_config(self, config: Dict, user_id: Optional[str] = None) -> Dict:
        """
        자동매매 설정 업데이트 (users 컬렉션의 trading_config 필드)
        
        Args:
            config: 업데이트할 설정 딕셔너리
            user_id: 사용자 ID. None이면 기본 사용자 ID 사용
        
        Returns:
            업데이트 결과 딕셔너리
        """
        try:
            from app.utils.user_context import get_current_user_id
            if user_id is None:
                user_id = get_current_user_id()
            
            db = get_mongodb_database()
            if db is None:
                logger.error("MongoDB 연결 실패")
                return {"success": False, "error": "MongoDB 연결 실패"}
            
            # 현재 설정 조회 (없으면 기본값 사용)
            current_config = self.get_auto_trading_config(user_id)
            
            # user_id와 _id 필드 제거 (embedded config에는 포함하지 않음)
            current_config.pop("user_id", None)
            current_config.pop("_id", None)
            current_config.pop("created_at", None)  # created_at도 제거 (trading_config에는 없음)
            
            # 설정 업데이트
            updated_config = {**current_config, **config, "updated_at": datetime.now()}
            
            # users 컬렉션의 trading_config 필드 업데이트
            update_result = db.users.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "trading_config": updated_config,
                        "updated_at": datetime.now()
                    }
                }
            )
            
            if update_result.matched_count == 0:
                return {"success": False, "error": f"사용자 '{user_id}'를 찾을 수 없습니다."}
            
            # 반환용으로 user_id 추가
            updated_config["user_id"] = user_id
            
            logger.info(f"사용자별 설정 업데이트 완료: user_id={user_id}")
            return {"success": True, "config": updated_config}
        
        except Exception as e:
            logger.error(f"자동매매 설정 업데이트 중 오류: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def get_buy_candidates(self, config: Optional[Dict] = None, user_id: Optional[str] = None) -> List[Dict]:
        """매수 추천 종목 조회"""
        if config is None:
            config = self.get_auto_trading_config(user_id=user_id)
        
        try:
            # 2. 매수 추천 종목 조회 (통합 분석 결과 사용)
            recommendations = self.stock_service.get_combined_recommendations_with_technical_and_sentiment(
                send_slack_notification=False
            )
            
            candidates = []
            if recommendations and recommendations.get("results"):
                # MongoDB에서 사용자별 레버리지 설정 조회
                # 모델 구조: User.stocks (List[UserStockEmbedded])
                # UserStockEmbedded에는 ticker, use_leverage만 있고, leverage_ticker는 stocks 컬렉션에서 조회
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
                            # embedded stocks에서 UserStockEmbedded 모델 구조에 맞게 ticker, use_leverage만 사용
                            for stock in user.get("stocks", []):
                                ticker = stock.get("ticker")  # UserStockEmbedded.ticker
                                if ticker:
                                    user_leverage_map[ticker] = {
                                        "use_leverage": stock.get("use_leverage", False)  # UserStockEmbedded.use_leverage
                                        # leverage_ticker는 Stock 모델에 있으므로 stocks 컬렉션에서 조회해야 함
                                    }
                except Exception as e:
                    logger.error(f"레버리지 설정 조회 실패: {str(e)}")

                # 중복 제거를 위한 set (티커 기준)
                seen_tickers = set()
                
                for stock in recommendations["results"]:
                    # 티커 기준 중복 제거
                    original_ticker = stock.get("ticker")
                    if not original_ticker:
                        continue
                    
                    if original_ticker in seen_tickers:
                        logger.warning(f"중복된 추천 종목 발견 및 제외: {stock.get('stock_name')} ({original_ticker})")
                        continue
                    seen_tickers.add(original_ticker)
                    
                    # 종합 점수 필터링
                    if stock.get("composite_score", 0) < config.get("min_composite_score", 2.0):
                        continue
                    
                    # use_leverage 필터링: use_leverage가 true인 종목만 매수
                    if original_ticker not in user_leverage_map:
                        # 사용자 설정에 없는 종목은 매수하지 않음
                        logger.info(f"{original_ticker} ({stock.get('stock_name')}) - 사용자 설정에 없어 매수 제외")
                        continue
                    
                    if not user_leverage_map[original_ticker]["use_leverage"]:
                        # use_leverage가 false인 종목은 매수하지 않음
                        logger.info(f"{original_ticker} ({stock.get('stock_name')}) - use_leverage가 false여서 매수 제외")
                        continue
                    
                    # 레버리지 설정 적용
                    # 모델 구조: Stock.leverage_ticker 필드를 stocks 컬렉션에서 조회
                    # UserStockEmbedded에는 leverage_ticker가 없으므로 stocks 컬렉션에서 조회해야 함
                    actual_ticker = original_ticker
                    is_leverage = False
                    
                    if user_leverage_map[original_ticker]["use_leverage"]:
                        # Stock 모델의 leverage_ticker 필드를 stocks 컬렉션에서 조회
                        if db is not None:
                            stock_doc = db.stocks.find_one({"ticker": original_ticker})
                            if stock_doc and stock_doc.get("leverage_ticker"):  # Stock.leverage_ticker
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
    
    def execute_auto_buy(self, dry_run: bool = False, user_id: Optional[str] = None) -> Dict:
        """자동 매수 실행"""
        try:
            from app.utils.user_context import get_current_user_id
            if user_id is None:
                user_id = get_current_user_id()
            
            # 설정 확인
            config = self.get_auto_trading_config(user_id=user_id)
            
            if not config.get("enabled", False):
                return {"success": False, "error": "자동매매가 비활성화되어 있습니다"}
            
            # 매수 후보 조회
            candidates = self.get_buy_candidates(config, user_id=user_id)
            
            if not candidates:
                return {"success": True, "message": "매수할 종목이 없습니다", "orders": []}
            
            # 현재 보유 종목 확인
            balance_result = get_overseas_balance()
            holding_tickers = set()
            if balance_result.get("rt_cd") == "0" and "output1" in balance_result:
                holding_tickers = {item.get("ovrs_pdno") for item in balance_result["output1"]}
            
            orders = []
            max_amount = config.get("max_amount_per_stock", 10000.0)
            
            # 중복 제거 (티커 기준) - 이중 안전장치
            seen_tickers = set()
            deduplicated_candidates = []
            for candidate in candidates:
                ticker = candidate.get("ticker")
                if ticker and ticker not in seen_tickers:
                    deduplicated_candidates.append(candidate)
                    seen_tickers.add(ticker)
                elif ticker:
                    logger.warning(f"매수 실행 시 중복된 티커 발견 및 제외: {candidate.get('stock_name')} ({ticker})")
            
            candidates = deduplicated_candidates
            logger.info(f"매수 후보 종목 수 (중복 제거 후): {len(candidates)}개")
            
            for candidate in candidates:
                ticker = candidate.get("ticker")
                stock_name = candidate.get("stock_name", "N/A")
                original_ticker = candidate.get("original_ticker")  # 레버리지 티커인 경우 원본 티커
                is_leverage = candidate.get("is_leverage", False)
                
                # 이미 보유 중인 종목은 스킵
                # if ticker in holding_tickers:
                #     logger.info(f"{ticker} - 이미 보유 중, 스킵")
                #     continue
                
                # stocks 컬렉션에서 거래소 정보 조회
                # 모델 구조: Stock.exchange 필드를 stocks 컬렉션에서 조회
                # 레버리지 티커인 경우: 레버리지 티커로 먼저 조회, 없으면 원본 티커로 조회
                exchange_code = None
                pure_ticker = ticker
                try:
                    from app.infrastructure.database.mongodb_client import get_mongodb_database
                    db = get_mongodb_database()
                    if db is not None:  # MongoDB Database 객체는 직접 boolean 평가 불가
                        # Stock 모델의 exchange 필드를 조회
                        # 레버리지 티커인 경우 레버리지 티커로 먼저 조회
                        stock_doc = db.stocks.find_one({"ticker": ticker})
                        
                        # 레버리지 티커로 조회 실패하고 원본 티커가 있으면 원본 티커로 조회
                        if not stock_doc and original_ticker and original_ticker != ticker:
                            stock_doc = db.stocks.find_one({"ticker": original_ticker})
                        
                        if stock_doc and stock_doc.get("exchange"):  # Stock.exchange
                            # stocks 컬렉션의 exchange 필드 사용 (예: "NASD", "NYSE", "AMEX")
                            exchange_code = stock_doc.get("exchange")
                            # "NASS" 같은 잘못된 코드는 정규화
                            if exchange_code == "NASS":
                                exchange_code = "NASD"
                            elif exchange_code == "NYS":
                                exchange_code = "NYSE"
                            elif exchange_code == "AMS":
                                exchange_code = "AMEX"
                except Exception as e:
                    logger.warning(f"{stock_name}({ticker}) - 거래소 정보 조회 실패: {str(e)}")
                
                # 거래소 코드 결정 (stocks 컬렉션에 없으면 티커 기반으로 판단)
                if not exchange_code:
                    if ticker.endswith(".X") or ticker.endswith(".N"):
                        # 거래소 구분이 티커에 포함된 경우
                        exchange_code = "NYSE" if ticker.endswith(".N") else "NASD"
                        pure_ticker = ticker.split(".")[0]
                    else:
                        # 기본값 NASDAQ으로 설정
                        exchange_code = "NASD"
                        pure_ticker = ticker
                else:
                    # exchange_code가 있으면 티커에서 거래소 구분 제거
                    if ticker.endswith(".X") or ticker.endswith(".N"):
                        pure_ticker = ticker.split(".")[0]
                    else:
                        pure_ticker = ticker
                
                # 거래소 코드 유효성 검증
                if not exchange_code or exchange_code not in ["NASD", "NYSE", "AMEX"]:
                    logger.warning(f"{stock_name}({ticker}) - 유효하지 않은 거래소 코드: {exchange_code}, 기본값 NASD 사용")
                    exchange_code = "NASD"
                
                # 거래소 코드 변환 (API 요청에 맞게 변환)
                from app.core.enums import get_exchange_code_for_api
                api_exchange_code = get_exchange_code_for_api(exchange_code)
                
                if not api_exchange_code:
                    logger.error(f"{stock_name}({ticker}) - 거래소 코드 변환 실패: {exchange_code}")
                    continue
                
                # 현재가 조회
                price_params = {
                    "AUTH": "",
                    "EXCD": api_exchange_code,  # 변환된 거래소 코드 사용
                    "SYMB": pure_ticker
                }
                
                price_result = get_current_price(price_params)
                
                if price_result.get("rt_cd") != "0":
                    error_msg = price_result.get('msg1', '알 수 없는 오류')
                    logger.error(f"{stock_name}({ticker}) - 현재가 조회 실패: {error_msg}")
                    continue
                
                # 현재가 추출
                last_price = price_result.get("output", {}).get("last", 0) or 0
                try:
                    current_price = float(last_price)
                except (ValueError, TypeError) as e:
                    logger.error(f"{stock_name}({ticker}) - 현재가 변환 실패: {last_price}, 오류: {str(e)}")
                    continue
                
                if current_price <= 0:
                    logger.error(f"{stock_name}({ticker}) - 현재가가 유효하지 않습니다: {current_price}")
                    continue
                
                # 매수 수량 계산
                quantity_result = self.calculate_buy_quantity(
                    ticker, exchange_code, current_price, max_amount
                )
                
                if not quantity_result.get("success"):
                    error_msg = quantity_result.get("error", "알 수 없는 오류")
                    logger.warning(f"{ticker} - 매수 수량 계산 실패: {error_msg}")
                    continue
                
                quantity = quantity_result.get("quantity", 0)
                if quantity <= 0:
                    max_available = quantity_result.get("max_available", 0)
                    estimated_amount = quantity_result.get("estimated_amount", 0)
                    logger.warning(
                        f"{ticker} - 매수 가능 수량 없음 "
                        f"(현재가: ${current_price:.2f}, 최대가능금액: ${max_available:.2f}, "
                        f"설정최대금액: ${max_amount:.2f}, 계산수량: {quantity})"
                    )
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
                    "status": OrderStatus.SUCCESS.value if order_result.get("rt_cd") == "0" else OrderStatus.FAILED.value,
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
    
    def execute_auto_sell(self, dry_run: bool = False, user_id: Optional[str] = None) -> Dict:
        """자동 매도 실행 (손절/익절)"""
        try:
            from app.utils.user_context import get_current_user_id
            if user_id is None:
                user_id = get_current_user_id()
            
            # 설정 확인
            config = self.get_auto_trading_config(user_id=user_id)
            
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
                    "status": OrderStatus.SUCCESS.value if order_result.get("rt_cd") == "0" else OrderStatus.FAILED.value,
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
    
    def get_auto_trading_status(self, user_id: Optional[str] = None) -> Dict:
        """자동매매 상태 조회"""
        try:
            from app.utils.user_context import get_current_user_id
            if user_id is None:
                user_id = get_current_user_id()
            
            config = self.get_auto_trading_config(user_id=user_id)
            
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
            buy_candidates = self.get_buy_candidates(config, user_id=user_id)
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
            db = get_mongodb_database()
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
            db = get_mongodb_database()
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

