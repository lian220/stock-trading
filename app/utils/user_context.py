"""
사용자 컨텍스트 관리 유틸리티
- 현재 사용자 ID 관리
- 사용자별 설정 및 데이터 접근
"""

import logging
from typing import Optional, List
from app.core.config import settings

logger = logging.getLogger(__name__)


class UserContext:
    """사용자 컨텍스트 관리 클래스"""
    
    def __init__(self, user_id: Optional[str] = None):
        """
        사용자 컨텍스트 초기화
        
        Args:
            user_id: 사용자 ID. None이면 기본 사용자 ID 사용
        """
        self._user_id = user_id or get_default_user_id()
    
    @property
    def user_id(self) -> str:
        """현재 사용자 ID 반환"""
        return self._user_id
    
    def set_user_id(self, user_id: str):
        """사용자 ID 설정"""
        if not user_id:
            raise ValueError("user_id는 빈 문자열일 수 없습니다")
        self._user_id = user_id
        logger.debug(f"사용자 컨텍스트 변경: {user_id}")


# 전역 사용자 컨텍스트 (스케줄러 등에서 사용)
_global_user_context: Optional[UserContext] = None


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
    
    전역 컨텍스트가 설정되어 있으면 그것을 사용하고,
    없으면 기본 사용자 ID를 반환합니다.
    
    Returns:
        현재 사용자 ID
    """
    if _global_user_context:
        return _global_user_context.user_id
    return get_default_user_id()


def set_global_user_context(user_id: Optional[str] = None):
    """
    전역 사용자 컨텍스트 설정
    
    Args:
        user_id: 사용자 ID. None이면 기본 사용자 ID 사용
    """
    global _global_user_context
    _global_user_context = UserContext(user_id)
    logger.info(f"전역 사용자 컨텍스트 설정: {_global_user_context.user_id}")


def get_global_user_context() -> Optional[UserContext]:
    """전역 사용자 컨텍스트 가져오기"""
    return _global_user_context


def clear_global_user_context():
    """전역 사용자 컨텍스트 초기화"""
    global _global_user_context
    _global_user_context = None
    logger.debug("전역 사용자 컨텍스트 초기화")


def get_active_users() -> List[str]:
    """
    자동매매가 활성화된 사용자 목록 조회
    
    MongoDB의 trading_configs 컬렉션 또는 users.trading_config 필드에서
    auto_trading_enabled=True인 사용자를 조회합니다.
    
    Returns:
        활성 사용자 ID 리스트
    """
    from app.db.mongodb import get_db
    
    db = get_db()
    if db is None:
        logger.warning("MongoDB 연결 실패 - 기본 사용자만 반환")
        return [get_default_user_id()]
    
    try:
        # users 컬렉션에서 trading_config.auto_trading_enabled=True인 사용자 조회
        active_users = db.users.find({
            "trading_config.auto_trading_enabled": True
        })
        
        user_ids = [user.get("user_id") for user in active_users if user.get("user_id")]
        
        # 활성 사용자가 없으면 기본 사용자만 반환
        if not user_ids:
            logger.info("활성 사용자가 없어 기본 사용자만 반환합니다.")
            return [get_default_user_id()]
        
        logger.info(f"활성 사용자 {len(user_ids)}명 조회: {user_ids}")
        return user_ids
    except Exception as e:
        logger.error(f"활성 사용자 조회 중 오류 발생: {str(e)}")
        # 오류 발생 시 기본 사용자만 반환
        return [get_default_user_id()]
