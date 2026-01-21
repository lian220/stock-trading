"""
자동매매 API 라우터
- 자동매매 설정 관리
- 자동 매수/매도 실행
- 자동매매 상태 조회
- 백테스팅
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.services.auto_trading_service import AutoTradingService
from app.utils.user_context import get_current_user_id
from app.schemas.auto_trading import (
    AutoTradingConfigUpdate,
    AutoTradingExecuteRequest,
    BacktestRequest
)

router = APIRouter()
auto_trading_service = AutoTradingService()


@router.get("/config", summary="자동매매 설정 조회")
def get_auto_trading_config():
    """
    현재 자동매매 설정을 조회합니다.
    
    ### 응답
    - **enabled**: 자동매매 활성화 여부
    - **auto_trading_enabled**: 자동매매 활성화 여부 (계정 단위)
    - **min_composite_score**: 최소 종합 점수
    - **max_stocks_to_buy**: 최대 매수 종목 수
    - **max_amount_per_stock**: 종목당 최대 매수 금액
    - **stop_loss_percent**: 손절 기준 (%)
    - **take_profit_percent**: 익절 기준 (%)
    - **use_sentiment**: 감정 분석 사용 여부
    - **min_sentiment_score**: 최소 감정 점수
    - **order_type**: 주문 구분
    - **allow_buy_existing_stocks**: 보유 중인 종목도 매수 허용 여부 (기본값: true)
    """
    try:
        user_id = get_current_user_id()
        config = auto_trading_service.get_auto_trading_config(user_id=user_id)
        return {
            "success": True,
            "config": config
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"설정 조회 중 오류: {str(e)}")


@router.put("/config", summary="자동매매 설정 업데이트")
def update_auto_trading_config(config: AutoTradingConfigUpdate):
    """
    자동매매 설정을 업데이트합니다.
    
    ### 입력값
    - **enabled**: 자동매매 활성화 여부 (True/False)
    - **auto_trading_enabled**: 자동매매 활성화 여부 (True/False)
    - **min_composite_score**: 최소 종합 점수 (0-100)
    - **max_stocks_to_buy**: 최대 매수 종목 수 (1-20)
    - **max_amount_per_stock**: 종목당 최대 매수 금액 (USD)
    - **stop_loss_percent**: 손절 기준 (%) - 음수 값 (예: -7.0)
    - **take_profit_percent**: 익절 기준 (%) - 양수 값 (예: 5.0)
    - **use_sentiment**: 감정 분석 사용 여부
    - **min_sentiment_score**: 최소 감정 점수 (-1 ~ 1)
    - **order_type**: 주문 구분 (00: 지정가)
    - **allow_buy_existing_stocks**: 보유 중인 종목도 매수 허용 여부 (기본값: true)
    
    ### 예시
    ```json
    {
        "enabled": true,
        "min_composite_score": 2.5,
        "max_stocks_to_buy": 3,
        "max_amount_per_stock": 5000.0,
        "stop_loss_percent": -7.0,
        "take_profit_percent": 5.0
    }
    ```
    """
    try:
        user_id = get_current_user_id()
        
        # None이 아닌 필드만 딕셔너리로 변환
        config_dict = {k: v for k, v in config.model_dump().items() if v is not None}
        
        result = auto_trading_service.update_auto_trading_config(config_dict, user_id=user_id)
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error"))
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"설정 업데이트 중 오류: {str(e)}")


@router.get("/candidates/buy", summary="매수 추천 종목 조회")
def get_buy_candidates():
    """
    현재 설정 기준으로 매수 추천 종목을 조회합니다.
    
    ### 응답
    - 종합 점수 기준으로 정렬된 매수 추천 종목 목록
    - 각 종목의 상세 정보 (가격, 점수, 기술적 지표, 감정 분석 등)
    """
    try:
        candidates = auto_trading_service.get_buy_candidates()
        
        return {
            "success": True,
            "message": f"{len(candidates)}개의 매수 추천 종목을 찾았습니다",
            "candidates": candidates
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"매수 추천 조회 중 오류: {str(e)}")


@router.get("/candidates/sell", summary="매도 대상 종목 조회")
def get_sell_candidates():
    """
    보유 종목 중 매도 대상을 조회합니다.
    
    ### 매도 조건
    1. 익절: 구매가 대비 +5% 이상 상승
    2. 손절: 구매가 대비 -7% 이하 하락
    3. 기술적 지표 매도 신호 3개 이상
    4. 부정적 감정 점수 + 기술적 지표 매도 신호 2개 이상
    
    ### 응답
    - 매도 대상 종목 목록
    - 각 종목의 매도 사유 및 상세 정보
    """
    try:
        result = auto_trading_service.stock_service.get_stocks_to_sell()
        
        return {
            "success": True,
            "message": result.get("message"),
            "candidates": result.get("sell_candidates", [])
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"매도 대상 조회 중 오류: {str(e)}")


@router.post("/execute/buy", summary="자동 매수 실행")
def execute_auto_buy(request: AutoTradingExecuteRequest):
    """
    매수 추천 종목을 자동으로 매수합니다.
    
    ### 입력값
    - **dry_run**: True이면 실제 주문 없이 시뮬레이션만 수행
    
    ### 실행 프로세스
    1. 자동매매 설정 확인
    2. 매수 추천 종목 조회
    3. 현재 보유 종목 확인 (중복 매수 방지)
    4. 각 종목의 현재가 조회
    5. 매수 가능 수량 계산
    6. 주문 실행 (dry_run=False인 경우)
    
    ### 응답
    - 주문 실행 결과 목록
    - 각 주문의 상태 및 상세 정보
    
    ### 주의사항
    - 자동매매가 활성화되어 있어야 합니다
    - 이미 보유 중인 종목은 자동으로 스킵됩니다
    - API Rate Limit을 고려하여 순차적으로 주문합니다
    """
    try:
        result = auto_trading_service.execute_auto_buy(dry_run=request.dry_run)
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error"))
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"자동 매수 실행 중 오류: {str(e)}")


@router.post("/execute/sell", summary="자동 매도 실행")
def execute_auto_sell(request: AutoTradingExecuteRequest):
    """
    보유 종목 중 매도 조건을 만족하는 종목을 자동으로 매도합니다.
    
    ### 입력값
    - **dry_run**: True이면 실제 주문 없이 시뮬레이션만 수행
    
    ### 실행 프로세스
    1. 자동매매 설정 확인
    2. 매도 대상 종목 조회
    3. 각 종목에 대해 매도 주문 실행 (dry_run=False인 경우)
    
    ### 응답
    - 주문 실행 결과 목록
    - 각 주문의 상태 및 매도 사유
    
    ### 주의사항
    - 자동매매가 활성화되어 있어야 합니다
    - 손절/익절 기준은 설정에서 변경 가능합니다
    - API Rate Limit을 고려하여 순차적으로 주문합니다
    """
    try:
        result = auto_trading_service.execute_auto_sell(dry_run=request.dry_run)
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error"))
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"자동 매도 실행 중 오류: {str(e)}")


@router.get("/status", summary="자동매매 상태 조회")
def get_auto_trading_status():
    """
    자동매매 시스템의 전반적인 상태를 조회합니다.
    
    ### 응답
    - **config**: 현재 자동매매 설정
    - **holdings**: 보유 종목 정보
      - count: 보유 종목 수
      - total_value: 총 평가 금액
      - items: 종목별 상세 정보
    - **available_cash**: 현금 잔고 (USD)
    - **candidates**: 매수/매도 후보
      - buy: 매수 추천 종목 목록
      - sell: 매도 대상 종목 목록
    - **recent_orders**: 최근 7일간 주문 내역
    
    ### 사용 예시
    - 자동매매 대시보드 구성
    - 포트폴리오 모니터링
    - 주문 실행 전 상태 확인
    """
    try:
        status = auto_trading_service.get_auto_trading_status()
        
        if "error" in status:
            raise HTTPException(status_code=500, detail=status["error"])
        
        return {
            "success": True,
            "status": status
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"상태 조회 중 오류: {str(e)}")


@router.get("/logs", summary="자동매매 주문 내역 조회")
def get_auto_trading_logs(
    days: int = Query(7, ge=1, le=90, description="조회 기간 (일)")
):
    """
    자동매매로 실행된 주문 내역을 조회합니다.
    
    ### 입력값
    - **days**: 조회 기간 (1-90일, 기본값: 7일)
    
    ### 응답
    - 기간 내 실행된 모든 주문 내역
    - 주문 유형 (매수/매도)
    - 주문 상태 (성공/실패)
    - 주문 가격 및 수량
    """
    try:
        logs = auto_trading_service._get_recent_orders(days=days)
        
        return {
            "success": True,
            "message": f"최근 {days}일간 {len(logs)}개의 주문 내역",
            "logs": logs
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"주문 내역 조회 중 오류: {str(e)}")


@router.post("/backtest", summary="백테스팅 실행")
def run_backtest(request: BacktestRequest):
    """
    과거 데이터를 기반으로 자동매매 전략을 백테스팅합니다.
    
    ### 입력값
    - **start_date**: 시작 날짜 (YYYY-MM-DD)
    - **end_date**: 종료 날짜 (YYYY-MM-DD)
    - **initial_capital**: 초기 자본금 (USD, 기본값: 100,000)
    
    ### 응답
    - 백테스팅 결과
    - 기간 내 수익률
    - 거래 내역
    - 성과 지표
    
    ### 주의사항
    - 이 기능은 현재 구현 중입니다
    - 실제 거래 결과와 다를 수 있습니다
    """
    try:
        result = auto_trading_service.run_backtest(
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital
        )
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"백테스팅 실행 중 오류: {str(e)}")

