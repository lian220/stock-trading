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
from app.db.supabase import supabase
from app.services.stock_recommendation_service import StockRecommendationService
from app.services.balance_service import (
    get_overseas_balance,
    order_overseas_stock,
    inquire_psamount,
    get_current_price
)
from app.core.config import settings

logger = logging.getLogger(__name__)


class AutoTradingService:
    """자동매매 서비스 클래스"""
    
    def __init__(self):
        self.stock_service = StockRecommendationService()
        self.default_config = {
            "enabled": False,
            "min_composite_score": 70.0,  # 최소 종합 점수
            "max_stocks_to_buy": 5,  # 최대 매수 종목 수
            "max_amount_per_stock": 10000.0,  # 종목당 최대 매수 금액 (USD)
            "stop_loss_percent": -7.0,  # 손절 기준 (%)
            "take_profit_percent": 5.0,  # 익절 기준 (%)
            "use_sentiment": True,  # 감정 분석 사용 여부
            "min_sentiment_score": 0.15,  # 최소 감정 점수
            "order_type": "00",  # 주문 구분 (00: 지정가)
        }
    
    def get_auto_trading_config(self) -> Dict:
        """자동매매 설정 조회"""
        try:
            response = supabase.table("auto_trading_config") \
                .select("*") \
                .order("created_at", desc=True) \
                .limit(1) \
                .execute()
            
            if response.data:
                return response.data[0]
            
            # 설정이 없으면 기본값 생성
            return self._create_default_config()
        
        except Exception as e:
            logger.error(f"자동매매 설정 조회 중 오류: {str(e)}")
            return self.default_config
    
    def _create_default_config(self) -> Dict:
        """기본 설정 생성"""
        try:
            config = {**self.default_config, "updated_at": datetime.now().isoformat()}
            response = supabase.table("auto_trading_config").insert(config).execute()
            return response.data[0] if response.data else self.default_config
        except Exception as e:
            logger.error(f"기본 설정 생성 중 오류: {str(e)}")
            return self.default_config
    
    def update_auto_trading_config(self, config: Dict) -> Dict:
        """자동매매 설정 업데이트"""
        try:
            current_config = self.get_auto_trading_config()
            
            # 설정 업데이트
            updated_config = {**current_config, **config, "updated_at": datetime.now().isoformat()}
            
            if "id" in current_config:
                # 기존 설정 업데이트
                response = supabase.table("auto_trading_config") \
                    .update(updated_config) \
                    .eq("id", current_config["id"]) \
                    .execute()
            else:
                # 새로운 설정 생성
                response = supabase.table("auto_trading_config").insert(updated_config).execute()
            
            return {"success": True, "config": response.data[0] if response.data else updated_config}
        
        except Exception as e:
            logger.error(f"자동매매 설정 업데이트 중 오류: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def get_buy_candidates(self, config: Optional[Dict] = None) -> List[Dict]:
        """매수 추천 종목 조회"""
        if config is None:
            config = self.get_auto_trading_config()
        
        try:
            # 통합 추천 데이터 가져오기 (서비스 호출 시에는 Slack 알림을 보내지 않음)
            recommendations = self.stock_service.get_combined_recommendations_with_technical_and_sentiment(send_slack_notification=False)
            
            if not recommendations.get("results"):
                return []
            
            # 설정에 따라 필터링
            candidates = []
            for stock in recommendations["results"]:
                # 종합 점수 필터링
                if stock.get("composite_score", 0) < config.get("min_composite_score", 70):
                    continue
                
                # 감정 분석 필터링 (설정이 활성화된 경우)
                if config.get("use_sentiment", True):
                    sentiment_score = stock.get("sentiment_score")
                    if sentiment_score is None or sentiment_score < config.get("min_sentiment_score", 0.15):
                        continue
                
                candidates.append(stock)
            
            # 종합 점수 기준 정렬 (높은 순)
            candidates.sort(key=lambda x: x.get("composite_score", 0), reverse=True)
            
            # 최대 매수 종목 수 제한
            max_stocks = config.get("max_stocks_to_buy", 5)
            return candidates[:max_stocks]
        
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
            max_buy_amount = float(output.get("max_ord_psbl_amt", 0))
            
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
                if ticker in holding_tickers:
                    logger.info(f"{ticker} - 이미 보유 중, 스킵")
                    continue
                
                # 현재가 조회
                exchange_code = self._get_exchange_code(ticker)
                price_result = get_current_price({
                    "EXCD": exchange_code.replace("D", "S"),  # NASD -> NAS
                    "SYMB": ticker
                })
                
                if price_result.get("rt_cd") != "0":
                    logger.error(f"{ticker} - 현재가 조회 실패")
                    continue
                
                current_price = float(price_result.get("output", {}).get("last", 0))
                if current_price <= 0:
                    logger.error(f"{ticker} - 유효하지 않은 가격")
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
                    "ORD_DVSN": config.get("order_type", "00")
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
                    "ORD_DVSN": config.get("order_type", "00")
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
                    quantity = float(item.get("ovrs_cblc_qty", 0))
                    current_price = float(item.get("now_pric2", 0))
                    total_value += quantity * current_price
            
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
        """주문 기록 저장"""
        try:
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
                "created_at": datetime.now().isoformat()
            }
            
            supabase.table("auto_trading_logs").insert(log_data).execute()
        
        except Exception as e:
            logger.error(f"주문 기록 저장 중 오류: {str(e)}")
    
    def _get_recent_orders(self, days: int = 7) -> List[Dict]:
        """최근 주문 내역 조회"""
        try:
            start_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            response = supabase.table("auto_trading_logs") \
                .select("*") \
                .gte("created_at", start_date) \
                .order("created_at", desc=True) \
                .execute()
            
            return response.data if response.data else []
        
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

