# Python 3.11 기반 이미지 사용 (더 최신 버전)
FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# 환경 변수 설정
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Seoul

# 시스템 패키지 업데이트 및 필요한 패키지 설치
# python3, bash, curl 등 필수 도구 확인 및 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    bash \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/* \
    && which python3 || (echo "ERROR: python3 not found" && exit 1) \
    && which bash || (echo "ERROR: bash not found" && exit 1) \
    && python3 --version

# 비root 사용자 생성
RUN groupadd -r appuser && useradd -r -g appuser appuser

# requirements.txt 복사 및 의존성 설치
# 레이어 캐싱을 위해 의존성 파일만 먼저 복사
COPY requirements.txt .

# 의존성 설치
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY . .

# 로그 디렉토리 생성
RUN mkdir -p /app/logs && \
    chown -R appuser:appuser /app

# 비root 사용자로 전환
USER appuser

# 포트 노출
EXPOSE 8000

# 헬스체크
# python3 명령어 사용 (더 명시적이고 안전함)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# 애플리케이션 실행
# python3 명령어 사용 (python:3.11-slim에서는 python과 python3 모두 사용 가능하지만, python3가 더 명시적)
# 절대 경로 사용으로 더 안전함
CMD ["python3", "scripts/run/run.py"]
