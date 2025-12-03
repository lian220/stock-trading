import httpx
import logging
from typing import Optional, Dict, Any
from app.core.config import settings

logger = logging.getLogger('slack_notifier')

class SlackNotifier:
    """Slack 알림을 보내는 클래스"""
    
    def __init__(self):
        self.webhook_url = settings.SLACK_WEBHOOK_URL
        self.enabled = settings.SLACK_ENABLED and self.webhook_url
        
        if not self.enabled:
            logger.info("Slack 알림이 비활성화되어 있습니다.")
    
    def send_message(self, message: str, blocks: Optional[list] = None) -> bool:
        """
        Slack으로 메시지를 전송합니다.
        
        Args:
            message: 전송할 메시지 텍스트
            blocks: Slack Block Kit 형식의 메시지 블록 (선택)
        
        Returns:
            bool: 전송 성공 여부
        """
        if not self.enabled:
            logger.debug("Slack 알림이 비활성화되어 있어 메시지를 전송하지 않습니다.")
            return False
        
        try:
            payload = {"text": message}
            if blocks:
                payload["blocks"] = blocks
            
            with httpx.Client(timeout=10.0) as client:
                response = client.post(self.webhook_url, json=payload)
                
                if response.status_code == 200:
                    logger.info("Slack 메시지 전송 성공")
                    return True
                else:
                    logger.error(f"Slack 메시지 전송 실패: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Slack 메시지 전송 중 오류 발생: {str(e)}")
            return False
    
    def send_buy_notification(
        self, 
        stock_name: str, 
        ticker: str, 
        quantity: int, 
        price: float,
        exchange_code: str,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> bool:
        """
        매수 알림을 전송합니다.
        
        Args:
            stock_name: 주식 이름
            ticker: 티커 심볼
            quantity: 매수 수량
            price: 매수 가격
            exchange_code: 거래소 코드
            success: 매수 성공 여부
            error_message: 실패 시 에러 메시지
        
        Returns:
            bool: 전송 성공 여부
        """
        if not self.enabled:
            return False
        
        # 이모지와 색상 설정
        emoji = "✅" if success else "❌"
        color = "#36a64f" if success else "#ff0000"  # 녹색 또는 빨간색
        
        # 기본 메시지
        if success:
            title = f"{emoji} 주식 매수 체결"
            status_text = "매수 주문이 성공적으로 체결되었습니다."
        else:
            title = f"{emoji} 주식 매수 실패"
            status_text = f"매수 주문이 실패했습니다.\n*오류:* {error_message}"
        
        # 총 금액 계산
        total_amount = quantity * price
        
        # Slack Block Kit 형식의 메시지 생성
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": title,
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*종목명:*\n{stock_name}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*티커:*\n{ticker}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*수량:*\n{quantity}주"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*가격:*\n${price:,.2f}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*거래소:*\n{exchange_code}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*총 금액:*\n${total_amount:,.2f}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": status_text
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"🕒 시각: {self._get_current_time()}"
                    }
                ]
            }
        ]
        
        # 간단한 텍스트 메시지 (알림용)
        text = f"{title}: {stock_name}({ticker}) {quantity}주 @ ${price:,.2f}"
        
        return self.send_message(text, blocks)
    
    def send_sell_notification(
        self,
        stock_name: str,
        ticker: str,
        quantity: int,
        price: float,
        exchange_code: str,
        sell_reasons: list,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> bool:
        """
        매도 알림을 전송합니다.
        
        Args:
            stock_name: 주식 이름
            ticker: 티커 심볼
            quantity: 매도 수량
            price: 매도 가격
            exchange_code: 거래소 코드
            sell_reasons: 매도 이유 목록
            success: 매도 성공 여부
            error_message: 실패 시 에러 메시지
        
        Returns:
            bool: 전송 성공 여부
        """
        if not self.enabled:
            return False
        
        # 이모지와 색상 설정
        emoji = "💰" if success else "❌"
        
        # 기본 메시지
        if success:
            title = f"{emoji} 주식 매도 체결"
            status_text = "매도 주문이 성공적으로 체결되었습니다."
        else:
            title = f"{emoji} 주식 매도 실패"
            status_text = f"매도 주문이 실패했습니다.\n*오류:* {error_message}"
        
        # 총 금액 계산
        total_amount = quantity * price
        
        # 매도 이유 포맷팅
        reasons_text = "\n".join([f"• {reason}" for reason in sell_reasons]) if sell_reasons else "정보 없음"
        
        # Slack Block Kit 형식의 메시지 생성
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": title,
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*종목명:*\n{stock_name}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*티커:*\n{ticker}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*수량:*\n{quantity}주"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*가격:*\n${price:,.2f}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*거래소:*\n{exchange_code}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*총 금액:*\n${total_amount:,.2f}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*매도 이유:*\n{reasons_text}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": status_text
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"🕒 시각: {self._get_current_time()}"
                    }
                ]
            }
        ]
        
        # 간단한 텍스트 메시지 (알림용)
        text = f"{title}: {stock_name}({ticker}) {quantity}주 @ ${price:,.2f}"
        
        return self.send_message(text, blocks)
    
    def _get_current_time(self) -> str:
        """현재 시각을 포맷팅해서 반환"""
        from datetime import datetime
        import pytz
        
        korea_tz = pytz.timezone('Asia/Seoul')
        ny_tz = pytz.timezone('America/New_York')
        
        now_korea = datetime.now(korea_tz)
        now_ny = datetime.now(ny_tz)
        
        return f"한국 {now_korea.strftime('%Y-%m-%d %H:%M:%S')} | 뉴욕 {now_ny.strftime('%Y-%m-%d %H:%M:%S')}"

# 싱글톤 인스턴스 생성
slack_notifier = SlackNotifier()

