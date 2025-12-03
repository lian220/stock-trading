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
    
    # 원격 URL 확인 및 수정
    CURRENT_URL=$(git remote get-url origin)
    if [[ "$CURRENT_URL" == *"lian-sfn"* ]] || [[ "$CURRENT_URL" == https://* ]]; then
        echo "원격 URL을 SSH로 변경합니다..."
        git remote set-url origin ssh://git@github.com/lian-sfn/stock-trading.git
        git remote set-url --push origin ssh://git@github.com/lian-sfn/stock-trading.git
        echo "✅ 원격 URL이 SSH로 변경되었습니다."
    fi
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

# 원격 URL을 SSH로 변경 (lian-sfn 계정은 SSH 키 사용)
echo "원격 URL을 SSH로 변경합니다..."
git remote set-url origin ssh://git@github.com/lian-sfn/stock-trading.git
git remote set-url --push origin ssh://git@github.com/lian-sfn/stock-trading.git

echo "변경된 Git 설정:"
echo "  User name: $(git config user.name)"
echo "  User email: $(git config user.email)"
echo ""
echo "변경된 원격 저장소:"
git remote -v

