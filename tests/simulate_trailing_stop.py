import sys
import os
from datetime import datetime
import asyncio
from unittest.mock import MagicMock, patch

# 프로젝트 루트 디렉토리를 path에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.trailing_stop_service import TrailingStopService

async def run_simulation():
    print("=== 트레일링 스톱 시뮬레이션 시작 ===")
    
    service = TrailingStopService()
    
    # DB Mocking
    with patch('app.services.trailing_stop_service.get_db') as mock_get_db:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        # 1. 일반 주식 (AAPL) 매수 시뮬레이션
        print("\n[Scenario 1: 일반 주식 (AAPL)]")
        ticker = "AAPL"
        purchase_price = 100.0
        
        # 초기화
        trailing_data = service.initialize_trailing_stop(
            ticker=ticker,
            purchase_price=purchase_price,
            purchase_date=datetime.utcnow(),
            is_leveraged=False,
            stock_name="Apple Inc.",
            trailing_distance_percent=5.0  # 5% 거리
        )
        trailing_data["_id"] = "mock_id_aapl" # 시뮬레이션을 위해 ID 추가
        print(f"초기 상태: 최고가=${trailing_data['highest_price']}, 익절가=${trailing_data['dynamic_stop_price']}")

        # 가격 상승 시뮬레이션
        prices = [105.0, 110.0, 108.0]
        current_data = trailing_data
        
        for price in prices:
            print(f"\n현재가 변동: ${price}")
            
            # DB 조회를 위한 Mock 설정
            mock_db.trailing_stops.find_one.return_value = current_data
            
            # 최고가 업데이트 시도
            # 실제 서비스 로직을 시뮬레이션하기 위해 수동으로 데이터 갱신 (서비스는 DB만 업데이트하므로)
            if price > current_data['highest_price']:
                new_stop = price * (1 - current_data['trailing_distance_percent'] / 100)
                if new_stop > current_data['dynamic_stop_price']:
                    current_data['highest_price'] = price
                    current_data['dynamic_stop_price'] = new_stop
                    print(f"최고가 갱신! 최고가=${current_data['highest_price']}, 익절가=${current_data['dynamic_stop_price']}")
                else:
                    print("최고가 갱신 시도했으나 익절가가 상향되지 않아 유지.")
            else:
                print("최고가 유지.")

            # 트리거 확인
            mock_db.trailing_stops.find_one.return_value = current_data
            with patch('app.services.auto_trading_service.AutoTradingService.get_auto_trading_config') as mock_config:
                mock_config.return_value = {
                    "trailing_stop_enabled": True,
                    "trailing_stop_min_profit_percent": 3.0
                }
                triggered = service.check_trailing_stop_triggered(ticker, price)
                print(f"트리거 여부: {triggered} (수익률: {((price-purchase_price)/purchase_price)*100:.2f}%)")

        # 2. 레버리지 주식 (TQQQ) 매수 시뮬레이션
        print("\n" + "="*40)
        print("[Scenario 2: 레버리지 주식 (TQQQ)]")
        ticker_lev = "TQQQ"
        purchase_price_lev = 50.0
        
        # 초기화 (10% 거리 적용)
        trailing_data_lev = service.initialize_trailing_stop(
            ticker=ticker_lev,
            purchase_price=purchase_price_lev,
            purchase_date=datetime.utcnow(),
            is_leveraged=True,
            stock_name="ProShares UltraPro QQQ",
            trailing_distance_percent=10.0
        )
        trailing_data_lev["_id"] = "mock_id_tqqq"
        print(f"초기 상태: 최고가=${trailing_data_lev['highest_price']}, 익절가=${trailing_data_lev['dynamic_stop_price']}")

        # 가격 상승 후 급락 시뮬레이션
        prices_lev = [60.0, 65.0, 58.0]
        current_data_lev = trailing_data_lev
        
        for price in prices_lev:
            print(f"\n현재가 변동: ${price}")
            
            mock_db.trailing_stops.find_one.return_value = current_data_lev
            
            if price > current_data_lev['highest_price']:
                new_stop = price * (1 - current_data_lev['trailing_distance_percent'] / 100)
                if new_stop > current_data_lev['dynamic_stop_price']:
                    current_data_lev['highest_price'] = price
                    current_data_lev['dynamic_stop_price'] = new_stop
                    print(f"최고가 갱신! 최고가=${current_data_lev['highest_price']}, 익절가=${current_data_lev['dynamic_stop_price']}")
                else:
                    print("최고가 갱신 시도했으나 익절가가 상향되지 않아 유지.")
            else:
                print("최고가 유지.")

            # 트리거 확인 (레버리지 전용 최소 수익률 5.0% 적용 시뮬레이션)
            mock_db.trailing_stops.find_one.return_value = current_data_lev
            with patch('app.services.auto_trading_service.AutoTradingService.get_auto_trading_config') as mock_config:
                mock_config.return_value = {
                    "trailing_stop_enabled": True,
                    "leveraged_trailing_stop_min_profit_percent": 5.0
                }
                triggered = service.check_trailing_stop_triggered(ticker_lev, price)
                print(f"트리거 여부: {triggered} (수익률: {((price-purchase_price_lev)/purchase_price_lev)*100:.2f}%)")

if __name__ == "__main__":
    asyncio.run(run_simulation())
