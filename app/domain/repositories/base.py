"""Repository 기본 인터페이스"""
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, List, Optional
from datetime import datetime

T = TypeVar('T')


class BaseRepository(ABC, Generic[T]):
    """Repository 기본 인터페이스"""
    
    @abstractmethod
    async def get_by_id(self, id: str) -> Optional[T]:
        """ID로 엔티티 조회"""
        pass
    
    @abstractmethod
    async def get_all(self) -> List[T]:
        """모든 엔티티 조회"""
        pass
    
    @abstractmethod
    async def create(self, entity: T) -> T:
        """엔티티 생성"""
        pass
    
    @abstractmethod
    async def update(self, entity: T) -> T:
        """엔티티 업데이트"""
        pass
    
    @abstractmethod
    async def delete(self, id: str) -> bool:
        """엔티티 삭제"""
        pass
