#!/usr/bin/env python
"""Create test users with different roles"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'boat_rental.settings')
django.setup()

from django.contrib.auth.models import User
from accounts.models import UserProfile

users_data = [
    {'username': 'turist1', 'password': 'kapitan123', 'email': 'turist1@kapitan-trips.ru', 'role': 'tourist'},
    {'username': 'manager1', 'password': 'kapitan123', 'email': 'manager1@kapitan-trips.ru', 'role': 'manager'},
    {'username': 'agent1', 'password': 'kapitan123', 'email': 'agent1@kapitan-trips.ru', 'role': 'captain'},
    {'username': 'kapitan1', 'password': 'kapitan123', 'email': 'kapitan1@kapitan-trips.ru', 'role': 'captain'},
]

print("=== СОЗДАНИЕ ПОЛЬЗОВАТЕЛЕЙ ===\n")

for user_data in users_data:
    username = user_data['username']
    
    if User.objects.filter(username=username).exists():
        user = User.objects.get(username=username)
        profile = user.profile
        old_role = profile.role
        profile.role = user_data['role']
        profile.save()
        print(f'✅ Обновлен: {username} ({old_role} -> {user_data["role"]})')
    else:
        user = User.objects.create_user(
            username=username,
            email=user_data['email'],
            password=user_data['password']
        )
        profile = user.profile
        profile.role = user_data['role']
        profile.save()
        print(f'✅ Создан: {username} (роль: {user_data["role"]}, email: {user_data["email"]})')

print("\n=== СТАТИСТИКА ПО РОЛЯМ ===")
for role_code, role_name in UserProfile.ROLE_CHOICES:
    count = UserProfile.objects.filter(role=role_code).count()
    print(f'{role_name}: {count}')

print("\n=== СПИСОК ВСЕХ ПОЛЬЗОВАТЕЛЕЙ ===")
for profile in UserProfile.objects.select_related('user').all():
    role_display = dict(UserProfile.ROLE_CHOICES).get(profile.role, profile.role)
    print(f'{profile.user.username:15} | {profile.user.email:35} | {role_display}')
