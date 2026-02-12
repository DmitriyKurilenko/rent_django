"""
Celery tasks для асинхронного парсинга лодок
"""
import logging
from celery import shared_task
from boats.parser import parse_boataround_url

logger = logging.getLogger(__name__)


@shared_task
def dummy_task():
    """
    Пустая задача для проверки Celery
    """
    return "Celery работает!"


@shared_task(bind=True, max_retries=3)
def parse_boat_detail(self, boat_slug):
    """
    Парсит детали одной лодки и сохраняет в БД
    
    Args:
        boat_slug: Slug лодки (например, 'excess-11-ad-astra')
    
    Returns:
        dict: Результат парсинга
    """
    try:
        logger.info(f"[Celery] Парсю лодку: {boat_slug}")
        
        url = f'https://www.boataround.com/ru/yachta/{boat_slug}/'
        result = parse_boataround_url(url, save_to_db=True)
        
        if result:
            logger.info(f"[Celery] ✅ Успешно спарсена: {boat_slug}")
            return {
                'status': 'success',
                'slug': boat_slug,
                'boat_id': result.get('boat_id'),
            }
        else:
            logger.warning(f"[Celery] ⚠️ Не удалось спарсить: {boat_slug}")
            return {
                'status': 'failed',
                'slug': boat_slug,
                'reason': 'Parser returned None'
            }
            
    except Exception as exc:
        logger.error(f"[Celery] ❌ Ошибка парсинга {boat_slug}: {exc}")
        
        # Retry с exponential backoff
        try:
            raise self.retry(exc=exc, countdown=60)
        except self.MaxRetriesExceededError:
            logger.error(f"[Celery] Max retries exceeded for {boat_slug}")
            return {
                'status': 'failed',
                'slug': boat_slug,
                'reason': str(exc)
            }


@shared_task(bind=True)
def parse_boats_batch(self, boat_slugs):
    """
    Парсит батч лодок (группа из ~50 лодок)
    
    Args:
        boat_slugs: List[str] - список slug'ов лодок
        
    Returns:
        dict: Статистика парсинга
    """
    total = len(boat_slugs)
    success = 0
    failed = 0
    
    logger.info(f"[Celery] 📦 Начинаю парсинг батча из {total} лодок")
    
    for idx, slug in enumerate(boat_slugs, 1):
        try:
            result = parse_boat_detail(slug)
            
            if result['status'] == 'success':
                success += 1
            else:
                failed += 1
            
            # Логируем прогресс каждые 10 лодок
            if idx % 10 == 0:
                logger.info(
                    f"[Celery] 🔄 Батч прогресс: {idx}/{total} "
                    f"(успешно: {success}, ошибок: {failed})"
                )
                
        except Exception as e:
            failed += 1
            logger.error(f"[Celery] Ошибка в батче при парсинге {slug}: {e}")
    
    logger.info(
        f"[Celery] ✅ Батч завершен! "
        f"Успешно: {success}, Ошибок: {failed}, Всего: {total}"
    )
    
    return {
        'status': 'completed',
        'total': total,
        'success': success,
        'failed': failed,
    }


@shared_task
def update_parsed_boats():
    """
    Обновляет уже спарсенные лодки (свежая информация)
    Может быть запущена по расписанию через Beat
    """
    from boats.models import ParsedBoat
    from django.utils import timezone
    from datetime import timedelta
    
    # Обновляем лодки которые парсили более 7 дней назад
    cutoff_date = timezone.now() - timedelta(days=7)
    old_boats = ParsedBoat.objects.filter(last_parsed__lt=cutoff_date)[:1000]
    
    logger.info(f"[Celery] 🔄 Обновляю {old_boats.count()} старых лодок")
    
    task_ids = []
    for boat in old_boats:
        task = parse_boat_detail.delay(boat.slug)
        task_ids.append(task.id)
    
    logger.info(f"[Celery] 📤 Отправлено {len(task_ids)} задач на обновление")
    
    return {
        'status': 'queued',
        'count': len(task_ids),
    }
