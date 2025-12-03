#!/bin/bash

# 가장 간단한 실행 스크립트 - Docker로 바로 실행

set -e

echo "🚀 Stock Trading API 빠른 실행..."
echo ""

# .env 파일이 없으면 기본값으로 생성
if [ ! -f .env ]; then
    echo "📝 .env 파일이 없습니다. 생성 중..."
    cat > .env << 'EOF'
# 한국투자증권 API 설정
KIS_USE_MOCK=false
KIS_APPKEY=your_appkey_here
KIS_APPSECRET=your_appsecret_here
KIS_CANO=your_cano_here
KIS_ACNT_PRDT_CD=01

# Supabase 설정
SUPABASE_URL=your_supabase_url_here
SUPABASE_KEY=your_supabase_key_here

# 기타 설정
TR_ID=your_tr_id_here
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key_here

# 애플리케이션 설정
APP_ENV=production
LOG_LEVEL=INFO
EOF
    echo "✅ .env 파일이 생성되었습니다."
    echo "⚠️  실제 API 키를 사용하려면 .env 파일을 편집해주세요."
    echo ""
fi

# Docker 실행
echo "🐳 Docker 컨테이너 시작..."
docker-compose up --build -d

echo ""
echo "✅ 실행 완료!"
echo ""
echo "📍 API: http://localhost:8000"
echo "📍 문서: http://localhost:8000/docs"
echo ""
echo "중지: docker-compose down 또는 ./stop.sh"

