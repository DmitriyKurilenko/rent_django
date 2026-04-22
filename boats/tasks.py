"""
Celery tasks для асинхронного парсинга лодок
"""
import logging
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


@shared_task(bind=True, max_retries=2)
def send_feedback_notification(self, feedback_id):
    """Уведомление о новом обращении через форму обратной связи.

    Отправляет сообщение в Telegram и на email (FEEDBACK_EMAIL).
    Оба канала независимы: сбой одного не блокирует другой.
    Fail-silent когда токены/SMTP не сконфигурированы.
    """
    from django.conf import settings
    from django.core.mail import send_mail
    from boats.models import Feedback
    from boats.telegram import send_telegram_message

    try:
        fb = Feedback.objects.get(pk=feedback_id)
    except Feedback.DoesNotExist:
        logger.warning('[Feedback] Feedback pk=%s not found, skipping', feedback_id)
        return {'status': 'not_found'}

    phone_line = f'Телефон: {fb.phone}\n' if fb.phone else ''
    tg_text = (
        f'📩 <b>Новое обращение с сайта</b>\n'
        f'Имя: {fb.name}\n'
        f'Email: {fb.email}\n'
        f'{phone_line}'
        f'Сообщение: {fb.message}'
    )
    tg_ok = False
    try:
        tg_ok = send_telegram_message(tg_text)
        if not tg_ok:
            logger.warning('[Feedback] Telegram skipped (not configured or API error)')
    except Exception:
        logger.exception('[Feedback] Telegram send failed')

    email_ok = False
    feedback_email = getattr(settings, 'FEEDBACK_EMAIL', '')
    if feedback_email:
        subject = f'Новое обращение: {fb.name}'
        body = (
            f'Имя: {fb.name}\n'
            f'Email: {fb.email}\n'
            f'Телефон: {fb.phone or "—"}\n\n'
            f'Сообщение:\n{fb.message}'
        )
        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[feedback_email],
                fail_silently=False,
            )
            email_ok = True
        except Exception as exc:
            logger.exception('[Feedback] Email send failed')
            try:
                raise self.retry(exc=exc, countdown=30)
            except self.MaxRetriesExceededError:
                logger.warning('[Feedback] Email max retries exceeded')
    else:
        logger.debug('[Feedback] Email skipped: FEEDBACK_EMAIL not configured')

    return {'tg': 'sent' if tg_ok else 'skipped', 'email': 'sent' if email_ok else 'skipped'}


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
        result = parse_boataround_url(url, save_to_db=True, html_mode='services_only')

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
        "[Celery] ✅ Батч завершен! "
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
    Deprecated.
    Ранее обновляла cockpit/entertainment/equipment из HTML, но это больше не
    соответствует source-of-truth политике проекта.
    """
    logger.warning(
        '[Celery] refresh_boat_amenities is deprecated and skipped for slug=%s '
        '(use parse_boats modes api/html/full instead)',
        boat_slug,
    )
    return {'status': 'skipped', 'slug': boat_slug, 'reason': 'deprecated'}


@shared_task(bind=True)
def refresh_amenities_batch(self, boat_slugs):
    """Deprecated batch wrapper for refresh_boat_amenities."""
    total = len(boat_slugs)
    skipped = 0
    logger.warning('[Celery] refresh_amenities_batch is deprecated, skipping %s лодок', total)
    for slug in boat_slugs:
        result = refresh_boat_amenities(slug)
        if result.get('status') == 'skipped':
            skipped += 1
    return {
        'status': 'completed',
        'total': total,
        'success': 0,
        'failed': 0,
        'skipped': skipped,
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
        'EMAIL не настроен, пропускаю отправку'
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
DETAIL_CACHE_LANGS = ['ru_RU', 'en_EN', 'de_DE', 'fr_FR', 'es_ES']


def _invalidate_boat_detail_cache(slugs):
    """Инвалидирует detail-кэш для набора slug по всем поддерживаемым языкам."""
    if not slugs:
        return
    try:
        from django.core.cache import cache

        keys = [
            f'boat_data:{slug}:{lang}'
            for slug in slugs
            for lang in DETAIL_CACHE_LANGS
            if slug
        ]
        if keys:
            cache.delete_many(keys)
    except Exception as e:
        logger.warning(f'[cache] failed to invalidate boat detail cache: {e}')


def _clear_api_unavailable_amenities(slugs):
    """
    API source-of-truth normalization.

    В API-поиске нет достоверных per-boat cockpit/entertainment/equipment,
    поэтому в mode=api эти поля должны быть очищены, чтобы не оставался
    исторический HTML-мусор в BoatDetails.
    """
    if not slugs:
        return 0

    try:
        from boats.models import BoatDetails

        return BoatDetails.objects.filter(boat__slug__in=slugs).update(
            cockpit=[],
            entertainment=[],
            equipment=[],
        )
    except Exception as e:
        logger.warning(f'[api-normalize] failed to clear amenities for api mode: {e}')
        return 0


def _job_log(job_id, message):
    """Атомарно добавляет строку в лог ParseJob."""
    from boats.models import ParseJob
    try:
        job = ParseJob.objects.get(job_id=job_id)
        job.append_log(message)
    except Exception:
        logger.warning(f'[parse_job] Не удалось записать лог для job {job_id}')


CACHE_DIR = (
    __import__('pathlib').Path(
        __import__('django.conf', fromlist=['settings']).settings.BASE_DIR
    ) / '.parse_cache'
)


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


def _save_slug_cache(destination, max_pages, slugs, thumb_map,
                     last_page=0, total_pages=0, complete=False):
    """Сохраняет slug'и и thumb_map в кэш (легковесный).

    API-метаданные больше НЕ хранятся в кэше — они сбрасываются в БД
    по мере сбора (per-page flush). Это предотвращает OOM на больших каталогах.
    """
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
        }
        with open(path, 'w') as f:
            _json.dump(data, f)
        logger.info(f'[collect_slugs] Кэш сохранён: {len(slugs)} slug, стр.{last_page}, complete={complete}')
    except Exception as e:
        logger.warning(f'[collect_slugs] Ошибка записи кэша: {e}')


def _collect_slugs_from_api(destination, max_pages, job_id=None, no_cache=False):
    """Собирает slug'и и thumb_map из API (только EN, без DB-записей).

    Легковесная функция — только сбор slug'ов и превью-URL.
    API-метаданные НЕ записываются в БД здесь — для этого используются
    отдельные disposable tasks (process_api_page_range).

    Инкрементальный кэш: сохраняет slugs + thumb_map после каждой страницы.
    При рестарте — продолжает с last_page.
    Завершённый кэш (complete=True) — возвращается мгновенно.
    --no-cache сбрасывает кэш и начинает с нуля.

    Returns:
        dict: {slugs, thumb_map, pages_scanned, effective_pages}
    """
    import gc
    from boats.boataround_api import BoataroundAPI, format_boat_data
    from boats.models import ParseJob

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
        tp = cached.get('total_pages', 0)
        eff = min(tp, max_pages) if max_pages and tp else tp
        if job_id:
            _job_log(job_id, f'Загружено из кэша: {len(cached["slugs"])} slug (завершённый)')
        return {
            'slugs': cached['slugs'],
            'thumb_map': cached.get('thumb_map', {}),
            'pages_scanned': 0,
            'effective_pages': eff,
        }

    # --- Восстанавливаем состояние из частичного кэша или начинаем с нуля ---
    if cached and not cached.get('complete'):
        slugs = cached.get('slugs', [])
        seen = set(slugs)
        thumb_map = cached.get('thumb_map', {})
        start_page = cached.get('last_page', 0) + 1
        total_pages = cached.get('total_pages') or None
        if job_id:
            _job_log(job_id, f'Продолжение из кэша: {len(slugs)} slug, стр.{start_page}')
        logger.info(f'[collect_slugs] Resume: {len(slugs)} slug, start page {start_page}')
    else:
        slugs = []
        seen = set()
        thumb_map = {}
        start_page = 1
        total_pages = None

    pages_scanned = 0
    page = start_page

    while True:
        # Проверяем отмену каждые 10 страниц
        if job_id and page % 10 == 0:
            try:
                status = ParseJob.objects.filter(
                    job_id=job_id,
                ).values_list('status', flat=True).first()
                if status == 'cancelled':
                    logger.info(f'[collect_slugs] Отмена на стр.{page}')
                    _job_log(job_id, f'Сбор прерван (отмена). Собрано {len(slugs)} slug, стр.{page}.')
                    _save_slug_cache(
                        destination, max_pages, slugs, thumb_map,
                        last_page=page, total_pages=total_pages or 0, complete=False,
                    )
                    break
            except Exception:
                pass

        # search() внутри уже имеет 3 retry с backoff
        results = BoataroundAPI.search(
            destination=destination or None,
            page=page, limit=18, lang='en_EN',
        )

        if not results or not results.get('boats'):
            logger.info(f'[collect_slugs] Пустая страница {page}, сохраняю кэш и завершаю')
            if job_id:
                _job_log(job_id, f'Пустая страница (стр.{page}). Собрано {len(slugs)} slug.')
            _save_slug_cache(
                destination, max_pages, slugs, thumb_map,
                last_page=page, total_pages=total_pages or 0, complete=False,
            )
            break

        # --- Обработка EN-результатов для slug/thumb ---
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

        pages_scanned += 1

        if total_pages is None:
            total_pages = int(results.get('totalPages') or 1)
        effective = min(total_pages, max_pages) if max_pages else total_pages

        # Кэш после каждой страницы
        is_complete = page >= effective
        _save_slug_cache(
            destination, max_pages, slugs, thumb_map,
            last_page=page, total_pages=total_pages, complete=is_complete,
        )

        # Прогресс каждые 10 страниц
        if job_id and pages_scanned % 10 == 0:
            _job_log(
                job_id,
                f'Сбор slug: стр.{page}/{effective}, найдено {len(slugs)} slug',
            )

        # gc каждые 50 страниц
        if pages_scanned % 50 == 0:
            gc.collect()

        if is_complete:
            if job_id:
                _job_log(job_id, f'Сбор завершён: {len(slugs)} slug, {pages_scanned} стр.')
            break
        page += 1

    effective_pages = (
        min(total_pages, max_pages) if max_pages and total_pages
        else (total_pages or 0)
    )
    return {
        'slugs': slugs,
        'thumb_map': thumb_map,
        'pages_scanned': pages_scanned,
        'effective_pages': effective_pages,
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
        _invalidate_boat_detail_cache(batch_slugs)

        ParseJob.objects.filter(job_id=job_id_hex).update(
            processed=F('processed') + len(batch_slugs),
            success=F('success') + updated,
            skipped=F('skipped') + (len(batch_slugs) - updated),
            batches_done=F('batches_done') + 1,
        )
        _job_log(
            job_id_hex,
            f'API batch OK: {len(batch_slugs)} slug, {updated} updated',
        )
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
def process_api_page_range(self, job_id_hex, destination, start_page, end_page):
    """Disposable task: загружает API-страницы start..end с 5 языками, пишет в БД.

    Каждый task обрабатывает ~20 страниц и завершается.
    Worker переиспользуется через --max-tasks-per-child.
    """
    import gc
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from boats.boataround_api import BoataroundAPI
    from boats.models import ParseJob
    from django.db.models import F

    job_id_hex = str(job_id_hex)
    total_updated = 0
    total_processed = 0

    for page in range(start_page, end_page + 1):
        # Fetch EN page
        results = BoataroundAPI.search(
            destination=destination or None,
            page=page, limit=18, lang='en_EN',
        )
        if not results or not results.get('boats'):
            break

        # Fetch other languages in parallel
        def _fetch_lang_page(api_lang):
            r = BoataroundAPI.search(
                destination=destination or None,
                page=page, limit=18, lang=api_lang,
            )
            return api_lang, (r or {}).get('boats', [])

        other_langs = [lang for lang in SUPPORTED_API_LANGS if lang != 'en_EN']
        boats_by_lang = {'en_EN': results.get('boats', [])}

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(_fetch_lang_page, lang): lang for lang in other_langs}
            for future in as_completed(futures):
                try:
                    lang, boats = future.result(timeout=60)
                    boats_by_lang[lang] = boats
                except Exception:
                    boats_by_lang[futures[future]] = []

        # Build api_meta and api_meta_by_lang for this page
        page_api_meta = {}
        page_api_meta_by_lang = {}

        for api_lang, boats_lang in boats_by_lang.items():
            for boat_lang in boats_lang:
                lang_slug = boat_lang.get('slug')
                if not lang_slug:
                    continue
                page_api_meta_by_lang.setdefault(api_lang, {})[lang_slug] = {
                    'title': boat_lang.get('title', ''),
                    'location': (
                        boat_lang.get('location', '')
                        or boat_lang.get('region', '')
                        or boat_lang.get('country', '')
                    ),
                    'marina': boat_lang.get('marina', ''),
                    'country': boat_lang.get('country', ''),
                    'region': boat_lang.get('region', ''),
                    'city': boat_lang.get('city', ''),
                }

        for boat in results['boats']:
            boat_slug = boat.get('slug')
            if not boat_slug:
                continue
            page_api_meta[boat_slug] = {
                'country': boat.get('country', ''),
                'region': boat.get('region', ''),
                'city': boat.get('city', ''),
                'marina': boat.get('marina', ''),
                'title': boat.get('title', ''),
                'location': (
                    boat.get('location', '')
                    or boat.get('region', '')
                    or boat.get('country', '')
                ),
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

        # Flush to DB
        page_updated = 0
        if page_api_meta:
            try:
                from boats.management.commands.parse_boats_parallel import (
                    Command as PBPCommand,
                )
                page_updated = PBPCommand._update_api_metadata(
                    page_api_meta, page_api_meta_by_lang,
                )
                page_slugs = list(page_api_meta.keys())
                _invalidate_boat_detail_cache(page_slugs)
                total_updated += page_updated
            except Exception as e:
                logger.error(f'[process_api_page_range] Page {page} flush error: {e}')

        total_processed += len(page_api_meta)

        # Update ParseJob counters
        try:
            ParseJob.objects.filter(job_id=job_id_hex).update(
                processed=F('processed') + len(page_api_meta),
                success=F('success') + page_updated,
            )
        except Exception:
            pass

        # Free memory
        del page_api_meta, page_api_meta_by_lang, boats_by_lang, results
        gc.collect()

    # Clear Django's internal query log and close stale DB connections
    from django import db
    db.reset_queries()
    db.close_old_connections()
    gc.collect()

    # Increment batches_done
    try:
        ParseJob.objects.filter(job_id=job_id_hex).update(
            batches_done=F('batches_done') + 1,
        )
    except Exception:
        pass

    _job_log(
        job_id_hex,
        f'API pages {start_page}-{end_page}: {total_processed} boats, '
        f'{total_updated} updated',
    )
    return {
        'status': 'ok',
        'processed': total_processed,
        'updated': total_updated,
        'pages': f'{start_page}-{end_page}',
    }


@shared_task(bind=True, max_retries=1)
def process_html_batch(self, job_id_hex, batch_slugs, thumb_map_subset, html_mode='services_only'):
    """Парсит батч лодок через HTML. Обновляет ParseJob атомарно."""
    from boats.models import ParseJob
    from django.db.models import F

    job_id_hex = str(job_id_hex)
    batch_success = 0
    batch_failed = 0
    batch_errors = []

    for slug in batch_slugs:
        try:
            url = f'https://www.boataround.com/ru/yachta/{slug}/'
            result = parse_boataround_url(url, save_to_db=True, html_mode=html_mode)
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
        f'(failed: {batch_failed}, html_mode={html_mode})'
    )

    # Free memory: clear query log and close stale connections
    import gc
    from django import db
    db.reset_queries()
    db.close_old_connections()
    gc.collect()

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

    # Обновляем счётчики из актуальных данных БД
    job.refresh_from_db()

    job.finished_at = timezone.now()

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
        '---',
        f'Slug\'ов: {job.total_slugs}',
        f'Обработано: {job.processed}',
        f'Успешно: {job.success}',
        f'Ошибок: {job.failed}',
        f'Пропущено: {job.skipped}',
        '---',
        f'Батчей: {job.batches_done}/{job.total_batches}',
        f'Время: {int(duration)}с ({duration / 60:.1f} мин)',
        f'Скорость: {rate:.1f}/с',
        '---',
        'БД итого:',
        f'  ParsedBoat: {db_stats["parsed_boats"]}',
        f'  Фото: {db_stats["photos"]}',
        f'  Описания: {db_stats["descriptions"]}',
        f'  Детали: {db_stats["details"]}',
        f'  Тех. спеки: {db_stats["specs"]}',
    ]
    if errors_count > 0:
        summary_lines.append('---')
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


# ------------------------------------------------------------------
# FAST PARALLEL PARSE (--workers N)
# ------------------------------------------------------------------

@shared_task(bind=True, max_retries=0)
def run_parse_workers(self, job_id_hex, workers=8, retry_slugs=None, no_cache=False,
                      skip_fresh_hours=None):
    """Быстрый параллельный парсинг: сбор slug'ов + ThreadPoolExecutor.

    Один Celery task, N параллельных потоков для I/O-bound HTTP.
    Обновляет ParseJob атомарно каждые FLUSH_EVERY slug'ов.
    """
    import gc
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from boats.models import ParseJob, ParsedBoat
    from django.db.models import F
    from django.utils import timezone

    FLUSH_EVERY = 10  # обновлять ParseJob каждые N slug'ов

    job_id_hex = str(job_id_hex)
    try:
        job = ParseJob.objects.get(job_id=job_id_hex)
    except ParseJob.DoesNotExist:
        logger.error(f'[run_parse_workers] ParseJob {job_id_hex} not found')
        return

    job.status = 'collecting'
    job.started_at = timezone.now()
    job.celery_task_id = self.request.id or ''
    job.save(update_fields=['status', 'started_at', 'celery_task_id'])

    # Глушим спам
    logging.getLogger('boats.parser').setLevel(logging.WARNING)
    logging.getLogger('boats.boataround_api').setLevel(logging.WARNING)

    # --- Фаза 1: Slug'и ---
    if retry_slugs:
        all_slugs = retry_slugs
        # thumb_map из кэша slug'ов (если есть)
        cached = _load_slug_cache(job.destination or None, job.max_pages)
        thumb_map = cached.get('thumb_map', {}) if cached else {}
        _job_log(job_id_hex, f'Retry mode: {len(all_slugs)} slug\'ов')
    else:
        try:
            collected = _collect_slugs_from_api(
                destination=job.destination or None,
                max_pages=job.max_pages,
                job_id=job_id_hex,
                no_cache=no_cache,
            )
        except Exception as e:
            job.status = 'failed'
            job.finished_at = timezone.now()
            job.summary = f'Ошибка сбора slug\'ов: {e}'
            job.save(update_fields=['status', 'finished_at', 'summary'])
            _job_log(job_id_hex, f'FAIL: сбор slug\'ов: {e}')
            return

        all_slugs = collected['slugs']
        thumb_map = collected['thumb_map']

    if not all_slugs:
        job.status = 'completed'
        job.finished_at = timezone.now()
        job.summary = 'Нет slug\'ов для обработки'
        job.save(update_fields=['status', 'finished_at', 'summary'])
        return

    # --- Фаза 2: Подготовка ---
    if job.mode in ('html', 'full'):
        html_mode = 'all_html' if job.mode == 'full' else 'services_only'
        slugs = list(all_slugs)

        if job.skip_existing:
            existing = set(ParsedBoat.objects.values_list('slug', flat=True))
            before = len(slugs)
            slugs = [s for s in slugs if s not in existing]
            skipped = before - len(slugs)
            if skipped:
                job.skipped = skipped
                _job_log(job_id_hex, f'Пропущено существующих: {skipped}')

        if skip_fresh_hours:
            cutoff = timezone.now() - timezone.timedelta(hours=skip_fresh_hours)
            fresh_slugs = set(
                ParsedBoat.objects.filter(
                    slug__in=slugs,
                    last_parsed__gte=cutoff,
                    last_parse_success=True,
                ).values_list('slug', flat=True)
            )
            if fresh_slugs:
                before = len(slugs)
                slugs = [s for s in slugs if s not in fresh_slugs]
                skipped_fresh = before - len(slugs)
                job.skipped = (job.skipped or 0) + skipped_fresh
                _job_log(job_id_hex, f'Пропущено свежих (<{skip_fresh_hours}ч): {skipped_fresh}')

        job.total_slugs = len(slugs) + (job.skipped or 0)
        job.status = 'running'
        job.save(update_fields=['total_slugs', 'status', 'skipped'])
        _job_log(
            job_id_hex,
            f'HTML-парсинг: {len(slugs)} slug, {workers} workers, html_mode={html_mode}',
        )

        _run_workers_html(job_id_hex, slugs, thumb_map, html_mode, workers, FLUSH_EVERY)

    elif job.mode == 'api':
        effective_pages = (
            0 if retry_slugs
            else collected.get('effective_pages', 0)
        )
        if not effective_pages:
            job.status = 'completed'
            job.finished_at = timezone.now()
            job.summary = 'Нет страниц для API-обработки'
            job.save(update_fields=['status', 'finished_at', 'summary'])
            return

        job.total_slugs = len(all_slugs)
        job.status = 'running'
        job.save(update_fields=['total_slugs', 'status'])
        _job_log(
            job_id_hex,
            f'API-парсинг: {effective_pages} стр., {workers} workers',
        )

        _run_workers_api(
            job_id_hex, all_slugs, thumb_map,
            effective_pages, job.destination, workers, FLUSH_EVERY,
        )

    # --- Фаза 3: Финализация ---
    # Инвалидируем кэш для обработанных slug'ов
    try:
        _invalidate_boat_detail_cache(all_slugs)
    except Exception:
        pass

    # Финализируем через стандартный finalize (синхронно)
    finalize_parse_job.apply(args=[[], job_id_hex])

    # Очистка
    from django import db
    db.reset_queries()
    db.close_old_connections()
    gc.collect()


def _run_workers_html(job_id_hex, slugs, thumb_map, html_mode, workers, flush_every):
    """Параллельный HTML-парсинг через ThreadPoolExecutor."""
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from boats.models import ParseJob
    from boats.parser import parse_boataround_url
    from django.db.models import F

    lock = threading.Lock()
    counters = {'success': 0, 'failed': 0}
    errors_batch = []

    def _parse_one(slug):
        try:
            url = f'https://www.boataround.com/ru/yachta/{slug}/'
            result = parse_boataround_url(url, save_to_db=True, html_mode=html_mode)
            if result:
                thumb_url = thumb_map.get(slug)
                if thumb_url:
                    _save_preview_for_slug(slug, thumb_url)
                with lock:
                    counters['success'] += 1
            else:
                with lock:
                    counters['failed'] += 1
                    errors_batch.append({'slug': slug, 'error': 'Parser returned None'})
        except Exception as e:
            with lock:
                counters['failed'] += 1
                errors_batch.append({'slug': slug, 'error': str(e)[:200]})

    done = 0
    last_flushed = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_parse_one, s): s for s in slugs}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception:
                pass
            done += 1

            if done - last_flushed >= flush_every:
                _flush_workers_progress(
                    job_id_hex, done - last_flushed,
                    counters, errors_batch, lock,
                )
                last_flushed = done

    # Финальный flush
    if done > last_flushed:
        _flush_workers_progress(
            job_id_hex, done - last_flushed,
            counters, errors_batch, lock,
        )


def _run_workers_api(job_id_hex, all_slugs, thumb_map, effective_pages,
                     destination, workers, flush_every):
    """Параллельный API-парсинг через ThreadPoolExecutor."""
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from boats.boataround_api import BoataroundAPI
    from boats.models import ParseJob
    from django.db.models import F

    lock = threading.Lock()
    counters = {'success': 0, 'failed': 0}
    errors_batch = []

    def _process_page(page):
        try:
            updated, errs = _fetch_and_save_api_page(
                page, destination, BoataroundAPI, SUPPORTED_API_LANGS,
            )
            with lock:
                counters['success'] += updated
                if errs:
                    counters['failed'] += len(errs)
                    errors_batch.extend(
                        {'slug': slug, 'error': err} for slug, err in errs
                    )
        except Exception as e:
            with lock:
                counters['failed'] += 1
                errors_batch.append({'slug': f'page-{page}', 'error': str(e)[:200]})

    pages = list(range(1, effective_pages + 1))
    done = 0
    last_flushed = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_process_page, p): p for p in pages}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception:
                pass
            done += 1

            if done - last_flushed >= flush_every:
                _flush_workers_progress(
                    job_id_hex, done - last_flushed,
                    counters, errors_batch, lock,
                )
                last_flushed = done

    if done > last_flushed:
        _flush_workers_progress(
            job_id_hex, done - last_flushed,
            counters, errors_batch, lock,
        )


def _flush_workers_progress(job_id_hex, processed_delta, counters, errors_batch, lock):
    """Сбрасывает накопленный прогресс в ParseJob."""
    from boats.models import ParseJob
    from django.db.models import F

    with lock:
        s = counters['success']
        f = counters['failed']
        errs = list(errors_batch)
        counters['success'] = 0
        counters['failed'] = 0
        errors_batch.clear()

    ParseJob.objects.filter(job_id=job_id_hex).update(
        processed=F('processed') + processed_delta,
        success=F('success') + s,
        failed=F('failed') + f,
    )

    if errs:
        try:
            job_obj = ParseJob.objects.get(job_id=job_id_hex)
            for err in errs:
                job_obj.append_error(err['slug'], err['error'])
        except Exception:
            pass


def _fetch_and_save_api_page(page, destination, BoataroundAPI, supported_langs):
    """Обрабатывает одну API-страницу: 5 языков, сохранение в БД."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = BoataroundAPI.search(
        destination=destination or None,
        page=page, limit=18, lang='en_EN',
    )
    if not results or not results.get('boats'):
        return 0, []

    other_langs = [lang for lang in supported_langs if lang != 'en_EN']
    boats_by_lang = {'en_EN': results.get('boats', [])}

    def _fetch_lang(api_lang):
        r = BoataroundAPI.search(
            destination=destination or None,
            page=page, limit=18, lang=api_lang,
        )
        return api_lang, (r or {}).get('boats', [])

    with ThreadPoolExecutor(max_workers=len(other_langs)) as executor:
        futs = {executor.submit(_fetch_lang, lang): lang for lang in other_langs}
        for fut in as_completed(futs):
            try:
                lang, boats = fut.result(timeout=60)
                boats_by_lang[lang] = boats
            except Exception:
                boats_by_lang[futs[fut]] = []

    page_api_meta = {}
    page_api_meta_by_lang = {}

    for api_lang, boats_lang in boats_by_lang.items():
        for boat_lang in boats_lang:
            lang_slug = boat_lang.get('slug')
            if not lang_slug:
                continue
            page_api_meta_by_lang.setdefault(api_lang, {})[lang_slug] = {
                'title': boat_lang.get('title', ''),
                'location': (
                    boat_lang.get('location', '')
                    or boat_lang.get('region', '')
                    or boat_lang.get('country', '')
                ),
                'marina': boat_lang.get('marina', ''),
                'country': boat_lang.get('country', ''),
                'region': boat_lang.get('region', ''),
                'city': boat_lang.get('city', ''),
            }

    for boat in results['boats']:
        boat_slug = boat.get('slug')
        if not boat_slug:
            continue
        page_api_meta[boat_slug] = {
            'country': boat.get('country', ''),
            'region': boat.get('region', ''),
            'city': boat.get('city', ''),
            'marina': boat.get('marina', ''),
            'title': boat.get('title', ''),
            'location': (
                boat.get('location', '')
                or boat.get('region', '')
                or boat.get('country', '')
            ),
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

    if page_api_meta:
        from boats.management.commands.parse_boats_parallel import (
            Command as PBPCommand,
        )
        updated = PBPCommand._update_api_metadata(
            page_api_meta, page_api_meta_by_lang,
        )
        page_slugs = list(page_api_meta.keys())
        _invalidate_boat_detail_cache(page_slugs)
        return updated, []
    return 0, []


@shared_task(bind=True, max_retries=0)
def run_parse_job(self, job_id_hex, no_cache=False):
    """Оркестратор: собирает slug'и (легковесно, EN-only), затем
    диспатчит disposable tasks для тяжёлой работы.

    Для mode=api: API source-of-truth (без HTML этапа).
    Для mode=html: HTML только фото + extras/additional_services/delivery_extras/not_included.
    Для mode=full: полностью HTML (legacy full HTML profile).
    Все tasks → chord → finalize_parse_job.
    """
    from boats.models import ParseJob, ParsedBoat
    from django.utils import timezone

    PAGES_PER_RANGE = 3

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
    _job_log(
        job_id_hex,
        f'Начат сбор slug\'ов (mode={job.mode}, dest={job.destination or "все"})',
    )

    # Глушим спам парсера в Celery-воркере
    logging.getLogger('boats.parser').setLevel(logging.WARNING)
    logging.getLogger('boats.boataround_api').setLevel(logging.WARNING)

    # --- Фаза 1: Лёгкий сбор slug'ов (EN-only, без DB-записей) ---
    try:
        collected = _collect_slugs_from_api(
            destination=job.destination or None,
            max_pages=job.max_pages,
            job_id=job_id_hex,
            no_cache=no_cache,
        )
    except Exception:
        job.status = 'failed'
        job.finished_at = timezone.now()
        job.summary = 'Ошибка сбора slug\'ов'
        job.save(update_fields=['status', 'finished_at', 'summary'])
        _job_log(job_id_hex, 'FAIL: сбор slug\'ов')
        return

    # Проверяем отмену после сбора
    job.refresh_from_db()
    if job.status == 'cancelled':
        _job_log(job_id_hex, 'Задание отменено после сбора slug\'ов')
        return

    all_slugs = collected['slugs']
    thumb_map = collected['thumb_map']
    effective_pages = collected.get('effective_pages', 0)

    _job_log(
        job_id_hex,
        f'Собрано {len(all_slugs)} slug\'ов ({collected["pages_scanned"]} стр., '
        f'effective_pages={effective_pages})',
    )

    # --- Фаза 2: Формируем tasks ---
    tasks_list = []

    # API page-range tasks только для mode=api.
    # mode=html/full не должны трогать API-пайплайн.
    if job.mode == 'api' and effective_pages > 0:
        for start in range(1, effective_pages + 1, PAGES_PER_RANGE):
            end = min(start + PAGES_PER_RANGE - 1, effective_pages)
            tasks_list.append(
                process_api_page_range.s(
                    job_id_hex, job.destination or None, start, end,
                )
            )
        _job_log(
            job_id_hex,
            f'API: {len(tasks_list)} page-range task(ов) '
            f'(по {PAGES_PER_RANGE} стр.)',
        )

    # HTML batch tasks (для mode=html или mode=full)
    if job.mode in ('html', 'full'):
        html_mode = 'all_html' if job.mode == 'full' else 'services_only'
        html_slugs = list(all_slugs)

        # Фильтрация существующих
        if job.skip_existing:
            existing = set(ParsedBoat.objects.values_list('slug', flat=True))
            before = len(html_slugs)
            html_slugs = [s for s in html_slugs if s not in existing]
            skipped = before - len(html_slugs)
            if skipped:
                _job_log(job_id_hex, f'Пропущено существующих: {skipped}')
                job.skipped = (job.skipped or 0) + skipped

        batch_size = job.batch_size
        slug_batches = [
            html_slugs[i:i + batch_size]
            for i in range(0, len(html_slugs), batch_size)
        ]
        for batch_slugs in slug_batches:
            thumb_subset = {s: thumb_map[s] for s in batch_slugs if s in thumb_map}
            tasks_list.append(
                process_html_batch.s(job_id_hex, batch_slugs, thumb_subset, html_mode)
            )
        _job_log(
            job_id_hex,
            f'HTML: {len(slug_batches)} batch(ей) '
            f'(batch_size={batch_size}, slug={len(html_slugs)}, html_mode={html_mode})',
        )

    if not tasks_list:
        job.refresh_from_db()
        job.status = 'completed'
        job.finished_at = timezone.now()
        job.total_slugs = len(all_slugs)
        job.summary = 'Нет задач для выполнения'
        job.save()
        _job_log(job_id_hex, 'Нет задач для выполнения')
        return

    # --- Фаза 3: Запуск chord ---
    job.refresh_from_db()
    job.total_slugs = len(all_slugs)
    job.total_batches = len(tasks_list)
    job.status = 'running'
    job.save(update_fields=['total_slugs', 'total_batches', 'status', 'skipped'])

    _job_log(
        job_id_hex,
        f'Запуск {len(tasks_list)} task(ов) → chord → finalize',
    )

    callback = finalize_parse_job.s(job_id_hex)
    chord(group(tasks_list))(callback)
