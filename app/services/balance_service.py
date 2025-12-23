import requests
import json
import time
from datetime import datetime, timedelta
import pytz
from app.core.config import settings
from app.core.enums import OrderStatus
from app.db.mongodb import get_db
from threading import Lock
from app.services.auth_service import parse_expiration_date
import logging
from app.utils.slack_notifier import slack_notifier

# 로거 설정
logger = logging.getLogger('balance_service')

# 메모리에 토큰 정보 저장 (캐싱) - 모의투자/실제투자별로 분리
_token_cache = {
    "mock": {  # 모의투자 토큰
        "access_token": None,
        "expires_at": None
    },
    "real": {  # 실제투자 토큰
        "access_token": None,
        "expires_at": None
    }
}
_last_refresh_time = {
    "mock": 0,
    "real": 0
}
_refresh_lock = Lock()  # 동시성 방지 락

def _get_token_cache_key():
    """현재 설정에 따른 토큰 캐시 키 반환"""
    return "mock" if settings.KIS_USE_MOCK else "real"

# API 호출 Rate Limiting 관리
_last_api_call_time = 0  # 마지막 API 호출 시간
_min_api_interval = 0.5  # API 호출 간 최소 간격 (초)
_api_lock = Lock()  # API 호출 동시성 방지 락

def _wait_for_api_rate_limit():
    """API 호출 간 최소 간격 보장"""
    global _last_api_call_time
    with _api_lock:
        current_time = time.time()
        time_since_last_call = current_time - _last_api_call_time
        if time_since_last_call < _min_api_interval:
            wait_time = _min_api_interval - time_since_last_call
            time.sleep(wait_time)
        _last_api_call_time = time.time()

def _handle_rate_limit_error(result, attempt, max_retries):
    """Rate limiting 에러 처리"""
    if result.get('msg_cd') == 'EGW00201':
        # Rate limiting 에러인 경우 더 긴 대기 시간
        wait_time = 3.0  # 3초 대기
        print(f"Rate limiting 에러 감지: {result.get('msg1', '')}. {wait_time}초 대기 후 재시도...")
        if attempt < max_retries - 1:
            time.sleep(wait_time)
            return True  # 재시도 가능
        else:
            print(f"Rate limiting 에러: 최대 재시도 횟수 초과")
            return False  # 재시도 불가
    return None  # Rate limiting 에러가 아님

def get_access_token(user_id: str = "lian"):
    """한국투자증권 API 접근 토큰 발급 또는 캐시된 토큰 반환
    
    Args:
        user_id: 사용자 ID (기본값: "lian")
    """
    global _token_cache, _last_refresh_time
    
    # 현재 설정에 따른 토큰 캐시 키
    cache_key = _get_token_cache_key()
    token_type = "모의투자" if settings.KIS_USE_MOCK else "실제투자"
    account_type = "mock" if settings.KIS_USE_MOCK else "real"
    
    # 현재 시간
    now = datetime.now(pytz.UTC)
    
    # 메모리에 캐시된 토큰이 있고 유효하면 그것을 사용
    cache = _token_cache[cache_key]
    if cache["access_token"] and cache["expires_at"] and now < cache["expires_at"]:
        return cache["access_token"]
    
    # 1분 제한 체크 및 락 획득
    current_time = time.time()
    if current_time - _last_refresh_time[cache_key] < 60:
        time_to_wait = 60 - (current_time - _last_refresh_time[cache_key])
        time.sleep(time_to_wait)
    
    with _refresh_lock:  # 동시성 방지
        # 락 획득 후 다시 캐시 확인
        if cache["access_token"] and cache["expires_at"] and now < cache["expires_at"]:
            return cache["access_token"]
        
        try:
            # MongoDB에서 토큰 레코드 조회 (user_id + account_type별로 최신 토큰 사용)
            db = get_db()
            if db is None:
                raise Exception("MongoDB 연결 실패")
            
            token_doc = db.access_tokens.find_one(
                {"user_id": user_id, "account_type": account_type},
                sort=[("created_at", -1)]
            )
            
            if token_doc:
                # auth_service의 parse_expiration_date 함수 사용
                expiration_time = parse_expiration_date(token_doc["expiration_time"])
                
                if now < expiration_time:  # 토큰이 아직 유효한 경우
                    cache["access_token"] = token_doc["access_token"]
                    cache["expires_at"] = expiration_time
                    _last_refresh_time[cache_key] = current_time
                    logger.info(f"[{user_id}] {token_type} 토큰 조회 성공 (MongoDB)")
                    return token_doc["access_token"]
                
                # 토큰이 만료된 경우 갱신
                token = refresh_token_with_retry(str(token_doc["_id"]), account_type=account_type, user_id=user_id)
                cache["access_token"] = token
                cache["expires_at"] = now + timedelta(days=1)
                _last_refresh_time[cache_key] = current_time
                return token
            else:
                token = refresh_token_with_retry(account_type=account_type, user_id=user_id)
                cache["access_token"] = token
                cache["expires_at"] = now + timedelta(days=1)
                _last_refresh_time[cache_key] = current_time
                return token
                
        except Exception as e:
            if cache["access_token"]:
                return cache["access_token"]
            raise Exception(f"[{user_id}] {token_type} 토큰 발급 실패: {str(e)}")

def refresh_token_with_retry(record_id=None, max_retries=3, account_type=None, user_id: str = "lian"):
    """토큰 갱신을 재시도하며 처리 (MongoDB access_tokens 컬렉션)
    
    Args:
        record_id: 업데이트할 토큰 레코드의 ID (없으면 새로 생성)
        max_retries: 최대 재시도 횟수
        account_type: 계정 유형 ("mock" 또는 "real")
        user_id: 사용자 ID (기본값: "lian")
    """
    # account_type이 없으면 현재 설정에서 결정
    if account_type is None:
        account_type = "mock" if settings.KIS_USE_MOCK else "real"
    
    token_type = "모의투자" if account_type == "mock" else "실제투자"
    
    for attempt in range(max_retries):
        try:
            url = f"{settings.kis_base_url}/oauth2/tokenP"
            data = {
                "grant_type": "client_credentials",
                "appkey": settings.KIS_APPKEY,
                "appsecret": settings.KIS_APPSECRET
            }
            
            response = requests.post(url, json=data)
            response_data = response.json()
            
            if 'access_token' not in response_data:
                raise Exception(f"토큰 발급 실패: {response_data}")
            
            access_token = response_data["access_token"]
            expires_in = response_data.get("expires_in", 86400)  # 기본값 24시간(초)
            now = datetime.now(pytz.UTC)
            expiration_time = now + timedelta(seconds=expires_in)
            
            token_data = {
                "access_token": access_token,
                "expiration_time": expiration_time.isoformat(),
                "user_id": user_id,
                "account_type": account_type,
                "is_active": True,
                "updated_at": datetime.now(pytz.UTC)
            }
            
            # MongoDB에 저장
            db = get_db()
            if db is None:
                raise Exception("MongoDB 연결 실패")
            
            # 레코드 ID가 있으면 업데이트, 없으면 upsert로 처리
            if record_id:
                from bson import ObjectId
                db.access_tokens.update_one(
                    {"_id": ObjectId(record_id)},
                    {"$set": token_data}
                )
                logger.info(f"[{user_id}] {token_type} 토큰 업데이트 완료 (MongoDB)")
            else:
                # user_id + account_type 기준으로 upsert
                db.access_tokens.update_one(
                    {"user_id": user_id, "account_type": account_type},
                    {"$set": token_data, "$setOnInsert": {"created_at": datetime.now(pytz.UTC)}},
                    upsert=True
                )
                logger.info(f"[{user_id}] {token_type} 토큰 저장 완료 (MongoDB)")
            
            return access_token
            
        except Exception as e:
            logger.error(f"[{user_id}] 토큰 갱신 오류 (시도 {attempt+1}/{max_retries}): {str(e)}")
            if "EGW00133" in str(e) and attempt < max_retries - 1:
                logger.warning("1분 제한 에러 발생, 61초 대기 후 재시도")
                time.sleep(61)  # 1분 이상 대기
            else:
                raise

def get_domestic_balance():
    """국내주식 잔고 조회"""
    # 토큰 가져오기
    access_token = get_access_token()
    
    url = f"{settings.kis_base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
    
    # 모의투자/실제투자에 따라 TR_ID 설정
    is_virtual = settings.KIS_USE_MOCK
    tr_id = "VTTC8434R" if is_virtual else "TTTC8434R"  # 국내주식 잔고 조회 TR ID
    
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": settings.KIS_APPKEY,
        "appsecret": settings.KIS_APPSECRET,
        "tr_id": tr_id
    }
    
    params = {
        "CANO": settings.KIS_CANO,
        "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
        "AFHR_FLPR_YN": "N",
        "OFL_YN": "",
        "INQR_DVSN": "02",
        "UNPR_DVSN": "01",
        "FUND_STTL_ICLD_YN": "N",
        "FNCG_AMT_AUTO_RDPT_YN": "N",
        "PRCS_DVSN": "00",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": ""
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # API 호출 간 최소 간격 보장
            _wait_for_api_rate_limit()
            
            response = requests.get(url, headers=headers, params=params)
            result = response.json()
            
            # Rate limiting 에러 처리
            rate_limit_handled = _handle_rate_limit_error(result, attempt, max_retries)
            if rate_limit_handled is True:
                continue  # 재시도
            elif rate_limit_handled is False:
                raise Exception(f"Rate limiting 에러: {result.get('msg1', '')}")
            
            # API 응답에 오류가 있고, 재시도 가능한 경우
            if 'rt_cd' in result and result['rt_cd'] != '0' and attempt < max_retries - 1:
                print(f"API 오류: {result['msg_cd']} - {result.get('msg1', '알 수 없는 오류')}. 토큰 갱신 후 재시도...")
                # 토큰 강제 갱신 후 재시도
                access_token = get_access_token()
                headers["authorization"] = f"Bearer {access_token}"
                time.sleep(1)  # 재시도 전 1초 대기
                continue
            
            return result
            
        except Exception as e:
            print(f"잔고 조회 중 오류 발생 (시도 {attempt+1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(1)  # 재시도 전 1초 대기
            else:
                raise

def get_overseas_balance(ovrs_excg_cd="NASD"):
    """해외주식 잔고 조회
    
    Args:
        ovrs_excg_cd (str, optional): 거래소 코드. Defaults to "NASD".
            NASD: 나스닥, NYSE: 뉴욕, AMEX: 아멕스
    """
    # 토큰 가져오기
    access_token = get_access_token()
    
    url = f"{settings.kis_base_url}/uapi/overseas-stock/v1/trading/inquire-balance"
    
    # 모의투자/실제투자에 따라 TR_ID 설정
    is_virtual = settings.KIS_USE_MOCK
    tr_id = "VTTS3012R" if is_virtual else "TTTS3012R"  # 해외주식 잔고 조회 TR ID
    
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": settings.KIS_APPKEY,
        "appsecret": settings.KIS_APPSECRET,
        "tr_id": tr_id
    }
    
    params = {
        "CANO": settings.KIS_CANO,
        "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
        "OVRS_EXCG_CD": ovrs_excg_cd,  # 매개변수로 받은 거래소 코드 사용
        "TR_CRCY_CD": "USD",     # 통화코드 USD
        "CTX_AREA_FK200": "",
        "CTX_AREA_NK200": ""
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # API 호출 간 최소 간격 보장
            _wait_for_api_rate_limit()
            
            response = requests.get(url, headers=headers, params=params)
            result = response.json()
            
            # Rate limiting 에러 처리
            rate_limit_handled = _handle_rate_limit_error(result, attempt, max_retries)
            if rate_limit_handled is True:
                continue  # 재시도
            elif rate_limit_handled is False:
                raise Exception(f"Rate limiting 에러: {result.get('msg1', '')}")
            
            # API 응답에 오류가 있고, 재시도 가능한 경우
            if 'rt_cd' in result and result['rt_cd'] != '0' and attempt < max_retries - 1:
                print(f"API 오류: {result['msg_cd']} - {result.get('msg1', '알 수 없는 오류')}. 토큰 갱신 후 재시도...")
                # 토큰 강제 갱신 후 재시도
                access_token = get_access_token()
                headers["authorization"] = f"Bearer {access_token}"
                time.sleep(1)
                continue
            
            return result
            
        except Exception as e:
            print(f"잔고 조회 중 오류 발생 (시도 {attempt+1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(1)  # 재시도 전 1초 대기
            else:
                raise

def get_overseas_present_balance():
    """해외주식 체결기준현재잔고 조회 (외화사용가능금액 포함)"""
    try:
        access_token = get_access_token()
        
        url = f"{settings.kis_base_url}/uapi/overseas-stock/v1/trading/inquire-present-balance"
        
        # 모의투자/실제투자에 따라 TR_ID 설정
        is_virtual = settings.KIS_USE_MOCK
        tr_id = "VTRP6504R" if is_virtual else "CTRP6504R"  # 체결기준현재잔고 TR_ID
        
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": settings.KIS_APPKEY,
            "appsecret": settings.KIS_APPSECRET,
            "tr_id": tr_id
        }
        
        params = {
            "CANO": settings.KIS_CANO,
            "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
            "TR_CRCY_CD": "USD",  # 통화코드 USD
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": ""
        }
        
        _wait_for_api_rate_limit()
        response = requests.get(url, headers=headers, params=params)
        result = response.json()
        
        return result
        
    except Exception as e:
        logger.error(f"체결기준현재잔고 조회 중 오류: {str(e)}")
        return {"rt_cd": "1", "msg1": str(e)}

def get_overseas_order_possible_amount(exchange_code="NASD", ticker="AAPL"):
    """해외주식 매수주문가능금액 조회 (TTTS3007R)
    
    Args:
        exchange_code (str): 거래소 코드 (NASD, NYSE, AMEX 등)
        ticker (str): 종목 심볼
        
    Returns:
        dict: API 응답 (주문가능금액 정보 포함)
    """
    access_token = get_access_token()
    
    url = f"{settings.kis_base_url}/uapi/overseas-stock/v1/trading/inquire-psamount"
    
    # 모의투자/실제투자에 따라 TR_ID 설정
    is_virtual = settings.KIS_USE_MOCK
    tr_id = "VTTS3007R" if is_virtual else "TTTS3007R"
    
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": settings.KIS_APPKEY,
        "appsecret": settings.KIS_APPSECRET,
        "tr_id": tr_id
    }
    
    params = {
        "CANO": settings.KIS_CANO,
        "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
        "OVRS_EXCG_CD": exchange_code,
        "OVRS_ORD_UNPR": "0",  # 해외주문단가 (0: 시장가)
        "ITEM_CD": ticker  # 종목코드
    }
    
    try:
        _wait_for_api_rate_limit()
        response = requests.get(url, headers=headers, params=params)
        result = response.json()
        return result
        
    except Exception as e:
        logger.error(f"주문가능금액 조회 중 오류: {str(e)}")
        return {"rt_cd": "1", "msg1": str(e)}

def get_all_overseas_balances():
    """모든 거래소의 해외주식 잔고 조회"""
    # 주요 거래소 목록
    exchanges = ["NASD", "NYSE", "AMEX"]
    all_holdings = []
    
    for exchange in exchanges:
        try:
            result = get_overseas_balance(exchange)
            
            if result.get("rt_cd") == "0" and "output1" in result:
                holdings = result.get("output1", [])
                if holdings:
                    all_holdings.extend(holdings)
            else:
                print(f"{exchange} 거래소 잔고 조회 실패: {result.get('msg1', '알 수 없는 오류')}")
                
            # API 요청 간 지연
            time.sleep(0.5)
            
        except Exception as e:
            print(f"{exchange} 거래소 잔고 조회 중 오류: {str(e)}")
    
    # 통합된 잔고 정보 반환
    if all_holdings:
        return {
            "rt_cd": "0",
            "msg_cd": "00000",
            "msg1": "모든 거래소 잔고 조회 완료",
            "output1": all_holdings,
            "output2": {}  # 합산 정보는 필요시 계산
        }
    else:
        return {
            "rt_cd": "0",
            "msg_cd": "00000",
            "msg1": "보유 종목이 없습니다.",
            "output1": [],
            "output2": {}
        }

# 추가: 해외주식 예약주문 접수
def overseas_order_resv(order_data):
    """해외주식 예약주문 접수"""
    try:
        access_token = get_access_token()
        url = f"{settings.kis_base_url}/uapi/overseas-stock/v1/trading/order-resv"
        
        # 모의투자 여부 확인
        is_virtual = "openapivts" in settings.kis_base_url
        
        # 매수/매도 여부 및 거래소에 따라 TR_ID 결정
        is_buy = order_data.get("is_buy", True)
        ovrs_excg_cd = order_data.get("OVRS_EXCG_CD", "")
        
        if ovrs_excg_cd in ["NASD", "NYSE", "AMEX"]:  # 미국 주식
            if is_buy:
                tr_id = "VTTT3014U" if is_virtual else "TTTT3014U"  # 미국 매수 예약
            else:
                tr_id = "VTTT3016U" if is_virtual else "TTTT3016U"  # 미국 매도 예약
        else:  # 기타 거래소
            tr_id = "VTTS3013U" if is_virtual else "TTTS3013U"  # 중국/홍콩/일본/베트남 예약
            
            # 중국/홍콩/일본/베트남의 경우 매수/매도 구분 코드 추가
            if not is_buy:
                order_data["SLL_BUY_DVSN_CD"] = "01"  # 매도
            else:
                order_data["SLL_BUY_DVSN_CD"] = "02"  # 매수
        
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": settings.KIS_APPKEY,
            "appsecret": settings.KIS_APPSECRET,
            "tr_id": tr_id
        }
        
        # 필수 파라미터를 포함한 요청 데이터 준비
        request_body = order_data.copy()
        if "is_buy" in request_body:
            del request_body["is_buy"]  # API 요청에는 필요 없는 필드 제거
            
        # 필수 파라미터 설정
        request_body["RVSE_CNCL_DVSN_CD"] = "00"  # 정정취소구분코드 (00: 주문시 필수)
        
        # API 호출 간 최소 간격 보장
        _wait_for_api_rate_limit()
        
        response = requests.post(url, headers=headers, json=request_body)
        result = response.json()
        
        # Rate limiting 에러 처리
        if result.get('msg_cd') == 'EGW00201':
            wait_time = 3.0
            print(f"Rate limiting 에러 감지: {result.get('msg1', '')}. {wait_time}초 대기 후 재시도...")
            time.sleep(wait_time)
            # 재시도
            _wait_for_api_rate_limit()
            response = requests.post(url, headers=headers, json=request_body)
            result = response.json()
        
        return result
    except Exception as e:
        print(f"예약주문 접수 중 오류 발생: {str(e)}")
        raise

def inquire_psamount(params):
    """해외주식 매수가능금액 조회"""
    try:
        access_token = get_access_token()
        url = f"{settings.kis_base_url}/uapi/overseas-stock/v1/trading/inquire-psamount"
        
        # 모의투자/실제투자에 따라 TR_ID 설정
        is_virtual = settings.KIS_USE_MOCK
        tr_id = "VTTS3011R" if is_virtual else "TTTS3011R"  # 해외주식 매수가능금액 조회 TR ID
        
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": settings.KIS_APPKEY,
            "appsecret": settings.KIS_APPSECRET,
            "tr_id": tr_id,
        }
        
        # 기존 파라미터 유지
        base_params = {
            "CANO": params.get("CANO"),
            "ACNT_PRDT_CD": params.get("ACNT_PRDT_CD"),
            "OVRS_EXCG_CD": params.get("OVRS_EXCG_CD"),
            "OVRS_ORD_UNPR": params.get("OVRS_ORD_UNPR"),
            "ITEM_CD": params.get("ITEM_CD"),
            
            # 추가 필수 파라미터
            "AFHR_FLPR_YN": "N",  # 장후플래그여부
            "OFL_YN": "N",        # 오프라인여부
            "INQR_DVSN": "02",    # 조회구분 (02: 상세조회)
            "UNPR_DVSN": "01",    # 단가구분 (01: 기본값)
            "FUND_STTL_ICLD_YN": "N",  # 펀드결제포함여부
            "FNCG_AMT_AUTO_RDPT_YN": "N",  # 융자금액자동상환여부
            "PRCS_DVSN": "00",    # 처리구분 
            "CTX_AREA_FK100": "", # 연속조회검색조건100
            "CTX_AREA_NK100": ""  # 연속조회키100
        }
        
        response = requests.get(url, headers=headers, params=base_params)
        result = response.json()
        
        return result
    except Exception as e:
        print(f"매수가능금액 조회 중 오류 발생: {str(e)}")
        raise

# 추가: 해외주식 현재체결가 조회
def get_current_price(params):
    """해외주식 현재체결가 조회"""
    try:
        access_token = get_access_token()
        url = f"{settings.kis_base_url}/uapi/overseas-price/v1/quotations/price"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": settings.KIS_APPKEY,
            "appsecret": settings.KIS_APPSECRET,
            "tr_id": "HHDFS00000300",
        }
        
        response = requests.get(url, headers=headers, params=params)
        result = response.json()
        
        return result
    except Exception as e:
        print(f"현재체결가 조회 중 오류 발생: {str(e)}")
        raise

def get_overseas_nccs(params):
    """해외주식 미체결내역 조회"""
    try:
        access_token = get_access_token()
        
        # 모의투자에서는 직접 API가 지원되지 않으므로 주문체결내역 API로 대체
        is_virtual = settings.KIS_USE_MOCK
        if is_virtual:
            # 모의투자 환경에서는 주문체결내역 API 사용
            url = f"{settings.kis_base_url}/uapi/overseas-stock/v1/trading/inquire-order"
            tr_id = "VTTS3035R"  # 모의투자 주문체결내역 TR_ID
        else:
            # 실전투자 환경에서는 미체결내역 API 사용
            url = f"{settings.kis_base_url}/uapi/overseas-stock/v1/trading/inquire-nccs"
            tr_id = "TTTS3018R"  # 실전투자 미체결내역 TR_ID
            
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": settings.KIS_APPKEY,
            "appsecret": settings.KIS_APPSECRET,
            "tr_id": tr_id,
        }
        
        response = requests.get(url, headers=headers, params=params)
        result = response.json()
        
        # 모의투자에서는 nccs_qty(미체결수량)가 0보다 큰 항목만 필터링
        if is_virtual and 'output' in result and isinstance(result['output'], list):
            result['output'] = [item for item in result['output'] if int(item.get('nccs_qty', 0)) > 0]
        
        return result
    except Exception as e:
        print(f"미체결내역 조회 중 오류 발생: {str(e)}")
        raise

def check_order_execution(
    order_no: str,
    exchange_code: str,
    ticker: str,
    max_retries: int = 3,
    retry_delay: int = 5,
    order_dt: str = None,
    order_gno_brno: str = None
):
    """
    주문번호로 체결 여부 확인

    Args:
        order_no: 주문번호 (ODNO)
        exchange_code: 거래소 코드 (NASD, NYSE 등)
        ticker: 티커 심볼
        max_retries: 최대 재시도 횟수
        retry_delay: 재시도 간격 (초)
        order_dt: 주문일자 (YYYYMMDD) - 저장된 값 사용 시 더 빠른 조회 가능
        order_gno_brno: 주문점번호 - 저장된 값 사용 시 더 빠른 조회 가능

    Returns:
        dict: 체결 정보 또는 None
    """
    from datetime import datetime, timedelta
    import time

    # 주문체결내역 조회 파라미터
    today = datetime.now()
    # order_dt가 있으면 해당 날짜 기준, 없으면 7일 전부터
    if order_dt:
        start_date = order_dt
        end_date = order_dt
    else:
        start_date = (today - timedelta(days=7)).strftime("%Y%m%d")
        end_date = today.strftime("%Y%m%d")

    params = {
        "CANO": settings.KIS_CANO,
        "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
        "PDNO": "",  # 종목번호 (공백: 전체)
        "ORD_STRT_DT": start_date,
        "ORD_END_DT": end_date,
        "SLL_BUY_DVSN": "00",  # 매도매수구분 (00: 전체)
        "CCLD_NCCS_DVSN": "00",  # 체결미체결구분 (00: 전체)
        "OVRS_EXCG_CD": exchange_code if exchange_code else "",  # 거래소코드 (공백: 전체)
        "SORT_SQN": "DS",  # 정순
        "ORD_DT": order_dt if order_dt else "",  # 주문일자 (있으면 사용)
        "ORD_GNO_BRNO": order_gno_brno if order_gno_brno else "",  # 주문점번호 (있으면 사용)
        "ODNO": "",  # 주문번호는 조회 결과에서 필터링
        "CTX_AREA_FK200": "",
        "CTX_AREA_NK200": ""
    }
    
    for attempt in range(max_retries):
        try:
            # 연속조회를 위한 변수 초기화
            ctx_area_fk200 = ""
            ctx_area_nk200 = ""
            max_pages = 10  # 최대 페이지 수 제한

            for page in range(max_pages):
                # 연속조회 키 설정
                params["CTX_AREA_FK200"] = ctx_area_fk200
                params["CTX_AREA_NK200"] = ctx_area_nk200

                # 주문체결내역 조회
                result = get_overseas_order_detail(params)

                if result.get("rt_cd") != "0":
                    break

                # output에서 해당 주문번호 찾기
                output = result.get("output", [])
                if not isinstance(output, list):
                    output = [output] if output else []

                for order in output:
                    # 응답의 주문번호 필드는 소문자 'odno'
                    if order.get("odno") == order_no:
                        # 체결 여부 확인 (nccs_qty: 미체결수량이 0이면 체결)
                        nccs_qty = int(order.get("nccs_qty", 0))
                        ft_ord_qty = int(order.get("ft_ord_qty", 0))
                        ft_ccld_qty = int(order.get("ft_ccld_qty", 0))

                        # 체결된 경우 (미체결수량이 0이거나 체결수량이 주문수량과 같으면)
                        if nccs_qty == 0 or ft_ccld_qty == ft_ord_qty:
                            return {
                                "executed": True,
                                "order": order,
                                "executed_qty": ft_ccld_qty,
                                "executed_price": float(order.get("ft_ccld_unpr3", 0))
                            }
                        else:
                            # 아직 미체결
                            return {
                                "executed": False,
                                "order": order,
                                "pending_qty": nccs_qty
                            }

                # 연속조회 키 업데이트
                ctx_area_fk200 = result.get("ctx_area_fk200", "").strip()
                ctx_area_nk200 = result.get("ctx_area_nk200", "").strip()

                # 더 이상 조회할 데이터가 없으면 종료
                if not ctx_area_nk200 or not output:
                    break

                time.sleep(0.5)  # API 호출 간격

            # 주문번호를 찾지 못한 경우 재시도
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue

            return None

        except Exception as e:
            logger.error(f"체결 확인 중 오류 발생: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return None

    return None

def get_overseas_order_detail(params):
    """해외주식 주문체결내역 조회 (v1_해외주식-007)

    한국투자증권 API 문서 기준 파라미터:
    - CANO: 계좌번호 앞 8자리 (필수)
    - ACNT_PRDT_CD: 계좌번호 뒤 2자리 (필수)
    - PDNO: 종목번호 (공백: 전체)
    - ORD_STRT_DT: 주문시작일자 (필수, YYYYMMDD)
    - ORD_END_DT: 주문종료일자 (필수, YYYYMMDD)
    - SLL_BUY_DVSN: 매도매수구분 (00: 전체, 01: 매도, 02: 매수)
    - CCLD_NCCS_DVSN: 체결미체결구분 (00: 전체, 01: 체결, 02: 미체결)
    - OVRS_EXCG_CD: 해외거래소코드 (공백: 전체, NASD, NYSE, AMEX 등)
    - SORT_SQN: 정렬순서 (DS: 정순)
    - ORD_DT: 주문일자 (연속조회용)
    - ORD_GNO_BRNO: 주문점번호 (연속조회용)
    - ODNO: 주문번호 (연속조회용)
    - CTX_AREA_FK200: 연속조회검색조건200
    - CTX_AREA_NK200: 연속조회키200
    """
    try:
        access_token = get_access_token()

        # 모의투자/실제투자에 따라 TR_ID 설정
        is_virtual = settings.KIS_USE_MOCK
        url = f"{settings.kis_base_url}/uapi/overseas-stock/v1/trading/inquire-ccnl"
        tr_id = "VTTS3035R" if is_virtual else "TTTS3035R"

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": settings.KIS_APPKEY,
            "appsecret": settings.KIS_APPSECRET,
            "tr_id": tr_id,
        }

        # 파라미터 검증 및 정리
        validated_params = {
            "CANO": params.get("CANO", settings.KIS_CANO),
            "ACNT_PRDT_CD": params.get("ACNT_PRDT_CD", settings.KIS_ACNT_PRDT_CD),
            "PDNO": params.get("PDNO", ""),  # 종목번호 (공백: 전체)
            "ORD_STRT_DT": params.get("ORD_STRT_DT", ""),  # 주문시작일자
            "ORD_END_DT": params.get("ORD_END_DT", ""),  # 주문종료일자
            "SLL_BUY_DVSN": params.get("SLL_BUY_DVSN", "00"),  # 매도매수구분
            "CCLD_NCCS_DVSN": params.get("CCLD_NCCS_DVSN", "00"),  # 체결미체결구분
            "OVRS_EXCG_CD": params.get("OVRS_EXCG_CD", ""),  # 거래소코드 (공백: 전체)
            "SORT_SQN": params.get("SORT_SQN", "DS"),
            "ORD_DT": params.get("ORD_DT", ""),
            "ORD_GNO_BRNO": params.get("ORD_GNO_BRNO", ""),
            "ODNO": params.get("ODNO", ""),
            "CTX_AREA_FK200": params.get("CTX_AREA_FK200", ""),
            "CTX_AREA_NK200": params.get("CTX_AREA_NK200", ""),
        }

        # 필수 파라미터 검증
        if not validated_params["CANO"] or not validated_params["ACNT_PRDT_CD"]:
            raise ValueError("CANO와 ACNT_PRDT_CD는 필수 파라미터입니다.")
        if not validated_params["ORD_STRT_DT"] or not validated_params["ORD_END_DT"]:
            raise ValueError("ORD_STRT_DT와 ORD_END_DT는 필수 파라미터입니다.")
        
        # 디버깅 정보
        logger.debug(f"API 요청: {url}")
        logger.debug(f"헤더: {headers}")
        logger.debug(f"파라미터: {validated_params}")
        
        response = requests.get(url, headers=headers, params=validated_params)
        
        # 응답 확인
        logger.debug(f"API 응답 상태 코드: {response.status_code}")
        logger.debug(f"API 응답 본문: {response.text[:200] if response.text else '비어있음'}")
        
        if response.status_code == 404:
            # 404 오류인 경우 빈 결과 반환
            return {
                "rt_cd": "0",
                "msg_cd": "NODATA",
                "msg1": "모의투자 환경에서는 해당 API를 사용할 수 없습니다.",
                "output": []
            }
        
        if not response.text:
            return {
                "rt_cd": "0",
                "msg_cd": "NODATA",
                "msg1": "응답 데이터가 없습니다.",
                "output": []
            }
        
        try:
            result = response.json()
            return result
        except ValueError:
            # JSON 파싱 오류 시 빈 결과 반환
            return {
                "rt_cd": "0",
                "msg_cd": "PARSEERR",
                "msg1": "응답 파싱 오류",
                "output": []
            }
    except Exception as e:
        logger.error(f"주문체결내역 조회 중 오류 발생: {str(e)}")
        # 예외 발생 시 빈 결과 반환
        return {
            "rt_cd": "1", 
            "msg_cd": "ERROR",
            "msg1": f"API 호출 오류: {str(e)}",
            "output": []
        }

def get_overseas_order_resv_list(params):
    """해외주식 예약주문 조회"""
    try:
        # 모의투자 환경 확인
        is_virtual = settings.KIS_USE_MOCK
        
        if is_virtual:
            # 모의투자에서는 지원되지 않으므로 안내 메시지 반환
            return {
                "rt_cd": "0",
                "msg_cd": "MOCK_UNSUPPORTED",
                "msg1": "모의투자 환경에서는 해외주식 예약주문조회 API를 지원하지 않습니다.",
                "output": []
            }
        
        # 실전투자 환경에서 API 호출
        access_token = get_access_token()
        
        # 거래소 코드에 따라 TR_ID 결정
        ovrs_excg_cd = params.get("OVRS_EXCG_CD", "")
        if ovrs_excg_cd in ["NASD", "NYSE", "AMEX"] or not ovrs_excg_cd:
            # 미국 주식
            tr_id = "TTTT3039R"
        else:
            # 아시아 주식 (일본, 중국, 홍콩, 베트남)
            tr_id = "TTTS3014R"
            
        url = f"{settings.kis_base_url}/uapi/overseas-stock/v1/trading/order-resv-list"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": settings.KIS_APPKEY,
            "appsecret": settings.KIS_APPSECRET,
            "tr_id": tr_id,
        }
        
        # 디버깅 정보
        print(f"예약주문조회 API 요청: {url}")
        print(f"파라미터: {params}")
        
        response = requests.get(url, headers=headers, params=params)
        
        # 응답 확인
        print(f"API 응답 상태 코드: {response.status_code}")
        
        if response.status_code != 200:
            return {
                "rt_cd": "1",
                "msg_cd": f"HTTP_{response.status_code}",
                "msg1": f"API 호출 실패: HTTP {response.status_code}",
                "output": []
            }
        
        if not response.text:
            return {
                "rt_cd": "0",
                "msg_cd": "NODATA",
                "msg1": "응답 데이터가 없습니다.",
                "output": []
            }
        
        try:
            result = response.json()
            return result
        except ValueError:
            return {
                "rt_cd": "1",
                "msg_cd": "PARSEERR",
                "msg1": "응답 파싱 오류",
                "output": []
            }
    except Exception as e:
        print(f"예약주문조회 중 오류 발생: {str(e)}")
        return {
            "rt_cd": "1", 
            "msg_cd": "ERROR",
            "msg1": f"API 호출 오류: {str(e)}",
            "output": []
        }

def order_overseas_stock_daytime(order_data):
    """해외주식 주간주문 실행 (10:00 ~ 18:00 한국시간)"""
    try:
        # 토큰 가져오기
        access_token = get_access_token()
        
        # 기본 계좌정보 설정
        if "CANO" not in order_data or not order_data["CANO"]:
            order_data["CANO"] = settings.KIS_CANO
        if "ACNT_PRDT_CD" not in order_data or not order_data["ACNT_PRDT_CD"]:
            order_data["ACNT_PRDT_CD"] = settings.KIS_ACNT_PRDT_CD
        
        # 모의투자 미지원
        is_virtual = "openapivts" in settings.kis_base_url
        if is_virtual:
            return {
                "rt_cd": "1",
                "msg_cd": "MOCK_UNSUPPORTED",
                "msg1": "주간주문 API는 모의투자에서 지원되지 않습니다.",
                "output": {}
            }
        
        # 매수/매도 여부 확인
        is_buy = order_data.get("is_buy", True)
        
        # 주간주문 TR_ID 결정 (미국 주식만 지원)
        # 문서 참조: 미국주간매수 : TTTS6036U, 미국주간매도 : TTTS6037U
        if is_buy:
            tr_id = "TTTS6036U"  # 미국 주간 매수
        else:
            tr_id = "TTTS6037U"  # 미국 주간 매도
        
        # API 요청 URL 및 헤더 설정
        url = f"{settings.kis_base_url}/uapi/overseas-stock/v1/trading/daytime-order"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": settings.KIS_APPKEY,
            "appsecret": settings.KIS_APPSECRET,
            "tr_id": tr_id
        }
        
        # 필수 파라미터 준비 (요청 본문에서 is_buy 제거)
        request_body = order_data.copy()
        if "is_buy" in request_body:
            del request_body["is_buy"]
        
        # 기본 값 설정
        if "ORD_SVR_DVSN_CD" not in request_body:
            request_body["ORD_SVR_DVSN_CD"] = "0"  # 주문서버구분코드 (필수)
        
        # 주문구분 설정 (주간주문은 지정가만 가능)
        if "ORD_DVSN" not in request_body:
            request_body["ORD_DVSN"] = "00"  # 지정가
        
        # 디버깅 정보 로깅
        order_type = "매수" if is_buy else "매도"
        logger.debug(f"주간주문 요청 헤더: {headers}")
        logger.debug(f"주간주문 요청 본문: {request_body}")
        
        # API 호출
        response = requests.post(url, headers=headers, json=request_body)
        
        # 응답 처리
        if response.status_code != 200:
            # HTTP 에러 발생 시 응답 본문 로깅
            error_response_text = response.text[:500] if response.text else "(응답 본문 없음)"
            logger.error(f"주간주문 API HTTP {response.status_code} 에러 발생")
            logger.error(f"요청 URL: {url}")
            logger.error(f"요청 본문: {request_body}")
            logger.error(f"응답 본문: {error_response_text}")
            
            # 응답 본문을 JSON으로 파싱 시도
            try:
                error_result = response.json()
                error_msg = error_result.get("msg1", f"HTTP {response.status_code}")
                error_code = error_result.get("msg_cd", f"HTTP_{response.status_code}")
            except (ValueError, AttributeError):
                error_msg = f"API 호출 실패: HTTP {response.status_code}"
                error_code = f"HTTP_{response.status_code}"
            
            return {
                "rt_cd": "1",
                "msg_cd": error_code,
                "msg1": error_msg,
                "output": {}
            }
        
        try:
            result = response.json()
        except ValueError:
            logger.error(f"주간주문 API 응답 파싱 오류. 응답 본문: {response.text[:500]}")
            return {
                "rt_cd": "1",
                "msg_cd": "PARSEERR",
                "msg1": "응답 파싱 오류",
                "output": {}
            }
        
        # 주문 결과 로깅
        if result.get("rt_cd") == "0":
            logger.info(f"해외주식 주간 {order_type} 주문 성공: {result.get('msg1', '주문이 접수되었습니다.')}")
        else:
            logger.error(f"해외주식 주간 {order_type} 주문 실패: {result.get('msg1', '알 수 없는 오류')}")
            logger.error(f"오류 코드: {result.get('msg_cd')}, 종목={request_body.get('PDNO')}")
        
        return result
        
    except Exception as e:
        logger.error(f"해외주식 주간주문 중 오류 발생: {str(e)}", exc_info=True)
        return {
            "rt_cd": "1", 
            "msg_cd": "ERROR",
            "msg1": f"API 호출 오류: {str(e)}",
            "output": {}
        }

def order_overseas_stock(order_data):
    """해외주식 주문 실행"""
    try:
        # 토큰 가져오기
        access_token = get_access_token()
        
        # 기본 계좌정보 설정
        if "CANO" not in order_data or not order_data["CANO"]:
            order_data["CANO"] = settings.KIS_CANO
        if "ACNT_PRDT_CD" not in order_data or not order_data["ACNT_PRDT_CD"]:
            order_data["ACNT_PRDT_CD"] = settings.KIS_ACNT_PRDT_CD
            
        # 모의투자 여부 확인
        is_virtual = "openapivts" in settings.kis_base_url
        
        # 매수/매도 여부 확인
        is_buy = order_data.get("is_buy", True)
        
        # 거래소 코드에 따라 tr_id 결정
        ovrs_excg_cd = order_data.get("OVRS_EXCG_CD", "")
        
        # tr_id 결정 (매수/매도 및 거래소에 따라 다름)
        if ovrs_excg_cd in ["NASD", "NYSE", "AMEX"]:
            # 미국 주식
            if is_buy:
                tr_id = "VTTT1002U" if is_virtual else "TTTT1002U"  # 미국 매수
            else:
                tr_id = "VTTT1001U" if is_virtual else "TTTT1006U"  # 미국 매도
        elif ovrs_excg_cd == "TKSE":
            # 일본 주식
            if is_buy:
                tr_id = "VTTS0308U" if is_virtual else "TTTS0308U"  # 일본 매수
            else:
                tr_id = "VTTS0307U" if is_virtual else "TTTS0307U"  # 일본 매도
        elif ovrs_excg_cd == "SHAA":
            # 상해 주식
            if is_buy:
                tr_id = "VTTS0202U" if is_virtual else "TTTS0202U"  # 상해 매수
            else:
                tr_id = "VTTS1005U" if is_virtual else "TTTS1005U"  # 상해 매도
        elif ovrs_excg_cd == "SEHK":
            # 홍콩 주식
            if is_buy:
                tr_id = "VTTS1002U" if is_virtual else "TTTS1002U"  # 홍콩 매수
            else:
                tr_id = "VTTS1001U" if is_virtual else "TTTS1001U"  # 홍콩 매도
        elif ovrs_excg_cd == "SZAA":
            # 심천 주식
            if is_buy:
                tr_id = "VTTS0305U" if is_virtual else "TTTS0305U"  # 심천 매수
            else:
                tr_id = "VTTS0304U" if is_virtual else "TTTS0304U"  # 심천 매도
        elif ovrs_excg_cd in ["HASE", "VNSE"]:
            # 베트남 주식
            if is_buy:
                tr_id = "VTTS0311U" if is_virtual else "TTTS0311U"  # 베트남 매수
            else:
                tr_id = "VTTS0310U" if is_virtual else "TTTS0310U"  # 베트남 매도
        else:
            return {
                "rt_cd": "1",
                "msg_cd": "INVALID_EXCHANGE",
                "msg1": f"지원되지 않는 거래소 코드: {ovrs_excg_cd}",
                "output": {}
            }
        
        # API 요청 URL 및 헤더 설정
        url = f"{settings.kis_base_url}/uapi/overseas-stock/v1/trading/order"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": settings.KIS_APPKEY,
            "appsecret": settings.KIS_APPSECRET,
            "tr_id": tr_id
        }
        
        # 필수 파라미터 준비 (요청 본문에서 is_buy 제거)
        request_body = order_data.copy()
        if "is_buy" in request_body:
            del request_body["is_buy"]
        
        # 기본 값 설정
        if "ORD_SVR_DVSN_CD" not in request_body:
            request_body["ORD_SVR_DVSN_CD"] = "0"
        
        # 주문구분 설정 (기본값: 지정가)
        if "ORD_DVSN" not in request_body:
            request_body["ORD_DVSN"] = "00"  # 지정가
        
        # 디버깅 정보 로깅
        order_type = "매수" if is_buy else "매도"
        logger.debug(f"요청 헤더: {headers}")
        logger.debug(f"요청 본문: {request_body}")
        
        # API 호출
        response = requests.post(url, headers=headers, json=request_body)
        
        # 응답 확인
        
        # 응답 처리
        if response.status_code != 200:
            return {
                "rt_cd": "1",
                "msg_cd": f"HTTP_{response.status_code}",
                "msg1": f"API 호출 실패: HTTP {response.status_code}",
                "output": {}
            }
        
        try:
            result = response.json()
            
            # 주문 정보 추출
            ticker = request_body.get('PDNO', 'N/A')
            stock_name = request_body.get('stock_name', ticker)  # 종목명이 있으면 사용, 없으면 티커 사용
            quantity = int(request_body.get('ORD_QTY', 0))
            price = float(request_body.get('OVRS_ORD_UNPR', 0))
            exchange_code = request_body.get('OVRS_EXCG_CD', 'N/A')
            
            # 주문 결과 로깅 (슬랙 알림은 스케줄러에서 체결/실패 시에만 전송)
            if result.get("rt_cd") == "0":
                logger.info(f"해외주식 {order_type} 주문 성공: {result.get('msg1', '주문이 접수되었습니다.')}")
                # 주문 접수 성공 시 Slack 알림은 보내지 않음 (체결 확인 후 스케줄러에서 전송)
            else:
                error_msg = result.get('msg1', '알 수 없는 오류')
                error_code = result.get('msg_cd', '')
                logger.error(f"해외주식 {order_type} 주문 실패: {error_msg}")
                logger.error(f"오류 코드: {error_code}, 종목={request_body.get('PDNO')}")
                
                # 장외거래시간 에러인 경우 슬랙 알림 보내지 않음
                if "장운영시간" in error_msg or "APBK0918" in error_code:
                    logger.info(f"장외거래시간 주문 실패로 슬랙 알림을 보내지 않습니다: {error_msg}")
                else:
                    # 슬랙 알림 전송 (실패) - 장외거래시간 에러가 아닌 경우에만
                    if is_buy:
                        slack_notifier.send_buy_notification(
                            stock_name=stock_name,  # 종목명 사용
                            ticker=ticker,
                            quantity=quantity,
                            price=price,
                            exchange_code=exchange_code,
                            success=False,
                            error_message=error_msg
                        )
                    else:
                        slack_notifier.send_sell_notification(
                            stock_name=stock_name,  # 종목명 사용
                            ticker=ticker,
                            quantity=quantity,
                            price=price,
                            exchange_code=exchange_code,
                            sell_reasons=["수동 매도"],
                            success=False,
                            error_message=error_msg
                        )
            
            # 주문 내역을 DB에 저장 (옵션)
            # save_order_history(request_body, result)
            return result
        except ValueError:
            logger.error("주문 API 응답 파싱 오류")
            return {
                "rt_cd": "1",
                "msg_cd": "PARSEERR",
                "msg1": "응답 파싱 오류",
                "output": {}
            }
    except Exception as e:
        logger.error(f"해외주식 주문 중 오류 발생: {str(e)}", exc_info=True)
        return {
            "rt_cd": "1", 
            "msg_cd": "ERROR",
            "msg1": f"API 호출 오류: {str(e)}",
            "output": {}
        }

def create_conditional_orders(params):
    """
    특정 가격에 도달했을 때 자동으로 실행되는 조건부 주문 설정
    손절매(stop loss)와 이익실현(take profit) 주문을 동시에 설정
    """
    try:
        # 1. 해외주식 잔고 조회
        balance_result = get_overseas_balance()
        
        if balance_result.get("rt_cd") != "0":
            return {
                "rt_cd": "1",
                "msg_cd": "BALANCE_ERROR",
                "msg1": f"잔고 조회 실패: {balance_result.get('msg1', '알 수 없는 오류')}",
                "output": {}
            }
        
        # 2. 종목 정보 찾기
        pdno = params.get("pdno")
        ovrs_excg_cd = params.get("ovrs_excg_cd")
        
        holdings = balance_result.get("output1", [])
        target_holding = None
        
        for holding in holdings:
            if holding.get("ovrs_pdno") == pdno:
                target_holding = holding
                break
        
        if not target_holding:
            return {
                "rt_cd": "1",
                "msg_cd": "NO_HOLDING",
                "msg1": f"해당 종목({pdno})을 보유하고 있지 않습니다.",
                "output": {}
            }
        
        # 3. 기준 가격, 손절매 가격, 이익실현 가격 계산
        base_price = params.get("base_price")
        if not base_price:
            # 매수 평균단가를 기준 가격으로 사용
            base_price = float(target_holding.get("pchs_avg_pric", "0"))
            
        if base_price <= 0:
            return {
                "rt_cd": "1",
                "msg_cd": "INVALID_PRICE",
                "msg1": "유효하지 않은 기준 가격입니다.",
                "output": {}
            }
        
        # 손절매, Profit Taking 퍼센트 설정
        stop_loss_percent = params.get("stop_loss_percent", -5.0)
        take_profit_percent = params.get("take_profit_percent", 5.0)
        
        # 가격 계산
        stop_loss_price = round(base_price * (1 + stop_loss_percent/100), 2)
        take_profit_price = round(base_price * (1 + take_profit_percent/100), 2)
        
        # 주문 수량 설정 (params에 quantity가 없으면 전체 보유 수량 사용)
        quantity = params.get("quantity", target_holding.get("ord_psbl_qty", "0"))
        
        # 4. 손절매 및 이익실현 주문 생성
        order_results = []
        
        # 손절매 주문 생성 (마이너스이면 실행)
        if stop_loss_percent < 0:
            stop_loss_order = {
                "CANO": settings.KIS_CANO,
                "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
                "PDNO": pdno,
                "OVRS_EXCG_CD": ovrs_excg_cd,
                "FT_ORD_QTY": quantity,
                "FT_ORD_UNPR3": str(stop_loss_price),
                "is_buy": False,  # 매도
                "ORD_DVSN": "00"  # 지정가
            }
            
            stop_loss_result = overseas_order_resv(stop_loss_order)
            stop_loss_result["order_type"] = "stop_loss"
            order_results.append(stop_loss_result)
        
        # 이익실현 주문 생성 (플러스이면 실행)
        if take_profit_percent > 0:
            take_profit_order = {
                "CANO": settings.KIS_CANO,
                "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
                "PDNO": pdno,
                "OVRS_EXCG_CD": ovrs_excg_cd,
                "FT_ORD_QTY": quantity,
                "FT_ORD_UNPR3": str(take_profit_price),
                "is_buy": False,  # 매도
                "ORD_DVSN": "00"  # 지정가
            }
            
            take_profit_result = overseas_order_resv(take_profit_order)
            take_profit_result["order_type"] = "take_profit"
            order_results.append(take_profit_result)
        
        # 5. 결과 반환
        success_count = sum(1 for r in order_results if r.get("rt_cd") == "0")
        
        return {
            "rt_cd": "0" if success_count > 0 else "1",
            "msg_cd": "SUCCESS" if success_count == len(order_results) else "PARTIAL_SUCCESS" if success_count > 0 else "FAILED",
            "msg1": f"{success_count}/{len(order_results)} 주문이 성공적으로 처리되었습니다.",
            "base_price": base_price,
            "stop_loss_price": stop_loss_price,
            "take_profit_price": take_profit_price,
            "order_results": order_results
        }
        
    except Exception as e:
        print(f"조건부 주문 생성 중 오류 발생: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return {
            "rt_cd": "1",
            "msg_cd": "ERROR",
            "msg1": f"조건부 주문 생성 중 오류 발생: {str(e)}",
            "output": {}
        }

def calculate_portfolio_profit():
    """
    계좌의 주식 수익율을 계산합니다.
    
    Returns:
        dict: {
            "success": bool,
            "holdings": list,  # 각 종목별 수익율 정보
            "total_cost": float,  # 총 매수금액
            "total_value": float,  # 총 평가금액
            "total_profit": float,  # 총 수익
            "total_profit_percent": float,  # 총 수익율 (%)
            "error": str (optional)
        }
    """
    try:
        # 모든 거래소의 잔고 조회
        balance_result = get_all_overseas_balances()
        
        if balance_result.get("rt_cd") != "0":
            return {
                "success": False,
                "holdings": [],
                "total_cost": 0.0,
                "total_value": 0.0,
                "total_profit": 0.0,
                "total_profit_percent": 0.0,
                "error": balance_result.get('msg1', '잔고 조회 실패')
            }
        
        holdings_data = balance_result.get("output1", [])
        
        if not holdings_data:
            return {
                "success": True,
                "holdings": [],
                "total_cost": 0.0,
                "total_value": 0.0,
                "total_profit": 0.0,
                "total_profit_percent": 0.0
            }
        
        # MongoDB에서 티커 -> 주식명 매핑 조회
        ticker_to_name = {}
        try:
            from app.db.mongodb import get_db
            db = get_db()
            if db is not None:
                stocks = db.stocks.find({})
                for stock in stocks:
                    ticker = stock.get("ticker")
                    stock_name = stock.get("stock_name")
                    if ticker and stock_name:
                        ticker_to_name[ticker] = stock_name
        except Exception as e:
            logger.warning(f"주식명 매핑 조회 중 오류: {str(e)}")
        
        # 티커별로 그룹화하여 중복 제거 (여러 거래소에 상장된 경우 대비)
        ticker_dict = {}
        
        for item in holdings_data:
            try:
                ticker = item.get("ovrs_pdno", "")
                if not ticker:
                    continue
                
                # 보유 수량
                quantity = float(item.get("ovrs_cblc_qty", "0") or "0")
                if quantity <= 0:
                    continue
                
                # 매수 평균단가
                avg_price = float(item.get("pchs_avg_pric", "0") or "0")
                if avg_price <= 0:
                    continue
                
                # 현재가
                current_price = float(item.get("now_pric2", "0") or "0")
                if current_price <= 0:
                    # 현재가가 없으면 평균단가로 대체
                    current_price = avg_price
                
                # 주식명 조회
                stock_name = ticker_to_name.get(ticker, ticker)
                
                # 매수금액 (수량 * 평균단가)
                cost = quantity * avg_price
                
                # 같은 티커가 이미 존재하는 경우 통합
                if ticker in ticker_dict:
                    existing = ticker_dict[ticker]
                    # 수량 합산
                    total_quantity = existing["quantity"] + quantity
                    # 가중평균단가 계산: (기존 매수금액 + 새 매수금액) / (기존 수량 + 새 수량)
                    total_cost_combined = existing["cost"] + cost
                    weighted_avg_price = total_cost_combined / total_quantity if total_quantity > 0 else avg_price
                    
                    # 현재가는 마지막 값 사용 (같은 종목이면 동일할 것)
                    ticker_dict[ticker] = {
                        "ticker": ticker,
                        "stock_name": stock_name,  # 주식명은 동일할 것
                        "quantity": total_quantity,
                        "avg_price": weighted_avg_price,
                        "current_price": current_price,  # 마지막 현재가 사용
                        "cost": total_cost_combined,
                        "value": total_quantity * current_price,  # 합산된 수량 * 현재가
                    }
                else:
                    # 새로운 티커인 경우
                    ticker_dict[ticker] = {
                        "ticker": ticker,
                        "stock_name": stock_name,
                        "quantity": quantity,
                        "avg_price": avg_price,
                        "current_price": current_price,
                        "cost": cost,
                        "value": quantity * current_price,
                    }
                
            except (ValueError, TypeError) as e:
                logger.warning(f"종목 수익율 계산 중 오류 (티커: {item.get('ovrs_pdno', 'N/A')}): {str(e)}")
                continue
        
        # 딕셔너리를 리스트로 변환하고 수익 계산
        holdings = []
        total_cost = 0.0
        total_value = 0.0
        
        for ticker, holding_data in ticker_dict.items():
            cost = holding_data["cost"]
            value = holding_data["value"]
            profit = value - cost
            profit_percent = (profit / cost * 100) if cost > 0 else 0.0
            
            holdings.append({
                "ticker": holding_data["ticker"],
                "stock_name": holding_data["stock_name"],
                "quantity": int(holding_data["quantity"]),
                "avg_price": holding_data["avg_price"],
                "current_price": holding_data["current_price"],
                "cost": cost,
                "value": value,
                "profit": profit,
                "profit_percent": profit_percent
            })
            
            total_cost += cost
            total_value += value
        
        # 총 수익 계산
        total_profit = total_value - total_cost
        total_profit_percent = (total_profit / total_cost * 100) if total_cost > 0 else 0.0
        
        return {
            "success": True,
            "holdings": holdings,
            "total_cost": total_cost,
            "total_value": total_value,
            "total_profit": total_profit,
            "total_profit_percent": total_profit_percent
        }
        
    except Exception as e:
        logger.error(f"계좌 수익율 계산 중 오류: {str(e)}", exc_info=True)
        return {
            "success": False,
            "holdings": [],
            "total_cost": 0.0,
            "total_value": 0.0,
            "total_profit": 0.0,
            "total_profit_percent": 0.0,
            "error": str(e)
        }


def calculate_cumulative_profit(user_id: str, days: int = 90, ticker: str = None):
    """
    완료된 거래(매수→매도)의 누적 수익률을 계산합니다.
    FIFO (First In First Out) 방식으로 매수/매도 거래를 매칭합니다.
    
    Args:
        user_id: 사용자 ID (필수)
        days: 조회 기간 (일, 기본값: 90일)
        ticker: 특정 티커만 조회 (선택사항, None이면 전체)
    
    Returns:
        dict: {
            "success": bool,
            "trades": list,  # 완료된 거래 목록 (매수→매도 매칭)
            "statistics": dict,  # 통계 정보
                - total_trades: 총 거래 횟수
                - winning_trades: 수익 거래 횟수
                - losing_trades: 손실 거래 횟수
                - win_rate: 승률 (%)
                - total_profit: 총 실현 수익 (USD)
                - total_cost: 총 매수 금액 (USD)
                - total_profit_percent: 총 수익률 (%)
                - avg_profit_percent: 평균 수익률 (%)
                - avg_winning_profit_percent: 평균 수익 거래 수익률 (%)
                - avg_losing_profit_percent: 평균 손실 거래 손실률 (%)
            "by_ticker": dict,  # 티커별 통계
            "error": str (optional)
        }
    """
    try:
        from datetime import datetime, timedelta
        
        if not user_id:
            return {
                "success": False,
                "trades": [],
                "statistics": {},
                "by_ticker": {},
                "error": "user_id는 필수입니다"
            }
        
        db = get_db()
        if db is None:
            return {
                "success": False,
                "trades": [],
                "statistics": {},
                "by_ticker": {},
                "error": "MongoDB 연결 실패"
            }
        
        # 조회 기간 설정
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # 거래 로그 조회 (user_id 필터 추가)
        query = {
            "user_id": user_id,  # 사용자별 필터링
            "created_at": {"$gte": start_date, "$lte": end_date},
            "status": {"$in": [OrderStatus.EXECUTED.value, OrderStatus.SUCCESS.value]}  # 체결된 거래만
        }
        
        if ticker:
            query["ticker"] = ticker
        
        # 매수 거래 조회
        buy_orders = list(db.trading_logs.find({
            **query,
            "order_type": "buy"
        }).sort("created_at", 1))  # 시간순 정렬
        
        # 매도 거래 조회
        sell_orders = list(db.trading_logs.find({
            **query,
            "order_type": "sell"
        }).sort("created_at", 1))  # 시간순 정렬
        
        if not buy_orders or not sell_orders:
            return {
                "success": True,
                "trades": [],
                "statistics": {
                    "total_trades": 0,
                    "winning_trades": 0,
                    "losing_trades": 0,
                    "win_rate": 0.0,
                    "total_profit": 0.0,
                    "total_cost": 0.0,
                    "total_profit_percent": 0.0,
                    "avg_profit_percent": 0.0,
                    "avg_winning_profit_percent": 0.0,
                    "avg_losing_profit_percent": 0.0
                },
                "by_ticker": {}
            }
        
        # FIFO 방식으로 매수/매도 매칭
        completed_trades = []
        
        # 티커별로 그룹화
        buy_by_ticker = {}
        for buy in buy_orders:
            ticker_key = buy.get("ticker", "")
            if ticker_key not in buy_by_ticker:
                buy_by_ticker[ticker_key] = []
            buy_by_ticker[ticker_key].append(buy)
        
        sell_by_ticker = {}
        for sell in sell_orders:
            ticker_key = sell.get("ticker", "")
            if ticker_key not in sell_by_ticker:
                sell_by_ticker[ticker_key] = []
            sell_by_ticker[ticker_key].append(sell)
        
        # 각 티커별로 매칭
        for ticker_key in set(list(buy_by_ticker.keys()) + list(sell_by_ticker.keys())):
            buys = buy_by_ticker.get(ticker_key, [])
            sells = sell_by_ticker.get(ticker_key, [])
            
            if not buys or not sells:
                continue
            
            # FIFO 매칭: 매수 큐와 매도 큐를 사용
            buy_queue = []
            sell_queue = []
            
            all_orders = sorted(
                buys + sells,
                key=lambda x: x.get("created_at", datetime.min)
            )
            
            for order in all_orders:
                if order.get("order_type") == "buy":
                    buy_queue.append(order)
                elif order.get("order_type") == "sell":
                    sell_queue.append(order)
                    
                    # 매도가 있으면 가장 오래된 매수와 매칭
                    while buy_queue and sell_queue:
                        buy_order = buy_queue[0]
                        sell_order = sell_queue[0]
                        
                        buy_price = buy_order.get("price", 0)
                        buy_qty = buy_order.get("quantity", 0)
                        sell_price = sell_order.get("price", 0)
                        sell_qty = sell_order.get("quantity", 0)
                        
                        if buy_price <= 0 or buy_qty <= 0 or sell_price <= 0 or sell_qty <= 0:
                            # 유효하지 않은 거래는 스킵
                            if buy_price <= 0 or buy_qty <= 0:
                                buy_queue.pop(0)
                            if sell_price <= 0 or sell_qty <= 0:
                                sell_queue.pop(0)
                            continue
                        
                        # 매칭 수량 결정
                        matched_qty = min(buy_qty, sell_qty)
                        
                        # 수익 계산
                        cost = buy_price * matched_qty
                        revenue = sell_price * matched_qty
                        profit = revenue - cost
                        profit_percent = (profit / cost * 100) if cost > 0 else 0.0
                        
                        # 거래 기간 계산
                        buy_date = buy_order.get("created_at")
                        sell_date = sell_order.get("created_at")
                        if isinstance(buy_date, str):
                            buy_date = datetime.fromisoformat(buy_date.replace('Z', '+00:00'))
                        if isinstance(sell_date, str):
                            sell_date = datetime.fromisoformat(sell_date.replace('Z', '+00:00'))
                        
                        holding_days = (sell_date - buy_date).days if buy_date and sell_date else 0
                        
                        completed_trades.append({
                            "ticker": ticker_key,
                            "stock_name": buy_order.get("stock_name", ticker_key),
                            "buy_date": buy_date.isoformat() if buy_date else None,
                            "sell_date": sell_date.isoformat() if sell_date else None,
                            "holding_days": holding_days,
                            "buy_price": buy_price,
                            "sell_price": sell_price,
                            "quantity": matched_qty,
                            "cost": cost,
                            "revenue": revenue,
                            "profit": profit,
                            "profit_percent": profit_percent,
                            "sell_reasons": sell_order.get("sell_reasons", [])
                        })
                        
                        # 사용된 수량만큼 차감
                        buy_qty -= matched_qty
                        sell_qty -= matched_qty
                        
                        if buy_qty <= 0:
                            buy_queue.pop(0)
                        else:
                            buy_queue[0]["quantity"] = buy_qty
                        
                        if sell_qty <= 0:
                            sell_queue.pop(0)
                        else:
                            sell_queue[0]["quantity"] = sell_qty
        
        # 통계 계산
        if not completed_trades:
            return {
                "success": True,
                "trades": [],
                "statistics": {
                    "total_trades": 0,
                    "winning_trades": 0,
                    "losing_trades": 0,
                    "win_rate": 0.0,
                    "total_profit": 0.0,
                    "total_cost": 0.0,
                    "total_profit_percent": 0.0,
                    "avg_profit_percent": 0.0,
                    "avg_winning_profit_percent": 0.0,
                    "avg_losing_profit_percent": 0.0
                },
                "by_ticker": {}
            }
        
        total_trades = len(completed_trades)
        winning_trades = [t for t in completed_trades if t["profit"] > 0]
        losing_trades = [t for t in completed_trades if t["profit"] < 0]
        
        total_cost = sum(t["cost"] for t in completed_trades)
        total_profit = sum(t["profit"] for t in completed_trades)
        total_profit_percent = (total_profit / total_cost * 100) if total_cost > 0 else 0.0
        
        avg_profit_percent = (sum(t["profit_percent"] for t in completed_trades) / total_trades) if total_trades > 0 else 0.0
        
        avg_winning_profit_percent = (
            sum(t["profit_percent"] for t in winning_trades) / len(winning_trades)
        ) if winning_trades else 0.0
        
        avg_losing_profit_percent = (
            sum(t["profit_percent"] for t in losing_trades) / len(losing_trades)
        ) if losing_trades else 0.0
        
        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0.0
        
        # 티커별 통계
        by_ticker = {}
        for trade in completed_trades:
            ticker_key = trade["ticker"]
            if ticker_key not in by_ticker:
                by_ticker[ticker_key] = {
                    "ticker": ticker_key,
                    "stock_name": trade["stock_name"],
                    "trades": 0,
                    "winning_trades": 0,
                    "losing_trades": 0,
                    "win_rate": 0.0,
                    "total_profit": 0.0,
                    "total_cost": 0.0,
                    "total_profit_percent": 0.0,
                    "avg_profit_percent": 0.0
                }
            
            by_ticker[ticker_key]["trades"] += 1
            by_ticker[ticker_key]["total_profit"] += trade["profit"]
            by_ticker[ticker_key]["total_cost"] += trade["cost"]
            
            if trade["profit"] > 0:
                by_ticker[ticker_key]["winning_trades"] += 1
            elif trade["profit"] < 0:
                by_ticker[ticker_key]["losing_trades"] += 1
        
        # 티커별 통계 계산
        for ticker_key in by_ticker:
            stats = by_ticker[ticker_key]
            stats["win_rate"] = (stats["winning_trades"] / stats["trades"] * 100) if stats["trades"] > 0 else 0.0
            stats["total_profit_percent"] = (stats["total_profit"] / stats["total_cost"] * 100) if stats["total_cost"] > 0 else 0.0
            
            # 티커별 평균 수익률 계산
            ticker_trades = [t for t in completed_trades if t["ticker"] == ticker_key]
            stats["avg_profit_percent"] = (
                sum(t["profit_percent"] for t in ticker_trades) / len(ticker_trades)
            ) if ticker_trades else 0.0
        
        return {
            "success": True,
            "trades": completed_trades,
            "statistics": {
                "total_trades": total_trades,
                "winning_trades": len(winning_trades),
                "losing_trades": len(losing_trades),
                "win_rate": round(win_rate, 2),
                "total_profit": round(total_profit, 2),
                "total_cost": round(total_cost, 2),
                "total_profit_percent": round(total_profit_percent, 2),
                "avg_profit_percent": round(avg_profit_percent, 2),
                "avg_winning_profit_percent": round(avg_winning_profit_percent, 2),
                "avg_losing_profit_percent": round(avg_losing_profit_percent, 2)
            },
            "by_ticker": list(by_ticker.values())
        }
        
    except Exception as e:
        logger.error(f"누적 수익률 계산 중 오류: {str(e)}", exc_info=True)
        return {
            "success": False,
            "trades": [],
            "statistics": {},
            "by_ticker": {},
            "error": str(e)
        }
    