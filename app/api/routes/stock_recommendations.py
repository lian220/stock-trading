from fastapi import APIRouter, HTTPException, Query
from app.services.stock_recommendation_service import StockRecommendationService
from app.utils.scheduler import run_auto_buy_now, start_scheduler, stop_scheduler, stock_scheduler, run_auto_sell_now, start_sell_scheduler, stop_sell_scheduler, get_scheduler_status
from typing import Optional
from datetime import datetime
import pytz
import logging

router = APIRouter()
# 서비스 인스턴스는 매번 새로 생성하여 최신 주식 목록을 반영
# (모듈 레벨에서 한 번만 생성하면 MongoDB에 주식이 추가되어도 반영되지 않음)
logger = logging.getLogger(__name__)

def get_service():
    """최신 주식 매핑을 반영한 StockRecommendationService 인스턴스를 반환"""
    return StockRecommendationService()

def get_today_date() -> str:
    """오늘 날짜를 YYYY-MM-DD 형식으로 반환"""
    korea_tz = pytz.timezone('Asia/Seoul')
    return datetime.now(korea_tz).strftime('%Y-%m-%d')

@router.get("/recommended-stocks", response_model=dict)
async def get_recommended_stocks_route():
    """
    Accuracy가 80% 이상이고 상승 확률이 3% 이상인 추천 주식 목록을 반환합니다.
    상승 확률 기준으로 내림차순 정렬됩니다.
    """
    try:
        service = get_service()
        return service.get_stock_recommendations()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"추천 주식 조회 중 오류 발생: {str(e)}")

@router.get("/recommended-stocks/with-sentiment", response_model=dict)
async def get_recommended_stocks_with_sentiment():
    """
    get_stock_recommendations의 결과를 ticker_sentiment_analysis에서 
    average_sentiment_score >= 0.15인 데이터와 결합하여 반환합니다.
    """
    try:
        service = get_service()
        result = service.get_recommendations_with_sentiment()
        if not result["results"]:
            return {"message": "조건을 만족하는 추천 주식이 없습니다", "results": []}
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"추천 주식 및 감정 분석 조회 중 오류 발생: {str(e)}")

@router.post("/recommended-stocks/analyze-news-sentiment", response_model=dict)
async def analyze_news_sentiment(
    start_date: Optional[str] = Query(None, description="분석 시작 날짜 (YYYY-MM-DD 형식, 기본값: 오늘)"),
    end_date: Optional[str] = Query(None, description="분석 종료 날짜 (YYYY-MM-DD 형식, 기본값: 오늘)")
):
    """
    추천 주식 목록에서 추출한 티커에 대해 뉴스 감정 분석을 수행합니다.
    실시간으로 처리하고 결과를 반환합니다.
    
    **날짜 범위 설정:**
    - `start_date`와 `end_date`가 없으면: 오늘 날짜 데이터를 분석합니다.
    - `start_date`와 `end_date`가 있으면: 해당 날짜 범위의 데이터를 분석합니다.
    """
    try:
        service = get_service()
        today = get_today_date()
        start_date = start_date or today
        end_date = end_date or today
        
        results = service.fetch_and_store_sentiment_for_recommendations(
            start_date=start_date,
            end_date=end_date
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"뉴스 감정 분석 중 오류 발생: {str(e)}")

@router.post("/recommended-stocks/generate-technical-recommendations", response_model=dict)
async def generate_technical_recommendations():
    """
    기술적 지표를 기반으로 추천 데이터를 생성하고 MongoDB에 저장합니다.
    
    **동작 방식:**
    - 최근 6개월(180일) 데이터를 자동으로 조회하여 분석합니다.
    - 기술적 지표(SMA20, SMA50, RSI, MACD) 계산을 위해 충분한 데이터를 확보합니다.
    
    **주의사항:**
    - 기술적 지표 계산을 위해 최소 50일 이상의 데이터가 필요합니다.
    - 기본적으로 최근 6개월 데이터를 사용하므로 충분한 데이터가 확보됩니다.
    """
    try:
        service = get_service()
        
        # 날짜 파라미터 없이 호출 (서비스에서 기본값 사용)
        recommendations = service.generate_technical_recommendations(
            start_date=None,
            end_date=None
        )
        return {"message": "기술적 추천 데이터가 성공적으로 생성되고 저장되었습니다", "data": recommendations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"기술적 추천 데이터 생성 중 오류 발생: {str(e)}")

@router.get("/recommended-stocks/with-technical-and-sentiment", response_model=dict)
async def get_recommended_stocks_with_technical_and_sentiment():
    """
    추천 주식 목록을 기술적 지표(stock_recommendations 테이블)와 감정 분석(ticker_sentiment_analysis 테이블)을
    결합하여 반환합니다.
    - stock_recommendations에서 골든_크로스=true, MACD_매수_신호=true, RSI<50 중 하나 이상 만족하는 종목 필터링
    - ticker_sentiment_analysis에서 average_sentiment_score >= 0.15인 데이터와 결합
    - get_stock_recommendations의 결과와 통합하여 반환
    """
    try:
        service = get_service()
        # API 호출 시에는 Slack 알림을 보내지 않음
        result = service.get_combined_recommendations_with_technical_and_sentiment(send_slack_notification=False)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"기술적 지표 및 감정 분석 조회 중 오류 발생: {str(e)}")

@router.post("/recommended-stocks/generate-complete-analysis", response_model=dict)
async def generate_complete_analysis():
    """
    기술적 지표 생성과 뉴스 감정 분석을 하나의 API로 통합하여 수행합니다.
    먼저 기술적 지표를 생성하고 저장한 다음, 뉴스 감정 분석을 수행합니다.
    두 기능의 결과를 통합하여 반환합니다.
    
    **동작 방식:**
    - 기술적 지표: 최근 6개월(180일) 데이터를 자동으로 조회하여 분석합니다.
    - 감정 분석: 오늘 날짜 기준으로 분석합니다.
    
    **주의사항:**
    - 기술적 지표 계산을 위해 최소 50일 이상의 데이터가 필요합니다.
    - 기본적으로 최근 6개월 데이터를 사용하므로 충분한 데이터가 확보됩니다.
    """
    try:
        service = get_service()
        today = get_today_date()
        
        # 1. 기술적 지표 생성 및 저장 (날짜 파라미터 없이 호출)
        logger.info(f"통합 분석 시작: 1단계 - 기술적 지표 생성 시작... (최근 6개월 데이터 사용)")
        tech_results = service.generate_technical_recommendations(
            start_date=None,
            end_date=None
        )
        tech_count = len(tech_results.get("data", []))
        logger.info(f"통합 분석: 1단계 완료 - 기술적 지표 생성 완료 ({tech_count}개 종목)")
        
        # 2. 뉴스 감정 분석 수행 (오늘 날짜 기준)
        logger.info(f"통합 분석: 2단계 - 뉴스 감정 분석 시작... (오늘 날짜: {today})")
        sentiment_results = service.fetch_and_store_sentiment_for_recommendations(
            start_date=today,
            end_date=today
        )
        sentiment_count = len(sentiment_results.get("results", []))
        logger.info(f"통합 분석: 2단계 완료 - 뉴스 감정 분석 완료 ({sentiment_count}개 티커)")
        
        # 3. 통합 분석 조회
        logger.info("통합 분석: 3단계 - 통합 분석 결과 조회 시작...")
        # 통합 분석 완료 시 슬랙 알림 전송
        combined_results = service.get_combined_recommendations_with_technical_and_sentiment(send_slack_notification=True)
        combined_count = len(combined_results.get("results", []))
        logger.info(f"통합 분석: 3단계 완료 - 통합 분석 결과 조회 완료 ({combined_count}개 추천 종목)")
        
        # 4. 결과 통합 및 반환
        logger.info("=" * 60)
        logger.info("통합 분석 완료:")
        logger.info(f"  - 기술적 지표 분석: {tech_count}개 종목 (최근 6개월 데이터 사용)")
        logger.info(f"  - 감정 분석: {sentiment_count}개 티커 (오늘 날짜: {today})")
        logger.info(f"  - 최종 추천 종목: {combined_count}개")
        logger.info("=" * 60)
        
        return {
            "message": "통합 분석이 완료되었습니다",
            "date_range": {
                "start_date": start_date,
                "end_date": end_date
            },
            "technical_analysis": {
                "message": tech_results["message"],
                "count": tech_count,
            },
            "sentiment_analysis": {
                "message": sentiment_results["message"],
                "count": sentiment_count,
            },
            "combined_results": combined_results
        }
    except Exception as e:
        logger.error(f"통합 분석 중 오류 발생: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"통합 분석 중 오류 발생: {str(e)}")

@router.get("/sell-candidates", response_model=dict)
async def get_sell_candidates():
    """
    매도 대상 종목을 조회하는 API
    
    다음 조건에 해당하는 보유 종목이 매도 대상으로 식별됩니다:
    
    1. 구매가 대비 현재가가 +5% 이상(익절) 또는 -5% 이하(손절)인 종목
    2. 감성 점수 < -0.15이고 기술적 지표 중 2개 이상 매도 신호인 종목
    3. 기술적 지표 중 3개 이상 매도 신호인 종목
    
    기술적 매도 신호:
    - 데드 크로스 (골든_크로스 = False)
    - 과매수 구간 (RSI > 70)
    - MACD 매도 신호 (MACD_매수_신호 = False)
    
    응답에는 각 매도 대상 종목에 대한 상세 정보와 매도 근거가 포함됩니다.
    """
    try:
        service = get_service()
        result = service.get_stocks_to_sell()
        return result
    except Exception as e:
        print(f"매도 대상 종목 조회 중 오류 발생: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"매도 대상 종목 조회 중 오류 발생: {str(e)}")

@router.post("/purchase/trigger", response_model=dict)
async def trigger_auto_purchase():
    """
    자동 매수 프로세스를 수동으로 트리거합니다. (테스트 및 즉시 실행용)
    
    이 API는 스케줄러에 설정된 자동 매수 로직을 즉시 실행합니다.
    - 매수 대상: get_combined_recommendations_with_technical_and_sentiment() 함수 호출하여 종목 추출
    - 해당 종목에 대해 한국투자증권 API를 통해 현재가 조회 및 매수 주문
    
    응답은 매수 프로세스가 트리거되었다는 메시지만 반환하며, 실제 처리 결과는 서버 로그에서 확인할 수 있습니다.
    """
    try:
        run_auto_buy_now()
        return {"message": "자동 매수 프로세스가 트리거되었습니다. 로그를 확인하세요."}
    except Exception as e:
        print(f"자동 매수 트리거 중 오류 발생: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"자동 매수 트리거 중 오류 발생: {str(e)}")

@router.post("/purchase/scheduler/start", response_model=dict)
async def start_auto_purchase_scheduler():
    """
    자동 매수 스케줄러를 시작합니다.
    
    스케줄러는 한국 시간 기준 매일 밤 12시(00:00)에 자동 매수 프로세스를 실행합니다.
    이미 실행 중인 경우 메시지만 반환합니다.
    """
    try:
        result = start_scheduler()
        if result:
            return {"message": "자동 매수 스케줄러가 시작되었습니다. 매일 밤 12시에 자동 매수가 실행됩니다."}
        else:
            return {"message": "자동 매수 스케줄러가 이미 실행 중입니다."}
    except Exception as e:
        print(f"스케줄러 시작 중 오류 발생: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"스케줄러 시작 중 오류 발생: {str(e)}")

@router.post("/purchase/scheduler/stop", response_model=dict)
async def stop_auto_purchase_scheduler():
    """
    자동 매수 스케줄러를 중지합니다.
    
    중지 후에는 더 이상 자동 매수가 실행되지 않습니다.
    다시 시작하려면 /purchase/scheduler/start API를 호출해야 합니다.
    이미 중지된 경우 메시지만 반환합니다.
    """
    try:
        result = stop_scheduler()
        if result:
            return {"message": "자동 매수 스케줄러가 중지되었습니다."}
        else:
            return {"message": "자동 매수 스케줄러가 이미 중지되었습니다."}
    except Exception as e:
        print(f"스케줄러 중지 중 오류 발생: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"스케줄러 중지 중 오류 발생: {str(e)}")

@router.get("/scheduler/status", response_model=dict)
async def get_scheduler_status():
    """
    자동 매수/매도 스케줄러의 현재 상태를 반환합니다.
    
    반환값:
    - buy_running: 매수 스케줄러 실행 중 여부 (true/false)
    - sell_running: 매도 스케줄러 실행 중 여부 (true/false)
    """
    try:
        # 스케줄러 인스턴스에서 직접 상태 가져오기
        buy_running = stock_scheduler.running
        sell_running = stock_scheduler.sell_running
        
        return {
            "buy_running": buy_running,
            "sell_running": sell_running,
            "message": f"매수 스케줄러: {'실행 중' if buy_running else '중지됨'}, 매도 스케줄러: {'실행 중' if sell_running else '중지됨'}"
        }
    except Exception as e:
        print(f"스케줄러 상태 확인 중 오류 발생: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"스케줄러 상태 확인 중 오류 발생: {str(e)}")

@router.post("/sell/trigger", response_model=dict)
async def trigger_auto_sell():
    """
    자동 매도 프로세스를 수동으로 트리거합니다. (테스트 및 즉시 실행용)
    
    이 API는 매도 스케줄러에 설정된 자동 매도 로직을 즉시 실행합니다.
    - 매도 대상: get_stocks_to_sell() 함수 호출하여 종목 추출
    - 해당 종목에 대해 한국투자증권 API를 통해 현재가 조회 및 매도 주문
    
    응답은 매도 프로세스가 트리거되었다는 메시지만 반환하며, 실제 처리 결과는 서버 로그에서 확인할 수 있습니다.
    """
    try:
        run_auto_sell_now()
        return {"message": "자동 매도 프로세스가 트리거되었습니다. 로그를 확인하세요."}
    except Exception as e:
        print(f"자동 매도 트리거 중 오류 발생: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"자동 매도 트리거 중 오류 발생: {str(e)}")

@router.post("/sell/scheduler/start", response_model=dict)
async def start_auto_sell_scheduler():
    """
    자동 매도 스케줄러를 시작합니다.
    
    스케줄러는 1분마다 매도 대상을 확인하고 조건을 만족하는 종목에 대해 자동 매도 주문을 실행합니다.
    매도 조건:
    1. 구매가 대비 현재가가 +5% 이상(익절) 또는 -5% 이하(손절)인 종목
    2. 감성 점수 < -0.15이고 기술적 지표 중 2개 이상 매도 신호인 종목
    3. 기술적 지표 중 3개 이상 매도 신호인 종목
    
    이미 실행 중인 경우 메시지만 반환합니다.
    """
    try:
        result = start_sell_scheduler()
        if result:
            return {"message": "자동 매도 스케줄러가 시작되었습니다. 1분마다 매도 대상을 확인합니다."}
        else:
            return {"message": "자동 매도 스케줄러가 이미 실행 중입니다."}
    except Exception as e:
        print(f"매도 스케줄러 시작 중 오류 발생: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"매도 스케줄러 시작 중 오류 발생: {str(e)}")

@router.post("/sell/scheduler/stop", response_model=dict)
async def stop_auto_sell_scheduler():
    """
    자동 매도 스케줄러를 중지합니다.
    
    중지 후에는 더 이상 자동 매도가 실행되지 않습니다.
    다시 시작하려면 /sell/scheduler/start API를 호출해야 합니다.
    이미 중지된 경우 메시지만 반환합니다.
    """
    try:
        result = stop_sell_scheduler()
        if result:
            return {"message": "자동 매도 스케줄러가 중지되었습니다."}
        else:
            return {"message": "자동 매도 스케줄러가 이미 중지되었습니다."}
    except Exception as e:
        print(f"매도 스케줄러 중지 중 오류 발생: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"매도 스케줄러 중지 중 오류 발생: {str(e)}")

# ============================================================
# MongoDB 하이브리드 조회 API
# ============================================================
# 날짜별 통합 조회: daily_stock_data 컬렉션 사용
# 종목별 시계열 조회: stock_recommendations 컬렉션 사용
# ============================================================

@router.get("/mongodb/daily/{date}", response_model=dict)
async def get_daily_data_from_mongodb(date: str):
    """
    📊 날짜별 통합 데이터 조회 (대시보드용)
    
    특정 날짜의 주가 데이터, 추천 정보, 경제 지표를 한 번에 조회합니다.
    MongoDB의 `daily_stock_data` 컬렉션을 사용하여 효율적으로 조회합니다.
    
    **사용 시나리오:**
    - 대시보드에서 오늘의 추천 종목 표시
    - 특정 날짜의 모든 시장 데이터 조회
    - 날짜별 통합 분석
    
    **데이터 소스:** `daily_stock_data` 컬렉션
    
    **Parameters:**
    - `date`: 조회할 날짜 (YYYY-MM-DD 형식, 예: "2025-12-12")
    
    **Returns:**
    ```json
    {
      "message": "2025-12-12 날짜의 통합 데이터 조회 성공",
      "date": "2025-12-12",
      "data": {
        "stocks": {...},              // 주가 데이터
        "recommendations": {...},     // 추천 정보 (ticker별)
        "recommended_tickers": [...], // 추천 종목 티커 리스트
        "recommended_count": 10,      // 추천 종목 개수
        "fred_indicators": {...},     // FRED 경제 지표
        "yfinance_indicators": {...}   // Yahoo Finance 시장 지표
      }
    }
    ```
    
    **예시:**
    ```bash
    GET /stocks/mongodb/daily/2025-12-12
    ```
    """
    try:
        service = get_service()
        result = service.get_daily_recommendations_from_mongodb(date)
        return result
    except Exception as e:
        logger.error(f"MongoDB 날짜별 통합 조회 중 오류 발생: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"MongoDB 날짜별 통합 조회 중 오류 발생: {str(e)}")

@router.get("/mongodb/stocks/{ticker}/recommendations", response_model=dict)
async def get_stock_recommendation_history(
    ticker: str,
    start_date: str = None,
    end_date: str = None,
    only_recommended: bool = False
):
    """
    📈 종목별 추천 이력 조회 (시계열 분석용)
    
    특정 종목의 추천 데이터를 시계열로 조회합니다.
    MongoDB의 `stock_recommendations` 컬렉션을 사용하여 인덱스 최적화된 조회를 수행합니다.
    
    **사용 시나리오:**
    - 종목별 추천 패턴 분석
    - 시계열 차트 데이터 생성
    - 종목별 추천 빈도 분석
    - 특정 종목의 기술적 지표 변화 추적
    
    **데이터 소스:** `stock_recommendations` 컬렉션
    
    **Parameters:**
    - `ticker`: 조회할 종목 티커 (예: "AAPL", "MSFT")
    - `start_date`: 시작 날짜 (YYYY-MM-DD 형식, 선택, 기본값: 30일 전)
    - `end_date`: 종료 날짜 (YYYY-MM-DD 형식, 선택, 기본값: 오늘)
    - `only_recommended`: 추천된 날짜만 조회 여부 (기본값: false)
    
    **Returns:**
    ```json
    {
      "message": "AAPL 종목의 추천 이력 조회 성공",
      "ticker": "AAPL",
      "start_date": "2025-11-12",
      "end_date": "2025-12-12",
      "history": [
        {
          "date": "2025-12-12",
          "ticker": "AAPL",
          "technical_indicators": {
            "sma20": 150.0,
            "sma50": 145.0,
            "golden_cross": true,
            "rsi": 45.0,
            "macd": 2.5,
            "signal": 2.0,
            "macd_buy_signal": true
          },
          "is_recommended": true
        }
      ],
      "total_count": 30,
      "recommended_count": 10
    }
    ```
    
    **예시:**
    ```bash
    # 최근 30일 이력 조회
    GET /stocks/mongodb/stocks/AAPL/recommendations
    
    # 특정 기간 조회
    GET /stocks/mongodb/stocks/AAPL/recommendations?start_date=2025-12-01&end_date=2025-12-12
    
    # 추천된 날짜만 조회
    GET /stocks/mongodb/stocks/AAPL/recommendations?only_recommended=true
    ```
    """
    try:
        service = get_service()
        result = service.get_stock_recommendation_history_from_mongodb(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            only_recommended=only_recommended
        )
        return result
    except Exception as e:
        logger.error(f"MongoDB 종목별 이력 조회 중 오류 발생: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"MongoDB 종목별 이력 조회 중 오류 발생: {str(e)}")

@router.get("/mongodb/recommendations/range", response_model=dict)
async def get_recommended_stocks_by_date_range(
    start_date: str,
    end_date: str = None
):
    """
    📊 날짜 범위별 추천 종목 집계 (통계 분석용)
    
    특정 기간 동안의 추천 종목을 날짜별로 집계하고 통계를 제공합니다.
    MongoDB의 `daily_stock_data` 컬렉션을 사용하여 효율적으로 집계합니다.
    
    **사용 시나리오:**
    - 기간별 추천 종목 통계
    - 가장 많이 추천된 종목 분석
    - 추천 패턴 분석
    - 리포트 생성
    
    **데이터 소스:** `daily_stock_data` 컬렉션
    
    **Parameters:**
    - `start_date`: 시작 날짜 (YYYY-MM-DD 형식, 필수)
    - `end_date`: 종료 날짜 (YYYY-MM-DD 형식, 선택, 기본값: 오늘)
    
    **Returns:**
    ```json
    {
      "message": "2025-12-05 ~ 2025-12-12 기간의 추천 종목 집계 완료",
      "date_range": {
        "start": "2025-12-05",
        "end": "2025-12-12"
      },
      "daily_recommendations": [
        {
          "date": "2025-12-12",
          "tickers": ["AAPL", "MSFT"],
          "count": 2
        }
      ],
      "total_recommended_days": 5,
      "most_recommended_tickers": {
        "AAPL": 5,
        "MSFT": 3
      },
      "total_unique_tickers": 10
    }
    ```
    
    **예시:**
    ```bash
    # 최근 7일 집계
    GET /stocks/mongodb/recommendations/range?start_date=2025-12-05&end_date=2025-12-12
    
    # 오늘까지 집계
    GET /stocks/mongodb/recommendations/range?start_date=2025-12-01
    ```
    """
    try:
        service = get_service()
        result = service.get_recommended_stocks_by_date_range_from_mongodb(
            start_date=start_date,
            end_date=end_date
        )
        return result
    except Exception as e:
        logger.error(f"MongoDB 날짜 범위별 집계 중 오류 발생: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"MongoDB 날짜 범위별 집계 중 오류 발생: {str(e)}")

@router.get("/mongodb/sync/{date}", response_model=dict)
async def verify_mongodb_sync(date: str):
    """
    🔄 MongoDB 컬렉션 동기화 상태 확인 (모니터링용)
    
    `daily_stock_data.recommendations`와 `stock_recommendations` 컬렉션 간의
    데이터 일관성을 확인합니다. 두 컬렉션은 하이브리드 접근법으로 동시에 사용되므로
    정기적인 동기화 확인이 필요합니다.
    
    **사용 시나리오:**
    - 데이터 일관성 모니터링
    - 문제 진단
    - 정기적인 헬스 체크
    - 데이터 마이그레이션 검증
    
    **Parameters:**
    - `date`: 확인할 날짜 (YYYY-MM-DD 형식)
    
    **Returns:**
    ```json
    {
      "message": "두 컬렉션이 동기화되어 있습니다",
      "date": "2025-12-12",
      "sync_status": "synced",
      "daily_stock_data_count": 50,
      "stock_recommendations_count": 50,
      "details": {
        "daily_tickers": ["AAPL", "MSFT", ...],
        "stock_rec_tickers": ["AAPL", "MSFT", ...],
        "only_in_daily": [],
        "only_in_stock_rec": [],
        "common_tickers": ["AAPL", "MSFT", ...]
      }
    }
    ```
    
    **동기화 상태:**
    - `synced`: 두 컬렉션이 일치 ✅
    - `mismatch`: 두 컬렉션 간 불일치 ⚠️
    - `missing`: 두 컬렉션 모두 데이터 없음 ❌
    
    **예시:**
    ```bash
    # 오늘 날짜 동기화 확인
    GET /stocks/mongodb/sync/2025-12-12
    ```
    """
    try:
        service = get_service()
        result = service.verify_mongodb_sync(date)
        return result
    except Exception as e:
        logger.error(f"MongoDB 동기화 확인 중 오류 발생: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"MongoDB 동기화 확인 중 오류 발생: {str(e)}")