# Claude 프로젝트 가이드

이 파일은 Claude Code를 위한 프로젝트 가이드입니다.

## 📍 기본 참조 파일

- **`AGENTS.md`** (프로젝트 루트) - 모든 AI 에이전트 툴이 공통으로 읽는 규칙 - **자동 참조됨**
- **`.ai/PROJECT_RULES.md`** - 프로젝트 공통 규칙 및 체크리스트
- **`.ai/rules.md`** - 프로젝트 상세 규칙 및 가이드라인
- **`.ai/guides/PROCESS.md`** - 개발 프로세스 핵심 가이드

## ⚠️ 핵심 규칙 요약

1. **데이터 조회는 모두 MongoDB에서 수행** (Supabase는 저장용만)
2. **Clean Architecture 패턴 준수**
3. **환경변수는 `app/core/config.py`의 `settings` 객체로만 접근**
4. **커밋 메시지는 한글로 작성** (Conventional Commits)
5. **기능 추가 전 기존 코드 확인 및 중복 코드 정리**

## 빠른 참조

자세한 내용은 프로젝트 루트의 `AGENTS.md` 파일을 참조하세요.
