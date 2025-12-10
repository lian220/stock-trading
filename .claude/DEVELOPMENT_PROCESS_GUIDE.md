# Claude Code 개발 프로세스 가이드

소스 코드 생성 작업 시 참조해야 할 종합 프로세스 문서입니다.

---

## 1. 아키텍처 개요

### Clean Architecture 레이어 구조

```
┌─────────────────────────────────────────────────────────────┐
│                    presentation/api/                        │
│                  (FastAPI 라우터, 컨트롤러)                    │
├─────────────────────────────────────────────────────────────┤
│                      application/                           │
│               (Use Cases, 비즈니스 로직, DI)                  │
├─────────────────────────────────────────────────────────────┤
│                        domain/                              │
│              (엔티티, Repository 인터페이스)                   │
├─────────────────────────────────────────────────────────────┤
│                     infrastructure/                         │
│            (DB 클라이언트, Repository 구현체)                  │
└─────────────────────────────────────────────────────────────┘
```

### 의존성 규칙 (위반 시 Hook이 차단함)

| 레이어 | 의존 가능 | 의존 불가 |
|--------|----------|----------|
| **domain** | 없음 (순수) | application, infrastructure, presentation |
| **application** | domain | infrastructure, presentation |
| **infrastructure** | domain, application | presentation |
| **presentation** | 모든 레이어 | - |

---

## 2. 데이터베이스 구조

### 하이브리드 저장 방식 (Supabase + MongoDB)

```
┌──────────────────┐     ┌──────────────────┐
│    Supabase      │     │     MongoDB      │
│   (PostgreSQL)   │     │     (Atlas)      │
├──────────────────┤     ├──────────────────┤
│ - RDB 형식       │     │ - 유연한 스키마   │
│ - Wide format    │     │ - Long format    │
│ - 기존 호환성     │     │ - 시계열 최적화   │
└──────────────────┘     └──────────────────┘
         │                        │
         └────────────────────────┘
                    │
              동시 저장
```

### MongoDB 핵심 컬렉션

| 컬렉션 | 용도 | 주요 인덱스 |
|--------|------|------------|
| `daily_stock_data` | 날짜별 통합 데이터 (대시보드용) | `{ date: 1 }` (unique) |
| `stocks` | 종목 기본 정보 | `{ ticker: 1 }` (unique) |
| `user_stocks` | 사용자별 관심 종목/설정 | `{ user_id: 1, stock_id: 1 }` |
| `stock_recommendations` | 종목별 추천 시계열 | `{ ticker: 1, date: -1 }` |
| `stock_predictions` | AI 예측 결과 | `{ date: 1, ticker: 1 }` |
| `stock_analysis` | AI 분석 결과 | `{ date: 1, ticker: 1, user_id: 1 }` |
| `sentiment_analysis` | 뉴스 감정 분석 | `{ ticker: 1, calculation_date: -1 }` |

### daily_stock_data 내장 필드 구조

```javascript
{
  date: "2024-12-15",
  fred_indicators: { ... },      // FRED 경제 지표
  yfinance_indicators: { ... },  // Yahoo Finance 시장 지표
  stocks: {                      // 주가 데이터
    "AAPL": { open, high, low, close, adjusted_close },
    "MSFT": { ... }
  },
  volumes: { "AAPL": Number, ... },        // 거래량
  recommendations: { "AAPL": { ... } },    // 기술적 추천
  sentiment: { "AAPL": { ... } },          // 감정 분석
  predictions: { "AAPL": { ... } },        // AI 예측
  analysis: { "AAPL": { ... } },           // AI 분석
  created_at: Date,
  updated_at: Date
}
```

---

## 3. 추천 시스템 프로세스

### 3가지 분석 방법 통합

```
┌─────────────────────────────────────────────────────────────┐
│              통합 추천 시스템 (Composite Score)              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  기술적 분석  │  │  AI 예측    │  │  감정 분석   │         │
│  │   (40%)     │  │   (30%)    │  │    (30%)    │         │
│  ├─────────────┤  ├─────────────┤  ├─────────────┤         │
│  │ 골든크로스   │  │ Accuracy   │  │ Sentiment  │         │
│  │ RSI < 50   │  │ ≥ 80%     │  │ Score ≥0.15 │         │
│  │ MACD 신호  │  │ Rise Prob  │  │ Articles≥5 │         │
│  │            │  │ ≥ 3%      │  │            │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│         │               │               │                  │
│         └───────────────┼───────────────┘                  │
│                         ▼                                  │
│              ┌─────────────────┐                           │
│              │  종합 점수 계산   │                           │
│              │  (Composite)    │                           │
│              └─────────────────┘                           │
│                         │                                  │
│                         ▼                                  │
│              ┌─────────────────┐                           │
│              │   최종 추천 필터  │                           │
│              │  (조건 1 OR 2)  │                           │
│              └─────────────────┘                           │
└─────────────────────────────────────────────────────────────┘
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

# 기술적 지표 점수
tech_conditions_count = (
    1.5 × golden_cross +       # 골든 크로스 (1.5점)
    1.0 × (rsi < 50) +        # RSI 과매도 (1.0점)
    1.0 × macd_buy_signal     # MACD 매수 (1.0점)
)
```

---

## 4. 스케줄러 시스템

### 자동 스케줄러 구성

```
┌─────────────────────────────────────────────────────────────┐
│                     서버 시작 (startup)                      │
├─────────────────────────────────────────────────────────────┤
│                           │                                 │
│     ┌─────────────────────┼─────────────────────┐          │
│     ▼                     ▼                     ▼          │
│ ┌─────────┐         ┌─────────┐         ┌─────────┐        │
│ │ 매수     │         │ 매도     │         │ 경제     │        │
│ │스케줄러  │         │스케줄러  │         │데이터    │        │
│ ├─────────┤         ├─────────┤         ├─────────┤        │
│ │매일 00:00│         │ 1분마다  │         │매일 06:05│        │
│ │(KST)    │         │         │         │(KST)    │        │
│ └─────────┘         └─────────┘         └─────────┘        │
│     │                   │                   │              │
│     ▼                   ▼                   ▼              │
│ ┌─────────┐         ┌─────────┐         ┌─────────┐        │
│ │장시간    │         │장시간    │         │장마감후  │        │
│ │확인     │         │확인     │         │확인     │        │
│ │9:30-16:00│        │9:30-16:00│        │         │        │
│ │(ET)     │         │(ET)     │         │         │        │
│ └─────────┘         └─────────┘         └─────────┘        │
└─────────────────────────────────────────────────────────────┘
```

### 매수 프로세스 흐름

```
매수 스케줄러 실행 (00:00 KST)
        │
        ▼
┌───────────────┐
│  주말 체크     │ ─── 토/일 ──→ 종료
│  (뉴욕 기준)   │
└───────┬───────┘
        │ 평일
        ▼
┌───────────────┐
│  장 시간 체크  │ ─── 장외 ──→ 종료
│  9:30-16:00 ET│
└───────┬───────┘
        │ 장중
        ▼
┌───────────────┐
│  보유 종목 조회 │
│  (중복 방지)   │
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  주문가능금액  │
│  조회         │
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  매수 추천    │
│  종목 조회    │
│  (종합점수순)  │
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  우선순위     │
│  순서대로 매수 │
├───────────────┤
│ - 보유중 SKIP │
│ - 잔고부족 SKIP│
│ - 현재가 조회  │
│ - 매수 주문   │
│ - 잔고 차감   │
│ - Slack 알림  │
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  완료 요약 로그│
└───────────────┘
```

### 매도 조건

| 조건 | 설명 | 기준 |
|------|------|------|
| 익절 | 구매가 대비 상승 | +5% 이상 |
| 손절 | 구매가 대비 하락 | -7% 이하 |
| 기술적 매도 | 기술 지표 악화 | 데드크로스, RSI>70, MACD 매도 중 3개 |
| 감정 매도 | 부정적 뉴스 | 감정<-0.15 + 기술 매도 2개 |

### 경제 데이터 수집 흐름

```
경제 데이터 스케줄러 (06:05 KST)
        │
        ▼
┌───────────────┐
│  장 시간 체크  │ ─── 장중 ──→ 종료
│  (마감 후만)   │
└───────┬───────┘
        │ 장외
        ▼
┌───────────────┐
│ 마지막 수집일  │
│ 확인 (MongoDB)│
└───────┬───────┘
        │
        ▼
┌───────────────┐     ┌───────────────┐
│ 경제 지표 수집 │     │ 주가 데이터   │
│ - 금, 달러, VIX│     │ 수집 (34종목) │
│ - 아시아 지수  │     │ - yfinance   │
│ - 유럽 지수   │     │              │
└───────┬───────┘     └───────┬───────┘
        │                     │
        └──────────┬──────────┘
                   │
                   ▼
        ┌───────────────────┐
        │      동시 저장     │
        ├───────────────────┤
        │ Supabase:         │
        │ economic_and_     │
        │ stock_data        │
        ├───────────────────┤
        │ MongoDB:          │
        │ daily_stock_data  │
        │ - fred_indicators │
        │ - yfinance_ind.   │
        │ - stocks          │
        │ - volumes         │
        └───────────────────┘
```

---

## 5. 코드 작성 규칙

### ⚠️ 필수 원칙: 기능 추가 전 존재 여부 확인 및 중복/사용되지 않는 코드 정리

**모든 기능 추가/수정 작업 시 반드시 준수할 규칙:**

1. **기능 추가 전 기존 코드 확인**
   - 추가하려는 기능과 유사한 기존 코드가 있는지 검색
   - 기존 코드가 있다면 재사용 (중복 생성 금지)

2. **중복 코드 통합**
   - 중복된 로직이 발견되면 공통 함수로 통합
   - 기존 중복 코드는 삭제

3. **사용되지 않는 코드 삭제**
   - 사용되지 않는 함수, 변수, import는 즉시 삭제
   - 주석 처리된 코드는 완전히 제거
   - 빈 함수는 구현하거나 삭제

4. **코드 정리 체크리스트 확인**
   - 기능 추가/수정 후 체크리스트 확인 및 정리

### 환경변수 접근

```python
# ❌ 잘못된 방법 (Hook이 차단함)
import os
url = os.getenv("MONGODB_URL")
url = os.environ["MONGODB_URL"]

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

### 마이그레이션 파일

```python
# ❌ 기존 마이그레이션 파일 수정 금지 (Hook이 차단함)
# app/db/migrations/001_initial.py 수정 불가

# ✅ 새 마이그레이션 파일 생성
# app/db/migrations/002_add_column.py 생성
```

### 중복 코드 방지 (기존 코드 재사용)

**⚠️ 필수 규칙: 기능 추가 전 반드시 기존 코드 확인 및 정리**

#### 1. 기능 추가 전 존재 여부 확인 절차

**기능 추가 전 반드시 수행할 작업:**

1. **코드베이스 검색** - 추가하려는 기능과 유사한 기존 코드 검색
   ```bash
   # grep 또는 codebase_search 사용
   # 예: 날짜 포맷팅 함수가 있는지 확인
   grep -r "format_date\|strftime" app/
   ```

2. **기존 코드 확인** - 유사한 기능이 있다면 재사용
   ```python
   # ❌ 새 함수 중복 생성 금지
   def format_date(dt):
       return dt.strftime("%Y-%m-%d")
   
   # ✅ 기존 함수 재사용
   from app.utils.date_utils import format_date
   ```

3. **중복 코드 정리** - 발견된 중복 코드는 통합
   ```python
   # ❌ 중복된 함수가 여러 파일에 존재
   # file1.py
   def calculate_score(data):
       return sum(data) / len(data)
   
   # file2.py
   def get_average(values):
       return sum(values) / len(values)
   
   # ✅ 공통 유틸리티로 통합
   # app/utils/math_utils.py
   def calculate_average(data):
       return sum(data) / len(data) if data else 0
   ```

4. **사용되지 않는 코드 삭제** - 더 이상 사용되지 않는 코드는 제거
   ```python
   # ❌ 사용되지 않는 함수 유지
   def old_calculation_method():
       # 더 이상 사용되지 않음
       pass
   
   # ✅ 사용되지 않는 코드 삭제
   # (완전히 제거)
   ```

**기능 추가 전 반드시 확인할 위치:**

| 기능 | 확인할 위치 | 검색 키워드 예시 |
|------|------------|----------------|
| 날짜/시간 유틸리티 | `app/utils/date_utils.py` | `format_date`, `parse_date`, `get_today` |
| Slack 전송 | `app/utils/slack_notifier.py` | `send_notification`, `slack_notifier` |
| MongoDB 연결 | `app/infrastructure/database/` | `get_mongodb`, `mongodb_client` |
| 점수 계산 | `app/services/` | `calculate_score`, `composite_score` |
| 로깅 설정 | `app/core/logging.py` | `logger`, `logging` |
| 검증 함수 | `app/utils/validators.py` | `validate`, `check`, `verify` |
| 설정값/상수 | `app/core/config.py` | `settings`, `DEFAULT`, `CONFIG` |
| API 호출 | `app/services/balance_service.py` | `get_`, `fetch_`, `request` |
| 데이터 변환 | `app/utils/` | `transform`, `convert`, `parse` |
| 에러 처리 | `app/utils/` | `handle_error`, `exception` |

```python
# ❌ 새 유틸리티 함수 중복 생성 (Claude가 검색하여 확인)
def format_date(dt):  # 이미 존재할 수 있음
    return dt.strftime("%Y-%m-%d")

# ✅ 기존 유틸리티 재사용
from app.utils.date_utils import format_date
```

### 서비스/레포지토리 중복 방지

```python
# ❌ 새 서비스 클래스 중복 생성 (Claude가 검색하여 확인)
class NewStockService:  # StockRecommendationService가 이미 존재
    pass

# ✅ 기존 서비스 확장
from app.services.stock_recommendation_service import StockRecommendationService

class StockRecommendationService:
    def new_method(self):  # 기존 클래스에 메서드 추가
        pass
```

### 중복 코드 정리 및 사용되지 않는 코드 삭제

#### 2. 중복 코드 발견 시 처리 절차

**중복 코드 발견 시 반드시 수행:**

1. **중복 코드 식별**
   ```python
   # ❌ 중복된 로직이 여러 곳에 존재
   # file1.py
   def get_stock_price(ticker):
       result = api_call(ticker)
       return float(result.get("price", 0))
   
   # file2.py
   def fetch_price(symbol):
       response = api_call(symbol)
       return float(response.get("price", 0))
   ```

2. **공통 함수로 통합**
   ```python
   # ✅ 공통 유틸리티로 통합
   # app/utils/stock_utils.py
   def get_stock_price(ticker: str) -> float:
       """
       종목 가격을 조회합니다.
       
       Args:
           ticker: 종목 티커
       
       Returns:
           float: 종목 가격
       """
       result = api_call(ticker)
       return float(result.get("price", 0))
   
   # file1.py, file2.py 모두 공통 함수 사용
   from app.utils.stock_utils import get_stock_price
   ```

3. **기존 중복 코드 제거**
   ```python
   # ❌ 중복 코드 유지
   def get_stock_price(ticker):
       # 기존 코드 유지 (중복)
       pass
   
   # ✅ 중복 코드 삭제하고 공통 함수 사용
   from app.utils.stock_utils import get_stock_price
   ```

#### 3. 사용되지 않는 코드 정리

**사용되지 않는 코드 발견 시 반드시 삭제:**

```python
# ❌ 사용되지 않는 함수 유지
def old_calculation_method():
    """더 이상 사용되지 않는 함수"""
    # 아무도 호출하지 않음
    pass

# ❌ 주석 처리된 코드 유지
# def deprecated_function():
#     return old_value

# ❌ 빈 함수 유지
def placeholder():
    pass

# ✅ 사용되지 않는 코드 완전히 삭제
# (파일에서 완전히 제거)
```

**사용되지 않는 코드 확인 방법:**

1. **Import 확인** - 다른 파일에서 import 되는지 확인
   ```bash
   grep -r "old_calculation_method" app/
   ```

2. **호출 확인** - 함수가 실제로 호출되는지 확인
   ```bash
   grep -r "old_calculation_method(" app/
   ```

3. **삭제** - 사용되지 않으면 완전히 삭제
   ```python
   # ✅ 완전히 삭제
   # (코드에서 제거)
   ```

#### 4. Dead Code 방지 규칙

```python
# ❌ Claude가 발견 시 삭제하는 패턴들
def unused_function():
    pass  # 빈 함수

# def old_code():  # 주석 처리된 코드
#     return something

# TODO: 나중에 구현  # TODO가 3개 이상이면 정리

# ✅ 올바른 방법
# - 빈 함수는 구현하거나 삭제
# - 주석 처리된 코드는 완전히 삭제
# - TODO는 해결 후 커밋
# - 사용되지 않는 import는 제거
```

#### 5. 코드 정리 체크리스트

**기능 추가/수정 시 반드시 확인:**

- [ ] 기존에 유사한 기능이 있는지 검색했는가?
- [ ] 기존 코드를 재사용할 수 있는가?
- [ ] 중복된 코드가 있는가? (있다면 통합)
- [ ] 사용되지 않는 함수/변수가 있는가? (있다면 삭제)
- [ ] 주석 처리된 코드가 있는가? (있다면 삭제)
- [ ] 빈 함수가 있는가? (있다면 구현하거나 삭제)
- [ ] 사용되지 않는 import가 있는가? (있다면 제거)
- [ ] TODO 주석이 3개 이상인가? (있다면 해결)

### 전역 상수 재정의 금지

```python
# ❌ 이미 정의된 상수 재정의 (Claude가 검색하여 확인)
DEFAULT_TIMEZONE = "Asia/Seoul"  # config.py에 이미 존재
MARKET_OPEN_HOUR = 9  # market_hours.py에 이미 존재

# ✅ 기존 상수 import
from app.core.config import settings
timezone = settings.DEFAULT_TIMEZONE
```

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

### 분석 작업 API (별도 호출 필요)

| API | 용도 |
|-----|------|
| `POST /stocks/recommended-stocks/generate-technical-recommendations` | 기술적 지표 생성 |
| `POST /stocks/recommended-stocks/analyze-news-sentiment` | 감정 분석 |
| `POST /stocks/recommended-stocks/generate-complete-analysis` | 통합 분석 |

### 스케줄러 제어 API

| API | 용도 |
|-----|------|
| `POST /stocks/recommendations/purchase/scheduler/start` | 매수 스케줄러 시작 |
| `POST /stocks/recommendations/purchase/scheduler/stop` | 매수 스케줄러 중지 |
| `POST /stocks/recommendations/sell/scheduler/start` | 매도 스케줄러 시작 |
| `POST /stocks/recommendations/sell/scheduler/stop` | 매도 스케줄러 중지 |
| `GET /stocks/recommendations/scheduler/status` | 스케줄러 상태 확인 |
| `POST /stocks/recommendations/purchase/trigger` | 즉시 매수 실행 |
| `POST /stocks/recommendations/sell/trigger` | 즉시 매도 실행 |

---

## 7. 데이터 조회 패턴

### 날짜별 통합 조회 (대시보드용)

```python
# MongoDB daily_stock_data 사용
doc = await db.daily_stock_data.find_one({"date": "2024-12-15"})

# 모든 정보가 한 문서에 포함
stocks = doc.get("stocks", {})
recommendations = doc.get("recommendations", {})
sentiment = doc.get("sentiment", {})
predictions = doc.get("predictions", {})
```

### 종목별 시계열 조회 (분석용)

```python
# MongoDB stock_recommendations 사용
cursor = db.stock_recommendations.find({
    "ticker": "AAPL",
    "date": {"$gte": start_date, "$lte": end_date}
}).sort("date", -1)
```

### 우선순위

1. MongoDB 우선 조회
2. 필요시 Supabase fallback
3. 종목 정보는 MongoDB `stocks` 컬렉션에서 조회

---

## 8. 커밋 메시지 규칙

```
<type>(<scope>): <한글 subject>

<한글 body>
```

### Type 종류

| Type | 설명 |
|------|------|
| feat | 새로운 기능 |
| fix | 버그 수정 |
| refactor | 리팩토링 |
| docs | 문서 |
| style | 코드 스타일 |
| test | 테스트 |
| chore | 빌드, 설정 |
| perf | 성능 개선 |

### 예시

```
feat(api): 경제 지표 조회 API 추가함

MongoDB에서 경제 지표를 조회하는 엔드포인트 구현
- FRED 지표 조회
- 시장 지표 조회
```

---

## 9. 참고 문서

| 문서 | 경로 | 설명 |
|------|------|------|
| MongoDB 스키마 | `docs/mongo/MongoDB_Schema_Design.md` | 컬렉션 구조, 인덱스 |
| 통합 추천 시스템 | `docs/recommendation/통합추천시스템_가이드.md` | 추천 로직 상세 |
| 스케줄러 | `docs/system/스케줄러_가이드.md` | 스케줄러 동작 방식 |
| 매수 동작 | `docs/trading/매수_동작_가이드.md` | 매수 프로세스 |
| AI 예측 모델 | `docs/recommendation/주식예측모델_가이드.md` | AI 모델 설명 |

---

**마지막 업데이트**: 2025-12-15
