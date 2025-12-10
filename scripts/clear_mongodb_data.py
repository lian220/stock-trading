#!/usr/bin/env python3
"""
MongoDB의 모든 컬렉션 데이터를 삭제하는 스크립트
주의: 이 스크립트는 모든 데이터를 영구적으로 삭제합니다.
"""
import sys
import os
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from urllib.parse import quote_plus
from app.core.config import settings
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _build_mongodb_url():
    """MongoDB 연결 URL 구성"""
    mongodb_url = (
        os.getenv("MONGO_URL") or
        os.getenv("MONGODB_URL") or
        settings.MONGODB_URL or
        "mongodb://localhost:27017"
    )
    
    mongo_user = (
        os.getenv("MONGO_USER") or
        os.getenv("MONGODB_USER")
    )
    mongo_password = (
        os.getenv("MONGO_PASSWORD") or
        os.getenv("MONGODB_PASSWORD")
    )
    
    if mongo_user and mongo_password:
        if "://" in mongodb_url:
            if "@" not in mongodb_url:
                schema, rest = mongodb_url.split("://", 1)
                mongodb_url = f"{schema}://{quote_plus(mongo_user)}:{quote_plus(mongo_password)}@{rest}"
        else:
            mongodb_url = f"mongodb+srv://{quote_plus(mongo_user)}:{quote_plus(mongo_password)}@{mongodb_url}"
    
    return mongodb_url


def clear_all_collections():
    """모든 컬렉션의 데이터를 삭제합니다."""
    try:
        mongodb_url = _build_mongodb_url()
        database_name = (
            os.getenv("MONGODB_DATABASE") or
            settings.MONGODB_DATABASE or
            "stock_trading"
        )
        
        client = MongoClient(mongodb_url, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        db = client[database_name]
        
        logger.info(f"MongoDB 연결 성공: {database_name}")
    except Exception as e:
        logger.error(f"MongoDB 연결 실패: {e}")
        return False
    
    try:
        # 삭제할 컬렉션 목록
        collections = [
            "stocks",
            "users",
            "user_stocks",
            "economic_data",
            "daily_stock_data",  # 실제 주가 데이터 저장 컬렉션
            "fred_indicators",  # FRED 경제 지표
            "yfinance_indicators",  # Yahoo Finance 지표/ETF
            "stock_recommendations",
            "stock_analysis",
            "sentiment_analysis",
            "trading_configs",
            "trading_logs"
        ]
        
        deleted_counts = {}
        
        for collection_name in collections:
            try:
                collection = db[collection_name]
                count = collection.count_documents({})
                
                if count > 0:
                    result = collection.delete_many({})
                    deleted_counts[collection_name] = result.deleted_count
                    logger.info(f"✅ {collection_name}: {result.deleted_count}개 문서 삭제")
                else:
                    deleted_counts[collection_name] = 0
                    logger.info(f"ℹ️ {collection_name}: 삭제할 데이터 없음")
            except Exception as e:
                logger.error(f"❌ {collection_name} 삭제 실패: {e}")
                deleted_counts[collection_name] = None
        
        # 요약 출력
        total_deleted = sum(count for count in deleted_counts.values() if count is not None)
        logger.info(f"\n📊 삭제 요약:")
        logger.info(f"   총 삭제된 문서 수: {total_deleted}개")
        
        return True
        
    except Exception as e:
        logger.error(f"MongoDB 데이터 삭제 중 오류 발생: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("⚠️  경고: 이 스크립트는 MongoDB의 모든 데이터를 삭제합니다!")
    print("=" * 60)
    
    response = input("정말로 모든 데이터를 삭제하시겠습니까? (yes/no): ")
    
    if response.lower() not in ['yes', 'y']:
        print("취소되었습니다.")
        sys.exit(0)
    
    print("\n데이터 삭제를 시작합니다...\n")
    
    success = clear_all_collections()
    
    if success:
        print("\n✅ 모든 데이터 삭제 완료!")
    else:
        print("\n❌ 데이터 삭제 중 오류가 발생했습니다.")
        sys.exit(1)
