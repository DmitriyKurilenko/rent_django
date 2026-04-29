# 📚 BoatRental Production Documentation Index

Complete guide for developers, DevOps engineers, and AI agents deploying this application to production.

## 🎯 Quick Links by Role

### 👨‍💻 Developers & AI Agents
Start here for architectural understanding and code patterns:
- **[.github/copilot-instructions.md](../.github/copilot-instructions.md)** - AI-focused architecture guide (concise, ~60 lines)
  - Data flow patterns (search, detail, bulk parsing)
  - Key files and cross-component communication
  - Image handling strategy (thumb vs main_img)
  - Production deployment overview
- **[API_DOCUMENTATION.md](./API_DOCUMENTATION.md)** 🆕 - Complete API reference
  - REST endpoints documentation
  - Authentication & rate limiting
  - Example requests and responses
  - Integration examples (Python, JavaScript)
- **[../CONTRIBUTING.md](../CONTRIBUTING.md)** 🆕 - Contribution guidelines
  - Development setup
  - Coding standards
  - Pull request process
  - Testing guidelines

### 🧠 Engineering Memory (Must read before code changes)
- **[../AGENTS.md](../AGENTS.md)** - persistent protocol for agents and guardrails
- **[TASK_STATE.md](./TASK_STATE.md)** - current priorities, done scope, open decisions
- **[DECISIONS.md](./DECISIONS.md)** - accepted behavior decisions (ADR-lite)
- **[KNOWN_ISSUES.md](./KNOWN_ISSUES.md)** - active bugs/risks and current mitigations
- **[DEV_LOG.md](./DEV_LOG.md)** - concise chronological development log
- **[TASK_TEMPLATE.md](./TASK_TEMPLATE.md)** - шаблон для постановки задачи «составить детальный план реализации»

### 🔒 Security
Security policies and best practices:
- **[../SECURITY.md](../SECURITY.md)** 🆕 - Security policy
  - Vulnerability reporting process
  - Security best practices
  - Known security considerations
  - Security tools and checklist

### 🛠️ DevOps / System Administrators  
Step-by-step production deployment guides:

1. **[QUICK_DEPLOY.md](./archive/QUICK_DEPLOY.md)** ⚡ START HERE (~30 min full setup)
   - One consolidated bash script for Ubuntu 20.04+
   - Installs PostgreSQL, Redis, Nginx, Gunicorn, Celery
   - Configures SSL with Let's Encrypt
   - Sets up systemd services

2. **[PRODUCTION_UBUNTU_DEPLOYMENT.md](./archive/PRODUCTION_UBUNTU_DEPLOYMENT.md)** 📖 DETAILED GUIDE
   - 10-step detailed walkthrough with explanations
   - Pre-deployment checklist
   - Server hardware requirements
   - Performance tuning recommendations
   - Troubleshooting section

3. **[../DEPLOYMENT_CHECKLIST_FINAL.md](../DEPLOYMENT_CHECKLIST_FINAL.md)** 🆕 ✅ COMPREHENSIVE VERIFICATION
  - 200+ production checklist items
  - Pre-deployment checks (code, config, database, static files)
  - Security configuration (server, application, SSL/TLS)
  - Web server setup (Nginx, Gunicorn)
  - Testing procedures (smoke tests, performance, Celery)
  - Monitoring & logging setup
  - Backup & recovery strategy
  - Go-live checklist with troubleshooting commands

4. **[TRIAL_DEPLOY_CHECKLIST.md](./TRIAL_DEPLOY_CHECKLIST.md)** 🧪 STAGING CHECKLIST
  - Минимальный чеклист перед пробным деплоем
  - Smoke-тесты ключевых пользовательских флоу
  - Критерии готовности staging

5. **[STAGING_RUNBOOK.md](./STAGING_RUNBOOK.md)** 🛠️ OPERATIONS RUNBOOK
  - Короткий operational-гайд на 1 страницу
  - Порядок запуска/проверки/rollback

### 🚀 Automated Deployment
Quick deployment scripts:
- **[../deploy.sh](../deploy.sh)** 🆕 - Automated production deployment script
  - Requirements check
  - Database backup
  - Docker image build
  - Migration & static collection
  - Service restart with health checks
- **[../setup-ssl.sh](../setup-ssl.sh)** 🆕 - SSL certificate setup script
  - Let's Encrypt certificate installation
  - Nginx configuration update
  - Auto-renewal setup

### 📊 Data Operations
Bulk boat parsing and image management:
- **Management commands:**
  - `parse_boats_parallel` — параллельный парсинг HTML + автоматическая загрузка thumb-превью на CDN
  - `cache_previews` — массовая загрузка thumb-превью на CDN из API (без полного парсинга)
  - `dump_parsed_boats --split` — экспорт в JSON по частям (для переноса на сервер)
  - `load_parsed_boats` — потоковая загрузка fixture (экономит RAM на VPS)
  - `upload_existing_images_to_s3` — загрузка полной галереи в S3

### ⚙️ Configuration
Environment and infrastructure setup:
- **[../.env.example](../.env.example)** - Unified .env template
  - Django security settings
  - Database connection
- **[../docker-compose.prod.yml](../docker-compose.prod.yml)** 🆕 - Production Docker Compose
  - Isolated backend network
  - Nginx reverse proxy
  - Health checks
  - Redis password protection
- **[../nginx/](../nginx/)** 🆕 - Nginx configuration files
  - Main configuration with gzip & rate limiting
  - Site configuration with SSL/TLS
  - Security headers
  - Redis/Celery configuration
  - AWS S3 credentials
  - SSL/TLS settings

- **[./PRODUCTION_INIT.md](./archive/PRODUCTION_INIT.md)** - S3 & ParsedBoat initialization
  - S3 bucket setup
  - Image upload workflow
  - Fixture export/import

### ❓ Help & Troubleshooting
- **[FAQ.md](./FAQ.md)** 🆕 - Frequently Asked Questions
  - General questions (tech stack, open source)
  - Development setup & languages
  - Deployment & production (requirements, SSL, monitoring, backups)
  - Boat parsing (how it works, timing, monitoring)
  - Offers & pricing (types, permissions, calculations)
  - Troubleshooting (Docker, database, Celery, images, API, SSL, performance, translations)
- **[../Makefile](../Makefile)** 🆕 - Quick command reference
  - Development shortcuts (build, up, logs, shell)
  - Database operations (migrate, backup, restore)
  - Testing (test, coverage, lint)
  - Boat parsing helpers
  - Production deployment

---

## 📋 Directory Structure

```
docs/
├── INDEX.md (this file)
├── TASK_STATE.md               # Current priorities and progress
├── DECISIONS.md                # ADR-lite decisions and invariants
├── KNOWN_ISSUES.md             # Active bugs/risks and mitigations
├── DEV_LOG.md                  # Chronological engineering log
├── QUICK_DEPLOY.md              # Fast bash deployment (~30 min)
├── PRODUCTION_UBUNTU_DEPLOYMENT.md  # Detailed step-by-step guide
├── PRODUCTION_INIT.md           # S3 & database initialization
├── API_DOCUMENTATION.md         # REST API reference
├── FAQ.md                       # Frequently asked questions
└── I18N_*.md                    # Internationalization guides

../
├── .github/
│   └── copilot-instructions.md  # AI agent architecture guide
├── .env.example                 # Unified .env template
├── AGENTS.md                    # Persistent working protocol for agents
├── README.md                    # Main project documentation
├── deploy.sh, setup-ssl.sh      # Deployment scripts
├── docker-compose.yml           # Local dev environment
├── Dockerfile, Makefile
└── requirements.txt

docs/
└── archive/
  ├── PRODUCTION_READINESS_SUMMARY.md
  ├── READY_FOR_PRODUCTION.md
  └── CLEANUP_SUMMARY.md
```

---

## 🚀 Deployment Flow (Start to Finish)

### Step 1: Plan (Review Documentation)
1. Read: [README.md](../README.md) - Overall architecture and features
2. Review: [PRODUCTION_UBUNTU_DEPLOYMENT.md](./archive/PRODUCTION_UBUNTU_DEPLOYMENT.md) - What will be installed
3. Prepare: [../DEPLOYMENT_CHECKLIST_FINAL.md](../DEPLOYMENT_CHECKLIST_FINAL.md) - 200+ checklist items

### Step 2: Configure
1. Create server on Ubuntu 20.04+ (4GB+ RAM, 50GB+ storage)
2. Copy [../.env.example](../.env.example) → `.env`
3. Fill in: SECRET_KEY, DOMAIN, DATABASE credentials, AWS keys

### Step 3: Deploy
1. SSH into server
2. Execute: [QUICK_DEPLOY.md](./archive/QUICK_DEPLOY.md) commands (or follow detailed steps)
3. Verify: [../DEPLOYMENT_CHECKLIST_FINAL.md](../DEPLOYMENT_CHECKLIST_FINAL.md)

### Step 4: Populate Data
1. Parse boats: `python manage.py parse_boats_parallel --workers 5` (парсинг HTML + загрузка thumb-превью на CDN)
2. Or load from fixture: `python manage.py load_parsed_boats boats/fixtures/split/`
3. Upload CDN previews (без полного парсинга): `python manage.py cache_previews --workers 5`
4. Upload full gallery to S3: `python manage.py upload_existing_images_to_s3`

### Step 5: Monitor & Maintain
- Daily: Check error logs
- Weekly: Database backups
- Monthly: OS updates, SSL cert renewal
- Quarterly: Re-parse boats for fresh data

---

## 🎯 Common Scenarios

### "I want to deploy this in 30 minutes"
→ [QUICK_DEPLOY.md](./archive/QUICK_DEPLOY.md)

### "I need step-by-step instructions with explanations"
→ [PRODUCTION_UBUNTU_DEPLOYMENT.md](./archive/PRODUCTION_UBUNTU_DEPLOYMENT.md)

### "I need to verify everything before going live"
→ [DEPLOYMENT_CHECKLIST.md](../DEPLOYMENT_CHECKLIST_FINAL.md)

### "I need to understand the architecture"
→ [.github/copilot-instructions.md](../.github/copilot-instructions.md)

### "I need to parse ~28,000 boats"
→ [BOAT_PARSING_GUIDE.md](../.github/copilot-instructions.md)

### "I need to set up S3 and upload images"
→ [PRODUCTION_INIT.md](./archive/PRODUCTION_INIT.md)

### "Something is broken in production"
→ [PRODUCTION_UBUNTU_DEPLOYMENT.md](./PRODUCTION_UBUNTU_DEPLOYMENT.md#-troubleshooting)

---

## 📊 System Architecture Summary

```
Internet
  ↓
Nginx (SSL/TLS, reverse proxy)
  ↓
Gunicorn (WSGI app server, 2 workers + 2 threads)
  ↓
Django Application
  ├─ boats/ (core app with dual API integration)
  ├─ accounts/ (user authentication)
  └─ templates/ (Alpine.js-driven UI)
    ↓
PostgreSQL (Django ORM, ParsedBoat model)
Redis (Celery broker + Django cache, DB 0/1)
  ↓
Celery Worker (async parsing, image download)
  ↓
parser.py (HTML scraper via BeautifulSoup)
  ↓
VK Cloud S3 (gallery images + thumb previews)
  ↓
CDN cdn2.prvms.ru (раздача изображений)
```

**Key Characteristic**: Dual-layer integration (JSON API + HTML parser) with local caching enables offline-first experience.

---

## 🔒 Security Highlights

- ✅ SSL/TLS with automatic renewal (Let's Encrypt)
- ✅ PostgreSQL with authentication
- ✅ Redis with password auth in production (internal network)
- ✅ UFW firewall (SSH, HTTP, HTTPS only)
- ✅ CSRF protection, secure cookies, HSTS headers
- ✅ AWS S3 public-read images (appropriate for public boat listings)

---

## 📈 Performance Targets

| Metric | Target | Actual |
|--------|--------|--------|
| Boat detail page (from cache) | <200ms | ~100ms |
| Boat search (API call) | <3s | 2-3s |
| Parse 1 boat (HTML) | 2-3s | 2-3s |
| Parse ~28,000 boats | <24h | ~15-20h |
| Gunicorn response time | <500ms | ~200-300ms |

---

## 🆘 Getting Help

### If deployment fails:
1. Check relevant doc section
2. Review [PRODUCTION_UBUNTU_DEPLOYMENT.md](./PRODUCTION_UBUNTU_DEPLOYMENT.md#-troubleshooting)
3. Check system logs: `sudo journalctl -xe`
4. Check service logs: `sudo systemctl status service-name`

### If parsing is slow:
1. Check Celery worker: `sudo systemctl status boatapp-celery`
2. Monitor Redis: `redis-cli info stats`
3. Increase workers: Edit `boatapp-celery.service` `--concurrency=8`

### If images aren't loading:
1. Verify S3 bucket: AWS console
2. Check CDN access: `curl https://imageresizer.yachtsbt.com/...`
3. Review template image handling in [.github/copilot-instructions.md](../.github/copilot-instructions.md)

---

## 📞 Documentation Maintainers

These docs are generated from live codebase (boats/parser.py, boats/boataround_api.py, etc.)

**Last Updated**: April 2026
**Tested**: Ubuntu 22.04 LTS, Python 3.13, Django 5.2 LTS
**Status**: Production-ready ✅

---

**Next Step**: Start with [STAGING_RUNBOOK.md](./STAGING_RUNBOOK.md) or [TRIAL_DEPLOY_CHECKLIST.md](./TRIAL_DEPLOY_CHECKLIST.md)
