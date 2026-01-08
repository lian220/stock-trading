#!/usr/bin/env python3
"""
해외주식 체결기준현재잔고 조회 스크립트
외화사용가능금액(입금된 달러 금액)을 확인합니다.

사용 방법:
1. 가상환경 활성화 후 실행:
   source venv/bin/activate  # 또는 . venv/bin/activate
   python scripts/check_balance.py

2. 또는 API 서버가 실행 중이면:
   curl http://localhost:8000/api/balance/overseas/present
"""

import sys
import os
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from app.services.balance_service import get_overseas_present_balance
except ImportError as e:
    print(f"❌ 모듈 import 실패: {e}")
    print("\n💡 해결 방법:")
    print("1. 가상환경을 활성화하세요:")
    print("   source venv/bin/activate  # 또는 . venv/bin/activate")
    print("\n2. 또는 API 서버가 실행 중이면 다음 명령어로 확인하세요:")
    print("   curl http://localhost:8000/api/balance/overseas/present")
    sys.exit(1)

import json

def main():
    """체결기준현재잔고 조회 및 출력"""
    print("=" * 80)
    print("해외주식 체결기준현재잔고 조회")
    print("=" * 80)
    print()
    
    try:
        # API 호출
        print("API 호출 중...")
        result = get_overseas_present_balance()
        
        # 결과 확인
        if result.get("rt_cd") != "0":
            print(f"❌ 오류 발생: {result.get('msg1', '알 수 없는 오류')}")
            print(f"응답 코드: {result.get('rt_cd')}")
            print(f"메시지 코드: {result.get('msg_cd')}")
            return
        
        print("✅ 조회 성공!")
        print()
        
        # output3 정보 출력 (외화사용가능금액 포함)
        if "output3" in result and result["output3"]:
            output3 = result["output3"]
            print("=" * 80)
            print("💰 외화 계좌 정보 (output3)")
            print("=" * 80)
            
            # 주요 필드 출력
            if "frcr_use_psbl_amt" in output3:
                available_usd = float(output3["frcr_use_psbl_amt"])
                print(f"💵 외화사용가능금액: ${available_usd:,.2f} USD")
            
            if "frcr_evlu_tota" in output3:
                total_valuation = float(output3["frcr_evlu_tota"])
                print(f"📊 외화평가총액: ${total_valuation:,.2f} USD")
            
            if "frcr_dncl_amt_2" in output3:
                dncl_amt = float(output3["frcr_dncl_amt_2"])
                print(f"💸 외화예수금액2: ${dncl_amt:,.2f} USD")
            
            print()
            print("전체 output3 데이터:")
            print(json.dumps(output3, indent=2, ensure_ascii=False))
            print()
        
        # output1 정보 출력 (보유 종목)
        if "output1" in result and result["output1"]:
            output1 = result["output1"]
            if isinstance(output1, list) and len(output1) > 0:
                print("=" * 80)
                print(f"📈 보유 종목 목록 (총 {len(output1)}개)")
                print("=" * 80)
                for i, item in enumerate(output1, 1):
                    ticker = item.get("ovrs_pdno", "N/A")
                    stock_name = item.get("ovrs_item_name", "N/A")
                    quantity = item.get("ovrs_cblc_qty", "0")
                    current_price = item.get("now_pric2", "0")
                    print(f"{i}. {ticker} ({stock_name}): {quantity}주 @ ${current_price}")
                print()
        
        # output2 정보 출력 (합계)
        if "output2" in result and result["output2"]:
            output2 = result["output2"]
            if output2:
                print("=" * 80)
                print("📊 합계 정보 (output2)")
                print("=" * 80)
                print(json.dumps(output2, indent=2, ensure_ascii=False))
                print()
        
        # 전체 응답 출력 (디버깅용)
        print("=" * 80)
        print("📋 전체 응답 (원본)")
        print("=" * 80)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())

