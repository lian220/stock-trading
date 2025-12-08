#!/bin/bash

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 배너 출력
echo -e "${BLUE}"
echo "╔════════════════════════════════════════╗"
echo "║   📈 Stock Trading API 실행 스크립트   ║"
echo "╔════════════════════════════════════════╗"
echo -e "${NC}"
echo ""

# 실행 모드 선택
echo -e "${YELLOW}실행 모드를 선택하세요:${NC}"
echo "1) Docker로 실행 (./start-docker.sh)"
echo "2) 로컬 Python으로 실행 (./start-local.sh)"
echo "3) 개발 모드로 실행 (코드 변경 시 자동 재시작)"
echo "4) 중지"
echo "5) 로그 확인"
echo ""
read -p "선택 (1-5): " choice

case $choice in
    1)
        echo ""
        echo -e "${BLUE}🐳 Docker 스크립트를 실행합니다...${NC}"
        chmod +x ./start-docker.sh
        ./start-docker.sh
        ;;
        
    2)
        echo ""
        echo -e "${BLUE}🐍 로컬 Python 스크립트를 실행합니다...${NC}"
        chmod +x ./start-local.sh
        ./start-local.sh
        ;;
        
    3)
        echo ""
        echo -e "${BLUE}🔧 개발 모드로 실행합니다...${NC}"
        
        # Docker compose 명령어 설정
        if docker compose version &> /dev/null; then
            DOCKER_COMPOSE="docker compose"
        elif command -v docker-compose &> /dev/null; then
            DOCKER_COMPOSE="docker-compose"
        else
            echo -e "${RED}❌ docker compose가 설치되어 있지 않습니다.${NC}"
            exit 1
        fi
        
        # .env 파일 확인
        if [ ! -f .env ]; then
            cp .env.example .env
            echo -e "${GREEN}✅ .env 파일이 생성되었습니다.${NC}"
        fi
        
        # docker-compose.override.yml 생성
        cat > docker-compose.override.yml << EOF
version: '3.8'

services:
  stock-trading-api:
    volumes:
      - ./app:/app/app
      - ./scripts/run/run.py:/app/scripts/run/run.py
    environment:
      - APP_ENV=development
EOF
        
        echo -e "${BLUE}📦 개발 모드로 Docker 컨테이너 실행 중...${NC}"
        $DOCKER_COMPOSE up --build
        ;;
        
    4)
        echo ""
        echo -e "${BLUE}🛑 애플리케이션을 중지합니다...${NC}"
        
        # stop.sh 스크립트 실행
        if [ -f "./stop.sh" ]; then
            chmod +x ./stop.sh
            ./stop.sh
        else
            # stop.sh가 없으면 직접 중지
            # Docker compose 명령어 설정
            DOCKER_COMPOSE=""
            if docker compose version &> /dev/null; then
                DOCKER_COMPOSE="docker compose"
            elif command -v docker-compose &> /dev/null; then
                DOCKER_COMPOSE="docker-compose"
            fi
            
            # Docker compose로 중지 시도
            if [ -n "$DOCKER_COMPOSE" ]; then
                $DOCKER_COMPOSE down 2>/dev/null
                
                # 실패하면 직접 컨테이너 중지
                if docker ps -a | grep -q "stock-trading"; then
                    docker stop $(docker ps -a | grep "stock-trading" | awk '{print $1}') 2>/dev/null
                    docker rm $(docker ps -a | grep "stock-trading" | awk '{print $1}') 2>/dev/null
                fi
            fi
            
            # Python 프로세스 중지
            PYTHON_PIDS=$(pgrep -f "python.*run.py|uvicorn.*main:app" 2>/dev/null)
            if [ -n "$PYTHON_PIDS" ]; then
                echo "$PYTHON_PIDS" | xargs kill -15 2>/dev/null
            fi
            
            # override 파일 삭제
            if [ -f "docker-compose.override.yml" ]; then
                rm docker-compose.override.yml
            fi
            
            echo -e "${GREEN}✅ 중지되었습니다.${NC}"
        fi
        ;;
        
    5)
        echo ""
        echo -e "${BLUE}📋 로그를 확인합니다...${NC}"
        echo ""
        
        # Docker compose 명령어 설정
        if docker compose version &> /dev/null; then
            DOCKER_COMPOSE="docker compose"
        elif command -v docker-compose &> /dev/null; then
            DOCKER_COMPOSE="docker-compose"
        else
            echo -e "${RED}❌ docker compose가 설치되어 있지 않습니다.${NC}"
            exit 1
        fi
        
        $DOCKER_COMPOSE logs -f
        ;;
        
    *)
        echo -e "${RED}❌ 잘못된 선택입니다.${NC}"
        exit 1
        ;;
esac

