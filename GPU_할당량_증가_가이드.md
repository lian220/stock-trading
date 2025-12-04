# GPU 할당량 증가 요청 가이드

## 🚨 T4 GPU 할당량 초과 에러

에러 메시지:
```
The following quota metrics exceed quota limits: 
aiplatform.googleapis.com/custom_model_training_nvidia_t4_gpus
```

이 에러는 Google Cloud 프로젝트의 T4 GPU 할당량이 부족할 때 발생합니다.

---

## 🔧 해결 방법

### 방법 1: 할당량 증가 요청 (권장)

1. **Google Cloud Console 접속**
   - https://console.cloud.google.com/ 접속
   - 프로젝트 선택

2. **할당량 페이지로 이동**
   - 좌측 메뉴에서 "IAM & Admin" → "Quotas" 클릭
   - 또는 직접 링크: https://console.cloud.google.com/iam-admin/quotas

3. **T4 GPU 할당량 검색**
   - 검색창에 `nvidia_t4` 또는 `custom_model_training_nvidia_t4_gpus` 입력
   - 필터: "Service" = "Vertex AI API" 또는 "AI Platform Training & Prediction API"
   - 필터: "Location" = 사용 중인 리전 (예: us-central1)

4. **할당량 증가 요청**
   - 해당 할당량 항목 선택
   - "EDIT QUOTAS" 버튼 클릭
   - 원하는 할당량 입력 (예: 1 → 2 또는 5)
   - 요청 사유 작성:
     ```
     주식 예측 모델 학습을 위한 Vertex AI Custom Job 실행에 필요합니다.
     하루 1회, 약 10분씩 실행되며 월 사용량은 약 5시간입니다.
     ```
   - "Submit Request" 클릭

5. **승인 대기**
   - 보통 24-48시간 내에 승인됩니다
   - 긴급한 경우 Google Cloud 지원팀에 문의

---

### 방법 2: 다른 GPU 타입 사용 (임시 해결책)

코드가 자동으로 다른 GPU 타입을 시도하도록 수정되었습니다.

**자동 시도 순서 (P4가 기본값인 경우):**
1. NVIDIA_TESLA_P4 (원래 설정, $0.69/시간)
2. NVIDIA_TESLA_T4 ($0.4025/시간)
3. NVIDIA_TESLA_P100 ($1.679/시간)
4. NVIDIA_TESLA_V100 ($2.852/시간)

**수동으로 GPU 타입 변경:**
`.env` 파일에서:
```env
# T4 대신 P100 사용 (할당량이 더 많을 수 있음)
VERTEX_AI_GPU_TYPE=NVIDIA_TESLA_P100
```

**비용 비교:**
- P4: $0.69/시간 → 월 약 $5.20 (기본값)
- T4: $0.4025/시간 → 월 약 $3.00 (가장 저렴)
- P100: $1.679/시간 → 월 약 $12.50
- V100: $2.852/시간 → 월 약 $21.00

---

### 방법 3: 다른 리전 사용

일부 리전은 T4 GPU 할당량이 더 많을 수 있습니다.

**사용 가능한 리전:**
- us-central1 (Iowa)
- us-east1 (South Carolina)
- us-west1 (Oregon)
- europe-west4 (Netherlands)
- asia-northeast1 (Tokyo)

`.env` 파일에서:
```env
GCP_REGION=us-east1  # 다른 리전 시도
```

---

## 📋 할당량 확인 방법

### Google Cloud Console에서 확인

1. https://console.cloud.google.com/iam-admin/quotas 접속
2. 검색: `nvidia` 또는 `gpu`
3. 필터 적용:
   - Service: "Vertex AI API"
   - Location: 사용 중인 리전
4. 현재 사용량과 한도 확인

### gcloud CLI로 확인

```bash
# 프로젝트 설정
gcloud config set project YOUR_PROJECT_ID

# T4 GPU 할당량 확인
gcloud compute project-info describe \
  --project=YOUR_PROJECT_ID \
  --format="value(quotas[metric='aiplatform.googleapis.com/custom_model_training_nvidia_t4_gpus'])"
```

---

## ⚠️ 주의사항

1. **할당량 증가 요청은 시간이 걸립니다**
   - 보통 24-48시간 소요
   - 긴급한 경우 지원팀에 문의

2. **다른 GPU 타입은 비용이 더 높습니다**
   - P100: T4의 약 4배
   - V100: T4의 약 7배

3. **리전별 할당량이 다릅니다**
   - 한 리전에서 할당량이 부족해도 다른 리전은 가능할 수 있음

---

## 🚀 빠른 해결 (임시)

즉시 실행이 필요한 경우:

1. **T4 GPU로 변경 (가장 저렴)**
   ```env
   VERTEX_AI_GPU_TYPE=NVIDIA_TESLA_T4
   ```
   
   또는 **P100 GPU로 변경**
   ```env
   VERTEX_AI_GPU_TYPE=NVIDIA_TESLA_P100
   ```

2. **다른 리전 시도**
   ```env
   GCP_REGION=us-east1
   ```

3. **할당량 증가 요청 제출** (장기 해결)

---

## 📞 지원 문의

할당량 증가 요청이 긴급하거나 문제가 있는 경우:

1. **Google Cloud 지원팀**
   - https://cloud.google.com/support 접속
   - "Create Support Case" 클릭
   - 할당량 증가 요청

2. **할당량 요청 상태 확인**
   - https://console.cloud.google.com/iam-admin/quotas
   - "Pending Requests" 탭에서 확인

---

**작성일**: 2025년 12월
