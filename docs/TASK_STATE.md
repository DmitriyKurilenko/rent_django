# TASK STATE

Last updated: 2026-03-11 (Europe/Moscow)

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

## Pending product decisions from user
- Canonical policy when upstream API returns two different totals for same query:
  - show freshest,
  - show conservative (higher/lower),
  - or apply multi-sample quorum before display.
