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
echo "║   🐍 Stock Trading API (로컬 Python)   ║"
echo "╔════════════════════════════════════════╗"
echo -e "${NC}"
echo ""

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
echo -e "${GREEN}📍 API 주소: http://localhost:8000${NC}"
echo -e "${GREEN}📍 API 문서: http://localhost:8000/docs${NC}"
echo ""
echo -e "${GREEN}✅ 로컬 환경에서는 Colab Selenium 실행이 지원됩니다!${NC}"
echo ""

python3 run.py

