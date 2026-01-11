#!/usr/bin/env python3
"""
자동 매수 테스트 스크립트
스케줄러의 _execute_auto_buy 함수를 직접 호출하여 매수 로직을 테스트합니다.

주의: 실제 계좌로 실행되므로 실제 주문이 발생할 수 있습니다.
"""

import sys
import asyncio
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.utils.scheduler import stock_scheduler

async def test_auto_buy():
    """자동 매수 테스트"""
    print("=" * 80)
    print("자동 매수 테스트 시작")
    print("=" * 80)
    print()
    print("⚠️  주의: 실제 계좌로 실행되므로 실제 주문이 발생할 수 있습니다.")
    print()
    
    try:
        # 스케줄러의 _execute_auto_buy 함수 직접 호출
        print("매수 로직 실행 중...")
        await stock_scheduler._execute_auto_buy(send_slack_notification=False)
        print()
        print("=" * 80)
        print("✅ 매수 테스트 완료")
        print("=" * 80)
        print()
        print("📋 로그 파일 확인: stock_scheduler.log")
        print()
        return 0
        
    except Exception as e:
        print(f"❌ 테스트 중 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(asyncio.run(test_auto_buy()))