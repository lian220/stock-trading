"""
트레일링 스톱 서비스
- 트레일링 스톱 설정 관리
- 최고가 갱신 및 동적 익절가 계산
- 트레일링 스톱 조건 확인
"""

import logging
from datetime import datetime
from typing import List, Dict, Optional
from bson import ObjectId
from app.db.mongodb import get_db

logger = logging.getLogger(__name__)

class TrailingStopService:
    """트레일링 스톱 서비스 클래스"""
    
    def __init__(self, user_id: Optional[str] = None):
        """
        트레일링 스톱 서비스 초기화
        
        Args:
            user_id: 사용자 ID. None이면 기본 사용자 ID 사용
        """
        from app.utils.user_context import get_current_user_id
        self.user_id = user_id or get_current_user_id()
        self._auto_trading_service = None

    @property
    def auto_trading_service(self):
        if self._auto_trading_service is None:
            from app.services.auto_trading_service import AutoTradingService
            self._auto_trading_service = AutoTradingService()
        return self._auto_trading_service
    
    def initialize_trailing_stop(
        self, 
        ticker: str, 
        purchase_price: float, 
        purchase_date: datetime,
        is_leveraged: bool = False,
        stock_name: Optional[str] = None,
        trailing_distance_percent: Optional[float] = None
    ) -> Dict:
        """
        매수 시 트레일링 스톱 레코드 초기화
        
        Args:
            ticker: 종목 티커
            purchase_price: 구매가
            purchase_date: 매수일
            is_leveraged: 레버리지 종목 여부
            stock_name: 종목명
            trailing_distance_percent: 트레일링 거리 (%). None이면 설정값 또는 기본값 사용
        
        Returns:
            생성된 TrailingStop 레코드
        """
        db = get_db()
        if db is None:
            logger.error("MongoDB 연결 실패 - 트레일링 스톱 초기화 불가")
            return {}
        
        # 설정에서 트레일링 거리 가져오기 (레버리지 여부에 따라 다름)
        config = self.auto_trading_service.get_auto_trading_config()
        
        if trailing_distance_percent is None:
            if is_leveraged:
                # 레버리지: 기본값 7-10%
                trailing_distance_percent = config.get("leveraged_trailing_stop_distance_percent", 7.0)
            else:
                # 일반: 기본값 5%
                trailing_distance_percent = config.get("trailing_stop_distance_percent", 5.0)
            
        initial_highest_price = purchase_price
        initial_stop_price = purchase_price * (1 - trailing_distance_percent / 100)
        
        trailing_stop = {
            "user_id": self.user_id,
            "ticker": ticker,
            "stock_name": stock_name,
            "purchase_price": purchase_price,
            "purchase_date": purchase_date,
            "highest_price": initial_highest_price,
            "highest_price_date": purchase_date,
            "trailing_distance_percent": trailing_distance_percent,
            "dynamic_stop_price": initial_stop_price,
            "is_leveraged": is_leveraged,
            "is_active": True,
            "last_updated": datetime.utcnow(),
            "created_at": datetime.utcnow()
        }
        
        # upsert로 처리 (이미 존재하면 업데이트, 없으면 생성)
        db.trailing_stops.update_one(
            {"user_id": self.user_id, "ticker": ticker},
            {"$set": trailing_stop},
            upsert=True
        )
        
        logger.info(f"트레일링 스톱 초기화: {ticker}, 구매가: ${purchase_price:.2f}, 동적 익절가: ${initial_stop_price:.2f}")
        return trailing_stop

    def update_highest_price(self, ticker: str, current_price: float) -> Optional[Dict]:
        """
        최고가 갱신 및 동적 익절가 재계산
        
        Args:
            ticker: 종목 티커
            current_price: 현재가
        
        Returns:
            갱신된 TrailingStop 정보
        """
        db = get_db()
        if db is None:
            return None
            
        # 트레일링 스톱 레코드 조회
        trailing_stop = db.trailing_stops.find_one({
            "user_id": self.user_id,
            "ticker": ticker,
            "is_active": True
        })
        
        if not trailing_stop:
            return None
        
        current_highest = trailing_stop["highest_price"]
        
        # 현재가가 최고가보다 높으면 갱신
        if current_price > current_highest:
            new_highest = current_price
            new_stop_price = new_highest * (1 - trailing_stop["trailing_distance_percent"] / 100)
            
            # 동적 익절가는 절대 하향 조정하지 않음
            # (현재 동적 익절가보다 낮으면 갱신하지 않음)
            if new_stop_price > trailing_stop["dynamic_stop_price"]:
                db.trailing_stops.update_one(
                    {"_id": trailing_stop["_id"]},
                    {
                        "$set": {
                            "highest_price": new_highest,
                            "highest_price_date": datetime.utcnow(),
                            "dynamic_stop_price": new_stop_price,
                            "last_updated": datetime.utcnow()
                        }
                    }
                )
                
                logger.info(
                    f"트레일링 스톱 최고가 갱신: {ticker} "
                    f"최고가: ${current_highest:.2f} → ${new_highest:.2f}, "
                    f"동적 익절가: ${trailing_stop['dynamic_stop_price']:.2f} → ${new_stop_price:.2f}"
                )
                return db.trailing_stops.find_one({"_id": trailing_stop["_id"]})
        
        return trailing_stop

    def check_trailing_stop_triggered(self, ticker: str, current_price: float) -> bool:
        """
        트레일링 스톱 조건 충족 여부 확인
        
        Args:
            ticker: 종목 티커
            current_price: 현재가
        
        Returns:
            트레일링 스톱 조건 충족 여부
        """
        db = get_db()
        if db is None:
            return False
            
        trailing_stop = db.trailing_stops.find_one({
            "user_id": self.user_id,
            "ticker": ticker,
            "is_active": True
        })
        
        if not trailing_stop:
            return False
        
        # 설정 확인
        config = self.auto_trading_service.get_auto_trading_config()
        if not config.get("trailing_stop_enabled", False):
            return False
            
        # 레버리지 여부에 따라 다른 최소 수익률 적용
        is_leveraged = trailing_stop.get("is_leveraged", False)
        if is_leveraged:
            min_profit_percent = config.get("leveraged_trailing_stop_min_profit_percent", 5.0)
        else:
            min_profit_percent = config.get("trailing_stop_min_profit_percent", 3.0)
        
        purchase_price = trailing_stop["purchase_price"]
        current_profit_percent = ((current_price - purchase_price) / purchase_price) * 100
        
        # 최소 수익률 미만이면 트레일링 스톱 비활성화 (트리거 안 됨)
        if current_profit_percent < min_profit_percent:
            return False
        
        # 현재가가 동적 익절가 이하로 떨어졌는지 확인
        dynamic_stop_price = trailing_stop["dynamic_stop_price"]
        
        return current_price <= dynamic_stop_price

    def deactivate_trailing_stop(self, ticker: str):
        """
        매도 시 트레일링 스톱 비활성화
        
        Args:
            ticker: 종목 티커
        """
        db = get_db()
        if db is None:
            return
            
        db.trailing_stops.update_one(
            {"user_id": self.user_id, "ticker": ticker},
            {
                "$set": {
                    "is_active": False,
                    "last_updated": datetime.utcnow()
                }
            }
        )
        
        logger.info(f"트레일링 스톱 비활성화: {ticker}")

    def get_trailing_stop_info(self, ticker: str) -> Optional[Dict]:
        """트레일링 스톱 정보 조회"""
        db = get_db()
        if db is None:
            return None
            
        return db.trailing_stops.find_one({
            "user_id": self.user_id,
            "ticker": ticker,
            "is_active": True
        })

    def get_active_trailing_stops(self) -> List[str]:
        """활성화된 트레일링 스톱 티커 목록 조회"""
        db = get_db()
        if db is None:
            return []
            
        cursor = db.trailing_stops.find(
            {"user_id": self.user_id, "is_active": True},
            {"ticker": 1}
        )
        return [doc["ticker"] for doc in cursor]
