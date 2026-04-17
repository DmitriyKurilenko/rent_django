"""
Management command для параллельного парсинга лодок с boataround.com

Фазы:
    1. Сбор slug'ов через поисковый API (с кэшированием в /tmp)
       Также собирает thumb URL для каждой лодки
    2. Параллельный парсинг HTML-страниц каждой лодки
       После парсинга загружает thumb-превью на CDN (S3) и сохраняет
       CDN URL в ParsedBoat.preview_cdn_url
    3. Итоговый отчёт со статистикой

Использование:
    python manage.py parse_boats_parallel --destination turkey --workers 5
    python manage.py parse_boats_parallel --destination turkey --workers 15 --skip-existing
    python manage.py parse_boats_parallel --destination turkey --workers 5 --verbose
    python manage.py parse_boats_parallel --destination turkey --no-cache  # без кэша slug'ов
    python manage.py parse_boats_parallel --destination turkey --cache-ttl 48  # кэш на 48 часов
    python manage.py parse_boats_parallel  # все лодки без фильтра
"""

import json
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from boats.boataround_api import BoataroundAPI
from boats.parser import parse_boataround_url, download_and_save_image
from boats.models import ParsedBoat, BoatDescription, BoatTechnicalSpecs
from django import db

logger = logging.getLogger(__name__)

CACHE_DIR = Path('/tmp/parse_boats_cache')
SUPPORTED_API_LANGS = ['ru_RU', 'en_EN', 'de_DE', 'fr_FR', 'es_ES']


class Command(BaseCommand):
    help = 'Параллельный парсинг лодок с boataround.com (несколько воркеров)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--workers',
            type=int,
            default=5,
            help='Количество параллельных воркеров (default: 5)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Ограничить количество лодок',
        )
        parser.add_argument(
            '--destination',
            type=str,
            default=None,
            help='Парсить только по определенному направлению (e.g., "turkey")',
        )
        parser.add_argument(
            '--skip-existing',
            action='store_true',
            help='Пропустить уже спарсенные лодки',
        )
        parser.add_argument(
            '--max-pages',
            type=int,
            default=None,
            help='Ограничение по числу страниц на направление',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Подробный вывод (все логи парсера)',
        )
        parser.add_argument(
            '--no-cache',
            action='store_true',
            help='Полностью отключить кэш (не читать и не писать)',
        )
        parser.add_argument(
            '--refresh-cache',
            action='store_true',
            help='Принудительно пересканировать API и обновить кэш',
        )
        parser.add_argument(
            '--cache-ttl',
            type=int,
            default=24,
            help='Время жизни кэша slug\'ов в часах (default: 24)',
        )

    def handle(self, *args, **options):
        workers = options['workers']
        limit = options['limit']
        destination = options['destination']
        skip_existing = options['skip_existing']
        max_pages = options.get('max_pages')
        verbose = options['verbose']
        no_cache = options['no_cache']
        refresh_cache = options['refresh_cache']
        cache_ttl = options['cache_ttl']

        # В обычном режиме глушим спам из парсера
        if not verbose:
            logging.getLogger('boats.parser').setLevel(logging.WARNING)
            logging.getLogger('boats.boataround_api').setLevel(logging.WARNING)

        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('  PARSE BOATS PARALLEL'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(f'  Направление:  {destination or "все"}')
        self.stdout.write(f'  Воркеры:      {workers}')
        self.stdout.write(f'  Лимит:        {limit or "нет"}')
        self.stdout.write(f'  Skip existing: {skip_existing}')
        cache_label = "выкл" if no_cache else ("обновление" if refresh_cache else f"{cache_ttl}ч")
        self.stdout.write(f'  Кэш:          {cache_label}')
        self.stdout.write('')

        # --- Фаза 1: Сбор slug'ов ---
        self.stdout.write('📋 Фаза 1: Сбор списка лодок...')
        phase1_start = time.time()

        # Пробуем загрузить из кэша
        cache_hit = False
        all_slugs = None
        search_stats = {'pages_scanned': 0, 'skipped_existing': 0, 'cache': False}
        thumb_map = {}  # slug → thumb URL
        api_meta = {}   # slug → API metadata
        api_meta_by_lang = {}  # api_lang -> slug -> localized metadata

        # Читаем из кэша только если не --no-cache и не --refresh-cache
        if not no_cache and not refresh_cache:
            cached = self._load_cache(destination, cache_ttl, max_pages)
            if cached is not None:
                all_slugs = cached.get('slugs', [])
                thumb_map = cached.get('thumb_map', {})
                api_meta = cached.get('api_meta', {})
                api_meta_by_lang = cached.get('api_meta_by_lang', {})
                cache_hit = True
                search_stats['cache'] = True
                self.stdout.write(f'   ⚡ Загружено из кэша: {len(all_slugs)} slug\'ов')

        if all_slugs is None:
            all_slugs, search_stats, thumb_map, api_meta, api_meta_by_lang = self._fetch_all_slugs(
                destination, max_pages
            )
            # Сохраняем в кэш если не --no-cache
            if not no_cache and all_slugs:
                self._save_cache(destination, max_pages, all_slugs, thumb_map, api_meta, api_meta_by_lang)
                self.stdout.write(f'   💾 Кэш сохранён: {len(all_slugs)} slug\'ов')

        # Фильтруем: skip_existing и limit
        boat_slugs = all_slugs
        if skip_existing:
            before = len(boat_slugs)
            existing_ids = set(
                ParsedBoat.objects.values_list('slug', flat=True)
            )
            boat_slugs = [s for s in boat_slugs if s not in existing_ids]
            search_stats['skipped_existing'] = before - len(boat_slugs)

        if limit:
            boat_slugs = boat_slugs[:limit]

        phase1_time = time.time() - phase1_start

        if not boat_slugs:
            self.stdout.write(self.style.WARNING('Не найдено лодок для парсинга'))
            if search_stats['skipped_existing'] > 0:
                self.stdout.write(f'   (все {search_stats["skipped_existing"]} уже в БД)')
            # Даже если нечего парсить — обновляем метаданные из API
            if api_meta:
                meta_updated = self._update_api_metadata(api_meta, api_meta_by_lang)
                if meta_updated:
                    self.stdout.write(f'   📍 API-метаданные обновлены: {meta_updated} лодок')
            return

        total = len(boat_slugs)
        self.stdout.write(f'   Всего slug:   {len(all_slugs)}')
        self.stdout.write(f'   К парсингу:   {total}')
        if search_stats.get('pages_scanned'):
            self.stdout.write(f'   Страниц:      {search_stats["pages_scanned"]}')
        self.stdout.write(f'   Пропущено:    {search_stats["skipped_existing"]}')
        self.stdout.write(f'   Источник:     {"кэш" if cache_hit else "API"}')
        self.stdout.write(f'   Время:        {phase1_time:.1f}s')
        self.stdout.write('')

        # --- Фаза 1.5: Обновление метаданных из API ---
        if api_meta:
            meta_updated = self._update_api_metadata(api_meta, api_meta_by_lang)
            if meta_updated:
                self.stdout.write(f'   📍 API-метаданные обновлены: {meta_updated} лодок (country/region/city/engine_type)')
            self.stdout.write('')

        # --- Фаза 2: Парсинг ---
        self.stdout.write(f'🔄 Фаза 2: Парсинг {total} лодок ({workers} воркеров)...')
        phase2_start = time.time()

        # Для оптимизации Phase 2.5: запоминаем, какие slug уже были в БД до парсинга.
        existing_before_phase2 = set(
            ParsedBoat.objects.filter(slug__in=boat_slugs).values_list('slug', flat=True)
        )
        success_slugs = []

        db.connections.close_all()

        stats = {
            'success': 0,
            'failed': 0,
            'photos': 0,
            'descriptions': 0,
            'prices': 0,
            'extras': 0,
            'details': 0,
        }
        lock = threading.Lock()

        def parse_one(slug):
            try:
                url = f'https://www.boataround.com/ru/yachta/{slug}/'
                result = parse_boataround_url(
                    url,
                    save_to_db=True,
                    html_mode='services_only',
                )
                if result:
                    # Загружаем превью из thumb API на CDN
                    thumb_url = thumb_map.get(slug)
                    if thumb_url:
                        self._save_preview(slug, thumb_url)

                    return (slug, True, {
                        'photos': len(result.get('pictures', [])),
                        'extras': len(result.get('extras', [])),
                        'descriptions': len(result.get('equipment_by_language', {})),
                    })
                return (slug, False, {})
            except Exception as e:
                if verbose:
                    logger.error(f"Ошибка при парсинге {slug}: {e}")
                return (slug, False, {})
            finally:
                db.connection.close()

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(parse_one, slug): slug for slug in boat_slugs}

            for idx, future in enumerate(as_completed(futures), 1):
                slug, ok, result_stats = future.result()
                with lock:
                    if ok:
                        stats['success'] += 1
                        stats['photos'] += result_stats.get('photos', 0)
                        stats['extras'] += result_stats.get('extras', 0)
                        stats['descriptions'] += result_stats.get('descriptions', 0)
                        success_slugs.append(slug)
                    else:
                        stats['failed'] += 1

                # Прогресс-бар
                elapsed = time.time() - phase2_start
                rate = idx / elapsed if elapsed > 0 else 0
                eta = (total - idx) / rate if rate > 0 else 0
                pct = idx * 100 // total
                bar_len = 30
                filled = bar_len * idx // total
                bar = '█' * filled + '░' * (bar_len - filled)

                sys.stdout.write(
                    f'\r   {bar} {pct:3d}% | {idx}/{total} | '
                    f'✅{stats["success"]} ❌{stats["failed"]} | '
                    f'{rate:.1f}/s | ETA {int(eta)}s'
                )
                sys.stdout.flush()

        phase2_time = time.time() - phase2_start
        sys.stdout.write('\n')

        # --- Фаза 2.5: API-метаданные только для НОВЫХ лодок из Phase 2 ---
        if api_meta and stats['success'] > 0:
            new_success_slugs = [
                slug for slug in success_slugs if slug not in existing_before_phase2
            ]
            new_api_meta = {
                slug: api_meta[slug]
                for slug in new_success_slugs
                if slug in api_meta
            }
            new_api_meta_by_lang = {}
            if api_meta_by_lang:
                for api_lang, lang_map in api_meta_by_lang.items():
                    if not isinstance(lang_map, dict):
                        continue
                    new_api_meta_by_lang[api_lang] = {
                        slug: lang_map[slug]
                        for slug in new_success_slugs
                        if slug in lang_map
                    }

            meta_updated = self._update_api_metadata(new_api_meta, new_api_meta_by_lang) if new_api_meta else 0
            if meta_updated:
                self.stdout.write(
                    f'   📍 API-метаданные обновлены для новых лодок: {meta_updated}'
                )
            self.stdout.write('')

        # --- Фаза 3: Итоговый отчёт ---
        total_time = phase1_time + phase2_time

        from boats.models import BoatGallery, BoatPrice, BoatDetails
        db_stats = {
            'parsed_boats': ParsedBoat.objects.count(),
            'photos': BoatGallery.objects.count(),
            'descriptions': BoatDescription.objects.count(),
            'prices': BoatPrice.objects.count(),
            'details': BoatDetails.objects.count(),
            'specs': BoatTechnicalSpecs.objects.count(),
        }

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('  ИТОГОВЫЙ ОТЧЁТ'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write('  Парсинг:')
        self.stdout.write(f'    Успешно:       {stats["success"]}')
        self.stdout.write(f'    Ошибки:        {stats["failed"]}')
        self.stdout.write(f'    Фото загр.:    {stats["photos"]}')
        self.stdout.write(f'    Скорость:      {stats["success"] / phase2_time:.1f} лодок/s' if phase2_time > 0 else '')
        self.stdout.write('')
        self.stdout.write('  База данных (всего):')
        self.stdout.write(f'    ParsedBoat:    {db_stats["parsed_boats"]}')
        self.stdout.write(f'    Фото:          {db_stats["photos"]}')
        self.stdout.write(f'    Описания:      {db_stats["descriptions"]}')
        self.stdout.write(f'    Цены:          {db_stats["prices"]}')
        self.stdout.write(f'    Детали:        {db_stats["details"]}')
        self.stdout.write(f'    Тех. спеки:    {db_stats["specs"]}')
        self.stdout.write('')
        self.stdout.write('  Время:')
        self.stdout.write(f'    Сбор slug:     {phase1_time:.1f}s')
        self.stdout.write(f'    Парсинг:       {phase2_time:.1f}s')
        self.stdout.write(f'    Итого:         {total_time:.1f}s ({total_time / 60:.1f} мин)')
        self.stdout.write(self.style.SUCCESS('=' * 60))

    # ---- Кэш slug'ов ----

    def _cache_key(self, destination, max_pages):
        dest = destination or 'all'
        mp = f'_mp{max_pages}' if max_pages else ''
        return f'{dest}{mp}'

    def _cache_path(self, destination, max_pages):
        return CACHE_DIR / f'{self._cache_key(destination, max_pages)}.json'

    def _load_cache(self, destination, cache_ttl, max_pages):
        """Загружает кэш, если он свежий. Возвращает dict или None.

        Формат:
            {
              'slugs': [...],
              'thumb_map': {slug: thumb_url},
                            'api_meta': {slug: {...}},
                            'api_meta_by_lang': {'ru_RU': {slug: {...}}, ...}
            }
        """
        path = self._cache_path(destination, max_pages)
        if not path.exists():
            return None

        try:
            age_hours = (time.time() - path.stat().st_mtime) / 3600
            if age_hours > cache_ttl:
                self.stdout.write(f'   Кэш устарел ({age_hours:.1f}ч > {cache_ttl}ч)')
                return None

            with open(path, 'r') as f:
                data = json.load(f)

            # Backward compatibility: старый формат кэша = просто list slug'ов.
            if isinstance(data, list):
                self.stdout.write(f'   Кэш старого формата ({age_hours:.1f}ч назад)')
                return {
                    'slugs': data,
                    'thumb_map': {},
                    'api_meta': {},
                    'api_meta_by_lang': {},
                }

            slugs = data.get('slugs', [])
            thumb_map = data.get('thumb_map', {})
            api_meta = data.get('api_meta', {})
            api_meta_by_lang = data.get('api_meta_by_lang', {})
            cached_at = data.get('cached_at', '?')
            self.stdout.write(f'   Кэш от {cached_at} ({age_hours:.1f}ч назад)')
            return {
                'slugs': slugs,
                'thumb_map': thumb_map if isinstance(thumb_map, dict) else {},
                'api_meta': api_meta if isinstance(api_meta, dict) else {},
                'api_meta_by_lang': api_meta_by_lang if isinstance(api_meta_by_lang, dict) else {},
            }
        except Exception as e:
            logger.warning(f'Ошибка чтения кэша: {e}')
            return None

    def _save_cache(self, destination, max_pages, slugs, thumb_map, api_meta, api_meta_by_lang):
        """Сохраняет slug'и и API-метаданные в кэш."""
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path = self._cache_path(destination, max_pages)
            data = {
                'destination': destination or 'all',
                'max_pages': max_pages,
                'count': len(slugs),
                'cached_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'slugs': slugs,
                'thumb_map': thumb_map,
                'api_meta': api_meta,
                'api_meta_by_lang': api_meta_by_lang,
            }
            with open(path, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f'Ошибка записи кэша: {e}')

    # ---- Сбор slug'ов из API ----

    def _fetch_all_slugs(self, destination=None, max_pages=None):
        """Получает ВСЕ slug'и через API (без фильтрации skip_existing).

        Если destination задан — ищем по нему.
        Если нет — запрос без параметра destinations, API отдаёт весь каталог.

        Returns:
            tuple: (slugs, search_stats, thumb_map, api_meta, api_meta_by_lang)
                thumb_map: {slug: thumb_url} для загрузки превью на CDN
                api_meta: {slug: metadata} для заполнения моделей из API
                api_meta_by_lang: {api_lang: {slug: localized_metadata}}
        """
        slugs = []
        seen = set()
        thumb_map = {}  # slug → thumb URL
        api_meta = {}   # slug → {country, region, city, engineType, category}
        api_meta_by_lang = {lang: {} for lang in SUPPORTED_API_LANGS}
        search_stats = {'pages_scanned': 0, 'skipped_existing': 0, 'cache': False}

        from boats.boataround_api import format_boat_data

        label = destination or 'весь каталог'
        self.stdout.write(f'   🔍 {label}...', ending='')
        sys.stdout.flush()

        page = 1
        total_pages = None
        count = 0

        while True:
            try:
                results = BoataroundAPI.search(
                    destination=destination,  # None = без фильтра
                    page=page,
                    limit=18,
                    lang='en_EN'
                )

                if not results or not results.get('boats'):
                    break

                # Для этой страницы подтягиваем локализованные geo/title по всем 5 языкам API.
                boats_by_lang = {'en_EN': results.get('boats', [])}
                for api_lang in SUPPORTED_API_LANGS:
                    if api_lang == 'en_EN':
                        continue
                    try:
                        lang_results = BoataroundAPI.search(
                            destination=destination,
                            page=page,
                            limit=18,
                            lang=api_lang,
                        )
                        boats_by_lang[api_lang] = (lang_results or {}).get('boats', [])
                    except Exception:
                        boats_by_lang[api_lang] = []

                for api_lang, boats_lang in boats_by_lang.items():
                    for boat_lang in boats_lang:
                        lang_slug = boat_lang.get('slug')
                        if not lang_slug:
                            continue
                        api_meta_by_lang.setdefault(api_lang, {})[lang_slug] = {
                            'title': boat_lang.get('title', ''),
                            'location': boat_lang.get('location', '') or boat_lang.get('region', '') or boat_lang.get('country', ''),
                            'marina': boat_lang.get('marina', ''),
                            'country': boat_lang.get('country', ''),
                            'region': boat_lang.get('region', ''),
                            'city': boat_lang.get('city', ''),
                        }

                search_stats['pages_scanned'] += 1

                for boat in results['boats']:
                    try:
                        formatted = format_boat_data(boat)
                    except Exception:
                        formatted = {}

                    boat_slug = formatted.get('slug') or boat.get('slug')
                    if not boat_slug or boat_slug in seen:
                        continue

                    seen.add(boat_slug)
                    slugs.append(boat_slug)
                    count += 1

                    # Сохраняем thumb для загрузки превью на CDN
                    thumb = boat.get('thumb') or boat.get('main_img', '')
                    if thumb and thumb.strip():
                        thumb_map[boat_slug] = thumb.strip()

                    # Сохраняем все метаданные из API
                    api_meta[boat_slug] = {
                        # Геолокация
                        'country': boat.get('country', ''),
                        'region': boat.get('region', ''),
                        'city': boat.get('city', ''),
                        'marina': boat.get('marina', ''),
                        'title': boat.get('title', ''),
                        'location': boat.get('location', '') or boat.get('region', '') or boat.get('country', ''),
                        'flag': boat.get('flag', ''),
                        'coordinates': boat.get('coordinates', []),
                        # Категория и тип
                        'category': boat.get('category', ''),
                        'category_slug': boat.get('category_slug', ''),
                        'engine_type': boat.get('engineType', ''),
                        'sail': boat.get('sail', ''),
                        'newboat': boat.get('newboat', False),
                        # Рейтинг и отзывы
                        'reviews_score': boat.get('reviewsScore'),
                        'total_reviews': boat.get('totalReviews'),
                        'prepayment': boat.get('prepayment'),
                        'usp': boat.get('usp', []),
                        # Параметры (cabin breakdown и т.д.)
                        'parameters': boat.get('parameters', {}),
                        # Чартер
                        'charter_name': boat.get('charter', ''),
                        'charter_id': boat.get('charter_id', ''),
                        'charter_logo': boat.get('charter_logo', ''),
                        'charter_rank': boat.get('charter_rank', {}),
                    }

                # totalPages уже пересчитан в BoataroundAPI.search()
                # по фактическому кол-ву лодок на странице
                if total_pages is None:
                    total_pages = int(results.get('totalPages') or 1)

                effective_total_pages = total_pages
                if max_pages and isinstance(max_pages, int) and max_pages > 0:
                    effective_total_pages = min(effective_total_pages, max_pages)

                # Прогресс сканирования страниц
                if page % 50 == 0:
                    sys.stdout.write(f'\r   🔍 {label}... стр. {page}/{effective_total_pages}, {count} лодок')
                    sys.stdout.flush()

                if page >= effective_total_pages:
                    break

                page += 1

            except Exception as e:
                logger.error(f"Ошибка при поиске стр.{page}: {e}")
                break

        self.stdout.write(f'\r   🔍 {label}... {count} лодок ({page} стр.)' + ' ' * 20)

        return slugs, search_stats, thumb_map, api_meta, api_meta_by_lang

    @staticmethod
    def _save_preview(slug: str, thumb_url: str):
        """Скачивает thumb и сохраняет CDN URL как preview_cdn_url."""
        from urllib.parse import urlparse

        try:
            parsed = urlparse(thumb_url)
            image_path = parsed.path.lstrip('/')
            if not image_path.startswith('boats/'):
                return

            cdn_url = download_and_save_image(image_path)
            if cdn_url:
                ParsedBoat.objects.filter(slug=slug).update(
                    preview_cdn_url=cdn_url
                )
        except Exception as e:
            logger.warning(f"Failed to save preview for {slug}: {e}")

    @staticmethod
    def _update_api_metadata(api_meta: dict, api_meta_by_lang: dict | None = None) -> int:
        """
        Batch-обновляет ParsedBoat, BoatTechnicalSpecs, BoatDescription и Charter
        из API-данных. Для ParsedBoat API-поля — обновляет всегда (авторитетный источник).
        Для BoatDescription/BoatTechnicalSpecs — заполняет только пустые поля.
        Returns: количество обновлённых лодок (ParsedBoat).
        """
        from boats.models import Charter

        if not api_meta:
            return 0

        updated = 0
        BATCH = 2000
        all_slugs = list(api_meta.keys())

        for batch_start in range(0, len(all_slugs), BATCH):
            batch_slugs = all_slugs[batch_start:batch_start + BATCH]

            # --- ParsedBoat: API-поля (всегда обновляем) ---
            boats_qs = ParsedBoat.objects.filter(slug__in=batch_slugs).defer('boat_data')
            boats_map = {pb.slug: pb for pb in boats_qs}

            pb_to_update = []
            pb_fields_changed = set()

            for slug in batch_slugs:
                pb = boats_map.get(slug)
                if not pb:
                    continue
                meta = api_meta[slug]
                changed = False

                # Строковые поля — обновляем если API присылает непустое значение
                for attr, key in [
                    ('category', 'category'),
                    ('category_slug', 'category_slug'),
                    ('flag', 'flag'),
                    ('sail', 'sail'),
                ]:
                    val = meta.get(key, '')
                    if val and getattr(pb, attr) != val:
                        setattr(pb, attr, val)
                        pb_fields_changed.add(attr)
                        changed = True

                # Числовые — обновляем если есть (рейтинг, отзывы, предоплата)
                for attr, key in [
                    ('reviews_score', 'reviews_score'),
                    ('total_reviews', 'total_reviews'),
                    ('prepayment', 'prepayment'),
                ]:
                    val = meta.get(key)
                    if val is not None and getattr(pb, attr) != val:
                        setattr(pb, attr, val)
                        pb_fields_changed.add(attr)
                        changed = True

                # Координаты
                coords = meta.get('coordinates', [])
                if isinstance(coords, list) and len(coords) == 2:
                    lat, lon = coords
                    if pb.latitude != lat or pb.longitude != lon:
                        pb.latitude = lat
                        pb.longitude = lon
                        pb_fields_changed.update(['latitude', 'longitude'])
                        changed = True

                # Boolean
                newboat = meta.get('newboat', False)
                if newboat != pb.newboat:
                    pb.newboat = newboat
                    pb_fields_changed.add('newboat')
                    changed = True

                # USP (JSON) — обновляем если есть из API
                usp = meta.get('usp', [])
                if usp:
                    pb.usp = usp
                    pb_fields_changed.add('usp')
                    changed = True

                if changed:
                    pb_to_update.append(pb)
                    updated += 1

            if pb_to_update and pb_fields_changed:
                ParsedBoat.objects.bulk_update(
                    pb_to_update, list(pb_fields_changed), batch_size=500
                )

            # --- Charter: создаём/обновляем и привязываем ---
            charter_cache = {}
            pb_charter_updates = []

            for slug in batch_slugs:
                pb = boats_map.get(slug)
                if not pb:
                    continue
                meta = api_meta[slug]
                charter_id = meta.get('charter_id', '')
                charter_name = meta.get('charter_name', '')
                if not charter_id or not charter_name:
                    continue

                if charter_id not in charter_cache:
                    charter_rank = meta.get('charter_rank', {})
                    charter_obj, _ = Charter.objects.update_or_create(
                        charter_id=charter_id,
                        defaults={
                            'name': charter_name,
                            'logo': meta.get('charter_logo', ''),
                            'rank_score': charter_rank.get('score'),
                            'rank_place': charter_rank.get('place'),
                            'rank_out_of': charter_rank.get('out_of'),
                            'rank_reviews_count': charter_rank.get('count'),
                        }
                    )
                    charter_cache[charter_id] = charter_obj

                charter_obj = charter_cache[charter_id]
                if pb.charter_id != charter_obj.pk:
                    pb.charter = charter_obj
                    pb_charter_updates.append(pb)

            if pb_charter_updates:
                ParsedBoat.objects.bulk_update(
                    pb_charter_updates, ['charter'], batch_size=500
                )

            # --- BoatDescription: создаём при отсутствии + заполняем пустые ---
            for slug in batch_slugs:
                pb = boats_map.get(slug)
                if not pb:
                    continue
                meta = api_meta[slug]
                base_qs = BoatDescription.objects.filter(boat=pb)

                # Если описаний нет — создаём для всех языков из API
                if not base_qs.exists():
                    description = ''
                    to_create = []
                    for language in ['ru_RU', 'en_EN', 'de_DE', 'fr_FR', 'es_ES']:
                        lang_meta = {}
                        if api_meta_by_lang and isinstance(api_meta_by_lang, dict):
                            lang_meta = api_meta_by_lang.get(language, {}).get(slug, {})

                        is_en = language == 'en_EN'

                        to_create.append(
                            BoatDescription(
                                boat=pb,
                                language=language,
                                title=(
                                    lang_meta.get('title')
                                    or (meta.get('title') if is_en else '')
                                    or pb.slug
                                ),
                                description=description,
                                location=lang_meta.get('location', meta.get('location', '') if is_en else ''),
                                marina=lang_meta.get('marina', meta.get('marina', '') if is_en else ''),
                                country=lang_meta.get('country', meta.get('country', '') if is_en else ''),
                                region=lang_meta.get('region', meta.get('region', '') if is_en else ''),
                                city=lang_meta.get('city', meta.get('city', '') if is_en else ''),
                            )
                        )
                    BoatDescription.objects.bulk_create(to_create, batch_size=100)
                    base_qs = BoatDescription.objects.filter(boat=pb)

                # Обновляем geo/title/location строго из API соответствующего языка.
                for language in ['ru_RU', 'en_EN', 'de_DE', 'fr_FR', 'es_ES']:
                    lang_meta = {}
                    if api_meta_by_lang and isinstance(api_meta_by_lang, dict):
                        lang_meta = api_meta_by_lang.get(language, {}).get(slug, {})

                    # Критично: не копируем en_EN fallback в другие языки,
                    # если для них не пришёл отдельный API payload.
                    if language != 'en_EN' and not lang_meta:
                        continue

                    if language == 'en_EN':
                        update_payload = {
                            'title': lang_meta.get('title') or meta.get('title') or pb.slug,
                            'location': lang_meta.get('location', meta.get('location', '')),
                            'marina': lang_meta.get('marina', meta.get('marina', '')),
                            'country': lang_meta.get('country', meta.get('country', '')),
                            'region': lang_meta.get('region', meta.get('region', '')),
                            'city': lang_meta.get('city', meta.get('city', '')),
                        }
                    else:
                        update_payload = {
                            'title': lang_meta.get('title') or pb.slug,
                            'location': lang_meta.get('location', ''),
                            'marina': lang_meta.get('marina', ''),
                            'country': lang_meta.get('country', ''),
                            'region': lang_meta.get('region', ''),
                            'city': lang_meta.get('city', ''),
                        }

                    base_qs.filter(language=language).update(**update_payload)

            # --- BoatTechnicalSpecs: создаём при отсутствии + заполняем ---
            specs_qs = BoatTechnicalSpecs.objects.filter(
                boat__slug__in=batch_slugs
            ).select_related('boat')
            specs_map = {s.boat.slug: s for s in specs_qs}

            missing_specs = []
            for slug in batch_slugs:
                pb = boats_map.get(slug)
                if pb and slug not in specs_map:
                    missing_specs.append(BoatTechnicalSpecs(boat=pb))
            if missing_specs:
                BoatTechnicalSpecs.objects.bulk_create(missing_specs, batch_size=500)
                specs_qs = BoatTechnicalSpecs.objects.filter(
                    boat__slug__in=batch_slugs
                ).select_related('boat')
                specs_map = {s.boat.slug: s for s in specs_qs}

            specs_to_update = []
            specs_fields_changed = set()

            for slug in batch_slugs:
                pb = boats_map.get(slug)
                if not pb:
                    continue
                spec = specs_map.get(slug)
                if not spec:
                    continue
                meta = api_meta[slug]
                params = meta.get('parameters', {})
                changed = False

                # Новые поля из API parameters — заполняем если пусты
                for attr, param_key in [
                    ('allowed_people', 'allowed_people'),
                    ('single_cabins', 'single_cabins'),
                    ('double_cabins', 'double_cabins'),
                    ('triple_cabins', 'triple_cabins'),
                    ('quadruple_cabins', 'quadruple_cabins'),
                    ('cabins_with_bunk_bed', 'cabins_with_bunk_bed'),
                    ('saloon_sleeps', 'saloon_sleeps'),
                    ('crew_sleeps', 'crew_sleeps'),
                    ('total_engine_power', 'total_engine_power'),
                ]:
                    val = params.get(param_key)
                    if val is not None and getattr(spec, attr) is None:
                        setattr(spec, attr, int(val))
                        specs_fields_changed.add(attr)
                        changed = True

                # cruising_consumption — float
                cc_val = params.get('cruising_consumption')
                if cc_val is not None and spec.cruising_consumption is None:
                    spec.cruising_consumption = float(cc_val)
                    specs_fields_changed.add('cruising_consumption')
                    changed = True

                # Существующие поля — заполняем только пустые
                for attr, param_key in [
                    ('length', 'length'),
                    ('beam', 'beam'),
                    ('draft', 'draft'),
                    ('cabins', 'cabins'),
                    ('berths', 'max_sleeps'),
                    ('toilets', 'toilets'),
                    ('fuel_capacity', 'fuel'),
                    ('water_capacity', 'water_tank'),
                    ('waste_capacity', 'waste_tank'),
                    ('max_speed', 'maximum_speed'),
                    ('engine_power', 'engine_power'),
                    ('number_engines', 'number_engines'),
                    ('renovated_year', 'renovated_year'),
                    ('sail_renovated_year', 'sail_renovated_year'),
                ]:
                    val = params.get(param_key)
                    if val is not None and val != 0 and getattr(spec, attr) is None:
                        if attr in ('length', 'beam', 'draft', 'max_speed'):
                            setattr(spec, attr, float(val))
                        else:
                            setattr(spec, attr, int(val))
                        specs_fields_changed.add(attr)
                        changed = True

                # engine_type — строка, заполняем только пустое
                et = meta.get('engine_type', '')
                if et and not spec.engine_type:
                    spec.engine_type = et
                    specs_fields_changed.add('engine_type')
                    changed = True

                if changed:
                    specs_to_update.append(spec)

            if specs_to_update and specs_fields_changed:
                BoatTechnicalSpecs.objects.bulk_update(
                    specs_to_update, list(specs_fields_changed), batch_size=500
                )

        return updated
