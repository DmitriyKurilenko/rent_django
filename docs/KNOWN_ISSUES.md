# KNOWN ISSUES

Last updated: 2026-04-12 (Europe/Moscow)

## KI-011: DaisyUI 5 fieldset/fieldset-legend CSS not generated in current build
- Severity: low (downgraded from medium — all templates migrated away from affected classes)
- Area: CSS build / DaisyUI 5 + Tailwind v4 plugin integration
- Symptom: `.fieldset` and `.fieldset-legend` class rules are NOT present in built `styles.css`. Using `<fieldset class="fieldset">` results in native browser fieldset rendering (borders, margin, padding, min-inline-size: min-content).
- Root cause: DaisyUI 5 plugin under Tailwind v4 (`@plugin "daisyui"`) does not emit fieldset component CSS. Only `fieldset:disabled .input`/`.select` selectors exist.
- Workaround: Do NOT use `<fieldset class="fieldset">` or `<legend class="fieldset-legend">` in templates. Use plain `<div>` wrappers with Tailwind utilities for form field grouping.
- Also affected: `.label` class IS emitted but as hint/description component (`white-space: nowrap`, 60% transparent color) — not suitable for prominent field labels. Use `text-sm font-semibold` instead.
- Status (2026-04-12): All templates fully migrated to DaisyUI 5 pattern. CSS compat shims removed. No template uses `form-control`, `label-text`, `label-text-alt`, or `class="label"` for form labels. Issue is no longer a practical blocker.
- Action needed: Investigate DaisyUI 5 version compatibility with Tailwind v4 plugin system. May require DaisyUI update or explicit component import.

## KI-007: parse_boats OOM kill during slug collection (RESOLVED 2026-04-08)
- Severity: critical (RESOLVED)
- Area: boats/tasks.py — _collect_slugs_from_api / run_parse_job
- Symptom: Celery worker killed by SIGKILL (signal 9) during slug collection phase on 1 GB RAM VPS. Job stuck in "Сбор slug'ов" forever.
- Root cause (v1): Unbounded memory accumulation of api_meta dicts. Fix (per-page flush): still OOM at page 155 due to Python arena fragmentation.
- Root cause (v2): ORM operations in a single long-running task fragment Python's memory arena. RSS grows unboundedly over 155+ pages.
- Fix (v2): Disposable Celery tasks architecture. Orchestrator only collects slugs (EN-only, ~11 MB). All heavy work in short-lived `process_api_page_range` tasks. Worker recycled by `--max-tasks-per-child=100`.
- Fix (v3, 2026-04-09): `PAGES_PER_RANGE: 20 → 5` (v2 still OOM at Job:16). Fixed `totalPages` inflation in `boataround_api.py`. See DR-034.
- Fix (v4, 2026-04-13): `PAGES_PER_RANGE: 5 → 3`, `--max-tasks-per-child: 100 → 20`, added `db.reset_queries()` + `db.close_old_connections()` + `gc.collect()` after each task. v3 still OOM at Job:30 with 5 languages per page.

## KI-001: Upstream price jitter for identical requests
- Severity: medium (PARTIALLY RESOLVED 2026-04-02)
- Area: search/detail/offers pricing
- Symptom: same slug + same dates may return different `totalPrice`/`discount` from Boataround.
- Notes:
  - observed directly in API payload samples,
  - top-level fields are less stable than `policies[0].prices`.
- Current mitigation:
  - canonical extraction from policy prices,
  - detail page resolves price server-side for requested dates,
  - **[FIXED 2026-04-02]** `get_price()` now checks Redis cache first (6-hour TTL per date range) before attempting consensus loop; eliminates symptom for users within cache window.
- Remaining risk: upstream can still return different totalPrice on first cache miss (within 5-request consensus window); risk is moved from every page refresh to once per 6 hours per date range. If shorter stability window needed, TTL config can be adjusted in settings.

## KI-002: Search anti-jitter consensus behavior is partial
- Severity: medium
- Area: `boat_search` display smoothing
- Symptom: when no confirmed baseline exists, first new candidate may still be shown immediately.
- Current mitigation: confirmation state with candidate hit tracking in cache.
- Remaining risk: user can still observe price movement on initial requests.

## KI-003: External timeout on price endpoint
- Severity: medium
- Area: boat detail / offer creation / booking
- Symptom: `Read timed out` from `api.boataround.com`.
- Current mitigation:
  - retries in API client,
  - unified DB fallback when live quote unavailable.
- Remaining risk: fallback may differ from current live market price.

## KI-004: Charter ID instability in upstream payload
- Severity: medium
- Area: commission calculation
- Symptom: charter id may be empty/unknown while charter name is present.
- Current mitigation: fallback matching by normalized charter name.
- Remaining risk: ambiguous names can map incorrectly without curated mapping rules.

## KI-005: Non-critical noisy logs for missing Apple touch icons
- Severity: low
- Area: HTTP logs
- Symptom: repeated 404 for `/apple-touch-icon.png` and `/apple-touch-icon-precomposed.png`.
- Current mitigation: none (informational only).

## KI-006: `/health/` returns 301 in some setups
- Severity: low
- Area: infra monitoring
- Symptom: healthcheck requests report redirect instead of direct 200.
- Current mitigation: not blocking app traffic; keep in monitor expectations.

## KI-007: Geographic data (country/region/city) partly absent in BoatDescription
- Severity: medium
- Area: boats data quality / BoatDescription model
- Symptom: ~93% of boats lacked country/region/city in BoatDescription despite API providing these fields.
- Root cause (FIXED 2026-03-31): `_update_api_metadata()` used truthiness check `if meta.get('country'):` which evaluated to False when API returned empty string `''` for un-geolocated boats.
- Fix applied: Changed to `if 'country' in meta:` in parse_boats_parallel.py. One-time backfill raised coverage from 1,619 (1.3%) to 8,900 (7.2%) boats.
- Remaining limitation: ~15,000 boats (~61%) still have no geo-data — API genuinely does not provide country/region/city for these boats (source data limitation, not a parsing bug).
- Action needed: Run `parse_boats_parallel --no-cache --destination all` on production server to maximally backfill from fresh API scan. Repeat periodically as API catalog expands.

## KI-008: Historical rows with English geo labels in non-English descriptions
- Severity: medium
- Area: localization quality / `BoatDescription`
- Symptom: part of historical boats had `ru_RU/de_DE/fr_FR/es_ES` country/region/city equal to English labels (e.g. `Italy`, `Croatia`).
- Root cause (FIXED 2026-03-31): metadata updater used English fallback for non-English records when per-language API payload was missing in current run.
- Fix applied: updater now uses strict per-language payload for non-English records and keeps fallback only for `en_EN`.
- Remaining limitation: stale rows from older runs require destination/page backfill to be rewritten with localized values.
- Action needed: run periodic destination-scoped `parse_boats_parallel --skip-existing --no-cache --max-pages N` backfills until stale pool is exhausted.

## KI-010: search_by_slug used wrong API parameter, causing missing BoatTechnicalSpecs (FIXED 2026-04-08)
- Severity: critical
- Area: boats/boataround_api.py — `search_by_slug()`
- Symptom: offers and detail pages showed empty specs (cabins, berths, length, beam, draft = None) for boats that exist in API but were not in the default top-50 results.
- Root cause: `search_by_slug()` sent `slug` (singular) as API parameter. API ignores unknown params and returns 50 default boats. Target boat not among them → no `BoatTechnicalSpecs` created.
- Fix: changed parameter from `slug` to `slugs` (plural) — the actual API-recognized parameter. Removed unnecessary `limit: 50`.
- Impact: all boats affected by this bug will get specs on next detail/offer view (triggers `_ensure_api_metadata_for_boat`).

## KI-009: Inconsistent role coverage in access control (CLOSED 2026-04-07)
- Severity: medium
- Area: boats/views.py — access control
- Symptoms (all FIXED in 0.8.0-dev):
  - `delete_booking` excluded superadmin
  - `offers_stats_api` / `offers_list_api` / `offers_list` showed all offers only for admin, not manager/superadmin
  - `book_offer` allowed only manager, not admin/superadmin
  - `delete_offer` allowed only admin, not superadmin
  - `clients_list` / `client_detail` / `client_edit` / `client_search_api` allowed only manager/superadmin, not admin
- Root cause: hardcoded role string comparisons with incomplete role coverage.
- Fix: replaced all hardcoded checks with `can_*()` permission methods (migration 0008).
