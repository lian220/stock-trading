-- =====================================================
-- ticker_sentiment_analysis 테이블 매수 조건 쿼리
-- =====================================================
-- 뉴스 감정 분석 결과를 기반으로 매수 추천 종목 조회
-- 
-- 조건:
-- 1. 평균 감정 점수(average_sentiment_score) >= 0.15 (긍정적)
-- 2. 기사 수(article_count) >= 5 (신뢰도 확보)
--
-- 감정 점수가 높고 기사 수가 많은 순서로 정렬
-- =====================================================

SELECT 
    tsa.ticker,
    stm.stock_name,
    tsa.average_sentiment_score,
    tsa.article_count,
    tsa.calculation_date,
    -- 가중 감정 점수 (기사 수를 고려한 신뢰도)
    ROUND((tsa.average_sentiment_score * LEAST(tsa.article_count, 20))::numeric, 2) AS weighted_sentiment,
    -- 감정 등급
    CASE 
        WHEN tsa.average_sentiment_score >= 0.30 THEN '매우 긍정적'
        WHEN tsa.average_sentiment_score >= 0.20 THEN '긍정적'
        WHEN tsa.average_sentiment_score >= 0.15 THEN '다소 긍정적'
        WHEN tsa.average_sentiment_score >= 0 THEN '중립'
        WHEN tsa.average_sentiment_score >= -0.15 THEN '다소 부정적'
        WHEN tsa.average_sentiment_score >= -0.30 THEN '부정적'
        ELSE '매우 부정적'
    END AS sentiment_level,
    -- 신뢰도 등급
    CASE 
        WHEN tsa.article_count >= 20 THEN '매우 높음'
        WHEN tsa.article_count >= 10 THEN '높음'
        WHEN tsa.article_count >= 5 THEN '보통'
        ELSE '낮음'
    END AS reliability_level,
    tsa.created_at
FROM ticker_sentiment_analysis tsa
-- 주식명 매핑을 위한 조인
LEFT JOIN stock_ticker_mapping stm ON tsa.ticker = stm.ticker
WHERE 
    -- 기본 매수 조건: 긍정적 감정
    tsa.average_sentiment_score >= 0.15
    -- 신뢰도 확보: 최소 5개 이상의 기사
    AND tsa.article_count >= 5
    -- 활성화된 주식만
    AND (stm.is_active = TRUE OR stm.is_active IS NULL)
    -- ETF 제외
    AND (stm.is_etf = FALSE OR stm.is_etf IS NULL)
ORDER BY 
    tsa.average_sentiment_score DESC,  -- 감정 점수 높은 순
    tsa.article_count DESC,            -- 기사 수 많은 순
    tsa.calculation_date DESC;         -- 최신 분석 순

