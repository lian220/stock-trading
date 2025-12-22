# Stock Trading - Cursor IDE 설정

이 디렉토리는 Cursor IDE가 프로젝트의 구조와 규칙을 이해하도록 돕는 설정 파일들을 포함합니다.

## 디렉토리 구조

```
.cursor/
├── README.md                    # 이 파일
├── rules.md                     # 상세 규칙 및 가이드라인
├── conventions/                 # 프로젝트 컨벤션
│   ├── COMMIT_CONVENTION.md    # 커밋 메시지 컨벤션
│   └── CODING_CONVENTION.md    # 코딩 컨벤션
├── .github/
│   └── pull_request_template.md # PR 작성 템플릿
└── guides/                      # Agent 가이드
    ├── TEST_GUIDE.md           # 테스트 코드 생성 가이드
    ├── REFACTORING_GUIDE.md    # 리팩토링 가이드
    └── PROMPT_GUIDE.md         # 프롬프트 생성 가이드
```

## 파일 설명

### 핵심 파일
- **`.cursorrules`** (프로젝트 루트): 핵심 규칙 - Cursor가 자동으로 읽는 파일 (토큰 효율적)

### 상세 규칙
- **`rules.md`**: 전체 규칙 및 가이드라인 (Python/FastAPI 기준)
  - Clean Architecture 구조
  - 데이터베이스 규칙 (MongoDB 우선)
  - 개발 가이드라인

### 컨벤션
- **`conventions/COMMIT_CONVENTION.md`**: 커밋 메시지 컨벤션
  - Conventional Commit 형식
  - 한글 작성 규칙
  - PR 작성 규칙
- **`conventions/CODING_CONVENTION.md`**: 코딩 컨벤션
  - Python 스타일 가이드
  - 네이밍 규칙
  - 코드 구조 규칙

### Agent 가이드 (`guides/`)
- **`TEST_GUIDE.md`**: 테스트 코드 생성 가이드
  - 테스트 작성 규칙 및 체크리스트
- **`REFACTORING_GUIDE.md`**: 리팩토링 가이드
  - 리팩토링 원칙, 패턴, 체크리스트
- **`PROMPT_GUIDE.md`**: 프롬프트 생성 가이드
  - 요구사항을 구조화된 프롬프트로 변환하는 방법

## 사용 방법

1. **`.cursorrules`** 파일이 Cursor IDE에서 자동으로 읽혀집니다
2. 상세 내용이 필요할 때는 각 디렉토리의 문서 파일을 참고하세요

## 빠른 검색

### 핵심 규칙
- 프로젝트 루트의 [`.cursorrules`](../.cursorrules) 파일 참고
- 프로젝트 공통 규칙: [PROJECT_RULES.md](../PROJECT_RULES.md)

### 컨벤션
- 전체 규칙: [rules.md](./rules.md)
- 커밋 규칙: [conventions/COMMIT_CONVENTION.md](./conventions/COMMIT_CONVENTION.md)
- 코딩 컨벤션: [conventions/CODING_CONVENTION.md](./conventions/CODING_CONVENTION.md)

### Agent 가이드
- 테스트 생성: [guides/TEST_GUIDE.md](./guides/TEST_GUIDE.md)
- 리팩토링: [guides/REFACTORING_GUIDE.md](./guides/REFACTORING_GUIDE.md)
- 프롬프트 생성: [guides/PROMPT_GUIDE.md](./guides/PROMPT_GUIDE.md)

## 프로젝트 개요

**Stock Trading**은 한국투자증권 API 기반 미국 주식 자동매매 시스템입니다.
- AI 주가 예측
- 기술적 지표 분석
- 뉴스 감정 분석
- FastAPI 기반 REST API

### 기술 스택
- Python 3.9+
- FastAPI
- MongoDB (주), Supabase PostgreSQL (레거시)
- Docker, GCP (Vertex AI, Colab)
