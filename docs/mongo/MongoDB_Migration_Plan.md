# MongoDB 마이그레이션 계획 및 설계 문서

## 목차
1. [현재 상황 분석](#현재-상황-분석)
2. [마이그레이션 목표](#마이그레이션-목표)
3. [MongoDB 스키마 설계](#mongodb-스키마-설계)
4. [마이그레이션 전략](#마이그레이션-전략)
5. [구현 단계](#구현-단계)
6. [코드 변경 계획](#코드-변경-계획)

---

## 현재 상황 분석

### 현재 RDB 구조의 문제점

1. **하드코딩된 종목 컬럼**
   - `stock_daily_volume`: 날짜별 각 종목의 거래량을 컬럼으로 저장
   - `predicted_stocks`: 날짜별 각 종목의 예측값/실제값을 컬럼으로 저장
   - `economic_and_stock_data`: 날짜별 경제지표 + 각 종목의 가격을 컬럼으로 저장
   - **문제**: 새 종목 추가 시 `ALTER TABLE` 필요 → 유연성 부족

2. **개인별 종목 관리 불가**
   - 모든 사용자가 동일한 종목 세트 사용
   - 사용자별 관심 종목 설정 불가
   - 사용자별 포트폴리오 관리 불가

3. **데이터 중복**
   - 동일 종목 정보가 여러 테이블에 중복 저장
   - 스키마 변경 시 여러 테이블 수정 필요

### 현재 사용 중인 테이블

| 테이블명 | 용도 | 문제점 |
|---------|------|--------|
| `stock_daily_volume` | 일일 거래량 저장 | ✅ **통합 완료** (MongoDB `daily_stock_data.volumes` 필드로) |
| `predicted_stocks` | 예측값/실제값 저장 | ✅ **하이브리드 완료** (Supabase + MongoDB `stock_predictions`) |
| `economic_and_stock_data` | 경제지표 + 주가 데이터 | 종목이 컬럼으로 하드코딩 |
| `stock_ticker_mapping` | 종목명-티커 매핑 | ✅ 정상 (이 테이블은 유지 가능) |
| `stock_recommendations` | 기술적 지표 추천 | 날짜+종목 복합키 → 개인화 불가 |
| `stock_analysis_results` | AI 예측 분석 결과 | ✅ **하이브리드 완료** (Supabase + MongoDB `stock_analysis`) |
| `ticker_sentiment_analysis` | 감정 분석 결과 | 티커 기준 → 개인화 불가 |
| `auto_trading_config` | 자동매매 설정 | 전역 설정 → 개인별 설정 필요 |
| `auto_trading_logs` | 자동매매 로그 | 사용자 식별 불가 |

---

## 마이그레이션 목표

1. **유연한 종목 관리**
   - 종목 추가/제거 시 스키마 변경 불필요
   - 동적 종목 추가 지원

2. **개인별 종목 관리**
   - 사용자별 관심 종목 설정
   - 사용자별 포트폴리오 관리
   - 사용자별 추천 및 분석 결과 저장

3. **데이터 구조 개선**
   - 중복 제거
   - 효율적인 쿼리 구조
   - 확장 가능한 스키마

---

## MongoDB 스키마 설계

### 1. Collections 구조

```
mongodb/
├── stocks/                    # 종목 기본 정보
├── users/                     # 사용자 정보
├── user_stocks/              # 사용자별 관심 종목
├── economic_data/            # 경제 지표 데이터
├── daily_stock_data/         # 일일 주가 데이터 (실제 사용)
├── stock_recommendations/    # 종목별 추천 (개인화 가능)
├── stock_analysis/           # AI 분석 결과 (개인화 가능)
├── sentiment_analysis/       # 감정 분석 결과
├── trading_configs/          # 자동매매 설정 (개인별)
└── trading_logs/             # 거래 로그 (개인별)
```

### 2. 상세 스키마 설계

#### 2.1. `stocks` Collection
```javascript
{
  _id: ObjectId,
  ticker: String,              // 예: "AAPL"
  stock_name: String,          // 한글명: "애플"
  stock_name_en: String,       // 영문명: "Apple Inc." (선택)
  is_etf: Boolean,
  leverage_ticker: String,     // 레버리지 티커 심볼 (예: "AAPU") - 종목 정보
  exchange: String,            // "NASDAQ", "NYSE" 등 (선택)
  sector: String,              // 섹터 정보 (선택)
  industry: String,            // 산업 정보 (선택)
  is_active: Boolean,
  created_at: Date,
  updated_at: Date
}
```
**주의**: `use_leverage`는 사용자별 설정이므로 `user_stocks` collection에 저장됩니다.

**인덱스:**
- `{ ticker: 1 }` (unique)
- `{ stock_name: 1 }` (unique)
- `{ is_active: 1 }`

---

#### 2.2. `users` Collection
```javascript
{
  _id: ObjectId,
  user_id: String,             // 사용자 식별자 (UUID 또는 이메일)
  email: String,               // 이메일 (선택)
  display_name: String,        // 표시명
  preferences: {
    default_currency: String,  // "USD", "KRW"
    notification_enabled: Boolean,
    // 기타 사용자 선호 설정
  },
  created_at: Date,
  updated_at: Date
}
```

**인덱스:**
- `{ user_id: 1 }` (unique)

---

#### 2.3. `user_stocks` Collection
```javascript
{
  _id: ObjectId,
  user_id: String,             // users._id 참조
  stock_id: String,            // stocks._id 참조
  ticker: String,              // 빠른 조회를 위한 중복 필드
  use_leverage: Boolean,       // 레버리지 사용 여부 (사용자별 설정)
  added_at: Date,              // 관심 종목 추가 일시
  notes: String,               // 사용자 메모 (선택)
  tags: [String],              // 사용자 정의 태그 (선택)
  is_active: Boolean,          // 활성/비활성
  created_at: Date,
  updated_at: Date
}
```
**설명**: 
- `use_leverage`: 사용자가 해당 종목에 레버리지를 사용할지 여부를 설정
- `stocks` collection의 `leverage_ticker`와 함께 사용하면 실제 거래 시 레버리지 티커를 선택할 수 있음

**인덱스:**
- `{ user_id: 1, stock_id: 1 }` (unique)
- `{ user_id: 1, is_active: 1 }`
- `{ ticker: 1 }`

**예시:**
```javascript
// 사용자 A가 관심 있는 종목들
{ user_id: "user123", stock_id: "stock_aapl", ticker: "AAPL", ... }
{ user_id: "user123", stock_id: "stock_msft", ticker: "MSFT", ... }
{ user_id: "user123", stock_id: "stock_tsla", ticker: "TSLA", ... }
```

---

#### 2.4. `economic_data` Collection
```javascript
{
  _id: ObjectId,
  date: Date,
  indicators: {
    "10년 기대 인플레이션율": Number,
    "장단기 금리차": Number,
    "기준금리": Number,
    "미시간대 소비자 심리지수": Number,
    "실업률": Number,
    // ... 기타 경제 지표
  },
  created_at: Date
}
```

**인덱스:**
- `{ date: 1 }` (unique)

**설계 이유:**
- 경제 지표는 날짜별로 하나의 문서만 존재
- `indicators` 객체에 동적으로 지표 추가 가능
- 스키마 변경 없이 새로운 지표 추가 가능

---

#### 2.5. `daily_stock_data` Collection
**목적**: 날짜별 주가 데이터 및 추천 정보 통합 저장 (하이브리드 접근법)

```javascript
{
  _id: ObjectId,
  date: String,                    // 거래일 (YYYY-MM-DD 형식, unique)
  fred_indicators: {               // FRED 경제 지표
    "10년 기대 인플레이션율": Number,
    "장단기 금리차": Number,
    // ... 기타 FRED 지표
  },
  yfinance_indicators: {          // Yahoo Finance 시장 지표
    "S&P 500 지수": Number,
    "QQQ ETF": Number,
    // ... 기타 시장 지표
  },
  stocks: {                        // 주가 데이터 (티커 기반 구조)
    "AAPL": {
      close_price: Number,          // 종가 (필수)
      short_interest: {            // 공매도 데이터 (선택)
        sharesShort: Number,        // 공매도 주식 수
        sharesShortPriorMonth: Number,  // 전월 공매도 주식 수
        shortRatio: Number,         // 공매도 비율
        shortPercentOfFloat: Number // 유동주식 대비 공매도 비율
      }
    },
    "MSFT": {
      close_price: Number,
      short_interest: {...}
    },
    // ... 모든 종목 주가 (티커를 키로 사용)
  },
  volumes: {                       // 거래량 데이터 (통합 완료)
    "AAPL": Number,
    "MSFT": Number,
    // ... 모든 종목 거래량
  },
  recommendations: {               // ✨ 추천 정보 (하이브리드 접근법)
    "AAPL": {
      technical_indicators: {
        sma20: Number,
        sma50: Number,
        golden_cross: Boolean,
        rsi: Number,
        macd: Number,
        signal: Number,
        macd_buy_signal: Boolean
      },
      is_recommended: Boolean,
      recommendation_score: Number
    },
    "MSFT": {...},
    // ... 모든 종목 추천 정보
  },
  sentiment: {                      // ✨ 감정 분석 정보 (하이브리드 접근법)
    "AAPL": {
      sentiment_score: Number,
      positive_count: Number,
      negative_count: Number,
      neutral_count: Number
    },
    "MSFT": {...},
    // ... 모든 종목 감정 분석 정보
  },
  predictions: {                     // ✨ AI 예측 정보 (하이브리드 접근법)
    "AAPL": {
      predicted_price: Number,
      actual_price: Number,
      forecast_horizon: Number
    },
    "MSFT": {...},
    // ... 모든 종목 예측 정보
  },
  analysis: {                        // ✨ AI 분석 결과 (하이브리드 접근법)
    "AAPL": {
      metrics: {
        mae: Number,
        mse: Number,
        rmse: Number,
        mape: Number,
        accuracy: Number
      },
      predictions: {
        last_actual_price: Number,
        predicted_future_price: Number,
        predicted_rise: Boolean,
        rise_probability: Number
      },
      recommendation: String,
      analysis: String
    },
    "MSFT": {...},
    // ... 모든 종목 분석 결과
  },
  created_at: Date,
  updated_at: Date
}
```

**인덱스:**
- `{ date: 1 }` (unique) - 날짜별 조회 최적화
- `{ recommendations: 1 }` (sparse) - recommendations 필드 존재 여부 필터링
- `{ date: 1, recommendations: 1 }` - 날짜 범위 조회 최적화
- `{ sentiment: 1 }` (sparse) - sentiment 필드 존재 여부 필터링
- `{ date: 1, sentiment: 1 }` - 날짜 범위 조회 최적화 (sentiment)
- `{ predictions: 1 }` (sparse) - predictions 필드 존재 여부 필터링
- `{ date: 1, predictions: 1 }` - 날짜 범위 조회 최적화 (predictions)
- `{ analysis: 1 }` (sparse) - analysis 필드 존재 여부 필터링
- `{ date: 1, analysis: 1 }` - 날짜 범위 조회 최적화 (analysis)

**설계 이유:**
- 주가 데이터는 날짜별로 하나의 문서만 존재
- 날짜별로 모든 데이터(주가 + 거래량 + 추천 + 감정 + 예측 + 분석)를 한 번에 조회 가능 (대시보드 최적화)
- 하이브리드 접근법으로 각 필드에 관련 정보 포함
- 스키마 변경 없이 새로운 종목 추가 가능
- `stock_prices`, `stock_volumes` 컬렉션을 통합하여 구조 단순화

**데이터 구조 개선**:
- **기존**: `stocks` 필드에 종가(close_price)만 Number로 저장
- **개선**: `stocks` 필드를 객체 형태로 확장 (open, high, low, close_price, adjusted_close)
- **추가**: `volumes` 필드로 거래량 데이터 통합 (`stock_daily_volume` 테이블 대체)
- **효과**: 날짜별 통합 조회 시 모든 가격 정보와 거래량을 한 번에 조회 가능

**하이브리드 접근법:**
- 이 컬렉션은 **날짜별 통합 조회용**으로 사용
- 종목별 시계열 조회는 별도 컬렉션 사용:
  - `stock_recommendations`: 기술적 분석 시계열
  - `sentiment_analysis`: 감정 분석 시계열
  - `stock_predictions`: 예측 결과 시계열
  - `stock_analysis`: 분석 결과 시계열
- 두 저장소는 동기화되어 유지됨

---

#### 2.6. `fred_indicators` Collection
```javascript
{
  _id: ObjectId,
  code: String,                  // FRED API 코드 (예: "T10YIE")
  name: String,                  // 지표 이름 (예: "10년 기대 인플레이션율")
  type: String,                  // "economic" | "index"
  is_active: Boolean,
  created_at: Date,
  updated_at: Date
}
```

**인덱스:**
- `{ code: 1 }` (unique)
- `{ name: 1 }` (unique)
- `{ type: 1 }`
- `{ is_active: 1 }`

---

#### 2.7. `yfinance_indicators` Collection
```javascript
{
  _id: ObjectId,
  ticker: String,                // Yahoo Finance 티커 (예: "^GSPC")
  name: String,                   // 지표 이름 (예: "S&P 500 지수")
  type: String,                   // "index" | "etf" | "commodity" | "currency"
  is_active: Boolean,
  created_at: Date,
  updated_at: Date
}
```

**인덱스:**
- `{ ticker: 1 }` (unique)
- `{ name: 1 }` (unique)
- `{ type: 1 }`
- `{ is_active: 1 }`

---

#### 2.8. `stock_recommendations` Collection
**목적**: 종목별 추천 데이터 시계열 저장 (하이브리드 접근법)

```javascript
{
  _id: ObjectId,
  date: Date,
  ticker: String,
  stock_id: String,
  user_id: String,             // null이면 전역 추천, 값이 있으면 개인화 추천
  technical_indicators: {
    sma20: Number,
    sma50: Number,
    golden_cross: Boolean,
    rsi: Number,
    macd: Number,
    signal: Number,
    macd_buy_signal: Boolean
  },
  recommendation_score: Number, // 추천 점수
  is_recommended: Boolean,
  created_at: Date
}
```

**인덱스:**
- `{ date: 1, ticker: 1, user_id: 1 }` - 복합 인덱스
- `{ user_id: 1, date: -1 }` - 사용자별 날짜 역순 조회
- `{ ticker: 1, date: -1 }` - 종목별 시계열 조회 (시계열 분석용)
- `{ is_recommended: 1, date: -1 }` - 추천 여부 필터링
- `{ ticker: 1, is_recommended: 1, date: -1 }` - 종목별 추천 이력 조회 최적화

**설계 이유:**
- 종목별 시계열 조회에 최적화
- 인덱스를 활용한 효율적인 쿼리
- 개인화 추천 지원 (user_id 필드)

**하이브리드 접근법:**
- 이 컬렉션은 **종목별 시계열 조회용**으로 사용
- 날짜별 통합 조회는 `daily_stock_data` 컬렉션 사용
- 두 컬렉션은 동기화되어 유지됨

**예시:**
```javascript
// 전역 추천 (모든 사용자에게 적용)
{ date: ISODate("2024-01-15"), ticker: "AAPL", user_id: null, ... }

// 개인화 추천 (특정 사용자에게만)
{ date: ISODate("2024-01-15"), ticker: "MSFT", user_id: "user123", ... }
```

---

#### 2.9. `stock_analysis` Collection
```javascript
{
  _id: ObjectId,
  date: Date,
  ticker: String,
  stock_id: String,
  user_id: String,             // null이면 전역 분석, 값이 있으면 개인화 분석
  metrics: {
    mae: Number,
    mse: Number,
    rmse: Number,
    mape: Number,
    accuracy: Number
  },
  predictions: {
    last_actual_price: Number,
    predicted_future_price: Number,
    predicted_rise: Boolean,
    rise_probability: Number
  },
  recommendation: String,
  analysis: String,
  created_at: Date
}
```

**인덱스:**
- `{ date: 1, ticker: 1, user_id: 1 }`
- `{ user_id: 1, date: -1 }`

---

#### 2.10. `sentiment_analysis` Collection
```javascript
{
  _id: ObjectId,
  ticker: String,
  stock_id: String,
  average_sentiment_score: Number,
  article_count: Number,
  calculation_date: Date,
  created_at: Date
}
```

**인덱스:**
- `{ ticker: 1, calculation_date: -1 }`

---

#### 2.11. `trading_configs` Collection
```javascript
{
  _id: ObjectId,
  user_id: String,             // users._id 참조
  enabled: Boolean,
  min_composite_score: Number,
  max_stocks_to_buy: Number,
  max_amount_per_stock: Number,
  stop_loss_percent: Number,
  take_profit_percent: Number,
  use_sentiment: Boolean,
  min_sentiment_score: Number,
  order_type: String,
  watchlist_stocks: [String],  // 관찰 종목 리스트 (ticker 배열)
  created_at: Date,
  updated_at: Date
}
```

**인덱스:**
- `{ user_id: 1 }` (unique)

---

#### 2.12. `trading_logs` Collection
```javascript
{
  _id: ObjectId,
  user_id: String,
  order_type: String,          // "buy" | "sell"
  ticker: String,
  stock_id: String,
  stock_name: String,
  price: Number,
  quantity: Number,
  status: String,              // "success" | "failed" | "dry_run"
  composite_score: Number,     // 매수 시
  price_change_percent: Number, // 매도 시
  sell_reasons: [String],      // 매도 사유
  order_result: Object,        // API 응답 JSON
  created_at: Date
}
```

**인덱스:**
- `{ user_id: 1, created_at: -1 }`
- `{ ticker: 1, created_at: -1 }`
- `{ order_type: 1, created_at: -1 }`

---

## 마이그레이션 전략

### Phase 1: 하이브리드 접근법 완성 ✅
- ✅ 경제 데이터: `daily_stock_data` 저장 완료
- ✅ 기술적 분석: 하이브리드 접근법 완료
- ✅ 뉴스 감정 분석: 하이브리드 접근법 완료
- ✅ AI 예측 결과: 하이브리드 접근법 완료 (`predicted_stocks` + `stock_predictions`)
- ✅ AI 분석 결과: 하이브리드 접근법 완료 (`stock_analysis_results` + `stock_analysis`)

### Phase 2: MongoDB 설정 및 기본 구조 구축
1. MongoDB 클라이언트 설정
2. 기본 Collections 생성
3. 인덱스 생성

### Phase 2: 데이터 마이그레이션
1. 기존 RDB 데이터 → MongoDB 변환
2. 데이터 검증

### Phase 3: 코드 마이그레이션
1. 데이터베이스 접근 로직 변경
2. 서비스 레이어 수정
3. API 엔드포인트 수정

### Phase 4: 개인화 기능 추가
1. 사용자 인증/인가 시스템 연동
2. 개인별 종목 관리 기능
3. 개인화된 추천 시스템

### Phase 5: 테스트 및 검증
1. 단위 테스트
2. 통합 테스트
3. 성능 테스트

---

## 구현 단계

### Step 1: MongoDB 클라이언트 설정

**파일: `app/db/mongodb.py`**
```python
from pymongo import MongoClient
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

# MongoDB 연결 설정
MONGODB_URL = settings.MONGODB_URL or "mongodb://localhost:27017"
DATABASE_NAME = settings.MONGODB_DATABASE or "stock_trading"

# 비동기 클라이언트 (FastAPI에서 사용)
async_client = AsyncIOMotorClient(MONGODB_URL)
db = async_client[DATABASE_NAME]

# 동기 클라이언트 (스크립트에서 사용)
sync_client = MongoClient(MONGODB_URL)
sync_db = sync_client[DATABASE_NAME]
```

**설정 추가: `app/core/config.py`**
```python
MONGODB_URL: Optional[str] = Field(
    default=None,
    description="MongoDB 연결 URL"
)
MONGODB_DATABASE: str = Field(
    default="stock_trading",
    description="MongoDB 데이터베이스 이름"
)
```

---

### Step 2: 데이터 마이그레이션 스크립트

**파일: `scripts/migrate_to_mongodb.py`**
- Supabase에서 데이터 읽기
- MongoDB 형식으로 변환
- MongoDB에 저장

---

### Step 3: 서비스 레이어 리팩토링

**변경 대상:**
- `app/services/economic_service.py`
- `app/services/stock_recommendation_service.py`
- `app/services/auto_trading_service.py`
- `scripts/utils/predict.py`

**변경 사항:**
- `supabase.table()` → MongoDB collections 접근
- 쿼리 로직 변경

---

### Step 4: 개인화 기능 구현

**새로운 API 엔드포인트:**
- `POST /api/users/{user_id}/stocks` - 관심 종목 추가
- `GET /api/users/{user_id}/stocks` - 관심 종목 조회
- `DELETE /api/users/{user_id}/stocks/{stock_id}` - 관심 종목 제거
- `GET /api/users/{user_id}/recommendations` - 개인화된 추천 조회

---

## 코드 변경 계획

### 1. 데이터베이스 접근 레이어

**기존:**
```python
from app.db.supabase import supabase
response = supabase.table("economic_and_stock_data").select("*").execute()
```

**변경 후:**
```python
from app.db.mongodb import db
# daily_stock_data에서 날짜별로 조회
data = await db.daily_stock_data.find({
    "date": {"$gte": start_date, "$lte": end_date}
}).sort("date", 1).to_list(length=100)
```

### 2. 데이터 저장 패턴

**기존 (RDB - Wide Format):**
```python
# economic_and_stock_data 테이블에 한 행으로 저장
{
  "날짜": "2024-01-15",
  "애플": 150.0,
  "마이크로소프트": 300.0,
  "아마존": 100.0,
  ...
}
```

**변경 후 (MongoDB - Wide Format + 하이브리드):**
```python
# daily_stock_data collection에 날짜별로 저장
{
  "date": "2024-01-15",
  "fred_indicators": {...},
  "yfinance_indicators": {...},
  "stocks": {
    "AAPL": 150.0,
    "MSFT": 300.0,
    // ... 모든 종목 주가
  },
  "recommendations": {  // ✨ 하이브리드 접근법
    "AAPL": {
      "technical_indicators": {...},
      "is_recommended": true
    },
    // ... 모든 종목 추천 정보
  }
}
```

**하이브리드 접근법:**
- `daily_stock_data.recommendations`: 날짜별 통합 조회용
- `stock_recommendations`: 종목별 시계열 조회용
- 두 컬렉션은 동기화되어 유지

### 3. 쿼리 패턴 변경

**기존: 종목 목록을 동적으로 생성하여 컬럼 선택**
```python
quoted_columns = [f'"{col}"' for col in self.stock_columns]
response = supabase.table("economic_and_stock_data") \
    .select(*quoted_columns) \
    .gte("날짜", start_date_str) \
    .execute()
```

**변경 후: 사용자별 관심 종목 또는 활성 종목 조회**
```python
# 사용자별 관심 종목 조회
user_stocks = await db.user_stocks.find(
    {"user_id": user_id, "is_active": True}
).to_list(length=None)

tickers = [s["ticker"] for s in user_stocks]

# 주가 데이터 조회 (daily_stock_data에서 날짜별로 조회)
prices = await db.daily_stock_data.find({
    "date": {"$gte": start_date}
}).sort("date", 1).to_list(length=None)
# indicators 객체에서 필요한 종목 데이터 추출
```

---

## 마이그레이션 체크리스트

### 준비 단계
- [ ] MongoDB 서버 설치 및 설정
- [ ] MongoDB 클라이언트 라이브러리 설치 (`pymongo`, `motor`)
- [ ] 환경 변수 추가 (`.env`)
- [ ] 백업 계획 수립

### 개발 단계
- [ ] MongoDB 클라이언트 모듈 작성
- [ ] 기본 Collections 및 인덱스 생성 스크립트
- [ ] 데이터 마이그레이션 스크립트 작성
- [ ] 서비스 레이어 리팩토링
- [ ] API 엔드포인트 수정
- [ ] 개인화 기능 구현

### 테스트 단계
- [ ] 마이그레이션 스크립트 테스트
- [ ] 데이터 정합성 검증
- [ ] 성능 테스트
- [ ] 통합 테스트

### 배포 단계
- [ ] 프로덕션 MongoDB 설정
- [ ] 데이터 마이그레이션 실행
- [ ] 애플리케이션 배포
- [ ] 모니터링 및 검증

---

## 장점 요약

### 1. 유연성
- ✅ 종목 추가/제거 시 스키마 변경 불필요
- ✅ 동적 필드 추가 가능

### 2. 확장성
- ✅ 사용자 수 증가에 대응 가능
- ✅ 개인화 기능 확장 용이

### 3. 성능
- ✅ 필요한 데이터만 조회 가능
- ✅ 인덱싱 최적화 가능

### 4. 유지보수성
- ✅ 데이터 구조가 직관적
- ✅ 중복 제거로 일관성 향상

---

## 주의사항

1. **트랜잭션 지원**: MongoDB는 다중 문서 트랜잭션을 지원하지만, RDB만큼 강력하지 않음
2. **조인 연산**: MongoDB는 조인이 제한적이므로 애플리케이션 레벨에서 처리 필요
3. **데이터 검증**: RDB의 제약 조건 대신 애플리케이션 레벨에서 검증 필요
4. **마이그레이션 시간**: 대용량 데이터 마이그레이션 시 시간 소요

---

## 하이브리드 접근법 상세

### 개요

하이브리드 접근법은 다음 데이터에 적용됩니다:

1. **기술적 분석 추천**:
   - `daily_stock_data.recommendations`: 날짜별 통합 조회용
   - `stock_recommendations`: 종목별 시계열 조회용

2. **뉴스 감정 분석**:
   - `daily_stock_data.sentiment`: 날짜별 통합 조회용
   - `sentiment_analysis`: 종목별 시계열 조회용

3. **AI 예측 결과** ✅ **완료**:
   - `predicted_stocks` (Supabase): 날짜별 한 행에 모든 종목 (Wide format)
   - `stock_predictions` (MongoDB): 종목별로 분리된 문서 (Long format)
   - `daily_stock_data.predictions` (MongoDB): 날짜별 통합 조회용

4. **AI 분석 결과** ✅ **완료**:
   - `stock_analysis_results` (Supabase): 종목별 한 행에 모든 분석 지표
   - `stock_analysis` (MongoDB): 종목별 문서 (구조화된 형태)
   - `daily_stock_data.analysis` (MongoDB): 날짜별 통합 조회용

### 왜 하이브리드 접근법을 사용하는가?

#### 장점

1. **각 용도에 최적화된 구조**
   - 날짜별 조회: `daily_stock_data` (1번의 쿼리로 모든 정보)
   - 종목별 조회: `stock_recommendations` (인덱스 최적화)

2. **성능 최적화**
   - 자주 사용하는 쿼리 패턴에 맞춘 구조
   - 인덱스 활용 최대화

3. **유연성**
   - 필요에 따라 적절한 컬렉션 선택
   - 확장 용이

#### 데이터 동기화

1. **기술적 분석**:
   - `generate_technical_recommendations()` 실행 시 두 컬렉션 모두 업데이트
   - `verify_mongodb_sync()` 함수로 동기화 상태 확인

2. **뉴스 감정 분석**:
   - `fetch_and_store_sentiment_for_recommendations()` 실행 시 두 컬렉션 모두 업데이트

3. **AI 예측 결과**:
   - `save_predictions_to_db()` 실행 시 Supabase와 MongoDB 모두 저장
   - `bulk_write`를 사용한 배치 처리로 성능 최적화
   - `daily_stock_data.predictions` 필드에도 동시 저장 (날짜별 통합 조회용)

4. **AI 분석 결과**:
   - `save_analysis_to_db()` 실행 시 Supabase와 MongoDB 모두 저장
   - `bulk_write`를 사용한 배치 처리로 성능 최적화
   - `daily_stock_data.analysis` 필드에도 동시 저장 (날짜별 통합 조회용)

### 인덱스 전략

#### daily_stock_data 인덱스

1. **`date_unique`** (unique)
   - 날짜별 조회 최적화
   - 중복 방지

2. **`recommendations_exists_idx`** (sparse)
   - recommendations 필드 존재 여부 필터링
   - sparse 인덱스로 필드가 없는 문서는 제외

3. **`date_recommendations_idx`**
   - 날짜 범위 조회 시 recommendations 필드가 있는 문서만 조회 최적화

4. **`sentiment_exists_idx`** (sparse)
   - sentiment 필드 존재 여부 필터링

5. **`date_sentiment_idx`**
   - 날짜 범위 조회 시 sentiment 필드가 있는 문서만 조회 최적화

6. **`predictions_exists_idx`** (sparse)
   - predictions 필드 존재 여부 필터링

7. **`date_predictions_idx`**
   - 날짜 범위 조회 시 predictions 필드가 있는 문서만 조회 최적화

8. **`analysis_exists_idx`** (sparse)
   - analysis 필드 존재 여부 필터링

9. **`date_analysis_idx`**
   - 날짜 범위 조회 시 analysis 필드가 있는 문서만 조회 최적화

#### stock_recommendations 인덱스

1. **`date_ticker_user_idx`**
   - 복합 인덱스 (날짜 + 티커 + 사용자)
   - 기본 조회 최적화

2. **`user_date_idx`**
   - 사용자별 날짜 역순 조회
   - 개인화 추천 조회 최적화

3. **`ticker_date_idx`**
   - 종목별 날짜 역순 조회
   - 시계열 분석 최적화

4. **`recommended_date_idx`**
   - 추천 여부 필터링 및 날짜 역순 정렬
   - 추천 종목만 조회 시 최적화

5. **`ticker_recommended_date_idx`**
   - 종목별 추천 여부 필터링
   - 종목별 추천 이력 조회 최적화

#### stock_predictions 인덱스 ✅

1. **`date_ticker_unique`** (unique)
   - 날짜+티커 복합 인덱스
   - upsert 쿼리 최적화 및 중복 방지

2. **`date_idx`**
   - 날짜별 조회 최적화

3. **`ticker_date_idx`**
   - 티커별 시계열 조회 최적화

#### stock_analysis 인덱스 ✅

1. **`date_ticker_user_idx`**
   - 날짜+티커+사용자 복합 인덱스
   - 기본 조회 최적화

2. **`user_date_idx`**
   - 사용자별 날짜 역순 조회 최적화

### API 엔드포인트

1. **날짜별 통합 조회**: `GET /stocks/mongodb/daily/{date}`
2. **종목별 시계열 조회**: `GET /stocks/mongodb/stocks/{ticker}/recommendations`
3. **날짜 범위별 집계**: `GET /stocks/mongodb/recommendations/range`
4. **동기화 상태 확인**: `GET /stocks/mongodb/sync/{date}`

자세한 내용은 `MongoDB_하이브리드_사용가이드.md` 참조

---

## 다음 단계

1. MongoDB 서버 설정
2. 기본 구조 구현
3. 하이브리드 접근법 구현
4. 데이터 마이그레이션 스크립트 작성
5. 서비스 레이어 단계적 리팩토링
6. 동기화 모니터링 설정
