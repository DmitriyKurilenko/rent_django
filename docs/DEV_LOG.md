# DEV LOG

Purpose: short, append-only engineering memory to avoid re-discovery and regressions.

## 2026-03-24
- Change:
  - Implemented Client (tourist) management feature — agents/captains can create client profiles and link them to offers, bookings, and contracts.
  - Added `Client` model with fields: last_name, first_name, middle_name, email, phone, passport_number, passport_issued_by, passport_date, address, notes. FK to User (created_by, required; user, optional).
  - Added nullable `client` FK to Booking, Offer, and Contract models.
  - Added `ClientForm` (ModelForm) in boats/forms.py.
  - Added 5 views: clients_list (paginated + search), client_create, client_detail (with history), client_edit, client_search_api (JSON autocomplete).
  - Added 5 URL patterns under `clients/` and `api/clients/search/`.
  - Created 3 templates: clients_list.html, client_form.html, client_detail.html (all with sidebar nav).
  - Added Alpine.js `clientSelector()` component in create_offer.html for client autocomplete.
  - Added Alpine.js `quickClientSelector()` component in detail.html (quick offer modal).
  - Client auto-propagates: offer.client → booking.client → contract.client.
  - Contract creation pre-fills signer data from client (passport, address, phone, email).
  - Client info card shown in captain offer template (offer_captain.html) for internal users.
  - Updated sidebar nav in my_bookings.html, contracts_list.html, base.html mobile nav.
  - Added ClientAdmin in boats/admin.py with fieldsets and search fields.
  - Fixed migration 0024 operation ordering (AddIndex on booking.client moved after AddField).
- Files:
  - `boats/models.py` (Client model + FK additions)
  - `boats/forms.py` (ClientForm)
  - `boats/views.py` (5 new views + modified create_offer, quick_create_offer, book_offer, create_contract)
  - `boats/urls.py` (5 new patterns)
  - `boats/admin.py` (ClientAdmin)
  - `templates/boats/clients_list.html` (new)
  - `templates/boats/client_form.html` (new)
  - `templates/boats/client_detail.html` (new)
  - `templates/boats/create_offer.html` (client selector + Alpine.js)
  - `templates/boats/detail.html` (quickClientSelector in offer modal + i18n load)
  - `templates/boats/offer_captain.html` (client info card)
  - `templates/boats/my_bookings.html` (sidebar nav)
  - `templates/boats/contracts_list.html` (sidebar nav)
  - `templates/base.html` (mobile nav)
  - `boats/migrations/0024_client_booking_boats_booki_client__2b4cf4_idx_and_more.py` (fixed ordering)
- Why:
  - Business need: agents/captains need to manage their customers who may not have accounts in the system, and link them to bookings and contracts for document generation.
- Validation:
  - `docker compose up -d --build` (passed)
  - `python manage.py makemigrations --check` (no changes detected)
  - `python manage.py check` (0 issues)
  - HTTP render checks: `/ru/clients/` 200, `/ru/clients/create/` 200, `/ru/api/clients/search/` 200
  - E2E test: create client → search API → detail page → cleanup (all passed)
  - Modified pages: `/ru/my-bookings/` 200, `/ru/contracts/` 200, `/ru/offers/` 200
- Risks / follow-up:
  - Client deduplication not implemented — agents can create duplicate clients. Consider adding unique constraint on (created_by, last_name, first_name, phone).
  - Tourist offer template (offer_tourist.html) does not show client info — only captain template does, as tourist template is client-facing.
  - Booking direct creation from boat detail (book_boat) does not have client selector — only offer-based flow propagates client.

## 2026-03-22
- Change:
  - Implemented online contract signing feature (models, views, PDF generator, templates, tasks, admin).
  - Added `ContractTemplate` and `Contract` models with audit fields (sign_ip, sign_user_agent, document_hash).
  - Created `boats/contract_generator.py` with two-pass PDF rendering (SHA-256 hash embedded in final doc).
  - Added 5 views: create_contract, contract_detail, sign_contract (public), download_contract, contracts_list.
  - Created 6 templates: create, detail, sign (with Canvas signature via Alpine.js), signed, expired, list.
  - Added Celery tasks: generate_contract_pdf_task, send_contract_notification (stub).
  - Updated my_bookings template with contract action buttons.
  - Updated base.html mobile nav with contracts link.
  - Added xhtml2pdf==0.2.16 to requirements.txt.
  - Updated Dockerfile with libcairo2-dev, pkg-config, python3-dev, gcc for pycairo (xhtml2pdf dep).
  - Fixed uuid module shadowing in Contract model (uuid field name shadows import within class body).
- Files:
  - `requirements.txt`
  - `Dockerfile`
  - `boats/models.py`
  - `boats/forms.py`
  - `boats/views.py`
  - `boats/urls.py`
  - `boats/admin.py`
  - `boats/tasks.py`
  - `boats/contract_generator.py` (new)
  - `templates/boats/create_contract.html` (new)
  - `templates/boats/contract_detail.html` (new)
  - `templates/boats/contract_sign.html` (new)
  - `templates/boats/contract_signed.html` (new)
  - `templates/boats/contract_expired.html` (new)
  - `templates/boats/contracts_list.html` (new)
  - `templates/boats/my_bookings.html`
  - `templates/base.html`
  - `boats/migrations/0023_contracttemplate_contract.py` (auto-generated)
- Why:
  - Business need for formalizing agent-client agreements with legally sufficient electronic signatures.
- Validation:
  - `docker compose down`
  - `docker compose up -d --build` (passed)
  - `python manage.py check` (passed, 0 issues)
  - HTTP render checks: `/ru/contracts/` 200, `/ru/my-bookings/` 200
- Risks / follow-up:
  - Email notification is a stub — needs SMTP config and real implementation.
  - PDF font rendering for Cyrillic may need font files bundled in Docker image.
  - Contract template text should be reviewed by legal before production use.

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
