"""
Management command для создания дампа спарсенных лодок (ParsedBoat).

Использование:
    python manage.py dump_parsed_boats  # Создать boats/fixtures/parsed_boats.json
    python manage.py dump_parsed_boats --output my_boats.json  # Кастомное имя файла
"""

import json
import logging
from pathlib import Path
from django.core.management.base import BaseCommand
from django.core import serializers
from boats.models import ParsedBoat

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Создаёт дамп всех спарсенных лодок (ParsedBoat) для инициализации БД в проде'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            type=str,
            default='boats/fixtures/parsed_boats.json',
            help='Путь для сохранения дампа (default: boats/fixtures/parsed_boats.json)',
        )

    def handle(self, *args, **options):
        output_path = options['output']
        
        self.stdout.write(self.style.SUCCESS('🚀 Создаю дамп спарсенных лодок...'))

        # Получаем все ParsedBoat
        boats = ParsedBoat.objects.all()
        count = boats.count()

        if count == 0:
            self.stdout.write(self.style.WARNING('❌ Нет спарсенных лодок в базе'))
            return

        self.stdout.write(f'📋 Найдено {count} лодок')

        try:
            # Создаём директорию если её нет
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Сериализуем в JSON
            self.stdout.write(f'💾 Сохраняю в {output_path}...')
            
            with open(output_file, 'w', encoding='utf-8') as f:
                # Используем встроенный сериализатор Django
                serializers.serialize('json', boats, stream=f, indent=2, ensure_ascii=False)

            file_size = output_file.stat().st_size / (1024 * 1024)  # MB
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✅ Дамп создан успешно!\n'
                    f'  Файл: {output_path}\n'
                    f'  Размер: {file_size:.2f} MB\n'
                    f'  Записей: {count}\n\n'
                    f'💡 Для загрузки в проде используйте:\n'
                    f'   python manage.py loaddata {output_path}'
                )
            )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Ошибка при сохранении дампа: {e}'))
            logger.error(f"Error creating dump: {e}", exc_info=True)
