"""MongoDB를 사용한 Economic Data Repository 구현"""
from typing import List, Optional
from datetime import datetime
import logging
from app.domain.entities.stock import EconomicData
from app.domain.repositories.stock_repository import IEconomicDataRepository
from app.infrastructure.database.mongodb_client import get_sync_mongodb_client

logger = logging.getLogger(__name__)


class MongodbEconomicRepository(IEconomicDataRepository):
    """MongoDB를 사용한 Economic Data Repository 구현"""
    
    def __init__(self):
        _, self._db = get_sync_mongodb_client()
        if not self._db:
            raise ValueError("MongoDB 클라이언트를 초기화할 수 없습니다.")
    
    async def get_economic_data(
        self, 
        start_date: datetime, 
        end_date: datetime,
        columns: Optional[List[str]] = None
    ) -> List[EconomicData]:
        """경제 데이터 조회"""
        try:
            query = {
                "date": {
                    "$gte": start_date,
                    "$lte": end_date
                }
            }
            
            cursor = self._db.daily_stock_data.find(query).sort("date", 1)
            
            economic_data_list = []
            for doc in cursor:
                date = doc.get("date")
                if isinstance(date, str):
                    from datetime import datetime
                    date = datetime.fromisoformat(date.replace('Z', '+00:00'))
                
                indicators = {}
                # 모든 필드를 indicators로 변환 (date 제외)
                for key, value in doc.items():
                    if key != "date" and key != "_id" and value is not None:
                        indicators[key] = value
                
                economic_data_list.append(EconomicData(date=date, indicators=indicators))
            
            return economic_data_list
        except Exception as e:
            logger.error(f"경제 데이터 조회 중 오류 발생: {e}")
            return []
    
    async def get_last_updated_date(self) -> Optional[datetime]:
        """마지막 업데이트 날짜 조회"""
        try:
            last_doc = self._db.daily_stock_data.find_one(
                sort=[("date", -1)]
            )
            
            if last_doc and "date" in last_doc:
                date = last_doc["date"]
                if isinstance(date, str):
                    from datetime import datetime
                    return datetime.fromisoformat(date.replace('Z', '+00:00'))
                return date
            return None
        except Exception as e:
            logger.error(f"마지막 업데이트 날짜 조회 중 오류 발생: {e}")
            return None
    
    async def save_economic_data(self, data: EconomicData) -> EconomicData:
        """경제 데이터 저장"""
        try:
            data_dict = {"date": data.date}
            data_dict.update(data.indicators)
            data_dict["created_at"] = datetime.utcnow()
            data_dict["updated_at"] = datetime.utcnow()
            
            self._db.daily_stock_data.insert_one(data_dict)
            return data
        except Exception as e:
            logger.error(f"경제 데이터 저장 중 오류 발생: {e}")
            raise
    
    async def update_economic_data(self, data: EconomicData) -> EconomicData:
        """경제 데이터 업데이트"""
        try:
            update_dict = {k: v for k, v in data.indicators.items() if v is not None}
            update_dict["updated_at"] = datetime.utcnow()
            
            if update_dict:
                self._db.daily_stock_data.update_one(
                    {"date": data.date},
                    {
                        "$set": update_dict,
                        "$setOnInsert": {
                            "created_at": datetime.utcnow()
                        }
                    },
                    upsert=True
                )
            return data
        except Exception as e:
            logger.error(f"경제 데이터 업데이트 중 오류 발생: {e}")
            raise
