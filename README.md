# 📈 Stock Trading API

한국투자증권 API를 활용한 주식 거래 및 분석 시스템

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
cp .env.example .env
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
cp .env.example .env
# .env 파일을 편집하여 API 키 입력

# 실행
python run.py
```

## 📋 환경 변수 설정

`.env` 파일에 다음 항목들을 설정해야 합니다:

```env
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
```

## 🔗 API 접근

- **API 서버**: http://localhost:8000
- **API 문서 (Swagger)**: http://localhost:8000/docs
- **API 문서 (ReDoc)**: http://localhost:8000/redoc

## 📚 주요 기능

- 주식 시세 조회
- 주식 추천 시스템
- 계좌 잔고 조회
- 경제 지표 분석
- 실시간 데이터 스케줄링

## 🛠️ 기술 스택

- **FastAPI**: 고성능 웹 프레임워크
- **Supabase**: 데이터베이스
- **Docker**: 컨테이너화
- **Pandas**: 데이터 분석
- **yfinance**: 주식 데이터 수집

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

## 🔧 개발 모드

코드 변경 시 자동으로 재시작되는 개발 모드:

```bash
./start.sh
# 옵션 3 선택: 개발 모드로 실행
```

또는:

```bash
docker-compose up --build
```

## 🐛 문제 해결

### Docker가 실행되지 않을 때
```bash
# Docker 데몬 확인
docker info

# Docker 데몬 시작 (macOS)
open -a Docker

# Docker 데몬 시작 (Linux)
sudo systemctl start docker
```

### 포트가 이미 사용 중일 때
```bash
# 8000번 포트를 사용하는 프로세스 확인
lsof -i :8000

# 프로세스 종료
kill -9 <PID>
```

### 로그 확인
```bash
# Docker 로그
docker-compose logs -f

# 또는 start.sh 사용
./start.sh
# 옵션 5 선택: 로그 확인
```

## 🛑 중지

```bash
# 스크립트 사용
./stop.sh

# 또는 직접 명령
docker-compose down
```

## 📝 라이선스

이 프로젝트는 개인 프로젝트입니다.

## 👥 기여

버그 리포트 및 기능 제안은 이슈로 등록해주세요.

