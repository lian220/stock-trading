-- =====================================================
-- 통합 매수 추천 쿼리
-- =====================================================
-- 모든 테이블의 데이터를 통합하여 최종 매수 추천 종목 조회
-- 
-- 통합 조건:
-- 1. stock_analysis_results: 정확도 >= 80%, 상승확률 >= 3%
-- 2. stock_recommendations: 기술적 신호 점수 >= 2.0
-- 3. ticker_sentiment_analysis: 감정 점수 >= 0.15 (선택)
--
-- 최종 매수 조건:
-- - 감정 점수 >= 0.15: 기술적 신호 >= 2.0 (2개 이상)
-- - 감정 점수 < 0.15: 기술적 신호 >= 3.5 (3개 모두)
--
-- 종합 점수 = 상승확률(30%) + 기술적지표(40%) + 감정점수(30%)
-- =====================================================

WITH 
-- 1. 기술적 지표 데이터
technical_data AS (
    SELECT 
        "종목",
        "날짜",
        "SMA20",
        "SMA50",
        "골든_크로스",
        "RSI",
        "MACD",
        "Signal",
        "MACD_매수_신호",
        "추천_여부",
        (CASE WHEN "골든_크로스" = TRUE THEN 1.5 ELSE 0 END +
         CASE WHEN "RSI" < 50 THEN 1.0 ELSE 0 END +
         CASE WHEN "MACD_매수_신호" = TRUE THEN 1.0 ELSE 0 END) AS tech_signal_score
    FROM stock_recommendations
    WHERE 
        ("골든_크로스" = TRUE OR "RSI" < 50 OR "MACD_매수_신호" = TRUE)
),

-- 2. 주가 예측 데이터
prediction_data AS (
    SELECT 
        "Stock" AS stock_name,
        "Accuracy (%)" AS accuracy,
        "Rise Probability (%)" AS rise_probability,
        "Last Actual Price" AS last_price,
        "Predicted Future Price" AS predicted_price,
        "Recommendation",
        "Analysis",
        created_at
    FROM stock_analysis_results
    WHERE 
        "Accuracy (%)" >= 80 
        AND "Rise Probability (%)" >= 3
        AND "Predicted Rise" = TRUE
),

-- 3. 감정 분석 데이터
sentiment_data AS (
    SELECT 
        ticker,
        average_sentiment_score,
        article_count,
        calculation_date
    FROM ticker_sentiment_analysis
),

-- 4. 주식명-티커 매핑
ticker_mapping AS (
    SELECT 
        stock_name,
        ticker
    FROM stock_ticker_mapping
    WHERE is_active = TRUE AND is_etf = FALSE
)

-- 5. 최종 통합 및 매수 추천
SELECT 
    tm.ticker,
    tm.stock_name,
    -- 주가 예측 정보
    pd.accuracy,
    pd.rise_probability,
    pd.last_price,
    pd.predicted_price,
    ROUND(((pd.predicted_price - pd.last_price) / pd.last_price * 100)::numeric, 2) AS expected_return_pct,
    pd."Recommendation" AS prediction_recommendation,
    pd."Analysis",
    -- 기술적 지표 정보
    td."날짜" AS technical_date,
    td."SMA20" AS sma20,
    td."SMA50" AS sma50,
    td."골든_크로스" AS golden_cross,
    td."RSI" AS rsi,
    td."MACD" AS macd,
    td."Signal" AS signal,
    td."MACD_매수_신호" AS macd_buy_signal,
    td.tech_signal_score,
    -- 감정 분석 정보
    COALESCE(sd.average_sentiment_score, 0) AS sentiment_score,
    sd.article_count,
    sd.calculation_date AS sentiment_date,
    -- 종합 점수 계산 (0~100점 스케일)
    ROUND((
        0.3 * pd.rise_probability +           -- 상승확률 30%
        0.4 * (td.tech_signal_score * 10) +   -- 기술적지표 40% (3.5점 만점 -> 35점으로 환산)
        0.3 * (COALESCE(sd.average_sentiment_score, 0) * 100)  -- 감정점수 30% (0~1 -> 0~100으로 환산)
    )::numeric, 2) AS composite_score,
    -- 매수 추천 이유
    CASE 
        WHEN sd.average_sentiment_score >= 0.15 AND td.tech_signal_score >= 2.0 THEN 
            '✅ 매수 추천: 긍정 감정(' || ROUND(sd.average_sentiment_score::numeric, 3) || ') + 기술 신호(' || td.tech_signal_score || '점)'
        WHEN COALESCE(sd.average_sentiment_score, 0) < 0.15 AND td.tech_signal_score >= 3.5 THEN 
            '✅ 매수 추천: 강력한 기술 신호(3개 모두 충족)'
        WHEN sd.average_sentiment_score >= 0.15 AND td.tech_signal_score >= 1.5 THEN
            '⚠️ 매수 고려: 긍정 감정 + 일부 기술 신호'
        WHEN td.tech_signal_score >= 3.0 THEN
            '⚠️ 매수 고려: 강한 기술 신호'
        ELSE '📊 관망: 조건 미달'
    END AS buy_decision,
    -- 매수 우선순위
    CASE 
        WHEN sd.average_sentiment_score >= 0.15 AND td.tech_signal_score >= 3.5 THEN 1  -- 최우선
        WHEN sd.average_sentiment_score >= 0.15 AND td.tech_signal_score >= 2.5 THEN 2  -- 높음
        WHEN sd.average_sentiment_score >= 0.15 AND td.tech_signal_score >= 2.0 THEN 3  -- 보통
        WHEN td.tech_signal_score >= 3.5 THEN 4  -- 기술적 강세
        ELSE 5  -- 낮음
    END AS priority,
    pd.created_at AS prediction_date
FROM ticker_mapping tm
-- 주가 예측 데이터와 조인 (필수)
INNER JOIN prediction_data pd ON tm.stock_name = pd.stock_name
-- 기술적 지표 데이터와 조인 (필수)
INNER JOIN technical_data td ON tm.stock_name = td."종목"
-- 감정 분석 데이터와 조인 (선택)
LEFT JOIN sentiment_data sd ON tm.ticker = sd.ticker
WHERE 
    -- 최종 매수 조건 필터링
    (
        -- 조건 1: 긍정적 감정 + 기술적 신호 2개 이상
        (sd.average_sentiment_score >= 0.15 AND td.tech_signal_score >= 2.0)
        OR
        -- 조건 2: 감정 점수 부족 시 기술적 신호 3개 모두
        (COALESCE(sd.average_sentiment_score, 0) < 0.15 AND td.tech_signal_score >= 3.5)
    )
ORDER BY 
    priority ASC,           -- 우선순위 높은 순
    composite_score DESC,   -- 종합 점수 높은 순
    pd.rise_probability DESC;  -- 상승확률 높은 순

