#!/usr/bin/env python3
"""
trading_config 마이그레이션 및 기능 테스트 스크립트
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from app.services.auto_trading_service import AutoTradingService
    from app.infrastructure.database.mongodb_client import get_mongodb_database
    from app.utils.user_context import get_current_user_id
except ImportError as e:
    print(f"❌ 모듈 import 실패: {e}")
    sys.exit(1)


def test_get_config(user_id: str = "lian"):
    """설정 조회 테스트"""
    print("=" * 80)
    print("테스트 1: 자동매매 설정 조회")
    print("=" * 80)
    print()
    
    try:
        service = AutoTradingService()
        config = service.get_auto_trading_config(user_id=user_id)
        
        print(f"✅ 설정 조회 성공 (user_id: {user_id})")
        print()
        print("📋 설정 내용:")
        for key, value in config.items():
            if key != "_id":  # _id는 출력에서 제외
                print(f"   - {key}: {value}")
        print()
        
        # 필수 필드 확인
        required_fields = [
            "enabled", "min_composite_score", "max_stocks_to_buy",
            "max_amount_per_stock", "stop_loss_percent", "take_profit_percent"
        ]
        
        missing_fields = [field for field in required_fields if field not in config]
        if missing_fields:
            print(f"⚠️  누락된 필수 필드: {missing_fields}")
            return False
        else:
            print("✅ 모든 필수 필드가 존재합니다.")
            print()
            return True
            
    except Exception as e:
        print(f"❌ 설정 조회 실패: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_update_config(user_id: str = "lian"):
    """설정 업데이트 테스트"""
    print("=" * 80)
    print("테스트 2: 자동매매 설정 업데이트")
    print("=" * 80)
    print()
    
    try:
        service = AutoTradingService()
        
        # 현재 설정 조회
        current_config = service.get_auto_trading_config(user_id=user_id)
        original_enabled = current_config.get("enabled", False)
        original_max_stocks = current_config.get("max_stocks_to_buy", 5)
        
        print(f"📋 현재 설정:")
        print(f"   - enabled: {original_enabled}")
        print(f"   - max_stocks_to_buy: {original_max_stocks}")
        print()
        
        # 테스트 업데이트 (반대 값으로 변경)
        test_update = {
            "enabled": not original_enabled,
            "max_stocks_to_buy": original_max_stocks + 1
        }
        
        print(f"🔄 업데이트할 설정:")
        print(f"   - enabled: {test_update['enabled']}")
        print(f"   - max_stocks_to_buy: {test_update['max_stocks_to_buy']}")
        print()
        
        # 업데이트 실행
        result = service.update_auto_trading_config(test_update, user_id=user_id)
        
        if not result.get("success"):
            print(f"❌ 설정 업데이트 실패: {result.get('error')}")
            return False
        
        print("✅ 설정 업데이트 성공")
        print()
        
        # 업데이트 확인
        updated_config = service.get_auto_trading_config(user_id=user_id)
        
        if updated_config.get("enabled") != test_update["enabled"]:
            print(f"❌ enabled 업데이트 확인 실패: {updated_config.get('enabled')} != {test_update['enabled']}")
            return False
        
        if updated_config.get("max_stocks_to_buy") != test_update["max_stocks_to_buy"]:
            print(f"❌ max_stocks_to_buy 업데이트 확인 실패: {updated_config.get('max_stocks_to_buy')} != {test_update['max_stocks_to_buy']}")
            return False
        
        print("✅ 업데이트 내용 확인 완료")
        print()
        
        # 원래 값으로 복구
        restore_update = {
            "enabled": original_enabled,
            "max_stocks_to_buy": original_max_stocks
        }
        service.update_auto_trading_config(restore_update, user_id=user_id)
        print("✅ 원래 설정으로 복구 완료")
        print()
        
        return True
        
    except Exception as e:
        print(f"❌ 설정 업데이트 실패: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_mongodb_structure(user_id: str = "lian"):
    """MongoDB 구조 검증"""
    print("=" * 80)
    print("테스트 3: MongoDB 구조 검증")
    print("=" * 80)
    print()
    
    try:
        db = get_mongodb_database()
        if db is None:
            print("❌ MongoDB 연결 실패")
            return False
        
        # users 컬렉션에서 사용자 조회
        user = db.users.find_one({"user_id": user_id})
        
        if not user:
            print(f"❌ 사용자 '{user_id}'를 찾을 수 없습니다.")
            return False
        
        print(f"✅ 사용자 '{user_id}' 조회 성공")
        print()
        
        # trading_config 필드 확인
        if "trading_config" not in user:
            print("❌ trading_config 필드가 없습니다.")
            return False
        
        trading_config = user.get("trading_config")
        
        if trading_config is None:
            print("⚠️  trading_config 필드는 존재하지만 값이 None입니다.")
            return False
        
        print("✅ trading_config 필드 확인 완료")
        print()
        print("📋 trading_config 구조:")
        print(f"   타입: {type(trading_config)}")
        if isinstance(trading_config, dict):
            print(f"   필드 수: {len(trading_config)}")
            print(f"   필드 목록: {list(trading_config.keys())}")
        print()
        
        return True
        
    except Exception as e:
        print(f"❌ MongoDB 구조 검증 실패: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_default_config_creation(user_id: str = "test_user_migration"):
    """기본 설정 생성 테스트"""
    print("=" * 80)
    print("테스트 4: 기본 설정 생성 (없는 사용자)")
    print("=" * 80)
    print()
    
    try:
        service = AutoTradingService()
        
        # 임시 사용자 생성 (테스트용)
        db = get_mongodb_database()
        if db is None:
            print("❌ MongoDB 연결 실패")
            return False
        
        # 임시 사용자 생성
        test_user = {
            "user_id": user_id,
            "email": None,
            "display_name": None,
            "preferences": {
                "default_currency": "USD",
                "notification_enabled": True
            },
            "stocks": [],
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        
        # 기존 사용자 삭제 (있는 경우)
        db.users.delete_one({"user_id": user_id})
        
        # 새 사용자 생성
        db.users.insert_one(test_user)
        print(f"✅ 테스트 사용자 '{user_id}' 생성 완료")
        print()
        
        # 설정 조회 (기본값 생성)
        config = service.get_auto_trading_config(user_id=user_id)
        
        if not config:
            print("❌ 기본 설정 생성 실패")
            return False
        
        print("✅ 기본 설정 생성 성공")
        print()
        
        # MongoDB에서 직접 확인
        user = db.users.find_one({"user_id": user_id})
        if not user.get("trading_config"):
            print("❌ users 컬렉션에 trading_config가 저장되지 않았습니다.")
            return False
        
        print("✅ MongoDB에 trading_config 저장 확인 완료")
        print()
        
        # 정리: 테스트 사용자 삭제
        db.users.delete_one({"user_id": user_id})
        print(f"✅ 테스트 사용자 '{user_id}' 삭제 완료")
        print()
        
        return True
        
    except Exception as e:
        print(f"❌ 기본 설정 생성 테스트 실패: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """메인 테스트 실행"""
    print()
    print("=" * 80)
    print("🚀 trading_config 마이그레이션 및 기능 테스트")
    print("=" * 80)
    print()
    
    user_id = "lian"  # 기본 테스트 사용자
    
    try:
        current_user_id = get_current_user_id()
        if current_user_id:
            user_id = current_user_id
            print(f"📌 현재 사용자 ID: {user_id}")
            print()
    except:
        print(f"📌 기본 사용자 ID 사용: {user_id}")
        print()
    
    test_results = []
    
    # 테스트 실행
    test_results.append(("MongoDB 구조 검증", test_mongodb_structure(user_id)))
    test_results.append(("설정 조회", test_get_config(user_id)))
    test_results.append(("설정 업데이트", test_update_config(user_id)))
    test_results.append(("기본 설정 생성", test_default_config_creation()))
    
    # 결과 요약
    print()
    print("=" * 80)
    print("📊 테스트 결과 요약")
    print("=" * 80)
    print()
    
    passed = sum(1 for _, result in test_results if result)
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ 통과" if result else "❌ 실패"
        print(f"   {status}: {test_name}")
    
    print()
    print(f"결과: {passed}/{total} 테스트 통과")
    print()
    
    if passed == total:
        print("✅ 모든 테스트가 성공적으로 완료되었습니다!")
        return 0
    else:
        print(f"❌ {total - passed}개의 테스트가 실패했습니다.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
