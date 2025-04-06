from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel
from typing import List, Optional, Dict
import pandas as pd
from datetime import datetime
import json

# 기존 모듈 임포트
from dbConnection import supabase
from getBalance import get_domestic_balance
import stock  # stock.py 모듈 임포트

app = FastAPI(
    title="주식 분석 API",
    description="해외주식 잔고 조회 및 주식 예측 API",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 오리진 허용 (실제 운영에서는 특정 도메인만 허용하는 것이 좋습니다)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 모델 정의
class StockPrediction(BaseModel):
    stock: str
    last_price: float
    predicted_price: float
    rise_probability: float
    recommendation: str
    analysis: str

class UpdateResponse(BaseModel):
    success: bool
    message: str
    total_records: int
    updated_records: int

@app.get("/")
def read_root():
    return {"message": "주식 분석 API에 오신 것을 환영합니다!"}

@app.get("/balance", summary="해외주식 잔고 조회")
def get_balance():
    try:
        result = get_domestic_balance()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"잔고 조회 중 오류 발생: {str(e)}")

@app.get("/predictions", summary="주식 예측 결과 조회", response_model=List[StockPrediction])
def get_predictions():
    try:
        # 여기서는 CSV 파일에서 예측 결과를 읽어오는 예시입니다.
        # 실제로는 데이터베이스에서 가져오거나 예측 모델을 직접 실행할 수 있습니다.
        df = pd.read_csv("final_stock_analysis.csv")
        
        predictions = []
        for _, row in df.iterrows():
            predictions.append(
                StockPrediction(
                    stock=row["Stock"],
                    last_price=row["Last Actual Price"],
                    predicted_price=row["Predicted Future Price"],
                    rise_probability=row["Rise Probability (%)"],
                    recommendation=row["Recommendation"],
                    analysis=row["Analysis"]
                )
            )
        return predictions
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"예측 결과 조회 중 오류 발생: {str(e)}")

@app.get("/stock/{ticker}", summary="특정 주식 정보 조회")
def get_stock_info(ticker: str):
    try:
        # 여기서는 Supabase에서 특정 주식 정보를 조회하는 예시입니다.
        response = supabase.table("stocks").select("*").eq("symbol", ticker).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail=f"{ticker} 주식 정보를 찾을 수 없습니다.")
        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"주식 정보 조회 중 오류 발생: {str(e)}")

@app.post("/update_data", summary="경제 및 주식 데이터 업데이트", response_model=UpdateResponse)
async def update_economic_data(background_tasks: BackgroundTasks):
    """
    stock.py에서 수집한 경제 및 주식 데이터를 Supabase에 저장합니다.
    이 작업은 백그라운드에서 실행되어 API 응답을 블로킹하지 않습니다.
    """
    try:
        # 백그라운드 작업으로 데이터 업데이트 실행
        background_tasks.add_task(update_data_in_background)
        
        return {
            "success": True,
            "message": "데이터 업데이트가 백그라운드에서 시작되었습니다.",
            "total_records": 0,  # 백그라운드에서 처리되므로 여기서는 0
            "updated_records": 0  # 백그라운드에서 처리되므로 여기서는 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터 업데이트 중 오류 발생: {str(e)}")

async def update_data_in_background():
    """백그라운드에서 데이터를 업데이트하는 함수"""
    try:
        # 이미 처리된 stock.py의 result_df 데이터프레임 사용
        df = stock.result_df
        
        # 날짜 형식 변환 (인덱스가 날짜인 경우)
        df = df.reset_index()
        df['날짜'] = pd.to_datetime(df['date']).dt.date if 'date' in df.columns else pd.to_datetime(df.index).date
        
        # 배치 크기 설정 (Supabase는 한 번에 너무 많은 레코드를 처리하지 못할 수 있음)
        batch_size = 100
        total_records = len(df)
        updated_records = 0
        
        # 배치 처리
        for i in range(0, total_records, batch_size):
            batch = df.iloc[i:min(i+batch_size, total_records)]
            
            # 각 레코드를 딕셔너리로 변환하여 Supabase에 업로드
            records = []
            for _, row in batch.iterrows():
                record = {'날짜': str(row['날짜'])}
                
                # DDL에 정의된 컬럼만 포함
                for column in [
                    '10년 기대 인플레이션율', '장단기 금리차', '기준금리', '미시간대 소비자 심리지수',
                    '실업률', '2년 만기 미국 국채 수익률', '10년 만기 미국 국채 수익률', '금융스트레스지수',
                    '개인 소비 지출', '소비자 물가지수', '5년 변동금리 모기지', '미국 달러 환율',
                    '통화 공급량 M2', '가계 부채 비율', 'GDP 성장률', '나스닥 종합지수',
                    'S&P 500 지수', '금 가격', '달러 인덱스', '나스닥 100',
                    'S&P 500 ETF', 'QQQ ETF', '러셀 2000 ETF', '다우 존스 ETF',
                    'VIX 지수', '닛케이 225', '상해종합', '항셍',
                    '영국 FTSE', '독일 DAX', '프랑스 CAC 40', '미국 전체 채권시장 ETF',
                    'TIPS ETF', '투자등급 회사채 ETF', '달러/엔', '달러/위안',
                    '미국 리츠 ETF', '애플', '마이크로소프트', '아마존',
                    '구글 A', '구글 C', '메타', '테슬라',
                    '엔비디아', '코스트코', '넷플릭스', '페이팔',
                    '인텔', '시스코', '컴캐스트', '펩시코',
                    '암젠', '허니웰 인터내셔널', '스타벅스', '몬델리즈',
                    '마이크론', '브로드컴', '어도비', '텍사스 인스트루먼트',
                    'AMD', '어플라이드 머티리얼즈'
                ]:
                    if column in row:
                        # NaN, inf 값 처리
                        value = row[column]
                        if pd.isna(value) or pd.isinf(value):
                            record[column] = None
                        else:
                            record[column] = float(value)
                    else:
                        record[column] = None
                
                records.append(record)
            
            # Upsert 연산 (기존 날짜가 있으면 업데이트, 없으면 삽입)
            if records:
                response = supabase.table("economic_and_stock_data").upsert(records).execute()
                updated_records += len(records)
        
        print(f"데이터 업데이트 완료: 총 {total_records}개 중 {updated_records}개 업데이트됨")
        
    except Exception as e:
        print(f"백그라운드 데이터 업데이트 중 오류 발생: {str(e)}")
        raise

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 