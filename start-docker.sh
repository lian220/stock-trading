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
echo "║   🐳 Stock Trading API (Docker)        ║"
echo "╔════════════════════════════════════════╗"
echo -e "${NC}"
echo ""

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
echo -e "${YELLOW}   Colab 기능을 사용하려면 로컬 버전(./start-local.sh)을 사용하세요.${NC}"
echo ""

