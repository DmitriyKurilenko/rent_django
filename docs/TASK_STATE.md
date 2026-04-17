# TASK STATE

Last updated: 2026-04-17 (Europe/Moscow)

## Current priorities

### P1.9: --skip-fresh flag + finalize_parse_job finished_at fix
- Status: **DONE (2026-04-15)**
- Feature: `--skip-fresh [HOURS]` пропускает лодки, успешно пропарсенные менее N часов назад.
- Bug fix: `finalize_parse_job` затирал `finished_at` через `refresh_from_db()`. Переставлен порядок.
- Files: `boats/management/commands/parse_boats.py`, `boats/tasks.py`.

### P1.8: HTML parser not updating last_parsed / last_parse_success
- Status: **DONE (2026-04-15)**
- Bug: `parse_boataround_url()` never set `last_parsed` or `last_parse_success` on ParsedBoat.
- Fix: Added both fields to the save flow in parser.py (success + failure paths).
- Files: `boats/parser.py`.

### P1.7: All parsing through Celery (--workers N → Celery task)
- Status: **DONE (2026-04-15)**
- Removed `--local` flag. `--workers N` now dispatches `run_parse_workers` Celery task.
- `--retry-errors` reads from `ParseJob.errors` in DB (no more file-based tracking).
- Live progress bar via ParseJob polling (Ctrl+C doesn't kill task).
- Files: `boats/tasks.py`, `boats/management/commands/parse_boats.py`.

### P1.6: --retry-errors for local parse
- Status: **DONE (2026-04-15), superseded by P1.7**
- Originally file-based, now DB-based via ParseJob.errors.

### P1.5: Local parallel parsing mode
- Status: **DONE (2026-04-14), superseded by P1.7**
- `parse_boats --local --workers N` — ThreadPoolExecutor-based parallel parsing without Celery.
- All 3 modes (api/html/full), live progress bar, auto-defaults workers to `cpu_count*2`.
- Files: `boats/management/commands/parse_boats.py`.

### P1.4: Amenities lost after parsing (cockpit/entertainment/equipment)
- Status: **DONE (2026-04-14)**
- Root cause: DR-041 changes incorrectly made `services_only` skip amenities and `mode=api` clear them. Both violated the IRON RULE (HTML owns amenities).
- Fix: Amenities saved in both `services_only` and `all_html` modes. API mode no longer touches BoatDetails amenity fields.
- Files: `boats/parser.py`, `boats/tasks.py`, `boats/tests/test_parser_persistence.py`, `boats/tests/test_parse_boats_api_mode.py`.

### P1.3: Parse mode boundaries (API vs HTML) to stop source-of-truth confusion
- Status: **DONE (2026-04-14), corrected by P1.4**
- `parse_boats` modes now have strict semantics:
  - `api`: API source-of-truth only. Does NOT touch HTML-owned fields (amenities).
  - `html`: photos + extras/additional_services/delivery_extras/not_included + cockpit/entertainment/equipment from HTML.
  - `full`: full HTML profile (legacy full HTML mode) — also saves descriptions.
- `parse_boataround_url` now receives explicit `html_mode`; task entry points pass mode intentionally.
- `run_parse_job` now dispatches API tasks only for `mode=api`; `mode=full` no longer mixes API stage.
- `refresh_amenities` command/tasks are deprecated to prevent accidental HTML amenities writes in API-first flows.
- Files: `boats/parser.py`, `boats/tasks.py`, `boats/management/commands/parse_boats.py`, `boats/models.py`, `boats/management/commands/refresh_amenities.py`.

### P1.2: Countdown timer missing in public offer view
- Status: **DONE (2026-04-13)**
- `offer_view` (public link `/offer/<uuid>/`) passed `show_countdown` but not `countdown_end_iso` — timer never rendered.
- Added same countdown calculation logic as `offer_detail`.
- Files: `boats/views.py`.

### P1.2b: OOM kill in Celery page-range tasks (v4)
- Status: **DONE (2026-04-13)**
- Worker SIGKILL at Job:30 on 1 GB VPS. Reduced `PAGES_PER_RANGE` 5→3, `--max-tasks-per-child` 100→20, added `db.reset_queries()` + `gc.collect()` cleanup.
- Files: `boats/tasks.py`, `docker-compose.prod.yml`.

### P1.1: Strip charter company name from boat descriptions
- Status: **DONE (2026-04-12)**
- Charter company mention (last sentence of every boat description) removed at presentation layer via template filter `strip_charter_company`.
- Covers all 5 languages (EN, RU, DE, ES, FR) and all boat types (yacht, motorboat, catamaran, gulet, houseboat).
- 17 regex patterns handle language-specific sentence structures.
- Tested on 1500+ real descriptions (300/language), 0 leaks.
- Files: `boats/templatetags/boat_filters.py`, `templates/boats/detail.html`.

### P1.0: Full DaisyUI 5 migration — all templates
- Status: **DONE (2026-04-12)**
- Phase 1: Auth forms (login, register) rewritten from legacy DaisyUI v4 patterns.
- Phase 2: All remaining 11 templates migrated. Eliminated every `form-control`, `label-text`, `label-text-alt`, and `class="label"` (as form label) across the entire codebase.
- CSS compat shims (`@utility form-control/label-text/label-text-alt`) removed from `assets/css/tailwind.input.css`.
- Pattern: `<div>` field wrappers, `text-sm font-semibold` labels, `input w-full`/`select w-full` inputs, `text-xs text-error` errors, `cursor-pointer flex items-center gap-2` checkbox labels.
- Files: `templates/accounts/login.html`, `templates/accounts/register.html`, `templates/accounts/profile.html`, `templates/accounts/price_settings.html`, `templates/boats/home.html`, `templates/boats/search.html`, `templates/boats/detail.html`, `templates/boats/offers_list.html`, `templates/boats/my_bookings.html`, `templates/boats/create_offer.html`, `templates/boats/create_contract.html`, `templates/boats/contract_sign.html`, `templates/boats/client_form.html`, `assets/css/tailwind.input.css`.

### P0.9: Commission display on offer page & offers list
- Status: **DONE (2026-04-12)**
- Captain sees agent commission on offer detail page (inside price card) and in offers list table.
- Manager/admin sees full breakdown (charter % + amount + agent commission + charter name).
- Tourist/anonymous sees nothing — commission block hidden entirely.
- Files: `boats/views.py`, `templates/boats/offer_captain.html`, `templates/boats/offers_list.html`.

### P0.8: Quick offer modal — countdown & force-refresh flags
- Status: **DONE (2026-04-11)**
- Added "Обратный отсчёт" and "Обновить данные" checkboxes to quick offer creation modals on boat detail page.
- Permission-based visibility: countdown for captain/assistant/manager/admin, force-refresh for assistant/manager/admin.
- New migration 0009, new permissions `use_countdown`/`use_force_refresh`, new methods `can_use_countdown()`/`can_use_force_refresh()`.
- Backend `quick_create_offer` view reads and applies both flags with permission enforcement.
- Files: `accounts/models.py`, `accounts/migrations/0009_add_countdown_refresh_permissions.py`, `boats/views.py`, `templates/boats/detail.html`.

### P0.7: Comprehensive search filters from Boataround API
- Status: **DONE (2026-04-10) — Testing complete**
- Added 11 new search filters: maxSleeps, allowedPeople, boatLength, manufacturer, skipper, sail, engineType, cockpit, entertainment, equipment, toilets.
- Fixed category values (sailboat→sailing-yacht, etc.), added gulet + power-catamaran.
- Expanded sort options: reviewsDown, dealsFirst.
- Collapsible amenity sections with checkbox persistence across page loads.
- Bug fixes from deep testing: checkbox substring matching → list check, manufacturer case-sensitivity → .lower(), duplicate @staticmethod removed.
- Files: `boats/boataround_api.py`, `boats/views.py`, `templates/boats/search.html`, `boats/templatetags/boat_filters.py`.

### P0.6: search_by_slug wrong API parameter → missing specs in offers
- Status: **DONE (2026-04-08)**
- `search_by_slug()` sent `slug` (singular) — API ignores it, returns 50 default boats. Target boat not found → no `BoatTechnicalSpecs` → offers/detail show empty specs.
- Fix: parameter `slug` → `slugs` (plural). One-line change in `boats/boataround_api.py`.
- See DR-035, KI-010.

### P0.4: parse_boats OOM kill during slug collection
- Status: **DONE (2026-04-09, v3)**
- v2 (disposable tasks, 20 pages/task) still OOM at Job:16 on 1 GB VPS. Also `totalPages` inflated 2× due to `len(boats)` vs `limit` in API pagination.
- Fix (v3): `PAGES_PER_RANGE: 20 → 5` (4× lighter per task). Fixed `totalPages` calculation in `boataround_api.py`. Added `batches_done` counter + `del results` in page-range task.
- See DR-034.

### P0.3: PEP 8 compliance
- Status: **DONE (2026-04-07)**
- Full flake8 audit: 835 violations found across 18 core `.py` files (max-line-length=120).
- Phase 1: auto whitespace cleanup (646 fixes via autopep8).
- Phase 2: manual fixes — unused imports (21), empty f-strings (33), bare except (12), undefined names (1), redefined imports (3), unused vars (2), ambiguous names (1), indentation (3), spacing (1).
- Phase 3: long line wrapping (67 E501 fixes).
- Result: **0 violations** across all 18 files. `manage.py check` — 0 issues.

### P0.1: Price breakdown visibility leak to captain
- Status: **DONE (2026-04-07)**
- `show_price_debug` in `my_bookings` had `'captain'` in role list — captains saw full breakdown.
- Fixed: removed `'captain'`, now only `manager`/`admin`/`superadmin`.

### P0.2: Force refresh ignored in offer creation
- Status: **DONE (2026-04-07)**
- "Обновить данные" checkbox sent `force_refresh` but backend never read it.
- Fixed: `_ensure_boat_data_for_critical_flow` now accepts `force_refresh=True` to skip cache.

### P0: Pricing consistency across search/detail/offers
- Status: **RESOLVED (2026-04-02)** — cache-first lookup in `get_price()` eliminates price jitter symptom for users.

### P0.5: Permission-based role system
- Status: **DONE (2026-04-06, extended 2026-04-07)** — Permission + Role models, 3-step migration, all `can_*()` delegate to `has_perm()`.
- Full audit completed: 28 hardcoded role checks found, 15 CRITICAL fixed. All views now use `can_*()` methods.
- ORM compatibility fixes: `profile__role` → `profile__role_ref__codename`, `check_data_status` values_list, `additional_services` guard.
- **Phase 2 (2026-04-07):** 6 new granular permissions added (`view_price_breakdown`, `assign_managers`, `delete_bookings`, `delete_offers`, `create_contracts`, `view_all_clients`). Migration 0008. Replaced all remaining 22+ hardcoded role checks in views.py + 8 in templates.
- Bugs fixed: `delete_booking` now includes superadmin; offers visibility expanded to manager+superadmin; `book_offer` expanded to admin+superadmin; `delete_offer` expanded to superadmin; client views expanded to admin.
- All 120 tests pass.

### P1.5: Booking option status + notifications for assistant
- Status: **DONE (2026-04-06)**
- Booking model: added `option` status + `option_until` DateField.
- Assistant can set bookings to "На опции" (with expiry date), confirm, or cancel.
- Notification model: sends notifications to booking creator on status changes.
- Bell icon in navbar + sidebar with unread count badge.
- Notifications page with mark-read/mark-all-read.
- All 120 tests pass.

### P1.6: Telegram notifications for assistant
- Status: **DONE**
- Sends Telegram messages to assistant on new booking creation (3 entry points) and status changes (confirm/option/cancel).
- Uses raw Telegram Bot API via `requests` (no new dependencies).
- Async via Celery task `send_telegram_notification` (2 retries, 30s backoff).
- Config: `TELEGRAM_BOT_TOKEN` + `TELEGRAM_ASSISTANT_CHAT_ID` env vars. Fails silently when not configured.

### P1.7: Contract signing download 404
- Status: **DONE (2026-04-07)**
- `LOGIN_URL` was `/login/` — didn't match i18n routes. Fixed to named URL `'login'`.
- Added `download_signed_contract` — token-based PDF download for signers (no auth required).
- Template `contract_signed.html` updated to use token-based URL.

### P1.8: PDF download crash
- Status: **DONE (2026-04-07)**
- `FileResponse` with streaming from FieldFile crashed browsers. Replaced with `HttpResponse` + `.read()`.

### P1.9: Notifications refactored to boats/notifications.py
- Status: **DONE (2026-04-07)**
- Centralized `notify_new_booking()` and `notify_status_change()`. Views call one-liner functions.
- Goal: one pricing pipeline and predictable user-visible price per request context.
- Scope:
  - search cards,
  - boat detail page,
  - offer creation/list/detail,
  - direct booking flows.
- Final solution: `BoataroundAPI.get_price()` checks 6-hour Redis cache before consensus loop; detail page price now stable within cache window. Legacy KI-001 (upstream jitter) is mitigated, not eliminated (5-request consensus loop still runs on cache miss).

### P1: Amenities refresh command reliability
- Status: in progress.
- Goal: `refresh_amenities` must reliably update cockpit/entertainment/equipment for selected boats, including `--async --destination`.
- Scope:
  - slug selection by destination via API,
  - async batch dispatch/wait/summary,
  - sync fallback mode.

### P2: Search card UI height parity with preview image
- Status: implemented in template/tests, monitor regressions.
- Goal: card content fits without exceeding preview height on desktop breakpoint.

## What is done (high-value)
- Unified pricing resolver is used in detail, offers, booking.
- Price extraction prefers `policies[0].prices` to avoid unstable top-level fields.
- Search -> detail links keep only dates in query string (`check_in`, `check_out`), price params removed.
- Search/detail price breakdown is now role-scoped: full breakdown for manager/admin/superadmin, charter commission only for captain.
- Added `update_charters` management command: scans API and assigns Charter FK to ParsedBoat records missing charter. Supports `--destination`, `--max-pages`, `--all`, `--dry-run`.
- Detail page price breakdown colors fixed: replaced DaisyUI semantic colors (text-secondary/text-info/text-success) with Tailwind direct colors (text-amber-200/text-yellow-200/text-green-200) for readability on purple gradient background. Font size increased from 11px to 13px.
- Destination-based amenities refresh selection now deduplicates and intersects with existing slugs in DB.
- Async amenities command now verifies active Celery worker and can wait with timeout/poll summary.
- Tests added for pricing extraction/resolver, detail snapshot behavior, amenities command async behavior.
- Added `import_charter_commissions` management command to import charter commissions from `.xlsx` by charter name normalization (including `d.o.o.` suffix stripping), with CSV audit outputs (`loaded` / `not_loaded`).
- **Major stack upgrade completed (2026-03-27):** Python 3.13, Django 5.2.12 LTS, Tailwind 4.2.2, DaisyUI 5.5.19, Node 22, all Python packages to latest. Validated: manage.py check, migrations, HTTP pages, CSS, Celery.
- **Dynamic country pricing (2026-03-28):** Replaced hardcoded 3-region pricing (55 fields on PriceSettings) with `CountryPriceConfig` model (FK, 15 fields per country). Admin can add/edit/delete countries from price settings UI. Migration 0030 seeds Turkey/Seychelles/Default. Templates and pricing logic fully dynamic.
- **Hidden service slugs (2026-04-04):** "Гибкая отмена" (flexible-cancellation) filtered from all UI via `HIDDEN_SERVICE_SLUGS` in helpers.py + view/template guards. DR-028.
- **Full documentation audit (2026-04-04):** README.md rewritten, 7 obsolete docs archived, CONTRIBUTING.md/SECURITY.md deleted, version/command/link fixes across 15+ files.

## Open risks / watch items
- Upstream Boataround API may return different `totalPrice` for identical query windows.
- Search “consensus” anti-jitter behavior can still show a new candidate early when no confirmed baseline exists.
- Network timeouts on price endpoint remain possible in production (fallback path must stay healthy).
- ~10k boats still without Charter FK — `update_charters` crashed on page 806/1471 due to DNS error. Command now has retry logic (5 attempts + skip on failure). Needs re-run.

### P7: Celery-batched parse_boats command
- Status: **refactored** (2026-04-04). Slug collection: single-pass all 5 languages, incremental JSON cache (saves every page, resumes from partial), no TTL (reset via `--no-cache`), concurrent lang fetch (4 threads), 1 empty page = stop. Lang meta passed to batches from orchestrator.
- Goal: unified management command for all parsing modes (API metadata, HTML parsing, combined) with Celery batch dispatch, progress tracking, and persistent reports.
- Scope:
  - `ParseJob` model for job state/counters/reports,
  - `parse_boats` management command with `--mode api|html|full`, `--destination`, `--max-pages`, `--batch-size`, `--skip-existing`, `--status`, `--no-cache`,
  - Celery tasks: `run_parse_job` (orchestrator), `process_api_batch`, `process_html_batch` (workers),
  - Incremental slug cache in `.parse_cache/` — saves after every page, resumes on restart,
  - Django admin with colored status, progress, duration columns,
  - Old commands (`parse_boats_parallel`) untouched.

### P3: Online contract signing
- Status: implemented, ready for testing.
- Goal: agents can create, send, and collect electronic signatures on rental contracts from clients.
- Scope:
  - ContractTemplate + Contract models,
  - PDF generation via xhtml2pdf (HTML→PDF),
  - Canvas signature drawing (Alpine.js),
  - UUID-based public signing links (no auth required for signer),
  - SHA-256 document hash + audit logging (IP, User-Agent, timestamp),
  - Celery async PDF generation task,
  - Email notification stub (not wired yet),
  - Integration with my_bookings and base nav.

### P4: Client (tourist) management
- Status: implemented, Docker-validated.
- Goal: agents/captains can create client profiles and link them to bookings, offers, contracts.
- Scope:
  - Client model (FIO, contacts, passport, notes),
  - FK relations to Booking, Offer, Contract (nullable),
  - CRUD views + JSON search API for autocomplete,
  - Alpine.js clientSelector component in create_offer and quick_create_offer,
  - Client auto-propagation: offer→booking→contract,
  - Contract pre-fill from client passport/address data,
  - Client info card on captain offer template,
  - Sidebar nav in bookings, contracts, clients list pages,
  - Django admin registration with fieldsets.

## Pending product decisions from user
- Canonical policy when upstream API returns two different totals for same query:
  - show freshest,
  - show conservative (higher/lower),
  - or apply multi-sample quorum before display.

### P5: Source-of-truth split (HTML vs API)
- Status: **implemented, production-validated** (2026-04-02).
- Goal: keep HTML only for service lists and photos; all other fields from API.
- Scope:
  - HTML writes: `extras`, `additional_services`, `delivery_extras`, `not_included`, `BoatGallery` photos, plus `cockpit` / `entertainment` / `equipment` (per-boat amenities).
  - API writes: `ParsedBoat` metadata, `BoatDescription`, `BoatTechnicalSpecs`, `Charter` linkage/rank fields.
  - API updater creates missing `BoatDescription` and `BoatTechnicalSpecs` records for newly parsed boats.
  - **Detail/offer flow**: `_ensure_boat_data_for_critical_flow` runs API metadata first, then HTML parsing (DR-023). No split modes outside management commands.
  - Management commands (`parse_boats`) support separate modes (api/html/full) for batch operations.
  - Cache payload stores `api_meta` and `thumb_map`, so cache-hit runs still execute complete Phase 1.5 metadata hydration.

### P6: Geo-data localization integrity
- Status: in progress (logic fixed, backfill ongoing).
- Goal: non-English `BoatDescription` (`ru_RU/de_DE/fr_FR/es_ES`) must be populated only from same-language API payload.
- Scope:
  - Remove cross-language fallback that copied `en_EN` geo labels into other languages.
  - Keep English fallback only for `en_EN` records.
  - Run destination-scoped metadata backfill to correct stale historical rows.
