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
    FRED_API_KEY: Optional[str] = Field(
        default=None,
        description="FRED (Federal Reserve Economic Data) API Key"
    )
    TR_ID: Optional[str] = Field(
        default=None,
        description="TR ID"
    )
    
    # Supabase 설정 (레거시 호환용)
    SUPABASE_URL: Optional[str] = Field(
        default=None,
        description="Supabase URL"
    )
    SUPABASE_KEY: Optional[str] = Field(
        default=None,
        description="Supabase API Key"
    )
    
    # GCP 설정
    GCP_PROJECT_ID: Optional[str] = Field(
        default=None,
        description="GCP 프로젝트 ID"
    )
    GCP_BUCKET_NAME: Optional[str] = Field(
        default=None,
        description="GCP 버킷 이름"
    )
    GCP_STAGING_BUCKET: Optional[str] = Field(
        default=None,
        description="GCP 스테이징 버킷 이름"
    )
    GCP_REGION: Optional[str] = Field(
        default=None,
        description="GCP 리전"
    )
    
    # Vertex AI 설정
    VERTEX_AI_CONTAINER_URI: Optional[str] = Field(
        default=None,
        description="Vertex AI 컨테이너 URI"
    )
    VERTEX_AI_MACHINE_TYPE: Optional[str] = Field(
        default=None,
        description="Vertex AI 머신 타입"
    )
    VERTEX_AI_GPU_TYPE: Optional[str] = Field(
        default=None,
        description="Vertex AI GPU 타입"
    )
    VERTEX_AI_GPU_COUNT: Optional[int] = Field(
        default=None,
        description="Vertex AI GPU 개수"
    )
    VERTEX_AI_USE_FLEX_START: bool = Field(
        default=False,
        description="Vertex AI Flex Start 사용 여부"
    )
    
    # GitHub 설정
    GITHUB_TOKEN: Optional[str] = Field(
        default=None,
        description="GitHub 토큰"
    )
    
    # 사용자 설정
    DEFAULT_USER_ID: Optional[str] = Field(
        default=None,
        description="기본 사용자 ID"
    )
    
    # Vertex AI 작업 설정
    USE_TRAINING_JOBS: bool = Field(
        default=True,
        description="Vertex AI Training Jobs 사용 여부 (false면 Custom Jobs 사용)"
    )
    
    @field_validator('USE_TRAINING_JOBS', mode='before')
    @classmethod
    def parse_use_training_jobs(cls, v):
        """빈 문자열을 True로 변환 (기본값)"""
        if v == '' or v is None:
            return True
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return bool(v)
    
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
    
    # MongoDB 설정
    # 하위 호환성: MONGO_URL, MONGO_USER, MONGO_PASSWORD도 지원
    MONGODB_URL: Optional[str] = Field(
        default=None,
        description="MongoDB 연결 URL (MONGO_URL 환경변수도 지원)"
    )
    MONGODB_USER: Optional[str] = Field(
        default=None,
        description="MongoDB 사용자명 (MONGO_USER 환경변수도 지원)"
    )
    MONGODB_PASSWORD: Optional[str] = Field(
        default=None,
        description="MongoDB 비밀번호 (MONGO_PASSWORD 환경변수도 지원)"
    )
    MONGODB_DATABASE: str = Field(
        default="stock_trading",
        description="MongoDB 데이터베이스 이름"
    )
    USE_MONGODB: bool = Field(
        default=False,
        description="MongoDB 사용 여부 (.env에서 USE_MONGODB=true/false로 설정 가능)"
    )
    
    def _get_env_var(self, primary: Optional[str], legacy_name: str) -> Optional[str]:
        """
        환경변수를 가져오는 헬퍼 메서드
        우선순위: primary 값 > legacy 환경변수
        
        Args:
            primary: Settings 필드 값
            legacy_name: 하위 호환성을 위한 환경변수 이름 (예: "MONGO_URL")
        
        Returns:
            환경변수 값 또는 None
        """
        if primary:
            return primary
        # config.py 내부에서만 os.getenv 사용 (하위 호환성)
        return os.getenv(legacy_name)
    
    @field_validator('USE_MONGODB', mode='before')
    @classmethod
    def parse_use_mongodb(cls, v):
        """빈 문자열을 False로 변환"""
        if v == '' or v is None:
            return False
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return bool(v)
    
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
    
    def get_mongodb_url(self) -> str:
        """
        MongoDB 연결 URL을 반환합니다.
        config.py를 통해서만 접근합니다.
        
        하위 호환성: MONGO_URL 환경변수도 지원
        """
        url = self._get_env_var(self.MONGODB_URL, "MONGO_URL")
        return url or "mongodb://localhost:27017"
    
    def get_mongodb_user(self) -> Optional[str]:
        """
        MongoDB 사용자명을 반환합니다.
        
        하위 호환성: MONGO_USER 환경변수도 지원
        """
        return self._get_env_var(self.MONGODB_USER, "MONGO_USER")
    
    def get_mongodb_password(self) -> Optional[str]:
        """
        MongoDB 비밀번호를 반환합니다.
        
        하위 호환성: MONGO_PASSWORD 환경변수도 지원
        """
        return self._get_env_var(self.MONGODB_PASSWORD, "MONGO_PASSWORD")
    
    def get_mongodb_database(self) -> str:
        """MongoDB 데이터베이스 이름을 반환합니다."""
        return self.MONGODB_DATABASE or "stock_trading"
    
    def is_mongodb_enabled(self) -> bool:
        """MongoDB 사용 여부를 반환합니다."""
        return self.USE_MONGODB

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
    """.env 파일에서 GOOGLE_APPLICATION_CREDENTIALS를 읽어 환경 변수로 설정 (로컬 환경에서만)"""
    # Docker 환경 체크: /app 디렉토리가 존재하고 /Users 디렉토리가 없으면 Docker 환경
    is_docker = Path("/app").exists() and not Path("/Users").exists()
    
    # Docker 환경에서는 환경 변수가 이미 설정되어 있으므로 건너뜀
    if is_docker:
        return None
    
    # 로컬 환경에서만 .env 파일에서 읽기
    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        # 현재 환경 변수 값 저장 (이미 설정되어 있으면 유지)
        existing_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        
        # .env 파일 직접 읽기 (기존 환경 변수는 유지)
        load_dotenv(env_file, override=False)
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        
        # 환경 변수가 이미 설정되어 있으면 .env 파일 값 무시
        if existing_creds:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = existing_creds
            return existing_creds if os.path.exists(existing_creds) else None
        
        # .env 파일에서 읽은 값이 있는 경우에만 설정
        if creds_path:
            # 상대 경로인 경우 절대 경로로 변환
            if not os.path.isabs(creds_path):
                project_root = Path(__file__).parent.parent.parent
                creds_path = str(project_root / creds_path)
            
            # 파일 존재 여부 확인
            creds_path_normalized = os.path.normpath(creds_path)
            if os.path.exists(creds_path_normalized):
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path_normalized
                return creds_path_normalized
            else:
                # 대안 경로 시도 (프로젝트 루트 기준)
                project_root = Path(__file__).parent.parent.parent
                alt_paths = [
                    str(project_root / "credentials" / "vertex-ai-key.json"),
                    str(Path.home() / "Desktop" / "workSpace" / "stock-trading" / "credentials" / "vertex-ai-key.json")
                ]
                for alt_path in alt_paths:
                    normalized_path = os.path.normpath(alt_path)
                    if os.path.exists(normalized_path):
                        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = normalized_path
                        return normalized_path
    return None

# 설정 로드 시 GOOGLE_APPLICATION_CREDENTIALS 환경 변수 설정
_load_google_credentials_from_env()
