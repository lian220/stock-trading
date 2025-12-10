"""Stock 엔티티"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Stock:
    """주식 엔티티"""
    ticker: str
    stock_name: str
    price: Optional[float] = None
    date: Optional[datetime] = None
    is_active: bool = True
    is_etf: bool = False
    
    def calculate_return(self, previous_price: float) -> Optional[float]:
        """수익률 계산"""
        if not self.price or previous_price == 0:
            return None
        return (self.price - previous_price) / previous_price


@dataclass
class EconomicData:
    """경제 지표 데이터 엔티티"""
    date: datetime
    indicators: dict[str, float]
    
    def get_indicator(self, name: str) -> Optional[float]:
        """특정 지표 값 조회"""
        return self.indicators.get(name)


@dataclass
class StockRecommendation:
    """주식 추천 엔티티"""
    stock_name: str
    ticker: str
    date: datetime
    sma20: float
    sma50: float
    rsi: float
    macd: float
    signal: float
    golden_cross: bool
    macd_buy_signal: bool
    is_recommended: bool
    composite_score: Optional[float] = None
    sentiment_score: Optional[float] = None
