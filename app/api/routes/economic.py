from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Query
from app.schemas.stock import UpdateResponse
from app.utils.scheduler import run_economic_data_update_now
from app.services.economic_service import update_economic_data_in_background
from datetime import date, datetime
from typing import Optional
import pytz

router = APIRouter()

@router.post("/update", summary="경제 및 주식 데이터 업데이트", response_model=UpdateResponse)
async def update_economic_data(
    background_tasks: BackgroundTasks,
    start_date: Optional[str] = Query(None, description="수집 시작 날짜 (YYYY-MM-DD 형식, 기본값: 오늘)"),
    end_date: Optional[str] = Query(None, description="수집 종료 날짜 (YYYY-MM-DD 형식, 기본값: 오늘)")
):
    """
    경제 및 주식 데이터를 Supabase와 MongoDB에 저장합니다.
    이 작업은 백그라운드에서 실행되어 API 응답을 블로킹하지 않습니다.
    
    **날짜 범위 설정:**
    - `start_date`와 `end_date`가 없으면: 오늘 날짜 데이터를 수집합니다.
    - `start_date`와 `end_date`가 있으면: 해당 날짜 범위의 데이터를 수집합니다.
    
    DB에서 마지막 수집 날짜를 자동으로 찾아 그 다음 날부터 수집합니다.
    기존 데이터의 NULL 값은 새 데이터로 자동 업데이트됩니다.
    
    **참고:** 기술적 지표 생성 및 감정 분석은 별도 API를 사용하세요:
    - 통합 분석: POST /recommended-stocks/generate-complete-analysis
    - 기술적 지표만: POST /recommended-stocks/generate-technical-recommendations
    - 감정 분석만: POST /recommended-stocks/analyze-news-sentiment
    """
    try:
        # 날짜 범위가 지정된 경우 직접 호출, 아니면 스케줄러 함수 사용
        if start_date or end_date:
            # 날짜 범위가 지정된 경우 직접 서비스 함수 호출
            korea_tz = pytz.timezone('Asia/Seoul')
            today = datetime.now(korea_tz).strftime('%Y-%m-%d')
            
            # 기본값 설정
            if not start_date:
                start_date = today
            if not end_date:
                end_date = today
            
            # 백그라운드 작업으로 실행
            background_tasks.add_task(
                update_economic_data_in_background,
                start_date=start_date,
                end_date=end_date
            )
            
            return {
                "success": True,
                "message": f"경제 데이터 업데이트가 백그라운드에서 시작되었습니다. (범위: {start_date} ~ {end_date})",
                "total_records": 0,
                "updated_records": 0
            }
        else:
            # 기본 동작: 스케줄러 함수 사용 (오늘 날짜 자동 처리)
            background_tasks.add_task(run_economic_data_update_now)
            
            return {
                "success": True,
                "message": "경제 데이터 업데이트가 백그라운드에서 시작되었습니다.",
                "total_records": 0,
                "updated_records": 0
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터 업데이트 중 오류 발생: {str(e)}")