import pandas as pd
import requests
import time
from datetime import datetime, timedelta
from app.db.mongodb import get_db
import numpy as np
from app.core.config import settings
from app.services.balance_service import get_overseas_balance
from app.utils.slack_notifier import slack_notifier
from app.services.stock_service import (
    get_ticker_from_stock_name,
    get_stock_name_from_ticker,
    get_active_stocks,
    get_active_stock_names,
    get_active_tickers,
    get_ticker_to_stock_mapping,
    get_stock_to_ticker_mapping,
    is_ticker_active,
    is_stock_name_active
)
import logging

logger = logging.getLogger('stock_recommendation_service')

class StockRecommendationService:
    def __init__(self):
        """StockRecommendationService 초기화"""
        self.lookback_days = 180  # 6개월 데이터

    def calculate_sma(self, series, period):
        """단순 이동평균(SMA) 계산"""
        return series.rolling(window=period).mean()

    def calculate_ema(self, series, period):
        """지수 이동평균(EMA) 계산"""
        return series.ewm(span=period, adjust=False).mean()

    def calculate_rsi(self, series, period=14):
        """RSI 계산"""
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_macd(self, series, short_period=12, long_period=26, signal_period=9):
        """MACD 및 Signal 라인 계산"""
        short_ema = self.calculate_ema(series, short_period)
        long_ema = self.calculate_ema(series, long_period)
        macd = short_ema - long_ema
        signal = self.calculate_ema(macd, signal_period)
        return macd, signal

    def generate_technical_recommendations(self, send_slack_notification: bool = False, start_date: str = None, end_date: str = None):
        """기술적 지표를 기반으로 추천 데이터를 생성하고 MongoDB에 저장
        
        Args:
            send_slack_notification: Slack 알림 전송 여부 (기본값: False, 스케줄러에서 관리)
            start_date: 분석 시작 날짜 (YYYY-MM-DD 형식, None이면 최근 6개월)
            end_date: 분석 종료 날짜 (YYYY-MM-DD 형식, None이면 오늘)
        """
        # MongoDB stocks 컬렉션에서 직접 활성화된 주식 조회
        try:
            stock_columns = get_active_stock_names(exclude_etf=True)
            
            if not stock_columns:
                error_msg = "활성화된 주식이 없습니다. MongoDB stocks 컬렉션에서 is_active=True인 주식을 확인하세요."
                logger.error(error_msg)
                return {"message": error_msg, "data": []}
            
            logger.info(f"MongoDB stocks 컬렉션에서 {len(stock_columns)}개의 활성화된 주식을 조회했습니다.")
        except Exception as e:
            error_msg = f"MongoDB stocks 컬렉션 조회 중 오류 발생: {str(e)}"
            logger.error(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            return {"message": error_msg, "data": []}
        
        # 날짜 범위가 지정된 경우 사용, 아니면 최근 6개월 데이터
        if start_date and end_date:
            start_date_str = start_date
            end_date_str = end_date
        else:
            # 최근 6개월 데이터만 가져오기
            end_date_dt = datetime.now()
            start_date_dt = end_date_dt - timedelta(days=self.lookback_days)
            start_date_str = start_date_dt.strftime("%Y-%m-%d")
            end_date_str = end_date_dt.strftime("%Y-%m-%d")
        
        # 기술적 지표 계산을 위해 최소 50일 데이터 필요
        # 날짜 범위가 지정된 경우에도 최소 50일 데이터를 확보하도록 조정
        if start_date and end_date:
            # 지정된 날짜 범위가 50일 미만이면 시작일을 50일 전으로 조정
            start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date_str, "%Y-%m-%d")
            days_diff = (end_dt - start_dt).days
            
            if days_diff < 50:
                logger.warning(f"⚠️ 지정된 날짜 범위({days_diff}일)가 기술적 지표 계산에 부족합니다. 시작일을 50일 전으로 조정합니다.")
                start_date_dt = end_dt - timedelta(days=50)
                start_date_str = start_date_dt.strftime("%Y-%m-%d")

        # MongoDB daily_stock_data에서 주식 데이터 조회
        try:
            db = get_db()
            if db is None:
                error_msg = "MongoDB 연결 실패"
                logger.error(error_msg)
                return {"message": error_msg, "data": []}
            
            # 날짜 범위의 daily_stock_data 조회
            daily_data = db.daily_stock_data.find({
                "date": {"$gte": start_date_str, "$lte": end_date_str}
            }).sort("date", 1)
            
            daily_list = list(daily_data)
            
            if not daily_list:
                error_msg = f"날짜 범위({start_date_str} ~ {end_date_str})에 daily_stock_data가 없습니다."
                logger.error(error_msg)
                return {"message": error_msg, "data": []}
            
            # 데이터프레임 생성
            data_dict = {}
            for doc in daily_list:
                date_str = doc.get("date")
                if not date_str:
                    logger.warning(f"⚠️ 날짜가 없는 문서 발견: {doc.get('_id')}")
                    continue
                
                stocks_data = doc.get("stocks", {})
                if not stocks_data:
                    logger.warning(f"⚠️ {date_str} 문서에 stocks 필드가 없거나 비어있습니다.")
                    continue
                
                # 각 주식의 가격 추출
                # daily_stock_data.stocks의 키는 티커(AAPL, MSFT 등), 값은 {"close_price": 가격, "short_interest": {...}} 형태
                found_count = 0
                for stock_name in stock_columns:
                    if stock_name not in data_dict:
                        data_dict[stock_name] = {}
                    
                    # 주식명을 티커로 변환
                    ticker = get_ticker_from_stock_name(stock_name)
                    if not ticker:
                        logger.warning(f"⚠️ {stock_name}의 티커를 찾을 수 없습니다. 건너뜁니다.")
                        continue
                    
                    # stocks_data의 키는 티커이므로 티커로 조회
                    stock_data = stocks_data.get(ticker)
                    if stock_data is not None:
                        # 값이 dict인 경우 close_price 가격 추출
                        if isinstance(stock_data, dict):
                            price = stock_data.get("adjusted_close") or stock_data.get("close_price")
                        else:
                            # 레거시: 숫자인 경우 그대로 사용 (하위 호환성)
                            price = stock_data
                        
                        if price is not None:
                            data_dict[stock_name][date_str] = float(price)
                            found_count += 1
            
            # DataFrame 생성
            if not data_dict:
                return {"message": "주식 가격 데이터가 없습니다", "data": []}
            
            # 날짜별로 데이터 정리
            all_dates = set()
            for stock_data in data_dict.values():
                all_dates.update(stock_data.keys())
            
            all_dates = sorted(all_dates)
            
            # DataFrame 생성
            df_data = {"날짜": all_dates}
            for stock_name in stock_columns:
                df_data[stock_name] = [data_dict.get(stock_name, {}).get(date, None) for date in all_dates]
            
            df = pd.DataFrame(df_data)
            
            # DataFrame이 비어있는지 확인
            if df.empty or len(df) == 0:
                error_msg = f"날짜 범위({start_date_str} ~ {end_date_str})에 주식 가격 데이터가 없습니다."
                logger.error(error_msg)
                return {"message": error_msg, "data": []}
            
            df["날짜"] = pd.to_datetime(df["날짜"])
            df.set_index("날짜", inplace=True)
            df = df.astype(float)
            
        except Exception as e:
            error_msg = f"MongoDB daily_stock_data 조회 중 오류 발생: {str(e)}"
            logger.error(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            return {"message": error_msg, "data": []}

        # DataFrame이 비어있는지 다시 확인
        if df.empty or len(df) == 0:
            error_msg = f"날짜 범위({start_date_str} ~ {end_date_str})에 주식 가격 데이터가 없습니다."
            logger.error(error_msg)
            return {"message": error_msg, "data": []}

        recommendations = []
        for stock in stock_columns:
            # 주식 컬럼이 DataFrame에 있는지 확인
            if stock not in df.columns:
                logger.warning(f"⚠️ {stock} 컬럼이 DataFrame에 없습니다. 건너뜁니다.")
                continue
            
            prices = df[stock]
            
            # 가격 데이터가 비어있거나 모두 NaN인지 확인
            if prices.empty or prices.isna().all():
                logger.warning(f"⚠️ {stock}의 가격 데이터가 없습니다. 건너뜁니다.")
                continue

            # 데이터가 충분한지 확인 (SMA50 계산을 위해 최소 50일 필요)
            if len(prices) < 50:
                logger.warning(f"⚠️ {stock}: 지표 계산을 위해 최소 50일 데이터가 필요합니다. 현재 {len(prices)}일 데이터만 있습니다.")
                continue

            # 지표 계산
            sma20 = self.calculate_sma(prices, 20)
            sma50 = self.calculate_sma(prices, 50)
            golden_cross = sma20 > sma50
            rsi = self.calculate_rsi(prices)
            macd, signal = self.calculate_macd(prices)
            macd_buy_signal = macd > signal
            recommended = golden_cross & (rsi < 50) & macd_buy_signal

            # 가장 최근 날짜의 결과만 저장
            if len(df.index) == 0:
                logger.warning(f"⚠️ {stock}의 날짜 인덱스가 비어있습니다. 건너뜁니다.")
                continue
                
            latest_date = df.index[-1]
            
            # 지표 값이 유효한지 확인
            sma20_val = sma20[latest_date] if latest_date in sma20.index else None
            sma50_val = sma50[latest_date] if latest_date in sma50.index else None
            rsi_val = rsi[latest_date] if latest_date in rsi.index else None
            macd_val = macd[latest_date] if latest_date in macd.index else None
            signal_val = signal[latest_date] if latest_date in signal.index else None
            
            if all(pd.notna([sma20_val, sma50_val, rsi_val, macd_val, signal_val])):
                recommendations.append({
                    "날짜": latest_date.strftime("%Y-%m-%d"),
                    "종목": stock,
                    "SMA20": float(sma20_val),
                    "SMA50": float(sma50_val),
                    "골든_크로스": bool(golden_cross[latest_date]) if latest_date in golden_cross.index else False,
                    "RSI": float(rsi_val),
                    "MACD": float(macd_val),
                    "Signal": float(signal_val),
                    "MACD_매수_신호": bool(macd_buy_signal[latest_date]) if latest_date in macd_buy_signal.index else False,
                    "추천_여부": bool(recommended[latest_date]) if latest_date in recommended.index else False
                })
            else:
                logger.warning(f"⚠️ {stock}: 지표 계산 결과가 유효하지 않습니다. (SMA20: {sma20_val}, SMA50: {sma50_val}, RSI: {rsi_val}, MACD: {macd_val}, Signal: {signal_val})")

        # recommendations가 비어있으면 저장하지 않음
        if not recommendations:
            error_msg = f"기술적 지표 계산을 위해 최소 50일 데이터가 필요합니다. 현재 날짜 범위({start_date_str} ~ {end_date_str})에는 {len(all_dates)}일 데이터만 있습니다."
            logger.warning(f"⚠️ {error_msg}")
            return {"message": error_msg, "data": []}

        # MongoDB에 저장
        try:
            # 가장 최근 날짜 사용 (recommendations의 첫 번째 항목에서 가져옴)
            today_str = recommendations[0].get("날짜")
            if not today_str:
                logger.error("⚠️ 추천 데이터에 날짜가 없습니다.")
                return {"message": "추천 데이터에 날짜가 없습니다", "data": []}
            
            # 하나의 상세한 로그로 통합
            recommended_count = len([r for r in recommendations if r.get('추천_여부', False)])
            logger.info(f"기술적 지표 분석 완료: {today_str} 기준 {len(recommendations)}개 종목 분석, 추천 종목 {recommended_count}개")
            
            # MongoDB에 저장
            try:
                db = get_db()
                if db is not None:
                    # MongoDB 사용 여부 확인
                    use_mongodb = settings.is_mongodb_enabled()
                    
                    if use_mongodb:
                        # 날짜 범위가 지정된 경우 end_date 사용, 없으면 오늘 날짜
                        if start_date and end_date:
                            analysis_date = end_date
                        else:
                            analysis_date = today_str
                        
                        # MongoDB에 저장할 데이터 변환
                        mongo_recommendations = []
                        recommendations_dict = {}  # daily_stock_data용
                        
                        for rec in recommendations:
                            stock_name = rec.get('종목')
                            ticker = get_ticker_from_stock_name(stock_name)
                            
                            # ticker가 없으면 건너뜀
                            if not ticker:
                                logger.warning(f"⚠️ {stock_name}에 대한 ticker를 찾을 수 없어 MongoDB 저장을 건너뜁니다.")
                                continue
                            
                            # stock_recommendations 컬렉션용 문서
                            mongo_doc = {
                                "date": analysis_date,  # YYYY-MM-DD 형식 (문자열)
                                "ticker": ticker,
                                "stock_id": None,  # 필요시 추가
                                "user_id": None,  # 전역 추천
                                "technical_indicators": {
                                    "sma20": rec.get('SMA20'),
                                    "sma50": rec.get('SMA50'),
                                    "golden_cross": rec.get('골든_크로스'),
                                    "rsi": rec.get('RSI'),
                                    "macd": rec.get('MACD'),
                                    "signal": rec.get('Signal'),
                                    "macd_buy_signal": rec.get('MACD_매수_신호')
                                },
                                "recommendation_score": None,  # 필요시 계산하여 추가
                                "is_recommended": rec.get('추천_여부', False),
                                "updated_at": datetime.utcnow()
                            }
                            mongo_recommendations.append(mongo_doc)
                            
                            # daily_stock_data용 딕셔너리 (ticker를 키로 사용)
                            recommendations_dict[ticker] = {
                                "technical_indicators": {
                                    "sma20": rec.get('SMA20'),
                                    "sma50": rec.get('SMA50'),
                                    "golden_cross": rec.get('골든_크로스'),
                                    "rsi": rec.get('RSI'),
                                    "macd": rec.get('MACD'),
                                    "signal": rec.get('Signal'),
                                    "macd_buy_signal": rec.get('MACD_매수_신호')
                                },
                                "is_recommended": rec.get('추천_여부', False),
                                "recommendation_score": None
                            }
                        
                        # 2. stock_recommendations 컬렉션에 저장
                        # ticker와 date 기준으로 upsert
                        if mongo_recommendations:
                            for mongo_doc in mongo_recommendations:
                                mongo_doc["updated_at"] = datetime.utcnow()
                                db.stock_recommendations.update_one(
                                    {
                                        "ticker": mongo_doc["ticker"],
                                        "date": mongo_doc["date"]  # ticker와 date 기준으로 upsert
                                    },
                                    {
                                        "$set": mongo_doc,
                                        "$setOnInsert": {
                                            "created_at": datetime.utcnow()
                                        }
                                    },
                                    upsert=True
                                )
                            logger.info(f"📊 MongoDB stock_recommendations 저장 성공: {analysis_date} 기준 {len(mongo_recommendations)}개 종목 저장 완료")
                        
                        # 3. daily_stock_data에 recommendations 필드 추가/업데이트
                        if recommendations_dict:
                            db.daily_stock_data.update_one(
                                {"date": analysis_date},
                                {
                                    "$set": {
                                        "recommendations": recommendations_dict,
                                        "updated_at": datetime.utcnow()
                                    },
                                    "$setOnInsert": {
                                        "created_at": datetime.utcnow()
                                    }
                                },
                                upsert=True
                            )
                            logger.info(f"📊 MongoDB daily_stock_data.recommendations 업데이트 성공: {analysis_date} 기준 {len(recommendations_dict)}개 종목")
                        else:
                            logger.warning(f"⚠️ MongoDB에 저장할 데이터가 없습니다. (ticker 매핑 실패)")
                    else:
                        logger.info(f"ℹ️ MongoDB가 비활성화되어 있습니다. (USE_MONGODB=False)")
                else:
                    logger.warning(f"⚠️ MongoDB 연결 실패: {today_str}")
            except Exception as mongo_e:
                logger.warning(f"⚠️ MongoDB 저장 실패: {str(mongo_e)}")
                import traceback
                logger.warning(traceback.format_exc())
        
        except Exception as e:
            print(f"오류 발생: {str(e)}")
            import traceback
            print(traceback.format_exc())  # 상세 스택 트레이스 출력
            
            # 슬랙 알림 - 실패 (send_slack_notification이 True인 경우에만)
            if send_slack_notification:
                slack_notifier.send_analysis_notification(
                    analysis_type='technical',
                    total_stocks=len(self.stock_columns),
                    success=False,
                    error_message=str(e)
                )
            
            raise Exception(f"추천 주식 분석 중 오류: {str(e)}")
        
        # 슬랙 알림 - 성공 (send_slack_notification이 True인 경우에만)
        if send_slack_notification:
            recommended_stocks = [rec for rec in recommendations if rec.get('추천_여부', False)]
            formatted_recommendations = []
            for rec in recommended_stocks:
                ticker = get_ticker_from_stock_name(rec['종목'])
                formatted_recommendations.append({
                    'stock_name': rec['종목'],
                    'ticker': ticker or 'N/A',
                    'recommendation_score': rec.get('RSI', 0)
                })
            
            slack_notifier.send_analysis_notification(
                analysis_type='technical',
                total_stocks=len(self.stock_columns),
                recommendations=formatted_recommendations,
                success=True
            )

        return {"message": f"{len(recommendations)}개의 추천 데이터가 생성되었습니다", "data": recommendations}

    def get_stock_recommendations(self):
        """
        Accuracy가 80% 이상이고 상승 확률이 3% 이상인 추천 주식 목록을 반환합니다.
        상승 확률 기준으로 내림차순 정렬됩니다.

        MongoDB stock_analysis 컬렉션에서 조회합니다.
        """
        try:
            db = get_db()
            if db is None:
                logger.error("MongoDB 연결 실패")
                return {"message": "MongoDB 연결 실패", "recommendations": []}

            # MongoDB stock_analysis 컬렉션에서 조회 (필터 조건 적용)
            cursor = db.stock_analysis.find({
                "metrics.accuracy": {"$gte": 80},
                "predictions.rise_probability": {"$gte": 3}
            }).sort("predictions.rise_probability", -1)
            data = list(cursor)

            if not data:
                logger.info("MongoDB stock_analysis에서 조건을 만족하는 데이터가 없음")
                return {"message": "분석 결과를 찾을 수 없습니다", "recommendations": []}

            # MongoDB 구조를 API 응답 형식으로 변환
            recommendations = []
            for doc in data:
                metrics = doc.get("metrics", {})
                predictions = doc.get("predictions", {})

                recommendations.append({
                    "Stock": doc.get("stock_name"),
                    "Accuracy (%)": metrics.get("accuracy"),
                    "Rise Probability (%)": predictions.get("rise_probability"),
                    "Last Actual Price": predictions.get("last_actual_price"),
                    "Predicted Future Price": predictions.get("predicted_future_price"),
                    "Recommendation": doc.get("recommendation"),
                    "Analysis": doc.get("analysis")
                })

            logger.info(f"MongoDB stock_analysis에서 {len(recommendations)}개 추천 종목 조회")
            return {
                "message": f"{len(recommendations)}개의 추천 주식을 찾았습니다",
                "recommendations": recommendations
            }
        except Exception as e:
            logger.error(f"get_stock_recommendations 오류: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {"message": f"분석 결과 조회 중 오류 발생: {str(e)}", "recommendations": []}

    def get_recommendations_with_sentiment(self):
        """
        get_stock_recommendations에서 가져온 추천 주식 중
        ticker_sentiment_analysis 테이블에서 average_sentiment_score >= 0.15인 주식만 필터링하고,
        두 데이터 소스의 정보를 결합하여 반환합니다.

        MongoDB sentiment_analysis 컬렉션에서 조회합니다.
        """
        stock_recs = self.get_stock_recommendations()
        recommendations = stock_recs.get("recommendations", [])
        if not recommendations:
            return {"message": "추천 주식이 없습니다", "results": []}

        # MongoDB에서 sentiment_analysis 조회
        try:
            db = get_db()
            if db is None:
                logger.error("MongoDB 연결 실패")
                return {"message": "MongoDB 연결 실패", "results": []}

            # MongoDB에서 average_sentiment_score >= 0.15인 데이터 조회
            cursor = db.sentiment_analysis.find({
                "average_sentiment_score": {"$gte": 0.15}
            })
            sentiment_list = list(cursor)

            if not sentiment_list:
                logger.info("MongoDB sentiment_analysis가 비어있음")
                return {"message": "감정 분석 데이터가 없습니다", "results": []}

            sentiment_data = {item["ticker"]: item for item in sentiment_list}
            logger.info(f"MongoDB sentiment_analysis에서 {len(sentiment_data)}개 조회")

        except Exception as e:
            logger.error(f"sentiment_analysis 조회 오류: {str(e)}")
            return {"message": f"감정 분석 데이터 조회 중 오류: {str(e)}", "results": []}

        # MongoDB에서 주식명으로 ticker 조회
        ticker_to_recommendation = {}
        for rec in recommendations:
            stock_name = rec["Stock"]
            ticker = get_ticker_from_stock_name(stock_name)
            if ticker:
                ticker_to_recommendation[ticker] = rec

        results = []
        for ticker, sentiment in sentiment_data.items():
            if ticker in ticker_to_recommendation:
                recommendation = ticker_to_recommendation[ticker]
                combined_data = {
                    "ticker": ticker,
                    "stock_name": recommendation["Stock"],
                    "accuracy": recommendation["Accuracy (%)"],
                    "rise_probability": recommendation["Rise Probability (%)"],
                    "last_actual_price": recommendation["Last Actual Price"],
                    "predicted_future_price": recommendation["Predicted Future Price"],
                    "recommendation": recommendation["Recommendation"],
                    "analysis": recommendation["Analysis"],
                    "average_sentiment_score": sentiment["average_sentiment_score"],
                    "article_count": sentiment["article_count"],
                    "calculation_date": sentiment.get("calculation_date") or sentiment.get("date")
                }
                results.append(combined_data)

        return {
            "message": f"{len(results)}개의 추천 주식을 분석했습니다",
            "results": results
        }

    def fetch_and_store_sentiment_for_recommendations(self, start_date: str = None, end_date: str = None):
        """
        추천 주식과 보유 중인 주식에 대해 뉴스 감정 데이터를 가져오고, MongoDB에 저장하며,
        감정 분석과 추천 정보를 통합하여 반환합니다.
        
        MongoDB 하이브리드 접근법:
        - sentiment_analysis 컬렉션: 종목별 시계열 조회용
        - daily_stock_data.sentiment 필드: 날짜별 통합 조회용
        
        Args:
            start_date: 분석 시작 날짜 (YYYY-MM-DD 형식, None이면 오늘)
            end_date: 분석 종료 날짜 (YYYY-MM-DD 형식, None이면 오늘)
        """
        # 날짜 범위 설정 (기본값: 오늘)
        if not start_date or not end_date:
            import pytz
            korea_tz = pytz.timezone('Asia/Seoul')
            today = datetime.now(korea_tz).strftime('%Y-%m-%d')
            start_date = start_date or today
            end_date = end_date or today
        
        # 추천 주식 목록 가져오기
        stock_recs = self.get_stock_recommendations()
        recommendations = stock_recs.get("recommendations", [])
        
        # 추천 주식의 티커 목록 생성
        recommended_tickers = []
        for rec in recommendations:
            stock_name = rec["Stock"]
            ticker = get_ticker_from_stock_name(stock_name)
            if ticker:
                recommended_tickers.append(ticker)
        
        # 보유 주식 정보 가져오기
        balance_result = get_overseas_balance()
        holdings = []
        
        if balance_result.get("rt_cd") == "0" and "output1" in balance_result:
            holdings = balance_result.get("output1", [])
            print(f"보유 주식 정보를 성공적으로 가져왔습니다. 총 {len(holdings)}개 종목 보유 중")
        else:
            print(f"보유 주식 정보를 가져오는데 실패했습니다: {balance_result.get('msg1', '알 수 없는 오류')}")
        
        # 보유 주식의 티커 목록 생성
        holding_tickers = [item.get("ovrs_pdno") for item in holdings if item.get("ovrs_pdno")]
        
        # 추천 주식과 보유 주식의 티커를 합치고 중복 제거
        all_tickers = list(set(recommended_tickers + holding_tickers))
        
        if not all_tickers:
            return {"message": "분석할 티커가 없습니다", "results": []}

        print(f"분석할 티커 목록 ({len(all_tickers)}개): {all_tickers} (날짜 범위: {start_date} ~ {end_date})")

        api_key = settings.ALPHA_VANTAGE_API_KEY
        relevance_threshold = 0.2
        sleep_interval = 5
        # start_date를 Alpha Vantage 형식으로 변환 (3일 전부터 조회)
        start_date_dt = datetime.strptime(start_date, '%Y-%m-%d')
        time_from = (start_date_dt - timedelta(days=3)).strftime("%Y%m%dT0000")

        base_url = "https://www.alphavantage.co/query"
        params = {
            "function": "NEWS_SENTIMENT",
            "time_from": time_from,
            "limit": 100,
            "apikey": api_key
        }

        # MongoDB에서 ticker_to_stock 매핑 생성
        ticker_to_stock = {}
        recommendations_by_ticker = {}
        for rec in recommendations:
            stock_name = rec["Stock"]
            ticker = get_ticker_from_stock_name(stock_name)
            if ticker:
                ticker_to_stock[ticker] = stock_name
                recommendations_by_ticker[ticker] = rec
        
        # 보유 주식 정보를 ticker로 매핑
        holdings_by_ticker = {item.get("ovrs_pdno"): item for item in holdings if item.get("ovrs_pdno")}

        # MongoDB 연결
        db = get_db()
        if db is None:
            logger.error("MongoDB 연결 실패 - 감정 분석 불가")
            return {"message": "MongoDB 연결 실패", "results": []}

        results = []
        for ticker in all_tickers:
            print(f"{ticker} 처리 중...")
            params["tickers"] = ticker

            response = requests.get(base_url, params=params)
            if response.status_code != 200:
                results.append({
                    "ticker": ticker,
                    "stock_name": ticker_to_stock.get(ticker, ticker),  # 티커명이 없으면 티커 자체를 표시
                    "message": "API 호출 실패",
                    "is_recommended": ticker in recommended_tickers,
                    "is_holding": ticker in holding_tickers,
                    "recommendation_info": recommendations_by_ticker.get(ticker, {}),
                    "holding_info": holdings_by_ticker.get(ticker, {})
                })
                time.sleep(sleep_interval)
                continue

            api_data = response.json()
            feed = api_data.get('feed', [])

            articles = [
                float(sentiment['ticker_sentiment_score'])
                for article in feed
                for sentiment in article.get('ticker_sentiment', [])
                if sentiment['ticker'] == ticker and float(sentiment['relevance_score']) >= relevance_threshold
            ]

            if not articles:
                results.append({
                    "ticker": ticker,
                    "stock_name": ticker_to_stock.get(ticker, ticker),
                    "message": "관련 기사 없음",
                    "is_recommended": ticker in recommended_tickers,
                    "is_holding": ticker in holding_tickers,
                    "recommendation_info": recommendations_by_ticker.get(ticker, {}),
                    "holding_info": holdings_by_ticker.get(ticker, {})
                })
                time.sleep(sleep_interval)
                continue

            average_sentiment = sum(articles) / len(articles)
            article_count = len(articles)
            calculation_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # MongoDB에 감정 분석 데이터 upsert (ticker 기준)
            db.sentiment_analysis.update_one(
                {"ticker": ticker},
                {
                    "$set": {
                        "average_sentiment_score": average_sentiment,
                        "article_count": article_count,
                        "calculation_date": calculation_date,
                        "updated_at": datetime.now()
                    },
                    "$setOnInsert": {
                        "created_at": datetime.now()
                    }
                },
                upsert=True
            )

            results.append({
                "ticker": ticker,
                "stock_name": ticker_to_stock.get(ticker, ticker),
                "average_sentiment_score": average_sentiment,
                "article_count": article_count,
                "calculation_date": calculation_date,
                "is_recommended": ticker in recommended_tickers,
                "is_holding": ticker in holding_tickers,
                "recommendation_info": recommendations_by_ticker.get(ticker, {}),
                "holding_info": holdings_by_ticker.get(ticker, {})
            })
            time.sleep(sleep_interval)

        # daily_stock_data에 sentiment 정보 저장
        try:
            db = get_db()
            if db is not None:
                use_mongodb = settings.is_mongodb_enabled()
                
                if use_mongodb:
                    # 날짜 범위가 지정된 경우 end_date 사용, 없으면 오늘 날짜
                    if start_date and end_date:
                        analysis_date = end_date
                    else:
                        import pytz
                        korea_tz = pytz.timezone('Asia/Seoul')
                        analysis_date = datetime.now(korea_tz).strftime('%Y-%m-%d')
                    
                    today_str = analysis_date
                    
                    # MongoDB에 저장할 데이터 변환
                    mongo_sentiments = []
                    sentiment_dict = {}  # daily_stock_data용
                    
                    for result in results:
                        if "average_sentiment_score" not in result:
                            continue  # API 호출 실패나 기사 없음은 제외
                        
                        ticker = result.get("ticker")
                        if not ticker:
                            continue
                        
                        # calculation_date를 datetime 객체로 변환
                        calc_date_str = result.get("calculation_date", calculation_date)
                        try:
                            calc_date_dt = datetime.strptime(calc_date_str, '%Y-%m-%d %H:%M:%S')
                        except:
                            calc_date_dt = datetime.utcnow()
                        
                        # sentiment_analysis 컬렉션용 문서
                        mongo_doc = {
                            "ticker": ticker,
                            "date": analysis_date,  # YYYY-MM-DD 형식
                            "stock_id": None,  # 필요시 추가
                            "average_sentiment_score": result.get("average_sentiment_score"),
                            "article_count": result.get("article_count"),
                            "calculation_date": calc_date_dt,
                            "updated_at": datetime.utcnow()
                        }
                        mongo_sentiments.append(mongo_doc)
                        
                        # daily_stock_data용 딕셔너리 (ticker를 키로 사용)
                        sentiment_dict[ticker] = {
                            "average_sentiment_score": result.get("average_sentiment_score"),
                            "article_count": result.get("article_count"),
                            "calculation_date": calc_date_str
                        }
                    
                    # 1. sentiment_analysis 컬렉션에 저장 (종목별 시계열 조회용)
                    # ticker와 date 기준으로 upsert
                    if mongo_sentiments:
                        for mongo_doc in mongo_sentiments:
                            mongo_doc["updated_at"] = datetime.utcnow()
                            db.sentiment_analysis.update_one(
                                {
                                    "ticker": mongo_doc["ticker"],
                                    "date": mongo_doc["date"]  # ticker와 date 기준으로 upsert
                                },
                                {
                                    "$set": mongo_doc,
                                    "$setOnInsert": {
                                        "created_at": datetime.utcnow()
                                    }
                                },
                                upsert=True
                            )
                        logger.info(f"📊 MongoDB sentiment_analysis 저장 성공: {today_str} 기준 {len(mongo_sentiments)}개 종목 저장 완료")
                    
                    # 2. daily_stock_data에 sentiment 필드 추가/업데이트 (날짜별 통합 조회용)
                    if sentiment_dict:
                        db.daily_stock_data.update_one(
                            {"date": today_str},
                            {
                                "$set": {
                                    "sentiment": sentiment_dict,
                                    "updated_at": datetime.utcnow()
                                },
                                "$setOnInsert": {
                                    "created_at": datetime.utcnow()
                                }
                            },
                            upsert=True
                        )
                        logger.info(f"📊 MongoDB daily_stock_data.sentiment 업데이트 성공: {today_str} 기준 {len(sentiment_dict)}개 종목")
                    else:
                        logger.warning(f"⚠️ MongoDB에 저장할 감정 분석 데이터가 없습니다.")
                else:
                    logger.info(f"ℹ️ MongoDB가 비활성화되어 있습니다. (USE_MONGODB=False)")
            else:
                logger.warning(f"⚠️ MongoDB 연결 실패")
        except Exception as mongo_e:
            logger.warning(f"⚠️ MongoDB 저장 실패: {str(mongo_e)}")
            import traceback
            logger.warning(traceback.format_exc())

        return {
            "message": f"{len(results)}개의 티커(추천 주식: {len(recommended_tickers)}개, 보유 주식: {len(holding_tickers)}개)를 분석했습니다",
            "results": results
        }

    def fetch_and_store_sentiment_independent(self):
        """
        AI 예측 결과에 의존하지 않고 독립적으로 감정 분석 수행
        - 활성화된 주식 목록 (MongoDB stocks 컬렉션)
        - 보유 주식 목록 (get_overseas_balance)
        """
        # 1. 활성화된 주식 목록 가져오기 (MongoDB에서 직접 조회)
        all_tickers = get_active_tickers(exclude_etf=True)
        
        # 2. 보유 주식 추가
        balance_result = get_overseas_balance()
        holdings = []
        
        if balance_result.get("rt_cd") == "0" and "output1" in balance_result:
            holdings = balance_result.get("output1", [])
            print(f"보유 주식 정보를 성공적으로 가져왔습니다. 총 {len(holdings)}개 종목 보유 중")
        else:
            print(f"보유 주식 정보를 가져오는데 실패했습니다: {balance_result.get('msg1', '알 수 없는 오류')}")
        
        # 보유 주식의 티커 목록 생성
        holding_tickers = [item.get("ovrs_pdno") for item in holdings if item.get("ovrs_pdno")]
        
        # 활성화된 주식과 보유 주식의 티커를 합치고 중복 제거
        all_tickers = list(set(all_tickers + holding_tickers))
        
        if not all_tickers:
            return {"message": "분석할 티커가 없습니다", "results": []}

        print(f"분석할 티커 목록 ({len(all_tickers)}개): {all_tickers}")

        api_key = settings.ALPHA_VANTAGE_API_KEY
        relevance_threshold = 0.2
        sleep_interval = 5
        # 오늘 날짜를 Alpha Vantage 형식으로 변환 (3일 전부터 조회)
        today_dt = datetime.now()
        time_from = (today_dt - timedelta(days=3)).strftime("%Y%m%dT0000")

        base_url = "https://www.alphavantage.co/query"
        params = {
            "function": "NEWS_SENTIMENT",
            "time_from": time_from,
            "limit": 100,
            "apikey": api_key
        }

        # MongoDB에서 ticker_to_stock 매핑 생성
        ticker_to_stock = get_ticker_to_stock_mapping(exclude_etf=False)
        
        # 보유 주식 정보를 ticker로 매핑
        holdings_by_ticker = {item.get("ovrs_pdno"): item for item in holdings if item.get("ovrs_pdno")}

        # MongoDB 연결
        db = get_db()
        if db is None:
            logger.error("MongoDB 연결 실패 - 감정 분석 불가")
            return {"message": "MongoDB 연결 실패", "results": []}

        results = []
        for ticker in all_tickers:
            print(f"{ticker} 처리 중...")
            params["tickers"] = ticker

            response = requests.get(base_url, params=params)
            if response.status_code != 200:
                results.append({
                    "ticker": ticker,
                    "stock_name": ticker_to_stock.get(ticker, ticker),
                    "message": "API 호출 실패",
                    "is_active": ticker in all_tickers,
                    "is_holding": ticker in holding_tickers,
                    "holding_info": holdings_by_ticker.get(ticker, {})
                })
                time.sleep(sleep_interval)
                continue

            api_data = response.json()
            feed = api_data.get('feed', [])

            articles = [
                float(sentiment['ticker_sentiment_score'])
                for article in feed
                for sentiment in article.get('ticker_sentiment', [])
                if sentiment['ticker'] == ticker and float(sentiment['relevance_score']) >= relevance_threshold
            ]

            if not articles:
                results.append({
                    "ticker": ticker,
                    "stock_name": ticker_to_stock.get(ticker, ticker),
                    "message": "관련 기사 없음",
                    "is_active": ticker in all_tickers,
                    "is_holding": ticker in holding_tickers,
                    "holding_info": holdings_by_ticker.get(ticker, {})
                })
                time.sleep(sleep_interval)
                continue

            average_sentiment = sum(articles) / len(articles)
            article_count = len(articles)
            calculation_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # MongoDB에 감정 분석 데이터 upsert (ticker 기준)
            db.sentiment_analysis.update_one(
                {"ticker": ticker},
                {
                    "$set": {
                        "average_sentiment_score": average_sentiment,
                        "article_count": article_count,
                        "calculation_date": calculation_date,
                        "updated_at": datetime.now()
                    },
                    "$setOnInsert": {
                        "created_at": datetime.now()
                    }
                },
                upsert=True
            )

            results.append({
                "ticker": ticker,
                "stock_name": ticker_to_stock.get(ticker, ticker),
                "average_sentiment_score": average_sentiment,
                "article_count": article_count,
                "is_active": ticker in all_tickers,
                "is_holding": ticker in holding_tickers,
                "holding_info": holdings_by_ticker.get(ticker, {})
            })
            time.sleep(sleep_interval)

        # 활성화된 주식 수 계산 (MongoDB에서 조회한 주식 수)
        active_tickers_from_db = get_active_tickers(exclude_etf=True)
        active_count = len([t for t in all_tickers if t in active_tickers_from_db])
        return {
            "message": f"{len(results)}개의 티커(활성화된 주식: {active_count}개, 보유 주식: {len(holding_tickers)}개)를 분석했습니다",
            "results": results
        }


    def get_combined_recommendations_with_technical_and_sentiment(self, send_slack_notification: bool = True):
        """
        추천 주식 목록을 기술적 지표(stock_recommendations 테이블)와 감정 분석(ticker_sentiment_analysis 테이블)을
        결합하여 반환합니다.
        - stock_recommendations에서 골든_크로스=true, MACD_매수_신호=true, RSI<50 중 하나 이상 만족하는 종목 필터링
        - ticker_sentiment_analysis에서 average_sentiment_score >= 0.15인 데이터와 결합
        - get_stock_recommendations의 결과와 통합하여 반환
        - 추가 조건: sentiment_score와 기술적 지표를 기반으로 매수 추천 필터링

        MongoDB stock_recommendations, sentiment_analysis 컬렉션에서 조회합니다.

        Args:
            send_slack_notification: Slack 알림 전송 여부 (기본값: True)
        """
        try:
            # 1. 기술적 지표 데이터 조회 (MongoDB 우선)
            tech_data = []
            db = get_db()

            if db is not None:
                # MongoDB stock_recommendations에서 조회 (date 내림차순)
                cursor = db.stock_recommendations.find({}).sort("date", -1)
                mongo_tech_data = list(cursor)

                if mongo_tech_data:
                    # MongoDB 필드명을 API 응답 형식으로 변환
                    for doc in mongo_tech_data:
                        tech_indicators = doc.get("technical_indicators", {})
                        tech_data.append({
                            "날짜": doc.get("date"),
                            "종목": get_stock_name_from_ticker(doc.get("ticker")) or doc.get("ticker"),
                            "ticker": doc.get("ticker"),
                            "SMA20": tech_indicators.get("sma20"),
                            "SMA50": tech_indicators.get("sma50"),
                            "골든_크로스": tech_indicators.get("golden_cross", False),
                            "RSI": tech_indicators.get("rsi"),
                            "MACD": tech_indicators.get("macd"),
                            "Signal": tech_indicators.get("signal"),
                            "MACD_매수_신호": tech_indicators.get("macd_buy_signal", False),
                            "추천_여부": doc.get("is_recommended", False)
                        })
                    logger.info(f"MongoDB stock_recommendations에서 {len(tech_data)}개 조회")

            # MongoDB에 데이터가 없으면 에러 반환
            if not tech_data:
                logger.info("MongoDB stock_recommendations가 비어있음")
                # 데이터가 없어도 슬랙 알림 전송
                if send_slack_notification:
                    try:
                        slack_notifier.send_combined_analysis_notification(
                            total_stocks=0,
                            recommendations=[],
                            analysis_stats={
                                'total_analyzed': 0,
                                'final_recommendations': 0,
                                'avg_composite_score': 0,
                                'technical_signals': 0,
                                'positive_sentiment': 0,
                                'ai_predictions': 0,
                                'avg_rise_probability': 0
                            },
                            success=True
                        )
                    except Exception as slack_error:
                        logger.error(f"슬랙 알림 전송 실패: {str(slack_error)}")
                return {"message": "기술적 지표 데이터가 없습니다", "results": []}

            tech_df = pd.DataFrame(tech_data)
            
            # 데이터 타입 변환
            tech_df["골든_크로스"] = tech_df["골든_크로스"].astype(bool)
            tech_df["MACD_매수_신호"] = tech_df["MACD_매수_신호"].astype(bool)
            tech_df["RSI"] = pd.to_numeric(tech_df["RSI"])
            
            # 필터링: 골든_크로스=true, MACD_매수_신호=true, RSI<50 중 하나 이상
            mask_golden = tech_df["골든_크로스"] == True
            mask_macd = tech_df["MACD_매수_신호"] == True
            mask_rsi = tech_df["RSI"] < 50
            combined_mask = np.logical_or.reduce([mask_golden, mask_macd, mask_rsi])
            filtered_tech_df = tech_df[combined_mask]
            
            # 2. 주가 예측 데이터 조회
            stock_recs = self.get_stock_recommendations()
            recommendations = stock_recs.get("recommendations", [])
            
            # 초기값 설정 (슬랙 알림을 위해)
            results = []
            final_results = []
            
            # 데이터가 있는 경우에만 처리
            if not filtered_tech_df.empty and recommendations:

                # 3. 감정 분석 데이터 조회 (MongoDB 우선)
                sentiment_map = {}
                if db is not None:
                    # MongoDB sentiment_analysis에서 조회
                    sentiment_cursor = db.sentiment_analysis.find({
                        "average_sentiment_score": {"$gte": 0.15}
                    })
                    sentiment_list = list(sentiment_cursor)
                    if sentiment_list:
                        sentiment_map = {item["ticker"]: item for item in sentiment_list}
                        logger.info(f"MongoDB sentiment_analysis에서 {len(sentiment_map)}개 조회")

                # MongoDB에 데이터가 없으면 빈 맵 사용
                if not sentiment_map:
                    logger.info("MongoDB sentiment_analysis가 비어있음")

                # 4. 데이터 매핑 준비
                tech_map = {row["종목"]: row.to_dict() for _, row in filtered_tech_df.iterrows()}
                
                # 5. 결과 통합
                for rec in recommendations:
                    stock_name = rec["Stock"]
                    ticker = get_ticker_from_stock_name(stock_name)
                    if not ticker:
                        continue
                    tech_data = tech_map.get(stock_name)
                    if tech_data is None:
                        continue  # 기술적 지표가 없으면 제외
                    
                    sentiment = sentiment_map.get(ticker)
                    
                    # 통합 데이터 생성
                    combined_data = {
                        "ticker": ticker,
                        "stock_name": stock_name,
                        "accuracy": rec["Accuracy (%)"],
                        "rise_probability": rec["Rise Probability (%)"],
                        "last_price": rec["Last Actual Price"],
                        "predicted_price": rec["Predicted Future Price"],
                        "recommendation": rec["Recommendation"],
                        "analysis": rec["Analysis"],
                        "sentiment_score": sentiment["average_sentiment_score"] if sentiment else None,
                        "article_count": sentiment["article_count"] if sentiment else None,
                        "sentiment_date": sentiment.get("calculation_date") or sentiment.get("date") if sentiment else None,
                        "technical_date": tech_data["날짜"],
                        "sma20": float(tech_data["SMA20"]),
                        "sma50": float(tech_data["SMA50"]),
                        "golden_cross": bool(tech_data["골든_크로스"]),
                        "rsi": float(tech_data["RSI"]),
                        "macd": float(tech_data["MACD"]),
                        "signal": float(tech_data["Signal"]),
                        "macd_buy_signal": bool(tech_data["MACD_매수_신호"]),
                        "technical_recommended": bool(tech_data["추천_여부"])
                    }
                    results.append(combined_data)
                
                # 6. 매수 추천 조건에 따른 추가 필터링 후 순위 계산
                for item in results:
                    sentiment_score = item["sentiment_score"]
                    tech_conditions = [item["golden_cross"], item["rsi"] < 50, item["macd_buy_signal"]]
                    
                    if sentiment_score is not None and sentiment_score >= 0.15:
                        if sum(tech_conditions) >= 2:
                            final_results.append(item)
                    else:
                        if sum(tech_conditions) >= 3:
                            final_results.append(item)

                # 7. 종합 점수 계산 및 정렬
                for item in final_results:
                    sentiment_score = item["sentiment_score"] if item["sentiment_score"] is not None else 0.0
                    tech_conditions_count = (
                        1.5 * item["golden_cross"] +
                        1.0 * (item["rsi"] < 50) +
                        1.0 * item["macd_buy_signal"]
                    )
                    item["composite_score"] = (
                        0.3 * item["rise_probability"] +
                        0.4 * tech_conditions_count +
                        0.3 * sentiment_score
                    )

                final_results.sort(key=lambda x: x["composite_score"], reverse=True)

            # 8. 슬랙 알림 - 통합 분석 완료 (4가지 분석 결과 포함)
            if send_slack_notification:
                try:
                    # 상위 5개 추천 종목 정보 준비
                    top_recommendations = [
                        {
                            'stock_name': item['stock_name'],
                            'ticker': item['ticker'],
                            'recommendation_score': item['composite_score'],
                            'rise_probability': item['rise_probability'],
                            'sentiment_score': item['sentiment_score'] if item['sentiment_score'] else 0,
                            'golden_cross': item['golden_cross'],
                            'rsi': item['rsi'],
                            'macd_buy_signal': item['macd_buy_signal']
                        }
                        for item in final_results[:5]
                    ]
                    
                    # 각 분석 통계 계산
                    technical_count = sum(1 for item in final_results if item['technical_recommended'])
                    sentiment_count = sum(1 for item in final_results if item['sentiment_score'] and item['sentiment_score'] >= 0.15)
                    ai_predictions = [item for item in final_results if item['rise_probability'] >= 3]
                    
                    slack_notifier.send_combined_analysis_notification(
                        total_stocks=len(results),
                        recommendations=top_recommendations,
                        analysis_stats={
                            'total_analyzed': len(results),
                            'final_recommendations': len(final_results),
                            'avg_composite_score': sum(item['composite_score'] for item in final_results) / len(final_results) if final_results else 0,
                            'technical_signals': technical_count,
                            'positive_sentiment': sentiment_count,
                            'ai_predictions': len(ai_predictions),
                            'avg_rise_probability': sum(item['rise_probability'] for item in final_results) / len(final_results) if final_results else 0
                        },
                        success=True
                    )
                except Exception as slack_error:
                    logger.error(f"슬랙 알림 전송 실패: {str(slack_error)}")

            # 9. 결과 반환
            return {
                "message": f"{len(final_results)}개의 매수 추천 주식을 찾았습니다",
                "results": final_results
            }
        
        except Exception as e:
            print(f"오류 발생: {str(e)}")
            import traceback
            print(traceback.format_exc())  # 상세 스택 트레이스 출력
            
            # 슬랙 알림 - 실패 (send_slack_notification이 True인 경우에만)
            if send_slack_notification:
                try:
                    slack_notifier.send_combined_analysis_notification(
                        total_stocks=0,
                        recommendations=[],
                        analysis_stats={},
                        success=False,
                        error_message=str(e)
                    )
                except Exception as slack_error:
                    print(f"슬랙 알림 전송 실패: {str(slack_error)}")
            
            raise Exception(f"추천 주식 분석 중 오류: {str(e)}")

    def get_stocks_to_sell(self):
        """
        매도 대상 종목을 식별하는 함수
        
        매도 조건:
        1. 구매가 대비 현재가가 +5% 이상(익절) 또는 -7% 이하(손절)인 종목
        2. 감성 점수 < -0.15이고 기술적 지표 중 2개 이상 매도 신호인 종목
        3. 기술적 지표 중 3개 이상 매도 신호인 종목
        
        반환값:
        - sell_candidates: 매도 대상 종목 목록
        - technical_data: 종목별 기술적 지표 데이터
        - sentiment_data: 종목별 감성 분석 데이터
        """
        try:
            # 1. 보유 종목 정보 가져오기
            balance_result = get_overseas_balance()
            if balance_result.get("rt_cd") != "0" or "output1" not in balance_result:
                return {
                    "message": f"보유 종목 정보를 가져오는데 실패했습니다: {balance_result.get('msg1', '알 수 없는 오류')}",
                    "sell_candidates": []
                }
            
            holdings = balance_result.get("output1", [])
            if not holdings:
                return {
                    "message": "보유 종목이 없습니다",
                    "sell_candidates": []
                }
            
            # 2. 티커와 한글명 매핑 생성
            ticker_to_korean = {}
            korean_to_ticker = {}
            
            for item in holdings:
                ticker = item.get("ovrs_pdno")
                name = item.get("ovrs_item_name")
                if ticker and name:
                    ticker_to_korean[ticker] = name
                    korean_to_ticker[name] = ticker
            
            # 3. 기술적 지표 데이터 가져오기 (MongoDB 우선)
            tech_list = []
            db = get_db()

            if db is not None:
                # MongoDB stock_recommendations에서 조회
                cursor = db.stock_recommendations.find({}).sort("date", -1)
                mongo_tech_data = list(cursor)

                if mongo_tech_data:
                    for doc in mongo_tech_data:
                        tech_indicators = doc.get("technical_indicators", {})
                        tech_list.append({
                            "날짜": doc.get("date"),
                            "종목": get_stock_name_from_ticker(doc.get("ticker")) or doc.get("ticker"),
                            "ticker": doc.get("ticker"),
                            "골든_크로스": tech_indicators.get("golden_cross", False),
                            "RSI": tech_indicators.get("rsi"),
                            "MACD_매수_신호": tech_indicators.get("macd_buy_signal", False),
                        })
                    logger.info(f"get_stocks_to_sell: MongoDB stock_recommendations에서 {len(tech_list)}개 조회")

            # MongoDB에 데이터가 없으면 빈 리스트
            if not tech_list:
                logger.info("get_stocks_to_sell: MongoDB stock_recommendations가 비어있음")

            tech_data = pd.DataFrame(tech_list) if tech_list else pd.DataFrame()

            if not tech_data.empty:
                # 데이터 타입 변환
                tech_data["골든_크로스"] = tech_data["골든_크로스"].astype(bool)
                tech_data["MACD_매수_신호"] = tech_data["MACD_매수_신호"].astype(bool)
                tech_data["RSI"] = pd.to_numeric(tech_data["RSI"])

                # 최신 데이터만 필터링 (종목별 가장 최근 날짜의 데이터)
                tech_data = tech_data.sort_values("날짜", ascending=False)
                tech_data = tech_data.drop_duplicates(subset=["종목"], keep="first")

            # 4. 감성 분석 데이터 가져오기 (MongoDB 우선)
            sentiment_data = {}
            if db is not None:
                sentiment_cursor = db.sentiment_analysis.find({})
                sentiment_list = list(sentiment_cursor)
                if sentiment_list:
                    sentiment_data = {item["ticker"]: item for item in sentiment_list}
                    logger.info(f"get_stocks_to_sell: MongoDB sentiment_analysis에서 {len(sentiment_data)}개 조회")

            # MongoDB에 데이터가 없으면 빈 딕셔너리
            if not sentiment_data:
                logger.info("get_stocks_to_sell: MongoDB sentiment_analysis가 비어있음")

            # 5. 매도 대상 종목 식별
            sell_candidates = []
            
            for item in holdings:
                ticker = item.get("ovrs_pdno")
                stock_name = item.get("ovrs_item_name")
                
                purchase_price = float(item.get("pchs_avg_pric", 0))
                current_price = float(item.get("now_pric2", 0))
                quantity = int(item.get("ovrs_cblc_qty", 0))
                exchange_code = item.get("ovrs_excg_cd", "")
                
                # 가격 변동률 계산
                price_change_percent = ((current_price - purchase_price) / purchase_price) * 100 if purchase_price > 0 else 0
                
                # 매도 근거와 신호 수를 추적할 변수들
                sell_reasons = []
                technical_sell_signals = 0
                
                # 조건 1: 가격 기반 매도 (익절/손절)
                if price_change_percent >= 5:
                    sell_reasons.append(f"익절 조건 충족: 구매가 대비 {price_change_percent:.2f}% 상승")
                elif price_change_percent <= -7:
                    sell_reasons.append(f"손절 조건 충족: 구매가 대비 {price_change_percent:.2f}% 하락")
                
                # 기술적 지표 확인
                tech_record = None
                if not tech_data.empty:
                    tech_filtered = tech_data[tech_data["종목"] == stock_name]
                    if not tech_filtered.empty:
                        tech_record = tech_filtered.iloc[0].to_dict()
                
                tech_sell_signals_details = []
                if tech_record:
                    # 기술적 지표 매도 신호 확인
                    if not tech_record["골든_크로스"]:  # 데드 크로스는 매도 신호
                        technical_sell_signals += 1
                        tech_sell_signals_details.append("데드 크로스")
                    
                    if tech_record["RSI"] > 70:  # RSI 70 이상은 과매수 구간(매도 신호)
                        technical_sell_signals += 1
                        tech_sell_signals_details.append(f"RSI 과매수({tech_record['RSI']:.2f})")
                    
                    if not tech_record["MACD_매수_신호"]:  # MACD 매수 신호가 없으면 매도 신호
                        technical_sell_signals += 1
                        tech_sell_signals_details.append("MACD 매도 신호")
                
                # 감성 분석 데이터 확인
                sentiment_score = None
                if ticker in sentiment_data:
                    sentiment_score = sentiment_data[ticker].get("average_sentiment_score")
                
                # 조건 3: 기술적 지표 중 3개 이상 매도 신호 (가장 강력한 매도 신호부터 체크)
                if technical_sell_signals >= 3:
                    sell_reasons.append(f"모든 기술적 지표가 매도 신호: {', '.join(tech_sell_signals_details)}")
                # 조건 2: 감성 점수 < -0.15이고 기술적 지표 중 2개 이상 매도 신호
                elif sentiment_score is not None and sentiment_score < -0.15 and technical_sell_signals >= 2:
                    sell_reasons.append(f"부정적 감성({sentiment_score:.2f})과 기술적 매도 신호({technical_sell_signals}개): {', '.join(tech_sell_signals_details)}")
                
                # 매도 대상 판단
                if sell_reasons:
                    sell_candidates.append({
                        "ticker": ticker,
                        "stock_name": stock_name,
                        "purchase_price": purchase_price,
                        "current_price": current_price,
                        "price_change_percent": price_change_percent,
                        "quantity": quantity,
                        "exchange_code": exchange_code,
                        "sell_reasons": sell_reasons,
                        "technical_sell_signals": technical_sell_signals,
                        "technical_sell_details": tech_sell_signals_details if tech_sell_signals_details else None,
                        "sentiment_score": sentiment_score,
                        "technical_data": tech_record
                    })
            
            # 가격 변동률이 큰 순서로 정렬 (절대값 기준)
            sell_candidates.sort(key=lambda x: abs(x["price_change_percent"]), reverse=True)
            
            return {
                "message": f"{len(sell_candidates)}개의 매도 대상 종목을 식별했습니다",
                "sell_candidates": sell_candidates
            }
            
        except Exception as e:
            print(f"매도 대상 종목 식별 중 오류 발생: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return {
                "message": f"매도 대상 종목 식별 중 오류 발생: {str(e)}",
                "sell_candidates": []
            }
    
    # ============================================================
    # MongoDB 하이브리드 조회 함수들
    # ============================================================
    
    def get_daily_recommendations_from_mongodb(self, date_str: str = None):
        """
        날짜별 통합 조회: daily_stock_data에서 주가 데이터와 추천 정보를 한 번에 조회
        
        Args:
            date_str: 조회할 날짜 (YYYY-MM-DD 형식). None이면 오늘 날짜 사용
        
        Returns:
            dict: {
                "date": str,
                "stocks": {...},           # 주가 데이터
                "recommendations": {...},  # 추천 정보
                "fred_indicators": {...},  # 경제 지표
                "yfinance_indicators": {...}  # 시장 지표
            }
        """
        try:
            from app.core.config import settings
            
            # MongoDB 사용 여부 확인
            use_mongodb = settings.is_mongodb_enabled()
            if not use_mongodb:
                logger.warning("MongoDB가 비활성화되어 있습니다.")
                return {"message": "MongoDB가 비활성화되어 있습니다", "data": None}
            
            db = get_db()
            if db is None:
                logger.warning("MongoDB 연결 실패")
                return {"message": "MongoDB 연결 실패", "data": None}
            
            # 날짜 설정
            if date_str is None:
                date_str = datetime.now().strftime('%Y-%m-%d')
            
            # daily_stock_data에서 조회
            daily_doc = db.daily_stock_data.find_one(
                {"date": date_str},
                {
                    "stocks": 1,
                    "recommendations": 1,
                    "fred_indicators": 1,
                    "yfinance_indicators": 1,
                    "date": 1
                }
            )
            
            if not daily_doc:
                return {
                    "message": f"{date_str} 날짜의 데이터를 찾을 수 없습니다",
                    "data": None
                }
            
            # 추천 종목만 필터링
            recommendations = daily_doc.get("recommendations", {})
            recommended_tickers = [
                ticker for ticker, rec in recommendations.items()
                if rec.get("is_recommended", False)
            ]
            
            return {
                "message": f"{date_str} 날짜의 통합 데이터 조회 성공",
                "date": date_str,
                "data": {
                    "stocks": daily_doc.get("stocks", {}),
                    "recommendations": recommendations,
                    "recommended_tickers": recommended_tickers,
                    "recommended_count": len(recommended_tickers),
                    "fred_indicators": daily_doc.get("fred_indicators", {}),
                    "yfinance_indicators": daily_doc.get("yfinance_indicators", {})
                }
            }
        except Exception as e:
            logger.error(f"날짜별 통합 조회 중 오류 발생: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {"message": f"조회 중 오류 발생: {str(e)}", "data": None}
    
    def get_stock_recommendation_history_from_mongodb(
        self, 
        ticker: str, 
        start_date: str = None, 
        end_date: str = None,
        only_recommended: bool = False
    ):
        """
        종목별 시계열 조회: stock_recommendations에서 특정 종목의 추천 이력 조회
        
        Args:
            ticker: 조회할 종목 티커 (예: "AAPL")
            start_date: 시작 날짜 (YYYY-MM-DD 형식). None이면 30일 전
            end_date: 종료 날짜 (YYYY-MM-DD 형식). None이면 오늘
            only_recommended: True면 추천된 날짜만 조회
        
        Returns:
            dict: {
                "ticker": str,
                "history": [...],  # 추천 이력 리스트
                "total_count": int,
                "recommended_count": int
            }
        """
        try:
            from app.core.config import settings
            
            # MongoDB 사용 여부 확인
            use_mongodb = settings.is_mongodb_enabled()
            if not use_mongodb:
                logger.warning("MongoDB가 비활성화되어 있습니다.")
                return {"message": "MongoDB가 비활성화되어 있습니다", "history": []}
            
            db = get_db()
            if db is None:
                logger.warning("MongoDB 연결 실패")
                return {"message": "MongoDB 연결 실패", "history": []}
            
            # 날짜 설정
            if end_date is None:
                end_date = datetime.now().strftime('%Y-%m-%d')
            if start_date is None:
                start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            
            # 날짜를 datetime 객체로 변환
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            
            # 쿼리 구성
            query = {
                "ticker": ticker,
                "date": {
                    "$gte": start_dt,
                    "$lte": end_dt
                },
                "user_id": None  # 전역 추천만
            }
            
            if only_recommended:
                query["is_recommended"] = True
            
            # stock_recommendations에서 조회 (인덱스 활용)
            cursor = db.stock_recommendations.find(query).sort("date", 1)
            
            history = []
            for doc in cursor:
                # ObjectId를 문자열로 변환
                doc["_id"] = str(doc["_id"])
                # date를 문자열로 변환
                if isinstance(doc.get("date"), datetime):
                    doc["date"] = doc["date"].strftime('%Y-%m-%d')
                history.append(doc)
            
            # 통계 계산
            recommended_count = sum(1 for h in history if h.get("is_recommended", False))
            
            return {
                "message": f"{ticker} 종목의 추천 이력 조회 성공",
                "ticker": ticker,
                "start_date": start_date,
                "end_date": end_date,
                "history": history,
                "total_count": len(history),
                "recommended_count": recommended_count
            }
        except Exception as e:
            logger.error(f"종목별 시계열 조회 중 오류 발생: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {"message": f"조회 중 오류 발생: {str(e)}", "history": []}
    
    def get_recommended_stocks_by_date_range_from_mongodb(
        self,
        start_date: str,
        end_date: str = None
    ):
        """
        날짜 범위별 추천 종목 집계: daily_stock_data에서 날짜 범위의 추천 종목 조회
        
        Args:
            start_date: 시작 날짜 (YYYY-MM-DD 형식)
            end_date: 종료 날짜 (YYYY-MM-DD 형식). None이면 오늘
        
        Returns:
            dict: {
                "date_range": {"start": str, "end": str},
                "daily_recommendations": [
                    {"date": str, "tickers": [...], "count": int},
                    ...
                ],
                "total_recommended_days": int,
                "most_recommended_tickers": {...}  # 종목별 추천 횟수
            }
        """
        try:
            from app.core.config import settings
            
            # MongoDB 사용 여부 확인
            use_mongodb = settings.is_mongodb_enabled()
            if not use_mongodb:
                logger.warning("MongoDB가 비활성화되어 있습니다.")
                return {"message": "MongoDB가 비활성화되어 있습니다", "data": None}
            
            db = get_db()
            if db is None:
                logger.warning("MongoDB 연결 실패")
                return {"message": "MongoDB 연결 실패", "data": None}
            
            # 날짜 설정
            if end_date is None:
                end_date = datetime.now().strftime('%Y-%m-%d')
            
            # daily_stock_data에서 날짜 범위 조회
            cursor = db.daily_stock_data.find({
                "date": {
                    "$gte": start_date,
                    "$lte": end_date
                },
                "recommendations": {"$exists": True}  # recommendations 필드가 있는 문서만
            }).sort("date", 1)
            
            daily_recommendations = []
            ticker_count = {}  # 종목별 추천 횟수 집계
            
            for doc in cursor:
                date_str = doc.get("date")
                recommendations = doc.get("recommendations", {})
                
                # 추천 종목만 필터링
                recommended_tickers = [
                    ticker for ticker, rec in recommendations.items()
                    if rec.get("is_recommended", False)
                ]
                
                if recommended_tickers:
                    daily_recommendations.append({
                        "date": date_str,
                        "tickers": recommended_tickers,
                        "count": len(recommended_tickers)
                    })
                    
                    # 종목별 추천 횟수 집계
                    for ticker in recommended_tickers:
                        ticker_count[ticker] = ticker_count.get(ticker, 0) + 1
            
            # 가장 많이 추천된 종목 정렬
            most_recommended = dict(sorted(
                ticker_count.items(),
                key=lambda x: x[1],
                reverse=True
            ))
            
            return {
                "message": f"{start_date} ~ {end_date} 기간의 추천 종목 집계 완료",
                "date_range": {
                    "start": start_date,
                    "end": end_date
                },
                "daily_recommendations": daily_recommendations,
                "total_recommended_days": len(daily_recommendations),
                "most_recommended_tickers": most_recommended,
                "total_unique_tickers": len(ticker_count)
            }
        except Exception as e:
            logger.error(f"날짜 범위별 추천 종목 집계 중 오류 발생: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {"message": f"집계 중 오류 발생: {str(e)}", "data": None}
    
    def verify_mongodb_sync(self, date_str: str = None):
        """
        두 컬렉션(daily_stock_data.recommendations와 stock_recommendations)의 동기화 상태 확인
        
        Args:
            date_str: 확인할 날짜 (YYYY-MM-DD 형식). None이면 오늘 날짜 사용
        
        Returns:
            dict: {
                "date": str,
                "daily_stock_data_count": int,
                "stock_recommendations_count": int,
                "sync_status": str,  # "synced" | "mismatch" | "missing"
                "details": {...}
            }
        """
        try:
            from app.core.config import settings
            
            # MongoDB 사용 여부 확인
            use_mongodb = settings.is_mongodb_enabled()
            if not use_mongodb:
                return {"message": "MongoDB가 비활성화되어 있습니다", "sync_status": "disabled"}
            
            db = get_db()
            if db is None:
                return {"message": "MongoDB 연결 실패", "sync_status": "error"}
            
            # 날짜 설정
            if date_str is None:
                date_str = datetime.now().strftime('%Y-%m-%d')
            
            # daily_stock_data에서 recommendations 조회
            daily_doc = db.daily_stock_data.find_one(
                {"date": date_str},
                {"recommendations": 1}
            )
            
            # stock_recommendations에서 해당 날짜의 데이터 조회
            rec_date = datetime.strptime(date_str, '%Y-%m-%d')
            stock_recs = list(db.stock_recommendations.find({
                "date": rec_date,
                "user_id": None
            }))
            
            # 비교
            daily_tickers = set(daily_doc.get("recommendations", {}).keys()) if daily_doc else set()
            stock_rec_tickers = {rec["ticker"] for rec in stock_recs}
            
            # 동기화 상태 확인
            if daily_tickers == stock_rec_tickers:
                sync_status = "synced"
                message = "두 컬렉션이 동기화되어 있습니다"
            elif len(daily_tickers) == 0 and len(stock_rec_tickers) == 0:
                sync_status = "missing"
                message = "두 컬렉션 모두 데이터가 없습니다"
            else:
                sync_status = "mismatch"
                message = "두 컬렉션 간 불일치가 있습니다"
            
            # 차이점 상세 정보
            only_in_daily = daily_tickers - stock_rec_tickers
            only_in_stock_rec = stock_rec_tickers - daily_tickers
            
            return {
                "message": message,
                "date": date_str,
                "sync_status": sync_status,
                "daily_stock_data_count": len(daily_tickers),
                "stock_recommendations_count": len(stock_rec_tickers),
                "details": {
                    "daily_tickers": sorted(list(daily_tickers)),
                    "stock_rec_tickers": sorted(list(stock_rec_tickers)),
                    "only_in_daily": sorted(list(only_in_daily)),
                    "only_in_stock_rec": sorted(list(only_in_stock_rec)),
                    "common_tickers": sorted(list(daily_tickers & stock_rec_tickers))
                }
            }
        except Exception as e:
            logger.error(f"동기화 확인 중 오류 발생: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {"message": f"확인 중 오류 발생: {str(e)}", "sync_status": "error"}