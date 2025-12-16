# Claude 프로젝트 가이드

이 파일은 Claude Code (claude.ai/code)를 위한 프로젝트 가이드입니다.
**Claude CLI는 이 파일을 자동으로 컨텍스트에 포함시킵니다.**

---

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

### 의존성 규칙 (위반 시 Hook 차단)

| 레이어 | 의존 가능 | 의존 불가 |
|--------|----------|----------|
| **domain** | 없음 (순수) | application, infrastructure, presentation |
| **application** | domain | infrastructure, presentation |
| **infrastructure** | domain, application | presentation |
| **presentation** | 모든 레이어 | - |

## Database

### ⚠️ CRITICAL: 데이터 조회 규칙

- **모든 데이터 조회는 MongoDB에서 수행해야 합니다**
- Supabase는 저장용으로만 사용 (레거시 호환성)
- 새로운 조회 기능은 반드시 MongoDB Repository 사용
- `get_stock_repository()` 또는 `get_economic_repository()` 사용 시 MongoDB 구현체가 반환되도록 확인

두 가지 DB 지원 (설정: `USE_MONGODB` 환경변수):
- **Supabase (PostgreSQL)**: 저장용 (레거시 호환)
- **MongoDB**: Atlas 지원, motor(async)/pymongo(sync) 사용, **모든 조회는 여기서 수행**

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

### MongoDB 핵심 컬렉션

| 컬렉션 | 용도 | 주요 인덱스 |
|--------|------|------------|
| `daily_stock_data` | 날짜별 통합 데이터 (대시보드용) | `{ date: 1 }` (unique) |
| `stocks` | 종목 기본 정보 | `{ ticker: 1 }` (unique) |
| `stock_recommendations` | 종목별 추천 시계열 | `{ ticker: 1, date: -1 }` |
| `stock_analysis` | AI 분석 결과 | `{ date: 1, ticker: 1 }` |
| `sentiment_analysis` | 뉴스 감정 분석 | `{ ticker: 1, calculation_date: -1 }` |

## 코드 작성 규칙

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

## API 구조

`app/api/api.py`에서 모든 라우터 중앙 등록:
- `/stocks`: 주식 추천, 주식 조회
- `/economic`: 경제 데이터
- `/balance`: 잔액 조회
- `/auto-trading`: 자동매매
- `/colab`: Colab/Vertex AI 연동
- `/gcs`: GCS 업로드

## Dependency Injection

`app/application/dependencies.py`에서 Repository 팩토리 함수 제공:
```python
from app.application.dependencies import get_stock_repository
repository = get_stock_repository()  # MongoDB Repository 반환 (조회용)
```

**⚠️ 중요**: Repository 팩토리 함수는 조회 시 MongoDB 구현체를 반환해야 합니다.

## Key Files

- `app/main.py`: FastAPI 앱 진입점, lifespan 이벤트로 스케줄러 관리
- `app/core/config.py`: 환경변수 설정 (Settings 클래스)
- `app/utils/scheduler.py`: 매수/매도 스케줄러
- `scripts/run/run.py`: uvicorn 서버 실행 스크립트

## 커밋 메시지 규칙

**모든 커밋 메시지는 한글로 작성해야 합니다.**

### 형식

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

## 규칙 요약 체크리스트

코드 작성/수정 전에 확인:
- [ ] **데이터 조회는 MongoDB에서 수행했는가?** (Supabase 조회 금지)
- [ ] Clean Architecture 계층 구조를 준수했는가?
- [ ] 환경변수는 `settings` 객체로 접근했는가?
- [ ] MongoDB/Supabase 컬렉션명/테이블명을 올바르게 사용했는가?
- [ ] 기존에 유사한 기능이 있는지 검색했는가?
- [ ] 중복된 코드가 있는가? (있다면 통합)
- [ ] 사용되지 않는 함수/변수가 있는가? (있다면 삭제)

## 추가 참조

자세한 개발 프로세스는 `.claude/DEVELOPMENT_PROCESS_GUIDE.md`를 참조하세요.
