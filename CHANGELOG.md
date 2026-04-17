# Changelog

All notable changes to BoatRental project will be documented in this file.

## [0.14.0-dev] - 2026-04-17

### ✨ Added — Fast Celery workers mode for catalog parsing
- **`boats/management/commands/parse_boats.py`**: added `--workers N` mode (single Celery task with internal parallel workers) and live progress polling in command output.
- **`boats/management/commands/parse_boats.py`** + **`boats/tasks.py`**: `--retry-errors` now reads failed slug list from `ParseJob.errors` (DB), no file-based retry source.
- **`boats/management/commands/parse_boats.py`** + **`boats/tasks.py`**: added `--skip-fresh [HOURS]` (default 24h when value omitted) to skip recently successful parses via `last_parsed` + `last_parse_success`.

### 🐛 Fixed — Parsing freshness and ParseJob completion metadata
- **`boats/parser.py`**: HTML save flow now updates `ParsedBoat.last_parsed` and `last_parse_success` (success and failure paths).
- **`boats/tasks.py`**: `finalize_parse_job` no longer loses `finished_at` after `refresh_from_db()`.

### 🔧 Changed — Parse mode boundaries and deprecated amenities refresh flow
- **`boats/parser.py`**, **`boats/tasks.py`**, **`boats/views.py`**, **`boats/helpers.py`**, **`boats/boataround_api.py`**, **`boats/management/commands/parse_all_boats.py`**, **`boats/management/commands/parse_boats_parallel.py`**: explicit `html_mode` routing is used across entry points; `services_only` is the default profile for critical flows.
- **`boats/management/commands/refresh_amenities.py`** and related Celery tasks in **`boats/tasks.py`** are now deprecated and return guidance to use `parse_boats --mode api|html|full`.
- **`boats/migrations/0035_alter_parsejob_mode.py`**: updated ParseJob mode labels to reflect source-of-truth semantics.
- **`docker-compose.yml`**: Celery worker concurrency is now configurable via `CELERY_CONCURRENCY`.
- **`.dockerignore`**: expanded build-context excludes (`media`, `mediafiles`, `.parse_cache`, `db.sqlite3`, backups/celery artifacts).

### 🧪 Tests
- Added **`boats/tests/test_parse_boats_api_mode.py`** (API mode behavior + cache invalidation checks).
- Extended **`boats/tests/test_parser_persistence.py`** with `services_only` / `all_html` persistence coverage.
- Updated **`boats/tests/test_refresh_amenities_tasks.py`** for deprecated-task semantics (`skipped` behavior).

## [0.13.1-dev] - 2026-04-13

### 🐛 Fixed — Countdown timer missing in public offer view
- **`boats/views.py`** (`offer_view`): Added countdown timer calculation (same logic as `offer_detail`). Previously `show_countdown` was passed as raw boolean but `countdown_end_iso` was missing — template condition `{% if show_countdown and countdown_end_iso %}` always failed, timer never rendered for clients viewing the public link.

### 🐛 Fixed — OOM kill (SIGKILL) in Celery page-range tasks (v4)
- **`boats/tasks.py`**: `PAGES_PER_RANGE: 5 → 3` — reduces memory footprint per task (3 pages × 5 languages instead of 5×5). Added `db.reset_queries()` + `db.close_old_connections()` + `gc.collect()` at end of both `process_api_page_range` and `process_html_batch` to clear Django query log and free ORM objects.
- **`docker-compose.prod.yml`**: `--max-tasks-per-child: 100 → 20` — worker fork recycled 5× more frequently, preventing Python arena fragmentation from accumulating to OOM on 1 GB VPS.

## [0.13.0-dev] - 2026-04-12

### ✨ Added — Strip charter company name from boat descriptions
- **`boats/templatetags/boat_filters.py`**: New template filter `strip_charter_company` removes the charter company mention sentence from the end of boat descriptions at display time (presentation layer only — database data untouched).
- **17 regex patterns** cover all 5 languages (EN, RU, DE, ES, FR) and all boat types: yacht, motorboat, catamaran, power catamaran, gulet, houseboat, goélette/péniche/goleta.
- **`templates/boats/detail.html`**: Description rendered via `{{ boat.description|strip_charter_company|linebreaks }}`. Description card hidden if result is empty.
- **Tested on 1500+ real descriptions** (300/language), 0 charter mentions leaked through.

## [0.12.0-dev] - 2026-04-12

### 🎨 Changed — Full DaisyUI 5 migration: all templates
- **13 templates migrated** from legacy DaisyUI v4 form classes (`form-control`, `label-text`, `label-text-alt`, `class="label"` as form labels) to DaisyUI 5 + Tailwind utilities.
- **Migration pattern**: `form-control` → plain `<div>`, `label`/`label-text` → `text-sm font-semibold mb-1.5`, errors → `text-xs text-error`, hints → `text-xs opacity-60`, checkbox wrappers → `cursor-pointer flex items-center gap-2`.
- **CSS compat shims removed**: 3 `@utility` blocks (form-control, label-text, label-text-alt) deleted from `assets/css/tailwind.input.css`.
- **Theme-native sizing**: Removed all explicit `-lg` size modifiers (`input-lg`, `select-lg`, `btn-lg`) from home, login, and register pages. All form elements now use the winter theme's `--size-field`/`--size-selector` sizing.
- **Templates**: `login.html`, `register.html`, `profile.html`, `price_settings.html`, `home.html`, `search.html`, `detail.html`, `offers_list.html`, `my_bookings.html`, `create_offer.html`, `create_contract.html`, `contract_sign.html`, `client_form.html`.
- **KI-011 downgraded**: from medium to low — no template uses affected classes anymore.

## [0.11.1-dev] - 2026-04-12

### 🐛 Fixed — Auth forms (login/register) broken layout
- **`templates/accounts/login.html`**: Replaced legacy DaisyUI v4 form structure (`form-control` divs, `label`/`label-text` spans, `focus:input-primary`, nested alert `<div>` wrappers) with working DaisyUI 5 approach: plain `<div>` field groups, `text-sm font-semibold` labels, `input w-full`/`select w-full`, `flex flex-col gap-4` form layout, flat `alert alert-error`.
- **`templates/accounts/register.html`**: Same migration. Subscription helper text uses `text-xs opacity-60 leading-relaxed` (wrappable). Select uses `select w-full`.
- **Root cause**: `.fieldset`/`.fieldset-legend` CSS rules are not generated by DaisyUI 5 plugin under Tailwind v4. `.label` class has `white-space: nowrap` + 60% transparent color — not suitable for field labels. See KI-011.

## [0.11.0-dev] - 2026-04-12

### ✨ Added — Commission display on offer page & offers list
- **`boats/views.py`**: Extracted `_compute_offer_commission(offer)` helper from `_build_price_debug` for reuse. `offer_detail` view now injects `commission` dict and visibility flags into context. `offers_list` view computes commission per offer via bulk DB query (`select_related('charter')`, single query for all slugs on the page).
- **`templates/boats/offer_captain.html`**: Commission block inside the price card — captain sees agent commission amount (€), manager/admin sees charter commission % + amount + agent commission + charter name.
- **`templates/boats/offers_list.html`**: New «Комиссия» column in desktop table and commission line in mobile cards. Captain sees agent commission, manager/admin sees full breakdown. Column hidden for users without commission visibility.
- **Visibility rules**: Reuses existing `_price_visibility_flags()` — `show_charter_commission_only` (captain) shows agent commission only; `show_full_price_breakdown` (manager/admin) shows full breakdown; anonymous/tourist sees nothing.

## [0.10.0-dev] - 2026-04-11

### ✨ Added — Quick offer modal: countdown timer & force-refresh flags
- **`templates/boats/detail.html`**: Both quick offer forms (manager/admin type-choice and captain-only) now include «Таймер обратного отсчета» (`show_countdown`) and «Обновить данные» (`force_refresh`) checkboxes. Rendered conditionally via `{% if user.profile.can_use_countdown %}` / `{% if user.profile.can_use_force_refresh %}`.
- **`boats/views.py`** (`quick_create_offer`): Reads `force_refresh` POST param with `can_use_force_refresh()` permission guard, passes to `_ensure_boat_data_for_critical_flow`. Reads `show_countdown` POST param with `can_use_countdown()` permission guard, sets on `Offer` model.
- **`accounts/models.py`**: New methods `can_use_countdown()` and `can_use_force_refresh()` delegating to permission system.
- **`accounts/migrations/0009_add_countdown_refresh_permissions.py`**: New permissions `use_countdown` (captain, assistant, manager, admin, superadmin) and `use_force_refresh` (assistant, manager, admin, superadmin).

## [0.9.0-dev] - 2026-04-10

### ✨ Added — Comprehensive search filters from Boataround API
- **11 new search filter parameters**: maxSleeps, allowedPeople, boatLength, manufacturer, skipper, sail, engineType, cockpit, entertainment, equipment, toilets.
- **`boats/boataround_api.py`**: `search()` accepts all 11 new named params, mapping to API camelCase equivalents (e.g., `engine_type` → `engineType`, `boat_length` → `boatLength`).
- **`boats/views.py`**: new GET param extraction with `getlist()` for multi-value checkboxes (sail, engine_type, cockpit, entertainment, equipment). `_build_range()` helper for DRY "from-to" formatting. Expanded `allowed_sorts` with `reviewsDown`, `dealsFirst`, `freeCancellation`. API filter response processed with `_id` → `id` rename (Django templates forbid underscore-prefix attributes). `_engine_names` fallback dict for engineType localization (API doesn't localize this filter). `active_*` context variables as lists for correct template membership check.
- **`templates/boats/search.html`**: Full sidebar rewrite with dynamic API-driven filters. Fixed category values (sailing-yacht, motor-yacht, motor-boat, catamaran, gulet, power-catamaran). Price filter moved after dates. Sticky scrollable sidebar (`max-h-[calc(100vh-6rem)] overflow-y-auto`). Collapsible sections for sail+engine, cockpit, entertainment, equipment using Alpine.js. Sort dropdown expanded. Active filter badges for all 17+ filter types. Detail link opens in new tab (`target="_blank"`). Mobile filter toggle.
- **`boats/templatetags/boat_filters.py`**: Added `split` template filter.

### 🐛 Fixed — Search filter bugs found during deep testing
- **Checkbox `checked` substring matching** (HIGH): `{% if item.id in active_sail %}` did string containment on comma-joined string. If one ID were a substring of another, both would show as checked. Fixed by passing lists instead of strings for all `active_*` context variables.
- **Manufacturer case-sensitivity** (MEDIUM): API expects lowercase slug IDs (`bavaria`), but text input allowed capitalized input (`Bavaria`). Added `.lower()` to manufacturer extraction.
- **Duplicate `@staticmethod` decorator** (LOW): `get_boat_combined_data()` in `boataround_api.py` had doubled decorator. Removed duplicate.

### 🔧 Improved — Search UX
- **Removed aggressive `Cache-Control` headers** from search response to allow browser bfcache. Prevents destination loss on back navigation.
- **Destination persistence**: Alpine.js `_lastSelectedName` tracking prevents `fetchLocations()` from zeroing selected destination when input text hasn't changed.
- **Sort persistence**: Sort choice saved in session — survives page changes and re-searches.

## [0.8.4-dev] - 2026-04-09

### 🐛 Fixed — OOM v3: reduce page-range task size + fix totalPages inflation
- **totalPages inflation**: `BoataroundAPI.search()` calculated `totalPages` using `len(boats)` on current page instead of the requested `limit`. When API returned fewer boats (e.g. 8 instead of 18), `totalPages` inflated from 1491 to 3354, doubling the number of dispatched tasks.
- **Fix**: use `limit` (stable value) for `totalPages` calculation in both response parsing branches.
- **PAGES_PER_RANGE: 20 → 5**: each `process_api_page_range` task now handles 5 pages (90 boats) instead of 20 (360 boats). Reduces ORM fragmentation per task by 4×. With full catalog (~1491 pages), dispatches ~298 tasks instead of ~75.
- **`process_api_page_range`**: added `batches_done` counter increment (was missing — `--status` showed `Батчи: 0/N` even at 88% progress). Added `del results` for per-page memory release.

## [0.8.3-dev] - 2026-04-08

### 🐛 Fixed — search_by_slug wrong API parameter (`slug` → `slugs`)
- **Root cause**: `search_by_slug()` sent `slug` (singular) as API query parameter. Boataround API ignores unknown params and returns 50 default boats. If target boat not in those 50 → `BoatTechnicalSpecs` never created → offers/detail pages show empty specs.
- **Fix**: renamed parameter to `slugs` (plural). Removed hardcoded `limit: 50`.
- **Impact**: all boats now reliably found by slug. Boats with missing specs get them on next detail/offer view.

### 🐛 Fixed — OOM kill in parse_boats on 1 GB RAM VPS (v2: disposable tasks)
- **Root cause**: v1 (per-page DB flush) still OOM at page 155/1560. Python arena fragmentation from repeated ORM operations in a single long-running Celery task caused RSS to grow beyond 1 GB VPS headroom.
- **Fix — Disposable tasks architecture**: Orchestrator (`run_parse_job`) is now lightweight — collects slugs EN-only (~11 MB for 28k boats). No multilingual fetches, no DB writes, no ThreadPoolExecutor during collection. gc.collect() every 50 pages.
- **New task `process_api_page_range`**: Handles ~20 API pages each. Fetches 5 languages via ThreadPoolExecutor(max_workers=3), calls `_update_api_metadata()` per page with gc.collect, then exits. Worker process recycled by `--max-tasks-per-child=100`.
- **`run_parse_job`**: Dispatches `process_api_page_range` tasks (for mode=api/full, ~80 tasks for full catalog) and/or `process_html_batch` tasks (for mode=html/full) via chord → finalize.
- **`process_api_batch`**: Kept for backward compatibility but no longer dispatched by orchestrator.

## [0.8.1-dev] - 2026-04-07

### 🔧 Refactor — PEP 8 compliance (835 → 0 violations)
- **Phase 1 — Auto whitespace cleanup (646 fixes)**: W291 trailing whitespace, W293 whitespace in blank lines, W391 blank line at EOF, E302/E303/E305/E306 expected blank lines, E231/E226/E261 spacing. All 18 core `.py` files.
- **Phase 2 — Manual fixes (122 fixes)**:
  - **F401** (21): removed unused imports across 7 files (`settings.py`, `contract_generator.py`, `forms.py`, `views.py`, `tasks.py`, `boataround_api.py`, `models.py`).
  - **F541** (33): replaced empty f-strings with plain strings across 6 files + management commands.
  - **E722** (12): replaced bare `except:` with specific `except (ValueError, TypeError):` or `except Exception:` in `boataround_api.py`.
  - **F821** (1): undefined `User` in `views.py` → added local `AuthUser` import.
  - **F811** (3): removed redundant re-imports of `Decimal` and `BoatDescription`.
  - **F841** (2): removed unused `as e` / `as exc` captures.
  - **E741** (1): renamed ambiguous `l` → `lang` in list comprehension.
  - **E127/E128** (3): fixed continuation line indentation.
  - **E225** (1): added missing whitespace around operator.
- **Phase 3 — Long lines E501 (67 fixes)**: line-wrapped all lines >120 chars using idiomatic Python patterns (implicit line continuation, parenthesized expressions, multi-line string concatenation). Files: `settings.py`, `admin.py`, `boataround_api.py`, `contract_generator.py`, `forms.py`, `helpers.py`, `models.py`, `parser.py`, `tasks.py`, `views.py`.
- **Validation**: `flake8 --max-line-length=120` reports **0 violations** across all 18 files. `manage.py check` — 0 issues. Full Docker rebuild successful.

## [0.8.0-dev] - 2026-04-07

### ✨ Added — Granular permission methods (Phase 2)
- **6 new permissions**: `view_price_breakdown`, `assign_managers`, `delete_bookings`, `delete_offers`, `create_contracts`, `view_all_clients`.
- **6 new `can_*()` methods** on `UserProfile`: `can_view_price_breakdown()`, `can_assign_managers()`, `can_delete_bookings()`, `can_delete_offers()`, `can_create_contracts()`, `can_view_all_clients()`.
- **Migration `0008_add_granular_permissions.py`**: creates permissions and assigns to roles (captain → `create_contracts`; assistant → `create_contracts`, `view_all_clients`; manager → `view_price_breakdown`, `delete_bookings`, `create_contracts`, `view_all_clients`; admin → all + `assign_managers`, `delete_offers`; superadmin → all).

### 🔧 Fixed — Eliminated ALL hardcoded role checks
- **25+ locations in `boats/views.py`**: replaced `profile.role == '...'` / `profile.role in (...)` with `can_*()` and `is_*` permission methods.
- **8 locations in templates**: `base.html`, `lk_sidebar.html`, `profile.html`, `my_bookings.html` — replaced 5-role OR chains with `not is_tourist`, `role == 'captain'` with `is_captain`.

### 🔧 Fixed — Access control bugs
- **`delete_booking`**: superadmin was excluded from deletion — now uses `can_delete_bookings()` (includes superadmin).
- **`offers_stats_api` / `offers_list_api` / `offers_list`**: only admin could see all offers — now uses `can_see_all_bookings()` (includes manager, superadmin).
- **`book_offer`**: only manager could book from offers — now uses `can_see_all_bookings()` (includes admin, superadmin).
- **`delete_offer`**: only admin could delete — now uses `can_delete_offers()` (includes superadmin).
- **`clients_list` / `client_detail` / `client_edit` / `client_search_api`**: admin was excluded from viewing all clients — now uses `can_view_all_clients()`.

## [0.7.2-dev] - 2026-04-07

### 🔧 Fixed — Force refresh in offer creation ignored
- **`create_offer`**: `force_refresh` checkbox was sent from frontend but backend ignored it. Now reads `force_refresh` from POST and passes `force_refresh=True` to `_ensure_boat_data_for_critical_flow` — triggers full re-parse (API + HTML) instead of returning cached data.

## [0.7.1-dev] - 2026-04-07

### 🔒 Fixed — Price breakdown visible to captain
- **`my_bookings` price debug**: removed `'captain'` from `show_price_debug` role list. Price breakdown (API price, discounts, charter/agent commissions, adjustments) is now visible **only** to `manager`, `admin`, `superadmin`. Captain sees total price only.

## [0.7.0-dev] - 2026-04-07

### ✨ Added — Booking option status + in-app notifications
- **Booking `option` status**: new `option` in `Booking.STATUS_CHOICES` + `option_until` DateField for option expiry date.
- **Notification model**: `boats/models.py` — `Notification(recipient, booking, message, is_read, created_at)` with indexes on `(recipient, -created_at)` and `(recipient, is_read)`.
- **Notification views**: `notifications_list`, `notification_mark_read`, `notifications_mark_all_read` — 3 new URL patterns in `boats/urls.py`.
- **Context processor**: `boats/context_processors.py` — provides `unread_notifications_count` globally for bell badge.
- **Bell icon**: navbar (desktop + mobile dropdown) + sidebar with unread count badge.
- **`update_booking_status`**: rewritten — `role != 'manager'` → `can_confirm_booking()`. Option action with date validation. All actions dispatch in-app + Telegram notifications.
- **Migration**: `0034_booking_option_until_alter_booking_status_and_more.py`.

### ✨ Added — Telegram notifications
- **`boats/telegram.py`** (NEW): raw Telegram Bot API via `requests.post`, fail-silent.
- **Celery task `send_telegram_notification`**: `boats/tasks.py` — `max_retries=2`, `countdown=30`. Only retries on exceptions (not on `False` return).
- **Settings**: `TELEGRAM_BOT_TOKEN` + `TELEGRAM_ASSISTANT_CHAT_ID` via decouple (reads `TELEGRAM_CHAT_ID` from `.env`).
- **`boats/notifications.py`** (NEW): centralized `notify_new_booking()` and `notify_status_change()` — dispatches both in-app `Notification.objects.bulk_create()` and Telegram via Celery task.
- Notifications sent from 3 booking creation points (`create_booking`, `book_offer`, `book_boat`) and 3 status change actions (confirm/option/cancel).

### 🔧 Fixed — Contract signing download 404
- **`LOGIN_URL`**: changed from `'/login/'` to `'login'` (named URL) — Django resolves with proper i18n prefix.
- **`download_signed_contract`** (NEW view): token-based PDF download at `contracts/<uuid>/sign/<sign_token>/download/` — no auth required, validates `sign_token` + `status='signed'`.
- **`contract_signed.html`**: link updated to use `download_signed_contract` instead of auth-protected `download_contract`.

### 🔧 Fixed — PDF download crash
- **`download_contract`**: replaced `FileResponse(contract.document_file.open('rb'))` with `HttpResponse(contract.document_file.read())` — atomic response instead of streaming that crashed browsers.

### 🔧 Fixed — Permission-based access
- **`assign_booking_manager`**: `role not in ('manager', 'superadmin')` → `can_see_all_bookings()`.
- **`my_bookings.html`**: hardcoded role names → `can_access_admin_panel` / `can_see_all_bookings` checks.

### 🧹 Changed
- **Admin**: `NotificationAdmin` registered, `BookingAdmin` shows `option_until`.
- **`check_data_status`**: added `option` status to bookings stats.
- **Template updates**: `my_bookings.html` (option badges, Alpine.js date picker, stats grid), `base.html` (bell), `lk_sidebar.html` (notifications link), various lists (permission-based visibility).

## [0.6.0-dev] - 2026-04-06

### ✨ Added — Permission-based role system
- **Permission + Role models**: `accounts/models.py` — `Permission(codename, name)` + `Role(codename, name, permissions M2M, is_system)`. 14 permissions, 6 system roles (tourist, captain, assistant, manager, admin, superadmin).
- **New role «Ассистент»**: подтверждение бронирований, уведомление капитанов, просмотр всех бронирований и капитанских офферов.
- **`UserProfile.role_ref`**: FK → Role. Свойство `role` (property) возвращает `role_ref.codename` — полная обратная совместимость с `profile.role == 'captain'`.
- **`can_*()` → `has_perm(codename)`**: все 15 permission-методов делегируют в `has_perm()` с кэшем `_perm_cache`.
- **Admin**: PermissionAdmin (readonly), RoleAdmin (filter_horizontal), updated UserProfileAdmin.
- **3-step migration**: 0005 (schema), 0006 (data populate), 0007 (remove old CharField).

### 🔧 Fixed — Role check hardcodes & ORM compatibility
- **28 hardcoded role checks → `can_*()` methods**: offers, contracts, clients, bookings — assistant/manager/admin access corrected.
- **ORM FieldError**: `profile__role='manager'` → `profile__role_ref__codename='manager'` (2 locations in views.py).
- **`my_bookings`**: `role in ('manager', 'superadmin')` → `can_see_all_bookings()`.
- **`accounts/views.py`**: `can_manage_boats`/`can_create_offers` called as properties → methods with `()`.
- **`check_data_status`**: `.values_list('role')` → `.values_list('role_ref__codename')`.
- **`additional_services` guard**: `if details else []` prevents AttributeError when BoatDetails is None.
- **`flexible_cancellation` underscore variant**: added to `HIDDEN_SERVICE_SLUGS` set (DB has underscore, not hyphen).
- **`extra_discount_max` fallback**: `5` → `0.0` (fail-closed when PriceSettings unavailable).

### 🧹 Refactored — Cleanup
- **Removed dead constants**: `INSURANCE_RATE`, `COOK_PRICE`, `TURKEY_NAMES`, etc. from `helpers.py` (moved to `PriceSettings`/`CountryPriceConfig` earlier).
- **`print()` → `logger`**: autocomplete_api, _build_price_debug, my_bookings price debug.
- **`pass` → `logger.exception()`**: silent exception swallowing replaced with proper logging.

### 🧪 Tests
- **test_boataround_api**: assertions updated for consensus-based `get_price` (5×3 retry matrix) and additive pricing model (850 not 855).
- **test_price_settings, test_views, test_boat_detail_api, test_pricing**: adapted for `role_ref` FK.
- **test_check_data_status_command**: new test file for `check_data_status` command.

## [0.5.4-dev] - 2026-04-06

### 🔧 Fixed — dump/load commands
- **`load_parsed_boats` directory support**: принимает путь к директории — загружает все `.json` файлы в отсортированном порядке. Раньше падало с `IsADirectoryError`.
- **SQL injection fix**: `_reset_sequences` использовал f-string для таблиц/sequences — заменён на параметризованные запросы + `quote_name()`.
- **`dump_parsed_boats`**: упрощена подсказка загрузки (одна команда вместо per-file), `docker-compose` → `docker compose`.
- **`how_to.md`**: обновлён с актуальными командами.

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
