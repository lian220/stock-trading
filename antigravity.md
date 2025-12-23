# Antigravity 프로젝트 규칙

> **⚠️ 중요**: 이 파일은 Antigravity 전용 설정입니다.
> 
> **공통 규칙**: 프로젝트 루트의 `AGENTS.md` 파일을 참조하세요. 이 파일은 모든 AI 에이전트 툴이 공통으로 읽습니다.

## 공통 규칙 파일 참조

**⚠️ 필수**: 다음 공통 규칙 파일들을 반드시 참조하세요:

- **`AGENTS.md`** (프로젝트 루트) - 모든 AI 에이전트 툴이 공통으로 읽는 규칙
- **`.ai/PROJECT_RULES.md`** - 프로젝트 공통 규칙 및 체크리스트
- **`.ai/rules.md`** - 프로젝트 상세 규칙 및 가이드라인
- **`.ai/conventions/COMMIT_CONVENTION.md`** - 커밋 메시지 컨벤션
- **`.ai/conventions/CODING_CONVENTION.md`** - Python 코딩 스타일 가이드

## 프로젝트 개요

한국투자증권 API 기반 미국 주식 자동매매 시스템. AI 주가 예측, 기술적 지표 분석, 뉴스 감정 분석을 통합한 FastAPI 서버.

### 기술 스택

- **언어**: Python 3.9+
- **프레임워크**: FastAPI
- **데이터베이스**: MongoDB (주), Supabase PostgreSQL (레거시 호환)
- **인프라**: Docker, GCP (Vertex AI, Colab)

### 빌드 및 실행 명령

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

## 언어 설정

- **언어**: 한국어
- **커밋 메시지**: 한글 (Conventional Commit 규칙 준수)

## 주요 아키텍처

Clean Architecture 패턴 사용:
- **domain/**: 엔티티, Repository 인터페이스 (의존성 없음)
- **application/**: Use Cases, 비즈니스 로직, DI 설정
- **infrastructure/**: DB 클라이언트 (Supabase/MongoDB), Repository 구현체
- **presentation/api/**: FastAPI 라우터

## 데이터베이스 규칙

**⚠️ CRITICAL: 데이터 조회 규칙**
- **모든 데이터 조회는 MongoDB에서 수행해야 합니다**
- Supabase는 저장용으로만 사용 (레거시 호환성)
- 새로운 조회 기능은 반드시 MongoDB Repository 사용

## 보안 규칙

**🔒 ABSOLUTELY NO SECRETS IN CODE OR COMMITS**
- **NEVER** commit `.env` files, API keys, tokens, credentials, or private keys
- Use environment variables for ALL sensitive data
- 모든 환경변수는 `app/core/config.py`의 `settings` 객체를 통해서만 접근

## 커밋 메시지 규칙

**⚠️ 커밋 전 필수**: 코드를 커밋하기 전에 반드시 실행 테스트를 수행해야 합니다.

커밋 메시지는 `.ai/conventions/COMMIT_CONVENTION.md` 파일의 규칙을 따라야 합니다:
- 형식: `<type>: <subject>`
- Type: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`
- 한글로 작성, 50자 이내

## 참고

상세 규칙은 `.ai/` 디렉토리의 파일들을 참조하세요.

