# Colab Extension을 사용한 T4 GPU 스케줄링 가이드

## 🎯 목표
VS Code의 Colab Extension을 사용하여 Google Colab 노트북을 T4 GPU로 연결하고, 일정 주기마다 자동 실행하기

## 📋 사전 준비

### 1. Colab Extension 설치 확인
- VS Code에서 "Google Colab" extension이 설치되어 있어야 합니다
- Extension ID: `Google.colab`

### 2. 필요한 것들
- Google 계정 (Colab 접근 권한)
- Colab Pro 또는 Colab Pro+ 구독 (T4 GPU 사용을 위해 권장)
- 또는 무료 Colab (GPU 사용 시간 제한 있음)

---

## 🚀 단계별 설정

### 1단계: Colab Extension으로 노트북 연결

#### VS Code에서 설정:

1. **Colab Extension 설치**
   - VS Code에서 Extensions 탭 열기 (Ctrl+Shift+X 또는 Cmd+Shift+X)
   - "Google Colab" 검색
   - Extension ID: `Google.colab` 설치

2. **노트북 파일 열기**
   - `predict.py`를 `.ipynb` 형식으로 변환하거나
   - 기존 Colab 노트북을 VS Code에서 열기
   - 또는 새 `.ipynb` 파일 생성

3. **Colab 런타임 선택 및 로그인**
   - 노트북 파일을 열면 상단 오른쪽에 **"Select Kernel"** 버튼이 표시됩니다
   - **"Select Kernel"** 버튼 클릭
   - 목록에서 **"Colab"** 선택
   - **처음 선택 시**: 브라우저가 자동으로 열리거나 VS Code 내에서 Google 계정 로그인 창이 나타납니다
   - Google 계정으로 로그인 (Gmail 계정 사용)
   - 로그인 완료 후 VS Code로 돌아오면 Colab 런타임에 연결됩니다

4. **GPU 런타임 선택**
   - 런타임이 연결되면 다시 **"Select Kernel"** 클릭
   - 또는 노트북 상단의 런타임 정보 클릭
   - **"Change Runtime Type"** 또는 **"GPU"** 옵션 선택
   - T4 GPU가 자동으로 할당됩니다 (Colab Pro/Pro+ 사용 시)

5. **노트북 실행**
   - 노트북 셀을 클릭하고 **Shift + Enter** 또는 **▶️ Run** 버튼 클릭
   - 또는 상단 메뉴에서 **"Run All"** 선택하여 모든 셀 실행

#### 또는 Colab 웹에서 직접:

1. **Colab 노트북 열기**
   - https://colab.research.google.com/drive/1j2dKN9jktFFldMI9YDaBXEVNsy6gGspV

2. **런타임 설정**
   - 상단 메뉴: **"Runtime"** → **"Change runtime type"**
   - **Hardware accelerator**: **"GPU"** 선택
   - **GPU type**: **"T4"** 선택 (Colab Pro+ 사용 시)
   - **"Save"** 클릭

---

### 2단계: 노트북 환경 변수 설정

Colab 노트북 시작 부분에 환경 변수 설정 코드 추가:

```python
import os

# 환경 변수 설정
os.environ["SUPABASE_URL"] = "YOUR_SUPABASE_URL"
os.environ["SUPABASE_KEY"] = "YOUR_SUPABASE_KEY"

# Supabase 클라이언트 생성
from supabase import create_client, Client
url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url, key)
```

**보안 팁**: 민감한 정보는 Colab의 Secrets 기능 사용:
```python
from google.colab import userdata

# Secrets에서 값 가져오기
url = userdata.get('SUPABASE_URL')
key = userdata.get('SUPABASE_KEY')
```

Secrets 설정 방법:
1. Colab 노트북에서 **"🔑"** 아이콘 클릭 (왼쪽 사이드바)
2. **"Add new secret"** 클릭
3. Key와 Value 입력
4. 노트북에서 `userdata.get('KEY_NAME')`으로 사용

---

### 3단계: 스케줄링 방법 선택

Colab 자체에는 스케줄링 기능이 없으므로, 다음 방법 중 선택:

#### 방법 1: 현재 프로젝트의 Scheduler 활용 (추천) ⭐

이미 구현된 `scheduler.py`를 사용하여 Colab 노트북을 트리거:

1. **Colab 노트북을 API로 실행 가능하게 만들기**

   Colab 노트북에 다음 코드 추가 (마지막 셀):
   
   ```python
   # 노트북 실행 완료 알림 (선택사항)
   import requests
   
   def notify_completion(status="success"):
       webhook_url = "YOUR_WEBHOOK_URL"  # Slack 또는 다른 웹훅
       message = f"Colab 노트북 실행 완료: {status}"
       requests.post(webhook_url, json={"text": message})
   
   # 실행 완료 후 알림
   notify_completion("success")
   ```

2. **Scheduler에서 Colab API 호출**

   `app/utils/scheduler.py`에 Colab 실행 함수 추가:
   
   ```python
   async def _execute_colab_notebook(self):
       """Colab 노트북 실행 (Colab API 사용)"""
       import httpx
       
       # Colab 노트북 실행을 위한 API 호출
       # 참고: Colab은 직접 API가 없으므로, 
       # 대신 Vertex AI나 다른 방법 사용 권장
       
       # 또는 Colab의 "Runtime" → "Run all" 기능을
       # 자동화하려면 Selenium 등 사용 (복잡함)
   ```

   **더 나은 방법**: 현재 프로젝트의 Vertex AI Job 방식을 그대로 사용하는 것을 권장합니다.

#### 방법 2: Google Cloud Scheduler + Cloud Functions

Colab 노트북을 Cloud Functions로 래핑하여 스케줄링:

1. **Cloud Functions 생성**
   ```bash
   # Cloud Functions에 Colab 노트북 코드 배포
   gcloud functions deploy run-colab-notebook \
     --runtime python39 \
     --trigger-http \
     --allow-unauthenticated \
     --memory 8GB \
     --timeout 540s
   ```

2. **Cloud Scheduler로 스케줄링**
   ```bash
   gcloud scheduler jobs create http run-colab-daily \
     --schedule="0 1 * * *" \
     --time-zone="Asia/Seoul" \
     --uri="https://REGION-PROJECT.cloudfunctions.net/run-colab-notebook" \
     --http-method=POST
   ```

#### 방법 3: 현재 프로젝트의 Vertex AI 방식 사용 (가장 추천) ⭐⭐⭐

이미 구현된 Vertex AI Job 방식을 그대로 사용:

- `app/utils/scheduler.py`의 `_execute_colab_trigger()` 함수 사용
- Vertex AI Custom Job 또는 Training Job으로 실행
- T4 GPU 자동 할당
- 스케줄링 이미 구현됨

**장점**:
- ✅ 이미 구현되어 있음
- ✅ T4 GPU 자동 할당
- ✅ 스케줄링 기능 완비
- ✅ 로그 및 모니터링 가능

---

### 4단계: 현재 프로젝트 Scheduler 활용 (권장)

현재 프로젝트의 스케줄러를 사용하여 Vertex AI Job 실행:

#### 설정 확인:

1. **`.env` 파일 설정**
   ```env
   GCP_PROJECT_ID=your-project-id
   GCP_REGION=us-central1
   VERTEX_AI_GPU_TYPE=NVIDIA_TESLA_T4
   VERTEX_AI_GPU_COUNT=1
   VERTEX_AI_MACHINE_TYPE=n1-standard-4
   ```

2. **스케줄러 시작**
   ```python
   from app.utils.scheduler import start_scheduler
   
   # 스케줄러 시작 (매일 새벽 1시에 Vertex AI Job 실행)
   start_scheduler()
   ```

3. **스케줄 확인**
   - `scheduler.py`의 76번째 줄: `schedule.every().day.at("11:00").do(self._run_colab_trigger)`
   - 한국 시간 기준 새벽 1시에 실행됩니다

#### 수동 실행 (테스트):

```python
from app.utils.scheduler import run_colab_trigger_now

# 즉시 Vertex AI Job 실행
run_colab_trigger_now()
```

---

## 💰 비용 비교

### Colab Pro/Pro+ 비용
- **Colab Pro**: $9.99/월
  - T4 GPU 사용 가능 (시간 제한 있음)
  - 우선 실행 권한
- **Colab Pro+**: $49.99/월
  - T4 GPU 사용 가능
  - 더 긴 세션 시간
  - 더 높은 우선순위

### Vertex AI Job 비용 (현재 프로젝트 방식)
- **T4 GPU**: 약 $0.875/시간
- **머신 타입**: 약 $0.19/시간
- **총**: 약 $1.065/시간
- **월간 예상**: 약 $15-33/월 (매일 30분-1시간 실행 시)

**비교**:
- Colab Pro+: 고정 비용 ($49.99/월)
- Vertex AI: 사용한 만큼만 과금 (더 유연함)

---

## ❓ 자주 묻는 질문 (FAQ)

### Q1: "Google 계정으로 로그인"은 파일을 어떻게 실행하는 건가요?

**A**: 이것은 파일을 실행하는 것이 아니라, VS Code Extension의 UI를 통한 설정 과정입니다.

**단계별 설명**:

1. **VS Code에서 노트북 파일 열기**
   ```bash
   # 예: predict.ipynb 파일을 VS Code에서 열기
   code predict.ipynb
   ```

2. **Select Kernel 버튼 클릭**
   - 노트북 파일을 열면 상단 오른쪽에 "Select Kernel" 버튼이 보입니다
   - 이 버튼을 클릭합니다

3. **Colab 선택**
   - 드롭다운 메뉴에서 "Colab" 선택
   - 처음 선택하면 자동으로 브라우저가 열리거나 VS Code 내에서 로그인 창이 나타납니다

4. **Google 계정 로그인**
   - 브라우저에서 Google 계정 선택 및 로그인
   - 권한 승인 (VS Code가 Colab에 접근할 수 있도록)
   - 로그인 완료 후 VS Code로 자동으로 돌아옵니다

5. **실제 코드 실행**
   - 로그인 후 노트북 셀에서 **Shift + Enter** 또는 **▶️ Run** 버튼 클릭
   - 이때 코드가 Google Colab의 원격 서버에서 실행됩니다

**요약**: 
- 로그인 = VS Code와 Google Colab을 연결하는 설정 과정
- 실행 = 노트북 셀에서 Shift+Enter 또는 Run 버튼 클릭

### Q2: 명령줄에서 실행할 수 있나요?

**A**: Colab Extension은 VS Code UI를 통해서만 작동합니다. 명령줄로는 직접 실행할 수 없습니다.

**대안**:
- **Colab 웹에서 직접 실행**: https://colab.research.google.com
- **Vertex AI Job 사용** (권장): 현재 프로젝트의 `run_predict_vertex_ai.py` 사용
  ```bash
  python run_predict_vertex_ai.py
  ```

### Q3: 자동으로 실행되게 할 수 있나요?

**A**: Colab Extension 자체는 자동 실행을 지원하지 않습니다. 하지만 현재 프로젝트의 스케줄러를 사용하면 자동 실행이 가능합니다:

```python
# 스케줄러 시작 (매일 밤 11시 자동 실행)
from app.utils.scheduler import start_scheduler
start_scheduler()
```

이 방식은 Vertex AI Job을 사용하여 자동으로 실행됩니다.

### Q4: Docker 컨테이너에서 Colab Extension을 사용할 수 있나요?

**A**: ❌ **불가능합니다.**

**이유**:
1. **VS Code Extension 필요**: Colab Extension은 VS Code Extension이므로 VS Code 환경이 필요합니다
2. **GUI 없음**: Docker 컨테이너는 일반적으로 GUI가 없는 헤드리스 환경입니다
3. **브라우저 없음**: Google 계정 로그인을 위한 브라우저가 컨테이너 내부에 없습니다

**코드 확인**:
현재 프로젝트의 `scheduler.py`에서도 Docker 환경을 감지하고 Colab 실행을 차단합니다:

```python
# Docker 환경 확인
is_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_CONTAINER') == 'true'

if is_docker:
    raise Exception("Docker 환경에서는 Selenium을 사용한 Colab 실행이 지원되지 않습니다.")
```

**Docker에서 사용 가능한 대안**:

✅ **Vertex AI Job 사용** (권장):
```python
# Docker 컨테이너 내에서도 작동
from app.utils.scheduler import start_scheduler
start_scheduler()  # Vertex AI Job으로 자동 실행
```

또는 직접 실행:
```bash
# Docker 컨테이너 내에서
python run_predict_vertex_ai.py
```

**요약**:
- ❌ Colab Extension: VS Code에서만 작동, Docker 불가
- ✅ Vertex AI Job: Docker에서도 작동 가능 (현재 프로젝트 방식)

---

## 🔧 문제 해결

### 문제 1: Colab Extension에서 GPU 연결 실패

**증상**: T4 GPU를 선택할 수 없음

**해결 방법**:
1. **Colab Pro/Pro+ 구독 확인**
   - 무료 Colab은 GPU 사용 시간이 제한적입니다
   - Colab Pro+를 구독하면 T4 GPU 사용 가능

2. **런타임 재시작**
   - Colab에서 "Runtime" → "Restart runtime"
   - VS Code에서도 커널 재시작

### 문제 2: 환경 변수가 설정되지 않음

**해결 방법**:
1. **Secrets 사용** (권장)
   ```python
   from google.colab import userdata
   url = userdata.get('SUPABASE_URL')
   ```

2. **직접 설정**
   ```python
   import os
   os.environ["SUPABASE_URL"] = "your-url"
   ```

### 문제 3: 스케줄링이 작동하지 않음

**해결 방법**:
- 현재 프로젝트의 Vertex AI Job 방식을 사용하는 것을 권장합니다
- 이미 구현되어 있고 테스트되었습니다

---

## 📚 참고 자료

- [Colab Extension 공식 문서](https://marketplace.visualstudio.com/items?itemName=Google.colab)
- [Colab Pro 가격 정보](https://colab.research.google.com/signup)
- [Vertex AI 가격 정보](https://cloud.google.com/vertex-ai/pricing)

---

## 🎯 요약 및 권장사항

### 추천 방법: Vertex AI Job 사용 ⭐⭐⭐

현재 프로젝트에 이미 구현된 Vertex AI Job 방식을 사용하는 것을 강력히 권장합니다:

**이유**:
1. ✅ 이미 구현되어 있음
2. ✅ T4 GPU 자동 할당
3. ✅ 스케줄링 기능 완비
4. ✅ 로그 및 모니터링 가능
5. ✅ 비용 효율적 (사용한 만큼만 과금)

**사용 방법**:
```python
# 스케줄러 시작 (매일 자동 실행)
from app.utils.scheduler import start_scheduler
start_scheduler()

# 또는 수동 실행
from app.utils.scheduler import run_colab_trigger_now
run_colab_trigger_now()
```

### Colab Extension 사용 시나리오

Colab Extension은 다음 경우에 유용합니다:
- 🔧 **개발 및 테스트**: 로컬에서 Colab GPU로 빠르게 테스트
- 📝 **코드 작성**: VS Code에서 편리하게 코드 작성
- 🚀 **프로덕션**: Vertex AI Job으로 자동 실행

**워크플로우**:
1. VS Code + Colab Extension으로 개발 및 테스트
2. 코드가 완성되면 Vertex AI Job으로 프로덕션 배포
3. Scheduler로 자동 실행

---

이제 Colab Extension으로 개발하고, Vertex AI Job으로 자동 실행할 수 있습니다! 🚀
