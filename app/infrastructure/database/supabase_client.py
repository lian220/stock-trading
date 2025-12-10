"""Supabase 클라이언트 관리"""
from supabase import create_client, Client
from typing import Optional
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

# 전역 Supabase 클라이언트 (싱글톤)
_supabase_client: Optional[Client] = None


def get_supabase_client() -> Optional[Client]:
    """
    Supabase 클라이언트를 반환합니다.
    싱글톤 패턴으로 연결을 재사용합니다.
    """
    global _supabase_client
    
    if _supabase_client is None:
        url = settings.SUPABASE_URL
        key = settings.SUPABASE_KEY
        
        if not url or not key:
            logger.warning("Supabase URL 또는 Key가 설정되지 않았습니다.")
            return None
        
        try:
            _supabase_client = create_client(url, key)
            logger.info("Supabase 클라이언트 연결 성공")
        except Exception as e:
            logger.error(f"Supabase 클라이언트 연결 실패: {e}")
            return None
    
    return _supabase_client


def close_supabase_client():
    """Supabase 클라이언트 연결 종료"""
    global _supabase_client
    if _supabase_client:
        # Supabase Python 클라이언트는 명시적인 close 메서드가 없음
        _supabase_client = None
        logger.info("Supabase 클라이언트 연결 종료")
