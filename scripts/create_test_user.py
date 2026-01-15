"""
테스트용 사용자 생성 스크립트

lian 사용자와 동일한 정보로 새 사용자를 생성합니다.
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from datetime import datetime
from app.db.mongodb import get_db
from app.services.auto_trading_service import AutoTradingService
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_test_user(source_user_id: str = "lian", new_user_id: str = "test_user_001"):
    """
    source_user_id와 동일한 정보로 새 사용자 생성
    
    Args:
        source_user_id: 복사할 원본 사용자 ID
        new_user_id: 생성할 새 사용자 ID
    """
    db = get_db()
    if db is None:
        logger.error("MongoDB 연결 실패")
        return False
    
    # 원본 사용자 조회
    source_user = db.users.find_one({"user_id": source_user_id})
    if not source_user:
        logger.error(f"원본 사용자 '{source_user_id}'를 찾을 수 없습니다.")
        return False
    
    logger.info(f"원본 사용자 '{source_user_id}' 정보 조회 완료")
    
    # 새 사용자가 이미 존재하는지 확인
    existing = db.users.find_one({"user_id": new_user_id})
    if existing:
        logger.warning(f"사용자 '{new_user_id}'가 이미 존재합니다. 삭제 후 재생성합니다.")
        db.users.delete_one({"user_id": new_user_id})
    
    # 새 사용자 문서 생성 (원본 복사)
    new_user = {
        "user_id": new_user_id,
        "email": f"{new_user_id}@test.com",
        "display_name": new_user_id,
        "preferences": source_user.get("preferences", {
            "default_currency": "USD",
            "notification_enabled": True
        }),
        "stocks": source_user.get("stocks", []).copy() if source_user.get("stocks") else [],
        "trading_config": source_user.get("trading_config", {}).copy() if source_user.get("trading_config") else None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    # trading_config가 없으면 기본 설정 생성
    if not new_user.get("trading_config"):
        logger.info(f"사용자 '{new_user_id}'의 기본 trading_config 생성 중...")
        auto_trading_service = AutoTradingService()
        default_config = auto_trading_service._create_default_config(user_id=new_user_id)
        new_user["trading_config"] = default_config
    
    # trading_config에 user_id가 없으면 추가
    if new_user.get("trading_config") and "user_id" not in new_user["trading_config"]:
        new_user["trading_config"]["user_id"] = new_user_id
    
    # 자동매매 활성화 (테스트용)
    if new_user.get("trading_config"):
        new_user["trading_config"]["auto_trading_enabled"] = True
    
    # 사용자 생성
    result = db.users.insert_one(new_user)
    logger.info(f"✅ 새 사용자 '{new_user_id}' 생성 완료 (ID: {result.inserted_id})")
    
    # 생성된 사용자 정보 출력
    created_user = db.users.find_one({"user_id": new_user_id})
    logger.info(f"\n생성된 사용자 정보:")
    logger.info(f"  - user_id: {created_user.get('user_id')}")
    logger.info(f"  - email: {created_user.get('email')}")
    logger.info(f"  - display_name: {created_user.get('display_name')}")
    logger.info(f"  - stocks 개수: {len(created_user.get('stocks', []))}")
    logger.info(f"  - trading_config: {created_user.get('trading_config') is not None}")
    if created_user.get('trading_config'):
        logger.info(f"  - auto_trading_enabled: {created_user.get('trading_config', {}).get('auto_trading_enabled', False)}")
    
    return True


if __name__ == "__main__":
    import random
    import string
    
    # 랜덤 user_id 생성 (test_user_ + 3자리 숫자)
    random_suffix = ''.join(random.choices(string.digits, k=3))
    new_user_id = f"test_user_{random_suffix}"
    
    logger.info("=" * 60)
    logger.info("테스트용 사용자 생성 시작")
    logger.info("=" * 60)
    logger.info(f"원본 사용자: lian")
    logger.info(f"새 사용자 ID: {new_user_id}")
    logger.info("")
    
    success = create_test_user(source_user_id="lian", new_user_id=new_user_id)
    
    if success:
        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ 테스트용 사용자 생성 완료!")
        logger.info("=" * 60)
        logger.info(f"생성된 사용자 ID: {new_user_id}")
        logger.info("")
        logger.info("다음 단계:")
        logger.info("1. 스케줄러 멀티 유저 개선 작업 진행")
        logger.info("2. 멀티 유저 스케줄러 테스트 실행")
    else:
        logger.error("❌ 테스트용 사용자 생성 실패")
        sys.exit(1)
