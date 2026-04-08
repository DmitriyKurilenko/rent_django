# DECISIONS (ADR-lite)

Last updated: 2026-04-08 (Europe/Moscow)

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
- Date: 2026-03-31 (SUPERSEDED 2026-04-08 by DR-029)
- Context: when slug list was loaded from local cache, command skipped API search call and had no `api_meta`/`thumb_map`, so Phase 1.5 metadata updates could be incomplete on cache-hit runs.
- Decision: cache file now persists `slugs`, `thumb_map`, and `api_meta`; cache loader restores all three with backward compatibility for old list-only cache format.
- Consequence: cache-hit runs keep API metadata update behavior consistent with fresh API scan and avoid unnecessary re-fetching.
- **Superseded**: DR-029 removes `api_meta`/`api_meta_by_lang` from cache to prevent OOM.

## DR-029: Per-page DB flush for API metadata during slug collection
- Date: 2026-04-08
- Context: `_collect_slugs_from_api` accumulated `api_meta` (28k×20 fields) + `api_meta_by_lang` (5 langs×28k×6 fields) in memory and serialized to JSON cache per page. On production VPS with limited RAM, Celery worker was killed by SIGKILL (OOM) at page 25 (~450 slugs). Supersedes DR-016.
- Decision: `_collect_slugs_from_api` flushes API metadata to DB per-page via `_update_api_metadata()` and discards page data immediately. Cache file stores only `slugs` + `thumb_map` (lightweight). For mode=api, orchestrator finalizes after collection (no chord). `process_api_batch` kept but no longer dispatched.
- Consequence: memory O(1) per page instead of O(N) catalog. Per-page DB writes add slight overhead (~18 boats/page). If flush fails on a page, that page's metadata lost (logged as error).

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
