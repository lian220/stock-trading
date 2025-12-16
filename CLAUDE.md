# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

한국투자증권 API 기반 미국 주식 자동매매 시스템. AI 주가 예측, 기술적 지표 분석, 뉴스 감정 분석을 통합한 FastAPI 서버.

## Build and Run Commands

```bash
# 로컬 실행
python scripts/run/run.py

# Docker 실행
docker-compose up --build -d

# 개발 모드 (auto-reload)
APP_ENV=development python scripts/run/run.py

# 로그 확인
docker-compose logs -f
```

## Architecture

Clean Architecture 패턴 사용:
- **domain/**: 엔티티, Repository 인터페이스 (의존성 없음)
- **application/**: Use Cases, 비즈니스 로직, DI 설정
- **infrastructure/**: DB 클라이언트 (Supabase/MongoDB), Repository 구현체
- **presentation/api/**: FastAPI 라우터

### Database

두 가지 DB 지원 (설정: `USE_MONGODB` 환경변수):
- **Supabase (PostgreSQL)**: 기본
- **MongoDB**: Atlas 지원, motor(async)/pymongo(sync) 사용

모든 환경변수는 `app/core/config.py`의 `settings` 객체를 통해서만 접근:
```python
from app.core.config import settings
url = settings.get_mongodb_url()  # ✅
# os.getenv() 직접 사용 금지 ❌
```

### MongoDB 컬렉션 네이밍

MongoDB 컬렉션명과 Supabase 테이블명이 다를 수 있음. 반드시 실제 저장하는 코드 확인 필요:

| 용도 | MongoDB 컬렉션 | Supabase 테이블 | 비고 |
|------|---------------|-----------------|------|
| AI 주가 예측 결과 | `stock_analysis` | `stock_analysis_results` | 필드 구조도 다름 |
| 기술적 지표 추천 | `stock_recommendations` | `stock_recommendations` | 동일 |
| 감정 분석 | `sentiment_analysis` | `ticker_sentiment_analysis` | 다름 |
| 일별 통합 데이터 | `daily_stock_data` | - | MongoDB 전용 |
| 주식 마스터 | `stocks` | `stocks` | 동일 |

**MongoDB 필드 구조 예시 (`stock_analysis`):**
```javascript
{
  "date": ISODate(),
  "ticker": "AAPL",
  "stock_name": "애플",
  "metrics": { "accuracy": 85.5, "mae": ..., "mse": ... },
  "predictions": { "rise_probability": 5.2, "last_actual_price": ..., "predicted_future_price": ... },
  "recommendation": "Buy",
  "analysis": "..."
}
```

**Supabase 필드 구조 (`stock_analysis_results`):**
```json
{
  "Stock": "애플",
  "Accuracy (%)": 85.5,
  "Rise Probability (%)": 5.2,
  "Last Actual Price": 150.0,
  "Predicted Future Price": 155.0,
  "Recommendation": "Buy"
}
```

### API 구조

`app/api/api.py`에서 모든 라우터 중앙 등록:
- `/stocks`: 주식 추천, 주식 조회
- `/economic`: 경제 데이터
- `/balance`: 잔액 조회
- `/auto-trading`: 자동매매
- `/colab`: Colab/Vertex AI 연동
- `/gcs`: GCS 업로드

### Dependency Injection

`app/application/dependencies.py`에서 Repository 팩토리 함수 제공:
```python
from app.application.dependencies import get_stock_repository
repository = get_stock_repository()  # MongoDB/Supabase 자동 선택
```

## Commit Message Rules

**반드시 한글로 작성**, Conventional Commits 형식:
```
<type>(<scope>): <한글 subject>

<한글 body>
```

예시:
```
feat(api): 경제 지표 조회 API 추가함
fix(scheduler): 주식 데이터 수집 오류 수정함
refactor(service): 데이터 저장 로직 개선함
```

Type: feat, fix, docs, style, refactor, test, chore, perf, ci, build, revert
Subject: 명령형 어미 ("추가함", "수정함", "개선함"), 마침표 없음, 50자 이내

## Key Files

- `app/main.py`: FastAPI 앱 진입점, lifespan 이벤트로 스케줄러 관리
- `app/core/config.py`: 환경변수 설정 (Settings 클래스)
- `app/utils/scheduler.py`: 매수/매도 스케줄러
- `scripts/run/run.py`: uvicorn 서버 실행 스크립트
