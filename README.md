# 📈 주식 자동 매매 시스템

한국투자증권 API를 활용한 AI 기반 주식 자동 매매 시스템

미국 주식 시장에서 AI 주가 예측, 기술적 지표 분석, 뉴스 감정 분석을 통합하여 자동으로 매수/매도를 수행합니다.

## ✨ 주요 기능

- 🤖 **AI 주가 예측**: 머신러닝 기반 주가 예측 (정확도 80% 이상)
- 📊 **기술적 지표 분석**: 골든크로스, RSI, MACD 기반 매수/매도 신호
- 💬 **뉴스 감정 분석**: Alpha Vantage API를 통한 실시간 뉴스 감정 분석
- ⏰ **자동 매수/매도 스케줄러**: 매일 자동으로 매수/매도 실행
- 🔔 **Slack 실시간 알림**: 거래 체결 시 즉시 Slack으로 알림
- 📈 **포트폴리오 관리**: 보유 종목 추적 및 손익 계산

## 🚀 빠른 시작

### 1️⃣ 가장 빠른 방법 (Docker)

```bash
# 실행 권한 부여 (최초 1회)
chmod +x quick-start.sh

# 바로 실행
./quick-start.sh
```

### 2️⃣ 상세 옵션이 있는 실행

```bash
# 실행 권한 부여 (최초 1회)
chmod +x start.sh

# 실행
./start.sh
```

실행 시 다음 옵션을 선택할 수 있습니다:
- Docker로 실행 (권장)
- 로컬 Python으로 실행
- 개발 모드로 실행 (코드 변경 시 자동 재시작)
- 중지
- 로그 확인

### 3️⃣ 수동 실행

#### Docker 사용
```bash
# .env 파일 생성
cp env.sample .env
# .env 파일을 편집하여 API 키 입력

# Docker로 실행
docker-compose up --build -d

# 로그 확인
docker-compose logs -f

# 중지
docker-compose down
```

#### 로컬 Python 사용
```bash
# 가상환경 생성 및 활성화
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# .env 파일 생성
cp env.sample .env
# .env 파일을 편집하여 API 키 입력

# 실행
python run.py
```

## 📋 환경 변수 설정

`.env` 파일을 생성하고 다음 항목들을 설정해야 합니다:

```bash
# .env 파일 생성
cp env.sample .env
```

그 다음 `.env` 파일을 편집하여 실제 값을 입력하세요:

```env
# Supabase 설정
SUPABASE_URL=your_supabase_url_here
SUPABASE_KEY=your_supabase_key_here

# 한국투자증권 API 설정
KIS_USE_MOCK=true  # 모의투자: true, 실전투자: false
KIS_APPKEY=your_appkey_here
KIS_APPSECRET=your_appsecret_here
KIS_CANO=50124930  # 계좌번호 앞 8자리
KIS_ACNT_PRDT_CD=01  # 계좌번호 뒤 2자리
TR_ID=your_tr_id_here

# Alpha Vantage API (뉴스 감정 분석용)
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key_here

# Slack 알림 설정 (선택사항)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
SLACK_ENABLED=true
```

자세한 설정 방법은 `env.sample` 파일을 참고하세요.

## 🔗 API 접근

- **API 서버**: http://localhost:8000
- **API 문서 (Swagger)**: http://localhost:8000/docs
- **API 문서 (ReDoc)**: http://localhost:8000/redoc

## 📚 상세 가이드

자동 매매 시스템의 자세한 사용 방법은 다음 문서를 참고하세요:

- **[매수_동작_가이드.md](./매수_동작_가이드.md)** - 자동 매수 시스템 전체 동작 방식 (⭐ 필독)
- **[스케줄러_가이드.md](./스케줄러_가이드.md)** - 자동 매수/매도 스케줄러 상세 가이드

## 🛠️ 기술 스택

- **FastAPI**: 고성능 웹 프레임워크
- **Supabase**: 데이터베이스 (PostgreSQL)
- **Docker**: 컨테이너화
- **Pandas**: 데이터 분석 및 기술적 지표 계산
- **yfinance**: 주식 데이터 수집
- **Alpha Vantage**: 뉴스 감정 분석
- **한국투자증권 API**: 실시간 거래 및 시세 조회

## 📁 프로젝트 구조

```
stock-trading/
├── app/
│   ├── api/          # API 라우트
│   ├── core/         # 핵심 설정
│   ├── db/           # 데이터베이스
│   ├── models/       # 데이터 모델
│   ├── schemas/      # Pydantic 스키마
│   ├── services/     # 비즈니스 로직
│   └── utils/        # 유틸리티
├── documents/        # API 문서
├── logs/            # 로그 파일
├── tests/           # 테스트
├── Dockerfile       # Docker 이미지 설정
├── docker-compose.yml
├── requirements.txt # Python 의존성
└── start.sh         # 실행 스크립트
```

## 🎯 빠른 API 테스트

서버 실행 후 다음 API를 테스트해보세요:

### 1. 매수 추천 종목 조회
```bash
curl http://localhost:8000/api/recommended-stocks/with-technical-and-sentiment
```

### 2. 통합 분석 실행
```bash
curl -X POST http://localhost:8000/api/recommended-stocks/generate-complete-analysis
```

### 3. 자동 매수 스케줄러 시작
```bash
curl -X POST http://localhost:8000/api/recommended-stocks/purchase/scheduler/start
```

### 4. 스케줄러 상태 확인
```bash
curl http://localhost:8000/api/recommended-stocks/scheduler/status
```

## 💡 주요 사용 시나리오

### 시나리오 1: 매일 자동 매수
```bash
# 1. 서버 시작
./start.sh

# 2. 자동 매수 스케줄러 시작
curl -X POST http://localhost:8000/api/recommended-stocks/purchase/scheduler/start

# 이제 매일 밤 12시에 자동으로 매수됩니다!
```

### 시나리오 2: 즉시 매수 테스트
```bash
# 1. 추천 종목 확인
curl http://localhost:8000/api/recommended-stocks/with-technical-and-sentiment

# 2. 즉시 매수 실행
curl -X POST http://localhost:8000/api/recommended-stocks/purchase/trigger
```

### 시나리오 3: 데이터 업데이트 및 분석
```bash
# 기술적 지표 + 뉴스 감정 분석 + 통합 결과를 한번에 실행
curl -X POST http://localhost:8000/api/recommended-stocks/generate-complete-analysis
```

## 🐛 문제 해결

### 로그 확인
```bash
# Docker 로그
docker-compose logs -f

# 스케줄러 로그
tail -f stock_scheduler.log
```

### 포트가 이미 사용 중일 때
```bash
# 8000번 포트를 사용하는 프로세스 확인 및 종료
lsof -i :8000
kill -9 <PID>
```

## 🛑 중지

```bash
# 스크립트 사용
./stop.sh

# 또는 직접 명령
docker-compose down
```

## 📚 더 알아보기

- **매수 시스템 상세 가이드**: [매수_동작_가이드.md](./매수_동작_가이드.md)
- **API 문서**: http://localhost:8000/docs (서버 실행 후 접속)
- **SQL 쿼리 가이드**: [documents/queries/README.md](./documents/queries/README.md)

## ⚠️ 주의사항

1. **실전 투자 전 모의투자로 테스트**
   - `.env` 파일에서 `KIS_USE_MOCK=true` 설정
   - 충분히 테스트 후 실전 투자 시작

2. **API 키 보안**
   - `.env` 파일을 절대 Git에 커밋하지 마세요
   - Slack Webhook URL도 노출되지 않도록 주의

3. **자동 매수/매도 확인**
   - 스케줄러 실행 후 로그를 주기적으로 확인
   - Slack 알림을 설정하여 실시간으로 모니터링

## 👥 기여

버그 리포트 및 기능 제안은 이슈로 등록해주세요.

