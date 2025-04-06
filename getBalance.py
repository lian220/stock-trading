import requests
import json
from datetime import datetime, timedelta
import pytz  # timezone 처리를 위한 패키지
from dbConnection import supabase

def get_token():
    """토큰 조회 또는 갱신"""
    try:
        # 테이블에서 토큰 레코드 조회
        response = supabase.table("access_tokens").select("*").limit(1).execute()
        
        # 토큰 레코드가 있는지 확인
        if response.data:
            token_data = response.data[0]
            # timezone 정보를 처리하기 위해 수정
            created_at = datetime.fromisoformat(token_data["created_at"].replace('Z', '+00:00'))
            now = datetime.now(pytz.UTC)  # 현재 시간을 UTC로 가져오기
            
            # 토큰 생성 후 정확히 24시간이 지났는지 확인
            time_since_creation = now - created_at
            if time_since_creation.total_seconds() < 24 * 60 * 60:  # 24시간(초 단위)
                print("기존 토큰 사용 - 생성 후 경과 시간:", time_since_creation)
                return token_data["access_token"]
            
            print("토큰 생성 후 24시간 경과, 갱신 가능")
        else:
            print("토큰 레코드 없음, 새로 생성")
            
        # 레코드가 없거나 토큰이 24시간 이상 지난 경우 새 토큰 발급 및 저장
        return refresh_token(response.data[0]["id"] if response.data else None)
    except Exception as e:
        print(f"토큰 조회 오류: {e}")
        # 오류 발생시 임시 하드코딩된 토큰 반환
        return "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJ0b2tlbiIsImF1ZCI6ImQ5YzA3Mjk1LTQxZmQtNDQ5Ny1hNTY0LTFkYTI5NjliZGM3MiIsInByZHRfY2QiOiIiLCJpc3MiOiJ1bm9ndyIsImV4cCI6MTc0MDM1MzE5MywiaWF0IjoxNzQwMjY2NzkzLCJqdGkiOiJQU3RVclY1ZWVaS0h0T0U2eEQzb1MxTFFMaEVPUTA0azNJb00ifQ.nPLU-xv6FSLXd88TNoaPRPkmSgjLBht84P6DBR5JMDXvkeOVLbXWigmVaxPx_sqwkSVZjsRa2E0GoC2RWUuPrQ"

def refresh_token(record_id=None):
    """새 토큰 발급 및 DB 업데이트"""
    try:
        # 새 토큰 발급
        url = "https://openapivts.koreainvestment.com:29443/oauth2/tokenP"
        
        data = {
            "grant_type": "client_credentials",
            "appkey": "PStUrV5eeZKHtOE6xD3oS1LQLhEOQ04k3IoM",
            "appsecret": "QNwNjrWXE11vewZ2eNMrSds5LivoCLOb894i643bXOuzsH4JYns5zi3JX4rLg6Sq5k28uhHs0m9JjMfHsqaKspy2ipRIok7XAC3fuRJRq1DvAhCYDblv+CieF7QlUl9riV4X+6SNU/L/YZFz+QFjmuthUVx15+hBn0lCJv7iZOWLekcfOV8="
        }
        
        response = requests.post(url, json=data)
        response_data = response.json()
        access_token = response_data["access_token"]
        
        # 현재 시간과 만료 시간 계산 (하루 후) - UTC 기준으로 통일
        now = datetime.now(pytz.UTC)
        expiration_time = now + timedelta(days=1)
        
        # 토큰 데이터 준비
        token_data = {
            "access_token": access_token,
            "created_at": now.isoformat(),
            "expiration_time": expiration_time.isoformat()
        }
        
        # 레코드 ID가 있으면 업데이트, 없으면 새로 생성
        if record_id:
            supabase.table("access_tokens").update(token_data).eq("id", record_id).execute()
            print("토큰 업데이트 완료")
        else:
            supabase.table("access_tokens").insert(token_data).execute()
            print("새 토큰 레코드 생성 완료")
        
        return access_token
    except Exception as e:
        print(f"토큰 갱신 오류: {e}")
        # 오류 발생시 하드코딩된 토큰 반환 (임시 방편)
        return "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJ0b2tlbiIsImF1ZCI6ImQ5YzA3Mjk1LTQxZmQtNDQ5Ny1hNTY0LTFkYTI5NjliZGM3MiIsInByZHRfY2QiOiIiLCJpc3MiOiJ1bm9ndyIsImV4cCI6MTc0MDM1MzE5MywiaWF0IjoxNzQwMjY2NzkzLCJqdGkiOiJQU3RVclY1ZWVaS0h0T0U2eEQzb1MxTFFMaEVPUTA0azNJb00ifQ.nPLU-xv6FSLXd88TNoaPRPkmSgjLBht84P6DBR5JMDXvkeOVLbXWigmVaxPx_sqwkSVZjsRa2E0GoC2RWUuPrQ"

def get_domestic_balance():
    """국내주식 잔고 조회"""
    # 토큰 가져오기
    access_token = get_token()
    
    url = "https://openapivts.koreainvestment.com:29443/uapi/domestic-stock/v1/trading/inquire-balance"
    
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": "PStUrV5eeZKHtOE6xD3oS1LQLhEOQ04k3IoM",
        "appsecret": "QNwNjrWXE11vewZ2eNMrSds5LivoCLOb894i643bXOuzsH4JYns5zi3JX4rLg6Sq5k28uhHs0m9JjMfHsqaKspy2ipRIok7XAC3fuRJRq1DvAhCYDblv+CieF7QlUl9riV4X+6SNU/L/YZFz+QFjmuthUVx15+hBn0lCJv7iZOWLekcfOV8=",
        "tr_id": "VTTC8434R"
    }
    
    params = {
        "CANO": "50124930",
        "ACNT_PRDT_CD": "01",
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
    
    response = requests.get(url, headers=headers, params=params)
    return response.json()

def get_overseas_balance():
    """해외주식 잔고 조회"""
    # 토큰 가져오기
    access_token = get_token()
    
    url = "https://openapivts.koreainvestment.com:29443/uapi/overseas-stock/v1/trading/inquire-balance"
    
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": "PStUrV5eeZKHtOE6xD3oS1LQLhEOQ04k3IoM",
        "appsecret": "QNwNjrWXE11vewZ2eNMrSds5LivoCLOb894i643bXOuzsH4JYns5zi3JX4rLg6Sq5k28uhHs0m9JjMfHsqaKspy2ipRIok7XAC3fuRJRq1DvAhCYDblv+CieF7QlUl9riV4X+6SNU/L/YZFz+QFjmuthUVx15+hBn0lCJv7iZOWLekcfOV8=",
        "tr_id": "VTTS3012R"
    }
    
    params = {
        "CANO": "50124930",
        "ACNT_PRDT_CD": "01",
        "OVRS_EXCG_CD": "NASD",  # NASD: 나스닥, NYSE: 뉴욕, AMEX: 아멕스
        "TR_CRCY_CD": "USD",     # 통화코드 USD
        "CTX_AREA_FK200": "",
        "CTX_AREA_NK200": ""
    }
    
    response = requests.get(url, headers=headers, params=params)
    return response.json()

if __name__ == "__main__":
    # 국내주식 잔고 조회
    result = get_domestic_balance()
    print("국내주식 잔고:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # 해외주식 잔고 조회
    result = get_overseas_balance()
    print("해외주식 잔고:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
