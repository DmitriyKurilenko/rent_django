# Changelog

All notable changes to BoatRental project will be documented in this file.

## [0.5.1-dev] - 2026-04-02

### 🔧 Fixed — Detail page full parsing & error resilience
- **Detail/offer: полный парсинг (API → HTML)**: при отсутствии данных лодки detail page теперь парсит сначала API (BoatTechnicalSpecs, descriptions, charter), затем HTML (фото, сервисы, amenities). Ранее — только HTML, specs не создавались.
- **`_ensure_api_metadata_for_boat()`**: новый helper — подтягивает specs и charter из API для одной лодки через `_update_api_metadata`.
- **`search_by_slug(raw=True)`**: возвращает сырые API данные (с `parameters`) для создания specs.
- **`technical_specs` RelatedObjectDoesNotExist**: обёрнуто в try/except — лодки без specs рендерятся gracefully.
- **`detail.html` error path**: при `boat=None` (ошибка парсинга) шаблон больше не падает на `{% url 'toggle_favorite' boat.slug %}`.

## [0.5.0-dev] - 2026-04-01

### ✨ Added — Celery Parsing Pipeline & Agent Commission Settings
- **`parse_boats` management command**: батчевый парсинг через Celery с тремя режимами:
  - `--mode api` — только API-метаданные (country, charter, specs, coordinates)
  - `--mode html` — только HTML-парсинг (фото, extras, описания)
  - `--mode full` — оба режима последовательно
  - `--status [JOB_ID]` — просмотр прогресса и отчётов
  - Поддержка `--destination`, `--max-pages`, `--batch-size`, `--skip-existing`
- **`ParseJob` модель**: хранение заданий парсинга (прогресс, логи, ошибки, длительность)
- **`check_data_status` command**: полная диагностика данных (чартеры, геоданные, спеки, галерея, цены, офферы, бронирования, клиенты, договоры, пользователи)
- **`agent_commission_pct`** в PriceSettings: настраиваемый процент комиссии агента (default 50% от чартера)
- **Профиль пользователя**: бейджи роли и подписки, отображение комиссии для капитанов
- **`server_tasks.sh`**: скрипт для фоновых серверных задач (запуск, логи, статус)

### 🔧 Fixed — Captain Price Visibility & Parsing Stability
- **Комиссия капитана**: капитан видит свою долю (50% от чартера), а не полную комиссию чартера
- **Расшифровка цен в офферах**: скрыта от капитанов — доступна только менеджеру/админу
- **Кеш деталей**: инвалидация после автопривязки чартера (комиссия появляется сразу)
- **pricing.py**: восстановлена переменная `additional_discount_val` (поисковик возвращал 0 результатов)
- **`update_charters`**: retry-логика при сетевых ошибках (5 попыток, нарастающая задержка 10с→5мин)

### 📄 Documentation
- **docs/DECISIONS.md**: DR-018 (agent commission from settings)
- **docs/TASK_STATE.md**: обновлён
- **docs/DEV_LOG.md**: сессия 2026-04-01

### Files Changed
- `boats/models.py`: ParseJob model, agent_commission_pct field
- `boats/tasks.py`: run_parse_job, process_api_batch, process_html_batch
- `boats/management/commands/parse_boats.py`: new
- `boats/management/commands/check_data_status.py`: new
- `boats/management/commands/update_charters.py`: retry logic
- `boats/pricing.py`: configurable agent commission
- `boats/views.py`: captain price visibility, cache invalidation
- `boats/admin.py`: ParseJob admin
- `boats/tests/test_views.py`: updated commission tests
- `boats/migrations/0032_parse_job.py`, `0033_agent_commission_pct.py`: new
- `accounts/views.py`: agent commission in profile context
- `templates/accounts/profile.html`: role/subscription badges, commission
- `templates/accounts/price_settings.html`: agent_commission_pct field
- `templates/boats/search.html`, `detail.html`: captain commission display
- `server_tasks.sh`: new
- `VERSION`: 0.4.1-dev → 0.5.0-dev

## [0.4.1-dev] - 2026-03-31

### 🔧 Fixed - Charter Commission & Detail UI
- **Charter commission source**: reverted hardcoded DEFAULT_CHARTER_COMMISSION=20 fallback; commission is taken strictly from Charter model
- **Detail page readability**: replaced DaisyUI semantic colors (text-secondary/text-info/text-success) with Tailwind direct colors (text-amber-200/text-yellow-200/text-green-200) on purple gradient card; font size 11px → 13px

### ✨ Added - Charter Assignment Command
- **`update_charters`**: management command that scans Boataround API and assigns Charter FK to ParsedBoat records missing charter
  - `--destination` — scan specific destination
  - `--max-pages` — limit API pages
  - `--all` — update all boats (not just missing)
  - `--dry-run` — preview without DB writes

### 📄 Documentation
- **docs/DECISIONS.md**: DR-017 (charter commission source of truth)
- **docs/TASK_STATE.md**: updated done list, added risk item for 23k boats without charter
- **docs/DEV_LOG.md**: session 2 entry

### Files Changed
- `boats/helpers.py`, `boats/pricing.py`: reverted DEFAULT_CHARTER_COMMISSION
- `boats/management/commands/update_charters.py`: new
- `templates/boats/detail.html`: color/size fix
- `VERSION`: 0.4.0-dev → 0.4.1-dev

## [0.4.0-dev] - 2026-04-02

### 🔧 Fixed - Price Stability on Detail Page
- **Price caching fix**: `BoataroundAPI.get_price()` now checks 6-hour Redis cache before consensus loop
- **Eliminates symptom**: Refreshing detail page with same dates no longer shows different prices
- **Reduced API calls**: Cached results bypass 5-request consensus window entirely
- **Cleaner error handling**: Returns empty dict when all API requests fail (allows graceful fallback)
- **Impact**: KI-001 severity reduced from high → medium; pricing consistency (P0) marked RESOLVED

### 📄 Documentation
- **docs/VERSIONING.md**: New—semantic versioning scheme for development stage
- **docs/DEV_LOG.md**: Added entry for 2026-04-02 price cache fix
- **docs/DECISIONS.md**: Added DR-017 (cache-first lookup strategy)
- **docs/KNOWN_ISSUES.md**: Updated KI-001 with resolution path
- **docs/TASK_STATE.md**: P0 pricing consistency marked RESOLVED
- **VERSION**: Introduced version file (0.4.0-dev)

### Files Changed
- `boats/boataround_api.py`: `get_price()` method refactored
- `docs/VERSIONING.md`: New versioning guide
- `docs/DEV_LOG.md`, `docs/DECISIONS.md`, `docs/KNOWN_ISSUES.md`, `docs/TASK_STATE.md`: Updated
- `VERSION`: New file (0.4.0-dev)

## [1.2.0] - 2026-02-01

### ✨ Added - Quick Offer Creation Feature
- **One-click offer creation** from boat detail pages
- **Modal interface** with role-based offer type selection
- **Role-based permissions**:
  - `captain` role: Captain (agent) offers only
  - `manager`/`admin` roles: Choice between captain and tourist offers
- **Dynamic pricing**: Auto-fetched from API based on dates
- **Instant creation**: No form page, direct offer generation
- New view: `quick_create_offer()` in `boats/views.py`
- New URL: `/boat/<slug>/create-offer/`
- Modal UI in `templates/boats/detail.html` with JavaScript logic

### 📚 Documentation Updates
- **README.md**: Complete project overview with quick start
- **Production checklist**: 50+ items for deployment verification
- **.env.example**: Comprehensive unified environment template
- **.github/copilot-instructions.md**: Updated with quick offer creation patterns
- Added architecture diagrams and data flow explanations

### 🔧 Improvements
- Enhanced `create_offer` view with session-based prefill support
- Better error handling in offer creation flow
- Improved role-based permission checks
- Added `has_meal` option for tourist offers

### 🐛 Bug Fixes
- Fixed source_url field type (TextField instead of URLField) for long URLs
- Improved price calculation logic for different offer types
- Better handling of missing boat data in offer creation

---

## [1.1.0] - 2026-01-25

### ✨ Added - Multi-Language Support
- 5 languages: English, Russian, German, Spanish, French
- URL-based language switching: `/ru/boat/`, `/en/boat/`, etc.
- Language-aware API requests (ru_RU, en_EN, de_DE, es_ES, fr_FR)
- Translated boat descriptions and UI elements
- Fallback logic for missing translations

### 📚 Documentation
- Complete I18N documentation suite in `docs/`
- Multi-language architecture guide
- Code examples and quick reference
- Setup and deployment instructions

---

## [1.0.0] - 2026-01-15

### 🎉 Initial Release

#### Core Features
- **Boat Management**: 28,000+ boats from boataround.com
- **Dual-layer integration**: REST API + HTML parsing
- **Smart caching**: ParsedBoat model with 24-hour TTL
- **Async parsing**: Celery-based bulk import (15-20 hours)
- **Search & filtering**: Fast API-based search with pagination
- **User roles**: Tourist, Captain, Manager, Admin

#### Technical Stack
- Django 4.2 on Python 3.8+
- PostgreSQL 15 with JSONField
- Redis 7 for Celery broker
- Celery 5.3 with retry logic
- Alpine.js + JSON API frontend
- BeautifulSoup4 for parsing
- VK Cloud S3 + Free CDN for images

#### Deployment
- Docker Compose for local development
- Ubuntu 20.04+ production guide
- Gunicorn + Nginx + systemd
- Let's Encrypt SSL support
- Comprehensive documentation

---

## Future Roadmap

### [1.3.0] - Planned
- [ ] Advanced search filters (price range, year, manufacturer)
- [ ] Booking system integration
- [ ] Payment gateway integration (Stripe/PayPal)
- [ ] Email notifications for offers
- [ ] SMS notifications via Twilio
- [ ] Real-time availability check
- [ ] Favorites/wishlist for tourists

### [2.0.0] - Future
- [ ] Mobile app (React Native)
- [ ] Progressive Web App (PWA)
- [ ] Advanced analytics dashboard
- [ ] AI-powered boat recommendations
- [ ] Customer reviews and ratings
- [ ] Multi-currency support
- [ ] Calendar integration
- [ ] WhatsApp Business API integration

---

## Version Format

We follow [Semantic Versioning](https://semver.org/):
- MAJOR version: Incompatible API changes
- MINOR version: New functionality (backward compatible)
- PATCH version: Bug fixes (backward compatible)

---

## Support

For bugs and feature requests, please open an issue on GitHub.

For production support, contact the development team.
