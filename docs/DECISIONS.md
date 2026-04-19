# DECISIONS (ADR-lite)

Last updated: 2026-04-19 (Europe/Moscow)

## DR-044: CaptainBrand — кастомный брендинг офферов + S3 для медиа
- Date: 2026-04-19
- Context: Капитаны хотят отправлять клиентам офферы под своим брендом (логотип, название, контакты) вместо Ахой!Rent. Скелет (`branding_mode` на Offer, `can_use_custom_branding()`) существовал как заглушка.
- Decision:
  - Новая модель `CaptainBrand` в `accounts/models.py` (owner FK → User, logo ImageField, primary_color, tagline, phone, email, website, telegram, whatsapp, footer_text, is_default). `save()` обеспечивает единственный is_default на пользователя.
  - FK `brand` (nullable, SET_NULL) на модели `Offer` → `CaptainBrand`.
  - CRUD брендов: `/ru/accounts/brands/` (brand_list, brand_create, brand_edit, brand_delete). Доступ только owner.
  - Живое превью бренда в UI — Alpine.js без серверного рендеринга (watch полей → обновляет mock-заголовок оффера).
  - При создании оффера с `branding_mode=custom_branding` отображается select бренда; default-бренд пользователя подставляется в quick_create_offer автоматически.
  - Оба шаблона (offer_tourist.html, offer_captain.html) рендерят брендинг через два блока в base.html: `{% block brand_header %}` (sticky шапка на всю ширину — градиент бренда, логотип, слоган, кнопки контактов) и `{% block brand_footer %}` (подвал с логотипом, слоганом, footer_text и контактами). Блок цены использует `primary_color` бренда вместо DaisyUI `bg-primary`. В нижней части страницы — крупные кнопки мессенджеров (WhatsApp, Telegram, phone, email). При отсутствии бренда — предупреждение только для создателя.
  - S3 (VK Cloud) подключается условно через env-переменные (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_ENDPOINT_URL`); при отсутствии — FileSystemStorage. Логотипы загружаются в `brands/logos/`.
  - Sidebar LK: ссылка «Бренды» для пользователей с `can_use_custom_branding`.
- Consequence: Капитаны с подпиской advanced или разрешением `custom_branding` могут создавать несколько брендов и выбирать нужный при создании каждого оффера. Публичный оффер отображает лого и контакты вместо Ахой!Rent. S3-хранение логотипов прозрачно — без изменения кода при переключении окружений.

## DR-043: parse_boats is Celery-first; retries and freshness are tracked in ParseJob/ParsedBoat
- Date: 2026-04-15
- Context: local parsing mode and file-based retry lists diverged from real ParseJob state in DB. Operators needed reliable restart semantics and a way to skip recently parsed boats in long-running jobs.
- Decision:
  - `parse_boats --workers N` always dispatches Celery task `run_parse_workers` (local process mode removed).
  - `--retry-errors` reads failed slugs from latest `ParseJob.errors` for selected mode (DB is single source of truth for retries).
  - `--skip-fresh [HOURS]` skips boats only when `last_parse_success=True` and `last_parsed` is inside freshness window (default 24h when value is omitted).
  - Command polls ParseJob for live progress; Ctrl+C only stops local polling and does not cancel Celery execution.
- Consequence: retries are reproducible across restarts/hosts, progress is observable from DB state, and repeated runs can safely avoid reprocessing fresh boats.

## DR-042: Amenities (cockpit/entertainment/equipment) are HTML-owned — saved in all HTML modes, untouched by API mode
- Date: 2026-04-14
- Context: DR-041 incorrectly classified cockpit/entertainment/equipment as API-owned, causing `services_only` to skip them and `mode=api` to clear them. This violated the IRON RULE: HTML parser is the source of truth for all BoatDetails fields including amenities. After running `mode=api` + `mode=html`, all amenity data was lost.
- Decision:
  - Both `services_only` and `all_html` modes save amenities from HTML.
  - API mode does NOT touch BoatDetails amenity fields (cockpit/entertainment/equipment).
  - `_clear_api_unavailable_amenities()` removed from API task pipeline.
  - Only `BoatDescription` and `BoatTechnicalSpecs` ownership differs between modes: descriptions are HTML-only in `all_html`, specs are API-only.
- Consequence: Running `mode=api` → `mode=html` no longer wipes amenities. HTML remains sole source of truth for all BoatDetails fields.

## DR-041: Parse modes are strictly separated to prevent HTML/API source-of-truth mixing
- Date: 2026-04-14
- Context: Team requirement: HTML must be used only in explicitly selected modes. Recurrent confusion came from mixed behavior where HTML parsing could overwrite fields that should come from API.
- Decision:
  - `parse_boats --mode api`: API source-of-truth only (HTML fields are not touched).
  - `parse_boats --mode html`: HTML updates `photos` + `extras` + `additional_services` + `delivery_extras` + `not_included` + `cockpit` + `entertainment` + `equipment`.
  - `parse_boats --mode full`: full HTML profile (legacy behavior), including HTML descriptions/amenities.
  - `parse_boataround_url` now accepts explicit `html_mode` (`services_only` / `all_html`) and all task entry points pass mode explicitly.
  - `run_parse_job` dispatches API page-range tasks only for `mode=api`; `mode=html/full` run only HTML batch tasks.
  - In `services_only`, parser updates photos + 4 service lists + 3 amenity lists (cockpit/entertainment/equipment). Descriptions are NOT saved.
  - API mode does not touch BoatDetails amenity fields. Detail cache keys `boat_data:<slug>:<lang>` are invalidated for touched slugs.
  - `refresh_amenities` command/tasks are deprecated to avoid accidental reintroduction of HTML-derived amenities in API-first flows.
- Consequence: Mode behavior is explicit and deterministic; no hidden cross-mode overwrites. Existing historical data is not globally cleaned automatically; new/updated batches follow the selected mode policy.

## DR-040: Charter company name stripped at presentation layer, not in database
- Date: 2026-04-12
- Context: Boataround.com descriptions end with a sentence naming the charter company (per language/boat type). This is undesirable to display to users but the data itself may be useful internally (e.g., for charter identification or commission mapping).
- Decision: Strip the charter sentence via a Django template filter (`strip_charter_company`) applied at render time. Database `BoatDescription.description` field remains unmodified. Filter uses 17 compiled regex patterns anchored to the end of string (`\Z`).
- Alternatives considered: (1) Strip during parsing/save — rejected because it would destroy potentially useful source data and require re-parsing all boats if the logic changes. (2) DB migration to clean existing data — rejected for same reason plus irreversibility.
- Consequence: Zero data loss. Filter can be updated independently if boataround.com changes sentence formats. New boat types or reformulated sentences require adding new regex patterns.

## DR-039: DaisyUI 5 form pattern — no fieldset/label, no size overrides, theme-native sizing
- Date: 2026-04-12
- Context: DaisyUI 5 under Tailwind v4 does not emit `.fieldset`/`.fieldset-legend` CSS. `.label` is a hint component (nowrap, dim), not a field label. Explicit `-lg` modifiers override the winter theme's `--size-field`/`--size-selector` variables, creating inconsistent sizing.
- Decision: All forms use plain `<div>` wrappers, `text-sm font-semibold` labels, DaisyUI `input`/`select`/`btn` without size modifiers, `text-xs text-error` errors, `text-xs opacity-60` hints. Checkbox/radio labels: `cursor-pointer flex items-center gap-2`. No `form-control`, `label-text`, `label-text-alt`, `class="label"`, `input-lg`, `select-lg`, `btn-lg`.
- Consequence: All 13 templates follow a single consistent pattern. Component sizing governed by theme variables. CSS compat shims removed. See KI-011 for background.

## DR-038: Commission visibility on offer pages reuses existing price visibility flags
- Date: 2026-04-12
- Context: Commission was visible in search and detail pages via `_price_visibility_flags()` (`show_full_price_breakdown` for manager/admin, `show_charter_commission_only` for captain). Offer detail and offers list lacked commission display.
- Decision: Reuse `_price_visibility_flags()` to gate commission on offer pages. Extract `_compute_offer_commission(offer)` from `_build_price_debug()` for independent reuse. For offers list, compute commission in bulk via single DB query with `select_related('charter')` instead of per-offer helper calls. Commission is never shown to tourists/anonymous — the `commission` context variable is only set when visibility flags are true.
- Consequence: Consistent commission visibility rules across all pages (search, detail, offer, offers list). No new permissions needed. Offers list uses optimized bulk query (one SELECT for all offers on the page).

## DR-037: Permission-gated countdown & force-refresh in quick offer modal
- Date: 2026-04-11
- Context: Quick offer creation modal on boat detail page lacked «Обратный отсчёт» and «Обновить данные» checkboxes present in the full create_offer form. Task requirement: countdown visible to captain/assistant/manager/admin; force-refresh visible to manager/assistant/admin only.
- Decision: New permissions `use_countdown` and `use_force_refresh` in the existing Role/Permission system. Template uses `{% if user.profile.can_use_countdown %}` / `{% if user.profile.can_use_force_refresh %}` for conditional rendering. Backend enforces same permission before applying values — if user lacks permission, flag is silently ignored (countdown defaults to False, force_refresh has no effect).
- Consequence: Feature parity between quick and full offer creation. Permission checks on both frontend (visibility) and backend (enforcement) prevent privilege escalation via crafted POST requests.

## DR-036: Comprehensive search filters with comma-separated multi-values
- Date: 2026-04-10
- Context: Search used only 6 basic filters. Boataround API supports 15+ params (sleeps, guests, length, manufacturer, skipper, sail, engineType, cockpit, entertainment, equipment, toilets).
- Decision: Add all supported params. Multi-value checkbox fields (sail, engine_type, cockpit, entertainment, equipment) use `getlist()` + comma-join in view, sent as comma-separated strings to API. Category values corrected to API format (sailing-yacht, motor-yacht, motor-boat, catamaran, gulet, power-catamaran). Amenity checkboxes in collapsible sections using Alpine.js `x-show`.
- Refinement (2026-04-10): `active_*` context variables changed from comma-joined strings to lists. Django `in` operator on strings does substring matching, which could cause false-positive `checked` state on overlapping IDs. Lists ensure exact membership check. Manufacturer input lowercased to match API slug format.
- Consequence: Users can filter by 17 parameters total. Checkbox state persists via `active_*` context variables (lists). Pagination URLs preserve all active filters.

## DR-035: search_by_slug uses `slugs` parameter (plural)
- Date: 2026-04-08
- Context: `BoataroundAPI.search_by_slug()` sent `slug` (singular) as API parameter. Boataround API ignores this unknown parameter and returns 50 default boats. If the target boat isn't among them, `BoatTechnicalSpecs` is never created — offers and detail pages show empty specs.
- Decision: change API parameter from `slug` to `slugs` (plural) — the actual parameter name the API recognizes. Remove hardcoded `limit: 50` (API returns only the matched boat). No other code changes needed.
- Consequence: `search_by_slug` now reliably finds any boat in the catalog. All existing flows (`_ensure_api_metadata_for_boat`, `_ensure_boat_data_for_critical_flow`, `boat_detail_api`) benefit immediately. Boats previously missing specs will get them on next detail/offer view.

## DR-001: Unified pricing pipeline
- Date: 2026-03-10
- Context: prices diverged between search, detail and offers due to duplicate logic.
- Decision: use one resolver in `boats/pricing.py` (`resolve_live_or_fallback_price`) everywhere.
- Consequence: behavior is consistent across entry points; changes must be made in one place.

## DR-002: Canonical source for discount math
- Date: 2026-03-10
- Context: Boataround top-level `totalPrice/discount` may differ between identical requests.
- Decision: prioritize `policies[0].prices` fields for price and discounts.
- Consequence: top-level fields are treated as fallback-only and may be reconciled to match total.

## DR-003: No stale per-date price cache as source of truth
- Date: 2026-03-10
- Context: old cached price snapshots caused incorrect detail/offers prices.
- Decision: fetch live quote per request dates; use DB fallback only when API unavailable.
- Consequence: less stale data risk; higher dependency on API latency and timeout handling.

## DR-004: Search -> detail snapshot transfer
- Date: 2026-03-10
- Context: user sees one price in search card and another on detail during close navigation.
- Decision: do not pass price snapshot params in URL; pass only dates (`check_in`, `check_out`) and recalculate on detail.
- Consequence: detail page is protected from stale/incorrect client-side price params.

## DR-005: Charter resolution fallback by normalized name
- Date: 2026-03-10
- Context: API may send unknown/rotating charter IDs while charter name is stable.
- Decision: resolve charter by `charter_id`, then by normalized `charter` name cache.
- Consequence: commissions remain more stable when IDs drift.

## DR-006: Search pagination derived from actual payload shape
- Date: 2026-03-10
- Context: API can ignore requested `limit`; `totalPages` from raw response may be misleading.
- Decision: compute `totalPages` from `total` and actual boats returned per page.
- Consequence: UI pagination aligns better with observed page size; must keep compatibility for wrapper/array response variants.

## DR-007: Amenities extraction policy
- Date: 2026-03-10
- Context: details page included unavailable amenities and had inconsistent language data.
- Decision: parse `<amenities>` component and persist only items with `is_present=true` for each supported language.
- Consequence: cleaner UI and less noise in equipment/cockpit/entertainment blocks.

## DR-008: Async amenities refresh operational safety
- Date: 2026-03-10
- Context: `refresh_amenities --async` reported no visible results in some runs.
- Decision: command checks active Celery workers, dispatches batches, and can wait with timeout/poll summary.
- Consequence: operator sees deterministic command outcome and partial completion info.

## DR-010: Online contract signing with simple electronic signature (ПЭП)
- Date: 2026-03-22
- Context: agents need a way to formalize agreements with clients through online contract signing.
- Decision: implement simple electronic signature (ПЭП) per Russian 63-ФЗ: canvas-drawn signature + audit log (IP, User-Agent, timestamp, SHA-256 hash). Public UUID-based signing links without authentication.
- Consequence: legally sufficient for agent rental contracts per 63-ФЗ art. 6; no qualified signature infra needed; audit trail stored in Contract model.

## DR-011: xhtml2pdf for PDF generation
- Date: 2026-03-22
- Context: need HTML→PDF for contract documents.
- Decision: use xhtml2pdf==0.2.16 (pure Python, lighter than WeasyPrint). Requires libcairo2-dev system dep in Docker.
- Consequence: Dockerfile updated with cairo dependencies; two-pass rendering embeds SHA-256 hash in final PDF.

## DR-009: Charter commissions import from XLSX without extra dependencies
- Date: 2026-03-19
- Context: commissions must be regularly loaded from `charters.xlsx`, while stack must stay unchanged.
- Decision: implement management command `import_charter_commissions` with native XLSX parsing (`zipfile` + XML), matching charters by normalized `name`.
- Consequence: no new dependency like `openpyxl`; import is deterministic and test-covered; optional creation of missing charters is explicit (`--create-missing`); decimal commissions from XLSX are rounded to integer (`ROUND_HALF_UP`) for `Charter.commission`; matching has second level by `lower()+без пробелов`, plus controlled fallback for duplicated letters (e.g. `Albatros` vs `Albatross`) with ambiguity protection; normalization strips trailing legal suffixes (`d.o.o.`, `ltd`, `co`, `sl`, etc.) and punctuation noise; rows with default commission `20%` are skipped from processing/reports; each run writes two CSV reports (`loaded` / `not_loaded`) for manual audit.

## DR-012: Client entity separate from User
- Date: 2026-03-24
- Context: agents/captains need to track their customers (tourists) who may not have accounts in the system.
- Decision: introduce `Client` model (boats/models.py) as a standalone entity with optional FK to `User`. Nullable FK added to Booking, Offer, and Contract. Client data auto-propagates through the chain: offer→booking→contract.
- Consequence: client is not a Django User; agents manage clients independently; contract forms pre-fill from client passport/contact data; existing data unaffected (all FK fields nullable).

## DR-013: Major stack upgrade — Django 5.2 LTS + Tailwind 4 + DaisyUI 5
- Date: 2026-03-27
- Context: stack was on aging versions (Django 4.2, Tailwind 3, DaisyUI 4, Python 3.11). Need security patches and LTS support.
- Decision: upgrade to Django 5.2.12 LTS (not 6.0), Python 3.13, Tailwind CSS 4.2.2, DaisyUI 5.5.19, Node 22, all Python packages to latest. PostgreSQL stays at 15 (major upgrade needs dump/restore).
- Consequence: Django 5.2 LTS supported until April 2028; Tailwind 4 uses CSS-first config (no tailwind.config.js); DaisyUI 5 has borders by default on inputs (-bordered classes are no-ops); settings.py uses STORAGES dict instead of STATICFILES_STORAGE.

## DR-014: Dynamic country pricing via CountryPriceConfig model
- Date: 2026-03-28
- Context: tourist offer pricing was hardcoded for 3 regions (Turkey/Seychelles/Default) with ~55 fields on PriceSettings. Adding new countries required code changes.
- Decision: introduce `CountryPriceConfig` model (FK to PriceSettings) with 15 pricing fields per country, alias-based matching, and default fallback. Admin can add/edit/delete countries from the price settings UI. Old hardcoded fields on PriceSettings remain (no data deletion) but are no longer read by pricing logic.
- Consequence: unlimited countries supported; `_resolve_country_config()` in helpers.py handles matching by lowercased aliases; templates render dynamically from DB; migration 0030 seeds 3 initial configs from existing hardcoded values.

## DR-015: HTML parsing scope is limited to services and photos
- Date: 2026-03-31
- Context: product requirement is to use HTML parsing only for fields unavailable via API.
- Decision: keep HTML persistence for service lists (`extras`, `additional_services`, `delivery_extras`, `not_included`), detail gallery photos, and per-boat amenities (`cockpit`, `entertainment`, `equipment`) because search API exposes these as aggregate filters, not reliable per-boat values. Treat API as source of truth for descriptions, specs, geo/category/review metadata, charter data, and other non-service fields.
- Consequence: parser save flow stays narrow but preserves amenities correctness; Phase 2.5 API metadata update is restricted to newly created boats from Phase 2 to avoid redundant second-pass updates.

## DR-017: Charter commission source of truth is Charter model only
- Date: 2026-03-31
- Context: 92% of ParsedBoat records had no Charter FK. Attempted fallback with DEFAULT_CHARTER_COMMISSION=20 in pricing layer — user rejected: commission must come from Charter object, boats without charter are incomplete data.
- Decision: pricing layer (`helpers.py`, `pricing.py`) uses charter.commission exclusively; if no charter, commission=0. New `update_charters` management command fills missing charters from API. Existing `import_charter_commissions` sets commission percentages from XLSX.
- Consequence: two-step workflow to fill commissions: (1) `update_charters` — assigns Charter FK from API, (2) `import_charter_commissions` — sets commission % from XLSX. Boats without charter show no commission breakdown.

## DR-016: parse_boats_parallel cache stores API metadata payload
- Date: 2026-03-31 (SUPERSEDED 2026-04-08 by DR-034)
- Context: when slug list was loaded from local cache, command skipped API search call and had no `api_meta`/`thumb_map`, so Phase 1.5 metadata updates could be incomplete on cache-hit runs.
- Decision: cache file now persists `slugs`, `thumb_map`, and `api_meta`; cache loader restores all three with backward compatibility for old list-only cache format.
- Consequence: cache-hit runs keep API metadata update behavior consistent with fresh API scan and avoid unnecessary re-fetching.
- **Superseded**: DR-034 moves all heavy work out of orchestrator into disposable Celery tasks.

## DR-034: Disposable Celery tasks for parse_boats on 1 GB RAM VPS
- Date: 2026-04-08
- Context: Production VPS has only 1 GB RAM. Original code (OOM at page 25) and per-page flush fix (OOM at page 155) both failed — Python memory fragmentation from ORM operations in a long-running task caused RSS to grow unboundedly. Supersedes DR-016.
- Decision: Orchestrator (`run_parse_job`) is now lightweight — collects slugs EN-only (~11 MB for 28k boats), no multilingual fetches, no DB writes, no ThreadPoolExecutor. All heavy work dispatched as disposable `process_api_page_range` tasks (5 pages each, ~90 boats). Each task: fetches 5 languages, calls `_update_api_metadata()` with per-page flush + `gc.collect()`, then exits. Worker process recycled by `--max-tasks-per-child=100`. `process_api_batch` kept for backward compat but no longer dispatched.
- Updated 2026-04-09: reduced PAGES_PER_RANGE from 20 to 5 after production OOM at Job:16 (320 pages accumulated). Fixed `totalPages` inflation in `boataround_api.py` (used `len(boats)` instead of `limit`).
- Consequence: Peak memory ~180 MB (orchestrator: ~160 MB base + 11 MB slugs; each page-range task: ~2 MB peak per page). Safe for 1 GB VPS. Trade-off: more Celery tasks dispatched (~298 for full catalog), slight scheduling overhead.

## DR-024: Search/detail price breakdown is role-scoped
- Date: 2026-03-31
- Context: search and detail pages exposed full internal pricing breakdown to roles that should only see charter commission.
- Decision: full price breakdown is visible only to `manager`, `admin`, and `superadmin`; `captain` sees only charter commission percent and amount; anonymous and tourist roles see no breakdown.
- Consequence: internal discount math and agent commission stay hidden from captain-level users, while manager/admin flows keep full pricing debug.

## DR-025: Cache-first lookup in BoataroundAPI.get_price()
- Date: 2026-04-02
- Context: price inconsistency symptom: user refreshes detail page with same URL (identical slug, check_in, check_out) and sees different prices. Root cause: `get_price()` consensus algorithm did NOT check Redis cache before making 5 API requests, causing every call to fetch fresh data and potentially resolve to different consensus values.
- Decision: check cache key `price_consensus:{slug}:{check_in}:{check_out}:{currency}` at function start and return immediately if found (6-hour TTL). Only perform consensus loop if cache miss.
- Consequence: price is stable for 6 hours per date range; second page refresh shows cached value in logs (INFO "Using cached price"); eliminates upstream jitter symptom for users within cache window; minimal latency improvement (saves 5 sequential API calls on hit).

## DR-026: geo-data population uses presence check instead of truthiness check
- Date: 2026-03-31
- Context: After analysis, only 1,619 boats (6.6%) had `country/region/city` in BoatDescription despite API providing these fields for ~8,000+ boats. Root cause: `_update_api_metadata()` was using `if meta.get('country'):` which fails when API returns empty string `''` because empty string is falsy in Python.
- Decision: changed all geo-field checks from truthiness `if meta.get('country'):` to presence checks `if 'country' in meta:`. This way, even empty strings from API are properly captured and stored in database.
- Consequence: geo-data coverage improved from 1,619 boats (1.3%) to 8,900+ boats (7.2%) in single backfill run. New boats created via parse_boats_parallel now always receive available API geo-metadata. Remaining ~15,000 boats without geo-data genuinely lack it in the API (not a parsing/storage issue, but a source data limitation).

## DR-027: no cross-language fallback for BoatDescription geo fields
- Date: 2026-03-31
- Context: On cache-hit and partial metadata runs, some boats received `en_EN` geo values copied into `ru_RU/de_DE/fr_FR/es_ES` when localized API payload was missing for those languages.
- Decision: in `_update_api_metadata()`, update `BoatDescription` per-language only from that language payload; keep English fallback only for `en_EN`; do not copy English geo values to non-English records.
- Consequence: new metadata updates preserve localization correctness; stale mixed-language records require destination-scoped backfill runs to be corrected in DB.

## DR-028: Hidden service slugs filtered at view + template level
- Date: 2026-04-04
- Context: "Гибкая отмена / 8% от полной стоимости" (slug: `flexible-cancellation`) appears in additional_services from parser but should not be shown to users.
- Decision: `HIDDEN_SERVICE_SLUGS` set in `helpers.py` filters additional_services in 3 view functions + 2 templates. Double layer: view filters for new data, template guards for existing offer snapshots in `boat_data` JSON.
- Consequence: hidden services are suppressed everywhere without modifying parser output or stored data. Adding new hidden slugs requires only updating the set.

## DR-019: Celery-batched parsing via parse_boats command
- Date: 2026-04-01
- Context: existing `parse_boats_parallel` runs synchronously in Django process using ThreadPoolExecutor, blocking the management command for hours and risking OOM/timeout on large catalogs. No persistent report storage — output lost if terminal closed.
- Decision: new `parse_boats` management command dispatches work to Celery via `ParseJob` model + batch tasks (`process_api_batch`, `process_html_batch`). Orchestrator task `run_parse_job` collects slugs from API, splits into batches, dispatches to Celery, and aggregates results. Three modes: `api` (metadata only), `html` (full HTML parse), `full` (both). Reports stored in DB (`summary`, `detailed_log`, `errors` JSON).
- Consequence: server not blocked during parsing; progress queryable via `--status`; network retries (5 attempts with exponential backoff) prevent single DNS/timeout failure from aborting entire job; old commands untouched for backward compatibility.

## DR-020: update_charters network retry
- Date: 2026-04-01
- Context: `update_charters --all` crashed on page 806/1471 due to transient DNS resolution failure (`Failed to resolve 'api.boataround.com'`). No retry logic — entire remaining catalog unprocessed.
- Decision: added 5-retry loop with exponential backoff (10s→30s→60s→2min→5min) per API page. Catches `ConnectionError`, `Timeout`, `OSError`. On exhausted retries, page is skipped (not aborted). Unexpected exceptions also skip page with error log.
- Consequence: transient network issues no longer abort full-catalog scans; worst case = a few skipped pages instead of 665 unprocessed pages.

## DR-021: Agent commission is configurable via PriceSettings
- Date: 2026-04-01
- Context: agent commission was hardcoded as `charter_commission / 2` in pricing.py and _build_price_debug. Business needs flexibility to change agent share without code changes.
- Decision: added `agent_commission_pct` field to PriceSettings (default=50, meaning 50% of charter commission). Used in pricing.py, views.py (_build_price_debug), and displayed in captain profile.
- Consequence: agent commission adjustable via /price-settings/ UI; captains see only their commission, not full charter commission.

## DR-022: Captain price visibility restricted
- Date: 2026-04-01
- Context: captains saw full charter commission (%) and price breakdown in offers, exposing internal pricing structure.
- Decision: (1) offer price_debug hidden from captains — only manager/admin/superadmin see it. (2) search/detail: captain sees agent commission amount only, not charter % or charter name. Manager/admin see full breakdown.
- Consequence: internal pricing math is no longer exposed to captain-level users.

## DR-023: Detail/offer full parsing order (API → HTML)
- Date: 2026-04-02
- Context: detail page called only HTML parser for missing boats. BoatTechnicalSpecs (source-of-truth: API) was never created, causing RelatedObjectDoesNotExist crash.
- Decision: `_ensure_boat_data_for_critical_flow` now runs API metadata first (specs, charter, descriptions), then HTML (photos, services, amenities). Uses `_update_api_metadata` from `parse_boats_parallel`. Management commands keep separate modes (api/html/full); all other flows always do full parsing.
- Consequence: any boat opened via detail/offer gets complete data from both sources; specs created from API before HTML rendering needs them.

## DR-024: Permission-based role system (Variant B)
- Date: 2026-04-06
- Context: CharField `role` на UserProfile с 5 жёстко заданными ролями. 15 `can_*()` методов с хардкодом. Нужна роль «Ассистент» и гибкое назначение прав.
- Decision: Новые модели `Permission(codename, name)` + `Role(codename, name, permissions M2M, is_system)`. UserProfile.role_ref → FK на Role. Свойство `role` (property) возвращает `role_ref.codename`, обеспечивая полную обратную совместимость с `profile.role == 'captain'` в views/templates. Все `can_*()` делегируют в `has_perm(codename)` с кэшем `_perm_cache`.
- Consequence: 6 системных ролей (tourist, captain, assistant, manager, admin, superadmin), 14 разрешений. Новые роли можно создавать через админку без изменения кода. Все 56+ прямых сравнений `role == 'string'` в views/templates продолжают работать.

## DR-033: Contract signing token-based download
- Date: 2026-04-07
- Context: After OTP signing, signer is not authenticated. `download_contract` requires `@login_required`, so "Скачать PDF" caused 404 via broken `LOGIN_URL`. Also `LOGIN_URL = '/login/'` didn't match i18n routes.
- Decision: (1) Fix `LOGIN_URL` to named URL `'login'` for i18n compatibility. (2) New `download_signed_contract` view — serves PDF by validating `sign_token` + `status='signed'` without auth. (3) `contract_signed.html` links to token-based endpoint.
- Consequence: Signers can download PDF immediately after OTP signing. Existing auth-based `download_contract` for staff is unchanged.

## DR-032: Centralized notification dispatch (boats/notifications.py)
- Date: 2026-04-07
- Context: Notification logic (in-app + Telegram) was inline in views.py with inline imports — PEP violation, mixed concerns.
- Decision: Separate module `boats/notifications.py` with `notify_new_booking()` and `notify_status_change()`. Uses `bulk_create()`. Views call one-liner functions.
- Consequence: Clean separation of concerns. Adding new notification channels (email, SMS) requires changes only in notifications.py.

## DR-031: Booking option status + in-app notifications
- Date: 2026-04-07
- Context: Assistant needs to set bookings "на опцию" with an expiry date and notify the responsible person (booking creator) about status changes.
- Decision: Add `option` status to Booking.STATUS_CHOICES + `option_until` DateField. New `Notification` model in `boats/models.py`. Context processor provides global unread count. Permission: `can_confirm_booking()`.
- Consequence: Status changes create in-app notifications. Bell icon with badge in navbar. No email/SMS — in-app only for now.

## DR-030: extra_discount_max fallback is fail-closed (0.0)
- Date: 2026-04-06
- Context: `calculate_final_price_with_discounts` had `except: extra_discount_max = 5` — when PriceSettings was unavailable (e.g. in tests), a hidden 5% discount was silently applied, making test assertions unpredictable.
- Decision: change fallback to `0.0` (fail-closed). If PriceSettings cannot be loaded, no extra discount is applied.
- Consequence: pricing in degraded mode is conservative (no hidden discounts); test environment doesn't depend on PriceSettings existing in DB for correct assertions.

## DR-029: Views/templates use can_*() methods instead of hardcoded role strings
- Date: 2026-04-06, extended 2026-04-07
- Context: Despite permission system (DR-024), 28+ locations in views/templates still used hardcoded `role == 'manager'`/`role in ('manager', 'superadmin')`. Bugs: delete_booking excluded superadmin, offers only visible to admin, client views missed admin, book_offer excluded admin/superadmin.
- Decision: Phase 1 (04-06): Replace 15 critical checks. Phase 2 (04-07): Add 6 new granular permissions (`view_price_breakdown`, `assign_managers`, `delete_bookings`, `delete_offers`, `create_contracts`, `view_all_clients`) with migration 0008. Replace ALL remaining hardcoded checks (25+ in Python, 8 in templates) with `can_*()` and `is_*` properties. Only exception: profile badge coloring (display logic).
- Consequence: All role-based access uses permission system. New roles/permissions can be managed via admin without code changes. 5 bugs fixed (expanded access for superadmin, admin, manager where previously missing).
- Consequence: Any role with `view_all_bookings` permission automatically gets access to all offers, bookings, contracts, clients. Destructive actions (delete_offer, delete_booking) remain restricted to admin/superadmin. New roles added via admin will work correctly if given appropriate permissions.
