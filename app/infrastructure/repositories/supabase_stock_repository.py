"""Supabase를 사용한 Stock Repository 구현"""
from typing import List, Optional
from datetime import datetime
import logging
from app.domain.entities.stock import Stock
from app.domain.repositories.stock_repository import IStockRepository
from app.infrastructure.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class SupabaseStockRepository(IStockRepository):
    """Supabase를 사용한 Stock Repository 구현"""
    
    def __init__(self):
        self._client = get_supabase_client()
        if not self._client:
            raise ValueError("Supabase 클라이언트를 초기화할 수 없습니다.")
    
    async def get_stock_by_ticker(self, ticker: str) -> Optional[Stock]:
        """티커로 주식 조회 - MongoDB 사용 (stock_ticker_mapping 제거됨)"""
        logger.warning("SupabaseStockRepository.get_stock_by_ticker는 더 이상 사용되지 않습니다. MongoDB를 사용하세요.")
        return None
    
    async def get_all_active_stocks(self) -> List[Stock]:
        """활성화된 모든 주식 조회 - MongoDB 사용 (stock_ticker_mapping 제거됨)"""
        logger.warning("SupabaseStockRepository.get_all_active_stocks는 더 이상 사용되지 않습니다. MongoDB를 사용하세요.")
        return []
    
    async def get_stock_mapping(self) -> dict[str, str]:
        """주식명-티커 매핑 조회 - MongoDB 사용 (stock_ticker_mapping 제거됨)"""
        logger.warning("SupabaseStockRepository.get_stock_mapping는 더 이상 사용되지 않습니다. MongoDB를 사용하세요.")
        return {}
    
    async def save_stock(self, stock: Stock) -> Stock:
        """주식 저장 - MongoDB 사용 (stock_ticker_mapping 제거됨)"""
        logger.warning("SupabaseStockRepository.save_stock는 더 이상 사용되지 않습니다. MongoDB를 사용하세요.")
        raise NotImplementedError("stock_ticker_mapping 테이블은 제거되었습니다. MongoDB stocks 컬렉션을 사용하세요.")
