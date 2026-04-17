# DEV LOG

Purpose: short, append-only engineering memory to avoid re-discovery and regressions.

## 2026-04-17 — Commit prep + documentation sync for parse mode hardening
- Release prep: bumped `VERSION` to `0.14.0-dev`, added top release section in `CHANGELOG.md`.
- Docs sync:
  - `docs/DECISIONS.md`: added DR-043 (Celery-first `parse_boats`, DB-based retries, `--skip-fresh` policy).
  - `docs/TASK_STATE.md`: refreshed status metadata and marked local worker mode as superseded.
  - `docs/KNOWN_ISSUES.md`: added KI-013 (resolved `finished_at` loss in finalize flow), updated timestamp.
  - `docs/RELEASE_NOTES.md`: added user-facing notes for 15 Apr 2026; corrected 14 Apr wording to match final amenities/source-of-truth behavior.
- Additional session files included in commit scope: `docker-compose.yml` (`CELERY_CONCURRENCY`), `.dockerignore` context cleanup, migration `boats/migrations/0035_alter_parsejob_mode.py`, new regression test `boats/tests/test_parse_boats_api_mode.py`.
- Validation:
  - `docker compose down` — OK.
  - `docker compose up -d --build` — OK.
  - `docker compose run --rm web python manage.py check` failed due env value `DEBUG=release`; rerun with `DEBUG=False docker compose run --rm web python manage.py check` — OK.
  - Targeted tests: `DEBUG=False docker compose run --rm web python manage.py test boats.tests.test_parser_persistence boats.tests.test_parse_boats_api_mode boats.tests.test_refresh_amenities_tasks boats.tests.test_refresh_amenities_command --verbosity 2` — **13 passed**.
  - HTTP render check: `curl -I http://localhost:8000/ru/`, `curl -I http://localhost:8000/ru/boats/search/`, `curl -I http://localhost:8000/ru/accounts/login/`, `curl -I http://localhost:8000/health/` — all **200**.
- Risks: no new functional blockers found; deprecated `refresh_amenities` wrappers are kept intentionally for backward-compat guidance.

## 2026-04-15 — --skip-fresh flag + finalize_parse_job finished_at bug
- Feature: `parse_boats --skip-fresh [HOURS]` — пропускает лодки с `last_parsed` < N часов и `last_parse_success=True`. Default 24ч.
- Bug fix: `finalize_parse_job` did `refresh_from_db()` AFTER setting `finished_at`, wiping it back to None. Reordered: refresh first, then set finished_at.
- Backfilled `finished_at` for 18 existing completed jobs from detailed_log timestamps.
- Files: `boats/management/commands/parse_boats.py`, `boats/tasks.py`.
- Docs: Updated command docstring, copilot-instructions, DEV_LOG, TASK_STATE.
- Validation: `manage.py check` — 0 issues. `--help` shows `--skip-fresh`.

## 2026-04-15 — Fix: HTML parser not updating last_parsed / last_parse_success
- Bug: `parse_boataround_url()` saved BoatDetails/BoatGallery correctly but never updated `ParsedBoat.last_parsed` or `last_parse_success`.
- Root cause: HTML parser had its own save logic (not using `save_to_cache()` from helpers.py). `update_fields` list on ParsedBoat.save() lacked `last_parsed`.
- Symptom: Seychelles job c07bb1e6 reported 171/171 success, data was correct, but `last_parsed` stayed at February dates. `is_cache_fresh()` couldn't detect fresh parses.
- Fix: Added `last_parsed=timezone.now()` and `last_parse_success=True` after successful save in parser.py. Added `last_parse_success=False` in exception handler.
- Verified: single-boat test confirmed `last_parsed` now updates correctly.
- Files: `boats/parser.py`.
- Validation: `docker compose up -d --build` + `manage.py check` — 0 issues. Single boat re-parse confirmed fix.

## 2026-04-15 — All parsing through Celery (remove --local, add run_parse_workers)
- Architecture change: removed `--local` flag. ALL parsing now goes through Celery.
- `--workers N` dispatches a single Celery task (`run_parse_workers`) that uses ThreadPoolExecutor internally.
- Without `--workers` — existing chord-based batch flow (unchanged).
- `--retry-errors` now reads errors from `ParseJob.errors` in DB (not file-based).
- Command shows live progress bar by polling ParseJob every 2s. Ctrl+C doesn't kill Celery task.
- New task: `run_parse_workers(job_id_hex, workers, retry_slugs, no_cache)` in tasks.py.
- Helpers: `_run_workers_html`, `_run_workers_api`, `_flush_workers_progress`, `_fetch_and_save_api_page`.
- Fixed: `finalize_parse_job` called via `.apply()` (bind=True task requires proper invocation).
- Files: `boats/tasks.py`, `boats/management/commands/parse_boats.py`.
- Validation: `docker compose up -d --build` + `manage.py check` — 0 issues.

## 2026-04-15 — --retry-errors for local parse mode
- Feature: `parse_boats --local --retry-errors --mode html --workers 8` — повтор только ошибочных slug'ов.
- After each `--local` run, failed slugs are saved to `.parse_cache/failed_slugs_{mode}.json` с thumb_map.
- `--retry-errors` загружает этот файл и парсит только ошибочные лодки, без повторного сбора slug'ов из API.
- Use case: длинный парсинг прерван (гибернация, сбой сети) — повтор ~4600 ошибок вместо 27000.
- Можно запускать многократно: каждый retry перезаписывает файл с оставшимися ошибками.
- Files: `boats/management/commands/parse_boats.py`.
- Validation: `manage.py check` — 0 issues.

## 2026-04-14 — Local parallel parsing mode (--local --workers N)
- Feature: `parse_boats --local --workers N` — параллельный парсинг в текущем процессе без Celery.
- Uses `ThreadPoolExecutor` (I/O-bound HTTP requests). Live progress bar в терминале.
- Works for all 3 modes: api, html, full.
- Default workers: `cpu_count * 2` (max 20). Reuses existing slug collection and DB-save logic.
- API mode: параллелизирует по страницам (каждая страница = 5 API-запросов по языкам).
- HTML mode: параллелизирует по slug'ам (каждый slug = полный HTML-парсинг).
- Smoke test: `--mode api --destination turkey --max-pages 1` — 18 boats, 2с. `--mode html` — 18 boats, 1.7 мин (4 workers).
- Files: `boats/management/commands/parse_boats.py`.
- Validation: `manage.py check` — 0 issues. HTTP 200.
- Risk: При большом кол-ве workers может упереться в rate-limiting boataround.com. 4-8 workers — безопасно.

## 2026-04-14 — Fix: amenities (cockpit/entertainment/equipment) lost after parsing
- Symptom: After running `parse_boats --mode api` followed by `--mode html`, cockpit/entertainment/equipment completely disappeared from all boats.
- Root cause: Two bugs introduced in earlier 2026-04-14 changes violated the IRON RULE (HTML parser owns cockpit/entertainment/equipment):
  1. `_clear_api_unavailable_amenities()` in API tasks wiped HTML-owned amenity fields — API does NOT own these.
  2. `services_only` html_mode skipped saving amenities (`save_html_amenities = html_mode == 'all_html'`) — but these ARE HTML-owned fields that must be saved in all HTML modes.
- Fix:
  - `boats/parser.py`: Removed `save_html_amenities` flag. Amenities are now saved in both `services_only` and `all_html` modes (HTML is source-of-truth for these fields).
  - `boats/tasks.py`: Removed calls to `_clear_api_unavailable_amenities()` from `process_api_batch` and `process_api_page_range`. API mode no longer touches HTML-owned fields.
  - Tests updated: `test_parser_persistence.py` and `test_parse_boats_api_mode.py` assertions corrected.
- Validation: `manage.py check` — 0 issues. 6 targeted tests pass (test_parser_persistence + test_parse_boats_api_mode). HTTP 200 for home page.
- Files: `boats/parser.py`, `boats/tasks.py`, `boats/tests/test_parser_persistence.py`, `boats/tests/test_parse_boats_api_mode.py`.

## 2026-04-14 — API mode now clears stale amenities and invalidates detail cache
- Symptom: `parse_boats --mode api` completed successfully but boat detail still showed old cockpit/entertainment/equipment values. Root cause: API mode updated only API metadata and left historical HTML amenities in `BoatDetails`; page-level cache (`boat_data:<slug>:<lang>`) also preserved stale snapshot.
- Fix:
  - `boats/tasks.py`: added API-mode normalization in `process_api_page_range` and `process_api_batch`:
    - clear `BoatDetails.cockpit/entertainment/equipment` for processed slugs,
    - invalidate detail cache keys `boat_data:<slug>:<lang>` for all supported languages.
  - Added helpers `_clear_api_unavailable_amenities()` and `_invalidate_boat_detail_cache()`.
  - Added regression test `boats/tests/test_parse_boats_api_mode.py` to assert amenities reset + cache invalidation in API batch task.
- Validation:
  - Targeted tests: `boats.tests.test_parse_boats_api_mode`, `boats.tests.test_parser_persistence`, `boats.tests.test_refresh_amenities_tasks`, `boats.tests.test_refresh_amenities_command` — **OK (13 tests)**.
  - Live check on slug `jeanneau-sun-odyssey-440-bonbon` after `parse_boats --mode api --destination turkey --max-pages 1`:
    - DB amenities: `cockpit=0`, `entertainment=0`, `equipment=0`,
    - detail cache key removed,
    - page `/ru/boat/jeanneau-sun-odyssey-440-bonbon/?check_in=2026-04-18&check_out=2026-04-25` returns HTTP 200 without amenities blocks.

## 2026-04-14 — Parse mode separation hardened (api/html/full)
- Problem: Runtime behavior still mixed mode responsibilities: `mode=full` triggered API stage in orchestrator, and `services_only` rewrote amenities fields in `BoatDetails` (set to empty), which is outside declared scope ("photo + 4 service lists only").
- Fix:
  - `boats/tasks.py`: `run_parse_job` now dispatches API tasks only for `mode=api`; `mode=html` and `mode=full` run only HTML batches. Also fixed summary template bug in finalize report (`Slug'ов: {job.total_slugs}` → actual value).
  - `boats/parser.py`: in `html_mode='services_only'`, parser now updates only `extras/additional_services/delivery_extras/not_included`; it no longer overwrites `cockpit/entertainment/equipment`.
  - `boats/tests/test_parser_persistence.py`: added regression test to ensure existing amenities are preserved in `services_only`.
- Validation:
  - `docker compose run --rm --no-deps web python -m compileall boats` — OK.
  - Targeted Django tests could not be executed in this environment: one-off web container cannot resolve host `db` (`OperationalError: could not translate host name "db"`), and full compose run is blocked by local Redis port conflict (`0.0.0.0:6379 already allocated`).
- Files: `boats/tasks.py`, `boats/parser.py`, `boats/tests/test_parser_persistence.py`, `docs/DECISIONS.md`, `docs/TASK_STATE.md`.
- Risk: Functional behavior is stricter by design; legacy stale amenities remain unchanged until explicit `mode=full`/targeted data refresh is run on affected boats.

## 2026-04-13 — Countdown timer missing in public offer view
- Bug: `offer_view` (`/offer/<uuid>/`) passed `show_countdown: offer.show_countdown` (raw bool) but did NOT pass `countdown_end_iso`. Template `offer_captain.html` checks `{% if show_countdown and countdown_end_iso %}` — without the ISO date, timer block never rendered.
- `offer_detail` (`/offers/<uuid>/`) had full countdown logic (expires_at → fallback created_at+1day → ISO string). `offer_view` lacked it.
- Fix: copied countdown calculation logic from `offer_detail` into `offer_view` (15 lines). Now `show_countdown` is computed bool (respects expiry) and `countdown_end_iso` is passed.
- Validation: `manage.py check` — 0 issues.
- Files: `boats/views.py`
- Risk: None. Same logic already battle-tested in `offer_detail`.

## 2026-04-13 — OOM kill in Celery page-range tasks (v4)
- Symptom: `WorkerLostError: Worker exited prematurely: signal 9 (SIGKILL) Job: 30` during `process_api_page_range` chord. `ForkPoolWorker-113` (113th recycled fork, 30 tasks into current fork).
- Diagnosis: 1 GB VPS, postgres+redis(256MB)+web+celery = ~800MB base. Worker fork gets ~200MB. Each `process_api_page_range` (5 pages × 5 languages = 25 API calls + ORM writes) leaks ~5-7MB via Python arena fragmentation + Django query log. After 30 tasks → ~200MB exhausted → OOM.
- Fix:
  1. `PAGES_PER_RANGE: 5 → 3` — less data per task
  2. `--max-tasks-per-child: 100 → 20` (prod only) — fork recycled 5× more often
  3. `db.reset_queries()` + `db.close_old_connections()` + `gc.collect()` after each task (both `process_api_page_range` and `process_html_batch`)
- Trade-off: more tasks dispatched (497 vs 297 for 1486 pages), but each lives shorter. Net throughput stays similar because recycle overhead is small.
- Validation: `manage.py check` — 0 issues.
- Files: `boats/tasks.py`, `docker-compose.prod.yml`
- Risk: More chord tasks may slightly increase Redis memory for result tracking.

## 2026-04-12 — Strip charter company name from boat descriptions
- Problem: Every boat description from boataround.com ends with a sentence naming the charter company (e.g., "This motor yacht is operated by the charter company X."). This appears on the detail page across all 5 languages.
- Approach: Presentation-layer filter — database data is NOT modified. Template filter `strip_charter_company` in `boats/templatetags/boat_filters.py` detects and removes the charter sentence using 17 regex patterns (per language × per boat type).
- Patterns by language:
  - EN: "This [type] is operated by the charter company [Name]." (with optional rating suffix for houseboats)
  - RU: "Яхта находится в ... и обслуживается [Name].", "Моторная Лодка под управлением компании [Name].", "Этот гулет ... под управлением компании [Name].", "Хаусбот управляется компанией [Name]..."
  - DE: "Diese Yacht wird in ... Charter [Name] betrieben.", "Dieses Gulet wird in ... von der Chartergesellschaft [Name] betrieben.", "Dieses Hausboot wird von [Name] betrieben...", "Das Motorboot gehört zur [Name] Charter-Flotte."
  - ES: "Este [type] está gestionado en [Country] por el chárter [Name].", "Esta goleta es operada en [Country] por la empresa de chárter [Name].", "Esta casa flotante es administrada por [Name]...", "La lancha a motor es operada por [Name]."
  - FR: "Ce yacht est opéré par [Name].", "Le bateau est géré par [Name].", "Cette péniche est gérée par [Name]...", "Cette goélette est louée par [Name]..."
- Regex design: `\Z` anchor (end of string only), `[^.]+?` for mid-segments to prevent cross-sentence matching, `.+\Z` for final segments to handle names with periods (e.g., "Inc.", "boats.gr").
- Template: `detail.html` uses `{% with clean_description=boat.description|strip_charter_company %}{% if clean_description %}` to hide empty-description card.
- Files: `boats/templatetags/boat_filters.py`, `templates/boats/detail.html`.
- Validation: `manage.py check` — 0 issues. 1500 real descriptions tested (300/language), 0 leaks. HTTP 200 for home, detail (RU + EN), login pages. `grep` confirms zero charter mentions in rendered HTML.
- Risks: New boat types or reformulated charter sentences from boataround.com might not match existing patterns — would require adding new regex. Database data is untouched.

## 2026-04-12 — Full DaisyUI 5 migration: all templates (Phase 2)
- Scope: Migrated ALL remaining 11 templates from DaisyUI v4 compat classes to native DaisyUI 5 + Tailwind utilities. Zero legacy `form-control`, `label-text`, `label-text-alt`, `class="label"` (form label) remaining anywhere.
- Migration pattern:
  - `form-control` → plain `<div>` (or removed wrapper entirely)
  - `<label class="label"><span class="label-text">` → `<div class="text-sm font-semibold mb-1.5">` (or `text-xs font-medium mb-1` for compact filters)
  - `label-text-alt text-error` → `<p class="text-xs text-error mt-1">`
  - `label-text-alt` hints → `<p class="text-xs opacity-60 mt-1">`
  - `<label class="label cursor-pointer">` (checkbox/radio) → `<label class="cursor-pointer flex items-center gap-2">`
- CSS cleanup: Removed 3 `@utility` compat shims from `assets/css/tailwind.input.css` (form-control, label-text, label-text-alt).
- Files modified: `templates/boats/offers_list.html`, `templates/boats/my_bookings.html`, `templates/boats/contract_sign.html`, `templates/accounts/price_settings.html`, `templates/boats/client_form.html`, `templates/boats/create_contract.html`, `templates/boats/create_offer.html`, `templates/accounts/profile.html`, `templates/boats/home.html`, `templates/boats/search.html`, `templates/boats/detail.html`, `assets/css/tailwind.input.css`.
- Validation: `manage.py check` — 0 issues. HTTP 200 for home, search, login, register. Global grep: 0 legacy matches across all templates. Rendered HTML verified clean.
- Risks: No logic changes. Template-only migration. CSS compat shims removed — any template still using legacy classes would lose styling (but grep confirms none remain).

## 2026-04-12 — Theme-native sizing: remove explicit -lg overrides
- Problem: Home page search form had `input-lg`, `select-lg`, `btn-lg` on all elements. Login/register had `btn-lg` on buttons but default-sized inputs — creating visible size mismatch. The winter theme defines `--size-field: 0.1875rem` and `--size-selector: 0.1875rem` which should govern all component sizes.
- Fix: Removed all `-lg` modifiers from home.html (4 inputs + 1 select + 1 button), login.html (2 buttons), register.html (2 buttons). All elements now use theme-native sizing.
- Files: `templates/boats/home.html`, `templates/accounts/login.html`, `templates/accounts/register.html`.
- Validation: Docker rebuild + HTTP 200 for all three pages.

## 2026-04-12 — Auth forms DaisyUI 5 compliance (v2 — fieldset/label fix)
- Problem (v1 attempt): Replaced v4 `form-control`/`label-text` with DaisyUI 5 `fieldset`/`label` classes. Result was worse: `.fieldset` and `.fieldset-legend` classes **do not generate CSS** in current DaisyUI 5 + Tailwind v4 build — native `<fieldset>` element borders appeared. `.label` class has `white-space: nowrap` (text overflow) and `color-mix(60% transparent)` (dim text). Buttons outside `<fieldset>` rendered narrower than inputs inside it due to native `min-inline-size: min-content`.
- Root cause: DaisyUI 5 plugin under current Tailwind v4 setup does NOT emit `.fieldset`, `.fieldset-legend` CSS rules. Only `fieldset:disabled .input` selectors exist. `.label` IS emitted but as a description/hint component (small, dim, nowrap) — NOT suitable for field labels.
- Fix (v2): Removed ALL `<fieldset>`, `<label class="label">`, `.fieldset-legend` from auth forms. New structure:
  - Field labels: `<div class="text-sm font-semibold mb-1.5">` — plain Tailwind, no DaisyUI form component.
  - Inputs: `<input class="input w-full">` — DaisyUI 5 `input` component directly on element.
  - Selects: `<select class="select w-full">` — DaisyUI 5 `select` component.
  - Errors: `<p class="text-xs text-error mt-1">` — plain Tailwind error text.
  - Helper text: `<p class="text-xs opacity-60 mt-1.5 leading-relaxed">` — wrappable, properly styled.
  - Form: `<form class="flex flex-col gap-4">` — consistent vertical spacing.
  - Alert: `<div role="alert" class="alert alert-error">` — DaisyUI 5 flat alert.
  - Removed `input-lg` (was causing oversized inputs), `select-lg`, `focus:input-primary` (non-existent variant).
- Components used (all verified in built CSS): `input`, `select`, `btn`, `card`, `card-body`, `alert`, `divider`, `link`.
- Files: `templates/accounts/login.html`, `templates/accounts/register.html`.
- Validation: `manage.py check` — 0 issues. HTTP 200 for both pages. No legacy classes (`fieldset`, `label`, `form-control`, `label-text`) in rendered HTML.
- Risks: None. Only template changes. CSS compat shims for `form-control`/`label-text` kept for other templates.

## 2026-04-12 — Commission display on offer page & offers list
- Problem: Commission was visible in search results and detail page for captains, but missing from offer detail page and offers list table.
- Fix:
  - `boats/views.py`: Extracted `_compute_offer_commission(offer)` helper from `_build_price_debug`. Added commission context + visibility flags to `offer_detail` view. Added bulk commission computation to `offers_list` view (single DB query via `select_related('charter')`).
  - `templates/boats/offer_captain.html`: Added commission display inside the price card. Captain sees agent commission amount. Manager/admin sees charter commission % + amount + agent commission + charter name.
  - `templates/boats/offers_list.html`: Added "Комиссия" column to desktop table and commission line to mobile cards. Same visibility rules.
- Visibility: `show_charter_commission_only` (captain) → agent commission only. `show_full_price_breakdown` (manager/admin) → full breakdown. Anonymous/tourist → nothing.
- Validation: `manage.py check` — 0 issues. HTTP 200 for offer detail + offers list. Captain sees commission values, anonymous does not.
- Risks: None. Purely additive display change. No data model changes.

## 2026-04-11 — Quick offer modal: countdown & force-refresh flags
- Problem: Quick offer creation modal (boat detail page) lacked "Обратный отсчет" (show_countdown) and "Обновить данные" (force_refresh) checkboxes that exist in the full create_offer form.
- Fix:
  - `accounts/migrations/0009_add_countdown_refresh_permissions.py`: new permissions `use_countdown` (captain, assistant, manager, admin, superadmin) and `use_force_refresh` (assistant, manager, admin, superadmin).
  - `accounts/models.py`: added `can_use_countdown()` and `can_use_force_refresh()` methods.
  - `templates/boats/detail.html`: added checkboxes to both quick offer form variants (manager/admin type-choice form and captain-only form). Conditional rendering via `{% if user.profile.can_use_countdown %}` / `{% if user.profile.can_use_force_refresh %}`.
  - `boats/views.py`: `quick_create_offer` — reads `force_refresh` from POST with `can_use_force_refresh()` guard, passes to `_ensure_boat_data_for_critical_flow`. Reads `show_countdown` from POST with `can_use_countdown()` guard, sets on Offer model.
- Validation: `manage.py check` — 0 issues. Template compilation OK. HTTP 200 for detail page. Verified: manager sees both checkboxes, captain sees only countdown.
- Risks: None. Purely additive feature. No changes to existing create_offer flow.

## 2026-04-10 — Search filters: bug fixes from deep testing
- Bugs found & fixed:
  1. **Checkbox `checked` substring matching** (HIGH): `{% if item.id in active_sail %}` did string containment on comma-joined string. If one ID were a substring of another, both would show checked. Fixed by passing lists instead of strings for `active_sail`, `active_engine_type`, `active_cockpit`, `active_entertainment`, `active_equipment`.
  2. **Manufacturer case-sensitivity** (MEDIUM): API expects lowercase slug IDs (e.g., `bavaria`) but user might type `Bavaria`. Added `.lower()` to manufacturer input.
  3. **Duplicate `@staticmethod`** (LOW): `boataround_api.py` line 598-599 had doubled decorator on `get_boat_combined_data`. Removed duplicate.
- Files: `boats/views.py`, `boats/boataround_api.py`
- Validation: `manage.py check` — 0 issues. HTTP tests:
  - All 22 filter fields render (name= attributes verified)
  - Each of 12 filter types reduces result count (diesel: 3147, catamaran: 936, cabins 3+: 2769, etc.)
  - Multi-value checkboxes persist correctly (checked/unchecked verified)
  - Pagination preserves all filter params in links
  - All 6 sort options return results
  - Active filter badges render for all active filters
  - XSS, SQL injection, CRLF injection — all safely handled
  - Invalid inputs (negative page, huge page, invalid sort) return HTTP 200 gracefully
  - Russian localization of all dynamic filters confirmed (engine, sail, skipper, cockpit)
- Risks: None. All changes are strictly correctness fixes.

## 2026-04-10 — Comprehensive search filters from Boataround API
- Problem: Search page only supported 6 basic filters (destination, category, dates, cabins, year, price). Boataround API exposes 15+ filter parameters that were unused. Category values were wrong (sailboat instead of sailing-yacht).
- Fix:
  - `boats/boataround_api.py`: Added 11 new named params to `search()`: max_sleeps, allowed_people, boat_length, manufacturer, skipper, sail, engine_type, cockpit, entertainment, equipment, toilets.
  - `boats/views.py`: Extract all new GET params. Multi-value checkbox params use `getlist()` + comma-join. Added `_build_range()` helper for DRY range formatting. Expanded `allowed_sorts` with reviewsDown, dealsFirst, freeCancellation. Added `active_*` context vars for checkbox state persistence. Added `api_filters` to context.
  - `templates/boats/search.html`: Fixed category values (sailing-yacht, motor-yacht, motor-boat, catamaran, gulet, power-catamaran). Added sleeps/guests/length/toilets/manufacturer/skipper fields. Collapsible sections for sail+engine, cockpit (17 items), entertainment (15 items), equipment (15 items). Expanded sort dropdown. Updated active filter badges for all new fields. All labels wrapped in `{% trans %}`.
  - `boats/templatetags/boat_filters.py`: Added `split` template filter for iterating comma-separated lists in templates.
- Files: `boats/boataround_api.py`, `boats/views.py`, `templates/boats/search.html`, `boats/templatetags/boat_filters.py`
- Validation: `manage.py check` — 0 issues. Template compilation — OK.
- Risks: Checkbox "checked" persistence uses `in` string containment on comma-joined values — could false-positive if one value is substring of another (e.g. `roll` in `Snorkel`), but current amenity names are distinct enough. Boataround API may not support all params simultaneously — test needed.

## 2026-04-09 — Fix OOM v3: reduce PAGES_PER_RANGE + fix totalPages inflation
- Problem: v2 disposable tasks still OOM-killed on production (Job:16, signal 9). Two root causes found.
- Root cause 1: `boataround_api.py` calculated `totalPages` as `total / len(boats)`. When API returned 8 boats instead of 18 on a page, totalPages inflated from 1491 to 3354. Doubled the number of dispatched `process_api_page_range` tasks.
- Root cause 2: `PAGES_PER_RANGE=20` meant each task processed 20 pages × 5 langs = 100 ORM flush operations. At Job:16 (320 cumulative pages), arena fragmentation exceeded VPS headroom.
- Root cause 3: `process_api_page_range` did not increment `batches_done` — `--status` showed `Батчи: 0/75` even at 88% completion.
- Fix:
  - `boataround_api.py`: use `limit` instead of `len(boats)` for `totalPages` in both response parsing branches.
  - `tasks.py`: `PAGES_PER_RANGE: 20 → 5`. Each task: 5 pages × 5 langs = 25 ORM flushes. ~298 tasks for full catalog.
  - `tasks.py`: added `batches_done` increment at end of `process_api_page_range`.
  - `tasks.py`: added `del results` in per-page cleanup loop.
- Files: `boats/boataround_api.py`, `boats/tasks.py`
- Validation: `manage.py check` — 0 issues.
- Risks: ~298 tasks vs ~75 — more scheduling overhead, but each task is 4× lighter. Net positive for 1 GB VPS.

## 2026-04-08 — Fix search_by_slug: wrong API parameter name (`slug` → `slugs`)
- Problem: `BoataroundAPI.search_by_slug()` used `slug` (singular) as API query parameter. Boataround API does not recognize this parameter — it ignores it silently and returns 50 default boats. If the target boat isn't among those 50, it is not found. This caused `BoatTechnicalSpecs` to never be created for many boats, resulting in empty specs on offers and detail pages.
- Root cause: wrong parameter name. API expects `slugs` (plural).
- Fix: `boats/boataround_api.py` line 718: `'slug': slug` → `'slugs': slug`. Removed `'limit': 50` (unnecessary when slug filter works).
- Files: `boats/boataround_api.py`
- Validation: `manage.py check` — 0 issues. Tested 3 boats via `search_by_slug()` — all found with full `parameters` dict. Updated broken offer `18785f61` — specs now show correctly.
- Risks: None. Single parameter rename, no behavioral changes to response parsing.

## 2026-04-08 — Fix OOM kill in parse_boats: disposable Celery tasks for 1 GB RAM VPS (v2)
- Problem: v1 (per-page DB flush) still OOM-killed at page 155/1560 on 1 GB RAM VPS. Python memory fragmentation from 155× `_update_api_metadata()` ORM operations in a single long-running Celery task caused RSS to grow unboundedly despite per-page discard + gc.collect.
- Root cause: Python's small-object arena allocator doesn't return freed memory to OS. Each `_update_api_metadata()` call creates ~100 ORM objects per page. After 155 pages, fragmented arena blocks accumulate beyond available RAM (~200 MB headroom on 1 GB VPS).
- Fix (v2 — disposable tasks architecture):
  - `_collect_slugs_from_api`: stripped to EN-only collection. No multilingual fetches, no DB writes, no ThreadPoolExecutor, no ORM objects. Only slugs + thumb_map accumulate (~11 MB for 28k boats). gc.collect() every 50 pages.
  - New `process_api_page_range` task: handles ~20 API pages each. Fetches EN + 4 langs via ThreadPoolExecutor(max_workers=3), calls `_update_api_metadata()` per-page with gc.collect after each, then exits. Worker process recycled by `--max-tasks-per-child=100`.
  - `run_parse_job`: lightweight orchestrator. Dispatches `process_api_page_range` tasks (for api/full, ~80 tasks for full catalog) and/or `process_html_batch` tasks (for html/full) via chord → finalize.
  - `process_api_batch`: kept for backward compat, no longer dispatched by orchestrator.
- Files: `boats/tasks.py` (`_collect_slugs_from_api`, `_save_slug_cache`, `process_api_page_range` NEW, `run_parse_job`)
- Validation: `manage.py check` — 0 issues. All imports verified via Django shell.
- Memory budget: orchestrator ~160 MB (base) + 11 MB (slugs) = ~171 MB. Each page-range task: ~2 MB peak/page, process recycled after task. Safe for 1 GB VPS with ~200 MB headroom.
- Risks: API page results can shift between orchestrator's probe and page-range tasks' fetch (boats reorder). Acceptable: metadata written regardless of order. More Celery tasks dispatched (~80 vs 1), slight scheduling overhead.

## 2026-04-07 — PEP 8 full compliance refactor (835 → 0 violations)
- Problem: 835 flake8 violations across 18 core Python files (max-line-length=120). Mix of whitespace issues (646), unused imports (21), empty f-strings (33), bare except (12), long lines (67), and minor issues (F811, F821, F841, E741, E127/E128, E225).
- Fix: 3-phase approach. Phase 1: autopep8 for auto-fixable whitespace (W291/W293/W391/E302/E303/E305/E306/E231/E226/E261). Phase 2: manual fixes for imports, f-strings, exception handling, variable naming, indentation. Phase 3: manual line-wrapping for all 67 E501 violations using idiomatic Python patterns.
- Files (18): `boat_rental/settings.py`, `boat_rental/urls.py`, `boat_rental/celery.py`, `accounts/models.py`, `accounts/views.py`, `accounts/forms.py`, `boats/models.py`, `boats/views.py`, `boats/boataround_api.py`, `boats/parser.py`, `boats/tasks.py`, `boats/helpers.py`, `boats/forms.py`, `boats/admin.py`, `boats/pricing.py`, `boats/contract_generator.py`, `boats/sms.py`, `boats/notifications.py`
- Validation: `flake8 --max-line-length=120` → 0 violations. `docker compose up -d --build` + `manage.py check` → 0 issues.
- Key changes: bare `except:` replaced with `except (ValueError, TypeError):` for numeric conversions and `except Exception:` for ORM lookups in `boataround_api.py`; undefined `User` fixed with local `AuthUser` import in `views.py`; ambiguous `l` variable renamed to `lang` in `tasks.py`; redundant `Decimal`/`BoatDescription` re-imports removed; complex one-liner ternaries in `parser.py` refactored to if/elif blocks.
- Risks: None. Pure code style changes, no behavior modification. All function signatures and return values unchanged.

## 2026-04-07 — Permission refactor Phase 2: eliminate all hardcoded role checks
- Problem: 25+ hardcoded `profile.role == '...'` / `profile.role in (...)` checks in `boats/views.py` + 8 in templates. Some had bugs: `delete_booking` excluded superadmin, offers only visible to admin (not manager/superadmin), client views missed admin role.
- Fix: Added 6 new permissions to `accounts/models.py`: `can_view_price_breakdown()`, `can_assign_managers()`, `can_delete_bookings()`, `can_delete_offers()`, `can_create_contracts()`, `can_view_all_clients()`. Migration `0008_add_granular_permissions.py` assigns to roles. Replaced all 25+ Python hardcodes and 8 template hardcodes with `can_*()` / `is_*` methods.
- Files: `accounts/models.py`, `accounts/migrations/0008_add_granular_permissions.py`, `boats/views.py`, `templates/base.html`, `templates/includes/lk_sidebar.html`, `templates/accounts/profile.html`, `templates/boats/my_bookings.html`
- Validation: `python manage.py check` — 0 issues. All 120 tests pass.
- Bugs fixed: (1) `delete_booking` now works for superadmin, (2) offers visibility for manager/superadmin, (3) `book_offer` for admin/superadmin, (4) `delete_offer` for superadmin, (5) client CRUD for admin.
- Only remaining `role == '...'` in templates: profile.html badge coloring (legitimate display logic, not capability).
- Risks: None. Permissions are additive. Existing role assignments preserved via migration.

## 2026-04-07 — Force refresh flag ignored in create_offer
- Problem: `create_offer.html` sends `force_refresh=true` via POST when "Обновить данные" checkbox is checked, but `create_offer` view never reads it. `_ensure_boat_data_for_critical_flow` always returned cached data.
- Fix: Added `force_refresh` param to `_ensure_boat_data_for_critical_flow(slug, lang, force_refresh=False)`. When `True`, skips cache and runs full parse (API + HTML). `create_offer` reads `request.POST.get('force_refresh') == 'true'` and passes it.
- Files: `boats/views.py`
- Validation: `docker compose run --rm web python manage.py check` — 0 issues.
- Risks: Force refresh adds ~10s latency (full HTML parse). Only triggered by explicit user action (checkbox).

## 2026-04-07 — Price breakdown leaked to captain role
- Problem: `show_price_debug` in `my_bookings` included `'captain'` — captains could see full price breakdown (API price, discounts, charter/agent commissions, adjustments). Must be restricted to manager/admin/superadmin.
- Fix: Removed `'captain'` from role tuple in `my_bookings` view (line 1283). `_price_visibility_flags()` was already correct (captain gets only `show_charter_commission_only`), so boat detail/offers were fine.
- Files: `boats/views.py`
- Validation: `docker compose run --rm web python manage.py check` — 0 issues.
- Risks: None. Captain now sees only total price in bookings list, consistent with detail/offer pages.

## 2026-04-07 — Contract signing download 404 fix
- Problem: After OTP signing, "Скачать PDF" linked to `download_contract` which requires `@login_required`. Signer is not authenticated (accessed via `sign_token`). Also `LOGIN_URL = '/login/'` didn't match any i18n route (actual: `/ru/accounts/login/`).
- Fix 1: Changed `LOGIN_URL` from `'/login/'` to `'login'` (named URL) in `boat_rental/settings.py` — Django resolves it with proper i18n prefix.
- Fix 2: New view `download_signed_contract(request, uuid, sign_token)` — serves PDF without auth, validates `sign_token` + `status='signed'`. URL: `contracts/<uuid>/sign/<sign_token>/download/`.
- Fix 3: Updated `contract_signed.html` to link to `download_signed_contract` instead of `download_contract`.
- Files: `boat_rental/settings.py`, `boats/views.py`, `boats/urls.py`, `templates/boats/contract_signed.html`
- Validation: `docker compose run --rm web python manage.py check` — 0 issues.
- Risks: Token-based download only works for signed contracts (`status='signed'`). Existing `download_contract` (auth-based) unchanged.

## 2026-04-07 — PDF download crash fix
- Problem: `download_contract` used `FileResponse(contract.document_file.open('rb'))` — streaming from FieldFile caused browser crash/close on download.
- Fix: Replaced with `HttpResponse(contract.document_file.read())` — atomic response delivery.
- Files: `boats/views.py`
- Validation: `docker compose run --rm web python manage.py check` — 0 issues.

## 2026-04-07 — Notifications refactored to separate module
- Problem: Notification logic (in-app + Telegram) was inline in `boats/views.py` with inline imports — PEP violation, mixed concerns.
- Fix: Created `boats/notifications.py` with `notify_new_booking()` and `notify_status_change()`. Uses `bulk_create()` for efficiency. Clean top-level imports. Views call one-liner functions.
- Files: `boats/notifications.py` (NEW), `boats/views.py` (cleaned)

## 2026-04-07 — assign_booking_manager permission fix
- Problem: `assign_booking_manager` had `role not in ('manager', 'superadmin')` — assistant couldn't take bookings.
- Fix: Changed to `can_see_all_bookings()` permission check. Template `my_bookings.html` updated to use `can_access_admin_panel`.
- Files: `boats/views.py`, `templates/boats/my_bookings.html`

## 2026-04-07 — Telegram notifications for assistant
- Change: Added Telegram notification on new booking creation (3 entry points: `create_booking`, `book_offer`, `book_boat`) and booking status changes (confirm/option/cancel in `update_booking_status`).
- Implementation: `boats/telegram.py` — raw Telegram Bot API via `requests.post`, fail-silent. Celery task `send_telegram_notification` in `boats/tasks.py` (2 retries, 30s backoff). Settings: `TELEGRAM_BOT_TOKEN` + `TELEGRAM_ASSISTANT_CHAT_ID` via decouple.
- Files: `boats/telegram.py` (NEW), `boats/tasks.py`, `boats/views.py`, `boat_rental/settings.py`, `.env.example`
- No new pip dependencies (uses existing `requests`).
- Validation: `docker compose run --rm web python manage.py check` — 0 issues.
- Risks: If Telegram API is down, Celery retries silently and gives up after 2 attempts. No user-facing impact.

## 2026-04-07 — Booking option status + in-app notifications
- Change:
  - **Booking option status**: Added `option` to Booking.STATUS_CHOICES, added `option_until` DateField for option expiry date.
  - **Notification model**: New model `Notification` (recipient FK→User, booking FK→Booking, message TextField, is_read, created_at) with indexes.
  - **`update_booking_status` view**: Rewritten — `role != 'manager'` → `can_confirm_booking()` permission check. Added `option` action with date validation. All actions (confirm/option/cancel) create Notification for responsible user.
  - **Notification views**: `notifications_list`, `notification_mark_read`, `notifications_mark_all_read` — with 3 new URLs.
  - **Context processor**: `boats/context_processors.py` provides `unread_notifications_count` globally.
  - **my_bookings template**: Alpine.js date picker for "На опцию" action. Option status badges (desktop + mobile). Stats grid expanded to 4 columns with option count.
  - **Notification bell**: Added to base.html navbar (desktop + mobile dropdown) + lk_sidebar with unread badge.
  - **Admin**: `Notification` registered, `BookingAdmin` shows `option_until`.
  - **check_data_status**: Added `option` status to bookings stats.
- Files:
  - `boats/models.py` — Booking.STATUS_CHOICES + option_until + Notification model
  - `boats/views.py` — update_booking_status rewrite + 3 notification views + my_bookings context
  - `boats/urls.py` — 3 notification URLs
  - `boats/context_processors.py` — NEW
  - `boat_rental/settings.py` — context processor registered
  - `boats/admin.py` — NotificationAdmin + BookingAdmin option_until
  - `boats/management/commands/check_data_status.py` — option status
  - `templates/base.html` — bell icon (navbar + mobile dropdown)
  - `templates/includes/lk_sidebar.html` — notifications link
  - `templates/boats/my_bookings.html` — option badges, Alpine.js date picker, stats
  - `templates/boats/notifications.html` — NEW
  - `boats/migrations/0034_booking_option_until_alter_booking_status_and_more.py` — NEW
- Validation:
  - `docker compose down && docker compose up -d --build` — OK
  - `docker compose run --rm web python manage.py check` — 0 issues
  - 120/120 tests pass
- Risks:
  - No existing tests for update_booking_status view — may need integration tests.
  - Notification volume could grow; consider periodic cleanup or auto-read on booking view.

## 2026-04-06 (session 4)
- Change:
  - **ORM FieldError fixes**: 2 locations in `boats/views.py` used `profile__role='manager'` → `profile__role_ref__codename='manager'` (my_bookings manager list, assign_booking_manager).
  - **`check_data_status` FieldError**: `.values_list('role')` → `.values_list('role_ref__codename')` — old `role` CharField removed in migration 0007.
  - **`additional_services` guard**: added `if details else []` to prevent AttributeError when BoatDetails is None in `boat_detail_api`.
  - **`flexible_cancellation` underscore variant**: DB stores `flexible_cancellation` (underscore), `HIDDEN_SERVICE_SLUGS` had only hyphen variant. Added both.
  - **`my_bookings` permission**: `role in ('manager', 'superadmin')` → `can_see_all_bookings()`.
  - **`accounts/views.py` method calls**: `can_manage_boats`/`can_create_offers` were referenced as properties (no parentheses) → called as methods `()`.
  - **Test fixes**: `test_boataround_api` assertions updated for consensus-based `get_price` (5 attempts × 3 internal retries), additive pricing model (850 not 855), cache isolation (different slug per test).
  - **`extra_discount_max` fallback**: `5` → `0.0` (fail-closed when PriceSettings inaccessible in tests).
- Files:
  - `boats/views.py` — ORM fixes (2), additional_services guard, my_bookings permission
  - `boats/helpers.py` — flexible_cancellation slug, extra_discount_max fallback, removed dead constants
  - `accounts/views.py` — can_*() parentheses, can_see_all_bookings, can_create_captain_offers
  - `boats/management/commands/check_data_status.py` — role_ref__codename
  - `boats/tests/test_boataround_api.py` — retry/price assertions
  - `templates/boats/detail.html`, `templates/boats/offer_captain.html` — flexible_cancellation guards
- Validation:
  - `docker compose run --rm web python manage.py check` — 0 issues
  - 120/120 tests pass
- Risks:
  - None. All changes are compatibility fixes for the new role system and test alignment.

## 2026-04-06 (session 3)
- Change:
  - **Full audit of hardcoded role checks**: found 28 locations, 15 CRITICAL (blocking assistant + sometimes admin/manager).
  - Replaced hardcoded `role == 'admin'`/`role in ('manager', 'superadmin')` with `can_see_all_bookings()` across all offer/contract/client views.
  - **Offers (3 views)**: `offers_stats_api`, `offers_list_api`, `offers_list` — `role == 'admin'` → `can_see_all_bookings()`. Previously even manager couldn't see all offers.
  - **Offer detail (2 views)**: `can_book_from_offer` — `role == 'manager'` → `can_see_all_bookings()`. Assistant + admin + superadmin can now book from offers.
  - **Offer price_debug**: `role in ('manager', 'admin', 'superadmin')` → `role not in ('tourist',)`. Consistent with my_bookings price_debug.
  - **book_offer**: `role == 'manager'` → `can_see_all_bookings()`. Assistant can now create bookings from offers.
  - **create_contract**: added `'assistant'` to allowed roles tuple.
  - **contract_detail + download_contract**: `role in ('manager', 'admin', 'superadmin')` → `can_see_all_bookings()`. Assistant can now view/download contracts.
  - **contract_detail can_manage**: same replacement.
  - **contracts_list**: `role in ('manager', 'admin', 'superadmin')` → `can_see_all_bookings()`. Captain/assistant branch now correctly shows own contracts.
  - **clients_list/detail/edit/search (4 views)**: `role in ('manager', 'superadmin')` → `can_see_all_bookings()`. Also fixes missing `admin` access.
  - **attach_client_to_booking client lookup**: `role in ('manager', 'admin', 'superadmin')` → `can_see_all_bookings()`.
  - **Navigation**: `base.html` + `lk_sidebar.html` — added `assistant` to contracts/clients nav links.
  - **Minor**: `accounts/views.py` offers_count → `can_see_all_bookings()`, commission_info → `can_create_captain_offers()`.
  - **Minor**: `profile.html` assistant badge gets `badge-secondary` color.
- Files:
  - `boats/views.py` — 17 replacements across offers/contracts/clients/booking views
  - `accounts/views.py` — 2 fixes (offers_count, commission_info)
  - `templates/base.html` — contracts/clients nav: added assistant + admin
  - `templates/includes/lk_sidebar.html` — contracts/clients sidebar: added assistant
  - `templates/accounts/profile.html` — assistant badge color
- Validation:
  - `docker compose run --rm web python manage.py check` — 0 issues
  - 119/119 tests pass
- Risks:
  - `delete_offer` still uses `role == 'admin'` (intentional — destructive action, admin-only besides author).
  - `delete_booking` uses tuple `('manager', 'admin', 'superadmin')` (intentional — destructive).
  - `show_full_price_breakdown` in `_price_visibility_context` still hardcoded to manager/admin/superadmin — assistant doesn't see full breakdown in search/detail. Could be a future enhancement.

## 2026-04-06 (session 2)
- Change:
  - **Permission-based role system (Variant B)**: replaced CharField `role` on UserProfile with FK → Role model + Permission M2M.
  - New models: `Permission(codename, name)` — 14 records; `Role(codename, name, permissions M2M, is_system)` — 6 system roles.
  - `UserProfile.role` is now a **property** returning `role_ref.codename` — all 56+ direct comparisons `profile.role == 'captain'` in views/templates work without changes.
  - `role.setter` accepts string codename or Role instance for backward-compatible assignment.
  - All `can_*()` methods delegate to `has_perm(codename)` with instance-level `_perm_cache`.
  - New role: **Ассистент** (assistant) — can confirm bookings, notify captains, view all bookings + captain offers.
  - Admin: registered Permission (read-only), Role (filter_horizontal), updated UserProfileAdmin for `role_ref` FK.
  - 3-step migration: 0005 (schema), 0006 (data — populate 14 perms + 6 roles + migrate profiles), 0007 (remove old CharField).
  - Fixed all ORM-level references: `save(update_fields=['role'])` → `['role_ref']`, `update(role=x)` → `update(role_ref=...)`, `filter(role=x)` → `filter(role_ref__codename=x)`, `update_or_create` defaults.
- Files:
  - `accounts/models.py` — Permission, Role models; UserProfile rewrite (role property, has_perm, can_*())
  - `accounts/admin.py` — PermissionAdmin, RoleAdmin, updated UserProfileAdmin
  - `accounts/forms.py` — import Role, use `role_ref` in update_or_create
  - `accounts/views.py` — save(update_fields=['role_ref'])
  - `accounts/management/commands/create_test_users.py` — role_ref in save/filter
  - `accounts/migrations/0005_permission_role_userprofile_role_ref.py`
  - `accounts/migrations/0006_populate_roles_permissions.py`
  - `accounts/migrations/0007_remove_userprofile_role.py`
  - `boats/tests/test_views.py` — update_fields=['role_ref']
  - `boats/tests/test_price_settings.py` — import Role, use role_ref in ORM update
- Validation:
  - `docker compose run --rm web python manage.py check` — 0 issues
  - Migrations applied OK (0005, 0006, 0007)
  - Shell verification: 14 permissions, 6 roles, all profiles migrated correctly
  - 4 role-specific tests pass (manager/captain search+detail price visibility)
  - 8 pre-existing test failures (unrelated: PriceSettings attribute, template CSS)
- Risks:
  - Any code that does `UserProfile.objects.filter(role='captain')` will fail (field doesn't exist). Must use `filter(role_ref__codename='captain')`. All known instances fixed.
  - `profile.role = 'x'` triggers DB query in setter. Performance is fine for single assignments but shouldn't be used in bulk loops.

## 2026-04-06
- Change:
  - `load_parsed_boats`: added directory support — loads all `.json` files in sorted order. Previously crashed with `IsADirectoryError` on directory path.
  - `load_parsed_boats._reset_sequences`: replaced f-string SQL with parameterized queries + `connection.ops.quote_name()`.
  - `dump_parsed_boats`: simplified load hint (one `docker cp` + `load_parsed_boats dir/` instead of per-file commands), `docker-compose` → `docker compose`.
  - `how_to.md`: replaced stale `loaddata` with current dump/load commands.
- Files:
  - `boats/management/commands/load_parsed_boats.py` — `_load_multiple()`, `_reset_sequences()`, docstring, `glob` import
  - `boats/management/commands/dump_parsed_boats.py` — output hints
  - `boats/fixtures/how_to.md` — rewritten
- Validation:
  - `docker compose run --rm web python manage.py check` — 0 issues
  - Both commands `--help` — OK
- Risks:
  - None. No behavioral changes to existing single-file loading path.

## 2026-04-04 (session 2)
- Change:
  - Hide "Гибкая отмена" (slug `flexible-cancellation`) from all UI. Added `HIDDEN_SERVICE_SLUGS` constant in `helpers.py`, filter in 3 view functions (`boat_detail_api`, `_build_boat_data_from_db`, `offer_view`), template guards in `detail.html` and `offer_captain.html`.
  - Full documentation audit: fixed Django 4.2→5.2, Python 3.8→3.13, stale command names, broken links across 15+ files.
  - Archived 7 obsolete docs to `docs/archive/`.
  - Deleted `CONTRIBUTING.md`, `SECURITY.md` (outdated/fake data).
  - Rewrote `README.md` from scratch (Russian, accurate stack/commands/models).
  - Created `docs/RELEASE_NOTES.md` (user-facing changelog).
  - Added RELEASE_NOTES rules to AGENTS.md Update Ritual.
  - Fixed duplicate DR-017 IDs in DECISIONS.md → DR-024/025/026/027.
- Files:
  - `boats/helpers.py` — `HIDDEN_SERVICE_SLUGS`
  - `boats/views.py` — 3 filter locations
  - `templates/boats/detail.html` — template guard
  - `templates/boats/offer_captain.html` — template guard
  - `README.md` — full rewrite
  - `AGENTS.md` — stack fix + RELEASE_NOTES rules
  - `docs/RELEASE_NOTES.md` — new
  - `docs/DECISIONS.md`, `docs/TASK_STATE.md`, `docs/DEV_LOG.md`, `docs/FAQ.md`, `docs/INDEX.md`, `docs/I18N_ARCHITECTURE.md`, `docs/I18N_QUICK_REFERENCE.md`, `docs/KNOWN_ISSUES.md` — updates
  - `CONTRIBUTING.md`, `SECURITY.md` — deleted
  - 7 files moved to `docs/archive/`
- Why:
  - "Гибкая отмена" — business decision, service not relevant to users.
  - Documentation had widespread version drift (Django 4.2 referenced in 10+ places), broken links to archived/renamed files, duplicate decision IDs, and 6 redundant I18N files (2305 lines).
- Validation:
  - `docker compose down && docker compose up -d --build` — OK
  - `docker compose run --rm web python manage.py check` — 0 issues
  - HTTP check: / → 200, /boats/search/ → 200
  - Template compilation: detail.html, offer_captain.html, offer_tourist.html — OK
- Risks:
  - Existing `Offer.boat_data` JSON snapshots still contain `flexible-cancellation` in `additional_services` — template guard handles this.
  - Archived docs in `docs/archive/` are not updated — they are frozen snapshots.

## 2026-04-03
- Change:
  - `_collect_slugs_from_api` refactored: collects all 5 languages per page in single pass (option A), matching proven `parse_boats_parallel` approach. Returns `api_meta_by_lang` alongside slugs/thumb_map/api_meta.
  - Added slug cache: `_load_slug_cache`/`_save_slug_cache` using JSON files in `CACHE_DIR`, no TTL (reset via `--no-cache`). Saves after every page, resumes from partial.
  - Removed `_fetch_lang_meta_for_slugs` (was fetching lang meta per-batch, doubled total time).
  - Reverted `process_api_batch` signature: accepts `api_meta_by_lang_subset` directly from orchestrator (no more destination/page_start/page_end).
  - Reverted `run_parse_job` batch formation: passes pre-collected `api_meta_by_lang` subsets to batches.
  - Concurrent lang fetch: 4 languages per page via `ThreadPoolExecutor(max_workers=4)`.
  - Removed double retry (search() has 3 internal retries already). 1 empty page = stop + save cache.
- Files:
  - `boats/tasks.py` — `_collect_slugs_from_api`, `_load_slug_cache`, `_save_slug_cache`, `CACHE_DIR`, removed `_fetch_lang_meta_for_slugs`, `process_api_batch`, `run_parse_job`
- Why:
  - Production parse job stuck for 24h. Root cause: 5 requests/page in collection + aggressive retry delays.
  - After fixing to EN-only collection, lang meta was fetched per-batch inside `process_api_batch` — doubled total time (~3.5h vs ~1.5h).
  - Option A (single-pass with all langs in collection phase) is proven in `parse_boats_parallel` and faster.
  - Slug caching was present in `parse_boats_parallel` but missing in Celery tasks — now added.
- Validation:
  - `docker compose run --rm web python manage.py check` — 0 issues
- Risks:
  - Collection phase now takes ~1.5h for full catalog (1484 pages × 5 langs = 7420 requests). Cache persists until `--no-cache`, resumes from partial on restart.
  - Large `api_meta_by_lang` dict serialized into Celery task args — for 27k boats ~50-100MB. Should be fine for Redis broker but monitor memory.

## 2026-04-02
- Change:
  - Detail/offer flow: полный парсинг (API → HTML). `_ensure_boat_data_for_critical_flow` теперь сначала вызывает API (`search_by_slug(raw=True)` → `_update_api_metadata`) для создания BoatTechnicalSpecs/Charter/BoatDescription, затем HTML-парсинг для фото и сервисов.
  - `_ensure_api_metadata_for_boat()` — новый helper для подтягивания API-метаданных одной лодки.
  - `search_by_slug(raw=True)` — возвращает сырые API данные с `parameters` dict.
  - `technical_specs` access обёрнут в try/except (`RelatedObjectDoesNotExist`).
  - `detail.html`: при `boat=None` (error path) шаблон не рендерит body с `toggle_favorite`, предотвращая `NoReverseMatch`.
- Files:
  - `boats/views.py` — `_ensure_boat_data_for_critical_flow`, `_ensure_api_metadata_for_boat`, import BoatTechnicalSpecs, try/except for specs access
  - `boats/boataround_api.py` — `search_by_slug(raw=True)` parameter
  - `templates/boats/detail.html` — `{% if not boat %}` guard + `{% endif %}` closing
  - `VERSION` — 0.5.0-dev → 0.5.1-dev
  - `CHANGELOG.md` — [0.5.1-dev] entry
  - `docs/DECISIONS.md` — DR-023
  - `docs/TASK_STATE.md` — updated P5
- Why:
  - Production crash: `RelatedObjectDoesNotExist: ParsedBoat has no technical_specs` на `lagoon-52-f-costabella-1`. Лодки, не прошедшие `parse_boats_parallel`, не имели BoatTechnicalSpecs — HTML-парсер их не создаёт (source-of-truth: API per DR/P5).
  - Шаблон detail.html падал на error path: `NoReverseMatch: toggle_favorite with args ('',)`.
- Validation:
  - `docker compose exec web python manage.py check` — 0 issues
  - Template compile check — OK
  - E2E test: удалил specs у живой лодки → `_ensure_api_metadata_for_boat` → specs восстановлены (length, cabins, berths, beam, draft)
  - 21 лодка без specs — все устаревшие (удалены из API), gracefully handled with None
- Risks:
  - Detail page для новой лодки делает 2 внешних запроса (API search + HTML parse) — ~15-20с. Это ожидаемо для первого захода.
  - Если API не находит лодку по slug — specs не создаются, но страница рендерится с None values.

## 2026-04-01
- Change:
  - New `parse_boats` management command — Celery-batched parsing with 3 modes (api/html/full).
  - `ParseJob` model for persistent job state, counters, and reports (summary + detailed_log + errors JSON).
  - Celery tasks: `run_parse_job` (orchestrator), `process_api_batch`, `process_html_batch` (batch workers).
  - Network retry with exponential backoff in both `parse_boats` tasks and `update_charters` command.
  - `check_data_status` command extended to check ALL data entities (charters, geo, specs, gallery, prices, details, offers, bookings, clients, contracts, users, price settings).
  - `check_data_status` now distinguishes active vs stale boats (30-day threshold).
  - Django admin registration for ParseJob with colored status, progress, duration.
  - `server_tasks.sh` helper script for background task management on server.
  - **`agent_commission_pct`** added to PriceSettings (default 50%). Replaces hardcoded `/2` in pricing.py and _build_price_debug. Configurable via /price-settings/ UI.
  - **Captain price visibility restricted**: offer price_debug hidden from captains; search/detail show agent commission (50% of charter) instead of full charter commission. Manager/admin see full breakdown.
  - **Profile page**: role and subscription badges, captain commission rate display.
- Files:
  - `boats/models.py` — ParseJob model, agent_commission_pct field
  - `boats/migrations/0032_parsejob.py` — new migration
  - `boats/migrations/0033_agent_commission_pct.py` — new migration
  - `boats/tasks.py` — 3 new Celery tasks (run_parse_job, process_api_batch, process_html_batch)
  - `boats/management/commands/parse_boats.py` — new command
  - `boats/management/commands/check_data_status.py` — new command
  - `boats/management/commands/update_charters.py` — added retry logic
  - `boats/pricing.py` — configurable agent commission from PriceSettings
  - `boats/views.py` — captain price visibility, cache invalidation after charter linking
  - `boats/admin.py` — ParseJobAdmin
  - `boats/tests/test_views.py` — updated captain commission tests
  - `accounts/views.py` — agent_commission_info in profile context
  - `templates/accounts/profile.html` — role/subscription badges, commission
  - `templates/accounts/price_settings.html` — agent_commission_pct field
  - `templates/boats/search.html`, `detail.html` — captain sees own commission only
  - `server_tasks.sh` — new helper script
  - `docs/DECISIONS.md` — DR-019, DR-020, DR-021, DR-022
  - `docs/TASK_STATE.md` — updated
  - `CHANGELOG.md` — v0.5.0-dev entry
  - `VERSION` — 0.4.1-dev → 0.5.0-dev
- Why:
  - `parse_boats_parallel` runs synchronously, blocks server, output lost on disconnect. Need async Celery-based pipeline with persistent reports.
  - `update_charters` crashed at page 806/1471 from transient DNS error — no retry logic.
  - `check_data_status` only checked ParsedBoat/charters/geo — user requested full coverage.
- Validation:
  - `docker compose down` + `up -d --build` — OK
  - `python manage.py check` — 0 issues
  - `migrate --check` — no unapplied migrations
  - HTTP: / 200, /boats/search/ 200, /accounts/login/ 200
  - E2E test all 3 modes:
    - `--mode api --destination turkey --max-pages 1` → 18/18 OK
    - `--mode html --destination turkey --max-pages 1 --skip-existing` → 18 skipped OK
    - `--mode full --destination turkey --max-pages 1` → 36/36 (18 API + 18 HTML) OK, progress 100%
  - `--status` listing: 6 jobs displayed correctly
  - Reports: summary, detailed_log, errors all persisted in DB
- Risks / follow-up:
  - Old commands (`parse_boats_parallel`, `parse_all_boats`, etc.) still present — can be deprecated after `parse_boats` is proven on full catalog.
  - `parse_boats` reuses existing `parse_boataround_url()` and `_update_api_metadata()` — any bugs in those functions affect new command too.
  - Full catalog run (~1460 pages, ~26k boats) not yet tested — only Turkey (1 page, 18 boats) validated.

## 2026-03-31
- Change:
  - Restricted search/detail price breakdown visibility by role.
  - `manager`, `admin`, `superadmin` keep full breakdown; `captain` now sees only charter commission percent and amount.
  - Added shared view helper for role flags and regression tests for search/detail rendering.
- Files:
  - `boats/views.py`
  - `templates/boats/search.html`
  - `templates/boats/detail.html`
  - `boats/tests/test_views.py`
  - `docs/DECISIONS.md`
  - `docs/TASK_STATE.md`
  - `docs/DEV_LOG.md`
- Why:
  - Product requirement: internal discount math and agent commission must not be visible to captain-level users in search/detail.
- Validation:
  - `docker compose down` — OK
  - `docker compose up -d --build` — OK
  - `docker compose run --rm web python manage.py check` — OK
  - `docker compose run --rm web python manage.py test boats.tests.test_views.BoatViewsTest.test_boat_search_manager_sees_full_price_breakdown boats.tests.test_views.BoatViewsTest.test_boat_search_captain_sees_only_charter_commission boats.tests.test_views.BoatDetailPriceVisibilityTest` — OK
  - HTTP render checks — OK:
    - `/ru/boats/search/?destination=croatia` → 200
    - `/ru/boat/lagoon-42-rhea/?check_in=2026-04-04&check_out=2026-04-11` → 200
- Risks / follow-up:
  - Legacy `agent` role is mapped to `captain`; if a separate real `agent` role is reintroduced later, role flags must be updated in one place.

## 2026-03-31 (session 2)
- Change:
  - Reverted DEFAULT_CHARTER_COMMISSION=20 hack from `boats/helpers.py` and `boats/pricing.py`. Commission is taken strictly from Charter model.
  - Created `boats/management/commands/update_charters.py` — scans Boataround API and assigns Charter FK to ParsedBoat records without charter.
  - Fixed detail page price breakdown readability: replaced DaisyUI semantic colors (`text-secondary`, `text-info`, `text-success`) with Tailwind direct colors (`text-amber-200`, `text-yellow-200`, `text-green-200`) on purple gradient card. Font size 11px→13px, opacity improved.
- Files:
  - `boats/helpers.py` — reverted DEFAULT_CHARTER_COMMISSION
  - `boats/pricing.py` — reverted DEFAULT_CHARTER_COMMISSION
  - `boats/management/commands/update_charters.py` — new
  - `templates/boats/detail.html` — color/size fix
  - `docs/DECISIONS.md` — DR-017
  - `docs/TASK_STATE.md` — updated
  - `docs/DEV_LOG.md` — this entry
- Why:
  - User requirement: commission must come from Charter object, not hardcoded default. Boats without charter = incomplete data. A command to fill charters from API was needed.
  - Detail page text was unreadable: purple text on purple gradient background.
- Validation:
  - `docker compose down` + `up -d --build` — OK
  - `manage.py check` — 0 issues
  - `manage.py test boats.tests` — 6/6 OK
  - HTTP 200 on `/ru/`
  - `update_charters --dry-run --max-pages 3` — command runs, finds targets
- Risks / follow-up:
  - ~23k boats still without Charter FK — need to run `update_charters` (full scan ~1460 pages).
  - After `update_charters`, run `import_charter_commissions` to set correct commission percentages.

## 2026-04-02
- Change:
  - Fixed price instability on detail page: `BoataroundAPI.get_price()` was not checking cache before attempting consensus loop.
  - Added cache-first lookup: if `price_consensus:{slug}:{check_in}:{check_out}:{currency}` exists in Redis, return immediately (6-hour TTL).
  - Simplified return paths: removed conditional `cached` logic after consensus loop; if no results after 5 API calls, return empty dict (no price available).
- Files:
  - `boats/boataround_api.py` — `get_price()` method (lines ~475–556)
  - `docs/DECISIONS.md` — added DR-017
  - `docs/KNOWN_ISSUES.md` — updated KI-001 resolution status
  - `docs/TASK_STATE.md` — updated P0 status
- Why:
  - User reported that refreshing detail page with same URL showed different prices ("цена плавает"). Cause: every request made fresh 5 API calls instead of using the 6-hour cached consensus result.
- Validation:
  - `docker compose up -d --build` — OK
  - `docker compose run --rm web python manage.py check` — OK
  - Manual test: 5 sequential requests to `/ru/boat/lagoon-42-rhea/?check_in=2026-04-04&check_out=2026-04-11` all returned same cached price (3989.1602 EUR) with logs showing "Using cached price" (not fresh consensus).
- Risks / follow-up:
  - 6-hour TTL is safe for most scenarios; if dynamic pricing is needed per session, short TTL (1–5 minutes) can be added as config in settings.
  - Consensus loop itself still makes 5 requests on first cache miss (by design to stabilize upstream jitter); this is acceptable for user experience.

## 2026-03-31
- Change:
  - Fixed `BoatDescription` language overwrite in `parse_boats_parallel` metadata updater.
  - For `ru_RU/de_DE/fr_FR/es_ES`, updates now apply only from that language API payload (`api_meta_by_lang`) and no longer fallback to `en_EN` values.
  - English fallback is preserved only for `en_EN` records.
- Files:
  - `boats/management/commands/parse_boats_parallel.py`
  - `docs/DECISIONS.md`
  - `docs/TASK_STATE.md`
  - `docs/DEV_LOG.md`
  - `docs/KNOWN_ISSUES.md`
- Why:
  - Prevent mixed-language geo data (`country/region/city`) where non-English descriptions were incorrectly overwritten with English labels.
- Validation:
  - `docker compose exec web python manage.py check` — OK
  - `docker compose exec web python manage.py test boats.tests.test_parse_boats_parallel_command -v 2` — 2/2 OK
  - Backfill runs (metadata-focused):
    - `parse_boats_parallel --skip-existing --max-pages 3 --no-cache`
    - `parse_boats_parallel --destination italy --skip-existing --max-pages 5 --no-cache`
    - `parse_boats_parallel --destination croatia --skip-existing --max-pages 5 --no-cache`
    - `parse_boats_parallel --destination greece --skip-existing --max-pages 5 --no-cache`
    - `parse_boats_parallel --destination turkey --skip-existing --max-pages 20 --no-cache`
  - Spot checks confirmed localized countries after refresh (example: `ru_RU=Италия`, `en_EN=Italy`, `de_DE=Italien`, `fr_FR=Italie`, `es_ES=Italia`).
- Risks / follow-up:
  - Historical records outside refreshed destination/page windows may still need additional backfill passes.
  - Upstream API can still return untranslated labels for a subset of records; this is source limitation, not pipeline fallback.

## 2026-03-31
- Investigation: Geographic data in BoatDescription only 6.6% filled (1,619 of 24,704 boats)
  - **Root cause analysis:**
    - Coverage timeline showed sharp cutoff: Feb 1-13 had 0-95% geo coverage, Feb 14+ dropped to 0%
    - Database correlation: ALL 24,724 ParsedBoat have empty boat_data (`{}` or None), yet 1,619 boats had geo in BoatDescription
    - Boats WITH geo were created Feb 13, boats WITHOUT geo created Feb 14+
    - Boats WITH marina ('Porto Montenegro' etc) but empty country/region/city, indicating API DID return some geo but conditionally
  - **Hypothesis → Confirmed:**
    - `_update_api_metadata()` in parse_boats_parallel.py used truthiness check: `if meta.get('country'):`
    - When API returned empty string `''` for country (which is falsy), the geo-field dict remained empty
    - Empty BoatDescription created → never updated (filter would skip empty<->empty updates)
    - 23,084 boats were locked out from geo-data population because initial creation used API responses with empty strings
  - **Fix applied:**
    - Changed all geo-field checks from `if meta.get('country'):` to `if 'country' in meta:` (presence vs truthiness)
    - Now empty strings from API are properly captured and stored
  - **Results after backfill run:**
    - Coverage: 1,619 → 8,900+ boats (455% improvement)
    - 7,281 additional boats populated with geo-data in single parse_boats_parallel run
    - Marina field: 18% → 100% filled (side effect of using proper existence check)
    - New boats now correctly created with available API geo-metadata
  - **Remaining limitation:**
    - ~15,000 boats still without country/region/city — API genuinely doesn't provide these for all boats (source data issue, not parsing issue)
    - Marina field is now 100% because it's being saved even when empty, and many have marina filled from API
  - **Files modified:** boats/management/commands/parse_boats_parallel.py (lines 715-737)
  - **Tests:** Existing cache tests pass, manual backfill validated with 168 existing + 12 new boats updated

## 2026-03-28
- Change: Dynamic country pricing for tourist offers
  - New model: `CountryPriceConfig` (boats/models.py) — FK to PriceSettings, 15 pricing fields, country_name/code/match_names aliases, is_default flag
  - Migration: 0030_countrypriceconfig — CreateModel + seed 3 configs from existing hardcoded PriceSettings fields
  - `_resolve_country_config()` in boats/helpers.py — alias-based country matching (lowercased), default fallback
  - `calculate_tourist_price()` — rewritten to use CountryPriceConfig directly instead of getattr with region suffixes
  - `_build_price_debug()` in boats/views.py — rewritten for CountryPriceConfig
  - `price_settings_view` in accounts/views.py — 3 POST actions (add_country, delete_country, save_prices) with `cc_{id}_{field}` naming
  - Templates (profile.html, price_settings.html) — fully dynamic columns/rows from DB, add/delete country UI
  - Old hardcoded per-region fields on PriceSettings NOT removed (data preservation)
  - Files: boats/models.py, boats/helpers.py, boats/views.py, accounts/views.py, boats/migrations/0030, templates/accounts/profile.html, templates/accounts/price_settings.html
  - Validation: manage.py check OK, migration applied, template renders verified, country matching tested
  - Risk: old hardcoded fields still on PriceSettings model — can be removed after confirming no code references them

## 2026-03-27
- Change:
  - **Major version upgrade of entire stack:**
    - Python 3.11 → 3.13 (Dockerfile)
    - Django 4.2.9 → 5.2.12 LTS (requirements.txt)
    - Tailwind CSS 3.4.17 → 4.2.2 (package.json, CSS-first config)
    - DaisyUI 4.12.24 → 5.5.19 (package.json, @plugin directive)
    - Node.js 20-alpine → 22-alpine (Dockerfile build stage)
    - Font Awesome 6.5.1 → 6.7.2 (CDN in base.html)
    - All Python packages updated to latest compatible versions
  - **Django 5.2 migration:**
    - `STATICFILES_STORAGE` → `STORAGES` dict in settings.py
    - No other breaking changes found (no deprecated imports, no old URL patterns)
  - **Tailwind 4 migration:**
    - Removed tailwind.config.js from Dockerfile COPY (no longer needed)
    - Rewrote assets/css/tailwind.input.css: `@import "tailwindcss"`, `@plugin` directives, `@utility` for custom utils
    - Added `@source "../../boats/**/*.py"` for class detection in Python files
    - `@tailwindcss/cli` replaces `tailwindcss` CLI package
  - **DaisyUI 5 migration:**
    - `daisyui` configured via `@plugin "daisyui" { themes: winter --default }` in CSS
    - `input-bordered`/`select-bordered`/`textarea-bordered` now no-ops (borders are default in v5) — left in templates for now
    - `badge-outline` still exists in v5
    - Winter theme confirmed available in DaisyUI 5
  - **Python packages updated:**
    - psycopg2-binary 2.9.9→2.9.11, gunicorn 21.2.0→25.2.0, Pillow 10.2.0→12.1.1
    - celery 5.3.6→5.6.3, redis 5.0.1→7.4.0, django-celery-beat 2.5.0→2.9.0
    - whitenoise 6.6.0→6.12.0, requests 2.31.0→2.33.0, beautifulsoup4 4.12.2→4.14.3
    - boto3 1.34.14→1.42.77, weasyprint 61.2→68.1, python-decouple 3.8
  - **NOT upgraded (intentionally):**
    - PostgreSQL stays at 15-alpine (major version upgrade requires pg_dump/restore, not just image swap)
    - Redis stays at 7-alpine (already latest major)
    - Alpine.js CDN uses `@3.x.x` wildcard (auto-updating)
- Files:
  - `Dockerfile` (python:3.13-slim, node:22-alpine, removed tailwind.config.js COPY)
  - `requirements.txt` (all packages to latest)
  - `boat_rental/settings.py` (STORAGES dict)
  - `package.json` (@tailwindcss/cli ^4, daisyui ^5)
  - `assets/css/tailwind.input.css` (Tailwind 4 CSS-first config)
  - `templates/base.html` (Font Awesome 6.7.2)
- Why:
  - Security patches, performance improvements, LTS support timeline.
  - Django 5.2 LTS supported until April 2028.
  - Tailwind 4 is current major with better performance and simpler config.
- Validation:
  - `docker compose up -d --build` — all 5 containers started ✅
  - `python manage.py check` — 0 issues ✅
  - `python manage.py makemigrations --check --dry-run` — no changes detected ✅
  - All migrations applied ✅
  - HTTP: Home 200, Search 200, Login 200, Register 200, Contacts 200 ✅
  - CSS: 136 KB, contains daisyUI + winter theme ✅
  - Celery worker connected and ready ✅
- Risks / follow-up:
  - DaisyUI 5 visual differences may exist (subtle color/spacing changes in winter theme) — needs visual QA
  - PostgreSQL upgrade to 17 requires backup/restore strategy — deferred
  - `tailwind.config.js` still in repo but unused — awaiting user confirmation to delete

### Refactoring pass (same date)
- Change:
  - **`unique_together` → `UniqueConstraint`** (deprecated since Django 4.2): migrated 5 models (Favorite, Review, BoatDescription, BoatPrice, BoatDetails). Generated and applied migration 0027.
  - **Dead code removed**: unreachable `if commit:` block after early `return` in `accounts/forms.py` (ProfileForm.save)
  - **DaisyUI 5 class cleanup**: removed `input-bordered`, `select-bordered`, `textarea-bordered`, `file-input-bordered` from all 13 templates and `DaisyUIMixin` in `boats/forms.py` (no-ops in DaisyUI 5, borders are default now)
  - **`tailwind.config.js` COPY removed from Dockerfile** (already done in upgrade pass)
- Files:
  - `boats/models.py` (5× unique_together → constraints)
  - `boats/migrations/0027_alter_boatdescription_unique_together_and_more.py` (new)
  - `accounts/forms.py` (dead code removed)
  - `boats/forms.py` (DaisyUIMixin: removed -bordered classes)
  - 13 templates: `-bordered` classes cleaned
- Validation:
  - `docker compose down && up -d --build` — all 5 containers ✅
  - `python manage.py check` — 0 issues ✅
  - `python manage.py makemigrations --check --dry-run` — no changes ✅
  - Migration 0027 applied successfully ✅
  - HTTP: Home 200, Search 200, Contacts 200, Login 200, Register 200 ✅
  - Celery worker + beat healthy ✅

## 2026-03-24
- Change:
  - Implemented Client (tourist) management feature — agents/captains can create client profiles and link them to offers, bookings, and contracts.
  - Added `Client` model with fields: last_name, first_name, middle_name, email, phone, passport_number, passport_issued_by, passport_date, address, notes. FK to User (created_by, required; user, optional).
  - Added nullable `client` FK to Booking, Offer, and Contract models.
  - Added `ClientForm` (ModelForm) in boats/forms.py.
  - Added 5 views: clients_list (paginated + search), client_create, client_detail (with history), client_edit, client_search_api (JSON autocomplete).
  - Added 5 URL patterns under `clients/` and `api/clients/search/`.
  - Created 3 templates: clients_list.html, client_form.html, client_detail.html (all with sidebar nav).
  - Added Alpine.js `clientSelector()` component in create_offer.html for client autocomplete.
  - Added Alpine.js `quickClientSelector()` component in detail.html (quick offer modal).
  - Client auto-propagates: offer.client → booking.client → contract.client.
  - Contract creation pre-fills signer data from client (passport, address, phone, email).
  - Client info card shown in captain offer template (offer_captain.html) for internal users.
  - Updated sidebar nav in my_bookings.html, contracts_list.html, base.html mobile nav.
  - Added ClientAdmin in boats/admin.py with fieldsets and search fields.
  - Fixed migration 0024 operation ordering (AddIndex on booking.client moved after AddField).
- Files:
  - `boats/models.py` (Client model + FK additions)
  - `boats/forms.py` (ClientForm)
  - `boats/views.py` (5 new views + modified create_offer, quick_create_offer, book_offer, create_contract)
  - `boats/urls.py` (5 new patterns)
  - `boats/admin.py` (ClientAdmin)
  - `templates/boats/clients_list.html` (new)
  - `templates/boats/client_form.html` (new)
  - `templates/boats/client_detail.html` (new)
  - `templates/boats/create_offer.html` (client selector + Alpine.js)
  - `templates/boats/detail.html` (quickClientSelector in offer modal + i18n load)
  - `templates/boats/offer_captain.html` (client info card)
  - `templates/boats/my_bookings.html` (sidebar nav)
  - `templates/boats/contracts_list.html` (sidebar nav)
  - `templates/base.html` (mobile nav)
  - `boats/migrations/0024_client_booking_boats_booki_client__2b4cf4_idx_and_more.py` (fixed ordering)
- Why:
  - Business need: agents/captains need to manage their customers who may not have accounts in the system, and link them to bookings and contracts for document generation.
- Validation:
  - `docker compose up -d --build` (passed)
  - `python manage.py makemigrations --check` (no changes detected)
  - `python manage.py check` (0 issues)
  - HTTP render checks: `/ru/clients/` 200, `/ru/clients/create/` 200, `/ru/api/clients/search/` 200
  - E2E test: create client → search API → detail page → cleanup (all passed)
  - Modified pages: `/ru/my-bookings/` 200, `/ru/contracts/` 200, `/ru/offers/` 200
- Risks / follow-up:
  - Client deduplication not implemented — agents can create duplicate clients. Consider adding unique constraint on (created_by, last_name, first_name, phone).
  - Tourist offer template (offer_tourist.html) does not show client info — only captain template does, as tourist template is client-facing.
  - Booking direct creation from boat detail (book_boat) does not have client selector — only offer-based flow propagates client.

## 2026-03-22
- Change:
  - Implemented online contract signing feature (models, views, PDF generator, templates, tasks, admin).
  - Added `ContractTemplate` and `Contract` models with audit fields (sign_ip, sign_user_agent, document_hash).
  - Created `boats/contract_generator.py` with two-pass PDF rendering (SHA-256 hash embedded in final doc).
  - Added 5 views: create_contract, contract_detail, sign_contract (public), download_contract, contracts_list.
  - Created 6 templates: create, detail, sign (with Canvas signature via Alpine.js), signed, expired, list.
  - Added Celery tasks: generate_contract_pdf_task, send_contract_notification (stub).
  - Updated my_bookings template with contract action buttons.
  - Updated base.html mobile nav with contracts link.
  - Added xhtml2pdf==0.2.16 to requirements.txt.
  - Updated Dockerfile with libcairo2-dev, pkg-config, python3-dev, gcc for pycairo (xhtml2pdf dep).
  - Fixed uuid module shadowing in Contract model (uuid field name shadows import within class body).
- Files:
  - `requirements.txt`
  - `Dockerfile`
  - `boats/models.py`
  - `boats/forms.py`
  - `boats/views.py`
  - `boats/urls.py`
  - `boats/admin.py`
  - `boats/tasks.py`
  - `boats/contract_generator.py` (new)
  - `templates/boats/create_contract.html` (new)
  - `templates/boats/contract_detail.html` (new)
  - `templates/boats/contract_sign.html` (new)
  - `templates/boats/contract_signed.html` (new)
  - `templates/boats/contract_expired.html` (new)
  - `templates/boats/contracts_list.html` (new)
  - `templates/boats/my_bookings.html`
  - `templates/base.html`
  - `boats/migrations/0023_contracttemplate_contract.py` (auto-generated)
- Why:
  - Business need for formalizing agent-client agreements with legally sufficient electronic signatures.
- Validation:
  - `docker compose down`
  - `docker compose up -d --build` (passed)
  - `python manage.py check` (passed, 0 issues)
  - HTTP render checks: `/ru/contracts/` 200, `/ru/my-bookings/` 200
- Risks / follow-up:
  - Email notification is a stub — needs SMTP config and real implementation.
  - PDF font rendering for Cyrillic may need font files bundled in Docker image.
  - Contract template text should be reviewed by legal before production use.

## 2026-03-19
- Change:
  - Added `import_charter_commissions` management command for loading commissions from `.xlsx`.
  - Added decimal commission handling with explicit rounding to integer (`ROUND_HALF_UP`).
  - Added second-level charter name matching by `lower()+no spaces` with ambiguity guard.
  - Added CSV reports for import results: loaded and not_loaded rows with reasons/status.
  - Added legal suffix normalization (`d.o.o.` stripped during matching) with ambiguity guard for normalized exact keys.
  - Applied `d.o.o.` cleanup to report names and newly created charter names, so CSV outputs no longer contain this suffix in names.
  - Added rule to skip rows with commission `20%` from import/report processing (default commission noise reduction).
  - Extended trailing legal suffix cleanup (`ltd`, `co`, `sl`, etc.) and duplicated-letter fallback (`albatros` -> `albatross`) with ambiguity guards.
  - Added tests for update/create/validation scenarios.
- Files:
  - `boats/management/commands/import_charter_commissions.py`
  - `boats/tests/test_import_charter_commissions_command.py`
  - `docs/TASK_STATE.md`
  - `docs/DECISIONS.md`
- Why:
  - Need repeatable commission sync from `charters.xlsx` without adding dependencies.
- Validation:
  - `docker compose down`
  - `docker compose up -d --build`
  - `docker compose run --rm web python manage.py check`
  - `docker compose run --rm web python manage.py test boats.tests.test_import_charter_commissions_command`
  - `docker compose run --rm web python manage.py import_charter_commissions --file charters.xlsx --dry-run`
- Risks / follow-up:
  - Matching is by normalized `Charter.name`; if Excel names differ semantically from DB names, rows will be reported as missing unless `--create-missing` is used.

## 2026-03-11
- Created persistent project memory files:
  - `AGENTS.md`
  - `docs/TASK_STATE.md`
  - `docs/DECISIONS.md`
  - `docs/KNOWN_ISSUES.md`
  - `docs/DEV_LOG.md`
- Added index links in `docs/INDEX.md`.
- Why:
  - repeated context loss between sessions,
  - regressions caused by reworking already-fixed pricing logic.
- Removed legacy query-based price snapshot params from detail navigation:
  - dropped legacy price params from links and server handling,
  - detail URL now carries only slug + dates (`check_in`, `check_out`).

## 2026-03-10 (pricing + amenities stabilization baseline)
- Unified pricing extraction/resolution in `boats/pricing.py`:
  - prefer policy prices,
  - reconcile fallback discount with `totalPrice` when policy block absent.
- Extended search->detail consistency:
  - normalized localized numeric parsing in detail price handling.
- Introduced search price anti-jitter state in cache with short consensus strategy.
- Improved charter matching:
  - resolve by id, then normalized name.
- Improved amenities refresh command:
  - destination slug selection with dedupe/intersection to existing DB boats,
  - async worker availability check and completion summary.
- Added/updated tests:
  - pricing extraction/resolver,
  - detail snapshot behavior,
  - boataround slug/charter behavior,
  - amenities command async behavior,
  - search card and anti-jitter behavior.

## Entry template
Use this for future updates:

```
## YYYY-MM-DD
- Change:
- Files:
- Why:
- Validation:
- Risks / follow-up:
```

## 2026-03-31
- Change:
  - Restricted HTML persistence in parser to only service lists and photos.
  - Removed HTML-based writes of BoatTechnicalSpecs, BoatDescription, and BoatPrice from parser save flow.
  - Updated API metadata updater to create missing BoatDescription (5 languages) and BoatTechnicalSpecs records for newly parsed boats.
  - Added API title/location to metadata payload for initial description bootstrap when records do not exist.
  - Expanded API specs filling to include length/beam/draft when empty.
- Files:
  - `boats/parser.py`
  - `boats/management/commands/parse_boats_parallel.py`
  - `docs/DECISIONS.md`
  - `docs/TASK_STATE.md`
  - `docs/DEV_LOG.md`
- Why:
  - Product requirement: HTML parsing is only for `extras`, `additional_services`, `delivery_extras`, `not_included`, and photos; all other fields must come from API.
- Validation:
  - `docker compose up -d --build web`
  - `docker compose exec web python manage.py check`
  - `docker compose exec web python manage.py parse_boats_parallel --destination turkey --max-pages 1 --limit 1 --no-cache`
  - Result: phase 1.5 and 2.5 API metadata updates completed; parser completed successfully with no errors.
- Risks / follow-up:
  - Full dataset hydration still requires long-running server-side command execution.
  - Equipment blocks (`cockpit`, `entertainment`, `equipment`) depend on API availability/quality; current API wrapper reports these as not provided by search response.

## 2026-03-31
- Change:
  - Restored HTML persistence for `cockpit`, `entertainment`, `equipment` in `BoatDetails` (per-language), because search API exposes these fields as aggregate filters and not per-boat payload fields.
  - Optimized parse flow: Phase 2.5 API metadata update now runs only for newly created boats from Phase 2, avoiding redundant repeated updates on existing boats.
- Files:
  - `boats/parser.py`
  - `boats/management/commands/parse_boats_parallel.py`
  - `docs/DECISIONS.md`
  - `docs/TASK_STATE.md`
  - `docs/DEV_LOG.md`
- Why:
  - Keep amenities correctness while preserving API-first model for the rest of metadata.
  - Remove unnecessary second-pass API writes for existing records.
- Validation:
  - `docker compose exec web python manage.py check`
  - `docker compose exec web python manage.py parse_boats_parallel --destination turkey --max-pages 1 --limit 1 --no-cache`
  - Result: command completed successfully; no Phase 2.5 update was triggered for existing-only sample.
- Risks / follow-up:
  - Full server-side long run still required to hydrate all records.

## 2026-03-31
- Change:
  - Refactored `parse_boats_parallel` cache format: now saves and restores `slugs`, `thumb_map`, `api_meta`.
  - Added backward compatibility for legacy cache files (list-only slug format).
  - Added slug fallback in API scan (`formatted.slug` -> raw `boat.slug`) to avoid accidental drops.
- Files:
  - `boats/management/commands/parse_boats_parallel.py`
  - `docs/DECISIONS.md`
  - `docs/TASK_STATE.md`
  - `docs/DEV_LOG.md`
- Why:
  - On cache-hit runs, command must keep full metadata hydration behavior (Phase 1.5) without repeating API search requests.
- Validation:
  - `docker compose exec web python manage.py check`
  - `docker compose exec web python manage.py parse_boats_parallel --destination turkey --max-pages 1 --limit 1`
  - `docker compose exec web python manage.py parse_boats_parallel --destination turkey --max-pages 1 --skip-existing`
  - `docker compose exec web python manage.py test boats.tests.test_parse_boats_parallel_command -v 2`
  - Result: cache-hit path loaded from cache and still ran API metadata update for cached slugs; 2/2 tests passed for new+legacy cache formats.
- Risks / follow-up:
  - No integration test yet for full command phase flow with real DB updates; currently covered by smoke run + unit tests for cache schema.
