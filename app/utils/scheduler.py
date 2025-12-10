import asyncio
import schedule
import time
import pytz
from datetime import datetime, timedelta
from pathlib import Path
import threading
from typing import Callable
from app.services.stock_recommendation_service import StockRecommendationService
from app.services.balance_service import get_current_price, order_overseas_stock, get_all_overseas_balances, get_overseas_balance, get_overseas_order_possible_amount
from app.core.config import settings
import logging
from app.services.economic_service import update_economic_data_in_background
from app.utils.slack_notifier import slack_notifier
import httpx

class StockScheduler:
    """주식 자동매매 스케줄러 클래스"""
    
    def __init__(self):
        self.recommendation_service = StockRecommendationService()
        self.running = False
        self.sell_running = False  # 매도 스케줄러 실행 상태
        self.analysis_running = False  # 분석 스케줄러 실행 상태
        self.scheduler_thread = None
        self.buy_executing = False  # 매수 작업 실행 중 플래그 (중복 실행 방지)
        self.analysis_executing = False  # 분석 작업 실행 중 플래그 (중복 실행 방지)
        self.prediction_executing = False  # Vertex AI 예측 작업 실행 중 플래그 (중복 실행 방지)
        self.stopping = False  # 중지 중 플래그 (중복 중지 방지)
    
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
            '_run_economic_data_update'
        ]
        
        for job in schedule.jobs:
            if job.job_func.__name__ in job_names:
                schedule.cancel_job(job)
        
        # 한국 시간 기준 새벽 6시 5분에 경제 데이터 업데이트 작업 실행
        schedule.every().day.at("06:05").do(self._run_economic_data_update)
        
        # 한국 시간 기준 밤 11시에 경제 데이터 재수집 (최신 지표 반영)
        schedule.every().day.at("23:00").do(self._run_economic_data_update)
        
        # 한국 시간 기준 밤 11시 15분에 병렬 분석 작업 실행
        schedule.every().day.at("23:15").do(self._run_parallel_analysis)

        # 한국 시간 기준 밤 11시 45분에 통합 분석 작업 실행
        schedule.every().day.at("23:45").do(self._run_combined_analysis)
        
        # 한국 시간 기준 밤 12시(00:00)에 매수 작업 실행
        schedule.every().day.at("00:00").do(self._run_auto_buy)
        
        # 별도 스레드에서 스케줄러 실행
        self.running = True
        self.analysis_running = True
        self.scheduler_thread = threading.Thread(target=self._run_scheduler)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()
        
        # 하나의 상세한 로그로 통합
        logger.info("주식 자동매매 스케줄러가 시작되었습니다.")
        logger.info("  - 경제 데이터: 매일 06:05, 23:00 (재수집)")
        logger.info("  - 병렬 분석: 매일 23:15 (Vertex AI + 기술적 지표 + 감정 분석)")
        logger.info("  - 통합 분석: 매일 23:45 (3가지 결과 통합)")
        logger.info("  - 매수: 매일 00:00")
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
            '_run_economic_data_update'
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
        logger.info(f"[{function_name}] 함수 실행 시작")
        if send_slack_notification:
            send_scheduler_slack_notification(f"📈 *경제 데이터 업데이트 시작*\n경제 데이터 수집을 시작합니다.")
        
        try:
            asyncio.run(update_economic_data_in_background())
            logger.info(f"[{function_name}] 함수 실행 완료")
            if send_slack_notification:
                send_scheduler_slack_notification(f"✅ *경제 데이터 업데이트 완료*\n경제 데이터 수집이 완료되었습니다.")
            return True
        except Exception as e:
            logger.error(f"[{function_name}] 함수 실행 중 오류 발생: {str(e)}", exc_info=True)
            logger.info(f"[{function_name}] 함수 실행 완료 (오류)")
            if send_slack_notification:
                send_scheduler_slack_notification(f"❌ *경제 데이터 업데이트 오류*\n오류 발생: {str(e)}")
            return False

    def _run_vertex_ai_prediction(self, send_slack_notification: bool = True):
        """Vertex AI를 사용한 주가 예측 작업 실행 (run_predict_vertex_ai.py)"""
        function_name = "_run_vertex_ai_prediction"
        logger.info("=" * 60)
        logger.info(f"[{function_name}] Vertex AI 주가 예측 작업 시작")
        logger.info("=" * 60)
        
        if self.prediction_executing:
            logger.warning(f"[{function_name}] 이미 실행 중입니다. 중복 실행을 방지합니다.")
            return False
        
        self.prediction_executing = True
        
        try:
            if send_slack_notification:
                send_scheduler_slack_notification(f"🚀 *Vertex AI 주가 예측 시작*\nrun_predict_vertex_ai.py 실행을 시작합니다.")
            
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
            if hasattr(settings, 'SUPABASE_URL') and settings.SUPABASE_URL:
                env['SUPABASE_URL'] = settings.SUPABASE_URL
            if hasattr(settings, 'SUPABASE_KEY') and settings.SUPABASE_KEY:
                env['SUPABASE_KEY'] = settings.SUPABASE_KEY
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
            # 환경변수 설정 (Supabase 연결 정보)
            env = os.environ.copy()
            if hasattr(settings, 'SUPABASE_URL') and settings.SUPABASE_URL:
                env['SUPABASE_URL'] = settings.SUPABASE_URL
            if hasattr(settings, 'SUPABASE_KEY') and settings.SUPABASE_KEY:
                env['SUPABASE_KEY'] = settings.SUPABASE_KEY
            
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
        
        # 1분마다 매도 작업 실행
        schedule.every(1).minutes.do(self._run_auto_sell)
        
        # 스케줄러 스레드가 없으면 시작
        if not self.running and not self.scheduler_thread:
            self.scheduler_thread = threading.Thread(target=self._run_scheduler)
            self.scheduler_thread.daemon = True
            self.scheduler_thread.start()
        
        self.sell_running = True
        logger.info("매도 스케줄러가 시작되었습니다.")
        logger.info("  - 실행 주기: 1분마다 매도 대상 확인")
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
        while self.running or self.sell_running or self.analysis_running:
            schedule.run_pending()
            time.sleep(1)
    
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
                send_scheduler_slack_notification(f"❌ *통합 분석 작업 오류*\n오류 발생: {str(e)}")
        finally:
            # 실행 완료 후 플래그 해제
            self.analysis_executing = False
    
    def _run_parallel_analysis(self, send_slack_notification: bool = True):
        """
        세 가지 분석 작업을 병렬로 실행
        - Vertex AI 예측 (백그라운드, ~2시간)
        - 기술적 지표 분석 (~5분)
        - 감정 분석 (독립적, ~20분)
        """
        function_name = "_run_parallel_analysis"
        
        # 중복 실행 방지
        if self.analysis_executing:
            logger.warning(f"[{function_name}] 분석 작업이 이미 실행 중입니다. 중복 실행을 건너뜁니다.")
            return False
        
        self.analysis_executing = True
        logger.info("=" * 60)
        logger.info(f"[{function_name}] 병렬 분석 작업 시작")
        logger.info("=" * 60)
        if send_slack_notification:
            send_scheduler_slack_notification(f"🚀 *병렬 분석 작업 시작*\nVertex AI 예측, 기술적 지표, 감정 분석을 병렬로 실행합니다.")
        
        try:
            import concurrent.futures
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                # 1. Vertex AI 예측 (백그라운드, 2시간 소요)
                logger.info(f"[{function_name}] Vertex AI 예측 시작...")
                vertex_future = executor.submit(
                    self._run_vertex_ai_prediction,
                    send_slack_notification=send_slack_notification
                )
                
                # 2. 기술적 지표 분석
                logger.info(f"[{function_name}] 기술적 지표 분석 시작...")
                tech_future = executor.submit(
                    self.recommendation_service.generate_technical_recommendations,
                    send_slack_notification=False  # 개별 알림은 비활성화
                )
                
                # 3. 감정 분석 (독립적)
                logger.info(f"[{function_name}] 감정 분석 시작...")
                sentiment_future = executor.submit(
                    self.recommendation_service.fetch_and_store_sentiment_independent
                )
                
                # 기술적 지표와 감정 분석 결과 대기 (Vertex AI는 백그라운드로 계속 실행)
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
                    send_scheduler_slack_notification(
                        f"📊 *기술적 지표 분석 완료*\n"
                        f"날짜: {date_str}\n"
                        f"분석 종목: {total_count}개\n"
                        f"추천 종목: {recommended_count}개"
                    )
                    
                    # 감정 분석 완료 슬랙 알림
                    sentiment_results = sentiment_result.get('results', [])
                    send_scheduler_slack_notification(
                        f"💬 *감정 분석 완료*\n"
                        f"{sentiment_result.get('message', '')}"
                    )
                
                # Vertex AI 예측은 백그라운드로 계속 실행 중
                logger.info(f"[{function_name}] ⏳ Vertex AI 예측은 백그라운드에서 계속 실행 중입니다...")
                
            logger.info("=" * 60)
            logger.info(f"[{function_name}] 병렬 분석 작업 완료 (Vertex AI는 백그라운드 실행 중)")
            logger.info("=" * 60)
            return True
            
        except Exception as e:
            logger.error(f"[{function_name}] ❌ 병렬 분석 중 오류 발생: {str(e)}", exc_info=True)
            if send_slack_notification:
                send_scheduler_slack_notification(f"❌ *병렬 분석 작업 오류*\n오류 발생: {str(e)}")
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
        
        logger.info("=" * 60)
        logger.info(f"[{function_name}] 통합 분석 시작")
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
        logger.info(f"[{function_name}] 함수 실행 시작")
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
        
        # 현재 시간이 미국 장 시간인지 확인 (서머타임 고려)
        now_in_korea = datetime.now(pytz.timezone('Asia/Seoul'))
        
        # 미국 뉴욕 시간 (서머타임 자동 고려)
        now_in_ny = datetime.now(pytz.timezone('America/New_York'))
        ny_hour = now_in_ny.hour
        ny_minute = now_in_ny.minute
        ny_weekday = now_in_ny.weekday()  # 0=월요일, 6=일요일
        
        # 매도 대상 종목 조회
        sell_candidates_result = self.recommendation_service.get_stocks_to_sell()
        
        if not sell_candidates_result or not sell_candidates_result.get("sell_candidates"):
            return
        
        sell_candidates = sell_candidates_result.get("sell_candidates", [])
        
        if not sell_candidates:
            return
        
        # 각 종목에 대해 매도 주문 실행
        for candidate in sell_candidates:
            try:
                ticker = candidate["ticker"]
                stock_name = candidate["stock_name"]
                exchange_code = candidate["exchange_code"]
                quantity = candidate["quantity"]
                
                # 매도 근거
                sell_reasons = candidate.get("sell_reasons", [])
                
                # 거래소 코드 변환 (API 요청에 맞게 변환)
                api_exchange_code = exchange_code
                if exchange_code == "NASD":
                    api_exchange_code = "NAS"
                elif exchange_code == "NYSE":
                    api_exchange_code = "NYS"
                
                # 현재가 조회
                price_params = {
                    "AUTH": "",
                    "EXCD": api_exchange_code,  # 변환된 거래소 코드 사용
                    "SYMB": ticker
                }
                
                price_result = get_current_price(price_params)
                
                if price_result.get("rt_cd") != "0":
                    logger.error(f"[{function_name}] {stock_name}({ticker}) 현재가 조회 실패: {price_result.get('msg1', '알 수 없는 오류')}")
                    # API 속도 제한에 도달했을 때 더 오래 대기
                    if "초당" in price_result.get('msg1', ''):
                        await asyncio.sleep(3)  # 속도 제한 오류 시 3초 대기
                    continue
                
                # 현재가 추출 (안전하게 처리)
                last_price = price_result.get("output", {}).get("last", "")
                try:
                    # 빈 문자열이나 None 체크
                    if not last_price or last_price == "":
                        logger.error(f"[{function_name}] {stock_name}({ticker}) 현재가가 비어있습니다. 다음 API 호출에서 다시 시도합니다.")
                        await asyncio.sleep(2)  # 잠시 기다렸다가 넘어감
                        continue
                    
                    current_price = float(last_price)
                    
                    if current_price <= 0:
                        logger.error(f"[{function_name}] {stock_name}({ticker}) 현재가가 유효하지 않습니다: {current_price}")
                        continue
                except ValueError as ve:
                    logger.error(f"[{function_name}] {stock_name}({ticker}) 현재가 변환 오류: {str(ve)}, 값: '{last_price}'")
                    continue
                
                # 매도 주문 실행
                order_data = {
                    "CANO": settings.KIS_CANO,
                    "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
                    "OVRS_EXCG_CD": exchange_code,  # API 문서에 따라 원래대로 exchange_code 사용
                    "PDNO": ticker,
                    "ORD_DVSN": "00",  # 지정가
                    "ORD_QTY": str(quantity),
                    "OVRS_ORD_UNPR": str(current_price),
                    "is_buy": False  # 매도
                }
                
                order_result = order_overseas_stock(order_data)
                
                if order_result.get("rt_cd") == "0":
                    logger.info(f"[{function_name}] {stock_name}({ticker}) 매도 주문 성공: {order_result.get('msg1', '주문이 접수되었습니다.')}")
                    # Slack 알림 전송 (성공 시에만)
                    slack_notifier.send_sell_notification(
                        stock_name=stock_name,
                        ticker=ticker,
                        quantity=quantity,
                        price=current_price,
                        exchange_code=exchange_code,
                        sell_reasons=sell_reasons,
                        success=True
                    )
                else:
                    error_msg = order_result.get('msg1', '알 수 없는 오류')
                    logger.error(f"[{function_name}] {stock_name}({ticker}) 매도 주문 실패: {error_msg}")
                
                # 요청 간 지연 (API 요청 제한 방지)
                await asyncio.sleep(2)  # 1초에서 2초로 증가
                
            except Exception as e:
                logger.error(f"[{function_name}] {candidate['stock_name']}({candidate['ticker']}) 매도 처리 중 오류: {str(e)}", exc_info=True)
                await asyncio.sleep(1)  # 오류 발생 시에도 잠시 대기
    
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
            
            # 보유 종목 티커 추출
            holdings = balance_result.get("output1", [])
            holding_tickers = set()
            
            for item in holdings:
                ticker = item.get("ovrs_pdno")
                if ticker:
                    holding_tickers.add(ticker)
            
            logger.info(f"[{function_name}] 현재 보유 중인 종목 수: {len(holding_tickers)}")
            
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
        
        buy_candidates = recommendations.get("results", [])
        
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
        
        # MongoDB에서 사용자 정보 조회 (레버리지 설정 확인용)
        user_leverage_map = {}  # ticker -> (use_leverage, leverage_ticker)
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
                        leverage_ticker = stock.get("leverage_ticker")
                        
                        if ticker:
                            user_leverage_map[ticker] = {
                                "use_leverage": use_leverage,
                                "leverage_ticker": leverage_ticker
                            }
                    
                    logger.info(f"[{function_name}] 사용자 '{user_id}'의 레버리지 설정 로드 완료: {len(user_leverage_map)}개 종목")
                else:
                    logger.warning(f"[{function_name}] 사용자 '{user_id}' 정보를 찾을 수 없거나 종목 정보가 없습니다.")
            else:
                logger.warning(f"[{function_name}] MongoDB 연결 실패 - 레버리지 설정을 사용할 수 없습니다.")
        except Exception as e:
            logger.error(f"[{function_name}] 사용자 레버리지 설정 조회 중 오류: {str(e)}", exc_info=True)
        
        # 성공한 매수 건수 추적
        successful_purchases = 0
        skipped_no_cash = 0
        
        # 각 종목에 대해 API 호출하여 현재 체결가 조회 및 매수 주문
        # buy_candidates는 이미 composite_score 순으로 정렬되어 있음
        for candidate in buy_candidates:
            try:
                ticker = candidate["ticker"]
                stock_name = candidate["stock_name"]
                
                # 사용자의 레버리지 설정 확인
                actual_ticker = ticker  # 기본값은 원래 티커
                if ticker in user_leverage_map:
                    leverage_info = user_leverage_map[ticker]
                    if leverage_info["use_leverage"] and leverage_info["leverage_ticker"]:
                        actual_ticker = leverage_info["leverage_ticker"]
                        logger.info(f"[{function_name}] {stock_name}({ticker}) - 레버리지 활성화, {actual_ticker}로 매수")
                    else:
                        logger.info(f"[{function_name}] {stock_name}({ticker}) - 일반 티커로 매수")
                else:
                    logger.info(f"[{function_name}] {stock_name}({ticker}) - 사용자 설정 없음, 일반 티커로 매수")                
                # 거래소 코드 결정 (미국 주식 기준)
                if actual_ticker.endswith(".X") or actual_ticker.endswith(".N"):
                    # 거래소 구분이 티커에 포함된 경우
                    exchange_code = "NYSE" if actual_ticker.endswith(".N") else "NASD"
                    pure_ticker = actual_ticker.split(".")[0]
                else:
                    # 기본값 NASDAQ으로 설정
                    exchange_code = "NASD"
                    pure_ticker = actual_ticker
                
                # 이미 보유 중인 종목인지 확인
                # if pure_ticker in holding_tickers:
                #     logger.info(f"[{function_name}] {stock_name}({ticker}) - 이미 보유 중인 종목이므로 매수하지 않습니다.")
                #     continue
                
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
                    logger.error(f"[{function_name}] {stock_name}({ticker}) 현재가 조회 실패: {price_result.get('msg1', '알 수 없는 오류')}")
                    continue
                
                # 현재가 추출
                last_price = price_result.get("output", {}).get("last", 0) or 0
                try:
                    current_price = float(last_price)
                except (ValueError, TypeError) as e:
                    logger.error(f"[{function_name}] {stock_name}({ticker}) 현재가 변환 실패: {last_price}, 오류: {str(e)}")
                    continue
                
                if current_price <= 0:
                    logger.error(f"[{function_name}] {stock_name}({ticker}) 현재가가 유효하지 않습니다: {current_price}")
                    continue
                
                # 매수 가능 여부 확인
                estimated_cost = current_price  # 1주 기준
                
                if available_cash < estimated_cost:
                    logger.warning(f"[{function_name}] {stock_name}({ticker}) - 잔고 부족으로 매수 건너뜀. 필요금액: ${estimated_cost:.2f}, 잔고: ${available_cash:.2f}")
                    skipped_no_cash += 1
                    continue
                
                # 매수 수량 계산: 기본 1주
                quantity = 1
                
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
                    "is_buy": True
                }
                
                logger.info(f"[{function_name}] {stock_name}({actual_ticker}) 매수 주문 실행: 수량 {quantity}주, 가격 ${current_price}")
                order_result = order_overseas_stock(order_data)
                
                if order_result.get("rt_cd") == "0":
                    logger.info(f"[{function_name}] {stock_name}({ticker}) 매수 주문 성공: {order_result.get('msg1', '주문이 접수되었습니다.')}")
                    
                    # 매수 성공 시 잔고 차감
                    available_cash -= (current_price * quantity)
                    successful_purchases += 1
                    logger.info(f"[{function_name}] 매수 후 잔고: ${available_cash:,.2f}")
                    
                    # 개별 알림은 제거하고 요약 알림만 사용 (중복 방지)
                else:
                    error_msg = order_result.get('msg1', '알 수 없는 오류')
                    logger.error(f"[{function_name}] {stock_name}({ticker}) 매수 주문 실패: {error_msg}")
                
                # 요청 간 지연 (API 요청 제한 방지)
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"[{function_name}] {candidate['stock_name']}({candidate['ticker']}) 매수 처리 중 오류: {str(e)}", exc_info=True)
        
        # 매수 처리 완료 요약
        logger.info("=" * 60)
        logger.info(f"[{function_name}] 자동 매수 처리가 완료되었습니다.")
        logger.info(f"[{function_name}] 총 매수 대상: {len(buy_candidates)}개")
        logger.info(f"[{function_name}] 매수 성공: {successful_purchases}개")
        logger.info(f"[{function_name}] 잔고 부족으로 건너뜀: {skipped_no_cash}개")
        logger.info(f"[{function_name}] 남은 잔고: ${available_cash:,.2f}")
        logger.info("=" * 60)
        logger.info(f"[{function_name}] 함수 실행 완료")
        
        # 매수 결과 요약 Slack 알림 (스케줄된 시간에만 전송)
        if send_slack_notification:
            if successful_purchases == 0:
                # 매수를 하나도 하지 않은 경우
                if skipped_no_cash > 0:
                    slack_notifier.send_no_buy_notification(
                        reason="잔고 부족",
                        details=f"총 매수 대상: {len(buy_candidates)}개\n잔고 부족으로 건너뜀: {skipped_no_cash}개\n현재 잔고: ${available_cash:,.2f}"
                    )
                else:
                    slack_notifier.send_no_buy_notification(
                        reason="매수 성공 없음",
                        details=f"총 매수 대상: {len(buy_candidates)}개\n매수 성공: 0개\n남은 잔고: ${available_cash:,.2f}"
                    )
            else:
                # 매수 성공한 경우 요약 알림
                summary_message = (
                    f"✅ *자동 매수 작업 완료*\n"
                    f"총 매수 대상: {len(buy_candidates)}개\n"
                    f"매수 성공: {successful_purchases}개\n"
                    f"잔고 부족으로 건너뜀: {skipped_no_cash}개\n"
                    f"남은 잔고: ${available_cash:,.2f}"
                )
                send_scheduler_slack_notification(summary_message)

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

def send_scheduler_slack_notification(message: str):
    """스케줄러 실행 알림을 Slack으로 전송"""
    webhook_url = settings.SLACK_WEBHOOK_URL_SCHEDULER
    if not webhook_url:
        return
    
    try:
        now_korea = datetime.now(pytz.timezone('Asia/Seoul'))
        formatted_message = f"📅 *스케줄러 알림*\n{message}\n\n🕒 {now_korea.strftime('%Y-%m-%d %H:%M:%S')} (KST)"
        
        payload = {"text": formatted_message}
        with httpx.Client(timeout=10.0) as client:
            response = client.post(webhook_url, json=payload)
            if response.status_code == 200:
                logger.debug(f"스케줄러 Slack 알림 전송 성공: {message}")
            else:
                logger.warning(f"스케줄러 Slack 알림 전송 실패: {response.status_code}")
    except Exception as e:
        logger.warning(f"스케줄러 Slack 알림 전송 중 오류: {str(e)}")
 