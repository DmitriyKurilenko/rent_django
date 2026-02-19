"""Management command для загрузки дампа лодок батчами (без OOM).

В отличие от стандартного loaddata, этот command:
- Читает JSON потоково (построчно), НЕ загружая весь файл в память
- Сохраняет объекты батчами с промежуточными коммитами
- Показывает прогресс загрузки

Использование:
    python manage.py load_parsed_boats boats/fixtures/boats_full_09.json
    python manage.py load_parsed_boats boats/fixtures/boats_full_09.json --batch-size 500
"""

import json
import logging
import os
import time

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers import deserialize
from django.db import transaction

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Загружает дамп лодок батчами (для больших фикстур)'

    def add_arguments(self, parser):
        parser.add_argument(
            'fixture',
            type=str,
            help='Путь к JSON-фикстуре',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=500,
            help='Размер батча (default: 500)',
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

        # Проверяем файл
        if not os.path.exists(fixture_path):
            raise CommandError(f'Файл не найден: {fixture_path}')

        file_size = os.path.getsize(fixture_path)
        file_size_mb = file_size / (1024 * 1024)
        self.stdout.write(self.style.SUCCESS(
            f'📂 Файл: {fixture_path} ({file_size_mb:.1f} MB)'
        ))

        # --- Фаза 1: Потоковое чтение и группировка по моделям ---
        self.stdout.write('📋 Фаза 1: Читаю записи (потоково)...')
        phase1_start = time.time()

        by_model = {}
        total = 0
        parse_errors = 0

        try:
            for record in self._stream_records(fixture_path):
                model_name = record.get('model', '')
                by_model.setdefault(model_name, []).append(record)
                total += 1

                if total % 50000 == 0:
                    self.stdout.write(f'  ...прочитано {total} записей')
        except Exception as e:
            raise CommandError(f'Ошибка чтения файла: {e}')

        phase1_time = time.time() - phase1_start
        self.stdout.write(f'  Прочитано: {total} записей за {phase1_time:.0f}s')

        if total == 0:
            self.stdout.write(self.style.WARNING('Файл пуст или не содержит записей'))
            return

        # Показываем статистику по моделям
        for model_name, items in sorted(by_model.items()):
            self.stdout.write(f'  {model_name}: {len(items)}')

        if dry_run:
            return

        # --- Фаза 2: Загрузка в БД ---
        self.stdout.write(f'\n🔄 Фаза 2: Загрузка в БД (батчами по {batch_size})...')

        # Порядок загрузки важен для FK
        model_order = [
            'boats.charter',
            'boats.boat',
            'boats.parsedboat',
            'boats.boattechnicalspecs',
            'boats.boatdescription',
            'boats.boatprice',
            'boats.boatgallery',
            'boats.boatdetails',
        ]

        saved_total = 0
        errors_total = 0
        start_time = time.time()

        for model_name in model_order:
            items = by_model.get(model_name)
            if not items:
                continue

            count = len(items)
            self.stdout.write(f'\n📦 {model_name}: {count} записей')

            saved = 0
            errors = 0

            for i in range(0, count, batch_size):
                batch = items[i:i + batch_size]
                batch_json = json.dumps(batch, ensure_ascii=False)

                try:
                    with transaction.atomic():
                        objects = list(deserialize('json', batch_json))
                        for obj in objects:
                            try:
                                obj.save()
                                saved += 1
                            except Exception as e:
                                errors += 1
                                if errors <= 5:
                                    logger.warning(f'  Ошибка сохранения {obj.object}: {e}')
                except Exception as e:
                    errors += len(batch)
                    logger.error(f'  Ошибка батча {i}-{i+len(batch)}: {e}')

                done = min(i + batch_size, count)
                if done % (batch_size * 10) == 0 or done == count:
                    elapsed = time.time() - start_time
                    self.stdout.write(
                        f'  [{done}/{count}] ✅ {saved} / ❌ {errors} ({elapsed:.0f}s)'
                    )

            # Освобождаем память после обработки модели
            del items
            by_model[model_name] = None

            saved_total += saved
            errors_total += errors

        elapsed = time.time() - start_time
        self.stdout.write(self.style.SUCCESS(
            f'\n🏁 Загрузка завершена за {elapsed:.0f}s\n'
            f'  Сохранено: {saved_total}\n'
            f'  Ошибок: {errors_total}\n'
            f'  Всего: {total}'
        ))

    def _stream_records(self, filepath):
        """Потоково читает JSON-массив записей построчно.

        Формат файла (от dump_parsed_boats):
            [
            {"model": "boats.charter", ...},
            {"model": "boats.boat", ...}
            ]

        Каждая запись — отдельная строка, возможно с запятой в начале.
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()

                # Пропускаем скобки массива и пустые строки
                if not line or line == '[' or line == ']':
                    continue

                # Убираем запятую в начале (формат: ,\n{...})
                if line.startswith(','):
                    line = line[1:].strip()

                # Убираем запятую в конце
                if line.endswith(','):
                    line = line[:-1].strip()

                if not line:
                    continue

                try:
                    record = json.loads(line)
                    yield record
                except json.JSONDecodeError:
                    # Может быть многострочная запись — пробуем собрать
                    logger.debug(f'Пропуск строки (не JSON): {line[:100]}')
                    continue
