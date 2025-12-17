from fastapi import APIRouter, HTTPException
from typing import List, Optional
from datetime import datetime
from pymongo.errors import DuplicateKeyError
from app.db.mongodb import get_db
from app.models.mongodb_models import Stock
from app.schemas.stock import StockPrediction
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class StockUpdate(BaseModel):
    """종목 정보 업데이트 요청 스키마 (ticker 제외)"""
    stock_name: Optional[str] = None
    stock_name_en: Optional[str] = None
    is_etf: Optional[bool] = None
    leverage_ticker: Optional[str] = None
    exchange: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    is_active: Optional[bool] = None

@router.get("", summary="종목 목록 조회", response_model=List[dict])
async def get_stocks(
    is_active: Optional[bool] = None,
    is_etf: Optional[bool] = None,
    ticker: Optional[str] = None
):
    """
    MongoDB의 stocks 컬렉션에서 종목 목록을 조회합니다.
    
    - **is_active**: 활성화된 종목만 조회 (선택)
    - **is_etf**: ETF 여부로 필터링 (선택)
    - **ticker**: 특정 티커로 검색 (선택, 부분 일치)
    
    모든 파라미터는 선택사항이며, 제공되지 않으면 모든 종목을 반환합니다.
    """
    try:
        db = get_db()
        if db is None:
            raise HTTPException(status_code=500, detail="MongoDB 연결에 실패했습니다.")
        
        # 쿼리 조건 구성
        query = {}
        if is_active is not None:
            query["is_active"] = is_active
        if is_etf is not None:
            query["is_etf"] = is_etf
        if ticker:
            query["ticker"] = {"$regex": ticker.upper(), "$options": "i"}
        
        # 종목 조회
        stocks = list(db.stocks.find(query).sort("ticker", 1))
        
        # ObjectId를 문자열로 변환
        for stock in stocks:
            stock["_id"] = str(stock["_id"])
        
        return stocks
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"종목 목록 조회 중 오류 발생: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"종목 목록 조회 중 오류 발생: {str(e)}")


@router.get("/predictions", summary="주식 예측 결과 조회", response_model=List[StockPrediction])
def read_predictions():
    try:
        # CSV 파일에서 예측 결과를 읽어오는 예시
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

@router.post("", summary="종목 추가", response_model=dict)
async def create_stock(stock: Stock):
    """
    MongoDB의 stocks 컬렉션에 새로운 종목을 추가합니다.
    
    - **ticker**: 종목 티커 (필수, 중복 불가)
    - **stock_name**: 종목명 (필수)
    - **stock_name_en**: 영문 종목명 (선택)
    - **is_etf**: ETF 여부 (기본값: False)
    - **leverage_ticker**: 레버리지 티커 심볼 (선택)
    - **exchange**: 거래소 (선택)
    - **sector**: 섹터 (선택)
    - **industry**: 산업 (선택)
    - **is_active**: 활성화 여부 (기본값: True)
    
    동일한 ticker가 이미 존재하는 경우 업데이트됩니다.
    """
    try:
        db = get_db()
        if db is None:
            raise HTTPException(status_code=500, detail="MongoDB 연결에 실패했습니다.")
        
        # ticker로 기존 종목 확인
        existing = db.stocks.find_one({"ticker": stock.ticker})
        
        now = datetime.utcnow()
        
        if existing:
            # 기존 종목 업데이트
            update_data = {
                "stock_name": stock.stock_name,
                "updated_at": now
            }
            
            # 선택적 필드 추가
            if stock.stock_name_en is not None:
                update_data["stock_name_en"] = stock.stock_name_en
            if stock.is_etf is not None:
                update_data["is_etf"] = stock.is_etf
            if stock.leverage_ticker is not None:
                update_data["leverage_ticker"] = stock.leverage_ticker
            if stock.exchange is not None:
                update_data["exchange"] = stock.exchange
            if stock.sector is not None:
                update_data["sector"] = stock.sector
            if stock.industry is not None:
                update_data["industry"] = stock.industry
            if stock.is_active is not None:
                update_data["is_active"] = stock.is_active
            
            result = db.stocks.update_one(
                {"ticker": stock.ticker},
                {"$set": update_data}
            )
            
            if result.modified_count > 0:
                logger.info(f"종목 업데이트 성공: {stock.ticker} ({stock.stock_name})")
                return {
                    "success": True,
                    "message": f"종목이 업데이트되었습니다: {stock.ticker}",
                    "ticker": stock.ticker,
                    "stock_name": stock.stock_name,
                    "action": "updated"
                }
            else:
                return {
                    "success": True,
                    "message": f"종목이 이미 존재하며 변경사항이 없습니다: {stock.ticker}",
                    "ticker": stock.ticker,
                    "stock_name": stock.stock_name,
                    "action": "no_change"
                }
        else:
            # 새 종목 추가
            stock_doc = {
                "ticker": stock.ticker,
                "stock_name": stock.stock_name,
                "stock_name_en": stock.stock_name_en,
                "is_etf": stock.is_etf if stock.is_etf is not None else False,
                "leverage_ticker": stock.leverage_ticker,
                "exchange": stock.exchange,
                "sector": stock.sector,
                "industry": stock.industry,
                "is_active": stock.is_active if stock.is_active is not None else True,
                "created_at": now,
                "updated_at": now
            }
            
            # None 값 제거
            stock_doc = {k: v for k, v in stock_doc.items() if v is not None}
            
            result = db.stocks.insert_one(stock_doc)
            
            logger.info(f"종목 추가 성공: {stock.ticker} ({stock.stock_name})")
            return {
                "success": True,
                "message": f"종목이 추가되었습니다: {stock.ticker}",
                "ticker": stock.ticker,
                "stock_name": stock.stock_name,
                "id": str(result.inserted_id),
                "action": "created"
            }
            
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail=f"종목 티커가 이미 존재합니다: {stock.ticker}")
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"종목 추가 중 오류 발생: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"종목 추가 중 오류 발생: {str(e)}")


@router.get("/{ticker}", summary="특정 주식 정보 조회")
def read_stock_info(ticker: str):
    """
    MongoDB에서 특정 티커의 종목 정보를 조회합니다.
    """
    try:
        # MongoDB에서 특정 주식 정보를 조회
        db = get_db()
        if db is None:
            raise HTTPException(status_code=500, detail="MongoDB 연결에 실패했습니다.")
        
        stock_doc = db.stocks.find_one({"ticker": ticker.upper()})
        if not stock_doc:
            raise HTTPException(status_code=404, detail=f"{ticker} 주식 정보를 찾을 수 없습니다.")
        
        # ObjectId를 문자열로 변환
        stock_doc["_id"] = str(stock_doc["_id"])
        
        return stock_doc
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"주식 정보 조회 중 오류 발생: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"주식 정보 조회 중 오류 발생: {str(e)}")


@router.put("/{ticker}", summary="종목 정보 수정", response_model=dict)
async def update_stock(ticker: str, stock_update: StockUpdate):
    """
    MongoDB의 stocks 컬렉션에서 종목 정보를 수정합니다.
    
    - **stock_name**: 종목명 (선택)
    - **stock_name_en**: 영문 종목명 (선택)
    - **is_etf**: ETF 여부 (선택)
    - **leverage_ticker**: 레버리지 티커 심볼 (선택)
    - **exchange**: 거래소 (선택)
    - **sector**: 섹터 (선택)
    - **industry**: 산업 (선택)
    - **is_active**: 활성화 여부 (선택)
    
    ticker는 변경할 수 없습니다. 제공된 필드만 업데이트됩니다.
    """
    try:
        db = get_db()
        if db is None:
            raise HTTPException(status_code=500, detail="MongoDB 연결에 실패했습니다.")
        
        # 종목 존재 확인
        stock_doc = db.stocks.find_one({"ticker": ticker.upper()})
        if not stock_doc:
            raise HTTPException(status_code=404, detail=f"{ticker} 종목 정보를 찾을 수 없습니다.")
        
        now = datetime.utcnow()
        
        # 업데이트할 데이터 구성
        update_data = {
            "updated_at": now
        }
        
        # 제공된 필드만 업데이트
        if stock_update.stock_name is not None:
            update_data["stock_name"] = stock_update.stock_name
        if stock_update.stock_name_en is not None:
            update_data["stock_name_en"] = stock_update.stock_name_en
        if stock_update.is_etf is not None:
            update_data["is_etf"] = stock_update.is_etf
        if stock_update.leverage_ticker is not None:
            update_data["leverage_ticker"] = stock_update.leverage_ticker
        if stock_update.exchange is not None:
            update_data["exchange"] = stock_update.exchange
        if stock_update.sector is not None:
            update_data["sector"] = stock_update.sector
        if stock_update.industry is not None:
            update_data["industry"] = stock_update.industry
        if stock_update.is_active is not None:
            update_data["is_active"] = stock_update.is_active
        
        # leverage_ticker를 None으로 설정하려면 $unset 사용
        if stock_update.leverage_ticker is None and "leverage_ticker" in stock_doc:
            # leverage_ticker 제거
            result = db.stocks.update_one(
                {"ticker": ticker.upper()},
                {
                    "$unset": {"leverage_ticker": ""},
                    "$set": {k: v for k, v in update_data.items() if k != "leverage_ticker"}
                }
            )
        else:
            result = db.stocks.update_one(
                {"ticker": ticker.upper()},
                {"$set": update_data}
            )
        
        if result.modified_count > 0:
            logger.info(f"종목 수정 성공: {ticker}")
            return {
                "success": True,
                "message": f"종목 정보가 수정되었습니다: {ticker}",
                "ticker": ticker.upper(),
                "action": "updated"
            }
        else:
            return {
                "success": True,
                "message": f"종목 정보에 변경사항이 없습니다: {ticker}",
                "ticker": ticker.upper(),
                "action": "no_change"
            }
            
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"종목 수정 중 오류 발생: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"종목 수정 중 오류 발생: {str(e)}")


@router.delete("/{ticker}", summary="종목 삭제", response_model=dict)
async def delete_stock(ticker: str):
    """
    MongoDB의 stocks 컬렉션에서 종목을 삭제합니다.
    
    실제로는 삭제하지 않고 `is_active`를 `False`로 설정합니다 (소프트 삭제).
    """
    try:
        db = get_db()
        if db is None:
            raise HTTPException(status_code=500, detail="MongoDB 연결에 실패했습니다.")
        
        # 종목 존재 확인
        stock_doc = db.stocks.find_one({"ticker": ticker.upper()})
        if not stock_doc:
            raise HTTPException(status_code=404, detail=f"{ticker} 주식 정보를 찾을 수 없습니다.")
        
        # 소프트 삭제: is_active를 False로 설정
        result = db.stocks.update_one(
            {"ticker": ticker.upper()},
            {
                "$set": {
                    "is_active": False,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count > 0:
            logger.info(f"종목 비활성화 성공: {ticker}")
            return {
                "success": True,
                "message": f"종목이 비활성화되었습니다: {ticker}",
                "ticker": ticker.upper(),
                "action": "deactivated"
            }
        else:
            return {
                "success": True,
                "message": f"종목이 이미 비활성화되어 있습니다: {ticker}",
                "ticker": ticker.upper(),
                "action": "already_deactivated"
            }
            
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"종목 삭제 중 오류 발생: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"종목 삭제 중 오류 발생: {str(e)}")