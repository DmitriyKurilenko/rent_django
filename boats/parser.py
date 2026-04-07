"""
Парсер лодок с boataround.com
Интегрирован для Django
"""
import json
import logging
import re
import os
import hashlib
from html import unescape
from pathlib import Path
from typing import Optional
from bs4 import BeautifulSoup
import requests
import mimetypes

# Импортируем BoataroundAPI для получения equipment на разных языках
try:
    from boats.boataround_api import BoataroundAPI
except ImportError:
    BoataroundAPI = None

# Optional boto3 for S3 uploads
try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except Exception:
    boto3 = None
    BotoCoreError = Exception
    ClientError = Exception

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# КОНСТАНТЫ
# =============================================================================

BASE_URL = 'https://www.boataround.com/ru/yachta'
IMAGE_HOST = 'imageresizer.yachtsbt.com'
CDN_URL = 'https://cdn2.prvms.ru'
MEDIA_ROOT = '/app/media/boats'  # Docker path

BOAT_ID_PATTERN = re.compile(r'/boats/([a-f0-9]{24})/')
BOAT_ID_FROM_PICTURE_PATTERN = re.compile(r'^boats/([^/]+)/', re.IGNORECASE)
NORMALIZED_PICTURE_PATH_PATTERN = re.compile(
    r'^boats/[^/]+/[^/?#]+\.(?:jpg|jpeg|png|webp)$',
    re.IGNORECASE,
)
SLUG_FROM_URL_PATTERN = re.compile(r'/(?:boat|yachta)/([^/?#]+)')


def add_currency_param(url: str, currency: str = 'EUR') -> str:
    """
    Добавляет параметр валюты к URL.

    Примеры:
        https://www.boataround.com/ru/yachta/bavaria-cruiser-46
        -> https://www.boataround.com/ru/yachta/bavaria-cruiser-46?currency=EUR

        https://www.boataround.com/ru/yachta/bavaria-cruiser-46?checkIn=2025-05-01
        -> https://www.boataround.com/ru/yachta/bavaria-cruiser-46?checkIn=2025-05-01&currency=EUR
    """
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

    parsed = urlparse(url)
    query_params = parse_qs(parsed.query, keep_blank_values=True)

    # Убираем списки из parse_qs и устанавливаем валюту
    flat_params = {k: v[0] if isinstance(v, list) else v for k, v in query_params.items()}
    flat_params['currency'] = currency

    # Собираем обратно URL
    new_query = urlencode(flat_params)
    new_parsed = parsed._replace(query=new_query)
    result_url = urlunparse(new_parsed)

    logger.info(f"[URL] Добавлен параметр currency={currency}: {result_url}")
    return result_url


# =============================================================================
# СОХРАНЕНИЕ ИЗОБРАЖЕНИЙ
# =============================================================================

def download_and_save_image(image_path: str) -> Optional[str]:
    """
    Скачивает изображение с imageresizer.yachtsbt.com и сохраняет локально.
    Возвращает CDN URL для использования в шаблонах.

    Args:
        image_path: Путь к изображению, например 'boats/62b96d157a9323583a5a4880/650d96fa43b7cac28800ead4.jpg'

    Returns:
        str: CDN URL вроде 'https://cdn2.prvms.ru/yachts/{boat_id}/{filename}' или None
    """
    normalized_path = _normalize_picture_path(image_path)
    if not normalized_path:
        logger.error(f"Невалидный путь изображения: {image_path}")
        return None

    image_path = normalized_path
    source_url = f"https://{IMAGE_HOST}/{image_path}?method=fit&width=1920&height=1080&format=jpeg"

    try:
        parts = image_path.strip('/').split('/')
        if len(parts) < 3:
            logger.error(f"Не удалось распарсить путь изображения: {image_path}")
            return None
        boat_id = parts[1]
        filename = parts[-1]

        # Создаем локальный путь
        local_path = Path(MEDIA_ROOT) / image_path
        local_path.parent.mkdir(parents=True, exist_ok=True)

        # ⭐ ГЛАВНОЕ: CDN URL
        cdn_url = f"https://cdn2.prvms.ru/yachts/{boat_id}/{filename}"
        s3_key = f"{boat_id}/{filename}"

        # ⭐ Если файл уже в S3, просто возвращаем CDN URL (экономим трафик)
        if check_s3_exists(s3_key):
            logger.info(f"Изображение уже в S3: {s3_key} - используем CDN URL")
            return cdn_url

        # Если файл уже существует локально — требуем успешную загрузку в S3.
        if local_path.exists():
            logger.info(f"Изображение уже существует локально: {image_path}")
            try:
                uploaded = upload_file_to_s3(local_path, s3_key, skip_existing=True)
                if uploaded or check_s3_exists(s3_key):
                    return cdn_url
            except Exception as e:
                logger.error(f"Ошибка загрузки локального файла в S3: {e}")
            logger.error(f"Критическая ошибка: изображение {image_path} не загружено в S3")
            return None

        # Скачиваем
        logger.info(f"Скачивание изображения: {source_url}")
        response = requests.get(source_url, timeout=30, stream=True)
        response.raise_for_status()

        # Сохраняем
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(f"Изображение сохранено: {local_path}")

        # ⭐ Загружаем в S3 с проверкой на существование
        try:
            # skip_existing=True: не загружаем, если уже в S3
            uploaded = upload_file_to_s3(local_path, s3_key, skip_existing=True)
            if uploaded or check_s3_exists(s3_key):
                logger.info(f"Изображение загружено в S3: {s3_key}")
                return cdn_url
        except Exception as e:
            logger.error(f"Ошибка при загрузке в S3: {e}")

        logger.error(f"Критическая ошибка: CDN URL не получен для {image_path}")
        return None

    except Exception as e:
        logger.error(f"Ошибка скачивания изображения {image_path}: {e}")
        return None


def get_cdn_url(image_path: str) -> str:
    """
    Формирует URL для CDN.

    Args:
        image_path: Путь к изображению, например '{boat_id}/{filename}.jpg'

    Returns:
        str: https://cdn2.prvms.ru/yachts/{boat_id}/{filename}.jpg
    """
    # Убираем лишние префиксы если они есть
    clean_path = image_path.lstrip('/')
    if clean_path.startswith('boats/'):
        clean_path = clean_path[len('boats/'):]

    # Добавляем yachts/ префикс (имя бакета)
    return f"{CDN_URL}/yachts/{clean_path}"


def check_s3_exists(s3_key: str) -> bool:
    """
    Проверяет, существует ли файл в S3.

    Args:
        s3_key: S3 object key (например: '62b96d157a9323583a5a4880/650d96fa43b7cac28800ead4.jpg')

    Returns:
        bool: True если файл уже в S3, False иначе
    """
    if boto3 is None:
        return False

    bucket = os.environ.get('S3_BUCKET_NAME')
    access_key = os.environ.get('AWS_ACCESS_KEY_ID')
    secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    endpoint = os.environ.get('S3_ENDPOINT_URL')
    region = os.environ.get('S3_REGION')

    if not bucket or not access_key or not secret_key:
        return False

    try:
        session = boto3.session.Session()
        client_kwargs = {
            'aws_access_key_id': access_key,
            'aws_secret_access_key': secret_key,
        }
        if region:
            client_kwargs['region_name'] = region
        if endpoint:
            s3 = session.client('s3', endpoint_url=endpoint, **client_kwargs)
        else:
            s3 = session.client('s3', **client_kwargs)

        s3_key = s3_key.lstrip('/')
        s3.head_object(Bucket=bucket, Key=s3_key)
        logger.debug(f"[S3 Check] Файл уже существует: {s3_key}")
        return True
    except Exception:
        # Файл не существует или ошибка доступа
        return False


def upload_file_to_s3(local_path: Path, s3_key: str, skip_existing: bool = False) -> bool:
    """Upload a local file to S3-compatible storage.

    Reads configuration from environment variables:
      - S3_BUCKET_NAME
      - AWS_ACCESS_KEY_ID
      - AWS_SECRET_ACCESS_KEY
      - S3_ENDPOINT_URL (optional)
      - S3_REGION (optional)

    Args:
        local_path: Path to local file
        s3_key: S3 object key
        skip_existing: If True, skip upload if object already exists in S3

    Returns True if upload succeeded, False otherwise.
    """
    if boto3 is None:
        logger.debug("boto3 not installed; skipping S3 upload")
        return False

    bucket = os.environ.get('S3_BUCKET_NAME')
    access_key = os.environ.get('AWS_ACCESS_KEY_ID')
    secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    endpoint = os.environ.get('S3_ENDPOINT_URL')
    region = os.environ.get('S3_REGION')

    if not bucket or not access_key or not secret_key:
        logger.debug("S3 credentials or bucket not set; skipping S3 upload")
        return False

    try:
        session = boto3.session.Session()
        client_kwargs = {
            'aws_access_key_id': access_key,
            'aws_secret_access_key': secret_key,
        }
        if region:
            client_kwargs['region_name'] = region
        if endpoint:
            s3 = session.client('s3', endpoint_url=endpoint, **client_kwargs)
        else:
            s3 = session.client('s3', **client_kwargs)

        # Ensure key has no leading slash
        s3_key = s3_key.lstrip('/')

        logger.info(f"[S3 Upload] Uploading to bucket='{bucket}', key='{s3_key}'")

        # Check if object already exists (if skip_existing is True)
        if skip_existing:
            try:
                s3.head_object(Bucket=bucket, Key=s3_key)
                logger.info(f"[S3 Upload] Object already exists, skipping: {s3_key}")
                return True
            except Exception:
                # Object doesn't exist, proceed with upload
                pass

        # Determine content type
        content_type, _ = mimetypes.guess_type(str(local_path))
        extra_args = {}
        if content_type:
            extra_args['ContentType'] = content_type

        # Make public by default so CDN can fetch
        extra_args['ACL'] = 'public-read'

        # Upload
        if extra_args:
            s3.upload_file(str(local_path), bucket, s3_key, ExtraArgs=extra_args)
        else:
            s3.upload_file(str(local_path), bucket, s3_key)
        return True
    except (BotoCoreError, ClientError, Exception) as e:
        logger.error(f"S3 upload failed for {s3_key}: {e}")
        return False


# =============================================================================
# ЗАГРУЗКА СТРАНИЦЫ
# =============================================================================

def fetch_page(url: str) -> Optional[str]:
    """Загружает страницу с обходом блокировок."""
    import time
    import random

    # Максимально реалистичные headers
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
    }

    # Retry логика
    max_retries = 3
    for attempt in range(max_retries):
        try:
            logger.info(f"[Requests] Попытка {attempt + 1}/{max_retries}: {url}")

            # Случайная задержка для имитации человека
            if attempt > 0:
                delay = random.uniform(2, 5)
                logger.info(f"[Requests] Ожидание {delay:.1f} сек...")
                time.sleep(delay)

            # Создаем сессию для cookies
            session = requests.Session()

            # Первый запрос для получения cookies
            response = session.get(
                url,
                headers=headers,
                timeout=30,
                allow_redirects=True,
                verify=True
            )

            # Проверка статуса
            if response.status_code == 200:
                logger.info(f"[Requests] Успешно загружено: {len(response.text)} байт")
                return response.text
            elif response.status_code == 403:
                logger.warning(f"[Requests] 403 Forbidden, попытка {attempt + 1}")
                continue
            elif response.status_code == 405:
                logger.warning(f"[Requests] 405 Method Not Allowed, попытка {attempt + 1}")
                # Пробуем добавить Referer
                headers['Referer'] = 'https://www.boataround.com/'
                continue
            elif response.status_code == 429:
                logger.warning("[Requests] 429 Too Many Requests, ждем...")
                time.sleep(10)
                continue
            else:
                logger.error(f"[Requests] Статус {response.status_code}")
                response.raise_for_status()

        except requests.exceptions.Timeout:
            logger.error(f"[Requests] Timeout на попытке {attempt + 1}")
            continue
        except requests.exceptions.ConnectionError as e:
            logger.error(f"[Requests] Connection error: {e}")
            continue
        except requests.exceptions.RequestException as e:
            logger.error(f"[Requests] Request error: {e}")
            continue
        except Exception as e:
            logger.error(f"[Requests] Неожиданная ошибка: {e}")
            continue

    logger.error(f"[Requests] Не удалось загрузить после {max_retries} попыток")
    return None


# =============================================================================
# ИЗВЛЕЧЕНИЕ ИЗОБРАЖЕНИЙ
# =============================================================================

def _normalize_picture_path(value: str) -> Optional[str]:
    """
    Нормализует любое представление картинки к виду:
    boats/{boat_id}/{filename}.{ext}
    """
    if not value:
        return None

    from urllib.parse import urlparse

    raw = unescape(str(value)).replace('\\/', '/').strip().strip('"').strip("'")
    if not raw:
        return None

    if raw.startswith('//'):
        raw = f'https:{raw}'

    path = raw
    if '://' in raw:
        parsed = urlparse(raw)
        path = (parsed.path or '').lstrip('/')
        if parsed.netloc == 'cdn2.prvms.ru' and path.startswith('yachts/'):
            path = f"boats/{path[len('yachts/'):]}"

    path = path.split('?', 1)[0].split('#', 1)[0].lstrip('/')
    if '/boats/' in path:
        path = path[path.find('boats/'):]
    if path.startswith('yachts/'):
        path = f"boats/{path[len('yachts/'):]}"

    if not NORMALIZED_PICTURE_PATH_PATTERN.match(path):
        return None

    return path


def _extract_pictures_from_gallery_component(soup: BeautifulSoup) -> list:
    """Извлекает изображения из компонентов с атрибутами :gallery/:images."""
    pics = []
    seen = set()

    components = [
        tag for tag in soup.find_all(True)
        if tag.has_attr(':gallery') or tag.has_attr(':images')
    ]
    if not components:
        logger.warning("Компоненты с атрибутами :gallery/:images не найдены")
        return pics

    def _push(candidate):
        normalized = _normalize_picture_path(candidate)
        if normalized and normalized not in seen:
            seen.add(normalized)
            pics.append(normalized)

    for component in components:
        for attr_name in (':gallery', ':images'):
            payload = component.get(attr_name)
            if not payload:
                continue
            try:
                data = json.loads(unescape(payload))
            except Exception as e:
                logger.warning(f"Ошибка парсинга JSON в {component.name}{attr_name}: {e}")
                continue

            if isinstance(data, dict):
                for key in ('images', 'gallery', 'data'):
                    if isinstance(data.get(key), list):
                        data = data[key]
                        break

            if not isinstance(data, list):
                continue

            for item in data:
                if isinstance(item, dict):
                    for field in ('path', 'url', 'src', 'main_img', 'thumb'):
                        _push(item.get(field))
                elif isinstance(item, str):
                    _push(item)

    logger.info(f"Извлечено {len(pics)} фото из gallery-mobile")

    return pics


def _extract_pictures_fallback(html_content: str) -> list:
    """Запасной метод — regex."""
    pics = []
    seen = set()
    pattern = re.compile(
        r'boats/([^/"\'\s]+)/([^"\'\s?]+?\.(?:jpg|jpeg|png|webp))',
        re.IGNORECASE,
    )

    for match in pattern.finditer(html_content):
        folder_id = match.group(1)
        filename = match.group(2)
        normalized = _normalize_picture_path(f"boats/{folder_id}/{filename}")
        if normalized and normalized not in seen:
            seen.add(normalized)
            pics.append(normalized)

    return pics


def extract_pictures(html_content: str, soup: BeautifulSoup = None) -> list:
    """Извлекает все изображения яхты."""
    if soup is None:
        soup = BeautifulSoup(html_content, 'html.parser')

    primary = _extract_pictures_from_gallery_component(soup)
    fallback = _extract_pictures_fallback(html_content)

    if not primary and fallback:
        logger.warning("Используем fallback для фото")

    result = []
    seen = set()
    for path in primary + fallback:
        if path not in seen:
            seen.add(path)
            result.append(path)

    return result


# =============================================================================
# ИЗВЛЕЧЕНИЕ УСЛУГ И РАСХОДОВ (extras)
# =============================================================================

def _extract_extras_from_component(soup: BeautifulSoup) -> list:
    """Извлекает услуги из компонента <extras-list :extras='[...]'>"""
    extras = []

    extras_list = soup.find('extras-list')
    if not extras_list:
        logger.warning("Компонент extras-list не найден")
        return extras

    extras_json = extras_list.get(':extras')
    if extras_json:
        try:
            extras_data = json.loads(extras_json)
            for item in extras_data:
                extra = {
                    'id': item.get('id', ''),
                    'name': item.get('name', ''),
                    'slug': item.get('slug', ''),
                    'additional_info': item.get('additional_info', ''),
                    'unit': item.get('unit', ''),
                    'price': (
                        item.get('price', {}).get('amount', 0)
                        if isinstance(item.get('price'), dict)
                        else item.get('price', 0)
                    ),
                    'price_nice': (
                        item.get('price', {}).get('nice', '')
                        if isinstance(item.get('price'), dict)
                        else ''
                    ),
                    'currency': (
                        item.get('price', {}).get('currency', 'EUR')
                        if isinstance(item.get('price'), dict)
                        else 'EUR'
                    ),
                    'deposit': (
                        item.get('deposit', {}).get('amount', 0)
                        if isinstance(item.get('deposit'), dict)
                        else 0
                    ),
                    'mandatory': item.get('mandatory', False),
                    'pay_when': item.get('pay_when', ''),
                    'insurance': item.get('insurance', False),
                    'amount_with_label': item.get('amount_with_label', ''),
                }
                extras.append(extra)
            logger.info(f"Извлечено {len(extras)} услуг из :extras")
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга :extras JSON: {e}")

    return extras


def _extract_additional_services_from_component(soup: BeautifulSoup) -> list:
    """Извлекает дополнительные услуги из :additional-services"""
    services = []

    extras_list = soup.find('extras-list')
    if not extras_list:
        return services

    services_json = extras_list.get(':additional-services')
    if services_json:
        try:
            services_data = json.loads(services_json)
            for item in services_data:
                service = {
                    'name': item.get('name', ''),
                    'slug': item.get('slug', ''),
                    'amount_with_unit': item.get('amountWithUnit', ''),
                    'amount': item.get('amount', 0),
                    'amount_type': item.get('amountType', ''),
                    'disclaimer': item.get('disclaimer', ''),
                    'badge': item.get('badge', ''),
                    'unit': item.get('unit', ''),
                }
                services.append(service)
            logger.info(f"Извлечено {len(services)} дополнительных услуг")
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга :additional-services JSON: {e}")

    return services


def _extract_delivery_extras(soup: BeautifulSoup) -> list:
    """Извлекает услуги доставки из :extras-delivery"""
    delivery = []

    extras_list = soup.find('extras-list')
    if not extras_list:
        return delivery

    delivery_json = extras_list.get(':extras-delivery')
    if delivery_json:
        try:
            delivery_data = json.loads(delivery_json)
            for item in delivery_data:
                d = {
                    'name': item.get('name', ''),
                    'additional_info': item.get('additional_info', ''),
                    'unit': item.get('unit', ''),
                    'price': (
                        item.get('price', {}).get('amount', 0)
                        if isinstance(item.get('price'), dict)
                        else item.get('price', 0)
                    ),
                }
                delivery.append(d)
            logger.info(f"Извлечено {len(delivery)} услуг доставки")
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга :extras-delivery JSON: {e}")

    return delivery


# =============================================================================
# ИЗВЛЕЧЕНИЕ "НЕ ВКЛЮЧЕНО В ЦЕНУ"
# =============================================================================

def _extract_not_included(soup: BeautifulSoup) -> list:
    """Извлекает информацию из секции "Не включено в цену" """
    not_included = []

    all_extras_lists = soup.find_all('div', class_='extras-list')

    for block in all_extras_lists:
        classes = block.get('class', [])

        if 'excluded' in classes:
            items = block.find_all('div', class_='extra-item')

            for item in items:
                heading = item.find('li', class_='extra-item__heading')
                price_div = item.find('div', class_='extra-item__price')
                type_span = item.find('span', class_=re.compile(r'extra-item__type--'))
                desc = item.find('div', class_='extra-item__description')

                entry = {
                    'name': heading.get_text(strip=True) if heading else '',
                    'price': price_div.get_text(strip=True) if price_div else '',
                    'option': type_span.get_text(strip=True) if type_span else '',
                    'description': desc.get_text(strip=True) if desc else '',
                }

                if entry['name']:
                    not_included.append(entry)

    logger.info(f"Извлечено {len(not_included)} позиций 'Не включено в цену'")
    return not_included


# =============================================================================
# ЛОКАЛИЗАЦИЯ: URL И ТЕКСТОВЫЕ ПОЛЯ ДЛЯ РАЗНЫХ ЯЗЫКОВ
# =============================================================================

# =============================================================================
# ЛОКАЛИЗАЦИЯ: EXTRAS, SERVICES И ПРОЧИЕ УСЛУГИ ДЛЯ РАЗНЫХ ЯЗЫКОВ
# =============================================================================


def get_boat_url_for_language(slug: str, lang: str) -> str:
    """
    Возвращает URL лодки для конкретного языка

    Args:
        slug: Slug лодки
        lang: Код языка (ru_RU, en_EN, de_DE, fr_FR, es_ES)

    Returns:
        str: URL типа https://www.boataround.com/{locale}/yacht-type/{slug}/
    """
    # Маппинг языков на локали и типы яхт
    LANGUAGE_MAPPING = {
        'ru_RU': ('ru', 'yachta'),      # Русский
        'en_EN': ('us', 'boat'),         # Английский (США)
        'de_DE': ('de', 'boot'),         # Немецкий
        'fr_FR': ('fr', 'bateau'),       # Французский
        'es_ES': ('es', 'bote'),         # Испанский
    }

    locale, boat_type = LANGUAGE_MAPPING.get(lang, ('ru', 'yachta'))  # По умолчанию русский
    return f"https://www.boataround.com/{locale}/{boat_type}/{slug}/"


# =============================================================================
# ИЗВЛЕЧЕНИЕ ОБОРУДОВАНИЯ (Cockpit, Entertainment, Equipment)
# =============================================================================

def _extract_amenities_from_html(soup) -> dict:
    """Extracts cockpit/entertainment/equipment from <amenities> Vue component.
    Only returns items where is_present=True."""
    result = {'cockpit': [], 'entertainment': [], 'equipment': []}
    amenities_tag = soup.find('amenities')
    if not amenities_tag:
        logger.debug('[parser] <amenities> component not found in HTML')
        return result
    for key in ['cockpit', 'entertainment', 'equipment']:
        attr_val = amenities_tag.get(f':{key}')
        if not attr_val:
            continue
        try:
            items = json.loads(attr_val)
            result[key] = [
                {'name': item['name']}
                for item in items
                if item.get('is_present') and item.get('name')
            ]
            logger.debug(f'[parser] amenities {key}: {len(result[key])} present of {len(items)}')
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f'[parser] Failed to parse amenities :{key}: {e}')
    return result


def _fetch_language_page_data(slug: str, lang: str) -> dict:
    """
    Загружает HTML-страницу лодки для одного языка ОДИН РАЗ и извлекает:
    - descriptions: title, description, location, marina
    - services: extras, additional_services, delivery_extras, not_included
    - amenities: cockpit, entertainment, equipment (только is_present=True)
    """
    empty = {
        'descriptions': {'title': '', 'description': '', 'location': '', 'marina': '', 'country': ''},
        'services': {'extras': [], 'additional_services': [], 'delivery_extras': [], 'not_included': []},
        'amenities': {'cockpit': [], 'entertainment': [], 'equipment': []},
        '_fetch_ok': False,
    }
    try:
        url = get_boat_url_for_language(slug, lang)
        url = add_currency_param(url, 'EUR')
        logger.info(f'[parser] 🌐 Загружаем страницу {lang}: {url}')
        html_content = fetch_page(url)
        if not html_content:
            logger.warning(f'[parser] Не удалось загрузить страницу {lang}')
            return empty

        soup = BeautifulSoup(html_content, 'html.parser')

        # --- Описания ---
        descriptions = {'title': '', 'description': '', 'location': '', 'marina': '', 'country': ''}
        for script in soup.find_all('script', {'type': 'application/ld+json'}):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    if '@graph' in data:
                        for item in data.get('@graph', []):
                            if isinstance(item, dict) and item.get('@type') == 'Product':
                                descriptions['title'] = item.get('name', '')
                                descriptions['description'] = item.get('description', '')
                                break
                    elif data.get('@type') == 'Product':
                        descriptions['title'] = data.get('name', '')
                        descriptions['description'] = data.get('description', '')
                if descriptions['title']:
                    break
            except (json.JSONDecodeError, TypeError):
                continue
        add_to_wishlist = soup.find('add-to-wishlist')
        if add_to_wishlist:
            descriptions['marina'] = add_to_wishlist.get('marina', '') or ''
            descriptions['location'] = add_to_wishlist.get('region', '') or ''
        # Дополняем из payment_box (mobile или desktop)
        payment_box = soup.find('mobile-payment-box') or soup.find('reservation-box')
        if payment_box:
            if not descriptions['location']:
                descriptions['location'] = payment_box.get('region', '') or ''
            descriptions['country'] = payment_box.get('country', '') or ''

        # --- Услуги ---
        services = {
            'extras': _extract_extras_from_component(soup),
            'additional_services': _extract_additional_services_from_component(soup),
            'delivery_extras': _extract_delivery_extras(soup),
            'not_included': _extract_not_included(soup),
        }

        # --- Оборудование (только is_present=True) ---
        amenities = _extract_amenities_from_html(soup)

        logger.info(
            f'[parser] ✅ {lang}: title="{descriptions["title"][:40]}", '
            f'extras={len(services["extras"])}, '
            f'cockpit={len(amenities["cockpit"])}, entertainment={len(amenities["entertainment"])}, '
            f'equipment={len(amenities["equipment"])}'
        )
        return {
            'descriptions': descriptions,
            'services': services,
            'amenities': amenities,
            '_fetch_ok': True,
        }

    except Exception as e:
        import traceback
        logger.error(f'[parser] Ошибка загрузки {lang} для {slug}: {e}\n{traceback.format_exc()}')
        return empty


def _fetch_all_languages_data(slug: str, languages: list) -> dict:
    """
    Загружает данные лодки для всех языков. Каждая страница тянется ровно ОДИН РАЗ.
    Возвращает: {lang: {'descriptions': {...}, 'services': {...}, 'amenities': {...}}}
    """
    return {lang: _fetch_language_page_data(slug, lang) for lang in languages}


def _extract_equipment_section(soup: BeautifulSoup, section_key: str) -> list:
    """Извлекает оборудование из vue компонента (cockpit, entertainment, equipment)"""
    items = []

    extras_list = soup.find('extras-list')
    if not extras_list:
        return items

    # Ищем атрибут :cockpit, :entertainment или :equipment
    attr_name = f':{section_key}'
    section_json = extras_list.get(attr_name)

    if section_json:
        try:
            section_data = json.loads(section_json)
            for item in section_data:
                entry = {
                    'name': item.get('name', ''),
                    'slug': item.get('slug', ''),
                    'additional_info': item.get('additional_info', ''),
                    'unit': item.get('unit', ''),
                    'price': (
                        item.get('price', {}).get('amount', 0)
                        if isinstance(item.get('price'), dict)
                        else item.get('price', 0)
                    ),
                    'price_nice': (
                        item.get('price', {}).get('nice', '')
                        if isinstance(item.get('price'), dict)
                        else ''
                    ),
                    'currency': (
                        item.get('price', {}).get('currency', 'EUR')
                        if isinstance(item.get('price'), dict)
                        else 'EUR'
                    ),
                    'mandatory': item.get('mandatory', False),
                    'pay_when': item.get('pay_when', ''),
                }
                if entry['name']:
                    items.append(entry)
            logger.info(f"Извлечено {len(items)} элементов из {section_key}")
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга :{section_key} JSON: {e}")
    else:
        logger.debug(f"Атрибут :{section_key} не найден в extras-list")

    return items


# =============================================================================
# ИЗВЛЕЧЕНИЕ ЦЕН
# =============================================================================

def _extract_prices(soup: BeautifulSoup, html_content: str) -> dict:
    """Извлекает все варианты цен."""
    prices = {
        'low_price': None,
        'currency': 'EUR',
        'min_price': None,
        'total_price': None,
        'old_price': None,
        'discount': None,
    }

    # Метод 1: Из компонента mobile-payment-box
    payment_box = soup.find('mobile-payment-box')
    if payment_box:
        price_attr = payment_box.get(':price')
        if price_attr and price_attr != 'price':
            try:
                prices['min_price'] = int(price_attr)
                prices['total_price'] = int(price_attr)
                logger.info(f"Цена из :price: {prices['total_price']}")
            except (ValueError, TypeError):
                pass

        old_price_attr = payment_box.get(':old-price')
        if old_price_attr and old_price_attr != 'oldPrice':
            try:
                prices['old_price'] = int(old_price_attr)
                logger.info(f"Старая цена из :old-price: {prices['old_price']}")
            except (ValueError, TypeError):
                pass

        discount_attr = payment_box.get(':discount')
        if discount_attr and discount_attr != 'discount':
            try:
                prices['discount'] = int(discount_attr)
                logger.info(f"Скидка из :discount: {prices['discount']}")
            except (ValueError, TypeError):
                pass

    # Метод 2: Из текста HTML (regex)
    if not prices['total_price']:
        # Ищем цены вида "1 234 €" или "1234€"
        price_patterns = [
            r'total["\']?\s*:\s*["\']?(\d+)',
            r'price["\']?\s*:\s*["\']?(\d+)',
            r'(\d[\d\s]{2,})\s*€',
            r'€\s*(\d[\d\s]{2,})',
        ]

        for pattern in price_patterns:
            matches = re.findall(pattern, html_content)
            if matches:
                try:
                    # Берем первое совпадение и убираем пробелы
                    price_str = matches[0].replace(' ', '').replace(',', '')
                    price = int(price_str)
                    if 100 < price < 100000:  # Разумные границы
                        prices['total_price'] = price
                        prices['min_price'] = price
                        logger.info(f"Цена из regex: {price}")
                        break
                except (ValueError, IndexError):
                    continue

    # Метод 3: Из JSON в HTML
    if not prices['total_price']:
        # Ищем JSON-блоки с ценами
        json_pattern = r'price["\']?\s*:\s*["\']?(\d+)'
        matches = re.findall(json_pattern, html_content)
        if matches:
            try:
                price = int(matches[0])
                if 100 < price < 100000:
                    prices['total_price'] = price
                    prices['min_price'] = price
                    logger.info(f"Цена из JSON: {price}")
            except (ValueError, IndexError):
                pass

    # Если нет цены - ошибка
    if not prices['total_price']:
        logger.warning("⚠️ Цена не найдена!")

    return prices


# =============================================================================
# ИЗВЛЕЧЕНИЕ БАЗОВОЙ ИНФОРМАЦИИ О ЯХТЕ
# =============================================================================

def _extract_boat_info(soup: BeautifulSoup, html_content: str) -> dict:
    """Извлекает базовую информацию о яхте."""
    info = {
        'title': '',
        'manufacturer': '',
        'model': '',
        'year': '',
        'cabins': '',
        'toilets': '',
        'people': '',
        'length': '',
        'location': '',
        'marina': '',
        'country': '',
        'description': '',
        # Технические параметры
        'beam': '',
        'draft': '',
        'engine_type': '',
        'fuel': '',
        'maximum_speed': '',
        'cruising_consumption': '',
        'renovated_year': '',
        'sail_renovated_year': '',
        'max_sleeps': '',
        'max_people': '',
        'single_cabins': '',
        'double_cabins': '',
        'triple_cabins': '',
        'quadruple_cabins': '',
        'cabins_with_bunk_bed': '',
        'saloon_sleeps': '',
        'crew_sleeps': '',
        'electric_toilets': '',
    }

    # Попробуем извлечь из JSON-LD (schema.org)
    script_tags = soup.find_all('script', {'type': 'application/ld+json'})
    logger.info(f"[parser] Found {len(script_tags)} JSON-LD scripts")

    for script_idx, script in enumerate(script_tags):
        try:
            data = json.loads(script.string)

            # Проверяем структуру данных
            if isinstance(data, list):
                logger.info(f"[parser] Script {script_idx}: list with {len(data)} items")
                for item_idx, item in enumerate(data):
                    if isinstance(item, dict):
                        item_type = item.get('@type', 'unknown')
                        logger.info(f"[parser] Script {script_idx} Item {item_idx}: @type={item_type}")
                        if item.get('@type') == 'Product':
                            info['title'] = item.get('name', info['title'])
                            info['description'] = item.get('description', info['description'])
                            manufacturer = item.get('manufacturer')
                            brand = item.get('brand')
                            if isinstance(manufacturer, dict):
                                info['manufacturer'] = manufacturer.get('name', info['manufacturer'])
                            elif isinstance(brand, dict):
                                info['manufacturer'] = brand.get('name', info['manufacturer'])
                            info['model'] = item.get('model', info['model'])
                            # Извлекаем технические параметры если есть
                            info['beam'] = item.get('beam', info['beam']) or ''
                            info['draft'] = item.get('draft', info['draft']) or ''
                            logger.info(f"[parser] ✅ Extracted from schema.org: title='{info['title']}'")
                            break

            elif isinstance(data, dict):
                data_type = data.get('@type', 'unknown')
                logger.info(f"[parser] Script {script_idx}: dict @type={data_type}")

                # Если это @graph, ищем Product внутри
                if data.get('@context') == 'https://schema.org' or '@graph' in data:
                    items = data.get('@graph', [data])
                    if not isinstance(items, list):
                        items = [items]
                    logger.info(f"[parser] Searching in graph: {len(items)} items")
                    for item in items:
                        if isinstance(item, dict) and item.get('@type') == 'Product':
                            info['title'] = item.get('name', info['title'])
                            info['description'] = item.get('description', info['description'])
                            info['model'] = item.get('model', info['model'])
                            logger.info(f"[parser] ✅ Extracted from @graph Product: title='{info['title']}'")
                            break

                elif data.get('@type') == 'Product':
                    info['title'] = data.get('name', info['title'])
                    info['description'] = data.get('description', info['description'])
                    manufacturer = data.get('manufacturer')
                    brand = data.get('brand')
                    if isinstance(manufacturer, dict):
                        info['manufacturer'] = manufacturer.get('name', info['manufacturer'])
                    elif isinstance(brand, dict):
                        info['manufacturer'] = brand.get('name', info['manufacturer'])
                    info['model'] = data.get('model', info['model'])
                    logger.info(f"[parser] ✅ Extracted from schema.org: title='{info['title']}'")

        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            logger.warning(f"[parser] Failed to parse JSON-LD script {script_idx}: {e}")
            continue

    # Компоненты с данными о локации/параметрах яхты
    # mobile-payment-box — мобильная версия, reservation-box — десктопная
    payment_box = soup.find('mobile-payment-box') or soup.find('reservation-box')
    if payment_box:
        logger.info(f"[parser] Found {payment_box.name}")
        info['title'] = payment_box.get('boat-title', '') or payment_box.get('title', '') or info['title']
        info['year'] = payment_box.get('boat-year', '') or info['year']
        info['cabins'] = payment_box.get('boat-cabins', '') or info['cabins']
        info['people'] = payment_box.get('boat-people', '') or info['people']
        info['length'] = payment_box.get('boat-length', '') or info['length']
        info['manufacturer'] = payment_box.get('manufacturer', '') or info['manufacturer']
        info['country'] = payment_box.get('country', '') or info['country']
        info['location'] = payment_box.get('region', '') or info['location']
        # Технические параметры (только из mobile-payment-box)
        info['beam'] = payment_box.get('boat-beam', '') or info['beam']
        info['draft'] = payment_box.get('boat-draft', '') or info['draft']
        info['engine_type'] = payment_box.get('boat-engine-type', '') or info['engine_type']
        info['fuel'] = payment_box.get('boat-fuel', '') or info['fuel']
        info['maximum_speed'] = payment_box.get('boat-max-speed', '') or info['maximum_speed']
        info['toilets'] = payment_box.get('boat-toilets', '') or info['toilets']
    else:
        logger.warning("[parser] payment_box не найден (ни mobile-payment-box, ни reservation-box)!")

    # Из boat-info-list компонента (основной источник技ических параметров)
    boat_info_list = soup.find('boat-info-list')
    if boat_info_list:
        params_str = boat_info_list.get(':parameters', '{}')
        try:
            params = json.loads(params_str)
            logger.info(f"[parser] ✅ boat-info-list найден с параметрами: {list(params.keys())[:10]}")
            # Извлекаем параметры
            info['single_cabins'] = str(params.get('single_cabins', ''))
            info['double_cabins'] = str(params.get('double_cabins', ''))
            info['triple_cabins'] = str(params.get('triple_cabins', ''))
            info['quadruple_cabins'] = str(params.get('quadruple_cabins', ''))
            info['cabins_with_bunk_bed'] = str(params.get('cabins_with_bunk_bed', ''))
            info['saloon_sleeps'] = str(params.get('saloon_sleeps', ''))
            info['crew_sleeps'] = str(params.get('crew_sleeps', ''))
            info['max_sleeps'] = str(params.get('max_sleeps', ''))
            info['max_people'] = str(params.get('max_people', ''))
            info['toilets'] = str(params.get('toilets', info['toilets']))
            info['electric_toilets'] = str(params.get('electric_toilets', ''))
            info['length'] = str(params.get('length', ''))
            info['beam'] = str(params.get('beam', ''))
            info['draft'] = str(params.get('draft', ''))
            info['engine_power'] = str(params.get('engine_power', ''))
            info['number_engines'] = str(params.get('number_engines', ''))
            info['total_engine_power'] = str(params.get('total_engine_power', ''))
            info['engine'] = str(params.get('engine', ''))
            info['fuel'] = str(params.get('fuel', ''))
            info['cruising_consumption'] = str(params.get('cruising_consumption', ''))
            info['maximum_speed'] = str(params.get('maximum_speed', ''))
            info['water_tank'] = str(params.get('water_tank', ''))
            info['waste_tank'] = str(params.get('waste_tank', ''))
            info['year'] = str(params.get('year', info['year']))
            info['renovated_year'] = str(params.get('renovated_year', ''))
            info['sail_renovated_year'] = str(params.get('sail_renovated_year', ''))
            info['cabins'] = str(params.get('cabins', info['cabins']))
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"[parser] Ошибка парсинга boat-info-list params: {e}")
    else:
        logger.warning("[parser] boat-info-list не найден!")

    # Из add-to-wishlist (fallback)
    wishlist = soup.find('add-to-wishlist')
    if wishlist:
        info['marina'] = wishlist.get('marina', info['marina']) or info['marina']
        if not info['year']:
            info['year'] = wishlist.get('year', '')
        if not info['cabins']:
            info['cabins'] = wishlist.get('cabins', '')

    # FALLBACK: Если manufacturer пустой, пробуем извлечь из title
    if not info['manufacturer'] and info['title']:
        # Title обычно "Lagoon 380 S2 | Aride", manufacturer - до |
        parts = info['title'].split('|')
        if len(parts) > 0:
            potential_manufacturer = parts[0].strip()
            # Если в manufacturer есть две части (manufacturer + model), берем первую
            model_parts = potential_manufacturer.split()
            if len(model_parts) > 0:
                info['manufacturer'] = model_parts[0]  # Первое слово - производитель

    logger.info(f"[parser] Final boat_info: {info}")
    return info


def _extract_boat_id(html_content: str) -> Optional[str]:
    match = BOAT_ID_PATTERN.search(html_content)
    return match.group(1) if match else None


def _extract_boat_id_from_pictures(pictures: list) -> Optional[str]:
    """Извлекает boat_id из путей картинок вида boats/{boat_id}/{filename}."""
    for pic_path in pictures or []:
        if not isinstance(pic_path, str):
            continue
        match = BOAT_ID_FROM_PICTURE_PATTERN.match(pic_path.strip('/'))
        if match:
            return match.group(1)
    return None


def _build_fallback_boat_id(slug: str) -> str:
    """Стабильный fallback boat_id для случаев, когда источник не отдал ID."""
    digest = hashlib.sha1((slug or '').encode('utf-8')).hexdigest()[:16]
    return f"slug-{digest}"


# =============================================================================
# ОСНОВНЫЕ ФУНКЦИИ
# =============================================================================

def parse_boataround_url(url: str, save_to_db: bool = True) -> Optional[dict]:
    """
    Парсит URL с boataround.com и возвращает данные о лодке.
    Главная функция для Django.

    Args:
        url: URL с boataround.com
        save_to_db: Сохранить в ParsedBoat

    Returns:
        dict: Полные данные о лодке
    """
    from urllib.parse import urlparse, parse_qs

    # ⭐ ГЛАВНОЕ: Добавляем параметр currency=EUR чтобы получить цены в евро
    url = add_currency_param(url, 'EUR')

    # Извлекаем параметры из URL
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)

    check_in = query_params.get('checkIn', [''])[0]
    check_out = query_params.get('checkOut', [''])[0]

    # Извлекаем slug
    match = SLUG_FROM_URL_PATTERN.search(url)
    slug = match.group(1) if match else 'unknown'

    # Загружаем страницу
    html_content = fetch_page(url)
    if not html_content:
        return None

    soup = BeautifulSoup(html_content, 'html.parser')

    # Извлекаем данные
    boat_id = _extract_boat_id(html_content)
    pics = extract_pictures(html_content, soup)
    if not boat_id:
        boat_id = _extract_boat_id_from_pictures(pics)
    boat_info = _extract_boat_info(soup, html_content)
    prices = _extract_prices(soup, html_content)
    extras = _extract_extras_from_component(soup)
    additional_services = _extract_additional_services_from_component(soup)
    delivery_extras = _extract_delivery_extras(soup)
    not_included = _extract_not_included(soup)

    # ⭐ Загружаем страницу каждого языка ОДИН РАЗ и извлекаем все данные
    SUPPORTED_LANGUAGES = ['ru_RU', 'en_EN', 'de_DE', 'fr_FR', 'es_ES']
    all_lang_data = _fetch_all_languages_data(slug, SUPPORTED_LANGUAGES)

    # Оборудование русской версии для основного результата
    ru_amenities = all_lang_data.get('ru_RU', {}).get('amenities', {})
    cockpit = ru_amenities.get('cockpit', [])
    entertainment = ru_amenities.get('entertainment', [])
    equipment = ru_amenities.get('equipment', [])

    # Скачиваем фото (первые 20)
    pics_to_download = pics[:20]
    downloaded_pics = []

    logger.info(f"Начинаем скачивание {len(pics_to_download)} фото...")
    for pic_path in pics_to_download:
        saved_path = download_and_save_image(pic_path)
        if saved_path:
            downloaded_pics.append(saved_path)

    logger.info(f"Успешно скачано {len(downloaded_pics)}/{len(pics_to_download)} фото")
    if pics_to_download and not downloaded_pics:
        logger.error(
            f"[parser] Критическая ошибка: не удалось сохранить ни одного фото для slug={slug}. "
            "Вероятно, недоступен S3/CDN."
        )
        return None

    # Формируем результат с полной структурой
    result = {
        # Основная информация
        'url': url,
        'slug': slug,
        'boat_id': boat_id,

        # Временные рамки
        'check_in': check_in,
        'check_out': check_out,

        # Техническая информация о лодке (все параметры)
        'boat_info': boat_info,

        # Цены
        'prices': prices,

        # ГЛАВНОЕ: Фото в разных форматах для максимальной совместимости
        'pictures': downloaded_pics,      # Пути в /app/media/boats/...
        'gallery': downloaded_pics,       # Синоним для API совместимости

        # Услуги и добавления
        'extras': extras,                           # Основные услуги (сапборд, капитан и т.д.)
        'additional_services': additional_services,  # Доп услуги (гибкая отмена и т.д.)
        'delivery_extras': delivery_extras,         # Услуги доставки
        'not_included': not_included,               # Что не включено в стоимость

        # Оборудование (основной язык - русский)
        'cockpit': cockpit,                         # Оборудование кокпита
        'entertainment': entertainment,             # Развлечения
        'equipment': equipment,                     # Оборудование

    }
    # Краткое структурированное логирование результата парсинга
    try:
        price_val = prices.get('total_price') or prices.get('min_price') or prices.get('low_price') or 0
    except Exception:
        price_val = 0

    logger.info(
        f"[parser-summary] title='{boat_info.get('title', '')}', boat_id={boat_id}, "
        f"price={price_val}, images={len(downloaded_pics)}, extras={len(extras)}, "
        f"adds={len(additional_services)}, delivery={len(delivery_extras)}, not_included={len(not_included)}, "
        f"cockpit={len(cockpit)}, entertainment={len(entertainment)}, equipment={len(equipment)}"
    )

    # Сохраняем в базу
    if save_to_db and slug and slug != 'unknown':
        try:
            from boats.models import (
                ParsedBoat, BoatGallery, BoatDetails, BoatDescription
            )

            # Получаем или создаем ParsedBoat.
            # Важно: boat_id у источника может отсутствовать в HTML.
            existing_by_slug = ParsedBoat.objects.filter(slug=slug).first()
            effective_boat_id = (
                boat_id
                or (existing_by_slug.boat_id if existing_by_slug else None)
                or _build_fallback_boat_id(slug)
            )
            result['boat_id'] = effective_boat_id

            created = False
            parsed_boat = ParsedBoat.objects.filter(boat_id=effective_boat_id).first()
            if not parsed_boat:
                parsed_boat = existing_by_slug

            if (
                parsed_boat
                and parsed_boat.boat_id != effective_boat_id
                and ParsedBoat.objects.filter(boat_id=effective_boat_id).exclude(pk=parsed_boat.pk).exists()
            ):
                logger.error(
                    f"[parser] Конфликт boat_id={effective_boat_id} для slug={slug}. "
                    f"Сохраняю текущий boat_id={parsed_boat.boat_id}."
                )
                effective_boat_id = parsed_boat.boat_id
                result['boat_id'] = effective_boat_id

            if parsed_boat:
                parsed_boat.boat_id = effective_boat_id
                parsed_boat.slug = slug
                parsed_boat.manufacturer = boat_info.get('manufacturer', '')
                parsed_boat.model = boat_info.get('model', '')
                parsed_boat.year = int(boat_info.get('year', 0)) if boat_info.get('year') else None
                parsed_boat.source_url = url
                parsed_boat.save(
                    update_fields=[
                        'boat_id',
                        'slug',
                        'manufacturer',
                        'model',
                        'year',
                        'source_url',
                        'updated_at',
                    ]
                )
            else:
                parsed_boat = ParsedBoat.objects.create(
                    boat_id=effective_boat_id,
                    slug=slug,
                    manufacturer=boat_info.get('manufacturer', ''),
                    model=boat_info.get('model', ''),
                    year=int(boat_info.get('year', 0)) if boat_info.get('year') else None,
                    source_url=url,
                )
                created = True

            # Из HTML сохраняем только фото (BoatGallery)
            BoatGallery.objects.filter(boat=parsed_boat).delete()
            for idx, pic_url in enumerate(downloaded_pics, 1):
                BoatGallery.objects.create(
                    boat=parsed_boat,
                    cdn_url=pic_url,
                    order=idx
                )

            # Из HTML сохраняем сервисные списки + amenities (BoatDetails)
            # + локализованные описания (BoatDescription) — title/country/marina/location
            for language in SUPPORTED_LANGUAGES:
                lang_equipment = all_lang_data.get(language, {}).get('amenities', {})
                lang_services = all_lang_data.get(language, {}).get('services', {})
                lang_desc = all_lang_data.get(language, {}).get('descriptions', {})

                BoatDetails.objects.update_or_create(
                    boat=parsed_boat,
                    language=language,
                    defaults={
                        # Локализованные услуги для каждого языка
                        'extras': lang_services.get('extras', []),
                        'additional_services': lang_services.get('additional_services', []),
                        'delivery_extras': lang_services.get('delivery_extras', []),
                        'not_included': lang_services.get('not_included', []),
                        # Локализованное оборудование (по лодке) берём из HTML amenities
                        'cockpit': lang_equipment.get('cockpit', []),
                        'entertainment': lang_equipment.get('entertainment', []),
                        'equipment': lang_equipment.get('equipment', []),
                    }
                )

                # Сохраняем локализованные текстовые поля из HTML в BoatDescription.
                # HTML-страница каждого языка содержит country/marina/location на нужном языке.
                desc_update = {}
                if lang_desc.get('title'):
                    desc_update['title'] = lang_desc['title']
                if lang_desc.get('country'):
                    desc_update['country'] = lang_desc['country']
                if lang_desc.get('marina'):
                    desc_update['marina'] = lang_desc['marina']
                if lang_desc.get('location'):
                    desc_update['location'] = lang_desc['location']
                if lang_desc.get('description'):
                    desc_update['description'] = lang_desc['description']

                if desc_update:
                    boat_title = desc_update.get('title') or boat_info.get('title', '') or parsed_boat.slug
                    BoatDescription.objects.update_or_create(
                        boat=parsed_boat,
                        language=language,
                        defaults={
                            'title': boat_title,
                            'description': desc_update.get('description', ''),
                            'country': desc_update.get('country', ''),
                            'marina': desc_update.get('marina', ''),
                            'location': desc_update.get('location', ''),
                        }
                    )
                    logger.info(
                        f"[parser] ✅ BoatDescription обновлён для {language}: "
                        f"country='{desc_update.get('country', '')}', "
                        f"marina='{desc_update.get('marina', '')}'"
                    )
                logger.info(
                    f"[parser] ✅ BoatDetails services сохранены для {language}: "
                    f"extras={len(lang_services.get('extras', []))}, "
                    f"adds={len(lang_services.get('additional_services', []))}, "
                    f"delivery={len(lang_services.get('delivery_extras', []))}, "
                    f"not_included={len(lang_services.get('not_included', []))}, "
                    f"cockpit={len(lang_equipment.get('cockpit', []))}, "
                    f"entertainment={len(lang_equipment.get('entertainment', []))}, "
                    f"equipment={len(lang_equipment.get('equipment', []))}"
                )

            # Увеличиваем счетчик парсингов
            if not created:
                parsed_boat.parse_count += 1
                parsed_boat.save(update_fields=['parse_count'])

            action = "создан" if created else "обновлен"
            logger.info(f"ParsedBoat {action}: {slug} (ID: {effective_boat_id})")

        except Exception as e:
            import traceback
            logger.error(f"Ошибка сохранения в ParsedBoat: {e}\n{traceback.format_exc()}")

    return result


# =============================================================================
# УТИЛИТЫ
# =============================================================================

def get_full_image_url(path: str, width: int = 1920, height: int = 1080) -> str:
    """
    Формирует URL изображения для CDN.

    Args:
        path: Путь к изображению, например 'boats/62b96d157a9323583a5a4880/650d96fa43b7cac28800ead4.jpg'

    Returns:
        str: https://b1cdn.prvms.ru/static/boats/.../image.jpg
    """
    return get_cdn_url(path)


def get_thumbnail_url(path: str, size: int = 200) -> str:
    """
    Формирует URL миниатюры для CDN.

    Args:
        path: Путь к изображению

    Returns:
        str: https://b1cdn.prvms.ru/static/boats/.../image.jpg
    """
    return get_cdn_url(path)


# =============================================================================
# МИНИМАЛЬНЫЙ ПАРСЕР (только фото и extras)
# =============================================================================

def parse_boataround_url_minimal(url: str) -> Optional[dict]:
    """
    Быстрый парсер который извлекает ТОЛЬКО:
    - Фото (pictures)
    - Extras, additional_services, delivery_extras, not_included

    Не парсит технические параметры (они берутся из API).
    Предназначен для быстрого обновления фото и услуг.

    Args:
        url: URL лодки на boataround.com

    Returns:
        dict: {'pictures': [...], 'extras': [...], ...} или None
    """
    try:
        logger.info(f"[parser-minimal] Загружаем: {url}")

        headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        logger.info(f"[parser-minimal] ✅ Загружено {len(response.content)} байт")

        result = {
            'pictures': [],
            'extras': [],
            'additional_services': [],
            'delivery_extras': [],
            'not_included': [],
        }

        # 1. Извлекаем фото из boat-info-list компонента
        boat_info_list = soup.find('boat-info-list')
        if boat_info_list:
            # Ищем изображения в компоненте и скрипте
            pass  # boat-info-list не содержит фото напрямую

        # 2. Ищем gallery-mobile компонент для фото
        gallery = soup.find('gallery-mobile')
        if gallery:
            logger.info("[parser-minimal] ✅ Найден gallery-mobile")
            images_attr = gallery.get(':images', '[]')
            try:
                images = json.loads(images_attr)
                if isinstance(images, list):
                    for img in images:
                        if isinstance(img, dict):
                            # Может быть url или path
                            pic_url = img.get('url') or img.get('path')
                            if pic_url:
                                result['pictures'].append(pic_url)
                    logger.info(f"[parser-minimal] Извлечено {len(result['pictures'])} фото")
            except Exception as e:
                logger.warning(f"[parser-minimal] Ошибка парсинга gallery images: {e}")
        else:
            logger.warning("[parser-minimal] gallery-mobile не найден")

        # 3. Извлекаем extras/services из extras-list компонента
        extras_list = soup.find('extras-list')
        if extras_list:
            logger.info("[parser-minimal] ✅ Найден extras-list")

            # Парсим extras
            extras_attr = extras_list.get(':extras', '[]')
            try:
                extras = json.loads(extras_attr)
                if isinstance(extras, list):
                    result['extras'] = extras
                    logger.info(f"[parser-minimal] Извлечено {len(extras)} extras")
            except Exception as e:
                logger.warning(f"[parser-minimal] Ошибка парсинга extras: {e}")

            # Парсим additional_services
            services_attr = extras_list.get(':additional-services', '[]')
            try:
                services = json.loads(services_attr)
                if isinstance(services, list):
                    result['additional_services'] = services
                    logger.info(f"[parser-minimal] Извлечено {len(services)} additional_services")
            except Exception as e:
                logger.warning(f"[parser-minimal] Ошибка парсинга services: {e}")

            # Парсим delivery extras
            delivery_attr = extras_list.get(':extras-delivery', '[]')
            try:
                delivery = json.loads(delivery_attr)
                if isinstance(delivery, list):
                    result['delivery_extras'] = delivery
                    logger.info(f"[parser-minimal] Извлечено {len(delivery)} delivery_extras")
            except Exception as e:
                logger.warning(f"[parser-minimal] Ошибка парсинга delivery: {e}")

        # 4. Извлекаем not_included
        # Ищем в description или отдельном блоке
        not_included_section = soup.find(class_='not-included') or soup.find(text=re.compile('не включено', re.I))
        if not_included_section:
            logger.info("[parser-minimal] Найдена секция 'не включено'")
            # TODO: парсить этот блок если нужно

        logger.info(
            f"[parser-minimal] ✅ Завершено: {len(result['pictures'])} фото, "
            f"{len(result['extras'])} extras")

        return result

    except Exception as e:
        logger.error(f"[parser-minimal] ❌ Ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None
