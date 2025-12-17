"""
Compute Engine VM을 직접 사용하여 predict.py를 실행하는 스크립트

이 스크립트는 Vertex AI CustomJob 대신 Compute Engine VM을 직접 생성하고
거기서 predict.py를 실행합니다. Compute Engine의 T4 GPU 할당량을 사용합니다.

사용법:
    python run_predict_compute_engine.py

환경 변수:
    GCP_PROJECT_ID: Google Cloud 프로젝트 ID
    GCP_REGION: 리전 (예: us-central1)
    GCP_ZONE: 존 (예: us-central1-a)
    MONGODB_URL: MongoDB URL
    MONGODB_USER: MongoDB 사용자명
    MONGODB_PASSWORD: MongoDB 비밀번호
    MONGODB_DATABASE: MongoDB 데이터베이스명
    GOOGLE_APPLICATION_CREDENTIALS: Google Cloud 인증 정보 파일 경로
"""

import os
import sys
import time
from pathlib import Path
from typing import Optional
import logging
from dotenv import load_dotenv

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# .env 파일 로드
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    load_dotenv(env_file)
    logger.info(f".env 파일 로드 완료: {env_file}")
else:
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        logger.info(f".env 파일 로드 완료: {env_file}")
    else:
        logger.warning(f".env 파일을 찾을 수 없습니다.")

# vertex-ai-key.json 파일 자동 찾기 및 설정
if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
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

from google.cloud import compute_v1
from google.cloud import storage
from google.api_core import exceptions


def get_env_var(var_name: str, default: Optional[str] = None) -> str:
    """환경 변수를 가져오고 없으면 기본값을 반환합니다."""
    value = os.getenv(var_name, default)
    if value is None:
        raise ValueError(f"환경 변수 {var_name}이 설정되지 않았습니다.")
    return value


def check_authentication() -> bool:
    """Google Cloud 인증이 제대로 설정되어 있는지 확인합니다."""
    try:
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if creds_path and os.path.exists(creds_path):
            logger.info(f"✅ 서비스 계정 키 파일 발견: {creds_path}")
            return True
        
        # gcloud CLI 기본 인증 확인
        from google.auth import default
        credentials, project = default()
        logger.info(f"✅ gcloud CLI 기본 인증 사용")
        return True
    except Exception as e:
        logger.error(f"❌ 인증 확인 실패: {e}")
        return False


def upload_file_to_gcs(bucket_name: str, source_file: str, destination_blob_name: str, project: str) -> str:
    """로컬 파일을 GCS 버킷에 업로드합니다."""
    storage_client = storage.Client(project=project)
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    
    logger.info(f"파일 업로드 중: {source_file} -> gs://{bucket_name}/{destination_blob_name}")
    blob.upload_from_filename(source_file)
    logger.info(f"✅ 파일 업로드 완료: gs://{bucket_name}/{destination_blob_name}")
    
    return f"gs://{bucket_name}/{destination_blob_name}"


def create_vm_instance(
    project: str,
    zone: str,
    instance_name: str,
    machine_type: str = "n1-standard-4",
    accelerator_type: str = "nvidia-tesla-t4",
    accelerator_count: int = 1,
    image_family: str = "ubuntu-2204-lts",
    image_project: str = "deeplearning-platform-release",
    startup_script: Optional[str] = None,
) -> bool:
    """Compute Engine VM 인스턴스를 gcloud CLI로 생성합니다."""
    try:
        import subprocess
        
        # 이미 존재하는 인스턴스 확인
        check_cmd = [
            "gcloud", "compute", "instances", "describe", instance_name,
            "--zone", zone,
            "--project", project,
            "--quiet"
        ]
        result = subprocess.run(check_cmd, capture_output=True, text=True)
        if result.returncode == 0:
            logger.warning(f"⚠️ 인스턴스 {instance_name}가 이미 존재합니다.")
            return True
        
        # gcloud 명령어로 VM 생성
        # 일반 Ubuntu 이미지 사용 (GPU 드라이버는 자동 설치됨)
        create_cmd = [
            "gcloud", "compute", "instances", "create", instance_name,
            "--zone", zone,
            "--project", project,
            "--machine-type", machine_type,
            "--accelerator", f"type={accelerator_type},count={accelerator_count}",
            "--image-family", "ubuntu-2204-lts",
            "--image-project", "ubuntu-os-cloud",
            "--boot-disk-size", "200GB",
            "--maintenance-policy", "TERMINATE",
            "--scopes", "cloud-platform",
            "--metadata", "install-nvidia-driver=True"
        ]
        
        logger.info(f"VM 인스턴스 생성 중: {instance_name}")
        logger.info(f"명령어: {' '.join(create_cmd)}")
        
        result = subprocess.run(create_cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"✅ VM 인스턴스 생성 완료: {instance_name}")
            return True
        else:
            logger.error(f"❌ VM 인스턴스 생성 실패: {result.stderr}")
            return False
        
    except Exception as e:
        logger.error(f"❌ VM 인스턴스 생성 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def wait_for_operation(project: str, zone: str, operation_name: str, operation_type: str):
    """Compute Engine 작업이 완료될 때까지 대기합니다. (gcloud CLI 사용 시 불필요)"""
    # gcloud CLI는 자동으로 대기하므로 이 함수는 사용하지 않음
    pass


def wait_for_instance_ready(project: str, zone: str, instance_name: str, timeout: int = 600):
    """VM 인스턴스가 준비될 때까지 대기합니다."""
    import subprocess
    
    logger.info(f"VM 인스턴스 준비 대기 중: {instance_name}")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            # gcloud로 인스턴스 상태 확인
            check_cmd = [
                "gcloud", "compute", "instances", "describe", instance_name,
                "--zone", zone,
                "--project", project,
                "--format", "get(status)",
                "--quiet"
            ]
            result = subprocess.run(check_cmd, capture_output=True, text=True)
            
            if result.returncode == 0 and "RUNNING" in result.stdout:
                # SSH 접속 가능할 때까지 추가 대기
                logger.info("VM이 실행 중입니다. SSH 접속 준비 대기 중...")
                time.sleep(30)
                logger.info(f"✅ VM 인스턴스 준비 완료: {instance_name}")
                return True
        except Exception as e:
            logger.debug(f"인스턴스 상태 확인 중: {e}")
        
        time.sleep(10)
    
    raise TimeoutError(f"VM 인스턴스가 {timeout}초 내에 준비되지 않았습니다.")


def execute_script_on_vm(
    project: str,
    zone: str,
    instance_name: str,
    script_path: str,
    environment_variables: Optional[dict] = None,
) -> bool:
    """VM에서 스크립트를 실행합니다."""
    try:
        import subprocess
        import tempfile
        
        # VM의 외부 IP 가져오기
        instance_client = compute_v1.InstancesClient()
        instance = instance_client.get(project=project, zone=zone, instance=instance_name)
        
        external_ip = None
        for network_interface in instance.network_interfaces:
            if network_interface.access_configs:
                external_ip = network_interface.access_configs[0].nat_i_p
                break
        
        if not external_ip:
            raise Exception("VM의 외부 IP를 찾을 수 없습니다.")
        
        logger.info(f"VM 외부 IP: {external_ip}")
        
        script_name = Path(script_path).name
        
        # predict.py 파일 읽기 및 수정 (Colab 전용 코드 제거)
        with open(script_path, 'r', encoding='utf-8') as f:
            script_content = f.read()
        
        # !pip install 라인 제거 및 import os 추가
        lines = script_content.split('\n')
        modified_lines = []
        has_import_os = False
        
        for line in lines:
            # !pip install 라인 제거
            if line.strip().startswith('!pip') or line.strip().startswith('!'):
                logger.info(f"Colab 전용 코드 제거: {line.strip()}")
                continue
            # import os 확인
            if 'import os' in line:
                has_import_os = True
            modified_lines.append(line)
        
        # import os가 없으면 추가
        if not has_import_os:
            # 첫 번째 import 전에 추가
            insert_index = 0
            for i, line in enumerate(modified_lines):
                if line.strip().startswith('import ') or line.strip().startswith('from '):
                    insert_index = i
                    break
            modified_lines.insert(insert_index, 'import os')
            logger.info("import os 추가됨")
        
        modified_script = '\n'.join(modified_lines)
        
        # 임시 파일로 저장
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp_file:
            tmp_file.write(modified_script)
            tmp_script_path = tmp_file.name
        
        try:
            # 환경 변수 설정
            env_vars = ""
            if environment_variables:
                for key, value in environment_variables.items():
                    env_vars += f'export {key}="{value}"\n'
            
            # 필요한 패키지 설치 및 스크립트 실행 명령어
            command = f"""
            {env_vars}
            cd /tmp
            # Python 및 pip 설치
            sudo apt-get update -qq
            sudo apt-get install -y -qq python3-pip python3-dev
            # 필요한 패키지 설치
            pip3 install --quiet pandas numpy scikit-learn tensorflow matplotlib pymongo
            # 스크립트 실행
            python3 {script_name}
            """
            
            # 파일 먼저 복사
            copy_command = [
                "gcloud", "compute", "scp",
                tmp_script_path,
                f"{instance_name}:/tmp/{script_name}",
                f"--zone={zone}",
                f"--project={project}",
                "--quiet"
            ]
            
            logger.info("수정된 스크립트 파일 복사 중...")
            result = subprocess.run(copy_command, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"파일 복사 실패: {result.stderr}")
                return False
            
            # gcloud compute ssh로 실행
            ssh_command = [
                "gcloud", "compute", "ssh",
                f"{instance_name}",
                f"--zone={zone}",
                f"--project={project}",
                "--command", command,
                "--quiet"
            ]
            
            logger.info(f"VM에서 스크립트 실행 중: {script_name}")
            logger.info("필요한 패키지 설치 중...")
            
            # 스크립트 실행
            result = subprocess.run(ssh_command, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info("✅ 스크립트 실행 완료")
                logger.info(f"출력:\n{result.stdout}")
                return True
            else:
                logger.error(f"❌ 스크립트 실행 실패: {result.stderr}")
                logger.error(f"출력: {result.stdout}")
                return False
        finally:
            # 임시 파일 삭제
            try:
                os.unlink(tmp_script_path)
            except:
                pass
            
    except Exception as e:
        logger.error(f"❌ VM에서 스크립트 실행 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def delete_vm_instance(project: str, zone: str, instance_name: str):
    """VM 인스턴스를 gcloud CLI로 삭제합니다."""
    try:
        import subprocess
        
        logger.info(f"VM 인스턴스 삭제 중: {instance_name}")
        delete_cmd = [
            "gcloud", "compute", "instances", "delete", instance_name,
            "--zone", zone,
            "--project", project,
            "--quiet"
        ]
        
        result = subprocess.run(delete_cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"✅ VM 인스턴스 삭제 완료: {instance_name}")
        else:
            if "not found" in result.stderr.lower():
                logger.warning(f"인스턴스 {instance_name}가 이미 삭제되었습니다.")
            else:
                logger.error(f"❌ VM 인스턴스 삭제 실패: {result.stderr}")
        
    except Exception as e:
        logger.error(f"❌ VM 인스턴스 삭제 실패: {e}")


def main():
    """메인 실행 함수"""
    try:
        # 인증 확인
        if not check_authentication():
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
            logger.error("=" * 60)
            sys.exit(1)
        
        # 환경 변수 로드
        project = get_env_var("GCP_PROJECT_ID")
        region = get_env_var("GCP_REGION", "us-central1")
        
        # 여러 리전과 존 시도 (T4 GPU 가용성에 따라)
        # 할당량 요청이 불가능한 경우 다른 리전을 자동으로 시도
        regions_to_try = [
            region,  # 먼저 설정된 리전 시도
            "us-east1",  # South Carolina
            "us-west1",  # Oregon
            "us-west4",  # Las Vegas
        ]
        
        # 각 리전의 존 목록
        zones_by_region = {
            "us-central1": ["us-central1-a", "us-central1-b", "us-central1-c", "us-central1-f"],
            "us-east1": ["us-east1-b", "us-east1-c", "us-east1-d"],
            "us-west1": ["us-west1-a", "us-west1-b", "us-west1-c"],
            "us-west4": ["us-west4-a", "us-west4-b", "us-west4-c"],
        }
        
        zone = None  # 나중에 설정됨
        
        logger.info(f"프로젝트: {project}")
        logger.info(f"리전: {region}")
        logger.info(f"존: {zone}")
        
        # VM 설정
        instance_name = f"predict-runner-{int(time.time())}"
        machine_type = os.getenv("GCE_MACHINE_TYPE", "n1-standard-4")
        accelerator_type = os.getenv("GCE_GPU_TYPE", "nvidia-tesla-t4")
        accelerator_count = int(os.getenv("GCE_GPU_COUNT", "1"))
        
        logger.info(f"인스턴스 이름: {instance_name}")
        logger.info(f"머신 타입: {machine_type}")
        logger.info(f"GPU 타입: {accelerator_type}")
        logger.info(f"GPU 개수: {accelerator_count}")
        
        # predict.py 경로 확인 (scripts/utils/predict.py)
        project_root = Path(__file__).parent.parent.parent
        script_path = project_root / "scripts" / "utils" / "predict.py"
        if not script_path.exists():
            logger.error(f"❌ predict.py 파일을 찾을 수 없습니다: {script_path}")
            sys.exit(1)
        
        logger.info(f"스크립트 경로: {script_path}")
        
        # 환경 변수 준비
        environment_variables = {}
        if os.getenv("MONGODB_URL"):
            environment_variables["MONGODB_URL"] = os.getenv("MONGODB_URL")
        if os.getenv("MONGODB_USER"):
            environment_variables["MONGODB_USER"] = os.getenv("MONGODB_USER")
        if os.getenv("MONGODB_PASSWORD"):
            environment_variables["MONGODB_PASSWORD"] = os.getenv("MONGODB_PASSWORD")
        if os.getenv("MONGODB_DATABASE"):
            environment_variables["MONGODB_DATABASE"] = os.getenv("MONGODB_DATABASE")
        
        # VM 생성 (여러 리전과 존 시도)
        logger.info("=" * 60)
        logger.info("🚀 Compute Engine VM 생성 시작")
        logger.info("=" * 60)
        logger.info("⚠️ 할당량 요청이 불가능한 경우 여러 리전을 자동으로 시도합니다.")
        logger.info("=" * 60)
        
        vm_created = False
        for region_to_try in regions_to_try:
            if region_to_try not in zones_by_region:
                continue
            
            zones_to_try = zones_by_region[region_to_try]
            logger.info(f"리전 {region_to_try} 시도 중...")
            
            for zone_to_try in zones_to_try:
                logger.info(f"  존 {zone_to_try}에서 VM 생성 시도 중...")
                if create_vm_instance(
                    project=project,
                    zone=zone_to_try,
                    instance_name=instance_name,
                    machine_type=machine_type,
                    accelerator_type=accelerator_type,
                    accelerator_count=accelerator_count,
                ):
                    zone = zone_to_try
                    region = region_to_try
                    vm_created = True
                    logger.info(f"✅ 리전 {region_to_try}, 존 {zone_to_try}에서 VM 생성 성공!")
                    break
                else:
                    logger.warning(f"  존 {zone_to_try}에서 VM 생성 실패, 다음 존 시도...")
            
            if vm_created:
                break
            else:
                logger.warning(f"리전 {region_to_try}의 모든 존에서 실패, 다음 리전 시도...")
        
        if not vm_created:
            logger.error("=" * 60)
            logger.error("❌ 모든 리전과 존에서 VM 생성 실패")
            logger.error("=" * 60)
            logger.error("해결 방법:")
            logger.error("1. 나중에 다시 시도 (리소스 가용성은 시간에 따라 변함)")
            logger.error("2. 다른 GPU 타입 사용 (.env에서 GCE_GPU_TYPE 변경)")
            logger.error("3. Google Cloud 지원팀에 문의")
            logger.error("=" * 60)
            sys.exit(1)
        
        try:
            # VM 준비 대기
            wait_for_instance_ready(project, zone, instance_name)
            
            # 스크립트 실행
            logger.info("=" * 60)
            logger.info("📝 스크립트 실행 시작")
            logger.info("=" * 60)
            
            if not execute_script_on_vm(
                project=project,
                zone=zone,
                instance_name=instance_name,
                script_path=str(script_path),
                environment_variables=environment_variables,
            ):
                logger.error("❌ 스크립트 실행 실패")
                sys.exit(1)
            
            logger.info("=" * 60)
            logger.info("✅ 모든 작업 완료!")
            logger.info("=" * 60)
            
        finally:
            # VM 삭제 (비용 절감)
            delete_option = os.getenv("GCE_DELETE_VM", "true").lower()
            if delete_option == "true":
                logger.info("=" * 60)
                logger.info("🗑️ VM 인스턴스 삭제 중 (비용 절감)")
                logger.info("=" * 60)
                delete_vm_instance(project, zone, instance_name)
            else:
                logger.info(f"⚠️ VM 인스턴스 유지: {instance_name}")
                logger.info("수동으로 삭제하려면:")
                logger.info(f"  gcloud compute instances delete {instance_name} --zone={zone} --project={project}")
        
    except Exception as e:
        logger.error(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
