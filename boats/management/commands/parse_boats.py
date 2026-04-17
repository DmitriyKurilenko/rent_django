"""
Management command для парсинга лодок через Celery.

Три режима:
    --mode api    — API source-of-truth (все API-данные; HTML поля не трогаются)
    --mode html   — только HTML: фото + extras/additional_services/delivery_extras/not_included
                    + cockpit/entertainment/equipment (amenities — HTML-owned)
    --mode full   — полностью HTML (legacy full HTML profile)

Без --workers — батчами через Celery chord (не блокирует, проверять через --status).
С --workers N — быстрый Celery task с N параллельными потоками, live-прогресс.

Примеры:
    # Базовый HTML-парсинг 8 потоками
    python manage.py parse_boats --mode html --workers 8

    # Конкретное направление
    python manage.py parse_boats --mode html --workers 8 --destination turkey

    # Пропустить лодки, пропарсенные менее 24ч назад (default)
    python manage.py parse_boats --mode html --workers 8 --skip-fresh

    # Пропустить лодки, пропарсенные менее 12ч назад
    python manage.py parse_boats --mode html --workers 8 --skip-fresh 12

    # API-парсинг
    python manage.py parse_boats --mode api --workers 4

    # Повтор ошибок из последнего задания
    python manage.py parse_boats --retry-errors --mode html --workers 8

    # Батчевый режим (без live-прогресса)
    python manage.py parse_boats --mode html --destination turkey --batch-size 30

    # Ограничение страниц (тест)
    python manage.py parse_boats --mode full --max-pages 10

    # Статусы заданий
    python manage.py parse_boats --status
    python manage.py parse_boats --status <job_id>
"""

import logging
import sys
import time

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Парсинг лодок через Celery. '
        '--workers N для быстрого параллельного режима. '
        'Режимы: api, html, full.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--mode',
            type=str,
            choices=['api', 'html', 'full'],
            default='full',
            help='Режим: api (API), html (HTML: фото+сервисы), full (всё из HTML)',
        )
        parser.add_argument(
            '--destination',
            type=str,
            default='',
            help='Направление (slug), например "turkey", "croatia". Пусто = весь каталог.',
        )
        parser.add_argument(
            '--max-pages',
            type=int,
            default=None,
            help='Ограничение по числу страниц API (18 лодок/стр.)',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='Размер одного Celery-батча (default: 50)',
        )
        parser.add_argument(
            '--skip-existing',
            action='store_true',
            help='Пропускать лодки, уже существующие в БД (для mode=html/full)',
        )
        parser.add_argument(
            '--skip-fresh',
            type=int,
            nargs='?',
            const=24,
            default=None,
            metavar='HOURS',
            help='Пропускать лодки, пропарсенные менее N часов назад (default: 24ч).',
        )
        parser.add_argument(
            '--no-cache',
            action='store_true',
            help='Сбросить кэш slug\'ов и собрать заново.',
        )
        parser.add_argument(
            '--workers',
            type=int,
            default=None,
            help='Быстрый режим: число параллельных потоков в Celery task.',
        )
        parser.add_argument(
            '--retry-errors',
            action='store_true',
            help='Повторить ошибочные slug\'ы из последнего задания (требует --workers).',
        )
        parser.add_argument(
            '--status',
            nargs='?',
            const='__list__',
            default=None,
            metavar='JOB_ID',
            help='Показать статусы заданий. Без аргумента — последние 10. С UUID — детали.',
        )

    def handle(self, *args, **options):
        if options['status'] is not None:
            return self._show_status(options['status'])

        if options.get('retry_errors') and not options.get('workers'):
            self.stdout.write(self.style.ERROR(
                '--retry-errors требует --workers N'
            ))
            return

        if options.get('workers'):
            return self._dispatch_workers_job(options)

        return self._dispatch_job(options)

    # ------------------------------------------------------------------
    # CELERY CHORD DISPATCH (standard batch mode)
    # ------------------------------------------------------------------

    def _dispatch_job(self, options):
        """Создаёт ParseJob и отправляет batch'и в Celery chord."""
        from boats.models import ParseJob
        from boats.tasks import run_parse_job

        mode = options['mode']
        destination = options['destination']
        max_pages = options.get('max_pages')
        batch_size = options['batch_size']
        skip_existing = options['skip_existing']

        if skip_existing and mode == 'api':
            self.stdout.write(self.style.WARNING(
                '--skip-existing игнорируется для mode=api (API всегда обновляет)'
            ))
            skip_existing = False

        if not self._check_celery():
            self.stdout.write(self.style.ERROR(
                'Celery worker не обнаружен. Запустите worker.'
            ))
            return

        job = ParseJob.objects.create(
            mode=mode,
            destination=destination,
            max_pages=max_pages,
            batch_size=batch_size,
            skip_existing=skip_existing,
        )

        no_cache = options.get('no_cache', False)
        task = run_parse_job.delay(str(job.job_id), no_cache=no_cache)
        job.celery_task_id = task.id
        job.save(update_fields=['celery_task_id'])

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('═' * 60))
        self.stdout.write(self.style.SUCCESS('  PARSE BOATS — задание создано'))
        self.stdout.write(self.style.SUCCESS('═' * 60))
        self.stdout.write(f'  Job ID:       {job.job_id}')
        self.stdout.write(f'  Режим:        {job.get_mode_display()}')
        self.stdout.write(f'  Направление:  {destination or "все"}')
        self.stdout.write(f'  Макс. стр.:   {max_pages or "нет"}')
        self.stdout.write(f'  Батч:         {batch_size}')
        self.stdout.write(f'  Skip exist:   {skip_existing}')
        self.stdout.write(f'  Celery task:  {task.id}')
        self.stdout.write('')
        self.stdout.write('  Задание отправлено в Celery. Проверить статус:')
        self.stdout.write(f'  python manage.py parse_boats --status {job.job_id}')
        self.stdout.write(self.style.SUCCESS('═' * 60))

    # ------------------------------------------------------------------
    # FAST PARALLEL DISPATCH (--workers N)
    # ------------------------------------------------------------------

    def _dispatch_workers_job(self, options):
        """Быстрый режим: один Celery task с ThreadPoolExecutor внутри."""
        from boats.models import ParseJob
        from boats.tasks import run_parse_workers

        mode = options['mode']
        workers = options['workers']
        destination = options['destination']
        retry_errors = options.get('retry_errors', False)
        skip_existing = options['skip_existing']

        if skip_existing and mode == 'api':
            self.stdout.write(self.style.WARNING(
                '--skip-existing игнорируется для mode=api'
            ))
            skip_existing = False

        if not self._check_celery():
            self.stdout.write(self.style.ERROR(
                'Celery worker не обнаружен. Запустите worker.'
            ))
            return

        # --retry-errors: slug'и из последнего задания с ошибками
        retry_slugs = None
        if retry_errors:
            last_job = ParseJob.objects.filter(
                mode=mode,
                status__in=['partial', 'failed', 'completed'],
            ).exclude(errors=[]).order_by('-created_at').first()

            if not last_job or not last_job.errors:
                self.stdout.write(self.style.ERROR(
                    f'Нет завершённых заданий с ошибками для mode={mode}'
                ))
                return

            retry_slugs = [
                err['slug'] for err in last_job.errors
                if isinstance(err, dict) and err.get('slug')
            ]
            if not retry_slugs:
                self.stdout.write(self.style.ERROR('Ошибочные slug\'ы не найдены'))
                return

        job = ParseJob.objects.create(
            mode=mode,
            destination=destination,
            max_pages=options.get('max_pages'),
            batch_size=options.get('batch_size', 50),
            skip_existing=skip_existing,
        )

        task = run_parse_workers.delay(
            str(job.job_id),
            workers=workers,
            retry_slugs=retry_slugs,
            no_cache=options.get('no_cache', False),
            skip_fresh_hours=options.get('skip_fresh'),
        )
        job.celery_task_id = task.id
        job.save(update_fields=['celery_task_id'])

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('═' * 60))
        self.stdout.write(self.style.SUCCESS('  PARSE BOATS — быстрый режим'))
        self.stdout.write(self.style.SUCCESS('═' * 60))
        self.stdout.write(f'  Job ID:       {job.job_id}')
        self.stdout.write(f'  Режим:        {job.get_mode_display()}')
        self.stdout.write(f'  Workers:      {workers}')
        self.stdout.write(f'  Направление:  {destination or "все"}')
        if retry_errors:
            self.stdout.write(f'  Retry:        {len(retry_slugs)} slug\'ов')
        self.stdout.write(f'  Skip exist:   {skip_existing}')
        if options.get('skip_fresh'):
            self.stdout.write(f'  Skip fresh:   < {options["skip_fresh"]}ч')
        self.stdout.write(self.style.SUCCESS('═' * 60))
        self.stdout.write('')

        # Live-прогресс (Ctrl+C не убивает задание)
        self._poll_progress(job)

    def _poll_progress(self, job):
        """Опрашивает ParseJob и рисует live-прогресс."""
        is_tty = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()

        try:
            while True:
                time.sleep(2)
                job.refresh_from_db()

                if job.status in ('completed', 'failed', 'partial', 'cancelled'):
                    break

                total = job.total_slugs or 0
                done = job.processed or 0

                if total == 0:
                    status_text = (
                        'сбор slug\'ов' if job.status == 'collecting'
                        else job.status
                    )
                    line = f'\r  ⏳ {status_text}...'
                else:
                    pct = done * 100 // total if total else 0
                    bar_len = 30
                    filled = bar_len * done // total if total else 0
                    bar = '█' * filled + '░' * (bar_len - filled)
                    line = (
                        f'\r  [{bar}] {pct}% '
                        f'({done}/{total}) '
                        f'ok={job.success} '
                        f'err={job.failed}'
                    )

                if is_tty:
                    sys.stdout.write(line)
                    sys.stdout.flush()

        except KeyboardInterrupt:
            if is_tty:
                sys.stdout.write('\n')
            self.stdout.write(self.style.WARNING(
                '  Ctrl+C — задание продолжает работать в Celery.'
            ))
            self.stdout.write(
                f'  Проверить: python manage.py parse_boats --status {job.job_id}'
            )
            return

        if is_tty:
            sys.stdout.write('\n')
            sys.stdout.flush()

        # Итоговый отчёт
        job.refresh_from_db()
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('═' * 60))
        self.stdout.write(self.style.SUCCESS('  ИТОГО'))
        self.stdout.write(self.style.SUCCESS('═' * 60))
        self.stdout.write(f'  Статус:       {job.get_status_display()}')
        self.stdout.write(f'  Обработано:   {job.processed}/{job.total_slugs}')
        self.stdout.write(f'  Успешно:      {job.success}')
        self.stdout.write(f'  Ошибки:       {job.failed}')

        if job.duration_seconds:
            d = job.duration_seconds
            rate = job.processed / d if d > 0 else 0
            self.stdout.write(f'  Время:        {int(d)}с ({d / 60:.1f} мин)')
            self.stdout.write(f'  Скорость:     {rate:.2f}/с')

        errors = job.errors if isinstance(job.errors, list) else []
        if errors:
            shown = errors[:20]
            self.stdout.write('')
            self.stdout.write(
                f'  --- Ошибки (первые {len(shown)} из {len(errors)}) ---'
            )
            for err in shown:
                if isinstance(err, dict):
                    self.stdout.write(
                        f'  ❌ {err.get("slug", "?")}: {err.get("error", "?")[:80]}'
                    )

        self.stdout.write(self.style.SUCCESS('═' * 60))

        if errors:
            self.stdout.write(
                f'\n  Повтор ошибок:\n'
                f'  python manage.py parse_boats --retry-errors'
                f' --mode {job.mode} --workers N'
            )

    # ------------------------------------------------------------------
    # STATUS
    # ------------------------------------------------------------------

    def _show_status(self, job_id_or_list):
        """Показывает статус заданий парсинга."""
        from boats.models import ParseJob

        if job_id_or_list == '__list__':
            return self._show_status_list()

        try:
            job = ParseJob.objects.get(job_id=job_id_or_list)
        except ParseJob.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Задание {job_id_or_list} не найдено'))
            return
        except Exception:
            jobs = ParseJob.objects.filter(job_id__startswith=job_id_or_list)
            if jobs.count() == 1:
                job = jobs.first()
            elif jobs.count() > 1:
                self.stdout.write(self.style.WARNING(
                    f'Найдено {jobs.count()} заданий. Уточните ID.'
                ))
                for j in jobs[:5]:
                    self.stdout.write(f'  {j.job_id} [{j.get_status_display()}]')
                return
            else:
                self.stdout.write(self.style.ERROR(f'Задание {job_id_or_list} не найдено'))
                return

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('═' * 60))
        self.stdout.write(self.style.SUCCESS(f'  PARSE JOB: {job.job_id}'))
        self.stdout.write(self.style.SUCCESS('═' * 60))
        self.stdout.write(f'  Режим:        {job.get_mode_display()}')
        self.stdout.write(f'  Направление:  {job.destination or "все"}')

        status_str = job.get_status_display()
        if job.status == 'completed':
            self.stdout.write(f'  Статус:       {self.style.SUCCESS(status_str)}')
        elif job.status in ('failed', 'cancelled'):
            self.stdout.write(f'  Статус:       {self.style.ERROR(status_str)}')
        elif job.status in ('running', 'collecting'):
            self.stdout.write(f'  Статус:       {self.style.WARNING(status_str)}')
        else:
            self.stdout.write(f'  Статус:       {status_str}')

        self.stdout.write(f'  Прогресс:     {job.progress_pct}%')
        self.stdout.write(f'  Обработано:   {job.processed}/{job.total_slugs}')
        self.stdout.write(f'  Успешно:      {job.success}')
        self.stdout.write(f'  Ошибки:       {job.failed}')
        self.stdout.write(f'  Пропущено:    {job.skipped}')
        self.stdout.write(f'  Батчи:        {job.batches_done}/{job.total_batches}')

        if job.started_at:
            self.stdout.write(f'  Начало:       {job.started_at.strftime("%Y-%m-%d %H:%M:%S")}')
        if job.finished_at:
            self.stdout.write(f'  Завершение:   {job.finished_at.strftime("%Y-%m-%d %H:%M:%S")}')
        if job.duration_seconds:
            d = job.duration_seconds
            self.stdout.write(f'  Время:        {int(d)}с ({d / 60:.1f} мин)')

        if job.summary:
            self.stdout.write('')
            self.stdout.write('  --- Краткий отчёт ---')
            for line in job.summary.split('\n'):
                self.stdout.write(f'  {line}')

        errors = job.errors if isinstance(job.errors, list) else []
        if errors:
            self.stdout.write('')
            self.stdout.write(f'  --- Ошибки (первые 20 из {len(errors)}) ---')
            for err in errors[:20]:
                if isinstance(err, dict):
                    self.stdout.write(
                        f'  ❌ {err.get("slug", "?")}: {err.get("error", "?")[:80]}'
                    )

        self.stdout.write(self.style.SUCCESS('═' * 60))

    def _show_status_list(self):
        """Показывает список последних заданий."""
        from boats.models import ParseJob

        jobs = ParseJob.objects.all()[:10]
        if not jobs:
            self.stdout.write('Нет заданий парсинга')
            return

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('═' * 80))
        self.stdout.write(self.style.SUCCESS('  ЗАДАНИЯ ПАРСИНГА (последние 10)'))
        self.stdout.write(self.style.SUCCESS('═' * 80))
        self.stdout.write(
            f'  {"ID":<38} {"Режим":<8} {"Статус":<12} {"Прогресс":<12} {"Создано"}'
        )
        self.stdout.write('  ' + '─' * 76)

        for job in jobs:
            status_str = job.get_status_display()
            progress = f'{job.progress_pct}%' if job.total_slugs > 0 else '—'
            created = job.created_at.strftime('%m-%d %H:%M') if job.created_at else '—'
            short_id = str(job.job_id)[:36]
            self.stdout.write(
                f'  {short_id:<38} {job.mode:<8} {status_str:<12} {progress:<12} {created}'
            )

        self.stdout.write(self.style.SUCCESS('═' * 80))
        self.stdout.write('  Детали: python manage.py parse_boats --status <JOB_ID>')

    def _check_celery(self):
        """Проверяет доступность хотя бы одного Celery worker."""
        try:
            from boat_rental.celery import app
            inspector = app.control.inspect(timeout=3.0)
            active = inspector.active_queues()
            return bool(active)
        except Exception:
            return False
