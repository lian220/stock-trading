"""Stock Use Cases"""
from typing import List, Optional
import logging
from app.domain.entities.stock import Stock
from app.domain.repositories.stock_repository import IStockRepository

logger = logging.getLogger(__name__)


class StockUseCase:
    """Stock Use Case"""
    
    def __init__(self, repository: IStockRepository):
        self.repository = repository
    
    async def get_stock_by_ticker(self, ticker: str) -> Optional[Stock]:
        """티커로 주식 조회"""
        return await self.repository.get_stock_by_ticker(ticker)
    
    async def get_all_active_stocks(self) -> List[Stock]:
        """활성화된 모든 주식 조회"""
        return await self.repository.get_all_active_stocks()
    
    async def get_stock_mapping(self) -> dict[str, str]:
        """주식명-티커 매핑 조회"""
        return await self.repository.get_stock_mapping()
    
    async def save_stock(self, stock: Stock) -> Stock:
        """주식 저장"""
        return await self.repository.save_stock(stock)
