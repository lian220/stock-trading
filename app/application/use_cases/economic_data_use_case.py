"""경제 데이터 Use Cases"""
from typing import List, Optional
from datetime import datetime, timedelta
import logging
from app.domain.entities.stock import EconomicData
from app.domain.repositories.stock_repository import IEconomicDataRepository
from app.core.config import settings

logger = logging.getLogger(__name__)


class EconomicDataUseCase:
    """경제 데이터 Use Case"""
    
    def __init__(self, repository: IEconomicDataRepository):
        self.repository = repository
    
    async def get_last_updated_date(self) -> Optional[datetime]:
        """마지막 업데이트 날짜 조회"""
        return await self.repository.get_last_updated_date()
    
    async def get_economic_data(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        columns: Optional[List[str]] = None
    ) -> List[EconomicData]:
        """경제 데이터 조회"""
        if start_date is None:
            # 기본값: 6개월 전
            start_date = datetime.now() - timedelta(days=180)
        if end_date is None:
            end_date = datetime.now()
        
        return await self.repository.get_economic_data(start_date, end_date, columns)
    
    async def save_economic_data(self, data: EconomicData) -> EconomicData:
        """경제 데이터 저장"""
        return await self.repository.save_economic_data(data)
    
    async def update_economic_data(self, data: EconomicData) -> EconomicData:
        """경제 데이터 업데이트"""
        return await self.repository.update_economic_data(data)
