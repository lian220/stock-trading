#!/usr/bin/env python3
"""
MongoDB market_indicators 컬렉션 초기 데이터 생성 스크립트

시장 지표 및 ETF 목록을 MongoDB에 저장합니다.
"""
import sys
from pathlib import Path
from datetime import datetime
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


def seed_market_indicators(db):
    """market_indicators 컬렉션에 시장 지표 및 ETF 데이터 삽입"""
    logger.info("📦 market_indicators 컬렉션에 시장 지표 및 ETF 데이터 삽입 중...")
    
    # 시장 지표 및 ETF 목록
    # source: 'fred' 또는 'yfinance'
    # code: FRED API 코드 (source='fred'인 경우)
    # ticker: Yahoo Finance 티커 (source='yfinance'인 경우)
    market_indicators_data = [
        # FRED 지표
        {"name": "10년 기대 인플레이션율", "type": "economic", "source": "fred", "code": "T10YIE", "is_active": True},
        {"name": "장단기 금리차", "type": "economic", "source": "fred", "code": "T10Y2Y", "is_active": True},
        {"name": "기준금리", "type": "economic", "source": "fred", "code": "FEDFUNDS", "is_active": True},
        {"name": "미시간대 소비자 심리지수", "type": "economic", "source": "fred", "code": "UMCSENT", "is_active": True},
        {"name": "실업률", "type": "economic", "source": "fred", "code": "UNRATE", "is_active": True},
        {"name": "2년 만기 미국 국채 수익률", "type": "economic", "source": "fred", "code": "DGS2", "is_active": True},
        {"name": "10년 만기 미국 국채 수익률", "type": "economic", "source": "fred", "code": "DGS10", "is_active": True},
        {"name": "금융스트레스지수", "type": "economic", "source": "fred", "code": "STLFSI4", "is_active": True},
        {"name": "개인 소비 지출", "type": "economic", "source": "fred", "code": "PCE", "is_active": True},
        {"name": "소비자 물가지수", "type": "economic", "source": "fred", "code": "CPIAUCSL", "is_active": True},
        {"name": "5년 변동금리 모기지", "type": "economic", "source": "fred", "code": "MORTGAGE5US", "is_active": True},
        {"name": "미국 달러 환율", "type": "economic", "source": "fred", "code": "DTWEXM", "is_active": True},
        {"name": "통화 공급량 M2", "type": "economic", "source": "fred", "code": "M2", "is_active": True},
        {"name": "가계 부채 비율", "type": "economic", "source": "fred", "code": "TDSP", "is_active": True},
        {"name": "GDP 성장률", "type": "economic", "source": "fred", "code": "GDPC1", "is_active": True},
        {"name": "나스닥 종합지수", "type": "index", "source": "fred", "code": "NASDAQCOM", "is_active": True},
        
        # Yahoo Finance 지표
        {"name": "S&P 500 지수", "type": "index", "source": "yfinance", "ticker": "^GSPC", "is_active": True},
        {"name": "금 가격", "type": "commodity", "source": "yfinance", "ticker": "GC=F", "is_active": True},
        {"name": "달러 인덱스", "type": "index", "source": "yfinance", "ticker": "DX-Y.NYB", "is_active": True},
        {"name": "나스닥 100", "type": "index", "source": "yfinance", "ticker": "^NDX", "is_active": True},
        {"name": "VIX 지수", "type": "index", "source": "yfinance", "ticker": "^VIX", "is_active": True},
        {"name": "닛케이 225", "type": "index", "source": "yfinance", "ticker": "^N225", "is_active": True},
        {"name": "상해종합", "type": "index", "source": "yfinance", "ticker": "000001.SS", "is_active": True},
        {"name": "항셍", "type": "index", "source": "yfinance", "ticker": "^HSI", "is_active": True},
        {"name": "영국 FTSE", "type": "index", "source": "yfinance", "ticker": "^FTSE", "is_active": True},
        {"name": "독일 DAX", "type": "index", "source": "yfinance", "ticker": "^GDAXI", "is_active": True},
        {"name": "프랑스 CAC 40", "type": "index", "source": "yfinance", "ticker": "^FCHI", "is_active": True},
        
        # ETF
        {"name": "S&P 500 ETF", "type": "etf", "source": "yfinance", "ticker": "SPY", "is_active": True},
        {"name": "QQQ ETF", "type": "etf", "source": "yfinance", "ticker": "QQQ", "is_active": True},
        {"name": "러셀 2000 ETF", "type": "etf", "source": "yfinance", "ticker": "IWM", "is_active": True},
        {"name": "다우 존스 ETF", "type": "etf", "source": "yfinance", "ticker": "DIA", "is_active": True},
        {"name": "미국 전체 채권시장 ETF", "type": "etf", "source": "yfinance", "ticker": "AGG", "is_active": True},
        {"name": "TIPS ETF", "type": "etf", "source": "yfinance", "ticker": "TIP", "is_active": True},
        {"name": "투자등급 회사채 ETF", "type": "etf", "source": "yfinance", "ticker": "LQD", "is_active": True},
        {"name": "미국 리츠 ETF", "type": "etf", "source": "yfinance", "ticker": "VNQ", "is_active": True},
        {"name": "SOXX ETF", "type": "etf", "source": "yfinance", "ticker": "SOXX", "is_active": True},
        
        # 환율
        {"name": "달러/엔", "type": "currency", "source": "yfinance", "ticker": "JPY=X", "is_active": True},
        {"name": "달러/위안", "type": "currency", "source": "yfinance", "ticker": "CNY=X", "is_active": True},
    ]
    
    inserted_count = 0
    updated_count = 0
    
    for indicator in market_indicators_data:
        indicator_doc = {
            "name": indicator["name"],
            "type": indicator["type"],
            "source": indicator.get("source"),  # 'fred' 또는 'yfinance'
            "code": indicator.get("code"),  # FRED API 코드
            "ticker": indicator.get("ticker"),  # Yahoo Finance 티커
            "is_active": indicator["is_active"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        try:
            # 기존 데이터 확인
            existing = db.market_indicators.find_one({"name": indicator["name"]})
            
            if existing:
                # 업데이트: 기존 created_at은 유지하고, 새로운 필드만 추가/업데이트
                update_fields = {
                    "source": indicator.get("source"),
                    "code": indicator.get("code"),
                    "ticker": indicator.get("ticker"),
                    "type": indicator["type"],  # type도 업데이트 (변경될 수 있음)
                    "is_active": indicator["is_active"],
                    "updated_at": datetime.utcnow()
                }
                # None 값 제거 (필드 삭제를 원하지 않으면)
                update_fields = {k: v for k, v in update_fields.items() if v is not None}
                
                db.market_indicators.update_one(
                    {"name": indicator["name"]},
                    {"$set": update_fields}
                )
                updated_count += 1
                logger.info(f"✓ {indicator['name']} 업데이트 (source: {indicator.get('source')}, code/ticker 추가)")
            else:
                # 삽입
                db.market_indicators.insert_one(indicator_doc)
                inserted_count += 1
                logger.info(f"✓ {indicator['name']} 삽입")
        except DuplicateKeyError:
            logger.warning(f"⚠️ {indicator['name']} 중복 키 오류 (무시)")
    
    logger.info(f"✅ market_indicators 컬렉션: {inserted_count}개 삽입, {updated_count}개 업데이트 완료")


def main():
    """메인 함수"""
    try:
        logger.info("🚀 MongoDB market_indicators 초기 데이터 생성 시작...\n")
        
        # MongoDB 연결
        client, db = get_mongodb_client()
        logger.info("✅ MongoDB 연결 성공!\n")
        
        # market_indicators 데이터 삽입
        seed_market_indicators(db)
        logger.info("")
        
        # 결과 확인
        logger.info("📊 생성 결과:")
        indicators_count = db.market_indicators.count_documents({})
        active_count = db.market_indicators.count_documents({"is_active": True})
        
        logger.info(f"  - market_indicators: {indicators_count}개 (활성: {active_count}개)")
        
        # 타입별 통계
        by_type = {}
        for indicator in db.market_indicators.find({"is_active": True}):
            ind_type = indicator.get("type", "unknown")
            by_type[ind_type] = by_type.get(ind_type, 0) + 1
        
        logger.info(f"  - 타입별 통계: {by_type}")
        
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
