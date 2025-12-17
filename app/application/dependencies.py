"""Dependency Injection 설정"""
from typing import Optional
from app.domain.repositories.stock_repository import (
    IStockRepository,
    IEconomicDataRepository,
    IStockRecommendationRepository
)
from app.infrastructure.repositories.mongodb_stock_repository import MongoDBStockRepository
from app.infrastructure.repositories.mongodb_economic_repository import MongodbEconomicRepository


def get_stock_repository() -> IStockRepository:
    """
    Stock Repository를 반환합니다.
    MongoDB를 사용합니다.
    """
    return MongoDBStockRepository()


def get_economic_repository() -> IEconomicDataRepository:
    """
    Economic Data Repository를 반환합니다.
    MongoDB를 사용합니다.
    """
    return MongodbEconomicRepository()


def get_recommendation_repository() -> Optional[IStockRecommendationRepository]:
    """Stock Recommendation Repository를 반환합니다."""
    # TODO: 추천 Repository 구현 추가
    return None
