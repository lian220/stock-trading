# Clean Architecture 구조

이 프로젝트는 Clean Architecture 패턴을 따릅니다.

## 디렉토리 구조

```
app/
├── domain/                  # Domain Layer (핵심 비즈니스 로직)
│   ├── entities/           # 도메인 엔티티 (순수 Python 객체)
│   └── repositories/       # Repository 인터페이스 (추상화)
│
├── application/            # Application Layer (Use Cases)
│   ├── use_cases/         # 비즈니스 로직 실행
│   └── dependencies.py    # Dependency Injection 설정
│
├── infrastructure/         # Infrastructure Layer (외부 의존성)
│   ├── database/          # DB 연결 관리
│   │   └── mongodb_client.py
│   └── repositories/      # Repository 구현체
│       └── mongodb_*.py
│
├── presentation/          # Presentation Layer (API)
│   └── api/              # FastAPI 라우터
│
└── core/                 # 공통 설정
    └── config.py         # 환경변수 설정 (통일된 패턴)
```

## 레이어 설명

### 1. Domain Layer (`app/domain/`)
- **의존성**: 없음 (가장 내부 레이어)
- **내용**: 엔티티와 Repository 인터페이스
- **예시**: `Stock`, `EconomicData` 엔티티

### 2. Application Layer (`app/application/`)
- **의존성**: Domain Layer만 의존
- **내용**: Use Cases와 비즈니스 로직
- **예시**: `EconomicDataUseCase`, `StockUseCase`

### 3. Infrastructure Layer (`app/infrastructure/`)
- **의존성**: Domain Layer만 의존 (Repository 인터페이스 구현)
- **내용**: DB 연결, 외부 API, Repository 구현체
- **예시**: `MongoDBStockRepository`, `MongodbEconomicRepository`

### 4. Presentation Layer (`app/presentation/` 또는 `app/api/`)
- **의존성**: Application Layer
- **내용**: FastAPI 라우터, 요청/응답 처리
- **예시**: API 엔드포인트

## DB 연결 관리

### MongoDB
- 설정: `app/infrastructure/database/mongodb_client.py`
- Repository: `app/infrastructure/repositories/mongodb_*.py`

설정은 `app/core/config.py`의 `USE_MONGODB` 플래그로 제어합니다.

## 환경변수 통일

모든 환경변수는 `app/core/config.py`를 통해서만 접근합니다.

```python
from app.core.config import settings

# ✅ 올바른 방법
url = settings.get_mongodb_url()
user = settings.get_mongodb_user()

# ❌ 잘못된 방법 (직접 os.getenv 사용 금지)
import os
url = os.getenv("MONGODB_URL")  # 사용하지 마세요!
```

## Dependency Injection

FastAPI의 `Depends`를 사용하여 Repository를 주입합니다:

```python
from fastapi import Depends
from app.application.dependencies import get_stock_repository
from app.application.use_cases.stock_use_case import StockUseCase

@router.get("/stocks")
async def get_stocks(
    repository = Depends(get_stock_repository)
):
    use_case = StockUseCase(repository)
    stocks = await use_case.get_all_active_stocks()
    return stocks
```

## 레거시 코드 호환성

기존 코드와의 호환성을 위해 레거시 래퍼를 제공합니다:

- `app/db/mongodb.py` → `app/infrastructure/database/mongodb_client.py`를 사용

새로운 코드는 Infrastructure Layer를 직접 사용하는 것을 권장합니다.

## 마이그레이션 가이드

기존 서비스를 Clean Architecture로 마이그레이션하는 방법:

1. **Repository 인터페이스 확인**: `app/domain/repositories/`에서 필요한 인터페이스 확인
2. **Repository 구현 확인**: `app/infrastructure/repositories/`에서 구현체 확인
3. **Use Case 생성**: `app/application/use_cases/`에 비즈니스 로직 이동
4. **API 업데이트**: `Depends`를 사용하여 Use Case 주입

예시:

```python
# 기존 코드
from app.db.mongodb import get_db
db = get_db()
stocks = list(db.stocks.find({"is_active": True}))

# 새로운 코드
from app.application.use_cases.stock_use_case import StockUseCase
from app.application.dependencies import get_stock_repository

use_case = StockUseCase(await get_stock_repository())
stocks = await use_case.get_all_active_stocks()
```
