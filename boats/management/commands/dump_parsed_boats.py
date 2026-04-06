"""Management command для создания дампа лодок и связанных сущностей.

Использование:
    python manage.py dump_parsed_boats
    python manage.py dump_parsed_boats --output boats_full.json
    python manage.py dump_parsed_boats --split --output-dir boats/fixtures/split/
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
            '--output-dir',
            type=str,
            default='boats/fixtures/split',
            help='Директория для split-дампа (default: boats/fixtures/split/)',
        )
        parser.add_argument(
            '--split',
            action='store_true',
            help='Разбить дамп на отдельные файлы по моделям',
        )
        parser.add_argument(
            '--parsed-only',
            action='store_true',
            help='Выгружать только ParsedBoat (legacy режим)',
        )
        parser.add_argument(
            '--max-records',
            type=int,
            default=20000,
            help='Макс. записей в одном файле при --split (default: 20000)',
        )

    def _get_model_querysets(self, parsed_only):
        if parsed_only:
            return [('boats.parsedboat', ParsedBoat.objects.all())]
        return [
            ('boats.charter', Charter.objects.all()),
            ('boats.boat', Boat.objects.all()),
            ('boats.parsedboat', ParsedBoat.objects.all()),
            ('boats.boattechnicalspecs', BoatTechnicalSpecs.objects.select_related('boat').all()),
            ('boats.boatdescription', BoatDescription.objects.select_related('boat').all()),
            ('boats.boatprice', BoatPrice.objects.select_related('boat').all()),
            ('boats.boatgallery', BoatGallery.objects.select_related('boat').all()),
            ('boats.boatdetails', BoatDetails.objects.select_related('boat').all()),
        ]

    def handle(self, *args, **options):
        parsed_only = options['parsed_only']
        split_mode = options['split']

        self.stdout.write(self.style.SUCCESS('🚀 Создаю дамп лодочных данных...'))

        model_querysets = self._get_model_querysets(parsed_only)

        total_count = sum(qs.count() for _, qs in model_querysets)
        parsed_count = ParsedBoat.objects.count()

        if parsed_count == 0:
            self.stdout.write(self.style.WARNING('❌ Нет спарсенных лодок (ParsedBoat) в базе'))
            return

        self.stdout.write(f'📋 ParsedBoat: {parsed_count}')
        self.stdout.write(f'📦 Всего записей: {total_count}')

        if split_mode:
            self._dump_split(model_querysets, options['output_dir'], options['max_records'])
        else:
            self._dump_single(model_querysets, options['output'], total_count)

    def _dump_split(self, model_querysets, output_dir, max_records):
        """Дамп в отдельные файлы по моделям с разбивкой больших моделей на части."""
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        start_time = time.time()
        written_total = 0
        files_created = []

        for idx, (model_label, queryset) in enumerate(model_querysets, 1):
            count = queryset.count()
            if count == 0:
                self.stdout.write(f'  ⏭️  {model_label}: 0 записей, пропуск')
                continue

            short_name = model_label.split('.')[-1]
            need_parts = count > max_records

            self.stdout.write(
                f'  💾 {model_label} ({count})'
                + (f'  →  {(count + max_records - 1) // max_records} частей' if need_parts else '')
            )

            part_num = 1
            file_written = 0
            model_written = 0
            f = None
            first_record = True

            def open_part():
                nonlocal f, first_record, file_written, part_num
                if need_parts:
                    filename = f'{idx:02d}_{short_name}_part{part_num:02d}.json'
                else:
                    filename = f'{idx:02d}_{short_name}.json'
                filepath = out_dir / filename
                f = open(filepath, 'w', encoding='utf-8')
                f.write('[\n')
                first_record = True
                file_written = 0
                return filepath, filename

            def close_part(filepath, filename):
                nonlocal part_num
                f.write('\n]')
                f.close()
                file_size = filepath.stat().st_size / (1024 * 1024)
                self.stdout.write(f'    ✅ {filename}: {file_written} записей, {file_size:.1f} MB')
                files_created.append((filename, file_written, file_size))
                part_num += 1

            filepath, filename = open_part()

            qs = queryset.iterator(chunk_size=BATCH_SIZE)
            batch = []

            for obj in qs:
                batch.append(obj)

                if len(batch) >= BATCH_SIZE:
                    n = self._write_batch(f, batch, first_record)
                    first_record = False
                    file_written += n
                    model_written += n
                    batch = []

                    # Разбиваем на части
                    if need_parts and file_written >= max_records:
                        close_part(filepath, filename)
                        filepath, filename = open_part()

            if batch:
                n = self._write_batch(f, batch, first_record)
                file_written += n
                model_written += n

            close_part(filepath, filename)
            written_total += model_written

        elapsed = time.time() - start_time

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'✅ Split-дамп создан за {elapsed:.0f}s'))
        self.stdout.write(f'  Директория: {output_dir}/')
        self.stdout.write(f'  Файлов: {len(files_created)}')
        self.stdout.write(f'  Записей: {written_total}')
        self.stdout.write('')
        self.stdout.write('💡 Загрузка на сервере:')
        self.stdout.write('')
        self.stdout.write(f'docker cp {output_dir}/ rent_django-web-1:/app/fixtures/')
        self.stdout.write(f'docker compose exec web python manage.py load_parsed_boats /app/fixtures/')
        self.stdout.write(f'docker compose exec web rm -rf /app/fixtures/')
        self.stdout.write('')

    def _dump_single(self, model_querysets, output_path, total_count):
        """Дамп в один файл (оригинальный режим)."""
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
                    f'\n✅ Дамп создан за {elapsed:.0f}s!\n'
                    f'  Файл: {output_path}\n'
                    f'  Размер: {file_size:.2f} MB\n'
                    f'  Записей: {written_total}\n'
                    f'  Модели:\n{details_lines}\n\n'
                    f'💡 Для загрузки:\n'
                    f'   python manage.py load_parsed_boats {output_path}\n'
                    f'   # или через Docker:\n'
                    f'   docker compose exec web python manage.py load_parsed_boats {output_path}'
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
