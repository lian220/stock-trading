# Stock Trading 프로젝트 규칙

> **⚠️ Agent 참조 알림**: 이 가이드를 참조하거나 사용할 때는 반드시 사용자에게 "프로젝트 규칙(rules.md)을 참조하여 작업을 진행합니다"라고 알려주세요.
> 
> 이 파일은 프로젝트의 상세 규칙 및 가이드라인을 제공합니다.
> 핵심 규칙은 프로젝트 루트의 `.cursorrules` 파일을 참고하세요.

## 📋 목차
- [프로젝트 개요](#프로젝트-개요)
- [아키텍처 패턴](#아키텍처-패턴)
- [개발 가이드라인](#개발-가이드라인)
- [데이터베이스 규칙](#데이터베이스-규칙)
- [참고 문서](#참고-문서)

> 📌 **핵심 규칙**: 프로젝트 루트의 [`.cursorrules`](../.cursorrules) 파일 참고
> 📌 **프로젝트 공통 규칙**: [PROJECT_RULES.md](../PROJECT_RULES.md) 참고
> 📌 **커밋 규칙**: [conventions/COMMIT_CONVENTION.md](./conventions/COMMIT_CONVENTION.md)

---

## 프로젝트 개요

한국투자증권 API 기반 미국 주식 자동매매 시스템. AI 주가 예측, 기술적 지표 분석, 뉴스 감정 분석을 통합한 FastAPI 서버.

### 기술 스택
- **언어**: Python 3.9+
- **프레임워크**: FastAPI
- **데이터베이스**: MongoDB (주), Supabase PostgreSQL (레거시 호환)
- **인프라**: Docker, GCP (Vertex AI, Colab)

---

## 아키텍처 패턴

### Clean Architecture 구조

프로젝트는 Clean Architecture 패턴을 따릅니다:

```
app/
├── domain/              # 도메인 계층 (의존성 없음)
│   ├── entities/        # 엔티티 정의
│   └── repositories/    # Repository 인터페이스
├── application/         # 애플리케이션 계층
│   ├── use_cases/      # Use Cases (비즈니스 로직)
│   └── dependencies.py # 의존성 주입 설정
├── infrastructure/      # 인프라 계층
│   ├── database/       # DB 클라이언트 (MongoDB, Supabase)
│   └── repositories/   # Repository 구현체
└── api/                # 프레젠테이션 계층
    └── routes/         # FastAPI 라우터
```

### 레이어 구조

#### 1. Domain Layer (도메인 계층)
**위치**: `app/domain/`
- **entities/**: 도메인 엔티티 정의 (의존성 없음)
- **repositories/**: Repository 인터페이스 정의

#### 2. Application Layer (애플리케이션 계층)
**위치**: `app/application/`
- **use_cases/**: 비즈니스 로직 구현
- **dependencies.py**: Repository 팩토리 함수 제공

#### 3. Infrastructure Layer (인프라 계층)
**위치**: `app/infrastructure/`
- **database/**: MongoDB, Supabase 클라이언트
- **repositories/**: Repository 인터페이스 구현체

#### 4. Presentation Layer (프레젠테이션 계층)
**위치**: `app/api/`
- **routes/**: FastAPI 라우터 정의
- **api.py**: 모든 라우터 중앙 등록

---

## 개발 가이드라인

### 개발 워크플로우

1. **도메인 정의**: `domain/entities/`에 엔티티 정의
2. **Repository 인터페이스**: `domain/repositories/`에 인터페이스 정의
3. **Repository 구현**: `infrastructure/repositories/`에 구현
4. **Use Case 구현**: `application/use_cases/`에 비즈니스 로직 구현
5. **API 라우터**: `api/routes/`에 엔드포인트 정의
6. **의존성 주입**: `application/dependencies.py`에서 Repository 팩토리 함수 제공

### 새 기능 추가 시

1. 도메인 엔티티 정의 (`domain/entities/`)
2. Repository 인터페이스 정의 (`domain/repositories/`)
3. Repository 구현 (`infrastructure/repositories/`)
4. Use Case 구현 (`application/use_cases/`)
5. API 라우터 추가 (`api/routes/`)
6. `api/api.py`에 라우터 등록

### 의존성 주입

`app/application/dependencies.py`에서 Repository 팩토리 함수 제공:

```python
from app.application.dependencies import get_stock_repository
repository = get_stock_repository()  # MongoDB Repository 반환
```

**⚠️ 중요**: Repository 팩토리 함수는 조회 시 MongoDB 구현체를 반환해야 합니다.

### 환경변수 접근

모든 환경변수는 `app/core/config.py`의 `settings` 객체를 통해서만 접근:

```python
from app.core.config import settings
url = settings.get_mongodb_url()  # ✅
# os.getenv() 직접 사용 금지 ❌
```

---

## 데이터베이스 규칙

### ⚠️ CRITICAL: 데이터 조회 규칙

- **모든 데이터 조회는 MongoDB에서 수행해야 합니다**
- Supabase는 저장용으로만 사용 (레거시 호환성)
- 새로운 조회 기능은 반드시 MongoDB Repository 사용
- `get_stock_repository()` 또는 `get_economic_repository()` 사용 시 MongoDB 구현체가 반환되도록 확인

### MongoDB 컬렉션 네이밍

MongoDB 컬렉션명과 Supabase 테이블명이 다를 수 있음. 반드시 실제 저장하는 코드 확인 필요:

| 용도 | MongoDB 컬렉션 | Supabase 테이블 | 비고 |
|------|---------------|-----------------|------|
| AI 주가 예측 결과 | `stock_analysis` | `stock_analysis_results` | 필드 구조도 다름 |
| 기술적 지표 추천 | `stock_recommendations` | `stock_recommendations` | 동일 |
| 감정 분석 | `sentiment_analysis` | `ticker_sentiment_analysis` | 다름 |
| 일별 통합 데이터 | `daily_stock_data` | - | MongoDB 전용 |
| 주식 마스터 | `stocks` | `stocks` | 동일 |

### 데이터베이스 접근 패턴

```python
# ✅ 올바른 방법
from app.application.dependencies import get_stock_repository
repository = get_stock_repository()  # MongoDB Repository
data = await repository.find_by_ticker("AAPL")

# ❌ 잘못된 방법
# Supabase에서 직접 조회 금지
```

---

## 코드 예시

### Use Case
```python
from app.domain.repositories.stock_repository import StockRepository
from app.application.dependencies import get_stock_repository

class GetStockRecommendationsUseCase:
    def __init__(self):
        self.repository: StockRepository = get_stock_repository()
    
    async def execute(self) -> List[StockRecommendation]:
        return await self.repository.find_recommendations()
```

### API Router
```python
from fastapi import APIRouter, Depends
from app.application.use_cases.get_stock_recommendations import GetStockRecommendationsUseCase

router = APIRouter(prefix="/stocks", tags=["stocks"])

@router.get("/recommendations")
async def get_recommendations(
    use_case: GetStockRecommendationsUseCase = Depends()
):
    return await use_case.execute()
```

---

## 빠른 참조

### 자주 사용하는 경로
- Domain Entities: `app/domain/entities/`
- Repository Interfaces: `app/domain/repositories/`
- Repository Implementations: `app/infrastructure/repositories/`
- Use Cases: `app/application/use_cases/`
- API Routers: `app/api/routes/`

### 자주 사용하는 함수
- `get_stock_repository()`: 주식 Repository 가져오기 (MongoDB)
- `get_economic_repository()`: 경제 데이터 Repository 가져오기 (MongoDB)
- `settings.get_mongodb_url()`: MongoDB URL 가져오기

---

## 참고 문서

### 컨벤션
- **핵심 규칙**: [`.cursorrules`](../.cursorrules) - Cursor가 자동으로 읽는 파일
- **프로젝트 공통 규칙**: [PROJECT_RULES.md](../PROJECT_RULES.md) - 프로젝트 전체 규칙
- **커밋 규칙**: [conventions/COMMIT_CONVENTION.md](./conventions/COMMIT_CONVENTION.md) - 커밋 메시지 컨벤션

### 프로젝트 문서
- **README**: [../README.md](../README.md)
- **Clean Architecture 가이드**: [../app/README_CLEAN_ARCHITECTURE.md](../app/README_CLEAN_ARCHITECTURE.md)
