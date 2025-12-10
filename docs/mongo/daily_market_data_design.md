# daily_market_data 컬렉션 설계 비교

## 두 가지 저장 방식 비교

### 방식 1: 날짜별로 저장 (Wide Format)
하나의 문서에 특정 날짜의 모든 시장 지표 데이터를 저장

```javascript
{
  _id: ObjectId("..."),
  date: ISODate("2024-01-15"),
  indicators: {
    "나스닥 종합지수": 15000.0,
    "S&P 500 지수": 4800.0,
    "금 가격": 2000.0,
    "달러 인덱스": 103.5,
    "VIX 지수": 15.2,
    "S&P 500 ETF": 480.0,
    "QQQ ETF": 380.0,
    // ... 모든 시장 지표
  },
  created_at: ISODate("2024-01-15"),
  updated_at: ISODate("2024-01-15")
}
```

**장점:**
- ✅ 특정 날짜의 모든 시장 지표를 한 번에 조회 가능
- ✅ 날짜별 집계/분석이 쉬움
- ✅ 경제 지표와 유사한 구조 (일관성)

**단점:**
- ❌ 새로운 시장 지표 추가 시 문서 구조 변경 필요 (하지만 MongoDB는 유연하므로 큰 문제 아님)
- ❌ 특정 지표의 시계열 조회 시 모든 문서를 스캔해야 함

---

### 방식 2: 지표별로 저장 (Long Format)
각 시장 지표마다 별도 문서로 저장

```javascript
// 나스닥 종합지수
{
  _id: ObjectId("..."),
  date: ISODate("2024-01-15"),
  indicator_name: "나스닥 종합지수",
  indicator_type: "index",
  value: 15000.0,
  created_at: ISODate("2024-01-15")
}

// S&P 500 지수
{
  _id: ObjectId("..."),
  date: ISODate("2024-01-15"),
  indicator_name: "S&P 500 지수",
  indicator_type: "index",
  value: 4800.0,
  created_at: ISODate("2024-01-15")
}

// ... 각 지표마다 별도 문서
```

**장점:**
- ✅ 새로운 지표 추가 시 새 문서만 추가하면 됨 (매우 유연)
- ✅ 특정 지표의 시계열 조회가 효율적 (인덱스 활용)
- ✅ `stock_prices`와 동일한 구조 (일관성)

**단점:**
- ❌ 특정 날짜의 모든 지표 조회 시 여러 쿼리 필요
- ❌ 문서 수가 많아짐 (날짜 수 × 지표 수)

---

## 추천: **방식 1 (날짜별 저장)**

### 이유:

1. **시장 지표의 특성**
   - 시장 지표는 날짜당 하나의 값만 존재
   - 모든 지표를 함께 분석하는 경우가 많음
   - 날짜별로 조회하는 패턴이 일반적

2. **기존 구조와의 일관성**
   - `economic_data` 컬렉션도 날짜별로 저장
   - `daily_market_data`는 `economic_data`의 확장 개념

3. **쿼리 효율성**
   - 특정 날짜의 모든 시장 데이터 조회 시 1번의 쿼리로 가능
   - 날짜 범위 조회도 효율적

4. **MongoDB의 유연성**
   - 새로운 지표 추가 시 `indicators` 객체에 자동으로 추가 가능
   - 스키마 변경 불필요

---

## 최종 설계

### `daily_market_data` Collection (날짜별 저장)

```javascript
{
  _id: ObjectId,
  date: Date,                    // 거래일 (unique)
  indicators: {                  // 시장 지표 데이터 (동적 객체)
    "나스닥 종합지수": Number,
    "S&P 500 지수": Number,
    "금 가격": Number,
    "달러 인덱스": Number,
    "VIX 지수": Number,
    "S&P 500 ETF": Number,
    "QQQ ETF": Number,
    // ... fred_indicators와 yfinance_indicators 컬렉션의 활성 지표들
  },
  created_at: Date,
  updated_at: Date
}
```

**인덱스:**
- `{ date: 1 }` (unique)

**특징:**
- `fred_indicators`와 `yfinance_indicators` 컬렉션의 활성 지표만 저장
- 새로운 지표 추가 시 해당 컬렉션에 추가하면 자동으로 포함됨
- 날짜별로 하나의 문서만 존재

---

## 대안: `economic_data`와 통합

`daily_market_data`를 별도로 만들지 않고 `economic_data`에 통합할 수도 있습니다:

```javascript
{
  _id: ObjectId,
  date: Date,
  indicators: {
    // 경제 지표
    "10년 기대 인플레이션율": Number,
    "기준금리": Number,
    // ...
    
    // 시장 지표 (fred_indicators와 yfinance_indicators에서 가져옴)
    "나스닥 종합지수": Number,
    "S&P 500 지수": Number,
    "VIX 지수": Number,
    // ...
  }
}
```

이 경우 `daily_market_data` 컬렉션은 필요 없고, `economic_data`만 사용하면 됩니다.

---

## 결론

**추천: `economic_data`에 통합하여 사용**

이유:
1. 경제 지표와 시장 지표는 모두 날짜별로 하나의 값만 존재
2. 별도 컬렉션으로 분리할 필요가 없음
3. 쿼리 단순화 (하나의 컬렉션만 조회)
4. 데이터 일관성 유지

`daily_market_data` 컬렉션은 제거하고, `economic_data`의 `indicators` 객체에 모든 지표를 저장하는 것을 권장합니다.
