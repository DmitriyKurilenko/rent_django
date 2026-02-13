# 🛥️ BoatRental - Django Boat Rental Platform

> Production-ready Django 4.2 platform for boat rental with external API integration, intelligent caching, async parsing, and multi-language support.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Django 4.2](https://img.shields.io/badge/django-4.2-green.svg)](https://www.djangoproject.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## 🎯 Quick Start

### Local Development (5 minutes)

```bash
# Clone repository
git clone <repository-url>
cd rent_django

# Start with Docker Compose
docker-compose up

# Create superuser (in another terminal)
docker-compose exec web python manage.py createsuperuser

# Visit http://localhost:8000
```

### Production Deployment (Ubuntu)

See detailed guide: [docs/PRODUCTION_UBUNTU_DEPLOYMENT.md](docs/PRODUCTION_UBUNTU_DEPLOYMENT.md)

```bash
# Quick version:
1. Ubuntu 20.04+ server with 4GB+ RAM
2. Clone repo and create .env from .env.example
3. Run setup script from docs/QUICK_DEPLOY.md
4. Parse boats: python manage.py parse_all_boats --async
5. Live at https://yourdomain.com
```

---

## ✨ Key Features

### 🚤 Boat Management
- **28,000+ boats** from boataround.com via REST API + HTML parsing
- **Smart caching** with 24-hour TTL in PostgreSQL (ParsedBoat model)
- **Async parsing** via Celery (15-20 hours initial bulk import)
- **Multi-language** support (EN, RU, DE, ES, FR) with localized URLs
- **Image optimization**: Free CDN thumbnails + S3 fallback for full images

### 💼 Offer System (NEW!)
- **Quick offer creation** directly from boat detail pages
- **Dual offer types**:
  - **Captain (Agent) offers**: Detailed information for B2B
  - **Tourist offers**: Beautiful simplified view for end clients
- **Role-based access**:
  - `captain` role → Captain offers only
  - `manager`/`admin` roles → Both offer types with type selector
- **One-click workflow**: View boat → Click "Create Offer" → Modal → Instant offer creation
- **Dynamic pricing**: Auto-fetched from API based on check_in/check_out dates
- **UUID sharing**: `/offer/<uuid>/` for secure client-facing links

### 👥 User Roles & Permissions
- **Tourist**: Browse, search, save favorites
- **Captain (Agent)**: + Create captain offers for clients
- **Manager**: + Create both captain and tourist offers
- **Admin**: Full access to all features

### 🔍 Search & Filtering
- **Fast search** with API integration (2-3 sec response)
- **Advanced filters**: Destination, dates, boat type, capacity
- **Price calculation**: Real-time pricing with discounts and extras
- **Paginated results**: 18 boats per page with infinite scroll support

### 🌐 Multi-Language Architecture
- URL-based language switching: `/ru/boat/...`, `/en/boat/...`, etc.
- Translated boat descriptions, equipment names, and UI elements
- Language-aware API requests (ru_RU, en_EN, de_DE, es_ES, fr_FR)
- Fallback logic: EN → RU if translation missing

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    USER REQUEST                          │
└─────────────────────┬───────────────────────────────────┘
                      ↓
              ┌───────────────┐
              │  Nginx + SSL  │
              └───────┬───────┘
                      ↓
              ┌───────────────┐
              │   Gunicorn    │ (WSGI Server)
              └───────┬───────┘
                      ↓
         ┌────────────────────────────┐
         │    Django Application      │
         ├────────────────────────────┤
         │  boats/views.py            │
         │  ├─ boat_search()          │ → API → Cache
         │  ├─ boat_detail_api()      │ → Cache → Parse if miss
         │  └─ quick_create_offer()   │ → Direct offer creation
         └────────┬───────────────────┘
                  ↓
    ┌─────────────────────────────────┐
    │       PostgreSQL 15              │
    │  ┌────────────────────────────┐ │
    │  │  ParsedBoat (cache layer)  │ │
    │  │  ├─ boat_id (indexed)      │ │
    │  │  ├─ slug (unique)          │ │
    │  │  └─ boat_data (JSON)       │ │
    │  ├────────────────────────────┤ │
    │  │  Offer (commercial)        │ │
    │  │  ├─ uuid (sharing)         │ │
    │  │  ├─ offer_type             │ │
    │  │  └─ boat_data (snapshot)   │ │
    │  └────────────────────────────┘ │
    └─────────────────────────────────┘
                  ↓
    ┌─────────────────────────────────┐
    │  Redis (Celery Broker)          │
    └─────────┬───────────────────────┘
              ↓
    ┌─────────────────────────────────┐
    │  Celery Workers (async)         │
    │  ├─ parse_boat_detail()         │
    │  ├─ parse_all_boats()           │
    │  └─ Retry logic: max_retries=3  │
    └─────────┬───────────────────────┘
              ↓
    ┌─────────────────────────────────┐
    │  boats/parser.py                │
    │  └─ BeautifulSoup HTML extract  │
    └─────────────────────────────────┘
              ↓
    ┌─────────────────────────────────┐
    │  Image Storage                  │
    │  ├─ CDN (free, 650px thumbs)   │
    │  └─ S3 (paid, full resolution)  │
    └─────────────────────────────────┘
```

---

## 📂 Project Structure

```
rent_django/
├── .github/
│   └── copilot-instructions.md    # AI agent guide (architecture, patterns)
├── boats/                         # Main app
│   ├── models.py                  # ParsedBoat, Offer, BoatTechnicalSpecs, etc.
│   ├── views.py                   # boat_search, boat_detail_api, quick_create_offer
│   ├── parser.py                  # BeautifulSoup HTML → structured JSON
│   ├── boataround_api.py          # REST API client (search, price, autocomplete)
│   ├── helpers.py                 # Cache management, pricing calculations
│   ├── tasks.py                   # Celery async tasks (parse_boat_detail)
│   ├── forms.py                   # OfferForm with role-based validation
│   └── management/commands/
│       ├── parse_all_boats.py     # Bulk import (--async/--sync)
│       ├── dump_parsed_boats.py   # Backup cache to JSON
│       └── clear_parsed_boats.py  # Reset cache
├── accounts/                      # User management
│   └── models.py                  # UserProfile with roles (tourist/captain/manager/admin)
├── templates/
│   └── boats/
│       ├── detail.html            # Boat details + quick offer button
│       ├── offer_tourist.html     # Client-facing offer view
│       └── offer_captain.html     # Agent-facing offer view
├── docs/                          # Comprehensive documentation
│   ├── PRODUCTION_UBUNTU_DEPLOYMENT.md  # Step-by-step production setup
│   ├── API_DOCUMENTATION.md            # REST API reference
│   ├── DEPLOYMENT_CHECKLIST_FINAL.md   # 200+ production checklist (in root)
│   ├── QUICK_DEPLOY.md                  # Fast deployment script
│   └── I18N_*.md                        # Multi-language documentation
├── docker-compose.yml             # Local dev environment
├── requirements.txt               # Python dependencies
└── README.md                      # This file
```

---

## 🔑 Key Technologies

- **Backend**: Django 4.2, Python 3.8+
- **Database**: PostgreSQL 15 with JSONField for flexible boat data
- **Cache/Queue**: Redis 7 (Celery broker + result backend)
- **Task Queue**: Celery 5.3 with exponential backoff retry
- **Frontend**: Alpine.js + fetch (JSON API pattern), Tailwind CSS + DaisyUI
- **Parsing**: BeautifulSoup4 + requests with realistic User-Agent
- **Storage**: VK Cloud S3 (boto3) + Free CDN for thumbnails
- **Deployment**: Gunicorn + Nginx + systemd on Ubuntu 20.04+
- **Monitoring**: Django logging + Celery task tracking

## 🎨 Frontend CSS Build (Tailwind + DaisyUI)

Проект использует локальную сборку CSS (без `cdn.tailwindcss.com`) для лучшей производительности и стабильного LCP.

```bash
# Установить зависимости (один раз)
npm install

# Собрать production CSS
npm run build:css

# Режим разработки (watch)
npm run watch:css
```

- Входной файл: `assets/css/tailwind.input.css`
- Конфиг: `tailwind.config.js`
- Выходной файл: `static/css/styles.css`
- В production CSS собирается автоматически на этапе `docker build` (см. `Dockerfile`, stage `assets`).

---

## 📚 Documentation Index

### For Developers
- [.github/copilot-instructions.md](.github/copilot-instructions.md) - **Start here!** Architecture, patterns, key files
- [docs/I18N_QUICK_REFERENCE.md](docs/I18N_QUICK_REFERENCE.md) - Multi-language quick reference
- [docs/I18N_CODE_EXAMPLES.md](docs/I18N_CODE_EXAMPLES.md) - Code examples and patterns

### For DevOps/SysAdmin
- [docs/PRODUCTION_UBUNTU_DEPLOYMENT.md](docs/PRODUCTION_UBUNTU_DEPLOYMENT.md) - Complete production guide
- [docs/QUICK_DEPLOY.md](docs/QUICK_DEPLOY.md) - Fast deployment script
- [docs/TRIAL_DEPLOY_CHECKLIST.md](docs/TRIAL_DEPLOY_CHECKLIST.md) - Staging/trial deploy checklist
- [docs/STAGING_RUNBOOK.md](docs/STAGING_RUNBOOK.md) - 1-page staging operations runbook
- [DEPLOYMENT_CHECKLIST_FINAL.md](DEPLOYMENT_CHECKLIST_FINAL.md) - 200+ production checklist
- [docs/FAQ.md](docs/FAQ.md) - Troubleshooting guide

### For Managers
- [docs/I18N_FINAL_REPORT.md](docs/I18N_FINAL_REPORT.md) - Implementation summary and metrics
- [docs/archive/PRODUCTION_READINESS_SUMMARY.md](docs/archive/PRODUCTION_READINESS_SUMMARY.md) - Production status report

---

## 🚀 Common Tasks

### Parse Boats (First Time Setup)
```bash
# Sync parsing (testing, 5 boats ~30 sec)
docker-compose exec web python manage.py parse_all_boats --sync --limit 5

# Async parsing (production, 28k boats ~15-20 hours)
docker-compose exec web python manage.py parse_all_boats --async --batch-size 50

# Parse specific destination
docker-compose exec web python manage.py parse_all_boats --async --destination turkey --max-pages 5

# Incremental update (skip existing)
docker-compose exec web python manage.py parse_all_boats --async --skip-existing
```

### Create Offers

**Via Web UI (Recommended):**
1. Navigate to boat detail page with dates: `/boat/bavaria-cruiser-46/?check_in=2026-02-21&check_out=2026-02-28`
2. Click "Создать оффер" button (requires authentication + captain/manager/admin role)
3. Select offer type (if manager/admin)
4. Offer created instantly with UUID link

**Via Admin Panel:**
1. Visit `/admin/boats/offer/`
2. Fill source_url with boat URL + dates
3. Choose offer type
4. Save

### Manage Cache
```bash
# Check cache statistics
docker-compose exec web python manage.py shell
>>> from boats.models import ParsedBoat
>>> ParsedBoat.objects.count()
>>> ParsedBoat.objects.filter(last_parse_success=True).count()

# Backup cache to JSON
docker-compose exec web python manage.py dump_parsed_boats

# Clear cache (reparse needed)
docker-compose exec web python manage.py clear_parsed_boats
```

### Monitor Celery Tasks
```bash
# Watch Celery worker logs
docker-compose logs -f celery_worker

# Check task status in Django shell
docker-compose exec web python manage.py shell
>>> from celery import current_app
>>> stats = current_app.control.inspect().stats()
```

---

## 🔒 Security

- ✅ CSRF protection enabled (Django default)
- ✅ SQL injection protection (Django ORM)
- ✅ XSS protection via template auto-escaping
- ✅ Secure password hashing (PBKDF2)
- ✅ HTTPS enforced in production (SECURE_SSL_REDIRECT)
- ✅ Session cookies: Secure + HttpOnly
- ✅ Secret keys in environment variables (never in code)
- ✅ Rate limiting recommended (django-ratelimit)

---

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open Pull Request

---

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## 🆘 Support & Troubleshooting

### Common Issues

**Celery not picking up tasks:**
```bash
# Check Redis connection
docker-compose exec redis redis-cli ping  # Should return PONG

# Restart Celery worker
docker-compose restart celery_worker
```

**Parsing fails:**
```bash
# Check ParsedBoat for failed boats
>>> ParsedBoat.objects.filter(last_parse_success=False).count()

# Re-parse specific boat
>>> from boats.parser import parse_boataround_url
>>> parse_boataround_url('https://www.boataround.com/ru/yachta/bavaria-cruiser-46/', save_to_db=True)
```

**Images not loading:**
- Check CDN URL first (free): `imageresizer.yachtsbt.com`
- Fallback to S3 (paid): Verify AWS credentials in .env
- Template automatically handles fallback: `boats/templatetags/cdn_tags.py`

### Getting Help

- 📖 Read [.github/copilot-instructions.md](.github/copilot-instructions.md) for architecture overview
- 🐛 Check [docs/FAQ.md](docs/FAQ.md) for common issues
- 💬 Open GitHub issue for bugs or feature requests

---

## 🎉 Credits

Built with ❤️ using Django, Celery, and open-source technologies.

Special thanks to:
- Django Software Foundation
- Celery Project
- BeautifulSoup4
- All contributors

---

**Ready to launch?** Follow [DEPLOYMENT_CHECKLIST_FINAL.md](DEPLOYMENT_CHECKLIST_FINAL.md) for production deployment! 🚀
