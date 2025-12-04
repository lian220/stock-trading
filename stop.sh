#!/bin/bash

# 애플리케이션 중지 스크립트

echo "🛑 Stock Trading API 중지 중..."

# 1. Docker 컨테이너 중지 시도
echo "📦 Docker 컨테이너 확인 중..."

# Docker compose 명령어 설정
DOCKER_COMPOSE=""
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
elif command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
fi

# Docker compose로 중지 시도
if [ -n "$DOCKER_COMPOSE" ]; then
    echo "🐳 Docker Compose로 중지 시도..."
    $DOCKER_COMPOSE down 2>/dev/null
    
    # 실패하면 직접 컨테이너 중지
    if docker ps -a | grep -q "stock-trading"; then
        echo "🔄 Docker 컨테이너 직접 중지 중..."
        docker stop $(docker ps -a | grep "stock-trading" | awk '{print $1}') 2>/dev/null
        docker rm $(docker ps -a | grep "stock-trading" | awk '{print $1}') 2>/dev/null
    fi
fi

# 2. Python 프로세스 중지
echo "🐍 Python 프로세스 확인 중..."
PYTHON_PIDS=$(pgrep -f "python.*run.py|uvicorn.*main:app|python.*main.py" 2>/dev/null)

if [ -n "$PYTHON_PIDS" ]; then
    echo "🔪 Python 프로세스 중지 중..."
    echo "$PYTHON_PIDS" | xargs kill -15 2>/dev/null
    sleep 2
    
    # 강제 종료가 필요한 경우
    PYTHON_PIDS=$(pgrep -f "python.*run.py|uvicorn.*main:app|python.*main.py" 2>/dev/null)
    if [ -n "$PYTHON_PIDS" ]; then
        echo "⚠️  강제 종료 중..."
        echo "$PYTHON_PIDS" | xargs kill -9 2>/dev/null
    fi
fi

# 3. 개발 모드 설정 제거
if [ -f "docker-compose.override.yml" ]; then
    rm docker-compose.override.yml
    echo "✅ 개발 모드 설정 제거됨"
fi

# 4. 최종 확인
echo ""
echo "🔍 최종 확인..."
if docker ps | grep -q "stock-trading"; then
    echo "⚠️  일부 Docker 컨테이너가 여전히 실행 중입니다."
    docker ps | grep "stock-trading"
elif pgrep -f "python.*run.py|uvicorn.*main:app" > /dev/null 2>&1; then
    echo "⚠️  일부 Python 프로세스가 여전히 실행 중입니다."
    pgrep -af "python.*run.py|uvicorn.*main:app"
else
    echo "✅ 모든 프로세스가 정상적으로 중지되었습니다!"
fi

echo ""
echo "✅ 중지 완료!"

