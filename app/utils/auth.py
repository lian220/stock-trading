"""
사용자 인증 및 권한 검증 유틸리티

사용자별 데이터 접근 권한을 검증하는 함수들을 제공합니다.
"""

import logging
from typing import Optional
from fastapi import HTTPException, status, Depends, Query
from app.utils.user_context import get_current_user_id, get_default_user_id
from app.db.mongodb import get_db

logger = logging.getLogger(__name__)


def verify_user_access(user_id: Optional[str] = None) -> str:
    """
    사용자 접근 권한 검증
    
    현재 사용자가 요청한 user_id에 접근할 수 있는지 확인합니다.
    
    현재 구현:
    - 요청한 user_id가 현재 사용자 ID와 일치하는지 확인
    - 일치하지 않으면 403 Forbidden 반환
    
    향후 확장:
    - 관리자 권한 확인
    - 역할 기반 접근 제어 (RBAC)
    - 리소스별 권한 확인
    
    Args:
        user_id: 접근하려는 사용자 ID (None이면 현재 사용자 ID 사용)
        
    Returns:
        검증된 사용자 ID
        
    Raises:
        HTTPException: 접근 권한이 없을 경우 403 Forbidden
    """
    current_user_id = get_current_user_id()
    
    # user_id가 None이면 현재 사용자 ID 사용
    if user_id is None:
        return current_user_id
    
    # 요청한 user_id가 현재 사용자 ID와 일치하는지 확인
    if user_id != current_user_id:
        logger.warning(
            f"접근 권한 없음: 현재 사용자({current_user_id})가 "
            f"다른 사용자({user_id})의 데이터에 접근 시도"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"다른 사용자의 데이터에 접근할 권한이 없습니다. (요청한 user_id: {user_id}, 현재 사용자: {current_user_id})"
        )
    
    return user_id


def get_user_id_dependency(
    user_id: Optional[str] = Query(None, description="사용자 ID (선택사항, 없으면 현재 사용자 ID 사용)")
) -> str:
    """
    FastAPI 의존성 함수: 사용자 ID 추출 및 검증
    
    쿼리 파라미터에서 user_id를 추출하고, 접근 권한을 검증합니다.
    
    사용 예시:
    ```python
    @router.get("/balance")
    async def get_balance(user_id: str = Depends(get_user_id_dependency)):
        # user_id는 검증된 사용자 ID
        return get_balance_for_user(user_id)
    ```
    
    Args:
        user_id: 쿼리 파라미터에서 추출한 사용자 ID
        
    Returns:
        검증된 사용자 ID
    """
    return verify_user_access(user_id)


def verify_user_exists(user_id: str) -> bool:
    """
    사용자 존재 여부 확인
    
    MongoDB의 users 컬렉션에서 사용자가 존재하는지 확인합니다.
    
    Args:
        user_id: 확인할 사용자 ID
        
    Returns:
        사용자가 존재하면 True, 없으면 False
    """
    try:
        db = get_db()
        if db is None:
            logger.warning("MongoDB 연결 실패 - 사용자 존재 여부 확인 불가")
            return False
        
        user = db.users.find_one({"user_id": user_id})
        return user is not None
    except Exception as e:
        logger.error(f"사용자 존재 여부 확인 중 오류 발생: {str(e)}")
        return False


def require_user_exists(user_id: str):
    """
    사용자 존재 여부 확인 및 예외 발생
    
    사용자가 존재하지 않으면 404 Not Found를 발생시킵니다.
    
    Args:
        user_id: 확인할 사용자 ID
        
    Raises:
        HTTPException: 사용자가 존재하지 않을 경우 404 Not Found
    """
    if not verify_user_exists(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"사용자를 찾을 수 없습니다: {user_id}"
        )


def verify_data_ownership(resource_user_id: Optional[str], current_user_id: Optional[str] = None) -> bool:
    """
    리소스 소유권 확인
    
    리소스가 특정 사용자에게 속하는지 확인합니다.
    
    Args:
        resource_user_id: 리소스의 소유자 user_id (None이면 전역 리소스)
        current_user_id: 현재 사용자 ID (None이면 get_current_user_id() 사용)
        
    Returns:
        소유권이 있으면 True, 없으면 False
    """
    if current_user_id is None:
        current_user_id = get_current_user_id()
    
    # 전역 리소스 (user_id가 None)는 모든 사용자가 접근 가능
    if resource_user_id is None:
        return True
    
    # 리소스 소유자와 현재 사용자가 일치하는지 확인
    return resource_user_id == current_user_id


def require_data_ownership(resource_user_id: Optional[str], current_user_id: Optional[str] = None):
    """
    리소스 소유권 확인 및 예외 발생
    
    소유권이 없으면 403 Forbidden을 발생시킵니다.
    
    Args:
        resource_user_id: 리소스의 소유자 user_id
        current_user_id: 현재 사용자 ID
        
    Raises:
        HTTPException: 소유권이 없을 경우 403 Forbidden
    """
    if not verify_data_ownership(resource_user_id, current_user_id):
        if current_user_id is None:
            current_user_id = get_current_user_id()
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"이 리소스에 접근할 권한이 없습니다. (리소스 소유자: {resource_user_id}, 현재 사용자: {current_user_id})"
        )


# 관리자 권한 확인 (향후 확장)
def is_admin(user_id: Optional[str] = None) -> bool:
    """
    관리자 권한 확인 (향후 구현)
    
    Args:
        user_id: 확인할 사용자 ID (None이면 현재 사용자 ID)
        
    Returns:
        관리자이면 True, 아니면 False
    """
    if user_id is None:
        user_id = get_current_user_id()
    
    # TODO: MongoDB에서 사용자 역할 확인
    # 예시:
    # db = get_db()
    # user = db.users.find_one({"user_id": user_id})
    # return user and user.get("role") == "admin"
    
    return False


def require_admin(user_id: Optional[str] = None):
    """
    관리자 권한 확인 및 예외 발생 (향후 구현)
    
    Args:
        user_id: 확인할 사용자 ID
        
    Raises:
        HTTPException: 관리자가 아닐 경우 403 Forbidden
    """
    if not is_admin(user_id):
        if user_id is None:
            user_id = get_current_user_id()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"관리자 권한이 필요합니다. (사용자: {user_id})"
        )
