# 프로젝트 GPS (영구 가이드라인)

이 명령어는 프로젝트의 영구적인 GPS 역할을 합니다.

**⚠️ 중요**: 모든 프로젝트 규칙은 `PROJECT_RULES.md` 파일에 정의되어 있습니다.

## 📍 필수 참조 파일

- **`PROJECT_RULES.md`** - 모든 프로젝트 공통 규칙 (기본 참조)
- `.cursorrules` - Cursor 전용 커밋 메시지 규칙

## ⚠️ 핵심 규칙 요약

1. **데이터 조회는 모두 MongoDB에서 수행** (Supabase는 저장용만)
2. **Clean Architecture 패턴 준수**
3. **환경변수는 `settings` 객체로만 접근**
4. **커밋 메시지는 한글로 작성**

자세한 내용은 `PROJECT_RULES.md` 파일을 참조하세요.
