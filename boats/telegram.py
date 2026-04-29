"""
Telegram notifications for assistant — new bookings & status changes.

Uses raw Telegram Bot API via requests (no extra dependencies).
Fails silently when TELEGRAM_BOT_TOKEN or TELEGRAM_ASSISTANT_CHAT_ID is empty.
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = 'https://api.telegram.org/bot{token}/sendMessage'


def send_telegram_message_to(chat_id: str, text: str) -> bool:
    """Send message to a specific Telegram chat_id. Fail-silent."""
    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    if not token or not chat_id:
        return False
    url = TELEGRAM_API_URL.format(token=token)
    try:
        resp = requests.post(url, json={
            'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML',
        }, timeout=10)
        return resp.status_code == 200 and resp.json().get('ok', False)
    except Exception:
        logger.exception('[Telegram] Failed to send to chat_id=%s', chat_id)
        return False


def send_telegram_message(text: str) -> bool:
    """Send a plain-text message to the assistant's Telegram chat.

    Returns True on success, False otherwise.  Never raises.
    """
    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    chat_id = getattr(settings, 'TELEGRAM_ASSISTANT_CHAT_ID', '')

    if not token or not chat_id:
        logger.debug('[Telegram] Skipped: TELEGRAM_BOT_TOKEN or TELEGRAM_ASSISTANT_CHAT_ID not configured')
        return False

    url = TELEGRAM_API_URL.format(token=token)
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200 and resp.json().get('ok'):
            logger.info('[Telegram] Message sent successfully')
            return True
        logger.warning('[Telegram] API error %s: %s', resp.status_code, resp.text[:300])
        return False
    except Exception:
        logger.exception('[Telegram] Failed to send message')
        return False
