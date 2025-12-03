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
echo "1) Docker로 실행 (권장)"
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
        
        if ! command -v docker-compose &> /dev/null; then
            echo -e "${RED}❌ docker-compose가 설치되어 있지 않습니다.${NC}"
            exit 1
        fi
        
        echo ""
        echo -e "${BLUE}📦 Docker 이미지 빌드 중...${NC}"
        docker-compose build
        
        echo ""
        echo -e "${BLUE}🚀 컨테이너 실행 중...${NC}"
        docker-compose up -d
        
        echo ""
        echo -e "${GREEN}✅ 애플리케이션이 실행되었습니다!${NC}"
        echo ""
        echo -e "${GREEN}📍 API 주소: http://localhost:8000${NC}"
        echo -e "${GREEN}📍 API 문서: http://localhost:8000/docs${NC}"
        echo ""
        echo -e "${YELLOW}💡 유용한 명령어:${NC}"
        echo "  - 로그 확인: docker-compose logs -f"
        echo "  - 컨테이너 중지: docker-compose down"
        echo "  - 컨테이너 재시작: docker-compose restart"
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
        
        # 가상환경 확인
        if [ ! -d "venv" ]; then
            echo -e "${YELLOW}가상환경이 없습니다. 생성하시겠습니까? (y/n):${NC}"
            read create_venv
            if [ "$create_venv" = "y" ] || [ "$create_venv" = "Y" ]; then
                echo -e "${BLUE}📦 가상환경 생성 중...${NC}"
                python3 -m venv venv
                echo -e "${GREEN}✅ 가상환경이 생성되었습니다.${NC}"
            fi
        fi
        
        # 가상환경 활성화
        if [ -d "venv" ]; then
            echo -e "${BLUE}🔄 가상환경 활성화 중...${NC}"
            source venv/bin/activate
        fi
        
        # 의존성 설치
        echo -e "${BLUE}📦 의존성 설치 중...${NC}"
        pip install -r requirements.txt
        
        echo ""
        echo -e "${BLUE}🚀 애플리케이션 실행 중...${NC}"
        echo ""
        python3 run.py
        ;;
        
    3)
        echo ""
        echo -e "${BLUE}🔧 개발 모드로 실행합니다...${NC}"
        
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
      - ./run.py:/app/run.py
    environment:
      - APP_ENV=development
EOF
        
        echo -e "${BLUE}📦 개발 모드로 Docker 컨테이너 실행 중...${NC}"
        docker-compose up --build
        ;;
        
    4)
        echo ""
        echo -e "${BLUE}🛑 애플리케이션을 중지합니다...${NC}"
        docker-compose down
        echo -e "${GREEN}✅ 중지되었습니다.${NC}"
        
        # override 파일 삭제
        if [ -f "docker-compose.override.yml" ]; then
            rm docker-compose.override.yml
            echo -e "${GREEN}✅ 개발 모드 설정이 제거되었습니다.${NC}"
        fi
        ;;
        
    5)
        echo ""
        echo -e "${BLUE}📋 로그를 확인합니다...${NC}"
        echo ""
        docker-compose logs -f
        ;;
        
    *)
        echo -e "${RED}❌ 잘못된 선택입니다.${NC}"
        exit 1
        ;;
esac

