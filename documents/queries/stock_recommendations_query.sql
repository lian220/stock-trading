-- =====================================================
-- stock_recommendations 테이블 매수 조건 쿼리
-- =====================================================
-- 기술적 지표를 기반으로 매수 추천 종목 조회
-- 
-- 조건:
-- 1. 골든크로스 = true (SMA20 > SMA50) - 가중치: 1.5
-- 2. RSI < 50 (과매도 구간) - 가중치: 1.0
-- 3. MACD 매수신호 = true (MACD > Signal) - 가중치: 1.0
--
-- 기술적 신호 점수: 최소 2.0 이상 추천 (3개 중 2개 이상)
-- =====================================================

SELECT 
    "종목",
    "날짜",
    "SMA20",
    "SMA50",
    "골든_크로스",
    "RSI",
    "MACD",
    "Signal",
    ("MACD" - "Signal") AS macd_diff,
    "MACD_매수_신호",
    "추천_여부",
    -- 각 지표별 점수 계산
    (CASE WHEN "골든_크로스" = TRUE THEN 1.5 ELSE 0 END) AS golden_cross_score,
    (CASE WHEN "RSI" < 50 THEN 1.0 ELSE 0 END) AS rsi_score,
    (CASE WHEN "MACD_매수_신호" = TRUE THEN 1.0 ELSE 0 END) AS macd_score,
    -- 총 기술적 신호 점수 (최대 3.5점)
    (CASE WHEN "골든_크로스" = TRUE THEN 1.5 ELSE 0 END +
     CASE WHEN "RSI" < 50 THEN 1.0 ELSE 0 END +
     CASE WHEN "MACD_매수_신호" = TRUE THEN 1.0 ELSE 0 END) AS total_tech_score,
    -- 신호 개수
    (CASE WHEN "골든_크로스" = TRUE THEN 1 ELSE 0 END +
     CASE WHEN "RSI" < 50 THEN 1 ELSE 0 END +
     CASE WHEN "MACD_매수_신호" = TRUE THEN 1 ELSE 0 END) AS signal_count,
    -- 추천 등급
    CASE 
        WHEN ("골든_크로스" = TRUE AND "RSI" < 50 AND "MACD_매수_신호" = TRUE) THEN '강력 매수 (3개 충족)'
        WHEN ((CASE WHEN "골든_크로스" = TRUE THEN 1.5 ELSE 0 END +
               CASE WHEN "RSI" < 50 THEN 1.0 ELSE 0 END +
               CASE WHEN "MACD_매수_신호" = TRUE THEN 1.0 ELSE 0 END) >= 2.5) THEN '매수 추천 (골든크로스 포함)'
        WHEN ((CASE WHEN "골든_크로스" = TRUE THEN 1.5 ELSE 0 END +
               CASE WHEN "RSI" < 50 THEN 1.0 ELSE 0 END +
               CASE WHEN "MACD_매수_신호" = TRUE THEN 1.0 ELSE 0 END) >= 2.0) THEN '매수 고려 (2개 충족)'
        ELSE '관망'
    END AS recommendation_level
FROM stock_recommendations
WHERE 
    -- 기술적 신호가 하나라도 있는 종목
    ("골든_크로스" = TRUE OR "RSI" < 50 OR "MACD_매수_신호" = TRUE)
    -- 기술적 신호 점수가 2.0 이상
    AND (CASE WHEN "골든_크로스" = TRUE THEN 1.5 ELSE 0 END +
         CASE WHEN "RSI" < 50 THEN 1.0 ELSE 0 END +
         CASE WHEN "MACD_매수_신호" = TRUE THEN 1.0 ELSE 0 END) >= 2.0
ORDER BY 
    total_tech_score DESC,  -- 기술적 점수 높은 순
    "RSI" ASC,              -- RSI 낮은 순 (더 과매도)
    "날짜" DESC;            -- 최신 데이터 순

