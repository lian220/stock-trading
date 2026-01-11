#!/usr/bin/env python3
"""
스케줄러의 잔고 조회 로직 테스트 스크립트
수정된 로직이 제대로 작동하는지 확인합니다.
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.balance_service import get_overseas_present_balance

def test_balance_check():
    """스케줄러의 잔고 조회 로직 테스트"""
    print("=" * 80)
    print("스케줄러 잔고 조회 로직 테스트")
    print("=" * 80)
    print()
    
    try:
        # 스케줄러에서 사용하는 로직과 동일하게 테스트
        function_name = "_execute_auto_buy"
        print(f"[{function_name}] 잔고 조회 시작...")
        
        # 1. 체결기준현재잔고 조회
        present_balance_result = get_overseas_present_balance()
        available_cash = 0.0
        
        if present_balance_result.get("rt_cd") == "0":
            # output3에서 외화사용가능금액 조회
            output3 = present_balance_result.get("output3", {})
            
            if output3:
                # frcr_use_psbl_amt: 외화사용가능금액 (USD)
                cash_str = output3.get("frcr_use_psbl_amt") or "0"
                try:
                    available_cash = float(cash_str)
                    print(f"[{function_name}] 💰 구매 가능 금액 (외화사용가능금액): ${available_cash:,.2f}")
                    
                    # 추가 디버깅 정보
                    frcr_evlu_tota = output3.get("frcr_evlu_tota", "0")
                    print(f"[{function_name}] 📊 외화평가총액: ${float(frcr_evlu_tota):,.2f}")
                    
                    # 테스트 결과
                    print()
                    print("=" * 80)
                    print("✅ 테스트 결과")
                    print("=" * 80)
                    print(f"• API 호출 성공: ✅")
                    print(f"• output3 조회 성공: ✅")
                    print(f"• frcr_use_psbl_amt 파싱 성공: ✅")
                    print(f"• 잔고 조회 값: ${available_cash:,.2f}")
                    
                    if available_cash > 0:
                        print(f"• 잔고 상태: 💰 잔고 있음 (${available_cash:,.2f})")
                    else:
                        print(f"• 잔고 상태: ⚠️ 잔고 없음 (${available_cash:,.2f})")
                        print("  (모의투자 계좌에 잔고가 없을 수 있습니다)")
                    
                    return 0
                    
                except (ValueError, TypeError) as e:
                    print(f"❌ [{function_name}] 외화사용가능금액 변환 실패: {cash_str}, 오류: {str(e)}")
                    return 1
            else:
                print(f"❌ [{function_name}] ⚠️ 체결기준현재잔고 조회 실패: output3이 비어있습니다.")
                print(f"전체 응답: {present_balance_result}")
                return 1
        else:
            error_msg = present_balance_result.get('msg1', '알 수 없는 오류')
            error_code = present_balance_result.get('msg_cd', 'N/A')
            print(f"❌ [{function_name}] 체결기준현재잔고 조회 실패: {error_msg} (코드: {error_code})")
            print(f"전체 응답: {present_balance_result}")
            return 1
            
    except Exception as e:
        print(f"❌ 테스트 중 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(test_balance_check())