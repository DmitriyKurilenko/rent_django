"""
Celery tasks для асинхронного парсинга лодок
"""
import json
import logging
import sys
import time
from celery import shared_task, chord, group
from boats.parser import parse_boataround_url, download_and_save_image

logger = logging.getLogger(__name__)


@shared_task
def dummy_task():
    """
    Пустая задача для проверки Celery
    """
    return "Celery работает!"


@shared_task(bind=True, max_retries=2)
def send_telegram_notification(self, text):
    """Отправка уведомления в Telegram (async через Celery)."""
    from boats.telegram import send_telegram_message
    try:
        ok = send_telegram_message(text)
        if not ok:
            logger.warning('[Telegram task] send_telegram_message returned False')
        return {'status': 'sent' if ok else 'skipped'}
    except Exception as exc:
        logger.exception('[Telegram task] Error')
        try:
            raise self.retry(exc=exc, countdown=30)
        except self.MaxRetriesExceededError:
            logger.warning('[Telegram task] Max retries exceeded')
            return {'status': 'failed'}


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


@shared_task(bind=True, max_retries=2)
def refresh_boat_amenities(self, boat_slug):
    """
    Обновляет только cockpit/entertainment/equipment для одной лодки на всех языках.
    Каждая языковая страница тянется один раз.
    """
    SUPPORTED_LANGUAGES = ['ru_RU', 'en_EN', 'de_DE', 'fr_FR', 'es_ES']
    try:
        from boats.models import ParsedBoat, BoatDetails
        from boats.parser import _fetch_language_page_data

        boat = ParsedBoat.objects.filter(slug=boat_slug).first()
        if not boat:
            logger.warning(f'[Celery] refresh_amenities: лодка не найдена {boat_slug}')
            return {'status': 'skipped', 'slug': boat_slug, 'reason': 'not found'}

        updated = 0
        failed_languages = []
        for lang in SUPPORTED_LANGUAGES:
            lang_data = _fetch_language_page_data(boat_slug, lang)
            if not lang_data.get('_fetch_ok'):
                failed_languages.append(lang)
                logger.warning(f'[Celery] refresh_amenities {boat_slug}: пропуск {lang}, страница не загружена')
                continue
            amenities = lang_data['amenities']
            rows = BoatDetails.objects.filter(boat=boat, language=lang)
            if rows.exists():
                rows.update(
                    cockpit=amenities['cockpit'],
                    entertainment=amenities['entertainment'],
                    equipment=amenities['equipment'],
                )
                updated += 1
            else:
                BoatDetails.objects.create(
                    boat=boat,
                    language=lang,
                    cockpit=amenities['cockpit'],
                    entertainment=amenities['entertainment'],
                    equipment=amenities['equipment'],
                    extras=[], additional_services=[], delivery_extras=[], not_included=[],
                )
                updated += 1

        if updated == 0:
            logger.error(
                f'[Celery] ❌ refresh_amenities {boat_slug}: не удалось загрузить ни один язык '
                f'({", ".join(failed_languages) if failed_languages else "unknown"})'
            )
            return {
                'status': 'failed',
                'slug': boat_slug,
                'languages_updated': 0,
                'failed_languages': failed_languages,
                'reason': 'all language pages failed',
            }

        if failed_languages:
            logger.warning(
                f'[Celery] ⚠️ refresh_amenities {boat_slug}: частично, обновлено {updated}, '
                f'ошибки языков: {", ".join(failed_languages)}'
            )
            return {
                'status': 'partial',
                'slug': boat_slug,
                'languages_updated': updated,
                'failed_languages': failed_languages,
            }

        logger.info(f'[Celery] ✅ refresh_amenities {boat_slug}: обновлено {updated} языков')
        return {'status': 'success', 'slug': boat_slug, 'languages_updated': updated}

    except Exception as exc:
        logger.error(f'[Celery] ❌ refresh_amenities {boat_slug}: {exc}')
        try:
            raise self.retry(exc=exc, countdown=30)
        except self.MaxRetriesExceededError:
            return {'status': 'failed', 'slug': boat_slug, 'reason': str(exc)}


@shared_task(bind=True)
def refresh_amenities_batch(self, boat_slugs):
    """Обновляет amenities для батча лодок."""
    total = len(boat_slugs)
    success = 0
    failed = 0
    logger.info(f'[Celery] 📦 refresh_amenities батч: {total} лодок')
    for idx, slug in enumerate(boat_slugs, 1):
        result = refresh_boat_amenities(slug)
        if result.get('status') == 'success':
            success += 1
        else:
            failed += 1
        if idx % 50 == 0:
            logger.info(f'[Celery] 🔄 {idx}/{total} (успешно: {success}, ошибок: {failed})')
    logger.info(f'[Celery] ✅ Батч завершен: успешно {success}, ошибок {failed}')
    return {'status': 'completed', 'total': total, 'success': success, 'failed': failed}


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


@shared_task(bind=True, max_retries=2)
def generate_contract_pdf_task(self, contract_id):
    """
    Асинхронная генерация PDF для договора.
    """
    try:
        from boats.models import Contract
        from boats.contract_generator import generate_and_save_pdf

        contract = Contract.objects.get(id=contract_id)
        generate_and_save_pdf(contract)

        logger.info(f'[Celery] ✅ PDF сгенерирован для договора {contract.contract_number}')
        return {'status': 'success', 'contract_number': contract.contract_number}

    except Exception as exc:
        logger.error(f'[Celery] ❌ Ошибка генерации PDF для договора {contract_id}: {exc}')
        try:
            raise self.retry(exc=exc, countdown=30)
        except self.MaxRetriesExceededError:
            return {'status': 'failed', 'contract_id': contract_id, 'reason': str(exc)}


@shared_task
def send_contract_notification(contract_id):
    """
    Заглушка: отправка уведомления о договоре.
    Требует настройки EMAIL_BACKEND в settings.py.
    """
    from boats.models import Contract
    contract = Contract.objects.get(id=contract_id)
    logger.info(
        f'[Celery] 📧 Уведомление о договоре {contract.contract_number} '
        f'для {contract.contract_data.get("signer_email", "n/a")} — '
        f'EMAIL не настроен, пропускаю отправку'
    )
    return {'status': 'skipped', 'reason': 'email not configured'}


# =============================================================================
# НОВАЯ СИСТЕМА ПАРСИНГА — батчевые задачи через ParseJob
# =============================================================================

SUPPORTED_API_LANGS = ['ru_RU', 'en_EN', 'de_DE', 'fr_FR', 'es_ES']
NETWORK_ERRORS = (
    __import__('requests').exceptions.ConnectionError,
    __import__('requests').exceptions.Timeout,
    OSError,
)


def _job_log(job_id, message):
    """Атомарно добавляет строку в лог ParseJob."""
    from boats.models import ParseJob
    try:
        job = ParseJob.objects.get(job_id=job_id)
        job.append_log(message)
    except Exception:
        logger.warning(f'[parse_job] Не удалось записать лог для job {job_id}')


CACHE_DIR = __import__('pathlib').Path(__import__('django.conf', fromlist=['settings']).settings.BASE_DIR) / '.parse_cache'


def _cache_path(destination, max_pages):
    dest = destination or 'all'
    mp = f'_mp{max_pages}' if max_pages else ''
    return CACHE_DIR / f'{dest}{mp}.json'


def _load_slug_cache(destination, max_pages):
    """Загружает кэш slug'ов. Возвращает dict или None."""
    path = _cache_path(destination, max_pages)
    if not path.exists():
        return None
    try:
        with open(path, 'r') as f:
            data = __import__('json').load(f)
        if not isinstance(data, dict) or 'slugs' not in data:
            return None
        age_hours = (time.time() - path.stat().st_mtime) / 3600
        logger.info(
            f'[collect_slugs] Кэш загружен: {len(data["slugs"])} slug ({age_hours:.1f}ч), '
            f'last_page={data.get("last_page", "?")}, complete={data.get("complete", False)}'
        )
        return data
    except Exception:
        return None


def _save_slug_cache(destination, max_pages, slugs, thumb_map, api_meta, api_meta_by_lang,
                     last_page=0, total_pages=0, complete=False):
    """Сохраняет slug'и и метаданные в кэш. Вызывается инкрементально."""
    import json as _json
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _cache_path(destination, max_pages)
        data = {
            'destination': destination or 'all',
            'max_pages': max_pages,
            'count': len(slugs),
            'last_page': last_page,
            'total_pages': total_pages,
            'complete': complete,
            'cached_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'slugs': slugs,
            'thumb_map': thumb_map,
            'api_meta': api_meta,
            'api_meta_by_lang': api_meta_by_lang,
        }
        with open(path, 'w') as f:
            _json.dump(data, f)
        logger.info(f'[collect_slugs] Кэш сохранён: {len(slugs)} slug, стр.{last_page}, complete={complete}')
    except Exception as e:
        logger.warning(f'[collect_slugs] Ошибка записи кэша: {e}')


def _collect_slugs_from_api(destination, max_pages, job_id=None, no_cache=False):
    """Собирает slug'и, thumb_map, api_meta и api_meta_by_lang из API.

    Инкрементальный кэш: сохраняется после каждой страницы.
    При рестарте — продолжает с last_page.
    Завершённый кэш (complete=True) — возвращается мгновенно.
    --no-cache сбрасывает кэш и начинает с нуля.

    Returns:
        dict: {slugs, thumb_map, api_meta, api_meta_by_lang, pages_scanned}
    """
    from boats.boataround_api import BoataroundAPI, format_boat_data
    from boats.models import ParseJob
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # --- Сброс кэша если --no-cache ---
    if no_cache:
        path = _cache_path(destination, max_pages)
        if path.exists():
            path.unlink()
            logger.info(f'[collect_slugs] Кэш сброшен: {path}')
            if job_id:
                _job_log(job_id, 'Кэш сброшен (--no-cache)')

    # --- Загружаем кэш (завершённый или частичный) ---
    cached = _load_slug_cache(destination, max_pages)

    if cached and cached.get('complete'):
        if job_id:
            _job_log(job_id, f'Загружено из кэша: {len(cached["slugs"])} slug (завершённый)')
        return {
            'slugs': cached['slugs'],
            'thumb_map': cached.get('thumb_map', {}),
            'api_meta': cached.get('api_meta', {}),
            'api_meta_by_lang': cached.get('api_meta_by_lang', {}),
            'pages_scanned': 0,
        }

    # --- Восстанавливаем состояние из частичного кэша или начинаем с нуля ---
    if cached and not cached.get('complete'):
        slugs = cached.get('slugs', [])
        seen = set(slugs)
        thumb_map = cached.get('thumb_map', {})
        api_meta = cached.get('api_meta', {})
        api_meta_by_lang = cached.get('api_meta_by_lang', {lang: {} for lang in SUPPORTED_API_LANGS})
        start_page = cached.get('last_page', 0) + 1
        total_pages = cached.get('total_pages') or None
        if job_id:
            _job_log(job_id, f'Продолжение из кэша: {len(slugs)} slug, стр.{start_page}')
        logger.info(f'[collect_slugs] Resume: {len(slugs)} slug, start page {start_page}')
    else:
        slugs = []
        seen = set()
        thumb_map = {}
        api_meta = {}
        api_meta_by_lang = {lang: {} for lang in SUPPORTED_API_LANGS}
        start_page = 1
        total_pages = None

    pages_scanned = 0
    page = start_page

    while True:
        # Проверяем отмену каждые 10 страниц
        if job_id and page % 10 == 0:
            try:
                status = ParseJob.objects.filter(job_id=job_id).values_list('status', flat=True).first()
                if status == 'cancelled':
                    logger.info(f'[collect_slugs] Отмена на стр.{page}')
                    _job_log(job_id, f'Сбор прерван (отмена). Собрано {len(slugs)} slug, стр.{page}.')
                    _save_slug_cache(destination, max_pages, slugs, thumb_map, api_meta, api_meta_by_lang,
                                     last_page=page, total_pages=total_pages or 0, complete=False)
                    break
            except Exception:
                pass

        # search() внутри уже имеет 3 retry с backoff
        results = BoataroundAPI.search(
            destination=destination or None,
            page=page, limit=18, lang='en_EN',
        )

        if not results or not results.get('boats'):
            # Пустой ответ — сохраняем прогресс и стоп
            logger.info(f'[collect_slugs] Пустая страница {page}, сохраняю кэш и завершаю')
            if job_id:
                _job_log(job_id, f'Пустая страница (стр.{page}). Собрано {len(slugs)} slug.')
            _save_slug_cache(destination, max_pages, slugs, thumb_map, api_meta, api_meta_by_lang,
                             last_page=page, total_pages=total_pages or 0, complete=False)
            break

        # Параллельный запрос остальных языков для этой страницы
        def _fetch_lang_page(api_lang):
            r = BoataroundAPI.search(
                destination=destination or None,
                page=page, limit=18, lang=api_lang,
            )
            return api_lang, (r or {}).get('boats', [])

        other_langs = [l for l in SUPPORTED_API_LANGS if l != 'en_EN']
        boats_by_lang = {'en_EN': results.get('boats', [])}

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(_fetch_lang_page, lang): lang for lang in other_langs}
            for future in as_completed(futures):
                try:
                    lang, boats = future.result(timeout=60)
                    boats_by_lang[lang] = boats
                except Exception:
                    boats_by_lang[futures[future]] = []

        # Обработка результатов всех языков
        for api_lang, boats_lang in boats_by_lang.items():
            for boat_lang in boats_lang:
                lang_slug = boat_lang.get('slug')
                if not lang_slug:
                    continue
                api_meta_by_lang.setdefault(api_lang, {})[lang_slug] = {
                    'title': boat_lang.get('title', ''),
                    'location': boat_lang.get('location', '') or boat_lang.get('region', '') or boat_lang.get('country', ''),
                    'marina': boat_lang.get('marina', ''),
                    'country': boat_lang.get('country', ''),
                    'region': boat_lang.get('region', ''),
                    'city': boat_lang.get('city', ''),
                }

        # Обработка EN-результатов для slug/thumb/meta
        for boat in results['boats']:
            try:
                formatted = format_boat_data(boat)
            except Exception:
                formatted = {}
            boat_slug = formatted.get('slug') or boat.get('slug')
            if not boat_slug or boat_slug in seen:
                continue
            seen.add(boat_slug)
            slugs.append(boat_slug)

            thumb = boat.get('thumb') or boat.get('main_img', '')
            if thumb and thumb.strip():
                thumb_map[boat_slug] = thumb.strip()

            api_meta[boat_slug] = {
                'country': boat.get('country', ''),
                'region': boat.get('region', ''),
                'city': boat.get('city', ''),
                'marina': boat.get('marina', ''),
                'title': boat.get('title', ''),
                'location': boat.get('location', '') or boat.get('region', '') or boat.get('country', ''),
                'flag': boat.get('flag', ''),
                'coordinates': boat.get('coordinates', []),
                'category': boat.get('category', ''),
                'category_slug': boat.get('category_slug', ''),
                'engine_type': boat.get('engineType', ''),
                'sail': boat.get('sail', ''),
                'newboat': boat.get('newboat', False),
                'reviews_score': boat.get('reviewsScore'),
                'total_reviews': boat.get('totalReviews'),
                'prepayment': boat.get('prepayment'),
                'usp': boat.get('usp', []),
                'parameters': boat.get('parameters', {}),
                'charter_name': boat.get('charter', ''),
                'charter_id': boat.get('charter_id', ''),
                'charter_logo': boat.get('charter_logo', ''),
                'charter_rank': boat.get('charter_rank', {}),
            }

        pages_scanned += 1

        if total_pages is None:
            total_pages = int(results.get('totalPages') or 1)
        effective = min(total_pages, max_pages) if max_pages else total_pages

        # Кэш после каждой страницы
        is_complete = page >= effective
        _save_slug_cache(destination, max_pages, slugs, thumb_map, api_meta, api_meta_by_lang,
                         last_page=page, total_pages=total_pages, complete=is_complete)

        # Прогресс каждые 10 страниц
        if job_id and pages_scanned % 10 == 0:
            _job_log(job_id, f'Сбор slug: стр.{page}/{effective}, найдено {len(slugs)} slug')

        if is_complete:
            if job_id:
                _job_log(job_id, f'Сбор завершён: {len(slugs)} slug, {pages_scanned} стр.')
            break
        page += 1

    return {
        'slugs': slugs,
        'thumb_map': thumb_map,
        'api_meta': api_meta,
        'api_meta_by_lang': api_meta_by_lang,
        'pages_scanned': pages_scanned,
    }


@shared_task(bind=True, max_retries=1)
def process_api_batch(self, job_id_hex, batch_slugs, api_meta_subset, api_meta_by_lang_subset):
    """Обрабатывает батч API-метаданных. Локализованные мета получает готовыми из оркестратора."""
    from boats.models import ParseJob
    from django.db.models import F

    job_id_hex = str(job_id_hex)

    try:
        from boats.management.commands.parse_boats_parallel import Command as PBPCommand
        updated = PBPCommand._update_api_metadata(api_meta_subset, api_meta_by_lang_subset)

        ParseJob.objects.filter(job_id=job_id_hex).update(
            processed=F('processed') + len(batch_slugs),
            success=F('success') + updated,
            skipped=F('skipped') + (len(batch_slugs) - updated),
            batches_done=F('batches_done') + 1,
        )
        _job_log(job_id_hex, f'API batch OK: {len(batch_slugs)} slug, {updated} updated')
        return {'status': 'ok', 'updated': updated, 'total': len(batch_slugs)}

    except Exception as exc:
        logger.error(f'[process_api_batch] Ошибка: {exc}')
        _job_log(job_id_hex, f'API batch FAIL: {exc}')
        ParseJob.objects.filter(job_id=job_id_hex).update(
            processed=F('processed') + len(batch_slugs),
            failed=F('failed') + len(batch_slugs),
            batches_done=F('batches_done') + 1,
        )
        # Записываем ошибки для каждого slug из батча
        try:
            job = ParseJob.objects.get(job_id=job_id_hex)
            job.append_error('batch', str(exc))
        except Exception:
            pass
        return {'status': 'failed', 'error': str(exc)}


@shared_task(bind=True, max_retries=1)
def process_html_batch(self, job_id_hex, batch_slugs, thumb_map_subset):
    """Парсит батч лодок через HTML. Обновляет ParseJob атомарно."""
    from boats.models import ParseJob, ParsedBoat
    from django.db.models import F

    job_id_hex = str(job_id_hex)
    batch_success = 0
    batch_failed = 0
    batch_errors = []

    for slug in batch_slugs:
        try:
            url = f'https://www.boataround.com/ru/yachta/{slug}/'
            result = parse_boataround_url(url, save_to_db=True)
            if result:
                # Загружаем превью
                thumb_url = thumb_map_subset.get(slug)
                if thumb_url:
                    _save_preview_for_slug(slug, thumb_url)
                batch_success += 1
            else:
                batch_failed += 1
                batch_errors.append({'slug': slug, 'error': 'Parser returned None'})
        except Exception as e:
            batch_failed += 1
            batch_errors.append({'slug': slug, 'error': str(e)[:200]})
            logger.error(f'[process_html_batch] {slug}: {e}')

    ParseJob.objects.filter(job_id=job_id_hex).update(
        processed=F('processed') + len(batch_slugs),
        success=F('success') + batch_success,
        failed=F('failed') + batch_failed,
        batches_done=F('batches_done') + 1,
    )

    # Записываем ошибки атомарно
    if batch_errors:
        try:
            job = ParseJob.objects.get(job_id=job_id_hex)
            for err in batch_errors:
                job.append_error(err['slug'], err['error'])
        except Exception:
            pass

    _job_log(
        job_id_hex,
        f'HTML batch OK: {batch_success}/{len(batch_slugs)} '
        f'(failed: {batch_failed})'
    )
    return {
        'status': 'ok',
        'success': batch_success,
        'failed': batch_failed,
        'total': len(batch_slugs),
    }


def _save_preview_for_slug(slug, thumb_url):
    """Скачивает thumb и сохраняет CDN URL как preview_cdn_url."""
    from urllib.parse import urlparse
    from boats.models import ParsedBoat

    try:
        parsed = urlparse(thumb_url)
        image_path = parsed.path.lstrip('/')
        if not image_path.startswith('boats/'):
            return
        cdn_url = download_and_save_image(image_path)
        if cdn_url:
            ParsedBoat.objects.filter(slug=slug).update(preview_cdn_url=cdn_url)
    except Exception as e:
        logger.warning(f'Failed to save preview for {slug}: {e}')


@shared_task(bind=True)
def finalize_parse_job(self, results, job_id_hex):
    """Финализирует ParseJob: формирует отчёт, ставит статус."""
    from boats.models import ParseJob, ParsedBoat, BoatGallery, BoatDescription, BoatDetails, BoatTechnicalSpecs
    from django.utils import timezone

    job_id_hex = str(job_id_hex)

    try:
        job = ParseJob.objects.get(job_id=job_id_hex)
    except ParseJob.DoesNotExist:
        logger.error(f'[finalize] ParseJob {job_id_hex} not found')
        return

    job.finished_at = timezone.now()

    # Обновляем счётчики из актуальных данных БД
    job.refresh_from_db()

    duration = job.duration_seconds or 0
    rate = job.processed / duration if duration > 0 else 0

    # Формируем краткий отчёт
    db_stats = {
        'parsed_boats': ParsedBoat.objects.count(),
        'photos': BoatGallery.objects.count(),
        'descriptions': BoatDescription.objects.count(),
        'details': BoatDetails.objects.count(),
        'specs': BoatTechnicalSpecs.objects.count(),
    }

    errors_count = len(job.errors) if isinstance(job.errors, list) else 0

    summary_lines = [
        f'Задание: {job.get_mode_display()}',
        f'Направление: {job.destination or "все"}',
        f'---',
        f'Slug\'ов: {job.total_slugs}',
        f'Обработано: {job.processed}',
        f'Успешно: {job.success}',
        f'Ошибок: {job.failed}',
        f'Пропущено: {job.skipped}',
        f'---',
        f'Батчей: {job.batches_done}/{job.total_batches}',
        f'Время: {int(duration)}с ({duration / 60:.1f} мин)',
        f'Скорость: {rate:.1f}/с',
        f'---',
        f'БД итого:',
        f'  ParsedBoat: {db_stats["parsed_boats"]}',
        f'  Фото: {db_stats["photos"]}',
        f'  Описания: {db_stats["descriptions"]}',
        f'  Детали: {db_stats["details"]}',
        f'  Тех. спеки: {db_stats["specs"]}',
    ]
    if errors_count > 0:
        summary_lines.append(f'---')
        summary_lines.append(f'Первые ошибки ({min(errors_count, 10)} из {errors_count}):')
        for err in job.errors[:10]:
            if isinstance(err, dict):
                summary_lines.append(f'  {err.get("slug", "?")}: {err.get("error", "?")[:80]}')

    job.summary = '\n'.join(summary_lines)

    if job.failed > 0 and job.success > 0:
        job.status = 'partial'
    elif job.failed > 0 and job.success == 0:
        job.status = 'failed'
    else:
        job.status = 'completed'

    job.save(update_fields=[
        'status', 'finished_at', 'summary',
        'processed', 'success', 'failed', 'skipped', 'batches_done',
    ])

    _job_log(job_id_hex, f'Задание завершено: {job.get_status_display()}')
    logger.info(f'[finalize] ParseJob {job_id_hex}: {job.status}')


@shared_task(bind=True, max_retries=0)
def run_parse_job(self, job_id_hex, no_cache=False):
    """Оркестратор: собирает slug'и, разбивает на батчи, запускает Celery chord."""
    from boats.models import ParseJob, ParsedBoat
    from django.utils import timezone
    from django.db.models import F

    job_id_hex = str(job_id_hex)

    try:
        job = ParseJob.objects.get(job_id=job_id_hex)
    except ParseJob.DoesNotExist:
        logger.error(f'[run_parse_job] ParseJob {job_id_hex} not found')
        return

    job.status = 'collecting'
    job.started_at = timezone.now()
    job.celery_task_id = self.request.id or ''
    job.save(update_fields=['status', 'started_at', 'celery_task_id'])
    _job_log(job_id_hex, f'Начат сбор slug\'ов (mode={job.mode}, dest={job.destination or "все"})')

    # Глушим спам парсера в Celery-воркере
    logging.getLogger('boats.parser').setLevel(logging.WARNING)
    logging.getLogger('boats.boataround_api').setLevel(logging.WARNING)

    # --- Фаза 1: Сбор slug'ов (только EN, без локализованных мета) ---
    try:
        collected = _collect_slugs_from_api(
            destination=job.destination or None,
            max_pages=job.max_pages,
            job_id=job_id_hex,
            no_cache=no_cache,
        )
    except Exception as exc:
        job.status = 'failed'
        job.finished_at = timezone.now()
        job.summary = f'Ошибка сбора slug\'ов: {exc}'
        job.save(update_fields=['status', 'finished_at', 'summary'])
        _job_log(job_id_hex, f'FAIL: сбор slug\'ов — {exc}')
        return

    # Проверяем отмену после сбора
    job.refresh_from_db()
    if job.status == 'cancelled':
        _job_log(job_id_hex, 'Задание отменено после сбора slug\'ов')
        return

    all_slugs = collected['slugs']
    thumb_map = collected['thumb_map']
    api_meta = collected['api_meta']
    api_meta_by_lang = collected['api_meta_by_lang']

    _job_log(
        job_id_hex,
        f'Собрано {len(all_slugs)} slug\'ов ({collected["pages_scanned"]} стр.)'
    )

    # Фильтрация
    if job.skip_existing and job.mode == 'html':
        existing = set(ParsedBoat.objects.values_list('slug', flat=True))
        before = len(all_slugs)
        all_slugs = [s for s in all_slugs if s not in existing]
        skipped = before - len(all_slugs)
        _job_log(job_id_hex, f'Пропущено существующих: {skipped}')
        job.skipped = skipped
    else:
        skipped = 0

    if not all_slugs and not api_meta:
        job.status = 'completed'
        job.finished_at = timezone.now()
        job.total_slugs = 0
        job.summary = 'Нет лодок для обработки'
        job.save()
        _job_log(job_id_hex, 'Нет лодок для обработки')
        return

    # --- Формируем батчи ---
    batch_size = job.batch_size
    slug_batches = [
        all_slugs[i:i + batch_size]
        for i in range(0, len(all_slugs), batch_size)
    ]

    # В full-режиме каждый slug обрабатывается дважды (API + HTML)
    multiplier = 2 if job.mode == 'full' else 1
    job.total_slugs = len(all_slugs) * multiplier
    job.status = 'running'

    # --- Режимы ---
    tasks_list = []

    if job.mode in ('api', 'full'):
        # API-метаданные по батчам (lang_meta уже собрана в collection phase)
        api_batches = []
        for batch_slugs in slug_batches:
            meta_subset = {s: api_meta[s] for s in batch_slugs if s in api_meta}
            lang_subset = {
                lang: {s: meta[s] for s in batch_slugs if s in meta}
                for lang, meta in api_meta_by_lang.items()
            }
            api_batches.append(
                process_api_batch.s(
                    job_id_hex, batch_slugs, meta_subset, lang_subset,
                )
            )
        tasks_list.extend(api_batches)

    if job.mode in ('html', 'full'):
        # HTML-парсинг по батчам
        html_batches = []
        for batch_slugs in slug_batches:
            thumb_subset = {s: thumb_map[s] for s in batch_slugs if s in thumb_map}
            html_batches.append(
                process_html_batch.s(job_id_hex, batch_slugs, thumb_subset)
            )
        tasks_list.extend(html_batches)

    if not tasks_list:
        job.status = 'completed'
        job.finished_at = timezone.now()
        job.summary = 'Нет задач для выполнения'
        job.save()
        return

    job.total_batches = len(tasks_list)
    job.save(update_fields=['total_slugs', 'total_batches', 'status', 'skipped'])

    _job_log(
        job_id_hex,
        f'Запуск {len(tasks_list)} батчей (batch_size={batch_size})'
    )

    # chord: все batch-таски параллельно → finalize
    callback = finalize_parse_job.s(job_id_hex)
    chord(group(tasks_list))(callback)
