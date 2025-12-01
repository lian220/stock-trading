#!/bin/bash

# Docker로 애플리케이션 실행하는 스크립트

echo "🐳 Docker로 주식 거래 API 실행 중..."
echo ""

# .env 파일 확인
if [ ! -f .env ]; then
    echo "⚠️  .env 파일이 없습니다. 기본 .env 파일을 생성합니다..."
    cat > .env << EOF
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
EOF
    echo "✅ .env 파일이 생성되었습니다. 필요한 값들을 입력해주세요."
    exit 1
fi

# Docker 이미지 빌드 및 실행
echo "📦 Docker 이미지 빌드 중..."
docker-compose build

echo ""
echo "🚀 컨테이너 실행 중..."
docker-compose up -d

echo ""
echo "✅ 애플리케이션이 실행되었습니다!"
echo "📍 API 주소: http://localhost:8000"
echo "📍 API 문서: http://localhost:8000/docs"
echo ""
echo "컨테이너 로그 확인: docker-compose logs -f"
echo "컨테이너 중지: docker-compose down"

