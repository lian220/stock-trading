# 자동매매 API 가이드

## 📋 목차
1. [개요](#개요)
2. [API 엔드포인트](#api-엔드포인트)
3. [자동매매 설정](#자동매매-설정)
4. [자동 매수](#자동-매수)
5. [자동 매도](#자동-매도)
6. [상태 조회](#상태-조회)
7. [사용 예시](#사용-예시)

---

## 개요

자동매매 API는 매수 추천 종목을 자동으로 매수하고, 보유 종목을 자동으로 매도하는 기능을 제공합니다.

### 주요 기능
- ✅ **자동 매수**: 종합 점수 기반 매수 추천 종목 자동 매수
- ✅ **자동 매도**: 손절/익절 조건에 따른 자동 매도
- ✅ **설정 관리**: 자동매매 조건 커스터마이징
- ✅ **상태 모니터링**: 포트폴리오 및 매매 내역 조회
- ✅ **Dry Run 모드**: 실제 주문 없이 시뮬레이션

---

## API 엔드포인트

### Base URL
```
http://localhost:8000/auto-trading
```

### 엔드포인트 목록

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| GET | `/config` | 자동매매 설정 조회 |
| PUT | `/config` | 자동매매 설정 업데이트 |
| GET | `/candidates/buy` | 매수 추천 종목 조회 |
| GET | `/candidates/sell` | 매도 대상 종목 조회 |
| POST | `/execute/buy` | 자동 매수 실행 |
| POST | `/execute/sell` | 자동 매도 실행 |
| GET | `/status` | 자동매매 상태 조회 |
| GET | `/logs` | 주문 내역 조회 |
| POST | `/backtest` | 백테스팅 실행 (개발 중) |

---

## 자동매매 설정

### 1. 설정 조회

**요청**
```bash
curl -X GET http://localhost:8000/auto-trading/config
```

**응답**
```json
{
  "success": true,
  "config": {
    "enabled": false,
    "min_composite_score": 70.0,
    "max_stocks_to_buy": 5,
    "max_amount_per_stock": 10000.0,
    "stop_loss_percent": -7.0,
    "take_profit_percent": 5.0,
    "use_sentiment": true,
    "min_sentiment_score": 0.15,
    "order_type": "00"
  }
}
```

### 2. 설정 업데이트

**요청**
```bash
curl -X PUT http://localhost:8000/auto-trading/config \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "min_composite_score": 75.0,
    "max_stocks_to_buy": 3,
    "max_amount_per_stock": 5000.0,
    "stop_loss_percent": -7.0,
    "take_profit_percent": 5.0
  }'
```

**설정 항목 설명**

| 항목 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `enabled` | boolean | false | 자동매매 활성화 여부 |
| `min_composite_score` | float | 70.0 | 최소 종합 점수 (0-100) |
| `max_stocks_to_buy` | int | 5 | 최대 매수 종목 수 (1-20) |
| `max_amount_per_stock` | float | 10000.0 | 종목당 최대 매수 금액 (USD) |
| `stop_loss_percent` | float | -7.0 | 손절 기준 (%) - 음수 |
| `take_profit_percent` | float | 5.0 | 익절 기준 (%) - 양수 |
| `use_sentiment` | boolean | true | 감정 분석 사용 여부 |
| `min_sentiment_score` | float | 0.15 | 최소 감정 점수 (-1 ~ 1) |
| `order_type` | string | "00" | 주문 구분 (00: 지정가) |

---

## 자동 매수

### 1. 매수 추천 종목 조회

**요청**
```bash
curl -X GET http://localhost:8000/auto-trading/candidates/buy
```

**응답**
```json
{
  "success": true,
  "message": "3개의 매수 추천 종목을 찾았습니다",
  "candidates": [
    {
      "ticker": "NVDA",
      "stock_name": "엔비디아",
      "composite_score": 87.5,
      "accuracy": 85.2,
      "rise_probability": 8.5,
      "last_price": 450.00,
      "predicted_price": 485.00,
      "sentiment_score": 0.35,
      "golden_cross": true,
      "rsi": 45.2,
      "macd_buy_signal": true
    }
  ]
}
```

### 2. 자동 매수 실행

#### Dry Run (테스트 모드)

실제 주문 없이 시뮬레이션만 수행합니다.

**요청**
```bash
curl -X POST http://localhost:8000/auto-trading/execute/buy \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'
```

**응답**
```json
{
  "success": true,
  "message": "3개 종목 주문 완료",
  "orders": [
    {
      "ticker": "NVDA",
      "stock_name": "엔비디아",
      "price": 450.00,
      "quantity": 10,
      "estimated_amount": 4500.00,
      "composite_score": 87.5,
      "status": "dry_run"
    }
  ]
}
```

#### 실제 주문 실행

**요청**
```bash
curl -X POST http://localhost:8000/auto-trading/execute/buy \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'
```

**주의사항**
- 자동매매가 활성화(`enabled: true`)되어 있어야 합니다
- 이미 보유 중인 종목은 자동으로 스킵됩니다
- API Rate Limit을 고려하여 순차적으로 주문합니다

---

## 자동 매도

### 1. 매도 대상 종목 조회

**요청**
```bash
curl -X GET http://localhost:8000/auto-trading/candidates/sell
```

**응답**
```json
{
  "success": true,
  "message": "2개의 매도 대상 종목을 식별했습니다",
  "candidates": [
    {
      "ticker": "TSLA",
      "stock_name": "테슬라",
      "purchase_price": 200.00,
      "current_price": 185.00,
      "price_change_percent": -7.5,
      "quantity": 5,
      "sell_reasons": [
        "손절 조건 충족: 구매가 대비 -7.50% 하락"
      ]
    }
  ]
}
```

### 2. 자동 매도 실행

#### Dry Run (테스트 모드)

**요청**
```bash
curl -X POST http://localhost:8000/auto-trading/execute/sell \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'
```

#### 실제 주문 실행

**요청**
```bash
curl -X POST http://localhost:8000/auto-trading/execute/sell \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'
```

### 매도 조건

| 조건 | 설명 |
|------|------|
| **익절** | 구매가 대비 +5% 이상 상승 (설정 가능) |
| **손절** | 구매가 대비 -7% 이하 하락 (설정 가능) |
| **기술적 매도** | 기술적 지표 매도 신호 3개 이상 |
| **감정 매도** | 부정적 감정 점수 + 기술적 매도 신호 2개 이상 |

---

## 상태 조회

### 1. 전체 상태 조회

**요청**
```bash
curl -X GET http://localhost:8000/auto-trading/status
```

**응답**
```json
{
  "success": true,
  "status": {
    "config": {
      "enabled": true,
      "min_composite_score": 75.0
    },
    "holdings": {
      "count": 5,
      "total_value": 50000.00,
      "items": [...]
    },
    "candidates": {
      "buy": {
        "count": 3,
        "items": [...]
      },
      "sell": {
        "count": 2,
        "items": [...]
      }
    },
    "recent_orders": [...]
  }
}
```

### 2. 주문 내역 조회

**요청**
```bash
curl -X GET "http://localhost:8000/auto-trading/logs?days=7"
```

**파라미터**
- `days`: 조회 기간 (1-90일, 기본값: 7일)

**응답**
```json
{
  "success": true,
  "message": "최근 7일간 15개의 주문 내역",
  "logs": [
    {
      "order_type": "buy",
      "ticker": "NVDA",
      "stock_name": "엔비디아",
      "price": 450.00,
      "quantity": 10,
      "status": "success",
      "created_at": "2025-12-03T10:30:00Z"
    }
  ]
}
```

---

## 사용 예시

### Python 클라이언트

```python
import requests

BASE_URL = "http://localhost:8000/auto-trading"

# 1. 자동매매 설정
config = {
    "enabled": True,
    "min_composite_score": 75.0,
    "max_stocks_to_buy": 3,
    "max_amount_per_stock": 5000.0
}

response = requests.put(f"{BASE_URL}/config", json=config)
print(response.json())

# 2. 매수 추천 종목 확인
response = requests.get(f"{BASE_URL}/candidates/buy")
candidates = response.json()["candidates"]
print(f"매수 추천: {len(candidates)}개 종목")

# 3. Dry Run으로 테스트
response = requests.post(
    f"{BASE_URL}/execute/buy",
    json={"dry_run": True}
)
print(response.json())

# 4. 실제 매수 실행
response = requests.post(
    f"{BASE_URL}/execute/buy",
    json={"dry_run": False}
)
print(response.json())

# 5. 상태 확인
response = requests.get(f"{BASE_URL}/status")
status = response.json()["status"]
print(f"보유 종목: {status['holdings']['count']}개")
print(f"총 평가액: ${status['holdings']['total_value']:,.2f}")
```

### JavaScript/TypeScript 클라이언트

```javascript
const BASE_URL = "http://localhost:8000/auto-trading";

// 1. 자동매매 설정
async function updateConfig() {
  const response = await fetch(`${BASE_URL}/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      enabled: true,
      min_composite_score: 75.0,
      max_stocks_to_buy: 3
    })
  });
  return await response.json();
}

// 2. 매수 실행
async function executeBuy(dryRun = true) {
  const response = await fetch(`${BASE_URL}/execute/buy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dry_run: dryRun })
  });
  return await response.json();
}

// 3. 상태 조회
async function getStatus() {
  const response = await fetch(`${BASE_URL}/status`);
  return await response.json();
}

// 사용
updateConfig().then(console.log);
executeBuy(true).then(console.log);
getStatus().then(console.log);
```

### cURL 스크립트

```bash
#!/bin/bash

# 자동매매 활성화
curl -X PUT http://localhost:8000/auto-trading/config \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "min_composite_score": 75.0}'

# Dry Run으로 테스트
curl -X POST http://localhost:8000/auto-trading/execute/buy \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'

# 매도 대상 확인
curl -X GET http://localhost:8000/auto-trading/candidates/sell

# 자동 매도 실행
curl -X POST http://localhost:8000/auto-trading/execute/sell \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'

# 상태 확인
curl -X GET http://localhost:8000/auto-trading/status
```

---

## 🎯 실전 활용 시나리오

### 시나리오 1: 보수적 자동매매

```json
{
  "enabled": true,
  "min_composite_score": 85.0,
  "max_stocks_to_buy": 2,
  "max_amount_per_stock": 3000.0,
  "stop_loss_percent": -5.0,
  "take_profit_percent": 7.0,
  "use_sentiment": true,
  "min_sentiment_score": 0.25
}
```

**특징:**
- 높은 종합 점수 요구 (85점 이상)
- 소수 종목 집중 투자 (최대 2종목)
- 빠른 손절 (-5%), 느린 익절 (+7%)
- 감정 분석 중시 (0.25 이상)

### 시나리오 2: 공격적 자동매매

```json
{
  "enabled": true,
  "min_composite_score": 70.0,
  "max_stocks_to_buy": 10,
  "max_amount_per_stock": 2000.0,
  "stop_loss_percent": -10.0,
  "take_profit_percent": 3.0,
  "use_sentiment": false,
  "min_sentiment_score": 0.0
}
```

**특징:**
- 낮은 종합 점수 허용 (70점 이상)
- 다수 종목 분산 투자 (최대 10종목)
- 느린 손절 (-10%), 빠른 익절 (+3%)
- 감정 분석 미사용

### 시나리오 3: 균형잡힌 자동매매

```json
{
  "enabled": true,
  "min_composite_score": 75.0,
  "max_stocks_to_buy": 5,
  "max_amount_per_stock": 5000.0,
  "stop_loss_percent": -7.0,
  "take_profit_percent": 5.0,
  "use_sentiment": true,
  "min_sentiment_score": 0.15
}
```

**특징:**
- 중간 수준 종합 점수 (75점 이상)
- 적정 분산 투자 (최대 5종목)
- 균형잡힌 손익 기준 (-7% / +5%)
- 감정 분석 사용 (0.15 이상)

---

## ⚠️ 주의사항

1. **자동매매 활성화 확인**
   - `enabled: true`로 설정되어 있어야 실제 주문이 실행됩니다
   - 처음에는 `dry_run: true`로 테스트를 권장합니다

2. **API Rate Limit**
   - 한국투자증권 API는 Rate Limit이 있습니다
   - 자동매매 시스템이 자동으로 대기 시간을 추가합니다

3. **중복 매수 방지**
   - 이미 보유 중인 종목은 자동으로 스킵됩니다
   - 포트폴리오 집중도를 관리하세요

4. **손익 기준 설정**
   - 손절 기준은 음수 값으로 입력 (예: -7.0)
   - 익절 기준은 양수 값으로 입력 (예: 5.0)

5. **백테스팅**
   - 실전 투자 전 과거 데이터로 검증하세요
   - 백테스팅 기능은 현재 개발 중입니다

---

## 📊 데이터 흐름

```
┌─────────────────────────────┐
│  매수 추천 시스템            │
│  - 주가 예측 (AI)           │
│  - 기술적 지표              │
│  - 감정 분석                │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  자동매매 설정 확인          │
│  - 최소 종합 점수           │
│  - 최대 매수 종목 수        │
│  - 감정 점수 기준           │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  매수 후보 필터링            │
│  - 종합 점수 정렬           │
│  - 보유 종목 중복 제거      │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  주문 실행                   │
│  - 현재가 조회              │
│  - 매수 수량 계산           │
│  - API 주문 전송            │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  주문 기록 저장              │
│  - auto_trading_logs        │
└─────────────────────────────┘
```

---

## 📞 문의 및 지원

자동매매 API 관련 문의사항이나 개선 제안이 있으시면 이슈를 등록해주세요.

**관련 문서:**
- [매수_쿼리_가이드.md](./매수_쿼리_가이드.md) - 매수 추천 로직 상세 설명
- [API 문서](http://localhost:8000/docs) - FastAPI 자동 생성 문서

