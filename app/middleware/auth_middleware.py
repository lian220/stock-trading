"""
사용자 인증 미들웨어 (선택사항, 향후 확장)

현재는 기본 구조만 구현되어 있으며, 향후 JWT 토큰 인증 등을 추가할 수 있습니다.

사용 방법:
1. JWT 토큰 인증이 필요한 경우:
   - 헤더에서 Authorization 토큰 추출
   - 토큰 검증 및 사용자 ID 추출
   - user_context에 사용자 ID 설정

2. API 키 인증이 필요한 경우:
   - 헤더에서 API 키 추출
   - API 키 검증 및 사용자 ID 매핑
   - user_context에 사용자 ID 설정

3. 현재는 기본 사용자 ID를 사용 (환경변수 DEFAULT_USER_ID)
"""

import logging
from typing import Optional
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from app.utils.user_context import set_global_user_context, get_current_user_id, get_default_user_id
from app.core.config import settings

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """
    사용자 인증 미들웨어
    
    현재 구현:
    - 쿼리 파라미터나 헤더에서 user_id 추출 시도
    - 없으면 기본 사용자 ID 사용
    - 전역 사용자 컨텍스트 설정
    
    향후 확장 가능:
    - JWT 토큰 인증
    - API 키 인증
    - OAuth 인증
    """
    
    def __init__(self, app, enable_auth: bool = False):
        """
        Args:
            app: FastAPI 애플리케이션
            enable_auth: 인증 활성화 여부 (기본값: False, 향후 확장용)
        """
        super().__init__(app)
        self.enable_auth = enable_auth
    
    async def dispatch(self, request: Request, call_next):
        """
        요청 처리 전 인증 로직 실행
        
        현재 동작:
        1. 쿼리 파라미터에서 user_id 추출 시도
        2. 헤더에서 user_id 추출 시도 (X-User-ID)
        3. 없으면 기본 사용자 ID 사용
        4. 전역 사용자 컨텍스트 설정
        """
        # 인증이 비활성화되어 있으면 기본 사용자 ID 사용
        if not self.enable_auth:
            # 기본 사용자 ID로 전역 컨텍스트 설정
            user_id = get_default_user_id()
            set_global_user_context(user_id)
            response = await call_next(request)
            return response
        
        # 향후 확장: JWT 토큰 인증 등
        # 현재는 쿼리 파라미터나 헤더에서 user_id 추출
        user_id: Optional[str] = None
        
        # 1. 쿼리 파라미터에서 user_id 추출
        if "user_id" in request.query_params:
            user_id = request.query_params.get("user_id")
            logger.debug(f"쿼리 파라미터에서 user_id 추출: {user_id}")
        
        # 2. 헤더에서 user_id 추출 (X-User-ID)
        if not user_id and "x-user-id" in request.headers:
            user_id = request.headers.get("x-user-id")
            logger.debug(f"헤더에서 user_id 추출: {user_id}")
        
        # 3. 향후 확장: Authorization 헤더에서 JWT 토큰 추출
        # if not user_id and "authorization" in request.headers:
        #     token = request.headers.get("authorization")
        #     if token.startswith("Bearer "):
        #         token = token[7:]
        #         # JWT 토큰 검증 및 user_id 추출
        #         user_id = self._verify_jwt_token(token)
        
        # 4. 기본 사용자 ID 사용
        if not user_id:
            user_id = get_default_user_id()
            logger.debug(f"기본 user_id 사용: {user_id}")
        
        # 전역 사용자 컨텍스트 설정
        set_global_user_context(user_id)
        
        # 요청 처리
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            logger.error(f"요청 처리 중 오류 발생: {str(e)}")
            raise
    
    def _verify_jwt_token(self, token: str) -> Optional[str]:
        """
        JWT 토큰 검증 (향후 구현)
        
        Args:
            token: JWT 토큰
            
        Returns:
            user_id 또는 None
        """
        # TODO: JWT 토큰 검증 로직 구현
        # 예시:
        # try:
        #     payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        #     return payload.get("user_id")
        # except jwt.InvalidTokenError:
        #     return None
        pass


def create_auth_middleware(enable_auth: bool = False):
    """
    인증 미들웨어 팩토리 함수
    
    Args:
        enable_auth: 인증 활성화 여부
        
    Returns:
        AuthMiddleware 인스턴스
    """
    return lambda app: AuthMiddleware(app, enable_auth=enable_auth)
