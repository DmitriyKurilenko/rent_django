"""Management command для создания дампа лодок и связанных сущностей.

Использование:
    python manage.py dump_parsed_boats
    python manage.py dump_parsed_boats --output boats_full.json
    python manage.py dump_parsed_boats --parsed-only
"""

import json
import logging
from pathlib import Path

from django.core import serializers
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

            self.stdout.write(f'💾 Сохраняю в {output_path}...')

            payload = []
            per_model_counts = []

            for model_label, queryset in model_querysets:
                serialized = serializers.serialize('json', queryset, ensure_ascii=False)
                records = json.loads(serialized)
                payload.extend(records)
                per_model_counts.append((model_label, len(records)))

            with open(output_file, 'w', encoding='utf-8') as file_obj:
                json.dump(payload, file_obj, ensure_ascii=False, indent=2)

            file_size = output_file.stat().st_size / (1024 * 1024)  # MB

            details_lines = '\n'.join(
                f'  - {model_label}: {model_count}'
                for model_label, model_count in per_model_counts
                if model_count > 0
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✅ Дамп создан успешно!\n'
                    f'  Файл: {output_path}\n'
                    f'  Размер: {file_size:.2f} MB\n'
                    f'  Записей: {len(payload)}\n'
                    f'  Модели:\n{details_lines if details_lines else "  - (нет записей)"}\n\n'
                    f'💡 Для загрузки в проде используйте:\n'
                    f'   python manage.py loaddata {output_path}'
                )
            )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Ошибка при сохранении дампа: {e}'))
            logger.error(f"Error creating dump: {e}", exc_info=True)
