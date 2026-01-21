"""
자동매매 관련 Pydantic 스키마 모델
"""

from pydantic import BaseModel, Field
from typing import Optional


class AutoTradingConfigUpdate(BaseModel):
    """자동매매 설정 업데이트 요청"""
    enabled: Optional[bool] = Field(None, description="자동매매 활성화 여부")
    auto_trading_enabled: Optional[bool] = Field(None, description="자동매매 활성화 여부 (계정 단위)")
    min_composite_score: Optional[float] = Field(None, ge=0, le=100, description="최소 종합 점수 (0-100)")
    max_stocks_to_buy: Optional[int] = Field(None, ge=1, le=20, description="최대 매수 종목 수 (1-20)")
    max_amount_per_stock: Optional[float] = Field(None, ge=100, description="종목당 최대 매수 금액 (USD)")
    stop_loss_percent: Optional[float] = Field(None, le=0, description="손절 기준 (%) - 음수 값")
    take_profit_percent: Optional[float] = Field(None, ge=0, description="익절 기준 (%) - 양수 값")
    use_sentiment: Optional[bool] = Field(None, description="감정 분석 사용 여부")
    min_sentiment_score: Optional[float] = Field(None, ge=-1, le=1, description="최소 감정 점수 (-1 ~ 1)")
    order_type: Optional[str] = Field(None, description="주문 구분 (00: 지정가)")
    allow_buy_existing_stocks: Optional[bool] = Field(None, description="보유 중인 종목도 매수 허용 여부")


class AutoTradingExecuteRequest(BaseModel):
    """자동매매 실행 요청"""
    dry_run: bool = Field(False, description="테스트 모드 (실제 주문 없이 시뮬레이션)")
    

class BacktestRequest(BaseModel):
    """백테스팅 요청"""
    start_date: str = Field(..., description="시작 날짜 (YYYY-MM-DD)")
    end_date: str = Field(..., description="종료 날짜 (YYYY-MM-DD)")
    initial_capital: float = Field(100000.0, ge=1000, description="초기 자본금 (USD)")

