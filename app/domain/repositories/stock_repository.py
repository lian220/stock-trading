"""Stock Repository 인터페이스"""
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime
from app.domain.entities.stock import Stock, EconomicData, StockRecommendation


class IStockRepository(ABC):
    """Stock Repository 인터페이스"""
    
    @abstractmethod
    async def get_stock_by_ticker(self, ticker: str) -> Optional[Stock]:
        """티커로 주식 조회"""
        pass
    
    @abstractmethod
    async def get_all_active_stocks(self) -> List[Stock]:
        """활성화된 모든 주식 조회"""
        pass
    
    @abstractmethod
    async def get_stock_mapping(self) -> dict[str, str]:
        """주식명-티커 매핑 조회"""
        pass
    
    @abstractmethod
    async def save_stock(self, stock: Stock) -> Stock:
        """주식 저장"""
        pass


class IEconomicDataRepository(ABC):
    """경제 데이터 Repository 인터페이스"""
    
    @abstractmethod
    async def get_economic_data(
        self, 
        start_date: datetime, 
        end_date: datetime,
        columns: Optional[List[str]] = None
    ) -> List[EconomicData]:
        """경제 데이터 조회"""
        pass
    
    @abstractmethod
    async def get_last_updated_date(self) -> Optional[datetime]:
        """마지막 업데이트 날짜 조회"""
        pass
    
    @abstractmethod
    async def save_economic_data(self, data: EconomicData) -> EconomicData:
        """경제 데이터 저장"""
        pass
    
    @abstractmethod
    async def update_economic_data(self, data: EconomicData) -> EconomicData:
        """경제 데이터 업데이트"""
        pass


class IStockRecommendationRepository(ABC):
    """주식 추천 Repository 인터페이스"""
    
    @abstractmethod
    async def get_recommendations(
        self, 
        date: Optional[datetime] = None
    ) -> List[StockRecommendation]:
        """추천 목록 조회"""
        pass
    
    @abstractmethod
    async def save_recommendations(
        self, 
        recommendations: List[StockRecommendation]
    ) -> List[StockRecommendation]:
        """추천 목록 저장"""
        pass
    
    @abstractmethod
    async def delete_recommendations_by_date(self, date: datetime) -> bool:
        """특정 날짜의 추천 삭제"""
        pass
