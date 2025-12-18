# Claude 프로젝트 가이드

이 파일은 Claude Code를 위한 프로젝트 가이드입니다.

## 📍 기본 참조 파일

- **`.cursorrules`** - 모든 프로젝트 규칙 (아키텍처, 데이터베이스, 커밋 규칙 등) - **자동 참조됨**
- **`.claude/DEVELOPMENT_PROCESS_GUIDE.md`** - 개발 프로세스 핵심 가이드 (빠른 참조용)

## ⚠️ 핵심 규칙 요약

1. **데이터 조회는 모두 MongoDB에서 수행** (Supabase는 저장용만)
2. **Clean Architecture 패턴 준수**
3. **환경변수는 `app/core/config.py`의 `settings` 객체로만 접근**
4. **커밋 메시지는 한글로 작성** (Conventional Commits)
5. **기능 추가 전 기존 코드 확인 및 중복 코드 정리**

## 빠른 참조

자세한 개발 프로세스는 `.claude/DEVELOPMENT_PROCESS_GUIDE.md`를 참조하세요.
