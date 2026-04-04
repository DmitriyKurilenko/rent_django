# 🚀 Quick Production Deployment (Ubuntu 20.04+)

## 5-Minute Setup Overview

```bash
# 1. Server Prep (first time only)
sudo apt update && sudo apt install -y python3 python3-pip postgresql redis-server nginx
sudo useradd -m -s /bin/bash boatapp && sudo su - boatapp

# 2. Clone & Setup
cd /home/boatapp
git clone https://github.com/yourusername/rent_django.git && cd rent_django
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 3. Configure PostgreSQL
sudo -u postgres psql
CREATE USER boat_user WITH PASSWORD 'strongpassword';
CREATE DATABASE boat_rental OWNER boat_user;
\q

# 4. Django Setup
cat > .env << 'EOF'
SECRET_KEY=your-random-secret-key-here-50-chars-min
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DATABASE_URL=postgresql://boat_user:strongpassword@localhost:5432/boat_rental
CELERY_BROKER_URL=redis://localhost:6379/0
AWS_ACCESS_KEY_ID=your-aws-key
AWS_SECRET_ACCESS_KEY=your-aws-secret
AWS_STORAGE_BUCKET_NAME=boat-images
AWS_S3_REGION_NAME=eu-west-1
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
EOF

python manage.py collectstatic --noinput
python manage.py migrate
python manage.py createsuperuser

# 5. Install SSL (Let's Encrypt)
sudo apt install -y certbot python3-certbot-nginx
sudo certbot certonly --nginx -d yourdomain.com -d www.yourdomain.com

# 6. Nginx Config
sudo tee /etc/nginx/sites-available/boatapp > /dev/null << 'EOF'
upstream app {
    server unix:/home/boatapp/rent_django/gunicorn.sock;
}

server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;
    
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    
    location /static/ {
        alias /home/boatapp/rent_django/staticfiles/;
    }
    
    location / {
        proxy_pass http://app;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/boatapp /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx

# 7. Gunicorn Systemd Service
sudo tee /etc/systemd/system/boatapp-gunicorn.service > /dev/null << 'EOF'
[Unit]
Description=Boat Rental Gunicorn
After=network.target postgresql.service

[Service]
User=boatapp
Group=www-data
WorkingDirectory=/home/boatapp/rent_django
ExecStart=/home/boatapp/rent_django/venv/bin/gunicorn \
    --workers 4 --bind unix:gunicorn.sock boat_rental.wsgi:application
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload && sudo systemctl enable boatapp-gunicorn
sudo systemctl start boatapp-gunicorn && sudo systemctl status boatapp-gunicorn

# 8. Celery Worker Systemd Service
sudo tee /etc/systemd/system/boatapp-celery.service > /dev/null << 'EOF'
[Unit]
Description=Boat Rental Celery Worker
After=redis-server.service postgresql.service

[Service]
User=boatapp
Group=www-data
WorkingDirectory=/home/boatapp/rent_django
Environment="PATH=/home/boatapp/rent_django/venv/bin"
ExecStart=/home/boatapp/rent_django/venv/bin/celery -A boat_rental worker -l info
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload && sudo systemctl enable boatapp-celery
sudo systemctl start boatapp-celery && sudo systemctl status boatapp-celery

# 9. Firewall
sudo ufw default deny incoming && sudo ufw default allow outgoing
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
sudo ufw enable

# 10. Parse Boats (runs in background)
source /home/boatapp/rent_django/venv/bin/activate
cd /home/boatapp/rent_django
python manage.py parse_all_boats --async

# 11. Upload Images to S3
python manage.py upload_existing_images_to_s3 --skip-existing
```

---

## ✅ Verification

```bash
# Check all services
sudo systemctl status boatapp-gunicorn boatapp-celery nginx postgresql redis-server

# Test site
curl https://yourdomain.com  # Should work
curl https://yourdomain.com/admin/  # Should work

# Check cache
python manage.py shell
from boats.models import ParsedBoat
print(f"Cached boats: {ParsedBoat.objects.count()}")  # Should show ~28,000
```

---

## 📊 Monitoring

```bash
# Watch Celery tasks
tail -f /home/boatapp/rent_django/logs/celery.log

# Check Gunicorn
tail -f /home/boatapp/rent_django/logs/gunicorn_error.log

# Nginx
sudo tail -f /var/log/nginx/error.log

# Progress
echo "Running tasks:" && redis-cli llen celery
```

---

## 🐛 Troubleshooting

```bash
# Service won't start?
sudo systemctl status boatapp-gunicorn  # Check error
sudo journalctl -xe  # System logs

# Permission denied?
sudo chown -R boatapp:www-data /home/boatapp/rent_django
sudo chmod 775 /home/boatapp/rent_django/logs

# Celery not working?
sudo systemctl restart redis-server
sudo systemctl restart boatapp-celery

# Database connection?
psql -h localhost -U boat_user -d boat_rental
\q
```

---

## 📚 Full Documentation

For detailed setup instructions, see:
- [PRODUCTION_UBUNTU_DEPLOYMENT.md](./PRODUCTION_UBUNTU_DEPLOYMENT.md)
- [../DEPLOYMENT_CHECKLIST_FINAL.md](../DEPLOYMENT_CHECKLIST_FINAL.md)
- [BOAT_PARSING_GUIDE.md](../BOAT_PARSING_GUIDE.md)
