#!/bin/bash

# 애플리케이션 중지 스크립트

echo "🛑 Stock Trading API 중지 중..."
docker-compose down

if [ -f "docker-compose.override.yml" ]; then
    rm docker-compose.override.yml
    echo "✅ 개발 모드 설정 제거됨"
fi

echo "✅ 중지 완료!"

