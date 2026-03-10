"""
Management command для обновления cockpit/entertainment/equipment у всех лодок в БД.
Используется для восстановления данных после очистки или добавления новой логики извлечения.

Использование:
    python manage.py refresh_amenities --async                          # все лодки через Celery
    python manage.py refresh_amenities --sync                           # все лодки синхронно
    python manage.py refresh_amenities --sync --limit 10               # первые 10 лодок
    python manage.py refresh_amenities --sync --slug bali-42-zephyr    # одна лодка
    python manage.py refresh_amenities --async --destination turkey     # только лодки из направления
    python manage.py refresh_amenities --async --batch-size 20         # батчи по 20
"""

import logging
from django.core.management.base import BaseCommand, CommandError
from boats.models import ParsedBoat

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Обновляет cockpit/entertainment/equipment для лодок в БД (из HTML boataround.com)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--async',
            action='store_true',
            help='Запустить асинхронно через Celery',
        )
        parser.add_argument(
            '--sync',
            action='store_true',
            help='Запустить синхронно',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Ограничить количество лодок',
        )
        parser.add_argument(
            '--slug',
            type=str,
            default=None,
            help='Обработать только одну лодку по slug',
        )
        parser.add_argument(
            '--destination',
            type=str,
            default=None,
            help='Фильтровать по направлению через API (e.g., turkey, greece)',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=20,
            help='Размер батча для Celery (default: 20)',
        )

    def handle(self, *args, **options):
        async_mode = options['async']
        sync_mode = options['sync']
        limit = options['limit']
        slug = options['slug']
        destination = options['destination']
        batch_size = options['batch_size']

        if not async_mode and not sync_mode:
            raise CommandError('Укажите --async или --sync')

        if slug:
            slugs = [slug]
        elif destination:
            slugs = self._get_slugs_by_destination(destination, limit)
        else:
            qs = ParsedBoat.objects.values_list('slug', flat=True).order_by('id')
            if limit:
                qs = qs[:limit]
            slugs = list(qs)

        self.stdout.write(f'Лодок для обработки: {len(slugs)}')

        if sync_mode:
            self._run_sync(slugs)
        else:
            self._run_async(slugs, batch_size)

    def _get_slugs_by_destination(self, destination, limit=None):
        """Получает slug'и лодок по направлению через API, фильтрует по наличию в БД."""
        from boats.boataround_api import BoataroundAPI, format_boat_data

        existing_slugs = set(ParsedBoat.objects.values_list('slug', flat=True))
        found = []
        page = 1
        total_pages = None

        self.stdout.write(f'Получаю лодки для направления "{destination}" через API...')

        while True:
            try:
                results = BoataroundAPI.search(destination=destination, page=page, limit=18, lang='en_EN')
                if not results or not results.get('boats'):
                    break

                for boat in results['boats']:
                    try:
                        formatted = format_boat_data(boat)
                    except Exception:
                        continue
                    boat_slug = formatted.get('slug')
                    if boat_slug and boat_slug in existing_slugs:
                        found.append(boat_slug)

                if limit and len(found) >= limit:
                    found = found[:limit]
                    break

                if total_pages is None:
                    try:
                        total_pages = int(results.get('totalPages') or 1)
                    except Exception:
                        total_pages = 1

                if page >= total_pages:
                    break
                page += 1

            except Exception as e:
                logger.error(f'Ошибка при получении лодок для {destination} стр.{page}: {e}')
                break

        self.stdout.write(f'Найдено {len(found)} лодок в БД для "{destination}"')
        return found

    def _run_sync(self, slugs):
        from boats.parser import _fetch_language_page_data
        from boats.models import BoatDetails

        SUPPORTED_LANGUAGES = ['ru_RU', 'en_EN', 'de_DE', 'fr_FR', 'es_ES']
        total = len(slugs)
        success = 0
        failed = 0

        for idx, slug in enumerate(slugs, 1):
            try:
                boat = ParsedBoat.objects.filter(slug=slug).first()
                if not boat:
                    self.stdout.write(self.style.WARNING(f'  [{idx}/{total}] не найдена: {slug}'))
                    failed += 1
                    continue

                for lang in SUPPORTED_LANGUAGES:
                    lang_data = _fetch_language_page_data(slug, lang)
                    amenities = lang_data['amenities']
                    rows = BoatDetails.objects.filter(boat=boat, language=lang)
                    if rows.exists():
                        rows.update(
                            cockpit=amenities['cockpit'],
                            entertainment=amenities['entertainment'],
                            equipment=amenities['equipment'],
                        )
                    else:
                        BoatDetails.objects.create(
                            boat=boat, language=lang,
                            cockpit=amenities['cockpit'],
                            entertainment=amenities['entertainment'],
                            equipment=amenities['equipment'],
                            extras=[], additional_services=[], delivery_extras=[], not_included=[],
                        )

                success += 1
                if idx % 10 == 0 or idx == total:
                    self.stdout.write(f'  [{idx}/{total}] успешно: {success}, ошибок: {failed}')

            except Exception as e:
                failed += 1
                logger.error(f'refresh_amenities sync error {slug}: {e}')
                self.stdout.write(self.style.ERROR(f'  [{idx}/{total}] ошибка {slug}: {e}'))

        self.stdout.write(self.style.SUCCESS(
            f'\nГотово! Успешно: {success}, ошибок: {failed}, всего: {total}'
        ))

    def _run_async(self, slugs, batch_size):
        try:
            from boats.tasks import refresh_amenities_batch
        except ImportError:
            raise CommandError('Celery tasks не найдены.')

        batches = [slugs[i:i + batch_size] for i in range(0, len(slugs), batch_size)]
        task_ids = []

        for idx, batch in enumerate(batches, 1):
            try:
                task = refresh_amenities_batch.delay(batch)
                task_ids.append(task.id)
                self.stdout.write(f'  Батч {idx}/{len(batches)} отправлен (ID: {task.id})')
            except Exception as e:
                logger.error(f'Ошибка отправки батча {idx}: {e}')

        self.stdout.write(self.style.SUCCESS(
            f'\n{len(task_ids)} батчей отправлены в очередь Celery!\n'
            f'Всего лодок: {len(slugs)}, размер батча: {batch_size}\n'
            f'Мониторинг: docker compose logs -f worker'
        ))
