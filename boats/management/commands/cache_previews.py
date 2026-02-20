"""
Management command для загрузки превью лодок на CDN.

Источник превью — поле thumb из поискового API Boataround.
Загружает через download_and_save_image() → S3 → сохраняет CDN URL в ParsedBoat.preview_cdn_url.

Фаза 1 (сбор thumb из API) кэшируется в JSON-файл, чтобы при ошибке
на следующих фазах не повторять ~50 мин запрос к API.

Использование:
    python manage.py cache_previews                    # загрузить превью
    python manage.py cache_previews --dry-run          # только посчитать
    python manage.py cache_previews --force            # перезаписать все
    python manage.py cache_previews --destination turkey  # только Турция
    python manage.py cache_previews --workers 10       # 10 потоков для скачивания
    python manage.py cache_previews --max-pages 5      # первые 5 страниц API
    python manage.py cache_previews --no-cache         # не использовать кэш Фазы 1
"""

import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand
from django import db

from boats.boataround_api import BoataroundAPI
from boats.models import ParsedBoat
from boats.parser import download_and_save_image, IMAGE_HOST

logger = logging.getLogger(__name__)

CACHE_FILE = Path(settings.BASE_DIR) / 'thumbs_cache.json'


def extract_image_path(thumb_url: str) -> str | None:
    """Извлекает путь изображения из thumb URL для download_and_save_image().

    Пример:
        https://imageresizer.yachtsbt.com/boats/62b.../650d...jpg?method=fit&width=400
        → boats/62b.../650d...jpg
    """
    if not thumb_url:
        return None

    try:
        parsed = urlparse(thumb_url)
        path = parsed.path.lstrip('/')
        # Ожидаем формат: boats/{24-char-id}/{filename}
        if path.startswith('boats/'):
            return path
        return None
    except Exception:
        return None


class Command(BaseCommand):
    help = 'Загрузка превью лодок на CDN из поискового API Boataround'

    def add_arguments(self, parser):
        parser.add_argument(
            '--workers',
            type=int,
            default=5,
            help='Потоки для скачивания (default: 5)',
        )
        parser.add_argument(
            '--destination',
            type=str,
            default=None,
            help='Фильтр по направлению (e.g., "turkey")',
        )
        parser.add_argument(
            '--max-pages',
            type=int,
            default=None,
            help='Лимит страниц API',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Перезаписать существующие превью',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Только подсчёт, без скачивания',
        )
        parser.add_argument(
            '--no-cache',
            action='store_true',
            help='Не использовать кэш Фазы 1 (перезапросить API)',
        )

    def handle(self, *args, **options):
        workers = options['workers']
        destination = options['destination']
        max_pages = options['max_pages']
        force = options['force']
        dry_run = options['dry_run']
        no_cache = options['no_cache']

        # Suppress noisy logs
        logging.getLogger('boats.parser').setLevel(logging.WARNING)
        logging.getLogger('boats.boataround_api').setLevel(logging.WARNING)

        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('  CACHE PREVIEWS → CDN'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(f'  Направление:  {destination or "все"}')
        self.stdout.write(f'  Воркеры:      {workers}')
        self.stdout.write(f'  Force:        {force}')
        self.stdout.write(f'  Dry run:      {dry_run}')
        self.stdout.write('')

        # --- Фаза 1: Сбор thumb URL из API (с кэшированием) ---
        previews = None

        if not no_cache and CACHE_FILE.exists():
            try:
                cached = json.loads(CACHE_FILE.read_text())
                # Проверяем что кэш для того же destination
                if cached.get('destination') == destination:
                    previews = cached['previews']
                    self.stdout.write(self.style.SUCCESS(
                        f'📋 Фаза 1: Загружено из кэша ({CACHE_FILE.name}): '
                        f'{len(previews)} превью'
                    ))
                else:
                    self.stdout.write(
                        f'   Кэш для другого направления '
                        f'({cached.get("destination")}), перезапрашиваю...'
                    )
            except Exception as e:
                self.stdout.write(f'   Ошибка чтения кэша: {e}, перезапрашиваю...')

        if previews is None:
            self.stdout.write('📋 Фаза 1: Сбор превью из API...')
            phase1_start = time.time()

            previews = self._fetch_all_thumbs(destination, max_pages)

            phase1_time = time.time() - phase1_start
            self.stdout.write(f'   Найдено лодок с thumb: {len(previews)}')
            self.stdout.write(f'   Время: {phase1_time:.1f}s')

            # Сохраняем кэш
            if previews:
                CACHE_FILE.write_text(json.dumps({
                    'destination': destination,
                    'previews': previews,
                }, ensure_ascii=False))
                self.stdout.write(f'   Кэш сохранён: {CACHE_FILE.name}')

        self.stdout.write('')

        if not previews:
            self.stdout.write(self.style.WARNING('Не найдено лодок с превью'))
            return

        # --- Фаза 2: Фильтрация ---
        if not force:
            # Только лодки без превью в БД
            existing = set(
                ParsedBoat.objects.filter(preview_cdn_url__gt='')
                .values_list('boat_id', flat=True)
            )
            before = len(previews)
            previews = {bid: path for bid, path in previews.items() if bid not in existing}
            skipped = before - len(previews)
            if skipped:
                self.stdout.write(f'   Уже есть превью: {skipped} (пропускаем)')

        # Только лодки, которые есть в БД
        known_ids = set(
            ParsedBoat.objects.filter(boat_id__in=list(previews.keys()))
            .values_list('boat_id', flat=True)
        )
        previews = {bid: path for bid, path in previews.items() if bid in known_ids}

        self.stdout.write(f'   К обработке: {len(previews)}')
        self.stdout.write('')

        if not previews:
            self.stdout.write(self.style.SUCCESS('Все превью уже загружены!'))
            return

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f'DRY RUN: нужно загрузить {len(previews)} превью'
            ))
            return

        # --- Фаза 3: Скачивание и загрузка на CDN ---
        self.stdout.write(f'🔄 Фаза 3: Загрузка {len(previews)} превью ({workers} воркеров)...')
        phase3_start = time.time()

        db.connections.close_all()

        stats = {'success': 0, 'failed': 0}
        total = len(previews)
        items = list(previews.items())

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._process_one, boat_id, image_path): boat_id
                for boat_id, image_path in items
            }

            for future in as_completed(futures):
                boat_id = futures[future]
                try:
                    cdn_url = future.result()
                    if cdn_url:
                        stats['success'] += 1
                    else:
                        stats['failed'] += 1
                except Exception as e:
                    stats['failed'] += 1
                    logger.error(f"Error processing {boat_id}: {e}")

                done = stats['success'] + stats['failed']
                if done % 50 == 0 or done == total:
                    sys.stdout.write(
                        f'\r   📸 {done}/{total} '
                        f'(ok: {stats["success"]}, fail: {stats["failed"]})'
                    )
                    sys.stdout.flush()

        phase3_time = time.time() - phase3_start

        # Удаляем кэш после успешной загрузки
        if CACHE_FILE.exists() and stats['failed'] == 0:
            CACHE_FILE.unlink()
            self.stdout.write('   Кэш удалён (все превью загружены)')

        self.stdout.write('')
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('  РЕЗУЛЬТАТ'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(f'  Загружено:  {stats["success"]}')
        self.stdout.write(f'  Ошибок:     {stats["failed"]}')
        self.stdout.write(f'  Время:      {phase3_time:.1f}s')
        self.stdout.write('')

    def _process_one(self, boat_id: str, image_path: str) -> str | None:
        """Скачивает превью и сохраняет CDN URL в ParsedBoat."""
        try:
            cdn_url = download_and_save_image(image_path)
            if not cdn_url:
                return None

            ParsedBoat.objects.filter(boat_id=boat_id).update(
                preview_cdn_url=cdn_url
            )
            return cdn_url
        except Exception as e:
            logger.error(f"Failed to process preview for {boat_id}: {e}")
            return None

    def _fetch_all_thumbs(self, destination=None, max_pages=None) -> dict:
        """Получает boat_id → image_path из API постранично.

        Returns:
            dict: {boat_id: image_path} где image_path — путь для download_and_save_image()
        """
        result = {}
        page = 1
        total_pages = None

        label = destination or 'весь каталог'

        while True:
            try:
                data = BoataroundAPI.search(
                    destination=destination,
                    page=page,
                    limit=18,
                    lang='en_EN'
                )

                if not data or not data.get('boats'):
                    break

                for boat in data['boats']:
                    boat_id = boat.get('_id') or boat.get('id')
                    thumb = boat.get('thumb') or boat.get('main_img', '')

                    if not boat_id or not thumb:
                        continue

                    image_path = extract_image_path(thumb)
                    if image_path:
                        result[str(boat_id)] = image_path

                if total_pages is None:
                    total_pages = int(data.get('totalPages') or 1)

                effective_total = total_pages
                if max_pages:
                    effective_total = min(effective_total, max_pages)

                if page % 20 == 0:
                    sys.stdout.write(
                        f'\r   🔍 {label}... стр. {page}/{effective_total}, '
                        f'{len(result)} превью'
                    )
                    sys.stdout.flush()

                if page >= effective_total:
                    break

                page += 1

            except Exception as e:
                logger.error(f"Error fetching page {page}: {e}")
                break

        self.stdout.write(
            f'\r   🔍 {label}... {len(result)} превью ({page} стр.)' + ' ' * 20
        )
        return result
