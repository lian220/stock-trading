"""
predict.py 파일을 GCS 버킷에 업로드하는 스크립트

사용법:
    python upload_to_gcs.py [--file predict.py] [--bucket stock-trading-packages] [--path packages/predict.py]

환경 변수:
    GCP_PROJECT_ID: Google Cloud 프로젝트 ID
    GCP_BUCKET_NAME: Cloud Storage 버킷 이름 (기본값: stock-trading-packages)
    GOOGLE_APPLICATION_CREDENTIALS: Google Cloud 인증 정보 파일 경로
"""

import os
import sys
import argparse
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

# .env 파일 로드 (없어도 괜찮음 - 환경 변수나 다른 방법으로 설정 가능)
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    load_dotenv(env_file)
    logger.debug(f".env 파일 로드 완료: {env_file}")
# .env 파일이 없어도 환경 변수로 직접 설정 가능하므로 경고를 출력하지 않음

# vertex-ai-key.json 파일 자동 찾기 및 설정
# 주의: 모듈 로드 시점에 실행되므로 Docker 환경에서는 환경 변수 사용 권장
def setup_credentials():
    """인증 파일을 찾아서 설정합니다. (필요할 때만 호출)"""
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return  # 이미 설정됨
    
    # Docker 환경 체크 (로컬 경로가 아닌 경우)
    if Path("/app").exists() or Path("/").exists() and not Path("/Users").exists():
        # Docker 컨테이너 내부에서는 환경 변수나 gcloud 인증 사용
        logger.debug("Docker 환경 감지: 환경 변수나 gcloud 인증을 사용합니다.")
        return
    
    # 로컬 개발 환경에서만 파일 찾기
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
            return
    
    logger.debug("로컬 인증 파일을 찾을 수 없습니다. 환경 변수나 gcloud 인증을 사용합니다.")

# 모듈 로드 시점에는 실행하지 않음 (함수 호출 시점에만 실행)

from google.cloud import storage
import json
import re
import tarfile
import tempfile
import shutil
from datetime import datetime


def upload_file_to_gcs(
    bucket_name: str,
    source_file: str,
    destination_blob_name: str,
    project: Optional[str] = None
) -> str:
    """
    로컬 파일을 GCS 버킷에 업로드합니다.
    
    Args:
        bucket_name: GCS 버킷 이름 (gs:// 제외)
        source_file: 업로드할 로컬 파일 경로
        destination_blob_name: GCS 내 목적지 경로 (예: packages/predict.py)
        project: Google Cloud 프로젝트 ID (선택사항)
    
    Returns:
        업로드된 파일의 GCS URI (gs://bucket/path)
    """
    try:
        # 인증 설정 시도 (로컬 환경에서만)
        setup_credentials()
        
        storage_client = storage.Client(project=project)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)
        
        # 파일 존재 확인
        source_path = Path(source_file)
        if not source_path.exists():
            raise FileNotFoundError(f"소스 파일을 찾을 수 없습니다: {source_file}")
        
        logger.info(f"파일 업로드 중: {source_file} -> gs://{bucket_name}/{destination_blob_name}")
        
        # 파일 업로드
        blob.upload_from_filename(str(source_path))
        
        gcs_uri = f"gs://{bucket_name}/{destination_blob_name}"
        logger.info(f"✅ 파일 업로드 완료: {gcs_uri}")
        
        return gcs_uri
        
    except Exception as e:
        logger.error(f"❌ 파일 업로드 실패: {e}")
        raise


def ensure_bucket_exists(bucket_name: str, project: str) -> bool:
    """버킷이 존재하는지 확인하고, 없으면 생성합니다."""
    try:
        # 인증 설정 시도 (로컬 환경에서만)
        setup_credentials()
        
        # 인증 확인
        try:
            storage_client = storage.Client(project=project)
        except Exception as auth_error:
            error_msg = str(auth_error)
            # Docker 환경에서 로컬 경로 에러가 나는 경우 더 명확한 메시지
            if "was not found" in error_msg or "File" in error_msg:
                logger.error(f"❌ Google Cloud 인증 파일을 찾을 수 없습니다.")
                logger.error("Docker 환경에서는 환경 변수로 인증 정보를 제공해야 합니다:")
                logger.error("  1. GOOGLE_APPLICATION_CREDENTIALS 환경 변수에 인증 파일 경로 설정")
                logger.error("  2. 또는 docker-compose.yml에서 인증 파일을 볼륨 마운트")
                logger.error("  3. 또는 서비스 계정 키를 환경 변수로 직접 설정")
            else:
                logger.error(f"❌ Google Cloud 인증 실패: {auth_error}")
                logger.error("인증 방법:")
                logger.error("  1. GOOGLE_APPLICATION_CREDENTIALS 환경 변수 설정")
                logger.error("  2. gcloud auth application-default login 실행")
            raise
        
        bucket = storage_client.bucket(bucket_name)
        if bucket.exists():
            logger.info(f"✅ 버킷이 이미 존재합니다: {bucket_name}")
            return True
        
        # 버킷 생성
        logger.info(f"버킷이 없습니다. 생성 중: {bucket_name}")
        try:
            bucket = storage_client.create_bucket(bucket_name)
            logger.info(f"✅ 버킷 생성 완료: {bucket_name}")
            return True
        except Exception as create_error:
            logger.error(f"❌ 버킷 생성 실패: {create_error}")
            logger.error("버킷 생성 권한이 없거나 이미 다른 프로젝트에 존재할 수 있습니다.")
            raise
        
    except Exception as e:
        logger.error(f"❌ 버킷 확인/생성 실패: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise


def get_current_version(bucket_name: str, project: str, base_name: str = "predict-package") -> int:
    """GCS에서 현재 패키지 버전을 가져옵니다. 없으면 0을 반환."""
    try:
        # 인증 설정 시도 (로컬 환경에서만)
        setup_credentials()
        
        storage_client = storage.Client(project=project)
        bucket = storage_client.bucket(bucket_name)
        
        # 버전 파일 읽기
        version_file_name = f"{base_name}-version.json"
        version_blob = bucket.blob(version_file_name)
        if version_blob.exists():
            version_data = json.loads(version_blob.download_as_text())
            current_version = version_data.get("version", 0)
            logger.info(f"📋 버전 파일에서 확인: v{current_version} ({version_file_name})")
            return current_version
        
        # 버전 파일이 없으면 기존 패키지 파일에서 최대 버전 찾기
        logger.info(f"📋 버전 파일이 없습니다. 기존 패키지에서 최대 버전을 찾는 중... (prefix: {base_name}-v)")
        blobs = list(bucket.list_blobs(prefix=f"packages/{base_name}-v"))
        
        max_version = 0
        version_pattern = re.compile(rf'{re.escape(base_name)}-v(\d+)\.tar\.gz')
        found_versions = []
        
        for blob in blobs:
            match = version_pattern.search(blob.name)
            if match:
                version = int(match.group(1))
                found_versions.append(version)
                max_version = max(max_version, version)
        
        if max_version > 0:
            found_versions.sort()
            logger.info(f"📋 기존 패키지에서 발견된 버전들: {found_versions}")
            logger.info(f"📋 최대 버전: v{max_version}")
            return max_version
        
        logger.info("📋 기존 패키지가 없습니다. 버전 0부터 시작합니다.")
        return 0
        
    except Exception as e:
        logger.warning(f"⚠️ 버전 확인 중 오류 (기본값 0 사용): {e}")
        return 0


def save_version(bucket_name: str, version: int, project: str, base_name: str = "predict-package") -> None:
    """GCS에 패키지 버전을 저장합니다."""
    try:
        # 인증 설정 시도 (로컬 환경에서만)
        setup_credentials()
        
        storage_client = storage.Client(project=project)
        bucket = storage_client.bucket(bucket_name)
        
        version_data = {
            "version": version,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        version_file_name = f"{base_name}-version.json"
        version_blob = bucket.blob(version_file_name)
        version_blob.upload_from_string(
            json.dumps(version_data, indent=2),
            content_type="application/json"
        )
        logger.info(f"💾 버전 정보 저장 완료: v{version} ({version_file_name})")
        
    except Exception as e:
        logger.error(f"❌ 버전 저장 실패: {e}")
        raise


def build_package_from_script(
    script_path: str,
    output_path: Optional[str] = None
) -> str:
    """
    predict.py 스크립트를 Vertex AI CustomJob 형식의 tar.gz 패키지로 빌드합니다.
    
    Args:
        script_path: 빌드할 Python 스크립트 경로 (예: predict.py)
        output_path: 출력 tar.gz 파일 경로 (None이면 임시 파일 생성)
    
    Returns:
        생성된 tar.gz 파일 경로
    """
    script_path_obj = Path(script_path)
    if not script_path_obj.exists():
        raise FileNotFoundError(f"스크립트 파일을 찾을 수 없습니다: {script_path}")
    
    # 임시 디렉토리 생성
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # 패키지 디렉토리 구조 생성
        package_dir = temp_path / "aiplatform_custom_trainer_script"
        package_dir.mkdir()
        
        # __init__.py 생성
        (package_dir / "__init__.py").write_text("")
        
        # task.py 생성 (predict.py 내용 복사)
        script_content = script_path_obj.read_text(encoding='utf-8')
        (package_dir / "task.py").write_text(script_content, encoding='utf-8')
        
        # setup.py 생성 (필요한 패키지 포함)
        required_packages = [
            "supabase>=2.0.0",
            "pandas>=2.0.0",
            "numpy>=1.24.0",
            "scikit-learn>=1.3.0",
            "tensorflow>=2.11.0",
            "matplotlib>=3.7.0",
            "pymongo>=4.6.0",  # MongoDB 연결용
        ]
        
        setup_py_content = f"""from setuptools import setup, find_packages

setup(
    name="aiplatform_custom_trainer_script",
    version="0.1",
    packages=find_packages(),
    install_requires={required_packages},
)
"""
        (temp_path / "setup.py").write_text(setup_py_content, encoding='utf-8')
        
        # MANIFEST.in 생성
        manifest_content = """include aiplatform_custom_trainer_script/*.py
"""
        (temp_path / "MANIFEST.in").write_text(manifest_content, encoding='utf-8')
        
        # tar.gz 파일 생성
        if output_path is None:
            output_file = tempfile.NamedTemporaryFile(delete=False, suffix='.tar.gz')
            output_path = output_file.name
            output_file.close()
        
        output_path_obj = Path(output_path)
        
        # tar.gz 압축
        with tarfile.open(output_path_obj, "w:gz") as tar:
            tar.add(temp_path / "setup.py", arcname="setup.py")
            tar.add(temp_path / "MANIFEST.in", arcname="MANIFEST.in")
            tar.add(package_dir, arcname="aiplatform_custom_trainer_script")
        
        logger.info(f"✅ 패키지 빌드 완료: {output_path}")
        return str(output_path_obj)


def upload_package_with_version(
    bucket_name: str,
    source_file: str,
    project: str,
    base_name: str = "predict-package",
    build_from_script: bool = False
) -> tuple[str, int]:
    """
    패키지를 버전 번호와 함께 GCS에 업로드합니다.
    
    Args:
        bucket_name: GCS 버킷 이름
        source_file: 업로드할 파일 경로 (tar.gz 또는 .py 스크립트)
        project: Google Cloud 프로젝트 ID
        base_name: 패키지 기본 이름
        build_from_script: True이면 source_file을 .py 스크립트로 간주하고 빌드
    
    Returns:
        (패키지 GCS URI, 버전 번호) 튜플
    """
    # 현재 버전 가져오기 (업로드 전 버전 체크)
    logger.info("=" * 60)
    logger.info("📦 패키지 업로드 시작")
    logger.info("=" * 60)
    logger.info(f"  버킷: {bucket_name}")
    logger.info(f"  소스 파일: {source_file}")
    logger.info(f"  기본 이름: {base_name}")
    
    current_version = get_current_version(bucket_name, project, base_name)
    logger.info(f"  ✅ 현재 최신 버전: v{current_version}")
    
    # 새 버전 (현재 버전 + 1)
    new_version = current_version + 1
    logger.info(f"  🆕 새 버전: v{new_version}")
    
    # 새 패키지 이름
    package_name = f"{base_name}-v{new_version}.tar.gz"
    package_path = f"packages/{package_name}"
    logger.info(f"  📁 패키지 경로: {package_path}")
    logger.info("=" * 60)
    
    # 스크립트에서 빌드해야 하는 경우
    temp_package_path = None
    if build_from_script or source_file.endswith('.py'):
        logger.info(f"스크립트에서 패키지 빌드 중: {source_file}")
        temp_package_path = build_package_from_script(source_file)
        source_file = temp_package_path
    
    try:
        # 파일 업로드
        gcs_uri = upload_file_to_gcs(
            bucket_name=bucket_name,
            source_file=source_file,
            destination_blob_name=package_path,
            project=project
        )
        
        # 버전 정보 저장
        save_version(bucket_name, new_version, project, base_name)
        
        logger.info("=" * 60)
        logger.info("✅ 패키지 업로드 완료")
        logger.info("=" * 60)
        logger.info(f"  버전: v{new_version}")
        logger.info(f"  GCS URI: {gcs_uri}")
        logger.info("=" * 60)
        
        return gcs_uri, new_version
    finally:
        # 임시 파일 정리
        if temp_package_path and os.path.exists(temp_package_path):
            try:
                os.unlink(temp_package_path)
            except Exception as e:
                logger.warning(f"임시 파일 삭제 실패: {e}")


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="predict.py 패키지를 버전 관리하여 GCS에 업로드")
    parser.add_argument(
        "--file",
        type=str,
        default="predict.py",
        help="업로드할 파일 경로 (기본값: predict.py, .py 파일이면 자동 빌드, .tar.gz 파일도 지원)"
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help=".py 스크립트를 자동으로 빌드하여 업로드 (기본값: 자동 감지)"
    )
    parser.add_argument(
        "--bucket",
        type=str,
        default=None,
        help="GCS 버킷 이름 (기본값: 환경 변수 GCP_BUCKET_NAME 또는 stock-trading-packages)"
    )
    parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="Google Cloud 프로젝트 ID (기본값: 환경 변수 GCP_PROJECT_ID)"
    )
    parser.add_argument(
        "--base-name",
        type=str,
        default="predict-package",
        help="패키지 기본 이름 (기본값: predict-package, 결과: predict-package-v1.tar.gz)"
    )
    parser.add_argument(
        "--no-version",
        action="store_true",
        help="버전 관리 없이 직접 업로드 (기존 방식)"
    )
    parser.add_argument(
        "--path",
        type=str,
        default=None,
        help="GCS 내 직접 경로 지정 (--no-version 사용 시)"
    )
    
    args = parser.parse_args()
    
    # 프로젝트 ID 확인
    project = args.project or os.getenv("GCP_PROJECT_ID")
    if not project:
        logger.error("❌ GCP_PROJECT_ID 환경 변수가 설정되지 않았거나 --project 인자를 제공하세요.")
        sys.exit(1)
    
    # 버킷 이름 확인
    bucket_name = args.bucket or os.getenv("GCP_BUCKET_NAME", "stock-trading-packages")
    if bucket_name.startswith("gs://"):
        bucket_name = bucket_name[5:]
    
    # 소스 파일 경로 확인
    source_file = Path(args.file)
    if not source_file.is_absolute():
        # 기본값이 predict.py인 경우 scripts/utils/predict.py를 찾음
        if args.file == "predict.py":
            source_file = Path(__file__).parent / "predict.py"
        else:
            source_file = Path(__file__).parent / source_file
    
    if not source_file.exists():
        logger.error(f"❌ 파일을 찾을 수 없습니다: {source_file}")
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("GCS 패키지 업로드 시작")
    logger.info("=" * 60)
    logger.info(f"프로젝트: {project}")
    logger.info(f"버킷: {bucket_name}")
    logger.info(f"소스 파일: {source_file}")
    logger.info("=" * 60)
    
    # 버킷 존재 확인 및 생성
    if not ensure_bucket_exists(bucket_name, project):
        logger.error("버킷을 생성할 수 없습니다.")
        sys.exit(1)
    
    # 파일 업로드
    try:
        if args.no_version:
            # 버전 관리 없이 직접 업로드
            if not args.path:
                logger.error("❌ --no-version 사용 시 --path 인자가 필요합니다.")
                sys.exit(1)
            
            gcs_uri = upload_file_to_gcs(
                bucket_name=bucket_name,
                source_file=str(source_file),
                destination_blob_name=args.path,
                project=project
            )
            
            logger.info("=" * 60)
            logger.info("✅ 업로드 완료!")
            logger.info(f"GCS URI: {gcs_uri}")
            logger.info("=" * 60)
        else:
            # 버전 관리와 함께 업로드
            # .py 파일이면 자동으로 빌드
            build_from_script = args.build or str(source_file).endswith('.py')
            
            gcs_uri, version = upload_package_with_version(
                bucket_name=bucket_name,
                source_file=str(source_file),
                project=project,
                base_name=args.base_name,
                build_from_script=build_from_script
            )
            
            logger.info("=" * 60)
            logger.info("✅ 업로드 완료!")
            logger.info(f"패키지 버전: v{version}")
            logger.info(f"GCS URI: {gcs_uri}")
            logger.info(f"다음 실행 시 자동으로 v{version}이 사용됩니다.")
            logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ 업로드 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()