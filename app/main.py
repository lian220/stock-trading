import warnings
import os
# urllib3의 OpenSSL 경고 무시 (서브프로세스에서도 적용되도록 환경 변수 설정)
# 최신 urllib3에서는 NotOpenSSLWarning이 없을 수 있으므로 일반적인 urllib3 경고 무시
try:
    os.environ['PYTHONWARNINGS'] = 'ignore::urllib3.exceptions.NotOpenSSLWarning'
except:
    # NotOpenSSLWarning이 없는 경우 일반 경고 무시
    pass
# 메인 프로세스에서도 경고 필터 설정
try:
    import urllib3
    # urllib3 버전에 따라 NotOpenSSLWarning이 없을 수 있음
    if hasattr(urllib3.exceptions, 'NotOpenSSLWarning'):
        warnings.filterwarnings('ignore', category=urllib3.exceptions.NotOpenSSLWarning)
except (ImportError, AttributeError):
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import asyncio
from datetime import datetime
from app.api.api import api_router
from app.core.config import settings
from app.services.economic_service import update_economic_data_in_background
from app.utils.scheduler import (
    start_scheduler, stop_scheduler, 
    start_sell_scheduler, stop_sell_scheduler
)
from contextlib import asynccontextmanager
import logging

logger = logging.getLogger('main')

async def periodic_status_log():
    """30분마다 서버 상태를 로깅하는 백그라운드 태스크"""
    while True:
        await asyncio.sleep(1800)  # 30분 = 1800초
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"서버 실행 중... [{current_time}]")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: runs once when app starts
    await startup()
    
    # 30분마다 상태 로그를 출력하는 백그라운드 태스크 시작
    status_task = asyncio.create_task(periodic_status_log())
    
    yield
    
    # Shutdown: 필요한 정리 작업
    status_task.cancel()  # 상태 로그 태스크 종료
    try:
        await status_task
    except asyncio.CancelledError:
        pass
    stop_scheduler()  # 매수 스케줄러 종료
    stop_sell_scheduler()  # 매도 스케줄러 종료

app = FastAPI(title="주식 분석 및 추천 API", lifespan=lifespan)

# CORS 미들웨어 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 오리진 허용 (프로덕션에서는 특정 도메인으로 제한 권장)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터 등록 (중앙 관리 방식)
app.include_router(api_router)

@app.get("/")
def read_root():
    return {"message": "주식 분석 및 추천 API에 오신 것을 환영합니다"}

# APScheduler 대신 직접 실행
async def startup():
    # 시작 시 즉시 한 번 경제 데이터 수집 실행 (옵션으로 제어)
    if settings.RUN_ECONOMIC_DATA_ON_STARTUP:
        logger.info("서비스 시작 시 경제 데이터 수집을 즉시 실행합니다...")
        try:
            await update_economic_data_in_background()
            logger.info("초기 경제 데이터 수집이 완료되었습니다.")
        except Exception as e:
            logger.error(f"초기 경제 데이터 수집 중 오류 발생 (앱은 계속 실행됩니다): {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    else:
        logger.info("서버 시작 시 경제 데이터 수집이 비활성화되어 있습니다. (RUN_ECONOMIC_DATA_ON_STARTUP=false)")
    
    
    # 주식 자동매매 스케줄러 시작
    try:
        start_scheduler()
    except Exception as e:
        logger.error(f"매수 스케줄러 시작 중 오류 발생: {str(e)}")
    
    try:
        start_sell_scheduler()
    except Exception as e:
        logger.error(f"매도 스케줄러 시작 중 오류 발생: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True, access_log=False)