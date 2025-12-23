# Cursor Rules 가이드

이 디렉토리는 Cursor IDE에서 사용하는 프로젝트 규칙 파일들을 포함합니다.

## 규칙 파일 목록

### 필수 규칙 (alwaysApply: true)

- **project-overview.mdc**: 프로젝트 개요 및 기술 스택
- **security.mdc**: 보안 규칙 및 비밀 정보 관리

### 선택적 규칙 (alwaysApply: false)

- **architecture.mdc**: Clean Architecture 패턴 및 레이어 구조
- **api-routes.mdc**: API 라우터 구조 및 등록 규칙
- **coding-convention.mdc**: Python 코딩 컨벤션 및 스타일 가이드
- **commit-convention.mdc**: 커밋 메시지 컨벤션 및 커밋 전 필수 체크사항
- **database.mdc**: 데이터베이스 규칙 및 MongoDB/Supabase 사용 가이드
- **models-schemas.mdc**: 모델과 스키마 분리 규칙 및 사용 가이드
- **services.mdc**: 서비스 레이어 규칙 및 비즈니스 로직 작성 가이드
- **error-handling.mdc**: 에러 처리 규칙 및 예외 처리 가이드
- **logging.mdc**: 로깅 규칙 및 로그 작성 가이드
- **scheduler.mdc**: 스케줄러 규칙 및 스케줄링 작업 가이드
- **testing.mdc**: 테스트 규칙 및 테스트 작성 가이드

## 규칙 파일 형식

각 규칙 파일은 `.mdc` 확장자를 사용하며, YAML 프론트매터와 마크다운 본문으로 구성됩니다:

```markdown
---
description: 규칙 설명
globs:
  - "app/**/*.py"
alwaysApply: false
---

# 규칙 제목

규칙 내용...
```

### 프론트매터 필드

- **description**: 규칙 파일에 대한 간단한 설명
- **globs**: 이 규칙이 적용될 파일 패턴 (선택사항)
- **alwaysApply**: 항상 적용 여부 (true/false)

## 규칙 파일 사용 방법

### 1. 자동 적용

`alwaysApply: true`로 설정된 규칙은 항상 자동으로 적용됩니다.

### 2. 파일 패턴 기반 적용

`globs` 필드에 파일 패턴을 지정하면 해당 파일을 편집할 때 규칙이 자동으로 적용됩니다.

예:
```yaml
globs:
  - "app/api/**/*.py"
```
→ `app/api/` 디렉토리의 모든 Python 파일에 자동 적용

### 3. 수동 참조

규칙 파일은 Cursor AI가 코드를 생성하거나 수정할 때 자동으로 참조됩니다.

## 규칙 파일 작성 가이드

### 1. 명확한 설명

각 규칙 파일은 명확하고 구체적인 설명을 포함해야 합니다.

### 2. 코드 예시

규칙을 설명할 때는 실제 코드 예시를 포함하는 것이 좋습니다:

```python
# ✅ 올바른 방법
from app.core.config import settings
api_key = settings.kis_api_key

# ❌ 잘못된 방법
api_key = "sk-1234567890abcdef"
```

### 3. 파일 패턴 지정

관련 파일에만 규칙이 적용되도록 `globs` 필드를 사용합니다:

```yaml
globs:
  - "app/services/**/*.py"
  - "app/api/routes/**/*.py"
```

### 4. 항상 적용 규칙

중요한 규칙은 `alwaysApply: true`로 설정:

```yaml
alwaysApply: true
```

## 규칙 파일 업데이트

규칙 파일을 수정할 때는:

1. **명확성**: 규칙이 명확하고 이해하기 쉬운지 확인
2. **일관성**: 다른 규칙 파일과 일관성 유지
3. **예시**: 실제 코드 예시 포함
4. **테스트**: 규칙이 올바르게 작동하는지 확인

## 공통 규칙 참조

**⚠️ 중요**: 모든 AI 에이전트 툴(커서, 클로드, 안티그래비티 등)은 다음 공통 규칙 파일을 참조해야 합니다:

- **상세 규칙**: `.ai/rules.md` - 프로젝트 상세 규칙 및 가이드라인
- **프로젝트 공통 규칙**: `.ai/PROJECT_RULES.md` - 프로젝트 공통 규칙 및 체크리스트
- **커밋 컨벤션**: `.ai/conventions/COMMIT_CONVENTION.md` - 커밋 메시지 규칙
- **코딩 컨벤션**: `.ai/conventions/CODING_CONVENTION.md` - Python 코딩 스타일 가이드

## 문제 해결

### 규칙이 적용되지 않을 때

1. 파일 패턴 확인: `globs` 필드의 패턴이 올바른지 확인
2. 파일 경로 확인: 편집 중인 파일이 패턴과 일치하는지 확인
3. Cursor 재시작: 규칙 파일을 수정한 후 Cursor를 재시작

### 규칙 충돌

여러 규칙 파일이 충돌하는 경우:

1. 더 구체적인 규칙이 우선 적용
2. `alwaysApply: true` 규칙이 우선 적용
3. 필요시 규칙 파일을 수정하여 충돌 해결

## 참고 자료

- [Cursor Rules 문서](https://cursor.sh/docs)
- 프로젝트 공통 규칙: `.ai/PROJECT_RULES.md`
- 프로젝트 상세 규칙: `.ai/rules.md`

