"""
Vertex AI 동적 워크로드 스케줄러(DWS)를 사용하여 predict.py를 실행하는 스크립트

이 스크립트는 Vertex AI CustomJob을 사용하여 predict.py를 실행합니다.
FLEX_START 스케줄링 전략을 사용하여 GPU 리소스가 사용 가능해질 때까지 대기합니다.

사용법:
    python run_predict_vertex_ai.py

환경 변수:
    GCP_PROJECT_ID: Google Cloud 프로젝트 ID
    GCP_REGION: 리전 (예: us-central1)
    SUPABASE_URL: Supabase URL
    SUPABASE_KEY: Supabase Key
    GOOGLE_APPLICATION_CREDENTIALS: Google Cloud 인증 정보 파일 경로
"""

import os
import sys
from pathlib import Path
from typing import Optional
import logging
from dotenv import load_dotenv

# 로깅 설정 (먼저 초기화)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# .env 파일 로드 (프로젝트 루트에서)
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    load_dotenv(env_file)
    logger.info(f".env 파일 로드 완료: {env_file}")
else:
    # 상위 디렉토리에서도 시도
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        logger.info(f".env 파일 로드 완료: {env_file}")
    else:
        logger.warning(f".env 파일을 찾을 수 없습니다. 환경 변수를 직접 설정하세요.")

# vertex-ai-key.json 파일 자동 찾기 및 설정
if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
    # 여러 경로에서 vertex-ai-key.json 찾기
    possible_paths = [
        Path(__file__).parent / "credentials" / "vertex-ai-key.json",
        Path(__file__).parent.parent / "credentials" / "vertex-ai-key.json",
        Path(__file__).parent / "vertex-ai-key.json",
    ]
    
    for creds_path in possible_paths:
        if creds_path.exists():
            abs_path = str(creds_path.resolve())
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = abs_path
            logger.info(f"✅ vertex-ai-key.json 파일 자동 설정: {abs_path}")
            break
    else:
        logger.warning("⚠️ vertex-ai-key.json 파일을 찾을 수 없습니다.")

# Vertex AI SDK
from google.cloud import aiplatform
from google.cloud.aiplatform_v1.types import custom_job as gca_custom_job_compat
from google.cloud import storage


def get_env_var(var_name: str, default: Optional[str] = None) -> str:
    """환경 변수를 가져오고 없으면 에러를 발생시킵니다."""
    value = os.getenv(var_name, default)
    if value is None:
        raise ValueError(f"환경 변수 {var_name}이 설정되지 않았습니다.")
    return value


def check_authentication() -> bool:
    """
    Google Cloud 인증이 제대로 설정되어 있는지 확인합니다.
    
    Returns:
        인증이 설정되어 있으면 True, 아니면 False
    """
    try:
        # 환경 변수로 인증 정보 확인
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if creds_path:
            if os.path.exists(creds_path):
                logger.info(f"✅ 서비스 계정 키 파일 발견: {creds_path}")
                return True
            else:
                logger.warning(f"⚠️ 인증 파일 경로가 설정되었지만 파일이 존재하지 않습니다: {creds_path}")
        
        # vertex-ai-key.json 자동 찾기 시도
        possible_paths = [
            Path(__file__).parent / "credentials" / "vertex-ai-key.json",
            Path(__file__).parent.parent / "credentials" / "vertex-ai-key.json",
            Path(__file__).parent / "vertex-ai-key.json",
        ]
        
        for creds_path in possible_paths:
            if creds_path.exists():
                abs_path = str(creds_path.resolve())
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = abs_path
                logger.info(f"✅ vertex-ai-key.json 파일 자동 발견 및 설정: {abs_path}")
                return True
        
        # gcloud CLI 인증 확인
        try:
            from google.auth import default
            credentials, project = default()
            logger.info(f"✅ gcloud CLI 인증 확인 완료")
            return True
        except Exception as e:
            logger.warning(f"gcloud CLI 인증 확인 실패: {e}")
            return False
            
    except Exception as e:
        logger.warning(f"인증 확인 중 오류: {e}")
        return False


def ensure_bucket_exists(bucket_name: str, project: str, location: str) -> bool:
    """
    Cloud Storage 버킷이 존재하는지 확인하고, 없으면 생성합니다.
    
    Args:
        bucket_name: 버킷 이름
        project: Google Cloud 프로젝트 ID
        location: 리전 (예: us-central1)
    
    Returns:
        버킷이 존재하거나 생성되었으면 True, 실패하면 False
    """
    try:
        storage_client = storage.Client(project=project)
        
        # 버킷 존재 여부 확인
        try:
            bucket = storage_client.bucket(bucket_name)
            if bucket.exists():
                logger.info(f"✅ 버킷이 이미 존재합니다: {bucket_name}")
                return True
        except Exception as e:
            logger.warning(f"버킷 확인 중 오류: {e}")
        
        # 버킷이 없으면 생성
        logger.info(f"버킷이 없습니다. 생성 중: {bucket_name}")
        bucket = storage_client.create_bucket(
            bucket_name,
            location=location
        )
        logger.info(f"✅ 버킷 생성 완료: {bucket_name}")
        return True
        
    except Exception as e:
        logger.error(f"❌ 버킷 생성 실패: {e}")
        logger.error("=" * 60)
        logger.error("버킷을 수동으로 생성하려면 다음 명령을 실행하세요:")
        logger.error(f"  gsutil mb -p {project} -l {location} gs://{bucket_name}")
        logger.error("=" * 60)
        return False


def create_custom_job_with_dws(
    project: str,
    location: str,
    staging_bucket: str,
    display_name: str,
    script_path: Optional[str] = None,  # 로컬 파일 경로 (deprecated: package_uri 사용 권장)
    package_uri: Optional[str] = None,  # GCS에 있는 tar.gz 패키지 URI (gs://bucket/package.tar.gz)
    python_module: str = "aiplatform_custom_trainer_script.task",  # 실행할 Python 모듈
    container_uri: Optional[str] = None,
    service_account: Optional[str] = None,
    machine_type: str = "n1-standard-4",
    accelerator_type: str = "NVIDIA_TESLA_T4",
    accelerator_count: int = 1,
    max_wait_duration: int = 1800,  # 30분 (초 단위)
    timeout: int = 3600,  # 1시간 (초 단위)
    environment_variables: Optional[dict] = None,
) -> str:
    """
    동적 워크로드 스케줄러(DWS)를 사용하여 CustomJob을 생성하고 실행합니다.
    
    Args:
        project: Google Cloud 프로젝트 ID
        location: 리전 (예: us-central1)
        staging_bucket: Cloud Storage 버킷 이름
        display_name: Job 표시 이름
        script_path: 실행할 Python 스크립트 경로 (로컬 파일, deprecated: package_uri 사용 권장)
        package_uri: GCS에 있는 tar.gz 패키지 URI (예: gs://bucket/package.tar.gz)
        python_module: 실행할 Python 모듈 (기본값: aiplatform_custom_trainer_script.task)
        container_uri: 커스텀 컨테이너 이미지 URI (None이면 TensorFlow GPU 컨테이너 사용)
        service_account: 서비스 계정 이메일 (선택사항)
        machine_type: 머신 타입 (기본값: n1-standard-4)
        accelerator_type: GPU 타입 (기본값: NVIDIA_TESLA_T4)
        accelerator_count: GPU 개수 (기본값: 1)
        max_wait_duration: 리소스를 기다릴 수 있는 최대 시간 (초, 기본값: 1800 = 30분)
        timeout: Job 실행 최대 시간 (초, 기본값: 3600 = 1시간)
        environment_variables: 환경 변수 딕셔너리
    
    Returns:
        Job 이름 (리소스 이름)
    """
    logger.info("=" * 60)
    logger.info("Vertex AI CustomJob 생성 시작 (DWS 사용)")
    logger.info("=" * 60)
    
    # Vertex AI 초기화
    aiplatform.init(
        project=project,
        location=location,
        staging_bucket=staging_bucket
    )
    
    logger.info(f"프로젝트: {project}")
    logger.info(f"리전: {location}")
    logger.info(f"스테이징 버킷: {staging_bucket}")
    logger.info(f"머신 타입: {machine_type}")
    logger.info(f"GPU 타입: {accelerator_type}")
    logger.info(f"GPU 개수: {accelerator_count}")
    logger.info(f"최대 대기 시간: {max_wait_duration}초 ({max_wait_duration/60:.1f}분)")
    logger.info(f"최대 실행 시간: {timeout}초 ({timeout/60:.1f}분)")
    
    # package_uri 또는 script_path 확인
    use_existing_package = package_uri is not None
    temp_script_path = None  # 임시 파일 경로 추적용
    
    if use_existing_package:
        # 이미 생성된 패키지 사용
        if not package_uri.startswith("gs://"):
            raise ValueError(f"package_uri는 GCS URI 형식이어야 합니다: {package_uri}")
        logger.info(f"기존 패키지 사용: {package_uri}")
        
        # 패키지 존재 확인
        from google.cloud import storage as gcs_storage
        gcs_path_parts = package_uri.replace("gs://", "").split("/", 1)
        gcs_bucket_name = gcs_path_parts[0]
        gcs_blob_name = gcs_path_parts[1] if len(gcs_path_parts) > 1 else ""
        
        storage_client = gcs_storage.Client(project=project)
        bucket = storage_client.bucket(gcs_bucket_name)
        blob = bucket.blob(gcs_blob_name)
        
        if not blob.exists():
            raise FileNotFoundError(f"GCS에서 패키지 파일을 찾을 수 없습니다: {package_uri}")
        logger.info(f"패키지 파일 확인 완료: {package_uri}")
        
    elif script_path:
        # 로컬 스크립트 사용 (기존 방식)
        logger.info(f"로컬 스크립트 사용: {script_path}")
        script_path_obj = Path(script_path)
        if not script_path_obj.exists():
            raise FileNotFoundError(f"로컬 스크립트 파일을 찾을 수 없습니다: {script_path}")
        logger.info(f"로컬 스크립트 파일 확인 완료: {script_path}")
    else:
        raise ValueError("package_uri 또는 script_path 중 하나는 반드시 제공해야 합니다.")
    
    # 환경 변수 설정
    env_vars = environment_variables or {}
    
    # Supabase 환경 변수 추가 (없으면 기본값 사용)
    if "SUPABASE_URL" not in env_vars:
        supabase_url = os.getenv("SUPABASE_URL")
        if supabase_url:
            env_vars["SUPABASE_URL"] = supabase_url
    
    if "SUPABASE_KEY" not in env_vars:
        supabase_key = os.getenv("SUPABASE_KEY")
        if supabase_key:
            env_vars["SUPABASE_KEY"] = supabase_key
    
    logger.info(f"환경 변수 개수: {len(env_vars)}")
    if env_vars:
        logger.info(f"환경 변수 키: {list(env_vars.keys())}")
    
        # CustomJob 생성
    try:
        # container_uri 설정
        if not container_uri:
            container_uri = "us-docker.pkg.dev/vertex-ai/training/tf-gpu.2-11.py310:latest"
            logger.info(f"컨테이너 URI가 지정되지 않아 기본값 사용: {container_uri}")
        else:
            logger.info(f"커스텀 컨테이너 사용: {container_uri}")
        
        # predict.py에 필요한 패키지 목록
        required_packages = [
            "supabase>=2.0.0",
            "pandas>=2.0.0",
            "numpy>=1.24.0",
            "scikit-learn>=1.3.0",
            "tensorflow>=2.11.0",
            "matplotlib>=3.7.0",
        ]
        
        if use_existing_package:
            # 이미 생성된 패키지 사용
            logger.info("=" * 60)
            logger.info("CustomJob 생성 (기존 패키지 사용)")
            logger.info("=" * 60)
            logger.info(f"  display_name: {display_name}")
            logger.info(f"  package_uri: {package_uri}")
            logger.info(f"  python_module: {python_module}")
            logger.info(f"  container_uri: {container_uri}")
            logger.info(f"  machine_type: {machine_type}")
            logger.info(f"  accelerator_type: {accelerator_type}")
            logger.info(f"  accelerator_count: {accelerator_count}")
            logger.info(f"  requirements: {required_packages}")
            logger.info(f"  environment_variables: {len(env_vars) if env_vars else 0}개")
            logger.info("=" * 60)
            
            # CustomJob을 직접 구성
            from google.cloud.aiplatform_v1.types import custom_job as gca_custom_job
            from google.cloud.aiplatform_v1.types import io as gca_io
            from google.cloud.aiplatform_v1.types import machine_resources
            
            # WorkerPoolSpec 생성
            # 환경 변수를 WorkerPoolSpec에 추가
            env_vars_list = []
            if env_vars:
                from google.cloud import aiplatform_v1
                for key, value in env_vars.items():
                    env_vars_list.append(
                        aiplatform_v1.types.EnvVar(name=key, value=str(value))
                    )
                logger.info(f"환경 변수 {len(env_vars_list)}개를 WorkerPoolSpec에 추가합니다: {list(env_vars.keys())}")
            
            # PythonPackageSpec 생성 (환경 변수 포함)
            python_package_spec = gca_custom_job.PythonPackageSpec(
                executor_image_uri=container_uri,
                package_uris=[package_uri],
                python_module=python_module,
            )
            
            # 환경 변수가 있으면 PythonPackageSpec에 추가
            if env_vars_list:
                python_package_spec.env = env_vars_list
            
            worker_pool_spec = gca_custom_job.WorkerPoolSpec(
                machine_spec=machine_resources.MachineSpec(
                    machine_type=machine_type,
                    accelerator_type=accelerator_type,
                    accelerator_count=accelerator_count,
                ),
                replica_count=1,
                python_package_spec=python_package_spec,
            )
            
            # CustomJob 생성
            # base_output_dir은 문자열로 전달 (GcsDestination 객체가 아닌)
            base_output_uri = f"gs://{staging_bucket}"
            job = aiplatform.CustomJob(
                display_name=display_name,
                worker_pool_specs=[worker_pool_spec],
                base_output_dir=base_output_uri,
            )
            
            if env_vars:
                logger.info(f"✅ 환경 변수가 WorkerPoolSpec에 설정되었습니다: {list(env_vars.keys())}")
            
            logger.info("기존 패키지를 사용한 CustomJob 객체 생성 완료")
        else:
            # 로컬 스크립트 사용 (기존 방식)
            logger.info("=" * 60)
            logger.info("CustomJob 생성 (로컬 스크립트 사용)")
            logger.info("=" * 60)
            logger.info(f"  display_name: {display_name}")
            logger.info(f"  script_path: {script_path}")
            logger.info(f"  container_uri: {container_uri}")
            logger.info(f"  machine_type: {machine_type}")
            logger.info(f"  accelerator_type: {accelerator_type}")
            logger.info(f"  accelerator_count: {accelerator_count}")
            logger.info(f"  requirements: {required_packages}")
            logger.info(f"  environment_variables: {len(env_vars) if env_vars else 0}개")
            logger.info("=" * 60)
            
            job_kwargs = {
                "display_name": display_name,
                "script_path": script_path,
                "container_uri": container_uri,
                "machine_type": machine_type,
                "accelerator_type": accelerator_type,
                "accelerator_count": accelerator_count,
                "requirements": required_packages,
            }
            
            if env_vars:
                job_kwargs["environment_variables"] = env_vars
            
            logger.info(f"from_local_script 호출 시작...")
            job = aiplatform.CustomJob.from_local_script(**job_kwargs)
            logger.info(f"from_local_script 호출 완료")
        
        logger.info(f"from_local_script 호출 완료")
        
        logger.info(f"CustomJob 객체 생성 완료: {display_name}")
        
        # DWS(FLEX_START) 지원 여부 확인
        # DWS는 L4, A100, H100, H200, B200만 지원 (T4는 지원 안 함)
        # 단, FLEX_START는 preemptible 인스턴스를 사용하므로 할당량이 필요함
        flex_start_supported_gpus = [
            "NVIDIA_L4",
            "NVIDIA_TESLA_A100",
            "NVIDIA_A100_80GB",
            "NVIDIA_H100_80GB",
            "NVIDIA_H200",
            "NVIDIA_B200"
        ]
        
        # 환경 변수로 FLEX_START 사용 여부 제어 (기본값: true)
        use_flex_start_env = os.getenv("VERTEX_AI_USE_FLEX_START", "true").lower()
        use_flex_start = (
            accelerator_type in flex_start_supported_gpus and 
            use_flex_start_env == "true"
        )
        
        if use_flex_start:
            logger.info("=" * 60)
            logger.info("CustomJob 실행 시작 (FLEX_START 스케줄링 전략)")
            logger.info("=" * 60)
            logger.info(f"GPU 타입 {accelerator_type}은 FLEX_START를 지원합니다.")
            logger.info("GPU 리소스가 사용 가능해질 때까지 대기 중...")
            
            job.run(
                service_account=service_account,
                max_wait_duration=max_wait_duration,
                timeout=timeout,
                scheduling_strategy=gca_custom_job_compat.Scheduling.Strategy.FLEX_START
            )
        else:
            logger.info("=" * 60)
            logger.info("CustomJob 실행 시작 (일반 스케줄링)")
            logger.info("=" * 60)
            logger.warning(f"⚠️ GPU 타입 {accelerator_type}은 FLEX_START를 지원하지 않습니다.")
            logger.warning(f"일반 스케줄링으로 실행됩니다.")
            logger.info(f"FLEX_START를 사용하려면 다음 GPU 중 하나를 사용하세요:")
            logger.info(f"  {', '.join(flex_start_supported_gpus)}")
            
            # 일반 스케줄링으로 실행 (FLEX_START 없이)
            job.run(
                service_account=service_account,
                timeout=timeout,
                # scheduling_strategy는 지정하지 않음 (기본 스케줄링 사용)
            )
        
        logger.info("=" * 60)
        logger.info("CustomJob 실행 완료")
        logger.info("=" * 60)
        
        # 임시 파일 정리 (GCS에서 다운로드한 경우)
        if temp_script_path and os.path.exists(temp_script_path):
            try:
                os.remove(temp_script_path)
                logger.info(f"임시 파일 삭제 완료: {temp_script_path}")
            except Exception as e:
                logger.warning(f"임시 파일 삭제 실패 (무시 가능): {e}")
        
        # run() 호출 후에 리소스 정보 접근 가능
        try:
            logger.info(f"Job 상태: {job.state}")
            logger.info(f"Job 이름: {job.name}")
            logger.info(f"Job 리소스 이름: {job.resource_name}")
            logger.info(f"Job 대시보드: https://console.cloud.google.com/vertex-ai/training/custom-jobs/{job.name}?project={project}")
        except Exception as e:
            logger.warning(f"Job 정보 조회 중 오류 (무시 가능): {e}")
            logger.info(f"Job 대시보드: https://console.cloud.google.com/vertex-ai/training/custom-jobs?project={project}")
            
        return job.name if hasattr(job, 'name') else None
        
    except Exception as e:
        logger.error(f"CustomJob 실행 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        raise


def main():
    """메인 함수"""
    try:
        # .env 파일에서 환경 변수 로드 확인
        logger.info("=" * 60)
        logger.info(".env 파일에서 환경 변수 로드 확인")
        logger.info("=" * 60)
        
        # 주요 환경 변수 확인 (디버깅용)
        env_vars_to_check = [
            "GCP_PROJECT_ID", "GCP_REGION", "GCP_BUCKET_NAME", "GCP_STAGING_BUCKET",
            "SUPABASE_URL", "SUPABASE_KEY",
            "VERTEX_AI_GPU_TYPE", "VERTEX_AI_MACHINE_TYPE", "VERTEX_AI_GPU_COUNT",
            "GOOGLE_APPLICATION_CREDENTIALS"
        ]
        for var in env_vars_to_check:
            value = os.getenv(var)
            if value:
                # 민감한 정보는 일부만 표시
                if "KEY" in var or "SECRET" in var:
                    logger.info(f"  {var}: {'*' * min(len(value), 20)}...")
                else:
                    logger.info(f"  {var}: {value}")
            else:
                logger.warning(f"  {var}: 설정되지 않음 (기본값 사용)")
        
        logger.info("=" * 60)
        
        # Google Cloud 인증 확인
        logger.info("Google Cloud 인증 확인 중...")
        if not check_authentication():
            logger.warning("⚠️ Google Cloud 인증이 설정되지 않았습니다.")
            logger.warning("다음 명령을 실행하여 인증을 설정하세요:")
            logger.warning("  gcloud auth application-default login")
            logger.warning("또는 .env 파일에 GOOGLE_APPLICATION_CREDENTIALS를 설정하세요.")
            logger.warning("계속 진행하지만 인증 오류가 발생할 수 있습니다...")
        logger.info("=" * 60)
        
        # 환경 변수에서 설정 가져오기
        project = get_env_var("GCP_PROJECT_ID")
        location = get_env_var("GCP_REGION", "us-central1")
        
        # 스테이징 버킷 (.env 파일의 GCP_BUCKET_NAME 또는 GCP_STAGING_BUCKET 사용)
        staging_bucket = os.getenv("GCP_STAGING_BUCKET") or os.getenv("GCP_BUCKET_NAME")
        if not staging_bucket:
            # 둘 다 없으면 기본값 사용
            staging_bucket = f"{project}-vertex-ai-staging"
            logger.warning(f"GCP_STAGING_BUCKET 또는 GCP_BUCKET_NAME이 설정되지 않아 기본값 사용: {staging_bucket}")
        else:
            logger.info(f"버킷 이름: {staging_bucket} (.env에서 로드됨)")
        
        # 버킷 이름에서 'gs://' 접두사 제거
        if staging_bucket.startswith("gs://"):
            staging_bucket = staging_bucket[5:]
        
        # 버킷이 존재하는지 확인하고 없으면 생성
        logger.info("=" * 60)
        logger.info("Cloud Storage 버킷 확인 중...")
        logger.info("=" * 60)
        if not ensure_bucket_exists(staging_bucket, project, location):
            logger.error("버킷 생성에 실패했습니다. 수동으로 생성 후 다시 시도하세요.")
            sys.exit(1)
        
        # 패키지 URI 또는 스크립트 경로 설정
        # 1순위: VERTEX_AI_PACKAGE_URI (GCS에 있는 tar.gz 패키지)
        # 2순위: PREDICT_SCRIPT_PATH (로컬 파일)
        package_uri = os.getenv("VERTEX_AI_PACKAGE_URI")
        script_path = None
        
        if package_uri:
            logger.info(f"패키지 URI 사용: {package_uri} (VERTEX_AI_PACKAGE_URI 환경 변수)")
        else:
            script_path = os.getenv("PREDICT_SCRIPT_PATH")
            if script_path:
                logger.info(f"스크립트 경로 사용: {script_path} (PREDICT_SCRIPT_PATH 환경 변수)")
            else:
                # 기본값: 가장 최신 버전의 패키지 사용
                package_uri = None
                logger.info("패키지 URI나 스크립트 경로가 설정되지 않았습니다.")
                logger.info("GCS에서 가장 최신 버전의 패키지를 찾는 중...")
                
                # GCS에서 최신 버전 패키지 찾기
                from google.cloud import storage as gcs_storage
                import json
                import re
                
                storage_client = gcs_storage.Client(project=project)
                bucket = storage_client.bucket(staging_bucket)
                
                # 방법 1: 버전 파일에서 최신 버전 읽기
                version_blob = bucket.blob("predict-package-version.json")
                if version_blob.exists():
                    try:
                        version_data = json.loads(version_blob.download_as_text())
                        latest_version = version_data.get("version", 0)
                        package_name = f"predict-package-v{latest_version}.tar.gz"
                        package_path = f"packages/{package_name}"
                        
                        # 패키지 파일 존재 확인
                        package_blob = bucket.blob(package_path)
                        if package_blob.exists():
                            package_uri = f"gs://{staging_bucket}/{package_path}"
                            logger.info(f"✅ 최신 버전 패키지 발견: v{latest_version}")
                            logger.info(f"패키지 URI: {package_uri}")
                        else:
                            logger.warning(f"버전 파일에는 v{latest_version}이 있지만 파일이 없습니다. 패턴 검색으로 찾는 중...")
                            package_uri = None  # 방법 2로 폴백
                    except Exception as e:
                        logger.warning(f"버전 파일 읽기 실패: {e}")
                        package_uri = None  # 방법 2로 폴백
                
                # 방법 2: 패키지 파일 패턴으로 최대 버전 찾기
                if not package_uri:
                    blobs = list(bucket.list_blobs(prefix="packages/predict-package-v"))
                    version_pattern = re.compile(r'predict-package-v(\d+)\.tar\.gz')
                    
                    max_version = 0
                    latest_package_blob = None
                    
                    for blob in blobs:
                        match = version_pattern.search(blob.name)
                        if match:
                            version = int(match.group(1))
                            if version > max_version:
                                max_version = version
                                latest_package_blob = blob
                    
                    if latest_package_blob:
                        package_uri = f"gs://{staging_bucket}/{latest_package_blob.name}"
                        logger.info(f"✅ 최신 버전 패키지 발견: v{max_version}")
                        logger.info(f"패키지 URI: {package_uri}")
                    else:
                        # 방법 3: 기존 aiplatform-*.tar.gz 패턴 (레거시)
                        logger.warning("predict-package-v*.tar.gz 패턴의 파일을 찾을 수 없습니다.")
                        logger.warning("레거시 aiplatform-*.tar.gz 패턴을 검색 중...")
                        
                        legacy_blobs = list(bucket.list_blobs(prefix="aiplatform-"))
                        if legacy_blobs:
                            legacy_blobs.sort(key=lambda x: x.time_created, reverse=True)
                            latest_package = legacy_blobs[0]
                            package_uri = f"gs://{staging_bucket}/{latest_package.name}"
                            logger.warning(f"레거시 패키지 사용: {package_uri}")
                        else:
                            raise ValueError(
                                "GCS에서 패키지를 찾을 수 없습니다. "
                                "다음 중 하나를 수행하세요:\n"
                                "  1. VERTEX_AI_PACKAGE_URI 환경 변수를 설정\n"
                                "  2. python upload_to_gcs.py로 패키지 업로드\n"
                                "  3. PREDICT_SCRIPT_PATH로 로컬 스크립트 사용"
                            )
        
        # Job 설정
        display_name = get_env_var(
            "VERTEX_AI_JOB_NAME",
            "stock-prediction-dws-job"
        )
        
        # 머신 및 GPU 설정 (.env 파일의 값 우선 사용)
        # GPU 타입별 머신 타입 매핑
        gpu_machine_mapping = {
            "NVIDIA_TESLA_T4": "n1-standard-4",
            "NVIDIA_L4": "g2-standard-4",
            "NVIDIA_TESLA_A100": "a2-highgpu-1g",
            "NVIDIA_A100_80GB": "a2-highgpu-1g",
            "NVIDIA_H100_80GB": "a3-highgpu-1g",
            "NVIDIA_H200": "a3-highgpu-1g",
            "NVIDIA_B200": "a3-highgpu-1g",
        }
        
        accelerator_type = os.getenv("VERTEX_AI_GPU_TYPE", "NVIDIA_TESLA_T4")
        accelerator_count = int(os.getenv("VERTEX_AI_GPU_COUNT", "1"))
        
        # 머신 타입이 명시적으로 설정되지 않았으면 GPU 타입에 맞는 기본값 사용
        machine_type = os.getenv("VERTEX_AI_MACHINE_TYPE")
        if not machine_type and accelerator_type in gpu_machine_mapping:
            machine_type = gpu_machine_mapping[accelerator_type]
            logger.info(f"머신 타입이 설정되지 않아 GPU 타입에 맞는 기본값 사용: {machine_type}")
        elif not machine_type:
            machine_type = "n1-standard-4"  # 기본값
            logger.warning(f"GPU 타입 {accelerator_type}에 대한 기본 머신 타입이 없어 기본값 사용: {machine_type}")
        
        logger.info(f"머신 타입: {machine_type} (.env에서 로드됨)")
        logger.info(f"GPU 타입: {accelerator_type} (.env에서 로드됨)")
        logger.info(f"GPU 개수: {accelerator_count} (.env에서 로드됨)")
        
        # 대기 시간 설정 (초 단위)
        # 기본값: 1800초 (30분), 0이면 무제한 대기
        max_wait_duration = int(get_env_var(
            "VERTEX_AI_MAX_WAIT_DURATION",
            "1800"
        ))
        
        # 타임아웃 설정 (초 단위, 최대 7일 = 604800초)
        timeout = int(get_env_var(
            "VERTEX_AI_TIMEOUT",
            "3600"  # 1시간
        ))
        
        # 서비스 계정 (선택사항)
        service_account = os.getenv("VERTEX_AI_SERVICE_ACCOUNT")
        
        # 커스텀 컨테이너 URI
        # .env에 설정되어 있으면 사용, 없으면 기본값 사용
        container_uri = os.getenv("VERTEX_AI_CONTAINER_URI")
        if container_uri:
            logger.info(f"컨테이너 URI: {container_uri} (.env에서 로드됨)")
        else:
            logger.info("컨테이너 URI: .env에 설정되지 않음 (기본값 사용 예정)")
        
        # 환경 변수 딕셔너리
        environment_variables = {}
        
        # Supabase 환경 변수 추가
        if os.getenv("SUPABASE_URL"):
            environment_variables["SUPABASE_URL"] = os.getenv("SUPABASE_URL")
        if os.getenv("SUPABASE_KEY"):
            environment_variables["SUPABASE_KEY"] = os.getenv("SUPABASE_KEY")
        
        # Python 모듈 경로 (기본값)
        python_module = os.getenv("VERTEX_AI_PYTHON_MODULE", "aiplatform_custom_trainer_script.task")
        
        # CustomJob 생성 및 실행
        create_custom_job_with_dws(
            project=project,
            location=location,
            staging_bucket=staging_bucket,
            display_name=display_name,
            script_path=script_path,
            package_uri=package_uri,
            python_module=python_module,
            container_uri=container_uri,
            service_account=service_account,
            machine_type=machine_type,
            accelerator_type=accelerator_type,
            accelerator_count=accelerator_count,
            max_wait_duration=max_wait_duration,
            timeout=timeout,
            environment_variables=environment_variables if environment_variables else None,
        )
        
        logger.info("✅ Job 실행이 성공적으로 완료되었습니다!")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ 오류 발생: {error_msg}")
        
        # 인증 오류인 경우 특별 안내
        if "authentication" in error_msg.lower() or "credentials" in error_msg.lower() or "auth" in error_msg.lower():
            logger.error("=" * 60)
            logger.error("🔐 Google Cloud 인증 오류")
            logger.error("=" * 60)
            logger.error("다음 중 하나의 방법으로 인증을 설정하세요:")
            logger.error("")
            logger.error("방법 1: gcloud CLI 사용 (권장)")
            logger.error("  gcloud auth application-default login")
            logger.error("")
            logger.error("방법 2: 서비스 계정 키 파일 사용")
            logger.error("  .env 파일에 다음을 추가:")
            logger.error("  GOOGLE_APPLICATION_CREDENTIALS=path/to/credentials.json")
            logger.error("")
            logger.error("방법 3: 환경 변수로 직접 설정")
            logger.error("  export GOOGLE_APPLICATION_CREDENTIALS='path/to/credentials.json'")
            logger.error("=" * 60)
        
        # 버킷 오류인 경우
        if "bucket" in error_msg.lower() or "404" in error_msg:
            logger.error("=" * 60)
            logger.error("📦 Cloud Storage 버킷 오류")
            logger.error("=" * 60)
            logger.error("버킷이 존재하지 않거나 접근할 수 없습니다.")
            logger.error("버킷을 수동으로 생성하려면:")
            project = os.getenv("GCP_PROJECT_ID", "your-project-id")
            location = os.getenv("GCP_REGION", "us-central1")
            staging_bucket = os.getenv("GCP_STAGING_BUCKET", f"{project}-vertex-ai-staging")
            if staging_bucket.startswith("gs://"):
                staging_bucket = staging_bucket[5:]
            logger.error(f"  gsutil mb -p {project} -l {location} gs://{staging_bucket}")
            logger.error("=" * 60)
        
        # 컨테이너 이미지 오류인 경우
        if "image" in error_msg.lower() and "not supported" in error_msg.lower():
            logger.error("=" * 60)
            logger.error("🐳 컨테이너 이미지 오류")
            logger.error("=" * 60)
            logger.error("지원되지 않는 컨테이너 이미지입니다.")
            logger.error("해결 방법:")
            logger.error("  .env 파일에 올바른 Vertex AI Python 패키지 학습용 이미지를 설정하세요:")
            logger.error("  VERTEX_AI_CONTAINER_URI=us-docker.pkg.dev/vertex-ai/training/tf-gpu.2-11.py310:latest")
            logger.error("  또는 다른 버전:")
            logger.error("  VERTEX_AI_CONTAINER_URI=us-docker.pkg.dev/vertex-ai/training/tf-gpu.2-13.py310:latest")
            logger.error("=" * 60)
        
        # container_uri 필수 인자 오류인 경우
        if "missing 1 required positional argument: 'container_uri'" in error_msg:
            logger.error("=" * 60)
            logger.error("🐳 container_uri 필수 인자 오류")
            logger.error("=" * 60)
            logger.error("SDK 버전에 따라 container_uri가 필수입니다.")
            logger.error("현재 container_uri 값:")
            container_uri_debug = os.getenv("VERTEX_AI_CONTAINER_URI", "None (설정되지 않음)")
            logger.error(f"  VERTEX_AI_CONTAINER_URI: {container_uri_debug}")
            logger.error("해결 방법:")
            logger.error("  .env 파일에 다음을 추가하세요:")
            logger.error("  VERTEX_AI_CONTAINER_URI=us-docker.pkg.dev/vertex-ai/training/tf-gpu.2-11.py310:latest")
            logger.error("=" * 60)
        
        # FLEX_START 지원 안 되는 GPU 오류인 경우
        if "flex_start" in error_msg.lower() and "not supported" in error_msg.lower():
            logger.error("=" * 60)
            logger.error("⚠️ FLEX_START 스케줄링 지원 오류")
            logger.error("=" * 60)
            logger.error("현재 GPU 타입은 FLEX_START 스케줄링을 지원하지 않습니다.")
            current_gpu = os.getenv("VERTEX_AI_GPU_TYPE", "NVIDIA_TESLA_T4")
            logger.error(f"현재 GPU: {current_gpu}")
            logger.error("")
            logger.error("해결 방법:")
            logger.error("  1. 일반 스케줄링 사용 (자동으로 처리됨)")
            logger.error("     - T4를 사용하면 자동으로 일반 스케줄링으로 실행됩니다")
            logger.error("")
            logger.error("  2. FLEX_START를 사용하려면 지원되는 GPU로 변경:")
            logger.error("     .env 파일에서:")
            logger.error("     VERTEX_AI_GPU_TYPE=NVIDIA_L4")
            logger.error("     또는")
            logger.error("     VERTEX_AI_GPU_TYPE=NVIDIA_TESLA_A100")
            logger.error("")
            logger.error("지원되는 GPU: L4, A100, H100, H200, B200")
            logger.error("=" * 60)
        
        # GPU 할당량 초과 오류인 경우
        if "quota" in error_msg.lower() and "exceed" in error_msg.lower():
            logger.error("=" * 60)
            logger.error("⚠️ GPU 할당량 초과 오류")
            logger.error("=" * 60)
            current_gpu = os.getenv("VERTEX_AI_GPU_TYPE", "NVIDIA_TESLA_T4")
            project = os.getenv("GCP_PROJECT_ID", "your-project-id")
            location = os.getenv("GCP_REGION", "us-central1")
            logger.error(f"현재 GPU: {current_gpu}")
            logger.error(f"프로젝트: {project}")
            logger.error(f"리전: {location}")
            logger.error("")
            
            # preemptible 할당량 오류인지 확인
            is_preemptible_error = "preemptible" in error_msg.lower()
            if is_preemptible_error:
                logger.error("📌 FLEX_START는 preemptible (선점형) 인스턴스를 사용합니다.")
                logger.error("   preemptible 할당량이 부족한 경우 일반 스케줄링을 사용하세요.")
                logger.error("")
                logger.error("💡 즉시 해결 방법: FLEX_START 비활성화")
                logger.error("   .env 파일에 다음을 추가:")
                logger.error("   VERTEX_AI_USE_FLEX_START=false")
                logger.error("   이렇게 하면 일반(non-preemptible) 인스턴스를 사용합니다.")
                logger.error("")
            
            logger.error("📌 중요: Colab과 Vertex AI는 할당량 시스템이 다릅니다!")
            logger.error("  - Colab: Colab 전용 할당량 사용 (무료/프리미엄 계정 기반)")
            logger.error("  - Vertex AI: 프로젝트별 Vertex AI 할당량 필요 (별도 요청 필요)")
            logger.error("")
            logger.error("Colab에서 T4 GPU가 작동했어도, Vertex AI에서는 할당량을 별도로 요청해야 합니다.")
            logger.error("")
            logger.error("해결 방법:")
            logger.error("")
            logger.error("방법 1: FLEX_START 비활성화 (즉시 해결, 권장)")
            logger.error("  .env 파일에 추가:")
            logger.error("    VERTEX_AI_USE_FLEX_START=false")
            logger.error("  일반(non-preemptible) 인스턴스를 사용하므로 할당량이 더 많을 수 있습니다.")
            logger.error("")
            logger.error("방법 2: 할당량 증가 요청 (24-48시간 소요)")
            logger.error("  1. Google Cloud Console 접속:")
            logger.error(f"     https://console.cloud.google.com/iam-admin/quotas?project={project}")
            if is_preemptible_error:
                logger.error("  2. 검색창에 'preemptible_nvidia_l4' 또는 'custom_model_training_preemptible_nvidia_l4_gpus' 입력")
            else:
                logger.error("  2. 검색창에 'nvidia_t4' 또는 'custom_model_training_nvidia_t4_gpus' 입력")
            logger.error(f"  3. 리전: {location} 필터 적용")
            logger.error("  4. 할당량 항목 선택 → 'EDIT QUOTAS' 클릭")
            logger.error("  5. 원하는 할당량 입력 (예: 0 → 1 또는 2)")
            logger.error("  6. 요청 사유 작성:")
            logger.error("     '주식 예측 모델 학습을 위한 Vertex AI Custom Job 실행에 필요합니다.")
            logger.error("      하루 1회, 약 30분~1시간씩 실행되며 월 사용량은 약 15시간입니다.'")
            logger.error("  7. 'Submit Request' 클릭")
            logger.error("  8. 승인 대기 (보통 24-48시간, 긴급 시 지원팀 문의)")
            logger.error("")
            logger.error("방법 3: 다른 리전 사용")
            logger.error("  .env 파일에서:")
            logger.error("    GCP_REGION=us-east1  # 다른 리전 시도 (할당량이 더 많을 수 있음)")
            logger.error("")
            logger.error("방법 4: Colab Enterprise 사용 (Colab과 유사한 환경)")
            logger.error("  Colab Enterprise를 사용하면 Colab과 동일한 할당량 시스템을 사용할 수 있습니다.")
            logger.error("  자세한 내용은 Colab_Enterprise_스케줄링_가이드.md 파일을 참고하세요.")
            logger.error("")
            logger.error("💡 추천: 방법 1 (FLEX_START 비활성화) - 즉시 해결 가능합니다!")
            logger.error("")
            logger.error("자세한 내용은 GPU_할당량_증가_가이드.md 파일을 참고하세요.")
            logger.error("=" * 60)
        
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
