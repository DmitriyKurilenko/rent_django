"""
SMS.ru API — отправка OTP-кодов по SMS.

Документация: https://sms.ru/api
"""
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

SMSRU_SEND_URL = 'https://sms.ru/sms/send'


def send_otp(phone, code, delivery_method='sms'):
    """Отправить OTP-код по SMS через SMS.ru."""
    api_id = settings.SMSRU_API_ID
    if not api_id:
        logger.warning(f'[SMS.ru] API ID not configured, SMS not sent. Code: {code} → {phone}')
        return False

    params = {
        'api_id': api_id,
        'to': phone,
        'msg': f'Код подтверждения договора: {code}. Никому не сообщайте этот код.',
        'json': 1,
    }

    try:
        resp = requests.get(SMSRU_SEND_URL, params=params, timeout=10)
        data = resp.json()
        status_code = data.get('status_code')

        if status_code == 100:
            logger.info(f'[SMS.ru] SMS sent to {phone}')
            return True
        else:
            status_text = data.get('status_text', 'unknown error')
            logger.error(f'[SMS.ru] SMS failed to {phone}: {status_code} — {status_text}')
            return False
    except requests.RequestException as e:
        logger.error(f'[SMS.ru] Request failed to {phone}: {e}')
        return False
