# 🚀 Production Deployment Checklist

Use this checklist before deploying to production. Check off each item as you complete it.

---

## 📋 Pre-Deployment (Code & Configuration)

### Django Settings
- [ ] `DEBUG = False` in `boat_rental/settings.py`
- [ ] `SECRET_KEY` generated and stored in `.env` (50+ characters)
- [ ] `ALLOWED_HOSTS` configured with actual domain(s)
- [ ] `SECURE_SSL_REDIRECT = True`
- [ ] `SESSION_COOKIE_SECURE = True`
- [ ] `CSRF_COOKIE_SECURE = True`
- [ ] `SECURE_HSTS_SECONDS = 31536000`
- [ ] `X_FRAME_OPTIONS = 'DENY'`
- [ ] `SECURE_CONTENT_TYPE_NOSNIFF = True`
- [ ] All hardcoded secrets removed from code

### Database
- [ ] PostgreSQL 12+ installed and running
- [ ] Strong database password (16+ characters, mixed)
- [ ] `DATABASE_URL` in `.env` with correct credentials
- [ ] Database created: `createdb boat_rental`
- [ ] Database user created with limited privileges
- [ ] Migrations applied: `python manage.py migrate`
- [ ] Database backups configured (pg_dump daily)
- [ ] Test database connection

### Redis & Celery
- [ ] Redis 7+ installed and running
- [ ] Redis password configured (if public facing)
- [ ] `CELERY_BROKER_URL` in `.env`
- [ ] `CELERY_RESULT_BACKEND` in `.env`
- [ ] Celery worker systemd service created
- [ ] Celery beat systemd service created (if needed)
- [ ] Test Celery: `python manage.py shell` → `from boats.tasks import dummy_task; dummy_task.delay()`

### Static Files & Media
- [ ] `STATIC_ROOT` configured
- [ ] Static files collected: `python manage.py collectstatic --noinput`
- [ ] `MEDIA_ROOT` configured and writable
- [ ] S3 credentials in `.env` (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
- [ ] S3 bucket created and accessible
- [ ] Test S3 upload/download

### Environment Variables
- [ ] `.env` file created from `.env.example`
- [ ] All required variables filled in `.env`
- [ ] `.env` excluded from git (check `.gitignore`)
- [ ] Environment variables loaded correctly (test with `python manage.py shell`)

---

## 🔒 Security Checks

### Server Security
- [ ] Firewall configured (UFW or iptables)
- [ ] Only necessary ports open: 22 (SSH), 80 (HTTP), 443 (HTTPS)
- [ ] SSH key-based authentication enabled
- [ ] SSH password authentication disabled
- [ ] Root login disabled
- [ ] Fail2ban installed and configured
- [ ] Automatic security updates enabled

### Application Security
- [ ] All user input sanitized (Django templates auto-escape by default)
- [ ] CSRF protection enabled (Django default)
- [ ] SQL injection protection (using Django ORM)
- [ ] XSS protection enabled
- [ ] Secure password hashing (PBKDF2 default)
- [ ] Rate limiting considered (django-ratelimit)
- [ ] File upload validation (if applicable)

### SSL/TLS
- [ ] Domain name configured (A/CNAME records)
- [ ] SSL certificate obtained (Let's Encrypt)
- [ ] Nginx configured for HTTPS
- [ ] HTTP to HTTPS redirect working
- [ ] SSL certificate auto-renewal configured (certbot)
- [ ] Test SSL: https://www.ssllabs.com/ssltest/

---

## 🌐 Web Server (Nginx)

### Nginx Configuration
- [ ] Nginx installed
- [ ] Site configuration created: `/etc/nginx/sites-available/boatrental`
- [ ] Symlink created: `/etc/nginx/sites-enabled/boatrental`
- [ ] Nginx configured as reverse proxy to Gunicorn
- [ ] Static files served directly by Nginx
- [ ] Gzip compression enabled
- [ ] Client max body size set (for uploads)
- [ ] Nginx syntax check: `sudo nginx -t`
- [ ] Nginx reloaded: `sudo systemctl reload nginx`
- [ ] Nginx enabled on boot: `sudo systemctl enable nginx`

---

## 🦄 Application Server (Gunicorn)

### Gunicorn Configuration
- [ ] Gunicorn installed: `pip install gunicorn`
- [ ] Gunicorn systemd service created: `/etc/systemd/system/gunicorn.service`
- [ ] Worker count configured: `workers = (2-4) * CPU_CORES`
- [ ] Worker class: `sync` or `gevent`
- [ ] Timeout configured (default 30s)
- [ ] Access and error logs configured
- [ ] Test Gunicorn: `gunicorn boat_rental.wsgi:application --bind 0.0.0.0:8000`
- [ ] Gunicorn service started: `sudo systemctl start gunicorn`
- [ ] Gunicorn enabled on boot: `sudo systemctl enable gunicorn`
- [ ] Verify Gunicorn status: `sudo systemctl status gunicorn`

---

## 📦 Dependencies & Requirements

### Python Environment
- [ ] Python 3.8+ installed
- [ ] Virtual environment created: `python3 -m venv venv`
- [ ] Virtual environment activated
- [ ] Requirements installed: `pip install -r requirements.txt`
- [ ] Requirements frozen: `pip freeze > requirements.txt` (if updated)

### System Dependencies
- [ ] PostgreSQL client libraries: `libpq-dev`
- [ ] Image processing libraries: `libjpeg-dev`, `libpng-dev` (for Pillow)
- [ ] Git installed (for deployment)

---

## 🗃️ Database Operations

### Initial Setup
- [ ] Superuser created: `python manage.py createsuperuser`
- [ ] Admin accessible: `https://yourdomain.com/admin/`
- [ ] User roles configured (tourist, captain, manager, admin)
- [ ] Test user accounts created for each role

### Data Import
- [ ] Initial boat parsing planned (28k boats ~15-20 hours)
- [ ] Parsing scheduled for off-peak hours (e.g., 2 AM)
- [ ] Parsing command ready: `python manage.py parse_all_boats --async --batch-size 50`
- [ ] Monitor parsing progress: `docker-compose logs -f celery_worker`

---

## 🧪 Testing in Production

### Smoke Tests
- [ ] Homepage loads: `https://yourdomain.com/`
- [ ] Search page works with dates
- [ ] Boat detail page loads with prices
- [ ] User registration works
- [ ] User login/logout works
- [ ] Offer creation works (captain role)
- [ ] Offer creation works (manager role with type selection)
- [ ] Offer viewing works (tourist vs captain templates)
- [ ] Multi-language URLs work: `/ru/`, `/en/`, `/de/`, etc.
- [ ] Image loading works (CDN + S3 fallback)
- [ ] Forms submit correctly (CSRF protection working)

### Performance Tests
- [ ] Page load time < 3 seconds
- [ ] Search response time < 2 seconds
- [ ] API response time < 1 second
- [ ] Static files load quickly (Nginx gzip)
- [ ] No 500 errors in logs
- [ ] No 404 errors for static files

### Celery Tests
- [ ] Celery worker running: `sudo systemctl status celery-worker`
- [ ] Test task execution: `python manage.py shell` → `dummy_task.delay()`
- [ ] Monitor Celery logs: `sudo journalctl -u celery-worker -f`
- [ ] Retry logic working (max_retries=3)

---

## 📊 Monitoring & Logging

### Logging Setup
- [ ] Django logs configured in `settings.py`
- [ ] Log rotation configured: `/etc/logrotate.d/boatrental`
- [ ] Nginx logs accessible: `/var/log/nginx/`
- [ ] Gunicorn logs accessible: `/var/log/gunicorn/`
- [ ] Celery logs accessible: `sudo journalctl -u celery-worker`
- [ ] Error logs monitored for issues

### Monitoring Tools (Optional but Recommended)
- [ ] Uptime monitoring: UptimeRobot, Pingdom, or similar
- [ ] Error tracking: Sentry configured (SENTRY_DSN in .env)
- [ ] Server monitoring: New Relic, Datadog, or similar
- [ ] Disk space alerts configured
- [ ] Database size monitoring
- [ ] Celery task monitoring: Flower installed

---

## 🔄 Backup & Recovery

### Backup Strategy
- [ ] Database backups automated (daily pg_dump)
- [ ] Backup storage location configured (S3, separate server)
- [ ] Backup retention policy defined (e.g., 30 days)
- [ ] Code repository backed up (GitHub, GitLab)
- [ ] `.env` file backed up securely (encrypted)
- [ ] Media files backup strategy (S3 already backed up)

### Recovery Plan
- [ ] Database restore tested: `psql < backup.sql`
- [ ] Application restore procedure documented
- [ ] Disaster recovery plan written
- [ ] RTO (Recovery Time Objective) defined
- [ ] RPO (Recovery Point Objective) defined

---

## 📱 DNS & Domain

### DNS Configuration
- [ ] Domain name purchased
- [ ] A record pointing to server IP
- [ ] CNAME record for www subdomain (if needed)
- [ ] DNS propagation verified (dig, nslookup)
- [ ] TTL set appropriately (300-3600 seconds)

---

## 🚦 Go-Live Checklist

### Final Verification
- [ ] All above sections completed ✅
- [ ] Team notified of go-live time
- [ ] Maintenance page ready (if needed)
- [ ] Rollback plan prepared
- [ ] Monitoring dashboards open
- [ ] Support team on standby

### Go-Live Steps
1. [ ] Final code push to production branch
2. [ ] Pull latest code on server: `git pull origin main`
3. [ ] Install/update dependencies: `pip install -r requirements.txt`
4. [ ] Run migrations: `python manage.py migrate`
5. [ ] Collect static files: `python manage.py collectstatic --noinput`
6. [ ] Restart services:
   - [ ] `sudo systemctl restart gunicorn`
   - [ ] `sudo systemctl restart celery-worker`
   - [ ] `sudo systemctl reload nginx`
7. [ ] Verify site is up: `curl -I https://yourdomain.com`
8. [ ] Check for errors in logs
9. [ ] Run smoke tests
10. [ ] Monitor for 1 hour

### Post Go-Live (First 24 Hours)
- [ ] Monitor error logs continuously
- [ ] Check server resources (CPU, RAM, disk)
- [ ] Verify Celery tasks executing
- [ ] Monitor database performance
- [ ] Check user feedback/reports
- [ ] Parse initial boats if not done: `python manage.py parse_all_boats --async`

---

## 🎉 Success Criteria

### Technical Metrics
- [ ] Uptime > 99.9%
- [ ] Average response time < 2 seconds
- [ ] Error rate < 0.1%
- [ ] All services healthy (green status)
- [ ] No critical errors in logs

### Business Metrics
- [ ] Users can register/login
- [ ] Search returns results
- [ ] Offers can be created by authorized users
- [ ] Boats display correctly with images
- [ ] Multi-language switching works

---

## 📞 Support Contacts

**Emergency Contacts:**
- DevOps Lead: [Name] - [Email] - [Phone]
- Backend Developer: [Name] - [Email] - [Phone]
- Database Admin: [Name] - [Email] - [Phone]

**Service Providers:**
- Hosting: [Provider] - [Support Link]
- Domain Registrar: [Provider] - [Support Link]
- SSL Certificate: Let's Encrypt (auto-renew)

---

## 🔍 Troubleshooting Quick Reference

**Site not loading:**
```bash
sudo systemctl status nginx
sudo systemctl status gunicorn
sudo nginx -t
sudo journalctl -u gunicorn -n 50
```

**500 errors:**
```bash
tail -f /var/log/gunicorn/error.log
python manage.py check --deploy
```

**Celery not working:**
```bash
sudo systemctl status celery-worker
sudo journalctl -u celery-worker -f
redis-cli ping
```

**Database issues:**
```bash
sudo systemctl status postgresql
psql -U boat_user -d boat_rental -c "SELECT version();"
```

---

**Last Updated:** 2026-02-01

**Checklist Version:** 1.2.0

**Notes:** This checklist should be reviewed and updated with each major release.
