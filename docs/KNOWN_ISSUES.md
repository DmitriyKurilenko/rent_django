# KNOWN ISSUES

Last updated: 2026-03-11 (Europe/Moscow)

## KI-001: Upstream price jitter for identical requests
- Severity: high
- Area: search/detail/offers pricing
- Symptom: same slug + same dates may return different `totalPrice`/`discount` from Boataround.
- Notes:
  - observed directly in API payload samples,
  - top-level fields are less stable than `policies[0].prices`.
- Current mitigation:
  - canonical extraction from policy prices,
  - detail page resolves price server-side for requested dates.
- Remaining risk: truly inconsistent upstream responses cannot be fully fixed locally without stronger business rule.

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
