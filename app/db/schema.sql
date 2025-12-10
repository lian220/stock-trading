-- stock_daily_volume 테이블 생성 (최종 제외 컬럼 반영: 코스트코, 넷플릭스, 페이팔, 시스코, 컴캐스트, 펩시코, 암젠, 허니웰 인터내셔널, 스타벅스, 몬델리즈, 어도비)

CREATE TABLE IF NOT EXISTS stock_daily_volume (
    "날짜" DATE PRIMARY KEY,
    "애플" BIGINT,
    "마이크로소프트" BIGINT,
    "아마존" BIGINT,
    "구글 A" BIGINT,
    "구글 C" BIGINT,
    "메타" BIGINT,
    "테슬라" BIGINT,
    "엔비디아" BIGINT,
    "인텔" BIGINT,
    "마이크론" BIGINT,
    "브로드컴" BIGINT,
    "텍사스 인스트루먼트" BIGINT,
    "AMD" BIGINT,
    "어플라이드 머티리얼즈" BIGINT,
    "셀레스티카" BIGINT,
    "버티브 홀딩스" BIGINT,
    "비스트라 에너지" BIGINT,
    "블룸에너지" BIGINT,
    "오클로" BIGINT,
    "팔란티어" BIGINT,
    "세일즈포스" BIGINT,
    "오라클" BIGINT,
    "앱플로빈" BIGINT,
    "팔로알토 네트웍스" BIGINT,
    "크라우드 스트라이크" BIGINT,
    "스노우플레이크" BIGINT,
    "TSMC" BIGINT,
    "크리도 테크놀로지 그룹 홀딩" BIGINT,
    "로빈후드" BIGINT,
    "일라이릴리" BIGINT,
    "월마트" BIGINT,
    "존슨앤존슨" BIGINT,
    "S&P 500 ETF" BIGINT,
    "QQQ ETF" BIGINT,
    "SOXX ETF" BIGINT
);

-- predicted_stocks 테이블 생성 (최종 제외 컬럼 및 추가 컬럼 반영)
CREATE TABLE IF NOT EXISTS predicted_stocks (
    id SERIAL PRIMARY KEY,
    "날짜" DATE NOT NULL,
    
    -- 기존 주식 예측 값 (14개 주식 및 2개 ETF)
    "애플_Predicted" NUMERIC,
    "애플_Actual" NUMERIC,
    "마이크로소프트_Predicted" NUMERIC,
    "마이크로소프트_Actual" NUMERIC,
    "아마존_Predicted" NUMERIC,
    "아마존_Actual" NUMERIC,
    "구글 A_Predicted" NUMERIC,
    "구글 A_Actual" NUMERIC,
    "구글 C_Predicted" NUMERIC,
    "구글 C_Actual" NUMERIC,
    "메타_Predicted" NUMERIC,
    "메타_Actual" NUMERIC,
    "테슬라_Predicted" NUMERIC,
    "테슬라_Actual" NUMERIC,
    "엔비디아_Predicted" NUMERIC,
    "엔비디아_Actual" NUMERIC,
    "인텔_Predicted" NUMERIC,
    "인텔_Actual" NUMERIC,
    "마이크론_Predicted" NUMERIC,
    "마이크론_Actual" NUMERIC,
    "브로드컴_Predicted" NUMERIC,
    "브로드컴_Actual" NUMERIC,
    "텍사스 인스트루먼트_Predicted" NUMERIC,
    "텍사스 인스트루먼트_Actual" NUMERIC,
    "AMD_Predicted" NUMERIC,
    "AMD_Actual" NUMERIC,
    "어플라이드 머티리얼즈_Predicted" NUMERIC,
    "어플라이드 머티리얼즈_Actual" NUMERIC,
    
    -- 추가된 주식 예측 값 (18개 주식)
    "셀레스티카_Predicted" NUMERIC,
    "셀레스티카_Actual" NUMERIC,
    "버티브 홀딩스_Predicted" NUMERIC,
    "버티브 홀딩스_Actual" NUMERIC,
    "비스트라 에너지_Predicted" NUMERIC,
    "비스트라 에너지_Actual" NUMERIC,
    "블룸에너지_Predicted" NUMERIC,
    "블룸에너지_Actual" NUMERIC,
    "오클로_Predicted" NUMERIC,
    "오클로_Actual" NUMERIC,
    "팔란티어_Predicted" NUMERIC,
    "팔란티어_Actual" NUMERIC,
    "세일즈포스_Predicted" NUMERIC,
    "세일즈포스_Actual" NUMERIC,
    "오라클_Predicted" NUMERIC,
    "오라클_Actual" NUMERIC,
    "앱플로빈_Predicted" NUMERIC,
    "앱플로빈_Actual" NUMERIC,
    "팔로알토 네트웍스_Predicted" NUMERIC,
    "팔로알토 네트웍스_Actual" NUMERIC,
    "크라우드 스트라이크_Predicted" NUMERIC,
    "크라우드 스트라이크_Actual" NUMERIC,
    "스노우플레이크_Predicted" NUMERIC,
    "스노우플레이크_Actual" NUMERIC,
    "TSMC_Predicted" NUMERIC,
    "TSMC_Actual" NUMERIC,
    "크리도 테크놀로지 그룹 홀딩_Predicted" NUMERIC,
    "크리도 테크놀로지 그룹 홀딩_Actual" NUMERIC,
    "로빈후드_Predicted" NUMERIC,
    "로빈후드_Actual" NUMERIC,
    "일라이릴리_Predicted" NUMERIC,
    "일라이릴리_Actual" NUMERIC,
    "월마트_Predicted" NUMERIC,
    "월마트_Actual" NUMERIC,
    "존슨앤존슨_Predicted" NUMERIC,
    "존슨앤존슨_Actual" NUMERIC,
    
    -- ETF 예측 값
    "S&P 500 ETF_Predicted" NUMERIC,
    "S&P 500 ETF_Actual" NUMERIC,
    "QQQ ETF_Predicted" NUMERIC,
    "QQQ ETF_Actual" NUMERIC,
    "SOXX ETF_Predicted" NUMERIC,
    "SOXX ETF_Actual" NUMERIC,
    
    -- 생성 시간 기록
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- 날짜에 대한 인덱스 추가
    CONSTRAINT unique_prediction_date UNIQUE ("날짜")
);

-- 날짜 검색을 위한 인덱스
CREATE INDEX IF NOT EXISTS idx_predicted_stocks_date ON predicted_stocks ("날짜");

-- economic_and_stock_data 테이블 생성 (최종 제외 컬럼 및 추가 컬럼 반영)
CREATE TABLE IF NOT EXISTS economic_and_stock_data (
    "날짜" DATE PRIMARY KEY,
    "10년 기대 인플레이션율" NUMERIC,
    "장단기 금리차" NUMERIC,
    "기준금리" NUMERIC,
    "미시간대 소비자 심리지수" NUMERIC,
    "실업률" NUMERIC,
    "2년 만기 미국 국채 수익률" NUMERIC,
    "10년 만기 미국 국채 수익률" NUMERIC,
    "금융스트레스지수" NUMERIC,
    "개인 소비 지출" NUMERIC,
    "소비자 물가지수" NUMERIC,
    "5년 변동금리 모기지" NUMERIC,
    "미국 달러 환율" NUMERIC,
    "통화 공급량 M2" NUMERIC,
    "가계 부채 비율" NUMERIC,
    "GDP 성장률" NUMERIC,
    "나스닥 종합지수" NUMERIC,
    "S&P 500 지수" NUMERIC,
    "금 가격" NUMERIC,
    "달러 인덱스" NUMERIC,
    "나스닥 100" NUMERIC,
    "S&P 500 ETF" NUMERIC,
    "QQQ ETF" NUMERIC,
    "러셀 2000 ETF" NUMERIC,
    "다우 존스 ETF" NUMERIC,
    "VIX 지수" NUMERIC,
    "닛케이 225" NUMERIC,
    "상해종합" NUMERIC,
    "항셍" NUMERIC,
    "영국 FTSE" NUMERIC,
    "독일 DAX" NUMERIC,
    "프랑스 CAC 40" NUMERIC,
    "미국 전체 채권시장 ETF" NUMERIC,
    "TIPS ETF" NUMERIC,
    "투자등급 회사채 ETF" NUMERIC,
    "달러/엔" NUMERIC,
    "달러/위안" NUMERIC,
    "미국 리츠 ETF" NUMERIC,
    "SOXX ETF" NUMERIC,
    "애플" NUMERIC,
    "마이크로소프트" NUMERIC,
    "아마존" NUMERIC,
    "구글 A" NUMERIC,
    "구글 C" NUMERIC,
    "메타" NUMERIC,
    "테슬라" NUMERIC,
    "엔비디아" NUMERIC,
    "인텔" NUMERIC,
    "마이크론" NUMERIC,
    "브로드컴" NUMERIC,
    "텍사스 인스트루먼트" NUMERIC,
    "AMD" NUMERIC,
    "어플라이드 머티리얼즈" NUMERIC,
    "셀레스티카" NUMERIC,
    "버티브 홀딩스" NUMERIC,
    "비스트라 에너지" NUMERIC,
    "블룸에너지" NUMERIC,
    "오클로" NUMERIC,
    "팔란티어" NUMERIC,
    "세일즈포스" NUMERIC,
    "오라클" NUMERIC,
    "앱플로빈" NUMERIC,
    "팔로알토 네트웍스" NUMERIC,
    "크라우드 스트라이크" NUMERIC,
    "스노우플레이크" NUMERIC,
    "TSMC" NUMERIC,
    "크리도 테크놀로지 그룹 홀딩" NUMERIC,
    "로빈후드" NUMERIC,
    "일라이릴리" NUMERIC,
    "월마트" NUMERIC,
    "존슨앤존슨" NUMERIC
);

-- 토큰 정보를 저장할 테이블 생성
CREATE TABLE IF NOT EXISTS access_tokens (
    id SERIAL PRIMARY KEY,                -- 자동 증가 기본 키
    access_token TEXT NOT NULL,           -- 접근 토큰 문자열
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,  -- 생성 시간
    expiration_time TIMESTAMP WITH TIME ZONE NOT NULL,  -- 만료 시간
    is_active BOOLEAN DEFAULT TRUE        -- 활성 상태 (선택사항)
);

-- 인덱스 생성 (성능 최적화)
CREATE INDEX IF NOT EXISTS idx_access_tokens_expiration ON access_tokens(expiration_time);
CREATE INDEX IF NOT EXISTS idx_access_tokens_created_at ON access_tokens(created_at);

-- 주석 추가
COMMENT ON TABLE access_tokens IS '한국투자증권 API 접근 토큰 정보';
COMMENT ON COLUMN access_tokens.access_token IS 'API 접근을 위한 JWT 토큰';
COMMENT ON COLUMN access_tokens.created_at IS '토큰 생성 시간';
COMMENT ON COLUMN access_tokens.expiration_time IS '토큰 만료 시간';
COMMENT ON COLUMN access_tokens.is_active IS '토큰 활성 상태';

-- stock_analysis_results 테이블 생성
CREATE TABLE IF NOT EXISTS stock_analysis_results (
    id SERIAL PRIMARY KEY,
    "Stock" TEXT NOT NULL,
    "MAE" NUMERIC,
    "MSE" NUMERIC,
    "RMSE" NUMERIC,
    "MAPE (%)" NUMERIC,
    "Accuracy (%)" NUMERIC,
    "Last Actual Price" NUMERIC,
    "Predicted Future Price" NUMERIC,
    "Predicted Rise" BOOLEAN,
    "Rise Probability (%)" NUMERIC,
    "Recommendation" TEXT,
    "Analysis" TEXT,
    
    -- 생성 시간 기록
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 주식명 검색을 위한 인덱스
CREATE INDEX IF NOT EXISTS idx_stock_analysis_stock ON stock_analysis_results ("Stock");
-- 추천 검색을 위한 인덱스
CREATE INDEX IF NOT EXISTS idx_stock_analysis_recommendation ON stock_analysis_results ("Recommendation");
-- 상승확률 검색을 위한 인덱스
CREATE INDEX IF NOT EXISTS idx_stock_analysis_rise_probability ON stock_analysis_results ("Rise Probability (%)");

-- stock_recommendations 테이블 생성
CREATE TABLE IF NOT EXISTS stock_recommendations (
    "날짜" DATE,
    "종목" VARCHAR(50),
    "SMA20" NUMERIC,
    "SMA50" NUMERIC,
    "골든_크로스" BOOLEAN,
    "RSI" NUMERIC,
    "MACD" NUMERIC,
    "Signal" NUMERIC,
    "MACD_매수_신호" BOOLEAN,
    "추천_여부" BOOLEAN,
    PRIMARY KEY ("날짜", "종목")
);

-- ticker_sentiment_analysis 테이블 생성
CREATE TABLE IF NOT EXISTS ticker_sentiment_analysis (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    average_sentiment_score FLOAT NOT NULL,
    article_count INTEGER NOT NULL,
    calculation_date TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- stock_ticker_mapping 테이블 생성 (주식명과 티커 심볼 매핑)
CREATE TABLE IF NOT EXISTS stock_ticker_mapping (
    id SERIAL PRIMARY KEY,
    stock_name VARCHAR(100) NOT NULL UNIQUE,  -- 한글 주식명
    ticker VARCHAR(10) NOT NULL UNIQUE,       -- 티커 심볼
    is_etf BOOLEAN DEFAULT FALSE,             -- ETF 여부
    leverage_ticker VARCHAR(10),              -- 레버리지 티커 심볼
    use_leverage BOOLEAN DEFAULT FALSE,       -- 레버리지 사용 여부
    is_active BOOLEAN DEFAULT TRUE,            -- 활성 여부
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_stock_ticker_mapping_stock_name ON stock_ticker_mapping (stock_name);
CREATE INDEX IF NOT EXISTS idx_stock_ticker_mapping_ticker ON stock_ticker_mapping (ticker);
CREATE INDEX IF NOT EXISTS idx_stock_ticker_mapping_is_active ON stock_ticker_mapping (is_active);

-- 주석 추가
COMMENT ON TABLE stock_ticker_mapping IS '한글 주식명과 티커 심볼 매핑 테이블';
COMMENT ON COLUMN stock_ticker_mapping.stock_name IS '한글 주식명';
COMMENT ON COLUMN stock_ticker_mapping.ticker IS '티커 심볼';
COMMENT ON COLUMN stock_ticker_mapping.is_etf IS 'ETF 여부';
COMMENT ON COLUMN stock_ticker_mapping.leverage_ticker IS '레버리지 티커 심볼';
COMMENT ON COLUMN stock_ticker_mapping.use_leverage IS '레버리지 사용 여부';
COMMENT ON COLUMN stock_ticker_mapping.is_active IS '활성 여부';

-- 초기 데이터 삽입 (최신 종목 정보 포함: 레버리지 티커 추가)
INSERT INTO stock_ticker_mapping (stock_name, ticker, is_etf, leverage_ticker, use_leverage, is_active) VALUES
    ('애플', 'AAPL', FALSE, 'AAPU', TRUE, TRUE),
    ('마이크로소프트', 'MSFT', FALSE, 'MSFU', TRUE, TRUE),
    ('아마존', 'AMZN', FALSE, 'AMZU', TRUE, TRUE),
    ('구글 A', 'GOOGL', FALSE, 'GGLL', TRUE, TRUE),
    ('메타', 'META', FALSE, 'FBL', TRUE, TRUE),
    ('테슬라', 'TSLA', FALSE, 'TSLL', TRUE, TRUE),
    ('엔비디아', 'NVDA', FALSE, 'NVDL', TRUE, TRUE),
    ('인텔', 'INTC', FALSE, 'INTL', TRUE, TRUE),
    ('마이크론', 'MU', FALSE, 'MULU', TRUE, TRUE),
    ('브로드컴', 'AVGO', FALSE, 'AVGL', TRUE, TRUE),
    ('텍사스 인스트루먼트', 'TXN', FALSE, 'TXNL', TRUE, TRUE),
    ('AMD', 'AMD', FALSE, 'AMDL', TRUE, TRUE),
    ('어플라이드 머티리얼즈', 'AMAT', FALSE, 'AMAL', TRUE, TRUE),
    ('TSMC', 'TSM', FALSE, 'TSML', TRUE, TRUE),
    ('크리도 테크놀로지 그룹 홀딩', 'CRDO', FALSE, 'CRDL', TRUE, TRUE),
    ('셀레스티카', 'CELH', FALSE, 'CELU', TRUE, TRUE),
    ('월마트', 'WMT', FALSE, 'WMTU', TRUE, TRUE),
    ('버티브 홀딩스', 'VRT', FALSE, 'VRTL', TRUE, TRUE),
    ('비스트라 에너지', 'VST', FALSE, 'VSTL', TRUE, TRUE),
    ('블룸에너지', 'BE', FALSE, 'BEL', TRUE, TRUE),
    ('오클로', 'OKLO', FALSE, 'OKLL', TRUE, TRUE),
    ('팔란티어', 'PLTR', FALSE, 'PLTL', TRUE, TRUE),
    ('세일즈포스', 'CRM', FALSE, 'CRML', TRUE, TRUE),
    ('오라클', 'ORCL', FALSE, 'ORCL', TRUE, TRUE),
    ('앱플로빈', 'APP', FALSE, 'APVL', TRUE, TRUE),
    ('팔로알토 네트웍스', 'PANW', FALSE, 'PANL', TRUE, TRUE),
    ('크라우드 스트라이크', 'CRWD', FALSE, 'CRWL', TRUE, TRUE),
    ('스노우플레이크', 'SNOW', FALSE, 'SNOL', TRUE, TRUE),
    ('로빈후드', 'HOOD', FALSE, 'HODL', TRUE, TRUE),
    ('일라이릴리', 'LLY', FALSE, 'LLYL', TRUE, TRUE),
    ('존슨앤존슨', 'JNJ', FALSE, 'JNJL', TRUE, TRUE),
    ('S&P 500 ETF', 'SPY', TRUE, 'UPRO', TRUE, TRUE),
    ('QQQ ETF', 'QQQ', TRUE, 'TQQQ', TRUE, TRUE),
    ('SOXX ETF', 'SOXX', TRUE, 'SOXL', TRUE, TRUE)
ON CONFLICT (stock_name) DO NOTHING;

-- ============================================
-- 마이그레이션: leverage_ticker, use_leverage 컬럼 추가
-- ============================================

-- stock_ticker_mapping 테이블에 레버리지 관련 컬럼 추가
ALTER TABLE stock_ticker_mapping ADD COLUMN IF NOT EXISTS leverage_ticker VARCHAR(10);
ALTER TABLE stock_ticker_mapping ADD COLUMN IF NOT EXISTS use_leverage BOOLEAN DEFAULT FALSE;

-- ============================================
-- 마이그레이션: 누락된 앱플로빈 컬럼 추가
-- 컬럼이 이미 존재하면 에러가 발생하지만 무시하고 진행하세요
-- ============================================

-- economic_and_stock_data 테이블에 앱플로빈 컬럼 추가
ALTER TABLE economic_and_stock_data ADD COLUMN IF NOT EXISTS "앱플로빈" NUMERIC;

-- predicted_stocks 테이블에 앱플로빈 컬럼 추가
ALTER TABLE predicted_stocks ADD COLUMN IF NOT EXISTS "앱플로빈_Predicted" NUMERIC;
ALTER TABLE predicted_stocks ADD COLUMN IF NOT EXISTS "앱플로빈_Actual" NUMERIC;

-- stock_daily_volume 테이블에 앱플로빈 컬럼 추가
ALTER TABLE stock_daily_volume ADD COLUMN IF NOT EXISTS "앱플로빈" BIGINT;

-- ============================================
-- 마이그레이션: SOXX ETF 컬럼 추가
-- ============================================

-- economic_and_stock_data 테이블에 SOXX ETF 컬럼 추가
ALTER TABLE economic_and_stock_data ADD COLUMN IF NOT EXISTS "SOXX ETF" NUMERIC;

-- predicted_stocks 테이블에 SOXX ETF 컬럼 추가
ALTER TABLE predicted_stocks ADD COLUMN IF NOT EXISTS "SOXX ETF_Predicted" NUMERIC;
ALTER TABLE predicted_stocks ADD COLUMN IF NOT EXISTS "SOXX ETF_Actual" NUMERIC;

-- stock_daily_volume 테이블에 SOXX ETF 컬럼 추가
ALTER TABLE stock_daily_volume ADD COLUMN IF NOT EXISTS "SOXX ETF" BIGINT;

-- ============================================
-- 자동매매 관련 테이블
-- ============================================

-- auto_trading_config 테이블 생성 (자동매매 설정)
CREATE TABLE IF NOT EXISTS auto_trading_config (
    id SERIAL PRIMARY KEY,
    enabled BOOLEAN DEFAULT FALSE,                    -- 자동매매 활성화 여부
    min_composite_score FLOAT DEFAULT 70.0,           -- 최소 종합 점수
    max_stocks_to_buy INTEGER DEFAULT 5,              -- 최대 매수 종목 수
    max_amount_per_stock FLOAT DEFAULT 10000.0,       -- 종목당 최대 매수 금액 (USD)
    stop_loss_percent FLOAT DEFAULT -7.0,             -- 손절 기준 (%)
    take_profit_percent FLOAT DEFAULT 5.0,            -- 익절 기준 (%)
    use_sentiment BOOLEAN DEFAULT TRUE,               -- 감정 분석 사용 여부
    min_sentiment_score FLOAT DEFAULT 0.15,           -- 최소 감정 점수
    order_type VARCHAR(10) DEFAULT '00',              -- 주문 구분 (00: 지정가)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_auto_trading_config_enabled ON auto_trading_config (enabled);

-- 주석 추가
COMMENT ON TABLE auto_trading_config IS '자동매매 설정 테이블';
COMMENT ON COLUMN auto_trading_config.enabled IS '자동매매 활성화 여부';
COMMENT ON COLUMN auto_trading_config.min_composite_score IS '최소 종합 점수 (0-100)';
COMMENT ON COLUMN auto_trading_config.max_stocks_to_buy IS '최대 매수 종목 수';
COMMENT ON COLUMN auto_trading_config.max_amount_per_stock IS '종목당 최대 매수 금액 (USD)';
COMMENT ON COLUMN auto_trading_config.stop_loss_percent IS '손절 기준 (%)';
COMMENT ON COLUMN auto_trading_config.take_profit_percent IS '익절 기준 (%)';
COMMENT ON COLUMN auto_trading_config.use_sentiment IS '감정 분석 사용 여부';
COMMENT ON COLUMN auto_trading_config.min_sentiment_score IS '최소 감정 점수 (-1 ~ 1)';

-- auto_trading_logs 테이블 생성 (자동매매 주문 기록)
CREATE TABLE IF NOT EXISTS auto_trading_logs (
    id SERIAL PRIMARY KEY,
    order_type VARCHAR(10) NOT NULL,                  -- 주문 유형 (buy/sell)
    ticker VARCHAR(10) NOT NULL,                      -- 티커 심볼
    stock_name VARCHAR(100),                          -- 주식명
    price FLOAT,                                      -- 주문 가격
    quantity INTEGER,                                 -- 주문 수량
    status VARCHAR(20),                               -- 주문 상태 (success/failed/dry_run)
    composite_score FLOAT,                            -- 종합 점수 (매수 시)
    price_change_percent FLOAT,                       -- 가격 변동률 (매도 시)
    sell_reasons TEXT[],                              -- 매도 사유 (매도 시)
    order_result JSONB,                               -- 주문 결과 (API 응답)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_auto_trading_logs_ticker ON auto_trading_logs (ticker);
CREATE INDEX IF NOT EXISTS idx_auto_trading_logs_order_type ON auto_trading_logs (order_type);
CREATE INDEX IF NOT EXISTS idx_auto_trading_logs_status ON auto_trading_logs (status);
CREATE INDEX IF NOT EXISTS idx_auto_trading_logs_created_at ON auto_trading_logs (created_at);

-- 주석 추가
COMMENT ON TABLE auto_trading_logs IS '자동매매 주문 기록 테이블';
COMMENT ON COLUMN auto_trading_logs.order_type IS '주문 유형 (buy: 매수, sell: 매도)';
COMMENT ON COLUMN auto_trading_logs.ticker IS '티커 심볼';
COMMENT ON COLUMN auto_trading_logs.stock_name IS '주식명';
COMMENT ON COLUMN auto_trading_logs.price IS '주문 가격';
COMMENT ON COLUMN auto_trading_logs.quantity IS '주문 수량';
COMMENT ON COLUMN auto_trading_logs.status IS '주문 상태 (success: 성공, failed: 실패, dry_run: 테스트)';
COMMENT ON COLUMN auto_trading_logs.composite_score IS '종합 점수 (매수 시)';
COMMENT ON COLUMN auto_trading_logs.price_change_percent IS '가격 변동률 (매도 시)';
COMMENT ON COLUMN auto_trading_logs.sell_reasons IS '매도 사유 배열 (매도 시)';
COMMENT ON COLUMN auto_trading_logs.order_result IS '주문 결과 (API 응답 JSON)';

