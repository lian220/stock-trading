import pandas as pd
# stock.py가 scripts/utils/로 이동했으므로 경로 수정
from scripts.utils.stock import collect_economic_data
import numpy as np
from datetime import datetime, timedelta
import pytz
from app.core.config import settings
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from app.services.stock_recommendation_service import StockRecommendationService
from app.services.stock_service import get_stock_to_ticker_mapping, get_ticker_to_stock_mapping
from app.utils.slack_notifier import slack_notifier
import httpx
import time
import os
from app.db.mongodb import get_db
import logging

logger = logging.getLogger(__name__)


# ============================================================
# 비즈니스 로직 함수
# ============================================================

def fetch_economic_data(start_date: str = None, end_date: str = None):
    """
    경제 데이터를 조회하고 반환합니다.
    
    Args:
        start_date: 수집 시작 날짜 (YYYY-MM-DD 형식, None이면 자동 계산)
        end_date: 수집 종료 날짜 (YYYY-MM-DD 형식, None이면 오늘)
    
    Returns:
        dict: {
            'new_data': DataFrame,  # 수집된 데이터
            'start_date': str,      # 수집 시작 날짜
            'storage_end_date': str,  # 저장 종료 날짜
            'stock_columns': list,   # 활성화된 주식 컬럼
            'previous_data': dict,   # 이전 데이터
            'today': str,           # 오늘 날짜
            'should_skip': bool     # 수집을 건너뛸지 여부
        }
    """
    # 미국 장 마감 여부 확인 (뉴욕 시간 기준으로 정확히 체크)
    now_korea = datetime.now(pytz.timezone('Asia/Seoul'))
    now_ny = datetime.now(pytz.timezone('America/New_York'))
    
    korea_time = now_korea.strftime('%H:%M')
    ny_hour = now_ny.hour
    ny_minute = now_ny.minute
    ny_weekday = now_ny.weekday()  # 0=월요일, 6=일요일
    
    # 미국 주식 시장은 평일(월-금) 9:30 AM - 4:00 PM ET
    is_weekday = 0 <= ny_weekday <= 4  # 월요일에서 금요일까지
    is_market_open_time = (
        (ny_hour == 9 and ny_minute >= 30) or
        (10 <= ny_hour < 16) or
        (ny_hour == 16 and ny_minute == 0)
    )
    
    is_market_hours = is_weekday and is_market_open_time
    
    # 미국 주식 시장이 열려 있는 경우에만 데이터 수집 연기
    if is_market_hours:
        print(f"현재 시간 (한국: {korea_time}, 뉴욕: {now_ny.strftime('%Y-%m-%d %H:%M')})은 미국 주식 시장 운영 시간입니다.")
        print(f"장 마감 후(뉴욕 시간 16:00 이후)에 데이터를 수집합니다.")
        return {'should_skip': True}
    
    print(f"현재 시간 (한국: {korea_time}, 뉴욕: {now_ny.strftime('%Y-%m-%d %H:%M')}) - 미국 장 마감 시간이므로 데이터 수집을 진행합니다.")

    # 한국 시간대 기준으로 현재 날짜 계산 (컨테이너 시간대 문제 방지)
    korea_tz = pytz.timezone('Asia/Seoul')
    now_korea_dt = datetime.now(korea_tz)
    today = now_korea_dt.strftime('%Y-%m-%d')
    yesterday = (now_korea_dt - timedelta(days=1)).strftime('%Y-%m-%d')
    
    # 날짜 범위가 지정된 경우 사용, 아니면 자동 계산
    if start_date and end_date:
        # 사용자가 지정한 날짜 범위 사용
        print(f"지정된 날짜 범위로 수집: {start_date} ~ {end_date}")
        collection_start_date = start_date
        collection_end_date = end_date
        storage_end_date = end_date  # 지정된 범위는 모두 저장
    else:
        # 기본 동작: 마지막 수집 날짜 조회 (다음 수집 시작일을 반환)
        next_collection_date = get_last_updated_date()
        
        # 오늘까지 수집해야 하므로, 수집 시작일을 조정
        # next_collection_date가 오늘보다 크거나 같으면, 오늘부터 수집
        if next_collection_date >= today:
            collection_start_date = today
            print(f"다음 수집 시작일({next_collection_date})이 오늘({today})보다 크거나 같으므로, 오늘 데이터부터 수집합니다.")
        else:
            collection_start_date = next_collection_date
        
        collection_end_date = today
        # 오늘 데이터도 저장 (API 호출 시 오늘 데이터 수집 및 저장)
        storage_end_date = today
    
    start_date = collection_start_date
    print(f"한국 시간 기준 오늘: {today}, 어제: {yesterday}, 수집 시작일: {start_date}, 수집 종료일: {collection_end_date}")
    
    # 수집 시작일이 종료일보다 크면 수집할 데이터가 없음
    if start_date > collection_end_date:
        print(f"수집 시작일({start_date})이 종료일({collection_end_date})보다 큽니다. 수집할 데이터가 없습니다.")
        return {'should_skip': True}
    
    # 이전 데이터 가져오기 (마지막 수집 날짜의 데이터) - MongoDB에서 조회
    previous_date = (datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
    previous_data = {}
    try:
        db = get_db()
        if db is not None:
            prev_doc = db.daily_stock_data.find_one({"date": previous_date})
            if prev_doc:
                # MongoDB 문서를 API 응답 형식으로 변환
                previous_data = {"날짜": prev_doc.get("date")}
                # FRED 지표
                for key, value in prev_doc.get("fred_indicators", {}).items():
                    previous_data[key] = value
                # Yahoo Finance 지표
                for key, value in prev_doc.get("yfinance_indicators", {}).items():
                    previous_data[key] = value
                # 주가 데이터 (티커를 그대로 사용 - categorize_data_for_mongodb에서 티커도 인식함)
                stocks_count = 0
                for ticker, stock_data in prev_doc.get("stocks", {}).items():
                    if isinstance(stock_data, dict):
                        previous_data[ticker] = stock_data.get("close_price")
                    else:
                        previous_data[ticker] = stock_data
                    stocks_count += 1
                
                if stocks_count > 0:
                    logger.debug(f"이전 데이터({previous_date})에서 주식 {stocks_count}개 로드 완료")
                else:
                    logger.warning(f"이전 데이터({previous_date})에 stocks 필드가 없거나 비어있음")
    except Exception as e:
        logger.warning(f"이전 데이터 조회 중 오류 발생: {str(e)}")
    
    # stock_columns를 최신 상태로 업데이트 (매번 실행 시 최신 활성화 상태 반영)
    stock_columns = get_active_stock_columns()
    
    # 데이터 수집 (오늘까지 수집)
    result = collect_economic_data(start_date=start_date, end_date=collection_end_date)
    
    # 반환값이 튜플인 경우 (공매도 데이터 포함)와 DataFrame만 반환하는 경우 처리
    if isinstance(result, tuple):
        new_data, short_interest_data = result
    else:
        new_data = result
        short_interest_data = {}
    
    # 디버깅: 수집된 데이터 확인
    print("\n=== 수집된 데이터 확인 ===")
    print(f"활성화된 주식 컬럼 수: {len(stock_columns)}")
    if new_data is not None and not new_data.empty:
        for date_idx in new_data.index[:3]:  # 처음 3개 날짜만
            date_str = date_idx.strftime('%Y-%m-%d') if isinstance(date_idx, pd.Timestamp) else date_idx
            print(f"날짜: {date_str}")
            for stock in stock_columns[:5]:  # 몇 개의 주가만 출력
                if stock in new_data.columns:
                    print(f"  {stock}: {new_data.loc[date_idx, stock]}")
    
    if new_data is None or new_data.empty:
        print("수집할 새 데이터가 없습니다.")
        return {'should_skip': True}
    
    return {
        'should_skip': False,
        'new_data': new_data,
        'short_interest_data': short_interest_data,  # 공매도 데이터 추가
        'start_date': start_date,
        'storage_end_date': storage_end_date,
        'stock_columns': stock_columns,
        'previous_data': previous_data,
        'today': today
    }


def categorize_data_for_mongodb(data_dict):
    """
    데이터를 FRED, Yahoo Finance, Stocks로 분류합니다.
    
    Args:
        data_dict: 분류할 데이터 딕셔너리
    
    Returns:
        dict: {
            'fred_indicators': {...},
            'yfinance_indicators': {...},
            'stocks': {...}
        }
    """
    try:
        db = get_db()
        if db is None:
            logger.warning("MongoDB 연결 실패 - 데이터 분류 불가")
            return {'fred_indicators': {}, 'yfinance_indicators': {}, 'stocks': {}}
        
        # MongoDB에서 각 카테고리의 이름 목록 가져오기
        fred_names = set()
        yfinance_names = set()
        stock_names = set()
        
        # FRED 지표 이름
        for doc in db.fred_indicators.find({"is_active": True}):
            if doc.get("name"):
                fred_names.add(doc["name"])
        
        # Yahoo Finance 지표 이름
        for doc in db.yfinance_indicators.find({"is_active": True}):
            if doc.get("name"):
                yfinance_names.add(doc["name"])
        
        # 주식 이름 (한글 주식명)
        for doc in db.stocks.find({"is_active": True}):
            if doc.get("stock_name"):
                stock_names.add(doc["stock_name"])
        
        # 티커 -> 한글 주식명 매핑 생성 (티커도 stocks로 분류하기 위해)
        ticker_to_stock = get_ticker_to_stock_mapping(exclude_etf=False)
        # 티커 목록 생성
        tickers = set(ticker_to_stock.keys())
        
        # 데이터 분류
        categorized = {
            'fred_indicators': {},
            'yfinance_indicators': {},
            'stocks': {}
        }
        
        # 디버깅: 분류되지 않은 주식 데이터 추적
        unclassified_stocks = []
        classified_stocks = []
        classified_by_ticker = []
        classified_by_stock_name = []
        
        for key, value in data_dict.items():
            if key in fred_names:
                categorized['fred_indicators'][key] = value
            elif key in yfinance_names:
                categorized['yfinance_indicators'][key] = value
            elif key in tickers:
                # 티커인 경우를 먼저 확인 (티커와 주식명이 겹칠 수 있으므로)
                categorized['stocks'][key] = value
                classified_stocks.append(key)
                classified_by_ticker.append(key)
            elif key in stock_names:
                # 한글 주식명인 경우 (티커가 아닌 경우만)
                categorized['stocks'][key] = value
                classified_stocks.append(key)
                classified_by_stock_name.append(key)
            # 분류되지 않은 데이터는 무시 (로그만 남김)
            else:
                # 주식으로 보이는 데이터는 별도로 추적
                if key not in ['날짜']:  # 날짜는 제외
                    unclassified_stocks.append(key)
                logger.debug(f"분류되지 않은 데이터: {key}")
        
        # 분류되지 않은 데이터가 있으면 경고 로그만 출력
        if unclassified_stocks:
            logger.warning(f"분류되지 않은 주식 데이터 {len(unclassified_stocks)}개 발견: {unclassified_stocks[:10]}")
        
        logger.debug(f"데이터 분류 완료: FRED {len(categorized['fred_indicators'])}개, "
                    f"Yahoo Finance {len(categorized['yfinance_indicators'])}개, "
                    f"Stocks {len(categorized['stocks'])}개")
        
        return categorized
    except Exception as e:
        logger.error(f"데이터 분류 중 오류 발생: {str(e)}")
        return {'fred_indicators': {}, 'yfinance_indicators': {}, 'stocks': {}}


def save_economic_data(new_data, start_date, storage_end_date, stock_columns, previous_data, today, short_interest_data=None):
    """
    조회한 경제 데이터를 데이터베이스에 저장합니다.
    
    Args:
        new_data: 수집된 데이터 DataFrame
        start_date: 수집 시작 날짜
        storage_end_date: 저장 종료 날짜
        stock_columns: 활성화된 주식 컬럼 리스트
        previous_data: 이전 데이터 딕셔너리
        today: 오늘 날짜
    
    Returns:
        dict: {'saved_count': int, 'total_records': int}
    """
    # 날짜 범위 생성 (시작일부터 어제까지만)
    all_dates = pd.date_range(start=start_date, end=storage_end_date)
    saved_count = 0
    
    # 재시도 로직이 포함된 데이터 저장 함수 (MongoDB 전용)
    def save_data_with_retry(date_str, data_dict, max_retries=3, short_interest_data_for_date=None):
        """MongoDB에 데이터 저장을 재시도하며 처리"""
        # 데이터 딕셔너리 검증
        if not data_dict:
            print(f"⚠️ {date_str}: 저장할 데이터가 없습니다 (data_dict가 비어있음)")
            return False
        
        # 날짜는 필수
        if not date_str:
            print(f"⚠️ 날짜가 없어서 저장할 수 없습니다")
            return False
        
        for attempt in range(max_retries):
            try:
                db = get_db()
                if db is None:
                    logger.error(f"MongoDB 연결 실패: {date_str}")
                    return False
                
                # 데이터 분류
                categorized = categorize_data_for_mongodb(data_dict)
                
                # 분류 결과 로깅 (디버그 레벨)
                logger.debug(f"{date_str} 데이터 분류: FRED {len(categorized['fred_indicators'])}개, "
                           f"Yahoo Finance {len(categorized['yfinance_indicators'])}개, "
                           f"Stocks {len(categorized['stocks'])}개")
                
                # stocks 필드에 공매도 데이터 통합
                # 티커 <-> 한글 주식명 매핑 생성
                stock_to_ticker = get_stock_to_ticker_mapping(exclude_etf=False)
                ticker_to_stock = get_ticker_to_stock_mapping(exclude_etf=False)
                
                # stocks 필드를 티커 기반으로 변환 (None 값 필터링)
                stocks_with_short_interest = {}
                ticker_not_found_stocks = []
                none_price_count = 0
                
                for key, price in categorized['stocks'].items():
                    # None 값은 저장하지 않음
                    if price is None:
                        none_price_count += 1
                        continue
                    
                    # key가 티커인지 한글 주식명인지 확인
                    if key in ticker_to_stock:
                        # 이미 티커인 경우
                        ticker = key
                    else:
                        # 한글 주식명인 경우 티커로 변환
                        ticker = stock_to_ticker.get(key)
                    
                    if ticker:
                        # 티커를 키로 사용
                        stocks_with_short_interest[ticker] = {
                            'close_price': price
                        }
                    else:
                        ticker_not_found_stocks.append(key)
                
                if none_price_count > 0:
                    logger.warning(f"{date_str}: None 값 가격 {none_price_count}개는 저장하지 않습니다.")
                
                if ticker_not_found_stocks:
                    logger.warning(f"{date_str}: 티커를 찾을 수 없는 주식명 {len(ticker_not_found_stocks)}개: {ticker_not_found_stocks[:5]}")
                
                # 공매도 데이터 통합 (티커 기반)
                if short_interest_data_for_date:
                    logger.debug(f"{date_str}: 공매도 데이터 {len(short_interest_data_for_date)}개 티커 통합")
                    for ticker, stock_data in short_interest_data_for_date.items():
                        if ticker in stocks_with_short_interest:
                            # 기존 close_price 가격과 공매도 데이터 통합
                            stocks_with_short_interest[ticker].update(stock_data)
                        else:
                            # 가격 데이터가 없어도 공매도 데이터만 저장
                            stocks_with_short_interest[ticker] = stock_data
                
                logger.debug(f"{date_str}: 최종 저장될 Stocks 수: {len(stocks_with_short_interest)}개")
                
                # MongoDB에 upsert (구조화된 형태로)
                mongo_doc = {
                    "date": date_str,
                    "fred_indicators": categorized['fred_indicators'],
                    "yfinance_indicators": categorized['yfinance_indicators'],
                    "stocks": stocks_with_short_interest,
                    "updated_at": datetime.utcnow()
                }
                
                db.daily_stock_data.update_one(
                    {"date": date_str},
                    {
                        "$set": mongo_doc,
                        "$setOnInsert": {
                            "created_at": datetime.utcnow()
                        }
                    },
                    upsert=True
                )
                print(f"  ✅ MongoDB 저장 성공: {date_str}")
                return True  # 성공
                
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"  ⚠️ {date_str} 저장 실패 (시도 {attempt+1}/{max_retries}): {str(e)}. 재시도...")
                    time.sleep(2)  # 재시도 전 대기
                else:
                    print(f"  ❌ {date_str} 저장 최종 실패: {str(e)}")
                    import traceback
                    print(traceback.format_exc())
                    return False
        return False
    
    # 어제까지 날짜에 대해서만 처리
    for date in all_dates:
        try:
            date_str = date.strftime('%Y-%m-%d')
            
            # 해당 날짜의 데이터가 수집되었는지 확인
            if date in new_data.index:
                row = new_data.loc[date]
                print(f"\n== {date_str} 데이터가 있음 (저장 대상) ==")
                # 주요 주가 데이터 몇 개 출력
                for stock in stock_columns[:5]:
                    if stock in row.index:
                        print(f"  원본 {stock}: {row[stock]}")
            else:
                print(f"\n== {date_str} 데이터가 없음, 이전 데이터 사용 (저장 대상) ==")
                row = pd.Series(dtype='object')
            
            # 데이터 딕셔너리 생성
            data_dict = {}
            if date in new_data.index:
                for col_name, value in row.items():
                    if not pd.isna(value):  # null이 아닌 값만 포함
                        data_dict[col_name] = value
            
            # 이전 데이터로 null 값 채우기 (모든 컬럼 대상)
            for col_name, value in previous_data.items():
                if col_name != "날짜" and col_name not in data_dict and value is not None:
                    data_dict[col_name] = value
            
            # 중요: 이전 데이터에 주식이 없거나 적은 경우, 더 이전 날짜의 데이터에서 가격을 찾아서 추가
            from app.services.stock_service import get_active_tickers
            active_tickers = get_active_tickers(exclude_etf=False)
            ticker_to_stock = get_ticker_to_stock_mapping(exclude_etf=False)
            
            # data_dict에 없는 티커들을 확인하고 이전 날짜 데이터에서 가격 찾기
            missing_tickers = [ticker for ticker in active_tickers if ticker not in data_dict]
            if missing_tickers:
                logger.debug(f"{date_str}: 활성화된 주식 중 data_dict에 없는 티커 {len(missing_tickers)}개 발견")
                
                # 더 이전 날짜의 데이터에서 가격 찾기 (최대 30일 전까지)
                db = get_db()
                if db:
                    found_count = 0
                    for days_back in range(1, 31):  # 1일 전부터 30일 전까지
                        search_date = (datetime.strptime(date_str, '%Y-%m-%d') - timedelta(days=days_back)).strftime('%Y-%m-%d')
                        prev_doc = db.daily_stock_data.find_one({"date": search_date})
                        
                        if prev_doc:
                            prev_stocks = prev_doc.get("stocks", {})
                            for ticker in missing_tickers[:]:  # 복사본으로 순회
                                if ticker in prev_stocks:
                                    stock_data = prev_stocks[ticker]
                                    if isinstance(stock_data, dict):
                                        price = stock_data.get("close_price")
                                    else:
                                        price = stock_data
                                    
                                    if price is not None:
                                        data_dict[ticker] = price
                                        missing_tickers.remove(ticker)
                                        found_count += 1
                                        if found_count >= len(missing_tickers):
                                            break
                        
                        if not missing_tickers:  # 모두 찾았으면 중단
                            break
                    
                    if found_count > 0:
                        logger.debug(f"{date_str}: {found_count}개 티커의 가격을 이전 날짜 데이터에서 찾아서 추가했습니다.")
                    if missing_tickers:
                        logger.warning(f"{date_str}: {len(missing_tickers)}개 티커는 가격을 찾지 못했습니다: {missing_tickers[:10]}")
            
            # 데이터 딕셔너리 검증
            if not data_dict:
                print(f"⚠️ {date_str}: 저장할 데이터가 없어서 건너뜁니다.")
                continue
            
            print(f"\n📊 {date_str} 데이터 준비 완료:")
            
            # 재시도 로직이 포함된 저장 함수 호출
            date_short_interest = short_interest_data.get(date_str, {}) if short_interest_data else {}
            if save_data_with_retry(date_str, data_dict, short_interest_data_for_date=date_short_interest):
                # 현재 데이터를 다음 날짜 처리를 위한 이전 데이터로 설정
                if data_dict:  # 데이터가 있는 경우에만
                    previous_data = {"날짜": date_str}
                    previous_data.update(data_dict)
                
                # 주요 주가 데이터 출력
                for stock in stock_columns[:5]:
                    if stock in data_dict:
                        print(f"  저장 전 {stock}: {data_dict[stock]}")
                
                saved_count += 1
            
        except Exception as e:
            # 개별 날짜 처리 중 에러가 발생해도 계속 진행
            print(f"{date_str} 처리 중 오류 발생 (다음 날짜로 계속 진행): {str(e)}")
            continue
    
    # 오늘 날짜 데이터는 수집했지만 저장하지 않는다고 표시
    if datetime.now().date() in new_data.index:
        print(f"\n== {today} 데이터는 수집했지만 저장하지 않습니다 ==")
    
    total_records = len(all_dates)
    print(f"총 {total_records}개 날짜 중 {saved_count}개가 처리되었습니다.")
    
    return {
        'saved_count': saved_count,
        'total_records': total_records
    }


async def update_economic_data_in_background(start_date: str = None, end_date: str = None):
    """
    백그라운드에서 경제 지표 데이터를 업데이트
    
    Args:
        start_date: 수집 시작 날짜 (YYYY-MM-DD 형식, None이면 자동 계산)
        end_date: 수집 종료 날짜 (YYYY-MM-DD 형식, None이면 오늘)
    """
    try:
        print("경제 지표 및 주가 데이터 업데이트 작업 시작...")
        
        # 1. 데이터 조회
        fetch_result = fetch_economic_data(start_date=start_date, end_date=end_date)
        
        # 조회를 건너뛰어야 하는 경우 (시장 운영 시간, 데이터 없음 등)
        if fetch_result.get('should_skip'):
            return {"success": True, "total_records": 0, "updated_records": 0}
        
        # 2. 데이터 저장
        save_result = save_economic_data(
            new_data=fetch_result['new_data'],
            start_date=fetch_result['start_date'],
            storage_end_date=fetch_result['storage_end_date'],
            stock_columns=fetch_result['stock_columns'],
            previous_data=fetch_result['previous_data'],
            today=fetch_result['today'],
            short_interest_data=fetch_result.get('short_interest_data', {})
        )
        
        # 3. 공매도 정보 슬랙 전송
        short_interest_data = fetch_result.get('short_interest_data', {})
        if short_interest_data:
            try:
                # 티커 -> 주식명 매핑 생성
                ticker_to_stock_mapping = get_ticker_to_stock_mapping(exclude_etf=False)
                # 공매도 정보 슬랙 전송
                slack_notifier.send_short_interest_notification(
                    short_interest_data=short_interest_data,
                    ticker_to_stock_mapping=ticker_to_stock_mapping
                )
            except Exception as slack_e:
                logger.warning(f"공매도 정보 슬랙 전송 중 오류 발생: {str(slack_e)}")
        
        # 참고: 기술적 지표 생성 및 뉴스 감정 분석은 별도 API로 분리됨
        # - 기술적 지표: POST /recommended-stocks/generate-technical-recommendations
        # - 감정 분석: POST /recommended-stocks/analyze-news-sentiment
        # - 통합 분석: POST /recommended-stocks/generate-complete-analysis
        
        return {
            "success": True,
            "message": "경제 및 주식 데이터 업데이트 완료",
            "total_records": save_result['total_records'],
            "updated_records": save_result['saved_count']
        }
    except Exception as e:
        print(f"경제 데이터 업데이트 중 오류 발생: {str(e)}")
        import traceback
        print(traceback.format_exc())
        # 에러가 발생해도 앱이 계속 실행되도록 예외를 다시 발생시키지 않고 로그만 남김
        return {
            "success": False,
            "message": f"경제 데이터 업데이트 중 오류 발생: {str(e)}",
            "total_records": 0,
            "updated_records": 0
        }


# ============================================================
# 데이터 조회 및 헬퍼 함수
# ============================================================

def get_last_updated_date():
    """
    MongoDB의 daily_stock_data 컬렉션에서 마지막으로 수집된 날짜를 조회합니다.
    """
    try:
        # MongoDB에서 조회
        db = get_db()
        if db is None:
            logger.error("MongoDB 연결 실패. 기본 시작 날짜로 설정합니다.")
            return "2006-01-01"
        
        # daily_stock_data 컬렉션에서 마지막 날짜 조회
        last_doc = db.daily_stock_data.find_one(
            sort=[("date", -1)]
        )
        
        if last_doc and "date" in last_doc:
            date = last_doc["date"]
            
            # date가 문자열인 경우 datetime으로 변환
            if isinstance(date, str):
                last_date = datetime.fromisoformat(date.replace('Z', '+00:00'))
            elif isinstance(date, datetime):
                last_date = date
            else:
                # 다른 타입인 경우 변환 시도
                last_date = pd.to_datetime(date).to_pydatetime()
            
            # 다음 날짜 반환
            next_date = (last_date + timedelta(days=1)).strftime('%Y-%m-%d')
            print(f"마지막 수집 날짜 (MongoDB daily_stock_data): {last_date.strftime('%Y-%m-%d')}, 다음 수집 시작일: {next_date}")
            return next_date
        else:
            # 데이터가 없으면 기본 시작 날짜 반환 (2006-01-01)
            print("MongoDB daily_stock_data 컬렉션에 데이터가 없습니다. 기본 시작 날짜(2006-01-01)로 설정합니다.")
            return "2006-01-01"
            
    except Exception as e:
        print(f"마지막 수집 날짜 조회 중 오류 발생: {str(e)}")
        import traceback
        print(traceback.format_exc())
        # 오류 발생 시 기본 시작 날짜 반환
        return "2006-01-01"



def get_active_stock_columns():
    """
    MongoDB의 stocks, fred_indicators, yfinance_indicators 컬렉션에서 활성화된 주식 및 지표 목록을 가져옵니다.
    """
    try:
        from app.core.config import settings
        
        # MongoDB 사용 여부 확인 (config.py를 통해서만 접근)
        use_mongodb = settings.is_mongodb_enabled()
        
        if not use_mongodb:
            print("⚠️ 경고: USE_MONGODB가 False로 설정되어 있습니다. 기본 목록을 사용합니다.")
            return _get_default_stock_columns()
        
        db = get_db()
        if db is None:
            print("⚠️ 경고: MongoDB 연결 실패 (get_db()가 None 반환). 기본 목록을 사용합니다.")
            print("   - USE_MONGODB 설정을 확인하세요.")
            print("   - MongoDB 연결 정보를 확인하세요.")
            return _get_default_stock_columns()
        
        # MongoDB에서 활성화된 주식 목록 가져오기 (stocks 컬렉션)
        try:
            from app.services.stock_service import get_active_stock_names
            active_stock_names = get_active_stock_names(exclude_etf=False)
        except Exception as e:
            logger.warning(f"⚠️ 경고: stocks 컬렉션 조회 실패: {str(e)}. 기본 목록을 사용합니다.")
            return _get_default_stock_columns()
        
        # MongoDB에서 활성화된 시장 지표 및 ETF 목록 가져오기
        # fred_indicators와 yfinance_indicators 컬렉션에서 조회
        try:
            economic_and_etf_columns = []
            # FRED 지표
            active_fred = db.fred_indicators.find({"is_active": True})
            for indicator in active_fred:
                economic_and_etf_columns.append(indicator.get("name"))
            # Yahoo Finance 지표
            active_yfinance = db.yfinance_indicators.find({"is_active": True})
            for indicator in active_yfinance:
                economic_and_etf_columns.append(indicator.get("name"))
        except Exception as e:
            print(f"⚠️ 경고: 지표 컬렉션 조회 실패: {str(e)}. 기본 목록을 사용합니다.")
            return _get_default_stock_columns()
        
        # 활성화된 주식 + 경제 지표/ETF 합치기
        all_stock_columns = economic_and_etf_columns + active_stock_names
        
        if len(all_stock_columns) == 0:
            print("⚠️ 경고: 활성화된 주식 및 지표가 없습니다. 기본 목록을 사용합니다.")
            return _get_default_stock_columns()
        
        return all_stock_columns
    except Exception as e:
        print(f"⚠️ 경고: MongoDB 조회 실패: {str(e)}. 기본 목록을 사용합니다.")
        import traceback
        print(traceback.format_exc())
        return _get_default_stock_columns()


def _get_default_stock_columns():
    """
    기본 주식 컬럼 목록 반환 (fallback)
    ⚠️ 경고: 이 함수는 MongoDB 조회 실패 시에만 사용됩니다. 
    정상 동작 시에는 get_active_stock_columns()를 사용해야 합니다.
    """
    logger.warning("⚠️ 경고: 하드코딩된 기본 주식 컬럼 목록을 사용합니다. MongoDB 조회를 확인하세요.")
    return [
        "나스닥 종합지수", "S&P 500 지수", "금 가격", "달러 인덱스", "나스닥 100", 
        "S&P 500 ETF", "QQQ ETF", "러셀 2000 ETF", "다우 존스 ETF", "VIX 지수", 
        "닛케이 225", "상해종합", "항셍", "영국 FTSE", "독일 DAX", "프랑스 CAC 40", 
        "미국 전체 채권시장 ETF", "TIPS ETF", "투자등급 회사채 ETF", "달러/엔", "달러/위안",
        "미국 리츠 ETF", "SOXX ETF", "애플", "마이크로소프트", "아마존", "구글 A", "구글 C", "메타", 
        "테슬라", "엔비디아", "인텔", "마이크론", "브로드컴", 
        "텍사스 인스트루먼트", "AMD", "어플라이드 머티리얼즈",
        "셀레스티카", "버티브 홀딩스", "비스트라 에너지", "블룸에너지", "오클로", "팔란티어",
        "세일즈포스", "오라클", "앱플로빈", "팔로알토 네트웍스", "크라우드 스트라이크",
        "스노우플레이크", "TSMC", "크리도 테크놀로지 그룹 홀딩", "로빈후드", "일라이릴리",
        "월마트", "존슨앤존슨"
    ]

