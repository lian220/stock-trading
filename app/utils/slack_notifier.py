import httpx
import logging
import time
import json
from typing import Optional, Dict, Any
from app.core.config import settings

logger = logging.getLogger('slack_notifier')

# httpx의 INFO 레벨 로그 비활성화
logging.getLogger('httpx').setLevel(logging.WARNING)

class SlackNotifier:
    """Slack 알림을 보내는 클래스"""
    
    def __init__(self):
        self.webhook_url_trading = settings.SLACK_WEBHOOK_URL_TRADING
        self.webhook_url_analysis = settings.SLACK_WEBHOOK_URL_ANALYSIS
        self.enabled = settings.SLACK_ENABLED
        
        self.trading_enabled = self.enabled and self.webhook_url_trading
        self.analysis_enabled = self.enabled and self.webhook_url_analysis
        
        if not self.enabled:
            logger.info("Slack 알림이 비활성화되어 있습니다.")
        else:
            if self.trading_enabled:
                logger.info("Slack 거래 알림이 활성화되어 있습니다.")
            if self.analysis_enabled:
                logger.info("Slack 분석 알림이 활성화되어 있습니다.")
    
    def send_message(self, message: str, blocks: Optional[list] = None, webhook_type: str = 'trading') -> bool:
        """
        Slack으로 메시지를 전송합니다.
        
        Args:
            message: 전송할 메시지 텍스트
            blocks: Slack Block Kit 형식의 메시지 블록 (선택)
            webhook_type: 웹훅 타입 ('trading' 또는 'analysis')
        
        Returns:
            bool: 전송 성공 여부
        """
        if not self.enabled:
            logger.debug("Slack 알림이 비활성화되어 있어 메시지를 전송하지 않습니다.")
            return False
        
        # 웹훅 타입에 따라 URL 선택
        if webhook_type == 'trading':
            webhook_url = self.webhook_url_trading
            if not self.trading_enabled:
                logger.debug("Slack 거래 알림이 비활성화되어 있어 메시지를 전송하지 않습니다.")
                return False
        elif webhook_type == 'analysis':
            webhook_url = self.webhook_url_analysis
            if not self.analysis_enabled:
                logger.debug("Slack 분석 알림이 비활성화되어 있어 메시지를 전송하지 않습니다.")
                return False
        else:
            logger.error(f"알 수 없는 웹훅 타입: {webhook_type}")
            return False
        
        try:
            payload = {"text": message}
            if blocks:
                payload["blocks"] = blocks
            
            max_retries = 3
            retry_count = 0
            
            with httpx.Client(timeout=10.0) as client:
                while retry_count <= max_retries:
                    response = client.post(webhook_url, json=payload)
                    
                    if response.status_code == 200:
                        logger.info(f"Slack 메시지 전송 성공 ({webhook_type})")
                        return True
                    elif response.status_code == 429:
                        # Rate limit 에러 처리
                        try:
                            error_data = response.json()
                            retry_after = error_data.get('retry_after', 1)
                            retry_after = max(1, int(retry_after))  # 최소 1초
                            
                            if retry_count < max_retries:
                                logger.warning(
                                    f"Slack API rate limit 도달 ({webhook_type}). "
                                    f"{retry_after}초 후 재시도합니다. (시도 {retry_count + 1}/{max_retries})"
                                )
                                time.sleep(retry_after)
                                retry_count += 1
                                continue
                            else:
                                logger.error(
                                    f"Slack 메시지 전송 실패 ({webhook_type}): "
                                    f"rate limit 재시도 횟수 초과 - {response.status_code} - {response.text}"
                                )
                                return False
                        except (json.JSONDecodeError, ValueError, KeyError):
                            # JSON 파싱 실패 시 기본값 사용
                            logger.warning(
                                f"Slack API rate limit 도달 ({webhook_type}). "
                                f"1초 후 재시도합니다. (시도 {retry_count + 1}/{max_retries})"
                            )
                            if retry_count < max_retries:
                                time.sleep(1)
                                retry_count += 1
                                continue
                            else:
                                logger.error(
                                    f"Slack 메시지 전송 실패 ({webhook_type}): "
                                    f"rate limit 재시도 횟수 초과 - {response.status_code} - {response.text}"
                                )
                                return False
                    else:
                        logger.error(f"Slack 메시지 전송 실패 ({webhook_type}): {response.status_code} - {response.text}")
                        return False
                
                # 모든 재시도 실패
                logger.error(f"Slack 메시지 전송 실패 ({webhook_type}): 최대 재시도 횟수 초과")
                return False
                    
        except Exception as e:
            logger.error(f"Slack 메시지 전송 중 오류 발생 ({webhook_type}): {str(e)}")
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
        if not self.trading_enabled:
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
        
        return self.send_message(text, blocks, webhook_type='trading')
    
    def send_no_buy_notification(
        self,
        reason: str,
        details: Optional[str] = None
    ) -> bool:
        """
        매수를 하지 않을 때 알림을 전송합니다.
        
        Args:
            reason: 매수를 하지 않는 이유 (예: "매수 대상 없음", "주말", "장 시간 아님", "잔고 부족" 등)
            details: 추가 상세 정보 (선택)
        
        Returns:
            bool: 전송 성공 여부
        """
        if not self.trading_enabled:
            return False
        
        title = "⏸️ 자동 매수 작업 건너뜀"
        
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
                "text": {
                    "type": "mrkdwn",
                    "text": f"*이유:* {reason}"
                }
            }
        ]
        
        if details:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*상세 정보:*\n{details}"
                }
            })
        
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"🕒 시각: {self._get_current_time()}"
                }
            ]
        })
        
        # 간단한 텍스트 메시지 (알림용)
        text = f"{title}: {reason}"
        if details:
            text += f"\n{details}"
        
        return self.send_message(text, blocks, webhook_type='trading')
    
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
        if not self.trading_enabled:
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
        
        return self.send_message(text, blocks, webhook_type='trading')
    
    def send_analysis_notification(
        self,
        analysis_type: str,
        total_stocks: int,
        recommendations: list = None,
        predictions: dict = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> bool:
        """
        주식 분석 결과 알림을 전송합니다.
        
        Args:
            analysis_type: 분석 유형 ('technical', 'prediction', 'sentiment' 등)
            total_stocks: 분석된 총 주식 수
            recommendations: 추천 주식 정보 리스트 (선택)
            predictions: 예측 결과 딕셔너리 (선택)
            success: 분석 성공 여부
            error_message: 실패 시 에러 메시지
        
        Returns:
            bool: 전송 성공 여부
        """
        if not self.analysis_enabled:
            return False
        
        # 이모지 및 타이틀 설정
        emoji_map = {
            'technical': '📊',
            'prediction': '🔮',
            'sentiment': '💬',
            'combined': '🎯'
        }
        emoji = emoji_map.get(analysis_type, '📈')
        
        title_map = {
            'technical': '기술적 지표 분석',
            'prediction': 'AI 주가 예측',
            'sentiment': '뉴스 감정 분석',
            'combined': '종합 매수 추천'
        }
        analysis_name = title_map.get(analysis_type, '주식 분석')
        
        # 기본 메시지
        if success:
            title = f"{emoji} {analysis_name} 완료"
            if analysis_type == 'combined':
                status_text = f"✅ 기술적 분석, AI 예측, 감정 분석을 종합한 매수 추천 분석이 완료되었습니다."
            else:
                status_text = f"✅ {analysis_name}이 성공적으로 완료되었습니다."
        else:
            title = f"❌ {analysis_name} 실패"
            status_text = f"분석 중 오류가 발생했습니다.\n*오류:* {error_message}"
        
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
                        "text": f"*분석 유형:*\n{analysis_name}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*분석 종목 수:*\n{total_stocks}개"
                    }
                ]
            }
        ]
        
        # 추천 주식 정보 추가
        if recommendations and len(recommendations) > 0:
            top_recommendations = recommendations[:5]  # 상위 5개만
            
            if analysis_type == 'combined':
                # 통합 분석인 경우 더 상세한 정보 표시
                rec_text = "*🎯 종합 추천 종목 (상위 5개):*\n"
                for i, rec in enumerate(top_recommendations, 1):
                    stock_name = rec.get('stock_name', 'N/A')
                    ticker = rec.get('ticker', 'N/A')
                    score = rec.get('recommendation_score', 0)
                    rise_prob = rec.get('rise_probability', 0)
                    sentiment = rec.get('sentiment_score', 0)
                    
                    rec_text += f"{i}. *{stock_name}* ({ticker})\n"
                    rec_text += f"   └ 종합점수: {score:.2f} | 상승확률: {rise_prob:.1f}% | 감정: {sentiment:.2f}\n"
            else:
                rec_text = "*🎯 추천 종목 (상위 5개):*\n"
                for i, rec in enumerate(top_recommendations, 1):
                    stock_name = rec.get('stock_name', 'N/A')
                    ticker = rec.get('ticker', 'N/A')
                    score = rec.get('recommendation_score', 0)
                    rec_text += f"{i}. *{stock_name}* ({ticker}) - 점수: {score:.2f}\n"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": rec_text
                }
            })
        
        # 예측 결과 정보 추가
        if predictions:
            if analysis_type == 'combined':
                # 통합 분석 통계 정보
                pred_text = "*📊 분석 통계:*\n"
                pred_text += f"• 총 분석 종목: {predictions.get('total_analyzed', 0)}개\n"
                pred_text += f"• 최종 추천 종목: {predictions.get('final_recommendations', 0)}개\n"
                avg_score = predictions.get('avg_composite_score', 0)
                pred_text += f"• 평균 종합 점수: {avg_score:.2f}\n"
            else:
                pred_text = "*🔮 예측 결과:*\n"
                if 'rising_stocks' in predictions:
                    rising = predictions['rising_stocks'][:5]  # 상위 5개만
                    pred_text += f"• 상승 예상 종목: {len(predictions.get('rising_stocks', []))}개\n"
                    if rising:
                        pred_text += "  └ "
                        pred_text += ", ".join([f"{s['stock_name']}({s.get('predicted_change', 'N/A')}%)" 
                                               for s in rising[:3]])
                        pred_text += "\n"
                
                if 'accuracy' in predictions:
                    pred_text += f"• 예측 정확도: {predictions['accuracy']:.2f}%\n"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": pred_text
                }
            })
        
        # 상태 메시지
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": status_text
            }
        })
        
        # 시간 정보
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"🕒 분석 시각: {self._get_current_time()}"
                }
            ]
        })
        
        # 간단한 텍스트 메시지 (알림용)
        text = f"{title}: {total_stocks}개 종목 분석 완료"
        
        return self.send_message(text, blocks, webhook_type='analysis')
    
    def send_combined_analysis_notification(
        self,
        total_stocks: int,
        recommendations: list,
        analysis_stats: dict,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> bool:
        """
        통합 분석 결과 알림을 전송합니다 (4가지 분석 결과 포함).
        
        Args:
            total_stocks: 분석된 총 주식 수
            recommendations: 추천 주식 정보 리스트
            analysis_stats: 분석 통계 정보
            success: 분석 성공 여부
            error_message: 실패 시 에러 메시지
        
        Returns:
            bool: 전송 성공 여부
        """
        if not self.analysis_enabled:
            return False
        
        # 기본 메시지
        if success:
            title = "🎯 종합 투자 분석 완료"
            status_text = "✅ 기술적 분석, AI 예측, 감정 분석을 종합한 투자 추천이 완료되었습니다."
        else:
            title = "❌ 종합 투자 분석 실패"
            status_text = f"분석 중 오류가 발생했습니다.\n*오류:* {error_message}"
        
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
                "text": {
                    "type": "mrkdwn",
                    "text": status_text
                }
            },
            {
                "type": "divider"
            }
        ]
        
        # 분석 통계 섹션
        if success and analysis_stats:
            stats_text = "*📊 분석 개요*\n"
            stats_text += f"• 총 분석 종목: {total_stocks}개\n"
            stats_text += f"• 최종 추천 종목: {analysis_stats.get('final_recommendations', 0)}개\n"
            stats_text += f"• 평균 종합 점수: {analysis_stats.get('avg_composite_score', 0):.2f}\n"
            stats_text += f"• 평균 상승 확률: {analysis_stats.get('avg_rise_probability', 0):.2f}%"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": stats_text
                }
            })
            blocks.append({"type": "divider"})
        
        # 4가지 분석 결과
        if success and analysis_stats:
            analysis_results = "*🔍 세부 분석 결과*\n\n"
            
            # 종목별 분류
            technical_stocks = []
            ai_stocks = []
            sentiment_stocks = []
            
            if recommendations:
                technical_stocks = [r for r in recommendations if r.get('golden_cross') or r.get('rsi', 100) < 50 or r.get('macd_buy_signal')]
                ai_stocks = [r for r in recommendations if r.get('rise_probability', 0) >= 3]
                sentiment_stocks = [r for r in recommendations if r.get('sentiment_score', 0) >= 0.15]
            
            # 1. 기술적 분석
            analysis_results += f"📊 *기술적 지표 분석*\n"
            if technical_stocks:
                stock_names = ", ".join([f"{r['stock_name']}({r['ticker']})" for r in technical_stocks[:3]])
                analysis_results += f"   └ {stock_names}"
                if len(technical_stocks) > 3:
                    analysis_results += f" 외 {len(technical_stocks)-3}개"
                analysis_results += "\n"
            else:
                analysis_results += f"   └ 조건 만족 종목 없음\n"
            analysis_results += f"   └ 골든크로스, RSI<50, MACD매수신호\n\n"
            
            # 2. AI 예측
            analysis_results += f"🔮 *AI 주가 예측*\n"
            if ai_stocks:
                stock_names = ", ".join([f"{r['stock_name']}({r['rise_probability']:.1f}%)" for r in ai_stocks[:3]])
                analysis_results += f"   └ {stock_names}"
                if len(ai_stocks) > 3:
                    analysis_results += f" 외 {len(ai_stocks)-3}개"
                analysis_results += "\n"
            else:
                analysis_results += f"   └ 상승 예상 종목 없음\n"
            analysis_results += f"   └ 평균 상승률: {analysis_stats.get('avg_rise_probability', 0):.1f}%\n\n"
            
            # 3. 감정 분석
            analysis_results += f"💬 *뉴스 감정 분석*\n"
            if sentiment_stocks:
                stock_names = ", ".join([f"{r['stock_name']}({r['sentiment_score']:.2f})" for r in sentiment_stocks[:3]])
                analysis_results += f"   └ {stock_names}"
                if len(sentiment_stocks) > 3:
                    analysis_results += f" 외 {len(sentiment_stocks)-3}개"
                analysis_results += "\n"
            else:
                analysis_results += f"   └ 긍정 감정 종목 없음\n"
            analysis_results += f"   └ 감정 점수 ≥ 0.15 (긍정)\n\n"
            
            # 4. 통합 결과
            analysis_results += f"🎯 *종합 추천*\n"
            if recommendations and len(recommendations) > 0:
                stock_names = ", ".join([f"{r['stock_name']}({r['ticker']})" for r in recommendations[:3]])
                analysis_results += f"   └ {stock_names}"
                if len(recommendations) > 3:
                    analysis_results += f" 외 {len(recommendations)-3}개"
                analysis_results += "\n"
            else:
                analysis_results += f"   └ 추천 종목 없음\n"
            analysis_results += f"   └ 3가지 분석 종합 ({analysis_stats.get('final_recommendations', 0)}개)"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": analysis_results
                }
            })
            blocks.append({"type": "divider"})
        
        # 추천 종목 상세 정보
        if recommendations and len(recommendations) > 0:
            rec_text = "*🏆 TOP 5 추천 종목*\n\n"
            
            for i, rec in enumerate(recommendations[:5], 1):
                stock_name = rec.get('stock_name', 'N/A')
                ticker = rec.get('ticker', 'N/A')
                score = rec.get('recommendation_score', 0)
                rise_prob = rec.get('rise_probability', 0)
                sentiment = rec.get('sentiment_score', 0)
                
                # 기술적 신호 표시
                signals = []
                if rec.get('golden_cross'):
                    signals.append("골든크로스")
                rsi_value = rec.get('rsi')
                if rsi_value is not None and not (isinstance(rsi_value, float) and (rsi_value != rsi_value)):  # NaN 체크
                    if rsi_value < 50:
                        signals.append(f"RSI {rsi_value:.0f}")
                if rec.get('macd_buy_signal'):
                    signals.append("MACD매수")
                signal_text = ", ".join(signals) if signals else "N/A"
                
                rec_text += f"*{i}. {stock_name}* (`{ticker}`)\n"
                rec_text += f"   • 종합점수: {score:.2f} | 상승확률: {rise_prob:.1f}% | 감정: {sentiment:.2f}\n"
                rec_text += f"   • 기술신호: {signal_text}\n\n"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": rec_text
                }
            })
        
        # 시간 정보
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"🕒 분석 시각: {self._get_current_time()}"
                }
            ]
        })
        
        # 간단한 텍스트 메시지 (알림용)
        text = f"{title}: {analysis_stats.get('final_recommendations', 0)}개 종목 추천"
        
        return self.send_message(text, blocks, webhook_type='analysis')
    
    def send_vertex_ai_job_started_notification(
        self, 
        job_name: str, 
        job_resource: str,
        project_id: str
    ) -> bool:
        """Vertex AI Job 시작 알림"""
        if not self.analysis_enabled:
            return False
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "☁️ Vertex AI Job 시작"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Job 이름:*\n{job_name}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*프로젝트:*\n{project_id}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*상태 확인:*\n<https://console.cloud.google.com/vertex-ai/training/custom-jobs?project={project_id}|Google Cloud Console>"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"🕒 시작 시각: {self._get_current_time()}"
                    }
                ]
            }
        ]
        
        text = f"Vertex AI Job 시작: {job_name}"
        return self.send_message(text, blocks, webhook_type='analysis')
    
    def send_vertex_ai_job_error_notification(self, error_message: str) -> bool:
        """Vertex AI Job 오류 알림"""
        if not self.analysis_enabled:
            return False
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "❌ Vertex AI Job 오류"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*오류 메시지:*\n```{error_message[:500]}```"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"🕒 오류 시각: {self._get_current_time()}"
                    }
                ]
            }
        ]
        
        text = f"Vertex AI Job 오류 발생"
        return self.send_message(text, blocks, webhook_type='analysis')
    
    def send_short_interest_notification(
        self,
        short_interest_data: dict,
        ticker_to_stock_mapping: dict
    ) -> bool:
        """
        공매도 정보 알림을 전송합니다.
        
        Args:
            short_interest_data: 공매도 데이터 딕셔너리 {날짜: {티커: {'short_interest': {...}}}}
            ticker_to_stock_mapping: 티커 -> 주식명 매핑 딕셔너리
        
        Returns:
            bool: 전송 성공 여부
        """
        if not self.analysis_enabled:
            return False
        
        # 공매도 데이터가 없으면 전송하지 않음
        if not short_interest_data:
            return False
        
        try:
            # 가장 최근 날짜의 데이터 사용 (공매도 데이터는 날짜별로 동일하므로 첫 번째 날짜 사용)
            first_date = list(short_interest_data.keys())[0] if short_interest_data else None
            if not first_date:
                return False
            
            date_short_data = short_interest_data.get(first_date, {})
            if not date_short_data:
                return False
            
            # 공매도 데이터가 있는 종목만 추출
            stocks_with_short_data = []
            for ticker, stock_data in date_short_data.items():
                short_info = stock_data.get('short_interest', {})
                if short_info:
                    stock_name = ticker_to_stock_mapping.get(ticker, ticker)
                    
                    shares_short = short_info.get('sharesShort')
                    shares_short_prior = short_info.get('sharesShortPriorMonth')
                    short_ratio = short_info.get('shortRatio')
                    short_percent = short_info.get('shortPercentOfFloat')
                    short_change_pct = short_info.get('shortChangePct')

                    stocks_with_short_data.append({
                        'ticker': ticker,
                        'stock_name': stock_name,
                        'sharesShort': shares_short,
                        'sharesShortPriorMonth': shares_short_prior,
                        'shortRatio': short_ratio,
                        'shortPercentOfFloat': short_percent,
                        'shortChangePct': short_change_pct
                    })
            
            # 공매도 데이터가 있는 종목이 없으면 전송하지 않음
            if not stocks_with_short_data:
                return False
            
            # 공매도 비율이 높은 순으로 정렬 (shortPercentOfFloat 기준, 없으면 shortRatio 기준)
            stocks_with_short_data.sort(
                key=lambda x: x.get('shortPercentOfFloat') or x.get('shortRatio') or 0,
                reverse=True
            )
            
            # 상위 10개만 표시
            top_stocks = stocks_with_short_data[:10]
            
            # Slack Block Kit 형식의 메시지 생성
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "📊 공매도 정보 수집 완료",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"✅ 공매도 데이터가 수집되었습니다.\n*수집 날짜:* {first_date}\n*수집 종목 수:* {len(stocks_with_short_data)}개"
                    }
                },
                {
                    "type": "divider"
                }
            ]
            
            # 상위 종목 정보 추가
            stock_text = "*🔝 공매도 비율 상위 종목 (Top 10):*\n\n"
            for i, stock in enumerate(top_stocks, 1):
                stock_name = stock['stock_name']
                ticker = stock['ticker']
                short_percent = stock.get('shortPercentOfFloat')
                short_ratio = stock.get('shortRatio')
                shares_short = stock.get('sharesShort')
                
                short_change_pct = stock.get('shortChangePct')

                stock_text += f"*{i}. {stock_name}* (`{ticker}`)\n"
                if short_percent is not None:
                    stock_text += f"   • 공매도 비율: {short_percent:.2f}%\n"
                if short_ratio is not None:
                    stock_text += f"   • Days to Cover: {short_ratio:.2f}일\n"
                if short_change_pct is not None:
                    # 증감률에 따라 이모지 표시
                    change_emoji = "📈" if short_change_pct > 0 else "📉" if short_change_pct < 0 else "➖"
                    stock_text += f"   • 전월 대비 증감: {change_emoji} {short_change_pct:+.2f}%\n"
                if shares_short is not None:
                    stock_text += f"   • 공매도 주식 수: {shares_short:,.0f}주\n"
                stock_text += "\n"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": stock_text
                }
            })
            
            # 시간 정보
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"🕒 수집 시각: {self._get_current_time()}"
                    }
                ]
            })
            
            # 간단한 텍스트 메시지 (알림용)
            text = f"📊 공매도 정보 수집 완료: {len(stocks_with_short_data)}개 종목"
            
            return self.send_message(text, blocks, webhook_type='analysis')
            
        except Exception as e:
            logger.error(f"공매도 정보 슬랙 전송 중 오류 발생: {str(e)}")
            return False
    
    def send_portfolio_profit_notification(
        self,
        holdings: list,
        total_cost: float,
        total_value: float,
        total_profit: float,
        total_profit_percent: float
    ) -> bool:
        """
        계좌 수익율 알림을 전송합니다.
        
        Args:
            holdings: 보유 종목 리스트 (각 항목은 ticker, stock_name, quantity, avg_price, current_price, profit, profit_percent 포함)
            total_cost: 총 매수금액
            total_value: 총 평가금액
            total_profit: 총 수익
            total_profit_percent: 총 수익율 (%)
        
        Returns:
            bool: 전송 성공 여부
        """
        if not self.trading_enabled:
            return False
        
        # 이모지 설정
        if total_profit >= 0:
            emoji = "📈"
            color = "#36a64f"  # 녹색
        else:
            emoji = "📉"
            color = "#ff0000"  # 빨간색
        
        title = f"{emoji} 계좌 수익율 리포트"
        
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
                        "text": f"*총 매수금액:*\n${total_cost:,.2f}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*총 평가금액:*\n${total_value:,.2f}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*총 수익:*\n${total_profit:+,.2f}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*총 수익율:*\n{total_profit_percent:+.2f}%"
                    }
                ]
            },
            {
                "type": "divider"
            }
        ]
        
        # 보유 종목별 수익율 정보
        if holdings and len(holdings) > 0:
            # 수익율 순으로 정렬 (내림차순)
            sorted_holdings = sorted(holdings, key=lambda x: x.get('profit_percent', 0), reverse=True)
            
            holdings_text = "*📊 보유 종목별 수익율:*\n\n"
            
            for i, holding in enumerate(sorted_holdings[:15], 1):  # 상위 15개만 표시
                ticker = holding.get('ticker', 'N/A')
                stock_name = holding.get('stock_name', ticker)
                quantity = holding.get('quantity', 0)
                avg_price = holding.get('avg_price', 0)
                current_price = holding.get('current_price', 0)
                profit = holding.get('profit', 0)
                profit_percent = holding.get('profit_percent', 0)
                
                # 수익/손실 이모지
                profit_emoji = "🟢" if profit >= 0 else "🔴"
                
                holdings_text += f"{profit_emoji} *{i}. {stock_name}* (`{ticker}`)\n"
                holdings_text += f"   • 보유: {quantity}주 | 평균단가: ${avg_price:.2f} | 현재가: ${current_price:.2f}\n"
                holdings_text += f"   • 수익: ${profit:+,.2f} ({profit_percent:+.2f}%)\n\n"
            
            if len(sorted_holdings) > 15:
                holdings_text += f"... 외 {len(sorted_holdings) - 15}개 종목\n"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": holdings_text
                }
            })
            blocks.append({"type": "divider"})
        else:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*보유 종목이 없습니다.*"
                }
            })
        
        # 시간 정보
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"🕒 리포트 시각: {self._get_current_time()}"
                }
            ]
        })
        
        # 간단한 텍스트 메시지 (알림용)
        text = f"{title}: 총 수익 ${total_profit:+,.2f} ({total_profit_percent:+.2f}%)"
        
        return self.send_message(text, blocks, webhook_type='trading')
    
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

