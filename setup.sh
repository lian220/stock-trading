#!/bin/bash

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}"
echo "╔════════════════════════════════════════╗"
echo "║   📈 Stock Trading API 초기 설정      ║"
echo "╔════════════════════════════════════════╗"
echo -e "${NC}"
echo ""

# .env 파일 생성
if [ -f .env ]; then
    echo -e "${YELLOW}⚠️  .env 파일이 이미 존재합니다.${NC}"
    read -p "덮어쓰시겠습니까? (y/n): " overwrite
    if [ "$overwrite" != "y" ] && [ "$overwrite" != "Y" ]; then
        echo "설정을 취소합니다."
        exit 0
    fi
fi

echo -e "${BLUE}📝 API 키를 입력해주세요 (Enter로 건너뛰면 기본값 사용):${NC}"
echo ""

# 사용자 입력 받기
read -p "한국투자증권 APP KEY: " KIS_APPKEY
read -p "한국투자증권 APP SECRET: " KIS_APPSECRET
read -p "한국투자증권 계좌번호 (CANO): " KIS_CANO
read -p "계좌상품코드 (기본값: 01): " KIS_ACNT_PRDT_CD
KIS_ACNT_PRDT_CD=${KIS_ACNT_PRDT_CD:-01}

echo ""
read -p "Supabase URL: " SUPABASE_URL
read -p "Supabase KEY: " SUPABASE_KEY

echo ""
read -p "TR_ID: " TR_ID
read -p "Alpha Vantage API KEY: " ALPHA_VANTAGE_API_KEY

# .env 파일 생성
cat > .env << EOF
# 한국투자증권 API 설정
KIS_USE_MOCK=false
KIS_APPKEY=${KIS_APPKEY:-your_appkey_here}
KIS_APPSECRET=${KIS_APPSECRET:-your_appsecret_here}
KIS_CANO=${KIS_CANO:-your_cano_here}
KIS_ACNT_PRDT_CD=${KIS_ACNT_PRDT_CD}

# Supabase 설정
SUPABASE_URL=${SUPABASE_URL:-your_supabase_url_here}
SUPABASE_KEY=${SUPABASE_KEY:-your_supabase_key_here}

# 기타 설정
TR_ID=${TR_ID:-your_tr_id_here}
ALPHA_VANTAGE_API_KEY=${ALPHA_VANTAGE_API_KEY:-your_alpha_vantage_key_here}

# 애플리케이션 설정
APP_ENV=production
LOG_LEVEL=INFO
EOF

echo ""
echo -e "${GREEN}✅ .env 파일이 생성되었습니다!${NC}"
echo ""
echo -e "${YELLOW}💡 다음 명령어로 실행하세요:${NC}"
echo "   ./quick-start.sh"
echo ""

