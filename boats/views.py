from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Avg
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.utils.translation import get_language
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Boat, Favorite, Booking, Review, Offer, ParsedBoat, BoatDescription, BoatDetails
from .forms import SearchForm, BoatForm, BookingForm, ReviewForm, OfferForm
from .parser import parse_boataround_url, get_full_image_url
from .boataround_api import BoataroundAPI
from django.views.decorators.cache import cache_page
import logging

logger = logging.getLogger(__name__)


def home(request):
    """Главная страница"""
    form = SearchForm(request.GET or None)
    featured_boats = Boat.objects.filter(available=True)[:6]
    
    destinations = [
        {'name': 'Греция', 'emoji': '🇬🇷', 'count': 3451},
        {'name': 'Хорватия', 'emoji': '🇭🇷', 'count': 2847},
        {'name': 'Турция', 'emoji': '🇹🇷', 'count': 2156},
        {'name': 'Франция', 'emoji': '🇫🇷', 'count': 1923},
        {'name': 'Испания', 'emoji': '🇪🇸', 'count': 1654},
        {'name': 'Италия', 'emoji': '🇮🇹', 'count': 1842},
    ]
    
    context = {
        'form': form,
        'featured_boats': featured_boats,
        'destinations': destinations,
    }
    return render(request, 'boats/home.html', context)


def boat_search(request):
    """Поиск лодок через API boataround.com с пагинацией и ценами"""
    from boats.boataround_api import BoataroundAPI, format_boat_data
    from django.core.cache import cache
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Получаем параметры поиска
    destination = request.GET.get('destination', request.GET.get('location', '')).strip()
    category = request.GET.get('category', request.GET.get('boat_type', '')).strip()
    check_in = request.GET.get('check_in', request.GET.get('checkIn', '')).strip()
    check_out = request.GET.get('check_out', request.GET.get('checkOut', '')).strip()
    
    # Новые фильтры
    cabins = request.GET.get('cabins', '').strip()
    year_from = request.GET.get('year_from', '').strip()
    year_to = request.GET.get('year_to', '').strip()
    price_from = request.GET.get('price_from', '').strip()
    price_to = request.GET.get('price_to', '').strip()
    
    try:
        page = int(request.GET.get('page', 1))
    except (ValueError, TypeError):
        page = 1
    page = max(1, page)  # Минимум 1 страница
    
    sort = request.GET.get('sort', 'rank').strip()
    
    logger.info(f"[Search View] ============== NEW SEARCH ==============")
    logger.info(f"[Search View] destination='{destination}'")
    logger.info(f"[Search View] category='{category}'")
    logger.info(f"[Search View] check_in='{check_in}'")
    logger.info(f"[Search View] check_out='{check_out}'")
    logger.info(f"[Search View] cabins='{cabins}'")
    logger.info(f"[Search View] year={year_from}-{year_to}")
    logger.info(f"[Search View] price={price_from}-{price_to}")
    logger.info(f"[Search View] page={page}")
    
    # Пустой контекст если нет локации
    if not destination:
        logger.warning(f"[Search View] No destination provided!")
        context = {
            'boats': [],
            'total_results': 0,
            'page': 1,
            'total_pages': 0,
            'has_previous': False,
            'has_next': False,
            'previous_page': 0,
            'next_page': 2,
            'destination': '',
            'category': '',
            'check_in': '',
            'check_out': '',
            'rental_days': None,
            'sort': sort,
            'error_message': 'Пожалуйста, выберите направление',
            'search_query_str': '',
        }
        return render(request, 'boats/search.html', context)
    
    try:
        # Запрос к API boataround
        logger.info(f"[Search View] Calling BoataroundAPI.search...")
        
        # Формируем year параметр для API
        year_param = None
        if year_from and year_to:
            year_param = f"{year_from}-{year_to}"
        elif year_from:
            year_param = f"{year_from}-"
        elif year_to:
            year_param = f"-{year_to}"
        
        # Формируем price параметр для API
        price_param = None
        if price_from and price_to:
            price_param = f"{price_from}-{price_to}"
        elif price_from:
            price_param = f"{price_from}-"
        elif price_to:
            price_param = f"-{price_to}"
        
        # Формат cabins для API: "4-" означает "4 или больше"
        cabins_param = None
        if cabins:
            if cabins == "5":
                cabins_param = "5-"  # 5+ кают
            else:
                cabins_param = f"{cabins}-"  # N или больше кают
        
        search_results = BoataroundAPI.search(
            destination=destination,
            category=category if category else None,
            check_in=check_in if check_in else None,
            check_out=check_out if check_out else None,
            cabins=cabins_param if cabins_param else None,
            year=year_param if year_param else None,
            price=price_param if price_param else None,
            page=page,
            limit=18,  # 18 лодок на страницу
            sort=sort,
            lang='en_EN'
        )
        
        logger.info(f"[Search View] API returned: boats={len(search_results.get('boats', []))}, total={search_results.get('total', 0)}, pages={search_results.get('totalPages', 0)}")
        
        # Форматируем данные лодок и кэшируем их
        from boats.helpers import save_to_cache
        from boats.models import Favorite, ParsedBoat

        boats = []
        # Получаем список избранных для текущего пользователя (если авторизован)
        favorite_slugs = set()
        if request.user.is_authenticated:
            favorite_slugs = set(Favorite.objects.filter(user=request.user).values_list('boat_slug', flat=True))

        # CDN-превью: один запрос на всю страницу по slug
        api_boats = search_results.get('boats', [])
        slugs = [b.get('slug', '') for b in api_boats if b.get('slug')]
        preview_map = dict(
            ParsedBoat.objects.filter(slug__in=slugs, preview_cdn_url__gt='')
            .values_list('slug', 'preview_cdn_url')
        ) if slugs else {}

        for boat in api_boats:
            try:
                formatted_boat = format_boat_data(boat)

                # Превью: CDN если есть, иначе thumb из API
                cdn_preview = preview_map.get(formatted_boat.get('slug', ''))
                formatted_boat['preview'] = cdn_preview or boat.get('thumb', '')

                # Стабилизируем цену в выдаче по slug+датам (чтобы не прыгала при refresh)
                if check_in and check_out and formatted_boat.get('slug'):
                    price_cache_key = f"search_price_v2:{formatted_boat['slug']}:{check_in}:{check_out}:EUR"
                    cached_price_data = cache.get(price_cache_key)

                    if cached_price_data:
                        logger.info(
                            f"[Search View] Price cache HIT slug={formatted_boat['slug']} "
                            f"price={cached_price_data.get('price')}"
                        )
                        formatted_boat['price'] = cached_price_data.get('price', formatted_boat.get('price', 0))
                        formatted_boat['old_price'] = cached_price_data.get('old_price', formatted_boat.get('old_price', 0))
                        formatted_boat['discount_percent'] = cached_price_data.get('discount_percent', formatted_boat.get('discount_percent', 0))
                    else:
                        logger.info(
                            f"[Search View] Price cache MISS slug={formatted_boat['slug']} "
                            f"price={formatted_boat.get('price')}"
                        )
                        cache.set(
                            price_cache_key,
                            {
                                'price': formatted_boat.get('price', 0),
                                'old_price': formatted_boat.get('old_price', 0),
                                'discount_percent': formatted_boat.get('discount_percent', 0),
                            },
                            timeout=60 * 60,
                        )

                # Добавляем информацию об избранном
                formatted_boat['is_favorite'] = formatted_boat.get('slug') in favorite_slugs
                boats.append(formatted_boat)
                
                # (Кэш лодок в поиске отключён для ускорения)
                    
            except Exception as e:
                logger.warning(f"[Search View] Failed to format boat: {e}")
                continue
        
        logger.info(f"[Search View] Successfully formatted {len(boats)} boats")
        
        # Подготавливаем контекст для шаблона
        total_pages = search_results.get('totalPages', 0)
        total_results = search_results.get('total', 0)
        
        # Безопасность: проверяем что page не больше total_pages
        if total_pages > 0 and page > total_pages:
            page = total_pages
            logger.warning(f"[Search View] Page {page} exceeded total pages {total_pages}, adjusting")
        
        # Строка параметров для пагинации
        query_params = []
        if destination:
            query_params.append(f"destination={destination}")
        if category:
            query_params.append(f"category={category}")
        if check_in:
            query_params.append(f"check_in={check_in}")
        if check_out:
            query_params.append(f"check_out={check_out}")
        if cabins:
            query_params.append(f"cabins={cabins}")
        if year_from:
            query_params.append(f"year_from={year_from}")
        if year_to:
            query_params.append(f"year_to={year_to}")
        if price_from:
            query_params.append(f"price_from={price_from}")
        if price_to:
            query_params.append(f"price_to={price_to}")
        if sort:
            query_params.append(f"sort={sort}")
        search_query_str = "&" + "&".join(query_params) if query_params else ""
        
        # ⭐ Расчет количества дней аренды
        rental_days = None
        if check_in and check_out:
            try:
                from datetime import datetime
                check_in_date = datetime.strptime(check_in, '%Y-%m-%d').date()
                check_out_date = datetime.strptime(check_out, '%Y-%m-%d').date()
                rental_days = (check_out_date - check_in_date).days
                if rental_days <= 0:
                    rental_days = None
            except (ValueError, TypeError):
                rental_days = None
        
        # Вычисляем номера страниц для пагинации (все как int)
        previous_page = int(page - 1)
        next_page = int(page + 1)
        page_minus_2 = int(page - 2)
        page_minus_1 = int(page - 1)
        page_plus_1 = int(page + 1)
        page_plus_2 = int(page + 2)
        
        context = {
            'boats': boats,
            'total_results': total_results,
            'page': int(page),
            'total_pages': int(total_pages),
            'has_previous': page > 1,
            'has_next': page < total_pages if total_pages > 0 else False,
            'previous_page': previous_page,
            'next_page': next_page,
            'page_minus_2': page_minus_2,
            'page_minus_1': page_minus_1,
            'page_plus_1': page_plus_1,
            'page_plus_2': page_plus_2,
            'destination': destination,
            'category': category,
            'check_in': check_in,
            'check_out': check_out,
            'rental_days': rental_days,  # ⭐ Добавляем количество дней
            'sort': sort,
            'show_pagination': total_pages > 1,
            'search_query_str': search_query_str,
        }
        
        logger.info(f"[Search View] Final context: boats={len(boats)}, total_pages={total_pages}, page={page}, has_next={context['has_next']}")
        
        response = render(request, 'boats/search.html', context)
        # Отключаем кеширование для динамических результатов поиска
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response
        
    except Exception as e:
        logger.error(f"[Search View] Error during search: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        context = {
            'boats': [],
            'total_results': 0,
            'page': 1,
            'total_pages': 0,
            'has_previous': False,
            'has_next': False,
            'previous_page': 0,
            'next_page': 2,
            'destination': destination,
            'category': category,
            'check_in': check_in,
            'check_out': check_out,
            'rental_days': None,
            'sort': sort,
            'error_message': f'Ошибка при поиске: {str(e)}',
            'search_query_str': '',
        }
        return render(request, 'boats/search.html', context)



def autocomplete_api(request):
    """
    Гибридный API endpoint для автодополнения локаций
    Сначала ищет в локальном JSON, затем пробует внешний API
    Поддержка русского и английского языков
    """
    from django.http import JsonResponse
    import json
    import os
    from boats.boataround_api import BoataroundAPI
    
    query = request.GET.get('query', '').strip()
    
    if len(query) < 2:
        return JsonResponse({'success': True, 'data': []})
    
    query_lower = query.lower()
    
    # ==========================================
    # ШАГ 1: Локальный поиск в destinations.json
    # ==========================================
    json_path = os.path.join(os.path.dirname(__file__), 'destinations.json')
    local_results = []
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        destinations = data.get('data', [])
        
        # Поиск по всей иерархии
        for country in destinations:
            country_name = country.get('lang', '').lower()
            country_slug = country.get('search_slug', '')
            
            # Проверяем страну
            if query_lower in country_name:
                local_results.append({
                    'name': country.get('lang', ''),
                    'label': country.get('lang', ''),
                    'value': country_slug,
                    'slug': country_slug,
                    'country': country.get('lang', ''),
                    'type': 'country',
                    'boats': country.get('boats', 0)
                })
            
            # Проверяем регионы
            for region in country.get('regions', []):
                region_name = region.get('lang', '').lower()
                region_slug = region.get('search_slug', '')
                
                if query_lower in region_name:
                    local_results.append({
                        'name': region.get('lang', ''),
                        'label': f"{region.get('lang', '')}, {country.get('lang', '')}",
                        'value': region_slug,
                        'slug': region_slug,
                        'country': country.get('lang', ''),
                        'type': 'region',
                        'boats': region.get('boats', 0)
                    })
                
                # Проверяем города
                for city in region.get('cities', []):
                    city_name = city.get('lang', '').lower()
                    city_slug = city.get('search_slug', '')
                    
                    if query_lower in city_name:
                        local_results.append({
                            'name': city.get('lang', ''),
                            'label': f"{city.get('lang', '')}, {region.get('lang', '')}",
                            'value': city_slug,
                            'slug': city_slug,
                            'country': country.get('lang', ''),
                            'type': 'city',
                            'boats': city.get('boats', 0)
                        })
                    
                    # Проверяем марины
                    for marina in city.get('marinas', []):
                        marina_name = marina.get('_id', '').lower()
                        marina_slug = marina.get('search_slug', '')
                        
                        if query_lower in marina_name:
                            local_results.append({
                                'name': marina.get('_id', ''),
                                'label': f"{marina.get('_id', '')}, {city.get('lang', '')}",
                                'value': marina_slug,
                                'slug': marina_slug,
                                'country': country.get('lang', ''),
                                'type': 'marina',
                                'boats': marina.get('boats', 0)
                            })
            
            # Ограничиваем локальные результаты
            if len(local_results) >= 10:
                break
        
        # Если есть локальные результаты, возвращаем их
        if local_results:
            return JsonResponse({
                'success': True, 
                'data': local_results[:10],
                'source': 'local'
            })
                
    except Exception as e:
        print(f"Error in local search: {e}")
    
    # ==========================================
    # ШАГ 2: Fallback на внешний API
    # ==========================================
    try:
        # Пробуем оба языка
        print(f"[View Autocomplete] Trying API with query={query}")
        api_results_en = BoataroundAPI.autocomplete(query, language='en_EN', limit=10)
        print(f"[View Autocomplete] EN results: {len(api_results_en)}")
        
        api_results_ru = BoataroundAPI.autocomplete(query, language='ru_RU', limit=10)
        print(f"[View Autocomplete] RU results: {len(api_results_ru)}")
        
        # Объединяем результаты - ПРИОРИТЕТ РУССКИМ!
        combined = {}
        
        # Сначала добавляем английские (как fallback)
        for item in api_results_en:
            item_id = item.get('id', '')
            if item_id:
                expression = item.get('expression', '')
                clean_expression = expression.replace('<em>', '').replace('</em>', '')
                
                combined[item_id] = {
                    'name': item.get('name', ''),
                    'name_en': item.get('name_en', ''),
                    'label': clean_expression,
                    'value': item_id,
                    'slug': item_id,
                    'meta': item.get('meta', ''),
                    'country': item.get('meta', ''),
                    'type': item.get('type', 'location'),
                    'boats': item.get('total', 0),
                    'total': item.get('total', 0)
                }
        
        # Затем ПЕРЕЗАПИСЫВАЕМ русскими (если есть)
        for item in api_results_ru:
            item_id = item.get('id', '')
            if item_id:
                expression = item.get('expression', '')
                clean_expression = expression.replace('<em>', '').replace('</em>', '')
                
                # ПЕРЕЗАПИСЫВАЕМ английские данные русскими
                combined[item_id] = {
                    'name': item.get('name', ''),  # Это будет русское название!
                    'name_en': item.get('name_en', ''),
                    'label': clean_expression,
                    'value': item_id,
                    'slug': item_id,
                    'meta': item.get('meta', ''),
                    'country': item.get('meta', ''),
                    'type': item.get('type', 'location'),
                    'boats': item.get('total', 0),
                    'total': item.get('total', 0)
                }
        
        api_results = list(combined.values())[:10]
        print(f"[View Autocomplete] Final API results: {len(api_results)}")
        if api_results:
            print(f"[View Autocomplete] First result: {api_results[0]}")
        
        if api_results:
            return JsonResponse({
                'success': True, 
                'data': api_results,
                'source': 'api'
            })
        
    except Exception as e:
        print(f"Error in API search: {e}")
        import traceback
        print(traceback.format_exc())
    
    # ==========================================
    # ШАГ 3: Пустой результат
    # ==========================================
    return JsonResponse({
        'success': True, 
        'data': [],
        'source': 'none'
    })


def boat_detail(request, pk):
    """Детальная страница лодки"""
    boat = get_object_or_404(Boat, pk=pk)
    is_favorite = False
    user_review = None
    
    if request.user.is_authenticated:
        is_favorite = Favorite.objects.filter(user=request.user, boat=boat).exists()
        user_review = Review.objects.filter(boat=boat, user=request.user).first()
    
    # Средний рейтинг
    avg_rating = boat.reviews.aggregate(Avg('rating'))['rating__avg']
    reviews = boat.reviews.all()[:5]
    
    # Похожие лодки
    similar_boats = Boat.objects.filter(
        boat_type=boat.boat_type,
        available=True
    ).exclude(pk=pk)[:3]
    
    context = {
        'boat': boat,
        'is_favorite': is_favorite,
        'avg_rating': avg_rating,
        'reviews': reviews,
        'user_review': user_review,
        'similar_boats': similar_boats,
    }
    return render(request, 'boats/detail.html', context)


def boat_detail_api(request, boat_id):
    """
    Детальная страница лодки
    URL: /ru/boat/<slug>/?check_in=2026-02-21&check_out=2026-02-28

    Получаем данные из БД по slug
    """
    try:
        from django.core.cache import cache

        logger.info(f"[Boat Detail] Loading boat: {boat_id}")

        # Получаем даты из request
        check_in = request.GET.get('check_in', '')
        check_out = request.GET.get('check_out', '')
        has_url_dates = bool(check_in and check_out)  # Флаг - даты из URL или дефолтные
        rental_days = None

        # Рассчитываем количество дней
        if check_in and check_out:
            try:
                from datetime import datetime
                check_in_date = datetime.strptime(check_in, '%Y-%m-%d').date()
                check_out_date = datetime.strptime(check_out, '%Y-%m-%d').date()
                rental_days = (check_out_date - check_in_date).days
            except (ValueError, TypeError):
                rental_days = None

        logger.info(f"[Boat Detail] check_in={check_in}, check_out={check_out}, days={rental_days}, has_url_dates={has_url_dates}")

        # Получаем текущий язык
        current_lang = get_language()
        lang_map = {
            'ru': 'ru_RU',
            'en': 'en_EN',
            'de': 'de_DE',
            'es': 'es_ES',
            'fr': 'fr_FR',
        }
        db_lang = lang_map.get(current_lang, 'ru_RU')

        # --- Кэшированные данные лодки (БД, без цен) ---
        boat_cache_key = f'boat_data:{boat_id}:{db_lang}'
        boat_static = cache.get(boat_cache_key)

        if not boat_static:
            # Шаг 1: Ищем в БД по slug
            parsed_boat = ParsedBoat.objects.filter(slug=boat_id).first()

            if not parsed_boat:
                logger.info(f"[Boat Detail] Not in DB, parsing: {boat_id}")

                # Парсим через парсер (save_to_db=True сохранит в БД)
                boat_url = f'https://www.boataround.com/ru/yachta/{boat_id}/'
                boat_data_raw = parse_boataround_url(boat_url, save_to_db=True)

                if not boat_data_raw:
                    logger.error(f"[Boat Detail] Failed to parse boat: {boat_id}")
                    return render(request, 'boats/detail.html', {
                        'boat': None,
                        'error': 'Лодка не найдена',
                    })

                # Переполучаем ParsedBoat из БД
                parsed_boat = ParsedBoat.objects.filter(slug=boat_id).first()
                if not parsed_boat:
                    logger.error(f"[Boat Detail] ParsedBoat not found after parsing: {boat_id}")
                    return render(request, 'boats/detail.html', {
                        'boat': None,
                        'error': 'Ошибка при сохранении данных',
                    })

                logger.info(f"[Boat Detail] Parsed and cached: {boat_id}")

            # Автопривязка чартера
            from boats.boataround_api import BoataroundAPI
            if not parsed_boat.charter:
                try:
                    from boats.helpers import get_or_create_charter
                    search_boat = BoataroundAPI.search_by_slug(parsed_boat.slug)
                    if search_boat:
                        charter_obj = get_or_create_charter(
                            search_boat.get('charter'),
                            search_boat.get('charter_id'),
                            search_boat.get('charter_logo'),
                        )
                        if charter_obj:
                            parsed_boat.charter = charter_obj
                            parsed_boat.save(update_fields=['charter'])
                            logger.info(f"[Boat Detail] Auto-linked charter for {parsed_boat.slug}: {charter_obj.name} ({charter_obj.commission}%)")
                except Exception as charter_err:
                    logger.warning(f"[Boat Detail] Failed to auto-link charter for {parsed_boat.slug}: {charter_err}")

            # Получаем описание на текущем языке
            description = parsed_boat.descriptions.filter(language=db_lang).first()
            if not description:
                description = parsed_boat.descriptions.filter(language='ru_RU').first()

            gallery = parsed_boat.gallery.all()

            details = parsed_boat.details.filter(language=db_lang).first()
            if not details:
                details = parsed_boat.details.filter(language='ru_RU').first()

            tech_specs = parsed_boat.technical_specs

            boat_static = {
                'name': description.title if description else 'Неизвестная лодка',
                'title': description.title if description else '',
                'description': description.description if description else '',
                'location': description.location if description else '',
                'marina': description.marina if description else '',
                'country': description.country if description else '',
                'region': description.region if description else '',
                'city': description.city if description else '',

                'manufacturer': parsed_boat.manufacturer,
                'model': parsed_boat.model,
                'year': parsed_boat.year,
                'length': tech_specs.length if tech_specs else None,
                'beam': tech_specs.beam if tech_specs else None,
                'draft': tech_specs.draft if tech_specs else None,
                'cabins': tech_specs.cabins if tech_specs else None,
                'berths': tech_specs.berths if tech_specs else None,
                'toilets': tech_specs.toilets if tech_specs else None,
                'fuel_capacity': tech_specs.fuel_capacity if tech_specs else None,
                'water_capacity': tech_specs.water_capacity if tech_specs else None,
                'max_speed': tech_specs.max_speed if tech_specs else None,
                'engine_power': tech_specs.engine_power if tech_specs else None,
                'number_engines': tech_specs.number_engines if tech_specs else None,
                'engine_type': tech_specs.engine_type if tech_specs else '',
                'fuel_type': tech_specs.fuel_type if tech_specs else '',

                'images': [g.cdn_url for g in gallery],
                'gallery': [g.cdn_url for g in gallery],

                'extras': details.extras if details else [],
                'additional_services': details.additional_services if details else [],
                'delivery_extras': details.delivery_extras if details else [],
                'not_included': details.not_included if details else [],
                'cockpit': details.cockpit if details else [],
                'entertainment': details.entertainment if details else [],
                'equipment': details.equipment if details else [],

                'slug': parsed_boat.slug,
                'boat_id': parsed_boat.boat_id,
                '_charter_commission': parsed_boat.charter.commission if parsed_boat.charter else 0,
            }

            cache.set(boat_cache_key, boat_static, 60 * 60)  # 1 час
            logger.info(f"[Boat Detail] Cached boat data for {boat_id}")
        else:
            logger.info(f"[Boat Detail] Using cached data for {boat_id}")

        # --- Цены: всегда из API (зависят от дат) ---
        api_check_in = check_in
        api_check_out = check_out

        if not api_check_in or not api_check_out:
            from datetime import date, timedelta
            today = date.today()
            api_check_in = (today + timedelta(days=7)).strftime('%Y-%m-%d')
            api_check_out = (today + timedelta(days=14)).strftime('%Y-%m-%d')

        # Кэшируем цену по slug+даты на 15 минут
        price_cache_key = f'boat_price:{boat_id}:{api_check_in}:{api_check_out}'
        price_info = cache.get(price_cache_key)

        if not price_info:
            from boats.boataround_api import BoataroundAPI
            price_data = BoataroundAPI.get_price(
                slug=boat_static['slug'],
                check_in=api_check_in,
                check_out=api_check_out,
                currency='EUR',
                lang=db_lang
            )

            price = 0
            discount = 0
            total_price = 0
            if price_data:
                base_price = float(price_data.get('price', 0))
                discount_without_extra = float(price_data.get('discount_without_additionalExtra', 0))
                additional_discount = float(price_data.get('additional_discount', 0))
                discount = discount_without_extra

                from boats.helpers import calculate_final_price_with_discounts

                # Используем сохранённую комиссию чартера
                class _Charter:
                    commission = boat_static.get('_charter_commission', 0)

                total_price = calculate_final_price_with_discounts(
                    base_price, discount_without_extra, additional_discount,
                    _Charter() if _Charter.commission else None
                )
                price = base_price

            old_price = 0
            discount_percent = 0
            try:
                if price and total_price and float(price) > float(total_price):
                    old_price = float(price)
                    discount_percent = round((float(price) - float(total_price)) / float(price) * 100)
            except (ValueError, TypeError, ZeroDivisionError):
                pass

            price_info = {
                'price': price,
                'discount': discount,
                'total_price': total_price,
                'old_price': old_price,
                'discount_percent': discount_percent,
                'currency': 'EUR',
            }
            cache.set(price_cache_key, price_info, 60 * 15)  # 15 минут

        # Собираем boat_dict из кэшированных данных + цены
        boat_dict = {**boat_static, **price_info}
        boat_dict.pop('_charter_commission', None)

        # Передаем все в контекст
        context = {
            'boat': boat_dict,
            'check_in': check_in if has_url_dates else '',
            'check_out': check_out if has_url_dates else '',
            'rental_days': rental_days,
            'current_language': current_lang,
        }

        # Избранное — всегда из БД (персональное, не кэшируем)
        if request.user.is_authenticated:
            context['is_favorite'] = Favorite.objects.filter(
                user=request.user,
                boat_slug=boat_static['slug']
            ).exists()
        else:
            context['is_favorite'] = False

        logger.info(f"[Boat Detail] Rendering: {boat_dict.get('name', 'Unknown')}")
        return render(request, 'boats/detail.html', context)
        
    except Exception as e:
        logger.error(f"[Boat Detail] Error loading boat {boat_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        return render(request, 'boats/detail.html', {
            'boat': None,
            'error': f'Ошибка: {str(e)}',
        })


@login_required
def toggle_favorite(request, boat_slug):
    """Добавление/удаление из избранного (JSON API для Alpine.js)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    # Get or create ParsedBoat
    parsed_boat = ParsedBoat.objects.filter(slug=boat_slug).first()
    
    if not parsed_boat:
        return JsonResponse({'error': 'Лодка не найдена'}, status=404)
    
    boat_id = parsed_boat.boat_id
    
    # Try to find existing favorite
    favorite = Favorite.objects.filter(user=request.user, boat_slug=boat_slug).first()
    
    if favorite:
        # Remove from favorites
        favorite.delete()
        is_favorite = False
    else:
        # Add to favorites
        Favorite.objects.create(
            user=request.user,
            parsed_boat=parsed_boat,
            boat_slug=boat_slug,
            boat_id=boat_id
        )
        is_favorite = True
    
    return JsonResponse({
        'success': True,
        'is_favorite': is_favorite,
        'boat_slug': boat_slug
    })


@login_required
def favorites_list(request):
    """Список избранных лодок"""
    favorites = Favorite.objects.filter(user=request.user).select_related(
        'parsed_boat',
        'parsed_boat__technical_specs',
    ).prefetch_related('parsed_boat__descriptions', 'parsed_boat__gallery').order_by('-created_at')
    
    # Prepare favorites data for template
    favorites_data = []
    for fav in favorites:
        if not fav.parsed_boat:
            continue
            
        pb = fav.parsed_boat
        boat_info = {}
        image_url = None
        
        # Try to get data from boat_data first
        if pb.boat_data:
            boat_info = pb.boat_data.get('boat_info', {})
            images = pb.boat_data.get('images', [])
            image_url = images[0].get('thumb') if images else None
        
        # Get description (multilingual)
        lang = get_language().replace('-', '_')
        description = pb.descriptions.filter(language=lang).first()
        if not description:
            description = pb.descriptions.first()
        
        # Get specs
        specs = pb.technical_specs if hasattr(pb, 'technical_specs') else None
        
        # Get gallery image if no image from boat_data
        if not image_url:
            gallery_img = pb.gallery.first()
            image_url = gallery_img.cdn_url if gallery_img else None
        
        # Build title
        title = boat_info.get('title') or (description.title if description else None) or f"{pb.manufacturer} {pb.model}".strip()
        
        favorites_data.append({
            'favorite': fav,
            'slug': fav.boat_slug,
            'title': title,
            'location': boat_info.get('location') or (description.location if description else ''),
            'marina': boat_info.get('marina') or (description.marina if description else ''),
            'country': boat_info.get('country') or (description.country if description else ''),
            'year': boat_info.get('year') or pb.year or '',
            'length': boat_info.get('length') or (specs.length if specs else ''),
            'cabins': boat_info.get('cabins') or (specs.cabins if specs else ''),
            'berths': boat_info.get('berths') or (specs.berths if specs else ''),
            'image_url': image_url,
            'created_at': fav.created_at,
        })
    
    context = {
        'favorites': favorites,
        'favorites_data': favorites_data,
    }
    return render(request, 'boats/favorites.html', context)


@login_required
def create_booking(request, pk):
    """Создание бронирования"""
    boat = get_object_or_404(Boat, pk=pk)
    
    if request.method == 'POST':
        form = BookingForm(request.POST, boat=boat)
        if form.is_valid():
            booking = form.save(commit=False)
            booking.boat = boat
            booking.user = request.user
            
            # Расчет цены
            days = (booking.end_date - booking.start_date).days
            booking.total_price = boat.price_per_day * days
            
            booking.save()
            
            messages.success(request, 'Бронирование создано! Ожидайте подтверждения.')

            return redirect('boat_detail', pk=pk)
    else:
        form = BookingForm(boat=boat)
    
    context = {
        'form': form,
        'boat': boat,
    }

    return render(request, 'boats/booking.html', context)


@login_required
def my_bookings(request):
    """Мои бронирования (для туристов и менеджеров)"""
    user = request.user

    # Только менеджер видит все бронирования.
    # Все остальные роли видят только свои.
    from django.core.paginator import Paginator
    page_number = request.GET.get('page', 1)
    base_select = ('offer', 'offer__created_by', 'user', 'assigned_manager')

    if user.profile.role in ('manager', 'superadmin'):
        bookings_qs = Booking.objects.all().select_related(*base_select).order_by('-created_at')
        author_query = request.GET.get('author_q', '').strip()
        if author_query:
            bookings_qs = bookings_qs.filter(
                Q(offer__created_by__username__icontains=author_query)
                | Q(offer__created_by__email__icontains=author_query)
                | Q(offer__created_by__first_name__icontains=author_query)
                | Q(offer__created_by__last_name__icontains=author_query)
            )
        only_mine = request.GET.get('only_mine') == '1'
        if only_mine:
            bookings_qs = bookings_qs.filter(assigned_manager=user)
    else:
        bookings_qs = Booking.objects.filter(user=user).select_related(*base_select).order_by('-created_at')
        author_query = ''
        only_mine = False

    paginator = Paginator(bookings_qs, 15)
    bookings = paginator.get_page(page_number)

    # Предзагрузка превью для всех бронирований страницы (1 запрос вместо N)
    boat_ids = set()
    for b in bookings:
        if b.offer and b.offer.boat_data:
            bid = b.offer.boat_data.get('boat_id', '')
            if bid:
                boat_ids.add(bid)
    preview_map = dict(
        ParsedBoat.objects.filter(boat_id__in=list(boat_ids), preview_cdn_url__gt='')
        .values_list('boat_id', 'preview_cdn_url')
    ) if boat_ids else {}

    for b in bookings:
        bid = ''
        if b.offer and b.offer.boat_data:
            bid = b.offer.boat_data.get('boat_id', '')
        b._cached_preview = preview_map.get(bid)

    # Статистика
    total_bookings = bookings_qs.count()
    pending_bookings = bookings_qs.filter(status='pending').count()
    confirmed_bookings = bookings_qs.filter(status='confirmed').count()

    # Список менеджеров для суперадмина
    managers = []
    if user.profile.role == 'superadmin':
        from accounts.models import UserProfile
        managers = User.objects.filter(profile__role='manager').order_by('first_name', 'username')

    context = {
        'bookings': bookings,
        'total_bookings': total_bookings,
        'pending_bookings': pending_bookings,
        'confirmed_bookings': confirmed_bookings,
        'author_query': author_query,
        'only_mine': only_mine,
        'managers': managers,
    }
    return render(request, 'boats/my_bookings.html', context)


@login_required
def update_booking_status(request, booking_id):
    """Подтверждение/отмена бронирования (только manager). Отмена деактивирует оффер, но не удаляет его."""
    if request.user.profile.role != 'manager':
        messages.error(request, 'У вас нет прав для изменения статуса бронирования')
        return redirect('my_bookings')

    if request.method != 'POST':
        return redirect('my_bookings')

    booking = get_object_or_404(Booking, id=booking_id)
    action = request.POST.get('action', '').strip()
    next_url = request.POST.get('next', '')

    if action == 'confirm':
        booking.status = 'confirmed'
        booking.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Бронирование подтверждено')
    elif action == 'cancel':
        booking.status = 'cancelled'
        booking.save(update_fields=['status', 'updated_at'])
        if booking.offer:
            booking.offer.is_active = False
            booking.offer.save(update_fields=['is_active'])
        messages.success(request, 'Бронирование отменено. Оффер деактивирован (история сохранена).')
    else:
        messages.error(request, 'Некорректное действие')

    if next_url:
        return redirect(next_url)
    return redirect('my_bookings')


@login_required
def assign_booking_manager(request, booking_id):
    """Назначение ответственного менеджера на бронирование."""
    role = request.user.profile.role

    if role not in ('manager', 'superadmin'):
        messages.error(request, 'У вас нет прав для назначения менеджера')
        return redirect('my_bookings')

    if request.method != 'POST':
        return redirect('my_bookings')

    booking = get_object_or_404(Booking, id=booking_id)
    action = request.POST.get('action', '').strip()
    next_url = request.POST.get('next', '')

    if action == 'unassign':
        booking.assigned_manager = None
        booking.save(update_fields=['assigned_manager', 'updated_at'])
        messages.success(request, 'Менеджер снят с бронирования')
    elif action == 'assign_self':
        booking.assigned_manager = request.user
        booking.save(update_fields=['assigned_manager', 'updated_at'])
        messages.success(request, 'Вы назначены ответственным')
    elif action == 'assign' and role == 'superadmin':
        manager_id = request.POST.get('manager_id')
        if manager_id:
            from accounts.models import UserProfile
            manager = get_object_or_404(User, id=manager_id, profile__role='manager')
            booking.assigned_manager = manager
            booking.save(update_fields=['assigned_manager', 'updated_at'])
            messages.success(request, f'Менеджер {manager.get_full_name() or manager.username} назначен')
        else:
            messages.error(request, 'Менеджер не выбран')
    else:
        messages.error(request, 'Некорректное действие')

    if next_url:
        return redirect(next_url)
    return redirect('my_bookings')


@login_required
def delete_booking(request, booking_id):
    """Удаление бронирования (только для менеджеров и админов)"""
    if request.user.profile.role not in ['manager', 'admin']:
        messages.error(request, 'У вас нет прав для удаления бронирований')
        return redirect('my_bookings')
    
    booking = get_object_or_404(Booking, id=booking_id)
    
    if request.method == 'POST':
        boat_title = booking.boat_title
        user_name = booking.user.username
        booking.delete()
        messages.success(request, f'Бронирование "{boat_title}" пользователя {user_name} удалено')
        return redirect('my_bookings')
    
    return redirect('my_bookings')


@login_required
def manage_boats(request):
    """Управление лодками (для капитанов и агентов)"""
    if not request.user.profile.can_manage_boats():
        messages.error(request, 'У вас нет прав для доступа к этой странице')
        return redirect('home')
    
    if request.user.profile.is_admin_role:
        boats = Boat.objects.all()
    else:
        boats = Boat.objects.filter(owner=request.user)
    
    context = {
        'boats': boats,
    }
    return render(request, 'boats/manage_boats.html', context)


@login_required
def create_boat(request):
    """Создание лодки"""
    if not request.user.profile.can_manage_boats():
        messages.error(request, 'У вас нет прав для создания лодок')
        return redirect('home')
    
    if request.method == 'POST':
        form = BoatForm(request.POST, request.FILES)
        if form.is_valid():
            boat = form.save(commit=False)
            boat.owner = request.user
            boat.save()
            messages.success(request, 'Лодка успешно добавлена!')
            return redirect('manage_boats')
    else:
        form = BoatForm()
    
    context = {
        'form': form,
    }
    return render(request, 'boats/create_boat.html', context)


@login_required
def add_review(request, pk):
    """Добавление отзыва"""
    boat = get_object_or_404(Boat, pk=pk)
    
    # Проверка, что пользователь бронировал эту лодку
    has_booking = Booking.objects.filter(
        boat=boat,
        user=request.user,
        status='completed'
    ).exists()
    
    if not has_booking:
        messages.error(request, 'Вы можете оставить отзыв только после завершенного бронирования')
        return redirect('boat_detail', pk=pk)
    
    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            review, created = Review.objects.update_or_create(
                boat=boat,
                user=request.user,
                defaults={
                    'rating': form.cleaned_data['rating'],
                    'comment': form.cleaned_data['comment'],
                }
            )

            messages.success(request, 'Отзыв добавлен!')
            return redirect('boat_detail', pk=pk)
    else:
        form = ReviewForm()
    
    context = {
        'form': form,
        'boat': boat,
    }
    return render(request, 'boats/partials/review_form.html', context)


# =============================================================================
# ОФФЕРЫ
# =============================================================================

@login_required
def offers_stats_api(request):
    """API endpoint для получения актуальной статистики офферов"""
    from django.http import JsonResponse
    
    if not request.user.profile.can_create_offers():
        return JsonResponse({'error': 'Forbidden'}, status=403)
    
    if request.user.profile.role == 'admin':
        offers = Offer.objects.all()
    else:
        offers = Offer.objects.filter(created_by=request.user)
    
    offers_data = []
    for offer in offers:
        offers_data.append({
            'uuid': str(offer.uuid),
            'views_count': offer.views_count,
        })
    
    return JsonResponse({
        'offers': offers_data
    })


@login_required
def offers_list_api(request):
    """API endpoint для получения списка офферов"""
    from django.http import JsonResponse
    
    if not request.user.profile.can_create_offers():
        return JsonResponse({'error': 'Forbidden'}, status=403)
    
    if request.user.profile.role == 'admin':
        offers = Offer.objects.all()
    else:
        offers = Offer.objects.filter(created_by=request.user)
    
    # Prepare offers data for Alpine.js
    from boats.helpers import get_offer_boat_data
    from urllib.parse import urlparse
    
    offers_data = []
    for offer in offers:
        # Извлекаем slug из URL
        parsed_url = urlparse(offer.source_url)
        url_parts = parsed_url.path.strip('/').split('/')
        slug = url_parts[-1] if url_parts else None
        
        # Получаем данные лодки из новой структуры или старого boat_data
        if slug:
            boat_data = get_offer_boat_data(slug)
        else:
            boat_data = offer.boat_data or {}
        
        # Get first image from CDN
        pictures = boat_data.get('pictures', [])
        first_image = None
        if pictures:
            first_image = pictures[0]
        
        title = offer.title or boat_data.get('title') or boat_data.get('boat_info', {}).get('title', 'Без названия')
        
        # Получаем количество гостей из max_sleeps лодки
        guests = boat_data.get('max_sleeps', boat_data.get('berths', 0))
        
        offers_data.append({
            'uuid': str(offer.uuid),
            'title': title,
            'check_in': offer.check_in.strftime('%d.%m.%Y') if offer.check_in else '',
            'check_out': offer.check_out.strftime('%d.%m.%Y') if offer.check_out else '',
            'guests': guests,
            'total_price': float(offer.total_price),
            'original_price': float(offer.original_price) if offer.original_price else None,
            'discount': float(offer.discount),
            'currency': offer.currency,
            'is_active': offer.is_active,
            'show_countdown': offer.show_countdown,
            'views_count': offer.views_count,
            'created_at': offer.created_at.isoformat(),
            'image': first_image,
        })
    
    return JsonResponse({'offers': offers_data})


def offers_list(request):
    """Список офферов (для агентов/менеджеров/админов)"""
    if not request.user.profile.can_create_offers():
        messages.error(request, 'У вас нет прав для доступа к этой странице')
        return redirect('home')

    offers_qs = Offer.objects.filter(created_by=request.user)

    search_query = request.GET.get('q', '').strip()
    if search_query:
        offers_qs = offers_qs.filter(
            Q(title__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(source_url__icontains=search_query)
        )

    # Статистика по полному queryset (до пагинации)
    from django.db.models import Sum
    active_offers = offers_qs.filter(is_active=True).count()
    total_views = offers_qs.aggregate(total=Sum('views_count'))['total'] or 0

    # Пагинация
    from django.core.paginator import Paginator
    page_number = request.GET.get('page', 1)
    paginator = Paginator(offers_qs, 15)
    page_obj = paginator.get_page(page_number)

    # Подготавливаем данные для шаблона (только текущая страница)
    import re

    # Собираем все slug за один проход
    slug_pattern = re.compile(r'/(?:boat|yachta)/([^/?#]+)')
    offer_slugs = []
    for offer in page_obj:
        m = slug_pattern.search(offer.source_url)
        offer_slugs.append(m.group(1) if m else None)

    # Один запрос на все превью страницы
    valid_slugs = [s for s in offer_slugs if s]
    preview_map = dict(
        ParsedBoat.objects.filter(slug__in=valid_slugs, preview_cdn_url__gt='')
        .values_list('slug', 'preview_cdn_url')
    ) if valid_slugs else {}

    offers_with_data = []
    for offer, slug in zip(page_obj, offer_slugs):
        boat_data = offer.boat_data or {}
        title = offer.title or boat_data.get('title') or boat_data.get('boat_info', {}).get('title', 'Без названия')
        guests = boat_data.get('max_sleeps', boat_data.get('berths', 0))

        offer.image = preview_map.get(slug) if slug else None
        offer.guests = guests
        offer.title_display = title

        offers_with_data.append(offer)

    context = {
        'offers': offers_with_data,
        'page_obj': page_obj,
        'total_views': total_views,
        'active_offers': active_offers,
        'search_query': search_query,
    }
    return render(request, 'boats/offers_list.html', context)


@login_required
def create_offer(request):
    """Создание нового оффера"""
    import logging
    logger = logging.getLogger(__name__)

    def ajax_error(message, status=400, form=None):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            payload = {'success': False, 'message': message}
            if form is not None:
                payload['errors'] = form.errors
            return JsonResponse(payload, status=status)
        messages.error(request, message)
        if form is not None:
            return render(request, 'boats/create_offer.html', {'form': form})
        return redirect('home')
    
    if not request.user.profile.can_create_offers():
        return ajax_error('У вас нет прав для создания офферов', status=403)
    
    if request.method == 'POST':
        form = OfferForm(request.POST, user=request.user)
        if form.is_valid():
            source_url = form.cleaned_data['source_url']
            offer_type = form.cleaned_data['offer_type']

            if offer_type == 'tourist' and not request.user.profile.can_create_tourist_offers():
                return ajax_error('Туристический оффер могут создавать только менеджер и суперадмин', form=form)

            if offer_type == 'captain' and not request.user.profile.can_create_captain_offers():
                return ajax_error('У вас нет прав для создания агентского оффера', form=form)
            
            # Извлекаем slug из URL используя регулярное выражение
            # Поддерживает URLs вида: /ru/yachta/{slug}/ с query параметрами
            import re
            slug_pattern = re.compile(r'/(?:boat|yachta)/([^/?#]+)')
            slug_match = slug_pattern.search(source_url)
            slug = slug_match.group(1) if slug_match else None
            
            if not slug:
                return ajax_error('Не удалось извлечь информацию о лодке из URL. Проверьте формат URL.', form=form)
            
            # Получаем данные из новой структуры
            from boats.helpers import get_offer_boat_data
            boat_data = get_offer_boat_data(slug)
            
            # Убеждаемся что boat_data это словарь
            if not isinstance(boat_data, dict):
                boat_data = {}
            
            # Если лодка не в DB, пытаемся распарсить её
            if not boat_data:
                from boats.parser import parse_boataround_url
                import traceback
                try:
                    messages.info(request, 'Парсим данные о лодке...')
                    url = f'https://www.boataround.com/ru/yachta/{slug}/'
                    boat_data = parse_boataround_url(url, save_to_db=True)
                    if not boat_data:
                        return ajax_error('Не удалось загрузить данные о лодке с сайта', form=form)
                    messages.success(request, '✓ Лодка успешно добавлена в систему')
                except Exception as e:
                    error_msg = f'Ошибка парсинга: {str(e)}\n{traceback.format_exc()}'
                    logger.error(error_msg)
                    return ajax_error(f'Ошибка парсинга: {str(e)}', form=form)
            else:
                messages.info(request, '✓ Данные лодки загружены')
            
            # Извлекаем даты из source_url или формы
            import re
            check_in_match = re.search(r'checkIn=(\d{4}-\d{2}-\d{2})', source_url, re.IGNORECASE)
            check_out_match = re.search(r'checkOut=(\d{4}-\d{2}-\d{2})', source_url, re.IGNORECASE)
            
            if check_in_match and check_out_match:
                check_in = check_in_match.group(1)
                check_out = check_out_match.group(1)
            else:
                # Берем даты из формы если их нет в URL
                check_in_date = form.cleaned_data.get('check_in')
                check_out_date = form.cleaned_data.get('check_out')
                if check_in_date and check_out_date:
                    check_in = check_in_date.strftime('%Y-%m-%d')
                    check_out = check_out_date.strftime('%Y-%m-%d')
                else:
                    return ajax_error('Укажите даты заезда и выезда', form=form)
            
            # ВСЕГДА получаем цену через BoataroundAPI.get_price()
            from boats.boataround_api import BoataroundAPI
            
            logger.info(f'[Create Offer] Calling BoataroundAPI.get_price for slug={slug}, check_in={check_in}, check_out={check_out}')
            price_data = BoataroundAPI.get_price(
                slug=slug,
                check_in=check_in,
                check_out=check_out,
                currency='EUR',
                lang='ru_RU'
            )
            logger.info(f'[Create Offer] Price API response: {price_data}')
            
            if not price_data:
                logger.error(f'[Create Offer] API returned no price data!')
                return ajax_error('Не удалось получить цену из API', form=form)
            
            # Извлекаем цены из API ответа
            api_price = float(price_data.get('price', 0))
            discount_without_extra = float(price_data.get('discount_without_additionalExtra', 0))
            additional_discount = float(price_data.get('additional_discount', 0))
            
            # Используем discount_without_additionalExtra как правильную скидку
            api_discount = discount_without_extra
            
            # Рассчитываем финальную цену с учётом всех скидок и комиссии
            from boats.models import ParsedBoat
            from boats.helpers import calculate_final_price_with_discounts
            try:
                parsed_boat = ParsedBoat.objects.get(slug=slug)
                api_total_price = calculate_final_price_with_discounts(
                    api_price,
                    discount_without_extra,
                    additional_discount,
                    parsed_boat.charter
                )
                logger.info(f'[Create Offer] Prices - base: {api_price}, discount_wo_extra: {discount_without_extra}%, additional: {additional_discount}%, charter_commission: {parsed_boat.charter.commission if parsed_boat.charter else 0}%, final: {api_total_price}')
            except ParsedBoat.DoesNotExist:
                logger.warning(f'[Create Offer] ParsedBoat not found for slug={slug}, calculating without charter')
                # Рассчитываем без чартера
                api_total_price = calculate_final_price_with_discounts(
                    api_price,
                    discount_without_extra,
                    additional_discount,
                    None
                )
            
            # Сохраняем в boat_data для шаблона
            boat_data['price'] = api_price
            boat_data['discount'] = api_discount
            boat_data['totalPrice'] = api_total_price
            
            # Создаем оффер
            offer = form.save(commit=False)
            offer.created_by = request.user
            offer.source_url = source_url
            offer.offer_type = offer_type

            requested_branding_mode = request.POST.get('branding_mode', 'default')
            if requested_branding_mode == 'no_branding' and not request.user.profile.can_use_no_branding():
                requested_branding_mode = 'default'
            if requested_branding_mode == 'custom_branding' and not request.user.profile.can_use_custom_branding():
                requested_branding_mode = 'default'
            offer.branding_mode = requested_branding_mode
            
            # Конвертируем Decimal в float для JSON сохранения
            from decimal import Decimal
            def convert_decimals(obj):
                """Конвертирует Decimal в float рекурсивно"""
                if isinstance(obj, dict):
                    return {k: convert_decimals(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_decimals(item) for item in obj]
                elif isinstance(obj, Decimal):
                    return float(obj)
                return obj
            
            boat_data_json = convert_decimals(boat_data)
            
            # Убеждаемся что boat_data_json это словарь
            if not isinstance(boat_data_json, dict):
                logger.error(f"boat_data_json is not a dict: {type(boat_data_json)}")
                return ajax_error('Ошибка: неправильный формат данных лодки', form=form)
            
            # Нормализуем структуру для консистентности
            # Убедимся что есть поле 'images' для шаблона
            if 'images' not in boat_data_json and 'pictures' in boat_data_json:
                boat_data_json['images'] = boat_data_json['pictures']
            if 'images' not in boat_data_json and 'gallery' in boat_data_json:
                boat_data_json['images'] = boat_data_json['gallery']
            if 'images' not in boat_data_json:
                boat_data_json['images'] = []
            
            offer.boat_data = boat_data_json
            
            # Даты уже установлены из формы через form.save(commit=False)
            # Проверяем что они установлены
            if not offer.check_in or not offer.check_out:
                return ajax_error('Пожалуйста укажите даты заезда и выезда', form=form)
            
            # Цены из boat_data с расчётом по логике
            from boats.helpers import calculate_tourist_price
            
            # Расчитываем цену из API (не из базы!)
            if offer_type == 'tourist':
                # Берём значение has_meal из формы
                has_meal = form.cleaned_data.get('has_meal', False)
                
                price_info = calculate_tourist_price(
                    boat_data=boat_data,
                    check_in=offer.check_in,
                    check_out=offer.check_out,
                    dish=has_meal,
                    discount=0
                )
                logger.info(f"[Create Offer] Price calculation for tourist offer (meal={has_meal}): {price_info}")
                offer.total_price = price_info['total_price']
                offer.original_price = price_info['original_price']
                offer.discount = price_info['discount']
                offer.has_meal = has_meal
            else:
                # Для капитанского оффера используем цену из API
                offer.total_price = api_total_price if api_total_price else api_price
                offer.original_price = None
                offer.discount = api_discount
                offer.has_meal = False
            
            # Корректировка цены (наценка или скидка)
            price_adjustment = float(form.cleaned_data.get('price_adjustment') or 0)
            if price_adjustment:
                offer.price_adjustment = price_adjustment
                offer.total_price = float(offer.total_price) + price_adjustment
                logger.info(f'[Create Offer] Price adjustment: {price_adjustment}, adjusted total: {offer.total_price}')

            logger.info(f'[Create Offer] Final offer prices - total_price: {offer.total_price}, discount: {offer.discount}')

            offer.currency = boat_data.get('currency', 'EUR')
            
            # Заголовок
            if not offer.title:
                offer.title = boat_data.get('title', 'Аренда яхты')
            
            # Сохраняем оффер
            offer.save()
            
            offer_type_label = 'капитанский' if offer.is_captain_offer() else 'туристический'
            messages.success(request, f'✓ {offer_type_label.capitalize()} оффер успешно создан! UUID: {offer.uuid}')
            
            # Если это AJAX запрос - возвращаем JSON с UUID
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                from django.urls import reverse
                offer_url = reverse('offer_detail', kwargs={'uuid': str(offer.uuid)})
                return JsonResponse({
                    'success': True,
                    'uuid': str(offer.uuid),
                    'offer_url': offer_url,
                    'message': f'✓ {offer_type_label.capitalize()} оффер успешно создан!'
                })
            else:
                return redirect('offer_detail', uuid=offer.uuid)
        else:
            # Форма не валидна - логируем ошибки
            logger.error(f'Form errors in create_offer: {form.errors}')
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
            return ajax_error('Проверьте поля формы', form=form)
    else:
        # Проверяем есть ли данные для предзаполнения из сессии
        initial_data = {}
        prefill = request.session.pop('prefill_offer', None)
        if prefill:
            initial_data = prefill
        
        form = OfferForm(user=request.user, initial=initial_data)
    
    context = {
        'form': form,
    }
    return render(request, 'boats/create_offer.html', context)


def offer_detail(request, uuid):
    """Просмотр деталей оффера (публичный доступ по ссылке)"""
    offer = get_object_or_404(Offer, uuid=uuid)
    
    # Увеличиваем счетчик просмотров
    offer.increment_views()
    
    # Вычисляем отображаемую скидку от исходной цены в boat_data
    display_old_price = 0
    display_discount_percent = 0
    display_discount_amount = 0

    try:
        old_price_raw = offer.boat_data.get('price', 0) if isinstance(offer.boat_data, dict) else 0
        old_price = float(old_price_raw) if old_price_raw else 0
        final_price = float(offer.total_price) if offer.total_price else 0

        if old_price > 0 and final_price > 0 and old_price > final_price:
            display_old_price = old_price
            display_discount_amount = old_price - final_price
            display_discount_percent = round((display_discount_amount / old_price) * 100)
    except (TypeError, ValueError, ZeroDivisionError):
        display_old_price = 0
        display_discount_percent = 0
        display_discount_amount = 0

    # Данные таймера
    countdown_end_at = offer.expires_at
    if offer.show_countdown and not countdown_end_at:
        # Дедлайн по умолчанию: до конца следующего дня (23:59:59)
        created_local = timezone.localtime(offer.created_at)
        next_day = created_local.date() + timedelta(days=1)
        countdown_end_at = timezone.make_aware(
            datetime.combine(next_day, datetime.max.time().replace(microsecond=0))
        )

    show_countdown = bool(
        offer.show_countdown
        and countdown_end_at
        and countdown_end_at > timezone.now()
    )

    hide_site_branding = offer.branding_mode in ['no_branding', 'custom_branding']
    is_custom_branding = offer.branding_mode == 'custom_branding'
    can_view_internal_notes = request.user.is_authenticated and request.user == offer.created_by
    can_book_from_offer = request.user.is_authenticated and (
        request.user == offer.created_by or request.user.profile.role == 'manager'
    )

    context = {
        'offer': offer,
        'display_old_price': display_old_price,
        'display_discount_percent': display_discount_percent,
        'display_discount_amount': display_discount_amount,
        'show_countdown': show_countdown,
        'countdown_end_iso': countdown_end_at.isoformat() if countdown_end_at else '',
        'hide_site_branding': hide_site_branding,
        'is_custom_branding': is_custom_branding,
        'can_view_internal_notes': can_view_internal_notes,
        'can_book_from_offer': can_book_from_offer,
    }
    
    # Выбираем шаблон в зависимости от типа оффера
    template = 'boats/offer_captain.html' if offer.is_captain_offer() else 'boats/offer_tourist.html'
    return render(request, template, context)


@login_required
def offer_view(request, uuid):
    """Просмотр оффера клиентом (требуется регистрация)"""
    offer = get_object_or_404(Offer, uuid=uuid, is_active=True)
    
    # Увеличиваем счетчик просмотров
    offer.increment_views()
    
    # Подготавливаем данные для шаблона
    boat_data = offer.boat_data
    boat_info = boat_data.get('boat_info', {})
    prices = boat_data.get('prices', {})
    pictures = boat_data.get('pictures', [])
    extras = boat_data.get('extras', [])
    additional_services = boat_data.get('additional_services', [])
    not_included = boat_data.get('not_included', [])
    delivery_extras = boat_data.get('delivery_extras', [])
    
    # Формируем полные URL для картинок
    full_images = [get_full_image_url(pic) for pic in pictures]
    
    context = {
        'offer': offer,
        'boat_info': boat_info,
        'prices': prices,
        'images': full_images,
        'check_in': offer.check_in,
        'check_out': offer.check_out,
        'total_price': offer.total_price,
        'original_price': offer.original_price,
        'discount': offer.discount,
        'currency': offer.currency,
        'show_countdown': offer.show_countdown,
        'notifications': offer.notifications,
        # Дополнительно для капитанского оффера
        'extras': extras,
        'additional_services': additional_services,
        'not_included': not_included,
        'delivery_extras': delivery_extras,
        'hide_site_branding': offer.branding_mode in ['no_branding', 'custom_branding'],
        'is_custom_branding': offer.branding_mode == 'custom_branding',
        'can_view_internal_notes': request.user == offer.created_by,
        'can_book_from_offer': request.user == offer.created_by or request.user.profile.role == 'manager',
    }
    
    # Выбираем шаблон в зависимости от типа оффера
    template_name = offer.get_template_name()
    
    return render(request, template_name, context)


@login_required
def delete_offer(request, uuid):
    """Удаление оффера"""
    from django.http import JsonResponse
    
    offer = get_object_or_404(Offer, uuid=uuid)
    
    # Проверка прав
    if not (request.user == offer.created_by or request.user.profile.role == 'admin'):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'error': 'У вас нет прав для удаления этого оффера'}, status=403)
        messages.error(request, 'У вас нет прав для удаления этого оффера')
        return redirect('offers_list')
    
    if request.method == 'POST':
        offer.delete()
        
        # Если это AJAX запрос, вернуть JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Оффер удален'})
        
        # Иначе перенаправить
        messages.success(request, 'Оффер удален')
        return redirect('offers_list')
    
    return render(request, 'boats/offer_confirm_delete.html', {'offer': offer})


@login_required
def quick_create_offer(request, boat_slug):
    """Создание оффера напрямую по slug и датам"""
    import logging
    logger = logging.getLogger(__name__)
    
    if request.method != 'POST':
        return redirect('boat_detail_api', boat_id=boat_slug)
    
    if not request.user.profile.can_create_offers():
        messages.error(request, 'Нет прав')
        return redirect('boat_detail_api', boat_id=boat_slug)
    
    check_in = request.GET.get('check_in', '')
    check_out = request.GET.get('check_out', '')
    offer_type = request.POST.get('offer_type', 'captain')

    if offer_type == 'tourist' and not request.user.profile.can_create_tourist_offers():
        messages.error(request, 'Туристический оффер могут создавать только менеджер и суперадмин')
        return redirect('boat_detail_api', boat_id=boat_slug)

    if offer_type == 'captain' and not request.user.profile.can_create_captain_offers():
        messages.error(request, 'У вас нет прав для создания агентского оффера')
        return redirect('boat_detail_api', boat_id=boat_slug)

    if offer_type not in ['captain', 'tourist']:
        messages.error(request, 'Некорректный тип оффера')
        return redirect('boat_detail_api', boat_id=boat_slug)
    
    if not check_in or not check_out:
        messages.error(request, 'Укажите даты')
        return redirect('boat_detail_api', boat_id=boat_slug)
    
    try:
        # Формируем source_url
        source_url = f'https://www.boataround.com/ru/yachta/{boat_slug}/?checkIn={check_in}&checkOut={check_out}&currency=EUR'
        
        # Используем существующую логику из create_offer
        from boats.helpers import get_offer_boat_data
        boat_data = get_offer_boat_data(boat_slug)
        
        if not isinstance(boat_data, dict):
            boat_data = {}
        
        # Если лодка не в DB, парсим
        if not boat_data:
            from boats.parser import parse_boataround_url
            logger.info(f'Парсим лодку {boat_slug}')
            boat_data = parse_boataround_url(f'https://www.boataround.com/ru/yachta/{boat_slug}/', save_to_db=True)
            if not boat_data:
                messages.error(request, 'Не удалось загрузить данные лодки')
                return redirect('boat_detail_api', boat_id=boat_slug)
        
        # ВСЕГДА получаем цену из BoataroundAPI.get_price()
        from boats.boataround_api import BoataroundAPI
        
        logger.info(f'[Quick Offer] Calling BoataroundAPI.get_price for slug={boat_slug}, check_in={check_in}, check_out={check_out}')
        price_data = BoataroundAPI.get_price(
            slug=boat_slug,
            check_in=check_in,
            check_out=check_out,
            currency='EUR',
            lang='ru_RU'
        )
        logger.info(f'[Quick Offer] Price API response: {price_data}')
        
        if not price_data:
            logger.error(f'[Quick Offer] API returned no price data!')
            messages.error(request, 'Не удалось получить цену из API')
            return redirect('boat_detail_api', boat_id=boat_slug)
        
        # Извлекаем цены из API ответа
        api_price = float(price_data.get('price', 0))
        discount_without_extra = float(price_data.get('discount_without_additionalExtra', 0))
        additional_discount = float(price_data.get('additional_discount', 0))
        
        # Используем discount_without_additionalExtra как правильную скидку
        api_discount = discount_without_extra
        
        # Рассчитываем финальную цену с учётом всех скидок и комиссии
        from boats.models import ParsedBoat
        from boats.helpers import calculate_final_price_with_discounts
        try:
            parsed_boat = ParsedBoat.objects.get(slug=boat_slug)
            api_total_price = calculate_final_price_with_discounts(
                api_price,
                discount_without_extra,
                additional_discount,
                parsed_boat.charter
            )
            logger.info(f'[Quick Offer] Prices - base: {api_price}, discount_wo_extra: {discount_without_extra}%, additional: {additional_discount}%, charter_commission: {parsed_boat.charter.commission if parsed_boat.charter else 0}%, final: {api_total_price}')
        except ParsedBoat.DoesNotExist:
            logger.warning(f'[Quick Offer] ParsedBoat not found for slug={boat_slug}, calculating without charter')
            api_total_price = calculate_final_price_with_discounts(
                api_price,
                discount_without_extra,
                additional_discount,
                None
            )
        
        # Сохраняем в boat_data для шаблона
        boat_data['price'] = api_price
        boat_data['discount'] = api_discount
        boat_data['totalPrice'] = api_total_price
        
        # Создаем оффер
        from datetime import datetime
        offer = Offer()
        offer.created_by = request.user
        offer.source_url = source_url
        offer.offer_type = offer_type
        requested_branding_mode = request.POST.get('branding_mode', 'default')
        if requested_branding_mode == 'no_branding' and not request.user.profile.can_use_no_branding():
            requested_branding_mode = 'default'
        if requested_branding_mode == 'custom_branding' and not request.user.profile.can_use_custom_branding():
            requested_branding_mode = 'default'
        offer.branding_mode = requested_branding_mode
        offer.check_in = datetime.strptime(check_in, '%Y-%m-%d').date()
        offer.check_out = datetime.strptime(check_out, '%Y-%m-%d').date()
        
        # Конвертируем Decimal в float
        from decimal import Decimal
        def convert_decimals(obj):
            if isinstance(obj, dict):
                return {k: convert_decimals(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_decimals(item) for item in obj]
            elif isinstance(obj, Decimal):
                return float(obj)
            return obj
        
        boat_data_json = convert_decimals(boat_data)
        
        if 'images' not in boat_data_json and 'pictures' in boat_data_json:
            boat_data_json['images'] = boat_data_json['pictures']
        if 'images' not in boat_data_json and 'gallery' in boat_data_json:
            boat_data_json['images'] = boat_data_json['gallery']
        if 'images' not in boat_data_json:
            boat_data_json['images'] = []
        
        offer.boat_data = boat_data_json
        
        # Рассчитываем цену из API (не из базы!)
        from boats.helpers import calculate_tourist_price
        
        if offer_type == 'tourist':
            has_meal = request.POST.get('has_meal', '') == 'on'
            price_info = calculate_tourist_price(
                boat_data=boat_data,
                check_in=offer.check_in,
                check_out=offer.check_out,
                dish=has_meal,
                discount=0
            )
            offer.total_price = price_info['total_price']
            offer.original_price = price_info['original_price']
            offer.discount = price_info['discount']
            offer.has_meal = has_meal
        else:
            # Для капитанского оффера используем цену из API
            offer.total_price = api_total_price if api_total_price else api_price
            offer.original_price = None
            offer.discount = api_discount
            offer.has_meal = False
        
        logger.info(f'[Quick Offer] Final offer prices - total_price: {offer.total_price}, discount: {offer.discount}')
        
        offer.currency = boat_data.get('currency', 'EUR')
        offer.title = boat_data.get('title', f'Аренда яхты {boat_slug}')
        
        offer.save()
        
        messages.success(request, f'✅ Оффер создан!')
        return redirect('offer_detail', uuid=offer.uuid)
        
    except Exception as e:
        logger.error(f"Ошибка создания оффера: {e}", exc_info=True)
        messages.error(request, f'Ошибка: {str(e)}')
        return redirect('boat_detail_api', boat_id=boat_slug)


@login_required
def book_offer(request, uuid):
    """Создание бронирования из оффера (только автор оффера или менеджер)"""
    offer = get_object_or_404(Offer, uuid=uuid)
    
    # Только автор оффера или менеджер могут создать бронирование из оффера
    if not (request.user == offer.created_by or request.user.profile.role == 'manager'):
        messages.error(request, 'Бронирование из оффера доступно только автору оффера или менеджеру')
        return redirect('offer_detail', uuid=uuid)
    
    # Проверяем, что бронирование еще не создано этим пользователем
    existing_booking = Booking.objects.filter(offer=offer, user=request.user).first()
    if existing_booking:
        messages.info(request, 'Вы уже забронировали эту лодку')
        return redirect('my_bookings')
    
    if request.method == 'POST':
        # Создаем бронирование
        booking = Booking.objects.create(
            offer=offer,
            user=request.user,
            start_date=offer.check_in,
            end_date=offer.check_out,
            total_price=offer.total_price,
            currency=offer.currency,
            boat_data=offer.boat_data,
            status='pending',
            message=request.POST.get('message', '')
        )
        
        logger.info(f'[Booking] Created booking {booking.id} for user {request.user.username} - offer {offer.uuid}')
        messages.success(request, '✅ Бронирование создано! Ожидайте подтверждения от менеджера.')
        return redirect('my_bookings')
    
    # GET - показываем форму подтверждения
    context = {
        'offer': offer,
    }
    return render(request, 'boats/create_booking.html', context)


@login_required
def book_boat(request, boat_slug):
    """Создание бронирования напрямую из страницы лодки (для туристов)"""
    
    # Проверяем, что пользователь может бронировать
    if not request.user.profile.can_book_boats():
        messages.error(request, 'У вас нет прав для создания бронирования')
        return redirect('boat_detail_api', boat_id=boat_slug)
    
    if request.method != 'POST':
        messages.error(request, 'Неверный метод запроса')
        return redirect('boat_detail_api', boat_id=boat_slug)
    
    # Получаем даты из GET параметров
    check_in_str = request.GET.get('check_in')
    check_out_str = request.GET.get('check_out')
    
    if not check_in_str or not check_out_str:
        messages.error(request, 'Пожалуйста, укажите даты')
        return redirect('boat_detail_api', boat_id=boat_slug)
    
    try:
        from datetime import datetime
        check_in = datetime.strptime(check_in_str, '%Y-%m-%d').date()
        check_out = datetime.strptime(check_out_str, '%Y-%m-%d').date()
    except ValueError:
        messages.error(request, 'Неверный формат даты')
        return redirect('boat_detail_api', boat_id=boat_slug)
    
    # Получаем данные лодки из кэша
    parsed_boat = get_object_or_404(ParsedBoat, slug=boat_slug)
    
    # Получаем цену из API ТОЧНО ТАК ЖЕ как в boat_detail_api
    try:
        # Получаем текущий язык
        current_lang = get_language()
        lang_map = {
            'ru': 'ru_RU',
            'en': 'en_EN',
            'de': 'de_DE',
            'es': 'es_ES',
            'fr': 'fr_FR',
        }
        db_lang = lang_map.get(current_lang, 'ru_RU')
        
        logger.info(f"[Book Boat] Calling price API for slug={parsed_boat.slug}, check_in={check_in_str}, check_out={check_out_str}")
        price_data = BoataroundAPI.get_price(
            slug=parsed_boat.slug,
            check_in=check_in_str,
            check_out=check_out_str,
            currency='EUR',
            lang=db_lang
        )
        logger.info(f"[Book Boat] Price API response: {price_data}")
        
        if price_data:
            base_price = float(price_data.get('price', 0))
            discount_without_extra = float(price_data.get('discount_without_additionalExtra', 0))
            additional_discount = float(price_data.get('additional_discount', 0))
            
            # Рассчитываем финальную цену с учётом всех скидок и комиссии
            from boats.helpers import calculate_final_price_with_discounts
            total_price = calculate_final_price_with_discounts(
                base_price,
                discount_without_extra,
                additional_discount,
                parsed_boat.charter
            )
            
            currency = 'EUR'
            logger.info(f"[Book Boat] Calculated price - base: {base_price}, discount_wo_extra: {discount_without_extra}%, additional: {additional_discount}%, charter_commission: {parsed_boat.charter.commission if parsed_boat.charter else 0}%, final: {total_price}")
        else:
            logger.error(f"[Book Boat] API returned no price data!")
            total_price = 0
            currency = 'EUR'
    except Exception as e:
        logger.error(f'[Book Boat] Error getting price: {e}')
        total_price = 0
        currency = 'EUR'
    
    # Создаем бронирование БЕЗ копирования данных - используем связь
    booking = Booking.objects.create(
        offer=None,
        parsed_boat=parsed_boat,  # Ссылка на ParsedBoat вместо копирования
        user=request.user,
        start_date=check_in,
        end_date=check_out,
        total_price=total_price,
        currency=currency,
        status='pending',
        message=''
    )
    
    logger.info(f'[Booking] Created direct booking {booking.id} for user {request.user.username} - boat {boat_slug}')
    messages.success(request, '✅ Бронирование создано! Ожидайте подтверждения от менеджера.')
    return redirect('my_bookings')


def terms(request):
    return render(request, 'boats/terms.html')


def privacy(request):
    return render(request, 'boats/privacy.html')


def contacts(request):
    return render(request, 'boats/contacts.html')
