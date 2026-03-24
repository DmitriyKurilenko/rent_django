# TASK STATE

Last updated: 2026-03-22 (Europe/Moscow)

## Current priorities

### P0: Pricing consistency across search/detail/offers
- Status: in progress (stabilization logic implemented, still monitoring production drift).
- Goal: one pricing pipeline and predictable user-visible price per request context.
- Scope:
  - search cards,
  - boat detail page,
  - offer creation/list/detail,
  - direct booking flows.

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
- Destination-based amenities refresh selection now deduplicates and intersects with existing slugs in DB.
- Async amenities command now verifies active Celery worker and can wait with timeout/poll summary.
- Tests added for pricing extraction/resolver, detail snapshot behavior, amenities command async behavior.
- Added `import_charter_commissions` management command to import charter commissions from `.xlsx` by charter name normalization (including `d.o.o.` suffix stripping), with CSV audit outputs (`loaded` / `not_loaded`).

## Open risks / watch items
- Upstream Boataround API may return different `totalPrice` for identical query windows.
- Search “consensus” anti-jitter behavior can still show a new candidate early when no confirmed baseline exists.
- Network timeouts on price endpoint remain possible in production (fallback path must stay healthy).

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
