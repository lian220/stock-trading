from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.core.config import settings
from app.utils.user_context import get_current_user_id
from app.services.balance_service import (
    get_domestic_balance, 
    get_overseas_balance,  
    get_overseas_present_balance,
    overseas_order_resv, 
    inquire_psamount, 
    get_current_price,
    get_overseas_nccs,
    get_overseas_order_detail,
    get_overseas_order_resv_list,
    order_overseas_stock,
    create_conditional_orders,
    calculate_portfolio_profit,
    calculate_cumulative_profit,
    calculate_total_return,
)

router = APIRouter()

@router.get("/", summary="국내주식 잔고 조회")
def read_balance():
    try:
        result = get_domestic_balance()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"잔고 조회 중 오류 발생: {str(e)}")

@router.get("/overseas", summary="해외주식 잔고 조회")
def read_balance_overseas():
    """
    해외주식 잔고 조회 API

    ### 응답
    - 성공 시: 해외주식 잔고 정보 반환
    - 실패 시: 오류 메시지와 함께 HTTP 상태 코드 반환
    """
    try:
        result = get_overseas_balance()  # 해외주식 잔고 조회
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"잔고 조회 중 오류 발생: {str(e)}")

@router.get("/overseas/present", summary="해외주식 체결기준현재잔고 조회 (외화사용가능금액 포함)")
def read_overseas_present_balance():
    """
    해외주식 체결기준현재잔고 조회 API
    
    외화사용가능금액(입금된 달러 금액)을 확인할 수 있는 API입니다.
    
    ### 응답 필드
    - **output3**: 체결기준현재잔고 정보
        - `frcr_use_psbl_amt`: 외화사용가능금액 (USD)
        - `frcr_evlu_tota`: 외화평가총액 (USD)
        - `frcr_dncl_amt_2`: 외화예수금액2 (외화로 표시된 외화사용가능금액)
    
    ### 참고
    - 모의계좌의 경우 output3만 정상 출력됩니다
    - 실전계좌에서는 output1(보유 종목), output2(합계), output3(외화평가총액 등) 모두 조회 가능합니다
    """
    try:
        result = get_overseas_present_balance()
        
        if result.get("rt_cd") != "0":
            raise HTTPException(
                status_code=400 if result.get("rt_cd") == "1" else 500,
                detail=result.get("msg1", "체결기준현재잔고 조회 실패")
            )
        
        # 응답을 더 읽기 쉽게 포맷팅
        formatted_result = {
            "success": True,
            "message": "체결기준현재잔고 조회 성공",
            "data": {
                "output1": result.get("output1", []),  # 보유 종목 목록
                "output2": result.get("output2", {}),   # 합계 정보
                "output3": result.get("output3", {})   # 외화평가총액 및 외화사용가능금액
            },
            "raw_response": result  # 원본 응답도 포함
        }
        
        # 외화사용가능금액이 있으면 별도로 표시
        if "output3" in result and result["output3"]:
            output3 = result["output3"]
            if "frcr_use_psbl_amt" in output3:
                formatted_result["available_usd"] = float(output3["frcr_use_psbl_amt"])
            if "frcr_evlu_tota" in output3:
                formatted_result["total_valuation_usd"] = float(output3["frcr_evlu_tota"])
        
        return formatted_result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"체결기준현재잔고 조회 중 오류 발생: {str(e)}")



# 해외주식 예약주문 접수 요청 모델
class OrderResvRequest(BaseModel):
    pdno: str  # 종목 코드 (예: AAPL)
    ovrs_excg_cd: str  # 거래소 코드 (예: NASD - 나스닥)
    ft_ord_qty: str  # 주문 수량 (예: 1)
    ft_ord_unpr3: str  # 주문 단가 (예: 148.00)
    is_buy: bool = True  # 매수 여부 (True: 매수, False: 매도)
    ord_dvsn: str = "00"  # 주문구분 (00: 지정가, 31: MOO - 미국 매도 예약주문만 가능)

@router.post("/order-resv", summary="해외주식 예약주문 접수")
def order_resv_route(order: OrderResvRequest):
    """
    해외주식 예약주문 접수 API

    미국 예약주문 접수시간
    1) 10:00 ~ 23:20 / 10:00 ~ 22:20 (서머타임 시)
    2) 주문제한 : 16:30 ~ 16:45 경까지 (사유 : 시스템 정산작업시간)
    3) 23:30 정규장으로 주문 전송 (서머타임 시 22:30 정규장 주문 전송)
    4) 미국 거래소 운영시간(한국시간 기준) : 23:30 ~ 06:00 (썸머타임 적용 시 22:30 ~ 05:00)

    ### 입력값 설명
    - **pdno**: 종목 코드 (예: AAPL - 애플 주식)
    - **ovrs_excg_cd**: 거래소 코드 (예: NASD - 나스닥, NYSE - 뉴욕증권거래소)
    - **ft_ord_qty**: 주문 수량 (예: 1 - 1주 매수)
    - **ft_ord_unpr3**: 주문 단가 (예: 148.00 - 달러 단위로 소수점 2자리까지)
    - **is_buy**: 매수 여부 (True: 매수, False: 매도) - 거래소에 따라 알맞은 TR_ID가 자동 지정됨
    - **ord_dvsn**: 주문구분 
        - "00": 지정가 (전 거래소 공통)
        - "31": MOO(장개시시장가) - 미국 매도 예약주문만 가능
    
    ### 유의사항
    - 미국 외 거래소(중국/홍콩/일본/베트남)는 매수/매도 구분을 위해 is_buy 값을 사용합니다.
    - 미국 매도 예약주문에서만 MOO(장개시시장가) 주문이 가능합니다.
    - 지정한 시간에 주문이 자동으로 전송됩니다.
    - 예약주문의 유효기간은 당일입니다.

    ### 응답
    - 성공 시: 주문 접수 결과 반환
    - 실패 시: 오류 메시지와 함께 HTTP 상태 코드 반환
    """
    try:
        order_data = {
            "CANO": settings.KIS_CANO,  # 계좌번호 (환경변수에서 가져옴)
            "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,  # 계좌상품코드 (환경변수에서 가져옴)
            "PDNO": order.pdno,
            "OVRS_EXCG_CD": order.ovrs_excg_cd,
            "FT_ORD_QTY": order.ft_ord_qty,
            "FT_ORD_UNPR3": order.ft_ord_unpr3,
            "is_buy": order.is_buy,  # 매수/매도 여부
            "ORD_DVSN": order.ord_dvsn,  # 주문 구분 (지정가/MOO 등)
            "ORD_SVR_DVSN_CD": "0"  # 주문 서버 구분 코드 (기본값)
        }
        result = overseas_order_resv(order_data)

        if result.get("rt_cd") != "0":
            raise HTTPException(status_code=400, detail=result.get("msg1", "주문 접수 실패"))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"예약주문 접수 중 오류 발생: {str(e)}")
    
@router.get("/inquire-psamount", summary="해외주식 매수가능금액 조회")
def inquire_psamount_route(
    ovrs_excg_cd: str,
    item_cd: str,
    ovrs_ord_unpr: str
):
    """
    해외주식 매수가능금액 조회 API

    ### 입력값 설명
    - **ovrs_excg_cd**: 거래소 코드 (예: NASD - 나스닥, NYSE - 뉴욕증권거래소)
    - **item_cd**: 종목 코드 (예: AAPL - 애플 주식)
    - **ovrs_ord_unpr**: 주문 단가 (예: 148.00 - 달러 단위로 소수점 2자리까지)

    ### 응답
    - 성공 시: 매수가능 금액 및 수량 반환
    - 실패 시: 오류 메시지와 함께 HTTP 상태 코드 반환
    """
    try:
        params = {
            "CANO": settings.KIS_CANO,  # 계좌번호 (환경변수에서 가져옴)
            "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,  # 계좌상품코드 (환경변수에서 가져옴)
            "OVRS_EXCG_CD": ovrs_excg_cd,
            "ITEM_CD": item_cd,
            "OVRS_ORD_UNPR": ovrs_ord_unpr
        }
        result = inquire_psamount(params)

        if result.get("rt_cd") != "0":
            raise HTTPException(status_code=400, detail=result.get("msg1", "조회 실패"))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"매수가능금액 조회 중 오류 발생: {str(e)}")
    
@router.get("/quotations/price", summary="해외주식 현재체결가 조회")
def get_current_price_route(
    excd: str,
    symb: str
):
    """
    해외주식 현재체결가 조회 API

    ### 입력값 설명
    - **excd**: 거래소 코드 (예: NAS - 나스닥, NYS - 뉴욕증권거래소)
    - **symb**: 종목 코드 (예: TSLA - 테슬라 주식)

    ### 응답
    - 성공 시: 현재 체결가 반환
    - 실패 시: 오류 메시지와 함께 HTTP 상태 코드 반환
    """
    try:
        params = {
            "EXCD": excd,
            "SYMB": symb
        }
        result = get_current_price(params)

        if result.get("rt_cd") != "0":
            raise HTTPException(status_code=400, detail=result.get("msg1", "조회 실패"))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"현재체결가 조회 중 오류 발생: {str(e)}")

@router.get("/nccs", summary="해외주식 미체결내역 조회 (모의투자 환경에서는 지원되지 않습니다.)")
def get_overseas_nccs_route(
    ovrs_excg_cd: str = Query(..., description="거래소 코드 (예: NASD - 나스닥, NYSE - 뉴욕증권거래소)"),
    sort_sqn: str = Query("DS", description="정렬순서 (DS: 정순, 그외: 역순)")
):
    """
    해외주식 미체결내역 조회 API
    """
    try:
        # 기본 파라미터 설정
        base_params = {
            "CANO": settings.KIS_CANO,
            "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
            "OVRS_EXCG_CD": ovrs_excg_cd,
            "SORT_SQN": sort_sqn,
        }
        
        # 환경변수에서 모의투자 여부 확인
        is_virtual = "openapivts" in settings.kis_base_url
        
        if is_virtual:
            # 모의투자: 현재 날짜 기준으로 지난 7일 데이터만 조회
            from datetime import datetime, timedelta
            today = datetime.now()
            # 일주일 전으로 설정 (더 짧은 기간으로 테스트)
            seven_days_ago = today - timedelta(days=7)
            
            params = {
                **base_params,
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
                "INQR_ST_DT": seven_days_ago.strftime("%Y%m%d"),
                "INQR_END_DT": today.strftime("%Y%m%d"),
            }
            result = get_overseas_order_detail(params)
        else:
            # 실전투자: 미체결내역 API 사용
            params = {
                **base_params,
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": "",
            }
            result = get_overseas_nccs(params)
        
        if result.get("rt_cd") != "0" and result.get("rt_cd") != "1":
            raise HTTPException(status_code=400, detail=result.get("msg1", "조회 실패"))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"미체결내역 조회 중 오류 발생: {str(e)}")

@router.get("/order-detail", summary="해외주식 주문체결내역 조회 (60일간 매수/매도 거래 내역)")
def get_overseas_order_detail_route(
    days: int = Query(60, ge=1, le=365, description="조회 기간 (일, 기본값: 60일)"),
    ticker: str = Query(None, description="특정 종목만 조회 (선택사항, 예: AAPL)"),
    exchange_code: str = Query(None, description="거래소 코드 (선택사항, 예: NASD, NYSE, AMEX)"),
    sll_buy_dvsn: str = Query("00", description="매도매수구분 (00: 전체, 01: 매도, 02: 매수)"),
    ccld_nccs_dvsn: str = Query("01", description="체결미체결구분 (00: 전체, 01: 체결, 02: 미체결)")
):
    """
    해외주식 주문체결내역 조회 API
    
    한국투자증권 API의 해외주식 주문체결내역 조회 API를 사용하여
    지정된 기간 동안의 매수/매도 거래 내역을 조회합니다.
    
    ### 입력값
    - **days**: 조회 기간 (1-365일, 기본값: 60일)
    - **ticker**: 특정 종목만 조회 (선택사항, 예: "AAPL")
    - **exchange_code**: 거래소 코드 (선택사항, 예: "NASD", "NYSE", "AMEX")
    - **sll_buy_dvsn**: 매도매수구분 (00: 전체, 01: 매도, 02: 매수, 기본값: 00)
    - **ccld_nccs_dvsn**: 체결미체결구분 (00: 전체, 01: 체결, 02: 미체결, 기본값: 01)
    
    ### 응답
    - **output**: 거래 내역 목록
        - 각 거래 내역에는 종목코드, 종목명, 주문일, 체결일, 수량, 단가, 금액, 수수료 등이 포함됩니다
    
    ### 사용 예시
    - 최근 60일간 전체 거래 내역: `GET /balance/order-detail?days=60`
    - 특정 종목 거래 내역: `GET /balance/order-detail?days=60&ticker=AAPL`
    - 매수 거래만 조회: `GET /balance/order-detail?days=60&sll_buy_dvsn=02`
    - 매도 거래만 조회: `GET /balance/order-detail?days=60&sll_buy_dvsn=01`
    
    ### 참고
    - 이 API는 한국투자증권 API의 주문체결내역 조회 API를 사용합니다
    - 모의투자 환경에서도 사용 가능합니다
    """
    try:
        from datetime import datetime, timedelta
        
        # 조회 기간 계산
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # 날짜 형식 변환 (YYYYMMDD)
        start_date_str = start_date.strftime("%Y%m%d")
        end_date_str = end_date.strftime("%Y%m%d")
        
        # API 파라미터 설정
        params = {
            "CANO": settings.KIS_CANO,
            "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
            "ORD_STRT_DT": start_date_str,  # 주문시작일자
            "ORD_END_DT": end_date_str,     # 주문종료일자
            "PDNO": ticker or "",           # 종목번호 (공백: 전체)
            "SLL_BUY_DVSN": sll_buy_dvsn,   # 매도매수구분
            "CCLD_NCCS_DVSN": ccld_nccs_dvsn,  # 체결미체결구분
            "OVRS_EXCG_CD": exchange_code or "",  # 거래소코드 (공백: 전체)
            "SORT_SQN": "DS",               # 정렬순서 (DS: 정순)
        }
        
        # API 호출
        result = get_overseas_order_detail(params)
        
        # 결과 확인
        if result.get("rt_cd") != "0":
            error_msg = result.get("msg1", "조회 실패")
            raise HTTPException(
                status_code=400 if result.get("rt_cd") == "1" else 500,
                detail=error_msg
            )
        
        # 응답 포맷팅
        output = result.get("output", [])
        if not isinstance(output, list):
            output = [output] if output else []
        
        # 통계 계산
        buy_orders = [o for o in output if o.get("sll_buy_dvsn_cd") == "02"]
        sell_orders = [o for o in output if o.get("sll_buy_dvsn_cd") == "01"]
        
        total_buy_amount = sum(
            float(o.get("ft_ord_amt", "0") or "0") 
            for o in buy_orders
        )
        total_sell_amount = sum(
            float(o.get("ft_ord_amt", "0") or "0") 
            for o in sell_orders
        )
        
        return {
            "success": True,
            "message": f"최근 {days}일간 {len(output)}건의 거래 내역을 조회했습니다",
            "period": {
                "start_date": start_date_str,
                "end_date": end_date_str,
                "days": days
            },
            "statistics": {
                "total_orders": len(output),
                "buy_orders": len(buy_orders),
                "sell_orders": len(sell_orders),
                "total_buy_amount": round(total_buy_amount, 2),
                "total_sell_amount": round(total_sell_amount, 2),
                "net_amount": round(total_sell_amount - total_buy_amount, 2)
            },
            "orders": output,
            "raw_response": result  # 원본 응답도 포함
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"주문체결내역 조회 중 오류 발생: {str(e)}")

@router.get("/order-resv-list", summary="해외주식 예약주문 조회 (모의투자 환경에서는 지원되지 않습니다.)")
def get_overseas_order_resv_list_route(
    ovrs_excg_cd: str = Query(None, description="거래소 코드 (예: NASD - 나스닥, NYSE - 뉴욕증권거래소)"),
    inqr_strt_dt: str = Query(..., description="조회 시작일자 (YYYYMMDD)"),
    inqr_end_dt: str = Query(..., description="조회 종료일자 (YYYYMMDD)"),
    inqr_dvsn_cd: str = Query("00", description="조회구분코드 (00: 전체, 01: 일반해외주식, 02: 미니스탁)"),
    prdt_type_cd: str = Query("", description="상품유형코드 (공백: 전체, 512: 미국 나스닥, 515: 일본, 등)")
):
    """
    해외주식 예약주문 조회 API

    ### 입력값 설명
    - **ovrs_excg_cd**: 거래소 코드 (예: NASD - 나스닥, NYSE - 뉴욕)
    - **inqr_strt_dt**: 조회 시작일자 (YYYYMMDD 형식)
    - **inqr_end_dt**: 조회 종료일자 (YYYYMMDD 형식)
    - **inqr_dvsn_cd**: 조회구분코드 (00: 전체, 01: 일반해외주식, 02: 미니스탁)
    - **prdt_type_cd**: 상품유형코드 (공백: 전체조회)
    
    ### 응답
    - 성공 시: 예약주문 내역 반환
    - 실패 시: 오류 메시지와 함께 HTTP 상태 코드 반환
    
    ※ 모의투자 환경에서는 이 API가 지원되지 않습니다.
    """
    try:
        # 날짜 형식 검증
        from datetime import datetime
        try:
            start_date = datetime.strptime(inqr_strt_dt, "%Y%m%d")
            end_date = datetime.strptime(inqr_end_dt, "%Y%m%d")
            
            # 종료일이 시작일보다 이전인지 확인
            if end_date < start_date:
                raise HTTPException(status_code=400, detail="종료일은 시작일 이후여야 합니다.")
        except ValueError:
            raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다. YYYYMMDD 형식으로 입력하세요.")
        
        # 파라미터 설정
        params = {
            "CANO": settings.KIS_CANO,
            "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
            "INQR_STRT_DT": inqr_strt_dt,
            "INQR_END_DT": inqr_end_dt,
            "INQR_DVSN_CD": inqr_dvsn_cd,
            "PRDT_TYPE_CD": prdt_type_cd,
            "OVRS_EXCG_CD": ovrs_excg_cd if ovrs_excg_cd else "",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": ""
        }
        
        from app.services.balance_service import get_overseas_order_resv_list
        result = get_overseas_order_resv_list(params)
        
        # 모의투자 환경에서는 안내 메시지 반환
        if result.get("msg_cd") == "MOCK_UNSUPPORTED":
            return result
        
        if result.get("rt_cd") != "0":
            status_code = 400 if result.get("rt_cd") == "1" else 500
            raise HTTPException(status_code=status_code, detail=result.get("msg1", "예약주문 조회 실패"))
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"예약주문 조회 중 오류 발생: {str(e)}")

# 해외주식 주문 요청 모델
class OrderOverseasRequest(BaseModel):
    pdno: str  # 종목 코드 (예: AAPL)
    ovrs_excg_cd: str  # 거래소 코드 (예: NASD - 나스닥)
    ord_qty: str  # 주문 수량 (예: 1)
    ovrs_ord_unpr: str  # 주문 단가 (예: 148.00)
    is_buy: bool = True  # 매수 여부 (True: 매수, False: 매도)
    ord_dvsn: str = "00"  # 주문구분 (00: 지정가)

@router.post("/order-overseas", summary="해외주식 매수/매도 주문")
def order_overseas_stock_route(request: OrderOverseasRequest):
    """
    해외주식 매수/매도 주문 API
    
    ### 입력값 설명
    - **pdno**: 종목 코드 (예: AAPL - 애플)
    - **ovrs_excg_cd**: 거래소 코드 (예: NASD - 나스닥)
    - **ord_qty**: 주문 수량 (예: 1)
    - **ovrs_ord_unpr**: 주문 단가 (예: 180.00)
    - **is_buy**: 매수 여부 (True: 매수, False: 매도)
    - **ord_dvsn**: 주문구분 (00: 지정가, 그 외 거래소별 문서 참조)
    
    ### 응답
    - 성공 시: 주문 접수 결과 반환
    - 실패 시: 오류 메시지와 함께 HTTP 상태 코드 반환
    """
    try:
        # 주문 데이터 준비
        order_data = {
            "CANO": settings.KIS_CANO,  # 계좌번호 앞 8자리
            "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,  # 계좌번호 뒤 2자리
            "PDNO": request.pdno,  # 종목코드
            "OVRS_EXCG_CD": request.ovrs_excg_cd,  # 해외거래소코드
            "ORD_QTY": request.ord_qty,  # 주문수량
            "OVRS_ORD_UNPR": request.ovrs_ord_unpr,  # 주문단가
            "is_buy": request.is_buy,  # 매수 여부
            "ORD_DVSN": request.ord_dvsn  # 주문구분
        }
        
        # 서비스 함수 호출
        result = order_overseas_stock(order_data)
        
        # 결과 확인
        if result.get("rt_cd") != "0":
            error_msg = result.get("msg1", "주문 처리 중 오류가 발생했습니다")
            raise HTTPException(status_code=400, detail=error_msg)
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"해외주식 주문 처리 중 오류 발생: {str(e)}")
        raise HTTPException(status_code=500, detail=f"주문 처리 중 오류가 발생했습니다: {str(e)}")

# 조건부 주문 요청 모델
class ConditionalOrderRequest(BaseModel):
    pdno: str  # 종목 코드 (예: AAPL)
    ovrs_excg_cd: str  # 거래소 코드 (예: NASD)
    base_price: float  # 기준 가격
    stop_loss_percent: Optional[float] = None  # 손절매 퍼센트 (예: -5.0)
    take_profit_percent: Optional[float] = None  # 이익실현 퍼센트 (예: 5.0)
    quantity: str  # 주문 수량

@router.post("/conditional-order", summary="조건부 주문 설정")
def conditional_order_route(request: ConditionalOrderRequest):
    """
    특정 가격에 도달했을 때 자동으로 실행되는 조건부 주문 설정
    
    ### 입력값 설명
    - **pdno**: 종목 코드 (예: AAPL)
    - **ovrs_excg_cd**: 거래소 코드 (예: NASD)
    - **base_price**: 기준 가격 (지정하지 않으면 보유 주식의 매수 가격으로 설정됨)
    - **stop_loss_percent**: 손절매 퍼센트 (예: -5.0)
    - **take_profit_percent**: 이익실현 퍼센트 (예: 5.0)
    - **quantity**: 주문 수량
    
    ### 예시
    - base_price가 100달러이고 stop_loss_percent가 -5.0이면, 주가가 95달러에 도달했을 때 매도 주문 실행
    - base_price가 100달러이고 take_profit_percent가 5.0이면, 주가가 105달러에 도달했을 때 매도 주문 실행
    """
    try:
        # 요청 데이터 준비
        params = {
            "pdno": request.pdno,
            "ovrs_excg_cd": request.ovrs_excg_cd,
            "base_price": request.base_price if request.base_price else None,
            "stop_loss_percent": request.stop_loss_percent if request.stop_loss_percent is not None else -5.0,
            "take_profit_percent": request.take_profit_percent if request.take_profit_percent is not None else 5.0,
            "quantity": request.quantity
        }
        
        # 조건부 주문 실행
        result = create_conditional_orders(params)
        
        # 결과 확인
        if result.get("rt_cd") != "0":
            error_msg = result.get("msg1", "조건부 주문 설정 중 오류가 발생했습니다")
            raise HTTPException(status_code=400, detail=error_msg)
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"조건부 주문 처리 중 오류 발생: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조건부 주문 처리 중 오류가 발생했습니다: {str(e)}")

@router.get("/profit/portfolio", summary="보유 종목 수익률 조회")
def get_portfolio_profit():
    """
    현재 보유 중인 종목의 수익률을 조회합니다.
    
    ### 응답
    - **holdings**: 각 종목별 수익률 정보
    - **total_cost**: 총 매수금액
    - **total_value**: 총 평가금액
    - **total_profit**: 총 수익 (미실현)
    - **total_profit_percent**: 총 수익률 (%)
    
    ### 참고
    - 이 API는 **현재 보유 중인 종목**의 미실현 수익률만 계산합니다
    - 완료된 거래(매수→매도)의 누적 수익률은 `/profit/cumulative` 엔드포인트를 사용하세요
    """
    try:
        result = calculate_portfolio_profit()
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "수익률 계산 실패"))
        
        return {
            "success": True,
            **result
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"수익률 조회 중 오류 발생: {str(e)}")

@router.get("/profit/total", summary="전체 수익률 조회 (총 자산 기준)")
def get_total_return(
    user_id: Optional[str] = Query(None, description="사용자 ID (기본값: 현재 사용자)")
):
    if user_id is None:
        user_id = get_current_user_id()
    """
    전체 수익률을 조회합니다.
    총 자산과 총 입금금액을 비교하여 전체 수익률을 계산합니다.
    
    ### 입력값
    - **user_id**: 사용자 ID (기본값: 현재 사용자, None이면 자동으로 현재 사용자 ID 사용)
    
    ### 응답
    - **total_deposit_usd**: 총 입금금액 (USD)
    - **total_assets_usd**: 총 자산 (USD)
    - **total_return_usd**: 총 수익 (USD, 총 자산 - 총 입금금액)
    - **total_return_percent**: 전체 수익률 (%)
    
    ### 계산식
    - 전체 수익률 = (총 자산 - 총 입금금액) / 총 입금금액 * 100
    
    ### 참고
    - 이 API는 **현재 시점의 총 자산**을 기준으로 수익률을 계산합니다
    - 미실현 수익과 실현 수익을 모두 포함합니다
    - 완료된 거래만의 수익률은 `/profit/cumulative` 엔드포인트를 사용하세요
    """
    try:
        result = calculate_total_return(user_id=user_id)
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "전체 수익률 계산 실패"))
        
        return {
            "success": True,
            **result
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"전체 수익률 조회 중 오류 발생: {str(e)}")

@router.get("/profit/cumulative", summary="완료된 거래 누적 수익률 조회")
def get_cumulative_profit(
    user_id: str = Query(..., description="사용자 ID (필수)"),
    days: int = Query(90, ge=1, le=365, description="조회 기간 (일, 기본값: 90일)"),
    ticker: str = Query(None, description="특정 티커만 조회 (선택사항)")
):
    """
    완료된 거래(매수→매도)의 누적 수익률을 조회합니다.
    FIFO (First In First Out) 방식으로 매수/매도 거래를 매칭합니다.
    
    ### 입력값
    - **user_id**: 사용자 ID (필수)
    - **days**: 조회 기간 (1-365일, 기본값: 90일)
    - **ticker**: 특정 티커만 조회 (선택사항, 예: "AAPL")
    
    ### 응답
    - **trades**: 완료된 거래 목록
        - ticker: 티커
        - stock_name: 종목명
        - buy_date: 매수일
        - sell_date: 매도일
        - holding_days: 보유 기간 (일)
        - buy_price: 매수가
        - sell_price: 매도가
        - quantity: 거래 수량
        - cost: 매수금액
        - revenue: 매도금액
        - profit: 실현 수익
        - profit_percent: 수익률 (%)
        - sell_reasons: 매도 사유
    
    - **statistics**: 통계 정보
        - total_trades: 총 거래 횟수
        - winning_trades: 수익 거래 횟수
        - losing_trades: 손실 거래 횟수
        - win_rate: 승률 (%)
        - total_profit: 총 실현 수익 (USD)
        - total_cost: 총 매수 금액 (USD)
        - total_profit_percent: 총 수익률 (%)
        - avg_profit_percent: 평균 수익률 (%)
        - avg_winning_profit_percent: 평균 수익 거래 수익률 (%)
        - avg_losing_profit_percent: 평균 손실 거래 손실률 (%)
    
    - **by_ticker**: 티커별 통계
    
    ### 사용 예시
    - 전체 누적 수익률 확인: `GET /profit/cumulative?user_id=system&days=90`
    - 특정 종목 수익률 확인: `GET /profit/cumulative?user_id=system&days=90&ticker=AAPL`
    - 최근 30일 거래만 확인: `GET /profit/cumulative?user_id=system&days=30`
    
    ### 참고
    - 이 API는 **완료된 거래**만 계산합니다 (매수 후 매도까지 완료된 거래)
    - 현재 보유 중인 종목의 미실현 수익률은 `/profit/portfolio` 엔드포인트를 사용하세요
    - **user_id별로 거래가 분리되어 계산됩니다**
    """
    try:
        result = calculate_cumulative_profit(user_id=user_id, days=days, ticker=ticker)
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "누적 수익률 계산 실패"))
        
        return {
            "success": True,
            **result
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"누적 수익률 조회 중 오류 발생: {str(e)}")

# 수동 입금 기록 요청 모델
class ManualDepositRequest(BaseModel):
    amount: float  # 입금 금액 (USD)
    date: Optional[datetime] = None  # 입금 일시 (기본값: 현재 시간)
    description: Optional[str] = None  # 입금 설명 (선택사항)

@router.post("/deposit", summary="수동 입금 기록")
def record_manual_deposit(
    request: ManualDepositRequest,
    user_id: Optional[str] = Query(None, description="사용자 ID (기본값: 현재 사용자)")
):
    if user_id is None:
        user_id = get_current_user_id()
    """
    수동으로 입금을 기록합니다 (보정용).
    
    ### 입력값
    - **amount**: 입금 금액 (USD, 필수)
    - **date**: 입금 일시 (선택사항, 기본값: 현재 시간)
    - **description**: 입금 설명 (선택사항)
    - **user_id**: 사용자 ID (쿼리 파라미터, 기본값: 현재 사용자, None이면 자동으로 현재 사용자 ID 사용)
    
    ### 사용 시나리오
    1. 입금 자동 감지가 실패한 경우 수동 보정
    2. 초기 입금금액 설정
    3. 입금 이력 관리
    
    ### 응답
    - **success**: 성공 여부
    - **total_deposit_usd**: 업데이트된 총 입금금액
    - **deposit_increase**: 증가한 입금금액
    
    ### 주의사항
    - 이 API는 총 입금금액을 직접 증가시킵니다
    - 입금 이력은 account_balance.deposit_history에 기록됩니다
    """
    try:
        from app.db.mongodb import get_db
        
        if request.amount <= 0:
            raise HTTPException(status_code=400, detail="입금 금액은 0보다 커야 합니다")
        
        db = get_db()
        if db is None:
            raise HTTPException(status_code=500, detail="MongoDB 연결 실패")
        
        # 기존 사용자 확인
        user = db.users.find_one({"user_id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail=f"사용자 '{user_id}'를 찾을 수 없습니다")
        
        # 현재 계좌 정보 조회
        account_balance = user.get("account_balance", {})
        current_deposit = account_balance.get("total_deposit_usd", 0.0) or 0.0
        previous_deposit = account_balance.get("previous_total_deposit_usd", 0.0) or 0.0
        
        # 입금 금액 추가
        new_deposit = current_deposit + request.amount
        
        # 입금 이력 업데이트
        deposit_history = account_balance.get("deposit_history", []) or []
        deposit_record = {
            "amount": request.amount,
            "date": (request.date or datetime.utcnow()).isoformat(),
            "description": request.description or "수동 입금 기록",
            "recorded_at": datetime.utcnow().isoformat()
        }
        deposit_history.append(deposit_record)
        
        # 계좌 정보 업데이트
        account_balance["total_deposit_usd"] = new_deposit
        account_balance["previous_total_deposit_usd"] = current_deposit
        account_balance["deposit_history"] = deposit_history
        account_balance["last_updated"] = datetime.utcnow()
        
        # 전체 수익률 재계산
        total_assets_usd = account_balance.get("total_assets_usd", 0.0) or 0.0
        if new_deposit > 0:
            total_return_percent = ((total_assets_usd - new_deposit) / new_deposit) * 100
            account_balance["total_return_percent"] = round(total_return_percent, 2)
        
        # MongoDB 업데이트
        result = db.users.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "account_balance": account_balance,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="계좌 정보 업데이트 실패")
        
        return {
            "success": True,
            "total_deposit_usd": round(new_deposit, 2),
            "deposit_increase": round(request.amount, 2),
            "previous_deposit": round(current_deposit, 2),
            "deposit_record": deposit_record
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"수동 입금 기록 중 오류 발생: {str(e)}")
