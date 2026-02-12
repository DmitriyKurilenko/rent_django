"""
Management command для загрузки уже скачанных изображений в S3 бакет.

Использование:
    python manage.py upload_existing_images_to_s3  # Загрузить все изображения
    python manage.py upload_existing_images_to_s3 --dry-run  # Просмотр без загрузки
"""

import logging
import os
from pathlib import Path
from django.core.management.base import BaseCommand
from boats.parser import upload_file_to_s3

logger = logging.getLogger(__name__)

MEDIA_ROOT = '/app/media/boats'  # Docker path


class Command(BaseCommand):
    help = 'Загружает все существующие изображения в S3 бакет'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Режим просмотра без загрузки',
        )
        parser.add_argument(
            '--skip-existing',
            action='store_true',
            help='Пропустить файлы, которые уже в S3',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        skip_existing = options.get('skip_existing', False)

        self.stdout.write(self.style.SUCCESS('🚀 Начинаю загрузку изображений в S3...'))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('⚠️  Режим DRY-RUN (без загрузки)'))
        
        if skip_existing:
            self.stdout.write(self.style.WARNING('⚠️  Режим --skip-existing (пропускаю существующие файлы)'))

        media_path = Path(MEDIA_ROOT)
        
        if not media_path.exists():
            self.stdout.write(self.style.ERROR(f'❌ Директория {MEDIA_ROOT} не существует'))
            return

        # Ищем все .jpg, .png, .webp файлы
        image_files = list(media_path.rglob('*.jpg'))
        image_files.extend(media_path.rglob('*.jpeg'))
        image_files.extend(media_path.rglob('*.png'))
        image_files.extend(media_path.rglob('*.webp'))

        self.stdout.write(f'📋 Найдено {len(image_files)} изображений для загрузки')

        if not image_files:
            self.stdout.write(self.style.WARNING('❌ Изображения не найдены'))
            return

        # Загружаем файлы
        uploaded = 0
        failed = 0
        skipped = 0

        for idx, file_path in enumerate(image_files, 1):
            try:
                # Формируем S3 key из пути
                # Пример: /app/media/boats/boats/6669a1a50e2fd7db20088ce9/671fa052dbe1ae0fd809cf5e.jpg
                # -> 6669a1a50e2fd7db20088ce9/671fa052dbe1ae0fd809cf5e.jpg
                relative_path = file_path.relative_to(media_path)
                
                # Убираем префикс 'boats/' если есть
                s3_key = str(relative_path).replace('\\', '/')  # для Windows
                if s3_key.startswith('boats/'):
                    s3_key = s3_key[len('boats/'):]

                # Проверяем что это правильный формат {boat_id}/{filename}
                parts = s3_key.split('/')
                if len(parts) != 2:
                    logger.warning(f"Пропускаю файл с неправильной структурой: {relative_path}")
                    skipped += 1
                    continue

                boat_id = parts[0]
                # Проверяем что boat_id это 24-символный hex (MongoDB ObjectId)
                if len(boat_id) != 24 or not all(c in '0123456789abcdef' for c in boat_id.lower()):
                    logger.warning(f"Пропускаю файл: boat_id неправильный: {boat_id}")
                    skipped += 1
                    continue

                if dry_run:
                    self.stdout.write(f'  [{idx}/{len(image_files)}] DRY-RUN: {s3_key}')
                else:
                    # Загружаем в S3
                    result = upload_file_to_s3(file_path, s3_key, skip_existing=skip_existing)
                    if result:
                        uploaded += 1
                        if idx % 10 == 0:
                            self.stdout.write(f'  ✅ [{idx}/{len(image_files)}] Загружено {uploaded} файлов')
                    else:
                        failed += 1
                        logger.warning(f"Не удалось загрузить: {s3_key}")
                        
            except Exception as e:
                failed += 1
                logger.error(f"Ошибка при загрузке {file_path}: {e}")

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✅ DRY-RUN завершен!\n'
                    f'  Готово к загрузке: {len(image_files) - skipped}\n'
                    f'  Пропущено: {skipped}'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✅ Загрузка завершена!\n'
                    f'  Успешно: {uploaded}\n'
                    f'  Ошибок: {failed}\n'
                    f'  Пропущено: {skipped}\n'
                    f'  Всего: {len(image_files)}'
                )
            )
