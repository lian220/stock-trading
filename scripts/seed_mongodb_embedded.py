#!/usr/bin/env python3
"""
MongoDB 초기 데이터 생성 스크립트 (Embedded Schema)

- stocks 컬렉션에 종목 데이터 삽입
- users 컬렉션에 사용자 생성 (stocks embedded)
"""
import sys
from pathlib import Path
from datetime import datetime
from bson import ObjectId
from urllib.parse import quote_plus

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, DuplicateKeyError
except ImportError:
    print("❌ pymongo 모듈이 설치되어 있지 않습니다.")
    print("설치 명령: pip install pymongo")
    sys.exit(1)

import os
from dotenv import load_dotenv
import logging

# .env 파일 로드
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_mongodb_client():
    """MongoDB 클라이언트 연결"""
    mongodb_url = (
        os.getenv("MONGO_URL") or 
        os.getenv("MONGODB_URL") or 
        "mongodb://localhost:27017"
    )
    
    mongo_user = os.getenv("MONGO_USER") or os.getenv("MONGODB_USER")
    mongo_password = os.getenv("MONGO_PASSWORD") or os.getenv("MONGODB_PASSWORD")
    
    final_url = mongodb_url
    
    # 인증 정보 처리
    if mongo_user and mongo_password:
        if "://" in mongodb_url:
            if "@" not in mongodb_url:
                schema, rest = mongodb_url.split("://", 1)
                final_url = f"{schema}://{quote_plus(mongo_user)}:{quote_plus(mongo_password)}@{rest}"
        else:
            final_url = f"mongodb+srv://{quote_plus(mongo_user)}:{quote_plus(mongo_password)}@{mongodb_url}"
    
    database_name = os.getenv("MONGODB_DATABASE") or "stock_trading"
    
    client = MongoClient(
        final_url,
        serverSelectionTimeoutMS=10000,
        connectTimeoutMS=10000,
    )
    
    # 연결 테스트
    client.admin.command('ping')
    
    db = client[database_name]
    
    return client, db


def seed_stocks(db):
    """stocks 컬렉션에 종목 데이터 삽입 (master data)"""
    logger.info("📦 stocks 컬렉션에 종목 데이터 삽입 중...")
    
    stocks_data = [
        {"id": 1, "stock_name": "애플", "ticker": "AAPL", "is_etf": False, "leverage_ticker": "AAPU", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 2, "stock_name": "마이크로소프트", "ticker": "MSFT", "is_etf": False, "leverage_ticker": "MSFU", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 3, "stock_name": "아마존", "ticker": "AMZN", "is_etf": False, "leverage_ticker": "AMZU", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 4, "stock_name": "구글 A", "ticker": "GOOGL", "is_etf": False, "leverage_ticker": "GGLL", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 6, "stock_name": "메타", "ticker": "META", "is_etf": False, "leverage_ticker": "FBL", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 7, "stock_name": "엔비디아", "ticker": "NVDA", "is_etf": False, "leverage_ticker": "NVDL", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 8, "stock_name": "인텔", "ticker": "INTC", "is_etf": False, "leverage_ticker": "INTL", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 9, "stock_name": "마이크론", "ticker": "MU", "is_etf": False, "leverage_ticker": "MUU", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 10, "stock_name": "브로드컴", "ticker": "AVGO", "is_etf": False, "leverage_ticker": "AVGL", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 11, "stock_name": "텍사스 인스트루먼트", "ticker": "TXN", "is_etf": False, "leverage_ticker": "TXNL", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 12, "stock_name": "AMD", "ticker": "AMD", "is_etf": False, "leverage_ticker": "AMDL", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 13, "stock_name": "어플라이드 머티리얼즈", "ticker": "AMAT", "is_etf": False, "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 14, "stock_name": "TSMC", "ticker": "TSM", "is_etf": False, "leverage_ticker": "TSML", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 15, "stock_name": "크리도 테크놀로지 그룹 홀딩", "ticker": "CRDO", "is_etf": False, "leverage_ticker": "CRDL", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 16, "stock_name": "셀레스티카", "ticker": "CELH", "is_etf": False, "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 17, "stock_name": "월마트", "ticker": "WMT", "is_etf": False, "leverage_ticker": "WMTU", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 18, "stock_name": "버티브 홀딩스", "ticker": "VRT", "is_etf": False, "leverage_ticker": "VRTL", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 19, "stock_name": "비스트라 에너지", "ticker": "VST", "is_etf": False, "leverage_ticker": "VSTL", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 20, "stock_name": "블룸에너지", "ticker": "BE", "is_etf": False, "leverage_ticker": "BEL", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 21, "stock_name": "오클로", "ticker": "OKLO", "is_etf": False, "leverage_ticker": "OKLL", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 22, "stock_name": "팔란티어", "ticker": "PLTR", "is_etf": False, "leverage_ticker": "PTIR", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 23, "stock_name": "세일즈포스", "ticker": "CRM", "is_etf": False, "leverage_ticker": "CRML", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 24, "stock_name": "오라클", "ticker": "ORCL", "is_etf": False, "leverage_ticker": "ORCL", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 25, "stock_name": "앱플로빈", "ticker": "APP", "is_etf": False, "leverage_ticker": "APVL", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 26, "stock_name": "팔로알토 네트웍스", "ticker": "PANW", "is_etf": False, "leverage_ticker": "PANL", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 27, "stock_name": "크라우드 스트라이크", "ticker": "CRWD", "is_etf": False, "leverage_ticker": "CRWL", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 28, "stock_name": "스노우플레이크", "ticker": "SNOW", "is_etf": False, "leverage_ticker": "SNOL", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 29, "stock_name": "로빈후드", "ticker": "HOOD", "is_etf": False, "leverage_ticker": "HODL", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 30, "stock_name": "일라이릴리", "ticker": "LLY", "is_etf": False, "leverage_ticker": "LLYL", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 31, "stock_name": "존슨앤존슨", "ticker": "JNJ", "is_etf": False, "leverage_ticker": "JNJL", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 32, "stock_name": "S&P 500 ETF", "ticker": "SPY", "is_etf": True, "leverage_ticker": "UPRO", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 33, "stock_name": "QQQ ETF", "ticker": "QQQ", "is_etf": True, "leverage_ticker": "TQQQ", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 34, "stock_name": "SOXX ETF", "ticker": "SOXX", "is_etf": True, "leverage_ticker": "SOXL", "is_active": True, "created_at": "2025-12-02 12:31:24.228989+00", "updated_at": "2025-12-02 12:31:24.228989+00"},
        {"id": 69, "stock_name": "테슬라", "ticker": "TSLA", "is_etf": False, "leverage_ticker": "TSLL", "is_active": True, "created_at": "2025-12-06 02:20:12.728315+00", "updated_at": "2025-12-06 02:20:12.728315+00"}
    ]
    
    inserted_count = 0
    updated_count = 0
    
    for stock in stocks_data:
        created_at = datetime.fromisoformat(stock["created_at"].replace("+00", "+00:00"))
        updated_at = datetime.fromisoformat(stock["updated_at"].replace("+00", "+00:00"))
        
        stock_doc = {
            "ticker": stock["ticker"],
            "stock_name": stock["stock_name"],
            "is_etf": stock["is_etf"],
            "leverage_ticker": stock.get("leverage_ticker"),
            "is_active": stock["is_active"],
            "created_at": created_at,
            "updated_at": updated_at
        }
        
        try:
            existing = db.stocks.find_one({"ticker": stock_doc["ticker"]})
            
            if existing:
                db.stocks.update_one(
                    {"ticker": stock_doc["ticker"]},
                    {"$set": stock_doc}
                )
                updated_count += 1
                logger.info(f"✓ {stock_doc['stock_name']} ({stock_doc['ticker']}) 업데이트")
            else:
                db.stocks.insert_one(stock_doc)
                inserted_count += 1
                logger.info(f"✓ {stock_doc['stock_name']} ({stock_doc['ticker']}) 삽입")
        except DuplicateKeyError:
            logger.warning(f"⚠️  {stock_doc['stock_name']} ({stock_doc['ticker']}) 중복 키 오류 (무시)")
    
    logger.info(f"✅ stocks 컬렉션: {inserted_count}개 삽입, {updated_count}개 업데이트 완료")


def seed_user_with_embedded_stocks(db, user_id="lian", email="lian.dy220@gmail.com"):
    """users 컬렉션에 사용자 생성 (stocks embedded)"""
    logger.info(f"👤 사용자 '{user_id}' 생성 중 (embedded stocks)...")
    
    # 모든 활성 종목 조회
    active_stocks = list(db.stocks.find({"is_active": True}))
    logger.info(f"  - {len(active_stocks)}개의 활성 종목 발견")
    
    # embedded stocks 배열 생성
    embedded_stocks = []
    for stock in active_stocks:
        embedded_stock = {
            "ticker": stock.get("ticker"),
            "stock_name": stock.get("stock_name"),
            "stock_name_en": stock.get("stock_name_en"),
            "is_etf": stock.get("is_etf", False),
            "leverage_ticker": stock.get("leverage_ticker"),
            "use_leverage": True,  # 기본값
            "notes": None,
            "tags": [],
            "is_active": True,
            "added_at": datetime.utcnow()
        }
        embedded_stocks.append(embedded_stock)
        logger.info(f"    ✓ {stock.get('ticker')} ({stock.get('stock_name')})")
    
    # 사용자 문서 생성
    user_doc = {
        "user_id": user_id,
        "email": email,
        "display_name": user_id,
        "preferences": {
            "default_currency": "USD",
            "notification_enabled": True
        },
        "stocks": embedded_stocks,  # 👈 embedded!
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    try:
        existing = db.users.find_one({"user_id": user_id})
        
        if existing:
            db.users.update_one(
                {"user_id": user_id},
                {"$set": user_doc}
            )
            logger.info(f"✓ 사용자 '{user_id}' 업데이트 완료 ({len(embedded_stocks)}개 종목 embedded)")
        else:
            result = db.users.insert_one(user_doc)
            logger.info(f"✓ 사용자 '{user_id}' 생성 완료 (ID: {result.inserted_id}, {len(embedded_stocks)}개 종목 embedded)")
        
        return user_id
    except DuplicateKeyError:
        logger.warning(f"⚠️  사용자 '{user_id}' 이미 존재함")
        return user_id


def main():
    """메인 함수"""
    try:
        logger.info("🚀 MongoDB 초기 데이터 생성 시작 (Embedded Schema)...\n")
        
        # MongoDB 연결
        client, db = get_mongodb_client()
        logger.info("✅ MongoDB 연결 성공!\n")
        
        # 1. stocks 데이터 삽입 (master data)
        seed_stocks(db)
        logger.info("")
        
        # 2. 사용자 생성 (stocks embedded)
        user_id = seed_user_with_embedded_stocks(db, user_id="lian", email="lian.dy220@gmail.com")
        logger.info("")
        
        # 결과 확인
        logger.info("📊 생성 결과:")
        stocks_count = db.stocks.count_documents({})
        users_count = db.users.count_documents({})
        
        user = db.users.find_one({"user_id": user_id})
        embedded_stocks_count = len(user.get("stocks", [])) if user else 0
        
        logger.info(f"  - stocks (master): {stocks_count}개")
        logger.info(f"  - users: {users_count}개")
        logger.info(f"  - user '{user_id}' embedded stocks: {embedded_stocks_count}개")
        
        client.close()
        logger.info("\n✅ 초기 데이터 생성 완료!")
        
    except ConnectionFailure as e:
        logger.error(f"❌ MongoDB 연결 실패: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
