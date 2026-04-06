"""Management command для загрузки дампа лодок батчами (без OOM).

Полностью потоковая загрузка:
- Читает JSON построчно, НЕ загружая файл в память
- Сохраняет батчами в одной транзакции (быстро, мало нагрузки на БД)
- При ошибке батча — пересохраняет поштучно (fallback)
- Пауза между батчами чтобы не перегружать БД
- Retry при потере соединения с БД
- Поддерживает загрузку директории (все .json файлы в отсортированном порядке)

Использование:
    python manage.py load_parsed_boats boats/fixtures/parsed_boats.json
    python manage.py load_parsed_boats boats/fixtures/split/
    python manage.py load_parsed_boats boats/fixtures/split/ --batch-size 200
    python manage.py load_parsed_boats boats/fixtures/split/ --skip-existing
    python manage.py load_parsed_boats boats/fixtures/split/ --dry-run
"""

import json
import logging
import os
import sys
import time
from glob import glob

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
            help='Путь к JSON-фикстуре или директории с .json файлами',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=200,
            help='Размер батча (default: 200)',
        )
        parser.add_argument(
            '--skip-existing',
            action='store_true',
            help='Пропускать существующие записи (по умолчанию — перезаписывать)',
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
        self.skip_existing = options['skip_existing']

        if not os.path.exists(fixture_path):
            raise CommandError(f'Путь не найден: {fixture_path}')

        # Поддержка директории: загрузить все .json файлы в отсортированном порядке
        if os.path.isdir(fixture_path):
            files = sorted(glob(os.path.join(fixture_path, '*.json')))
            if not files:
                raise CommandError(f'Нет .json файлов в директории: {fixture_path}')
            total_size = sum(os.path.getsize(f) for f in files) / (1024 * 1024)
            self.stdout.write(self.style.SUCCESS(
                f'📂 Директория: {fixture_path} ({len(files)} файлов, {total_size:.1f} MB)'
            ))
            for f in files:
                self.stdout.write(f'  - {os.path.basename(f)}')
            self.stdout.write('')
            return self._load_multiple(files, batch_size, dry_run)

        file_size_mb = os.path.getsize(fixture_path) / (1024 * 1024)
        self.stdout.write(self.style.SUCCESS(
            f'📂 Файл: {fixture_path} ({file_size_mb:.1f} MB)'
        ))
        if self.skip_existing:
            self.stdout.write('  Режим: пропуск существующих (--skip-existing)')
        else:
            self.stdout.write('  Режим: перезапись существующих')

        if dry_run:
            self._dry_run(fixture_path)
            return

        self.stdout.write(f'🔄 Загрузка в БД (батчами по {batch_size})...')
        self.stdout.write('')

        start_time = time.time()
        saved_total = 0
        updated_total = 0
        errors_total = 0
        skipped_total = 0
        current_model = None
        current_batch = []
        model_saved = 0
        model_updated = 0
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
                    s, u, e, sk = self._save_batch(current_batch)
                    model_saved += s
                    model_updated += u
                    model_errors += e
                    model_skipped += sk

                if current_model is not None:
                    self._print_model_stats(
                        model_saved, model_updated, model_skipped, model_errors, model_count
                    )
                    saved_total += model_saved
                    updated_total += model_updated
                    errors_total += model_errors
                    skipped_total += model_skipped

                current_model = model_name
                current_batch = []
                model_saved = 0
                model_updated = 0
                model_errors = 0
                model_skipped = 0
                model_count = 0
                self.stdout.write(f'\n📦 {model_name}...')

            current_batch.append(record)
            model_count += 1

            # Батч заполнен — сохраняем
            if len(current_batch) >= batch_size:
                s, u, e, sk = self._save_batch(current_batch)
                model_saved += s
                model_updated += u
                model_errors += e
                model_skipped += sk
                current_batch = []

                # Прогресс
                if model_count % (batch_size * 10) == 0:
                    elapsed = time.time() - start_time
                    rate = records_read / elapsed if elapsed > 0 else 0
                    sys.stdout.write(
                        f'\r  [{model_count}] ✅ {model_saved} 🔄 {model_updated} '
                        f'⏭️  {model_skipped} ❌ {model_errors} | {rate:.0f} rec/s'
                    )
                    sys.stdout.flush()

        # Последний батч
        if current_batch:
            s, u, e, sk = self._save_batch(current_batch)
            model_saved += s
            model_updated += u
            model_errors += e
            model_skipped += sk

        if current_model is not None:
            self._print_model_stats(
                model_saved, model_updated, model_skipped, model_errors, model_count
            )
            saved_total += model_saved
            updated_total += model_updated
            errors_total += model_errors
            skipped_total += model_skipped

        # Сброс sequences после загрузки с явными ID
        self._reset_sequences()

        elapsed = time.time() - start_time
        self.stdout.write(self.style.SUCCESS(
            f'\n🏁 Загрузка завершена за {elapsed:.0f}s\n'
            f'  Прочитано:   {records_read}\n'
            f'  Новых:       {saved_total}\n'
            f'  Обновлено:   {updated_total}\n'
            f'  Пропущено:   {skipped_total}\n'
            f'  Ошибок:      {errors_total}'
        ))

    def _load_multiple(self, files, batch_size, dry_run):
        """Загрузка нескольких файлов последовательно."""
        if self.skip_existing:
            self.stdout.write('  Режим: пропуск существующих (--skip-existing)')
        else:
            self.stdout.write('  Режим: перезапись существующих')

        if dry_run:
            for filepath in files:
                self.stdout.write(f'\n--- {os.path.basename(filepath)} ---')
                self._dry_run(filepath)
            return

        grand_start = time.time()
        grand_saved = 0
        grand_updated = 0
        grand_errors = 0
        grand_skipped = 0
        grand_read = 0

        for i, filepath in enumerate(files, 1):
            basename = os.path.basename(filepath)
            file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
            self.stdout.write(self.style.SUCCESS(
                f'\n━━━ [{i}/{len(files)}] {basename} ({file_size_mb:.1f} MB) ━━━'
            ))

            start_time = time.time()
            saved_total = 0
            updated_total = 0
            errors_total = 0
            skipped_total = 0
            current_model = None
            current_batch = []
            model_saved = 0
            model_updated = 0
            model_errors = 0
            model_skipped = 0
            model_count = 0
            records_read = 0

            for record in self._stream_records(filepath):
                records_read += 1
                model_name = record.get('model', '')

                if model_name != current_model:
                    if current_batch:
                        s, u, e, sk = self._save_batch(current_batch)
                        model_saved += s
                        model_updated += u
                        model_errors += e
                        model_skipped += sk

                    if current_model is not None:
                        self._print_model_stats(
                            model_saved, model_updated, model_skipped, model_errors, model_count
                        )
                        saved_total += model_saved
                        updated_total += model_updated
                        errors_total += model_errors
                        skipped_total += model_skipped

                    current_model = model_name
                    current_batch = []
                    model_saved = 0
                    model_updated = 0
                    model_errors = 0
                    model_skipped = 0
                    model_count = 0
                    self.stdout.write(f'\n📦 {model_name}...')

                current_batch.append(record)
                model_count += 1

                if len(current_batch) >= batch_size:
                    s, u, e, sk = self._save_batch(current_batch)
                    model_saved += s
                    model_updated += u
                    model_errors += e
                    model_skipped += sk
                    current_batch = []

            if current_batch:
                s, u, e, sk = self._save_batch(current_batch)
                model_saved += s
                model_updated += u
                model_errors += e
                model_skipped += sk

            if current_model is not None:
                self._print_model_stats(
                    model_saved, model_updated, model_skipped, model_errors, model_count
                )
                saved_total += model_saved
                updated_total += model_updated
                errors_total += model_errors
                skipped_total += model_skipped

            elapsed = time.time() - start_time
            self.stdout.write(
                f'  ⏱  {basename}: {records_read} записей за {elapsed:.0f}s'
            )

            grand_saved += saved_total
            grand_updated += updated_total
            grand_errors += errors_total
            grand_skipped += skipped_total
            grand_read += records_read

        self._reset_sequences()

        elapsed = time.time() - grand_start
        self.stdout.write(self.style.SUCCESS(
            f'\n🏁 Загрузка завершена за {elapsed:.0f}s\n'
            f'  Файлов:      {len(files)}\n'
            f'  Прочитано:   {grand_read}\n'
            f'  Новых:       {grand_saved}\n'
            f'  Обновлено:   {grand_updated}\n'
            f'  Пропущено:   {grand_skipped}\n'
            f'  Ошибок:      {grand_errors}'
        ))

    def _print_model_stats(self, saved, updated, skipped, errors, total):
        self.stdout.write(
            f'  ✅ {saved} новых / 🔄 {updated} обн. / ⏭️  {skipped} пропущ. / '
            f'❌ {errors} ош. (всего {total})'
        )

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
        """Сохраняет батч. Возвращает (saved, updated, errors, skipped)."""
        batch_json = json.dumps(batch, ensure_ascii=False)
        saved = 0
        updated = 0
        errors = 0
        skipped = 0

        if not self._ensure_connection():
            self.stderr.write('❌ Не удалось подключиться к БД!')
            return 0, 0, len(batch), 0

        try:
            objects = list(deserialize('json', batch_json))
        except Exception as e:
            logger.error(f'Ошибка десериализации: {e}')
            return 0, 0, len(batch), 0

        if self.skip_existing:
            return self._save_skip_existing(objects)

        # Режим перезаписи: весь батч в одной транзакции
        try:
            with transaction.atomic():
                for obj in objects:
                    # Проверяем, существует ли запись
                    Model = obj.object.__class__
                    pk = obj.object.pk
                    exists = Model.objects.filter(pk=pk).exists()
                    obj.save()
                    if exists:
                        updated += 1
                    else:
                        saved += 1
            time.sleep(0.05)
            return saved, updated, 0, 0
        except Exception:
            saved = 0
            updated = 0

        # Fallback: поштучно
        return self._save_individual(objects, overwrite=True)

    def _save_skip_existing(self, objects):
        """Сохраняет только новые записи, пропуская существующие."""
        saved = 0
        skipped = 0
        errors = 0

        # Группируем по модели для batch-проверки существования
        by_model = {}
        for obj in objects:
            Model = obj.object.__class__
            model_key = Model._meta.label
            if model_key not in by_model:
                by_model[model_key] = {'model': Model, 'objects': []}
            by_model[model_key]['objects'].append(obj)

        for model_key, data in by_model.items():
            Model = data['model']
            model_objects = data['objects']
            pks = [obj.object.pk for obj in model_objects]
            existing_pks = set(Model.objects.filter(pk__in=pks).values_list('pk', flat=True))

            new_objects = [obj for obj in model_objects if obj.object.pk not in existing_pks]
            skipped += len(model_objects) - len(new_objects)

            if not new_objects:
                continue

            # Попытка батчом
            try:
                with transaction.atomic():
                    for obj in new_objects:
                        obj.save()
                        saved += 1
                time.sleep(0.05)
            except Exception:
                # Fallback поштучно
                saved_before = saved
                saved = saved_before - len(new_objects)  # откат
                s, u, e, sk = self._save_individual(new_objects, overwrite=False)
                saved += s
                skipped += sk
                errors += e

        return saved, 0, errors, skipped

    def _save_individual(self, objects, overwrite=True):
        """Поштучное сохранение с savepoint. Возвращает (saved, updated, errors, skipped)."""
        saved = 0
        updated = 0
        errors = 0
        skipped = 0

        for obj in objects:
            if not self._ensure_connection():
                errors += 1
                continue
            try:
                Model = obj.object.__class__
                pk = obj.object.pk
                exists = Model.objects.filter(pk=pk).exists()

                if exists and not overwrite:
                    skipped += 1
                    continue

                with transaction.atomic():
                    obj.save()
                    if exists:
                        updated += 1
                    else:
                        saved += 1
            except Exception as e:
                err_msg = str(e)
                if 'duplicate key' in err_msg or 'already exists' in err_msg:
                    skipped += 1
                elif 'foreign key' in err_msg or 'not present' in err_msg:
                    skipped += 1
                else:
                    errors += 1
                    if errors <= 3:
                        logger.warning(f'Ошибка: {e}')

        return saved, updated, errors, skipped

    def _reset_sequences(self):
        """Сбрасывает PostgreSQL sequences для всех таблиц boats_*."""
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT c.relname
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relkind = 'r' AND n.nspname = 'public' AND c.relname LIKE 'boats_%%'
                """)
                tables = [row[0] for row in cursor.fetchall()]
                reset_count = 0
                for table in tables:
                    cursor.execute(
                        "SELECT pg_get_serial_sequence(%s, 'id')", [table]
                    )
                    seq = cursor.fetchone()[0]
                    if seq:
                        cursor.execute(
                            "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
                            "COALESCE((SELECT MAX(id) FROM {} ), 1))".format(
                                connection.ops.quote_name(table)
                            ),
                            [table],
                        )
                        reset_count += 1
                if reset_count:
                    self.stdout.write(f'🔧 Sequences сброшены для {reset_count} таблиц')
        except Exception as e:
            self.stderr.write(f'⚠️  Не удалось сбросить sequences: {e}')

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
