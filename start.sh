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
echo "1) Docker로 실행"
echo "2) 로컬 Python으로 실행"
echo "3) 개발 모드로 실행 (코드 변경 시 자동 재시작)"
echo "4) 중지"
echo "5) 로그 확인"
echo ""
read -p "선택 (1-5): " choice

case $choice in
    1)
        echo ""
        echo -e "${BLUE}🐳 Docker로 실행합니다...${NC}"
        
        # .env 파일 확인
        if [ ! -f .env ]; then
            echo -e "${YELLOW}⚠️  .env 파일이 없습니다.${NC}"
            read -p ".env.example을 복사하여 .env를 생성하시겠습니까? (y/n): " create_env
            if [ "$create_env" = "y" ] || [ "$create_env" = "Y" ]; then
                cp .env.example .env
                echo -e "${GREEN}✅ .env 파일이 생성되었습니다.${NC}"
                echo -e "${YELLOW}⚠️  .env 파일을 편집하여 실제 API 키를 입력해주세요.${NC}"
                echo ""
                read -p "계속하시겠습니까? (y/n): " continue_run
                if [ "$continue_run" != "y" ] && [ "$continue_run" != "Y" ]; then
                    exit 0
                fi
            else
                echo -e "${RED}❌ .env 파일이 필요합니다. 종료합니다.${NC}"
                exit 1
            fi
        fi
        
        # Docker 확인
        if ! command -v docker &> /dev/null; then
            echo -e "${RED}❌ Docker가 설치되어 있지 않습니다.${NC}"
            echo "Docker를 설치해주세요: https://www.docker.com/get-started"
            exit 1
        fi
        
        # docker-compose 명령어 설정 (v2는 docker compose, v1은 docker-compose)
        if docker compose version &> /dev/null; then
            DOCKER_COMPOSE="docker compose"
        elif command -v docker-compose &> /dev/null; then
            DOCKER_COMPOSE="docker-compose"
        else
            echo -e "${RED}❌ docker compose가 설치되어 있지 않습니다.${NC}"
            exit 1
        fi
        
        echo ""
        echo -e "${BLUE}📦 Docker 이미지 빌드 중...${NC}"
        $DOCKER_COMPOSE build
        
        echo ""
        echo -e "${BLUE}🚀 컨테이너 실행 중...${NC}"
        $DOCKER_COMPOSE up -d
        
        echo ""
        echo -e "${GREEN}✅ 애플리케이션이 실행되었습니다!${NC}"
        echo ""
        echo -e "${GREEN}📍 API 주소: http://localhost:8000${NC}"
        echo -e "${GREEN}📍 API 문서: http://localhost:8000/docs${NC}"
        echo ""
        echo -e "${YELLOW}💡 유용한 명령어:${NC}"
        echo "  - 로그 확인: $DOCKER_COMPOSE logs -f"
        echo "  - 컨테이너 중지: $DOCKER_COMPOSE down"
        echo "  - 컨테이너 재시작: $DOCKER_COMPOSE restart"
        echo ""
        echo -e "${YELLOW}⚠️  참고: Docker 환경에서는 Colab Selenium 실행이 지원되지 않습니다.${NC}"
        echo -e "${YELLOW}   Colab 기능을 사용하려면 로컬 버전(옵션 2)을 사용하세요.${NC}"
        echo ""
        ;;
        
    2)
        echo ""
        echo -e "${BLUE}🐍 로컬 Python으로 실행합니다...${NC}"
        
        # Python 확인
        if ! command -v python3 &> /dev/null; then
            echo -e "${RED}❌ Python3가 설치되어 있지 않습니다.${NC}"
            exit 1
        fi
        
        # .env 파일 확인
        if [ ! -f .env ]; then
            echo -e "${YELLOW}⚠️  .env 파일이 없습니다.${NC}"
            read -p ".env.example을 복사하여 .env를 생성하시겠습니까? (y/n): " create_env
            if [ "$create_env" = "y" ] || [ "$create_env" = "Y" ]; then
                cp .env.example .env
                echo -e "${GREEN}✅ .env 파일이 생성되었습니다.${NC}"
                echo -e "${YELLOW}⚠️  .env 파일을 편집하여 실제 API 키를 입력해주세요.${NC}"
                echo ""
            else
                echo -e "${RED}❌ .env 파일이 필요합니다. 종료합니다.${NC}"
                exit 1
            fi
        fi
        
        # 의존성 설치 (시스템 Python 사용)
        echo -e "${BLUE}📦 의존성 설치 중...${NC}"
        python3 -m pip install -r requirements.txt --user
        
        echo ""
        echo -e "${BLUE}🚀 애플리케이션 실행 중...${NC}"
        echo ""
        echo -e "${GREEN}📍 API 주소: http://localhost:8000${NC}"
        echo -e "${GREEN}📍 API 문서: http://localhost:8000/docs${NC}"
        echo ""
        echo -e "${GREEN}✅ 로컬 환경에서는 Colab Selenium 실행이 지원됩니다!${NC}"
        echo ""
        
        python3 scripts/run/run.py
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

