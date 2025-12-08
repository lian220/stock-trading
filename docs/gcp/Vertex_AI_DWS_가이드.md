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

### 기본 실행

```bash
python run_predict_vertex_ai.py
```

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

```
1. 로컬에서 python run_predict_vertex_ai.py 실행
   ↓
2. from_local_script가 predict.py를 tar.gz로 패키징
   ↓
3. GCS 스테이징 버킷에 업로드 (예: gs://stock-trading-packages)
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
   ↓
6. python predict.py 실행
   ↓
7. 결과 저장 (Supabase 등)
```

### 수동 패키지 설치 (대안)

만약 `requirements` 파라미터 대신 `requirements.txt` 파일을 사용하려면:

1. `requirements.txt` 파일 생성
2. `predict.py` 내에서 직접 설치:

```python
import subprocess
import sys

def install_packages():
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
```

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

- `run_predict_vertex_ai.py`: Vertex AI DWS를 사용하여 predict.py를 실행하는 스크립트
- `predict.py`: 주식 예측 모델 학습 및 예측 스크립트
- `requirements.txt`: 필요한 Python 패키지 목록
