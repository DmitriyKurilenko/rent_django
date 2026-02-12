"""
Helper функции для работы с кэшированием ParsedBoat
"""
from django.utils import timezone
from datetime import timedelta

# Константы для расчёта цены туристического оффера
INSURANCE_RATE = 0.10
INSURANCE_MIN = 400
TURKEY_BASE_PRICE = 4400
SEYCHELLES_BASE_PRICE = 4500
DEFAULT_BASE_PRICE = 4500
PRASLIN_EXTRA = 400
LENGTH_EXTRA = 200
COOK_PRICE = 1400
TURKEY_DISH_BASE = 150
SEYCHELLES_DISH_BASE = 210
DEFAULT_DISH_BASE = 210
MAX_DOUBLE_CABINS_FREE = 4
DOUBLE_CABIN_EXTRA = 200
CATAMARAN_LENGTH_EXTRA = 500
SAILING_LENGTH_EXTRA = 300

# Названия стран для проверок
TURKEY_NAMES = ('turkey', 'турция')
SEYCHELLES_NAMES = ('seychelles', 'сейшелы')


def apply_charter_commission(price, charter):
    """
    Применить комиссию чартерной компании к цене
    
    Args:
        price: Базовая цена (float или int)
        charter: Charter instance или None
        
    Returns:
        float: Цена с учетом комиссии
    """
    if not charter or not price:
        return float(price) if price else 0
    
    commission_rate = float(charter.commission) if charter.commission else 0
    
    if commission_rate == 0:
        return float(price)
    
    # Добавляем комиссию к цене: price * (1 + commission/100)
    final_price = float(price) * (1 + commission_rate / 100)
    
    return final_price


def calculate_final_price_with_discounts(base_price, discount_without_extra, additional_discount, charter=None):
    """
    Рассчитать финальную цену с учетом всех скидок и комиссии чартера
    
    Логика:
    1. Применяем discount_without_additionalExtra
    2. Применяем additional_discount
    3. Если additional_discount < commission чартера: применяем дополнительную скидку 5% (но не более commission)
    4. НЕ добавляем комиссию чартера к цене (она используется только для условия)
    
    Args:
        base_price: Базовая цена (float)
        discount_without_extra: Скидка без дополнительных бонусов (%)
        additional_discount: Дополнительная скидка (%)
        charter: Charter instance или None
        
    Returns:
        float: Финальная цена
    """
    if not base_price:
        return 0
    
    price = float(base_price)
    
    # 1. Применяем discount_without_additionalExtra
    if discount_without_extra:
        price = price * (1 - float(discount_without_extra) / 100)
    
    # 2. Применяем additional_discount
    if additional_discount:
        price = price * (1 - float(additional_discount) / 100)
    
    # 3. Условная дополнительная скидка
    if charter and charter.commission:
        commission = float(charter.commission)
        additional_discount_val = float(additional_discount) if additional_discount else 0
        
        # Если additional_discount < commission: применяем ещё 5% (но не более commission)
        if additional_discount_val < commission:
            extra_discount = min(5, commission)
            price = price * (1 - extra_discount / 100)
    
    return price


def get_boat_from_cache(boat_id=None, slug=None):
    """
    Получить лодку из кэша по boat_id или slug
    
    Returns:
        ParsedBoat или None
    """
    from boats.models import ParsedBoat
    
    try:
        if boat_id:
            return ParsedBoat.objects.get(boat_id=boat_id)
        elif slug:
            return ParsedBoat.objects.get(slug=slug)
    except ParsedBoat.DoesNotExist:
        return None
    
    return None


def get_or_create_charter(charter_name, charter_id=None, charter_logo=None):
    """
    Получить или создать чартерную компанию
    
    Args:
        charter_name: Название чартера
        charter_id: ID чартера (опционально)
        charter_logo: Путь к логотипу (опционально)
        
    Returns:
        Charter instance или None
    """
    from boats.models import Charter
    
    # Поддерживаем разные форматы из API: строка или объект
    if isinstance(charter_name, dict):
        charter_data = charter_name
        charter_name = (
            charter_data.get('name')
            or charter_data.get('title')
            or charter_data.get('company')
            or ''
        )
        charter_id = charter_id or charter_data.get('_id') or charter_data.get('id')
        charter_logo = (
            charter_logo
            or charter_data.get('logo')
            or charter_data.get('logo_url')
            or charter_data.get('image')
        )

    if not charter_name:
        return None

    # Гарантируем строковый тип
    charter_name = str(charter_name).strip()
    if not charter_name:
        return None
    
    # Используем charter_name как charter_id если ID не указан
    if not charter_id:
        charter_id = charter_name.lower().replace(' ', '-')
    else:
        charter_id = str(charter_id).strip()
    
    charter, created = Charter.objects.get_or_create(
        charter_id=charter_id,
        defaults={
            'name': charter_name,
            'logo': charter_logo or '',
            'commission': 20,  # По умолчанию 20%
        }
    )
    
    # Обновляем логотип если он изменился
    if not created and charter_logo and charter.logo != charter_logo:
        charter.logo = charter_logo
        charter.save(update_fields=['logo'])
    
    return charter


def is_cache_fresh(parsed_boat, max_age_hours=24):
    """
    Проверить, свежий ли кэш
    
    Args:
        parsed_boat: ParsedBoat instance
        max_age_hours: Максимальный возраст кэша в часах
        
    Returns:
        bool: True если кэш свежий
    """
    if not parsed_boat:
        return False
    
    age = timezone.now() - parsed_boat.last_parsed
    return age < timedelta(hours=max_age_hours)


def save_to_cache(boat_data, boat_id, slug):
    """
    Сохранить данные лодки в кэш
    
    Args:
        boat_data: dict с данными лодки
        boat_id: ID лодки
        slug: slug лодки
        
    Returns:
        ParsedBoat instance
    """
    from boats.models import ParsedBoat
    
    # Извлекаем базовую информацию для быстрого поиска
    boat_info = boat_data.get('boat_info', {})
    
    # Извлекаем информацию о чартере
    charter_name = boat_data.get('charter') or boat_info.get('charter')
    charter_logo = boat_data.get('charter_logo') or boat_info.get('charter_logo')
    charter_id_raw = boat_data.get('charter_id') or boat_info.get('charter_id')

    # Если charter пришёл объектом, извлекаем из него поля
    if isinstance(charter_name, dict):
        charter_data = charter_name
        charter_name = (
            charter_data.get('name')
            or charter_data.get('title')
            or charter_data.get('company')
            or ''
        )
        charter_logo = (
            charter_logo
            or charter_data.get('logo')
            or charter_data.get('logo_url')
            or charter_data.get('image')
            or ''
        )
        charter_id_raw = charter_id_raw or charter_data.get('_id') or charter_data.get('id')
    
    # Создаем/получаем чартера если есть данные
    charter = None
    if charter_name:
        charter = get_or_create_charter(charter_name, charter_id_raw, charter_logo)
    
    # Проверяем существующий parse_count
    existing = ParsedBoat.objects.filter(boat_id=boat_id).first()
    if not existing and slug:
        existing = ParsedBoat.objects.filter(slug=slug).first()

    # Не затираем существующую связь с чартером, если в текущем payload нет данных чартера
    charter_to_save = charter or (existing.charter if existing else None)

    new_parse_count = (existing.parse_count + 1) if existing else 1
    
    parsed_boat, created = ParsedBoat.objects.update_or_create(
        boat_id=boat_id,
        defaults={
            'slug': slug,
            'boat_data': boat_data,
            'charter': charter_to_save,
            'title': boat_info.get('title', ''),
            'location': boat_info.get('location', ''),
            'manufacturer': boat_info.get('manufacturer', ''),
            'year': boat_info.get('year', ''),
            'last_parsed': timezone.now(),
            'parse_count': new_parse_count,
            'last_parse_success': True,
        }
    )
    
    return parsed_boat


def get_boat_data_from_cache_or_parse(url, boat_id=None, slug=None, force_refresh=False, max_cache_age_hours=24):
    """
    Получить данные лодки из кэша или спарсить
    
    Args:
        url: URL для парсинга
        boat_id: ID лодки (опционально)
        slug: slug лодки (опционально)
        force_refresh: bool - игнорировать кэш
        max_cache_age_hours: int - максимальный возраст кэша
        
    Returns:
        dict: boat_data с флагом from_cache
    """
    from boats.parser import parse_boataround_url
    
    # Попытка получить из кэша
    if not force_refresh:
        if boat_id:
            cached = get_boat_from_cache(boat_id=boat_id)
        elif slug:
            cached = get_boat_from_cache(slug=slug)
        else:
            cached = None
        
        if cached and is_cache_fresh(cached, max_cache_age_hours):
            boat_data = cached.boat_data.copy()
            boat_data['from_cache'] = True
            return boat_data
    
    # Парсим заново
    boat_data = parse_boataround_url(url, save_to_db=False)
    
    if boat_data:
        # Извлекаем boat_id и slug из URL
        if not boat_id or not slug:
            from urllib.parse import urlparse
            path = urlparse(url).path
            parts = path.strip('/').split('/')
            if not slug and len(parts) > 0:
                slug = parts[-1]
            if not boat_id:
                boat_id = slug  # Используем slug как boat_id
        
        # Сохраняем в кэш
        save_to_cache(boat_data, boat_id, slug)
        boat_data['from_cache'] = False
    
    return boat_data


def get_offer_boat_data(slug):
    """
    Получить данные о лодке для оффера из новой структуры.
    
    Args:
        slug: Slug лодки
        
    Returns:
        dict: Комбинированные данные о лодке для отображения
    """
    from boats.boataround_api import BoataroundAPI
    
    boat_data = BoataroundAPI.get_boat_combined_data(slug)
    return boat_data or {}


# Ценовые константы для расчёта
INSURANCE_MIN = 400
INSURANCE_RATE = 0.10
COOK_PRICE = 1400
TURKEY_BASE_PRICE = 4400
SEYCHELLES_BASE_PRICE = 4500
DEFAULT_BASE_PRICE = 4500
TURKEY_DISH_BASE = 150
SEYCHELLES_DISH_BASE = 210
DEFAULT_DISH_BASE = 210
PRASLIN_EXTRA = 400
LENGTH_EXTRA = 200
CATAMARAN_LENGTH_EXTRA = 500
SAILING_LENGTH_EXTRA = 300
DOUBLE_CABIN_EXTRA = 180
MAX_DOUBLE_CABINS_FREE = 4

TURKEY_NAMES = ['turkey', 'турция']
SEYCHELLES_NAMES = ['seychelles', 'сейшелы']


def calculate_tourist_price(boat_data, check_in=None, check_out=None, dish=False, discount=0):
    """
    Расчёт итоговой цены для туристического оффера (полная логика как в старом коде)
    
    Args:
        boat_data: dict с данными лодки
        check_in: дата заезда (не используется в расчёте, только для информации)
        check_out: дата выезда (не используется в расчёте, только для информации)
        dish: bool - включено ли питание
        discount: float - дополнительная скидка/наценка
        
    Returns:
        dict: {'total_price': float, 'original_price': float, 'discount': float, 'nights': int}
    """
    from datetime import datetime
    
    # Берём базовую цену из API
    total_price = float(boat_data.get('totalPrice') or boat_data.get('price') or 0)
    if not total_price:
        return {'total_price': 0, 'original_price': 0, 'discount': 0, 'nights': 1}
    
    full_price = float(boat_data.get('price') or 0)
    boat_discount = float(boat_data.get('discount', 0) or 0)
    
    # Количество ночей
    nights = 1
    if check_in and check_out:
        try:
            if isinstance(check_in, str):
                check_in = datetime.strptime(check_in, '%Y-%m-%d')
            if isinstance(check_out, str):
                check_out = datetime.strptime(check_out, '%Y-%m-%d')
            nights = max((check_out - check_in).days, 1)
        except (ValueError, TypeError):
            nights = 1
    
    # Параметры лодки
    parameters = boat_data.get('parameters', {})
    country = boat_data.get('country', '').lower()
    category = boat_data.get('category', '')
    marina = boat_data.get('marina', '').lower()
    length = float(parameters.get('length', 0) or 0)
    max_sleeps = int(parameters.get('max_sleeps', 0) or parameters.get('berths', 0) or 0)
    doubles = int(parameters.get('double_cabins', 0) or 0)
    
    # 1. Страхование депозита
    insurance = max(total_price * INSURANCE_RATE, INSURANCE_MIN)
    total_price += insurance
    
    # 2. Доплата за дополнительные каюты (Сейшелы)
    if country in SEYCHELLES_NAMES and doubles > MAX_DOUBLE_CABINS_FREE:
        extra_cabins = doubles - MAX_DOUBLE_CABINS_FREE
        total_price += extra_cabins * DOUBLE_CABIN_EXTRA
    
    # 3. Базовая цена по стране
    if country in TURKEY_NAMES:
        total_price += TURKEY_BASE_PRICE
        dish_base = TURKEY_DISH_BASE
    elif country in SEYCHELLES_NAMES:
        total_price += SEYCHELLES_BASE_PRICE
        dish_base = SEYCHELLES_DISH_BASE
    else:
        total_price += DEFAULT_BASE_PRICE
        dish_base = DEFAULT_DISH_BASE
    
    # 4. Доплата за марину Praslin
    if marina == 'praslin marina':
        total_price += PRASLIN_EXTRA
    
    # 5. Доплата за длину > 14.2м (46 футов)
    if length > 14.2:
        total_price += LENGTH_EXTRA
    
    # 6. Доплата за длину > 13.8м в Турции
    if length > 13.8 and country in TURKEY_NAMES:
        if category == 'Катамаран':
            total_price += CATAMARAN_LENGTH_EXTRA
        elif category == 'Парусная Яхта':
            total_price += SAILING_LENGTH_EXTRA
    
    # 7. Питание
    if dish and max_sleeps > 0:
        total_price += (max_sleeps - 2) * dish_base + COOK_PRICE
    
    # 8. Применение скидки/наценки
    if discount:
        total_price += discount
    
    return {
        'total_price': round(total_price, 2),
        'original_price': round(full_price, 2),
        'discount': boat_discount,
        'nights': nights,
    }