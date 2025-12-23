# 프로젝트 지침

> **⚠️ 공통 규칙**: 이 파일은 모든 AI 에이전트 툴(커서, 클로드, 안티그래비티 등)이 공통으로 참조하는 규칙 파일입니다.
> 
> **상세 규칙**: `.ai/rules.md` 및 `.ai/PROJECT_RULES.md` 참조

## 프로젝트 개요

한국투자증권 API 기반 미국 주식 자동매매 시스템. AI 주가 예측, 기술적 지표 분석, 뉴스 감정 분석을 통합한 FastAPI 서버.

### 기술 스택
- **언어**: Python 3.9+
- **프레임워크**: FastAPI
- **데이터베이스**: MongoDB (주), Supabase PostgreSQL (레거시 호환)
- **인프라**: Docker, GCP (Vertex AI, Colab)

### 빌드 및 실행
```bash
# 로컬 실행
python scripts/run/run.py

# Docker 실행
docker-compose up --build -d

# 개발 모드 (auto-reload)
APP_ENV=development python scripts/run/run.py
```

## ⚠️ 핵심 규칙

### 1. 데이터베이스 규칙 (CRITICAL)
- **모든 데이터 조회는 MongoDB에서 수행** (Supabase는 저장용만)
- `get_stock_repository()` 또는 `get_economic_repository()` 사용 시 MongoDB 구현체 반환 확인
- Supabase에서 직접 조회 금지

### 2. 아키텍처
- **Clean Architecture 패턴 준수**
- 레이어 구조: `domain/` → `application/` → `infrastructure/` → `api/`
- 의존성 방향: Presentation → Application → Domain ← Infrastructure

### 3. 환경변수 접근
- 모든 환경변수는 `app/core/config.py`의 `settings` 객체로만 접근
- `os.getenv()` 직접 사용 금지

### 4. 보안
- **절대 비밀 정보를 코드나 커밋에 포함하지 않음**
- `.env` 파일, API 키, 토큰 등은 환경변수로만 관리

### 5. 커밋 메시지
- 형식: `<type>: <subject>` (한글)
- Type: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`
- 커밋 전 반드시 실행 테스트 수행

### 6. 코드 스타일
- PEP 8 준수
- Type Hints 사용 권장
- Docstring 작성 (Google 스타일)

## 개발 워크플로우

1. 도메인 엔티티 정의 (`domain/entities/`)
2. Repository 인터페이스 정의 (`domain/repositories/`)
3. Repository 구현 (`infrastructure/repositories/`)
4. Use Case 구현 (`application/use_cases/`)
5. API 라우터 추가 (`api/routes/`)
6. `api/api.py`에 라우터 등록

## 데이터베이스 접근 패턴

```python
# ✅ 올바른 방법
from app.application.dependencies import get_stock_repository
repository = get_stock_repository()  # MongoDB Repository
data = await repository.find_by_ticker("AAPL")

# ❌ 잘못된 방법
# Supabase에서 직접 조회 금지
```

## MongoDB 컬렉션 네이밍

| 용도 | MongoDB 컬렉션 | Supabase 테이블 |
|------|---------------|-----------------|
| AI 주가 예측 결과 | `stock_analysis` | `stock_analysis_results` |
| 기술적 지표 추천 | `stock_recommendations` | `stock_recommendations` |
| 감정 분석 | `sentiment_analysis` | `ticker_sentiment_analysis` |
| 일별 통합 데이터 | `daily_stock_data` | - |
| 주식 마스터 | `stocks` | `stocks` |

## 참고 문서

- **상세 규칙**: `.ai/rules.md`
- **프로젝트 공통 규칙**: `.ai/PROJECT_RULES.md`
- **커밋 컨벤션**: `.ai/conventions/COMMIT_CONVENTION.md`
- **코딩 컨벤션**: `.ai/conventions/CODING_CONVENTION.md`

