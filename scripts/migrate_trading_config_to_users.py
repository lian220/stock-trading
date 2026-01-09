#!/usr/bin/env python3
"""
trading_configs 컬렉션 → users.trading_config 필드 마이그레이션 스크립트

기존 trading_configs 컬렉션의 데이터를 users 컬렉션의 trading_config 필드로 이동시킵니다.
"""

import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from app.infrastructure.database.mongodb_client import get_mongodb_database
    from app.models.mongodb_models import TradingConfigEmbedded
except ImportError as e:
    print(f"❌ 모듈 import 실패: {e}")
    print("\n💡 해결 방법:")
    print("1. 가상환경을 활성화하세요:")
    print("   source venv/bin/activate  # 또는 . venv/bin/activate")
    sys.exit(1)


def migrate_trading_config_to_users(dry_run: bool = False) -> Dict:
    """
    trading_configs 컬렉션의 데이터를 users.trading_config로 마이그레이션
    
    Args:
        dry_run: True면 실제 마이그레이션 없이 검증만 수행
    
    Returns:
        마이그레이션 결과 딕셔너리
    """
    print("=" * 80)
    print("trading_configs → users.trading_config 마이그레이션")
    print("=" * 80)
    print()
    
    if dry_run:
        print("⚠️  DRY RUN 모드: 실제로 데이터를 변경하지 않습니다.")
        print()
    
    try:
        db = get_mongodb_database()
        if db is None:
            print("❌ MongoDB 연결 실패")
            return {"success": False, "error": "MongoDB 연결 실패"}
        
        # 1. trading_configs 컬렉션에서 모든 문서 조회
        print("1️⃣ trading_configs 컬렉션에서 데이터 조회 중...")
        trading_configs = list(db.trading_configs.find({}))
        print(f"   ✓ {len(trading_configs)}개의 trading_config 문서를 찾았습니다.")
        print()
        
        if len(trading_configs) == 0:
            print("ℹ️  마이그레이션할 데이터가 없습니다.")
            return {"success": True, "migrated": 0, "skipped": 0, "errors": 0}
        
        migrated_count = 0
        skipped_count = 0
        error_count = 0
        errors = []
        
        # 2. 각 trading_config를 users 컬렉션으로 마이그레이션
        print("2️⃣ users 컬렉션으로 데이터 마이그레이션 중...")
        print()
        
        for config_doc in trading_configs:
            user_id = config_doc.get("user_id")
            if not user_id:
                print(f"   ⚠️  user_id가 없는 문서 건너뜀: {config_doc.get('_id')}")
                skipped_count += 1
                continue
            
            try:
                # 사용자 존재 확인
                user = db.users.find_one({"user_id": user_id})
                if not user:
                    print(f"   ⚠️  사용자 '{user_id}'를 찾을 수 없어 건너뜀")
                    skipped_count += 1
                    continue
                
                # 이미 trading_config가 있는지 확인
                if user.get("trading_config") and not dry_run:
                    print(f"   ℹ️  사용자 '{user_id}'는 이미 trading_config가 있어 건너뜀")
                    skipped_count += 1
                    continue
                
                # trading_config 데이터 구성 (embedded 형식으로 변환)
                trading_config = {
                    "enabled": config_doc.get("enabled", False),
                    "min_composite_score": config_doc.get("min_composite_score", 2.0),
                    "max_stocks_to_buy": config_doc.get("max_stocks_to_buy", 5),
                    "max_amount_per_stock": config_doc.get("max_amount_per_stock", 10000.0),
                    "max_portfolio_weight_per_stock": config_doc.get("max_portfolio_weight_per_stock", 20.0),
                    "stop_loss_percent": config_doc.get("stop_loss_percent", -7.0),
                    "take_profit_percent": config_doc.get("take_profit_percent", 5.0),
                    "use_sentiment": config_doc.get("use_sentiment", True),
                    "min_sentiment_score": config_doc.get("min_sentiment_score", 0.15),
                    "order_type": config_doc.get("order_type", "00"),
                    "allow_buy_existing_stocks": config_doc.get("allow_buy_existing_stocks", True),
                    "trailing_stop_enabled": config_doc.get("trailing_stop_enabled", False),
                    "trailing_stop_distance_percent": config_doc.get("trailing_stop_distance_percent", 5.0),
                    "trailing_stop_min_profit_percent": config_doc.get("trailing_stop_min_profit_percent", 3.0),
                    "leveraged_trailing_stop_distance_percent": config_doc.get("leveraged_trailing_stop_distance_percent", 7.0),
                    "leveraged_trailing_stop_min_profit_percent": config_doc.get("leveraged_trailing_stop_min_profit_percent", 5.0),
                    "updated_at": config_doc.get("updated_at", datetime.now())
                }
                
                # min_composite_score 변환 (70.0 → 2.0 스케일로 변환)
                if trading_config["min_composite_score"] > 10.0:
                    # 기존 점수 체계(70점 만점)를 새 점수 체계(2~3점)로 변환
                    old_score = trading_config["min_composite_score"]
                    # 간단한 선형 변환: 70점 → 2.5점, 50점 → 2.0점
                    if old_score >= 70:
                        trading_config["min_composite_score"] = 2.5
                    elif old_score >= 50:
                        trading_config["min_composite_score"] = 2.0
                    else:
                        trading_config["min_composite_score"] = 1.5
                    print(f"   📊 사용자 '{user_id}': min_composite_score {old_score} → {trading_config['min_composite_score']} (변환됨)")
                
                if not dry_run:
                    # users 컬렉션 업데이트
                    result = db.users.update_one(
                        {"user_id": user_id},
                        {
                            "$set": {
                                "trading_config": trading_config,
                                "updated_at": datetime.now()
                            }
                        }
                    )
                    
                    if result.modified_count > 0:
                        print(f"   ✅ 사용자 '{user_id}': trading_config 마이그레이션 완료")
                        migrated_count += 1
                    else:
                        print(f"   ⚠️  사용자 '{user_id}': 업데이트 실패 (이미 동일한 데이터일 수 있음)")
                        skipped_count += 1
                else:
                    print(f"   [DRY RUN] 사용자 '{user_id}': trading_config 마이그레이션 예정")
                    migrated_count += 1
                
            except Exception as e:
                error_msg = f"사용자 '{user_id}' 마이그레이션 실패: {str(e)}"
                print(f"   ❌ {error_msg}")
                errors.append(error_msg)
                error_count += 1
        
        print()
        print("=" * 80)
        print("📊 마이그레이션 결과")
        print("=" * 80)
        print(f"   ✅ 성공: {migrated_count}개")
        print(f"   ⏭️  건너뜀: {skipped_count}개")
        print(f"   ❌ 오류: {error_count}개")
        print()
        
        if errors:
            print("오류 상세:")
            for error in errors:
                print(f"   - {error}")
            print()
        
        return {
            "success": True,
            "migrated": migrated_count,
            "skipped": skipped_count,
            "errors": error_count,
            "error_details": errors if errors else None
        }
        
    except Exception as e:
        print(f"❌ 마이그레이션 중 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


def verify_migration() -> Dict:
    """
    마이그레이션 결과 검증
    """
    print("=" * 80)
    print("🔍 마이그레이션 결과 검증")
    print("=" * 80)
    print()
    
    try:
        db = get_mongodb_database()
        if db is None:
            print("❌ MongoDB 연결 실패")
            return {"success": False, "error": "MongoDB 연결 실패"}
        
        # trading_configs 컬렉션에서 user_id 목록 추출
        trading_configs = list(db.trading_configs.find({}, {"user_id": 1}))
        trading_config_user_ids = {doc.get("user_id") for doc in trading_configs if doc.get("user_id")}
        
        print(f"📋 trading_configs 컬렉션: {len(trading_config_user_ids)}개의 사용자")
        print()
        
        # users 컬렉션에서 trading_config가 있는 사용자 확인
        users_with_config = list(db.users.find(
            {"trading_config": {"$exists": True, "$ne": None}},
            {"user_id": 1, "trading_config": 1}
        ))
        users_with_config_ids = {user.get("user_id") for user in users_with_config}
        
        print(f"✅ users.trading_config 필드: {len(users_with_config_ids)}개의 사용자")
        print()
        
        # 비교
        missing_users = trading_config_user_ids - users_with_config_ids
        extra_users = users_with_config_ids - trading_config_user_ids
        
        print("📊 비교 결과:")
        print(f"   - trading_configs에만 있는 사용자: {len(missing_users)}명")
        if missing_users:
            for user_id in missing_users:
                print(f"     • {user_id}")
        print(f"   - users.trading_config에만 있는 사용자: {len(extra_users)}명")
        if extra_users:
            for user_id in extra_users:
                print(f"     • {user_id}")
        print()
        
        if len(missing_users) == 0 and len(trading_config_user_ids) > 0:
            print("✅ 모든 trading_config가 users 컬렉션으로 마이그레이션되었습니다!")
        elif len(missing_users) > 0:
            print(f"⚠️  {len(missing_users)}명의 사용자 설정이 아직 마이그레이션되지 않았습니다.")
        
        return {
            "success": True,
            "trading_configs_count": len(trading_config_user_ids),
            "users_with_config_count": len(users_with_config_ids),
            "missing_users": list(missing_users),
            "extra_users": list(extra_users)
        }
        
    except Exception as e:
        print(f"❌ 검증 중 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="trading_configs → users.trading_config 마이그레이션")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제로 데이터를 변경하지 않고 검증만 수행"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="마이그레이션 결과만 검증 (마이그레이션은 수행하지 않음)"
    )
    
    args = parser.parse_args()
    
    if args.verify:
        result = verify_migration()
        sys.exit(0 if result.get("success") else 1)
    else:
        result = migrate_trading_config_to_users(dry_run=args.dry_run)
        if result.get("success"):
            print()
            print("=" * 80)
            print("🔍 마이그레이션 결과 검증")
            print("=" * 80)
            verify_result = verify_migration()
            sys.exit(0)
        else:
            print(f"❌ 마이그레이션 실패: {result.get('error')}")
            sys.exit(1)
