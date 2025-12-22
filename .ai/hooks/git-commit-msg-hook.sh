#!/bin/sh
# Git hook to validate commit messages
# Delegates to the shared python script in .ai/hooks

PYTHON_SCRIPT=".ai/hooks/check_commit_msg.py"

if [ -f "$PYTHON_SCRIPT" ]; then
    python3 "$PYTHON_SCRIPT" "$1"
    exit_code=$?
    if [ $exit_code -ne 0 ]; then
        echo "❌ 커밋 메시지 규칙 위반으로 커밋이 차단되었습니다."
        exit 1
    fi
else
    echo "⚠️ 검증 스크립트($PYTHON_SCRIPT)를 찾을 수 없어 검증을 건너뜁니다."
fi
