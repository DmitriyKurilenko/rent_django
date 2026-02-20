"""
Helper функции для работы с API boataround.com
Документация: https://api.boataround.com
"""
import requests
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


def normalize_image_url(image_url: str) -> str:
    """
    Преобразование относительного пути изображения в полный URL
    
    Args:
        image_url: URL или путь к изображению
        
    Returns:
        str: Полный URL к изображению
    """
    if not image_url:
        return ''
    
    image_url = str(image_url).strip()
    
    # Если уже полный URL - возвращаем как есть
    if image_url.startswith('http://') or image_url.startswith('https://'):
        return image_url
    
    # Если это путь начинающийся с / - добавляем домен
    if image_url.startswith('/'):
        return f"https://api.boataround.com{image_url}"
    
    # Если это просто имя файла - предполагаем что он в boats
    if not image_url.startswith('boats/'):
        return f"https://api.boataround.com/boats/{image_url}"
    
    return f"https://api.boataround.com/{image_url}"


class BoataroundAPI:
    """Класс для работы с API boataround.com"""
    
    BASE_URL = "https://api.boataround.com/v1"
    
    # Реалистичные headers для обхода блокировок
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Origin': 'https://www.boataround.com',
        'Referer': 'https://www.boataround.com/',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
    }
    
    @staticmethod
    def autocomplete(
        query: str,
        language: str = "en_EN",
        limit: int = 10
    ) -> List[Dict]:
        """
        Автодополнение для поиска локаций
        
        Args:
            query: Поисковый запрос
            language: Язык (en_EN, ru_RU, etc)
            limit: Лимит результатов (1-50)
            
        Returns:
            List[Dict]: Список вариантов направлений
        """
        try:
            url = f"{BoataroundAPI.BASE_URL}/autocomplete/"
            params = {
                "query": query,
                "lang": language,
                "limit": limit
            }
            
            logger.info(f"[Autocomplete] Request: {url} with query={query}, lang={language}")
            
            response = requests.get(
                url, 
                params=params, 
                headers=BoataroundAPI.HEADERS,
                timeout=5
            )
            
            logger.info(f"[Autocomplete] Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                logger.info(f"[Autocomplete] Raw data type: {type(data)}")
                logger.info(f"[Autocomplete] Raw data: {str(data)[:500]}")
                
                # API может возвращать разные форматы
                if isinstance(data, list):
                    results = data
                elif isinstance(data, dict) and 'data' in data:
                    results = data['data']
                elif isinstance(data, dict) and data.get('status') == 'Success':
                    results = data.get('data', [])
                else:
                    results = []
                
                logger.info(f"[Autocomplete] Found {len(results)} results")
                if results and len(results) > 0:
                    logger.info(f"[Autocomplete] First result: {results[0]}")
                return results
            
            logger.warning(f"[Autocomplete] Non-200 status: {response.status_code}")
            return []
            
        except Exception as e:
            logger.error(f"[Autocomplete] Error: {e}")
            return []
    
    @staticmethod
    def search(
        check_in: Optional[str] = None,
        check_out: Optional[str] = None,
        destination: Optional[str] = None,
        category: Optional[str] = None,
        cabins: Optional[str] = None,
        year: Optional[str] = None,
        price: Optional[str] = None,
        page: int = 1,
        limit: int = 18,
        sort: str = "rank",
        lang: str = "en_EN",
        **kwargs
    ) -> Dict:
        """
        Поиск лодок через API boataround.com
        
        Args:
            check_in: Дата заезда (YYYY-MM-DD)
            check_out: Дата выезда (YYYY-MM-DD)
            destination: Направление (slug из autocomplete)
            category: Категория (sailing-yacht, catamaran, motor-yacht, motor-boat, gulet, power-catamaran)
            cabins: Количество кают (число, список через запятую, или диапазон X-Y)
            year: Год выпуска (число, список через запятую, или диапазон X-Y)
            price: Диапазон цен (формат [X-Y])
            page: Номер страницы (≥1)
            limit: Количество результатов (1-50, default 18)
            sort: Сортировка (priceDown, priceUp, rank, etc)
            lang: Язык (en_EN, ru_RU, etc)
            **kwargs: Дополнительные параметры
            
        Returns:
            Dict: {
                'boats': List[Dict],
                'total': int,
                'page': int,
                'totalPages': int,
                'filters': Dict
            }
        """
        try:
            url = f"{BoataroundAPI.BASE_URL}/search"  # БЕЗ слэша в конце!
            
            # Базовые параметры - ОБЯЗАТЕЛЬНО limit!
            params = {
                'limit': limit,
                'page': page
            }
            
            # Добавляем опциональные параметры
            if check_in:
                params['checkIn'] = check_in
            if check_out:
                params['checkOut'] = check_out
            if destination:
                # API веб-интерфейса использует параметр `destinations` (plural)
                # e.g. https://www.boataround.com/search?destinations=seychelles
                params['destinations'] = destination
            if category:
                params['category'] = category
            if cabins:
                params['cabins'] = cabins
            if year:
                params['year'] = year
            if price:
                params['price'] = price
            if sort:
                params['sort'] = sort
            
            # Язык (важно для фильтров и названий)
            if lang:
                params['lang'] = lang
            
            # Добавляем дополнительные параметры
            params.update(kwargs)
            
            logger.info(f"[Search] Request: {url}")
            logger.info(f"[Search] Params: {params}")
            
            # Формируем полный URL для отладки
            from urllib.parse import urlencode
            full_url = f"{url}?{urlencode(params)}"
            logger.info(f"[Search] Full URL: {full_url}")
            
            # Retry logic for timeouts
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = requests.get(
                        url, 
                        params=params, 
                        headers=BoataroundAPI.HEADERS,
                        timeout=30  # Increased timeout for large responses
                    )
                    break  # Success, exit retry loop
                except (requests.Timeout, requests.ConnectionError) as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"[Search] Timeout on attempt {attempt + 1}/{max_retries}, retrying...")
                        import time
                        time.sleep(2 ** attempt)  # Exponential backoff
                    else:
                        raise
            
            logger.info(f"[Search] Status: {response.status_code}")
            logger.info(f"[Search] Response length: {len(response.text) if response.text else 0} bytes")
            
            # Обработка 500 ошибки API (баг с фильтрами + сортировкой)
            if response.status_code == 500:
                logger.error(f"[Search] API returned 500 error. Response: {response.text[:500]}")
                # Если есть сортировка И фильтры, попробуем без сортировки
                if sort and (cabins or year or price):
                    logger.warning(f"[Search] Retrying without sort parameter due to API bug...")
                    params.pop('sort', None)
                    response = requests.get(url, params=params, headers=BoataroundAPI.HEADERS, timeout=30)
                    logger.info(f"[Search] Retry status: {response.status_code}")
                else:
                    return {'boats': [], 'total': 0, 'totalPages': 0, 'filters': {}}
            
            if response.status_code == 200:
                data = response.json()
                
                logger.info(f"[Search] ==================== API RESPONSE ====================")
                logger.info(f"[Search] Response type: {type(data)}")
                logger.info(f"[Search] Response keys: {list(data.keys()) if isinstance(data, dict) else 'not dict'}")
                
                # Проверяем структуру ответа
                if isinstance(data, dict):
                    
                    # Если есть status и data - это обёртка
                    if 'status' in data and 'data' in data:
                        inner_data = data.get('data', [])
                        logger.info(f"[Search] Inner data type: {type(inner_data)}")
                        
                        # data может быть массивом с одним объектом
                        if isinstance(inner_data, list) and len(inner_data) > 0:
                            actual_data = inner_data[0]
                            logger.info(f"[Search] Actual data keys: {list(actual_data.keys())}")
                            
                            # Лодки внутри вложенного data
                            boats = actual_data.get('data', [])
                            
                            # ВАЖНО: totalResults может быть на РАЗНЫХ уровнях!
                            total = actual_data.get('totalResults', 0)
                            total_boats = actual_data.get('totalBoats', 0)
                            
                            logger.info(f"[Search] totalResults from actual_data: {total}")
                            logger.info(f"[Search] totalBoats from actual_data: {total_boats}")
                            
                            # Используем максимальное значение
                            total = max(total, total_boats, len(boats))
                            
                            # Вычисляем totalPages по реальному кол-ву лодок на странице
                            # API может игнорировать наш limit и отдавать свой (напр. 18)
                            actual_per_page = len(boats) if boats else limit
                            total_pages = (total + actual_per_page - 1) // actual_per_page if total > 0 else 1
                            
                            logger.info(f"[Search] FINAL: boats={len(boats)}, total={total}, pages={total_pages}")
                            
                            return {
                                'boats': boats,
                                'total': total,
                                'page': page,
                                'totalPages': total_pages,
                                'filters': actual_data.get('filter', {})
                            }
                
                # Прямой массив лодок
                if isinstance(data, list):
                    logger.info(f"[Search] Got {len(data)} boats (direct array)")
                    actual_count = len(data)
                    return {
                        'boats': data[:limit],
                        'total': actual_count,
                        'page': page,
                        'totalPages': 1,  # Прямой массив = одна страница
                        'filters': {}
                    }
                
                # Ищем лодки в разных местах (старая логика)
                boats = []
                if 'results' in data:
                    boats = data['results']
                elif 'boats' in data:
                    boats = data['boats']
                elif 'data' in data:
                    boats = data['data']
                
                # Ищем total в разных местах
                total = 0
                if 'totalResults' in data:
                    total = data['totalResults']
                elif 'totalBoats' in data:
                    total = data['totalBoats']
                elif 'total' in data:
                    total = data['total']
                else:
                    total = len(boats)
                
                # Считаем totalPages по реальному кол-ву лодок на странице
                # API может игнорировать наш limit и отдавать свой (напр. 18)
                actual_per_page = len(boats) if boats else limit
                if total > 0 and actual_per_page > 0:
                    total_pages = (total + actual_per_page - 1) // actual_per_page
                else:
                    total_pages = 1

                logger.info(f"[Search] Parsed: boats={len(boats)}, total={total}, pages={total_pages}, actual_per_page={actual_per_page}")
                if boats and len(boats) > 0:
                    logger.info(f"[Search] First boat keys: {list(boats[0].keys())}")
                
                return {
                    'boats': boats,
                    'total': total,
                    'page': page,
                    'totalPages': total_pages,
                    'filters': data.get('filters', {})
                }
            
            elif response.status_code == 204:
                # No Content - возвращаем пустой результат
                logger.info("[Search] No content (204)")
                data = response.json() if response.text else {}
                return {
                    'boats': [],
                    'total': 0,
                    'page': 1,
                    'totalPages': 0,
                    'filters': data.get('filters', {})
                }
            
            logger.warning(f"[Search] Non-success status: {response.status_code}")
            logger.warning(f"[Search] Response text: {response.text[:500]}")
            
            return {
                'boats': [],
                'total': 0,
                'page': 1,
                'totalPages': 0,
                'filters': {}
            }
            
        except Exception as e:
            logger.error(f"[Search] Error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'boats': [],
                'total': 0,
                'page': 1,
                'totalPages': 0,
                'filters': {}
            }

    @staticmethod
    def get_price(
        slug: str,
        check_in: Optional[str] = None,
        check_out: Optional[str] = None,
        currency: str = 'EUR',
        lang: str = 'en_EN'
    ) -> Dict:
        """
        Получение цены для конкретной лодки
        
        Args:
            slug: Slug лодки
            check_in: Дата заезда (YYYY-MM-DD)
            check_out: Дата выезда (YYYY-MM-DD)
            currency: Валюта (EUR, USD, etc)
            lang: Язык
            
        Returns:
            Dict: Данные о цене
        """
        try:
            url = f"{BoataroundAPI.BASE_URL}/price/{slug}"
            
            params = {
                'currency': currency,
                'lang': lang,
                'loggedIn': '0'
            }
            
            if check_in:
                params['checkIn'] = check_in
            if check_out:
                params['checkOut'] = check_out
            
            response = requests.get(
                url,
                params=params,
                headers=BoataroundAPI.HEADERS,
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # API возвращает: data[0]['data'][0] с информацией о цене
                if isinstance(data, dict) and 'data' in data:
                    outer_list = data.get('data', [])
                    if isinstance(outer_list, list) and len(outer_list) > 0:
                        outer_data = outer_list[0]
                        if isinstance(outer_data, dict) and 'data' in outer_data:
                            inner_list = outer_data.get('data', [])
                            if isinstance(inner_list, list) and len(inner_list) > 0:
                                price_info = inner_list[0]
                                if isinstance(price_info, dict):
                                    # Получаем все параметры цены из policies[0].prices (объект с price_id)
                                    base_price = 0
                                    discount_without_extra = 0
                                    additional_discount = 0
                                    policies = price_info.get('policies', [])
                                    if policies and len(policies) > 0:
                                        prices = policies[0].get('prices', {})
                                        if prices:
                                            price_id = prices.get('price_id')
                                            base_price = prices.get('price', 0)  # Цена из policies.prices
                                            discount_without_extra = prices.get('discount_without_additionalExtra', 0)
                                            additional_discount = prices.get('additional_discount', 0)
                                            logger.debug(f"[get_price] Using prices from price_id={price_id}: price={base_price}, discount_without_extra={discount_without_extra}, additional_discount={additional_discount}")
                                    
                                    # Если нет policies, используем цену с верхнего уровня как fallback
                                    if not base_price:
                                        base_price = price_info.get('price', 0)
                                    
                                    # Возвращаем только нужные поля включая все скидки
                                    return {
                                        'price': base_price,
                                        'totalPrice': price_info.get('totalPrice', 0),
                                        'discount': price_info.get('discount', 0),
                                        'discount_without_additionalExtra': discount_without_extra,
                                        'additional_discount': additional_discount,
                                        'slug': price_info.get('slug'),
                                        'title': price_info.get('title'),
                                    }
                
                return {}
            
            return {}
            
        except Exception as e:
            logger.error(f"[Price] Error getting price for {slug}: {e}")
            return {}
    
    @staticmethod
    @staticmethod
    def get_boat_combined_data(slug: str) -> Dict:
        """
        Получает комбинированные данные о лодке из новой структуры моделей.
        
        Returns:
            Dict: Полные данные о лодке или {}
        """
        try:
            logger.info(f"[get_boat_combined_data] Getting data for: {slug}")
            
            # Ищем в БД
            from boats.models import (
                ParsedBoat, BoatTechnicalSpecs, BoatDescription, 
                BoatPrice, BoatGallery, BoatDetails
            )
            
            # Получаем лодку со всеми связанными данными
            parsed_boat = ParsedBoat.objects.select_related(
                'technical_specs'
            ).prefetch_related(
                'descriptions', 'prices', 'gallery', 'details'
            ).filter(slug=slug).first()
            
            if not parsed_boat:
                logger.warning(f"[get_boat_combined_data] No boat in DB for: {slug}")
                return {}
            
            logger.info(f"[get_boat_combined_data] ✅ Found in DB: {slug}")
            
            # Получаем описание (предпочитаем русский)
            try:
                desc = parsed_boat.descriptions.get(language='ru_RU')
            except:
                desc = parsed_boat.descriptions.first()
            
            if not desc:
                logger.warning(f"[get_boat_combined_data] No description found for: {slug}")
                return {}
            
            # Получаем технические параметры
            specs = parsed_boat.technical_specs
            
            # Получаем цену (предпочитаем EUR)
            try:
                price = parsed_boat.prices.get(currency='EUR')
            except:
                price = parsed_boat.prices.first()
            
            # Получаем детали (extras, adds, not_included) на русском
            try:
                details = parsed_boat.details.get(language='ru_RU')
            except:
                details = parsed_boat.details.first()
            
            if not details:
                details = None
            
            # Получаем фото
            photos = list(parsed_boat.gallery.all().values_list('cdn_url', flat=True))
            
            # Форматируем для отображения в шаблоне
            result = {
                # Основная информация
                'title': desc.title,
                'name': desc.title,
                'slug': slug,
                'boat_id': parsed_boat.boat_id,
                
                # ⭐ ГЛАВНЫЕ ПОЛЯ (из BoatTechnicalSpecs)
                'cabins': specs.cabins or '',
                'toilets': specs.toilets or '',
                'length': specs.length or '',
                'beam': specs.beam or '',
                'draft': specs.draft or '',
                'year': parsed_boat.year or '',
                'engine': specs.engine_type or '',
                'fuel': specs.fuel_capacity or '',
                'maximum_speed': specs.max_speed or '',
                'berths': specs.berths or '',
                'max_sleeps': specs.berths or '',
                'type': parsed_boat.manufacturer or '',
                'category': parsed_boat.model or '',
                
                # Параметры (все технические данные)
                'parameters': {
                    'cabins': specs.cabins or '',
                    'berths': specs.berths or '',
                    'toilets': specs.toilets or '',
                    'length': specs.length or '',
                    'beam': specs.beam or '',
                    'draft': specs.draft or '',
                    'year': parsed_boat.year or '',
                    'maximum_speed': specs.max_speed or '',
                    'engine': specs.engine_type or '',
                    'fuel_capacity': specs.fuel_capacity or '',
                    'water_capacity': specs.water_capacity or '',
                    'engine_power': specs.engine_power or '',
                    'number_engines': specs.number_engines or '',
                },
                
                # Географическая информация
                'marina': desc.marina or '',
                'location': desc.location or '',
                'country': desc.country or '',
                'region': desc.region or '',
                'city': desc.city or '',
                'description': desc.description or '',
                'manufacturer': parsed_boat.manufacturer or '',
                'model': parsed_boat.model or '',
                
                # ГЛАВНОЕ: Фото (используем CDN URLs)
                'pictures': photos,
                'gallery': photos,
                'images': photos,
                'image': photos[0] if photos else '',
                
                # ГЛАВНОЕ: Услуги
                'extras': details.extras if details else [],
                'additional_services': details.additional_services if details else [],
                'delivery_extras': details.delivery_extras if details else [],
                'not_included': details.not_included if details else [],
                'cockpit': details.cockpit if details and hasattr(details, 'cockpit') else [],
                'entertainment': details.entertainment if details and hasattr(details, 'entertainment') else [],
                'equipment': details.equipment if details and hasattr(details, 'equipment') else [],
                
                # Цены
                'price': price.price_per_day if price else 0,
                'currency': price.currency if price else 'EUR',
                'prices': {
                    'total_price': price.price_per_day if price else 0,
                    'currency': price.currency if price else 'EUR',
                },
                
                # Метаданные
                'parsed_at': str(parsed_boat.last_parsed) if parsed_boat.last_parsed else '',
            }
            
            logger.info(f"[get_boat_combined_data] ✅ Formatted data for: {result['title']}, "
                       f"images={len(result['images'])}, extras={len(result['extras'])}")
            return result
            
        except Exception as e:
            logger.error(f"[get_boat_combined_data] Error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {}
    
    @staticmethod
    def search_by_slug(slug: str) -> Dict:
        """
        Поиск лодки по slug через API
        
        Args:
            slug: Slug лодки
            
        Returns:
            Dict: Данные лодки или {}
        """
        try:
            logger.info(f"[search_by_slug] Searching for: {slug}")
            
            url = f"{BoataroundAPI.BASE_URL}/search"
            params = {
                'slug': slug,
                'limit': 1,
                'lang': 'en_EN'
            }
            
            response = requests.get(
                url,
                params=params,
                headers=BoataroundAPI.HEADERS,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if isinstance(data, dict) and 'status' in data:
                    # Структура ответа: {"status": "OK", "data": [{"data": [...]}]}
                    results = data.get('data', [])
                    if results and isinstance(results, list):
                        for result_group in results:
                            boats = result_group.get('data', [])
                            if boats and len(boats) > 0:
                                boat_data = boats[0]
                                logger.info(f"[search_by_slug] ✅ Found: {boat_data.get('title')}")
                                return format_boat_data(boat_data)
            
            logger.warning(f"[search_by_slug] No boats found for {slug}")
            return {}
            
        except Exception as e:
            logger.error(f"[search_by_slug] Error: {e}")
            return {}
    
    def get_boat_detail(boat_id_or_slug: str) -> Dict:
        """
        Получение полной детальной информации о лодке.
        Использует парсер для получения фото, услуг и дополнительной информации.
        
        Args:
            boat_id_or_slug: ID или slug лодки
            
        Returns:
            Dict: Отформатированная полная информация о лодке
        """
        try:
            logger.info(f"[Boat Detail] Looking up boat: {boat_id_or_slug}")
            
            # Используем парсер для получения полных данных
            boat_url = f"https://www.boataround.com/ru/yachta/{boat_id_or_slug}/"
            logger.info(f"[Boat Detail] Parser URL: {boat_url}")
            
            from boats.parser import parse_boataround_url
            parsed_data = parse_boataround_url(boat_url, save_to_db=True)
            
            if parsed_data:
                logger.info(f"[Boat Detail] Successfully parsed boat: {parsed_data.get('slug')}")
                return BoataroundAPI._format_parsed_result(parsed_data)
            else:
                logger.warning(f"[Boat Detail] Failed to parse boat")
                return {}
            
        except Exception as e:
            logger.error(f"[Boat Detail] Error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {}

    
    @staticmethod
    def _format_parsed_boat(parsed_boat) -> Dict:
        """
        Форматирует данные из ParsedBoat модели в словарь для шаблона
        Ожидает ПОЛНЫЕ ПАРСИРОВАННЫЕ данные (boat_info, pictures, prices)
        
        Args:
            parsed_boat: Объект ParsedBoat из БД с полными парсированными данными
            
        Returns:
            Dict: Отформатированные данные
        """
        from boats.parser import get_cdn_url
        
        # Получаем данные из boat_data JSON поля
        boat_data_raw = parsed_boat.boat_data or {}
        boat_info = boat_data_raw.get('boat_info', {})
        pictures = boat_data_raw.get('pictures', [])
        prices = boat_data_raw.get('prices', {})
        extras = boat_data_raw.get('extras', [])
        additional_services = boat_data_raw.get('additional_services', [])
        delivery_extras = boat_data_raw.get('delivery_extras', [])
        not_included = boat_data_raw.get('not_included', [])
        
        # Получаем длину
        length = boat_info.get('length', 0)
        try:
            if isinstance(length, str):
                length = float(length.replace('m', '').replace(',', '.').strip())
            length = round(float(length), 1) if length else 0
        except:
            length = 0
        
        # Получаем цену
        price_val = prices.get('total', {}).get('amount') or prices.get('price_per_day', {}).get('amount') or 0
        try:
            price = int(float(price_val)) if price_val else 0
        except:
            price = 0
        
        # Формируем массив изображений с CDN URL
        images = [get_cdn_url(pic) for pic in pictures] if pictures else []
        
        # Получаем кабины и места
        cabins = 0
        berths = 0
        try:
            cabins = int(boat_info.get('cabins', 0)) if boat_info.get('cabins') else 0
        except:
            cabins = 0
        try:
            berths = int(boat_info.get('people', 0)) if boat_info.get('people') else 0
        except:
            berths = 0
        
        # Извлекаем параметры
        boat_data = {
            'id': str(parsed_boat.boat_id),
            'slug': parsed_boat.slug,
            'name': boat_info.get('title', 'Лодка'),
            'marina': boat_info.get('marina', ''),
            'country': boat_info.get('country', ''),
            'region': boat_info.get('region', ''),
            'city': boat_info.get('city', ''),
            'location': parsed_boat.location or boat_info.get('location', ''),
            'description': boat_info.get('description', ''),
            'currency': prices.get('currency', 'EUR'),
            'price': price,
            'image': images[0] if images else '',
            'images': images,
            # Основные параметры
            'cabins': cabins,
            'berths': berths,
            'length': length,
            'year': boat_info.get('year', ''),
            'category': boat_info.get('category', ''),
            'type': boat_info.get('manufacturer', ''),
            # Дополнительные параметры
            'max_sleeps': boat_info.get('max_sleeps', ''),
            'max_people': boat_info.get('max_people', ''),
            'single_cabins': boat_info.get('single_cabins', ''),
            'double_cabins': boat_info.get('double_cabins', ''),
            'triple_cabins': boat_info.get('triple_cabins', ''),
            'quadruple_cabins': boat_info.get('quadruple_cabins', ''),
            'cabins_with_bunk_bed': boat_info.get('cabins_with_bunk_bed', ''),
            'saloon_sleeps': boat_info.get('saloon_sleeps', ''),
            'crew_sleeps': boat_info.get('crew_sleeps', ''),
            'toilets': boat_info.get('toilets', ''),
            'electric_toilets': boat_info.get('electric_toilets', ''),
            'beam': boat_info.get('beam', ''),
            'draft': boat_info.get('draft', ''),
            'renovated_year': boat_info.get('renovated_year', ''),
            'sail_renovated_year': boat_info.get('sail_renovated_year', ''),
            'engine': boat_info.get('engine', ''),
            'engine_type': boat_info.get('engine_type', ''),
            'fuel': boat_info.get('fuel', ''),
            'cruising_consumption': boat_info.get('cruising_consumption', ''),
            'maximum_speed': boat_info.get('maximum_speed', ''),
            # Прочие поля
            'rating': 0,
            'charter': '',
            'coordinates': [],
            'extras': extras,
            'additional_services': additional_services,
            'delivery_extras': delivery_extras,
            'not_included': not_included,
        }
        
        logger.info(f"[format_parsed_boat] {boat_data['name']} | price={price}, images={len(images)}, cabins={cabins}, berths={berths}")
        
        return boat_data
    
    @staticmethod
    def _format_parsed_result(parsed_data: dict) -> Dict:
        """
        Форматирует результат парсера в словарь для шаблона
        
        Args:
            parsed_data: Результат из parse_boataround_url()
            
        Returns:
            Dict: Отформатированные данные
        """
        from boats.parser import get_cdn_url
        
        boat_info = parsed_data.get('boat_info', {})
        pictures = parsed_data.get('pictures', [])
        prices = parsed_data.get('prices', {})
        extras = parsed_data.get('extras', [])
        additional_services = parsed_data.get('additional_services', [])
        delivery_extras = parsed_data.get('delivery_extras', [])
        not_included = parsed_data.get('not_included', [])
        
        # DEBUG логирование
        logger.info(f"[format_parsed_result] boat_info: {boat_info}")
        logger.info(f"[format_parsed_result] prices: {prices}")
        
        # Получаем длину
        length = boat_info.get('length', 0)
        try:
            if isinstance(length, str):
                length = float(length.replace('m', '').replace(',', '.').strip())
            length = round(float(length), 1) if length else 0
        except:
            length = 0
        
        # Получаем цену
        # Парсер возвращает: min_price, total_price, low_price
        price_val = prices.get('total_price') or prices.get('min_price') or prices.get('low_price') or 0
        try:
            price = int(float(price_val)) if price_val else 0
        except:
            price = 0
        
        # Формируем массив изображений с CDN URL
        images = [get_cdn_url(pic) for pic in pictures] if pictures else []
        
        boat_data = {
            'id': parsed_data.get('boat_id', ''),
            'slug': parsed_data.get('slug', ''),
            'name': boat_info.get('title', 'Лодка'),
            'marina': boat_info.get('marina', ''),
            'country': boat_info.get('country', ''),
            'region': boat_info.get('region', ''),
            'city': boat_info.get('city', ''),
            'location': boat_info.get('location', ''),
            'description': boat_info.get('description', ''),
            'currency': prices.get('currency', 'EUR'),
            'price': price,
            'image': images[0] if images else '',
            'images': images,
            'cabins': int(boat_info.get('cabins', 0)) if boat_info.get('cabins') else 0,
            'berths': int(boat_info.get('people', 0)) if boat_info.get('people') else 0,
            'length': length,
            'year': boat_info.get('year', ''),
            'category': boat_info.get('category', ''),
            'type': boat_info.get('manufacturer', ''),
            'rating': 0,
            'charter': '',
            'coordinates': [],
            'extras': extras,
            'additional_services': additional_services,
            'delivery_extras': delivery_extras,
            'not_included': not_included,
        }
        
        logger.info(f"[format_parsed_result] {boat_data['name']} | price={price}, images={len(images)}, extras={len(extras)}, adds={len(additional_services)}")
        
        return boat_data
    
    @staticmethod
    def _get_boat_from_api(boat_id_or_slug: str) -> Dict:
        """
        Fallback метод: получает данные через API поиск по slug
        
        Args:
            boat_id_or_slug: ID или slug лодки
            
        Returns:
            Dict: Отформатированные данные или пусто
        """
        try:
            logger.info(f"[Boat Detail API Fallback] Trying API search: {boat_id_or_slug}")
            
            url = f"{BoataroundAPI.BASE_URL}/search"
            params = {
                'slug': boat_id_or_slug,
                'limit': 1,
                'lang': 'en_EN'
            }
            
            response = requests.get(
                url,
                params=params,
                headers=BoataroundAPI.HEADERS,
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if isinstance(data, dict) and 'status' in data and 'data' in data:
                    inner_data = data.get('data', [])
                    
                    if isinstance(inner_data, list) and len(inner_data) > 0:
                        actual_data = inner_data[0]
                        boats = actual_data.get('data', [])
                        
                        if boats and len(boats) > 0:
                            boat_data = boats[0]
                            logger.info(f"[Boat Detail API Fallback] Found boat: {boat_data.get('title')}")
                            return format_boat_data(boat_data)
        
        except Exception as e:
            logger.error(f"[Boat Detail API Fallback] Error: {e}")
        
        return {}



def format_boat_data(boat: Dict) -> Dict:
    """
    Форматирование данных лодки из API для отображения в шаблоне
    
    Args:
        boat: Данные лодки от API boataround.com
        
    Returns:
        Dict: Отформатированные данные с правильными типами
    """
    # ОТЛАДКА: выводим все ключи в boat
    logger.debug(f"[format_boat_data] Full boat object keys: {list(boat.keys())}")
    if boat.get('title'):
        logger.debug(f"[format_boat_data] Title from boat: {boat.get('title')}")
    
    # Словарь переводов стран
    COUNTRY_TRANSLATIONS = {
        'Turkey': 'Турция',
        'Greece': 'Греция',
        'Croatia': 'Хорватия',
        'Spain': 'Испания',
        'France': 'Франция',
        'Italy': 'Италия',
        'Montenegro': 'Черногория',
        'Slovenia': 'Словения',
        'Malta': 'Мальта',
        'Cyprus': 'Кипр',
        'Portugal': 'Португалия',
        'Thailand': 'Таиланд',
        'Seychelles': 'Сейшелы',
        'Maldives': 'Мальдивы',
        'United States': 'США',
        'Mexico': 'Мексика',
        'Philippines': 'Филиппины',
        'Indonesia': 'Индонезия',
        'Egypt': 'Египет',
    }
    
    # ID и slug (основные идентификаторы)
    boat_id = boat.get('_id') or boat.get('id') or 'unknown'
    slug = boat.get('slug', '')
    
    # Название лодки - ТУТ САМАЯ ВАЖНАЯ ЧАСТЬ!
    # Ищем название в разных полях, в порядке приоритета
    name = None
    for field in ['title', 'name', 'boatName', 'boat_name', 'displayName']:
        if field in boat and boat[field] and str(boat[field]).strip():
            name = str(boat[field]).strip()
            logger.info(f"[format_boat_data] Found name in field '{field}': {name}")
            break
    
    # Если название не найдено, используем параметры
    if not name:
        if 'parameters' in boat and isinstance(boat['parameters'], dict):
            name = boat['parameters'].get('displayName') or boat['parameters'].get('name')
            if name:
                logger.info(f"[format_boat_data] Found name in parameters: {name}")
    
    # Последняя попытка - формируем из других данных
    if not name or name.strip() == '':
        boat_type = boat.get('type', 'Boat')
        country = boat.get('country', 'Unknown')
        location = boat.get('city') or boat.get('marina') or country
        if boat_type and location:
            name = f"{boat_type} in {location}"
            logger.warning(f"[format_boat_data] Using generated name: {name}")
        else:
            name = 'Лодка'
            logger.warning(f"[format_boat_data] No name found, using default")
    
    # Локация: marina, country, region, city
    marina = boat.get('marina', '')
    country_en = boat.get('country', '')
    country = COUNTRY_TRANSLATIONS.get(country_en, country_en)
    region = boat.get('region', '')
    city = boat.get('city', '')
    
    # Формируем полное название локации
    location_parts = [p for p in [marina, city, region] if p and p.strip()]
    location = ', '.join(location_parts) if location_parts else country
    
    # === ИЗОБРАЖЕНИЯ ===
    # API может вернуть изображения в разных полях
    images = []
    
    # DEBUG: логируем какие поля есть для изображений
    img_fields = [k for k in boat.keys() if 'img' in k.lower() or 'image' in k.lower() or 'gallery' in k.lower() or 'photo' in k.lower()]
    logger.debug(f"[format_boat_data] Image-related fields: {img_fields}")
    
    # Основное изображение - ПРИОРИТЕТ: thumb (уже готовый URL от imageresizer) > main_img (нужно нормализовать)
    thumb = boat.get('thumb')
    main_img = boat.get('main_img')
    
    # Используем thumb если он есть - это уже отресайзированное изображение
    if thumb and thumb.strip():
        images.append(thumb)
        logger.debug(f"[format_boat_data] Added thumb: {thumb[:80]}")
    elif main_img and main_img.strip():
        # Если thumb не найден, используем main_img и нормализуем URL
        normalized = normalize_image_url(main_img)
        images.append(normalized)
        logger.debug(f"[format_boat_data] Added main_img: {main_img[:80]}")
    
    # Дополнительные изображения
    if 'images' in boat and isinstance(boat['images'], list):
        logger.debug(f"[format_boat_data] Found 'images' field with {len(boat['images'])} items")
        for img in boat['images']:
            if img and img.strip():
                normalized = normalize_image_url(img)
                if normalized not in images:
                    images.append(normalized)
    elif 'gallery' in boat and isinstance(boat['gallery'], list):
        logger.debug(f"[format_boat_data] Found 'gallery' field with {len(boat['gallery'])} items")
        for img in boat['gallery']:
            if img and img.strip():
                normalized = normalize_image_url(img)
                if normalized not in images:
                    images.append(normalized)
    
    # Если нет изображений, используем main_img
    if not images and main_img:
        images = [main_img]
    
    # === ЦЕНА ===
    # Единая логика как на detail:
    # 1) discount_without_additionalExtra
    # 2) additional_discount
    # 3) доп.скидка до 5% при additional_discount < charter.commission
    base_price = 0
    discount_without_extra = 0
    additional_discount = 0
    avg_price = boat.get('avg_price', 0)  # Средняя цена за сутки

    # Приоритет для выдачи поиска:
    # - base_price берём из price (это базовая цена до скидок), fallback на totalPrice
    # - additional_discount берём из additionalDiscount
    # - discount_without_extra:
    #     * если есть discount_without_additionalExtra -> используем его
    #     * иначе вычисляем как (discount - additionalDiscount), потому что discount часто уже total
    base_price = boat.get('price', 0) or boat.get('totalPrice', 0)
    additional_discount = boat.get('additionalDiscount', 0) or boat.get('additional_discount', 0)

    explicit_discount_wo_extra = boat.get('discount_without_additionalExtra', 0)
    total_discount = boat.get('discount', 0)
    if explicit_discount_wo_extra:
        discount_without_extra = explicit_discount_wo_extra
    elif total_discount and additional_discount:
        discount_without_extra = max(float(total_discount) - float(additional_discount), 0)
    else:
        discount_without_extra = total_discount

    # Fallback на policies[0].prices, если в выдаче нет нужных полей
    policies = boat.get('policies', [])
    if policies and len(policies) > 0:
        prices = policies[0].get('prices', {})
        if prices:
            price_id = prices.get('price_id')
            if not base_price:
                base_price = prices.get('price', 0)
            if not discount_without_extra:
                discount_without_extra = prices.get('discount_without_additionalExtra', 0)
            if not additional_discount:
                additional_discount = prices.get('additional_discount', 0)
            logger.debug(
                f"[format_boat_data] Fallback prices from price_id={price_id}: "
                f"price={base_price}, discount_without_extra={discount_without_extra}, additional_discount={additional_discount}"
            )

    # Дополнительная информация (нужна для чартера/комиссии в расчёте)
    charter_info = boat.get('charter', '')
    charter_logo = boat.get('charter_logo', '')
    charter_id_raw = boat.get('charter_id', '')

    if isinstance(charter_info, dict):
        charter_data = charter_info
        charter_id_raw = charter_id_raw or charter_data.get('_id') or charter_data.get('id', '')
        charter_logo = charter_logo or charter_data.get('logo') or charter_data.get('logo_url') or charter_data.get('image', '')
        charter_info = charter_data.get('name') or charter_data.get('title') or charter_data.get('company') or ''

    # Fallback: иногда данные чартера приходят внутри parameters
    params = boat.get('parameters', {})
    if not charter_info and isinstance(params, dict):
        params_charter = params.get('charter')
        if isinstance(params_charter, dict):
            charter_id_raw = charter_id_raw or params_charter.get('_id') or params_charter.get('id', '')
            charter_logo = charter_logo or params_charter.get('logo') or params_charter.get('logo_url') or params_charter.get('image', '')
            charter_info = params_charter.get('name') or params_charter.get('title') or ''
        elif isinstance(params_charter, str):
            charter_info = params_charter

    # Единый расчёт цены через helper (как на detail)
    charter_obj = None
    try:
        if charter_info:
            from boats.helpers import get_or_create_charter
            charter_obj = get_or_create_charter(charter_info, charter_id_raw, charter_logo)
    except Exception as charter_err:
        logger.debug(f"[format_boat_data] Charter resolve error: {charter_err}")

    # Для search API используем totalPrice как более стабильный источник
    # (в API поле discount может "прыгать" при одинаковых параметрах)
    total_price_from_api = boat.get('totalPrice', 0)
    try:
        if total_price_from_api:
            price = float(total_price_from_api)

            # Применяем только дополнительный шаг по комиссии чартера
            # если additional_discount < commission -> еще скидка min(5, commission)
            if charter_obj and charter_obj.commission:
                commission = float(charter_obj.commission)
                additional_discount_val = float(additional_discount) if additional_discount else 0
                if additional_discount_val < commission:
                    extra_discount = min(5, commission)
                    price = price * (1 - extra_discount / 100)
        else:
            from boats.helpers import calculate_final_price_with_discounts
            price = calculate_final_price_with_discounts(
                base_price,
                discount_without_extra,
                additional_discount,
                charter_obj,
            )
    except Exception as calc_err:
        logger.warning(f"[format_boat_data] Price calc fallback due to error: {calc_err}")
        price = base_price
    
    # Пытаемся конвертировать в float
    try:
        if isinstance(price, str):
            price = float(price.replace(',', '.'))
        elif price is None:
            price = 0
        else:
            price = float(price)
    except (ValueError, TypeError):
        price = 0
    
    # Округляем до целого числа для отображения
    price = int(price) if price else 0

    # Старая цена и процент выгоды для UI
    old_price = 0
    discount_percent = 0
    try:
        base_price_float = float(base_price) if base_price else 0
        if base_price_float > 0 and price > 0 and base_price_float > price:
            old_price = int(base_price_float)
            discount_percent = round((base_price_float - float(price)) / base_price_float * 100)
    except (ValueError, TypeError):
        old_price = 0
        discount_percent = 0
    
    # Цена за сутки (avg_price из API или считаем сами)
    price_per_day = 0
    if avg_price:
        try:
            price_per_day = int(float(avg_price))
        except:
            price_per_day = 0
    
    currency = boat.get('currency', 'EUR')
    
    # === ХАРАКТЕРИСТИКИ ===
    # Получаем параметры из 'parameters' (это основное поле в API ответе)
    params = boat.get('parameters', {})
    
    # Каюты из parameters
    cabins = params.get('cabins') or boat.get('cabins') or boat.get('cabin', 0)
    try:
        cabins = int(cabins) if cabins else 0
    except (ValueError, TypeError):
        cabins = 0
    
    # Места из parameters (max_sleeps) или параметр berths
    berths = params.get('max_sleeps') or params.get('allowed_people') or boat.get('berths') or boat.get('berth', 0)
    try:
        berths = int(berths) if berths else 0
    except (ValueError, TypeError):
        berths = 0
    
    # freeBerths может быть объектом
    if not berths and 'freeBerths' in boat:
        free_berths = boat.get('freeBerths')
        if isinstance(free_berths, dict):
            try:
                berths = int(free_berths.get('value', 0)) or 0
            except:
                berths = 0
        elif isinstance(free_berths, (int, float)):
            try:
                berths = int(free_berths) or 0
            except:
                berths = 0
    
    # Длина лодки (всегда в parameters)
    parameters = boat.get('parameters', {})
    length = parameters.get('length', 0) if isinstance(parameters, dict) else 0
    
    try:
        if isinstance(length, str):
            length = float(length.replace('m', '').replace(',', '.').strip())
        else:
            length = float(length) if length else 0
        length = round(length, 1)
    except (ValueError, TypeError):
        length = 0
    
    # Год выпуска
    year = boat.get('year') or boat.get('buildYear', '')
    if year:
        try:
            year = int(year)
        except (ValueError, TypeError):
            year = ''
    
    # Рейтинг
    rating = boat.get('reviewsScore') or boat.get('rating', 0)
    try:
        rating = float(rating) if rating else 0
    except (ValueError, TypeError):
        rating = 0
    
    # Категория
    category = boat.get('category', '')
    boat_type = boat.get('type', '')
    
    # Дополнительная информация (уже извлечена выше для расчёта цены)
    coordinates = boat.get('coordinates', [])
    
    # === ОБОРУДОВАНИЕ ИЗ FILTER (из API) ===
    # Эти данные приходят в поле 'filter' в структуре: filter.cockpit, filter.entertainment, filter.equipment
    # Каждое это массив объектов: [{"_id":"...", "name":"...", "count":1}, ...]
    # Извлекаем только 'name' для отображения
    filter_data = boat.get('filter', {}) if isinstance(boat.get('filter'), dict) else {}
    
    cockpit = []
    entertainment = []
    equipment = []
    
    if filter_data:
        # Парсим cockpit
        if 'cockpit' in filter_data and isinstance(filter_data['cockpit'], list):
            cockpit = [{'name': item.get('name', '')} for item in filter_data['cockpit'] if item.get('name')]
        
        # Парсим entertainment
        if 'entertainment' in filter_data and isinstance(filter_data['entertainment'], list):
            entertainment = [{'name': item.get('name', '')} for item in filter_data['entertainment'] if item.get('name')]
        
        # Парсим equipment
        if 'equipment' in filter_data and isinstance(filter_data['equipment'], list):
            equipment = [{'name': item.get('name', '')} for item in filter_data['equipment'] if item.get('name')]
    
    # Лог для отладки
    logger.info(
        f"[format_boat_data] {name} | base={base_price}, discount_wo_extra={discount_without_extra}, "
        f"additional={additional_discount}, charter_commission={charter_obj.commission if charter_obj else 0}, "
        f"price={price}, images={len(images)}, cabins={cabins}, berths={berths}"
    )
    
    return {
        'id': boat_id,
        'slug': slug,
        'name': name,
        'marina': marina,
        'country': country,
        'region': region,
        'city': city,
        'location': location,
        'price': price,
        'old_price': old_price,
        'discount_percent': discount_percent,
        'price_per_day': price_per_day,
        'currency': currency,
        'image': images[0] if images else '',
        'images': images,  # Массив для шаблона
        'cabins': cabins,
        'berths': berths,
        'length': length,
        'year': year,
        'category': category,
        'type': boat_type,
        'rating': rating,
        'charter': charter_info,
        'charter_logo': charter_logo,
        'charter_id': charter_id_raw,
        'coordinates': coordinates,
        # Оборудование из API filter
        'cockpit': cockpit,
        'entertainment': entertainment,
        'equipment': equipment,
    }