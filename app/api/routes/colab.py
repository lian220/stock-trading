"""
Colab/Vertex AI Job 호출 API 라우터
- predict.py 실행을 위한 Colab 트리거
- Vertex AI Job 실행 상태 조회
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional
from app.utils.scheduler import run_colab_trigger_now, stock_scheduler
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/trigger", summary="Colab/Vertex AI Job 실행")
async def trigger_colab_job(
    background_tasks: BackgroundTasks,
    send_slack_notification: bool = False
):
    """
    Colab/Vertex AI Job을 즉시 실행하여 predict.py를 실행합니다.
    
    ### 실행 내용
    - Vertex AI Job을 통해 predict.py 실행
    - AI 예측 모델 학습 및 예측 수행
    - 결과를 Supabase에 저장
    
    ### 파라미터
    - **send_slack_notification**: Slack 알림 전송 여부 (기본값: False)
    
    ### 응답
    - **success**: 실행 성공 여부
    - **message**: 실행 메시지
    - **status**: 현재 Job 실행 상태
    """
    try:
        # 이미 실행 중인지 확인
        if stock_scheduler.colab_trigger_executing:
            return {
                "success": False,
                "message": "Colab 트리거 작업이 이미 실행 중입니다. 잠시 후 다시 시도해주세요.",
                "status": "running"
            }
        
        # 백그라운드에서 Colab 트리거 실행
        def run_colab_task():
            try:
                run_colab_trigger_now(send_slack_notification=send_slack_notification)
            except Exception as e:
                logger.error(f"Colab 트리거 실행 중 오류 발생: {str(e)}", exc_info=True)
        
        background_tasks.add_task(run_colab_task)
        
        return {
            "success": True,
            "message": "Colab/Vertex AI Job이 시작되었습니다. 백그라운드에서 실행됩니다.",
            "status": "started"
        }
    except Exception as e:
        logger.error(f"Colab 트리거 실행 요청 중 오류 발생: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Colab 트리거 실행 중 오류 발생: {str(e)}")


@router.get("/status", summary="Colab/Vertex AI Job 실행 상태 조회")
def get_colab_job_status():
    """
    현재 Colab/Vertex AI Job 실행 상태를 조회합니다.
    
    ### 응답
    - **is_running**: Job이 실행 중인지 여부
    - **status**: 상태 메시지
    """
    try:
        is_running = stock_scheduler.colab_trigger_executing
        
        return {
            "success": True,
            "is_running": is_running,
            "status": "running" if is_running else "idle",
            "message": "Colab/Vertex AI Job이 실행 중입니다." if is_running else "Colab/Vertex AI Job이 대기 중입니다."
        }
    except Exception as e:
        logger.error(f"Colab Job 상태 조회 중 오류 발생: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Colab Job 상태 조회 중 오류 발생: {str(e)}")
