#!/usr/bin/env python3
"""
사용자 계좌 정보 업데이트 스크립트
해외주식 체결기준현재잔고 조회 결과를 users 컬렉션에 업데이트합니다.
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from app.services.balance_service import (
        get_overseas_present_balance, 
        calculate_cumulative_profit,
        get_overseas_order_detail
    )
    from app.db.mongodb import get_db
    from app.core.config import settings
    from app.core.enums import OrderStatus
    from datetime import timedelta
except ImportError as e:
    print(f"❌ 모듈 import 실패: {e}")
    print("\n💡 해결 방법:")
    print("1. 가상환경을 활성화하세요:")
    print("   source venv/bin/activate  # 또는 . venv/bin/activate")
    sys.exit(1)

def update_user_balance(user_id: str = "lian"):
    """사용자 계좌 정보 업데이트"""
    print("=" * 80)
    print(f"사용자 계좌 정보 업데이트: {user_id}")
    print("=" * 80)
    print()
    
    try:
        # 1. 계좌 정보 조회
        print("1️⃣ 계좌 정보 조회 중...")
        balance_result = get_overseas_present_balance()
        
        if balance_result.get("rt_cd") != "0":
            print(f"❌ 계좌 정보 조회 실패: {balance_result.get('msg1', '알 수 없는 오류')}")
            return 1
        
        print("✅ 계좌 정보 조회 성공!")
        print()
        
        # 2. 계좌 정보 추출
        output3 = balance_result.get("output3", {})
        output2 = balance_result.get("output2", [])
        output1 = balance_result.get("output1", [])
        
        # 주요 정보 추출 (소수점 2자리까지 정확하게 저장)
        def safe_float(value, default=0.0):
            """문자열 또는 숫자를 float로 안전하게 변환"""
            if value is None:
                return default
            try:
                return round(float(str(value).replace(",", "")), 2)
            except (ValueError, TypeError):
                return default
        
        # 환율 정보 추출 (output2에서)
        exchange_rate = 1.0
        if output2 and isinstance(output2, list) and len(output2) > 0:
            output2_data = output2[0]
            exchange_rate = safe_float(output2_data.get("frst_bltn_exrt", "1") or "1")
        
        # output3의 값들은 원화(KRW)이므로 USD로 환산 필요
        # output2의 frcr_drwg_psbl_amt_1은 이미 USD 단위
        
        # output1에서 각 종목의 매입금액 합산 (이미 USD 단위)
        total_purchase_usd = 0.0
        if output1 and isinstance(output1, list):
            for item in output1:
                frcr_pchs_amt = safe_float(item.get("frcr_pchs_amt", "0") or "0")
                total_purchase_usd += frcr_pchs_amt
        
        # 현재 보유 현금 (원화를 USD로 환산)
        available_cash_usd = round(safe_float(output3.get("frcr_use_psbl_amt", "0") or "0") / exchange_rate, 2)
        
        # 총 입금금액 = 매입금액 + 현재 보유 현금
        total_deposit_usd = round(total_purchase_usd + available_cash_usd, 2)
        
        account_info = {
            # output3 값들은 원화이므로 USD로 환산
            "available_usd": available_cash_usd,
            "total_valuation_usd": round(safe_float(output3.get("frcr_evlu_tota", "0") or "0") / exchange_rate, 2),
            "total_assets_usd": round(safe_float(output3.get("tot_asst_amt", "0") or "0") / exchange_rate, 2),
            "total_cost_usd": round(total_purchase_usd, 2),  # output1에서 합산한 실제 매입금액 사용
            "total_value_usd": round(safe_float(output3.get("evlu_amt_smtl_amt", "0") or "0") / exchange_rate, 2),
            "total_profit_usd": round(safe_float(output3.get("tot_evlu_pfls_amt", "0") or "0") / exchange_rate, 2),
            "total_profit_percent": safe_float(output3.get("evlu_erng_rt1", "0") or "0"),
            "total_deposit_usd": total_deposit_usd,  # 총 입금금액 (매입금액 + 현재 보유 현금)
            "holdings_count": len(output1) if isinstance(output1, list) else 0,
            "exchange_rate": exchange_rate,  # 기준환율 저장
            "last_updated": datetime.utcnow()
        }
        
        # output2에서 추가 정보 추출 (이미 USD 단위)
        if output2 and isinstance(output2, list) and len(output2) > 0:
            output2_data = output2[0]
            account_info["currency"] = output2_data.get("crcy_cd", "USD")
            account_info["currency_name"] = output2_data.get("crcy_cd_name", "미국 달러")
            account_info["withdrawable_amount_usd"] = safe_float(output2_data.get("frcr_drwg_psbl_amt_1", "0") or "0")
        
        print("2️⃣ 추출된 계좌 정보:")
        print(f"   💰 총 입금금액: ${account_info['total_deposit_usd']:,.2f} USD")
        print(f"      - 매입금액: ${account_info['total_cost_usd']:,.2f} USD")
        print(f"      - 현재 보유 현금: ${account_info['available_usd']:,.2f} USD")
        print()
        print(f"   💵 외화사용가능금액: ${account_info['available_usd']:,.2f} USD")
        print(f"   📊 외화평가총액: ${account_info['total_valuation_usd']:,.2f} USD")
        print(f"   💰 총 자산: ${account_info['total_assets_usd']:,.2f} USD")
        print(f"   💸 매입금액 합계: ${account_info['total_cost_usd']:,.2f} USD")
        print(f"   📈 평가금액 합계: ${account_info['total_value_usd']:,.2f} USD")
        print(f"   📉 총 평가손익: ${account_info['total_profit_usd']:,.2f} USD ({account_info['total_profit_percent']:.2f}%)")
        if account_info.get('total_return_percent') is not None:
            print(f"   📊 전체 수익률: {account_info['total_return_percent']:.2f}% (총 자산 기준)")
        if account_info.get('realized_return_percent') is not None:
            print(f"   💰 실현 수익률: {account_info['realized_return_percent']:.2f}% (완료된 거래 기준)")
        print(f"   📊 보유 종목 수: {account_info['holdings_count']}개")
        print()
        
        # 3. MongoDB 연결 및 업데이트
        print("3️⃣ MongoDB 업데이트 중...")
        db = get_db()
        if db is None:
            print("❌ MongoDB 연결 실패")
            return 1
        
        # 기존 사용자 확인
        existing_user = db.users.find_one({"user_id": user_id})
        
        # 입금 감지 로직: 이전 총 입금금액과 비교
        previous_deposit = 0.0
        if existing_user and "account_balance" in existing_user:
            previous_deposit = existing_user["account_balance"].get("total_deposit_usd", 0.0) or 0.0
        
        current_calculated = total_deposit_usd  # 매입금액 + 현재 보유 현금
        
        # 입금 감지: 증가분만 입금으로 간주
        if current_calculated > previous_deposit:
            deposit_increase = current_calculated - previous_deposit
            account_info["total_deposit_usd"] = current_calculated
            account_info["previous_total_deposit_usd"] = previous_deposit
            print(f"💰 입금 감지: ${deposit_increase:,.2f} USD 증가 (이전: ${previous_deposit:,.2f} → 현재: ${current_calculated:,.2f})")
        else:
            # 감소하거나 같으면 기존 값 유지 (매매로 인한 변화)
            account_info["total_deposit_usd"] = previous_deposit
            account_info["previous_total_deposit_usd"] = previous_deposit
            if current_calculated < previous_deposit:
                print(f"ℹ️  총 입금금액 유지: ${previous_deposit:,.2f} USD (계산값: ${current_calculated:,.2f} - 매매로 인한 변화로 간주)")
        
        # 수익률 계산
        # 전체 수익률: (총 자산 - 총 입금금액) / 총 입금금액 * 100
        if account_info["total_deposit_usd"] > 0:
            total_return_percent = ((account_info["total_assets_usd"] - account_info["total_deposit_usd"]) / account_info["total_deposit_usd"]) * 100
            account_info["total_return_percent"] = round(total_return_percent, 2)
        else:
            account_info["total_return_percent"] = 0.0
        
        # 4. 2025년 11월 1일부터 오늘까지 매매 기록 조회 및 trading_logs 동기화
        print()
        print("4️⃣ 2025년 11월 1일부터 오늘까지 매매 기록 조회 및 동기화 중...")
        try:
            # 2025년 11월 1일부터 오늘까지
            end_date = datetime.utcnow()
            start_date = datetime(2025, 11, 1)
            start_date_str = start_date.strftime("%Y%m%d")
            end_date_str = end_date.strftime("%Y%m%d")
            
            sync_result = sync_trading_logs_from_api(
                user_id=user_id, 
                start_date_str=start_date_str,
                end_date_str=end_date_str
            )
            if sync_result.get("success"):
                print(f"   ✅ 매매 기록 동기화 완료:")
                print(f"      - 조회된 거래: {sync_result.get('total_orders', 0)}건")
                print(f"      - 새로 추가된 거래: {sync_result.get('new_orders', 0)}건")
                print(f"      - 기존 거래: {sync_result.get('existing_orders', 0)}건")
            else:
                print(f"   ⚠️  매매 기록 동기화 실패: {sync_result.get('error', '알 수 없는 오류')}")
        except Exception as e:
            print(f"   ⚠️  매매 기록 동기화 중 오류: {str(e)}")
        
        # 5. trading_logs 통계 확인
        print()
        print("5️⃣ trading_logs 통계 확인 중...")
        try:
            # 2025년 11월 1일부터 오늘까지 모든 거래 조회 (trade_datetime 또는 created_at 기준)
            end_date = datetime.utcnow()
            start_date = datetime(2025, 11, 1)
            
            # trade_datetime이 있으면 그것을 사용, 없으면 created_at 사용
            all_buy_orders = list(db.trading_logs.find({
                "user_id": user_id,
                "order_type": "buy",
                "$or": [
                    {"trade_datetime": {"$gte": start_date, "$lte": end_date}},
                    {"$and": [
                        {"trade_datetime": {"$exists": False}},
                        {"created_at": {"$gte": start_date, "$lte": end_date}}
                    ]}
                ],
                "status": {"$in": [OrderStatus.EXECUTED.value, OrderStatus.SUCCESS.value]}
            }))
            
            all_sell_orders = list(db.trading_logs.find({
                "user_id": user_id,
                "order_type": "sell",
                "$or": [
                    {"trade_datetime": {"$gte": start_date, "$lte": end_date}},
                    {"$and": [
                        {"trade_datetime": {"$exists": False}},
                        {"created_at": {"$gte": start_date, "$lte": end_date}}
                    ]}
                ],
                "status": {"$in": [OrderStatus.EXECUTED.value, OrderStatus.SUCCESS.value]}
            }))
            
            print(f"   📊 2025년 11월 1일부터 오늘까지 거래 통계:")
            print(f"      - 매수 거래: {len(all_buy_orders)}건")
            print(f"      - 매도 거래: {len(all_sell_orders)}건")
            print(f"      - 총 거래: {len(all_buy_orders) + len(all_sell_orders)}건")
            
            # 티커별 매수/매도 현황
            buy_by_ticker = {}
            for order in all_buy_orders:
                ticker = order.get("ticker", "N/A")
                buy_by_ticker[ticker] = buy_by_ticker.get(ticker, 0) + 1
            
            sell_by_ticker = {}
            for order in all_sell_orders:
                ticker = order.get("ticker", "N/A")
                sell_by_ticker[ticker] = sell_by_ticker.get(ticker, 0) + 1
            
            if buy_by_ticker:
                print(f"   📈 티커별 매수 현황:")
                for ticker, count in sorted(buy_by_ticker.items(), key=lambda x: x[1], reverse=True)[:10]:
                    sell_count = sell_by_ticker.get(ticker, 0)
                    print(f"      - {ticker}: 매수 {count}건, 매도 {sell_count}건")
            
        except Exception as e:
            print(f"   ⚠️  통계 확인 중 오류: {str(e)}")
        
        # 6. 실현 수익률 계산 (2025년 11월 1일부터 오늘까지 완료된 거래 기준)
        print()
        print("6️⃣ 수익률 계산 중...")
        try:
            # 2025년 11월 1일부터 오늘까지의 일수 계산
            end_date = datetime.utcnow()
            start_date = datetime(2025, 11, 1)
            days_diff = (end_date - start_date).days
            
            cumulative_result = calculate_cumulative_profit(user_id=user_id, days=days_diff)
            if cumulative_result.get("success") and cumulative_result.get("statistics"):
                stats = cumulative_result["statistics"]
                account_info["realized_return_percent"] = round(stats.get("total_profit_percent", 0.0), 2)
                print(f"   ✅ 2025년 11월 1일부터 오늘까지 실현 수익률: {account_info['realized_return_percent']:.2f}%")
                print(f"      - 완료된 거래 (매수→매도): {stats.get('total_trades', 0)}건")
                print(f"      - 승률: {stats.get('win_rate', 0):.2f}%")
                print(f"      - 총 실현 수익: ${stats.get('total_profit', 0):,.2f} USD")
                print(f"      - 총 매수 금액: ${stats.get('total_cost', 0):,.2f} USD")
                print(f"      - 평균 수익률: {stats.get('avg_profit_percent', 0):.2f}%")
                
                # 종목별 실현 수익률 계산 및 저장 (수익률 + 금액)
                by_ticker = cumulative_result.get("by_ticker", {})
                ticker_realized_profit = {}
                if isinstance(by_ticker, dict):
                    for ticker, ticker_stats in by_ticker.items():
                        if isinstance(ticker_stats, dict):
                            profit_percent = round(ticker_stats.get("total_profit_percent", 0.0), 2)
                            profit_usd = round(ticker_stats.get("total_profit", 0.0), 2)
                            ticker_realized_profit[ticker] = {
                                "profit_percent": profit_percent,
                                "profit_usd": profit_usd
                            }
                elif isinstance(by_ticker, list):
                    for ticker_stats in by_ticker:
                        if isinstance(ticker_stats, dict):
                            ticker = ticker_stats.get("ticker", "N/A")
                            profit_percent = round(ticker_stats.get("total_profit_percent", 0.0), 2)
                            profit_usd = round(ticker_stats.get("total_profit", 0.0), 2)
                            ticker_realized_profit[ticker] = {
                                "profit_percent": profit_percent,
                                "profit_usd": profit_usd
                            }
                
                account_info["ticker_realized_profit"] = ticker_realized_profit if ticker_realized_profit else None
                print(f"   📊 종목별 실현 수익률: {len(ticker_realized_profit)}개 종목")
                if ticker_realized_profit:
                    for ticker, profit_data in sorted(ticker_realized_profit.items(), key=lambda x: x[1].get("profit_percent", 0) if isinstance(x[1], dict) else x[1], reverse=True)[:5]:
                        if isinstance(profit_data, dict):
                            profit_percent = profit_data.get("profit_percent", 0.0)
                            profit_usd = profit_data.get("profit_usd", 0.0)
                            print(f"      - {ticker}: {profit_percent:.2f}% (${profit_usd:+,.2f})")
                        else:
                            # 레거시 호환 (이전 형식)
                            print(f"      - {ticker}: {profit_data:.2f}%")
            else:
                account_info["realized_return_percent"] = 0.0
                account_info["ticker_realized_profit"] = None
                print(f"   ℹ️  완료된 거래가 없습니다.")
        except Exception as e:
            print(f"   ⚠️  실현 수익률 계산 중 오류: {str(e)}")
            account_info["realized_return_percent"] = 0.0
        
        # 6. 현재 보유 종목 수익률 정보
        print()
        print("6️⃣ 현재 보유 종목 수익률:")
        print(f"   📊 총 평가손익: ${account_info['total_profit_usd']:,.2f} USD ({account_info['total_profit_percent']:.2f}%)")
        print(f"      - 매입금액: ${account_info['total_cost_usd']:,.2f} USD")
        print(f"      - 평가금액: ${account_info['total_value_usd']:,.2f} USD")
        
        if not existing_user:
            print(f"⚠️  사용자 '{user_id}'가 존재하지 않습니다.")
            print("   새 사용자를 생성합니다...")
            
            # 새 사용자 생성 (account_balance에 저장)
            user_doc = {
                "user_id": user_id,
                "email": None,
                "display_name": None,
                "preferences": {
                    "default_currency": "USD",
                    "notification_enabled": True
                },
                "account_balance": account_info,
                "stocks": [],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            result = db.users.insert_one(user_doc)
            print(f"✅ 새 사용자 생성 완료 (ID: {result.inserted_id})")
            print(f"   📝 account_balance 필드에 데이터 저장됨")
        else:
            # 기존 사용자 업데이트 (account_balance에 저장)
            update_data = {
                "$set": {
                    "account_balance": account_info,
                    "updated_at": datetime.utcnow()
                }
            }
            
            result = db.users.update_one(
                {"user_id": user_id},
                update_data
            )
            
            if result.modified_count > 0:
                print(f"✅ 사용자 '{user_id}' 계좌 정보 업데이트 완료")
                print(f"   📝 account_balance 필드에 데이터 저장됨")
            else:
                print(f"ℹ️  사용자 '{user_id}' 정보가 변경되지 않았습니다 (이미 최신 정보일 수 있음)")
        
        print()
        print("=" * 80)
        print("✅ 업데이트 완료!")
        print("=" * 80)
        
        # 업데이트된 정보 확인 (account_balance에서 조회)
        updated_user = db.users.find_one({"user_id": user_id})
        if updated_user and "account_balance" in updated_user:
            balance = updated_user["account_balance"]
            print()
            print("📋 저장된 계좌 정보 (account_balance):")
            print(f"   💰 총 입금금액: ${balance.get('total_deposit_usd', 0):,.2f} USD")
            print(f"      - 매입금액: ${balance.get('total_cost_usd', 0):,.2f} USD")
            print(f"      - 현재 보유 현금: ${balance.get('available_usd', 0):,.2f} USD")
            print()
            print(f"   💵 외화사용가능금액: ${balance.get('available_usd', 0):,.2f} USD")
            print(f"   📊 외화평가총액: ${balance.get('total_valuation_usd', 0):,.2f} USD")
            print(f"   💰 총 자산: ${balance.get('total_assets_usd', 0):,.2f} USD")
            print(f"   💸 매입금액 합계: ${balance.get('total_cost_usd', 0):,.2f} USD")
            print(f"   📈 평가금액 합계: ${balance.get('total_value_usd', 0):,.2f} USD")
            print(f"   📉 총 평가손익: ${balance.get('total_profit_usd', 0):,.2f} USD ({balance.get('total_profit_percent', 0):.2f}%)")
            if balance.get('total_return_percent') is not None:
                print(f"   📊 전체 수익률: {balance.get('total_return_percent', 0):.2f}% (총 자산 기준)")
            if balance.get('realized_return_percent') is not None:
                print(f"   💰 실현 수익률: {balance.get('realized_return_percent', 0):.2f}% (완료된 거래 기준)")
            print(f"   📊 보유 종목 수: {balance.get('holdings_count', 0)}개")
            if 'withdrawable_amount_usd' in balance:
                print(f"   💸 출금가능금액: ${balance.get('withdrawable_amount_usd', 0):,.2f} USD")
            print(f"   🕐 마지막 업데이트: {balance.get('last_updated', 'N/A')}")
            
            # 기존 account_balance 정보도 표시 (비교용)
            if "account_balance" in updated_user:
                old_balance = updated_user["account_balance"]
                print()
                print("📋 기존 계좌 정보 (account_balance - 참고용):")
                print(f"   💰 총 입금금액: ${old_balance.get('total_deposit_usd', 0):,.2f} USD")
                print(f"   💰 총 자산: ${old_balance.get('total_assets_usd', 0):,.2f} USD")
                print(f"   🕐 마지막 업데이트: {old_balance.get('last_updated', 'N/A')}")
        
        return 0
        
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


def sync_trading_logs_from_api(user_id: str = "lian", start_date_str: str = None, end_date_str: str = None, days: int = None):
    """
    KIS API에서 매매 기록을 조회하여 trading_logs에 없는 거래를 추가합니다.
    
    Args:
        user_id: 사용자 ID
        start_date_str: 시작일자 (YYYYMMDD 형식, 예: "20251101")
        end_date_str: 종료일자 (YYYYMMDD 형식, 예: "20250106")
        days: 조회 기간 (일) - start_date_str이 없을 때만 사용
    
    Returns:
        dict: {
            "success": bool,
            "total_orders": int,
            "new_orders": int,
            "existing_orders": int,
            "error": str (optional)
        }
    """
    try:
        db = get_db()
        if db is None:
            return {"success": False, "error": "MongoDB 연결 실패"}
        
        # 조회 기간 설정
        if start_date_str and end_date_str:
            # 직접 날짜 지정
            pass
        elif days:
            # days 기준으로 계산
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            start_date_str = start_date.strftime("%Y%m%d")
            end_date_str = end_date.strftime("%Y%m%d")
        else:
            # 기본값: 2025년 11월 1일부터 오늘까지
            end_date = datetime.utcnow()
            start_date = datetime(2025, 11, 1)
            start_date_str = start_date.strftime("%Y%m%d")
            end_date_str = end_date.strftime("%Y%m%d")
        
        # 날짜별로 나눠서 조회 (연속조회가 제대로 작동하지 않으므로)
        def fetch_orders_by_date_range(date_str: str):
            """특정 날짜의 거래 내역 조회 (연속조회 포함)"""
            params = {
                "CANO": settings.KIS_CANO,
                "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
                "ORD_STRT_DT": date_str,
                "ORD_END_DT": date_str,
                "SLL_BUY_DVSN": "00",  # 전체
                "CCLD_NCCS_DVSN": "01",  # 체결만
                "OVRS_EXCG_CD": "",  # 전체 거래소
                "SORT_SQN": "DS",  # 정순
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": ""
            }
            
            date_orders = []
            ctx_area_fk200 = ""
            ctx_area_nk200 = ""
            max_pages = 100  # 일별로 최대 100페이지까지 조회
            seen_keys = set()
            previous_nk200 = None
            
            for page in range(max_pages):
                params["CTX_AREA_FK200"] = ctx_area_fk200
                params["CTX_AREA_NK200"] = ctx_area_nk200
                
                result = get_overseas_order_detail(params)
                
                if result.get("rt_cd") != "0":
                    if page == 0:
                        break
                    else:
                        break
                
                output = result.get("output", [])
                if not isinstance(output, list):
                    output = [output] if output else []
                
                if not output:
                    break
                
                # 중복 제거
                page_new_orders = []
                for order in output:
                    order_key = (
                        order.get("odno", ""),
                        order.get("ord_dt", ""),
                        order.get("pdno", "").strip(),
                        order.get("sll_buy_dvsn_cd", "")
                    )
                    if order_key not in seen_keys:
                        seen_keys.add(order_key)
                        page_new_orders.append(order)
                
                if not page_new_orders:
                    # 새로운 거래가 없으면 종료
                    break
                
                date_orders.extend(page_new_orders)
                
                # 연속조회 키 업데이트
                next_ctx_area_fk200 = result.get("ctx_area_fk200", "") or result.get("CTX_AREA_FK200", "")
                next_ctx_area_nk200 = result.get("ctx_area_nk200", "") or result.get("CTX_AREA_NK200", "")
                
                if isinstance(next_ctx_area_fk200, str):
                    next_ctx_area_fk200 = next_ctx_area_fk200.strip()
                if isinstance(next_ctx_area_nk200, str):
                    next_ctx_area_nk200 = next_ctx_area_nk200.strip()
                
                if not next_ctx_area_nk200:
                    # 연속조회 키가 없으면 종료
                    break
                
                if previous_nk200 is not None and next_ctx_area_nk200 == previous_nk200:
                    # 연속조회 키가 변경되지 않으면 종료 (같은 데이터 반복 방지)
                    break
                
                ctx_area_fk200 = next_ctx_area_fk200
                ctx_area_nk200 = next_ctx_area_nk200
                previous_nk200 = next_ctx_area_nk200
            
            return date_orders
        
        # 날짜 범위를 일별로 나눠서 조회
        start_date = datetime.strptime(start_date_str, "%Y%m%d")
        end_date = datetime.strptime(end_date_str, "%Y%m%d")
        
        all_orders = []
        seen_keys = set()
        current_date = end_date  # 최신부터 과거로
        
        print(f"   📅 날짜별 분할 조회 시작: {start_date_str} ~ {end_date_str}")
        
        while current_date >= start_date:
            date_str = current_date.strftime("%Y%m%d")
            date_orders = fetch_orders_by_date_range(date_str)
            
            # 중복 제거
            for order in date_orders:
                order_key = (
                    order.get("odno", ""),
                    order.get("ord_dt", ""),
                    order.get("pdno", "").strip(),
                    order.get("sll_buy_dvsn_cd", "")
                )
                if order_key not in seen_keys:
                    seen_keys.add(order_key)
                    all_orders.append(order)
            
            if date_orders:
                print(f"      📆 {date_str}: {len(date_orders)}건 조회")
            
            current_date -= timedelta(days=1)
        
        if not all_orders:
            return {
                "success": True,
                "total_orders": 0,
                "new_orders": 0,
                "existing_orders": 0
            }
        
        # trading_logs에 없는 거래 찾기 및 추가
        new_orders_count = 0
        existing_orders_count = 0
        skipped_orders = 0  # 스킵된 주문 수 (디버깅용)
        skipped_no_order_no = 0
        skipped_not_executed = 0
        skipped_unknown_type = 0
        skipped_invalid_data = 0
        
        print(f"   🔍 조회된 거래 내역 분석 중... (총 {len(all_orders)}건)")
        
        # 샘플 데이터 확인 (처음 3개) - 필드명 디버깅
        if len(all_orders) > 0:
            print(f"   📋 샘플 거래 내역 (처음 3개):")
            for i, sample_order in enumerate(all_orders[:3]):
                # 실제 필드명 확인을 위해 모든 키 출력
                if i == 0:
                    print(f"      [필드명 확인] 첫 번째 거래의 모든 키: {list(sample_order.keys())[:10]}")
                print(f"      [{i+1}] 주문번호: {sample_order.get('odno', 'N/A')}, "
                      f"매수/매도: {sample_order.get('sll_buy_dvsn_cd', 'N/A')}, "
                      f"체결수량: {sample_order.get('ft_ccld_qty', 'N/A')}, "
                      f"미체결수량: {sample_order.get('nccs_qty', 'N/A')}, "
                      f"종목: {sample_order.get('pdno', 'N/A')}")
        
        for order in all_orders:
            try:
                # 주문번호로 중복 확인 (대소문자 모두 확인)
                order_no = order.get("odno") or order.get("ODNO") or ""
                if not order_no:
                    skipped_no_order_no += 1
                    skipped_orders += 1
                    continue
                
                # order_no 정규화 (문자열로 변환, 앞뒤 공백 제거)
                order_no = str(order_no).strip()
                
                # 체결 여부 확인 - 미체결 주문은 저장하지 않음 (대소문자 모두 확인)
                nccs_qty = int(order.get("nccs_qty") or order.get("NCCS_QTY") or 0) or 0  # 미체결수량
                ft_ccld_qty = int(order.get("ft_ccld_qty") or order.get("FT_CCLD_QTY") or 0) or 0  # 체결수량
                
                # 미체결 주문은 제외 (미체결수량이 0보다 크면 미체결)
                if nccs_qty > 0:
                    skipped_not_executed += 1
                    skipped_orders += 1
                    continue
                
                # 체결수량이 0이면 체결되지 않은 주문이므로 제외
                if ft_ccld_qty <= 0:
                    skipped_not_executed += 1
                    skipped_orders += 1
                    continue
                
                # 이미 trading_logs에 있는지 확인
                # 여러 방법으로 검색: order_no 필드, order_result.odno
                # order_no는 문자열로 정규화 (앞뒤 공백 제거, 문자열로 변환)
                order_no_normalized = str(order_no).strip()
                
                # user_id도 함께 확인 (다른 사용자의 거래와 구분)
                existing_log = db.trading_logs.find_one({
                    "user_id": user_id,  # user_id 필터 추가
                    "$or": [
                        {"order_no": order_no_normalized},  # order_no 필드로 직접 저장된 경우
                        {"order_no": order_no},  # 원본 형식도 확인
                        {"order_result.odno": order_no_normalized},  # order_result 내부에 저장된 경우
                        {"order_result.odno": order_no}  # 원본 형식도 확인
                    ]
                })
                
                if existing_log:
                    existing_orders_count += 1
                    if existing_orders_count <= 5:  # 처음 5개만 출력
                        print(f"      ⏭️  기존 거래 스킵: order_no={order_no}, ticker={order.get('pdno', 'N/A')}")
                    continue
                
                # 매수/매도 구분 (실제 필드명: sll_buy_dvsn_cd)
                sll_buy_dvsn = order.get("sll_buy_dvsn_cd") or order.get("sll_buy_dvsn") or order.get("SLL_BUY_DVSN") or ""
                order_type = "buy" if sll_buy_dvsn == "02" else "sell" if sll_buy_dvsn == "01" else "unknown"
                
                if order_type == "unknown":
                    skipped_unknown_type += 1
                    skipped_orders += 1
                    continue
                
                # 거래 정보 추출 (실제 필드명: pdno, prdt_name)
                ticker = (order.get("pdno") or order.get("ovrs_pdno") or order.get("OVRS_PDNO") or "").strip()
                stock_name = (order.get("prdt_name") or order.get("ovrs_item_name") or order.get("OVRS_ITEM_NAME") or order.get("item_name") or "").strip()
                quantity = int(order.get("ft_ccld_qty") or order.get("FT_CCLD_QTY") or 0) or 0  # 체결수량
                price = float(order.get("ft_ccld_unpr3") or order.get("FT_CCLD_UNPR3") or 0) or 0  # 체결단가
                
                if not ticker or quantity <= 0 or price <= 0:
                    skipped_invalid_data += 1
                    skipped_orders += 1
                    continue
                
                # 주문일시 파싱 (대소문자 모두 확인)
                ord_dt = order.get("ord_dt") or order.get("ORD_DT") or ""  # YYYYMMDD
                ord_tmd = order.get("ord_tmd") or order.get("ORD_TMD") or ""  # HHMMSS
                
                if ord_dt and ord_tmd:
                    try:
                        order_datetime = datetime.strptime(f"{ord_dt}{ord_tmd}", "%Y%m%d%H%M%S")
                    except:
                        order_datetime = datetime.utcnow()
                else:
                    order_datetime = datetime.utcnow()
                
                # trading_logs에 저장할 데이터
                log_data = {
                    "user_id": user_id,
                    "order_type": order_type,
                    "ticker": ticker,
                    "stock_name": stock_name,
                    "price": price,
                    "quantity": quantity,
                    "status": OrderStatus.EXECUTED.value if order_type in ["buy", "sell"] else OrderStatus.SUCCESS.value,
                    "order_no": order_no,  # 주문번호 (중복 체크용)
                    "order_dt": ord_dt,  # 주문일자 (YYYYMMDD)
                    "order_tmd": ord_tmd,  # 주문시각 (HHMMSS)
                    "trade_datetime": order_datetime,  # 실제 거래 일시 (API에서 가져온 시간)
                    "order_result": {
                        "odno": order_no,
                        "ord_dt": ord_dt,
                        "ord_tmd": ord_tmd,
                        "ovrs_excg_cd": order.get("ovrs_excg_cd", ""),
                        "ft_ccld_qty": quantity,
                        "ft_ccld_unpr3": price,
                        "sll_buy_dvsn": sll_buy_dvsn,
                        "full_order": order  # 전체 주문 정보 보관
                    },
                    "created_at": datetime.utcnow()  # 레코드 생성 시간 (현재 시간)
                }
                
                # trading_logs에 저장
                db.trading_logs.insert_one(log_data)
                new_orders_count += 1
                
                if new_orders_count <= 5:  # 처음 5개만 출력
                    print(f"      ✅ 새 거래 추가: {order_type.upper()} {ticker} {quantity}주 @ ${price:.2f} (주문번호: {order_no})")
                
            except Exception as e:
                print(f"   ⚠️  거래 기록 처리 중 오류 (주문번호: {order.get('odno', 'N/A')}): {str(e)}")
                skipped_orders += 1
                continue
        
        print(f"   📊 분석 결과:")
        print(f"      - 체결된 거래: {len(all_orders) - skipped_orders}건")
        print(f"      - 기존 거래: {existing_orders_count}건")
        print(f"      - 새로 추가: {new_orders_count}건")
        if skipped_orders > 0:
            print(f"      - 스킵된 거래: {skipped_orders}건")
            print(f"        • 주문번호 없음: {skipped_no_order_no}건")
            print(f"        • 미체결: {skipped_not_executed}건")
            print(f"        • 매수/매도 구분 불명: {skipped_unknown_type}건")
            print(f"        • 정보 부족: {skipped_invalid_data}건")
        
        return {
            "success": True,
            "total_orders": len(all_orders),
            "new_orders": new_orders_count,
            "existing_orders": existing_orders_count,
            "skipped_orders": skipped_orders
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "total_orders": 0,
            "new_orders": 0,
            "existing_orders": 0
        }


if __name__ == "__main__":
    import sys
    user_id = sys.argv[1] if len(sys.argv) > 1 else "lian"
    exit(update_user_balance(user_id))

