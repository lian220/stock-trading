"""
Supabase 연결 모듈 (레거시 호환성 유지)
새로운 코드는 app.infrastructure.database.supabase_client를 사용하세요.
"""
from app.infrastructure.database.supabase_client import get_supabase_client

# 레거시 호환성을 위한 전역 변수
supabase = None

def _get_supabase():
    """레거시 호환성을 위한 Supabase 클라이언트 반환"""
    global supabase
    if supabase is None:
        supabase = get_supabase_client()
    return supabase

def get_data(table_name):
    """Supabase에서 데이터 가져오기 (레거시 호환성)"""
    try:
        client = _get_supabase()
        if not client:
            return None
        response = client.table(table_name).select("*").execute()
        print(f"{table_name}에서 데이터를 성공적으로 가져왔습니다!")
        return response.data
    except Exception as e:
        print(f"데이터 가져오기 오류: {e}")
        return None

# 레거시 호환성을 위해 전역 변수 초기화
supabase = _get_supabase()