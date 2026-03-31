# TASK STATE

Last updated: 2026-04-02 (Europe/Moscow)

## Current priorities

### P0: Pricing consistency across search/detail/offers
- Status: **RESOLVED (2026-04-02)** — cache-first lookup in `get_price()` eliminates price jitter symptom for users.
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

## Open risks / watch items
- Upstream Boataround API may return different `totalPrice` for identical query windows.
- Search “consensus” anti-jitter behavior can still show a new candidate early when no confirmed baseline exists.
- Network timeouts on price endpoint remain possible in production (fallback path must stay healthy).- ~23k boats still without Charter FK — need to run `update_charters` to fill. Commission is 0 for these boats until then.
## Required validation workflow (project rule)
1. `docker compose down`
2. `docker compose up -d --build`
3. `docker compose run --rm web python manage.py check`
4. Run tests for touched modules
5. Verify affected HTTP pages render correctly
6. If any error: fix and rerun from failed step

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
- Status: implemented, ready for full server run.
- Goal: keep HTML only for service lists and photos; all other fields from API.
- Scope:
  - HTML writes: `extras`, `additional_services`, `delivery_extras`, `not_included`, `BoatGallery` photos, plus `cockpit` / `entertainment` / `equipment` (per-boat amenities).
  - API writes: `ParsedBoat` metadata, `BoatDescription`, `BoatTechnicalSpecs`, `Charter` linkage/rank fields.
  - API updater creates missing `BoatDescription` and `BoatTechnicalSpecs` records for newly parsed boats.
  - Phase 2.5 API updater runs only for newly created boats (no repeated update for existing boats).
  - Cache payload stores `api_meta` and `thumb_map`, so cache-hit runs still execute complete Phase 1.5 metadata hydration.

### P6: Geo-data localization integrity
- Status: in progress (logic fixed, backfill ongoing).
- Goal: non-English `BoatDescription` (`ru_RU/de_DE/fr_FR/es_ES`) must be populated only from same-language API payload.
- Scope:
  - Remove cross-language fallback that copied `en_EN` geo labels into other languages.
  - Keep English fallback only for `en_EN` records.
  - Run destination-scoped metadata backfill to correct stale historical rows.