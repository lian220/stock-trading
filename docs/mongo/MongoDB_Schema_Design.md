# MongoDB 스키마 설계 문서

## 개요

이 문서는 MongoDB로 마이그레이션할 때의 스키마 설계를 정의합니다.
RDB(Supabase) 스키마와는 독립적으로 설계되었으며, 유연한 종목 관리와 개인별 설정을 지원합니다.

---

## 핵심 설계 원칙

1. **종목 정보와 사용자 설정 분리**
   - `stocks`: 종목 기본 정보 (모든 사용자 공통)
   - `user_stocks`: 사용자별 관심 종목 및 설정 (개인화)

2. **레버리지 사용 여부는 사용자별 설정**
   - 종목 자체에는 `leverage_ticker`만 저장 (어떤 레버리지 티커가 있는지 정보)
   - 실제 레버리지 사용 여부는 각 사용자가 `user_stocks`에서 설정

---

## Collections 구조

## 📊 분석 관련 컬렉션 (우선순위)

### 1. `stock_predictions` Collection
**목적**: AI 모델 예측 결과 저장 (하이브리드 접근법)

```javascript
{
  _id: ObjectId,
  date: Date,                  // 예측 기준일
  ticker: String,              // 티커 심볼 (예: "AAPL")
  stock_name: String,          // 한글 종목명 (예: "애플")
  predicted_price: Number,     // 예측 가격
  actual_price: Number,        // 실제 가격 (나중에 업데이트)
  forecast_horizon: Number,    // 예측 기간 (일) - 기본값: 14일
  created_at: Date,
  updated_at: Date
}
```

**인덱스:**
- `{ date: 1, ticker: 1 }` (unique) - upsert 쿼리 최적화 및 중복 방지
- `{ date: -1 }` - 날짜별 조회 최적화
- `{ ticker: 1, date: -1 }` - 티커별 시계열 조회 최적화

**하이브리드 접근법:**
- **Supabase `predicted_stocks`**: 날짜별 한 행에 모든 종목의 예측값/실제값 (Wide format)
- **MongoDB `stock_predictions`**: 종목별로 분리된 문서 (Long format)
- **MongoDB `daily_stock_data.predictions`**: 날짜별 통합 조회용
- 두 저장소에 동시 저장하여 서로 다른 조회 패턴 지원
- MongoDB는 종목별 시계열 분석에 최적화

**저장 최적화:**
- `bulk_write`를 사용한 배치 처리로 성능 향상
- 날짜+티커 조합을 키로 사용하여 중복 방지

---

### 2. `stock_analysis` Collection
**목적**: AI 분석 결과 저장 (하이브리드 접근법)

```javascript
{
  _id: ObjectId,
  date: Date,                  // 분석 기준일
  ticker: String,              // 티커 심볼
  stock_name: String,          // 한글 종목명
  stock_id: String,            // stocks._id 참조 (선택)
  user_id: String,            // null이면 전역 분석, 값이 있으면 개인화 분석
  metrics: {
    mae: Number,               // Mean Absolute Error
    mse: Number,               // Mean Squared Error
    rmse: Number,              // Root Mean Squared Error
    mape: Number,              // Mean Absolute Percentage Error
    accuracy: Number           // Accuracy (%)
  },
  predictions: {
    last_actual_price: Number,      // 마지막 실제 가격
    predicted_future_price: Number, // 예측 미래 가격
    predicted_rise: Boolean,        // 상승 예측 여부
    rise_probability: Number        // 상승 확률 (%)
  },
  recommendation: String,      // 추천 (예: "Buy", "Hold", "Sell")
  analysis: String,            // 분석 텍스트
  created_at: Date,
  updated_at: Date
}
```

**인덱스:**
- `{ date: 1, ticker: 1, user_id: 1 }` - 복합 인덱스 (기본 조회 최적화)
- `{ user_id: 1, date: -1 }` - 사용자별 날짜 역순 조회

**하이브리드 접근법:**
- **Supabase `stock_analysis_results`**: 종목별 한 행에 모든 분석 지표
- **MongoDB `stock_analysis`**: 종목별 문서 (구조화된 형태)
- **MongoDB `daily_stock_data.analysis`**: 날짜별 통합 조회용
- 두 저장소에 동시 저장하여 서로 다른 조회 패턴 지원
- MongoDB는 종목별 시계열 분석에 최적화

**저장 최적화:**
- `bulk_write`를 사용한 배치 처리로 성능 향상
- 날짜+티커+user_id 조합을 키로 사용하여 중복 방지

---

### 3. `stock_recommendations` Collection
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

**설계 이유**:
- 종목별 시계열 조회에 최적화
- 인덱스를 활용한 효율적인 쿼리
- 개인화 추천 지원 (user_id 필드)

**인덱스**:
- `{ date: 1, ticker: 1, user_id: 1 }` - 복합 인덱스
- `{ user_id: 1, date: -1 }` - 사용자별 날짜 역순 조회
- `{ ticker: 1, date: -1 }` - 종목별 시계열 조회 (시계열 분석용)
- `{ is_recommended: 1, date: -1 }` - 추천 여부 필터링
- `{ ticker: 1, is_recommended: 1, date: -1 }` - 종목별 추천 이력 조회 최적화

**하이브리드 접근법**:
- 이 컬렉션은 **종목별 시계열 조회용**으로 사용
- 날짜별 통합 조회는 `daily_stock_data` 컬렉션 사용
- 두 컬렉션은 동기화되어 유지됨

**하이브리드 접근법 상세 설명**:

1. **날짜별 통합 조회**: `daily_stock_data.recommendations` 사용
   - 대시보드에서 오늘의 추천 종목 표시
   - 특정 날짜의 모든 시장 데이터 조회
   - 1번의 쿼리로 모든 정보 조회 가능

2. **종목별 시계열 조회**: `stock_recommendations` 사용
   - 종목별 추천 패턴 분석
   - 시계열 차트 데이터 생성
   - 인덱스 최적화된 조회

3. **동기화**: 두 컬렉션은 동일한 데이터를 저장하되 용도에 따라 분리
   - `generate_technical_recommendations()` 실행 시 두 컬렉션 모두 업데이트
   - `verify_mongodb_sync()` 함수로 동기화 상태 확인 가능

---

### 4. `sentiment_analysis` Collection
**목적**: 뉴스 감정 분석 결과 저장 (하이브리드 접근법)

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

**하이브리드 접근법**:
- **MongoDB `sentiment_analysis`**: 종목별 시계열 조회용
- **MongoDB `daily_stock_data.sentiment`**: 날짜별 통합 조회용
- 두 컬렉션은 동기화되어 유지됨

---

### 5. `daily_stock_data` Collection
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
  volumes: {                       // 거래량 데이터 (개선된 구조)
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

**설계 이유**:
- 날짜별로 모든 데이터를 한 번에 조회 가능 (대시보드 최적화)
- 주가 데이터와 추천 정보를 통합하여 조회 효율성 향상
- MongoDB의 유연한 스키마 활용
- `stock_prices`, `stock_volumes` 컬렉션을 통합하여 구조 단순화
- 상세 가격 정보(open, high, low, close_price)와 거래량을 한 곳에서 관리

**인덱스**:
- `{ date: 1 }` (unique) - 날짜별 조회 최적화
- `{ recommendations: 1 }` (sparse) - recommendations 필드 존재 여부 필터링
- `{ date: 1, recommendations: 1 }` - 날짜 범위 조회 최적화
- `{ sentiment: 1 }` (sparse) - sentiment 필드 존재 여부 필터링
- `{ date: 1, sentiment: 1 }` - 날짜 범위 조회 최적화 (sentiment)
- `{ predictions: 1 }` (sparse) - predictions 필드 존재 여부 필터링
- `{ date: 1, predictions: 1 }` - 날짜 범위 조회 최적화 (predictions)
- `{ analysis: 1 }` (sparse) - analysis 필드 존재 여부 필터링
- `{ date: 1, analysis: 1 }` - 날짜 범위 조회 최적화 (analysis)
- `{ stocks: 1 }` (sparse) - stocks 필드 존재 여부 필터링
- `{ volumes: 1 }` (sparse) - volumes 필드 존재 여부 필터링

**하이브리드 접근법**:
- 이 컬렉션은 **날짜별 통합 조회용**으로 사용
- 종목별 시계열 조회는 별도 컬렉션 사용:
  - `stock_recommendations`: 기술적 분석 시계열
  - `sentiment_analysis`: 감정 분석 시계열
  - `stock_predictions`: 예측 결과 시계열
  - `stock_analysis`: 분석 결과 시계열
- 두 저장소는 동기화되어 유지됨

---

## 📋 기본 컬렉션

### 6. `stocks` Collection
**목적**: 종목 기본 정보 저장 (모든 사용자 공통)

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

**설명**:
- `leverage_ticker`: 해당 종목의 레버리지 티커가 무엇인지 정보만 저장
- `use_leverage`는 없음 (사용자별 설정이므로)

**인덱스**:
- `{ ticker: 1 }` (unique)
- `{ stock_name: 1 }` (unique)
- `{ is_active: 1 }`

**예시**:
```javascript
{
  _id: ObjectId("..."),
  ticker: "AAPL",
  stock_name: "애플",
  is_etf: false,
  leverage_ticker: "AAPU",  // 레버리지 티커 정보
  is_active: true,
  created_at: ISODate("2024-01-01"),
  updated_at: ISODate("2024-01-01")
}
```

---

### 7. `user_stocks` Collection
**목적**: 사용자별 관심 종목 및 개인 설정

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
- `use_leverage`: 사용자가 해당 종목에 레버리지를 사용할지 여부를 개인적으로 설정
- `stocks` collection의 `leverage_ticker`와 함께 사용하면 실제 거래 시 레버리지 티커를 선택할 수 있음

**인덱스**:
- `{ user_id: 1, stock_id: 1 }` (unique)
- `{ user_id: 1, is_active: 1 }`
- `{ ticker: 1 }`

**예시**:
```javascript
// 사용자 A가 애플을 관심 종목으로 추가하고 레버리지 사용 설정
{
  _id: ObjectId("..."),
  user_id: "user123",
  stock_id: "stock_aapl_id",
  ticker: "AAPL",
  use_leverage: true,  // 이 사용자는 레버리지 사용
  notes: "장기 투자 예정",
  tags: ["tech", "blue-chip"],
  is_active: true,
  added_at: ISODate("2024-01-15"),
  created_at: ISODate("2024-01-15"),
  updated_at: ISODate("2024-01-15")
}

// 사용자 B도 애플을 관심 종목으로 추가했지만 레버리지 미사용
{
  _id: ObjectId("..."),
  user_id: "user456",
  stock_id: "stock_aapl_id",
  ticker: "AAPL",
  use_leverage: false,  // 이 사용자는 레버리지 미사용
  is_active: true,
  added_at: ISODate("2024-01-20"),
  created_at: ISODate("2024-01-20"),
  updated_at: ISODate("2024-01-20")
}
```

---

### 8. `users` Collection
```javascript
{
  _id: ObjectId,
  user_id: String,             // 사용자 식별자 (UUID 또는 이메일)
  email: String,               // 이메일 (선택)
  display_name: String,        // 표시명
  preferences: {
    default_currency: String,  // "USD", "KRW"
    notification_enabled: Boolean,
  },
  created_at: Date,
  updated_at: Date
}
```

---

### 9. `stock_prices` Collection ⚠️ **사용 안 함 (deprecated)**
> **참고**: 이 컬렉션은 더 이상 사용되지 않습니다. 주가 데이터는 `daily_stock_data.stocks` 필드에 통합되었습니다.
> 
> 종목별 시계열 조회가 필요한 경우에만 별도 컬렉션을 고려할 수 있습니다.

---

### 10. `stock_volumes` Collection ⚠️ **사용 안 함 (deprecated)**
> **참고**: 이 컬렉션은 더 이상 사용되지 않습니다. 거래량 데이터는 `daily_stock_data.volumes` 필드에 통합되었습니다.
> 
> 종목별 시계열 조회가 필요한 경우에만 별도 컬렉션을 고려할 수 있습니다.

---

### 11. `economic_data` Collection
```javascript
{
  _id: ObjectId,
  date: Date,
  indicators: {
    "10년 기대 인플레이션율": Number,
    "장단기 금리차": Number,
    "기준금리": Number,
    // ... 기타 경제 지표 (동적 추가 가능)
  },
  created_at: Date
}
```

**설계 이유**:
- 경제 지표는 날짜별로 하나의 문서만 존재
- `indicators` 객체에 동적으로 지표 추가 가능
- 스키마 변경 없이 새로운 지표 추가 가능

---

### 12. `trading_configs` Collection
```javascript
{
  _id: ObjectId,
  user_id: String,
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

---

### 13. `trading_logs` Collection
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

---

## 레버리지 사용 흐름

### 시나리오: 사용자가 레버리지를 사용하여 주식을 매수

1. **종목 정보 조회**
   ```python
   stock = await db.stocks.find_one({"ticker": "AAPL"})
   # stock.leverage_ticker = "AAPU"
   ```

2. **사용자 설정 확인**
   ```python
   user_stock = await db.user_stocks.find_one({
       "user_id": "user123",
       "ticker": "AAPL"
   })
   # user_stock.use_leverage = true
   ```

3. **실제 거래 티커 결정**
   ```python
   if user_stock.use_leverage and stock.leverage_ticker:
       trading_ticker = stock.leverage_ticker  # "AAPU" 사용
   else:
       trading_ticker = stock.ticker  # "AAPL" 사용
   ```

4. **거래 실행**
   - 결정된 티커(`AAPU` 또는 `AAPL`)로 주문

---

## 데이터 구조 비교

### 기존 RDB 구조 (Wide Format)
```sql
-- 하나의 행에 모든 종목 데이터
economic_and_stock_data 테이블:
날짜       | 애플 | 마이크로소프트 | 아마존 | ...
2024-01-15 | 150  | 300           | 100    | ...
```

**문제점**:
- 새 종목 추가 시 `ALTER TABLE` 필요
- 사용자별 설정 불가

### MongoDB 구조 (Long Format)
```javascript
// 각 종목별로 별도 문서
stock_prices collection:
[
  {date: "2024-01-15", ticker: "AAPL", close: 150},
  {date: "2024-01-15", ticker: "MSFT", close: 300},
  {date: "2024-01-15", ticker: "AMZN", close: 100}
]
```

**장점**:
- 종목 추가 시 스키마 변경 불필요
- 사용자별 설정 가능 (`user_stocks` collection)

---

## 사용 예시

### 사용자별 관심 종목 추가 및 레버리지 설정

```python
# 1. 종목 정보 조회
stock = await db.stocks.find_one({"ticker": "AAPL"})

# 2. 사용자 관심 종목 추가 (레버리지 사용 설정)
user_stock = {
    "user_id": "user123",
    "stock_id": str(stock["_id"]),
    "ticker": "AAPL",
    "use_leverage": True,  # 레버리지 사용
    "is_active": True
}
await db.user_stocks.insert_one(user_stock)

# 3. 사용자의 관심 종목 조회
user_stocks = await db.user_stocks.find({
    "user_id": "user123",
    "is_active": True
}).to_list(length=None)

# 4. 각 종목의 거래 티커 결정
for us in user_stocks:
    stock = await db.stocks.find_one({"_id": ObjectId(us["stock_id"])})
    if us["use_leverage"] and stock["leverage_ticker"]:
        trading_ticker = stock["leverage_ticker"]
    else:
        trading_ticker = stock["ticker"]
    
    print(f"{stock['stock_name']}: {trading_ticker} 사용")
```

---

## 마이그레이션 시 주의사항

1. **기존 RDB 데이터 마이그레이션 시**
   - `stock_ticker_mapping`의 데이터를 `stocks` collection으로 변환
   - `use_leverage` 정보는 마이그레이션하지 않음 (사용자가 나중에 설정)

2. **새로운 종목 추가**
   - `stocks` collection에만 추가하면 됨
   - 스키마 변경 불필요

3. **사용자별 설정**
   - 각 사용자가 `user_stocks`에서 개인 설정
   - 같은 종목이라도 사용자마다 다른 설정 가능

---

## 요약

### 컬렉션 구조

- ✅ `stocks`: 종목 기본 정보 (공통)
  - `leverage_ticker`: 레버리지 티커 정보만 저장
  
- ✅ `user_stocks`: 사용자별 설정
  - `use_leverage`: 사용자가 레버리지 사용 여부를 개인적으로 설정

- ✅ `daily_stock_data`: 날짜별 통합 데이터
  - `stocks`: 주가 데이터 (개선: 객체 형태로 open, high, low, close 포함)
  - `volumes`: 거래량 데이터 (통합 완료, `stock_daily_volume` 대체)
  - `recommendations`: 추천 정보 포함 (하이브리드 접근법)
  - 날짜별 통합 조회 최적화
  - 인덱스: `date_unique`, `recommendations_exists_idx`, `date_recommendations_idx`, `stocks_exists_idx`, `volumes_exists_idx`

- ✅ `stock_recommendations`: 종목별 시계열 데이터
  - 종목별 시계열 조회 최적화
  - 개인화 추천 지원
  - 인덱스: `ticker_date_idx`, `recommended_date_idx`, `ticker_recommended_date_idx` 등

### 하이브리드 접근법

- **날짜별 조회**: `daily_stock_data` 사용
  - 대시보드, 날짜별 통합 분석
  - 1번의 쿼리로 모든 정보 조회 (주가, 거래량, 추천, 감정, 예측, 분석)

- **종목별 조회**: 별도 컬렉션 사용
  - `stock_recommendations`: 시계열 분석, 종목별 추천 이력
  - `stock_predictions`: 종목별 예측 이력
  - `stock_analysis`: 종목별 분석 이력
  - 인덱스 최적화된 조회

- **동기화**: 두 저장소는 동일한 데이터를 저장하되 용도에 따라 분리
  - `generate_technical_recommendations()` 실행 시 자동 동기화
  - `verify_mongodb_sync()` 함수로 상태 확인

### 데이터 구조 개선 사항

- ✅ `stock_prices`, `stock_volumes` 컬렉션 통합
  - `daily_stock_data.stocks`: 객체 형태로 상세 가격 정보 저장
  - `daily_stock_data.volumes`: 거래량 데이터 통합
  - 구조 단순화 및 조회 효율성 향상

### 인덱스 전략

**daily_stock_data:**
- 날짜별 조회 최적화
- recommendations 필드 필터링 최적화

**stock_recommendations:**
- 종목별 시계열 조회 최적화
- 추천 여부 필터링 최적화
- 복합 인덱스로 다양한 쿼리 패턴 지원

이렇게 분리하여 각 사용자가 자신만의 레버리지 사용 전략을 설정할 수 있으며, 각 용도에 최적화된 조회가 가능합니다.
