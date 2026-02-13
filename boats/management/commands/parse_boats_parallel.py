"""
Management command для параллельного парсинга лодок с boataround.com

Обёртка над parse_all_boats с поддержкой нескольких воркеров (потоков).

Использование:
    python manage.py parse_boats_parallel --destination turkey --workers 5
    python manage.py parse_boats_parallel --destination turkey --workers 5 --skip-existing --limit 100
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.core.management.base import BaseCommand, CommandError
from boats.boataround_api import BoataroundAPI
from boats.parser import parse_boataround_url
from boats.models import ParsedBoat
from django import db

logger = logging.getLogger(__name__)


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

    def handle(self, *args, **options):
        workers = options['workers']
        limit = options['limit']
        destination = options['destination']
        skip_existing = options['skip_existing']
        max_pages = options.get('max_pages')

        self.stdout.write(self.style.SUCCESS(
            f'🚀 Параллельный парсинг ({workers} воркеров)...'
        ))

        # Собираем список slug'ов
        self.stdout.write('📋 Получаю список лодок через API...')
        boat_slugs = self._get_all_boat_slugs(destination, limit, skip_existing, max_pages)

        if not boat_slugs:
            self.stdout.write(self.style.WARNING('❌ Не найдено лодок для парсинга'))
            return

        total = len(boat_slugs)
        self.stdout.write(self.style.SUCCESS(
            f'✅ Найдено {total} лодок. Запуск {workers} воркеров...'
        ))

        # Закрываем старые DB-соединения перед форком потоков
        db.connections.close_all()

        success = 0
        failed = 0
        lock = threading.Lock()

        def parse_one(slug):
            """Парсинг одной лодки в отдельном потоке."""
            try:
                url = f'https://www.boataround.com/ru/yachta/{slug}/'
                result = parse_boataround_url(url, save_to_db=True)
                return (slug, bool(result))
            except Exception as e:
                logger.error(f"Ошибка при парсинге {slug}: {e}")
                return (slug, False)
            finally:
                db.connection.close()

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(parse_one, slug): slug for slug in boat_slugs}

            for idx, future in enumerate(as_completed(futures), 1):
                slug, ok = future.result()
                with lock:
                    if ok:
                        success += 1
                    else:
                        failed += 1

                if idx % 10 == 0 or idx == total:
                    self.stdout.write(
                        f'  [{idx}/{total}] ✅ {success} / ❌ {failed}'
                    )

        self.stdout.write(self.style.SUCCESS(
            f'\n🏁 Парсинг завершён!\n'
            f'  Успешно: {success}\n'
            f'  Ошибок: {failed}\n'
            f'  Всего: {total}\n'
            f'  Воркеров: {workers}'
        ))

    def _get_all_boat_slugs(self, destination=None, limit=None, skip_existing=False, max_pages=None):
        """Получает список всех slug'ов лодок через API."""
        slugs = set()

        if destination:
            destinations = [destination]
        else:
            destinations = [
                'turkey', 'greece', 'croatia', 'italy', 'spain', 'france',
                'portugal', 'malta', 'cyprus', 'bahamas', 'bvi', 'usvi',
                'mexico', 'french-polynesia', 'new-zealand', 'australia'
            ]

        for dest in destinations:
            self.stdout.write(f'🔍 Ищу лодки в {dest}...')
            page = 1
            dest_count = 0
            total_pages = None

            while True:
                try:
                    results = BoataroundAPI.search(
                        destination=dest,
                        page=page,
                        limit=50,
                        lang='en_EN'
                    )

                    if not results or not results.get('boats'):
                        break

                    from boats.boataround_api import format_boat_data

                    for boat in results['boats']:
                        try:
                            formatted = format_boat_data(boat)
                        except Exception as e:
                            logger.warning(f"Ошибка форматирования лодки: {e}")
                            formatted = {}

                        boat_id = formatted.get('id')
                        boat_slug = formatted.get('slug')

                        if not boat_id or not boat_slug:
                            continue

                        if skip_existing and ParsedBoat.objects.filter(boat_id=boat_id).exists():
                            continue

                        slugs.add(boat_slug)
                        dest_count += 1

                    if limit and len(slugs) >= limit:
                        return list(slugs)[:limit]

                    if total_pages is None:
                        try:
                            total_pages = int(results.get('totalPages') or 1)
                        except Exception:
                            total_pages = 1

                    effective_total_pages = total_pages
                    if max_pages and isinstance(max_pages, int) and max_pages > 0:
                        effective_total_pages = min(effective_total_pages, max_pages)

                    if page >= effective_total_pages:
                        break

                    page += 1

                except Exception as e:
                    logger.error(f"Ошибка при поиске в {dest} стр.{page}: {e}")
                    break

            self.stdout.write(f'  ✅ Найдено {dest_count} лодок в {dest}')

        return list(slugs)
