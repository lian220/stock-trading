#!/usr/bin/env python3
"""
MongoDB 컬렉션 생성 및 초기 데이터 세팅 스크립트

이 스크립트는:
1. MongoDB의 모든 데이터를 삭제 (선택사항, --clear 옵션)
2. 필요한 collections과 인덱스를 생성
3. 기본 설정 정보(fred_indicators, yfinance_indicators)를 stock.py의 기본값 딕셔너리에서 세팅
"""
import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, DuplicateKeyError
except ImportError:
    print("❌ pymongo 모듈이 설치되어 있지 않습니다.")
    print("설치 명령: pip install pymongo")
    sys.exit(1)

from app.core.config import settings
import os
from dotenv import load_dotenv
from urllib.parse import quote_plus
import logging
from datetime import datetime

# .env 파일 로드
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


def clear_all_collections(db):
    """모든 컬렉션의 데이터를 삭제합니다."""
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
        logger.info(f"\n📊 삭제 요약: 총 {total_deleted}개 문서 삭제 완료")
        return True
        
    except Exception as e:
        logger.error(f"MongoDB 데이터 삭제 중 오류 발생: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def _get_default_fred_indicators():
    """기본 FRED 지표 딕셔너리 (stock.py와 동일)"""
    return {
        'T10YIE': '10년 기대 인플레이션율',
        'T10Y2Y': '장단기 금리차',
        'FEDFUNDS': '기준금리',
        'UMCSENT': '미시간대 소비자 심리지수',
        'UNRATE': '실업률',
        'DGS2': '2년 만기 미국 국채 수익률',
        'DGS10': '10년 만기 미국 국채 수익률',
        'STLFSI4': '금융스트레스지수',
        'PCE': '개인 소비 지출',
        'CPIAUCSL': '소비자 물가지수',
        'MORTGAGE5US': '5년 변동금리 모기지',
        'DTWEXM': '미국 달러 환율',
        'M2': '통화 공급량 M2',
        'TDSP': '가계 부채 비율',
        'GDPC1': 'GDP 성장률',
        'NASDAQCOM': '나스닥 종합지수'
    }


def _get_default_yfinance_indicators():
    """기본 Yahoo Finance 지표 딕셔너리 (stock.py와 동일)"""
    return {
        'S&P 500 지수': '^GSPC',
        '금 가격': 'GC=F',
        '달러 인덱스': 'DX-Y.NYB',
        '나스닥 100': '^NDX',
        'S&P 500 ETF': 'SPY',
        'QQQ ETF': 'QQQ',
        '러셀 2000 ETF': 'IWM',
        '다우 존스 ETF': 'DIA',
        'VIX 지수': '^VIX',
        '닛케이 225': '^N225',
        '상해종합': '000001.SS',
        '항셍': '^HSI',
        '영국 FTSE': '^FTSE',
        '독일 DAX': '^GDAXI',
        '프랑스 CAC 40': '^FCHI',
        '미국 전체 채권시장 ETF': 'AGG',
        'TIPS ETF': 'TIP',
        '투자등급 회사채 ETF': 'LQD',
        '달러/엔': 'JPY=X',
        '달러/위안': 'CNY=X',
        '미국 리츠 ETF': 'VNQ',
        'SOXX ETF': 'SOXX',
    }


def seed_fred_indicators_from_defaults(db):
    """
    stock.py의 기본값 딕셔너리를 사용하여 fred_indicators 컬렉션에 데이터 세팅
    """
    logger.info("📦 fred_indicators 컬렉션에 기본 설정 정보 세팅 중...")
    
    # 기본값 딕셔너리 가져오기
    default_fred = _get_default_fred_indicators()  # {code: name}
    
    inserted_count = 0
    updated_count = 0
    
    # FRED 지표 세팅
    for code, name in default_fred.items():
        # type 결정
        ind_type = "index" if name == "나스닥 종합지수" else "economic"
        
        existing = db.fred_indicators.find_one({"code": code})
        
        if existing:
            # 기존 데이터가 있으면 업데이트
            update_fields = {
                "name": name,
                "type": ind_type,
                "is_active": True,
                "updated_at": datetime.utcnow()
            }
            db.fred_indicators.update_one(
                {"code": code},
                {"$set": update_fields}
            )
            updated_count += 1
            logger.info(f"✓ {name} 업데이트 (FRED: {code})")
        else:
            # 새로 추가
            indicator_doc = {
                "code": code,
                "name": name,
                "type": ind_type,
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            try:
                db.fred_indicators.insert_one(indicator_doc)
                inserted_count += 1
                logger.info(f"✓ {name} 추가 (FRED: {code})")
            except DuplicateKeyError:
                logger.warning(f"⚠️ {name} 중복 키 오류 (무시)")
    
    logger.info(f"✅ fred_indicators 세팅 완료: {inserted_count}개 추가, {updated_count}개 업데이트")


def seed_yfinance_indicators_from_defaults(db):
    """
    stock.py의 기본값 딕셔너리를 사용하여 yfinance_indicators 컬렉션에 데이터 세팅
    """
    logger.info("📦 yfinance_indicators 컬렉션에 기본 설정 정보 세팅 중...")
    
    # 기본값 딕셔너리 가져오기
    default_yfinance = _get_default_yfinance_indicators()  # {name: ticker}
    
    inserted_count = 0
    updated_count = 0
    
    # Yahoo Finance 지표 세팅
    for name, ticker in default_yfinance.items():
        # type 결정
        if "ETF" in name:
            ind_type = "etf"
        elif any(currency in name for currency in ["엔", "위안"]):
            ind_type = "currency"
        elif name == "금 가격":
            ind_type = "commodity"
        else:
            ind_type = "index"
        
        existing = db.yfinance_indicators.find_one({"ticker": ticker})
        
        if existing:
            # 기존 데이터가 있으면 업데이트
            update_fields = {
                "name": name,
                "type": ind_type,
                "is_active": True,
                "updated_at": datetime.utcnow()
            }
            db.yfinance_indicators.update_one(
                {"ticker": ticker},
                {"$set": update_fields}
            )
            updated_count += 1
            logger.info(f"✓ {name} 업데이트 (Yahoo Finance: {ticker})")
        else:
            # 새로 추가
            indicator_doc = {
                "ticker": ticker,
                "name": name,
                "type": ind_type,
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            try:
                db.yfinance_indicators.insert_one(indicator_doc)
                inserted_count += 1
                logger.info(f"✓ {name} 추가 (Yahoo Finance: {ticker})")
            except DuplicateKeyError:
                logger.warning(f"⚠️ {name} 중복 키 오류 (무시)")
    
    logger.info(f"✅ yfinance_indicators 세팅 완료: {inserted_count}개 추가, {updated_count}개 업데이트")


def seed_stocks_from_defaults(db):
    """
    stocks 컬렉션에 기본 주식 데이터 세팅
    seed_mongodb_data.py의 seed_stocks 함수와 동일한 로직
    """
    logger.info("📦 stocks 컬렉션에 기본 주식 데이터 세팅 중...")
    
    stocks_data = [
        {"stock_name": "애플", "ticker": "AAPL", "is_etf": False, "leverage_ticker": "AAPU", "is_active": True},
        {"stock_name": "마이크로소프트", "ticker": "MSFT", "is_etf": False, "leverage_ticker": "MSFU", "is_active": True},
        {"stock_name": "아마존", "ticker": "AMZN", "is_etf": False, "leverage_ticker": "AMZU", "is_active": True},
        {"stock_name": "구글 A", "ticker": "GOOGL", "is_etf": False, "leverage_ticker": "GGLL", "is_active": True},
        {"stock_name": "메타", "ticker": "META", "is_etf": False, "leverage_ticker": "FBL", "is_active": True},
        {"stock_name": "엔비디아", "ticker": "NVDA", "is_etf": False, "leverage_ticker": "NVDL", "is_active": True},
        {"stock_name": "인텔", "ticker": "INTC", "is_etf": False, "leverage_ticker": "INTL", "is_active": True},
        {"stock_name": "마이크론", "ticker": "MU", "is_etf": False, "leverage_ticker": "MUU", "is_active": True},
        {"stock_name": "브로드컴", "ticker": "AVGO", "is_etf": False, "leverage_ticker": "AVGL", "is_active": True},
        {"stock_name": "텍사스 인스트루먼트", "ticker": "TXN", "is_etf": False, "leverage_ticker": "TXNL", "is_active": True},
        {"stock_name": "AMD", "ticker": "AMD", "is_etf": False, "leverage_ticker": "AMDL", "is_active": True},
        {"stock_name": "어플라이드 머티리얼즈", "ticker": "AMAT", "is_etf": False, "is_active": True},
        {"stock_name": "TSMC", "ticker": "TSM", "is_etf": False, "leverage_ticker": "TSML", "is_active": True},
        {"stock_name": "크리도 테크놀로지 그룹 홀딩", "ticker": "CRDO", "is_etf": False, "leverage_ticker": "CRDL", "is_active": True},
        {"stock_name": "셀레스티카", "ticker": "CELH", "is_etf": False, "is_active": True},
        {"stock_name": "월마트", "ticker": "WMT", "is_etf": False, "leverage_ticker": "WMTU", "is_active": True},
        {"stock_name": "버티브 홀딩스", "ticker": "VRT", "is_etf": False, "leverage_ticker": "VRTL", "is_active": True},
        {"stock_name": "비스트라 에너지", "ticker": "VST", "is_etf": False, "leverage_ticker": "VSTL", "is_active": True},
        {"stock_name": "블룸에너지", "ticker": "BE", "is_etf": False, "leverage_ticker": "BEL", "is_active": True},
        {"stock_name": "오클로", "ticker": "OKLO", "is_etf": False, "leverage_ticker": "OKLL", "is_active": True},
        {"stock_name": "팔란티어", "ticker": "PLTR", "is_etf": False, "leverage_ticker": "PTIR", "is_active": True},
        {"stock_name": "세일즈포스", "ticker": "CRM", "is_etf": False, "leverage_ticker": "CRML", "is_active": True},
        {"stock_name": "오라클", "ticker": "ORCL", "is_etf": False, "leverage_ticker": "ORCL", "is_active": True},
        {"stock_name": "앱플로빈", "ticker": "APP", "is_etf": False, "leverage_ticker": "APVL", "is_active": True},
        {"stock_name": "팔로알토 네트웍스", "ticker": "PANW", "is_etf": False, "leverage_ticker": "PANL", "is_active": True},
        {"stock_name": "크라우드 스트라이크", "ticker": "CRWD", "is_etf": False, "leverage_ticker": "CRWL", "is_active": True},
        {"stock_name": "스노우플레이크", "ticker": "SNOW", "is_etf": False, "leverage_ticker": "SNOL", "is_active": True},
        {"stock_name": "로빈후드", "ticker": "HOOD", "is_etf": False, "leverage_ticker": "HODL", "is_active": True},
        {"stock_name": "일라이릴리", "ticker": "LLY", "is_etf": False, "leverage_ticker": "LLYL", "is_active": True},
        {"stock_name": "존슨앤존슨", "ticker": "JNJ", "is_etf": False, "leverage_ticker": "JNJL", "is_active": True},
        {"stock_name": "S&P 500 ETF", "ticker": "SPY", "is_etf": True, "leverage_ticker": "UPRO", "is_active": True},
        {"stock_name": "QQQ ETF", "ticker": "QQQ", "is_etf": True, "leverage_ticker": "TQQQ", "is_active": True},
        {"stock_name": "SOXX ETF", "ticker": "SOXX", "is_etf": True, "leverage_ticker": "SOXL", "is_active": True},
        {"stock_name": "테슬라", "ticker": "TSLA", "is_etf": False, "leverage_ticker": "TSLL", "is_active": True},
    ]
    
    inserted_count = 0
    updated_count = 0
    
    for stock in stocks_data:
        stock_doc = {
            "ticker": stock["ticker"],
            "stock_name": stock["stock_name"],
            "is_etf": stock["is_etf"],
            "leverage_ticker": stock.get("leverage_ticker"),
            "is_active": stock["is_active"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        try:
            existing = db.stocks.find_one({"ticker": stock_doc["ticker"]})
            
            if existing:
                # 업데이트
                db.stocks.update_one(
                    {"ticker": stock_doc["ticker"]},
                    {"$set": {
                        "stock_name": stock_doc["stock_name"],
                        "is_etf": stock_doc["is_etf"],
                        "leverage_ticker": stock_doc["leverage_ticker"],
                        "is_active": stock_doc["is_active"],
                        "updated_at": stock_doc["updated_at"]
                    }}
                )
                updated_count += 1
                logger.info(f"✓ {stock_doc['stock_name']} ({stock_doc['ticker']}) 업데이트")
            else:
                # 삽입
                db.stocks.insert_one(stock_doc)
                inserted_count += 1
                logger.info(f"✓ {stock_doc['stock_name']} ({stock_doc['ticker']}) 추가")
        except DuplicateKeyError:
            logger.warning(f"⚠️ {stock_doc['stock_name']} ({stock_doc['ticker']}) 중복 키 오류 (무시)")
        except Exception as e:
            logger.error(f"❌ {stock_doc['stock_name']} ({stock_doc['ticker']}) 처리 실패: {e}")
    
    logger.info(f"✅ stocks 세팅 완료: {inserted_count}개 추가, {updated_count}개 업데이트")


def create_collections(clear_first=False):
    """모든 collections와 인덱스 생성, 그리고 기본 데이터 세팅"""
    try:
        # MongoDB 연결
        mongodb_url = _build_mongodb_url()
        database_name = (
            os.getenv("MONGODB_DATABASE") or 
            settings.MONGODB_DATABASE or 
            "stock_trading"
        )
        
        # 비밀번호 마스킹 (로그용)
        display_url = mongodb_url
        mongo_password = os.getenv("MONGO_PASSWORD") or os.getenv("MONGODB_PASSWORD")
        if mongo_password:
            display_url = display_url.replace(quote_plus(mongo_password), "****")
        
        logger.info(f"MongoDB 연결 시도: {display_url}")
        logger.info(f"데이터베이스: {database_name}")
        
        client = MongoClient(
            mongodb_url,
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
        )
        
        # 연결 테스트
        client.admin.command('ping')
        logger.info("✅ MongoDB 연결 성공!")
        
        db = client[database_name]
        
        # 1단계: 데이터 삭제 (선택사항)
        if clear_first:
            logger.info("\n" + "=" * 60)
            logger.info("🗑️  기존 데이터 삭제 중...")
            logger.info("=" * 60)
            clear_all_collections(db)
            logger.info("")
        
        # 2단계: 컬렉션 목록
        collections_to_create = [
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
        
        logger.info("\n" + "=" * 60)
        logger.info("📦 컬렉션 생성 중...")
        logger.info("=" * 60)
        for collection_name in collections_to_create:
            # 컬렉션이 없으면 생성 (데이터 삽입 시 자동 생성되지만 명시적으로 생성)
            if collection_name not in db.list_collection_names():
                db.create_collection(collection_name)
                logger.info(f"✓ {collection_name} 컬렉션 생성")
            else:
                logger.info(f"○ {collection_name} 컬렉션 이미 존재")
        
        logger.info("\n" + "=" * 60)
        logger.info("🔍 인덱스 생성 중...")
        logger.info("=" * 60)
        
        # 기존 인덱스 정리 및 재생성
        def create_index_safe(collection, index_spec, unique=False, name=None, sparse=False):
            """인덱스 생성 (기존 인덱스가 있으면 삭제 후 재생성)"""
            try:
                # 기존 인덱스 삭제
                if name:
                    try:
                        collection.drop_index(name)
                        logger.info(f"  기존 인덱스 '{name}' 삭제")
                    except:
                        pass
                else:
                    # name이 없으면 key pattern으로 삭제 시도
                    try:
                        collection.drop_index(list(index_spec.keys()))
                        logger.info(f"  기존 인덱스 삭제")
                    except:
                        pass
                
                # 새 인덱스 생성
                if unique:
                    # unique 인덱스의 경우 null 값이 있는 문서 처리
                    if name == "ticker_unique":
                        # ticker가 null인 문서 제거 또는 수정
                        null_count = collection.count_documents({"ticker": None})
                        if null_count > 0:
                            logger.warning(f"  ticker가 null인 문서 {null_count}개 발견. 삭제합니다.")
                            collection.delete_many({"ticker": None})
                    elif name == "stock_name_unique":
                        # stock_name이 null인 문서 제거
                        null_count = collection.count_documents({"stock_name": None})
                        if null_count > 0:
                            logger.warning(f"  stock_name이 null인 문서 {null_count}개 발견. 삭제합니다.")
                            collection.delete_many({"stock_name": None})
                
                # 인덱스 생성 옵션
                index_options = {"unique": unique, "name": name}
                if sparse:
                    index_options["sparse"] = True
                
                collection.create_index(list(index_spec.items()), **index_options)
                return True
            except Exception as e:
                logger.warning(f"  인덱스 생성 실패: {e}")
                return False
        
        # 1. stocks collection
        logger.info("stocks collection 인덱스 생성 중...")
        create_index_safe(db.stocks, {"ticker": 1}, unique=True, name="ticker_unique")
        create_index_safe(db.stocks, {"stock_name": 1}, unique=True, name="stock_name_unique")
        create_index_safe(db.stocks, {"is_active": 1}, unique=False, name="is_active_idx")
        logger.info("✓ stocks 인덱스 생성 완료")
        
        # 2. users collection
        logger.info("users collection 인덱스 생성 중...")
        create_index_safe(db.users, {"user_id": 1}, unique=True, name="user_id_unique")
        logger.info("✓ users 인덱스 생성 완료")
        
        # 3. user_stocks collection
        logger.info("user_stocks collection 인덱스 생성 중...")
        create_index_safe(db.user_stocks, {"user_id": 1, "stock_id": 1}, unique=True, name="user_stock_unique")
        create_index_safe(db.user_stocks, {"user_id": 1, "is_active": 1}, unique=False, name="user_active_stocks_idx")
        create_index_safe(db.user_stocks, {"ticker": 1}, unique=False, name="ticker_idx")
        logger.info("✓ user_stocks 인덱스 생성 완료")
        
        # 4. economic_data collection
        logger.info("economic_data collection 인덱스 생성 중...")
        create_index_safe(db.economic_data, {"date": 1}, unique=True, name="date_unique")
        logger.info("✓ economic_data 인덱스 생성 완료")
        
        # 5. daily_stock_data collection (실제 주가 데이터 저장)
        logger.info("daily_stock_data collection 인덱스 생성 중...")
        create_index_safe(db.daily_stock_data, {"date": 1}, unique=True, name="date_unique")
        # recommendations 필드 존재 여부로 필터링하는 쿼리를 위한 인덱스
        create_index_safe(db.daily_stock_data, {"recommendations": 1}, unique=False, name="recommendations_exists_idx", sparse=True)
        # 날짜 범위 조회 최적화 (recommendations 필드가 있는 문서만)
        create_index_safe(db.daily_stock_data, {"date": 1, "recommendations": 1}, unique=False, name="date_recommendations_idx")
        # sentiment 필드 존재 여부로 필터링하는 쿼리를 위한 인덱스
        create_index_safe(db.daily_stock_data, {"sentiment": 1}, unique=False, name="sentiment_exists_idx", sparse=True)
        # 날짜 범위 조회 최적화 (sentiment 필드가 있는 문서만)
        create_index_safe(db.daily_stock_data, {"date": 1, "sentiment": 1}, unique=False, name="date_sentiment_idx")
        # predictions 필드 존재 여부로 필터링하는 쿼리를 위한 인덱스
        create_index_safe(db.daily_stock_data, {"predictions": 1}, unique=False, name="predictions_exists_idx", sparse=True)
        # 날짜 범위 조회 최적화 (predictions 필드가 있는 문서만)
        create_index_safe(db.daily_stock_data, {"date": 1, "predictions": 1}, unique=False, name="date_predictions_idx")
        # analysis 필드 존재 여부로 필터링하는 쿼리를 위한 인덱스
        create_index_safe(db.daily_stock_data, {"analysis": 1}, unique=False, name="analysis_exists_idx", sparse=True)
        # 날짜 범위 조회 최적화 (analysis 필드가 있는 문서만)
        create_index_safe(db.daily_stock_data, {"date": 1, "analysis": 1}, unique=False, name="date_analysis_idx")
        # stocks 필드 존재 여부로 필터링하는 쿼리를 위한 인덱스
        create_index_safe(db.daily_stock_data, {"stocks": 1}, unique=False, name="stocks_exists_idx", sparse=True)
        # volumes 필드 존재 여부로 필터링하는 쿼리를 위한 인덱스
        create_index_safe(db.daily_stock_data, {"volumes": 1}, unique=False, name="volumes_exists_idx", sparse=True)
        logger.info("✓ daily_stock_data 인덱스 생성 완료")
        
        # 6. fred_indicators collection
        logger.info("fred_indicators collection 인덱스 생성 중...")
        create_index_safe(db.fred_indicators, {"code": 1}, unique=True, name="code_unique")
        create_index_safe(db.fred_indicators, {"name": 1}, unique=True, name="name_unique")
        create_index_safe(db.fred_indicators, {"type": 1}, unique=False, name="type_idx")
        create_index_safe(db.fred_indicators, {"is_active": 1}, unique=False, name="is_active_idx")
        logger.info("✓ fred_indicators 인덱스 생성 완료")
        
        # 7. yfinance_indicators collection
        logger.info("yfinance_indicators collection 인덱스 생성 중...")
        create_index_safe(db.yfinance_indicators, {"ticker": 1}, unique=True, name="ticker_unique")
        create_index_safe(db.yfinance_indicators, {"name": 1}, unique=True, name="name_unique")
        create_index_safe(db.yfinance_indicators, {"type": 1}, unique=False, name="type_idx")
        create_index_safe(db.yfinance_indicators, {"is_active": 1}, unique=False, name="is_active_idx")
        logger.info("✓ yfinance_indicators 인덱스 생성 완료")
        
        # 8. stock_recommendations collection
        logger.info("stock_recommendations collection 인덱스 생성 중...")
        # ticker와 date 기준 unique 인덱스 (upsert 최적화)
        create_index_safe(db.stock_recommendations, {"ticker": 1, "date": 1}, unique=True, name="ticker_date_unique")
        # 사용자별 날짜 역순 조회
        create_index_safe(db.stock_recommendations, {"user_id": 1, "date": -1}, unique=False, name="user_date_idx")
        # 종목별 날짜 역순 조회 (시계열 분석용)
        create_index_safe(db.stock_recommendations, {"ticker": 1, "date": -1}, unique=False, name="ticker_date_idx")
        # 날짜별 조회 최적화
        create_index_safe(db.stock_recommendations, {"date": -1}, unique=False, name="date_idx")
        # 추천 여부 필터링용 인덱스
        create_index_safe(db.stock_recommendations, {"is_recommended": 1, "date": -1}, unique=False, name="recommended_date_idx")
        # 종목별 추천 여부 필터링 (종목별 추천 이력 조회 최적화)
        create_index_safe(db.stock_recommendations, {"ticker": 1, "is_recommended": 1, "date": -1}, unique=False, name="ticker_recommended_date_idx")
        logger.info("✓ stock_recommendations 인덱스 생성 완료")
        
        # 9. stock_analysis collection
        logger.info("stock_analysis collection 인덱스 생성 중...")
        create_index_safe(db.stock_analysis, {"date": 1, "ticker": 1, "user_id": 1}, unique=False, name="date_ticker_user_idx")
        create_index_safe(db.stock_analysis, {"user_id": 1, "date": -1}, unique=False, name="user_date_idx")
        logger.info("✓ stock_analysis 인덱스 생성 완료")
        
        # 10. stock_predictions collection
        logger.info("stock_predictions collection 인덱스 생성 중...")
        # 날짜+티커 복합 인덱스 (unique, upsert 쿼리 최적화)
        create_index_safe(db.stock_predictions, {"date": 1, "ticker": 1}, unique=True, name="date_ticker_unique")
        # 날짜별 조회 최적화
        create_index_safe(db.stock_predictions, {"date": -1}, unique=False, name="date_idx")
        # 티커별 조회 최적화 (시계열 분석용)
        create_index_safe(db.stock_predictions, {"ticker": 1, "date": -1}, unique=False, name="ticker_date_idx")
        logger.info("✓ stock_predictions 인덱스 생성 완료")
        
        # 11. sentiment_analysis collection
        logger.info("sentiment_analysis collection 인덱스 생성 중...")
        # ticker와 date 기준 unique 인덱스 (upsert 최적화)
        create_index_safe(db.sentiment_analysis, {"ticker": 1, "date": 1}, unique=True, name="ticker_date_unique")
        # 날짜별 조회 최적화
        create_index_safe(db.sentiment_analysis, {"date": -1}, unique=False, name="date_idx")
        # 티커별 날짜 역순 조회 (시계열 분석용)
        create_index_safe(db.sentiment_analysis, {"ticker": 1, "date": -1}, unique=False, name="ticker_date_idx")
        logger.info("✓ sentiment_analysis 인덱스 생성 완료")
        
        # 12. trading_configs collection
        logger.info("trading_configs collection 인덱스 생성 중...")
        create_index_safe(db.trading_configs, {"user_id": 1}, unique=True, name="user_id_unique")
        logger.info("✓ trading_configs 인덱스 생성 완료")
        
        # 13. trading_logs collection
        logger.info("trading_logs collection 인덱스 생성 중...")
        create_index_safe(db.trading_logs, {"user_id": 1, "created_at": -1}, unique=False, name="user_created_idx")
        create_index_safe(db.trading_logs, {"ticker": 1, "created_at": -1}, unique=False, name="ticker_created_idx")
        create_index_safe(db.trading_logs, {"order_type": 1, "created_at": -1}, unique=False, name="order_type_created_idx")
        logger.info("✓ trading_logs 인덱스 생성 완료")
        
        logger.info("\n✅ 모든 컬렉션과 인덱스 생성 완료!")
        
        # 3단계: 기본 데이터 세팅
        logger.info("\n" + "=" * 60)
        logger.info("📊 기본 설정 데이터 세팅 중...")
        logger.info("=" * 60)
        seed_fred_indicators_from_defaults(db)
        seed_yfinance_indicators_from_defaults(db)
        seed_stocks_from_defaults(db)
        
        # 생성된 컬렉션 목록 출력
        logger.info("\n" + "=" * 60)
        logger.info("📋 생성된 컬렉션 목록:")
        logger.info("=" * 60)
        for collection_name in db.list_collection_names():
            count = db[collection_name].count_documents({})
            indexes = list(db[collection_name].list_indexes())
            logger.info(f"  - {collection_name}: 문서 {count}개, 인덱스 {len(indexes)}개")
        
        client.close()
        logger.info("\n✅ 완료!")
        
    except ConnectionFailure as e:
        logger.error(f"❌ MongoDB 연결 실패: {e}")
        logger.error("MongoDB가 실행 중인지 확인해주세요.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 오류 발생: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    if not settings.USE_MONGODB:
        logger.warning("⚠️  USE_MONGODB 설정이 False입니다.")
        logger.warning("그래도 컬렉션 생성은 진행합니다...\n")
    
    # 데이터 삭제 여부 확인
    clear_first = False
    if len(sys.argv) > 1 and sys.argv[1] == "--clear":
        print("=" * 60)
        print("⚠️  경고: 기존 데이터를 모두 삭제합니다!")
        print("=" * 60)
        response = input("정말로 모든 데이터를 삭제하시겠습니까? (yes/no): ")
        if response.lower() in ['yes', 'y']:
            clear_first = True
        else:
            print("데이터 삭제를 취소하고 컬렉션 생성만 진행합니다.\n")
    
    create_collections(clear_first=clear_first)
