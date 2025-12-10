# daily_market_data 컬렉션 설계 비교

## 현재 상황

- `economic_data`: 날짜별로 저장 (경제 지표만)
- `stock_prices`: 종목별로 저장 (Long Format)
- `fred_indicators`: FRED 경제 지표 목록 관리 (메타데이터)
- `yfinance_indicators`: Yahoo Finance 지표/ETF 목록 관리 (메타데이터)

## 두 가지 저장 방식 비교

### 방식 1: 날짜별로 저장 (추천 ⭐)

```javascript
// 하나의 문서에 특정 날짜의 모든 시장 지표
{
  _id: ObjectId("..."),
  date: ISODate("2024-01-15"),
  indicators: {
    "나스닥 종합지수": 15000.0,
    "S&P 500 지수": 4800.0,
    "금 가격": 2000.0,
    "VIX 지수": 15.2,
    "S&P 500 ETF": 480.0,
    "QQQ ETF": 380.0,
    // ... 모든 시장 지표
  },
  created_at: ISODate("2024-01-15")
}
```

**장점:**
- ✅ 특정 날짜의 모든 시장 데이터를 한 번에 조회
- ✅ `economic_data`와 구조 일관성
- ✅ 날짜별 집계/분석이 효율적
- ✅ MongoDB의 유연성으로 새 지표 추가 용이

**단점:**
- ❌ 특정 지표의 시계열 조회 시 모든 문서 스캔 (하지만 인덱스로 해결 가능)

**쿼리 예시:**
```python
# 특정 날짜의 모든 시장 지표 조회
data = db.daily_market_data.find_one({"date": target_date})

# 날짜 범위 조회
data = db.daily_market_data.find({
    "date": {"$gte": start_date, "$lte": end_date}
}).sort("date", 1)
```

---

### 방식 2: 지표별로 저장

```javascript
// 각 지표마다 별도 문서
{
  _id: ObjectId("..."),
  date: ISODate("2024-01-15"),
  indicator_name: "나스닥 종합지수",
  indicator_type: "index",
  value: 15000.0,
  created_at: ISODate("2024-01-15")
}
```

**장점:**
- ✅ 특정 지표의 시계열 조회가 효율적
- ✅ `stock_prices`와 구조 일관성
- ✅ 새 지표 추가 시 새 문서만 추가

**단점:**
- ❌ 특정 날짜의 모든 지표 조회 시 여러 쿼리 필요
- ❌ 문서 수가 많아짐 (날짜 수 × 지표 수)
- ❌ 집계 쿼리가 복잡함

**쿼리 예시:**
```python
# 특정 날짜의 모든 지표 조회 (비효율적)
indicators = db.daily_market_data.find({"date": target_date})
# 여러 문서를 조회하고 Python에서 합쳐야 함

# 특정 지표의 시계열 조회 (효율적)
nasdaq_history = db.daily_market_data.find({
    "indicator_name": "나스닥 종합지수",
    "date": {"$gte": start_date, "$lte": end_date}
}).sort("date", 1)
```

---

## 추천: **방식 1 (날짜별 저장)**

### 이유:

1. **사용 패턴**
   - 대부분의 경우 특정 날짜의 모든 시장 지표를 함께 분석
   - 날짜별로 조회하는 패턴이 일반적

2. **기존 구조와의 일관성**
   - `economic_data`도 날짜별로 저장
   - 두 컬렉션을 통합하거나 유사한 구조 유지

3. **쿼리 효율성**
   - 날짜별 조회: 1번의 쿼리
   - 지표별 조회: 인덱스 활용 가능 (`indicators.나스닥 종합지수`)

4. **MongoDB의 유연성**
   - `indicators` 객체에 동적으로 지표 추가 가능
   - `fred_indicators`와 `yfinance_indicators` 컬렉션의 활성 지표만 저장

---

## 최종 설계 제안

### 옵션 A: `economic_data`에 통합 (가장 추천 ⭐⭐⭐)

`daily_market_data`를 별도로 만들지 않고, `economic_data`의 `indicators`에 모든 지표를 저장:

```javascript
{
  _id: ObjectId("..."),
  date: ISODate("2024-01-15"),
  indicators: {
    // 경제 지표
    "10년 기대 인플레이션율": 2.5,
    "기준금리": 5.25,
    // ...
    
    // 시장 지표 (fred_indicators와 yfinance_indicators에서 가져옴)
    "나스닥 종합지수": 15000.0,
    "S&P 500 지수": 4800.0,
    "VIX 지수": 15.2,
    "S&P 500 ETF": 480.0,
    // ...
  },
  created_at: ISODate("2024-01-15")
}
```

**장점:**
- 하나의 컬렉션으로 모든 지표 관리
- 쿼리 단순화
- 데이터 일관성

---

### 옵션 B: `daily_market_data` 별도 컬렉션

경제 지표와 시장 지표를 분리:

```javascript
// economic_data: 경제 지표만
{
  date: ISODate("2024-01-15"),
  indicators: {
    "10년 기대 인플레이션율": 2.5,
    "기준금리": 5.25,
    // ...
  }
}

// daily_market_data: 시장 지표만
{
  date: ISODate("2024-01-15"),
  indicators: {
    "나스닥 종합지수": 15000.0,
    "S&P 500 지수": 4800.0,
    // ...
  }
}
```

**장점:**
- 역할 분리 (경제 지표 vs 시장 지표)
- 필요에 따라 선택적 조회 가능

**단점:**
- 두 컬렉션을 조인해야 하는 경우가 생김
- 관리 복잡도 증가

---

## 최종 추천: **옵션 A (economic_data에 통합)**

`daily_market_data` 컬렉션을 만들지 않고, `economic_data`의 `indicators`에 모든 지표를 저장하는 것을 권장합니다.
