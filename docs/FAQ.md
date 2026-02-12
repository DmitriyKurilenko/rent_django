# Frequently Asked Questions (FAQ)

## Table of Contents
- [General Questions](#general-questions)
- [Development](#development)
- [Deployment & Production](#deployment--production)
- [Boat Parsing](#boat-parsing)
- [Offers & Pricing](#offers--pricing)
- [Troubleshooting](#troubleshooting)

---

## General Questions

### What is BoatRental?
BoatRental is a Django-based boat rental platform that integrates with boataround.com to provide search, booking, and offer management for ~28,000 boats worldwide.

### What technologies are used?
- **Backend**: Django 4.2, PostgreSQL 15, Redis 7, Celery 5.3
- **Frontend**: Alpine.js, Tailwind CSS, DaisyUI (JSON API + fetch)
- **External API**: boataround.com REST API + BeautifulSoup HTML parsing
- **Storage**: VK Cloud S3 + Free CDN (imageresizer.yachtsbt.com)
- **Deployment**: Docker, Nginx, Gunicorn, systemd

### Is this project open source?
Yes, the project uses MIT license. See [LICENSE](../LICENSE) for details.

---

## Development

### How do I set up the development environment?

**Quick Start:**
```bash
# Clone repository
git clone <repository-url>
cd rent_django

# Start all services
docker-compose up

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Access at http://localhost:8000
```

**Using Makefile:**
```bash
make up        # Start services
make logs-web  # View Django logs
make shell     # Open Django shell
```

See [CONTRIBUTING.md](../CONTRIBUTING.md) for detailed setup instructions.

### Why use Docker?
Docker ensures consistent environments across development, testing, and production. All dependencies (PostgreSQL, Redis, Celery) are pre-configured.

### Can I run without Docker?
Yes, but you'll need to manually install:
- Python 3.8+
- PostgreSQL 15
- Redis 7
- Configure environment variables

See [PRODUCTION_UBUNTU_DEPLOYMENT.md](./PRODUCTION_UBUNTU_DEPLOYMENT.md) for manual setup.

### How do I add a new language?

1. Add language to `settings.py`:
```python
LANGUAGES = [
    ('en', 'English'),
    ('ru', 'Русский'),
    ('de', 'Deutsch'),
    ('es', 'Español'),
    ('fr', 'Français'),
    ('it', 'Italiano'),  # New language
]
```

2. Generate translation files:
```bash
make messages  # Or python manage.py makemessages -l it
```

3. Edit translations in `locale/it/LC_MESSAGES/django.po`

4. Compile:
```bash
make compilemessages
```

See [I18N_ARCHITECTURE.md](./I18N_ARCHITECTURE.md) for full guide.

---

## Deployment & Production

### What are the server requirements?

**Minimum:**
- 2 CPU cores
- 4 GB RAM
- 50 GB SSD
- Ubuntu 20.04+

**Recommended:**
- 4 CPU cores
- 8 GB RAM
- 100 GB SSD
- Ubuntu 22.04 LTS

See [PRODUCTION_UBUNTU_DEPLOYMENT.md](./PRODUCTION_UBUNTU_DEPLOYMENT.md) section 1.

### How long does initial deployment take?
- Server setup: 30-60 minutes
- Initial boat parsing: 15-20 hours (for ~28,000 boats)
- Total: ~1 day including parsing

### How do I deploy to production?

**Automated (Recommended):**
```bash
# Copy and configure environment
cp .env.example .env
nano .env

# Run deployment script
./deploy.sh
```

**Manual:**
Follow [DEPLOYMENT_CHECKLIST_FINAL.md](../DEPLOYMENT_CHECKLIST_FINAL.md).

### How do I setup SSL certificates?

**Automated:**
```bash
sudo ./setup-ssl.sh
```

**Manual with Certbot:**
```bash
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

Certificates auto-renew every 60 days.

### How do I monitor the application?
```bash
# Docker logs
docker-compose -f docker-compose.prod.yml logs -f web

# Celery tasks
docker-compose -f docker-compose.prod.yml logs -f celery_worker

# System resources
htop

# Database
docker-compose -f docker-compose.prod.yml exec db psql -U $DB_USER $DB_NAME
```

See [Monitoring section](./DEPLOYMENT_CHECKLIST_FINAL.md#monitoring--logging) in deployment checklist.

### How do I backup the database?

**Using Makefile:**
```bash
make backup
```

**Manual:**
```bash
docker-compose exec -T db pg_dump -U admin boat_rental > backups/backup_$(date +%Y%m%d).sql
```

**Restore:**
```bash
make restore FILE=backups/backup_20260201.sql
```

See [DEPLOYMENT_CHECKLIST_FINAL.md](../DEPLOYMENT_CHECKLIST_FINAL.md#backup--recovery).

---

## Boat Parsing

### How does boat parsing work?

BoatRental uses a **dual-layer integration**:
1. **REST API** (fast): Search results, autocomplete, pricing
2. **HTML Parsing** (slow but complete): Detailed specs, images, equipment

Data is cached in `ParsedBoat` model with 24-hour TTL.

### How long does parsing take?
- **Single boat**: ~10 seconds
- **5 boats (test)**: 30 seconds
- **100 boats**: ~15 minutes (async with batch_size=50)
- **28,000 boats**: 15-20 hours

### How do I parse boats?

**Test (5 boats):**
```bash
make parse-test
```

**Production (1000 boats):**
```bash
make parse-async LIMIT=1000
```

**Specific destination:**
```bash
make parse-turkey
```

See [BOAT_PARSING_GUIDE.md](../BOAT_PARSING_GUIDE.md) for complete workflow.

### Why use async parsing?
Synchronous parsing of 28k boats would take days and block the terminal. Async parsing uses Celery workers to parse in parallel with automatic retries.

### How do I monitor parsing progress?

**Watch Celery logs:**
```bash
make logs-celery
```

**Check database:**
```bash
docker-compose exec web python manage.py shell
>>> from boats.models import ParsedBoat
>>> ParsedBoat.objects.count()
>>> ParsedBoat.objects.filter(last_parse_success=True).count()
```

### Can I skip already parsed boats?
Yes, use `--skip-existing` flag:
```bash
docker-compose exec web python manage.py parse_all_boats --async --skip-existing --limit 5000
```

### What if parsing fails?
Failed boats are tracked with `last_parse_success=False`. Celery automatically retries 3 times with exponential backoff (60s, 120s, 240s).

**Find failed boats:**
```python
from boats.models import ParsedBoat
failed = ParsedBoat.objects.filter(last_parse_success=False)
```

---

## Offers & Pricing

### What are offer types?

1. **Captain Offers**: Detailed offers with full boat specifications
2. **Tourist Offers**: Simplified, beautiful offers for client viewing

### Who can create offers?

| Role | Captain Offers | Tourist Offers |
|------|----------------|----------------|
| Tourist | ❌ | ❌ |
| Captain | ✅ | ❌ |
| Manager | ✅ | ✅ |
| Admin | ✅ | ✅ |

### How does quick offer creation work?
From boat detail page → "Создать оффер" button → Modal (role-based) → Direct offer creation → Redirect to offer detail.

See [Quick Offer Creation](.github/copilot-instructions.md#quick-offer-creation-one-click-from-detail-page).

### How is pricing calculated?

**Base Price** comes from API:
```python
price = BoataroundAPI.get_price(boat_id, check_in, check_out, currency='EUR')
```

**Tourist Offers** include extras:
```python
total_price = calculate_tourist_price(
    base_price=price,
    has_meal=True,
    destination='turkey',
    rental_days=7
)
```

See `boats/helpers.py` for pricing logic.

### Why are some boats missing specs?
The external API (`boataround.com`) doesn't provide complete specs in search results. We parse HTML for complete data, but it takes time. Use `parse_boat_detail` task to fetch missing data.

---

## Troubleshooting

### Docker containers won't start

**Check logs:**
```bash
docker-compose logs
```

**Common issues:**
- Port 8000 already in use: Change in `docker-compose.yml`
- Database connection failed: Check `DATABASE_URL` in `.env`
- Redis connection failed: Ensure Redis is running

### Database migration errors

**Reset migrations (DANGEROUS):**
```bash
# Backup first!
make backup

# Reset database
make reset-db
```

**Specific migration issues:**
```bash
# Show migrations
docker-compose exec web python manage.py showmigrations

# Fake a migration
docker-compose exec web python manage.py migrate boats 0001 --fake
```

### Celery tasks not running

**Check Celery is running:**
```bash
docker-compose ps celery_worker
```

**Check Redis connection:**
```bash
docker-compose exec redis redis-cli ping
# Expected: PONG
```

**Test task manually:**
```python
from boats.tasks import parse_boat_detail
result = parse_boat_detail.delay('bavaria-cruiser-46-2022')
print(result.id)
```

### Images not loading

**Check image URL structure:**
1. **CDN (free)**: `https://imageresizer.yachtsbt.com/...` 
2. **S3 (fallback)**: `https://yachts.hb.ru-msk.vkcloud-storage.ru/boats/...`

**Template automatically tries both** via `cdn_tags.py` template filter.

**Check S3 credentials:**
```python
from boats.helpers import upload_image_to_s3
upload_image_to_s3(local_path, s3_key)
```

### External API rate limiting

**Symptoms:**
- 429 status codes
- Slow responses
- Connection timeouts

**Solution:**
- Use `--async` parsing with `--batch-size 50` (default)
- Lower batch size: `--batch-size 25`
- Add delays in `boats/parser.py` if needed

### SSL certificate issues

**Certificate not found:**
```bash
sudo certbot certificates
```

**Renewal failed:**
```bash
sudo certbot renew --dry-run
```

**Manual renewal:**
```bash
sudo certbot renew
sudo systemctl reload nginx
```

### Performance issues

**Database slow queries:**
```sql
-- Enable query logging
ALTER SYSTEM SET log_min_duration_statement = 1000;  -- Log queries > 1s
SELECT pg_reload_conf();

-- Check slow queries
SELECT * FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;
```

**Too many Celery tasks:**
```bash
# Check queue length
docker-compose exec redis redis-cli LLEN celery

# Clear queue (CAREFUL!)
docker-compose exec redis redis-cli FLUSHALL
```

**Memory issues:**
```bash
# Check memory usage
docker stats

# Increase worker memory limit in docker-compose.yml
```

### Translation not working

**Compile messages:**
```bash
make compilemessages
```

**Check locale directory:**
```bash
ls -la locale/ru/LC_MESSAGES/
# Should contain django.po and django.mo
```

**Force language in view:**
```python
from django.utils.translation import activate
activate('ru')
```

---

## Still Need Help?

### Documentation
- 📖 [README.md](../README.md) - Project overview
- 🔧 [CONTRIBUTING.md](../CONTRIBUTING.md) - Development guide
- 🔒 [SECURITY.md](../SECURITY.md) - Security policy
- 📝 [API_DOCUMENTATION.md](./API_DOCUMENTATION.md) - API reference

### Support Channels
- 💬 GitHub Discussions
- 📧 Email: support@boatrental.com
- 🐛 GitHub Issues (for bugs)

### Debugging Checklist
1. Check logs: `make logs`
2. Verify environment variables: `.env`
3. Test database connection: `make dbshell`
4. Check Redis: `docker-compose exec redis redis-cli ping`
5. Review recent changes: `git log`
6. Search GitHub issues
7. Create new issue with reproduction steps

---

**Last Updated:** 2026-02-01
