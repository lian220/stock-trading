from fastapi import APIRouter, HTTPException
from typing import List, Optional
from datetime import datetime
from pymongo.errors import DuplicateKeyError
from app.db.mongodb import get_db
from app.models.mongodb_models import UserPreferences
from app.schemas.user import UserCreate, UserUpdate, UserStockAdd, UserStockUpdate
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def enrich_user_stocks_with_stock_info(db, user_stocks: List[dict]) -> List[dict]:
    """
    사용자의 stocks 배열을 stocks 컬렉션 정보와 조인하여 반환합니다.
    
    Args:
        db: MongoDB 데이터베이스 객체
        user_stocks: users.stocks 배열
    
    Returns:
        stocks 컬렉션 정보가 추가된 stocks 배열
    """
    if not user_stocks:
        return []
    
    # ticker 목록 추출
    tickers = [stock.get("ticker") for stock in user_stocks if stock.get("ticker")]
    if not tickers:
        return user_stocks
    
    # stocks 컬렉션에서 종목 정보 조회
    stock_info_map = {}
    for stock_doc in db.stocks.find({"ticker": {"$in": tickers}}):
        ticker = stock_doc.get("ticker")
        stock_info_map[ticker] = {
            "stock_name": stock_doc.get("stock_name"),
            "stock_name_en": stock_doc.get("stock_name_en"),
            "is_etf": stock_doc.get("is_etf", False),
            "leverage_ticker": stock_doc.get("leverage_ticker"),
            "exchange": stock_doc.get("exchange"),
            "sector": stock_doc.get("sector"),
            "industry": stock_doc.get("industry"),
        }
    
    # 사용자 stocks에 stocks 컬렉션 정보 추가
    enriched_stocks = []
    for user_stock in user_stocks:
        ticker = user_stock.get("ticker")
        enriched_stock = user_stock.copy()  # 사용자별 정보 복사
        
        # stocks 컬렉션 정보 추가
        if ticker in stock_info_map:
            enriched_stock.update(stock_info_map[ticker])
        
        enriched_stocks.append(enriched_stock)
    
    return enriched_stocks


@router.get("", summary="사용자 목록 조회", response_model=List[dict])
async def get_users(
    user_id: Optional[str] = None,
    email: Optional[str] = None
):
    """
    MongoDB의 users 컬렉션에서 사용자 목록을 조회합니다.
    
    - **user_id**: 특정 user_id로 검색 (선택, 부분 일치)
    - **email**: 특정 이메일로 검색 (선택, 부분 일치)
    
    모든 파라미터는 선택사항이며, 제공되지 않으면 모든 사용자를 반환합니다.
    """
    try:
        db = get_db()
        if db is None:
            raise HTTPException(status_code=500, detail="MongoDB 연결에 실패했습니다.")
        
        # 쿼리 조건 구성
        query = {}
        if user_id:
            query["user_id"] = {"$regex": user_id, "$options": "i"}
        if email:
            query["email"] = {"$regex": email, "$options": "i"}
        
        # 사용자 조회
        users = list(db.users.find(query).sort("user_id", 1))
        
        # ObjectId를 문자열로 변환하고 stocks 정보 조인
        for user in users:
            user["_id"] = str(user["_id"])
            # stocks 컬렉션 정보와 조인
            if "stocks" in user and user["stocks"]:
                user["stocks"] = enrich_user_stocks_with_stock_info(db, user["stocks"])
        
        return users
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"사용자 목록 조회 중 오류 발생: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"사용자 목록 조회 중 오류 발생: {str(e)}")


@router.get("/{user_id}", summary="특정 사용자 정보 조회", response_model=dict)
async def get_user(user_id: str):
    """
    MongoDB에서 특정 user_id의 사용자 정보를 조회합니다.
    """
    try:
        db = get_db()
        if db is None:
            raise HTTPException(status_code=500, detail="MongoDB 연결에 실패했습니다.")
        
        user_doc = db.users.find_one({"user_id": user_id})
        if not user_doc:
            raise HTTPException(status_code=404, detail=f"user_id '{user_id}' 사용자 정보를 찾을 수 없습니다.")
        
        # ObjectId를 문자열로 변환하고 stocks 정보 조인
        user_doc["_id"] = str(user_doc["_id"])
        # stocks 컬렉션 정보와 조인
        if "stocks" in user_doc and user_doc["stocks"]:
            user_doc["stocks"] = enrich_user_stocks_with_stock_info(db, user_doc["stocks"])
        
        return user_doc
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"사용자 정보 조회 중 오류 발생: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"사용자 정보 조회 중 오류 발생: {str(e)}")


@router.post("", summary="사용자 추가", response_model=dict)
async def create_user(user: UserCreate):
    """
    MongoDB의 users 컬렉션에 새로운 사용자를 추가합니다.
    
    - **user_id**: 사용자 ID (필수, 중복 불가)
    - **email**: 이메일 (선택)
    - **display_name**: 표시명 (선택)
    - **preferences**: 사용자 선호 설정 (선택)
    
    동일한 user_id가 이미 존재하는 경우 오류를 반환합니다.
    """
    try:
        db = get_db()
        if db is None:
            raise HTTPException(status_code=500, detail="MongoDB 연결에 실패했습니다.")
        
        # user_id로 기존 사용자 확인
        existing = db.users.find_one({"user_id": user.user_id})
        if existing:
            raise HTTPException(status_code=409, detail=f"user_id '{user.user_id}'가 이미 존재합니다.")
        
        now = datetime.utcnow()
        
        # 새 사용자 추가
        user_doc = {
            "user_id": user.user_id,
            "email": user.email,
            "display_name": user.display_name,
            "preferences": user.preferences.dict() if user.preferences else UserPreferences().dict(),
            "stocks": [],
            "created_at": now,
            "updated_at": now
        }
        
        # None 값 제거
        user_doc = {k: v for k, v in user_doc.items() if v is not None}
        
        result = db.users.insert_one(user_doc)
        
        logger.info(f"사용자 추가 성공: {user.user_id}")
        return {
            "success": True,
            "message": f"사용자가 추가되었습니다: {user.user_id}",
            "user_id": user.user_id,
            "id": str(result.inserted_id),
            "action": "created"
        }
            
    except HTTPException as he:
        raise he
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail=f"user_id '{user.user_id}'가 이미 존재합니다.")
    except Exception as e:
        logger.error(f"사용자 추가 중 오류 발생: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"사용자 추가 중 오류 발생: {str(e)}")


@router.put("/{user_id}", summary="사용자 정보 수정", response_model=dict)
async def update_user(user_id: str, user_update: UserUpdate):
    """
    MongoDB의 users 컬렉션에서 사용자 정보를 수정합니다.
    
    - **email**: 이메일 (선택)
    - **display_name**: 표시명 (선택)
    - **preferences**: 사용자 선호 설정 (선택)
    
    제공된 필드만 업데이트됩니다.
    """
    try:
        db = get_db()
        if db is None:
            raise HTTPException(status_code=500, detail="MongoDB 연결에 실패했습니다.")
        
        # 사용자 존재 확인
        existing = db.users.find_one({"user_id": user_id})
        if not existing:
            raise HTTPException(status_code=404, detail=f"user_id '{user_id}' 사용자 정보를 찾을 수 없습니다.")
        
        now = datetime.utcnow()
        
        # 업데이트할 데이터 구성
        update_data = {
            "updated_at": now
        }
        
        if user_update.email is not None:
            update_data["email"] = user_update.email
        if user_update.display_name is not None:
            update_data["display_name"] = user_update.display_name
        if user_update.preferences is not None:
            update_data["preferences"] = user_update.preferences.dict()
        
        result = db.users.update_one(
            {"user_id": user_id},
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            logger.info(f"사용자 업데이트 성공: {user_id}")
            return {
                "success": True,
                "message": f"사용자 정보가 업데이트되었습니다: {user_id}",
                "user_id": user_id,
                "action": "updated"
            }
        else:
            return {
                "success": True,
                "message": f"사용자 정보에 변경사항이 없습니다: {user_id}",
                "user_id": user_id,
                "action": "no_change"
            }
            
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"사용자 수정 중 오류 발생: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"사용자 수정 중 오류 발생: {str(e)}")


@router.delete("/{user_id}", summary="사용자 삭제", response_model=dict)
async def delete_user(user_id: str):
    """
    MongoDB의 users 컬렉션에서 사용자를 삭제합니다.
    
    실제로 문서를 삭제합니다 (하드 삭제).
    """
    try:
        db = get_db()
        if db is None:
            raise HTTPException(status_code=500, detail="MongoDB 연결에 실패했습니다.")
        
        # 사용자 존재 확인
        user_doc = db.users.find_one({"user_id": user_id})
        if not user_doc:
            raise HTTPException(status_code=404, detail=f"user_id '{user_id}' 사용자 정보를 찾을 수 없습니다.")
        
        # 사용자 삭제
        result = db.users.delete_one({"user_id": user_id})
        
        if result.deleted_count > 0:
            logger.info(f"사용자 삭제 성공: {user_id}")
            return {
                "success": True,
                "message": f"사용자가 삭제되었습니다: {user_id}",
                "user_id": user_id,
                "action": "deleted"
            }
        else:
            raise HTTPException(status_code=404, detail=f"user_id '{user_id}' 사용자 정보를 찾을 수 없습니다.")
            
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"사용자 삭제 중 오류 발생: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"사용자 삭제 중 오류 발생: {str(e)}")


@router.post("/{user_id}/stocks", summary="사용자 주식 종목 추가", response_model=dict)
async def add_user_stock(user_id: str, stock: UserStockAdd):
    """
    사용자의 관심 종목 목록에 주식 종목을 추가합니다.
    
    - **ticker**: 종목 티커 (필수)
    - **use_leverage**: 레버리지 사용 여부 (기본값: False)
    - **notes**: 사용자 메모 (선택)
    - **tags**: 사용자 정의 태그 (선택)
    - **is_active**: 활성화 여부 (기본값: True)
    
    동일한 ticker가 이미 존재하는 경우 오류를 반환합니다.
    """
    try:
        db = get_db()
        if db is None:
            raise HTTPException(status_code=500, detail="MongoDB 연결에 실패했습니다.")
        
        # 사용자 존재 확인
        user_doc = db.users.find_one({"user_id": user_id})
        if not user_doc:
            raise HTTPException(status_code=404, detail=f"user_id '{user_id}' 사용자 정보를 찾을 수 없습니다.")
        
        # stocks 컬렉션에서 종목 존재 확인
        stock_doc = db.stocks.find_one({"ticker": stock.ticker.upper()})
        if not stock_doc:
            raise HTTPException(status_code=404, detail=f"종목 '{stock.ticker}'가 stocks 컬렉션에 존재하지 않습니다. 먼저 종목을 추가해주세요.")
        
        # 이미 추가된 종목인지 확인
        existing_stocks = user_doc.get("stocks", [])
        for existing_stock in existing_stocks:
            if existing_stock.get("ticker", "").upper() == stock.ticker.upper():
                raise HTTPException(status_code=409, detail=f"종목 '{stock.ticker}'가 이미 관심 종목 목록에 있습니다.")
        
        now = datetime.utcnow()
        
        # 새 종목 추가
        new_stock = {
            "ticker": stock.ticker.upper(),
            "use_leverage": stock.use_leverage,
            "notes": stock.notes,
            "tags": stock.tags if stock.tags else [],
            "is_active": stock.is_active,
            "added_at": now
        }
        
        # None 값 제거
        new_stock = {k: v for k, v in new_stock.items() if v is not None}
        
        # stocks 배열에 추가
        result = db.users.update_one(
            {"user_id": user_id},
            {
                "$push": {"stocks": new_stock},
                "$set": {"updated_at": now}
            }
        )
        
        if result.modified_count > 0:
            logger.info(f"사용자 '{user_id}'의 종목 '{stock.ticker}' 추가 성공")
            return {
                "success": True,
                "message": f"종목 '{stock.ticker}'가 관심 종목 목록에 추가되었습니다.",
                "user_id": user_id,
                "ticker": stock.ticker.upper(),
                "action": "added"
            }
        else:
            raise HTTPException(status_code=500, detail="종목 추가에 실패했습니다.")
            
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"사용자 종목 추가 중 오류 발생: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"사용자 종목 추가 중 오류 발생: {str(e)}")


@router.delete("/{user_id}/stocks/{ticker}", summary="사용자 주식 종목 삭제", response_model=dict)
async def remove_user_stock(user_id: str, ticker: str):
    """
    사용자의 관심 종목 목록에서 주식 종목을 삭제합니다.
    
    - **user_id**: 사용자 ID
    - **ticker**: 삭제할 종목 티커
    """
    try:
        db = get_db()
        if db is None:
            raise HTTPException(status_code=500, detail="MongoDB 연결에 실패했습니다.")
        
        # 사용자 존재 확인
        user_doc = db.users.find_one({"user_id": user_id})
        if not user_doc:
            raise HTTPException(status_code=404, detail=f"user_id '{user_id}' 사용자 정보를 찾을 수 없습니다.")
        
        # 종목이 존재하는지 확인
        existing_stocks = user_doc.get("stocks", [])
        ticker_upper = ticker.upper()
        stock_exists = any(
            existing_stock.get("ticker", "").upper() == ticker_upper 
            for existing_stock in existing_stocks
        )
        
        if not stock_exists:
            raise HTTPException(status_code=404, detail=f"종목 '{ticker}'가 관심 종목 목록에 없습니다.")
        
        now = datetime.utcnow()
        
        # stocks 배열에서 종목 제거
        result = db.users.update_one(
            {"user_id": user_id},
            {
                "$pull": {"stocks": {"ticker": {"$regex": f"^{ticker_upper}$", "$options": "i"}}},
                "$set": {"updated_at": now}
            }
        )
        
        if result.modified_count > 0:
            logger.info(f"사용자 '{user_id}'의 종목 '{ticker}' 삭제 성공")
            return {
                "success": True,
                "message": f"종목 '{ticker}'가 관심 종목 목록에서 삭제되었습니다.",
                "user_id": user_id,
                "ticker": ticker_upper,
                "action": "removed"
            }
        else:
            raise HTTPException(status_code=500, detail="종목 삭제에 실패했습니다.")
            
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"사용자 종목 삭제 중 오류 발생: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"사용자 종목 삭제 중 오류 발생: {str(e)}")


@router.put("/{user_id}/stocks/{ticker}", summary="사용자 주식 종목 수정", response_model=dict)
async def update_user_stock(user_id: str, ticker: str, stock_update: UserStockUpdate):
    """
    사용자의 관심 종목 정보를 수정합니다.
    
    - **user_id**: 사용자 ID
    - **ticker**: 수정할 종목 티커
    - **use_leverage**: 레버리지 사용 여부 (선택)
    - **notes**: 사용자 메모 (선택)
    - **tags**: 사용자 정의 태그 (선택)
    - **is_active**: 활성화 여부 (선택)
    
    제공된 필드만 업데이트됩니다.
    """
    try:
        db = get_db()
        if db is None:
            raise HTTPException(status_code=500, detail="MongoDB 연결에 실패했습니다.")
        
        # 사용자 존재 확인
        user_doc = db.users.find_one({"user_id": user_id})
        if not user_doc:
            raise HTTPException(status_code=404, detail=f"user_id '{user_id}' 사용자 정보를 찾을 수 없습니다.")
        
        # 종목이 존재하는지 확인
        existing_stocks = user_doc.get("stocks", [])
        ticker_upper = ticker.upper()
        stock_index = None
        for idx, existing_stock in enumerate(existing_stocks):
            if existing_stock.get("ticker", "").upper() == ticker_upper:
                stock_index = idx
                break
        
        if stock_index is None:
            raise HTTPException(status_code=404, detail=f"종목 '{ticker}'가 관심 종목 목록에 없습니다.")
        
        now = datetime.utcnow()
        
        # 업데이트할 필드 구성
        update_fields = {}
        if stock_update.use_leverage is not None:
            update_fields["stocks.$.use_leverage"] = stock_update.use_leverage
        if stock_update.notes is not None:
            update_fields["stocks.$.notes"] = stock_update.notes
        if stock_update.tags is not None:
            update_fields["stocks.$.tags"] = stock_update.tags
        if stock_update.is_active is not None:
            update_fields["stocks.$.is_active"] = stock_update.is_active
        
        if not update_fields:
            return {
                "success": True,
                "message": f"변경할 필드가 없습니다.",
                "user_id": user_id,
                "ticker": ticker_upper,
                "action": "no_change"
            }
        
        update_fields["updated_at"] = now
        
        # stocks 배열의 특정 요소 업데이트
        result = db.users.update_one(
            {"user_id": user_id, "stocks.ticker": {"$regex": f"^{ticker_upper}$", "$options": "i"}},
            {"$set": update_fields}
        )
        
        if result.modified_count > 0:
            logger.info(f"사용자 '{user_id}'의 종목 '{ticker}' 수정 성공")
            return {
                "success": True,
                "message": f"종목 '{ticker}' 정보가 수정되었습니다.",
                "user_id": user_id,
                "ticker": ticker_upper,
                "action": "updated"
            }
        else:
            return {
                "success": True,
                "message": f"종목 '{ticker}' 정보에 변경사항이 없습니다.",
                "user_id": user_id,
                "ticker": ticker_upper,
                "action": "no_change"
            }
            
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"사용자 종목 수정 중 오류 발생: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"사용자 종목 수정 중 오류 발생: {str(e)}")
