#!/bin/sh
set -e

echo "==================================="
echo "🚢 BoatRental - Starting..."
echo "==================================="

echo ""
echo "⏳ Waiting 5 seconds for PostgreSQL..."
sleep 5

echo ""
echo "📊 Running makemigrations..."
python manage.py makemigrations accounts
python manage.py makemigrations boats
python manage.py makemigrations

echo ""
echo "🔄 Applying migrations..."
python manage.py migrate --noinput

echo ""
echo "👤 Creating superuser..."
python manage.py shell << END
from django.contrib.auth.models import User
from accounts.models import UserProfile

if not User.objects.filter(username='admin').exists():
    user = User.objects.create_superuser('admin', 'admin@example.com', 'admin')
    # Обновляем роль профиля на admin
    profile = UserProfile.objects.get(user=user)
    profile.role = 'admin'
    profile.save()
    print('✅ Superuser created: admin / admin (role: admin)')
else:
    print('✅ Superuser already exists: admin / admin')
    # Проверяем и обновляем роль если нужно
    user = User.objects.get(username='admin')
    profile, created = UserProfile.objects.get_or_create(user=user)
    if profile.role != 'admin':
        profile.role = 'admin'
        profile.save()
        print('✅ Updated admin role to: admin')
END

echo ""
echo "📦 Collecting static files..."
python manage.py collectstatic --noinput

echo ""
echo "==================================="
echo "✅ Setup complete!"
echo "🌐 Server starting on http://localhost:8000"
echo "🔐 Admin: admin / admin"
echo "==================================="
echo ""

exec daphne -b 0.0.0.0 -p 8000 boat_rental.asgi:application
