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
    python manage.py refresh_amenities --async --destination turkey --no-wait
"""

import logging
import time
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
        parser.add_argument(
            '--no-wait',
            action='store_true',
            help='Для --async: не ждать завершения батчей, только отправить в очередь',
        )
        parser.add_argument(
            '--wait-timeout',
            type=int,
            default=7200,
            help='Для --async: таймаут ожидания завершения батчей в секундах (default: 7200)',
        )
        parser.add_argument(
            '--poll-interval',
            type=int,
            default=5,
            help='Для --async: интервал опроса статуса задач в секундах (default: 5)',
        )

    def handle(self, *args, **options):
        async_mode = options['async']
        sync_mode = options['sync']
        limit = options['limit']
        slug = options['slug']
        destination = options['destination']
        batch_size = options['batch_size']
        no_wait = options['no_wait']
        wait_timeout = options['wait_timeout']
        poll_interval = options['poll_interval']

        if not async_mode and not sync_mode:
            raise CommandError('Укажите --async или --sync')
        if async_mode and sync_mode:
            raise CommandError('Используйте только один режим: --async или --sync')
        if batch_size <= 0:
            raise CommandError('--batch-size должен быть > 0')
        if wait_timeout <= 0:
            raise CommandError('--wait-timeout должен быть > 0')
        if poll_interval <= 0:
            raise CommandError('--poll-interval должен быть > 0')

        if slug:
            slugs = [slug]
        elif destination:
            slugs = self._get_slugs_by_destination(destination, limit)
        else:
            qs = ParsedBoat.objects.values_list('slug', flat=True).order_by('id')
            if limit:
                qs = qs[:limit]
            slugs = list(qs)

        slugs = self._normalize_and_dedupe_slugs(slugs)

        self.stdout.write(f'Лодок для обработки: {len(slugs)}')
        if not slugs:
            self.stdout.write(self.style.WARNING('Нет лодок для обработки.'))
            return

        if sync_mode:
            self._run_sync(slugs)
        else:
            self._run_async(
                slugs=slugs,
                batch_size=batch_size,
                wait_for_completion=not no_wait,
                wait_timeout=wait_timeout,
                poll_interval=poll_interval,
            )

    @staticmethod
    def _normalize_slug(slug):
        if not slug:
            return ''
        return str(slug).strip().strip('/').lower()

    @classmethod
    def _normalize_and_dedupe_slugs(cls, slugs):
        normalized = []
        seen = set()
        for slug in slugs:
            clean_slug = cls._normalize_slug(slug)
            if not clean_slug or clean_slug in seen:
                continue
            seen.add(clean_slug)
            normalized.append(clean_slug)
        return normalized

    def _extract_slug_from_boat_payload(self, boat_payload):
        """Возвращает slug из raw payload поиска без дорогого format_boat_data."""
        if not isinstance(boat_payload, dict):
            return ''
        direct = (
            boat_payload.get('slug')
            or boat_payload.get('boatSlug')
            or boat_payload.get('url_slug')
        )
        if direct:
            return self._normalize_slug(direct)
        url = boat_payload.get('url') or boat_payload.get('link')
        if isinstance(url, str):
            parts = [p for p in url.split('/') if p]
            if parts:
                return self._normalize_slug(parts[-1].split('?')[0])
        return ''

    def _get_slugs_by_destination(self, destination, limit=None):
        """Получает slug'и лодок по направлению через API, фильтрует по наличию в БД."""
        from boats.boataround_api import BoataroundAPI

        page_size = 18
        existing_slugs = set(
            self._normalize_and_dedupe_slugs(ParsedBoat.objects.values_list('slug', flat=True))
        )
        found = []
        found_set = set()
        page = 1
        max_pages = None
        safety_pages_limit = 200

        self.stdout.write(f'Получаю лодки для направления "{destination}" через API...')

        while page <= safety_pages_limit:
            try:
                results = BoataroundAPI.search(
                    destination=destination,
                    page=page,
                    limit=page_size,
                    lang='en_EN'
                )
                boats = results.get('boats') if results else []
                if not boats:
                    break

                for boat in boats:
                    boat_slug = self._extract_slug_from_boat_payload(boat)
                    if (
                        boat_slug
                        and boat_slug in existing_slugs
                        and boat_slug not in found_set
                    ):
                        found.append(boat_slug)
                        found_set.add(boat_slug)

                if limit and len(found) >= limit:
                    found = found[:limit]
                    break

                if max_pages is None:
                    try:
                        total = int(results.get('total') or 0)
                        max_pages = (total + page_size - 1) // page_size if total > 0 else None
                    except Exception:
                        max_pages = None

                if max_pages and page >= max_pages:
                    break
                if len(boats) < page_size:
                    break
                page += 1

            except Exception as e:
                logger.error(f'Ошибка при получении лодок для {destination} стр.{page}: {e}')
                break

        if page > safety_pages_limit:
            self.stdout.write(self.style.WARNING(
                f'Достигнут safety limit {safety_pages_limit} страниц для "{destination}"'
            ))

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

    def _run_async(
        self,
        slugs,
        batch_size,
        wait_for_completion=True,
        wait_timeout=7200,
        poll_interval=5,
    ):
        try:
            from boats.tasks import refresh_amenities_batch
        except ImportError:
            raise CommandError('Celery tasks не найдены.')

        active_workers = self._get_active_workers()
        if not active_workers:
            self.stdout.write(self.style.WARNING(
                'Celery inspect не вернул активных воркеров. '
                'Продолжаю отправку батчей в очередь; '
                'проверьте сервис `celery_worker` '
                '(`docker compose logs -f celery_worker`, '
                'контейнер обычно `rent_django-celery_worker-1`).'
            ))
        else:
            self.stdout.write(
                f"Активные Celery workers: {', '.join(sorted(active_workers.keys()))}"
            )

        batches = [slugs[i:i + batch_size] for i in range(0, len(slugs), batch_size)]
        task_ids = []

        for idx, batch in enumerate(batches, 1):
            try:
                task = refresh_amenities_batch.delay(batch)
                task_ids.append(task.id)
                self.stdout.write(f'  Батч {idx}/{len(batches)} отправлен (ID: {task.id})')
            except Exception as e:
                logger.error(f'Ошибка отправки батча {idx}: {e}')

        if not task_ids:
            raise CommandError('Не удалось отправить батчи в Celery очередь.')

        self.stdout.write(
            self.style.SUCCESS(
                f'\n{len(task_ids)} батчей отправлены в очередь Celery!\n'
                f'Всего лодок: {len(slugs)}, размер батча: {batch_size}'
            )
        )

        if not wait_for_completion:
            self.stdout.write(
                'Мониторинг: docker compose logs -f celery_worker '
                '(контейнер обычно rent_django-celery_worker-1)'
            )
            return

        self.stdout.write(
            f'Ожидаю завершения задач (timeout={wait_timeout}s, poll={poll_interval}s)...'
        )
        summary = self._wait_for_async_batches(
            task_ids=task_ids,
            timeout=wait_timeout,
            poll_interval=poll_interval,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Async завершен: батчей {summary['completed_batches']}/{summary['total_batches']}, "
                f"успешно лодок {summary['success_boats']}, ошибок {summary['failed_boats']}, "
                f"ошибок батчей {summary['failed_batches']}"
            )
        )
        if summary['timed_out_batches'] > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"Не дождались {summary['timed_out_batches']} батчей: {', '.join(summary['pending_task_ids'])}"
                )
            )

    def _get_active_workers(self):
        from celery import current_app

        # В проде inspect.ping() с timeout=1 может давать ложный "нет воркеров".
        # Пробуем несколько таймаутов и fallback на inspect.stats().
        last_error = None
        for timeout in (1, 3, 5):
            try:
                inspect = current_app.control.inspect(timeout=timeout)
                if not inspect:
                    continue

                workers = inspect.ping() or {}
                if workers:
                    return workers

                stats = inspect.stats() or {}
                if stats:
                    return {name: {'ok': 'stats-only'} for name in stats.keys()}
            except Exception as e:
                last_error = e
                logger.warning(f'Celery inspect failed (timeout={timeout}s): {e}')

        if last_error:
            logger.warning(f'Celery worker detection failed, last error: {last_error}')
        return {}

    def _wait_for_async_batches(self, task_ids, timeout=7200, poll_interval=5):
        from celery.result import AsyncResult
        from celery.states import READY_STATES

        pending = set(task_ids)
        started_at = time.time()
        summary = {
            'total_batches': len(task_ids),
            'completed_batches': 0,
            'failed_batches': 0,
            'success_boats': 0,
            'failed_boats': 0,
            'timed_out_batches': 0,
            'pending_task_ids': [],
        }

        while pending:
            if time.time() - started_at > timeout:
                break

            just_completed = []
            for task_id in list(pending):
                task_result = AsyncResult(task_id)
                if task_result.state not in READY_STATES:
                    continue

                just_completed.append(task_id)
                summary['completed_batches'] += 1

                if task_result.successful():
                    payload = task_result.result if isinstance(task_result.result, dict) else {}
                    summary['success_boats'] += int(payload.get('success', 0) or 0)
                    summary['failed_boats'] += int(payload.get('failed', 0) or 0)
                else:
                    summary['failed_batches'] += 1

            for done_id in just_completed:
                pending.discard(done_id)

            if pending:
                time.sleep(poll_interval)

        if pending:
            summary['timed_out_batches'] = len(pending)
            summary['pending_task_ids'] = sorted(pending)

        return summary
