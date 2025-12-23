"""
주식 관련 API 스키마 정의

API 요청/응답용 스키마를 정의합니다.
DB 모델은 app.models.mongodb_models를 참조하세요.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime


class StockPrediction(BaseModel):
    """주식 예측 결과 스키마"""
    stock: str
    last_price: float
    predicted_price: float
    rise_probability: float
    recommendation: str
    analysis: str


class UpdateResponse(BaseModel):
    """업데이트 응답 스키마"""
    success: bool
    message: str
    total_records: int = 0
    updated_records: int = 0


class StockCreate(BaseModel):
    """종목 생성 요청 스키마 (API 요청용)"""
    ticker: str = Field(..., description="종목 티커")
    stock_name: str = Field(..., description="종목명")
    stock_name_en: Optional[str] = Field(None, description="영문 종목명")
    is_etf: bool = Field(False, description="ETF 여부")
    leverage_ticker: Optional[str] = Field(None, description="레버리지 티커 심볼")
    exchange: Optional[str] = Field(None, description="거래소")
    sector: Optional[str] = Field(None, description="섹터")
    industry: Optional[str] = Field(None, description="산업")
    is_active: bool = Field(True, description="활성화 여부")


class StockUpdate(BaseModel):
    """종목 정보 업데이트 요청 스키마 (ticker 제외)"""
    stock_name: Optional[str] = Field(None, description="종목명")
    stock_name_en: Optional[str] = Field(None, description="영문 종목명")
    is_etf: Optional[bool] = Field(None, description="ETF 여부")
    leverage_ticker: Optional[str] = Field(None, description="레버리지 티커 심볼")
    exchange: Optional[str] = Field(None, description="거래소")
    sector: Optional[str] = Field(None, description="섹터")
    industry: Optional[str] = Field(None, description="산업")
    is_active: Optional[bool] = Field(None, description="활성화 여부")


class StockResponse(BaseModel):
    """종목 정보 응답 스키마"""
    id: Optional[str] = Field(None, alias="_id", description="MongoDB ObjectId")
    ticker: str
    stock_name: str
    stock_name_en: Optional[str] = None
    is_etf: bool = False
    leverage_ticker: Optional[str] = None
    exchange: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True