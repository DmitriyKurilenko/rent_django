"""
Management command для параллельного парсинга лодок с boataround.com

Использование:
    python manage.py parse_boats_parallel --destination turkey --workers 5
    python manage.py parse_boats_parallel --destination turkey --workers 15 --skip-existing
    python manage.py parse_boats_parallel --destination turkey --workers 5 --verbose
    python manage.py parse_boats_parallel --destination turkey --no-cache  # без кэша slug'ов
    python manage.py parse_boats_parallel --destination turkey --cache-ttl 48  # кэш на 48 часов
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
from boats.parser import parse_boataround_url
from boats.models import ParsedBoat
from django import db

logger = logging.getLogger(__name__)

CACHE_DIR = Path('/tmp/parse_boats_cache')


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

        # Читаем из кэша только если не --no-cache и не --refresh-cache
        if not no_cache and not refresh_cache:
            all_slugs = self._load_cache(destination, cache_ttl, max_pages)
            if all_slugs is not None:
                cache_hit = True
                search_stats['cache'] = True
                self.stdout.write(f'   ⚡ Загружено из кэша: {len(all_slugs)} slug\'ов')

        if all_slugs is None:
            all_slugs, search_stats = self._fetch_all_slugs(
                destination, max_pages
            )
            # Сохраняем в кэш если не --no-cache
            if not no_cache and all_slugs:
                self._save_cache(destination, max_pages, all_slugs)
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

        # --- Фаза 2: Парсинг ---
        self.stdout.write(f'🔄 Фаза 2: Парсинг {total} лодок ({workers} воркеров)...')
        phase2_start = time.time()

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
                result = parse_boataround_url(url, save_to_db=True)
                if result:
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

        # --- Фаза 3: Итоговый отчёт ---
        total_time = phase1_time + phase2_time

        from boats.models import BoatGallery, BoatDescription, BoatPrice, BoatDetails, BoatTechnicalSpecs
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
        self.stdout.write(f'  Парсинг:')
        self.stdout.write(f'    Успешно:       {stats["success"]}')
        self.stdout.write(f'    Ошибки:        {stats["failed"]}')
        self.stdout.write(f'    Фото загр.:    {stats["photos"]}')
        self.stdout.write(f'    Скорость:      {stats["success"] / phase2_time:.1f} лодок/s' if phase2_time > 0 else '')
        self.stdout.write('')
        self.stdout.write(f'  База данных (всего):')
        self.stdout.write(f'    ParsedBoat:    {db_stats["parsed_boats"]}')
        self.stdout.write(f'    Фото:          {db_stats["photos"]}')
        self.stdout.write(f'    Описания:      {db_stats["descriptions"]}')
        self.stdout.write(f'    Цены:          {db_stats["prices"]}')
        self.stdout.write(f'    Детали:        {db_stats["details"]}')
        self.stdout.write(f'    Тех. спеки:    {db_stats["specs"]}')
        self.stdout.write('')
        self.stdout.write(f'  Время:')
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
        """Загружает slug'и из кэша, если он свежий. Возвращает list или None."""
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

            slugs = data.get('slugs', [])
            cached_at = data.get('cached_at', '?')
            self.stdout.write(f'   Кэш от {cached_at} ({age_hours:.1f}ч назад)')
            return slugs
        except Exception as e:
            logger.warning(f'Ошибка чтения кэша: {e}')
            return None

    def _save_cache(self, destination, max_pages, slugs):
        """Сохраняет slug'и в кэш."""
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path = self._cache_path(destination, max_pages)
            data = {
                'destination': destination or 'all',
                'max_pages': max_pages,
                'count': len(slugs),
                'cached_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'slugs': slugs,
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
        """
        slugs = []
        seen = set()
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
                    limit=50,
                    lang='en_EN'
                )

                if not results or not results.get('boats'):
                    break

                search_stats['pages_scanned'] += 1

                for boat in results['boats']:
                    try:
                        formatted = format_boat_data(boat)
                    except Exception:
                        formatted = {}

                    boat_slug = formatted.get('slug')
                    if not boat_slug or boat_slug in seen:
                        continue

                    seen.add(boat_slug)
                    slugs.append(boat_slug)
                    count += 1

                if total_pages is None:
                    try:
                        total_pages = int(results.get('totalPages') or 1)
                    except Exception:
                        total_pages = 1

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

        return slugs, search_stats
