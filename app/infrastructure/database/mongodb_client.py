"""MongoDB 클라이언트 관리"""
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from pymongo.database import Database
from typing import Optional, Tuple
from urllib.parse import quote_plus
import logging
from app.core.config import settings

# OperationCancelled는 pymongo.errors 모듈에서 직접 import 불가하므로
# 일반 Exception으로 처리하거나, 에러 메시지로 확인

logger = logging.getLogger(__name__)

# 전역 클라이언트 인스턴스 (싱글톤)
_async_client: Optional[AsyncIOMotorClient] = None
_sync_client: Optional[MongoClient] = None
_async_db: Optional[Database] = None
_sync_db: Optional[Database] = None


def _build_mongodb_url() -> str:
    """
    MongoDB 연결 URL을 구성합니다.
    config.py를 통해서만 환경변수에 접근합니다.
    """
    mongodb_url = settings.get_mongodb_url()
    mongo_user = settings.get_mongodb_user()
    mongo_password = settings.get_mongodb_password()
    
    # 인증 정보가 있으면 URL에 추가
    if mongo_user and mongo_password:
        if "://" in mongodb_url:
            if "@" not in mongodb_url:
                schema, rest = mongodb_url.split("://", 1)
                mongodb_url = f"{schema}://{quote_plus(mongo_user)}:{quote_plus(mongo_password)}@{rest}"
        else:
            mongodb_url = f"mongodb+srv://{quote_plus(mongo_user)}:{quote_plus(mongo_password)}@{mongodb_url}"
    
    return mongodb_url


def get_async_mongodb_client() -> Tuple[Optional[AsyncIOMotorClient], Optional[Database]]:
    """
    비동기 MongoDB 클라이언트 반환 (FastAPI에서 사용)
    싱글톤 패턴으로 연결을 재사용합니다.
    """
    global _async_client, _async_db
    
    if not settings.is_mongodb_enabled():
        logger.debug("MongoDB가 비활성화되어 있습니다.")
        return None, None
    
    if _async_client is None:
        try:
            mongodb_url = _build_mongodb_url()
            database_name = settings.get_mongodb_database()
            
            _async_client = AsyncIOMotorClient(
                mongodb_url,
                serverSelectionTimeoutMS=30000,  # 30초로 증가
                connectTimeoutMS=30000,  # 30초로 증가
                socketTimeoutMS=30000,  # 소켓 타임아웃 추가 (30초)
                maxPoolSize=50,  # 최대 연결 풀 크기
                minPoolSize=10,  # 최소 연결 풀 크기
                retryWrites=True,  # 쓰기 재시도 활성화
            )
            _async_db = _async_client[database_name]
            
            logger.info(f"MongoDB 비동기 클라이언트 연결 성공: {database_name}")
        except Exception as e:
            # OperationCancelled 등 기타 예외 처리
            error_msg = str(e)
            if "operation cancelled" in error_msg.lower() or "OperationCancelled" in str(type(e).__name__):
                logger.error(f"MongoDB 비동기 클라이언트 작업 취소됨 (타임아웃 가능성): {e}")
            else:
                logger.error(f"MongoDB 비동기 클라이언트 연결 실패: {e}")
            _async_client = None
            _async_db = None
            return None, None
    
    return _async_client, _async_db


def get_sync_mongodb_client() -> Tuple[Optional[MongoClient], Optional[Database]]:
    """
    동기 MongoDB 클라이언트 반환 (스크립트에서 사용)
    싱글톤 패턴으로 연결을 재사용합니다.
    """
    global _sync_client, _sync_db
    
    if not settings.is_mongodb_enabled():
        logger.debug("MongoDB가 비활성화되어 있습니다.")
        return None, None
    
    if _sync_client is None:
        try:
            mongodb_url = _build_mongodb_url()
            database_name = settings.get_mongodb_database()
            
            _sync_client = MongoClient(
                mongodb_url,
                serverSelectionTimeoutMS=30000,  # 30초로 증가
                connectTimeoutMS=30000,  # 30초로 증가
                socketTimeoutMS=30000,  # 소켓 타임아웃 추가 (30초)
                maxPoolSize=50,  # 최대 연결 풀 크기
                minPoolSize=10,  # 최소 연결 풀 크기
                retryWrites=True,  # 쓰기 재시도 활성화
            )
            _sync_db = _sync_client[database_name]
            
            # 연결 테스트
            _sync_client.admin.command('ping')
            logger.info(f"MongoDB 동기 클라이언트 연결 성공: {database_name}")
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"MongoDB 동기 클라이언트 연결 실패: {e}")
            _sync_client = None
            _sync_db = None
            return None, None
        except Exception as e:
            # OperationCancelled 등 기타 예외 처리
            error_msg = str(e)
            if "operation cancelled" in error_msg.lower() or "OperationCancelled" in str(type(e).__name__):
                logger.error(f"MongoDB 동기 클라이언트 작업 취소됨 (타임아웃 가능성): {e}")
            else:
                logger.error(f"MongoDB 동기 클라이언트 연결 실패: {e}")
            _sync_client = None
            _sync_db = None
            return None, None
    
    return _sync_client, _sync_db


def get_mongodb_database() -> Optional[Database]:
    """
    동기 MongoDB 데이터베이스 인스턴스를 반환합니다.
    스크립트나 동기 코드에서 사용합니다.
    """
    _, db = get_sync_mongodb_client()
    return db


def close_mongodb_connections():
    """모든 MongoDB 연결 종료"""
    global _async_client, _sync_client, _async_db, _sync_db
    
    if _async_client:
        _async_client.close()
        _async_client = None
        _async_db = None
        logger.info("MongoDB 비동기 클라이언트 연결 종료")
    
    if _sync_client:
        _sync_client.close()
        _sync_client = None
        _sync_db = None
        logger.info("MongoDB 동기 클라이언트 연결 종료")
