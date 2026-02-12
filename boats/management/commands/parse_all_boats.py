"""
Management command для массового парсинга всех лодок с boataround.com

Использование:
    python manage.py parse_all_boats --async  # Запустить асинхронно через Celery
    python manage.py parse_all_boats --sync   # Синхронно (для тестирования)
    python manage.py parse_all_boats --limit 100  # Ограничить количество лодок
    python manage.py parse_all_boats --destination turkey  # Парсить только по направлению
"""

import logging
from django.core.management.base import BaseCommand, CommandError
from boats.boataround_api import BoataroundAPI
from boats.parser import parse_boataround_url
from boats.models import ParsedBoat

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Парсит все лодки с boataround.com и сохраняет в БД'

    def add_arguments(self, parser):
        parser.add_argument(
            '--async',
            action='store_true',
            help='Запустить асинхронно через Celery',
        )
        parser.add_argument(
            '--sync',
            action='store_true',
            help='Запустить синхронно (для тестирования)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Ограничить количество лодок',
        )
        parser.add_argument(
            '--destination',
            type=str,
            default=None,
            help='Парсить только по определенному направлению (e.g., "turkey")',
        )
        parser.add_argument(
            '--skip-existing',
            action='store_true',
            help='Пропустить уже спарсенные лодки',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='Размер батча для Celery (default: 50)',
        )
        parser.add_argument(
            '--max-pages',
            type=int,
            default=None,
            help='Ограничение по числу страниц на направление (по умолчанию без ограничения)',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🚀 Начинаем парсинг лодок...'))
        
        # Определяем синхронный или асинхронный режим
        async_mode = options['async']
        sync_mode = options['sync']
        limit = options['limit']
        destination = options['destination']
        skip_existing = options['skip_existing']
        batch_size = options['batch_size']
        
        if not async_mode and not sync_mode:
            raise CommandError('Укажите --async или --sync')
        
        # Получаем список всех лодок через API
        self.stdout.write('📋 Получаю список всех лодок через API...')
        
        max_pages = options.get('max_pages')
        boat_slugs = self._get_all_boat_slugs(destination, limit, skip_existing, max_pages)
        
        if not boat_slugs:
            self.stdout.write(self.style.WARNING('❌ Не найдено лодок для парсинга'))
            return
        
        self.stdout.write(
            self.style.SUCCESS(f'✅ Найдено {len(boat_slugs)} лодок для парсинга')
        )
        
        if sync_mode:
            self._parse_boats_sync(boat_slugs)
        else:
            self._parse_boats_async(boat_slugs, batch_size)

    def _get_all_boat_slugs(self, destination=None, limit=None, skip_existing=False, max_pages=None):
        """Получает список всех slug'ов лодок через API"""
        slugs = set()
        
        # Если задано направление - ищем по нему
        if destination:
            # Используем переданное значение напрямую — пользователь явно указывает destination
            destinations = [destination]
        else:
            # Иначе ищем по популярным направлениям
            destinations = [
                'turkey', 'greece', 'croatia', 'italy', 'spain', 'france',
                'portugal', 'malta', 'cyprus', 'bahamas', 'bvi', 'usvi',
                'mexico', 'french-polynesia', 'new-zealand', 'australia'
            ]
        
        for dest in destinations:
            self.stdout.write(f'🔍 Ищу лодки в {dest}...')
            page = 1
            dest_count = 0
            # Будем ориентироваться на totalPages из API, но можно ограничить через --max-pages
            total_pages = None

            while True:
                try:
                    results = BoataroundAPI.search(
                        destination=dest,
                        page=page,
                        limit=50,  # Максимум на странице
                        lang='en_EN'
                    )
                    
                    if not results or not results.get('boats'):
                        break
                    
                    from boats.boataround_api import format_boat_data

                    for boat in results['boats']:
                        # Преобразуем сырой объект лодки в стандартный формат
                        try:
                            formatted = format_boat_data(boat)
                        except Exception as e:
                            logger.warning(f"Ошибка форматирования лодки из API: {e}")
                            formatted = {}

                        boat_id = formatted.get('id')
                        boat_slug = formatted.get('slug')

                        if not boat_id or not boat_slug:
                            # Логируем проблему с объектом лодки для отладки
                            logger.debug(f"[parse_all_boats] Skipping boat, missing id/slug. Raw keys: {list(boat.keys())}")
                            continue

                        # Если skip_existing - пропускаем уже спарсенные
                        if skip_existing and ParsedBoat.objects.filter(boat_id=boat_id).exists():
                            continue

                        slugs.add(boat_slug)
                        dest_count += 1
                    
                    # Проверяем лимит по найденным лодкам
                    if limit and len(slugs) >= limit:
                        slugs = list(slugs)[:limit]
                        return slugs

                    # Определим общее число страниц, исходя из ответа API
                    if total_pages is None:
                        try:
                            total_pages = int(results.get('totalPages') or 1)
                        except Exception:
                            total_pages = 1

                    # Если задано внешнее ограничение по страницам - применяем
                    effective_total_pages = total_pages
                    if max_pages and isinstance(max_pages, int) and max_pages > 0:
                        effective_total_pages = min(effective_total_pages, max_pages)

                    # Переходим на следующую страницу или выходим
                    if page >= effective_total_pages:
                        break

                    page += 1
                    
                except Exception as e:
                    logger.error(f"Ошибка при поиске в {dest} стр.{page}: {e}")
                    break
            
            self.stdout.write(f'  ✅ Найдено {dest_count} лодок в {dest}')
        
        return list(slugs)

    def _parse_boats_sync(self, boat_slugs):
        """Синхронный парсинг (для тестирования)"""
        total = len(boat_slugs)
        success = 0
        failed = 0
        
        self.stdout.write(f'🔄 Начинаю синхронный парсинг {total} лодок...')
        
        for idx, slug in enumerate(boat_slugs, 1):
            try:
                url = f'https://www.boataround.com/ru/yachta/{slug}/'
                
                # Парсим и сохраняем
                result = parse_boataround_url(url, save_to_db=True)
                
                if result:
                    success += 1
                    if idx % 10 == 0:
                        self.stdout.write(
                            f'  ✅ [{idx}/{total}] {slug[:40]}... успешно'
                        )
                else:
                    failed += 1
                    
            except Exception as e:
                failed += 1
                logger.error(f"Ошибка при парсинге {slug}: {e}")
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\n✅ Парсинг завершен!\n'
                f'  Успешно: {success}\n'
                f'  Ошибок: {failed}\n'
                f'  Всего: {total}'
            )
        )

    def _parse_boats_async(self, boat_slugs, batch_size):
        """Асинхронный парсинг через Celery"""
        try:
            from boats.tasks import parse_boats_batch
        except ImportError:
            raise CommandError('Celery tasks не найдены. Убедитесь что boats/tasks.py существует.')
        
        total = len(boat_slugs)
        batches = [boat_slugs[i:i+batch_size] for i in range(0, total, batch_size)]
        
        self.stdout.write(
            f'📤 Отправляю {len(batches)} батчей по {batch_size} лодок в Celery...'
        )
        
        task_ids = []
        for batch_idx, batch in enumerate(batches, 1):
            try:
                task = parse_boats_batch.delay(batch)
                task_ids.append(task.id)
                self.stdout.write(f'  ✅ Батч {batch_idx}/{len(batches)} отправлен (ID: {task.id})')
            except Exception as e:
                logger.error(f"Ошибка отправки батча {batch_idx}: {e}")
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\n✅ {len(task_ids)} батчей отправлены в очередь Celery!\n'
                f'  Всего лодок: {total}\n'
                f'  Размер батча: {batch_size}\n'
                f'  Количество батчей: {len(batches)}\n\n'
                f'💡 Для мониторинга выполнения используйте:\n'
                f'   docker-compose logs -f worker'
            )
        )
