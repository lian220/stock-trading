"""
MongoDB 데이터 모델 정의

Pydantic 모델을 사용하여 MongoDB 문서의 구조를 정의합니다.
"""
from pydantic import BaseModel, Field, field_serializer
from pydantic.json_schema import GetJsonSchemaHandler
from pydantic_core import core_schema
from typing import Optional, List, Dict, Any, Annotated
from datetime import datetime
from bson import ObjectId


class PyObjectId(ObjectId):
    """ObjectId를 문자열로 직렬화하기 위한 클래스 (Pydantic v2 호환)"""
    
    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler
    ) -> core_schema.CoreSchema:
        def validate_from_str(value: Any) -> ObjectId:
            if isinstance(value, ObjectId):
                return value
            if isinstance(value, str):
                if ObjectId.is_valid(value):
                    return ObjectId(value)
                raise ValueError("Invalid ObjectId string")
            raise ValueError("Invalid ObjectId type")
        
        return core_schema.union_schema([
            core_schema.is_instance_schema(ObjectId),
            core_schema.chain_schema([
                core_schema.str_schema(),
                core_schema.no_info_plain_validator_function(validate_from_str),
            ])
        ])
    
    @classmethod
    def __get_pydantic_json_schema__(
        cls, _core_schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> Dict[str, Any]:
        """JSON 스키마 생성 - 문자열로 표시"""
        return {"type": "string", "format": "objectid"}


# ============= Stocks =============

class Stock(BaseModel):
    """종목 기본 정보"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    ticker: str
    stock_name: str
    stock_name_en: Optional[str] = None
    is_etf: bool = False
    leverage_ticker: Optional[str] = None  # 레버리지 티커 심볼 (종목 정보)
    exchange: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    @field_serializer('id', when_used='json')
    def serialize_id(self, value: Optional[PyObjectId]) -> Optional[str]:
        return str(value) if value else None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


# ============= Users =============

class UserPreferences(BaseModel):
    """사용자 선호 설정"""
    default_currency: str = "USD"
    notification_enabled: bool = True


class UserStockEmbedded(BaseModel):
    """사용자 문서에 embedded되는 종목 정보 (사용자별 고유 정보만 저장)
    
    stocks 컬렉션에 있는 정보(ticker, stock_name, is_etf, leverage_ticker 등)는 
    stocks 컬렉션을 참조하여 조회합니다.
    
    Note: 실제 seed 스크립트에서는 stock_name, leverage_ticker 등도 embedded되지만,
    모델에서는 사용자별 고유 정보만 정의합니다.
    """
    ticker: str  # stocks 컬렉션 참조용
    use_leverage: bool = False  # 사용자별 레버리지 사용 여부
    notes: Optional[str] = None  # 사용자 메모
    tags: Optional[List[str]] = Field(default_factory=list)  # 사용자 정의 태그
    is_active: bool = True  # 사용자별 활성화 여부 (stocks.is_active와 독립적)
    added_at: Optional[datetime] = Field(default_factory=datetime.utcnow)  # 관심 종목 추가 일시
    # 실제 데이터에는 stock_name, leverage_ticker 등도 포함되지만, 
    # 이는 stocks 컬렉션 참조용이므로 모델에서는 생략


class User(BaseModel):
    """사용자 정보 (MongoDB embedded 구조)"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: str  # UUID 또는 이메일
    email: Optional[str] = None
    display_name: Optional[str] = None
    preferences: Optional[UserPreferences] = Field(default_factory=UserPreferences)
    stocks: Optional[List[UserStockEmbedded]] = Field(default_factory=list)  # 👈 embedded stocks
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


# ============= Stock Prices =============

class StockPrice(BaseModel):
    """일일 주가 데이터"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    date: datetime
    ticker: str
    stock_id: Optional[str] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: float
    adjusted_close: Optional[float] = None
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


# ============= Stock Volumes =============

class StockVolume(BaseModel):
    """일일 거래량 데이터"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    date: datetime
    ticker: str
    stock_id: Optional[str] = None
    volume: int
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


# ============= Stock Predictions =============

class StockPrediction(BaseModel):
    """주가 예측 데이터"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    date: datetime
    ticker: str
    stock_id: Optional[str] = None
    predicted_price: float
    actual_price: Optional[float] = None
    forecast_horizon: int = 30  # 예측 기간 (일)
    model_version: Optional[str] = None
    confidence_score: Optional[float] = None
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


# ============= Economic Data =============

class EconomicData(BaseModel):
    """경제 지표 데이터"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    date: datetime
    indicators: Dict[str, Optional[float]]  # 동적 경제 지표
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


# ============= Stock Recommendations =============

class TechnicalIndicators(BaseModel):
    """기술적 지표"""
    sma20: Optional[float] = None
    sma50: Optional[float] = None
    golden_cross: Optional[bool] = None
    rsi: Optional[float] = None
    macd: Optional[float] = None
    signal: Optional[float] = None
    macd_buy_signal: Optional[bool] = None


class StockRecommendation(BaseModel):
    """종목 추천 데이터"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    date: str  # YYYY-MM-DD 형식
    ticker: str
    stock_id: Optional[str] = None
    user_id: Optional[str] = None  # null이면 전역 추천
    technical_indicators: Optional[TechnicalIndicators] = None
    recommendation_score: Optional[float] = None
    is_recommended: bool = False
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


# ============= Stock Analysis =============

class AnalysisMetrics(BaseModel):
    """분석 지표"""
    mae: Optional[float] = None
    mse: Optional[float] = None
    rmse: Optional[float] = None
    mape: Optional[float] = None
    accuracy: Optional[float] = None


class AnalysisPredictions(BaseModel):
    """예측 정보"""
    last_actual_price: Optional[float] = None
    predicted_future_price: Optional[float] = None
    predicted_rise: Optional[bool] = None
    rise_probability: Optional[float] = None


class StockAnalysis(BaseModel):
    """AI 분석 결과"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    date: datetime
    ticker: str
    stock_id: Optional[str] = None
    user_id: Optional[str] = None  # null이면 전역 분석
    metrics: Optional[AnalysisMetrics] = None
    predictions: Optional[AnalysisPredictions] = None
    recommendation: Optional[str] = None
    analysis: Optional[str] = None
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


# ============= Sentiment Analysis =============

class SentimentAnalysis(BaseModel):
    """감정 분석 결과"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    ticker: str
    date: str  # YYYY-MM-DD 형식
    stock_id: Optional[str] = None
    average_sentiment_score: float
    article_count: int
    calculation_date: datetime
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


# ============= Trading Config =============

class TradingConfig(BaseModel):
    """자동매매 설정"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: str
    enabled: bool = False
    min_composite_score: float = 70.0
    max_stocks_to_buy: int = 5
    max_amount_per_stock: float = 10000.0
    stop_loss_percent: float = -7.0
    take_profit_percent: float = 5.0
    use_sentiment: bool = True
    min_sentiment_score: float = 0.15
    order_type: str = "00"
    allow_buy_existing_stocks: bool = True  # 보유 중인 종목도 매수 허용 여부
    trailing_stop_enabled: bool = False
    trailing_stop_distance_percent: float = 5.0
    trailing_stop_min_profit_percent: float = 3.0
    leveraged_trailing_stop_distance_percent: float = 10.0
    leveraged_trailing_stop_min_profit_percent: float = 5.0
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


# ============= Trailing Stop =============

class TrailingStop(BaseModel):
    """트레일링 스톱 정보"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: str = "lian"  # 기본값
    ticker: str
    stock_name: Optional[str] = None
    purchase_price: float
    purchase_date: datetime
    highest_price: float  # 초기값은 purchase_price
    highest_price_date: datetime  # 초기값은 purchase_date
    trailing_distance_percent: float = 5.0  # 기본값 5%
    dynamic_stop_price: float  # highest_price * (1 - trailing_distance_percent / 100)
    is_leveraged: bool = False
    is_active: bool = True
    last_updated: Optional[datetime] = Field(default_factory=datetime.utcnow)
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    @field_serializer('id', when_used='json')
    def serialize_id(self, value: Optional[PyObjectId]) -> Optional[str]:
        return str(value) if value else None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


# ============= Trading Log =============

class TradingLog(BaseModel):
    """거래 로그"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: str
    order_type: str  # "buy" | "sell"
    ticker: str
    stock_id: Optional[str] = None
    stock_name: Optional[str] = None
    price: Optional[float] = None
    quantity: Optional[int] = None
    status: str  # "success" | "failed" | "dry_run"
    composite_score: Optional[float] = None
    price_change_percent: Optional[float] = None
    sell_reasons: Optional[List[str]] = Field(default_factory=list)
    order_result: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
