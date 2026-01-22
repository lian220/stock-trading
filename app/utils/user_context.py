"""
사용자 컨텍스트 관리 유틸리티
- 현재 사용자 ID 관리
- 사용자별 설정 및 데이터 접근

ContextVar를 사용하여 요청별로 격리된 사용자 컨텍스트를 관리합니다.
이를 통해 FastAPI의 동시 요청 처리 시 race condition을 방지합니다.
"""

import logging
from typing import Optional, List
from contextvars import ContextVar
import pymongo.errors
from app.core.config import settings

logger = logging.getLogger(__name__)

# 요청별로 격리된 사용자 ID 컨텍스트 변수
_user_context_var: ContextVar[Optional[str]] = ContextVar("user_id", default=None)


def get_default_user_id() -> str:
    """
    기본 사용자 ID 가져오기
    
    우선순위:
    1. settings.DEFAULT_USER_ID (환경변수에서 자동 로드)
    2. "lian" (하위 호환성)
    
    Returns:
        기본 사용자 ID
    """
    # settings 객체에서 가져오기 (환경변수는 Pydantic이 자동으로 로드)
    if settings.DEFAULT_USER_ID:
        return settings.DEFAULT_USER_ID
    
    # 기본값 (하위 호환성)
    return "lian"


def get_current_user_id() -> str:
    """
    현재 사용자 ID 가져오기
    
    ContextVar에서 현재 요청의 user_id를 가져옵니다.
    설정되어 있지 않으면 기본 사용자 ID를 반환합니다.
    
    Returns:
        현재 사용자 ID (ContextVar가 None이면 기본 사용자 ID 반환)
    """
    user_id = _user_context_var.get()
    if user_id is not None:
        logger.debug(f"ContextVar에서 user_id 조회: {user_id}")
        return user_id
    
    default_user_id = get_default_user_id()
    logger.debug(f"ContextVar가 None이므로 기본 user_id 사용: {default_user_id}")
    return default_user_id


def set_global_user_context(user_id: Optional[str] = None):
    """
    현재 컨텍스트의 사용자 ID 설정
    
    ContextVar를 사용하여 요청별로 격리된 사용자 ID를 설정합니다.
    이 함수는 각 요청의 컨텍스트에서 독립적으로 동작하여 동시 요청 간 race condition을 방지합니다.
    
    Args:
        user_id: 사용자 ID. None이면 기본 사용자 ID 사용
    """
    if user_id is None:
        user_id = get_default_user_id()
        logger.debug(f"user_id가 None이므로 기본 사용자 ID 사용: {user_id}")
    
    _user_context_var.set(user_id)
    logger.debug(f"ContextVar에 user_id 설정 완료: {user_id}")


def clear_global_user_context():
    """
    현재 컨텍스트의 사용자 ID 초기화
    
    요청 처리 완료 후 컨텍스트를 정리하기 위해 호출됩니다.
    ContextVar를 None으로 설정하여 다음 요청과 격리합니다.
    """
    previous_user_id = _user_context_var.get()
    _user_context_var.set(None)
    if previous_user_id:
        logger.debug(f"ContextVar 초기화 완료 (이전 user_id: {previous_user_id})")
    else:
        logger.debug("ContextVar 초기화 완료 (이전 user_id: None)")


def get_active_users(mode: str = "all") -> List[str]:
    """
    자동매매가 활성화된 사용자 목록 조회
    
    MongoDB의 trading_configs 컬렉션 또는 users.trading_config 필드에서
    자동매수/자동매매 활성화된 사용자를 조회합니다.
    
    Args:
        mode: "buy" | "sell" | "all" (기본값: "all")
    
    Returns:
        활성 사용자 ID 리스트
    """
    from app.db.mongodb import get_db
    
    db = get_db()
    if db is None:
        logger.warning("MongoDB 연결 실패 - 활성 사용자 조회 불가")
        return []
    
    try:
        if mode not in {"buy", "sell", "all"}:
            logger.warning(f"알 수 없는 mode={mode}, 기본값 'all'로 처리합니다.")
            mode = "all"
        
        if mode == "buy":
            query = {
                "$or": [
                    {"trading_config.auto_trading_enabled": True},
                    {"trading_config.enabled": True}
                ]
            }
        elif mode == "sell":
            query = {
                "$or": [
                    {"trading_config.enabled": True},
                    {"trading_config.auto_trading_enabled": True}
                ]
            }
        else:
            query = {
                "$or": [
                    {"trading_config.enabled": True},
                    {"trading_config.auto_trading_enabled": True}
                ]
            }
        
        # users 컬렉션에서 활성 사용자 조회
        active_users = db.users.find(query)
        
        user_ids = [user.get("user_id") for user in active_users if user.get("user_id")]
        
        # 활성 사용자가 없으면 기본 사용자만 반환
        if not user_ids:
            logger.info("활성 사용자가 없습니다.")
            return []
        else:
            return user_ids
    except pymongo.errors.PyMongoError as e:
        logger.exception("활성 사용자 조회 중 MongoDB 오류 발생")
        # 오류 발생 시 기본 사용자만 반환
        return [get_default_user_id()]
