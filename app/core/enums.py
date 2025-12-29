"""
공통 Enum 및 상수 정의 모듈

애플리케이션 전반에서 사용되는 상수 및 상태값을 Enum으로 관리합니다.
"""
from enum import Enum, IntEnum
from typing import Dict


class OrderStatus(str, Enum):
    """주문 상태"""
    ACCEPTED = "accepted"  # 주문 접수
    EXECUTED = "executed"  # 체결 완료
    PENDING = "pending"  # 대기 중
    FAILED = "failed"  # 실패
    RETRY = "retry"  # 재시도
    SUCCESS = "success"  # 성공 (레거시 호환용, EXECUTED와 동일 의미)


class OrderType(str, Enum):
    """주문 타입"""
    LIMIT = "00"  # 지정가
    MARKET = "02"  # 시장가


class SellPriority(IntEnum):
    """매도 우선순위"""
    STOP_LOSS = 1  # 손절
    TRAILING_STOP = 2  # 트레일링 스톱
    TAKE_PROFIT = 3  # 익절
    TECHNICAL = 4  # 기술적 매도


class ExchangeCode(str, Enum):
    """거래소 코드"""
    NASD = "NASD"  # 나스닥
    NYSE = "NYSE"  # 뉴욕증권거래소
    AMEX = "AMEX"  # 아멕스
    NAS = "NAS"  # API용 변환 코드 (나스닥)
    NYS = "NYS"  # API용 변환 코드 (뉴욕증권거래소)
    AMS = "AMS"  # API용 변환 코드 (아멕스)


# 거래소 코드 매핑 (API 요청에 맞게 변환)
EXCHANGE_CODE_MAP: Dict[ExchangeCode, ExchangeCode] = {
    ExchangeCode.NASD: ExchangeCode.NAS,
    ExchangeCode.NYSE: ExchangeCode.NYS,
    ExchangeCode.AMEX: ExchangeCode.AMS
}


def get_exchange_code_for_api(exchange_code: str) -> str:
    """
    거래소 코드를 API 요청용 코드로 변환
    
    Args:
        exchange_code: 원본 거래소 코드 (NASD, NYSE, AMEX 등)
        
    Returns:
        API 요청용 거래소 코드 (NAS, NYS, AMS 등)
    """
    try:
        exchange_enum = ExchangeCode(exchange_code)
        return EXCHANGE_CODE_MAP.get(exchange_enum, exchange_code).value
    except ValueError:
        # Enum에 없는 코드는 그대로 반환
        return exchange_code

