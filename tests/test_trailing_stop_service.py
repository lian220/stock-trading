import sys
import os
from datetime import datetime, timedelta
import unittest
from unittest.mock import MagicMock, patch

# 프로젝트 루트 디렉토리를 path에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.trailing_stop_service import TrailingStopService
from app.models.mongodb_models import TrailingStop

class TestTrailingStopService(unittest.TestCase):
    def setUp(self):
        self.service = TrailingStopService()
        self.ticker = "AAPL"
        self.purchase_price = 100.0
        self.purchase_date = datetime.utcnow()
        self.stock_name = "Apple Inc."
        self.trailing_distance = 5.0

    @patch('app.services.trailing_stop_service.get_db')
    def test_initialize_trailing_stop(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        result = self.service.initialize_trailing_stop(
            ticker=self.ticker,
            purchase_price=self.purchase_price,
            purchase_date=self.purchase_date,
            stock_name=self.stock_name,
            trailing_distance_percent=self.trailing_distance
        )
        
        self.assertEqual(result['ticker'], self.ticker)
        self.assertEqual(result['highest_price'], 100.0)
        self.assertEqual(result['dynamic_stop_price'], 95.0)
        self.assertTrue(result['is_active'])
        
        mock_db.trailing_stops.update_one.assert_called_once()

    @patch('app.services.trailing_stop_service.get_db')
    def test_update_highest_price(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        # 기존 데이터 시뮬레이션
        existing_stop = {
            "_id": "mock_id",
            "ticker": self.ticker,
            "highest_price": 100.0,
            "dynamic_stop_price": 95.0,
            "trailing_distance_percent": 5.0,
            "is_active": True
        }
        mock_db.trailing_stops.find_one.return_value = existing_stop
        
        # 1. 가격 상승 -> 갱신 성공
        self.service.update_highest_price(self.ticker, 110.0)
        mock_db.trailing_stops.update_one.assert_called()
        
        # 2. 가격 하락 -> 갱신 안 함 (현재 최고가 100.0보다 낮은 95.0으로 시도)
        mock_db.trailing_stops.update_one.reset_mock()
        self.service.update_highest_price(self.ticker, 95.0)
        mock_db.trailing_stops.update_one.assert_not_called()

    @patch('app.services.trailing_stop_service.get_db')
    @patch('app.services.auto_trading_service.AutoTradingService.get_auto_trading_config')
    def test_check_trailing_stop_triggered(self, mock_get_config, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        # 설정 초기화
        mock_get_config.return_value = {
            "trailing_stop_enabled": True,
            "trailing_stop_min_profit_percent": 3.0
        }
        
        # 기존 데이터 시뮬레이션
        existing_stop = {
            "purchase_price": 100.0,
            "highest_price": 120.0,
            "dynamic_stop_price": 114.0, # 120 * 0.95
            "trailing_distance_percent": 5.0,
            "is_active": True
        }
        mock_db.trailing_stops.find_one.return_value = existing_stop
        
        # 1. 트리거 안 됨 (현재가 > 동적 익절가)
        self.assertFalse(self.service.check_trailing_stop_triggered(self.ticker, 115.0))
        
        # 2. 트리거 됨 (현재가 <= 동적 익절가)
        self.assertTrue(self.service.check_trailing_stop_triggered(self.ticker, 113.0))
        
        # 3. 최소 수익률 미달 -> 트리거 안 됨 (현재 113.0이지만, 만약 구매가가 111.0이면 수익률 1.8% < 3.0%)
        existing_stop["purchase_price"] = 111.0
        self.assertFalse(self.service.check_trailing_stop_triggered(self.ticker, 113.0))

    @patch('app.services.trailing_stop_service.get_db')
    @patch('app.services.auto_trading_service.AutoTradingService.get_auto_trading_config')
    def test_check_leveraged_trailing_stop_triggered(self, mock_get_config, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        # 설정 초기화 (레버리지 전용 임계값 설정)
        mock_get_config.return_value = {
            "trailing_stop_enabled": True,
            "leveraged_trailing_stop_min_profit_percent": 5.0
        }
        
        # 레버리지 종목 데이터 시뮬레이션
        existing_stop = {
            "purchase_price": 100.0,
            "highest_price": 120.0,
            "dynamic_stop_price": 108.0, # 120 * 0.90 (레버리지는 distance 10% 가정)
            "trailing_distance_percent": 10.0,
            "is_leveraged": True,
            "is_active": True
        }
        mock_db.trailing_stops.find_one.return_value = existing_stop
        
        # 1. 트리거 안 됨 (현재가 > 동적 익절가)
        self.assertFalse(self.service.check_trailing_stop_triggered(self.ticker, 110.0))
        
        # 2. 트리거 됨 (현재가 <= 동적 익절가)
        self.assertTrue(self.service.check_trailing_stop_triggered(self.ticker, 107.0))
        
        # 3. 최소 수익률(5%) 미달 -> 트리거 안 됨
        # (현재 107.0이지만, 만약 구매가가 103.0이면 수익률 3.8% < 5.0%)
        existing_stop["purchase_price"] = 103.0
        self.assertFalse(self.service.check_trailing_stop_triggered(self.ticker, 107.0))

    @patch('app.services.trailing_stop_service.get_db')
    def test_deactivate_trailing_stop(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        self.service.deactivate_trailing_stop(self.ticker)
        mock_db.trailing_stops.update_one.assert_called_once()
        args, kwargs = mock_db.trailing_stops.update_one.call_args
        self.assertEqual(args[1]['$set']['is_active'], False)

if __name__ == '__main__':
    unittest.main()
