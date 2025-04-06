from supabase import create_client, Client

url: str = "https://kygqxmuwhwfsywkdvadb.supabase.co"
key: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imt5Z3F4bXV3aHdmc3l3a2R2YWRiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDA5Njc5ODMsImV4cCI6MjA1NjU0Mzk4M30.ZUP0bmeUBFF9ZbzzD1BXXWkdeLBpbUQ1-aJKZDukw3c"
supabase: Client = create_client(url, key)

def get_data(table_name):
    """Supabase에서 데이터 가져오기"""
    try:
        response = supabase.table(table_name).select("*").execute()
        print(f"{table_name}에서 데이터를 성공적으로 가져왔습니다!")
        return response.data
    except Exception as e:
        print(f"데이터 가져오기 오류: {e}")
        return None

# 테스트
if __name__ == "__main__":
    # 테이블 이름을 실제 테이블 이름으로 변경하세요
    data = get_data("your_table_name")
    print(data)