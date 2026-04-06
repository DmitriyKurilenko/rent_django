from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Avg
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import get_language, gettext as _
from django.utils import timezone
from datetime import datetime, timedelta
from urllib.parse import urlencode
from .models import Boat, Favorite, Booking, Review, Offer, ParsedBoat, BoatDescription, BoatDetails, Contract, ContractTemplate, Client, ContractOTP, BoatTechnicalSpecs
from .forms import SearchForm, BoatForm, BookingForm, ReviewForm, OfferForm, ContractCreateForm, ContractSignForm, ClientForm
from .parser import parse_boataround_url, get_full_image_url
from .boataround_api import BoataroundAPI
from .pricing import resolve_live_or_fallback_price
from django.views.decorators.cache import cache_page
import logging

logger = logging.getLogger(__name__)

LANG_TO_API = {
    'ru': 'ru_RU',
    'en': 'en_EN',
    'de': 'de_DE',
    'fr': 'fr_FR',
    'es': 'es_ES',
}

DESTINATION_SLUG_LABELS = {
    'turkey': 'Турция',
    'greece': 'Греция',
    'seychelles': 'Сейшелы',
    'croatia': 'Хорватия',
    'spain': 'Испания',
    'italy': 'Италия',
    'france': 'Франция',
}


def _request_lang_prefix(request) -> str:
    current = get_language() or ''
    if not current:
        current = request.LANGUAGE_CODE if hasattr(request, 'LANGUAGE_CODE') else ''
    return str(current).split('-')[0].lower() or 'ru'


def _request_api_lang(request) -> str:
    return LANG_TO_API.get(_request_lang_prefix(request), 'en_EN')


def _localized_destination_display(destination: str) -> str:
    slug = str(destination or '').strip().lower().lstrip('_')
    if not slug:
        return ''
    base_label = DESTINATION_SLUG_LABELS.get(slug)
    if base_label:
        return _(base_label)
    return destination


def _price_visibility_flags(user) -> dict:
    if not getattr(user, 'is_authenticated', False):
        return {
            'show_full_price_breakdown': False,
            'show_charter_commission_only': False,
        }

    role = getattr(getattr(user, 'profile', None), 'role', '')
    return {
        'show_full_price_breakdown': role in ('manager', 'admin', 'superadmin'),
        'show_charter_commission_only': role == 'captain',
    }


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
    destination_display = _localized_destination_display(destination)
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

    # Сохраняем сортировку пользователя в сессии, чтобы не выбирать каждый раз заново
    allowed_sorts = {'rank', 'priceUp', 'priceDown', 'discountDown'}
    sort_session_key = 'boat_search_sort'
    raw_sort = request.GET.get('sort')
    if raw_sort is not None:
        sort_candidate = raw_sort.strip()
        sort = sort_candidate if sort_candidate in allowed_sorts else 'rank'
        request.session[sort_session_key] = sort
    else:
        saved_sort = request.session.get(sort_session_key, 'rank')
        sort = saved_sort if saved_sort in allowed_sorts else 'rank'
    
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
            'destination_display': '',
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
            lang=_request_api_lang(request),
        )
        
        logger.info(f"[Search View] API returned: boats={len(search_results.get('boats', []))}, total={search_results.get('total', 0)}, pages={search_results.get('totalPages', 0)}")
        
        # Форматируем данные лодок
        from boats.models import Favorite, ParsedBoat

        boats = []
        # Получаем список избранных для текущего пользователя (если авторизован)
        favorite_slugs = set()
        if request.user.is_authenticated:
            favorite_slugs = set(Favorite.objects.filter(user=request.user).values_list('boat_slug', flat=True))

        # Один запрос к ParsedBoat на всю страницу:
        # - CDN-превью для карточек
        # - связанный чартер для консистентного расчёта цены
        api_boats = search_results.get('boats', [])
        slugs = [b.get('slug', '') for b in api_boats if b.get('slug')]
        preview_map = {}
        charter_map = {}
        if slugs:
            parsed_boats = (
                ParsedBoat.objects
                .select_related('charter')
                .filter(slug__in=slugs)
            )
            for parsed_boat in parsed_boats:
                if parsed_boat.preview_cdn_url:
                    preview_map[parsed_boat.slug] = parsed_boat.preview_cdn_url
                if parsed_boat.charter:
                    charter_map[parsed_boat.slug] = parsed_boat.charter

        # Защита от "скачков" цены в поиске:
        # переключаем отображаемую цену только после 4 одинаковых новых наблюдений подряд.
        # Приоритет: если кандидат дешевле — подтверждаем быстрее (3 наблюдения).
        CONSENSUS_HITS_DEFAULT = 5
        CONSENSUS_HITS_LOWER = 4  # меньше наблюдений если цена ниже

        def _to_float(value):
            try:
                if value in (None, ''):
                    return 0.0
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        def _snapshot_from_boat(item):
            return {
                'price': round(_to_float(item.get('price')), 2),
                'old_price': round(_to_float(item.get('old_price')), 2),
                'discount_percent': int(round(_to_float(item.get('discount_percent')))),
                'price_per_day': round(_to_float(item.get('price_per_day')), 2),
                'currency': str(item.get('currency') or 'EUR'),
                'price_breakdown': item.get('price_breakdown'),
            }

        def _same_snapshot(a, b):
            if not isinstance(a, dict) or not isinstance(b, dict):
                return False
            return (
                abs(_to_float(a.get('price')) - _to_float(b.get('price'))) < 0.01
                and abs(_to_float(a.get('old_price')) - _to_float(b.get('old_price'))) < 0.01
                and int(round(_to_float(a.get('discount_percent')))) == int(round(_to_float(b.get('discount_percent'))))
                and str(a.get('currency') or 'EUR') == str(b.get('currency') or 'EUR')
            )

        def _required_hits(candidate_snap, confirmed_snap):
            """Меньше наблюдений нужно если кандидат дешевле текущей подтверждённой цены."""
            if confirmed_snap and _to_float(candidate_snap.get('price')) < _to_float(confirmed_snap.get('price')):
                return CONSENSUS_HITS_LOWER
            return CONSENSUS_HITS_DEFAULT

        for boat in api_boats:
            try:
                slug = boat.get('slug', '')
                formatted_boat = format_boat_data(
                    boat,
                    charter_override=charter_map.get(slug)
                )

                if slug and check_in and check_out:
                    key = f"search_price_consensus:{slug}:{check_in}:{check_out}:{formatted_boat.get('currency', 'EUR')}"
                    state = cache.get(key) or {}
                    current = _snapshot_from_boat(formatted_boat)
                    confirmed = state.get('confirmed')
                    candidate = state.get('candidate')
                    candidate_hits = int(state.get('candidate_hits') or 0)

                    if confirmed:
                        if _same_snapshot(current, confirmed):
                            candidate = None
                            candidate_hits = 0
                            display = confirmed
                        else:
                            if _same_snapshot(current, candidate):
                                candidate_hits += 1
                            else:
                                candidate = current
                                candidate_hits = 1
                            needed = _required_hits(candidate or current, confirmed)
                            if candidate_hits >= needed:
                                confirmed = candidate or current
                                candidate = None
                                candidate_hits = 0
                            display = confirmed
                    else:
                        # Ещё нет подтверждённой цены — набираем консенсус
                        if _same_snapshot(current, candidate):
                            candidate_hits += 1
                        else:
                            candidate = current
                            candidate_hits = 1
                        if candidate_hits >= CONSENSUS_HITS_DEFAULT:
                            confirmed = current
                            candidate = None
                            candidate_hits = 0
                            display = confirmed
                        else:
                            # Показываем кандидата с наибольшим числом наблюдений,
                            # а не сырую цену API — это убирает скачки до подтверждения
                            display = candidate

                    state = {
                        'confirmed': confirmed,
                        'candidate': candidate,
                        'candidate_hits': candidate_hits,
                    }
                    cache.set(key, state, 60 * 60 * 6)

                    formatted_boat['price'] = display.get('price', formatted_boat.get('price', 0))
                    formatted_boat['old_price'] = display.get('old_price', formatted_boat.get('old_price', 0))
                    formatted_boat['discount_percent'] = display.get('discount_percent', formatted_boat.get('discount_percent', 0))
                    formatted_boat['price_per_day'] = display.get('price_per_day', formatted_boat.get('price_per_day', 0))
                    formatted_boat['currency'] = display.get('currency', formatted_boat.get('currency', 'EUR'))
                    if display.get('price_breakdown'):
                        formatted_boat['price_breakdown'] = display['price_breakdown']

                # Превью: CDN если есть, иначе thumb из API
                cdn_preview = preview_map.get(formatted_boat.get('slug', ''))
                formatted_boat['preview'] = cdn_preview or boat.get('thumb', '')

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
        query_params = {}
        if destination:
            query_params['destination'] = destination
        if category:
            query_params['category'] = category
        if check_in:
            query_params['check_in'] = check_in
        if check_out:
            query_params['check_out'] = check_out
        if cabins:
            query_params['cabins'] = cabins
        if year_from:
            query_params['year_from'] = year_from
        if year_to:
            query_params['year_to'] = year_to
        if price_from:
            query_params['price_from'] = price_from
        if price_to:
            query_params['price_to'] = price_to
        if sort:
            query_params['sort'] = sort
        search_query_str = "&" + urlencode(query_params) if query_params else ""
        
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
            'destination_display': destination_display,
            'category': category,
            'check_in': check_in,
            'check_out': check_out,
            'rental_days': rental_days,  # ⭐ Добавляем количество дней
            'sort': sort,
            'show_pagination': total_pages > 1,
            'search_query_str': search_query_str,
            **_price_visibility_flags(request.user),
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
            'destination_display': destination_display,
            'category': category,
            'check_in': check_in,
            'check_out': check_out,
            'rental_days': None,
            'sort': sort,
            'error_message': f'Ошибка при поиске: {str(e)}',
            'search_query_str': '',
            **_price_visibility_flags(request.user),
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
    preferred_api_lang = _request_api_lang(request)

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

    except Exception:
        logger.exception('[View Autocomplete] Local search failed for query=%r', query)

    # ==========================================
    # ШАГ 2: Fallback на внешний API
    # ==========================================
    api_results = []
    try:
        # Пробуем сначала язык текущей локали, затем en_EN как fallback
        logger.info('[View Autocomplete] Trying API with query=%s', query)
        api_results_primary = BoataroundAPI.autocomplete(query, language=preferred_api_lang, limit=10)
        logger.info(
            '[View Autocomplete] PRIMARY(%s) results: %s',
            preferred_api_lang,
            len(api_results_primary),
        )

        api_results_fallback = []
        if preferred_api_lang != 'en_EN':
            api_results_fallback = BoataroundAPI.autocomplete(query, language='en_EN', limit=10)
            logger.info('[View Autocomplete] EN fallback results: %s', len(api_results_fallback))

        # Объединяем результаты: приоритет текущему языку
        combined = {}

        for item in api_results_fallback:
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

        for item in api_results_primary:
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

        api_results = list(combined.values())[:10]
        logger.info('[View Autocomplete] Final API results: %s', len(api_results))
        if api_results:
            logger.debug('[View Autocomplete] First result payload: %s', api_results[0])

    except Exception:
        logger.exception('[View Autocomplete] API search failed for query=%r', query)

    # ==========================================
    # ШАГ 3: Сливаем API + local
    # ==========================================
    merged = []
    seen = set()
    for item in api_results + local_results:
        item_id = str(item.get('value') or item.get('slug') or item.get('name') or '')
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        merged.append(item)
        if len(merged) >= 10:
            break

    if merged:
        source = 'api' if api_results else 'local'
        return JsonResponse({'success': True, 'data': merged, 'source': source})

    # ==========================================
    # ШАГ 4: Пустой результат
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


def _ensure_boat_data_for_critical_flow(boat_slug, lang_code='ru_RU'):
    """
    Для detail/offer: если лодка есть в БД — возвращаем.
    Если нет — полный парсинг: API → HTML.
    """
    parsed_boat = ParsedBoat.objects.filter(slug=boat_slug).first()

    if parsed_boat:
        # Если specs нет — подтянем из API (одноразовая операция)
        if not BoatTechnicalSpecs.objects.filter(boat=parsed_boat).exists():
            _ensure_api_metadata_for_boat(parsed_boat)
        return parsed_boat, None

    # Лодки нет в БД — полный парсинг
    logger.info(f"[Boat Data] {boat_slug} not in DB, starting full parse")

    # --- Фаза 1: API metadata (specs, descriptions, charter) ---
    raw_boat = BoataroundAPI.search_by_slug(boat_slug, raw=True)
    if raw_boat:
        boat_id = raw_boat.get('_id') or raw_boat.get('id', '')
        parsed_boat, _ = ParsedBoat.objects.get_or_create(
            slug=boat_slug,
            defaults={'boat_id': boat_id or boat_slug, 'source_url': f'https://www.boataround.com/ru/yachta/{boat_slug}/'}
        )
        _ensure_api_metadata_for_boat(parsed_boat, raw_boat)

    # --- Фаза 2: HTML parsing (gallery, services, amenities, geo) ---
    boat_url = f'https://www.boataround.com/ru/yachta/{boat_slug}/'
    parsed_result = parse_boataround_url(boat_url, save_to_db=True)
    if not parsed_result:
        return None, (
            f"Критическая ошибка данных лодки {boat_slug}: "
            "не удалось получить данные из источника."
        )

    parsed_boat = ParsedBoat.objects.filter(slug=boat_slug).first()
    if not parsed_boat:
        return None, (
            f"Критическая ошибка данных лодки {boat_slug}: "
            "запись не была сохранена в БД после парсинга."
        )

    return parsed_boat, None


def _ensure_api_metadata_for_boat(parsed_boat, raw_boat=None):
    """
    Подтягивает BoatTechnicalSpecs и Charter из API для одной лодки.
    Использует _update_api_metadata из parse_boats_parallel (batch=1).
    """
    try:
        if not raw_boat:
            raw_boat = BoataroundAPI.search_by_slug(parsed_boat.slug, raw=True)
        if not raw_boat:
            logger.warning(f"[Boat Data] API returned no data for {parsed_boat.slug}, skipping API metadata")
            return

        api_meta = {
            parsed_boat.slug: {
                'country': raw_boat.get('country', ''),
                'region': raw_boat.get('region', ''),
                'city': raw_boat.get('city', ''),
                'marina': raw_boat.get('marina', ''),
                'title': raw_boat.get('title', ''),
                'location': raw_boat.get('location', '') or raw_boat.get('region', '') or raw_boat.get('country', ''),
                'flag': raw_boat.get('flag', ''),
                'coordinates': raw_boat.get('coordinates', []),
                'category': raw_boat.get('category', ''),
                'category_slug': raw_boat.get('category_slug', ''),
                'engine_type': raw_boat.get('engineType', ''),
                'sail': raw_boat.get('sail', ''),
                'reviews_score': raw_boat.get('reviewsScore'),
                'total_reviews': raw_boat.get('totalReviews'),
                'prepayment': raw_boat.get('prepayment'),
                'parameters': raw_boat.get('parameters', {}),
                'charter_name': raw_boat.get('charter', ''),
                'charter_id': raw_boat.get('charter_id', ''),
                'charter_logo': raw_boat.get('charter_logo', ''),
                'charter_rank': raw_boat.get('charter_rank', {}),
            }
        }

        from boats.management.commands.parse_boats_parallel import Command as PBPCommand
        PBPCommand._update_api_metadata(api_meta)
        logger.info(f"[Boat Data] API metadata updated for {parsed_boat.slug}")

    except Exception as e:
        logger.warning(f"[Boat Data] Failed to update API metadata for {parsed_boat.slug}: {e}")


def boat_detail_api(request, boat_id):
    """
    Детальная страница лодки
    URL: /ru/boat/<slug>/?check_in=2026-02-21&check_out=2026-02-28

    Получаем данные из БД по slug
    """
    try:
        from django.core.cache import cache
        from boats.helpers import HIDDEN_SERVICE_SLUGS

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

        parsed_boat, parse_error = _ensure_boat_data_for_critical_flow(boat_id, db_lang)
        if parse_error:
            logger.error(f"[Boat Detail] {parse_error} slug={boat_id}")
            return render(request, 'boats/detail.html', {
                'boat': {
                    'slug': boat_id,
                    'name': boat_id,
                    'images': [],
                    'gallery': [],
                    'total_price': 0,
                    'old_price': 0,
                    'discount_percent': 0,
                },
                'error': parse_error,
                'check_in': check_in if has_url_dates else '',
                'check_out': check_out if has_url_dates else '',
                'rental_days': rental_days,
                'current_language': current_lang,
                'is_favorite': False,
                **_price_visibility_flags(request.user),
            })

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
                        # Инвалидируем кэш, чтобы _charter_commission обновилась
                        cache.delete(f'boat_data:{boat_id}:{db_lang}')
                        logger.info(f"[Boat Detail] Auto-linked charter for {parsed_boat.slug}: {charter_obj.name} ({charter_obj.commission}%)")
            except Exception as charter_err:
                logger.warning(f"[Boat Detail] Failed to auto-link charter for {parsed_boat.slug}: {charter_err}")

        # --- Кэшированные данные лодки (БД, без цен) ---
        boat_cache_key = f'boat_data:{boat_id}:{db_lang}'
        boat_static = cache.get(boat_cache_key)
        if boat_static:
            cached_images = boat_static.get('images') or boat_static.get('gallery') or []
            has_required_cache_fields = (
                bool(boat_static.get('slug'))
                and bool(boat_static.get('name'))
                and bool(cached_images)
                and ('extras' in boat_static)
                and ('equipment' in boat_static)
            )
            if not has_required_cache_fields:
                logger.info(f"[Boat Detail] Cached boat data for {boat_id} is incomplete, invalidating cache")
                cache.delete(boat_cache_key)
                boat_static = None

        if not boat_static:
            # Получаем описание на текущем языке
            description = parsed_boat.descriptions.filter(language=db_lang).first()
            if not description:
                description = parsed_boat.descriptions.filter(language='ru_RU').first()

            gallery = parsed_boat.gallery.all()

            details = parsed_boat.details.filter(language=db_lang).first()
            if not details:
                details = parsed_boat.details.filter(language='ru_RU').first()

            try:
                tech_specs = parsed_boat.technical_specs
            except ParsedBoat.technical_specs.RelatedObjectDoesNotExist:
                tech_specs = None

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
                'additional_services': [s for s in (details.additional_services or []) if s.get('slug') not in HIDDEN_SERVICE_SLUGS] if details else [],
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

        slug = boat_static['slug']
        # Комиссия всегда из живого объекта БД, а не из кэша
        charter_commission = float(parsed_boat.charter.commission) if parsed_boat.charter else 0.0

        class _Charter:
            commission = charter_commission

        quote = resolve_live_or_fallback_price(
            slug=slug,
            check_in=api_check_in,
            check_out=api_check_out,
            lang=db_lang,
            charter=_Charter() if charter_commission else None,
            rental_days=rental_days,
            currency='EUR',
        )

        if quote.get('source') == 'db':
            logger.warning(
                f"[Boat Detail] Price API unavailable for {slug}, using DB fallback price "
                f"for {api_check_in}..{api_check_out}"
            )
        elif quote.get('source') == 'none':
            logger.warning(
                f"[Boat Detail] Price unavailable for {slug} ({api_check_in}..{api_check_out})"
            )

        price_info = {
            'price': quote.get('base_price', 0),
            'discount': quote.get('discount_without_extra', 0),
            'total_price': quote.get('final_price', 0),
            'old_price': quote.get('old_price', 0),
            'discount_percent': quote.get('discount_percent', 0),
            'currency': quote.get('currency', 'EUR'),
        }

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
            **_price_visibility_flags(request.user),
        }

        # Расшифровка цены видна только ролям с доступом к pricing debug.
        if context['show_full_price_breakdown'] or context['show_charter_commission_only']:
            charter_name = ''
            if parsed_boat and parsed_boat.charter:
                charter_name = parsed_boat.charter.name or ''
            context['price_breakdown'] = {
                'base_price': round(float(quote.get('base_price', 0)), 2),
                'discount_without_extra': round(float(quote.get('discount_without_extra', 0)), 2),
                'additional_discount': round(float(quote.get('additional_discount', 0)), 2),
                'charter_commission': round(charter_commission, 2),
                'charter_commission_amount': round(float(quote.get('charter_commission_amount', 0)), 2),
                'agent_commission': round(float(quote.get('agent_commission', 0)), 2),
                'extra_discount_applied': round(float(quote.get('extra_discount_applied', 0)), 2),
                'final_price': round(float(quote.get('final_price', 0)), 2),
                'charter_name': charter_name,
                'source': quote.get('source', ''),
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

    # Роли с view_all_bookings видят все бронирования.
    # Остальные роли видят только свои.
    from django.core.paginator import Paginator
    page_number = request.GET.get('page', 1)
    base_select = ('offer', 'offer__created_by', 'user', 'assigned_manager', 'client')

    if user.profile.can_see_all_bookings():
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
    import re
    slug_pattern = re.compile(r'/(?:boat|yachta)/([^/?#]+)')
    booking_slugs = {}
    for b in bookings:
        if b.offer and b.offer.source_url:
            m = slug_pattern.search(b.offer.source_url)
            if m:
                booking_slugs[b.pk] = m.group(1).rstrip('/')
    valid_slugs = list(set(booking_slugs.values()))
    preview_map = {}
    if valid_slugs:
        preview_map = dict(
            ParsedBoat.objects.filter(slug__in=valid_slugs)
            .exclude(preview_cdn_url='')
            .exclude(preview_cdn_url__isnull=True)
            .values_list('slug', 'preview_cdn_url')
        )
        logger.info(f'[Bookings] Slugs: {valid_slugs[:5]}... Preview found: {len(preview_map)}/{len(valid_slugs)}')

    for b in bookings:
        slug = booking_slugs.get(b.pk)
        b._cached_preview = preview_map.get(slug) if slug else None

    # Предзагрузка активных договоров (1 запрос)
    booking_ids = [b.pk for b in bookings]
    if booking_ids:
        active_contracts = {}
        for c in Contract.objects.filter(
            booking_id__in=booking_ids
        ).exclude(status__in=('rejected', 'expired')).order_by('-created_at'):
            if c.booking_id not in active_contracts:
                active_contracts[c.booking_id] = c
        for b in bookings:
            b.active_contract = active_contracts.get(b.pk)

    # Статистика
    total_bookings = bookings_qs.count()
    pending_bookings = bookings_qs.filter(status='pending').count()
    confirmed_bookings = bookings_qs.filter(status='confirmed').count()

    # Расшифровка цены для капитанов/менеджеров/админов
    booking_price_debug = {}
    show_price_debug = user.profile.role in ('captain', 'manager', 'admin', 'superadmin')
    if show_price_debug:
        for b in bookings:
            if b.offer:
                try:
                    booking_price_debug[b.pk] = _build_price_debug(b.offer)
                except Exception:
                    logger.exception('[Bookings] Failed to build price debug for booking_id=%s', b.pk)

    # Список менеджеров для суперадмина
    managers = []
    if user.profile.role == 'superadmin':
        from django.contrib.auth.models import User as AuthUser
        managers = AuthUser.objects.filter(profile__role_ref__codename='manager').order_by('first_name', 'username')

    context = {
        'bookings': bookings,
        'total_bookings': total_bookings,
        'pending_bookings': pending_bookings,
        'confirmed_bookings': confirmed_bookings,
        'author_query': author_query,
        'only_mine': only_mine,
        'managers': managers,
        'booking_price_debug': booking_price_debug,
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
            manager = get_object_or_404(User, id=manager_id, profile__role_ref__codename='manager')
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
def attach_client_to_booking(request, booking_id):
    """Привязать клиента к бронированию (AJAX POST)."""
    role = request.user.profile.role
    if role not in ('captain', 'manager', 'admin', 'superadmin'):
        return JsonResponse({'error': 'Нет прав'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    booking = get_object_or_404(Booking, id=booking_id)

    import json
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        data = request.POST

    client_id = data.get('client_id')
    action = data.get('action', 'attach')

    if action == 'detach':
        booking.client = None
        booking.save(update_fields=['client', 'updated_at'])
        return JsonResponse({'ok': True, 'client': None})

    if not client_id:
        return JsonResponse({'error': 'Не выбран клиент'}, status=400)

    if role in ('manager', 'admin', 'superadmin'):
        client = get_object_or_404(Client, id=client_id)
    else:
        client = get_object_or_404(Client, id=client_id, created_by=request.user)

    booking.client = client
    booking.save(update_fields=['client', 'updated_at'])

    return JsonResponse({
        'ok': True,
        'client': {
            'id': client.pk,
            'full_name': client.full_name,
            'phone': client.phone,
        },
    })


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


@login_required
def offers_list(request):
    """Список офферов (для агентов/менеджеров/админов)"""
    if not request.user.profile.can_create_offers():
        messages.error(request, 'У вас нет прав для доступа к этой странице')
        return redirect('home')

    if request.user.profile.role == 'admin':
        offers_qs = Offer.objects.all()
    else:
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
        m = slug_pattern.search(offer.source_url or '')
        offer_slugs.append(m.group(1).rstrip('/') if m else None)

    # Один запрос на все превью страницы
    valid_slugs = [s for s in offer_slugs if s]
    preview_map = {}
    if valid_slugs:
        # Диагностика: проверяем что лодки вообще есть в БД
        existing = list(
            ParsedBoat.objects.filter(slug__in=valid_slugs)
            .values_list('slug', 'preview_cdn_url')
        )
        logger.info(f'[Offers] DB lookup for slugs {valid_slugs[:3]}: {existing[:3]}')
        preview_map = {slug: url for slug, url in existing if url}
        logger.info(f'[Offers] Preview found: {len(preview_map)}/{len(valid_slugs)}')

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


def _build_boat_data_from_db(parsed_boat):
    """Собирает полный boat_data dict из ParsedBoat для сохранения в оффере."""
    from boats.helpers import HIDDEN_SERVICE_SLUGS
    desc = parsed_boat.descriptions.filter(language='ru_RU').first()
    try:
        tech = parsed_boat.technical_specs
    except Exception:
        tech = None
    details = parsed_boat.details.filter(language='ru_RU').first()

    return {
        'title': desc.title if desc else parsed_boat.model or parsed_boat.slug,
        'name': desc.title if desc else parsed_boat.model or parsed_boat.slug,
        'slug': parsed_boat.slug,
        'boat_id': parsed_boat.boat_id,
        'manufacturer': parsed_boat.manufacturer,
        'model': parsed_boat.model,
        'year': parsed_boat.year,
        'type': parsed_boat.boat_type if hasattr(parsed_boat, 'boat_type') else '',
        'location': desc.location if desc else '',
        'marina': desc.marina if desc else '',
        'country': desc.country if desc else '',
        'description': desc.description if desc else '',
        'currency': 'EUR',
        # Технические характеристики
        'length': float(tech.length) if tech and tech.length else None,
        'beam': float(tech.beam) if tech and tech.beam else None,
        'draft': float(tech.draft) if tech and tech.draft else None,
        'cabins': tech.cabins if tech else None,
        'berths': tech.berths if tech else None,
        'max_sleeps': tech.berths if tech else None,
        'toilets': tech.toilets if tech else None,
        'fuel': float(tech.fuel_capacity) if tech and tech.fuel_capacity else None,
        'water_tank': float(tech.water_capacity) if tech and tech.water_capacity else None,
        'maximum_speed': float(tech.max_speed) if tech and tech.max_speed else None,
        'engine': tech.engine_type if tech else '',
        'engine_power': float(tech.engine_power) if tech and tech.engine_power else None,
        'number_engines': tech.number_engines if tech else None,
        'engine_type': tech.engine_type if tech else '',
        'fuel_type': tech.fuel_type if tech else '',
        # Галерея
        'images': list(parsed_boat.gallery.values_list('cdn_url', flat=True)),
        # Детали (extras, equipment и т.д.)
        'extras': details.extras if details else [],
        'additional_services': [s for s in (details.additional_services or []) if s.get('slug') not in HIDDEN_SERVICE_SLUGS],
        'delivery_extras': details.delivery_extras if details else [],
        'not_included': details.not_included if details else [],
        'cockpit': details.cockpit if details else [],
        'entertainment': details.entertainment if details else [],
        'equipment': details.equipment if details else [],
    }


def _extract_slug_from_boat_url(url: str) -> str:
    """Извлекает slug лодки из boataround URL."""
    import re
    if not url:
        return ''
    match = re.search(r'/(?:boat|yachta)/([^/?#]+)', str(url))
    return match.group(1) if match else ''


def _hydrate_offer_boat_data_if_needed(offer):
    """
    Для старых офферов без фото в snapshot:
    подтягивает актуальные данные лодки из ParsedBoat и сохраняет в offer.boat_data.
    """
    boat_data = offer.boat_data if isinstance(offer.boat_data, dict) else {}
    images = boat_data.get('images') or boat_data.get('gallery') or boat_data.get('pictures') or []
    if images:
        return None

    slug = (
        boat_data.get('slug')
        or boat_data.get('boat_info', {}).get('slug')
        or _extract_slug_from_boat_url(offer.source_url)
    )
    if not slug:
        return 'Критическая ошибка оффера: не удалось определить slug лодки.'

    parsed_boat, parse_error = _ensure_boat_data_for_critical_flow(slug, 'ru_RU')
    if parse_error:
        return parse_error

    refreshed_data = _build_boat_data_from_db(parsed_boat)
    refreshed_images = refreshed_data.get('images') or []
    if not refreshed_images:
        return f'Критическая ошибка оффера: после обновления у лодки {slug} нет фото.'

    merged = dict(boat_data)
    for key, value in refreshed_data.items():
        merged[key] = value

    # Сохраняем ценовой snapshot оффера, если он уже был установлен.
    for price_key in ('price', 'discount', 'totalPrice'):
        if price_key in boat_data:
            merged[price_key] = boat_data[price_key]

    merged['slug'] = slug
    merged['images'] = refreshed_images
    merged['gallery'] = refreshed_images
    offer.boat_data = merged
    offer.save(update_fields=['boat_data', 'updated_at'])
    return None


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
            
            parsed_boat, parse_error = _ensure_boat_data_for_critical_flow(slug, 'ru_RU')
            if parse_error:
                logger.error(f"[Create Offer] {parse_error} slug={slug}")
                return ajax_error(parse_error, form=form)

            boat_data = _build_boat_data_from_db(parsed_boat)
            logger.info(f'[Create Offer] Boat data from DB for {slug}')
            
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
            
            charter = parsed_boat.charter if parsed_boat else None

            rental_days = None
            try:
                rental_days = max(
                    (datetime.strptime(check_out, '%Y-%m-%d').date() - datetime.strptime(check_in, '%Y-%m-%d').date()).days,
                    1
                )
            except (ValueError, TypeError):
                rental_days = None

            quote = resolve_live_or_fallback_price(
                slug=slug,
                check_in=check_in,
                check_out=check_out,
                lang='ru_RU',
                charter=charter,
                rental_days=rental_days,
                currency='EUR',
            )

            if quote.get('source') == 'none':
                logger.error(f'[Create Offer] Price unavailable for slug={slug} ({check_in}..{check_out})')
                return ajax_error('Не удалось получить цену: нет данных API и fallback из БД', form=form)

            api_price = float(quote.get('base_price', 0))
            api_discount = float(quote.get('discount_without_extra', 0))
            api_total_price = float(quote.get('final_price', 0))

            logger.info(
                f"[Create Offer] Unified price quote source={quote.get('source')} slug={slug} "
                f"base={api_price} discount={api_discount}% total={api_total_price}"
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
            
            if boat_data_json.get('description'):
                boat_data_json['description'] = _strip_last_sentence(boat_data_json['description'])
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
                offer.price_captain = price_info['price_captain']
                offer.price_fuel = price_info['price_fuel']
                offer.price_moorings = price_info['price_moorings']
                offer.price_transit_cleaning = price_info['price_transit_cleaning']
                offer.price_trips_markup = price_info['price_trips_markup']
            else:
                # Для капитанского оффера используем цену из API
                offer.total_price = api_total_price if api_total_price else api_price
                offer.original_price = None
                offer.discount = api_discount
                offer.has_meal = False
            
            # Корректировка цены (наценка или скидка)
            from decimal import Decimal
            price_adjustment = form.cleaned_data.get('price_adjustment') or Decimal('0')
            if price_adjustment:
                offer.price_adjustment = price_adjustment
                offer.total_price = Decimal(str(offer.total_price)) + Decimal(str(price_adjustment))
                logger.info(f'[Create Offer] Price adjustment: {price_adjustment}, adjusted total: {offer.total_price}')

            logger.info(f'[Create Offer] Final offer prices - total_price: {offer.total_price}, discount: {offer.discount}')

            offer.currency = boat_data.get('currency', 'EUR')
            
            # Заголовок — производитель + модель (например "Bali 4.2")
            if not offer.title:
                manufacturer = boat_data.get('manufacturer', '')
                model = boat_data.get('model', '')
                offer.title = ' '.join(filter(None, [manufacturer, model])) or boat_data.get('title', 'Аренда яхты')
            
            # Сохраняем оффер
            # Привязка клиента
            client_id = request.POST.get('client_id')
            if client_id:
                try:
                    offer.client = Client.objects.get(pk=int(client_id))
                except (Client.DoesNotExist, ValueError):
                    pass
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
    data_error = _hydrate_offer_boat_data_if_needed(offer)
    if data_error:
        logger.error(f"[Offer Detail] {data_error} offer={offer.uuid}")
    
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
        'data_error': data_error,
    }

    if request.user.is_authenticated and request.user.profile.role in ('manager', 'admin', 'superadmin'):
        context['price_debug'] = _build_price_debug(offer)

    # Выбираем шаблон в зависимости от типа оффера
    template = 'boats/offer_captain.html' if offer.is_captain_offer() else 'boats/offer_tourist.html'
    return render(request, template, context)


def _strip_last_sentence(text: str) -> str:
    """Убирает последнее предложение из текста (обычно содержит название чартера)."""
    import re
    text = text.strip()
    # Ищем последнюю границу предложения: точка/восклицание/вопрос + пробел/конец строки/перенос
    matches = list(re.finditer(r'[.!?][\s\n]+', text))
    if not matches:
        return text
    last = matches[-1]
    return text[:last.end()].rstrip()


def _build_price_debug(offer):
    """Разбивка формулы цены для отладки."""
    from boats.models import PriceSettings, ParsedBoat

    cfg = PriceSettings.get_settings()
    bd = offer.boat_data
    adjustment = float(offer.price_adjustment or 0)

    # Комиссия чартера и агентская комиссия
    charter_commission = 0.0
    charter_commission_amount = 0.0
    agent_commission = 0.0
    agent_pct = float(cfg.agent_commission_pct) / 100.0
    try:
        import re
        slug_match = re.search(r'/(?:boat|yachta)/([^/?#]+)', offer.source_url or '')
        if slug_match:
            pb = ParsedBoat.objects.select_related('charter').filter(slug=slug_match.group(1).rstrip('/')).first()
            if pb and pb.charter and pb.charter.commission:
                charter_commission = float(pb.charter.commission)
                charter_commission_amount = round(float(offer.total_price) * charter_commission / 100, 2)
                agent_commission = round(charter_commission_amount * agent_pct, 2)
    except Exception:
        logger.exception('[Price Debug] Failed to resolve charter commission for offer=%s', offer.pk)

    if offer.is_captain_offer():
        api_price = float(bd.get('price', 0))
        discount_wo_extra_pct = float(bd.get('discount', 0))
        additional_discount_pct = float(bd.get('additional_discount', 0))
        api_total = float(bd.get('totalPrice', 0))
        total_discount = discount_wo_extra_pct + additional_discount_pct
        after_dwe = round(api_price * (1 - total_discount / 100), 2) if total_discount else api_price
        return {
            'type': 'captain',
            'api_price': api_price,
            'discount_wo_extra_pct': discount_wo_extra_pct,
            'additional_discount_pct': additional_discount_pct,
            'after_discount_wo_extra': after_dwe,
            'api_total': api_total,
            'extra_discount_max': float(cfg.extra_discount_max),
            'charter_commission': charter_commission,
            'charter_commission_amount': charter_commission_amount,
            'agent_commission': agent_commission,
            'adjustment': adjustment,
            'total_price': float(offer.total_price),
        }

    # Tourist
    api_total = float(bd.get('totalPrice', 0))
    country = bd.get('country', '').lower()
    location = bd.get('location', '').lower()
    marina = bd.get('marina', '').lower()
    # category: разные ключи в зависимости от источника данных
    category = bd.get('category', '') or bd.get('type', '') or ''
    # параметры могут быть вложены в 'parameters' (API/парсер) или плоско (DB)
    params = bd.get('parameters', {}) or {}
    length = float(params.get('length', 0) or bd.get('length', 0) or 0)
    double_cabins = int(params.get('double_cabins', 0) or bd.get('double_cabins', 0) or 0)
    max_sleeps = int(
        params.get('max_sleeps', 0) or params.get('berths', 0)
        or bd.get('max_sleeps', 0) or bd.get('berths', 0) or 0
    )

    # Dynamic country config lookup
    from boats.helpers import _resolve_country_config
    cc = _resolve_country_config(cfg, country, location, marina)
    if cc is None:
        return {'type': 'tourist', 'error': 'no country configs'}
    country_label = cc.country_name

    insurance_rate = float(cc.insurance_rate)
    insurance_min = float(cc.insurance_min)
    insurance = round(max(api_total * insurance_rate, insurance_min), 2)

    price_captain = float(cc.captain)
    price_fuel = float(cc.fuel)
    price_moorings = float(cc.moorings)
    price_transit_cleaning = float(cc.transit_cleaning)
    price_trips_markup = float(cc.trips_markup)

    base_components_total = price_captain + price_fuel + price_moorings + price_transit_cleaning + price_trips_markup

    max_double_free = int(cc.max_double_cabins_free)
    double_cabin_extra = float(cc.double_cabin_extra)
    extra_cabins_count = max(double_cabins - max_double_free, 0)
    extra_cabins = round(extra_cabins_count * double_cabin_extra, 2)

    praslin = float(cc.praslin_extra) if marina == 'praslin marina' else 0

    length_extra_val = float(cc.length_extra)
    length_extra = length_extra_val if length > 14.2 else 0

    cat_sail_extra = 0
    cat_sail_note = ''
    if length > 13.8:
        if category == 'Катамаран':
            cat_sail_extra = float(cc.catamaran_length_extra)
            cat_sail_note = 'катамаран'
        elif category == 'Парусная Яхта':
            cat_sail_extra = float(cc.sailing_length_extra)
            cat_sail_note = 'парусная яхта'

    food = 0
    food_formula = ''
    dish_base = float(cc.dish_base)
    if offer.has_meal and max_sleeps > 0:
        cook = float(cc.cook_price)
        food = round((max_sleeps - 2) * dish_base + cook, 2)
        food_formula = f'({max_sleeps} − 2) × {dish_base} + {cook}'

    subtotal = round(
        api_total + insurance + extra_cabins + base_components_total
        + praslin + length_extra + cat_sail_extra + food, 2
    )

    return {
        'type': 'tourist',
        'country': bd.get('country', '') or '—',
        'country_label': country_label,
        'marina': bd.get('marina', '') or '—',
        'category': category or '—',
        'length': length,
        'double_cabins': double_cabins,
        'max_sleeps': max_sleeps,
        'has_meal': offer.has_meal,
        # шаги
        'api_total': api_total,
        'insurance': insurance,
        'insurance_formula': f'max({api_total} × {round(insurance_rate*100,1)}%, {insurance_min})',
        'extra_cabins': extra_cabins,
        'extra_cabins_formula': f'{extra_cabins_count} × {double_cabin_extra}' if extra_cabins else '—',
        'price_captain': price_captain,
        'price_fuel': price_fuel,
        'price_moorings': price_moorings,
        'price_transit_cleaning': price_transit_cleaning,
        'price_trips_markup': price_trips_markup,
        'base_components_total': base_components_total,
        'base_country_label': country_label,
        'praslin': praslin,
        'length_extra': length_extra,
        'turkey_length_extra': cat_sail_extra,
        'turkey_length_note': cat_sail_note,
        'food': food,
        'food_formula': food_formula or '—',
        'subtotal': subtotal,
        'charter_commission': charter_commission,
        'charter_commission_amount': charter_commission_amount,
        'agent_commission': agent_commission,
        'adjustment': adjustment,
        'total_price': float(offer.total_price),
    }


@login_required
def offer_view(request, uuid):
    """Просмотр оффера клиентом (требуется регистрация)"""
    offer = get_object_or_404(Offer, uuid=uuid, is_active=True)
    
    # Увеличиваем счетчик просмотров
    offer.increment_views()
    
    # Подготавливаем данные для шаблона
    from boats.helpers import HIDDEN_SERVICE_SLUGS
    boat_data = offer.boat_data
    boat_info = boat_data.get('boat_info', {})
    prices = boat_data.get('prices', {})
    pictures = boat_data.get('pictures', [])
    extras = boat_data.get('extras', [])
    additional_services = [s for s in boat_data.get('additional_services', []) if s.get('slug') not in HIDDEN_SERVICE_SLUGS]
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

        parsed_boat, parse_error = _ensure_boat_data_for_critical_flow(boat_slug, 'ru_RU')
        if parse_error:
            logger.error(f"[Quick Offer] {parse_error} slug={boat_slug}")
            messages.error(request, parse_error)
            return redirect('boat_detail_api', boat_id=boat_slug)
        boat_data = _build_boat_data_from_db(parsed_boat)
        logger.info(f'[Quick Offer] Boat data from DB for {boat_slug}')
        
        rental_days = None
        try:
            rental_days = max(
                (datetime.strptime(check_out, '%Y-%m-%d').date() - datetime.strptime(check_in, '%Y-%m-%d').date()).days,
                1
            )
        except (ValueError, TypeError):
            rental_days = None

        quote = resolve_live_or_fallback_price(
            slug=boat_slug,
            check_in=check_in,
            check_out=check_out,
            lang='ru_RU',
            charter=parsed_boat.charter if parsed_boat else None,
            rental_days=rental_days,
            currency='EUR',
        )
        if quote.get('source') == 'none':
            logger.error(f'[Quick Offer] Price unavailable for slug={boat_slug} ({check_in}..{check_out})')
            messages.error(request, 'Не удалось получить цену: нет данных API и fallback из БД')
            return redirect('boat_detail_api', boat_id=boat_slug)

        api_price = float(quote.get('base_price', 0))
        api_discount = float(quote.get('discount_without_extra', 0))
        api_total_price = float(quote.get('final_price', 0))
        logger.info(
            f"[Quick Offer] Unified price quote source={quote.get('source')} slug={boat_slug} "
            f"base={api_price} discount={api_discount}% total={api_total_price}"
        )
        
        # Сохраняем в boat_data для шаблона
        boat_data['price'] = api_price
        boat_data['discount'] = api_discount
        boat_data['totalPrice'] = api_total_price
        
        # Создаем оффер
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

        if boat_data_json.get('description'):
            boat_data_json['description'] = _strip_last_sentence(boat_data_json['description'])
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
            offer.price_captain = price_info['price_captain']
            offer.price_fuel = price_info['price_fuel']
            offer.price_moorings = price_info['price_moorings']
            offer.price_transit_cleaning = price_info['price_transit_cleaning']
            offer.price_trips_markup = price_info['price_trips_markup']
        else:
            # Для капитанского оффера используем цену из API
            offer.total_price = api_total_price if api_total_price else api_price
            offer.original_price = None
            offer.discount = api_discount
            offer.has_meal = False
        
        # Корректировка цены
        from decimal import Decimal
        price_adjustment = Decimal(str(request.POST.get('price_adjustment', 0) or 0))
        if price_adjustment:
            offer.price_adjustment = price_adjustment
            offer.total_price = Decimal(str(offer.total_price)) + price_adjustment

        logger.info(f'[Quick Offer] Final offer prices - total_price: {offer.total_price}, discount: {offer.discount}, adjustment: {price_adjustment}')

        offer.currency = boat_data.get('currency', 'EUR')
        manufacturer = boat_data.get('manufacturer', '')
        model = boat_data.get('model', '')
        offer.title = ' '.join(filter(None, [manufacturer, model])) or boat_data.get('title', f'Аренда яхты {boat_slug}')
        
        client_id = request.POST.get('client_id')
        if client_id:
            try:
                offer.client = Client.objects.get(pk=int(client_id), created_by=request.user)
            except (Client.DoesNotExist, ValueError, TypeError):
                pass
        
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
            message=request.POST.get('message', ''),
            client=offer.client,
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
    
    # Единый расчет цены (API -> fallback DB), как в detail/offers.
    current_lang = get_language()
    lang_map = {
        'ru': 'ru_RU',
        'en': 'en_EN',
        'de': 'de_DE',
        'es': 'es_ES',
        'fr': 'fr_FR',
    }
    db_lang = lang_map.get(current_lang, 'ru_RU')
    rental_days = max((check_out - check_in).days, 1)

    quote = resolve_live_or_fallback_price(
        slug=parsed_boat.slug,
        check_in=check_in_str,
        check_out=check_out_str,
        lang=db_lang,
        charter=parsed_boat.charter,
        rental_days=rental_days,
        currency='EUR',
    )
    total_price = float(quote.get('final_price', 0))
    currency = quote.get('currency', 'EUR')

    if total_price <= 0:
        logger.error(
            f"[Book Boat] Price unavailable for booking slug={parsed_boat.slug} "
            f"({check_in_str}..{check_out_str}), source={quote.get('source')}"
        )
        messages.error(request, 'Не удалось рассчитать стоимость бронирования. Попробуйте позже.')
        return redirect('boat_detail_api', boat_id=boat_slug)
    
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


# ────────────────────────────────────────────────────────────
# Договоры
# ────────────────────────────────────────────────────────────

@login_required
def create_contract(request, booking_id):
    """Создание договора для бронирования (менеджер/капитан)."""
    booking = get_object_or_404(Booking, id=booking_id)

    if not request.user.profile.role in ('captain', 'manager', 'admin', 'superadmin'):
        messages.error(request, 'У вас нет прав для создания договоров')
        return redirect('my_bookings')

    # Проверка что для этого бронирования ещё нет активного договора
    existing = Contract.objects.filter(booking=booking).exclude(status__in=('rejected', 'expired')).first()
    if existing:
        messages.info(request, f'Договор {existing.contract_number} уже создан для этого бронирования')
        return redirect('contract_detail', uuid=existing.uuid)

    if request.method == 'POST':
        form = ContractCreateForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data

            # Определить шаблон по типу оффера
            contract_type = 'agent_rental'
            if booking.offer and booking.offer.is_captain_offer():
                contract_type = 'captain_services'

            template = ContractTemplate.objects.filter(
                contract_type=contract_type, is_active=True
            ).first()

            # Если нет шаблона в БД — создаём дефолтный
            if not template:
                template, _ = ContractTemplate.objects.get_or_create(
                    contract_type=contract_type,
                    defaults={
                        'name': f'Договор ({contract_type}) авто',
                        'template_content': '',
                        'is_active': True,
                    },
                )
                if not template.is_active:
                    template.is_active = True
                    template.save(update_fields=['is_active'])

            contract = Contract(
                contract_number=Contract.generate_contract_number(),
                booking=booking,
                offer=booking.offer,
                template=template,
                created_by=request.user,
                signer=booking.user,
                client=booking.client,
                contract_data={
                    'signer_full_name': cd['signer_full_name'],
                    'signer_passport': cd['signer_passport'],
                    'signer_address': cd['signer_address'],
                    'signer_phone': cd['signer_phone'],
                    'signer_email': cd['signer_email'],
                    'agent_full_name': cd['agent_full_name'],
                    'agent_company': cd.get('agent_company', ''),
                    'agent_phone': cd['agent_phone'],
                    'additional_terms': cd.get('additional_terms', ''),
                },
                status='draft',
                expires_at=timezone.now() + timedelta(days=14),
            )
            contract.save()

            # Генерация PDF
            try:
                from .contract_generator import generate_and_save_pdf
                generate_and_save_pdf(contract)
                contract.status = 'sent'
                contract.save(update_fields=['status', 'updated_at'])
                messages.success(request, f'Договор {contract.contract_number} создан и готов к подписанию')
            except Exception as e:
                logger.error(f'[Contract] PDF generation failed: {e}')
                messages.warning(request, f'Договор создан, но PDF не сгенерирован: {e}')

            return redirect('contract_detail', uuid=contract.uuid)
    else:
        # Предзаполнение формы
        user = booking.user
        client = booking.client
        initial = {
            'signer_full_name': (client.full_name if client else None) or user.get_full_name() or user.username,
            'signer_email': (client.email if client else None) or user.email,
            'signer_phone': (client.phone if client else None) or (getattr(user, 'profile', None) and user.profile.phone or ''),
            'signer_passport': (client.passport_number if client else '') or '',
            'signer_address': (client.address if client else '') or '',
            'agent_full_name': request.user.get_full_name() or request.user.username,
            'agent_phone': getattr(request.user, 'profile', None) and request.user.profile.phone or '',
        }
        form = ContractCreateForm(initial=initial)

    context = {
        'form': form,
        'booking': booking,
    }
    return render(request, 'boats/create_contract.html', context)


@login_required
def contract_detail(request, uuid):
    """Просмотр деталей договора."""
    contract = get_object_or_404(Contract, uuid=uuid)

    # Доступ: создатель, подписант, менеджер, админ
    if not (request.user == contract.created_by
            or request.user == contract.signer
            or request.user.profile.role in ('manager', 'admin', 'superadmin')):
        messages.error(request, 'У вас нет доступа к этому договору')
        return redirect('my_bookings')

    # Формируем URL подписания
    from django.urls import reverse
    sign_url = request.build_absolute_uri(
        reverse('sign_contract', args=[contract.uuid, contract.sign_token])
    )

    context = {
        'contract': contract,
        'sign_url': sign_url,
        'can_manage': request.user == contract.created_by or request.user.profile.role in ('manager', 'admin', 'superadmin'),
    }
    return render(request, 'boats/contract_detail.html', context)


def _mask_phone(phone):
    """Маскируем телефон: +7 (999) ***-**-45 → показываем только последние 2 цифры."""
    if not phone or len(phone) < 4:
        return phone or ''
    digits = ''.join(c for c in phone if c.isdigit())
    if len(digits) <= 2:
        return '***'
    return f'***{digits[-2:]}'


def _get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def send_contract_otp(request, uuid, sign_token):
    """AJAX endpoint: отправить OTP-код для подписания договора."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    contract = get_object_or_404(Contract, uuid=uuid, sign_token=sign_token)

    if not contract.can_be_signed():
        return JsonResponse({'error': 'Договор не может быть подписан'}, status=400)

    # Throttle: не больше 1 кода в 60 сек
    recent_otp = ContractOTP.objects.filter(
        contract=contract,
        created_at__gte=timezone.now() - timedelta(seconds=60),
    ).first()
    if recent_otp:
        return JsonResponse({'error': 'Подождите 60 секунд перед повторной отправкой'}, status=429)

    phone = contract.contract_data.get('signer_phone', '')
    if not phone:
        return JsonResponse({'error': 'Телефон подписанта не указан в договоре'}, status=400)

    otp = ContractOTP.create_for_contract(contract, phone, delivery_method='sms')

    # Отправка через MTS Exolve (SMS с fallback на Telegram)
    from .sms import send_otp
    sent = send_otp(phone, otp.code, delivery_method=otp.delivery_method)
    if not sent:
        logger.warning(f'[OTP] Delivery failed for contract {contract.contract_number} → {phone}')

    resp = {
        'ok': True,
        'phone_masked': _mask_phone(phone),
        'expires_in': ContractOTP.CODE_LIFETIME_SECONDS,
    }
    if settings.DEBUG:
        resp['debug_code'] = otp.code
    return JsonResponse(resp)


def sign_contract(request, uuid, sign_token):
    """Страница подписания договора с OTP-кодом (доступно по токену без авторизации)."""
    contract = get_object_or_404(Contract, uuid=uuid, sign_token=sign_token)

    if contract.status == 'signed':
        return render(request, 'boats/contract_signed.html', {'contract': contract})

    if contract.is_expired():
        contract.status = 'expired'
        contract.save(update_fields=['status', 'updated_at'])
        return render(request, 'boats/contract_expired.html', {'contract': contract})

    if not contract.can_be_signed():
        messages.error(request, 'Этот договор не может быть подписан')
        return render(request, 'boats/contract_expired.html', {'contract': contract})

    # Отметить как просмотренный
    if contract.status == 'sent':
        contract.status = 'viewed'
        contract.save(update_fields=['status', 'updated_at'])

    signer_phone = contract.contract_data.get('signer_phone', '')

    if request.method == 'POST':
        form = ContractSignForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            otp_code = cd['otp_code']

            # Проверяем OTP
            otp = ContractOTP.objects.filter(
                contract=contract,
                is_verified=False,
            ).order_by('-created_at').first()

            if not otp or not otp.is_valid():
                form.add_error('otp_code', 'Код истёк или не был отправлен. Запросите новый код.')
            elif otp.code != otp_code:
                otp.attempts += 1
                otp.save(update_fields=['attempts'])
                remaining = otp.MAX_ATTEMPTS - otp.attempts
                if remaining > 0:
                    form.add_error('otp_code', f'Неверный код. Осталось попыток: {remaining}')
                else:
                    form.add_error('otp_code', 'Превышено количество попыток. Запросите новый код.')
            else:
                # OTP верный — подписываем
                otp.is_verified = True
                otp.save(update_fields=['is_verified'])

                client_ip = _get_client_ip(request)

                contract.signature_data = f'otp_verified:{otp.id}'
                contract.signed_at = timezone.now()
                contract.sign_ip = client_ip
                contract.sign_user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
                contract.status = 'signed'

                contract.contract_data['signed_name_confirm'] = cd['signer_name_confirm']
                contract.contract_data['signed_at_iso'] = contract.signed_at.isoformat()
                contract.contract_data['sign_ip'] = client_ip
                contract.contract_data['otp_verified'] = True
                contract.contract_data['otp_phone'] = signer_phone

                contract.save(update_fields=[
                    'signature_data', 'signed_at', 'sign_ip', 'sign_user_agent',
                    'status', 'contract_data', 'updated_at',
                ])

                logger.info(
                    f'[Contract] Signed via OTP: {contract.contract_number} '
                    f'by {cd["signer_name_confirm"]} from {client_ip}'
                )

                return render(request, 'boats/contract_signed.html', {'contract': contract})
    else:
        initial = {
            'signer_name_confirm': contract.contract_data.get('signer_full_name', ''),
        }
        form = ContractSignForm(initial=initial)

    # Рендерим контент договора для просмотра
    from .contract_generator import build_contract_context
    from django.template import Template, Context
    from .contract_generator import DEFAULT_AGENT_RENTAL_TEMPLATE

    template_str = contract.template.template_content if contract.template and contract.template.template_content else DEFAULT_AGENT_RENTAL_TEMPLATE
    ctx = build_contract_context(contract)
    contract_html = Template(template_str).render(Context(ctx))

    context = {
        'contract': contract,
        'form': form,
        'contract_html': contract_html,
        'signer_phone_masked': _mask_phone(signer_phone),
        'otp_lifetime': ContractOTP.CODE_LIFETIME_SECONDS,
    }
    return render(request, 'boats/contract_sign.html', context)


@login_required
def download_contract(request, uuid):
    """Скачать PDF документ договора."""
    contract = get_object_or_404(Contract, uuid=uuid)

    # Доступ: создатель, подписант, менеджер
    if not (request.user == contract.created_by
            or request.user == contract.signer
            or request.user.profile.role in ('manager', 'admin', 'superadmin')):
        messages.error(request, 'У вас нет доступа к этому файлу')
        return redirect('my_bookings')

    if not contract.document_file:
        messages.error(request, 'PDF документ ещё не сгенерирован')
        return redirect('contract_detail', uuid=contract.uuid)

    from django.http import FileResponse
    response = FileResponse(
        contract.document_file.open('rb'),
        content_type='application/pdf',
    )
    response['Content-Disposition'] = f'attachment; filename="contract_{contract.contract_number}.pdf"'
    return response


@login_required
def contracts_list(request):
    """Список договоров для менеджера/капитана."""
    user = request.user

    if user.profile.role in ('manager', 'admin', 'superadmin'):
        contracts_qs = Contract.objects.all()
    elif user.profile.role == 'captain':
        contracts_qs = Contract.objects.filter(created_by=user)
    else:
        contracts_qs = Contract.objects.filter(signer=user)

    contracts_qs = contracts_qs.select_related(
        'booking', 'offer', 'created_by', 'signer'
    ).order_by('-created_at')

    # Фильтр по статусу
    status_filter = request.GET.get('status', '')
    if status_filter:
        contracts_qs = contracts_qs.filter(status=status_filter)

    paginator = Paginator(contracts_qs, 15)
    contracts = paginator.get_page(request.GET.get('page', 1))

    context = {
        'contracts': contracts,
        'status_filter': status_filter,
        'status_choices': Contract.STATUS_CHOICES,
    }
    return render(request, 'boats/contracts_list.html', context)


# =========================================================================
# Клиенты (CRUD)
# =========================================================================

@login_required
def clients_list(request):
    """Список клиентов агента/капитана"""
    user = request.user
    if user.profile.role in ('manager', 'superadmin'):
        clients_qs = Client.objects.all()
    else:
        clients_qs = Client.objects.filter(created_by=user)

    search_q = request.GET.get('q', '').strip()
    if search_q:
        clients_qs = clients_qs.filter(
            Q(last_name__icontains=search_q)
            | Q(first_name__icontains=search_q)
            | Q(phone__icontains=search_q)
            | Q(email__icontains=search_q)
        )

    clients_qs = clients_qs.select_related('created_by')
    paginator = Paginator(clients_qs, 20)
    clients = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'boats/clients_list.html', {
        'clients': clients,
        'search_q': search_q,
    })


@login_required
def client_create(request):
    """Создание нового клиента"""
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save(commit=False)
            client.created_by = request.user
            client.save()
            messages.success(request, f'Клиент {client.full_name} создан')
            next_url = request.GET.get('next')
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                separator = '&' if '?' in next_url else '?'
                return redirect(f'{next_url}{separator}client_id={client.pk}')
            return redirect('client_detail', pk=client.pk)
    else:
        form = ClientForm()

    return render(request, 'boats/client_form.html', {
        'form': form,
        'title': 'Новый клиент',
    })


@login_required
def client_detail(request, pk):
    """Карточка клиента с историей"""
    if request.user.profile.role in ('manager', 'superadmin'):
        client = get_object_or_404(Client, pk=pk)
    else:
        client = get_object_or_404(Client, pk=pk, created_by=request.user)

    bookings = Booking.objects.filter(client=client).select_related('offer').order_by('-created_at')[:10]
    offers = Offer.objects.filter(client=client).order_by('-created_at')[:10]
    contracts = Contract.objects.filter(client=client).order_by('-created_at')[:10]

    return render(request, 'boats/client_detail.html', {
        'client': client,
        'bookings': bookings,
        'offers': offers,
        'contracts': contracts,
    })


@login_required
def client_edit(request, pk):
    """Редактирование клиента"""
    if request.user.profile.role in ('manager', 'superadmin'):
        client = get_object_or_404(Client, pk=pk)
    else:
        client = get_object_or_404(Client, pk=pk, created_by=request.user)

    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, f'Клиент {client.full_name} обновлён')
            return redirect('client_detail', pk=client.pk)
    else:
        form = ClientForm(instance=client)

    return render(request, 'boats/client_form.html', {
        'form': form,
        'client': client,
        'title': f'Редактирование: {client.short_name}',
    })


@login_required
def client_search_api(request):
    """JSON API для поиска клиентов (автодополнение)"""
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})

    if request.user.profile.role in ('manager', 'superadmin'):
        qs = Client.objects.all()
    else:
        qs = Client.objects.filter(created_by=request.user)

    qs = qs.filter(
        Q(last_name__icontains=q)
        | Q(first_name__icontains=q)
        | Q(phone__icontains=q)
        | Q(email__icontains=q)
    )[:10]

    results = []
    for c in qs:
        results.append({
            'id': c.pk,
            'full_name': c.full_name,
            'short_name': c.short_name,
            'phone': c.phone,
            'email': c.email,
        })

    return JsonResponse({'results': results})


def terms(request):
    return render(request, 'boats/terms.html')


def privacy(request):
    return render(request, 'boats/privacy.html')


def contacts(request):
    return render(request, 'boats/contacts.html')
