"""
Management command для парсинга лодок через Celery.

Три режима:
    --mode api    — только API-метаданные (country, region, charter, specs)
    --mode html   — только HTML-парсинг (фото, extras, описания, amenities)
    --mode full   — оба (сначала API, потом HTML)

Выполнение — батчами через Celery, не блокирует сервер.
Отчёт сохраняется в модели ParseJob: краткий + подробный лог.

Примеры:
    python manage.py parse_boats --mode api
    python manage.py parse_boats --mode html --destination turkey --batch-size 30
    python manage.py parse_boats --mode full --max-pages 10
    python manage.py parse_boats --mode api --destination croatia --skip-existing
    python manage.py parse_boats --status                         # Показать статусы
    python manage.py parse_boats --status <job_id>                # Детали по заданию
"""

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Запуск парсинга лодок через Celery батчами. '
        'Режимы: api (метаданные), html (полный парсинг), full (оба).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--mode',
            type=str,
            choices=['api', 'html', 'full'],
            default='full',
            help='Режим: api | html | full (default: full)',
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
            help='Пропускать лодки, уже существующие в БД (только для mode=html)',
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

        return self._dispatch_job(options)

    def _dispatch_job(self, options):
        """Создаёт ParseJob и отправляет в Celery."""
        from boats.models import ParseJob
        from boats.tasks import run_parse_job

        mode = options['mode']
        destination = options['destination']
        max_pages = options.get('max_pages')
        batch_size = options['batch_size']
        skip_existing = options['skip_existing']

        # Проверка: skip-existing имеет смысл только для html/full
        if skip_existing and mode == 'api':
            self.stdout.write(self.style.WARNING(
                '--skip-existing игнорируется для mode=api (API всегда обновляет)'
            ))
            skip_existing = False

        # Проверяем доступность Celery
        if not self._check_celery():
            self.stdout.write(self.style.ERROR(
                'Celery worker не обнаружен. Запустите worker перед использованием.'
            ))
            return

        job = ParseJob.objects.create(
            mode=mode,
            destination=destination,
            max_pages=max_pages,
            batch_size=batch_size,
            skip_existing=skip_existing,
        )

        # Запускаем оркестратор
        task = run_parse_job.delay(str(job.job_id))
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

    def _show_status(self, job_id_or_list):
        """Показывает статус заданий парсинга."""
        from boats.models import ParseJob

        if job_id_or_list == '__list__':
            return self._show_status_list()

        # Показ конкретного задания
        try:
            job = ParseJob.objects.get(job_id=job_id_or_list)
        except ParseJob.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Задание {job_id_or_list} не найдено'))
            return
        except Exception:
            # Попробуем по частичному ID
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

        # Цвет статуса
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
