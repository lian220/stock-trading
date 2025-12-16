# Claude 개발 프로세스 가이드

소스 코드 생성 작업 시 빠르게 참조할 수 있는 핵심 가이드입니다.

---

## 1. 아키텍처 구조

### Clean Architecture 레이어

```
presentation/api/     → FastAPI 라우터, 컨트롤러
application/          → Use Cases, 비즈니스 로직, DI
domain/               → 엔티티, Repository 인터페이스 (의존성 없음)
infrastructure/       → DB 클라이언트, Repository 구현체
```

### 의존성 규칙 (위반 시 Hook 차단)

| 레이어 | 의존 가능 | 의존 불가 |
|--------|----------|----------|
| **domain** | 없음 (순수) | application, infrastructure, presentation |
| **application** | domain | infrastructure, presentation |
| **infrastructure** | domain, application | presentation |
| **presentation** | 모든 레이어 | - |

---

## 2. 데이터베이스 규칙

### ⚠️ CRITICAL: 데이터 조회 규칙

- **모든 데이터 조회는 MongoDB에서 수행**
- Supabase는 저장용으로만 사용 (레거시 호환성)
- `get_stock_repository()` 또는 `get_economic_repository()` 사용 시 MongoDB 구현체 반환 확인

### MongoDB 핵심 컬렉션

| 컬렉션 | 용도 | 주요 인덱스 |
|--------|------|------------|
| `daily_stock_data` | 날짜별 통합 데이터 (대시보드용) | `{ date: 1 }` (unique) |
| `stocks` | 종목 기본 정보 | `{ ticker: 1 }` (unique) |
| `stock_recommendations` | 종목별 추천 시계열 | `{ ticker: 1, date: -1 }` |
| `stock_analysis` | AI 분석 결과 | `{ date: 1, ticker: 1 }` |
| `sentiment_analysis` | 뉴스 감정 분석 | `{ ticker: 1, calculation_date: -1 }` |

### daily_stock_data 구조

```javascript
{
  date: "2024-12-15",
  fred_indicators: { ... },      // FRED 경제 지표
  yfinance_indicators: { ... },  // Yahoo Finance 시장 지표
  stocks: { "AAPL": { open, high, low, close, adjusted_close }, ... },
  volumes: { "AAPL": Number, ... },
  recommendations: { "AAPL": { ... } },
  sentiment: { "AAPL": { ... } },
  predictions: { "AAPL": { ... } },
  analysis: { "AAPL": { ... } }
}
```

---

## 3. 코드 작성 규칙

### ⚠️ 필수 원칙: 기능 추가 전 존재 여부 확인 및 중복 코드 정리

**모든 기능 추가/수정 작업 시 반드시 준수:**

1. **기능 추가 전 기존 코드 확인**
   - 추가하려는 기능과 유사한 기존 코드 검색
   - 기존 코드가 있다면 재사용 (중복 생성 금지)

2. **중복 코드 통합**
   - 중복된 로직이 발견되면 공통 함수로 통합
   - 기존 중복 코드는 삭제

3. **사용되지 않는 코드 삭제**
   - 사용되지 않는 함수, 변수, import는 즉시 삭제
   - 주석 처리된 코드는 완전히 제거
   - 빈 함수는 구현하거나 삭제

### 환경변수 접근

```python
# ❌ 잘못된 방법 (Hook이 차단함)
import os
url = os.getenv("MONGODB_URL")

# ✅ 올바른 방법
from app.core.config import settings
url = settings.get_mongodb_url()
```

### Repository 사용

```python
# ❌ 잘못된 방법 (Hook이 차단함)
from app.infrastructure.repositories import MongoStockRepository
repo = MongoStockRepository()

# ✅ 올바른 방법
from app.application.dependencies import get_stock_repository
repo = get_stock_repository()  # MongoDB/Supabase 자동 선택
```

### 서비스 파일 작성 (docstring 필수)

```python
# ❌ 잘못된 방법 (Hook이 차단함)
def calculate_recommendation(stock_data):
    return score

# ✅ 올바른 방법
def calculate_recommendation(stock_data):
    """
    종목 데이터를 기반으로 추천 점수를 계산합니다.

    Args:
        stock_data: 종목 분석 데이터

    Returns:
        float: 추천 점수 (0-10)
    """
    return score
```

### 기존 코드 확인 위치

| 기능 | 확인할 위치 | 검색 키워드 |
|------|------------|------------|
| 날짜/시간 유틸리티 | `app/utils/date_utils.py` | `format_date`, `parse_date` |
| Slack 전송 | `app/utils/slack_notifier.py` | `send_notification` |
| MongoDB 연결 | `app/infrastructure/database/` | `get_mongodb` |
| 점수 계산 | `app/services/` | `calculate_score` |
| 설정값/상수 | `app/core/config.py` | `settings`, `DEFAULT` |

### 코드 정리 체크리스트

- [ ] 기존에 유사한 기능이 있는지 검색했는가?
- [ ] 기존 코드를 재사용할 수 있는가?
- [ ] 중복된 코드가 있는가? (있다면 통합)
- [ ] 사용되지 않는 함수/변수가 있는가? (있다면 삭제)
- [ ] 주석 처리된 코드가 있는가? (있다면 삭제)
- [ ] 빈 함수가 있는가? (있다면 구현하거나 삭제)
- [ ] 사용되지 않는 import가 있는가? (있다면 제거)

---

## 4. 추천 시스템 프로세스

### 통합 추천 시스템 (Composite Score)

```
기술적 분석 (40%) + AI 예측 (30%) + 감정 분석 (30%) → 종합 점수
```

### 매수 추천 조건

**조건 1**: 긍정적 감정 + 기술적 신호
```python
if sentiment_score >= 0.15 and tech_conditions >= 2:
    # 매수 추천
```

**조건 2**: 강력한 기술적 신호
```python
if tech_conditions == 3:  # 골든크로스 + RSI<50 + MACD
    # 매수 추천 (감정 점수 무관)
```

### 종합 점수 계산

```python
composite_score = (
    0.3 × rise_probability +           # AI 예측 상승률
    0.4 × tech_conditions_count +      # 기술적 지표 점수 (최대 3.5)
    0.3 × sentiment_score              # 감정 분석 점수
)
```

---

## 5. 스케줄러 시스템

### 자동 스케줄러 구성

- **매수 스케줄러**: 매일 00:00 KST, 장시간(9:30-16:00 ET) 확인
- **매도 스케줄러**: 1분마다, 장시간(9:30-16:00 ET) 확인
- **경제 데이터 스케줄러**: 매일 06:05 KST, 장마감 후 확인

### 매수 프로세스 흐름

```
매수 스케줄러 실행 → 주말 체크 → 장 시간 체크 → 보유 종목 조회 
→ 주문가능금액 조회 → 매수 추천 종목 조회 → 우선순위 순서대로 매수
```

### 매도 조건

| 조건 | 설명 | 기준 |
|------|------|------|
| 익절 | 구매가 대비 상승 | +5% 이상 |
| 손절 | 구매가 대비 하락 | -7% 이하 |
| 기술적 매도 | 기술 지표 악화 | 데드크로스, RSI>70, MACD 매도 중 3개 |
| 감정 매도 | 부정적 뉴스 | 감정<-0.15 + 기술 매도 2개 |

---

## 6. API 엔드포인트 구조

### 주요 라우터

| 경로 | 용도 |
|------|------|
| `/stocks` | 주식 추천, 조회 |
| `/economic` | 경제 데이터 |
| `/balance` | 잔액 조회 |
| `/auto-trading` | 자동매매 |
| `/colab` | Colab/Vertex AI |
| `/gcs` | GCS 업로드 |

### 분석 작업 API

| API | 용도 |
|-----|------|
| `POST /stocks/recommended-stocks/generate-technical-recommendations` | 기술적 지표 생성 |
| `POST /stocks/recommended-stocks/analyze-news-sentiment` | 감정 분석 |
| `POST /stocks/recommended-stocks/generate-complete-analysis` | 통합 분석 |

---

## 7. 데이터 조회 패턴

### 날짜별 통합 조회 (대시보드용)

```python
# MongoDB daily_stock_data 사용
doc = await db.daily_stock_data.find_one({"date": "2024-12-15"})
stocks = doc.get("stocks", {})
recommendations = doc.get("recommendations", {})
```

### 종목별 시계열 조회 (분석용)

```python
# MongoDB stock_recommendations 사용
cursor = db.stock_recommendations.find({
    "ticker": "AAPL",
    "date": {"$gte": start_date, "$lte": end_date}
}).sort("date", -1)
```

---

## 8. 커밋 메시지 규칙

```
<type>(<scope>): <한글 subject>

<한글 body>
```

### Type 종류

- `feat`: 새로운 기능
- `fix`: 버그 수정
- `refactor`: 리팩토링
- `docs`: 문서
- `style`: 코드 스타일
- `test`: 테스트
- `chore`: 빌드, 설정
- `perf`: 성능 개선

### 예시

```
feat(api): 경제 지표 조회 API 추가함

MongoDB에서 경제 지표를 조회하는 엔드포인트 구현
- FRED 지표 조회
- 시장 지표 조회
```

---

**마지막 업데이트**: 2025-12-15
