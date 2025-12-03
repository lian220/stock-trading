# 매수 추천 쿼리 모음

## 📁 파일 구조

```
queries/
├── README.md (이 파일)
├── stock_recommendations_query.sql          # 기술적 지표
├── stock_analysis_results_query.sql         # 주가 예측
├── ticker_sentiment_analysis_query.sql      # 감정 분석
└── combined_buy_recommendation_query.sql    # 통합 추천 ⭐
```

---

## 🎯 빠른 시작

### 최종 매수 추천 확인 (권장)
```bash
psql -f combined_buy_recommendation_query.sql
```
→ 모든 조건을 통합한 최종 매수 추천 리스트

---

## 📊 테이블별 쿼리

### 1. stock_recommendations_query.sql
**기술적 지표 기반 매수 추천**

| 조건 | 설명 | 가중치 |
|-----|------|-------|
| 골든크로스 | SMA20 > SMA50 | 1.5점 |
| RSI < 50 | 과매도 구간 | 1.0점 |
| MACD 매수신호 | MACD > Signal | 1.0점 |

**매수 기준**: 기술적 신호 점수 ≥ 2.0점

---

### 2. stock_analysis_results_query.sql
**AI 주가 예측 기반 매수 추천**

| 조건 | 기준값 |
|-----|--------|
| 정확도 | ≥ 80% |
| 상승확률 | ≥ 3% |

**매수 기준**: 정확도와 상승확률 모두 충족

---

### 3. ticker_sentiment_analysis_query.sql
**뉴스 감정 분석 기반 매수 추천**

| 조건 | 기준값 |
|-----|--------|
| 감정 점수 | ≥ 0.15 (긍정적) |
| 기사 수 | ≥ 5개 |

**매수 기준**: 긍정적 감정 + 충분한 기사 수

---

### 4. combined_buy_recommendation_query.sql ⭐
**통합 매수 추천 (최종 결정)**

#### 최종 매수 조건
```
조건 1: 감정 점수 ≥ 0.15 AND 기술적 신호 ≥ 2.0
       → 긍정적 감정 + 기술적 신호

조건 2: 감정 점수 < 0.15 AND 기술적 신호 ≥ 3.5
       → 강력한 기술적 신호 (3개 모두)
```

#### 종합 점수 계산
```
종합 점수 = 상승확률(30%) + 기술적지표(40%) + 감정점수(30%)
```

---

## 🔍 사용 예시

### Python에서 실행
```python
from app.db.supabase import supabase

# 쿼리 파일 읽기
with open('documents/queries/combined_buy_recommendation_query.sql', 'r') as f:
    query = f.read()

# 실행 (Supabase는 직접 SQL 제한적)
# Python 로직 사용 권장
```

### 서비스 클래스에서 사용
```python
from app.services.stock_recommendation_service import StockRecommendationService

service = StockRecommendationService()
result = service.get_combined_recommendations_with_technical_and_sentiment()

print(result['message'])
for stock in result['results']:
    print(f"{stock['stock_name']}: {stock['composite_score']}")
```

---

## 📋 출력 예시

### combined_buy_recommendation_query.sql 결과
```
ticker | stock_name | composite_score | buy_decision              | priority
-------|------------|-----------------|---------------------------|----------
NVDA   | 엔비디아   | 87.5            | ✅ 매수 추천: 긍정 감정 + 기술 신호 | 1
AAPL   | 애플       | 82.3            | ✅ 매수 추천: 강력한 기술 신호      | 2
TSLA   | 테슬라     | 78.9            | ⚠️ 매수 고려: 긍정 감정 + 일부 기술 | 3
```

---

## 📖 상세 가이드

전체 매수 조건 및 상세 설명은 다음 문서를 참고하세요:
- **[매수_쿼리_가이드.md](../매수_쿼리_가이드.md)**

---

## 🛠️ 쿼리 커스터마이징

### 조건 완화 (더 많은 종목)
```sql
-- stock_recommendations_query.sql
WHERE tech_signal_score >= 1.5  -- 기본: 2.0

-- stock_analysis_results_query.sql
WHERE "Accuracy (%)" >= 75      -- 기본: 80
  AND "Rise Probability (%)" >= 2  -- 기본: 3
```

### 조건 강화 (더 적은 종목, 높은 신뢰도)
```sql
-- combined_buy_recommendation_query.sql
WHERE 
    (sd.average_sentiment_score >= 0.25 AND td.tech_signal_score >= 2.5)
    OR
    (td.tech_signal_score >= 3.5 AND pd.accuracy >= 85)
```

---

## ⚠️ 주의사항

1. **데이터 최신성**: 각 테이블의 데이터가 최신인지 확인
2. **NULL 처리**: 감정 분석 데이터가 없는 경우 자동으로 0 처리
3. **백테스팅**: 실전 투자 전 과거 데이터로 검증 권장

---

## 📞 지원

쿼리 관련 문의: 이슈 등록 또는 문서 확인

