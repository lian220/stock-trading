from pydantic import Field
from pydantic_settings import BaseSettings
from typing import List, Optional, Union, Literal, get_type_hints
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

class Settings(BaseSettings):
    PROJECT_NAME: str = "주식 분석 API"
    PROJECT_DESCRIPTION: str = "해외주식 잔고 조회 및 주식 예측 API"
    PROJECT_VERSION: str = "1.0.0"
    
    # DEBUG 설정 추가
    DEBUG: bool = Field(default=False, description="디버그 모드 활성화 여부")
    
    CORS_ORIGINS: List[str] = ["*"]
    
    SUPABASE_URL: str = os.getenv("SUPABASE_URL")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY")
    
    # 한국투자증권 API 설정
    KIS_BASE_URL: str = Field(
        default="https://openapivts.koreainvestment.com:29443", 
        description="한국투자증권 API 기본 URL (모의투자용)"
    )
    KIS_REAL_URL: str = Field(
        default="https://openapi.koreainvestment.com:9443", 
        description="한국투자증권 API 기본 URL (실제투자용)"
    )
    KIS_APPKEY: str = Field(..., description="한국투자증권 API 앱키")
    KIS_APPSECRET: str = Field(..., description="한국투자증권 API 앱시크릿")
    KIS_CANO: str = os.getenv("KIS_CANO", "")  # 환경변수에서 읽어오되, 없으면 기본값 사용
    KIS_ACNT_PRDT_CD: str = os.getenv("KIS_ACNT_PRDT_CD", "01")  # 환경변수에서 읽어오되, 없으면 기본값 사용
    KIS_USE_MOCK: bool = Field(
        default=False,
        description="모의투자 사용 여부 (.env에서 KIS_USE_MOCK=true/false로 설정 가능)"
    )

    ALPHA_VANTAGE_API_KEY: str = os.getenv("ALPHA_VANTAGE_API_KEY", "")
    TR_ID: str = os.getenv("TR_ID")
    
    # Slack 알림 설정
    SLACK_WEBHOOK_URL_TRADING: Optional[str] = Field(
        default=None,
        description="Slack Webhook URL (매수/매도 알림용)"
    )
    SLACK_WEBHOOK_URL_ANALYSIS: Optional[str] = Field(
        default=None,
        description="Slack Webhook URL (주식 분석/추천 알림용)"
    )
    SLACK_ENABLED: bool = Field(
        default=False,
        description="Slack 알림 활성화 여부"
    )
    
    # 서버 시작 시 경제 데이터 수집 실행 여부
    RUN_ECONOMIC_DATA_ON_STARTUP: bool = Field(
        default=False,
        description="서버 시작 시 경제 데이터 수집 실행 여부 (.env에서 RUN_ECONOMIC_DATA_ON_STARTUP=true/false로 설정 가능)"
    )
    
    @property
    def kis_base_url(self) -> str:
        """사용할 한국투자증권 API URL 반환"""
        return self.KIS_BASE_URL if self.KIS_USE_MOCK else self.KIS_REAL_URL

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

# 싱글톤 설정 객체 생성
settings = Settings()