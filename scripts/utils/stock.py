import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import numpy as np
import time
import logging
import sys
from pathlib import Path

# app 모듈 import를 위한 경로 추가
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from app.core.config import settings

# 로거 설정 (중복 핸들러 방지)
logger = logging.getLogger(__name__)
logger.propagate = False  # 부모 로거로 전파하지 않음 (중복 방지)
if not logger.handlers:  # 핸들러가 없을 때만 추가
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# FRED API Key 설정 (환경변수에서 가져오기)
api_key = settings.FRED_API_KEY or 'aedfbcd8ba091c740281c0bd8ca93b46'  # 기본값 유지 (레거시 호환)

# MongoDB에서 지표 정보를 동적으로 로드하는 함수
def load_indicators_from_mongodb():
    """
    MongoDB의 fred_indicators와 yfinance_indicators 컬렉션에서 활성화된 지표 정보를 로드합니다.
    
    Returns:
        tuple: (fred_indicators dict, yfinance_indicators dict)
            - fred_indicators: {code: name} 형태
            - yfinance_indicators: {name: ticker} 형태
    """
    try:
        from app.db.mongodb import get_db
        
        db = get_db()
        if db is None:
            logger.warning("MongoDB 연결 실패. 기본 지표 딕셔너리를 사용합니다.")
            return _get_default_fred_indicators(), _get_default_yfinance_indicators()
        
        # FRED 지표 조회
        fred_indicators = {}
        try:
            active_fred = db.fred_indicators.find({"is_active": True})
            for indicator in active_fred:
                code = indicator.get("code")
                name = indicator.get("name")
                if code and name:
                    fred_indicators[code] = name
        except Exception as e:
            logger.warning(f"fred_indicators 조회 실패: {e}")
        
        # Yahoo Finance 지표 조회
        yfinance_indicators = {}
        try:
            active_yfinance = db.yfinance_indicators.find({"is_active": True})
            for indicator in active_yfinance:
                ticker = indicator.get("ticker")
                name = indicator.get("name")
                if ticker and name:
                    yfinance_indicators[name] = ticker
        except Exception as e:
            logger.warning(f"yfinance_indicators 조회 실패: {e}")
        
        logger.info(f"MongoDB에서 지표 로드 완료: FRED {len(fred_indicators)}개, Yahoo Finance {len(yfinance_indicators)}개")
        return fred_indicators, yfinance_indicators
        
    except Exception as e:
        logger.warning(f"MongoDB에서 지표 로드 실패: {e}. 기본 지표 딕셔너리를 사용합니다.")
        return _get_default_fred_indicators(), _get_default_yfinance_indicators()


def _get_default_fred_indicators():
    """
    기본 FRED 지표 딕셔너리 (MongoDB 조회 실패 시 fallback용)
    ⚠️ 경고: 이 함수는 MongoDB 조회 실패 시에만 사용됩니다.
    정상 동작 시에는 load_indicators_from_mongodb()를 사용해야 합니다.
    """
    logger.warning("⚠️ 경고: 하드코딩된 기본 FRED 지표 딕셔너리를 사용합니다. MongoDB 조회를 확인하세요.")
    return {
        'T10YIE': '10년 기대 인플레이션율',
        'T10Y2Y': '장단기 금리차',
        'FEDFUNDS': '기준금리',
        'UMCSENT': '미시간대 소비자 심리지수',
        'UNRATE': '실업률',
        'DGS2': '2년 만기 미국 국채 수익률',
        'DGS10': '10년 만기 미국 국채 수익률',
        'STLFSI4': '금융스트레스지수',
        'PCE': '개인 소비 지출',
        'CPIAUCSL': '소비자 물가지수',
        'MORTGAGE5US': '5년 변동금리 모기지',
        'DTWEXM': '미국 달러 환율',
        'M2': '통화 공급량 M2',
        'TDSP': '가계 부채 비율',
        'GDPC1': 'GDP 성장률',
        'NASDAQCOM': '나스닥 종합지수'
    }


def _get_default_yfinance_indicators():
    """
    기본 Yahoo Finance 지표 딕셔너리 (MongoDB 조회 실패 시 fallback용)
    ⚠️ 경고: 이 함수는 MongoDB 조회 실패 시에만 사용됩니다.
    정상 동작 시에는 load_indicators_from_mongodb()를 사용해야 합니다.
    """
    logger.warning("⚠️ 경고: 하드코딩된 기본 Yahoo Finance 지표 딕셔너리를 사용합니다. MongoDB 조회를 확인하세요.")
    return {
        'S&P 500 지수': '^GSPC',
        '금 가격': 'GC=F',
        '달러 인덱스': 'DX-Y.NYB',
        '나스닥 100': '^NDX',
        'S&P 500 ETF': 'SPY',
        'QQQ ETF': 'QQQ',
        '러셀 2000 ETF': 'IWM',
        '다우 존스 ETF': 'DIA',
        'VIX 지수': '^VIX',
        '닛케이 225': '^N225',
        '상해종합': '000001.SS',
        '항셍': '^HSI',
        '영국 FTSE': '^FTSE',
        '독일 DAX': '^GDAXI',
        '프랑스 CAC 40': '^FCHI',
        '미국 전체 채권시장 ETF': 'AGG',
        'TIPS ETF': 'TIP',
        '투자등급 회사채 ETF': 'LQD',
        '달러/엔': 'JPY=X',
        '달러/위안': 'CNY=X',
        '미국 리츠 ETF': 'VNQ',
        'SOXX ETF': 'SOXX',
    }


# MongoDB에서 지표 로드 (모듈 레벨에서 실행)
fred_indicators, yfinance_indicators = load_indicators_from_mongodb()

# 결과 데이터프레임을 전역 변수로 정의 (초기에는 None)
result_df = None

# yfinance.py에서 가져온 함수
def get_short_interest_data(ticker_symbol: str) -> dict:
    """
    yfinance를 사용하여 공매도 관련 데이터를 가져옵니다.
    
    Args:
        ticker_symbol: 주식 티커 (예: "AAPL", "TSLA")
    
    Returns:
        dict: 공매도 관련 데이터 딕셔너리 (필요한 필드만)
    """
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        
        # 필요한 공매도 필드만 추출
        shares_short = info.get('sharesShort')
        shares_short_prior = info.get('sharesShortPriorMonth')

        short_interest = {
            'sharesShort': shares_short,
            'sharesShortPriorMonth': shares_short_prior,
            'shortRatio': info.get('shortRatio'),
            'shortPercentOfFloat': info.get('shortPercentOfFloat')
        }

        # 공매도 증감률 계산 (전월 대비)
        if shares_short is not None and shares_short_prior is not None and shares_short_prior > 0:
            short_change_pct = round((shares_short - shares_short_prior) / shares_short_prior * 100, 2)
            short_interest['shortChangePct'] = short_change_pct

        # None 값 제거
        short_interest = {k: v for k, v in short_interest.items() if v is not None}

        return short_interest if short_interest else None
    except Exception as e:
        logger.warning(f"공매도 데이터 조회 실패 ({ticker_symbol}): {str(e)}")
        return None

def download_yahoo_chart(symbol, start_date, end_date, interval="1d"):
    """
    Yahoo Finance Chart API를 통해 주어진 symbol의 종가(Close) 시계열을 가져옵니다.
    - symbol: Yahoo Finance 티커 문자열 (예: "^GSPC", "AAPL")
    - start_date: 시작일 (YYYY-MM-DD)
    - end_date: 종료일 (YYYY-MM-DD)
    - interval: "1d", "1wk", "1mo"
    """
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    })
    
    # 날짜 범위로 변환
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    delta = end_dt - start_dt
    
    # 범위 문자열 결정 (차이가 1달 이하이면 1mo, 3달 이하이면 3mo, 6달 이하이면 6mo, 그 이상이면 max)
    if delta.days <= 30:
        range_str = "1mo"
    elif delta.days <= 90:
        range_str = "3mo"
    elif delta.days <= 180:
        range_str = "6mo"
    elif delta.days <= 365:
        range_str = "1y"
    elif delta.days <= 730:
        range_str = "2y"
    elif delta.days <= 1825:
        range_str = "5y"
    else:
        range_str = "max"
    
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {
        "range": range_str,
        "interval": interval,
        "includePrePost": "false",
        "events": "div|split"
    }
    
    r = sess.get(url, params=params)
    r.raise_for_status()
    result = r.json().get("chart", {}).get("result", [None])[0]
    if not result:
        raise ValueError(f"No data for symbol: {symbol}")
    
    timestamps = result["timestamp"]
    closes = result["indicators"]["quote"][0]["close"]
    
    # 시작 - 수정된 부분: 날짜만 사용하도록 처리
    # 각 타임스탬프를 datetime으로 변환하고 날짜 부분만 사용
    date_only = [pd.Timestamp.fromtimestamp(ts).date() for ts in timestamps]
    
    # 데이터프레임 생성 시 날짜만 포함하도록 수정
    df = pd.DataFrame({
        "Close": closes
    }, index=pd.DatetimeIndex(date_only))
    
    # 중복된 날짜가 있는 경우 마지막 값만 유지
    if df.index.duplicated().any():
        df = df[~df.index.duplicated(keep='last')]
    # 종료 - 수정된 부분
    
    # 시작일과 종료일 사이의 데이터만 필터링
    df = df[(df.index >= pd.Timestamp(start_date)) & (df.index <= pd.Timestamp(end_date))]
    
    return df

def collect_economic_data(start_date='2006-01-01', end_date=None):
    """
    경제 데이터를 수집하는 메인 함수
    
    Args:
        start_date (str): 데이터 수집 시작 날짜 (YYYY-MM-DD 형식)
        end_date (str, optional): 데이터 수집 종료 날짜. 기본값은 현재 날짜.
    
    Returns:
        pd.DataFrame: 수집된 모든 경제 및 주식 데이터
    """
    global result_df
    
    # end_date가 지정되지 않은 경우 현재 날짜 사용
    if end_date is None:
        end_date = datetime.today().strftime('%Y-%m-%d')
    
    logger.info(f"경제 데이터 수집 시작: {start_date} ~ {end_date}")
    
    # 지표 정보를 다시 로드 (동적으로 변경 가능)
    global fred_indicators, yfinance_indicators
    fred_indicators, yfinance_indicators = load_indicators_from_mongodb()
    
    # FRED API를 통한 데이터 수집
    logger.info(f"FRED 경제 지표 수집 중... (총 {len(fred_indicators)}개)")
    fred_data_frames = []
    for code, name in fred_indicators.items():
        # 지표별 제공 주기에 따른 요청 주기 설정
        if code in ['FEDFUNDS', 'UMCSENT', 'UNRATE', 'USREC', 'PCE', 'INDPRO',
                    'HOUST', 'UNEMPLOY', 'RSAFS', 'CPIENGSL', 'AHETPI', 'PPIACO', 'CPIAUCSL',
                    'CSUSHPINSA', 'DTWEXM']:
            frequency = 'm'
        elif code in ['STLFSI4', 'M2', 'MORTGAGE30US', 'MORTGAGE15US', 'MORTGAGE5US']:
            frequency = 'w'
        elif code in ['TDSP', 'A939RX0Q048SBEA', 'GDPC1', 'W019RCQ027SBEA', 'DRBLACBS']:
            frequency = 'q'
        else:
            frequency = 'd'
    
        url = f'https://api.stlouisfed.org/fred/series/observations'
        params = {
            'series_id': code,
            'api_key': api_key,
            'file_type': 'json',
            'observation_start': start_date,
            'observation_end': end_date,
            'frequency': frequency
        }
        
        # 재시도 로직 추가 (최대 3번 시도)
        max_retries = 3
        response = None
        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=params, timeout=30)
                if response.status_code == 200:
                    break  # 성공하면 루프 탈출
                elif attempt < max_retries - 1:
                    logger.warning(f"FRED API 호출 실패 ({name}/{code}): {response.status_code}, 재시도 중... (시도 {attempt+1}/{max_retries})")
                    time.sleep(2 ** attempt)  # exponential backoff
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, 
                    requests.exceptions.RequestException) as e:
                if attempt < max_retries - 1:
                    logger.warning(f"FRED API 연결 오류 ({name}/{code}): {str(e)}, 재시도 중... (시도 {attempt+1}/{max_retries})")
                    time.sleep(2 ** attempt)  # exponential backoff
                else:
                    logger.error(f"FRED API 최종 실패 ({name}/{code}): {str(e)}")
                    response = None
        
        if response and response.status_code == 200:
            data = response.json().get('observations', [])
            if data:
                df = pd.DataFrame(data)[['date', 'value']]
                df.columns = ['date', name]
                df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
                fred_data_frames.append(df.set_index('date'))
            else:
                logger.warning(f"No data found for indicator {name} ({code}).")
        else:
            if response:
                logger.warning(f"Failed to fetch data for indicator {name} ({code}): {response.status_code}")
            else:
                logger.warning(f"Failed to fetch data for indicator {name} ({code}): 연결 실패")
    
    # 데이터 빈도에 따른 리샘플링 처리
    for i, df in enumerate(fred_data_frames):
        if df.empty:
            logger.warning(f"DataFrame {i} is empty, skipping resampling.")
            continue
        try:
            inferred_freq = df.index.inferred_freq
            # 빈도에 따라 일간 데이터로 변환
            if inferred_freq in ['M', 'MS']:  # 월간 데이터
                fred_data_frames[i] = df.resample('D').ffill()
            elif inferred_freq in ['W', 'W-FRI']:  # 주간 데이터
                fred_data_frames[i] = df.resample('D').ffill()
            elif inferred_freq in ['Q', 'QS-OCT']:  # 분기 데이터
                fred_data_frames[i] = df.resample('D').ffill()
            elif inferred_freq in ['B']:  # 영업일 데이터
                fred_data_frames[i] = df.resample('D').ffill()
            else:
                fred_data_frames[i] = df.resample('D').ffill()
        except Exception as e:
            logger.error(f"Error processing DataFrame {i}: {e}")
    
    # yfinance를 통한 데이터 수집 (yfinance.py의 방식으로 대체)
    logger.info(f"\nYahoo Finance 지표 데이터 수집 중... (총 {len(yfinance_indicators)}개)")
    yfinance_data_frames = []
    for name, ticker in yfinance_indicators.items():
        try:
            # download_yahoo_chart 함수를 사용하여 데이터 수집
            df = download_yahoo_chart(ticker, start_date, end_date)
            if not df.empty:
                df.columns = [name]  # 'Close' 컬럼명을 지표 이름으로 변경
                df.index = df.index.tz_localize(None)  # 시간대 정보 제거
                yfinance_data_frames.append(df)
                logger.info(f"{name}({ticker}) 수집 완료, {len(df)}개")
            else:
                logger.warning(f"No data found for indicator {name} ({ticker}).")
        except Exception as e:
            logger.error(f"Error downloading data for {ticker} ({name}): {e}")
        # 요청 간 간격을 두어 rate limit 방지
        time.sleep(1)
    
    # MongoDB에서 활성화된 주식 목록 가져오기
    logger.info("\nMongoDB에서 활성화된 주식 목록 조회 중...")
    try:
        # app.db.mongodb를 동적으로 import (모듈이 없을 수 있으므로)
        try:
            from app.db.mongodb import get_db
            db = get_db()
            if db is None:
                raise ValueError("MongoDB 연결 실패. MongoDB 연결을 확인하세요.")
            
            # stocks 컬렉션에서 활성화된 주식 조회 (공용 함수 사용 시도)
            try:
                from app.services.stock_service import get_active_stocks
                stocks_list = get_active_stocks(exclude_etf=False)
                active_stocks = [(stock.get("ticker"), stock.get("stock_name")) for stock in stocks_list if stock.get("ticker") and stock.get("stock_name")]
            except (ImportError, Exception) as import_error:
                # app 모듈을 import할 수 없는 경우 직접 조회
                logger.warning(f"app.services.stock_service를 사용할 수 없어 직접 조회합니다: {import_error}")
                active_stocks_cursor = db.stocks.find({"is_active": True})
                active_stocks = [(stock["ticker"], stock["stock_name"]) for stock in active_stocks_cursor]
            logger.info(f"✅ 활성화된 주식 {len(active_stocks)}개를 MongoDB stocks 컬렉션에서 찾았습니다.")
            if len(active_stocks) == 0:
                raise ValueError("활성화된 주식이 없습니다. MongoDB stocks 컬렉션에서 is_active=true인 주식을 확인하세요.")
        except ImportError:
            raise ImportError("app.db.mongodb 모듈을 import할 수 없습니다. MongoDB 연결을 확인하세요.")
    except Exception as e:
        logger.error(f"❌ 오류: MongoDB stocks 컬렉션 조회 실패: {str(e)}")
        import traceback
        traceback.print_exc()
        raise Exception(f"주식 목록을 가져올 수 없습니다. MongoDB stocks 컬렉션과 데이터베이스 연결을 확인하세요: {str(e)}")
    
    # 활성화된 주식 데이터 수집
    logger.info(f"\n활성화된 주식 {len(active_stocks)}개 데이터 수집 중...")
    nasdaq_data_frames = []
    # 공매도 데이터를 저장할 딕셔너리 (날짜별로 관리)
    short_interest_data = {}  # {날짜: {주식명: {short_interest: {...}}}}
    
    for ticker, name in active_stocks:
        try:
            # download_yahoo_chart 함수를 사용하여 데이터 수집
            df = download_yahoo_chart(ticker, start_date, end_date)
            if not df.empty:
                df.columns = [name]  # 'Close' 컬럼명을 종목 한글 이름으로 변경
                df.index = df.index.tz_localize(None)  # 시간대 정보 제거
                nasdaq_data_frames.append(df)
                logger.info(f"{name}({ticker}) 수집 완료, {len(df)}개")
                
                # 공매도 데이터 수집 (최신 데이터만, 날짜별로는 동일하게 적용)
                try:
                    short_info = get_short_interest_data(ticker)
                    if short_info:
                        # 모든 날짜에 동일한 공매도 데이터 적용 (공매도 데이터는 월 1-2회 업데이트되므로)
                        # 티커를 키로 사용 (주식명이 아님)
                        for date_idx in df.index:
                            date_str = date_idx.strftime('%Y-%m-%d') if hasattr(date_idx, 'strftime') else str(date_idx)
                            if date_str not in short_interest_data:
                                short_interest_data[date_str] = {}
                            short_interest_data[date_str][ticker] = {'short_interest': short_info}
                        logger.info(f"{name}({ticker}) 공매도 데이터 수집 완료")
                except Exception as short_e:
                    logger.warning(f"{name}({ticker}) 공매도 데이터 수집 실패: {str(short_e)}")
            else:
                logger.warning(f"No data found for stock {name} ({ticker}).")
        except Exception as e:
            logger.error(f"Error downloading data for {ticker} ({name}): {e}")
        # 요청 간 간격을 두어 rate limit 방지
        time.sleep(1)
    
    # 모든 데이터를 날짜 기준으로 외부 결합하여 하나의 데이터프레임으로 결합
    all_data_frames = fred_data_frames + yfinance_data_frames + nasdaq_data_frames
    if all_data_frames:
        # 중복된 인덱스 처리
        for i, df in enumerate(all_data_frames):
            if df.index.duplicated().any():
                all_data_frames[i] = df[~df.index.duplicated(keep='first')]
        
        # 결합
        logger.info("데이터프레임 병합 중...")
        result_df = pd.concat(all_data_frames, axis=1, join='outer')
    
        # 결측치 및 비정상적인 값 처리
        result_df.replace('.', pd.NA, inplace=True)
        
        # 결측치를 이전 값으로 채움
        result_df.sort_index(inplace=True)
        result_df.ffill(inplace=True)
        
        # 주요 수정: 날짜 인덱스의 시간 부분을 제거하고 일자만 남김
        # 동일 날짜의 데이터가 여러 개 있는 경우, 마지막 데이터만 사용
        logger.info("날짜 인덱스 표준화 중...")
        result_df.index = pd.to_datetime(result_df.index.date)  # 날짜만 남김
        result_df = result_df[~result_df.index.duplicated(keep='last')]  # 중복 날짜 제거, 마지막 값 유지
        
        # DDL 기준 제외된 주식 컬럼 제거 (코스트코, 넷플릭스, 페이팔, 시스코, 컴캐스트, 펩시코, 암젠, 허니웰 인터내셔널, 스타벅스, 몬델리즈, 어도비)
        excluded_stocks = ['코스트코', '넷플릭스', '페이팔', '시스코', '컴캐스트', '펩시코', '암젠', '허니웰 인터내셔널', '스타벅스', '몬델리즈', '어도비']
        for stock in excluded_stocks:
            if stock in result_df.columns:
                result_df = result_df.drop(columns=[stock])
                logger.info(f"제외된 주식 컬럼 제거: {stock}")
        
        # 결과 데이터프레임 로그 출력
        logger.info("\n=== 결과 데이터프레임 정보 ===")
        logger.info(f"행 수: {len(result_df)}")
        logger.info(f"열 수: {len(result_df.columns)}")
        logger.info("컬럼 목록:")
        for col in result_df.columns:
            logger.info(f"  - {col}")
        
        logger.info("\n=== 결과 데이터프레임 처음 5행 ===")
        logger.info(result_df.head())
        
        logger.info("\n=== 결과 데이터프레임 마지막 5행 ===")
        logger.info(result_df.tail())
        
        logger.info(f"\n데이터 수집 완료")
        # 공매도 데이터도 함께 반환 (딕셔너리 형태)
        return result_df, short_interest_data
    else:
        logger.warning("No data collected for any indicators.")
        return None, {}

# 스크립트가 직접 실행될 때만 데이터 수집 진행
if __name__ == "__main__":
    result_df = collect_economic_data()
