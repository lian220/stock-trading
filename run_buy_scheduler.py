#!/usr/bin/env python3
"""
매수 스케줄러를 수동으로 실행하는 스크립트
"""
import asyncio
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.utils.scheduler import stock_scheduler

async def main():
    """매수 스케줄러 실행"""
    print("=" * 80)
    print("매수 스케줄러 수동 실행 시작")
    print("=" * 80)
    
    try:
        # 매수 스케줄러 실행 (Slack 알림 포함)
        await stock_scheduler._execute_auto_buy(send_slack_notification=True)
        print("=" * 80)
        print("매수 스케줄러 실행 완료")
        print("=" * 80)
    except Exception as e:
        print(f"오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
