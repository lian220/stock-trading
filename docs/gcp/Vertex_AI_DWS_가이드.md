# Vertex AI 동적 워크로드 스케줄러(DWS) 가이드

## 📋 개요

이 가이드는 Vertex AI의 동적 워크로드 스케줄러(Dynamic Workload Scheduler, DWS)를 사용하여 `predict.py`를 실행하는 방법을 설명합니다.

DWS는 GPU 리소스가 사용 가능해질 때까지 작업을 대기시켜주는 기능으로, 피크 시간대에 GPU 할당량이 부족할 때 유용합니다.

## 🎯 주요 기능

- **FLEX_START 스케줄링**: GPU 리소스가 사용 가능해질 때까지 자동 대기
- **지원 GPU**: L4, A100, H100, H200, B200
- **최대 대기 시간 설정**: 리소스를 기다릴 수 있는 최대 시간 설정 가능
- **자동 리소스 할당**: GPU가 사용 가능해지면 자동으로 작업 시작

## 📦 사전 준비

### 1. 필요한 패키지 설치

```bash
pip install google-cloud-aiplatform>=1.25.0
```

### 2. 환경 변수 설정

`.env` 파일에 다음 환경 변수를 설정하세요:

```env
# Google Cloud 설정
GCP_PROJECT_ID=your-project-id
GCP_REGION=us-central1
GCP_STAGING_BUCKET=your-project-vertex-ai-staging

# Vertex AI Job 설정
VERTEX_AI_JOB_NAME=stock-prediction-dws-job
VERTEX_AI_MACHINE_TYPE=a2-highgpu-1g
VERTEX_AI_GPU_TYPE=NVIDIA_TESLA_A100
VERTEX_AI_GPU_COUNT=1
VERTEX_AI_MAX_WAIT_DURATION=1800  # 30분 (초 단위, 0이면 무제한 대기)
VERTEX_AI_TIMEOUT=3600  # 1시간 (초 단위, 최대 7일 = 604800초)

# Supabase 설정 (predict.py에서 사용)
SUPABASE_URL=your-supabase-url
SUPABASE_KEY=your-supabase-key

# Google Cloud 인증 (선택사항)
GOOGLE_APPLICATION_CREDENTIALS=path/to/credentials.json
VERTEX_AI_SERVICE_ACCOUNT=your-service-account@project.iam.gserviceaccount.com
```

### 3. Google Cloud 인증

```bash
# 방법 1: gcloud CLI 사용
gcloud auth application-default login

# 방법 2: 서비스 계정 키 파일 사용
export GOOGLE_APPLICATION_CREDENTIALS="path/to/credentials.json"
```

### 4. Cloud Storage 버킷 생성

스테이징 버킷이 없으면 생성하세요:

```bash
gsutil mb -p your-project-id -l us-central1 gs://your-project-vertex-ai-staging
```

## 🚀 사용 방법

### 전체 워크플로우

Vertex AI에서 predict.py를 실행하는 방법은 두 가지가 있습니다:

#### 방법 1: 패키지 빌드 및 업로드 후 실행 (권장)

이 방법은 패키지를 미리 빌드하고 GCS에 업로드한 후, 버전 관리와 함께 사용합니다.

```bash
# 1단계: predict.py를 패키지로 빌드하고 GCS에 업로드
python scripts/utils/upload_to_gcs.py

# 2단계: 업로드된 패키지를 사용하여 Vertex AI Job 실행
python scripts/run/run_predict_vertex_ai.py
```

**장점**:
- 패키지 버전 관리 (v1, v2, v3...)
- 재사용 가능 (같은 패키지를 여러 번 실행 가능)
- 빌드와 실행을 분리하여 관리 용이

#### 방법 2: 로컬 스크립트 직접 실행

로컬의 predict.py를 직접 사용하여 실행합니다.

```bash
# 환경 변수로 스크립트 경로 지정
PREDICT_SCRIPT_PATH=scripts/utils/predict.py python scripts/run/run_predict_vertex_ai.py
```

**장점**:
- 빠른 테스트에 유용
- 패키지 빌드 과정 생략

### 기본 실행

```bash
python scripts/run/run_predict_vertex_ai.py
```

기본적으로 GCS에서 가장 최신 버전의 패키지를 자동으로 찾아서 사용합니다.

### 환경 변수로 설정 오버라이드

```bash
# GPU 타입 변경 (L4 사용)
VERTEX_AI_GPU_TYPE=NVIDIA_L4 python run_predict_vertex_ai.py

# 대기 시간 변경 (1시간)
VERTEX_AI_MAX_WAIT_DURATION=3600 python run_predict_vertex_ai.py

# 무제한 대기 (리소스가 사용 가능해질 때까지 계속 대기)
VERTEX_AI_MAX_WAIT_DURATION=0 python run_predict_vertex_ai.py
```

## ⚙️ 설정 옵션

### 지원되는 GPU 타입

DWS는 다음 GPU 타입을 지원합니다:

- `NVIDIA_L4`: L4 GPU
- `NVIDIA_TESLA_A100`: A100 GPU (기본값)
- `NVIDIA_A100_80GB`: A100 80GB GPU
- `NVIDIA_H100_80GB`: H100 80GB GPU
- `NVIDIA_H200`: H200 GPU
- `NVIDIA_B200`: B200 GPU

### 머신 타입

GPU 타입에 따라 적절한 머신 타입을 선택하세요:

- **A100**: `a2-highgpu-1g`, `a2-highgpu-2g`, `a2-highgpu-4g`, `a2-highgpu-8g`
- **L4**: `g2-standard-4`, `g2-standard-8`, `g2-standard-12`, `g2-standard-16`
- **H100**: `a3-highgpu-1g`, `a3-highgpu-2g`, `a3-highgpu-4g`, `a3-highgpu-8g`

### 대기 시간 설정

- `max_wait_duration`: 리소스를 기다릴 수 있는 최대 시간 (초 단위)
  - `0`: 무제한 대기 (리소스가 사용 가능해질 때까지 계속 대기)
  - `1800`: 30분 (기본값)
  - `3600`: 1시간
  - `7200`: 2시간

### 타임아웃 설정

- `timeout`: Job 실행 최대 시간 (초 단위)
  - 최대 7일 (604800초)
  - 기본값: 3600초 (1시간)

## 📝 predict.py 수정 사항

`predict.py`를 Vertex AI에서 실행하려면 다음 수정이 필요합니다:

### 1. os 모듈 import 추가

```python
import os  # 추가 필요
```

### 2. Jupyter 노트북 전용 코드 제거

```python
# 이 줄 제거 또는 주석 처리
# !pip install supabase
```

## 📦 패키지 빌드 및 업로드

### upload_to_gcs.py 사용

`upload_to_gcs.py`는 `predict.py`를 Vertex AI CustomJob 형식의 패키지로 빌드하고 GCS에 업로드합니다.

#### 기본 사용법

```bash
# predict.py를 자동으로 빌드하고 업로드
python scripts/utils/upload_to_gcs.py

# 특정 파일 지정
python scripts/utils/upload_to_gcs.py --file scripts/utils/predict.py

# 버킷 지정
python scripts/utils/upload_to_gcs.py --bucket your-bucket-name

# 패키지 기본 이름 변경
python scripts/utils/upload_to_gcs.py --base-name my-package
```

#### 패키지 구조

빌드된 패키지는 다음 구조를 가집니다:

```
aiplatform_custom_trainer_script/
├── __init__.py
└── task.py          # predict.py의 내용
setup.py              # 패키지 메타데이터 및 의존성
MANIFEST.in           # 포함할 파일 목록
```

#### 버전 관리

패키지는 자동으로 버전 관리됩니다:

- 첫 번째 업로드: `predict-package-v1.tar.gz`
- 두 번째 업로드: `predict-package-v2.tar.gz`
- 버전 정보는 `predict-package-version.json`에 저장됩니다

#### GCS 저장 위치

```
gs://your-bucket-name/
├── packages/
│   ├── predict-package-v1.tar.gz
│   ├── predict-package-v2.tar.gz
│   └── predict-package-v3.tar.gz
└── predict-package-version.json
```

#### 환경 변수

```bash
# GCS 버킷 이름 (기본값: stock-trading-packages)
GCP_BUCKET_NAME=your-bucket-name

# Google Cloud 프로젝트 ID
GCP_PROJECT_ID=your-project-id
```

### 패키지 빌드 프로세스

1. **스크립트 읽기**: `predict.py` 파일을 읽습니다
2. **패키지 구조 생성**: `aiplatform_custom_trainer_script/` 디렉토리 생성
3. **task.py 생성**: `predict.py` 내용을 `task.py`로 복사
   - `main()` 함수 확인 및 entry point 추가
   - 모듈 실행 시 작동하도록 조건 추가
4. **setup.py 생성**: 패키지 메타데이터 및 의존성 정의
5. **MANIFEST.in 생성**: 포함할 파일 목록 정의
6. **tar.gz 압축**: 패키지를 tar.gz로 압축
7. **GCS 업로드**: 버전 관리와 함께 GCS에 업로드

## 🔧 패키지 설치 방식

### 자동 패키지 설치 (권장)

`run_predict_vertex_ai.py`는 `from_local_script`의 `requirements` 파라미터를 사용하여 필요한 패키지를 자동으로 설치합니다:

```python
required_packages = [
    "supabase>=2.0.0",
    "pandas>=2.0.0",
    "numpy>=1.24.0",
    "scikit-learn>=1.3.0",
    "tensorflow>=2.11.0",
    "matplotlib>=3.7.0",
    "pymongo>=4.6.0",  # MongoDB 연결용
    "protobuf>=3.20.1,<5.0.0dev",  # 버전 충돌 해결
]

job = aiplatform.CustomJob.from_local_script(
    script_path="predict.py",
    requirements=required_packages,  # 자동으로 pip install 실행
    # ... 기타 설정
)
```

**동작 방식**:
1. Vertex AI가 컨테이너를 시작합니다
2. `requirements` 리스트의 패키지들을 자동으로 `pip install` 합니다
3. 패키지 설치 완료 후 `predict.py`를 실행합니다

### 실행 흐름

#### 방법 1: 패키지 빌드 및 업로드 방식 (권장)

```
1. 로컬에서 python scripts/utils/upload_to_gcs.py 실행
   ↓
2. predict.py를 Vertex AI CustomJob 형식으로 패키징
   - aiplatform_custom_trainer_script/task.py 생성
   - setup.py, MANIFEST.in 생성
   - tar.gz 파일로 압축
   ↓
3. GCS 스테이징 버킷에 버전 관리와 함께 업로드
   - packages/predict-package-v{version}.tar.gz
   - predict-package-version.json (버전 정보 저장)
   ↓
4. 로컬에서 python scripts/run/run_predict_vertex_ai.py 실행
   ↓
5. GCS에서 최신 버전 패키지 자동 검색
   - predict-package-version.json에서 최신 버전 확인
   - 또는 패키지 파일 패턴으로 최신 버전 찾기
   ↓
6. Vertex AI CustomJob 생성 (package_uri 사용)
   ↓
7. Vertex AI가 TensorFlow GPU 컨테이너 인스턴스 생성
   ↓
8. 컨테이너 내부에서 패키지 설치
   - pip install -e /path/to/package.tar.gz
   - setup.py의 install_requires에 따라 패키지 자동 설치
   ↓
9. python -m aiplatform_custom_trainer_script.task 실행
   ↓
10. 결과 저장 (Supabase, MongoDB 등)
```

#### 방법 2: 로컬 스크립트 직접 실행 방식

```
1. 로컬에서 python scripts/run/run_predict_vertex_ai.py 실행
   (PREDICT_SCRIPT_PATH 환경 변수로 스크립트 경로 지정)
   ↓
2. from_local_script가 predict.py를 tar.gz로 패키징
   ↓
3. GCS 스테이징 버킷에 임시 업로드
   ↓
4. Vertex AI가 TensorFlow GPU 컨테이너 인스턴스 생성
   ↓
5. 컨테이너 내부에서 pip install 실행
   - pip install supabase>=2.0.0
   - pip install pandas>=2.0.0
   - pip install numpy>=1.24.0
   - pip install scikit-learn>=1.3.0
   - pip install tensorflow>=2.11.0
   - pip install matplotlib>=3.7.0
   - pip install pymongo>=4.6.0
   - pip install "protobuf>=3.20.1,<4.0.0dev"
   ↓
6. python -m aiplatform_custom_trainer_script.task 실행
   ↓
7. 결과 저장 (Supabase 등)
```

### 자동 패키지 설치 (predict.py 내부)

`predict.py` 스크립트 시작 부분에 자동 패키지 설치 로직이 포함되어 있습니다:

```python
def install_required_packages():
    """필요한 패키지가 없으면 자동으로 설치"""
    required_packages = {
        "pymongo": "pymongo>=4.6.0",
        "protobuf": "protobuf>=3.20.1,<5.0.0dev"
    }
    # ... 자동 설치 로직
```

이렇게 하면:
- `from_local_script`를 사용하는 경우: `requirements` 파라미터로 설치
- 기존 패키지를 사용하는 경우: `predict.py` 내부에서 자동 설치
- 어떤 방식으로 실행되든 필요한 패키지가 자동으로 설치됨

### 수동 패키지 설치 (대안)

만약 `requirements` 파라미터 대신 `requirements.txt` 파일을 사용하려면:

1. `requirements.txt` 파일 생성
2. `predict.py` 내에서 직접 설치 (이미 구현됨)

## 🔍 모니터링

### Google Cloud Console에서 확인

1. [Vertex AI Custom Jobs 페이지](https://console.cloud.google.com/vertex-ai/training/custom-jobs) 접속
2. 실행 중인 Job 확인
3. 로그 및 상태 모니터링

### 로그 확인

```bash
# gcloud CLI로 로그 확인
gcloud ai custom-jobs describe JOB_ID \
  --project=your-project-id \
  --region=us-central1
```

## 💰 비용

### GPU 비용 (시간당)

- **L4**: $0.4025/시간
- **A100**: $3.00/시간
- **H100**: $8.00/시간
- **H200**: $10.00/시간
- **B200**: $12.00/시간

### DWS 추가 비용

DWS를 사용하면 동적 워크로드 스케줄러 가격 책정이 적용됩니다. 인프라 사용량 외에 서버리스 학습 관리 수수료가 있습니다.

## ⚠️ 주의사항

1. **할당량 확인**: DWS를 사용하면 선점형(preemptible) 할당량을 소비합니다. 할당량이 충분한지 확인하세요.

2. **최대 대기 시간**: `max_wait_duration`을 0으로 설정하면 리소스가 사용 가능해질 때까지 무제한 대기합니다. 비용이 발생하지 않지만, 작업이 시작되지 않을 수 있습니다.

3. **타임아웃**: Job 실행 시간이 `timeout`을 초과하면 작업이 중단됩니다. 충분한 시간을 설정하세요.

4. **환경 변수**: `predict.py`에서 사용하는 환경 변수(SUPABASE_URL, SUPABASE_KEY 등)가 올바르게 설정되어 있는지 확인하세요.

## 🐛 문제 해결

### Exit Status 127 오류 (command not found)

**오류 메시지**:
```
The replica workerpool0-0 exited with a non-zero status of 127
```

**원인**:
- PythonPackageSpec을 사용할 때 Vertex AI는 `python -m {python_module}` 형태로 실행합니다
- TensorFlow GPU 컨테이너에는 `python3`는 있지만 `python` 명령어가 없을 수 있습니다
- `python` 명령어를 찾을 수 없어서 exit 127 발생

**해결 방법**:

1. **환경 변수에 python3 경로 추가** (자동 처리됨)
   - `run_predict_vertex_ai.py`에서 자동으로 PATH에 python3 경로 추가
   - `/usr/bin`, `/usr/local/bin` 경로를 PATH 앞에 추가

2. **PYTHON 환경 변수 설정** (자동 처리됨)
   - `PYTHON=python3` 환경 변수 설정

3. **컨테이너 확인** (수동 검증)
   ```bash
   # TensorFlow GPU 컨테이너에서 python 명령어 확인
   docker run --rm -it us-docker.pkg.dev/vertex-ai/training/tf-gpu.2-13.py310:latest bash
   which python
   which python3
   python --version
   python3 --version
   ```

4. **패키지 빌드 확인**
   - `task.py`에 올바른 entry point가 있는지 확인
   - 조건 없는 `main()` 호출이 없는지 확인
   - `if __name__ == "__main__" or __name__.endswith(".task") or __name__ == "aiplatform_custom_trainer_script.task":` 조건 포함 확인

**참고**:
- PythonPackageSpec을 사용하면 `containerSpec.command`/`args`는 사용하지 않습니다
- PythonPackageSpec은 SDK가 자동으로 `python -m {python_module}` 형태로 실행합니다
- 현재 코드는 자동으로 python3 경로를 PATH에 추가하므로 대부분의 경우 해결됩니다

### GPU 할당량 부족

```
Error: The following quota metrics exceed quota limits
```

**해결 방법**:
1. 할당량 증가 요청: [Google Cloud Console 할당량 페이지](https://console.cloud.google.com/iam-admin/quotas)
2. 다른 GPU 타입 사용 (예: L4 → A100)
3. 다른 리전 사용

### 인증 오류

```
Error: Could not automatically determine credentials
```

**해결 방법**:
```bash
gcloud auth application-default login
```

또는

```bash
export GOOGLE_APPLICATION_CREDENTIALS="path/to/credentials.json"
```

### 스크립트 파일을 찾을 수 없음

```
FileNotFoundError: 스크립트 파일을 찾을 수 없습니다
```

**해결 방법**:
```bash
# 환경 변수로 스크립트 경로 지정
PREDICT_SCRIPT_PATH=/absolute/path/to/predict.py python run_predict_vertex_ai.py
```

## 📚 참고 자료

- [Vertex AI 동적 워크로드 스케줄러 문서](https://docs.cloud.google.com/vertex-ai/docs/training/schedule-jobs-dws?hl=ko)
- [Vertex AI CustomJob 문서](https://cloud.google.com/vertex-ai/docs/training/create-custom-job)
- [GPU 할당량 증가 가이드](./GPU_할당량_증가_가이드.md)

## 🔗 관련 파일

- `scripts/run/run_predict_vertex_ai.py`: Vertex AI DWS를 사용하여 predict.py를 실행하는 스크립트
- `scripts/utils/predict.py`: 주식 예측 모델 학습 및 예측 스크립트
- `scripts/utils/upload_to_gcs.py`: predict.py를 패키지로 빌드하고 GCS에 업로드하는 스크립트
- `requirements.txt`: 필요한 Python 패키지 목록

## 📋 전체 프로세스 체크리스트

### 초기 설정

- [ ] Google Cloud 프로젝트 생성 및 활성화
- [ ] Vertex AI API 활성화
- [ ] Cloud Storage 버킷 생성
- [ ] 서비스 계정 생성 및 권한 부여
- [ ] 환경 변수 설정 (.env 파일)

### 패키지 빌드 및 업로드

- [ ] `predict.py` 파일 확인 및 수정
  - [ ] `main()` 함수 포함 확인
  - [ ] entry point 확인 (`if __name__ == "__main__" or __name__.endswith(".task")`)
  - [ ] MongoDB 조회 로직 확인
- [ ] 패키지 빌드: `python scripts/utils/upload_to_gcs.py`
- [ ] GCS 업로드 확인
- [ ] 버전 정보 확인

### Vertex AI Job 실행

- [ ] 환경 변수 확인
  - [ ] `GCP_PROJECT_ID`
  - [ ] `GCP_REGION`
  - [ ] `GCP_STAGING_BUCKET`
  - [ ] `SUPABASE_URL`, `SUPABASE_KEY`
  - [ ] `MONGODB_URL` (선택사항)
- [ ] Job 실행: `python scripts/run/run_predict_vertex_ai.py`
- [ ] 로그 확인
- [ ] 결과 확인 (Supabase, MongoDB)
