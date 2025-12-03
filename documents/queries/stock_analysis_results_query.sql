-- =====================================================
-- stock_analysis_results 테이블 매수 조건 쿼리
-- =====================================================
-- AI 주가 예측 결과를 기반으로 매수 추천 종목 조회
-- 
-- 조건:
-- 1. 정확도(Accuracy) >= 80%
-- 2. 상승확률(Rise Probability) >= 3%
--
-- 상승확률이 높고 정확도가 높은 순서로 정렬
-- =====================================================

SELECT 
    "Stock",
    "Accuracy (%)",
    "Rise Probability (%)",
    "Last Actual Price",
    "Predicted Future Price",
    -- 예상 가격 변동
    ("Predicted Future Price" - "Last Actual Price") AS expected_price_change,
    -- 예상 수익률 (%)
    ROUND((("Predicted Future Price" - "Last Actual Price") / "Last Actual Price" * 100)::numeric, 2) AS expected_return_pct,
    "Predicted Rise",
    "Recommendation",
    "Analysis",
    -- 신뢰도 점수 (정확도와 상승확률의 조합)
    ROUND((("Accuracy (%)" * 0.6) + ("Rise Probability (%)" * 0.4))::numeric, 2) AS confidence_score,
    -- 추천 등급
    CASE 
        WHEN "Accuracy (%)" >= 90 AND "Rise Probability (%)" >= 10 THEN '강력 매수'
        WHEN "Accuracy (%)" >= 85 AND "Rise Probability (%)" >= 5 THEN '매수 추천'
        WHEN "Accuracy (%)" >= 80 AND "Rise Probability (%)" >= 3 THEN '매수 고려'
        ELSE '관망'
    END AS prediction_level,
    created_at
FROM stock_analysis_results
WHERE 
    -- 기본 매수 조건
    "Accuracy (%)" >= 80 
    AND "Rise Probability (%)" >= 3
    -- 상승 예측인 경우만
    AND "Predicted Rise" = TRUE
    -- 예측 가격이 현재 가격보다 높은 경우만
    AND "Predicted Future Price" > "Last Actual Price"
ORDER BY 
    "Rise Probability (%)" DESC,  -- 상승확률 높은 순
    "Accuracy (%)" DESC,           -- 정확도 높은 순
    expected_return_pct DESC,      -- 기대수익률 높은 순
    created_at DESC;               -- 최신 예측 순

