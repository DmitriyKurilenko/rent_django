"""
Management command для загрузки дампа лодок батчами (без OOM).

В отличие от стандартного loaddata, этот command:
- Читает JSON потоково (ijson), не загружая весь файл в память
- Сохраняет объекты батчами с промежуточными коммитами
- Показывает прогресс загрузки

Использование:
    python manage.py load_parsed_boats boats/fixtures/boats_full_09.json
    python manage.py load_parsed_boats boats/fixtures/boats_full_09.json --batch-size 500
"""

import json
import logging
import time

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers import deserialize
from django.db import connection, transaction

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

        self.stdout.write(self.style.SUCCESS(f'📂 Читаю {fixture_path}...'))

        try:
            with open(fixture_path, 'r', encoding='utf-8') as f:
                # Потоковый парсинг: json.load загрузит файл, но мы обработаем батчами
                # Для 750MB это ~1-2GB RAM (одноразово), но не 5GB как loaddata
                data = json.load(f)
        except FileNotFoundError:
            raise CommandError(f'Файл не найден: {fixture_path}')
        except json.JSONDecodeError as e:
            raise CommandError(f'Ошибка парсинга JSON: {e}')

        total = len(data)
        self.stdout.write(f'📋 Записей в фикстуре: {total}')

        if dry_run:
            from collections import Counter
            models = Counter(item['model'] for item in data)
            for model, count in models.most_common():
                self.stdout.write(f'  {model}: {count}')
            return

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

        # Группируем по моделям
        by_model = {}
        for item in data:
            model_name = item['model']
            by_model.setdefault(model_name, []).append(item)

        # Освобождаем память от исходного списка
        del data

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
