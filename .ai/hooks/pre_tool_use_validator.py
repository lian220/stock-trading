#!/usr/bin/env python3
"""
Claude Code Hook Dispatcher
프로젝트 규칙을 검증하는 PreToolUse 훅
"""
import sys
import json
import re

def main():
    print("🚀 디스패처 실행됨!", file=sys.stderr)

    try:
        # Claude가 stdin을 통해 전달한 JSON 데이터를 읽습니다.
        input_data = sys.stdin.read()
        data = json.loads(input_data)

        tool_name = data.get("tool_name", "")
        tool_input = data.get("tool_input", {})

        # 파일 경로는 tool_input 객체 안에 다양한 형태로 존재할 수 있어, 순차적으로 확인합니다.
        file_path = (
            tool_input.get("path") or
            tool_input.get("file_path") or
            (tool_input.get("args", [None])[0] if tool_input.get("args") else "") or
            ""
        )

        print(f"🔧 Tool: {tool_name}, 📁 File: {file_path}", file=sys.stderr)

        # 규칙 1: 민감한 파일 접근 제어 (.env, credentials)
        sensitive_patterns = [".env", "/credentials"]
        for pattern in sensitive_patterns:
            if pattern in file_path:
                if tool_name in ("Read", "Grep"):
                    print(f"❌ 보안 규칙 위반: {pattern} 파일은 읽을 수 없습니다. 작업이 차단되었습니다.", file=sys.stderr)
                    sys.exit(2)  # 작업 차단

        # 규칙 2: 마이그레이션 파일 수정 제어 (app/db/migrations/ 경로)
        if "app/db/migrations/" in file_path:
            if tool_name in ("Edit", "Write", "MultiEdit"):
                print("❌ 데이터 불변성 규칙 위반: 마이그레이션 파일은 수정할 수 없습니다. 새 마이그레이션 파일을 생성하세요. 작업이 차단되었습니다.", file=sys.stderr)
                sys.exit(2)  # 작업 차단

        # 규칙 3: 서비스 파일 문서화 정책 (Python docstring 필수)
        if "app/services/" in file_path:
            if tool_name in ("Edit", "Write"):
                content = tool_input.get("content") or tool_input.get("new_string") or ""
                # 새 파일 생성(Write) 또는 함수/클래스 추가 시 docstring 확인
                if tool_name == "Write" and content:
                    # 파일에 클래스나 함수가 있는데 docstring이 없는 경우
                    if ("def " in content or "class " in content) and '"""' not in content and "'''" not in content:
                        print("❌ 문서화 규칙 위반: 서비스 파일의 함수/클래스에는 반드시 docstring이 포함되어야 합니다. 작업이 차단되었습니다.", file=sys.stderr)
                        sys.exit(2)  # 작업 차단

        # 규칙 4: Clean Architecture 의존성 규칙 검증
        # domain/ 레이어는 다른 레이어에 의존하면 안 됨
        if "app/domain/" in file_path:
            if tool_name in ("Edit", "Write"):
                content = tool_input.get("content") or tool_input.get("new_string") or ""
                forbidden_imports = [
                    "from app.infrastructure",
                    "from app.application",
                    "from app.presentation",
                    "import app.infrastructure",
                    "import app.application",
                    "import app.presentation",
                ]
                for forbidden in forbidden_imports:
                    if forbidden in content:
                        print(f"❌ Clean Architecture 위반: domain 레이어는 다른 레이어({forbidden.split('.')[-1]})에 의존할 수 없습니다. 작업이 차단되었습니다.", file=sys.stderr)
                        sys.exit(2)

        # 규칙 5: application/ 레이어는 infrastructure/presentation에 의존하면 안 됨
        if "app/application/" in file_path:
            if tool_name in ("Edit", "Write"):
                content = tool_input.get("content") or tool_input.get("new_string") or ""
                forbidden_imports = [
                    "from app.infrastructure",
                    "from app.presentation",
                    "import app.infrastructure",
                    "import app.presentation",
                ]
                for forbidden in forbidden_imports:
                    if forbidden in content:
                        layer = forbidden.split(".")[-1]
                        print(f"❌ Clean Architecture 위반: application 레이어는 {layer} 레이어에 의존할 수 없습니다. 작업이 차단되었습니다.", file=sys.stderr)
                        sys.exit(2)

        # 규칙 6: 환경변수 직접 접근 금지 (settings 객체 사용 강제)
        if file_path.endswith(".py") and "app/core/config.py" not in file_path:
            if tool_name in ("Edit", "Write"):
                content = tool_input.get("content") or tool_input.get("new_string") or ""
                # os.getenv() 또는 os.environ 직접 사용 감지
                if "os.getenv(" in content or "os.environ[" in content or "os.environ.get(" in content:
                    print("❌ 환경변수 접근 규칙 위반: os.getenv() 대신 'from app.core.config import settings'를 사용하세요. 작업이 차단되었습니다.", file=sys.stderr)
                    sys.exit(2)

        # 규칙 7: Repository 직접 생성 금지 (DI 팩토리 함수 사용 강제)
        if file_path.endswith(".py"):
            if tool_name in ("Edit", "Write"):
                content = tool_input.get("content") or tool_input.get("new_string") or ""
                # Repository 직접 인스턴스화 감지 (infrastructure 레이어 제외)
                if "app/infrastructure/" not in file_path and "app/application/dependencies" not in file_path:
                    # MongoRepository(), SupabaseRepository() 등 직접 생성 패턴
                    repo_pattern = r"(Mongo|Supabase|Postgres)\w*Repository\s*\("
                    if re.search(repo_pattern, content):
                        print("❌ DI 규칙 위반: Repository를 직접 생성하지 마세요. 'from app.application.dependencies import get_*_repository'를 사용하세요. 작업이 차단되었습니다.", file=sys.stderr)
                        sys.exit(2)

        # 위의 모든 규칙에 해당하지 않으면 작업을 허용합니다.
        # 참고: 중복 코드 검사, 기존 코드 재사용 확인, Dead Code 정리는
        # Claude가 Grep/Glob 도구로 직접 수행합니다 (더 정확한 검색 가능).
        print("✅ 모든 규칙 통과", file=sys.stderr)
        sys.exit(0)

    except json.JSONDecodeError as e:
        print(f"❌ JSON 파싱 오류: {e}", file=sys.stderr)
        sys.exit(0)  # 오류가 있어도 작업은 계속 진행
    except Exception as e:
        print(f"❌ 디스패처 오류: {e}", file=sys.stderr)
        sys.exit(0)  # 오류가 있어도 작업은 계속 진행


if __name__ == "__main__":
    main()
