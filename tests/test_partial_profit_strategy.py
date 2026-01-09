import sys
import os
from datetime import datetime, timedelta
import unittest
from unittest.mock import MagicMock, patch, Mock

# 프로젝트 루트 디렉토리를 path에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.stock_recommendation_service import StockRecommendationService


class TestPartialProfitStrategy(unittest.TestCase):
    """부분 익절 전략 테스트"""
    
    def setUp(self):
        self.service = StockRecommendationService()
        self.ticker = "AAPL"
        self.stock_name = "Apple Inc."
        self.purchase_price = 100.0
        self.initial_quantity = 100  # 초기 보유 수량
        self.user_id = "lian"
    
    @patch('app.services.stock_recommendation_service.get_db')
    def test_check_partial_profit_stage_1st_stage(self, mock_get_db):
        """1단계 부분 익절 테스트 (+5% 도달 시 30% 매도)"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        # 히스토리가 없는 경우
        mock_db.partial_sell_history.find_one.return_value = None
        
        # +5% 도달 (1단계 트리거)
        price_change_percent = 5.0
        current_quantity = 100
        
        result = self.service._check_partial_profit_stage(
            ticker=self.ticker,
            price_change_percent=price_change_percent,
            quantity=current_quantity,
            purchase_price=self.purchase_price
        )
        
        self.assertIsNotNone(result)
        self.assertEqual(result['stage'], 1)
        self.assertEqual(result['profit_percent'], 5.0)
        self.assertEqual(result['sell_percent'], 30.0)
        self.assertEqual(result['sell_quantity'], 30)  # 100 * 0.3 = 30
        self.assertTrue(result['triggered'])
    
    @patch('app.services.stock_recommendation_service.get_db')
    def test_check_partial_profit_stage_2nd_stage(self, mock_get_db):
        """2단계 부분 익절 테스트 (+8% 도달 시 30% 매도)"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        # 1단계 완료 상태
        existing_history = {
            "user_id": self.user_id,
            "ticker": self.ticker,
            "initial_quantity": 100,
            "partial_sells": [
                {
                    "stage": 1,
                    "profit_percent": 5.0,
                    "sell_quantity": 30,
                    "sell_price": 105.0,
                    "sell_date": datetime.utcnow(),
                    "remaining_quantity": 70
                }
            ],
            "is_completed": False
        }
        mock_db.partial_sell_history.find_one.return_value = existing_history
        
        # +8% 도달 (2단계 트리거)
        price_change_percent = 8.0
        current_quantity = 70  # 1단계 매도 후 남은 수량
        
        result = self.service._check_partial_profit_stage(
            ticker=self.ticker,
            price_change_percent=price_change_percent,
            quantity=current_quantity,
            purchase_price=self.purchase_price
        )
        
        self.assertIsNotNone(result)
        self.assertEqual(result['stage'], 2)
        self.assertEqual(result['profit_percent'], 8.0)
        self.assertEqual(result['sell_percent'], 30.0)
        # 초기 수량(100) 기준 30% = 30주
        self.assertEqual(result['sell_quantity'], 30)
        self.assertTrue(result['triggered'])
    
    @patch('app.services.stock_recommendation_service.get_db')
    def test_check_partial_profit_stage_3rd_stage(self, mock_get_db):
        """3단계 부분 익절 테스트 (+12% 도달 시 40% 매도)"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        # 1단계, 2단계 완료 상태
        existing_history = {
            "user_id": self.user_id,
            "ticker": self.ticker,
            "initial_quantity": 100,
            "partial_sells": [
                {
                    "stage": 1,
                    "profit_percent": 5.0,
                    "sell_quantity": 30,
                    "sell_price": 105.0,
                    "sell_date": datetime.utcnow(),
                    "remaining_quantity": 70
                },
                {
                    "stage": 2,
                    "profit_percent": 8.0,
                    "sell_quantity": 30,
                    "sell_price": 108.0,
                    "sell_date": datetime.utcnow(),
                    "remaining_quantity": 40
                }
            ],
            "is_completed": False
        }
        mock_db.partial_sell_history.find_one.return_value = existing_history
        
        # +12% 도달 (3단계 트리거)
        price_change_percent = 12.0
        current_quantity = 40  # 2단계 매도 후 남은 수량
        
        result = self.service._check_partial_profit_stage(
            ticker=self.ticker,
            price_change_percent=price_change_percent,
            quantity=current_quantity,
            purchase_price=self.purchase_price
        )
        
        self.assertIsNotNone(result)
        self.assertEqual(result['stage'], 3)
        self.assertEqual(result['profit_percent'], 12.0)
        self.assertEqual(result['sell_percent'], 40.0)
        # 초기 수량(100) 기준 40% = 40주
        self.assertEqual(result['sell_quantity'], 40)
        self.assertTrue(result['triggered'])
    
    @patch('app.services.stock_recommendation_service.get_db')
    def test_check_partial_profit_stage_already_completed(self, mock_get_db):
        """모든 단계 완료 후 테스트"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        # 모든 단계 완료 상태
        existing_history = {
            "user_id": self.user_id,
            "ticker": self.ticker,
            "initial_quantity": 100,
            "partial_sells": [
                {"stage": 1, "profit_percent": 5.0, "sell_quantity": 30},
                {"stage": 2, "profit_percent": 8.0, "sell_quantity": 30},
                {"stage": 3, "profit_percent": 12.0, "sell_quantity": 40}
            ],
            "is_completed": True
        }
        mock_db.partial_sell_history.find_one.return_value = existing_history
        
        # +15% 도달해도 더 이상 부분 매도 안 함
        price_change_percent = 15.0
        current_quantity = 0
        
        result = self.service._check_partial_profit_stage(
            ticker=self.ticker,
            price_change_percent=price_change_percent,
            quantity=current_quantity,
            purchase_price=self.purchase_price
        )
        
        self.assertIsNone(result)  # 완료되었으면 None 반환
    
    @patch('app.services.stock_recommendation_service.get_db')
    def test_check_partial_profit_stage_not_triggered(self, mock_get_db):
        """부분 익절 조건 미도달 테스트"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        # 히스토리가 없는 경우
        mock_db.partial_sell_history.find_one.return_value = None
        
        # +3% (1단계 조건 미도달)
        price_change_percent = 3.0
        current_quantity = 100
        
        result = self.service._check_partial_profit_stage(
            ticker=self.ticker,
            price_change_percent=price_change_percent,
            quantity=current_quantity,
            purchase_price=self.purchase_price
        )
        
        self.assertIsNone(result)  # 조건 미도달이면 None 반환
    
    @patch('app.services.stock_recommendation_service.get_db')
    def test_check_partial_profit_stage_skip_completed_stages(self, mock_get_db):
        """완료된 단계는 스킵하는지 테스트"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        # 1단계만 완료된 상태
        existing_history = {
            "user_id": self.user_id,
            "ticker": self.ticker,
            "initial_quantity": 100,
            "partial_sells": [
                {
                    "stage": 1,
                    "profit_percent": 5.0,
                    "sell_quantity": 30,
                    "sell_price": 105.0,
                    "sell_date": datetime.utcnow(),
                    "remaining_quantity": 70
                }
            ],
            "is_completed": False
        }
        mock_db.partial_sell_history.find_one.return_value = existing_history
        
        # +5% (1단계는 이미 완료, 2단계는 미도달)
        price_change_percent = 5.5  # 1단계는 완료, 2단계는 아직
        
        result = self.service._check_partial_profit_stage(
            ticker=self.ticker,
            price_change_percent=price_change_percent,
            quantity=70,
            purchase_price=self.purchase_price
        )
        
        self.assertIsNone(result)  # 1단계는 완료, 2단계는 미도달이므로 None
    
    @patch('app.services.stock_recommendation_service.get_db')
    def test_check_partial_profit_stage_sell_quantity_adjustment(self, mock_get_db):
        """매도 수량이 현재 보유 수량을 초과하지 않도록 조정 테스트"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        # 히스토리가 없는 경우
        mock_db.partial_sell_history.find_one.return_value = None
        
        # 초기 수량이 10주인 경우 (30% = 3주)
        price_change_percent = 5.0
        current_quantity = 10
        
        result = self.service._check_partial_profit_stage(
            ticker=self.ticker,
            price_change_percent=price_change_percent,
            quantity=current_quantity,
            purchase_price=self.purchase_price
        )
        
        self.assertIsNotNone(result)
        # 초기 수량이 10주면 30%는 3주
        # 하지만 initial_quantity가 없으면 현재 수량 기준으로 계산
        # 실제로는 초기 수량이 히스토리에 저장되어야 함
        self.assertLessEqual(result['sell_quantity'], current_quantity)


class TestPartialProfitHistoryIntegration(unittest.TestCase):
    """부분 익절 히스토리 통합 테스트"""
    
    def setUp(self):
        self.ticker = "AAPL"
        self.stock_name = "Apple Inc."
        self.purchase_price = 100.0
        self.initial_quantity = 100
        self.user_id = "lian"
    
    @patch('app.db.mongodb.get_db')
    def test_initialize_partial_profit_history_after_buy(self, mock_get_db):
        """매수 후 부분 익절 히스토리 초기화 테스트"""
        from app.utils.scheduler import StockScheduler
        
        mock_db = MagicMock()
        # get_db가 실제로 mock_db를 반환하도록 설정 (None이 아니어야 함)
        mock_get_db.return_value = mock_db
        
        scheduler = StockScheduler()
        
        # 히스토리가 없는 경우 (None 반환)
        mock_db.partial_sell_history.find_one.return_value = None
        
        scheduler._initialize_partial_profit_history_after_buy(
            ticker=self.ticker,
            stock_name=self.stock_name,
            purchase_price=self.purchase_price,
            initial_quantity=self.initial_quantity,
            function_name="test"
        )
        
        # insert_one이 호출되었는지 확인
        mock_db.partial_sell_history.insert_one.assert_called_once()
        
        # 호출된 인자 확인
        call_args = mock_db.partial_sell_history.insert_one.call_args[0][0]
        self.assertEqual(call_args['ticker'], self.ticker)
        self.assertEqual(call_args['initial_quantity'], self.initial_quantity)
        self.assertEqual(call_args['purchase_price'], self.purchase_price)
        self.assertFalse(call_args['is_completed'])
        self.assertEqual(len(call_args['partial_sells']), 0)  # 초기에는 빈 리스트


if __name__ == '__main__':
    unittest.main()
