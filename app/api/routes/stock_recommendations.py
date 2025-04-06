from fastapi import APIRouter, HTTPException
from app.services.stock_recommendation_service import StockRecommendationService

router = APIRouter()
service = StockRecommendationService()

@router.get("/recommended-stocks", response_model=dict)
async def get_recommended_stocks_route():
    """
    Accuracy가 80% 이상이고 상승 확률이 3% 이상인 추천 주식 목록을 반환합니다.
    상승 확률 기준으로 내림차순 정렬됩니다.
    """
    try:
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
        result = service.get_recommendations_with_sentiment()
        if not result["results"]:
            return {"message": "조건을 만족하는 추천 주식이 없습니다", "results": []}
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"추천 주식 및 감정 분석 조회 중 오류 발생: {str(e)}")

@router.post("/recommended-stocks/analyze-news-sentiment", response_model=dict)
async def analyze_news_sentiment():
    """
    추천 주식 목록에서 추출한 티커에 대해 뉴스 감정 분석을 수행합니다.
    실시간으로 처리하고 결과를 반환합니다.
    """
    try:
        results = service.fetch_and_store_sentiment_for_recommendations()
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"뉴스 감정 분석 중 오류 발생: {str(e)}")

@router.post("/recommended-stocks/generate-technical-recommendations", response_model=dict)
async def generate_technical_recommendations():
    """
    기술적 지표를 기반으로 추천 데이터를 생성하고 Supabase에 저장합니다.
    """
    try:
        recommendations = service.generate_technical_recommendations()
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
        result = service.get_combined_recommendations_with_technical_and_sentiment()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"기술적 지표 및 감정 분석 조회 중 오류 발생: {str(e)}")

@router.post("/recommended-stocks/generate-complete-analysis", response_model=dict)
async def generate_complete_analysis():
    """
    기술적 지표 생성과 뉴스 감정 분석을 하나의 API로 통합하여 수행합니다.
    먼저 기술적 지표를 생성하고 저장한 다음, 뉴스 감정 분석을 수행합니다.
    두 기능의 결과를 통합하여 반환합니다.
    """
    try:
        # 1. 기술적 지표 생성 및 저장
        print("1단계: 기술적 지표 생성 시작...")
        tech_results = service.generate_technical_recommendations()
        print(f"기술적 지표 생성 완료: {tech_results['message']}")
        
        # 2. 뉴스 감정 분석 수행
        print("2단계: 뉴스 감정 분석 시작...")
        sentiment_results = service.fetch_and_store_sentiment_for_recommendations()
        print(f"뉴스 감정 분석 완료: {sentiment_results['message']}")
        
        # 3. 통합 분석 조회
        print("3단계: 통합 분석 결과 조회...")
        combined_results = service.get_combined_recommendations_with_technical_and_sentiment()
        
        # 4. 결과 통합 및 반환
        return {
            "message": "통합 분석이 완료되었습니다",
            "technical_analysis": {
                "message": tech_results["message"],
                "count": len(tech_results.get("data", [])),
            },
            "sentiment_analysis": {
                "message": sentiment_results["message"],
                "count": len(sentiment_results.get("results", [])),
            },
            "combined_results": combined_results
        }
    except Exception as e:
        print(f"통합 분석 중 오류 발생: {str(e)}")
        import traceback
        print(traceback.format_exc())
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
        result = service.get_stocks_to_sell()
        return result
    except Exception as e:
        print(f"매도 대상 종목 조회 중 오류 발생: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"매도 대상 종목 조회 중 오류 발생: {str(e)}")