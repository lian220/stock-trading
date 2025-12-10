"""Supabase를 사용한 Economic Data Repository 구현"""
from typing import List, Optional
from datetime import datetime
import pandas as pd
import logging
from app.domain.entities.stock import EconomicData
from app.domain.repositories.stock_repository import IEconomicDataRepository
from app.infrastructure.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class SupabaseEconomicRepository(IEconomicDataRepository):
    """Supabase를 사용한 Economic Data Repository 구현"""
    
    def __init__(self):
        self._client = get_supabase_client()
        if not self._client:
            raise ValueError("Supabase 클라이언트를 초기화할 수 없습니다.")
    
    async def get_economic_data(
        self, 
        start_date: datetime, 
        end_date: datetime,
        columns: Optional[List[str]] = None
    ) -> List[EconomicData]:
        """경제 데이터 조회"""
        try:
            start_str = start_date.strftime("%Y-%m-%d")
            end_str = end_date.strftime("%Y-%m-%d")
            
            query = self._client.table("economic_and_stock_data") \
                .select("*") \
                .gte("날짜", start_str) \
                .lte("날짜", end_str) \
                .order("날짜")
            
            response = query.execute()
            
            economic_data_list = []
            for item in response.data:
                date_str = item.get("날짜")
                if date_str:
                    date = pd.to_datetime(date_str).to_pydatetime()
                    # 날짜 필드를 제외한 모든 필드를 indicators로 사용
                    indicators = {k: v for k, v in item.items() if k != "날짜" and v is not None}
                    economic_data_list.append(EconomicData(date=date, indicators=indicators))
            
            return economic_data_list
        except Exception as e:
            logger.error(f"경제 데이터 조회 중 오류 발생: {e}")
            return []
    
    async def get_last_updated_date(self) -> Optional[datetime]:
        """마지막 업데이트 날짜 조회"""
        try:
            response = self._client.table("economic_and_stock_data") \
                .select("날짜") \
                .order("날짜", desc=True) \
                .limit(1) \
                .execute()
            
            if response.data and len(response.data) > 0:
                date_str = response.data[0]["날짜"]
                return pd.to_datetime(date_str).to_pydatetime()
            return None
        except Exception as e:
            logger.error(f"마지막 업데이트 날짜 조회 중 오류 발생: {e}")
            return None
    
    async def save_economic_data(self, data: EconomicData) -> EconomicData:
        """경제 데이터 저장"""
        try:
            data_dict = {"날짜": data.date.strftime("%Y-%m-%d")}
            data_dict.update(data.indicators)
            
            self._client.table("economic_and_stock_data").insert(data_dict).execute()
            return data
        except Exception as e:
            logger.error(f"경제 데이터 저장 중 오류 발생: {e}")
            raise
    
    async def update_economic_data(self, data: EconomicData) -> EconomicData:
        """경제 데이터 업데이트"""
        try:
            date_str = data.date.strftime("%Y-%m-%d")
            update_dict = {k: v for k, v in data.indicators.items() if v is not None}
            
            if update_dict:
                self._client.table("economic_and_stock_data") \
                    .update(update_dict) \
                    .eq("날짜", date_str) \
                    .execute()
            return data
        except Exception as e:
            logger.error(f"경제 데이터 업데이트 중 오류 발생: {e}")
            raise
