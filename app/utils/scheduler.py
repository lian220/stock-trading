import asyncio
import schedule
import time
import pytz
from datetime import datetime, timedelta
from pathlib import Path
import threading
from typing import Callable
from app.core.enums import (
    OrderStatus, 
    OrderType, 
    SellPriority, 
    ExchangeCode,
    EXCHANGE_CODE_MAP,
    get_exchange_code_for_api
)
from app.services.stock_recommendation_service import StockRecommendationService
from app.services.balance_service import get_current_price, order_overseas_stock, order_overseas_stock_daytime, get_all_overseas_balances, get_overseas_balance, get_overseas_order_possible_amount, check_order_execution, calculate_portfolio_profit, update_ticker_realized_profit, calculate_total_return, calculate_cumulative_profit
from app.services.auto_trading_service import AutoTradingService
from app.core.config import settings
import logging
from app.services.economic_service import update_economic_data_in_background
from app.utils.slack_notifier import slack_notifier
from app.db.mongodb import get_db
import httpx

# ============= 상수 정의 =============
class SchedulerConfig:
    """스케줄러 설정 상수"""
    # 현재가 조회 실패 관련
    MAX_PRICE_FETCH_FAILURES = 3  # 최대 실패 횟수
    PRICE_FETCH_EXCLUDE_MINUTES = 30  # 제외 시간 (분)
    PRICE_FETCH_RATE_LIMIT_SLEEP_SECONDS = 3  # API 속도 제한 오류 시 대기 시간 (초)
    
    # 주문 실패 관련
    ORDER_FAILURE_EXCLUDE_MINUTES = 60  # 주문 실패 후 제외 시간 (분)
    
    # API 요청 간 지연
    ORDER_DELAY_SECONDS = 2  # 주문 간 지연 시간 (초)
    EXECUTION_CHECK_DELAY_SECONDS = 5  # 체결 확인 대기 시간 (초)
    EXECUTION_CHECK_TIMEOUT_SECONDS = 60  # 체결 확인 타임아웃 (초)
    
    
    # 스케줄 시간
    SCHEDULE_ECONOMIC_DATA_UPDATE_1 = "06:05"
    SCHEDULE_ECONOMIC_DATA_UPDATE_2 = "23:00"  # 경제 데이터 재수집 및 Vertex AI 예측 병렬 실행 시간
    SCHEDULE_VERTEX_AI_PREDICTION = "23:00"  # 레거시: 이제 SCHEDULE_ECONOMIC_DATA_UPDATE_2와 함께 _run_23_00_tasks에서 병렬 실행됨
    SCHEDULE_PARALLEL_ANALYSIS = "23:05"
    SCHEDULE_COMBINED_ANALYSIS = "23:45"
    SCHEDULE_AUTO_BUY = "23:50"
    SCHEDULE_CLEANUP_ORDERS = "06:30"
    SCHEDULE_PORTFOLIO_PROFIT_REPORT = "07:00"
    
    # 시장 시간
    MARKET_OPEN_HOUR = 9
    MARKET_OPEN_MINUTE = 30
    MARKET_CLOSE_HOUR = 16
    MARKET_CLOSE_MINUTE = 0
    DAYTIME_TRADING_START_HOUR = 10  # 한국시간 기준 주간거래 시작 시간
    DAYTIME_TRADING_END_HOUR = 18  # 한국시간 기준 주간거래 종료 시간

class StockScheduler:
    """주식 자동매매 스케줄러 클래스"""
    
    def __init__(self):
        self.recommendation_service = StockRecommendationService()
        self.auto_trading_service = AutoTradingService()
        self.running = False
        self.sell_running = False  # 매도 스케줄러 실행 상태
        self.analysis_running = False  # 분석 스케줄러 실행 상태
        self.scheduler_thread = None
        self.buy_executing = False  # 매수 작업 실행 중 플래그 (중복 실행 방지)
        self.analysis_executing = False  # 분석 작업 실행 중 플래그 (중복 실행 방지)
        self.prediction_executing = False  # Vertex AI 예측 작업 실행 중 플래그 (중복 실행 방지)
        self.economic_executing = False  # 경제 데이터 업데이트 작업 실행 중 플래그 (중복 실행 방지)
        self.tasks_23_00_executing = False  # 23:00 작업 실행 중 플래그 (중복 실행 방지)
        self.stopping = False  # 중지 중 플래그 (중복 중지 방지)
        # 현재가 조회 실패한 종목 추적 (ticker -> (실패 횟수, 마지막 실패 시간))
        self.price_fetch_failures = {}  # type: dict[str, tuple[int, datetime]]
        # 주문 실패한 종목 추적 (ticker -> 마지막 실패 시간)
        self.order_failures = {}  # type: dict[str, datetime]
    
    def start(self):
        """매수 스케줄러 시작"""
        if self.running:
            logger.warning("매수 스케줄러가 이미 실행 중입니다.")
            return False
        
        # 기존 작업이 있다면 먼저 취소 (중복 등록 방지)
        job_names = [
            '_run_auto_buy',
            '_run_analysis',
            '_run_parallel_analysis',
            '_run_combined_analysis',
            '_run_vertex_ai_prediction',
            '_run_economic_data_update',
            '_run_23_00_tasks',
            '_run_portfolio_profit_report'
        ]
        
        for job in schedule.jobs:
            if job.job_func.__name__ in job_names:
                schedule.cancel_job(job)
        
        # 한국 시간 기준 새벽 6시 5분에 경제 데이터 업데이트 작업 실행
        schedule.every().day.at(SchedulerConfig.SCHEDULE_ECONOMIC_DATA_UPDATE_1).do(self._run_economic_data_update)
        
        # 한국 시간 기준 밤 11시에 경제 데이터 재수집 및 Vertex AI 예측 작업을 병렬로 실행
        schedule.every().day.at(SchedulerConfig.SCHEDULE_ECONOMIC_DATA_UPDATE_2).do(self._run_23_00_tasks)
        
        # 한국 시간 기준 밤 11시 5분에 병렬 분석 작업 실행 (충분한 시간 확보)
        parallel_job = schedule.every().day.at(SchedulerConfig.SCHEDULE_PARALLEL_ANALYSIS).do(self._run_parallel_analysis)
        logger.info(f"병렬 분석 작업 등록 완료: 매일 {SchedulerConfig.SCHEDULE_PARALLEL_ANALYSIS} (KST)")

        # 한국 시간 기준 밤 11시 45분에 통합 분석 작업 실행
        combined_job = schedule.every().day.at(SchedulerConfig.SCHEDULE_COMBINED_ANALYSIS).do(self._run_combined_analysis)
        logger.info(f"통합 분석 작업 등록 완료: 매일 {SchedulerConfig.SCHEDULE_COMBINED_ANALYSIS} (KST)")
        
        # 한국 시간 기준 밤 11시 50분(23:50)에 매수 작업 실행 (장 시작 20분 후)
        schedule.every().day.at(SchedulerConfig.SCHEDULE_AUTO_BUY).do(self._run_auto_buy)
        
        # 한국 시간 기준 새벽 6시 30분에 장 마감 후 미체결 주문 정리 (16:00 ET 이후)
        schedule.every().day.at(SchedulerConfig.SCHEDULE_CLEANUP_ORDERS).do(self._cleanup_pending_orders)
        
        # 한국 시간 기준 오전 7시에 계좌 수익율 리포트 전송
        schedule.every().day.at(SchedulerConfig.SCHEDULE_PORTFOLIO_PROFIT_REPORT).do(self._run_portfolio_profit_report)
        
        # 별도 스레드에서 스케줄러 실행
        self.running = True
        self.analysis_running = True
        self.scheduler_thread = threading.Thread(target=self._run_scheduler)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()
        
        # 하나의 상세한 로그로 통합
        logger.info("=" * 60)
        logger.info("주식 자동매매 스케줄러가 시작되었습니다.")
        logger.info("=" * 60)
        logger.info("등록된 스케줄:")
        logger.info("  - 경제 데이터: 매일 06:05")
        logger.info("  - 23:00 작업: 매일 23:00 (경제 데이터 업데이트 + Vertex AI 예측 병렬 실행)")
        logger.info(f"  - 병렬 분석: 매일 {SchedulerConfig.SCHEDULE_PARALLEL_ANALYSIS} (기술적 지표 + 감정 분석)")
        logger.info(f"  - 통합 분석: 매일 {SchedulerConfig.SCHEDULE_COMBINED_ANALYSIS} (AI 예측 + 기술적 지표 + 감정 분석)")
        logger.info("  - 매수: 매일 00:00")
        logger.info("  - 미체결 주문 정리: 매일 06:30 (장 마감 후)")
        logger.info("  - 계좌 수익율 리포트: 매일 07:00")
        
        # Slack 알림 설정 확인
        if settings.SLACK_WEBHOOK_URL_SCHEDULER:
            logger.info(f"Slack 스케줄러 알림: 활성화됨")
        else:
            logger.warning("⚠️  Slack 스케줄러 알림: SLACK_WEBHOOK_URL_SCHEDULER 환경변수가 설정되지 않아 알림이 전송되지 않습니다.")
        logger.info("=" * 60)
        return True
    
    def stop(self):
        """매수 스케줄러 중지 (분석 스케줄러도 함께 중지)"""
        if not self.running:
            return False
        
        if self.stopping:
            return False  # 이미 중지 중이면 중복 로그 방지
        
        self.stopping = True
        self.running = False
        self.analysis_running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        
        # 매수 및 분석 관련 작업 취소 (sell 스케줄러는 유지)
        job_names = [
            '_run_auto_buy',
            '_run_analysis',
            '_run_parallel_analysis',
            '_run_combined_analysis',
            '_run_vertex_ai_prediction',
            '_run_economic_data_update',
            '_run_23_00_tasks',
            '_cleanup_pending_orders',
            '_run_portfolio_profit_report'
        ]
        
        for job in schedule.jobs:
            if job.job_func.__name__ in job_names:
                schedule.cancel_job(job)
        
        logger.info("매수 및 분석 스케줄러가 중지되었습니다.")
        self.stopping = False
        return True

    def _run_economic_data_update(self, send_slack_notification: bool = True):
        """경제 데이터 업데이트 실행 함수"""
        function_name = "_run_economic_data_update"
        
        # 중복 실행 방지
        if self.economic_executing:
            logger.warning(f"[{function_name}] 경제 데이터 업데이트가 이미 실행 중입니다. 중복 실행을 건너뜁니다.")
            return False
        
        # 시간 진단 로깅
        korea_tz = pytz.timezone('Asia/Seoul')
        now_korea = datetime.now(korea_tz)
        now_local = datetime.now()
        start_time_str = now_korea.strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"[{function_name}] 함수 실행 시작 (시스템 시간: {now_local.strftime('%Y-%m-%d %H:%M:%S')}, 한국 시간: {start_time_str} KST)")
        
        self.economic_executing = True
        
        if send_slack_notification:
            send_scheduler_slack_notification(f"📈 *경제 데이터 업데이트 시작*\n경제 데이터 수집을 시작합니다.\n실행 시간: {start_time_str} (KST)")
        
        try:
            asyncio.run(update_economic_data_in_background())
            end_time_korea = datetime.now(korea_tz)
            end_time_str = end_time_korea.strftime('%Y-%m-%d %H:%M:%S')
            elapsed_time = (end_time_korea - now_korea).total_seconds()
            logger.info(f"[{function_name}] 함수 실행 완료 (소요 시간: {elapsed_time:.1f}초)")
            if send_slack_notification:
                success = send_scheduler_slack_notification(
                    f"✅ *경제 데이터 업데이트 완료*\n"
                    f"경제 데이터 수집이 완료되었습니다.\n"
                    f"시작: {start_time_str} (KST)\n"
                    f"완료: {end_time_str} (KST)\n"
                    f"소요 시간: {elapsed_time:.1f}초"
                )
                if not success:
                    logger.warning(f"[{function_name}] 슬랙 알림 전송 실패 (경제 데이터 업데이트 완료)")
            return True
        except Exception as e:
            logger.error(f"[{function_name}] 함수 실행 중 오류 발생: {str(e)}", exc_info=True)
            logger.info(f"[{function_name}] 함수 실행 완료 (오류)")
            if send_slack_notification:
                success = send_scheduler_slack_notification(f"❌ *경제 데이터 업데이트 오류*\n오류 발생: {str(e)}")
                if not success:
                    logger.warning(f"[{function_name}] 슬랙 알림 전송 실패 (경제 데이터 업데이트 오류)")
            return False
        finally:
            # 실행 완료 후 플래그 해제
            self.economic_executing = False

    def _run_23_00_tasks(self, send_slack_notification: bool = True):
        """
        23:00에 실행되어야 하는 작업들을 병렬로 실행
        - 경제 데이터 업데이트
        - Vertex AI 예측
        """
        function_name = "_run_23_00_tasks"
        
        # 중복 실행 방지
        if self.tasks_23_00_executing:
            logger.warning(f"[{function_name}] 23:00 작업이 이미 실행 중입니다. 중복 실행을 건너뜁니다.")
            return False
        
        korea_tz = pytz.timezone('Asia/Seoul')
        now_korea = datetime.now(korea_tz)
        start_time_str = now_korea.strftime('%Y-%m-%d %H:%M:%S')
        
        self.tasks_23_00_executing = True
        
        logger.info("=" * 60)
        logger.info(f"[{function_name}] 23:00 작업 시작 (한국 시간: {start_time_str} KST)")
        logger.info("=" * 60)
        
        if send_slack_notification:
            send_scheduler_slack_notification(
                f"🚀 *23:00 작업 시작*\n"
                f"경제 데이터 업데이트와 Vertex AI 예측을 병렬로 실행합니다.\n"
                f"실행 시간: {start_time_str} (KST)"
            )
        
        try:
            import concurrent.futures
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                # 1. 경제 데이터 업데이트
                logger.info(f"[{function_name}] 경제 데이터 업데이트 시작...")
                economic_future = executor.submit(
                    self._run_economic_data_update,
                    send_slack_notification=False  # 개별 알림은 비활성화 (통합 알림만)
                )
                
                # 2. Vertex AI 예측
                logger.info(f"[{function_name}] Vertex AI 예측 시작...")
                prediction_future = executor.submit(
                    self._run_vertex_ai_prediction,
                    send_slack_notification=False  # 개별 알림은 비활성화 (통합 알림만)
                )
                
                # 두 작업 완료 대기
                economic_result = economic_future.result()
                prediction_result = prediction_future.result()
                
                end_time_korea = datetime.now(korea_tz)
                end_time_str = end_time_korea.strftime('%Y-%m-%d %H:%M:%S')
                elapsed_time = (end_time_korea - now_korea).total_seconds()
                
                logger.info(f"[{function_name}] ✅ 경제 데이터 업데이트 완료: {economic_result}")
                logger.info(f"[{function_name}] ✅ Vertex AI 예측 완료: {prediction_result}")
                logger.info("=" * 60)
                logger.info(f"[{function_name}] 23:00 작업 완료 (소요 시간: {elapsed_time:.1f}초)")
                logger.info("=" * 60)
                
                if send_slack_notification:
                    send_scheduler_slack_notification(
                        f"✅ *23:00 작업 완료*\n"
                        f"경제 데이터 업데이트: {'성공' if economic_result else '실패'}\n"
                        f"Vertex AI 예측: {'성공' if prediction_result else '실패'}\n"
                        f"시작: {start_time_str} (KST)\n"
                        f"완료: {end_time_str} (KST)\n"
                        f"소요 시간: {elapsed_time:.1f}초"
                    )
                
                return economic_result and prediction_result
                
        except Exception as e:
            logger.error(f"[{function_name}] ❌ 23:00 작업 중 오류 발생: {str(e)}", exc_info=True)
            if send_slack_notification:
                send_scheduler_slack_notification(f"❌ *23:00 작업 오류*\n오류 발생: {str(e)}")
            return False
        finally:
            # 실행 완료 후 플래그 해제
            self.tasks_23_00_executing = False

    def _run_vertex_ai_prediction(self, send_slack_notification: bool = True):
        """Vertex AI를 사용한 주가 예측 작업 실행 (run_predict_vertex_ai.py)"""
        function_name = "_run_vertex_ai_prediction"
        # 시간 진단 로깅
        korea_tz = pytz.timezone('Asia/Seoul')
        now_korea = datetime.now(korea_tz)
        now_local = datetime.now()
        start_time_str = now_korea.strftime('%Y-%m-%d %H:%M:%S')
        logger.info("=" * 60)
        logger.info(f"[{function_name}] Vertex AI 주가 예측 작업 시작 (시스템 시간: {now_local.strftime('%Y-%m-%d %H:%M:%S')}, 한국 시간: {start_time_str} KST)")
        logger.info("=" * 60)
        
        if self.prediction_executing:
            logger.warning(f"[{function_name}] 이미 실행 중입니다. 중복 실행을 방지합니다.")
            return False
        
        self.prediction_executing = True
        
        try:
            if send_slack_notification:
                send_scheduler_slack_notification(f"🚀 *Vertex AI 주가 예측 시작*\nrun_predict_vertex_ai.py 실행을 시작합니다.\n실행 시간: {start_time_str} (KST)")
            
            import subprocess
            import sys
            import os
            from pathlib import Path
            
            # run_predict_vertex_ai.py 파일 경로 확인
            project_root = Path(__file__).parent.parent.parent
            script_path = project_root / "scripts" / "run" / "run_predict_vertex_ai.py"
            
            if not script_path.exists():
                logger.error(f"[{function_name}] ❌ run_predict_vertex_ai.py 파일을 찾을 수 없습니다: {script_path}")
                if send_slack_notification:
                    send_scheduler_slack_notification(f"❌ *Vertex AI 주가 예측 실패*\nrun_predict_vertex_ai.py 파일을 찾을 수 없습니다.")
                return False
            
            logger.info(f"[{function_name}] 예측 스크립트 경로: {script_path}")
            
            # 환경변수 설정
            env = os.environ.copy()
            if hasattr(settings, 'GCP_PROJECT_ID') and settings.GCP_PROJECT_ID:
                env['GCP_PROJECT_ID'] = settings.GCP_PROJECT_ID
            if hasattr(settings, 'GCP_REGION') and settings.GCP_REGION:
                env['GCP_REGION'] = settings.GCP_REGION
            if hasattr(settings, 'GCP_BUCKET_NAME') and settings.GCP_BUCKET_NAME:
                env['GCP_BUCKET_NAME'] = settings.GCP_BUCKET_NAME
            if hasattr(settings, 'GCP_STAGING_BUCKET') and settings.GCP_STAGING_BUCKET:
                env['GCP_STAGING_BUCKET'] = settings.GCP_STAGING_BUCKET
            
            # GOOGLE_APPLICATION_CREDENTIALS 환경 변수 확인
            if not env.get('GOOGLE_APPLICATION_CREDENTIALS'):
                # 컨테이너 내부 경로 확인
                container_creds_path = Path("/app/credentials/vertex-ai-key.json")
                if container_creds_path.exists():
                    env['GOOGLE_APPLICATION_CREDENTIALS'] = str(container_creds_path)
                    logger.info(f"[{function_name}] 인증 파일 경로 설정: {container_creds_path}")
            
            try:
                # run_predict_vertex_ai.py 실행
                logger.info(f"[{function_name}] Vertex AI 주가 예측 작업 실행 중...")
                result = subprocess.run(
                    [sys.executable, str(script_path)],
                    capture_output=True,
                    text=True,
                    cwd=str(project_root),
                    env=env,
                    timeout=7200  # 2시간 타임아웃
                )
                
                if result.returncode == 0:
                    logger.info(f"[{function_name}] ✅ Vertex AI 주가 예측 작업 완료")
                    logger.info(result.stdout)
                    if send_slack_notification:
                        # 출력의 마지막 부분만 전송 (너무 길면 잘림)
                        output_preview = result.stdout[-1000:] if len(result.stdout) > 1000 else result.stdout
                        send_scheduler_slack_notification(
                            f"✅ *Vertex AI 주가 예측 완료*\n"
                            f"run_predict_vertex_ai.py 실행이 성공적으로 완료되었습니다.\n\n"
                            f"출력:\n```\n{output_preview}\n```"
                        )
                    return True
                else:
                    logger.error(f"[{function_name}] ❌ Vertex AI 주가 예측 작업 실패 (Exit Code: {result.returncode})")
                    logger.error(result.stderr)
                    if send_slack_notification:
                        error_preview = result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr
                        send_scheduler_slack_notification(
                            f"❌ *Vertex AI 주가 예측 실패*\n"
                            f"Exit Code: {result.returncode}\n\n"
                            f"오류:\n```\n{error_preview}\n```"
                        )
                    return False
                    
            except subprocess.TimeoutExpired:
                logger.error(f"[{function_name}] ❌ Vertex AI 주가 예측 작업 타임아웃 (2시간 초과)")
                if send_slack_notification:
                    send_scheduler_slack_notification(f"❌ *Vertex AI 주가 예측 타임아웃*\n실행 시간이 2시간을 초과했습니다.")
                return False
            except Exception as e:
                logger.error(f"[{function_name}] 실행 중 오류 발생: {str(e)}", exc_info=True)
                if send_slack_notification:
                    send_scheduler_slack_notification(f"❌ *Vertex AI 주가 예측 오류*\n오류 발생: {str(e)}")
                return False
                
        finally:
            self.prediction_executing = False
            logger.info(f"[{function_name}] 함수 실행 완료")
            logger.info("=" * 60)

    def _run_predict_model(self):
        """AI 예측 모델 학습 및 예측 실행 (predict.py)"""
        function_name = "_run_predict_model"
        logger.info("=" * 60)
        logger.info(f"[{function_name}] 함수 실행 시작")
        logger.info("=" * 60)
        send_scheduler_slack_notification(f"🤖 *AI 예측 모델 학습 시작*\npredict.py 실행을 시작합니다.")
        
        import subprocess
        import sys
        import os
        
        # predict.py 파일 경로 확인
        project_root = Path(__file__).parent.parent.parent
        predict_path = project_root / "scripts" / "utils" / "predict.py"

        if not predict_path.exists():
            logger.error(f"[{function_name}] ❌ predict.py 파일을 찾을 수 없습니다: {predict_path}")
            logger.info(f"[{function_name}] 함수 실행 완료 (실패)")
            return False
        
        try:
            # 환경변수 설정
            env = os.environ.copy()
            
            # predict.py 실행 (최대 2시간 타임아웃)
            logger.info(f"predict.py 실행 중... (경로: {predict_path})")
            result = subprocess.run(
                [sys.executable, str(predict_path)],
                capture_output=True,
                text=True,
                timeout=7200,  # 2시간 타임아웃
                env=env,
                cwd=str(predict_path.parent)  # 작업 디렉토리를 predict.py가 있는 디렉토리로 설정
            )
            
            if result.returncode == 0:
                logger.info("✅ AI 예측 모델 학습 완료")
                logger.info("=" * 60)
                # 출력이 너무 길면 마지막 50줄만 출력
                output_lines = result.stdout.split('\n')
                if len(output_lines) > 50:
                    logger.info("출력 (마지막 50줄):")
                    for line in output_lines[-50:]:
                        if line.strip():
                            logger.info(line)
                else:
                    logger.info("출력:")
                    logger.info(result.stdout)
                logger.info("=" * 60)
                
                # Slack 알림 전송
                try:
                    slack_notifier.send_prediction_complete_notification()
                except Exception as e:
                    logger.warning(f"Slack 알림 전송 실패: {str(e)}")
                
                return True
            else:
                logger.error("❌ AI 예측 모델 학습 실패")
                logger.error(f"에러 코드: {result.returncode}")
                logger.error("에러 출력:")
                logger.error(result.stderr)
                
                # Slack 알림 전송
                try:
                    slack_notifier.send_prediction_error_notification(str(result.stderr))
                except Exception as e:
                    logger.warning(f"Slack 알림 전송 실패: {str(e)}")
                
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("❌ AI 예측 모델 학습 타임아웃 (2시간 초과)")
            logger.error("예측 모델 학습이 너무 오래 걸립니다. GPU 사용을 고려하세요.")
            return False
        except FileNotFoundError:
            logger.error(f"❌ Python 실행 파일을 찾을 수 없습니다: {sys.executable}")
            return False
        except Exception as e:
            logger.error(f"❌ AI 예측 모델 학습 중 오류 발생: {str(e)}", exc_info=True)
            return False

    def start_sell_scheduler(self):
        """매도 스케줄러 시작"""
        if self.sell_running:
            logger.warning("매도 스케줄러가 이미 실행 중입니다.")
            return False
        
        # 기존 매도 작업이 있다면 먼저 취소 (중복 등록 방지)
        sell_jobs = [job for job in schedule.jobs if job.job_func.__name__ == '_run_auto_sell']
        for job in sell_jobs:
            schedule.cancel_job(job)
            logger.debug(f"기존 매도 작업 취소: {job.job_func.__name__}")
        
        # 5분마다 매도 작업 실행
        schedule.every(5).minutes.do(self._run_auto_sell)
        
        # 스케줄러 스레드가 없으면 시작
        if not self.running and not self.scheduler_thread:
            self.scheduler_thread = threading.Thread(target=self._run_scheduler)
            self.scheduler_thread.daemon = True
            self.scheduler_thread.start()
        
        self.sell_running = True
        logger.info("매도 스케줄러가 시작되었습니다.")
        logger.info("  - 실행 주기: 5분마다 매도 대상 확인")
        return True
    
    def stop_sell_scheduler(self):
        """매도 스케줄러 중지"""
        if not self.sell_running:
            return False
        
        if self.stopping:
            return False  # 이미 중지 중이면 중복 로그 방지
        
        self.stopping = True
        # 매도 관련 작업만 취소
        sell_jobs = [job for job in schedule.jobs if job.job_func.__name__ == '_run_auto_sell']
        for job in sell_jobs:
            schedule.cancel_job(job)
        
        self.sell_running = False
        
        # 매수, 매도 모두 중지된 경우 스레드 종료
        if not self.running and self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
            self.scheduler_thread = None
            
        logger.info("매도 스케줄러가 중지되었습니다.")
        self.stopping = False
        return True
    
    def _run_scheduler(self):
        """스케줄러 백그라운드 실행 함수"""
        # 시간대 확인 로깅 (최초 1회)
        korea_tz = pytz.timezone('Asia/Seoul')
        now_korea = datetime.now(korea_tz)
        now_local = datetime.now()
        logger.info(f"[스케줄러 시작] 시스템 로컬 시간: {now_local.strftime('%Y-%m-%d %H:%M:%S')}, 한국 시간: {now_korea.strftime('%Y-%m-%d %H:%M:%S')} (KST)")
        
        last_log_time = None
        while self.running or self.sell_running or self.analysis_running:
            schedule.run_pending()
            time.sleep(1)
            
            # 1시간마다 시간대 확인 로깅 (디버깅용)
            current_time = datetime.now()
            if last_log_time is None or (current_time - last_log_time).total_seconds() >= 3600:
                now_korea = datetime.now(korea_tz)
                logger.debug(f"[스케줄러 동작 중] 시스템 로컬 시간: {current_time.strftime('%Y-%m-%d %H:%M:%S')}, 한국 시간: {now_korea.strftime('%Y-%m-%d %H:%M:%S')} (KST)")
                last_log_time = current_time
    
    def _run_analysis(self, send_slack_notification: bool = True):
        """통합 분석 실행 (기술적 지표 + 감정 분석)"""
        function_name = "_run_analysis"
        
        # 중복 실행 방지: 이미 실행 중이면 건너뜀
        if self.analysis_executing:
            logger.warning(f"[{function_name}] 분석 작업이 이미 실행 중입니다. 중복 실행을 건너뜁니다.")
            return False
        
        self.analysis_executing = True
        logger.info("=" * 50)
        logger.info(f"[{function_name}] 함수 실행 시작")
        logger.info("=" * 50)
        if send_slack_notification:
            send_scheduler_slack_notification(f"📊 *통합 분석 작업 시작*\n기술적 지표 + 감정 분석을 시작합니다.")
        
        try:
            # 1단계: 기술적 지표 생성 및 저장
            logger.info(f"[{function_name}] 1단계: 기술적 지표 분석 시작...")
            # 스케줄러에서 슬랙 알림을 관리하므로 서비스 레이어에서는 슬랙 알림 비활성화
            tech_result = self.recommendation_service.generate_technical_recommendations(send_slack_notification=False)
            logger.info(f"[{function_name}] ✅ 기술적 지표 분석 완료: {tech_result.get('message', '')}")
            
            # 기술적 지표 분석 완료 슬랙 알림 (스케줄러에서 관리)
            if send_slack_notification:
                tech_data = tech_result.get('data', [])
                recommended_count = len([r for r in tech_data if r.get('추천_여부', False)])
                total_count = len(tech_data)
                # 날짜 정보는 recommendations의 첫 번째 항목에서 가져오거나, 없으면 현재 날짜 사용
                date_str = tech_data[0].get('날짜', datetime.now().strftime("%Y-%m-%d")) if tech_data else datetime.now().strftime("%Y-%m-%d")
                send_scheduler_slack_notification(
                    f"📊 *기술적 지표 분석 완료*\n"
                    f"날짜: {date_str}\n"
                    f"분석 종목: {total_count}개\n"
                    f"추천 종목: {recommended_count}개"
                )
            
            # 2단계: 뉴스 감정 분석 수행
            logger.info(f"[{function_name}] 2단계: 뉴스 감정 분석 시작...")
            sentiment_result = self.recommendation_service.fetch_and_store_sentiment_for_recommendations()
            logger.info(f"[{function_name}] ✅ 뉴스 감정 분석 완료: {sentiment_result.get('message', '')}")
            
            # 3단계: 통합 분석 결과 조회 (슬랙 알림 포함)
            logger.info(f"[{function_name}] 3단계: 통합 분석 결과 조회 및 슬랙 알림...")
            # send_slack_notification이 True인 경우에만 Slack 알림 전송 (get_combined_recommendations_with_technical_and_sentiment 내부에서 처리)
            combined_result = self.recommendation_service.get_combined_recommendations_with_technical_and_sentiment(
                send_slack_notification=send_slack_notification
            )
            
            final_count = len(combined_result.get('results', []))
            logger.info(f"[{function_name}] ✅ 통합 분석 완료: {final_count}개 종목 추천")
            logger.info(f"[{function_name}]    매수 대상: {combined_result.get('message', '')}")
            
            logger.info("=" * 50)
            logger.info(f"[{function_name}] 함수 실행 완료")
            logger.info("=" * 50)
            # get_combined_recommendations_with_technical_and_sentiment 내부에서 이미 Slack 알림을 전송하므로 중복 전송 제거
            
        except Exception as e:
            logger.error(f"[{function_name}] ❌ 통합 분석 중 오류 발생: {str(e)}", exc_info=True)
            logger.info(f"[{function_name}] 함수 실행 완료 (오류)")
            if send_slack_notification:
                success = send_scheduler_slack_notification(f"❌ *통합 분석 작업 오류*\n오류 발생: {str(e)}")
                if not success:
                    logger.warning(f"[{function_name}] 슬랙 알림 전송 실패 (통합 분석 작업 오류)")
        finally:
            # 실행 완료 후 플래그 해제
            self.analysis_executing = False
    
    def _run_parallel_analysis(self, send_slack_notification: bool = True):
        """
        두 가지 분석 작업을 병렬로 실행
        - 기술적 지표 분석 (~5분)
        - 감정 분석 (독립적, ~20분)
        
        참고: Vertex AI 예측은 23:00에 별도로 실행됨
        """
        function_name = "_run_parallel_analysis"
        # 시간 진단 로깅
        korea_tz = pytz.timezone('Asia/Seoul')
        now_korea = datetime.now(korea_tz)
        now_local = datetime.now()
        start_time_str = now_korea.strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"[{function_name}] 함수 실행 시작 (시스템 시간: {now_local.strftime('%Y-%m-%d %H:%M:%S')}, 한국 시간: {start_time_str} KST)")
        
        # 중복 실행 방지
        if self.analysis_executing:
            logger.warning(f"[{function_name}] 분석 작업이 이미 실행 중입니다. 중복 실행을 건너뜁니다.")
            return False
        
        self.analysis_executing = True
        logger.info("=" * 60)
        logger.info(f"[{function_name}] 병렬 분석 작업 시작")
        logger.info("=" * 60)
        if send_slack_notification:
            send_scheduler_slack_notification(f"🚀 *병렬 분석 작업 시작*\n기술적 지표와 감정 분석을 병렬로 실행합니다.\n실행 시간: {start_time_str} (KST)")
        
        try:
            import concurrent.futures
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                # 1. 기술적 지표 분석
                logger.info(f"[{function_name}] 기술적 지표 분석 시작...")
                tech_future = executor.submit(
                    self.recommendation_service.generate_technical_recommendations,
                    send_slack_notification=False  # 개별 알림은 비활성화
                )
                
                # 2. 감정 분석 (독립적)
                logger.info(f"[{function_name}] 감정 분석 시작...")
                sentiment_future = executor.submit(
                    self.recommendation_service.fetch_and_store_sentiment_independent
                )
                
                # 기술적 지표와 감정 분석 결과 대기
                tech_result = tech_future.result()
                sentiment_result = sentiment_future.result()
                
                logger.info(f"[{function_name}] ✅ 기술적 지표 분석 완료: {tech_result.get('message', '')}")
                logger.info(f"[{function_name}] ✅ 감정 분석 완료: {sentiment_result.get('message', '')}")
                
                # 기술적 지표 분석 완료 슬랙 알림
                if send_slack_notification:
                    tech_data = tech_result.get('data', [])
                    recommended_count = len([r for r in tech_data if r.get('추천_여부', False)])
                    total_count = len(tech_data)
                    date_str = tech_data[0].get('날짜', datetime.now().strftime("%Y-%m-%d")) if tech_data else datetime.now().strftime("%Y-%m-%d")
                    success = send_scheduler_slack_notification(
                        f"📊 *기술적 지표 분석 완료*\n"
                        f"날짜: {date_str}\n"
                        f"분석 종목: {total_count}개\n"
                        f"추천 종목: {recommended_count}개"
                    )
                    if not success:
                        logger.warning(f"[{function_name}] 슬랙 알림 전송 실패 (기술적 지표 분석 완료)")
                    
                    # 감정 분석 완료 슬랙 알림
                    sentiment_results = sentiment_result.get('results', [])
                    success = send_scheduler_slack_notification(
                        f"💬 *감정 분석 완료*\n"
                        f"{sentiment_result.get('message', '')}"
                    )
                    if not success:
                        logger.warning(f"[{function_name}] 슬랙 알림 전송 실패 (감정 분석 완료)")
                
            end_time_korea = datetime.now(korea_tz)
            end_time_str = end_time_korea.strftime('%Y-%m-%d %H:%M:%S')
            elapsed_time = (end_time_korea - now_korea).total_seconds()
            logger.info("=" * 60)
            logger.info(f"[{function_name}] 병렬 분석 작업 완료 (소요 시간: {elapsed_time:.1f}초)")
            logger.info("=" * 60)
            if send_slack_notification:
                send_scheduler_slack_notification(
                    f"✅ *병렬 분석 작업 완료*\n"
                    f"시작: {start_time_str} (KST)\n"
                    f"완료: {end_time_str} (KST)\n"
                    f"소요 시간: {elapsed_time:.1f}초"
                )
            return True
            
        except Exception as e:
            logger.error(f"[{function_name}] ❌ 병렬 분석 중 오류 발생: {str(e)}", exc_info=True)
            if send_slack_notification:
                success = send_scheduler_slack_notification(f"❌ *병렬 분석 작업 오류*\n오류 발생: {str(e)}")
                if not success:
                    logger.warning(f"[{function_name}] 슬랙 알림 전송 실패 (병렬 분석 작업 오류)")
            return False
        finally:
            # 실행 완료 후 플래그 해제
            self.analysis_executing = False
    
    def _run_combined_analysis(self, send_slack_notification: bool = True):
        """
        세 가지 분석 결과를 통합하여 최종 추천 생성
        - AI 예측 결과 (stock_analysis_results)
        - 기술적 지표 분석 결과 (stock_recommendations)
        - 감정 분석 결과 (ticker_sentiment_analysis)
        """
        function_name = "_run_combined_analysis"
        # 시간 진단 로깅
        korea_tz = pytz.timezone('Asia/Seoul')
        now_korea = datetime.now(korea_tz)
        now_local = datetime.now()
        logger.info("=" * 60)
        logger.info(f"[{function_name}] 통합 분석 시작 (시스템 시간: {now_local.strftime('%Y-%m-%d %H:%M:%S')}, 한국 시간: {now_korea.strftime('%Y-%m-%d %H:%M:%S')} KST)")
        logger.info("=" * 60)
        if send_slack_notification:
            send_scheduler_slack_notification(f"🔗 *통합 분석 시작*\n세 가지 분석 결과를 통합합니다.")
        
        try:
            # 통합 분석 결과 조회 (슬랙 알림 포함)
            combined_result = self.recommendation_service.get_combined_recommendations_with_technical_and_sentiment(
                send_slack_notification=send_slack_notification
            )
            
            final_count = len(combined_result.get('results', []))
            logger.info(f"[{function_name}] ✅ 통합 분석 완료: {final_count}개 종목 추천")
            logger.info(f"[{function_name}]    매수 대상: {combined_result.get('message', '')}")
            
            logger.info("=" * 60)
            logger.info(f"[{function_name}] 통합 분석 완료")
            logger.info("=" * 60)
            return True
            
        except Exception as e:
            logger.error(f"[{function_name}] ❌ 통합 분석 중 오류 발생: {str(e)}", exc_info=True)
            if send_slack_notification:
                send_scheduler_slack_notification(f"❌ *통합 분석 오류*\n오류 발생: {str(e)}")
            return False

    def _run_auto_buy(self, send_slack_notification: bool = True):
        """자동 매수 실행 함수 - 스케줄링된 시간에 실행됨"""
        function_name = "_run_auto_buy"
        
        # 중복 실행 방지: 이미 실행 중이면 건너뜀
        if self.buy_executing:
            logger.warning(f"[{function_name}] 매수 작업이 이미 실행 중입니다. 중복 실행을 건너뜁니다.")
            return False
        
        self.buy_executing = True
        # 시간 진단 로깅
        korea_tz = pytz.timezone('Asia/Seoul')
        now_korea = datetime.now(korea_tz)
        now_local = datetime.now()
        logger.info(f"[{function_name}] 함수 실행 시작 (시스템 시간: {now_local.strftime('%Y-%m-%d %H:%M:%S')}, 한국 시간: {now_korea.strftime('%Y-%m-%d %H:%M:%S')} KST)")
        if send_slack_notification:
            send_scheduler_slack_notification(f"💰 *자동 매수 작업 시작*\n매수 작업을 시작합니다.")
        
        try:
            # 주말 체크 (뉴욕 시간 기준)
            now_ny = datetime.now(pytz.timezone('America/New_York'))
            ny_weekday = now_ny.weekday()  # 0=월요일, 6=일요일
            
            # 주말(토요일=5, 일요일=6)이면 실행하지 않음
            if ny_weekday >= 5:
                logger.info(f"[{function_name}] 현재 시간 (뉴욕: {now_ny.strftime('%Y-%m-%d %H:%M:%S')})은 주말입니다. 매수 작업을 건너뜁니다.")
                logger.info(f"[{function_name}] 함수 실행 완료 (주말로 인한 건너뜀)")
                return False
            
            # 새 스레드에서 비동기 함수 실행
            import threading
            def run_in_thread():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    new_loop.run_until_complete(self._execute_auto_buy(send_slack_notification=send_slack_notification))
                finally:
                    new_loop.close()
            
            thread = threading.Thread(target=run_in_thread)
            thread.start()
            thread.join()
            
            logger.info(f"[{function_name}] 함수 실행 완료")
            return True
        except Exception as e:
            logger.error(f"[{function_name}] 함수 실행 중 오류 발생: {str(e)}", exc_info=True)
            logger.info(f"[{function_name}] 함수 실행 완료 (오류)")
            return False
        finally:
            # 실행 완료 후 플래그 해제
            self.buy_executing = False
    
    def _run_auto_sell(self):
        """자동 매도 실행 함수 - 1분마다 실행됨"""
        function_name = "_run_auto_sell"
        
        try:
            # 주말 체크 (뉴욕 시간 기준)
            now_ny = datetime.now(pytz.timezone('America/New_York'))
            ny_weekday = now_ny.weekday()  # 0=월요일, 6=일요일
            
            # 주말(토요일=5, 일요일=6)이면 실행하지 않음
            if ny_weekday >= 5:
                return False
        
            # 새 스레드에서 비동기 함수 실행
            import threading
            def run_in_thread():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    new_loop.run_until_complete(self._execute_auto_sell())
                finally:
                    new_loop.close()
            
            thread = threading.Thread(target=run_in_thread)
            thread.start()
            thread.join()
            
            return True
        except Exception as e:
            logger.error(f"[{function_name}] 함수 실행 중 오류 발생: {str(e)}", exc_info=True)
            return False
    
    async def _execute_auto_sell(self):
        """자동 매도 실행 로직"""
        function_name = "_execute_auto_sell"
        
        # 트레일링 스톱 활성화된 종목의 최고가 갱신 (매도 조건 체크 전에 실행)
        try:
            from app.services.trailing_stop_service import TrailingStopService
            trailing_stop_service = TrailingStopService()
            
            # 설정 확인
            config = self.auto_trading_service.get_auto_trading_config()
            if config.get("trailing_stop_enabled", False):
                # 보유 종목 조회
                balance_result = get_overseas_balance()
                if balance_result.get("rt_cd") == "0":
                    holdings = balance_result.get("output1", [])
                    active_trailing_stops = trailing_stop_service.get_active_trailing_stops()
                    
                    # 활성화된 트레일링 스톱 종목만 최고가 갱신
                    for item in holdings:
                        ticker = item.get("ovrs_pdno")
                        if ticker in active_trailing_stops:
                            try:
                                current_price = float(item.get("now_pric2", 0))
                                if current_price > 0:
                                    trailing_stop_service.update_highest_price(ticker, current_price)
                            except (ValueError, TypeError) as e:
                                logger.debug(f"[{function_name}] {ticker} 최고가 갱신 중 오류 (무시): {str(e)}")
        except Exception as e:
            logger.warning(f"[{function_name}] 트레일링 스톱 최고가 갱신 중 오류 (계속 진행): {str(e)}")
        
        # 매도 대상 종목 조회
        sell_candidates_result = self.recommendation_service.get_stocks_to_sell()
        
        if not sell_candidates_result or not sell_candidates_result.get("sell_candidates"):
            return
        
        sell_candidates = sell_candidates_result.get("sell_candidates", [])
        
        if not sell_candidates:
            return
        
        # 우선순위별 통계 추적
        priority_stats = {
            SellPriority.STOP_LOSS: {"count": 0, "success": 0, "failed": 0, "name": "손절 (Priority 1)"},
            SellPriority.TRAILING_STOP: {"count": 0, "success": 0, "failed": 0, "name": "트레일링 스톱 (Priority 2)"},
            SellPriority.TAKE_PROFIT: {"count": 0, "success": 0, "failed": 0, "name": "익절 (Priority 3)"},
            SellPriority.TECHNICAL: {"count": 0, "success": 0, "failed": 0, "name": "기술적 매도 (Priority 4)"}
        }
        
        # 우선순위별로 그룹화하여 로깅
        priority_groups = {
            SellPriority.STOP_LOSS: [],
            SellPriority.TRAILING_STOP: [],
            SellPriority.TAKE_PROFIT: [],
            SellPriority.TECHNICAL: []
        }
        for candidate in sell_candidates:
            priority = candidate.get("priority", SellPriority.TECHNICAL)  # 기본값 4
            if priority in priority_groups:
                priority_groups[priority].append(candidate)
        
        logger.info(f"[{function_name}] 매도 대상 종목 {len(sell_candidates)}개 발견")
        logger.info(f"[{function_name}] 우선순위별 분류: Priority 1 (손절) {len(priority_groups[1])}개, Priority 2 (트레일링 스톱) {len(priority_groups[2])}개, Priority 3 (익절) {len(priority_groups[3])}개, Priority 4 (기술적 매도) {len(priority_groups[4])}개")
        
        # 우선순위 순서대로 처리 (Priority 1 → 2 → 3 → 4)
        for priority in [SellPriority.STOP_LOSS, SellPriority.TRAILING_STOP, SellPriority.TAKE_PROFIT, SellPriority.TECHNICAL]:
            if not priority_groups[priority]:
                continue
            
            priority_name = priority_stats[priority]["name"]
            logger.info(f"[{function_name}] ========== {priority_name} 처리 시작 ({len(priority_groups[priority])}개) ==========")
            
            # 각 종목에 대해 매도 주문 실행
            for candidate in priority_groups[priority]:
                try:
                    ticker = candidate["ticker"]
                    stock_name = candidate["stock_name"]
                    exchange_code = candidate["exchange_code"]
                    quantity = candidate["quantity"]
                    
                    # 매도 근거
                    sell_reasons = candidate.get("sell_reasons", [])
                    
                    # 거래소 코드 변환 (API 요청에 맞게 변환)
                    api_exchange_code = get_exchange_code_for_api(exchange_code)
                    
                    # 현재가 조회 실패 추적: 일정 횟수 이상 실패한 종목은 일정 시간 동안 제외
                    MAX_PRICE_FETCH_FAILURES = SchedulerConfig.MAX_PRICE_FETCH_FAILURES
                    PRICE_FETCH_EXCLUDE_MINUTES = SchedulerConfig.PRICE_FETCH_EXCLUDE_MINUTES
                    
                    now = datetime.now()
                    
                    # 이전에 실패한 적이 있는 종목인지 확인
                    if ticker in self.price_fetch_failures:
                        failure_count, last_failure_time = self.price_fetch_failures[ticker]
                        time_since_last_failure = now - last_failure_time
                        
                        # 실패 횟수가 최대치를 초과하고, 제외 시간이 지나지 않았으면 스킵
                        if failure_count >= MAX_PRICE_FETCH_FAILURES:
                            if time_since_last_failure < timedelta(minutes=PRICE_FETCH_EXCLUDE_MINUTES):
                                logger.debug(f"[{function_name}] {stock_name}({ticker}) 현재가 조회 실패로 인해 일시적으로 제외됨 (실패 {failure_count}회, {int((PRICE_FETCH_EXCLUDE_MINUTES * 60 - time_since_last_failure.total_seconds()) / 60)}분 후 재시도 가능)")
                                continue
                            else:
                                # 제외 시간이 지났으면 카운터 리셋
                                logger.info(f"[{function_name}] {stock_name}({ticker}) 제외 시간이 경과하여 다시 시도합니다.")
                                del self.price_fetch_failures[ticker]
                    
                    # 레버리지 티커인지 확인하고, 본주 티커 가격으로 매도 조건 체크
                    base_ticker = None  # 본주 티커 (레버리지 티커인 경우)
                    is_leverage = False
                    
                    # MongoDB에서 레버리지 티커인지 확인 (leverage_ticker 필드로 역매핑)
                    try:
                        from app.db.mongodb import get_db
                        db = get_db()
                        if db is not None:
                            # stocks 컬렉션에서 leverage_ticker가 현재 티커인 문서 찾기
                            base_stock = db.stocks.find_one({"leverage_ticker": ticker})
                            if base_stock:
                                base_ticker = base_stock.get("ticker")
                                is_leverage = True
                                logger.info(f"[{function_name}] {stock_name}({ticker})는 레버리지 티커입니다. 본주 {base_ticker}의 가격으로 매도 조건을 확인합니다.")
                    except Exception as e:
                        logger.warning(f"[{function_name}] 레버리지 티커 확인 중 오류 (계속 진행): {str(e)}")
                    
                    # 매도 조건 체크용 가격 조회 (레버리지 티커인 경우 본주 가격, 아니면 원래 티커)
                    price_check_ticker = base_ticker if is_leverage else ticker
                    
                    # 현재가 조회 (매도 조건 체크용)
                    exchanges = ["NAS", "AMS", "NYS"]
                    price_result = None
                    
                    # 기본 거래소를 맨 앞으로
                    if api_exchange_code in exchanges:
                        exchanges.remove(api_exchange_code)
                        exchanges.insert(0, api_exchange_code)
                    
                    # 여러 거래소에서 현재가 조회 시도 (본주 티커로 - 레버리지인 경우)
                    for exchange in exchanges:
                        price_params = {
                            "AUTH": "",
                            "EXCD": exchange,
                            "SYMB": price_check_ticker
                        }
                        
                        temp_result = get_current_price(price_params)
                        
                        # 데이터가 있는지 확인 (last나 base가 있어야 함)
                        output = temp_result.get("output", {})
                        if temp_result.get("rt_cd") == "0" and (output.get("last") or output.get("base")):
                            price_result = temp_result
                            if exchange != api_exchange_code:
                                logger.info(f"[{function_name}] {stock_name}({ticker}) 거래소 변경 발견: {api_exchange_code} -> {exchange}")
                            break
                        
                        # 마지막 시도였으면 결과 저장 (에러 메시지 확인용)
                        if exchange == exchanges[-1]:
                            price_result = temp_result
                    
                    # API 호출 자체가 실패한 경우
                    if not price_result or price_result.get("rt_cd") != "0":
                        error_msg = price_result.get('msg1', '알 수 없는 오류') if price_result else 'API 호출 실패'
                        logger.error(f"[{function_name}] {stock_name}({ticker}) 현재가 조회 실패 (모든 거래소): {error_msg}")
                        # 실패 횟수 증가
                        if ticker not in self.price_fetch_failures:
                            self.price_fetch_failures[ticker] = (1, now)
                        else:
                            failure_count, _ = self.price_fetch_failures[ticker]
                            self.price_fetch_failures[ticker] = (failure_count + 1, now)
                        
                        # API 속도 제한에 도달했을 때 더 오래 대기
                        if price_result and "초당" in error_msg:
                            await asyncio.sleep(SchedulerConfig.PRICE_FETCH_RATE_LIMIT_SLEEP_SECONDS)
                        continue
                    
                    # 현재가 추출 (안전하게 처리) - last 우선, 없으면 base(전일 종가) 사용
                    output = price_result.get("output", {})
                    last_price = output.get("last", "") or ""
                    base_price = output.get("base", "") or ""
                    
                    try:
                        current_price = None
                        
                        # 1순위: 실시간 현재가 (last)
                        if last_price and last_price != "":
                            try:
                                current_price = float(last_price)
                                if current_price > 0:
                                    if is_leverage:
                                        logger.info(f"[{function_name}] {stock_name}({ticker}) 레버리지 티커 - 본주 {price_check_ticker}의 실시간 현재가 사용: {current_price}")
                                    else:
                                        logger.debug(f"[{function_name}] {stock_name}({ticker}) 실시간 현재가 사용: {current_price}")
                            except (ValueError, TypeError):
                                pass
                        
                        # 2순위: 전일 종가 (base) - 레버리지 ETF 등 특수 종목 대응
                        if (current_price is None or current_price <= 0) and base_price and base_price != "":
                            try:
                                current_price = float(base_price)
                                if current_price > 0:
                                    if is_leverage:
                                        logger.warning(f"[{function_name}] {stock_name}({ticker}) 레버리지 티커 - 본주 {price_check_ticker}의 실시간 현재가 없음, 전일 종가 사용: {current_price}")
                                    else:
                                        logger.warning(f"[{function_name}] {stock_name}({ticker}) 실시간 현재가 없음, 전일 종가 사용: {current_price}")
                            except (ValueError, TypeError):
                                pass
                        
                        # 현재가를 찾지 못한 경우
                        if current_price is None or current_price <= 0:
                            logger.error(f"[{function_name}] {stock_name}({ticker}) 현재가가 비어있거나 유효하지 않습니다 (last: '{last_price}', base: '{base_price}'). 실패 횟수를 기록합니다.")
                            # 실패 횟수 증가
                            if ticker not in self.price_fetch_failures:
                                self.price_fetch_failures[ticker] = (1, now)
                            else:
                                failure_count, _ = self.price_fetch_failures[ticker]
                                self.price_fetch_failures[ticker] = (failure_count + 1, now)
                            
                            if self.price_fetch_failures[ticker][0] >= MAX_PRICE_FETCH_FAILURES:
                                logger.warning(f"[{function_name}] {stock_name}({ticker}) 현재가 조회가 {MAX_PRICE_FETCH_FAILURES}회 연속 실패했습니다. {PRICE_FETCH_EXCLUDE_MINUTES}분 동안 제외합니다.")
                            else:
                                logger.info(f"[{function_name}] {stock_name}({ticker}) 현재가 조회 실패 ({self.price_fetch_failures[ticker][0]}/{MAX_PRICE_FETCH_FAILURES}회). 다음 스케줄러 실행에서 다시 시도합니다.")
                            
                            await asyncio.sleep(2)  # 잠시 기다렸다가 넘어감
                            raise Exception("현재가 조회 실패 - continue 처리")  # except 블록에서 continue 처리
                        
                        # 현재가 조회 성공: 실패 카운터 리셋 (있었다면)
                        if ticker in self.price_fetch_failures:
                            del self.price_fetch_failures[ticker]
                            logger.debug(f"[{function_name}] {stock_name}({ticker}) 현재가 조회 성공. 실패 카운터를 리셋했습니다.")
                    
                    except Exception as ve:
                        if "현재가 조회 실패 - continue 처리" in str(ve):
                            continue
                        logger.error(f"[{function_name}] {stock_name}({ticker}) 현재가 변환 오류: {str(ve)}, last: '{last_price}', base: '{base_price}'")
                        continue
                    
                    # 매도 주문 실행
                    # 레버리지 티커인 경우: 본주 가격으로 조건 확인했지만, 실제 주문은 레버리지 티커의 현재가 사용
                    # (본주 가격으로 주문하면 레버리지 티커의 시장 가격과 다를 수 있으므로)
                    order_price = current_price  # 기본값은 조회한 가격 (본주 가격)
                    
                    # 레버리지 티커인 경우 레버리지 티커의 실제 현재가도 조회 시도 (주문 가격으로 사용)
                    if is_leverage:
                        try:
                            leverage_price_result = None
                            for exchange in exchanges:
                                leverage_price_params = {
                                    "AUTH": "",
                                    "EXCD": exchange,
                                    "SYMB": ticker  # 레버리지 티커로 조회
                                }
                                leverage_temp_result = get_current_price(leverage_price_params)
                                output = leverage_temp_result.get("output", {})
                                if leverage_temp_result.get("rt_cd") == "0" and (output.get("last") or output.get("base")):
                                    leverage_price_result = leverage_temp_result
                                    break
                            
                            if leverage_price_result and leverage_price_result.get("rt_cd") == "0":
                                leverage_output = leverage_price_result.get("output", {})
                                leverage_last = leverage_output.get("last", "") or ""
                                leverage_base = leverage_output.get("base", "") or ""
                                
                                if leverage_last and leverage_last != "":
                                    try:
                                        order_price = float(leverage_last)
                                        if order_price > 0:
                                            logger.info(f"[{function_name}] {stock_name}({ticker}) 레버리지 티커의 현재가 조회 성공: {order_price} (본주 {base_ticker} 가격: {current_price})")
                                    except (ValueError, TypeError):
                                        pass
                                elif leverage_base and leverage_base != "":
                                    try:
                                        order_price = float(leverage_base)
                                        if order_price > 0:
                                            logger.warning(f"[{function_name}] {stock_name}({ticker}) 레버리지 티커의 현재가 없음, 전일 종가 사용: {order_price} (본주 {base_ticker} 가격: {current_price})")
                                    except (ValueError, TypeError):
                                        pass
                            else:
                                logger.warning(f"[{function_name}] {stock_name}({ticker}) 레버리지 티커의 현재가 조회 실패, 본주 가격({current_price})으로 주문 진행")
                        except Exception as e:
                            logger.warning(f"[{function_name}] {stock_name}({ticker}) 레버리지 티커 가격 조회 중 오류: {str(e)}, 본주 가격({current_price})으로 주문 진행")
                    
                    # 주문 가격 검증
                    if order_price is None or order_price <= 0:
                        logger.error(f"[{function_name}] {stock_name}({ticker}) 주문 가격이 유효하지 않습니다: {order_price}")
                        continue
                    
                    # 주문 데이터 준비
                    # 거래소 코드는 원래 값 사용 (NASD, NYSE, AMEX 등)
                    # order_overseas_stock 함수 내부에서 필요시 변환됨
                    order_data = {
                        "CANO": settings.KIS_CANO,
                        "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
                        "OVRS_EXCG_CD": exchange_code,  # 원래 거래소 코드 사용 (NASD, NYSE, AMEX 등)
                        "PDNO": ticker,  # 레버리지 티커로 주문
                        "ORD_DVSN": OrderType.LIMIT.value,  # 지정가
                        "ORD_QTY": str(quantity),
                        "OVRS_ORD_UNPR": f"{order_price:.2f}",  # 소수점 2자리로 포맷팅
                        "is_buy": False,  # 매도
                        "stock_name": stock_name  # 종목명 추가
                    }
                    
                    # 주문 실패 추적: 일정 시간 동안 실패한 종목은 제외
                    ORDER_FAILURE_EXCLUDE_MINUTES = SchedulerConfig.ORDER_FAILURE_EXCLUDE_MINUTES
                    now = datetime.now()
                    
                    # 이전에 주문 실패한 적이 있는 종목인지 확인
                    if ticker in self.order_failures:
                        time_since_last_failure = now - self.order_failures[ticker]
                        if time_since_last_failure < timedelta(minutes=ORDER_FAILURE_EXCLUDE_MINUTES):
                            logger.info(f"[{function_name}] {stock_name}({ticker}) 이전 주문 실패로 인해 일시적으로 제외됨 ({int((ORDER_FAILURE_EXCLUDE_MINUTES * 60 - time_since_last_failure.total_seconds()) / 60)}분 후 재시도 가능)")
                            continue
                        else:
                            # 제외 시간이 지났으면 제거
                            del self.order_failures[ticker]
                    
                    # 주간거래 시간 체크 (10:00 ~ 18:00 한국시간)
                    now_in_korea = datetime.now(pytz.timezone('Asia/Seoul'))
                    korea_hour = now_in_korea.hour
                    is_daytime_trading = SchedulerConfig.DAYTIME_TRADING_START_HOUR <= korea_hour < SchedulerConfig.DAYTIME_TRADING_END_HOUR
                    
                    # 주간거래 시간이고 미국 주식인 경우 주간주문 API 사용
                    if is_daytime_trading and exchange_code in ["NASD", "NYSE", "AMEX"]:
                        logger.info(f"[{function_name}] {stock_name}({ticker}) 주간거래 시간(10:00~18:00)이므로 주간주문 API를 사용합니다.")
                        order_result = order_overseas_stock_daytime(order_data)
                    else:
                        # 일반 주문 API 사용
                        order_result = order_overseas_stock(order_data)
                    
                    # 우선순위 통계 업데이트
                    priority_stats[priority]["count"] += 1
                    
                    if order_result.get("rt_cd") == "0":
                        # 주문 성공: 실패 기록 제거 (있었다면)
                        if ticker in self.order_failures:
                            del self.order_failures[ticker]
                        
                        # 우선순위별 성공 통계 업데이트
                        priority_stats[priority]["success"] += 1
                        
                        order_type = "시장가" if order_data["ORD_DVSN"] == OrderType.MARKET.value else "지정가"
                        sell_type_name = candidate.get("sell_type", "unknown")
                        logger.info(f"[{function_name}] ✅ {stock_name}({ticker}) 매도 주문 성공 ({order_type}, {sell_type_name}): {order_result.get('msg1', '주문이 접수되었습니다.')}")
                        
                        # 매도 성공 기록을 MongoDB에 저장
                        save_success = self._save_trading_log(
                            order_type="sell",
                            ticker=ticker,
                            stock_name=stock_name,
                            price=order_price,
                            quantity=quantity,
                            status=OrderStatus.EXECUTED.value,  # 매도 성공은 executed로 처리
                            price_change_percent=candidate.get("price_change_percent"),
                            sell_reasons=sell_reasons,
                            order_result=order_result,
                            exchange_code=exchange_code
                        )
                        
                        if not save_success:
                            logger.warning(f"[{function_name}] ⚠️ {stock_name}({ticker}) 매도 주문은 성공했으나 기록 저장에 실패했습니다. 수동으로 확인이 필요합니다.")
                        
                        # 부분 익절 히스토리 업데이트 (부분 매도인 경우)
                        sell_type = candidate.get("sell_type", "")
                        if sell_type == "partial_profit":
                            try:
                                from app.db.mongodb import get_db
                                db = get_db()
                                if db is not None:
                                    partial_profit_info = candidate.get("partial_profit_info")
                                    if partial_profit_info:
                                        stage = partial_profit_info.get("stage")
                                        stage_profit = partial_profit_info.get("profit_percent")
                                        sell_qty = partial_profit_info.get("sell_quantity")
                                        
                                        from app.utils.user_context import get_current_user_id
                                        user_id = get_current_user_id()
                                        
                                        # 부분 익절 히스토리 조회 또는 생성
                                        history = db.partial_sell_history.find_one({
                                            "user_id": user_id,
                                            "ticker": ticker
                                        })
                                        
                                        # 현재 보유 수량 확인 (부분 매도 후 남은 수량)
                                        # 잔고 조회를 통해 정확한 남은 수량 확인
                                        remaining_quantity = 0
                                        try:
                                            balance_result = get_overseas_balance()
                                            if balance_result.get("rt_cd") == "0":
                                                holdings = balance_result.get("output1", [])
                                                for item in holdings:
                                                    if item.get("ovrs_pdno") == ticker:
                                                        remaining_quantity = int(item.get("ovrs_cblc_qty", 0))
                                                        break
                                        except Exception as e:
                                            logger.warning(f"[{function_name}] {stock_name}({ticker}) 부분 매도 후 남은 수량 조회 실패: {str(e)}")
                                        
                                        # 구매 평균단가 조회
                                        purchase_price = candidate.get("purchase_price", 0)
                                        if purchase_price <= 0:
                                            # candidate에 없으면 잔고에서 조회
                                            try:
                                                balance_result = get_overseas_balance()
                                                if balance_result.get("rt_cd") == "0":
                                                    holdings = balance_result.get("output1", [])
                                                    for item in holdings:
                                                        if item.get("ovrs_pdno") == ticker:
                                                            purchase_price = float(item.get("pchs_avg_pric", 0))
                                                            break
                                            except Exception as e:
                                                logger.warning(f"[{function_name}] {stock_name}({ticker}) 구매 평균단가 조회 실패: {str(e)}")
                                        
                                        # 부분 매도 기록 생성
                                        partial_sell_record = {
                                            "stage": stage,
                                            "profit_percent": stage_profit,
                                            "sell_quantity": sell_qty,
                                            "sell_price": order_price,
                                            "sell_date": datetime.utcnow(),
                                            "remaining_quantity": remaining_quantity
                                        }
                                        
                                        if history:
                                            # 기존 히스토리 업데이트
                                            partial_sells = history.get("partial_sells", [])
                                            partial_sells.append(partial_sell_record)
                                            
                                            # 초기 수량이 없으면 현재 수량 + 매도 수량으로 설정
                                            initial_quantity = history.get("initial_quantity")
                                            if not initial_quantity:
                                                initial_quantity = remaining_quantity + sell_qty
                                            
                                            # 모든 단계가 완료되었는지 확인 (3단계 모두 완료)
                                            completed_stages = {sell.get("stage") for sell in partial_sells}
                                            is_completed = len(completed_stages) >= 3
                                            
                                            db.partial_sell_history.update_one(
                                                {"user_id": user_id, "ticker": ticker},
                                                {
                                                    "$set": {
                                                        "partial_sells": partial_sells,
                                                        "is_completed": is_completed,
                                                        "last_updated": datetime.utcnow()
                                                    }
                                                }
                                            )
                                            
                                            logger.info(
                                                f"[{function_name}] 📝 {stock_name}({ticker}) 부분 익절 {stage}단계 히스토리 업데이트 완료 "
                                                f"(매도: {sell_qty}주 @ ${order_price:.2f}, 남은 수량: {remaining_quantity}주)"
                                            )
                                        else:
                                            # 새로운 히스토리 생성
                                            initial_quantity = remaining_quantity + sell_qty
                                            is_completed = stage >= 3  # 3단계면 완료
                                            
                                            new_history = {
                                                "user_id": user_id,
                                                "ticker": ticker,
                                                "stock_name": stock_name,
                                                "purchase_price": purchase_price,
                                                "initial_quantity": initial_quantity,
                                                "partial_sells": [partial_sell_record],
                                                "is_completed": is_completed,
                                                "last_updated": datetime.utcnow(),
                                                "created_at": datetime.utcnow()
                                            }
                                            
                                            db.partial_sell_history.insert_one(new_history)
                                            
                                            logger.info(
                                                f"[{function_name}] 📝 {stock_name}({ticker}) 부분 익절 히스토리 생성 완료 "
                                                f"(초기 수량: {initial_quantity}주, {stage}단계 매도: {sell_qty}주 @ ${order_price:.2f})"
                                            )
                                        
                                        # 3단계 모두 완료되었으면 로그 추가
                                        if is_completed:
                                            logger.info(
                                                f"[{function_name}] ✅ {stock_name}({ticker}) 부분 익절 전략 완료 "
                                                f"(1단계: +5%, 2단계: +8%, 3단계: +12% 모두 매도 완료). "
                                                f"나머지는 트레일링 스톱으로 관리됩니다."
                                            )
                            except Exception as e:
                                logger.warning(f"[{function_name}] 부분 익절 히스토리 업데이트 중 오류 (무시): {str(e)}", exc_info=True)
                        
                        # 트레일링 스톱 비활성화 (전체 매도인 경우만, 부분 매도는 유지)
                        try:
                            from app.services.trailing_stop_service import TrailingStopService
                            trailing_stop_service = TrailingStopService()
                            
                            # 부분 익절이 아닌 경우에만 트레일링 스톱 비활성화
                            if sell_type != "partial_profit":
                                trailing_stop_service.deactivate_trailing_stop(ticker)
                            
                            # 트레일링 스톱 매도인 경우 상세 정보 로깅
                            if sell_type == "trailing_stop":
                                trailing_info = trailing_stop_service.get_trailing_stop_info(ticker)
                                if trailing_info:
                                    logger.info(f"[{function_name}] 📊 {stock_name}({ticker}) 트레일링 스톱 매도 상세:")
                                    logger.info(f"    최고가: ${trailing_info.get('highest_price', 0):.2f}")
                                    logger.info(f"    동적 익절가: ${trailing_info.get('dynamic_stop_price', 0):.2f}")
                                    logger.info(f"    매도가: ${order_price:.2f}")
                                    purchase_price = trailing_info.get('purchase_price', 0)
                                    if purchase_price > 0:
                                        profit_percent = ((order_price - purchase_price) / purchase_price) * 100
                                        logger.info(f"    수익률: {profit_percent:.2f}%")
                        except Exception as e:
                            logger.warning(f"[{function_name}] 트레일링 스톱 비활성화 중 오류 (무시): {str(e)}")
                        
                        # Slack 알림 전송 (성공 시에만)
                        slack_notifier.send_sell_notification(
                            stock_name=stock_name,
                            ticker=ticker,
                            quantity=quantity,
                            price=order_price if order_data["ORD_DVSN"] == OrderType.LIMIT.value else None,  # 시장가는 가격 없음
                            exchange_code=exchange_code,
                            sell_reasons=sell_reasons,
                            success=True
                        )
                    else:
                        error_msg = order_result.get('msg1', '알 수 없는 오류')
                        error_code = order_result.get('msg_cd', '')
                        
                        # 장외거래시간 에러인 경우: 실패 기록하지 않고 조용히 건너뜀 (로그 레벨을 INFO로 변경)
                        if "장운영시간" in error_msg or "APBK0918" in error_code:
                            logger.info(f"[{function_name}] {stock_name}({ticker}) 장외거래시간 주문 불가: {error_msg}. 다음 스케줄러 실행에서 다시 시도합니다.")
                            continue  # 실패 기록 없이 다음 종목으로 (재시도 안 함)
                        
                        # 다른 에러인 경우: 실패 기록
                        priority_stats[priority]["failed"] += 1
                        sell_type_name = candidate.get("sell_type", "unknown")
                        logger.error(f"[{function_name}] ❌ {stock_name}({ticker}) 매도 주문 실패 ({sell_type_name}): {error_msg}")
                        self.order_failures[ticker] = now
                        logger.warning(f"[{function_name}] {stock_name}({ticker}) 주문 실패로 {ORDER_FAILURE_EXCLUDE_MINUTES}분 동안 제외합니다.")
                    
                    # 요청 간 지연 (API 요청 제한 방지)
                    await asyncio.sleep(SchedulerConfig.ORDER_DELAY_SECONDS)
                    
                except Exception as e:
                    priority_stats[priority]["failed"] += 1
                    logger.error(f"[{function_name}] ❌ {candidate['stock_name']}({candidate['ticker']}) 매도 처리 중 오류: {str(e)}", exc_info=True)
                    await asyncio.sleep(1)  # 오류 발생 시에도 잠시 대기
            
            # 우선순위별 처리 완료 로깅
            stats = priority_stats[priority]
            if stats["count"] > 0:
                logger.info(f"[{function_name}] {priority_name} 처리 완료: 총 {stats['count']}개, 성공 {stats['success']}개, 실패 {stats['failed']}개")
        
        # 전체 매도 작업 요약 로깅
        total_count = sum(s["count"] for s in priority_stats.values())
        total_success = sum(s["success"] for s in priority_stats.values())
        total_failed = sum(s["failed"] for s in priority_stats.values())
        
        logger.info("=" * 80)
        logger.info(f"[{function_name}] 📊 매도 작업 요약")
        logger.info(f"  총 매도 대상: {total_count}개")
        logger.info(f"  ✅ 주문 성공: {total_success}개")
        logger.info(f"  ❌ 주문 실패: {total_failed}개")
        logger.info("")
        logger.info("  우선순위별 상세:")
        for priority in [SellPriority.STOP_LOSS, SellPriority.TAKE_PROFIT, SellPriority.TECHNICAL]:
            stats = priority_stats[priority]
            if stats["count"] > 0:
                logger.info(f"    {stats['name']}: {stats['count']}개 (성공: {stats['success']}개, 실패: {stats['failed']}개)")
        logger.info("=" * 80)
    
    async def _execute_auto_buy(self, send_slack_notification: bool = True):
        """자동 매수 실행 로직"""
        function_name = "_execute_auto_buy"
        logger.info(f"[{function_name}] 함수 실행 시작")
        
        # 현재 시간이 미국 장 시간인지 확인 (서머타임 고려)
        now_in_korea = datetime.now(pytz.timezone('Asia/Seoul'))
        now_in_ny = datetime.now(pytz.timezone('America/New_York'))
        ny_hour = now_in_ny.hour
        ny_minute = now_in_ny.minute
        ny_weekday = now_in_ny.weekday()  # 0=월요일, 6=일요일
        
        # 주말 체크
        if ny_weekday >= 5:  # 토요일(5) 또는 일요일(6)
            logger.info(f"[{function_name}] 현재 시간 (한국: {now_in_korea.strftime('%Y-%m-%d %H:%M:%S')}, 뉴욕: {now_in_ny.strftime('%Y-%m-%d %H:%M:%S')})은 주말입니다. 매수 작업을 건너뜁니다.")
            if send_slack_notification:
                slack_notifier.send_no_buy_notification(
                    reason="주말",
                    details=f"현재 시간 (한국: {now_in_korea.strftime('%Y-%m-%d %H:%M:%S')}, 뉴욕: {now_in_ny.strftime('%Y-%m-%d %H:%M:%S')})은 주말입니다."
                )
            logger.info(f"[{function_name}] 함수 실행 완료 (주말로 인한 건너뜀)")
            return
        
        # 미국 주식 시장은 평일(월-금) 9:30 AM - 4:00 PM ET
        is_weekday = 0 <= ny_weekday <= 4  # 월요일에서 금요일까지
        is_market_open_time = (
            (ny_hour == 9 and ny_minute >= 30) or
            (10 <= ny_hour < 16) or
            (ny_hour == 16 and ny_minute == 0)
        )
        
        is_market_hours = is_weekday and is_market_open_time
        
        if not is_market_hours:
            # 주말이거나 장 시간이 아닌 경우
            logger.info(f"[{function_name}] 현재 시간 (한국: {now_in_korea.strftime('%Y-%m-%d %H:%M:%S')}, 뉴욕: {now_in_ny.strftime('%Y-%m-%d %H:%M:%S')})은 미국 장 시간이 아닙니다. 매수 작업을 건너뜁니다.")
            if send_slack_notification:
                slack_notifier.send_no_buy_notification(
                    reason="장 시간 아님",
                    details=f"현재 시간 (한국: {now_in_korea.strftime('%Y-%m-%d %H:%M:%S')}, 뉴욕: {now_in_ny.strftime('%Y-%m-%d %H:%M:%S')})은 미국 장 시간이 아닙니다.\n미국 주식 시장은 평일 9:30 AM - 4:00 PM ET입니다."
                )
            logger.info(f"[{function_name}] 함수 실행 완료 (장 시간 아님)")
            return
        
        logger.info(f"[{function_name}] 미국 장 시간 확인: {now_in_korea.strftime('%Y-%m-%d %H:%M:%S')} (뉴욕: {now_in_ny.strftime('%Y-%m-%d %H:%M:%S')})")
        
        # 보유 종목 및 잔고 조회
        try:
            # 1. 모든 거래소의 보유 종목 조회
            balance_result = get_all_overseas_balances()
            if balance_result.get("rt_cd") != "0":
                logger.error(f"[{function_name}] 보유 종목 조회 실패: {balance_result.get('msg1', '알 수 없는 오류')}")
                if send_slack_notification:
                    slack_notifier.send_no_buy_notification(
                        reason="보유 종목 조회 실패",
                        details=balance_result.get('msg1', '알 수 없는 오류')
                    )
                logger.info(f"[{function_name}] 함수 실행 완료 (보유 종목 조회 실패)")
                return
            
            # 보유 종목 티커 추출 및 보유 수량 저장 (체결 확인용)
            holdings = balance_result.get("output1", [])
            holding_tickers = set()
            holding_quantities = {}  # ticker -> quantity (체결 확인용)
            holding_values = {}  # ticker -> current_value (포트폴리오 비중 계산용)
            portfolio_total_value = 0.0  # 포트폴리오 총 가치
            
            for item in holdings:
                ticker = item.get("ovrs_pdno")
                if ticker:
                    holding_tickers.add(ticker)
                    quantity = int(item.get("ovrs_cblc_qty", 0))
                    holding_quantities[ticker] = quantity
                    
                    # 평가 금액 계산 (포트폴리오 비중 계산용)
                    try:
                        current_price = float(item.get("now_pric2", "0") or "0")
                        if current_price > 0 and quantity > 0:
                            current_value = quantity * current_price
                            holding_values[ticker] = current_value
                            portfolio_total_value += current_value
                    except (ValueError, TypeError):
                        # 가격 정보가 없거나 변환 실패 시 0으로 처리
                        holding_values[ticker] = 0.0
            
            logger.info(f"[{function_name}] 현재 보유 중인 종목 수: {len(holding_tickers)}")
            logger.info(f"[{function_name}] 📊 포트폴리오 총 가치: ${portfolio_total_value:,.2f}")
            
            # 2. 주문가능금액 조회 - TTTS3007R API 사용
            order_psbl_result = get_overseas_order_possible_amount("NASD", "AAPL")
            available_cash = 0.0
            
            if order_psbl_result.get("rt_cd") == "0":
                output = order_psbl_result.get("output", {})
                
                if output:
                    # ord_psbl_frcr_amt: 주문가능외화금액
                    # ovrs_ord_psbl_amt: 해외주문가능금액
                    cash_str = output.get("ord_psbl_frcr_amt") or output.get("ovrs_ord_psbl_amt") or "0"
                    available_cash = float(cash_str)
                    logger.info(f"[{function_name}] 💰 구매 가능 금액: ${available_cash:,.2f}")
                else:
                    logger.warning(f"[{function_name}] ⚠️ 주문가능금액 조회 실패: output이 비어있습니다.")
                    if send_slack_notification:
                        slack_notifier.send_no_buy_notification(
                            reason="주문가능금액 조회 실패",
                            details="주문가능금액 조회 결과가 비어있습니다."
                        )
                    logger.info(f"[{function_name}] 함수 실행 완료 (주문가능금액 조회 실패)")
                    return
            else:
                logger.error(f"[{function_name}] 주문가능금액 조회 실패: {order_psbl_result.get('msg1', '알 수 없는 오류')}")
                if send_slack_notification:
                    slack_notifier.send_no_buy_notification(
                        reason="주문가능금액 조회 실패",
                        details=order_psbl_result.get('msg1', '알 수 없는 오류')
                    )
                logger.info(f"[{function_name}] 함수 실행 완료 (주문가능금액 조회 실패)")
                return
                
        except Exception as e:
            logger.error(f"[{function_name}] 보유 종목 및 잔고 조회 중 오류 발생: {str(e)}", exc_info=True)
            if send_slack_notification:
                slack_notifier.send_no_buy_notification(
                    reason="보유 종목 및 잔고 조회 오류",
                    details=str(e)
                )
            logger.info(f"[{function_name}] 함수 실행 완료 (오류)")
            return
            
        # StockRecommendationService에서 이미 필터링된 매수 대상 종목 가져오기
        # 매수 작업에서는 분석 완료 Slack 알림이 불필요하므로 send_slack_notification=False로 설정
        recommendations = self.recommendation_service.get_combined_recommendations_with_technical_and_sentiment(
            send_slack_notification=False
        )
        
        if not recommendations or not recommendations.get("results"):
            logger.info(f"[{function_name}] 매수 대상 종목이 없습니다.")
            if send_slack_notification:
                slack_notifier.send_no_buy_notification(
                    reason="매수 대상 종목 없음",
                    details="통합 분석 결과 매수 조건을 만족하는 종목이 없습니다."
                )
            logger.info(f"[{function_name}] 함수 실행 완료")
            return
        
        raw_candidates = recommendations.get("results", [])
        logger.info(f"[{function_name}] 추천 종목 수 (중복 제거 전): {len(raw_candidates)}개")
        
        # MongoDB에서 사용자 정보 조회 (레버리지 설정 확인용) - 필터링을 위해 먼저 조회
        user_leverage_map = {}  # ticker -> use_leverage (leverage_ticker는 stocks 컬렉션에서 조회)
        db = None
        try:
            from app.infrastructure.database.mongodb_client import get_mongodb_database
            db = get_mongodb_database()
            
            if db is not None:
                # 사용자 정보 조회 (user_id는 설정에서 가져오거나 기본값 사용)
                user_id = getattr(settings, 'USER_ID', 'lian')  # 기본값 'lian'
                user = db.users.find_one({"user_id": user_id})
                
                if user and user.get("stocks"):
                    for stock in user.get("stocks", []):
                        ticker = stock.get("ticker")
                        use_leverage = stock.get("use_leverage", False)
                        
                        if ticker:
                            user_leverage_map[ticker] = {
                                "use_leverage": use_leverage
                                # leverage_ticker는 stocks 컬렉션에서 조회
                            }
                    
                    logger.info(f"[{function_name}] 사용자 '{user_id}'의 레버리지 설정 로드 완료: {len(user_leverage_map)}개 종목")
                else:
                    logger.warning(f"[{function_name}] 사용자 '{user_id}' 정보를 찾을 수 없거나 종목 정보가 없습니다.")
            else:
                logger.warning(f"[{function_name}] MongoDB 연결 실패 - 레버리지 설정을 사용할 수 없습니다.")
        except Exception as e:
            logger.error(f"[{function_name}] 사용자 레버리지 설정 조회 중 오류: {str(e)}", exc_info=True)
        
        # 중복 제거 및 use_leverage 필터링
        buy_candidates = []
        seen_tickers = set()
        
        for candidate in raw_candidates:
            ticker = candidate.get("ticker")
            stock_name = candidate.get("stock_name", "N/A")
            
            if not ticker:
                logger.warning(f"[{function_name}] 티커가 없는 추천 종목 발견 및 제외: {stock_name}")
                continue
            
            # 중복 제거
            if ticker in seen_tickers:
                logger.warning(f"[{function_name}] 중복된 티커 발견 및 제외: {stock_name} ({ticker})")
                continue
            seen_tickers.add(ticker)
            
            # use_leverage 필터링: use_leverage가 true인 종목만 매수
            if ticker not in user_leverage_map:
                # 사용자 설정에 없는 종목은 매수하지 않음
                logger.info(f"[{function_name}] {stock_name}({ticker}) - 사용자 설정에 없어 매수 제외")
                continue
            
            if not user_leverage_map[ticker]["use_leverage"]:
                # use_leverage가 false인 종목은 매수하지 않음
                logger.info(f"[{function_name}] {stock_name}({ticker}) - use_leverage가 false여서 매수 제외")
                continue
            
            buy_candidates.append(candidate)
        
        logger.info(f"[{function_name}] 매수 후보 종목 수 (중복 제거 및 use_leverage 필터링 후): {len(buy_candidates)}개")
        
        if not buy_candidates:
            logger.info(f"[{function_name}] 매수 조건을 만족하는 종목이 없습니다.")
            if send_slack_notification:
                slack_notifier.send_no_buy_notification(
                    reason="매수 조건 불만족",
                    details="매수 조건을 만족하는 종목이 없습니다."
                )
            logger.info(f"[{function_name}] 함수 실행 완료")
            return
        
        
        logger.info(f"[{function_name}] 매수 대상 종목 {len(buy_candidates)}개를 찾았습니다. (종합 점수 높은 순)")
        
        # 자동매매 설정 조회 (보유 중인 종목 매수 허용 여부 확인)
        trading_config = self.auto_trading_service.get_auto_trading_config()
        allow_buy_existing_stocks = trading_config.get("allow_buy_existing_stocks", True)  # 기본값: True
        max_portfolio_weight = trading_config.get("max_portfolio_weight_per_stock", 20.0)  # 기본값: 20%
        logger.info(f"[{function_name}] 보유 중인 종목 매수 허용: {allow_buy_existing_stocks}")
        logger.info(f"[{function_name}] 단일 종목 최대 투자 비중: {max_portfolio_weight}%")
        
        # 성공한 매수 건수 추적
        successful_purchases = 0
        skipped_no_cash = 0
        skipped_already_holding = 0
        skipped_price_fetch_failed = 0
        skipped_invalid_price = 0
        skipped_portfolio_weight = 0  # 포트폴리오 비중 초과로 스킵된 건수
        failed_orders = 0
        
        # 체결 확인 태스크 추적 (요약 로그 출력 전 모든 체결 확인 완료 대기용)
        execution_tasks = []
        
        # 각 종목에 대해 API 호출하여 현재 체결가 조회 및 매수 주문
        # buy_candidates는 이미 composite_score 순으로 정렬되어 있음
        for candidate in buy_candidates:
            try:
                ticker = candidate["ticker"]
                stock_name = candidate["stock_name"]
                
                # 사용자의 레버리지 설정 확인 (leverage_ticker는 stocks 컬렉션에서 조회)
                actual_ticker = ticker  # 기본값은 원래 티커
                if ticker in user_leverage_map and user_leverage_map[ticker]["use_leverage"]:
                    # stocks 컬렉션에서 레버리지 티커 조회
                    stock_doc = db.stocks.find_one({"ticker": ticker})
                    if stock_doc and stock_doc.get("leverage_ticker"):
                        actual_ticker = stock_doc["leverage_ticker"]
                        logger.info(f"[{function_name}] {stock_name}({ticker}) - 레버리지 활성화, {actual_ticker}로 매수")
                    else:
                        logger.warning(f"[{function_name}] {stock_name}({ticker}) - 레버리지 설정 활성화되었으나 leverage_ticker가 없음, 일반 티커로 매수")
                else:
                    logger.info(f"[{function_name}] {stock_name}({ticker}) - 일반 티커로 매수")                
                # 거래소 코드 결정 (미국 주식 기준)
                if actual_ticker.endswith(".X") or actual_ticker.endswith(".N"):
                    # 거래소 구분이 티커에 포함된 경우
                    exchange_code = "NYSE" if actual_ticker.endswith(".N") else "NASD"
                    pure_ticker = actual_ticker.split(".")[0]
                else:
                    # 기본값 NASDAQ으로 설정
                    exchange_code = "NASD"
                    pure_ticker = actual_ticker
                
                # 이미 보유 중인 종목인지 확인 (옵션에 따라)
                if not allow_buy_existing_stocks and pure_ticker in holding_tickers:
                    logger.info(f"[{function_name}] ⏭️ {stock_name}({ticker}) - 이미 보유 중인 종목이므로 매수하지 않습니다. (allow_buy_existing_stocks=false)")
                    skipped_already_holding += 1
                    continue
                elif allow_buy_existing_stocks and pure_ticker in holding_tickers:
                    logger.info(f"[{function_name}] ℹ️ {stock_name}({ticker}) - 이미 보유 중이지만 매수 허용 옵션이 활성화되어 있어 매수합니다.")
                
                # 거래소 코드 변환 (API 요청에 맞게 변환)
                api_exchange_code = "NAS"
                if exchange_code == "NYSE":
                    api_exchange_code = "NYS"
                
                # 현재가 조회
                price_params = {
                    "AUTH": "",
                    "EXCD": api_exchange_code,  # 변환된 거래소 코드 사용
                    "SYMB": pure_ticker
                }
                
                price_result = get_current_price(price_params)
                
                if price_result.get("rt_cd") != "0":
                    error_msg = price_result.get('msg1', '알 수 없는 오류')
                    logger.error(f"[{function_name}] ⏭️ {stock_name}({ticker}) 현재가 조회 실패: {error_msg}")
                    skipped_price_fetch_failed += 1
                    continue
                
                # 현재가 추출
                last_price = price_result.get("output", {}).get("last", 0) or 0
                try:
                    current_price = float(last_price)
                except (ValueError, TypeError) as e:
                    logger.error(f"[{function_name}] ⏭️ {stock_name}({ticker}) 현재가 변환 실패: {last_price}, 오류: {str(e)}")
                    skipped_invalid_price += 1
                    continue
                
                if current_price <= 0:
                    logger.error(f"[{function_name}] ⏭️ {stock_name}({ticker}) 현재가가 유효하지 않습니다: {current_price}")
                    skipped_invalid_price += 1
                    continue
                
                # 포트폴리오 비중 체크
                current_holding_value = holding_values.get(pure_ticker, 0.0)
                current_weight = (current_holding_value / portfolio_total_value * 100) if portfolio_total_value > 0 else 0.0
                
                # 매수 예정 금액 (1주 기준)
                buy_amount = current_price
                new_total_value = portfolio_total_value + buy_amount
                new_holding_value = current_holding_value + buy_amount
                new_weight = (new_holding_value / new_total_value * 100) if new_total_value > 0 else 0.0
                
                # 최대 비중 초과 체크
                if new_weight > max_portfolio_weight:
                    # 현재 보유 비중이 이미 최대 비중을 초과하는 경우
                    if current_weight >= max_portfolio_weight:
                        logger.warning(f"[{function_name}] ⏭️ {stock_name}({ticker}) - 현재 보유 비중({current_weight:.2f}%)이 이미 최대 비중({max_portfolio_weight}%)을 초과하여 매수하지 않습니다.")
                        skipped_portfolio_weight += 1
                        continue
                    else:
                        # 최대 비중을 초과하지 않도록 매수 금액 조정
                        max_allowed_value = (new_total_value * max_portfolio_weight / 100) - current_holding_value
                        if max_allowed_value <= 0:
                            logger.warning(f"[{function_name}] ⏭️ {stock_name}({ticker}) - 최대 비중 제한으로 인해 추가 매수 불가. 현재 비중: {current_weight:.2f}%, 최대 비중: {max_portfolio_weight}%")
                            skipped_portfolio_weight += 1
                            continue
                        
                        # 조정된 매수 금액으로 수량 재계산
                        adjusted_quantity = max(1, int(max_allowed_value / current_price))
                        buy_amount = adjusted_quantity * current_price
                        new_holding_value = current_holding_value + buy_amount
                        new_total_value = portfolio_total_value + buy_amount
                        new_weight = (new_holding_value / new_total_value * 100) if new_total_value > 0 else 0.0
                        
                        logger.info(f"[{function_name}] ⚖️ {stock_name}({ticker}) - 포트폴리오 비중 제한 적용: 최대 비중({max_portfolio_weight}%)을 초과하지 않도록 매수 금액 조정")
                        logger.info(f"[{function_name}]    현재 비중: {current_weight:.2f}% → 예상 비중: {new_weight:.2f}% (매수 금액: ${buy_amount:.2f})")
                
                # 매수 가능 여부 확인 (조정된 금액 기준)
                if available_cash < buy_amount:
                    logger.warning(f"[{function_name}] ⏭️ {stock_name}({ticker}) - 잔고 부족으로 매수 건너뜀. 필요금액: ${buy_amount:.2f}, 잔고: ${available_cash:.2f}")
                    skipped_no_cash += 1
                    continue
                
                # 매수 수량 계산
                quantity = max(1, int(buy_amount / current_price))
                
                # 가격을 소수점 2자리로 반올림 (API 요구사항)
                rounded_price = round(current_price, 2)
                
                # 매수 주문 실행
                order_data = {
                    "CANO": settings.KIS_CANO,
                    "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
                    "OVRS_EXCG_CD": exchange_code,  # API 문서에 따라 원래대로 exchange_code 사용
                    "PDNO": pure_ticker,
                    "ORD_DVSN": "00",  # 지정가
                    "ORD_QTY": str(quantity),
                    "OVRS_ORD_UNPR": str(rounded_price),
                    "is_buy": True,
                    "stock_name": stock_name  # 종목명 추가
                }
                
                logger.info(f"[{function_name}] 📤 {stock_name}({actual_ticker}) 매수 주문 실행: 수량 {quantity}주, 가격 ${current_price:.2f} (지정가)")
                order_result = order_overseas_stock(order_data)
                
                # 주문 결과 상세 정보 추출
                order_output = order_result.get("output", {})
                order_no = order_output.get("ODNO", "N/A")  # 주문번호
                order_gno_brno = order_output.get("KRX_FWDG_ORD_ORGNO", "")  # 주문점번호
                order_tmd = order_output.get("ORD_TMD", "")  # 주문시각
                order_msg = order_result.get('msg1', '주문이 접수되었습니다.')

                # 주문일자 (오늘 날짜, YYYYMMDD 형식)
                order_dt = datetime.now().strftime("%Y%m%d")

                if order_result.get("rt_cd") == "0":
                    logger.info(f"[{function_name}] ✅ {stock_name}({ticker}) 매수 주문 접수 성공: {order_msg}")
                    logger.info(f"[{function_name}]    주문번호: {order_no}, 가격: ${current_price:.2f}, 수량: {quantity}주")

                    # 주문 접수 성공 시 즉시 저장 (status: "accepted")
                    save_success = self._save_trading_log(
                        order_type="buy",
                        ticker=ticker,  # 원본 티커 (표시용)
                        stock_name=stock_name,
                        price=current_price,
                        quantity=quantity,
                        status=OrderStatus.ACCEPTED.value,  # 주문 접수 상태
                        composite_score=candidate.get("composite_score"),
                        order_result=order_result,
                        exchange_code=exchange_code,
                        order_no=order_no if order_no and order_no != "N/A" else None,
                        order_ticker=pure_ticker,  # 실제 주문에 사용된 티커 (체결 조회용)
                        order_dt=order_dt,  # 주문일자 (체결 조회용)
                        order_gno_brno=order_gno_brno if order_gno_brno else None,  # 주문점번호 (체결 조회용)
                        order_tmd=order_tmd if order_tmd else None  # 주문시각
                    )
                    
                    if save_success:
                        logger.info(f"[{function_name}] 📝 {stock_name}({ticker}) 주문 접수 기록 저장 완료")
                        
                        # 주문번호가 유효한 경우 체결 확인 (백그라운드)
                        if order_no and order_no != "N/A":
                            logger.info(f"[{function_name}]    ⏳ 체결 여부 확인 중... (5초 후 확인)")
                            
                            # 비동기로 체결 확인 (다음 종목 매수를 막지 않음)
                            # 주문 접수 전 보유 수량 전달 (체결 확인용)
                            before_quantity = holding_quantities.get(pure_ticker, 0)
                            task = asyncio.create_task(self._check_and_update_execution(
                                order_no=order_no,
                                ticker=ticker,
                                stock_name=stock_name,
                                function_name=function_name,
                                before_quantity=before_quantity,
                                order_quantity=quantity
                            ))
                            execution_tasks.append(task)
                        else:
                            logger.warning(f"[{function_name}] ⚠️ 주문번호를 확인할 수 없어 체결 확인을 건너뜁니다.")
                    else:
                        logger.error(f"[{function_name}] ❌ {stock_name}({ticker}) 주문 접수 기록 저장 실패")
                    
                    # 주문 접수 성공으로 카운트 (체결은 별도로 확인)
                    successful_purchases += 1
                    
                    # 포트폴리오 총 가치 업데이트 (다음 종목 비중 계산을 위해)
                    actual_buy_amount = quantity * current_price
                    portfolio_total_value += actual_buy_amount
                    holding_values[pure_ticker] = holding_values.get(pure_ticker, 0.0) + actual_buy_amount
                else:
                    error_msg = order_result.get('msg1', '알 수 없는 오류')
                    error_code = order_result.get('msg_cd', 'N/A')
                    logger.error(f"[{function_name}] ❌ {stock_name}({ticker}) 매수 주문 실패: {error_msg} (오류코드: {error_code})")
                    
                    # 주문 실패 시 Slack 알림 전송
                    slack_notifier.send_buy_notification(
                        stock_name=stock_name,
                        ticker=ticker,
                        quantity=quantity,
                        price=current_price,
                        exchange_code=exchange_code,
                        success=False,
                        error_message=f"{error_msg} (오류코드: {error_code})"
                    )
                    logger.info(f"[{function_name}] 📨 {stock_name}({ticker}) 주문 실패 Slack 알림 전송 완료")
                    
                    failed_orders += 1
                
                # 요청 간 지연 (API 요청 제한 방지 및 다음 종목 조회 전 텀 확보)
                await asyncio.sleep(3)
                
            except Exception as e:
                logger.error(f"[{function_name}] ❌ {candidate['stock_name']}({candidate['ticker']}) 매수 처리 중 오류: {str(e)}", exc_info=True)
                failed_orders += 1
        
        # 체결 확인 태스크들이 모두 완료될 때까지 대기
        if execution_tasks:
            logger.info(f"[{function_name}] ⏳ 체결 확인 완료를 기다리는 중... (최대 60초, {len(execution_tasks)}개 주문)")
            try:
                # 모든 체결 확인 태스크가 완료될 때까지 대기
                await asyncio.wait_for(
                    asyncio.gather(*execution_tasks, return_exceptions=True),
                    timeout=SchedulerConfig.EXECUTION_CHECK_TIMEOUT_SECONDS
                )
                logger.info(f"[{function_name}] ✅ 모든 체결 확인 완료")
            except asyncio.TimeoutError:
                logger.warning(f"[{function_name}] ⚠️ 체결 확인 대기 시간 초과 ({SchedulerConfig.EXECUTION_CHECK_TIMEOUT_SECONDS}초), 일부 체결 확인이 완료되지 않았을 수 있습니다.")
        
        # 체결 완료된 종목 수 확인
        executed_count = 0
        if execution_tasks:
            try:
                db = get_db()
                if db is not None:
                    # 최근 5분 이내에 체결 완료된 매수 주문 수 확인
                    five_minutes_ago = datetime.now() - timedelta(minutes=5)
                    executed_count = db.trading_logs.count_documents({
                        "order_type": "buy",
                        "status": "executed",
                        "created_at": {"$gte": five_minutes_ago}
                    })
            except Exception as e:
                logger.warning(f"[{function_name}] 체결 완료 종목 수 확인 중 오류: {str(e)}")
        
        # 매수 작업 요약 정보 로깅 (체결 확인 완료 후)
        total_candidates = len(buy_candidates)
        logger.info("=" * 80)
        logger.info(f"[{function_name}] 📊 매수 작업 요약")
        logger.info(f"  총 추천 종목: {total_candidates}개")
        logger.info(f"  ✅ 주문 접수 성공: {successful_purchases}개")
        if executed_count > 0:
            logger.info(f"  ✅ 체결 완료: {executed_count}개")
        logger.info(f"  ❌ 주문 실패: {failed_orders}개")
        logger.info(f"  ⏭️  건너뛴 종목: {total_candidates - successful_purchases - failed_orders}개")
        logger.info(f"    - 이미 보유 중: {skipped_already_holding}개")
        logger.info(f"    - 현재가 조회 실패: {skipped_price_fetch_failed}개")
        logger.info(f"    - 유효하지 않은 가격: {skipped_invalid_price}개")
        logger.info(f"    - 잔고 부족: {skipped_no_cash}개")
        logger.info(f"    - 포트폴리오 비중 초과: {skipped_portfolio_weight}개")
        logger.info(f"  💰 남은 잔고: ${available_cash:,.2f}")
        logger.info("=" * 80)
        
        # Slack 알림 전송 (요약 정보)
        if send_slack_notification:
            summary_msg = f"📊 *매수 작업 완료*\n"
            summary_msg += f"• 총 추천 종목: {total_candidates}개\n"
            summary_msg += f"• 주문 접수 성공: {successful_purchases}개\n"
            if executed_count > 0:
                summary_msg += f"• 체결 완료: {executed_count}개\n"
            if failed_orders > 0:
                summary_msg += f"• 주문 실패: {failed_orders}개\n"
            if skipped_already_holding > 0 or skipped_price_fetch_failed > 0 or skipped_invalid_price > 0 or skipped_no_cash > 0 or skipped_portfolio_weight > 0:
                summary_msg += f"• 건너뛴 종목: {total_candidates - successful_purchases - failed_orders}개\n"
                if skipped_already_holding > 0:
                    summary_msg += f"  - 이미 보유 중: {skipped_already_holding}개\n"
                if skipped_price_fetch_failed > 0:
                    summary_msg += f"  - 현재가 조회 실패: {skipped_price_fetch_failed}개\n"
                if skipped_invalid_price > 0:
                    summary_msg += f"  - 유효하지 않은 가격: {skipped_invalid_price}개\n"
                if skipped_no_cash > 0:
                    summary_msg += f"  - 잔고 부족: {skipped_no_cash}개\n"
                if skipped_portfolio_weight > 0:
                    summary_msg += f"  - 포트폴리오 비중 초과: {skipped_portfolio_weight}개\n"
            summary_msg += f"• 남은 잔고: ${available_cash:,.2f}"
            send_scheduler_slack_notification(summary_msg)
    
    async def _check_and_update_execution(
        self,
        order_no: str,
        ticker: str,
        stock_name: str,
        function_name: str = "_execute_auto_buy",
        before_quantity: int = 0,
        order_quantity: int = 0
    ):
        """
        주문 체결 여부를 확인하고, 상태를 업데이트
        
        Args:
            order_no: 주문번호
            ticker: 티커 심볼
            stock_name: 종목명
            function_name: 함수명 (로깅용)
            before_quantity: 주문 접수 전 보유 수량
            order_quantity: 주문 수량
        """
        try:
            # 체결 확인 대기 (주문 접수 후 체결까지 시간 필요)
            await asyncio.sleep(SchedulerConfig.EXECUTION_CHECK_DELAY_SECONDS)
            
            logger.info(f"[{function_name}] 🔍 {stock_name}({ticker}) 주문번호 {order_no} 체결 여부 확인 중...")
            
            # 주문번호로 저장된 기록 찾기
            db = get_db()
            if db is None:
                logger.error(f"[{function_name}] ❌ MongoDB 연결 실패 - 체결 상태 업데이트 불가")
                return
            
            # 주문번호로 기록 찾기 (최근 것부터) - 매수/매도 모두 처리
            log_record = db.trading_logs.find_one(
                {
                    "order_no": order_no,
                    "ticker": ticker
                },
                sort=[("created_at", -1)]
            )
            
            # order_type 확인
            order_type = log_record.get("order_type", "buy") if log_record else "buy"
            
            if not log_record:
                logger.warning(f"[{function_name}] ⚠️ 주문번호 {order_no}에 해당하는 기록을 찾을 수 없습니다.")
                return
            
            # 거래소 코드 및 주문 정보 가져오기
            exchange_code = log_record.get("exchange_code", "NASD")
            order_ticker = log_record.get("order_ticker", ticker)  # 실제 주문에 사용된 티커
            order_dt = log_record.get("order_dt")  # 주문일자
            order_gno_brno = log_record.get("order_gno_brno")  # 주문점번호

            # 체결 여부 확인 (order_ticker 사용)
            execution_result = check_order_execution(
                order_no=order_no,
                exchange_code=exchange_code,
                ticker=order_ticker,  # 실제 주문 티커로 조회
                max_retries=3,
                retry_delay=5,
                order_dt=order_dt,  # 저장된 주문일자 사용
                order_gno_brno=order_gno_brno  # 저장된 주문점번호 사용
            )
            
            if execution_result is None:
                logger.warning(f"[{function_name}] ⚠️ {stock_name}({ticker}) 주문번호 {order_no} 체결 확인 실패 (주문 조회 불가)")
                logger.info(f"[{function_name}] 🔄 잔고 조회로 체결 여부 확인 시도...")
                
                # Fallback: 잔고 조회로 체결 여부 확인
                try:
                    # 주문 접수 전 보유 수량 확인 (이미 알고 있는 값 사용)
                    # 주문 접수 후 일정 시간(10초) 대기 후 잔고 확인
                    await asyncio.sleep(10)
                    
                    balance_result = get_all_overseas_balances()
                    if balance_result.get("rt_cd") == "0":
                        holdings = balance_result.get("output1", [])
                        for item in holdings:
                            if item.get("ovrs_pdno") == order_ticker:  # 실제 주문 티커로 잔고 확인
                                # 해당 종목을 보유하고 있으면 체결된 것으로 간주
                                # 현재 보유 수량
                                current_qty = int(item.get("ovrs_cblc_qty", 0))
                                
                                # 주문 접수 전 보유 수량과 비교하여 증가했는지 확인
                                if current_qty > before_quantity:
                                    # 보유 수량이 증가했으면 체결된 것으로 간주
                                    executed_qty = current_qty - before_quantity
                                    logger.info(f"[{function_name}] ✅ {stock_name}({ticker}) 잔고 조회로 체결 확인: 보유 수량 증가 ({before_quantity}주 → {current_qty}주, 체결: {executed_qty}주)")
                                    
                                    # 상태 업데이트 (executed) - 잔고 조회로 확인한 경우
                                    update_result = db.trading_logs.update_one(
                                        {"_id": log_record["_id"]},
                                        {
                                            "$set": {
                                                "status": "executed",
                                                "quantity": executed_qty,
                                                "executed_at": datetime.now(),
                                                "execution_check_method": "balance_check",  # 체결 확인 방법 기록
                                                "execution_result": {
                                                    "method": "balance_check",
                                                    "before_quantity": before_quantity,
                                                    "current_quantity": current_qty,
                                                    "executed_quantity": executed_qty
                                                }
                                            }
                                        }
                                    )
                                    
                                    if update_result.modified_count > 0:
                                        logger.info(f"[{function_name}] ✅ {stock_name}({ticker}) 체결 상태 업데이트 완료 (잔고 조회)")
                                        
                                        # 트레일링 스톱 초기화 (체결 완료 시)
                                        self._initialize_trailing_stop_after_buy(
                                            ticker=order_ticker,  # 실제 주문 티커 사용
                                            stock_name=stock_name,
                                            purchase_price=log_record.get("price", 0),
                                            function_name=function_name
                                        )
                                        
                                        # 부분 익절 히스토리 초기화 (체결 완료 시)
                                        self._initialize_partial_profit_history_after_buy(
                                            ticker=order_ticker,  # 실제 주문 티커 사용
                                            stock_name=stock_name,
                                            purchase_price=log_record.get("price", 0),
                                            initial_quantity=current_qty,  # 체결 후 현재 보유 수량
                                            function_name=function_name
                                        )
                                        
                                        # Slack 알림 전송 (체결 완료)
                                        slack_notifier.send_buy_notification(
                                            stock_name=stock_name,
                                            ticker=ticker,
                                            quantity=executed_qty,
                                            price=log_record.get("price", 0),
                                            exchange_code=exchange_code,
                                            success=True
                                        )
                                        logger.info(f"[{function_name}] 📨 {stock_name}({ticker}) 체결 완료 Slack 알림 전송 완료")
                                        return
                                elif current_qty == before_quantity and current_qty > 0:
                                    # 보유 수량이 같지만 이미 보유 중이었던 경우 (추가 매수)
                                    # 주문 수량만큼 체결된 것으로 간주
                                    logger.info(f"[{function_name}] ✅ {stock_name}({ticker}) 잔고 조회로 체결 확인: 이미 보유 중이었으나 추가 매수로 간주 (체결: {order_quantity}주)")
                                    
                                    # 상태 업데이트 (executed) - 잔고 조회로 확인한 경우 (추가 매수로 간주)
                                    update_result = db.trading_logs.update_one(
                                        {"_id": log_record["_id"]},
                                        {
                                            "$set": {
                                                "status": "executed",
                                                "quantity": order_quantity,
                                                "executed_at": datetime.now(),
                                                "execution_check_method": "balance_check_assumed",  # 체결 확인 방법 기록
                                                "execution_result": {
                                                    "method": "balance_check_assumed",
                                                    "before_quantity": before_quantity,
                                                    "current_quantity": current_qty,
                                                    "executed_quantity": order_quantity,
                                                    "note": "이미 보유 중이었으나 추가 매수로 간주"
                                                }
                                            }
                                        }
                                    )
                                    
                                    if update_result.modified_count > 0:
                                        logger.info(f"[{function_name}] ✅ {stock_name}({ticker}) 체결 상태 업데이트 완료 (잔고 조회, 추가 매수로 간주)")
                                        
                                        # 트레일링 스톱 초기화 (체결 완료 시)
                                        self._initialize_trailing_stop_after_buy(
                                            ticker=order_ticker,  # 실제 주문 티커 사용
                                            stock_name=stock_name,
                                            purchase_price=log_record.get("price", 0),
                                            function_name=function_name
                                        )
                                        
                                        # 부분 익절 히스토리 초기화 (체결 완료 시)
                                        self._initialize_partial_profit_history_after_buy(
                                            ticker=order_ticker,  # 실제 주문 티커 사용
                                            stock_name=stock_name,
                                            purchase_price=log_record.get("price", 0),
                                            initial_quantity=current_qty,  # 체결 후 현재 보유 수량
                                            function_name=function_name
                                        )
                                        
                                        # Slack 알림 전송 (체결 완료)
                                        slack_notifier.send_buy_notification(
                                            stock_name=stock_name,
                                            ticker=ticker,
                                            quantity=order_quantity,
                                            price=log_record.get("price", 0),
                                            exchange_code=exchange_code,
                                            success=True
                                        )
                                        logger.info(f"[{function_name}] 📨 {stock_name}({ticker}) 체결 완료 Slack 알림 전송 완료")
                                        return
                    
                    # 잔고에 없거나 증가하지 않았으면 미체결로 간주
                    logger.warning(f"[{function_name}] ⏳ {stock_name}({ticker}) 잔고에 변화가 없어 미체결로 간주 (이전: {before_quantity}주)")
                    
                except Exception as e:
                    logger.error(f"[{function_name}] ❌ 잔고 조회 중 오류: {str(e)}")
                
                # 체결 확인 실패 시 상태는 "accepted"로 유지하고 실패 알림 전송
                slack_notifier.send_buy_notification(
                    stock_name=stock_name,
                    ticker=ticker,
                    quantity=log_record.get("quantity", 0),
                    price=log_record.get("price", 0),
                    exchange_code=exchange_code,
                    success=False,
                    error_message="체결 확인 실패 (주문 조회 불가, 잔고 확인도 실패)"
                )
                logger.info(f"[{function_name}] 📨 {stock_name}({ticker}) 체결 확인 실패 Slack 알림 전송 완료")
                return
            
            if execution_result.get("executed"):
                # 체결 성공
                executed_qty = execution_result.get("executed_qty", log_record.get("quantity", 0))
                executed_price = execution_result.get("executed_price", log_record.get("price", 0))
                execution_order_detail = execution_result.get("order", {})  # 주문체결내역 상세 정보
                
                if order_type == "sell":
                    logger.info(f"[{function_name}] ✅ {stock_name}({ticker}) 매도 체결 완료!")
                else:
                    logger.info(f"[{function_name}] ✅ {stock_name}({ticker}) 매수 체결 완료!")
                logger.info(f"[{function_name}]    체결 수량: {executed_qty}주, 체결 가격: ${executed_price:.2f}")
                
                # 상태 업데이트 (executed) - 주문체결내역 상세 정보도 함께 저장
                update_data = {
                    "status": "executed",
                    "price": executed_price,
                    "quantity": executed_qty,
                    "executed_at": datetime.now(),
                    "execution_result": execution_order_detail,  # 주문체결내역 상세 정보 저장
                    "execution_check_method": "order_detail_api"  # 체결 확인 방법 기록
                }
                
                update_result = db.trading_logs.update_one(
                    {"_id": log_record["_id"]},
                    {"$set": update_data}
                )
                
                if update_result.modified_count > 0:
                    logger.info(f"[{function_name}] ✅ {stock_name}({ticker}) 체결 상태 업데이트 완료")
                    
                    # 매도 체결 시 종목별 실현 수익률 업데이트
                    if order_type == "sell":
                        try:
                            from app.utils.user_context import get_current_user_id
                            user_id = log_record.get("user_id") or get_current_user_id()
                            update_result_profit = update_ticker_realized_profit(user_id=user_id, ticker=ticker)
                            if update_result_profit.get("success"):
                                profit_percent = update_result_profit.get("realized_profit_percent", 0.0)
                                logger.info(f"[{function_name}] ✅ {stock_name}({ticker}) 종목별 실현 수익률 업데이트 완료: {profit_percent:.2f}%")
                            else:
                                logger.warning(f"[{function_name}] ⚠️ {stock_name}({ticker}) 종목별 실현 수익률 업데이트 실패: {update_result_profit.get('error', '알 수 없는 오류')}")
                        except Exception as e:
                            logger.error(f"[{function_name}] ❌ 종목별 실현 수익률 업데이트 중 오류: {str(e)}")
                    else:
                        # 매수 체결 시 트레일링 스톱 초기화
                        self._initialize_trailing_stop_after_buy(
                            ticker=order_ticker,  # 실제 주문 티커 사용
                            stock_name=stock_name,
                            purchase_price=executed_price,
                            function_name=function_name
                        )
                        
                        # 부분 익절 히스토리 초기화 (매수 체결 시)
                        # 현재 보유 수량 조회
                        try:
                            from app.services.balance_service import get_overseas_balance
                            balance_result = get_overseas_balance()
                            current_qty = executed_qty  # 기본값은 체결 수량
                            
                            if balance_result.get("rt_cd") == "0":
                                holdings = balance_result.get("output1", [])
                                for item in holdings:
                                    if item.get("ovrs_pdno") == ticker or item.get("ovrs_pdno") == order_ticker:
                                        current_qty = int(item.get("ovrs_cblc_qty", executed_qty))
                                        break
                            
                            self._initialize_partial_profit_history_after_buy(
                                ticker=order_ticker,  # 실제 주문 티커 사용
                                stock_name=stock_name,
                                purchase_price=executed_price,
                                initial_quantity=current_qty,  # 체결 후 현재 보유 수량
                                function_name=function_name
                            )
                        except Exception as e:
                            logger.warning(f"[{function_name}] 부분 익절 히스토리 초기화 중 오류 (무시): {str(e)}")
                    
                    # Slack 알림 전송 (체결 완료)
                    if order_type == "sell":
                        slack_notifier.send_sell_notification(
                            stock_name=stock_name,
                            ticker=ticker,
                            quantity=executed_qty,
                            price=executed_price,
                            exchange_code=exchange_code,
                            success=True
                        )
                    else:
                        slack_notifier.send_buy_notification(
                            stock_name=stock_name,
                            ticker=ticker,
                            quantity=executed_qty,
                            price=executed_price,
                            exchange_code=exchange_code,
                            success=True
                        )
                    logger.info(f"[{function_name}] 📨 {stock_name}({ticker}) 체결 완료 Slack 알림 전송 완료")
                else:
                    logger.error(f"[{function_name}] ❌ {stock_name}({ticker}) 체결 상태 업데이트 실패")
            else:
                # 미체결
                pending_qty = execution_result.get("pending_qty", log_record.get("quantity", 0))
                logger.warning(f"[{function_name}] ⏳ {stock_name}({ticker}) 주문번호 {order_no} 아직 미체결 (미체결 수량: {pending_qty}주)")
                logger.warning(f"[{function_name}]    지정가 주문이므로 가격이 맞지 않으면 체결되지 않을 수 있습니다.")
                
                # 상태 업데이트 (pending) - 주문체결내역 정보도 함께 저장
                execution_order_detail = execution_result.get("order", {})  # 주문체결내역 상세 정보
                update_result = db.trading_logs.update_one(
                    {"_id": log_record["_id"]},
                    {
                        "$set": {
                            "status": OrderStatus.PENDING.value,
                            "pending_qty": pending_qty,
                            "execution_result": execution_order_detail,  # 주문체결내역 상세 정보 저장 (미체결 상태 포함)
                            "execution_check_method": "order_detail_api"  # 체결 확인 방법 기록
                        }
                    }
                )
                
                if update_result.modified_count > 0:
                    logger.info(f"[{function_name}] 📝 {stock_name}({ticker}) 미체결 상태 업데이트 완료")
                    
                    # 미체결 알림 전송 (실패로 처리)
                    slack_notifier.send_buy_notification(
                        stock_name=stock_name,
                        ticker=ticker,
                        quantity=log_record.get("quantity", 0),
                        price=log_record.get("price", 0),
                        exchange_code=exchange_code,
                        success=False,
                        error_message=f"미체결 (미체결 수량: {pending_qty}주). 지정가 주문이므로 가격이 맞지 않으면 체결되지 않을 수 있습니다."
                    )
                    logger.info(f"[{function_name}] 📨 {stock_name}({ticker}) 미체결 Slack 알림 전송 완료")
                
        except Exception as e:
            logger.error(f"[{function_name}] ❌ {stock_name}({ticker}) 체결 확인 중 오류: {str(e)}", exc_info=True)
    
    def _cleanup_pending_orders(self, send_slack_notification: bool = True):
        """장 마감 후 어제 주문한 주식 체결 확인 및 미체결 주문 재주문"""
        function_name = "_cleanup_pending_orders"
        # 시간 진단 로깅
        korea_tz = pytz.timezone('Asia/Seoul')
        now_korea = datetime.now(korea_tz)
        now_local = datetime.now()
        logger.info(f"[{function_name}] 함수 실행 시작 (시스템 시간: {now_local.strftime('%Y-%m-%d %H:%M:%S')}, 한국 시간: {now_korea.strftime('%Y-%m-%d %H:%M:%S')} KST)")
        
        try:
            # 현재 시간 확인 (뉴욕 시간 기준)
            now_in_ny = datetime.now(pytz.timezone('America/New_York'))
            now_in_korea = datetime.now(pytz.timezone('Asia/Seoul'))
            ny_hour = now_in_ny.hour
            ny_weekday = now_in_ny.weekday()
            
            # 장 마감 후인지 확인 (16:00 ET 이후, 평일)
            is_weekday = 0 <= ny_weekday <= 4
            is_after_market_close = ny_hour >= 16 or (ny_weekday == 4 and ny_hour >= 16)  # 금요일 16시 이후 또는 주말
            
            if not is_weekday and ny_weekday != 0:  # 월요일이 아니고 주말인 경우
                # 주말이면 전날(금요일) 장 마감 후로 간주
                is_after_market_close = True
            
            if not is_after_market_close and is_weekday:
                logger.info(f"[{function_name}] 현재 시간 (한국: {now_in_korea.strftime('%Y-%m-%d %H:%M:%S')}, 뉴욕: {now_in_ny.strftime('%Y-%m-%d %H:%M:%S')})은 장 마감 전입니다. 정리 작업을 건너뜁니다.")
                return
            
            db = get_db()
            if db is None:
                logger.error(f"[{function_name}] ❌ MongoDB 연결 실패 - 미체결 주문 정리 불가")
                return
            
            # 어제 날짜 기준으로 주문 조회 (어제 00:00:00 ~ 23:59:59)
            yesterday = datetime.now() - timedelta(days=1)
            yesterday_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday_end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            # 어제 주문한 매수 주문 조회 (pending, accepted, executed 상태 모두 확인)
            yesterday_orders = list(db.trading_logs.find({
                "order_type": "buy",
                "created_at": {
                    "$gte": yesterday_start,
                    "$lte": yesterday_end
                },
                "status": {"$in": [OrderStatus.PENDING.value, OrderStatus.ACCEPTED.value, OrderStatus.EXECUTED.value]}
            }))
            
            if not yesterday_orders:
                logger.info(f"[{function_name}] 어제 주문한 주문이 없습니다.")
                if send_slack_notification:
                    send_scheduler_slack_notification("✅ *어제 주문 체결 확인 완료*\n어제 주문한 주문이 없습니다.")
                return
            
            logger.info(f"[{function_name}] 어제 주문 조회: {len(yesterday_orders)}개")
            
            # 체결 확인 및 재주문 통계
            executed_count = 0
            pending_count = 0
            retry_success_count = 0
            retry_failed_count = 0
            retry_orders = []
            retry_failed_orders = []
            
            # 보유 종목 조회 (중복 매수 방지용)
            holding_tickers = set()
            try:
                balance_result = get_all_overseas_balances()
                if balance_result.get("rt_cd") == "0":
                    holdings = balance_result.get("output1", [])
                    for item in holdings:
                        ticker = item.get("ovrs_pdno")
                        if ticker:
                            holding_tickers.add(ticker)
            except Exception as e:
                logger.warning(f"[{function_name}] 보유 종목 조회 실패 (중복 매수 체크 건너뜀): {str(e)}")
            
            # 주문가능금액 조회
            available_cash = 0.0
            try:
                order_psbl_result = get_overseas_order_possible_amount("NASD", "AAPL")
                if order_psbl_result.get("rt_cd") == "0":
                    output = order_psbl_result.get("output", {})
                    if output:
                        cash_str = output.get("ord_psbl_frcr_amt") or output.get("ovrs_ord_psbl_amt") or "0"
                        available_cash = float(cash_str)
            except Exception as e:
                logger.warning(f"[{function_name}] 주문가능금액 조회 실패: {str(e)}")
            
            for order in yesterday_orders:
                try:
                    ticker = order.get("ticker", "N/A")
                    stock_name = order.get("stock_name", ticker)
                    order_type = order.get("order_type", "buy")
                    quantity = order.get("quantity", 0)
                    price = order.get("price", 0)
                    order_no = order.get("order_no")
                    exchange_code = order.get("exchange_code", "NASD")
                    order_ticker = order.get("order_ticker", ticker)  # 실제 주문 티커
                    current_status = order.get("status")
                    
                    # 이미 executed 상태인 주문은 체결 확인만 수행
                    if current_status == OrderStatus.EXECUTED.value:
                        executed_count += 1
                        logger.info(f"[{function_name}] ✅ {stock_name}({ticker}) 이미 체결 완료 상태")
                        continue
                    
                    # 체결 확인 (주문번호가 있는 경우)
                    is_executed = False
                    if order_no:
                        logger.info(f"[{function_name}] {stock_name}({ticker}) 주문(주문번호: {order_no}) 체결 확인 중...")
                        try:
                            execution_result = check_order_execution(
                                order_no=order_no,
                                exchange_code=exchange_code,
                                ticker=order_ticker,
                                max_retries=2,
                                retry_delay=2,
                                order_dt=order.get("order_dt"),
                                order_gno_brno=order.get("order_gno_brno")
                            )
                            
                            if execution_result and execution_result.get("executed"):
                                # 체결된 것으로 확인됨 -> 상태 업데이트
                                executed_qty = execution_result.get("executed_qty", quantity)
                                executed_price = execution_result.get("executed_price", price)
                                
                                logger.info(f"[{function_name}] ✅ {stock_name}({ticker}) 체결 확인됨! (수량: {executed_qty}, 가격: {executed_price})")
                                
                                db.trading_logs.update_one(
                                    {"_id": order["_id"]},
                                    {
                                        "$set": {
                                            "status": OrderStatus.EXECUTED.value,
                                            "executed_at": datetime.now(),
                                            "quantity": executed_qty,
                                            "price": executed_price,
                                            "execution_check_method": "cleanup_job",
                                            "execution_result": execution_result.get("order", {})
                                        }
                                    }
                                )
                                
                                executed_count += 1
                                is_executed = True
                                
                                # 체결 성공 알림 전송 (지연된 알림)
                                slack_notifier.send_buy_notification(
                                    stock_name=stock_name,
                                    ticker=ticker,
                                    quantity=executed_qty,
                                    price=executed_price,
                                    exchange_code=exchange_code,
                                    success=True
                                )
                                logger.info(f"[{function_name}] 📨 {stock_name}({ticker}) 체결 확인 알림 전송 완료")
                        except Exception as e:
                            logger.error(f"[{function_name}] ❌ {stock_name}({ticker}) 체결 확인 중 오류: {str(e)}")
                    
                    # 체결되지 않은 경우 재주문 시도
                    if not is_executed and order_type == "buy":
                        pending_count += 1
                        logger.info(f"[{function_name}] ⚠️ {stock_name}({ticker}) 미체결 주문 발견, 재주문 시도 중...")
                        
                        # 재주문 시도 횟수 확인 (최대 1회)
                        retry_count = order.get("retry_count", 0)
                        if retry_count >= 1:
                            logger.info(f"[{function_name}] ⏭️ {stock_name}({ticker}) 재주문 시도 횟수 초과 (이미 {retry_count}회 시도), 건너뜀")
                            retry_failed_count += 1
                            retry_failed_orders.append({
                                "ticker": ticker,
                                "stock_name": stock_name,
                                "quantity": quantity,
                                "price": price,
                                "reason": "재주문 시도 횟수 초과"
                            })
                            continue
                        
                        # 이미 보유 중인 종목인지 확인
                        if ticker in holding_tickers:
                            logger.info(f"[{function_name}] ⏭️ {stock_name}({ticker}) 이미 보유 중, 재주문 건너뜀")
                            retry_failed_count += 1
                            retry_failed_orders.append({
                                "ticker": ticker,
                                "stock_name": stock_name,
                                "quantity": quantity,
                                "price": price,
                                "reason": "이미 보유 중"
                            })
                            continue
                        
                        # 현재가 조회
                        try:
                            current_price_params = {
                                "AUTH": "",
                                "EXCD": exchange_code,
                                "SYMB": order_ticker
                            }
                            current_price_result = get_current_price(current_price_params)
                            
                            if current_price_result.get("rt_cd") != "0":
                                error_msg = current_price_result.get("msg1", "현재가 조회 실패")
                                logger.warning(f"[{function_name}] ❌ {stock_name}({ticker}) 현재가 조회 실패: {error_msg}")
                                retry_failed_count += 1
                                retry_failed_orders.append({
                                    "ticker": ticker,
                                    "stock_name": stock_name,
                                    "quantity": quantity,
                                    "price": price,
                                    "reason": f"현재가 조회 실패: {error_msg}"
                                })
                                continue
                            
                            output = current_price_result.get("output", {})
                            current_price = float(output.get("last", "0") or "0")
                            
                            if current_price <= 0:
                                logger.warning(f"[{function_name}] ❌ {stock_name}({ticker}) 유효하지 않은 현재가: {current_price}")
                                retry_failed_count += 1
                                retry_failed_orders.append({
                                    "ticker": ticker,
                                    "stock_name": stock_name,
                                    "quantity": quantity,
                                    "price": price,
                                    "reason": "유효하지 않은 현재가"
                                })
                                continue
                            
                            # 주문 금액 계산
                            order_amount = current_price * quantity
                            
                            # 잔고 확인
                            if order_amount > available_cash:
                                logger.warning(f"[{function_name}] ❌ {stock_name}({ticker}) 잔고 부족 (필요: ${order_amount:,.2f}, 보유: ${available_cash:,.2f})")
                                retry_failed_count += 1
                                retry_failed_orders.append({
                                    "ticker": ticker,
                                    "stock_name": stock_name,
                                    "quantity": quantity,
                                    "price": current_price,
                                    "reason": "잔고 부족"
                                })
                                continue
                            
                            # 재주문 실행
                            logger.info(f"[{function_name}] 🔄 {stock_name}({ticker}) 재주문 실행 중... (수량: {quantity}, 가격: ${current_price:.2f})")
                            
                            order_data = {
                                "CANO": settings.KIS_CANO,
                                "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
                                "OVRS_EXCG_CD": exchange_code,
                                "PDNO": order_ticker,
                                "ORD_DVSN": "00",  # 지정가
                                "ORD_QTY": str(quantity),
                                "OVRS_ORD_UNPR": str(current_price),
                                "ORD_SVR_DVSN_CD": "0",
                                "is_buy": True
                            }
                            
                            order_result = order_overseas_stock(order_data)
                            
                            if order_result.get("rt_cd") == "0":
                                # 재주문 성공
                                output = order_result.get("output", {})
                                new_order_no = output.get("ODNO", "")
                                
                                logger.info(f"[{function_name}] ✅ {stock_name}({ticker}) 재주문 성공! (주문번호: {new_order_no})")
                                
                                # 새 주문 레코드 저장
                                new_order_log = {
                                    "order_type": "buy",
                                    "ticker": ticker,
                                    "stock_name": stock_name,
                                    "price": current_price,
                                    "quantity": quantity,
                                    "status": OrderStatus.ACCEPTED.value,
                                    "order_no": new_order_no,
                                    "exchange_code": exchange_code,
                                    "order_ticker": order_ticker,
                                    "order_dt": output.get("ORD_DT", ""),
                                    "order_gno_brno": output.get("ORD_GNO_BRNO", ""),
                                    "original_order_id": str(order["_id"]),
                                    "retry_count": retry_count + 1,
                                    "retry_at": datetime.now(),
                                    "created_at": datetime.now()
                                }
                                db.trading_logs.insert_one(new_order_log)
                                
                                # 기존 주문 레코드 업데이트
                                db.trading_logs.update_one(
                                    {"_id": order["_id"]},
                                    {
                                        "$set": {
                                            "status": OrderStatus.RETRY.value,
                                            "retry_at": datetime.now(),
                                            "retry_count": retry_count + 1,
                                            "retry_order_id": str(new_order_log.get("_id", ""))
                                        }
                                    }
                                )
                                
                                retry_success_count += 1
                                retry_orders.append({
                                    "ticker": ticker,
                                    "stock_name": stock_name,
                                    "quantity": quantity,
                                    "price": current_price,
                                    "order_no": new_order_no
                                })
                                
                                # Slack 알림 전송
                                slack_notifier.send_buy_notification(
                                    stock_name=stock_name,
                                    ticker=ticker,
                                    quantity=quantity,
                                    price=current_price,
                                    exchange_code=exchange_code,
                                    success=True
                                )
                            else:
                                # 재주문 실패
                                error_msg = order_result.get("msg1", "알 수 없는 오류")
                                logger.error(f"[{function_name}] ❌ {stock_name}({ticker}) 재주문 실패: {error_msg}")
                                retry_failed_count += 1
                                retry_failed_orders.append({
                                    "ticker": ticker,
                                    "stock_name": stock_name,
                                    "quantity": quantity,
                                    "price": current_price,
                                    "reason": f"주문 실패: {error_msg}"
                                })
                                
                                # Slack 알림 전송
                                slack_notifier.send_buy_notification(
                                    stock_name=stock_name,
                                    ticker=ticker,
                                    quantity=quantity,
                                    price=current_price,
                                    exchange_code=exchange_code,
                                    success=False,
                                    error_message=f"재주문 실패: {error_msg}"
                                )
                        
                        except Exception as e:
                            logger.error(f"[{function_name}] ❌ {stock_name}({ticker}) 재주문 처리 중 오류: {str(e)}", exc_info=True)
                            retry_failed_count += 1
                            retry_failed_orders.append({
                                "ticker": ticker,
                                "stock_name": stock_name,
                                "quantity": quantity,
                                "price": price,
                                "reason": f"오류: {str(e)}"
                            })
                    
                except Exception as e:
                    logger.error(f"[{function_name}] ❌ 주문 {order.get('_id')} 처리 중 오류: {str(e)}", exc_info=True)
            
            # 요약 로깅
            logger.info("=" * 80)
            logger.info(f"[{function_name}] 📊 어제 주문 체결 확인 및 재주문 요약")
            logger.info(f"  어제 주문 수: {len(yesterday_orders)}개")
            logger.info(f"  ✅ 체결 완료: {executed_count}개")
            logger.info(f"  ⚠️ 미체결 주문: {pending_count}개")
            logger.info(f"    - 재주문 성공: {retry_success_count}개")
            logger.info(f"    - 재주문 실패: {retry_failed_count}개")
            logger.info("=" * 80)
            
            # 요약 Slack 알림
            if send_slack_notification:
                summary_msg = f"🔄 *어제 주문 체결 확인 및 재주문 완료*\n\n"
                summary_msg += f"• 어제 주문 수: {len(yesterday_orders)}개\n"
                summary_msg += f"• 체결 완료: {executed_count}개\n"
                summary_msg += f"• 미체결 주문: {pending_count}개\n"
                summary_msg += f"  - 재주문 성공: {retry_success_count}개\n"
                summary_msg += f"  - 재주문 실패: {retry_failed_count}개\n"
                
                if retry_orders:
                    summary_msg += f"\n*재주문 성공:*\n"
                    for order_info in retry_orders[:10]:  # 최대 10개만 표시
                        summary_msg += f"  - {order_info['stock_name']}({order_info['ticker']}): {order_info['quantity']}주 @ ${order_info['price']:.2f} (주문번호: {order_info.get('order_no', 'N/A')})\n"
                    if len(retry_orders) > 10:
                        summary_msg += f"  ... 외 {len(retry_orders) - 10}개\n"
                
                if retry_failed_orders:
                    summary_msg += f"\n*재주문 실패:*\n"
                    for order_info in retry_failed_orders[:10]:  # 최대 10개만 표시
                        summary_msg += f"  - {order_info['stock_name']}({order_info['ticker']}): {order_info['quantity']}주 @ ${order_info.get('price', 0):.2f} ({order_info.get('reason', '알 수 없음')})\n"
                    if len(retry_failed_orders) > 10:
                        summary_msg += f"  ... 외 {len(retry_failed_orders) - 10}개\n"
                
                send_scheduler_slack_notification(summary_msg)
            
            logger.info(f"[{function_name}] 함수 실행 완료")
            
        except Exception as e:
            logger.error(f"[{function_name}] ❌ 어제 주문 체결 확인 및 재주문 중 오류: {str(e)}", exc_info=True)
            if send_slack_notification:
                send_scheduler_slack_notification(f"❌ *어제 주문 체결 확인 및 재주문 실패*\n오류 발생: {str(e)}")
    
    def _run_portfolio_profit_report(self, send_slack_notification: bool = True):
        """계좌 수익율 리포트 전송"""
        function_name = "_run_portfolio_profit_report"
        # 시간 진단 로깅
        korea_tz = pytz.timezone('Asia/Seoul')
        now_korea = datetime.now(korea_tz)
        now_local = datetime.now()
        logger.info(f"[{function_name}] 함수 실행 시작 (시스템 시간: {now_local.strftime('%Y-%m-%d %H:%M:%S')}, 한국 시간: {now_korea.strftime('%Y-%m-%d %H:%M:%S')} KST)")
        
        if send_slack_notification:
            send_scheduler_slack_notification(f"📊 *계좌 수익율 리포트 생성 중*\n계좌 잔고를 조회하고 수익율을 계산합니다.")
        
        try:
            # 수익율 계산
            profit_result = calculate_portfolio_profit()
            
            if not profit_result.get("success"):
                error_msg = profit_result.get("error", "알 수 없는 오류")
                logger.error(f"[{function_name}] ❌ 수익율 계산 실패: {error_msg}")
                if send_slack_notification:
                    send_scheduler_slack_notification(f"❌ *계좌 수익율 리포트 실패*\n오류 발생: {error_msg}")
                return False
            
            holdings = profit_result.get("holdings", [])
            total_cost = profit_result.get("total_cost", 0.0)
            total_value = profit_result.get("total_value", 0.0)
            total_profit = profit_result.get("total_profit", 0.0)
            total_profit_percent = profit_result.get("total_profit_percent", 0.0)
            
            logger.info(f"[{function_name}] ✅ 수익율 계산 완료")
            logger.info(f"  - 보유 종목: {len(holdings)}개")
            logger.info(f"  - 총 매수금액: ${total_cost:,.2f}")
            logger.info(f"  - 총 평가금액: ${total_value:,.2f}")
            logger.info(f"  - 총 수익: ${total_profit:+,.2f} ({total_profit_percent:+.2f}%)")
            
            # 추가 수익률 및 계좌 정보 조회
            from app.utils.user_context import get_current_user_id
            user_id = get_current_user_id()
            account_info = {}
            total_return_info = {}
            realized_return_info = {}
            ticker_realized_profit = {}
            
            try:
                # 전체 포트폴리오 수익률 (총 자산 기준)
                total_return_result = calculate_total_return(user_id=user_id)
                if total_return_result.get("success"):
                    total_return_info = {
                        "total_deposit_usd": total_return_result.get("total_deposit_usd", 0.0),
                        "total_assets_usd": total_return_result.get("total_assets_usd", 0.0),
                        "total_return_usd": total_return_result.get("total_return_usd", 0.0),
                        "total_return_percent": total_return_result.get("total_return_percent", 0.0)
                    }
                    logger.info(f"[{function_name}] ✅ 전체 포트폴리오 수익률 조회 완료: {total_return_info['total_return_percent']:.2f}%")
                
                # 실현 수익률 (완료된 거래)
                end_date = datetime.now()
                start_date = datetime(2025, 11, 1)
                days_diff = (end_date - start_date).days
                cumulative_result = calculate_cumulative_profit(user_id=user_id, days=days_diff)
                if cumulative_result.get("success"):
                    stats = cumulative_result.get("statistics", {})
                    realized_return_info = {
                        "total_profit": stats.get("total_profit", 0.0),
                        "total_cost": stats.get("total_cost", 0.0),
                        "total_profit_percent": stats.get("total_profit_percent", 0.0),
                        "win_rate": stats.get("win_rate", 0.0),
                        "total_trades": stats.get("total_trades", 0),
                        "winning_trades": stats.get("winning_trades", 0),
                        "losing_trades": stats.get("losing_trades", 0)
                    }
                    
                    # 종목별 실현 수익률 (수익률 + 금액)
                    by_ticker = cumulative_result.get("by_ticker", {})
                    if isinstance(by_ticker, dict):
                        for ticker, ticker_stats in by_ticker.items():
                            if isinstance(ticker_stats, dict):
                                profit_percent = round(ticker_stats.get("total_profit_percent", 0.0), 2)
                                profit_usd = round(ticker_stats.get("total_profit", 0.0), 2)
                                ticker_realized_profit[ticker] = {
                                    "profit_percent": profit_percent,
                                    "profit_usd": profit_usd
                                }
                    elif isinstance(by_ticker, list):
                        for ticker_stats in by_ticker:
                            if isinstance(ticker_stats, dict):
                                ticker = ticker_stats.get("ticker", "N/A")
                                profit_percent = round(ticker_stats.get("total_profit_percent", 0.0), 2)
                                profit_usd = round(ticker_stats.get("total_profit", 0.0), 2)
                                ticker_realized_profit[ticker] = {
                                    "profit_percent": profit_percent,
                                    "profit_usd": profit_usd
                                }
                    
                    logger.info(f"[{function_name}] ✅ 실현 수익률 조회 완료: {realized_return_info['total_profit_percent']:.2f}%")
                
                # 계좌 정보 조회 (MongoDB에서)
                db = get_db()
                if db is not None:
                    user = db.users.find_one({"user_id": user_id})
                    if user and "account_balance" in user:
                        balance = user["account_balance"]
                        account_info = {
                            "available_usd": balance.get("available_usd", 0.0),
                            "total_assets_usd": balance.get("total_assets_usd", 0.0),
                            "total_deposit_usd": balance.get("total_deposit_usd", 0.0),
                            "total_cost_usd": balance.get("total_cost_usd", 0.0),
                            "total_value_usd": balance.get("total_value_usd", 0.0),
                            "total_profit_usd": balance.get("total_profit_usd", 0.0),
                            "total_profit_percent": balance.get("total_profit_percent", 0.0),
                            "holdings_count": balance.get("holdings_count", 0)
                        }
                        logger.info(f"[{function_name}] ✅ 계좌 정보 조회 완료")
            except Exception as e:
                logger.warning(f"[{function_name}] ⚠️ 추가 정보 조회 중 오류 (계속 진행): {str(e)}")
            
            # Slack 알림 전송
            if send_slack_notification:
                slack_notifier.send_portfolio_profit_notification(
                    holdings=holdings,
                    total_cost=total_cost,
                    total_value=total_value,
                    total_profit=total_profit,
                    total_profit_percent=total_profit_percent,
                    account_info=account_info,
                    total_return_info=total_return_info,
                    realized_return_info=realized_return_info,
                    ticker_realized_profit=ticker_realized_profit
                )
                logger.info(f"[{function_name}] 📨 계좌 수익율 리포트 Slack 알림 전송 완료")
            
            logger.info(f"[{function_name}] 함수 실행 완료")
            return True
            
        except Exception as e:
            logger.error(f"[{function_name}] ❌ 계좌 수익율 리포트 중 오류 발생: {str(e)}", exc_info=True)
            if send_slack_notification:
                send_scheduler_slack_notification(f"❌ *계좌 수익율 리포트 오류*\n오류 발생: {str(e)}")
            return False
        
    def _initialize_trailing_stop_after_buy(
        self,
        ticker: str,
        stock_name: str,
        purchase_price: float,
        function_name: str = "_execute_auto_buy"
    ):
        """
        매수 체결 완료 후 트레일링 스톱 초기화
        
        Args:
            ticker: 실제 주문 티커 (레버리지 티커 또는 원본 티커)
            stock_name: 종목명
            purchase_price: 구매가
            function_name: 함수명 (로깅용)
        """
        try:
            from app.services.trailing_stop_service import TrailingStopService
            trailing_stop_service = TrailingStopService()
            
            # 설정 확인
            config = self.auto_trading_service.get_auto_trading_config()
            if not config.get("trailing_stop_enabled", False):
                logger.debug(f"[{function_name}] 트레일링 스톱이 비활성화되어 있어 초기화하지 않습니다.")
                return
            
            # 레버리지 여부 확인
            is_leveraged = False
            db = get_db()
            if db is not None:
                try:
                    # MongoDB에서 레버리지 티커인지 확인
                    base_stock = db.stocks.find_one({"leverage_ticker": ticker})
                    if base_stock:
                        is_leveraged = True
                        logger.debug(f"[{function_name}] {stock_name}({ticker})는 레버리지 티커로 확인됨")
                    else:
                        # 종목명 키워드로 확인
                        leverage_keywords = ["2X", "3X", "Leverage", "Ultra", "레버리지", "2배", "3배"]
                        for keyword in leverage_keywords:
                            if keyword.lower() in stock_name.lower():
                                is_leveraged = True
                                logger.debug(f"[{function_name}] {stock_name}({ticker})는 종목명 키워드로 레버리지로 확인됨")
                                break
                except Exception as e:
                    logger.warning(f"[{function_name}] 레버리지 여부 확인 중 오류 (계속 진행): {str(e)}")
            
            # 트레일링 스톱 초기화
            trailing_stop_service.initialize_trailing_stop(
                ticker=ticker,
                purchase_price=purchase_price,
                purchase_date=datetime.now(),
                is_leveraged=is_leveraged,
                stock_name=stock_name
            )
            logger.info(f"[{function_name}] ✅ {stock_name}({ticker}) 트레일링 스톱 초기화 완료 (구매가: ${purchase_price:.2f}, 레버리지: {is_leveraged})")
            
        except Exception as e:
            logger.error(f"[{function_name}] ❌ {stock_name}({ticker}) 트레일링 스톱 초기화 중 오류: {str(e)}", exc_info=True)
    
    def _initialize_partial_profit_history_after_buy(
        self,
        ticker: str,
        stock_name: str,
        purchase_price: float,
        initial_quantity: int,
        function_name: str = "_execute_auto_buy"
    ):
        """
        매수 체결 완료 후 부분 익절 히스토리 초기화
        
        Args:
            ticker: 실제 주문 티커 (레버리지 티커 또는 원본 티커)
            stock_name: 종목명
            purchase_price: 구매가
            initial_quantity: 초기 보유 수량 (부분 매도 전 전체 수량)
            function_name: 함수명 (로깅용)
        """
        try:
            from app.db.mongodb import get_db
            db = get_db()
            if db is None:
                logger.warning(f"[{function_name}] MongoDB 연결 실패 - 부분 익절 히스토리 초기화 불가")
                return
            
            from app.utils.user_context import get_current_user_id
            user_id = get_current_user_id()
            
            # 이미 히스토리가 있는지 확인
            existing_history = db.partial_sell_history.find_one({
                "user_id": user_id,
                "ticker": ticker
            })
            
            if existing_history:
                # 이미 히스토리가 있으면 초기 수량만 업데이트 (부분 매도가 아직 시작되지 않은 경우)
                if not existing_history.get("partial_sells") or len(existing_history.get("partial_sells", [])) == 0:
                    # 부분 매도가 아직 없는 경우 초기 수량 업데이트
                    db.partial_sell_history.update_one(
                        {"user_id": user_id, "ticker": ticker},
                        {
                            "$set": {
                                "initial_quantity": initial_quantity,
                                "purchase_price": purchase_price,
                                "last_updated": datetime.utcnow()
                            }
                        }
                    )
                    logger.info(f"[{function_name}] ✅ {stock_name}({ticker}) 부분 익절 히스토리 초기 수량 업데이트 완료 ({initial_quantity}주)")
            else:
                # 새로운 히스토리 생성
                new_history = {
                    "user_id": user_id,
                    "ticker": ticker,
                    "stock_name": stock_name,
                    "purchase_price": purchase_price,
                    "initial_quantity": initial_quantity,
                    "partial_sells": [],
                    "is_completed": False,
                    "last_updated": datetime.utcnow(),
                    "created_at": datetime.utcnow()
                }
                
                db.partial_sell_history.insert_one(new_history)
                logger.info(f"[{function_name}] ✅ {stock_name}({ticker}) 부분 익절 히스토리 초기화 완료 (초기 수량: {initial_quantity}주, 구매가: ${purchase_price:.2f})")
            
        except Exception as e:
            logger.error(f"[{function_name}] ❌ {stock_name}({ticker}) 부분 익절 히스토리 초기화 중 오류: {str(e)}", exc_info=True)
    
    def _save_trading_log(
        self,
        order_type: str,
        ticker: str,
        stock_name: str,
        price: float,
        quantity: int,
        status: str,
        composite_score: float = None,
        price_change_percent: float = None,
        sell_reasons: list = None,
        order_result: dict = None,
        exchange_code: str = None,
        order_no: str = None,
        order_ticker: str = None,  # 실제 주문에 사용된 티커 (레버리지 티커 또는 원본 티커)
        order_dt: str = None,  # 주문일자 (YYYYMMDD)
        order_gno_brno: str = None,  # 주문점번호
        order_tmd: str = None  # 주문시각
    ):
        """매매 기록을 MongoDB trading_logs 컬렉션에 저장"""
        try:
            db = get_db()
            if db is None:
                logger.error(f"❌ MongoDB 연결 실패 - 매매 기록 저장 불가: {order_type} {ticker} {quantity}주 @ ${price}")
                return False

            log_data = {
                "user_id": "system",  # 스케줄러는 시스템 계정으로 저장
                "order_type": order_type,  # "buy" | "sell"
                "ticker": ticker,
                "stock_name": stock_name,
                "price": price,
                "quantity": quantity,
                "status": status,  # OrderStatus enum value
                "created_at": datetime.now()
            }

            # 선택적 필드 추가
            if composite_score is not None:
                log_data["composite_score"] = composite_score
            if price_change_percent is not None:
                log_data["price_change_percent"] = price_change_percent
            if sell_reasons:
                log_data["sell_reasons"] = sell_reasons
            if order_result:
                log_data["order_result"] = order_result
            if exchange_code:
                log_data["exchange_code"] = exchange_code
            if order_no:
                log_data["order_no"] = order_no  # 주문번호 저장
            if order_ticker:
                log_data["order_ticker"] = order_ticker  # 실제 주문 티커 저장 (체결 조회용)
            if order_dt:
                log_data["order_dt"] = order_dt  # 주문일자 저장 (체결 조회용)
            if order_gno_brno:
                log_data["order_gno_brno"] = order_gno_brno  # 주문점번호 저장 (체결 조회용)
            if order_tmd:
                log_data["order_tmd"] = order_tmd  # 주문시각 저장
            
            result = db.trading_logs.insert_one(log_data)
            if result.inserted_id:
                logger.info(f"✅ 매매 기록 저장 완료: {order_type} {ticker} {stock_name} {quantity}주 @ ${price} (status: {status}, ID: {result.inserted_id})")
                return True
            else:
                logger.error(f"❌ 매매 기록 저장 실패: {order_type} {ticker} {stock_name} {quantity}주 @ ${price} - inserted_id가 None입니다")
                return False
        
        except Exception as e:
            logger.error(f"❌ 매매 기록 저장 중 오류: {order_type} {ticker} {stock_name} {quantity}주 @ ${price} - {str(e)}", exc_info=True)
            return False

# 싱글톤 인스턴스 생성
stock_scheduler = StockScheduler()

# 스케줄러 초기화 여부 추적 (중복 등록 방지)
_scheduler_initialized = False

def start_scheduler():
    """매수 스케줄러 시작 함수"""
    global _scheduler_initialized
    if _scheduler_initialized:
        logger.warning("스케줄러가 이미 초기화되었습니다. 중복 등록을 방지합니다.")
        return False
    result = stock_scheduler.start()
    if result:
        _scheduler_initialized = True
    return result

def stop_scheduler():
    """매수 스케줄러 중지 함수"""
    global _scheduler_initialized
    result = stock_scheduler.stop()
    if result:
        _scheduler_initialized = False
    return result

def start_sell_scheduler():
    """매도 스케줄러 시작 함수"""
    return stock_scheduler.start_sell_scheduler()

def stop_sell_scheduler():
    """매도 스케줄러 중지 함수"""
    return stock_scheduler.stop_sell_scheduler()

def get_scheduler_status():
    """스케줄러 상태 확인"""
    return {
        "buy_running": stock_scheduler.running,
        "sell_running": stock_scheduler.sell_running
    }

def run_auto_buy_now():
    """즉시 매수 실행 함수 (테스트용) - 슬랙 알림 없음"""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 이미 실행 중인 루프가 있으면 create_task 사용
            asyncio.create_task(stock_scheduler._execute_auto_buy(send_slack_notification=False))
        else:
            # 실행 중인 루프가 없으면 asyncio.run 사용
            asyncio.run(stock_scheduler._execute_auto_buy(send_slack_notification=False))
    except RuntimeError:
        # RuntimeError 발생 시 새 스레드에서 실행
        import threading
        def run_in_thread():
            asyncio.run(stock_scheduler._execute_auto_buy(send_slack_notification=False))
        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()
    
def run_auto_sell_now():
    """즉시 매도 실행 함수 (테스트용)"""
    stock_scheduler._run_auto_sell()

def run_vertex_ai_prediction_now(send_slack_notification: bool = False):
    """즉시 Vertex AI 주가 예측 작업 실행 함수 (API 호출용)"""
    return stock_scheduler._run_vertex_ai_prediction(send_slack_notification=send_slack_notification)

def run_analysis_now(send_slack_notification: bool = False):
    """즉시 분석 실행 함수 (API 호출용)"""
    return stock_scheduler._run_analysis(send_slack_notification=send_slack_notification)


def run_economic_data_update_now():
    """즉시 경제 데이터 업데이트 실행 함수 (테스트용) - 슬랙 알림 없음"""
    return stock_scheduler._run_economic_data_update(send_slack_notification=False)

# 타임아웃 방지를 위한 커스텀 StreamHandler
class SafeStreamHandler(logging.StreamHandler):
    """flush 실패 시 타임아웃 에러를 무시하는 안전한 StreamHandler"""
    def flush(self):
        try:
            super().flush()
        except (TimeoutError, OSError) as e:
            # 로깅 실패를 무시 (무한 루프 방지)
            pass

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        SafeStreamHandler(),  # 타임아웃 방지 핸들러 사용
        logging.FileHandler('stock_scheduler.log')
    ]
)
logger = logging.getLogger('stock_scheduler')

def send_scheduler_slack_notification(message: str) -> bool:
    """
    스케줄러 실행 알림을 Slack으로 전송 (재시도 포함, 최대 3번)
    
    Args:
        message: 알림 메시지 (이미 실행 시간이 포함되어 있을 수 있음)
    
    Returns:
        bool: 전송 성공 여부
    """
    webhook_url = settings.SLACK_WEBHOOK_URL_SCHEDULER
    if not webhook_url:
        logger.warning("SLACK_WEBHOOK_URL_SCHEDULER 환경변수가 설정되지 않아 스케줄러 알림을 전송할 수 없습니다.")
        return False
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # 메시지에 이미 시간이 포함되어 있으면 중복 추가하지 않음
            if "실행 시간:" in message or "시작:" in message or "완료:" in message:
                formatted_message = f"📅 *스케줄러 알림*\n{message}"
            else:
                now_korea = datetime.now(pytz.timezone('Asia/Seoul'))
                formatted_message = f"📅 *스케줄러 알림*\n{message}\n\n🕒 알림 전송 시간: {now_korea.strftime('%Y-%m-%d %H:%M:%S')} (KST)"
            
            payload = {"text": formatted_message}
            with httpx.Client(timeout=10.0) as client:
                response = client.post(webhook_url, json=payload)
                if response.status_code == 200:
                    logger.debug(f"스케줄러 Slack 알림 전송 성공: {message}")
                    return True
                elif attempt < max_retries - 1:
                    logger.warning(f"스케줄러 Slack 알림 전송 실패 ({response.status_code}), 재시도 중... (시도 {attempt+1}/{max_retries})")
                    time.sleep(2 ** attempt)  # exponential backoff
                else:
                    logger.warning(f"스케줄러 Slack 알림 전송 최종 실패: {response.status_code}")
                    return False
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"스케줄러 Slack 알림 전송 중 오류 (재시도 중...): {str(e)} (시도 {attempt+1}/{max_retries})")
                time.sleep(2 ** attempt)  # exponential backoff
            else:
                logger.error(f"스케줄러 Slack 알림 전송 최종 실패: {str(e)}")
                return False
    
    return False
 