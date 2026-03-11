# AGENTS: Protocol for This Repository

## Purpose
This file is the persistent operating protocol for AI/code agents working in this repository.
Primary goal: avoid repeated regressions and loss of context between sessions.

## Mandatory Read Order Before Any Code Change
1. `docs/TASK_STATE.md`
2. `docs/DECISIONS.md`
3. `docs/KNOWN_ISSUES.md`
4. `docs/DEV_LOG.md` (latest entries first)
5. Current task file (`задача.md` when present)

If instructions conflict, do not guess. Stop and ask the user for a decision.

## Non-Negotiable Guardrails
- Keep stack unchanged unless user explicitly approves extension:
  - Django, Ninja, Redis, Celery, Postgres, Docker, DaisyUI, AlpineJS, htmx, charts.js
- Do not remove production data without explicit user approval.
- Do not run local venv workflows for validation; use Docker-based commands.
- Do not introduce one-off hacks for symptoms. Fix root logic and all affected flows.

## Pricing Domain Rules (Current)
- Treat Boataround top-level `totalPrice` and `discount` as unstable.
- Canonical extraction priority: `policies[0].prices`.
- Use unified resolver (`boats/pricing.py`) for:
  - search formatting,
  - boat detail,
  - offers,
  - bookings.
- If price API is unavailable:
  - fallback to DB price via unified resolver,
  - never silently mix unrelated cached values.

## Update Ritual (Required After Non-Trivial Changes)
After each meaningful code change:
1. Add/update decision in `docs/DECISIONS.md` if behavior/invariant changed.
2. Update `docs/TASK_STATE.md` (done/in progress/blocked).
3. Add concise entry to `docs/DEV_LOG.md` with date, files, validation, risks.
4. If a known bug is discovered or closed, update `docs/KNOWN_ISSUES.md`.

## Validation Baseline (Docker)
Unless task says otherwise, use:
1. `docker compose down`
2. `docker compose up -d --build`
3. `docker compose run --rm web python manage.py check`
4. Targeted tests for changed modules
5. Manual HTTP render check for affected pages

If any step fails, fix and rerun. Partial validation is not considered done.

