"""Management command для загрузки дампа лодок батчами (без OOM).

Полностью потоковая загрузка:
- Читает JSON построчно, НЕ загружая файл в память
- Сохраняет батчами в одной транзакции (быстро, мало нагрузки на БД)
- При ошибке батча — пересохраняет поштучно (fallback)
- Пауза между батчами чтобы не перегружать БД
- Retry при потере соединения с БД

Использование:
    python manage.py load_parsed_boats boats/fixtures/boats_full_02.json
    python manage.py load_parsed_boats boats/fixtures/boats_full_02.json --batch-size 200
    python manage.py load_parsed_boats boats/fixtures/boats_full_02.json --dry-run
"""

import json
import logging
import os
import sys
import time

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers import deserialize
from django.db import connection, transaction

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
RETRY_DELAY = 10  # секунд


class Command(BaseCommand):
    help = 'Загружает дамп лодок батчами (потоково, без OOM)'

    def add_arguments(self, parser):
        parser.add_argument(
            'fixture',
            type=str,
            help='Путь к JSON-фикстуре',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=200,
            help='Размер батча (default: 200)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Только подсчитать записи, не загружать',
        )

    def handle(self, *args, **options):
        fixture_path = options['fixture']
        batch_size = options['batch_size']
        dry_run = options['dry_run']

        if not os.path.exists(fixture_path):
            raise CommandError(f'Файл не найден: {fixture_path}')

        file_size_mb = os.path.getsize(fixture_path) / (1024 * 1024)
        self.stdout.write(self.style.SUCCESS(
            f'📂 Файл: {fixture_path} ({file_size_mb:.1f} MB)'
        ))

        if dry_run:
            self._dry_run(fixture_path)
            return

        self.stdout.write(f'🔄 Загрузка в БД (батчами по {batch_size})...')
        self.stdout.write('')

        start_time = time.time()
        saved_total = 0
        errors_total = 0
        skipped_total = 0
        current_model = None
        current_batch = []
        model_saved = 0
        model_errors = 0
        model_skipped = 0
        model_count = 0
        records_read = 0

        for record in self._stream_records(fixture_path):
            records_read += 1
            model_name = record.get('model', '')

            # Модель сменилась — сбрасываем батч и выводим итоги предыдущей
            if model_name != current_model:
                if current_batch:
                    s, e, sk = self._save_batch(current_batch)
                    model_saved += s
                    model_errors += e
                    model_skipped += sk

                if current_model is not None:
                    self.stdout.write(
                        f'  ✅ {model_saved} / ⏭️  {model_skipped} дубл. / ❌ {model_errors} '
                        f'(всего {model_count})'
                    )
                    saved_total += model_saved
                    errors_total += model_errors
                    skipped_total += model_skipped

                current_model = model_name
                current_batch = []
                model_saved = 0
                model_errors = 0
                model_skipped = 0
                model_count = 0
                self.stdout.write(f'\n📦 {model_name}...')

            current_batch.append(record)
            model_count += 1

            # Батч заполнен — сохраняем
            if len(current_batch) >= batch_size:
                s, e, sk = self._save_batch(current_batch)
                model_saved += s
                model_errors += e
                model_skipped += sk
                current_batch = []

                # Прогресс
                if model_count % (batch_size * 10) == 0:
                    elapsed = time.time() - start_time
                    rate = records_read / elapsed if elapsed > 0 else 0
                    sys.stdout.write(
                        f'\r  [{model_count}] ✅ {model_saved} ⏭️  {model_skipped} '
                        f'❌ {model_errors} | {rate:.0f} rec/s'
                    )
                    sys.stdout.flush()

        # Последний батч
        if current_batch:
            s, e, sk = self._save_batch(current_batch)
            model_saved += s
            model_errors += e
            model_skipped += sk

        if current_model is not None:
            self.stdout.write(
                f'  ✅ {model_saved} / ⏭️  {model_skipped} дубл. / ❌ {model_errors} '
                f'(всего {model_count})'
            )
            saved_total += model_saved
            errors_total += model_errors
            skipped_total += model_skipped

        elapsed = time.time() - start_time
        self.stdout.write(self.style.SUCCESS(
            f'\n🏁 Загрузка завершена за {elapsed:.0f}s\n'
            f'  Прочитано: {records_read}\n'
            f'  Сохранено: {saved_total}\n'
            f'  Дубликатов: {skipped_total}\n'
            f'  Ошибок: {errors_total}'
        ))

    def _ensure_connection(self):
        """Проверяет соединение с БД, при необходимости ждёт и переподключается."""
        for attempt in range(MAX_RETRIES):
            try:
                connection.ensure_connection()
                return True
            except Exception:
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_DELAY * (attempt + 1)
                    self.stderr.write(
                        f'⏳ БД недоступна, жду {wait}s (попытка {attempt + 1}/{MAX_RETRIES})...'
                    )
                    time.sleep(wait)
                    connection.close()
        return False

    def _save_batch(self, batch):
        """Сохраняет батч в одной транзакции. При ошибке — fallback поштучно."""
        batch_json = json.dumps(batch, ensure_ascii=False)
        saved = 0
        errors = 0
        skipped = 0

        # Проверяем соединение с БД
        if not self._ensure_connection():
            self.stderr.write('❌ Не удалось подключиться к БД!')
            return 0, len(batch), 0

        try:
            objects = list(deserialize('json', batch_json))
        except Exception as e:
            logger.error(f'Ошибка десериализации: {e}')
            return 0, len(batch), 0

        # Попытка 1: весь батч в одной транзакции (быстро)
        try:
            with transaction.atomic():
                for obj in objects:
                    obj.save()
                    saved += 1
            # Пауза между батчами — даём БД отдышаться
            time.sleep(0.05)
            return saved, 0, 0
        except Exception:
            # Батч упал — откат. Переходим к поштучному сохранению
            saved = 0

        # Попытка 2: поштучно с savepoint (медленно, но надёжно)
        for obj in objects:
            if not self._ensure_connection():
                errors += len(objects) - saved - skipped - errors
                break
            try:
                with transaction.atomic():
                    obj.save()
                    saved += 1
            except Exception as e:
                err_msg = str(e)
                if 'duplicate key' in err_msg or 'already exists' in err_msg:
                    skipped += 1
                elif 'foreign key' in err_msg or 'not present' in err_msg:
                    skipped += 1  # FK нарушение — родитель не загружен, пропускаем
                else:
                    errors += 1
                    if errors <= 3:
                        logger.warning(f'Ошибка: {e}')

        return saved, errors, skipped

    def _dry_run(self, filepath):
        """Подсчёт записей без загрузки."""
        from collections import Counter
        models = Counter()
        total = 0
        for record in self._stream_records(filepath):
            models[record.get('model', '?')] += 1
            total += 1
            if total % 100000 == 0:
                self.stdout.write(f'  ...{total}')

        self.stdout.write(f'\n📋 Записей: {total}')
        for model, count in models.most_common():
            self.stdout.write(f'  {model}: {count}')

    def _stream_records(self, filepath):
        """Потоково читает JSON-массив построчно.

        Формат от dump_parsed_boats — один JSON-объект на строку:
            [
            {"model": "boats.charter", ...},
            {"model": "boats.boat", ...}
            ]
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                if not line or line == '[' or line == ']' or line == '[{':
                    continue

                # Убираем запятую в начале или конце
                if line.startswith(','):
                    line = line[1:].strip()
                if line.endswith(','):
                    line = line[:-1].strip()

                if not line or not line.startswith('{'):
                    continue

                try:
                    yield json.loads(line)
                except json.JSONDecodeError as e:
                    if line_num <= 5:
                        self.stderr.write(
                            f'⚠️  Строка {line_num}: не удалось распарсить '
                            f'({len(line)} символов): {str(e)[:80]}'
                        )
                        self.stderr.write(f'    Начало: {line[:120]}...')
