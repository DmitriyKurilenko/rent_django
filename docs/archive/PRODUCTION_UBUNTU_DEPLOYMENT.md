# Production Deployment Guide - Ubuntu Server

Полное руководство для деплоя BoatRental на Ubuntu сервер с Nginx, PostgreSQL, Redis и Gunicorn.

## 📋 Pre-Deployment Checklist

### Server Requirements
- Ubuntu 20.04+ (LTS recommended)
- Minimum 4GB RAM (8GB+ for high traffic)
- 50GB+ SSD storage (boats/ media files: ~500MB after parsing)
- Python 3.8+
- Public IP or domain name

### Environment Vars Needed
```
SECRET_KEY=your-django-secret-key-here
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DATABASE_URL=postgresql://boat_user:password@localhost:5432/boat_rental
CELERY_BROKER_URL=redis://localhost:6379/0
AWS_ACCESS_KEY_ID=your-aws-key
AWS_SECRET_ACCESS_KEY=your-aws-secret
AWS_STORAGE_BUCKET_NAME=your-bucket
AWS_S3_REGION_NAME=eu-west-1
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

---

## 🚀 Step 1: Initial Server Setup

### 1.1 Update System
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git curl wget
sudo apt install -y postgresql postgresql-contrib
sudo apt install -y redis-server
sudo apt install -y nginx supervisor
```

### 1.2 Create Application User
```bash
sudo useradd -m -s /bin/bash boatapp
sudo usermod -aG sudo boatapp
sudo su - boatapp
```

### 1.3 Clone Repository
```bash
cd /home/boatapp
git clone https://github.com/yourusername/rent_django.git
cd rent_django
```

### 1.4 Python Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

---

## 🗄️ Step 2: PostgreSQL Setup

### 2.1 Create Database and User
```bash
sudo -i -u postgres
psql

# Inside PostgreSQL shell:
CREATE USER boat_user WITH PASSWORD 'strong_password_here';
CREATE DATABASE boat_rental OWNER boat_user;
ALTER ROLE boat_user SET client_encoding TO 'utf8';
ALTER ROLE boat_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE boat_user SET default_transaction_deferrable TO on;
ALTER ROLE boat_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE boat_rental TO boat_user;
\q
```

### 2.2 Test Connection
```bash
exit  # Back to boatapp user
psql -h localhost -U boat_user -d boat_rental
```

---

## 🔧 Step 3: Django Application Setup

### 3.1 Create .env File
```bash
cat > /home/boatapp/rent_django/.env << 'EOF'
SECRET_KEY=django-insecure-your-secret-key-change-this
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com,127.0.0.1
DATABASE_URL=postgresql://boat_user:strong_password_here@localhost:5432/boat_rental
CELERY_BROKER_URL=redis://localhost:6379/0
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_STORAGE_BUCKET_NAME=boat-rental-images
AWS_S3_REGION_NAME=eu-west-1
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
STATIC_URL=/static/
MEDIA_URL=/media/
EOF
```

### 3.2 Create Directories
```bash
mkdir -p /home/boatapp/rent_django/staticfiles
mkdir -p /home/boatapp/rent_django/media
mkdir -p /home/boatapp/rent_django/logs
```

### 3.3 Run Migrations
```bash
source venv/bin/activate
python manage.py collectstatic --noinput
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser  # Create admin user
```

### 3.4 Optional: Load Parsed Boats Fixture
```bash
# If you have pre-parsed boats (from PRODUCTION_INIT.md)
python manage.py loaddata boats/fixtures/parsed_boats.json
```

### 3.5 Upload Images to S3 (if needed)
```bash
# Dry-run first
python manage.py upload_existing_images_to_s3 --dry-run

# Then upload
python manage.py upload_existing_images_to_s3 --skip-existing
```

---

## 🐳 Step 4: Gunicorn WSGI Server

### 4.1 Create Gunicorn Systemd Service
```bash
sudo tee /etc/systemd/system/boatapp-gunicorn.service > /dev/null << 'EOF'
[Unit]
Description=Boat Rental Django Gunicorn Application
After=network.target postgresql.service redis-server.service
Wants=boatapp-celery.service

[Service]
Type=notify
User=boatapp
Group=www-data
WorkingDirectory=/home/boatapp/rent_django
ExecStart=/home/boatapp/rent_django/venv/bin/gunicorn \
    --workers 4 \
    --worker-class sync \
    --bind unix:/home/boatapp/rent_django/gunicorn.sock \
    --timeout 60 \
    --access-logfile /home/boatapp/rent_django/logs/gunicorn_access.log \
    --error-logfile /home/boatapp/rent_django/logs/gunicorn_error.log \
    boat_rental.wsgi:application
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable boatapp-gunicorn
sudo systemctl start boatapp-gunicorn
sudo systemctl status boatapp-gunicorn
```

### 4.2 Check Socket Created
```bash
ls -la /home/boatapp/rent_django/gunicorn.sock
```

---

## 🔄 Step 5: Celery Worker & Beat Scheduler

### 5.1 Create Celery Worker Service
```bash
sudo tee /etc/systemd/system/boatapp-celery.service > /dev/null << 'EOF'
[Unit]
Description=Boat Rental Celery Worker
After=network.target redis-server.service postgresql.service
PartOf=boatapp-gunicorn.service

[Service]
Type=forking
User=boatapp
Group=www-data
WorkingDirectory=/home/boatapp/rent_django
Environment="PATH=/home/boatapp/rent_django/venv/bin"
ExecStart=/home/boatapp/rent_django/venv/bin/celery \
    -A boat_rental \
    worker \
    -l info \
    --logfile=/home/boatapp/rent_django/logs/celery.log \
    --pidfile=/home/boatapp/rent_django/celery.pid \
    --concurrency=4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable boatapp-celery
sudo systemctl start boatapp-celery
sudo systemctl status boatapp-celery
```

### 5.2 Create Celery Beat Scheduler (Optional - for periodic tasks)
```bash
sudo tee /etc/systemd/system/boatapp-celery-beat.service > /dev/null << 'EOF'
[Unit]
Description=Boat Rental Celery Beat Scheduler
After=boatapp-celery.service redis-server.service

[Service]
Type=simple
User=boatapp
Group=www-data
WorkingDirectory=/home/boatapp/rent_django
Environment="PATH=/home/boatapp/rent_django/venv/bin"
ExecStart=/home/boatapp/rent_django/venv/bin/celery \
    -A boat_rental \
    beat \
    -l info \
    --logfile=/home/boatapp/rent_django/logs/celery_beat.log \
    --scheduler django_celery_beat.schedulers:DatabaseScheduler
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable boatapp-celery-beat
sudo systemctl start boatapp-celery-beat
```

---

## 🌐 Step 6: Nginx Reverse Proxy

### 6.1 Create Nginx Configuration
```bash
sudo tee /etc/nginx/sites-available/boatapp > /dev/null << 'EOF'
upstream boatapp_gunicorn {
    server unix:/home/boatapp/rent_django/gunicorn.sock fail_timeout=0;
}

server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    
    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    # SSL certificates (use Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    client_max_body_size 100M;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;

    location = /favicon.ico { access_log off; log_not_found off; }
    
    location /static/ {
        alias /home/boatapp/rent_django/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
    
    location /media/ {
        alias /home/boatapp/rent_django/media/;
        expires 7d;
    }

    location / {
        proxy_pass http://boatapp_gunicorn;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/boatapp /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default  # Remove default config
sudo nginx -t
sudo systemctl restart nginx
```

### 6.2 Setup SSL with Let's Encrypt (Certbot)
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot certonly --nginx -d yourdomain.com -d www.yourdomain.com
sudo systemctl restart nginx
```

### 6.3 Auto-Renew SSL Certificates
```bash
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
sudo systemctl status certbot.timer
```

---

## 🔐 Step 7: Firewall & Security

### 7.1 Configure UFW Firewall
```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS
sudo ufw enable
```

### 7.2 Permissions
```bash
sudo chown -R boatapp:www-data /home/boatapp/rent_django
sudo chmod -R 755 /home/boatapp/rent_django
sudo chmod -R 775 /home/boatapp/rent_django/media
sudo chmod -R 775 /home/boatapp/rent_django/logs
```

---

## 📊 Step 8: Image Handling Strategy (main_img vs thumb)

### 8.1 parser.py Extracts Two Image URLs
```python
# From boataround.com HTML:
thumb: "https://imageresizer.yachtsbt.com/boats/62b96d15.../650d96fa.jpg"
main_img: "boats/62b96d157a9323583a5a4880/650d96fa43b7cac28800ead4.jpg"
```

### 8.2 Storage Strategy
1. **thumb** (pre-optimized by boataround CDN)
   - Already resized (650px width)
   - Already JPEG compressed
   - Served directly from imageresizer.yachtsbt.com
   - Use in templates: `<img src="{{ boat.boat_data.thumb }}" />`

2. **main_img** (fallback if CDN unavailable)
   - Downloaded via `download_and_save_image()`
   - Stored in S3 at: `s3://bucket/boat_id/filename.jpg`
   - Normalized via `normalize_image_url()` → S3 public URL
   - Use only as fallback: `<img src="{{ boat.boat_data.main_img or boat.boat_data.thumb }}" />`

### 8.3 Production Recommendation
```python
# In templates/boats/detail.html
{# Primary: Use CDN-optimized thumb #}
<img src="{{ boat.boat_data.thumb }}" alt="{{ boat.boat_data.name }}"
     class="boat-hero-image" loading="lazy" />

{# Backup gallery images from S3 #}
{% for img in boat.boat_data.images %}
    {% if img.s3_url %}
        <img src="{{ img.s3_url }}" alt="Boat image" loading="lazy" />
    {% endif %}
{% endfor %}
```

### 8.4 Storage Cost Optimization
- **thumb URLs** = Free (boataround.com CDN serves them)
- **S3 storage** = Only for gallery overflow images or backup
- **Bandwidth** = Minimal (thumbnails come from boataround CDN)

---

## 🔍 Step 9: Monitoring & Logging

### 9.1 Check Service Status
```bash
sudo systemctl status boatapp-gunicorn
sudo systemctl status boatapp-celery
sudo systemctl status nginx
sudo systemctl status postgresql
sudo systemctl status redis-server
```

### 9.2 View Logs
```bash
# Django + Gunicorn
tail -f /home/boatapp/rent_django/logs/gunicorn_error.log

# Celery worker
tail -f /home/boatapp/rent_django/logs/celery.log

# Nginx
sudo tail -f /var/log/nginx/error.log
```

### 9.3 Monitor Celery Tasks
```bash
source venv/bin/activate
python manage.py shell
from celery.app.control import Inspect
i = Inspect()
print(i.active())  # Show running tasks
```

---

## 🔄 Step 10: Bulk Parsing on Production

### 10.1 Parse ~28,000 boats asynchronously
```bash
cd /home/boatapp/rent_django
source venv/bin/activate
python manage.py parse_all_boats --async --batch-size 50

# Monitor progress
tail -f /home/boatapp/rent_django/logs/celery.log
```

### 10.2 Expected Timeline
- ~28,000 boats at 2-3 sec/boat = ~15-20 hours total
- With 4 Celery workers, distribute load effectively
- Increase workers if needed: edit boatapp-celery.service `--concurrency=8`

### 10.3 Upload Images to S3
```bash
python manage.py upload_existing_images_to_s3 --skip-existing
```

---

## 🚨 Troubleshooting

### Issue: Gunicorn socket permission denied
```bash
sudo chown boatapp:www-data /home/boatapp/rent_django/gunicorn.sock
sudo chmod 660 /home/boatapp/rent_django/gunicorn.sock
```

### Issue: Celery tasks not running
```bash
# Restart Redis
sudo systemctl restart redis-server

# Restart Celery
sudo systemctl restart boatapp-celery

# Check broker connection
python manage.py shell
from celery import current_app
current_app.connection().connect()
```

### Issue: Static files not loading
```bash
python manage.py collectstatic --noinput --clear
sudo systemctl restart boatapp-gunicorn
```

### Issue: SSL certificate expired
```bash
sudo certbot renew --dry-run  # Test renewal
sudo certbot renew            # Actual renewal
```

---

## 📈 Performance Tuning (Optional)

### Gunicorn Workers
```bash
# Calculate: (CPU cores * 2) + 1
# For 4 cores: 9 workers
# Edit: /etc/systemd/system/boatapp-gunicorn.service
--workers 9
```

### PostgreSQL Connection Pool (pgBouncer)
```bash
sudo apt install pgbouncer
# Edit /etc/pgbouncer/pgbouncer.ini for connection pooling
```

### Redis Memory Optimization
```bash
# Edit /etc/redis/redis.conf
maxmemory 512mb
maxmemory-policy allkeys-lru
```

---

## ✅ Final Verification Checklist

- [ ] Django running without errors (`curl http://localhost:8000`)
- [ ] Gunicorn socket exists (`ls -la gunicorn.sock`)
- [ ] Nginx reverse proxy works (`curl https://yourdomain.com`)
- [ ] SSL certificate valid (`sudo certbot certificates`)
- [ ] PostgreSQL database accessible
- [ ] Redis connection working
- [ ] Celery worker accepting tasks (`tail -f celery.log`)
- [ ] Static files loading (`/static/admin/css/...`)
- [ ] Admin panel accessible (`/admin/`)
- [ ] Boat detail pages loading from ParsedBoat cache
- [ ] Images serving from S3 or boataround CDN

---

## 🚀 Deployment Complete!

Site is now live at `https://yourdomain.com` with:
- ✅ PostgreSQL database
- ✅ Redis caching + Celery async tasks
- ✅ Nginx reverse proxy with SSL/TLS
- ✅ Gunicorn WSGI server
- ✅ ~28,000 cached boats from parser.py
- ✅ Images served from CDN or S3
