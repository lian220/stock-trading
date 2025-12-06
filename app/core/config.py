from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from typing import List, Optional, Union, Literal, get_type_hints
import os
from pathlib import Path
from dotenv import load_dotenv

class Settings(BaseSettings):
    PROJECT_NAME: str = "주식 분석 API"
    PROJECT_DESCRIPTION: str = "해외주식 잔고 조회 및 주식 예측 API"
    PROJECT_VERSION: str = "1.0.0"
    
    # DEBUG 설정 추가
    DEBUG: bool = Field(default=False, description="디버그 모드 활성화 여부")
    
    CORS_ORIGINS: List[str] = ["*"]
    
    SUPABASE_URL: Optional[str] = Field(
        default=None,
        description="Supabase URL"
    )
    SUPABASE_KEY: Optional[str] = Field(
        default=None,
        description="Supabase Key"
    )
    
    # 한국투자증권 API 설정
    KIS_BASE_URL: str = Field(
        default="https://openapivts.koreainvestment.com:29443", 
        description="한국투자증권 API 기본 URL (모의투자용)"
    )
    KIS_REAL_URL: str = Field(
        default="https://openapi.koreainvestment.com:9443", 
        description="한국투자증권 API 기본 URL (실제투자용)"
    )
    KIS_APPKEY: Optional[str] = Field(
        default=None,
        description="한국투자증권 API 앱키"
    )
    KIS_APPSECRET: Optional[str] = Field(
        default=None,
        description="한국투자증권 API 앱시크릿"
    )
    KIS_CANO: str = Field(
        default="",
        description="한국투자증권 계좌번호"
    )
    KIS_ACNT_PRDT_CD: str = Field(
        default="01",
        description="한국투자증권 계좌상품코드"
    )
    KIS_USE_MOCK: bool = Field(
        default=False,
        description="모의투자 사용 여부 (.env에서 KIS_USE_MOCK=true/false로 설정 가능)"
    )

    ALPHA_VANTAGE_API_KEY: str = Field(
        default="",
        description="Alpha Vantage API Key"
    )
    TR_ID: Optional[str] = Field(
        default=None,
        description="TR ID"
    )
    
    # Slack 알림 설정
    SLACK_WEBHOOK_URL_TRADING: Optional[str] = Field(
        default=None,
        description="Slack Webhook URL (매수/매도 알림용)"
    )
    SLACK_WEBHOOK_URL_ANALYSIS: Optional[str] = Field(
        default=None,
        description="Slack Webhook URL (주식 분석/추천 알림용)"
    )
    SLACK_WEBHOOK_URL_SCHEDULER: Optional[str] = Field(
        default=None,
        description="Slack Webhook URL (스케줄러 실행 알림용)"
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
    
    @field_validator('KIS_USE_MOCK', mode='before')
    @classmethod
    def parse_kis_use_mock(cls, v):
        """빈 문자열을 False로 변환"""
        if v == '' or v is None:
            return False
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return bool(v)
    
    @field_validator('DEBUG', mode='before')
    @classmethod
    def parse_debug(cls, v):
        """빈 문자열을 False로 변환"""
        if v == '' or v is None:
            return False
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return bool(v)
    
    @field_validator('SLACK_ENABLED', mode='before')
    @classmethod
    def parse_slack_enabled(cls, v):
        """빈 문자열을 False로 변환"""
        if v == '' or v is None:
            return False
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return bool(v)
    
    @field_validator('RUN_ECONOMIC_DATA_ON_STARTUP', mode='before')
    @classmethod
    def parse_run_economic_data_on_startup(cls, v):
        """빈 문자열을 False로 변환"""
        if v == '' or v is None:
            return False
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return bool(v)
    
    @property
    def kis_base_url(self) -> str:
        """사용할 한국투자증권 API URL 반환"""
        return self.KIS_BASE_URL if self.KIS_USE_MOCK else self.KIS_REAL_URL

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"  # .env 파일의 추가 필드 무시 (GOOGLE_APPLICATION_CREDENTIALS 등)

# 싱글톤 설정 객체 생성
settings = Settings()

# .env 파일에서 GOOGLE_APPLICATION_CREDENTIALS 읽어서 환경 변수로 설정
# (Settings에서 extra="ignore"로 인해 무시되므로 직접 처리)
def _load_google_credentials_from_env():
    """.env 파일에서 GOOGLE_APPLICATION_CREDENTIALS를 읽어 환경 변수로 설정"""
    # .env 파일 경로 찾기
    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        # .env 파일 직접 읽기
        load_dotenv(env_file)
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if creds_path:
            # 상대 경로인 경우 절대 경로로 변환
            if not os.path.isabs(creds_path):
                project_root = Path(__file__).parent.parent.parent
                creds_path = str(project_root / creds_path)
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
            
            # 파일 존재 여부 확인
            creds_path_normalized = os.path.normpath(creds_path)
            if os.path.exists(creds_path_normalized):
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path_normalized
                return creds_path_normalized
            else:
                # 대안 경로 시도
                alt_paths = [
                    "/Users/imdoyeong/Desktop/workSpace/stock-trading/credentials/vertex-ai-key.json",
                    str(Path.home() / "Desktop" / "workSpace" / "stock-trading" / "credentials" / "vertex-ai-key.json")
                ]
                for alt_path in alt_paths:
                    if os.path.exists(alt_path):
                        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = alt_path
                        return alt_path
    return None

# 설정 로드 시 GOOGLE_APPLICATION_CREDENTIALS 환경 변수 설정
_load_google_credentials_from_env()