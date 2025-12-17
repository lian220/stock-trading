"""
MongoDB 스키마 및 인덱스 생성 스크립트

이 스크립트는 MongoDB에 필요한 collections과 인덱스를 생성합니다.
"""
import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.db.mongodb import get_sync_client
from app.core.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_indexes():
    """모든 collections에 인덱스 생성"""
    try:
        client, db = get_sync_client()
        
        logger.info("MongoDB 인덱스 생성 시작...")
        
        # 1. stocks collection
        logger.info("stocks collection 인덱스 생성 중...")
        db.stocks.create_index([("ticker", 1)], unique=True, name="ticker_unique")
        db.stocks.create_index([("stock_name", 1)], unique=True, name="stock_name_unique")
        db.stocks.create_index([("is_active", 1)], name="is_active_idx")
        logger.info("✓ stocks 인덱스 생성 완료")
        
        # 2. users collection
        logger.info("users collection 인덱스 생성 중...")
        db.users.create_index([("user_id", 1)], unique=True, name="user_id_unique")
        logger.info("✓ users 인덱스 생성 완료")
        
        # 3. user_stocks collection
        logger.info("user_stocks collection 인덱스 생성 중...")
        db.user_stocks.create_index(
            [("user_id", 1), ("stock_id", 1)], 
            unique=True, 
            name="user_stock_unique"
        )
        db.user_stocks.create_index([("user_id", 1), ("is_active", 1)], name="user_active_stocks_idx")
        db.user_stocks.create_index([("ticker", 1)], name="ticker_idx")
        logger.info("✓ user_stocks 인덱스 생성 완료")
        
        # 4. economic_data collection
        logger.info("economic_data collection 인덱스 생성 중...")
        db.economic_data.create_index([("date", 1)], unique=True, name="date_unique")
        logger.info("✓ economic_data 인덱스 생성 완료")
        
        # 5. daily_stock_data collection
        logger.info("daily_stock_data collection 인덱스 생성 중...")
        db.daily_stock_data.create_index([("date", 1)], unique=True, name="date_unique")
        # recommendations 필드 존재 여부로 필터링하는 쿼리를 위한 인덱스
        db.daily_stock_data.create_index([("recommendations", 1)], name="recommendations_exists_idx", sparse=True)
        # 날짜 범위 조회 최적화 (recommendations 필드가 있는 문서만)
        db.daily_stock_data.create_index([("date", 1), ("recommendations", 1)], name="date_recommendations_idx")
        # sentiment 필드 존재 여부로 필터링하는 쿼리를 위한 인덱스
        db.daily_stock_data.create_index([("sentiment", 1)], name="sentiment_exists_idx", sparse=True)
        # 날짜 범위 조회 최적화 (sentiment 필드가 있는 문서만)
        db.daily_stock_data.create_index([("date", 1), ("sentiment", 1)], name="date_sentiment_idx")
        # predictions 필드 존재 여부로 필터링하는 쿼리를 위한 인덱스
        db.daily_stock_data.create_index([("predictions", 1)], name="predictions_exists_idx", sparse=True)
        # 날짜 범위 조회 최적화 (predictions 필드가 있는 문서만)
        db.daily_stock_data.create_index([("date", 1), ("predictions", 1)], name="date_predictions_idx")
        # analysis 필드 존재 여부로 필터링하는 쿼리를 위한 인덱스
        db.daily_stock_data.create_index([("analysis", 1)], name="analysis_exists_idx", sparse=True)
        # 날짜 범위 조회 최적화 (analysis 필드가 있는 문서만)
        db.daily_stock_data.create_index([("date", 1), ("analysis", 1)], name="date_analysis_idx")
        # stocks 필드 존재 여부로 필터링하는 쿼리를 위한 인덱스
        db.daily_stock_data.create_index([("stocks", 1)], name="stocks_exists_idx", sparse=True)
        # volumes 필드 존재 여부로 필터링하는 쿼리를 위한 인덱스
        db.daily_stock_data.create_index([("volumes", 1)], name="volumes_exists_idx", sparse=True)
        logger.info("✓ daily_stock_data 인덱스 생성 완료")
        
        # 6. fred_indicators collection
        logger.info("fred_indicators collection 인덱스 생성 중...")
        db.fred_indicators.create_index([("code", 1)], unique=True, name="code_unique")
        db.fred_indicators.create_index([("name", 1)], unique=True, name="name_unique")
        db.fred_indicators.create_index([("type", 1)], name="type_idx")
        db.fred_indicators.create_index([("is_active", 1)], name="is_active_idx")
        logger.info("✓ fred_indicators 인덱스 생성 완료")
        
        # 7. yfinance_indicators collection
        logger.info("yfinance_indicators collection 인덱스 생성 중...")
        db.yfinance_indicators.create_index([("ticker", 1)], unique=True, name="ticker_unique")
        db.yfinance_indicators.create_index([("name", 1)], unique=True, name="name_unique")
        db.yfinance_indicators.create_index([("type", 1)], name="type_idx")
        db.yfinance_indicators.create_index([("is_active", 1)], name="is_active_idx")
        logger.info("✓ yfinance_indicators 인덱스 생성 완료")
        
        # 8. stock_recommendations collection
        logger.info("stock_recommendations collection 인덱스 생성 중...")
        # ticker와 date 기준 unique 인덱스 (upsert 최적화)
        db.stock_recommendations.create_index(
            [("ticker", 1), ("date", 1)], 
            unique=True,
            name="ticker_date_unique"
        )
        # 사용자별 날짜 역순 조회
        db.stock_recommendations.create_index([("user_id", 1), ("date", -1)], name="user_date_idx")
        # 종목별 날짜 역순 조회 (시계열 분석용)
        db.stock_recommendations.create_index([("ticker", 1), ("date", -1)], name="ticker_date_idx")
        # 날짜별 조회 최적화
        db.stock_recommendations.create_index([("date", -1)], name="date_idx")
        # 추천 여부 필터링용 인덱스
        db.stock_recommendations.create_index([("is_recommended", 1), ("date", -1)], name="recommended_date_idx")
        # 종목별 추천 여부 필터링 (종목별 추천 이력 조회 최적화)
        db.stock_recommendations.create_index(
            [("ticker", 1), ("is_recommended", 1), ("date", -1)], 
            name="ticker_recommended_date_idx"
        )
        logger.info("✓ stock_recommendations 인덱스 생성 완료")
        
        # 9. stock_analysis collection
        logger.info("stock_analysis collection 인덱스 생성 중...")
        db.stock_analysis.create_index(
            [("date", 1), ("ticker", 1), ("user_id", 1)], 
            name="date_ticker_user_idx"
        )
        db.stock_analysis.create_index([("user_id", 1), ("date", -1)], name="user_date_idx")
        logger.info("✓ stock_analysis 인덱스 생성 완료")
        
        # 10. stock_predictions collection
        logger.info("stock_predictions collection 인덱스 생성 중...")
        # 날짜+티커 복합 인덱스 (unique, upsert 쿼리 최적화)
        db.stock_predictions.create_index(
            [("date", 1), ("ticker", 1)], 
            unique=True, 
            name="date_ticker_unique"
        )
        # 날짜별 조회 최적화
        db.stock_predictions.create_index([("date", -1)], name="date_idx")
        # 티커별 조회 최적화 (시계열 분석용)
        db.stock_predictions.create_index([("ticker", 1), ("date", -1)], name="ticker_date_idx")
        logger.info("✓ stock_predictions 인덱스 생성 완료")
        
        # 11. sentiment_analysis collection
        logger.info("sentiment_analysis collection 인덱스 생성 중...")
        # ticker와 date 기준 unique 인덱스 (upsert 최적화)
        db.sentiment_analysis.create_index([("ticker", 1), ("date", 1)], unique=True, name="ticker_date_unique")
        # 날짜별 조회 최적화
        db.sentiment_analysis.create_index([("date", -1)], name="date_idx")
        # 티커별 날짜 역순 조회 (시계열 분석용)
        db.sentiment_analysis.create_index([("ticker", 1), ("date", -1)], name="ticker_date_idx")
        logger.info("✓ sentiment_analysis 인덱스 생성 완료")
        
        # 12. trading_configs collection
        logger.info("trading_configs collection 인덱스 생성 중...")
        db.trading_configs.create_index([("user_id", 1)], unique=True, name="user_id_unique")
        logger.info("✓ trading_configs 인덱스 생성 완료")
        
        # 13. trading_logs collection
        logger.info("trading_logs collection 인덱스 생성 중...")
        db.trading_logs.create_index([("user_id", 1), ("created_at", -1)], name="user_created_idx")
        db.trading_logs.create_index([("ticker", 1), ("created_at", -1)], name="ticker_created_idx")
        db.trading_logs.create_index([("order_type", 1), ("created_at", -1)], name="order_type_created_idx")
        logger.info("✓ trading_logs 인덱스 생성 완료")
        
        logger.info("\n✅ 모든 인덱스 생성 완료!")
        
        # 인덱스 목록 출력
        logger.info("\n생성된 인덱스 확인:")
        collections = [
            "stocks", "users", "user_stocks", "economic_data", "daily_stock_data",
            "fred_indicators", "yfinance_indicators", "stock_recommendations",
            "stock_analysis", "stock_predictions", "sentiment_analysis", "trading_configs", "trading_logs"
        ]
        
        for collection_name in collections:
            indexes = list(db[collection_name].list_indexes())
            logger.info(f"\n{collection_name}:")
            for idx in indexes:
                logger.info(f"  - {idx.get('name', 'unknown')}: {idx.get('key', {})}")
        
    except Exception as e:
        logger.error(f"인덱스 생성 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    if not settings.USE_MONGODB:
        logger.error("USE_MONGODB 설정이 False입니다. .env 파일에서 USE_MONGODB=true로 설정해주세요.")
        sys.exit(1)
    
    try:
        # 인덱스 생성
        create_indexes()
        
        logger.info("\n✅ MongoDB 스키마 설정 완료!")
        
    except Exception as e:
        logger.error(f"스크립트 실행 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
