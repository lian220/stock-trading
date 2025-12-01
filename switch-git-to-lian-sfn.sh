#!/bin/bash

# Git 계정을 lian-sfn으로 변경하는 스크립트

echo "현재 Git 계정 확인 중..."
CURRENT_NAME=$(git config user.name)
CURRENT_EMAIL=$(git config user.email)
echo "  현재 User name: $CURRENT_NAME"
echo "  현재 User email: $CURRENT_EMAIL"
echo ""

if [ "$CURRENT_NAME" = "lian-sfn" ]; then
    echo "⚠️  이미 'lian-sfn' 계정으로 설정되어 있습니다."
    exit 0
fi

echo "Git 계정을 lian-sfn으로 변경합니다..."

# 사용자 이름 변경
git config user.name "lian-sfn"

# 이메일은 기존 설정 유지
if [ -n "$CURRENT_EMAIL" ]; then
    git config user.email "$CURRENT_EMAIL"
fi

echo "✅ Git 사용자 이름이 'lian-sfn'으로 변경되었습니다."
echo ""
echo "변경된 Git 설정:"
echo "  User name: $(git config user.name)"
echo "  User email: $(git config user.email)"

