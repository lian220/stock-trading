"""
MongoDB 데이터베이스 연결 모듈 (레거시 호환성 유지)
새로운 코드는 app.infrastructure.database.mongodb_client를 사용하세요.
"""
from app.infrastructure.database.mongodb_client import (
    get_async_mongodb_client as get_async_client,
    get_sync_mongodb_client as get_sync_client,
    get_mongodb_database as get_db,
    close_mongodb_connections as close_connections
)
