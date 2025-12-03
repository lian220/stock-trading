#!/bin/bash

# 애플리케이션 중지 스크립트

echo "🛑 Stock Trading API 중지 중..."

# Docker compose 명령어 설정
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
elif command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    echo "❌ docker compose가 설치되어 있지 않습니다."
    exit 1
fi

$DOCKER_COMPOSE down

if [ -f "docker-compose.override.yml" ]; then
    rm docker-compose.override.yml
    echo "✅ 개발 모드 설정 제거됨"
fi

echo "✅ 중지 완료!"

