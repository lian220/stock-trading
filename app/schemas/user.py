"""
사용자 관련 API 스키마 정의

API 요청/응답용 스키마를 정의합니다.
DB 모델은 app.models.mongodb_models를 참조하세요.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.models.mongodb_models import UserPreferences


class UserCreate(BaseModel):
    """사용자 생성 요청 스키마"""
    user_id: str = Field(..., description="사용자 ID")
    email: Optional[str] = Field(None, description="이메일")
    display_name: Optional[str] = Field(None, description="표시명")
    preferences: Optional[UserPreferences] = Field(None, description="사용자 선호 설정")


class UserUpdate(BaseModel):
    """사용자 업데이트 요청 스키마"""
    email: Optional[str] = Field(None, description="이메일")
    display_name: Optional[str] = Field(None, description="표시명")
    preferences: Optional[UserPreferences] = Field(None, description="사용자 선호 설정")


class UserStockAdd(BaseModel):
    """사용자 주식 종목 추가 요청 스키마"""
    ticker: str = Field(..., description="종목 티커")
    use_leverage: bool = Field(False, description="레버리지 사용 여부")
    notes: Optional[str] = Field(None, description="사용자 메모")
    tags: Optional[List[str]] = Field(None, description="사용자 정의 태그")
    is_active: bool = Field(True, description="활성화 여부")


class UserStockUpdate(BaseModel):
    """사용자 주식 종목 수정 요청 스키마"""
    use_leverage: Optional[bool] = Field(None, description="레버리지 사용 여부")
    notes: Optional[str] = Field(None, description="사용자 메모")
    tags: Optional[List[str]] = Field(None, description="사용자 정의 태그")
    is_active: Optional[bool] = Field(None, description="활성화 여부")

