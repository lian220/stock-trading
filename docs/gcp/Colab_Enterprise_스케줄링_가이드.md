# Colab Enterprise 노트북 T4 GPU 스케줄링 가이드

## 🎯 목표
Google Colab Enterprise 노트북을 T4 GPU로 일정 주기마다 자동으로 실행하기

## 📋 사전 준비

### 1. 필요한 권한
- **관리자 권한**: 기본 런타임 템플릿 생성 및 스케줄링 설정을 위해 필요합니다
- **Colab Enterprise 접근 권한**: Google Cloud Console에서 Colab Enterprise에 접근 가능해야 합니다

### 2. Google Cloud 프로젝트 설정

```bash
# 1. Google Cloud CLI 설치 및 로그인
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# 2. 필요한 API 활성화
gcloud services enable notebooks.googleapis.com
gcloud services enable aiplatform.googleapis.com
gcloud services enable storage.googleapis.com
```

---

## 🚀 단계별 설정

### 1단계: 기본 런타임 템플릿 생성 (관리자)

T4 GPU를 포함한 기본 런타임 템플릿을 생성합니다.

#### Google Cloud Console에서 설정:

1. **Google Cloud Console** 접속
   - https://console.cloud.google.com/

2. **Colab Enterprise** 메뉴로 이동
   - 왼쪽 메뉴에서 "Vertex AI" → "Workbench" → "Colab Enterprise" 선택
   - 또는 직접 URL: https://console.cloud.google.com/vertex-ai/workbench/colab

3. **기본 런타임 템플릿 생성**
   - 왼쪽 메뉴에서 **"Runtime templates"** 선택
   - **"Create runtime template"** 클릭
   - 다음 설정 입력:
     ```
     Template name: t4-gpu-template
     Machine type: n1-standard-4
     Accelerator type: NVIDIA_TESLA_T4
     Accelerator count: 1
     Data disk: 100 GB (pd-standard)
     ```
   - **"Create"** 클릭

#### 또는 gcloud CLI로 생성:

```bash
# 기본 런타임 템플릿 생성 (T4 GPU 포함)
gcloud notebooks runtimes create t4-gpu-template \
  --location=us-central1 \
  --machine-type=n1-standard-4 \
  --accelerator-type=NVIDIA_TESLA_T4 \
  --accelerator-count=1 \
  --data-disk-size=100 \
  --data-disk-type=pd-standard
```

**참고**: T4 GPU가 지원되는 리전 확인
- `us-central1` (Iowa)
- `us-east1` (South Carolina)
- `us-west1` (Oregon)
- `europe-west4` (Netherlands)
- `asia-southeast1` (Singapore)

---

### 2단계: 노트북 준비

#### 노트북 URL 확인
- Colab Enterprise 노트북 URL: `https://colab.research.google.com/drive/1j2dKN9jktFFldMI9YDaBXEVNsy6gGspV`
- 이 노트북이 Colab Enterprise에 업로드되어 있어야 합니다

#### 노트북 환경 변수 설정
노트북 내에서 Supabase 연결 정보를 환경 변수로 설정:

```python
import os

# 환경 변수 설정 (노트북 내에서)
os.environ["SUPABASE_URL"] = "YOUR_SUPABASE_URL"
os.environ["SUPABASE_KEY"] = "YOUR_SUPABASE_KEY"
```

또는 노트북 시작 부분에 다음 코드 추가:

```python
# Supabase 연결 설정
url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")
```

---

### 3단계: 노트북 스케줄링 설정

#### Google Cloud Console에서 스케줄링:

1. **Colab Enterprise 노트북 페이지로 이동**
   - https://console.cloud.google.com/vertex-ai/workbench/colab/notebooks

2. **노트북 선택**
   - 스케줄링할 노트북을 클릭하여 선택

3. **스케줄 메뉴 열기**
   - 노트북 상단의 **"Notebook actions"** (⋮) 메뉴 클릭
   - **"Schedule"** 선택

4. **스케줄 설정**
   ```
   Schedule name: predict-daily-schedule
   Runtime template: t4-gpu-template (1단계에서 생성한 템플릿)
   Run schedule: Recurring
   Frequency: Daily (또는 원하는 주기)
   Time: 01:00 (한국 시간 기준 새벽 1시 = UTC 16:00)
   Timezone: Asia/Seoul
   ```

5. **출력 위치 설정**
   - **Output location**: Cloud Storage 버킷 선택
     - 예: `gs://your-bucket-name/colab-outputs/`
   - 결과 파일이 이 버킷에 저장됩니다

6. **서비스 계정 설정** (필요한 경우)
   - 런타임 템플릿에 end-user credentials가 비활성화된 경우
   - **Service account** 필드에 서비스 계정 이메일 입력
   - 서비스 계정에는 다음 권한이 필요:
     - `storage.objects.create` (Cloud Storage 쓰기)
     - `aiplatform.user` (Vertex AI 사용)

7. **제출**
   - **"Submit"** 클릭하여 스케줄 생성 완료

#### 또는 gcloud CLI로 스케줄링:

```bash
# 노트북 스케줄 생성
gcloud notebooks schedules create predict-daily-schedule \
  --location=us-central1 \
  --notebook-id=YOUR_NOTEBOOK_ID \
  --runtime-template=t4-gpu-template \
  --schedule="0 1 * * *" \
  --timezone="Asia/Seoul" \
  --output-location=gs://your-bucket-name/colab-outputs/
```

**스케줄 표현식 (Cron 형식)**:
- 매일 새벽 1시: `0 1 * * *`
- 매일 오전 9시: `0 9 * * *`
- 매주 월요일 새벽 1시: `0 1 * * 1`
- 매시간: `0 * * * *`

---

### 4단계: 스케줄 확인 및 관리

#### 스케줄 목록 확인:

```bash
# 모든 스케줄 목록 조회
gcloud notebooks schedules list --location=us-central1
```

#### 스케줄 실행 이력 확인:

1. **Google Cloud Console**에서:
   - "Vertex AI" → "Workbench" → "Colab Enterprise" → "Schedules" 선택
   - 스케줄을 클릭하여 실행 이력 확인

2. **실행 로그 확인**:
   - 각 실행의 로그는 Cloud Storage 버킷의 출력 위치에 저장됩니다
   - 또는 Cloud Logging에서 확인:
     ```bash
     gcloud logging read "resource.type=notebooks.googleapis.com/Notebook" --limit=50
     ```

#### 스케줄 수정:

```bash
# 스케줄 업데이트
gcloud notebooks schedules update predict-daily-schedule \
  --location=us-central1 \
  --schedule="0 2 * * *"  # 새벽 2시로 변경
```

#### 스케줄 삭제:

```bash
# 스케줄 삭제
gcloud notebooks schedules delete predict-daily-schedule \
  --location=us-central1
```

---

## 💰 비용 관리

### T4 GPU 비용 (2024년 기준)

Colab Enterprise (Vertex AI Workbench)의 T4 GPU 비용 구조:

#### 1. GPU 비용
- **T4 GPU 기본 비용**: 약 **$0.525/시간** (Compute Engine 가격)
- **Vertex AI Workbench 관리 수수료**: **$0.35/GPU 시간**
- **GPU 총 비용**: 약 **$0.875/시간**

#### 2. 머신 타입 비용
- **n1-standard-4 머신 타입**: 약 **$0.19/시간**
  - 4 vCPU, 15GB RAM

#### 3. 총 예상 비용
- **총 시간당 비용**: 약 **$1.065/시간** ($0.875 + $0.19)
- **하루 1시간 실행 시**: 약 **$1.065/일**
- **한 달 (30일) 실행 시**: 약 **$31.95/월**

#### 4. 실제 사용 예시
- **predict.py 실행 시간**: 약 30분 ~ 1시간 (데이터 크기에 따라 다름)
- **일일 실행 비용**: 약 **$0.50 ~ $1.10/일**
- **월간 실행 비용**: 약 **$15 ~ $33/월**

**참고**: 
- 리전에 따라 가격이 다를 수 있습니다
- 최신 가격은 [Vertex AI 가격 페이지](https://cloud.google.com/vertex-ai/pricing)에서 확인하세요

### 비용 최적화 팁
1. **실행 시간 최소화**: 노트북 코드 최적화
2. **필요한 시간에만 실행**: 불필요한 스케줄 제거
3. **비용 알림 설정**: Cloud Billing에서 예산 알림 설정

```bash
# 예산 알림 설정
gcloud billing budgets create \
  --billing-account=YOUR_BILLING_ACCOUNT_ID \
  --display-name="Colab Enterprise Budget" \
  --budget-amount=100USD \
  --threshold-rule=percent=50 \
  --threshold-rule=percent=90 \
  --threshold-rule=percent=100
```

---

## 🔧 문제 해결

### 문제 0: 무료 티어에서 GPU 사용 불가 오류 ⚠️

**증상**: 
```
Your billing account is currently in the free tier where non-TPU accelerators are not available. 
Please upgrade to a paid billing account
```

**원인**: 
- Google Cloud 무료 티어에서는 GPU(비-TPU 가속기) 사용이 제한됩니다
- T4 GPU를 사용하려면 유료 결제 계정으로 업그레이드해야 합니다

**해결 방법**:

#### 1단계: 결제 계정 업그레이드

1. **Google Cloud Console 접속**
   - https://console.cloud.google.com/

2. **결제 계정 업그레이드**
   - 상단 메뉴에서 **"Free trial status"** 또는 **"Activate"** 버튼 클릭
   - 또는 직접: https://console.cloud.google.com/billing
   - **"Upgrade"** 또는 **"계정 업그레이드"** 클릭

3. **결제 정보 입력**
   - 신용카드 또는 결제 수단 등록
   - 결제 프로필 생성

**중요 사항**:
- 무료 티어 크레딧이 남아있으면 먼저 사용됩니다
- 크레딧 소진 후에만 실제 결제가 발생합니다
- 무료 티어 크레딧: 보통 $300 (90일간 사용 가능)

#### 2단계: GPU 할당량 요청

업그레이드 후 GPU 할당량을 요청해야 합니다:

1. **할당량 페이지 접속**
   - https://console.cloud.google.com/iam-admin/quotas
   - 또는 "IAM & Admin" → "Quotas" 메뉴

2. **GPU 할당량 필터링**
   - 검색창에 `NVIDIA_TESLA_T4` 입력
   - 또는 `GPU` 검색

3. **할당량 증가 요청**
   - T4 GPU 할당량 선택
   - **"Edit Quotas"** 클릭
   - 필요한 할당량 입력 (예: 1개)
   - 요청 사유 입력:
     ```
     Colab Enterprise 노트북에서 T4 GPU를 사용하여 
     주식 예측 모델 학습을 실행하기 위해 필요합니다.
     ```
   - **"Submit Request"** 클릭

4. **승인 대기**
   - 보통 24-48시간 내 승인됩니다
   - 이메일로 승인 알림을 받습니다

#### 3단계: 업그레이드 확인

```bash
# 현재 프로젝트의 결제 계정 확인
gcloud billing accounts list

# 프로젝트에 결제 계정 연결 확인
gcloud billing projects describe YOUR_PROJECT_ID
```

**참고 링크**:
- [무료 티어 업그레이드 가이드](https://cloud.google.com/free/docs/gcp-free-tier#how-to-upgrade)
- [GPU 할당량 요청 가이드](https://cloud.google.com/compute/docs/gpus/request-gpu-quota)

---

### 문제 1: T4 GPU 할당량 부족

**증상**: 스케줄 실행 시 "quota exceeded" 오류

**해결 방법**:
1. Google Cloud Console에서 할당량 확인:
   - "IAM & Admin" → "Quotas" → "NVIDIA_TESLA_T4" 검색
2. 할당량 증가 요청:
   - 할당량 페이지에서 "Edit Quotas" 클릭
   - 필요한 할당량 입력 후 요청 제출

### 문제 2: 노트북 실행 실패

**증상**: 스케줄이 실행되지만 노트북이 실패

**해결 방법**:
1. **로그 확인**:
   ```bash
   gcloud logging read "resource.type=notebooks.googleapis.com/Notebook" --limit=50 --format=json
   ```
2. **환경 변수 확인**: 노트북 내에서 `os.getenv()`로 환경 변수 확인
3. **의존성 확인**: 필요한 패키지가 모두 설치되어 있는지 확인

### 문제 3: 스케줄이 실행되지 않음

**해결 방법**:
1. **스케줄 상태 확인**:
   ```bash
   gcloud notebooks schedules describe predict-daily-schedule --location=us-central1
   ```
2. **시간대 확인**: 스케줄의 timezone 설정 확인
3. **권한 확인**: 서비스 계정에 필요한 권한이 있는지 확인

---

## 📚 참고 자료

- [Colab Enterprise 공식 문서](https://cloud.google.com/colab/docs)
- [기본 런타임 템플릿 설정](https://cloud.google.com/colab/docs/default-runtimes-with-gpus)
- [노트북 스케줄링 가이드](https://cloud.google.com/colab/docs/schedule-notebook-run)
- [GPU 가격 정보](https://cloud.google.com/vertex-ai/pricing)

---

## 🎯 요약

1. ✅ **기본 런타임 템플릿 생성** (T4 GPU 포함)
2. ✅ **노트북 준비** (환경 변수 설정)
3. ✅ **스케줄 생성** (원하는 주기 설정)
4. ✅ **실행 확인** (로그 및 결과 확인)

이제 Colab Enterprise 노트북이 T4 GPU로 자동으로 주기적으로 실행됩니다! 🚀
