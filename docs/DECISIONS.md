# DECISIONS (ADR-lite)

Last updated: 2026-03-11 (Europe/Moscow)

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
