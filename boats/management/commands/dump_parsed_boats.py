"""Management command для создания дампа лодок и связанных сущностей.

Использование:
    python manage.py dump_parsed_boats
    python manage.py dump_parsed_boats --output boats_full.json
    python manage.py dump_parsed_boats --parsed-only
"""

import json
import logging
import time
from pathlib import Path

from django.core.serializers import serialize
from django.core.management.base import BaseCommand

from boats.models import (
    Boat,
    BoatDescription,
    BoatDetails,
    BoatGallery,
    BoatPrice,
    BoatTechnicalSpecs,
    Charter,
    ParsedBoat,
)

logger = logging.getLogger(__name__)

BATCH_SIZE = 2000


class Command(BaseCommand):
    help = 'Создаёт дамп всех лодочных данных для инициализации БД в проде'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            type=str,
            default='boats/fixtures/parsed_boats.json',
            help='Путь для сохранения дампа (default: boats/fixtures/parsed_boats.json)',
        )
        parser.add_argument(
            '--parsed-only',
            action='store_true',
            help='Выгружать только ParsedBoat (legacy режим)',
        )

    def handle(self, *args, **options):
        output_path = options['output']
        parsed_only = options['parsed_only']

        self.stdout.write(self.style.SUCCESS('🚀 Создаю дамп лодочных данных...'))

        model_querysets = [
            ('boats.charter', Charter.objects.all()),
            ('boats.boat', Boat.objects.all()),
            ('boats.parsedboat', ParsedBoat.objects.all()),
            ('boats.boattechnicalspecs', BoatTechnicalSpecs.objects.select_related('boat').all()),
            ('boats.boatdescription', BoatDescription.objects.select_related('boat').all()),
            ('boats.boatprice', BoatPrice.objects.select_related('boat').all()),
            ('boats.boatgallery', BoatGallery.objects.select_related('boat').all()),
            ('boats.boatdetails', BoatDetails.objects.select_related('boat').all()),
        ]

        if parsed_only:
            model_querysets = [('boats.parsedboat', ParsedBoat.objects.all())]

        total_count = sum(queryset.count() for _, queryset in model_querysets)
        parsed_count = ParsedBoat.objects.count()

        if parsed_count == 0:
            self.stdout.write(self.style.WARNING('❌ Нет спарсенных лодок (ParsedBoat) в базе'))
            return

        if total_count == 0:
            self.stdout.write(self.style.WARNING('❌ Нет лодочных данных для выгрузки'))
            return

        self.stdout.write(f'📋 ParsedBoat: {parsed_count}')
        self.stdout.write(f'📦 Всего записей к выгрузке: {total_count}')

        try:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            self.stdout.write(f'💾 Сохраняю в {output_path} (потоковая запись)...')

            start_time = time.time()
            written_total = 0
            per_model_counts = []
            first_record = True

            with open(output_file, 'w', encoding='utf-8') as f:
                f.write('[\n')

                for model_label, queryset in model_querysets:
                    model_count = 0
                    # iterator() не загружает все объекты в память
                    qs = queryset.iterator(chunk_size=BATCH_SIZE)
                    batch = []

                    for obj in qs:
                        batch.append(obj)

                        if len(batch) >= BATCH_SIZE:
                            model_count += self._write_batch(f, batch, first_record)
                            first_record = False
                            written_total += len(batch)
                            batch = []

                            if written_total % 10000 == 0:
                                elapsed = time.time() - start_time
                                self.stdout.write(
                                    f'  [{written_total}/{total_count}] ({elapsed:.0f}s)'
                                )

                    # Остаток
                    if batch:
                        model_count += self._write_batch(f, batch, first_record)
                        first_record = False
                        written_total += len(batch)

                    per_model_counts.append((model_label, model_count))
                    if model_count > 0:
                        self.stdout.write(f'  ✅ {model_label}: {model_count}')

                f.write('\n]')

            elapsed = time.time() - start_time
            file_size = output_file.stat().st_size / (1024 * 1024)

            details_lines = '\n'.join(
                f'  - {label}: {count}'
                for label, count in per_model_counts
                if count > 0
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✅ Дамп создан успешно за {elapsed:.0f}s!\n'
                    f'  Файл: {output_path}\n'
                    f'  Размер: {file_size:.2f} MB\n'
                    f'  Записей: {written_total}\n'
                    f'  Модели:\n{details_lines}\n\n'
                    f'💡 Для загрузки используйте:\n'
                    f'   python manage.py load_parsed_boats {output_path}'
                )
            )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Ошибка при сохранении дампа: {e}'))
            logger.error(f"Error creating dump: {e}", exc_info=True)

    def _write_batch(self, f, objects, first_record):
        """Сериализует и пишет батч объектов в файл."""
        serialized = serialize('json', objects, ensure_ascii=False)
        records = json.loads(serialized)

        for record in records:
            if not first_record:
                f.write(',\n')
            else:
                first_record = False
            json.dump(record, f, ensure_ascii=False)

        return len(records)
