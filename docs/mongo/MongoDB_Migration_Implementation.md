# MongoDB 마이그레이션 구현 가이드

## 시작하기 전에

### 1. MongoDB 설치 및 실행

**로컬 MongoDB 설치:**
```bash
# macOS (Homebrew)
brew tap mongodb/brew
brew install mongodb-community
brew services start mongodb-community

# 또는 Docker 사용
docker run -d -p 27017:27017 --name mongodb mongo:latest
```

**MongoDB Atlas (클라우드) 사용:**
1. https://www.mongodb.com/cloud/atlas 에서 계정 생성
2. 클러스터 생성
3. Connection String 복사

### 2. 환경 변수 설정

`.env` 파일에 다음 설정 추가:

```env
# MongoDB 설정
USE_MONGODB=true
MONGODB_URL=mongodb://localhost:27017
# 또는 MongoDB Atlas 사용 시:
# MONGODB_URL=mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority

MONGODB_DATABASE=stock_trading
```

### 3. 의존성 설치

```bash
pip install -r requirements.txt
```

---

## 단계별 구현 가이드

### Step 1: MongoDB 스키마 설정

```bash
# 스키마 및 인덱스 생성
python scripts/setup_mongodb_schema.py
```

이 스크립트는:
- 모든 collections 생성
- 필요한 인덱스 생성
- 기존 `stock_ticker_mapping` 데이터 마이그레이션 (선택사항)

### Step 2: 데이터 마이그레이션

데이터 마이그레이션 스크립트 작성 예정 (`scripts/migrate_to_mongodb.py`)

---

## MongoDB vs Supabase 비교

### 데이터 저장 방식

**기존 (RDB - Wide Format):**
```python
# 하나의 행에 모든 종목 데이터
{
  "날짜": "2024-01-15",
  "애플": 150.0,
  "마이크로소프트": 300.0,
  "아마존": 100.0,
  ...
}
```

**MongoDB (Long Format):**
```python
# 각 종목별로 별도 문서
[
  {"date": "2024-01-15", "ticker": "AAPL", "close": 150.0},
  {"date": "2024-01-15", "ticker": "MSFT", "close": 300.0},
  {"date": "2024-01-15", "ticker": "AMZN", "close": 100.0},
]
```

### 쿼리 예시

**기존 (Supabase):**
```python
quoted_columns = [f'"{col}"' for col in stock_columns]
response = supabase.table("economic_and_stock_data") \
    .select(*quoted_columns) \
    .gte("날짜", start_date_str) \
    .execute()
```

**MongoDB:**
```python
# 사용자별 관심 종목 조회
user_stocks = await db.user_stocks.find(
    {"user_id": user_id, "is_active": True}
).to_list(length=None)

tickers = [s["ticker"] for s in user_stocks]

# 주가 데이터 조회
prices = await db.stock_prices.find({
    "ticker": {"$in": tickers},
    "date": {"$gte": start_date}
}).sort("date", 1).to_list(length=None)
```

---

## 주요 변경 사항

### 1. 서비스 레이어 변경

**기존:**
- `app/services/economic_service.py`
- `app/services/stock_recommendation_service.py`
- `app/services/auto_trading_service.py`

**변경:**
- MongoDB collections 사용
- 비동기 쿼리로 변경 (FastAPI와 호환)

### 2. 데이터 저장 로직 변경

**기존:**
```python
# predicted_stocks 테이블에 한 행으로 저장
{
  "날짜": "2024-01-15",
  "애플_Predicted": 155.0,
  "애플_Actual": 150.0,
  "마이크로소프트_Predicted": 305.0,
  ...
}
```

**변경 후:**
```python
# stock_predictions collection에 종목별로 저장
[
  {
    "date": "2024-01-15",
    "ticker": "AAPL",
    "predicted_price": 155.0,
    "actual_price": 150.0
  },
  {
    "date": "2024-01-15",
    "ticker": "MSFT",
    "predicted_price": 305.0,
    "actual_price": 300.0
  }
]
```

---

## 개인화 기능 구현

### 사용자별 관심 종목 추가

```python
# app/api/routes/user_stocks.py (새로 생성)

@router.post("/users/{user_id}/stocks")
async def add_user_stock(user_id: str, ticker: str):
    """사용자의 관심 종목 추가"""
    # 1. 종목 정보 조회
    stock = await db.stocks.find_one({"ticker": ticker, "is_active": True})
    if not stock:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다.")
    
    # 2. 사용자 관심 종목 추가
    user_stock = {
        "user_id": user_id,
        "stock_id": str(stock["_id"]),
        "ticker": ticker,
        "is_active": True,
        "added_at": datetime.utcnow()
    }
    
    result = await db.user_stocks.insert_one(user_stock)
    return {"message": "관심 종목이 추가되었습니다.", "id": str(result.inserted_id)}
```

### 개인화된 추천 조회

```python
@router.get("/users/{user_id}/recommendations")
async def get_user_recommendations(user_id: str):
    """사용자별 개인화된 추천 조회"""
    # 1. 사용자의 관심 종목 조회
    user_stocks = await db.user_stocks.find(
        {"user_id": user_id, "is_active": True}
    ).to_list(length=None)
    
    tickers = [s["ticker"] for s in user_stocks]
    
    # 2. 해당 종목들의 추천 조회
    recommendations = await db.stock_recommendations.find({
        "ticker": {"$in": tickers},
        "user_id": {"$in": [None, user_id]},  # 전역 또는 개인화 추천
        "is_recommended": True
    }).sort("recommendation_score", -1).to_list(length=10)
    
    return {"recommendations": recommendations}
```

---

## 마이그레이션 체크리스트

### Phase 1: 기본 구조 구축 ✅
- [x] MongoDB 클라이언트 설정
- [x] Config 설정 추가
- [x] 스키마 및 인덱스 생성 스크립트
- [x] Pydantic 모델 정의

### Phase 2: 데이터 마이그레이션
- [ ] 마이그레이션 스크립트 작성
- [ ] 기존 데이터 변환 및 검증
- [ ] 데이터 정합성 확인

### Phase 3: 서비스 레이어 리팩토링
- [ ] Economic Service 리팩토링
- [ ] Stock Recommendation Service 리팩토링
- [ ] Auto Trading Service 리팩토링
- [ ] Predict 스크립트 리팩토링

### Phase 4: API 엔드포인트 수정
- [ ] 기존 API 엔드포인트 수정
- [ ] 개인화 API 엔드포인트 추가
- [ ] 사용자 인증/인가 연동

### Phase 5: 테스트
- [ ] 단위 테스트
- [ ] 통합 테스트
- [ ] 성능 테스트

---

## 다음 단계

1. **데이터 마이그레이션 스크립트 작성**
   - Supabase → MongoDB 변환
   - 데이터 검증

2. **서비스 레이어 단계적 리팩토링**
   - 하나씩 변경하며 테스트
   - 기존 Supabase 코드와 병행 운영 가능하도록

3. **개인화 기능 구현**
   - 사용자 인증 시스템 연동
   - 관심 종목 관리 기능
