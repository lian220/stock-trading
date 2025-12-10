"""MongoDB를 사용한 Stock Repository 구현"""
from typing import List, Optional
from datetime import datetime
import logging
from app.domain.entities.stock import Stock
from app.domain.repositories.stock_repository import IStockRepository
from app.infrastructure.database.mongodb_client import get_sync_mongodb_client

logger = logging.getLogger(__name__)


class MongoDBStockRepository(IStockRepository):
    """MongoDB를 사용한 Stock Repository 구현"""
    
    def __init__(self):
        _, self._db = get_sync_mongodb_client()
        if not self._db:
            raise ValueError("MongoDB 클라이언트를 초기화할 수 없습니다.")
    
    async def get_stock_by_ticker(self, ticker: str) -> Optional[Stock]:
        """티커로 주식 조회"""
        try:
            stock_doc = self._db.stocks.find_one({"ticker": ticker, "is_active": True})
            if stock_doc:
                return Stock(
                    ticker=stock_doc["ticker"],
                    stock_name=stock_doc["stock_name"],
                    is_active=stock_doc.get("is_active", True),
                    is_etf=stock_doc.get("is_etf", False)
                )
            return None
        except Exception as e:
            logger.error(f"주식 조회 중 오류 발생: {e}")
            return None
    
    async def get_all_active_stocks(self) -> List[Stock]:
        """활성화된 모든 주식 조회"""
        try:
            stocks_docs = self._db.stocks.find({"is_active": True})
            stocks = []
            for doc in stocks_docs:
                stocks.append(Stock(
                    ticker=doc["ticker"],
                    stock_name=doc["stock_name"],
                    is_active=doc.get("is_active", True),
                    is_etf=doc.get("is_etf", False)
                ))
            return stocks
        except Exception as e:
            logger.error(f"주식 목록 조회 중 오류 발생: {e}")
            return []
    
    async def get_stock_mapping(self) -> dict[str, str]:
        """주식명-티커 매핑 조회"""
        try:
            stocks_docs = self._db.stocks.find({"is_active": True})
            mapping = {doc["stock_name"]: doc["ticker"] for doc in stocks_docs}
            return mapping
        except Exception as e:
            logger.error(f"주식 매핑 조회 중 오류 발생: {e}")
            return {}
    
    async def save_stock(self, stock: Stock) -> Stock:
        """주식 저장"""
        try:
            data = {
                "ticker": stock.ticker,
                "stock_name": stock.stock_name,
                "is_active": stock.is_active,
                "is_etf": stock.is_etf
            }
            self._db.stocks.insert_one(data)
            return stock
        except Exception as e:
            logger.error(f"주식 저장 중 오류 발생: {e}")
            raise
