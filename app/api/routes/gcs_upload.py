"""
GCS 패키지 업로드 API

버전 관리와 함께 GCS에 패키지를 업로드하는 엔드포인트를 제공합니다.
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import logging

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scripts.utils.upload_to_gcs import (
    upload_package_with_version,
    upload_file_to_gcs,
    ensure_bucket_exists,
    get_current_version,
    build_package_from_script,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class UploadResponse(BaseModel):
    """업로드 응답 모델"""
    success: bool
    version: Optional[int] = None
    package_uri: Optional[str] = None
    message: str


class VersionResponse(BaseModel):
    """버전 정보 응답 모델"""
    current_version: int
    package_uri: Optional[str] = None


def get_gcs_config():
    """GCS 설정 가져오기"""
    project = os.getenv("GCP_PROJECT_ID")
    bucket_name = os.getenv("GCP_BUCKET_NAME", "stock-trading-packages")
    
    if bucket_name.startswith("gs://"):
        bucket_name = bucket_name[5:]
    
    if not project:
        raise HTTPException(
            status_code=500,
            detail="GCP_PROJECT_ID 환경 변수가 설정되지 않았습니다."
        )
    
    return {
        "project": project,
        "bucket_name": bucket_name,
    }


@router.post("/build-and-upload", response_model=UploadResponse, tags=["GCS 업로드"])
async def build_and_upload_predict(
    base_name: str = Form("predict-package"),
    config: dict = Depends(get_gcs_config)
):
    """
    predict.py를 자동으로 빌드하여 버전 관리와 함께 GCS에 업로드합니다.
    
    - 프로젝트의 predict.py를 자동으로 찾아서 빌드
    - 자동으로 버전 번호가 증가됩니다 (v1, v2, v3...)
    - 업로드된 패키지는 `packages/{base_name}-v{version}.tar.gz` 경로에 저장됩니다
    """
    try:
        # predict.py 파일 찾기
        project_root = Path(__file__).parent.parent.parent.parent
        script_path = project_root / "scripts" / "utils" / "predict.py"
        
        if not script_path.exists():
            raise HTTPException(
                status_code=404,
                detail="predict.py 파일을 찾을 수 없습니다."
            )
        
        logger.info(f"predict.py 자동 빌드: {script_path}")
        
        # 버킷 존재 확인
        try:
            ensure_bucket_exists(config["bucket_name"], config["project"])
        except Exception as e:
            logger.error(f"버킷 확인/생성 실패: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"버킷 확인/생성에 실패했습니다: {str(e)}"
            )
        
        # 버전 관리와 함께 업로드 (자동 빌드)
        gcs_uri, version = upload_package_with_version(
            bucket_name=config["bucket_name"],
            source_file=str(script_path),
            project=config["project"],
            base_name=base_name,
            build_from_script=True
        )
        
        logger.info(f"패키지 업로드 성공: v{version}, URI: {gcs_uri}")
        
        return UploadResponse(
            success=True,
            version=version,
            package_uri=gcs_uri,
            message=f"패키지 v{version}이(가) 성공적으로 업로드되었습니다."
        )
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"패키지 업로드 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"패키지 업로드 중 오류가 발생했습니다: {str(e)}"
        )


@router.post("/upload", response_model=UploadResponse, tags=["GCS 업로드"])
async def upload_package(
    file: Optional[UploadFile] = File(None, description="업로드할 파일 (.py 또는 .tar.gz, 없으면 predict.py 자동 빌드)"),
    base_name: str = Form("predict-package"),
    config: dict = Depends(get_gcs_config)
):
    """
    파일을 업로드하거나 predict.py를 자동 빌드하여 버전 관리와 함께 GCS에 저장합니다.
    
    - 파일이 없으면 프로젝트의 predict.py를 자동으로 빌드
    - .py 파일이면 자동으로 tar.gz 패키지로 빌드
    - .tar.gz 파일이면 그대로 업로드
    - 자동으로 버전 번호가 증가됩니다 (v1, v2, v3...)
    - 업로드된 패키지는 `packages/{base_name}-v{version}.tar.gz` 경로에 저장됩니다
    """
    try:
        # 파일이 없으면 predict.py 자동 사용
        if file is None:
            project_root = Path(__file__).parent.parent.parent.parent
            script_path = project_root / "scripts" / "utils" / "predict.py"
            
            if not script_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail="predict.py 파일을 찾을 수 없습니다."
                )
            
            logger.info(f"predict.py 자동 빌드: {script_path}")
            build_from_script = True
            source_file = str(script_path)
            temp_file_path = None
        else:
            # 파일이 있으면 업로드된 파일 사용
            file_ext = Path(file.filename).suffix if file.filename else ""
            
            if file_ext == '.py':
                # .py 파일이면 빌드
                build_from_script = True
                with tempfile.NamedTemporaryFile(delete=False, suffix='.py', mode='w') as tmp_file:
                    content = await file.read()
                    tmp_file.write(content.decode('utf-8'))
                    source_file = tmp_file.name
                    temp_file_path = tmp_file.name
            elif file_ext == '.gz' or (file.filename and file.filename.endswith('.tar.gz')):
                # .tar.gz 파일이면 그대로 사용
                build_from_script = False
                with tempfile.NamedTemporaryFile(delete=False, suffix='.tar.gz') as tmp_file:
                    content = await file.read()
                    tmp_file.write(content)
                    source_file = tmp_file.name
                    temp_file_path = tmp_file.name
            else:
                raise HTTPException(
                    status_code=400,
                    detail="파일은 .py 또는 .tar.gz 형식이어야 합니다."
                )
        
        try:
            # 버킷 존재 확인
            try:
                ensure_bucket_exists(config["bucket_name"], config["project"])
            except Exception as e:
                logger.error(f"버킷 확인/생성 실패: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"버킷 확인/생성에 실패했습니다: {str(e)}"
                )
            
            # 버전 관리와 함께 업로드
            gcs_uri, version = upload_package_with_version(
                bucket_name=config["bucket_name"],
                source_file=source_file,
                project=config["project"],
                base_name=base_name,
                build_from_script=build_from_script
            )
            
            logger.info(f"패키지 업로드 성공: v{version}, URI: {gcs_uri}")
            
            return UploadResponse(
                success=True,
                version=version,
                package_uri=gcs_uri,
                message=f"패키지 v{version}이(가) 성공적으로 업로드되었습니다."
            )
            
        finally:
            # 임시 파일 삭제 (업로드된 파일만)
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.warning(f"임시 파일 삭제 실패: {e}")
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"패키지 업로드 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"패키지 업로드 중 오류가 발생했습니다: {str(e)}"
        )


@router.get("/version", response_model=VersionResponse, tags=["GCS 업로드"])
async def get_current_package_version(
    config: dict = Depends(get_gcs_config)
):
    """
    현재 패키지 버전 정보를 조회합니다.
    """
    try:
        # 버킷 존재 확인
        from google.cloud import storage
        storage_client = storage.Client(project=config["project"])
        bucket = storage_client.bucket(config["bucket_name"])
        
        if not bucket.exists():
            raise HTTPException(
                status_code=404,
                detail="버킷을 찾을 수 없습니다."
            )
        
        # 현재 버전 조회
        current_version = get_current_version(config["bucket_name"], config["project"])
        
        # 패키지 URI 생성
        package_uri = None
        if current_version > 0:
            package_name = f"predict-package-v{current_version}.tar.gz"
            package_path = f"packages/{package_name}"
            package_blob = bucket.blob(package_path)
            
            if package_blob.exists():
                package_uri = f"gs://{config['bucket_name']}/{package_path}"
        
        return VersionResponse(
            current_version=current_version,
            package_uri=package_uri
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"버전 조회 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"버전 조회 중 오류가 발생했습니다: {str(e)}"
        )


@router.post("/upload-direct", response_model=UploadResponse, tags=["GCS 업로드"])
async def upload_file_direct(
    file: UploadFile = File(..., description="업로드할 파일"),
    path: str = File(..., description="GCS 내 경로 (예: packages/file.tar.gz)"),
    config: dict = Depends(get_gcs_config)
):
    """
    버전 관리 없이 직접 파일을 GCS에 업로드합니다.
    """
    try:
        # 임시 파일로 저장
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_file_path = tmp_file.name
        
        try:
            # 버킷 존재 확인
            try:
                ensure_bucket_exists(config["bucket_name"], config["project"])
            except Exception as e:
                logger.error(f"버킷 확인/생성 실패: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"버킷 확인/생성에 실패했습니다: {str(e)}"
                )
            
            # 파일 업로드
            gcs_uri = upload_file_to_gcs(
                bucket_name=config["bucket_name"],
                source_file=tmp_file_path,
                destination_blob_name=path,
                project=config["project"]
            )
            
            logger.info(f"파일 업로드 성공: {gcs_uri}")
            
            return UploadResponse(
                success=True,
                package_uri=gcs_uri,
                message="파일이 성공적으로 업로드되었습니다."
            )
            
        finally:
            # 임시 파일 삭제
            try:
                os.unlink(tmp_file_path)
            except Exception as e:
                logger.warning(f"임시 파일 삭제 실패: {e}")
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"파일 업로드 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"파일 업로드 중 오류가 발생했습니다: {str(e)}"
        )