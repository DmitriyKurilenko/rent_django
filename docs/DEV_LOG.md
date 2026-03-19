# DEV LOG

Purpose: short, append-only engineering memory to avoid re-discovery and regressions.

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
