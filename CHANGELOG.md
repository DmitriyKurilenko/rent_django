# Changelog

All notable changes to BoatRental project will be documented in this file.

## [0.5.3-dev] - 2026-04-04

### 🔧 Fixed — Hide "Гибкая отмена" service from all UI
- **HIDDEN_SERVICE_SLUGS**: `{'flexible-cancellation'}` constant in `helpers.py` — filters `additional_services` at view level (boat_detail_api, _build_boat_data_from_db, offer_view) and template level (detail.html, offer_captain.html).

### 📄 Docs — Full documentation audit & cleanup
- **README.md**: полностью переписан (актуальный стек, Docker-команды, модели, ссылки).
- **AGENTS.md**: стек обновлён (убраны Ninja/htmx/charts.js, добавлены версии). Добавлены правила RELEASE_NOTES.md в Update Ritual.
- **docs/RELEASE_NOTES.md**: создан — пользовательский changelog на русском.
- **docs/DECISIONS.md**: исправлены дублированные DR-017 → DR-024/025/026/027.
- **docs/TASK_STATE.md**: P7 обновлён, удалена дублированная секция.
- **docs/DEV_LOG.md**: исправлена запись 04-03 (TTL, retries).
- **docs/FAQ.md**: Django 4.2→5.2 LTS, Python 3.8→3.13, команды обновлены, bare-metal убран.
- **docs/INDEX.md**: битые ссылки исправлены, версии обновлены.
- **docs/I18N_ARCHITECTURE.md, I18N_QUICK_REFERENCE.md**: ссылки на Django docs 4.2→5.2.
- **Архивировано 7 файлов** в docs/archive/: I18N_FINAL_REPORT, I18N_SETUP, I18N_CODE_EXAMPLES, I18N_INDEX, PRODUCTION_INIT, QUICK_DEPLOY, PRODUCTION_UBUNTU_DEPLOYMENT.
- **Удалены**: CONTRIBUTING.md (устаревший), SECURITY.md (фейковые данные).

## [0.5.2-dev] - 2026-04-04

### ⚡ Perf — Slug collection: incremental cache, concurrent lang fetch
- **Incremental cache**: slug collection saves to `.parse_cache/` after every page. On restart resumes from `last_page`, no work lost. Complete cache returned instantly on next run.
- **Concurrent lang fetch**: 4 languages per page via `ThreadPoolExecutor` (~5s/page instead of ~17s sequential).
- **Removed double retry**: `search()` already has 3 internal retries; outer retry loop removed. 1 empty page = stop + save cache.
- **Single-pass lang meta**: `_fetch_lang_meta_for_slugs` removed — lang meta collected during collection phase, passed to batch tasks directly.
- **`--no-cache` flag**: deletes cache file, forces fresh collection. No TTL — cache persists until explicit `--no-cache`.
- **Removed `_boat_data_completeness`**: boat exists in DB = return it, no intermediate completeness checks.

## [0.5.1-dev] - 2026-04-02

### 🔧 Fixed — Detail page full parsing & error resilience
- **Detail/offer: полный парсинг (API → HTML)**: при отсутствии данных лодки detail page теперь парсит сначала API (BoatTechnicalSpecs, descriptions, charter), затем HTML (фото, сервисы, amenities). Ранее — только HTML, specs не создавались.
- **`_ensure_api_metadata_for_boat()`**: новый helper — подтягивает specs и charter из API для одной лодки через `_update_api_metadata`.
- **`search_by_slug(raw=True)`**: возвращает сырые API данные (с `parameters`) для создания specs.
- **`technical_specs` RelatedObjectDoesNotExist**: обёрнуто в try/except — лодки без specs рендерятся gracefully.
- **`detail.html` error path**: при `boat=None` (ошибка парсинга) шаблон больше не падает на `{% url 'toggle_favorite' boat.slug %}`.

## [0.5.0-dev] - 2026-04-01

### ✨ Added — Celery Parsing Pipeline & Agent Commission Settings
- **`parse_boats` management command**: батчевый парсинг через Celery с тремя режимами:
  - `--mode api` — только API-метаданные (country, charter, specs, coordinates)
  - `--mode html` — только HTML-парсинг (фото, extras, описания)
  - `--mode full` — оба режима последовательно
  - `--status [JOB_ID]` — просмотр прогресса и отчётов
  - Поддержка `--destination`, `--max-pages`, `--batch-size`, `--skip-existing`
- **`ParseJob` модель**: хранение заданий парсинга (прогресс, логи, ошибки, длительность)
- **`check_data_status` command**: полная диагностика данных (чартеры, геоданные, спеки, галерея, цены, офферы, бронирования, клиенты, договоры, пользователи)
- **`agent_commission_pct`** в PriceSettings: настраиваемый процент комиссии агента (default 50% от чартера)
- **Профиль пользователя**: бейджи роли и подписки, отображение комиссии для капитанов
- **`server_tasks.sh`**: скрипт для фоновых серверных задач (запуск, логи, статус)

### 🔧 Fixed — Captain Price Visibility & Parsing Stability
- **Комиссия капитана**: капитан видит свою долю (50% от чартера), а не полную комиссию чартера
- **Расшифровка цен в офферах**: скрыта от капитанов — доступна только менеджеру/админу
- **Кеш деталей**: инвалидация после автопривязки чартера (комиссия появляется сразу)
- **pricing.py**: восстановлена переменная `additional_discount_val` (поисковик возвращал 0 результатов)
- **`update_charters`**: retry-логика при сетевых ошибках (5 попыток, нарастающая задержка 10с→5мин)

### 📄 Documentation
- **docs/DECISIONS.md**: DR-018 (agent commission from settings)
- **docs/TASK_STATE.md**: обновлён
- **docs/DEV_LOG.md**: сессия 2026-04-01

### Files Changed
- `boats/models.py`: ParseJob model, agent_commission_pct field
- `boats/tasks.py`: run_parse_job, process_api_batch, process_html_batch
- `boats/management/commands/parse_boats.py`: new
- `boats/management/commands/check_data_status.py`: new
- `boats/management/commands/update_charters.py`: retry logic
- `boats/pricing.py`: configurable agent commission
- `boats/views.py`: captain price visibility, cache invalidation
- `boats/admin.py`: ParseJob admin
- `boats/tests/test_views.py`: updated commission tests
- `boats/migrations/0032_parse_job.py`, `0033_agent_commission_pct.py`: new
- `accounts/views.py`: agent commission in profile context
- `templates/accounts/profile.html`: role/subscription badges, commission
- `templates/accounts/price_settings.html`: agent_commission_pct field
- `templates/boats/search.html`, `detail.html`: captain commission display
- `server_tasks.sh`: new
- `VERSION`: 0.4.1-dev → 0.5.0-dev

## [0.4.1-dev] - 2026-03-31

### 🔧 Fixed - Charter Commission & Detail UI
- **Charter commission source**: reverted hardcoded DEFAULT_CHARTER_COMMISSION=20 fallback; commission is taken strictly from Charter model
- **Detail page readability**: replaced DaisyUI semantic colors (text-secondary/text-info/text-success) with Tailwind direct colors (text-amber-200/text-yellow-200/text-green-200) on purple gradient card; font size 11px → 13px

### ✨ Added - Charter Assignment Command
- **`update_charters`**: management command that scans Boataround API and assigns Charter FK to ParsedBoat records missing charter
  - `--destination` — scan specific destination
  - `--max-pages` — limit API pages
  - `--all` — update all boats (not just missing)
  - `--dry-run` — preview without DB writes

### 📄 Documentation
- **docs/DECISIONS.md**: DR-017 (charter commission source of truth)
- **docs/TASK_STATE.md**: updated done list, added risk item for 23k boats without charter
- **docs/DEV_LOG.md**: session 2 entry

### Files Changed
- `boats/helpers.py`, `boats/pricing.py`: reverted DEFAULT_CHARTER_COMMISSION
- `boats/management/commands/update_charters.py`: new
- `templates/boats/detail.html`: color/size fix
- `VERSION`: 0.4.0-dev → 0.4.1-dev

## [0.4.0-dev] - 2026-04-02

### 🔧 Fixed - Price Stability on Detail Page
- **Price caching fix**: `BoataroundAPI.get_price()` now checks 6-hour Redis cache before consensus loop
- **Eliminates symptom**: Refreshing detail page with same dates no longer shows different prices
- **Reduced API calls**: Cached results bypass 5-request consensus window entirely
- **Cleaner error handling**: Returns empty dict when all API requests fail (allows graceful fallback)
- **Impact**: KI-001 severity reduced from high → medium; pricing consistency (P0) marked RESOLVED

### 📄 Documentation
- **docs/VERSIONING.md**: New—semantic versioning scheme for development stage
- **docs/DEV_LOG.md**: Added entry for 2026-04-02 price cache fix
- **docs/DECISIONS.md**: Added DR-017 (cache-first lookup strategy)
- **docs/KNOWN_ISSUES.md**: Updated KI-001 with resolution path
- **docs/TASK_STATE.md**: P0 pricing consistency marked RESOLVED
- **VERSION**: Introduced version file (0.4.0-dev)

### Files Changed
- `boats/boataround_api.py`: `get_price()` method refactored
- `docs/VERSIONING.md`: New versioning guide
- `docs/DEV_LOG.md`, `docs/DECISIONS.md`, `docs/KNOWN_ISSUES.md`, `docs/TASK_STATE.md`: Updated
- `VERSION`: New file (0.4.0-dev)