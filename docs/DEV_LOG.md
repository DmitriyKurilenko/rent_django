# DEV LOG

Purpose: short, append-only engineering memory to avoid re-discovery and regressions.

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
