# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read First

Before any non-trivial code change, read in order:
1. `docs/TASK_STATE.md` — current priorities and done/blocked status
2. `docs/DECISIONS.md` — behavioral invariants and past decisions
3. `docs/KNOWN_ISSUES.md` — active bugs and gotchas
4. `docs/DEV_LOG.md` (latest entries first) — recent changes
5. `задача.md` if present — current task file

If instructions conflict, stop and ask the user. Do not guess.

## Stack

Django 5.2 LTS · Python 3.13 · PostgreSQL · Redis · Celery · Docker · DaisyUI + Tailwind CSS · Alpine.js · htmx · Font Awesome 6

## Development Commands

**All commands run inside Docker. Never install packages on the host.**

```bash
# Start / stop
make up           # docker compose up -d
make down         # docker compose down
make build        # docker compose build

# Django
docker compose exec web python manage.py shell
docker compose exec web python manage.py migrate
docker compose exec web python manage.py makemigrations

# Tests
docker compose exec web python manage.py test                          # all
docker compose exec web python manage.py test boats                    # one app
docker compose exec web python manage.py test boats.tests.test_pricing # one file
make coverage                                                           # with HTML report

# Tailwind CSS (host has no node — use Docker)
docker run --rm -v "$(pwd)":/app -w /app node:18-alpine sh -c "npm install && npx tailwindcss ..."

# Lint
docker compose exec web flake8 boats accounts boat_rental --max-line-length=120

# Boat parsing
make parse-test          # 5 boats sync (safe)
make parse-async LIMIT=100

# i18n
make messages            # makemessages -l ru/en/de/es/fr
make compilemessages
```

## Validation Baseline

After every non-trivial change:
```bash
docker compose down && docker compose up -d --build
docker compose run --rm web python manage.py check
docker compose exec web python manage.py test <changed_module>
# manual HTTP render check for affected pages
```

## Project Structure

```
boat_rental/   settings, urls.py, celery.py
boats/         main app — models, views, helpers, parser, boataround_api, pricing, tasks, notifications
accounts/      users, UserProfile, Role, CaptainBrand, auth views
templates/     all templates (not app-level)
locale/        ru/en/de/es/fr translations
docs/          living documentation (DECISIONS, DEV_LOG, KNOWN_ISSUES, TASK_STATE, …)
```

### URL Architecture

All routes in `boats.urls` and `accounts.urls` are wrapped in `i18n_patterns(prefix_default_language=True)`, giving every URL a language prefix (`/ru/`, `/en/`, etc.).

**Never hardcode URL paths in JavaScript.** Always use `{% url "name" %}` template tags. For dynamic segments: `'{% url "name" 9999999 %}'.replace('9999999', id)`.

In tests, use `translation.override('ru')` to reverse i18n URLs:
```python
from django.utils import translation
with translation.override('ru'):
    url = reverse('name')
```

## Core Models (boats/models.py)

| Model | Purpose |
|---|---|
| `ParsedBoat` | Source-of-truth for boats scraped from boataround.com (`boat_id`, `slug`) |
| `BoatDescription` | Per-language title/location/description (FK → ParsedBoat) |
| `BoatTechnicalSpecs` | One-to-one technical params (length, cabins, …) |
| `BoatPrice` | Per-currency prices (FK → ParsedBoat) |
| `BoatGallery` | CDN photo URLs ordered by `order` |
| `BoatDetails` | Per-language extras/amenities JSON |
| `Charter` | Charter company with commission % |
| `Offer` | Commercial offer (tourist or captain type) with UUID |
| `Booking` | Booking against Offer or ParsedBoat |
| `Client` | Tourist profile created by captain/agent |
| `Contract` | PDF contract with OTP signing flow |
| `PriceSettings` | Global pricing singleton (pk=1, cached 5 min in Redis) |
| `CountryPriceConfig` | Per-country pricing profile linked to PriceSettings |
| `ParseJob` | Background parse job tracking |
| `Feedback` | Contact form submissions |

`Boat` (local, non-API) is legacy — primary data lives in `ParsedBoat`.

## Roles & Permissions (accounts/models.py)

`UserProfile.role` returns the `Role.codename` string. Hierarchy: `tourist < captain < assistant < manager < admin < superadmin`.

Permissions are checked via `profile.has_perm('codename')` (cached per instance). Named helpers: `can_manage_charters()`, `can_manage_prices()`, `can_create_offers()`, etc.

`CaptainBrand` — custom branding profile for offers (logo, colors, contact links). Captains with `advanced` subscription can use custom/no-branding modes.

## Pricing

**Never read PriceSettings fields directly.** Always call `PriceSettings.get_settings()` — it returns a Redis-cached instance (5 min TTL). Cache key: `price_settings`, invalidated on every `PriceSettings.save()` and `CountryPriceConfig.save()/delete()`.

Pricing pipeline:
1. `boats/pricing.py` — unified resolver used everywhere (search, boat detail, offers, bookings)
2. `boats/helpers.py` — `calculate_final_price_with_discounts()`, `apply_charter_commission()`
3. Canonical price extraction from Boataround API: use `policies[0].prices`, **not** top-level `totalPrice`/`discount` (those are unstable)
4. Fallback to DB price via unified resolver when API is unavailable; never mix cached values from unrelated sources

## Boataround API & Parser

- `boats/boataround_api.py` — `BoataroundAPI` client (search, boat detail, amenities, pricing)
- `boats/parser.py` — HTML scraper that enriches ParsedBoat with photos, services, descriptions
- `boats/tasks.py` — Celery tasks: `send_telegram_notification`, `send_feedback_notification`, parse orchestration
- Images uploaded to S3 (VK Cloud Storage); `ParsedBoat.preview_cdn_url` stores the CDN thumbnail URL

## PriceSettings Singleton Pattern

```python
def save(self, *args, **kwargs):
    self.pk = 1
    kwargs.pop('force_insert', None)  # prevent IntegrityError from objects.create()
    self._state.adding = not type(self).objects.filter(pk=1).exists()
    super().save(*args, **kwargs)
```

## After Non-Trivial Changes

1. Update `docs/DECISIONS.md` if behavior or invariant changed.
2. Update `docs/TASK_STATE.md` (done / in progress / blocked).
3. Add entry to `docs/DEV_LOG.md` (date, files, validation done, risks).
4. If a bug is found or closed, update `docs/KNOWN_ISSUES.md`.
5. If the change is user-visible (UI, behavior, removed/added feature), add entry to `docs/RELEASE_NOTES.md` in Russian, from the user's perspective, no technical internals.
