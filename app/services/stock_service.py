"""
MongoDB stocks 컬렉션 조회 공용 유틸리티 서비스
모든 주식 관련 조회 로직을 통합하여 재사용 가능하도록 제공
"""
from typing import Optional, List, Dict
from app.db.mongodb import get_db
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


def get_ticker_from_stock_name(stock_name: str) -> Optional[str]:
    """
    MongoDB stocks 컬렉션에서 주식명으로 ticker를 조회합니다.
    
    Args:
        stock_name: 주식명
    
    Returns:
        ticker 또는 None
    """
    try:
        db = get_db()
        if db is None:
            return None
        
        stock = db.stocks.find_one({"stock_name": stock_name, "is_active": True})
        if stock:
            return stock.get("ticker")
        return None
    except Exception as e:
        logger.error(f"주식명으로 ticker 조회 중 오류 발생: {str(e)}")
        return None


def get_stock_name_from_ticker(ticker: str) -> Optional[str]:
    """
    MongoDB stocks 컬렉션에서 ticker로 주식명을 조회합니다.
    
    Args:
        ticker: 티커 심볼
    
    Returns:
        stock_name 또는 None
    """
    try:
        db = get_db()
        if db is None:
            return None
        
        stock = db.stocks.find_one({"ticker": ticker, "is_active": True})
        if stock:
            return stock.get("stock_name")
        return None
    except Exception as e:
        logger.error(f"ticker로 주식명 조회 중 오류 발생: {str(e)}")
        return None


def get_active_stocks(exclude_etf: bool = False) -> List[Dict]:
    """
    MongoDB stocks 컬렉션에서 활성화된 주식 목록을 조회합니다.
    
    Args:
        exclude_etf: True이면 ETF 제외 (기본값: False)
    
    Returns:
        활성화된 주식 목록 (딕셔너리 리스트)
    """
    try:
        db = get_db()
        if db is None:
            return []
        
        query = {"is_active": True}
        if exclude_etf:
            query["is_etf"] = {"$ne": True}
        
        stocks = list(db.stocks.find(query))
        return stocks
    except Exception as e:
        logger.error(f"활성화된 주식 목록 조회 중 오류 발생: {str(e)}")
        return []


def get_active_stock_names(exclude_etf: bool = False) -> List[str]:
    """
    MongoDB stocks 컬렉션에서 활성화된 주식명 목록을 조회합니다.
    
    Args:
        exclude_etf: True이면 ETF 제외 (기본값: False)
    
    Returns:
        활성화된 주식명 목록
    """
    stocks = get_active_stocks(exclude_etf=exclude_etf)
    return [stock.get("stock_name") for stock in stocks if stock.get("stock_name")]


def get_active_tickers(exclude_etf: bool = False) -> List[str]:
    """
    MongoDB stocks 컬렉션에서 활성화된 ticker 목록을 조회합니다.
    
    Args:
        exclude_etf: True이면 ETF 제외 (기본값: False)
    
    Returns:
        활성화된 ticker 목록
    """
    stocks = get_active_stocks(exclude_etf=exclude_etf)
    return [stock.get("ticker") for stock in stocks if stock.get("ticker")]


def get_ticker_to_stock_mapping(exclude_etf: bool = False) -> Dict[str, str]:
    """
    MongoDB stocks 컬렉션에서 ticker -> stock_name 매핑을 생성합니다.
    
    Args:
        exclude_etf: True이면 ETF 제외 (기본값: False)
    
    Returns:
        {ticker: stock_name} 형태의 딕셔너리
    """
    try:
        db = get_db()
        if db is None:
            return {}
        
        query = {"is_active": True}
        if exclude_etf:
            query["is_etf"] = {"$ne": True}
        
        stocks = db.stocks.find(query)
        mapping = {}
        for stock in stocks:
            ticker = stock.get("ticker")
            stock_name = stock.get("stock_name")
            if ticker and stock_name:
                mapping[ticker] = stock_name
        
        return mapping
    except Exception as e:
        logger.error(f"ticker_to_stock 매핑 생성 중 오류 발생: {str(e)}")
        return {}


def get_stock_to_ticker_mapping(exclude_etf: bool = False) -> Dict[str, str]:
    """
    MongoDB stocks 컬렉션에서 stock_name -> ticker 매핑을 생성합니다.
    
    Args:
        exclude_etf: True이면 ETF 제외 (기본값: False)
    
    Returns:
        {stock_name: ticker} 형태의 딕셔너리
    """
    try:
        db = get_db()
        if db is None:
            return {}
        
        query = {"is_active": True}
        if exclude_etf:
            query["is_etf"] = {"$ne": True}
        
        stocks = db.stocks.find(query)
        mapping = {}
        for stock in stocks:
            ticker = stock.get("ticker")
            stock_name = stock.get("stock_name")
            if ticker and stock_name:
                mapping[stock_name] = ticker
        
        return mapping
    except Exception as e:
        logger.error(f"stock_to_ticker 매핑 생성 중 오류 발생: {str(e)}")
        return {}


def is_ticker_active(ticker: str) -> bool:
    """
    특정 ticker가 활성화되어 있는지 확인합니다.
    
    Args:
        ticker: 티커 심볼
    
    Returns:
        활성화 여부
    """
    try:
        db = get_db()
        if db is None:
            return False
        
        stock = db.stocks.find_one({"ticker": ticker, "is_active": True})
        return stock is not None
    except Exception as e:
        logger.error(f"ticker 활성화 여부 확인 중 오류 발생: {str(e)}")
        return False


def is_stock_name_active(stock_name: str) -> bool:
    """
    특정 주식명이 활성화되어 있는지 확인합니다.
    
    Args:
        stock_name: 주식명
    
    Returns:
        활성화 여부
    """
    try:
        db = get_db()
        if db is None:
            return False
        
        stock = db.stocks.find_one({"stock_name": stock_name, "is_active": True})
        return stock is not None
    except Exception as e:
        logger.error(f"주식명 활성화 여부 확인 중 오류 발생: {str(e)}")
        return False

