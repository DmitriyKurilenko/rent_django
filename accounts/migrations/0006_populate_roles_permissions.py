"""
Populate Permission records, Role records with permissions,
and migrate UserProfile.role CharField → role_ref FK.
"""

from django.db import migrations


# All 14 permissions
PERMISSIONS = [
    ('search_boats', 'Поиск яхт'),
    ('add_favorites', 'Избранное'),
    ('book_boats', 'Бронирование'),
    ('create_captain_offers', 'Капитанские офферы'),
    ('create_tourist_offers', 'Туристические офферы'),
    ('confirm_booking', 'Подтверждение бронирований'),
    ('notify_captains', 'Уведомление капитанов'),
    ('view_all_bookings', 'Просмотр всех бронирований'),
    ('manage_boats', 'Управление лодками'),
    ('access_admin', 'Доступ в админ-панель'),
    ('manage_charters', 'Управление чартерами'),
    ('manage_prices', 'Управление ценами'),
    ('no_branding', 'Без брендинга'),
    ('custom_branding', 'Кастомный брендинг'),
]

# Role → list of permission codenames
ROLES = {
    'tourist': {
        'name': 'Турист',
        'perms': ['search_boats', 'add_favorites', 'book_boats'],
    },
    'captain': {
        'name': 'Капитан',
        'perms': ['search_boats', 'add_favorites', 'book_boats',
                  'create_captain_offers'],
    },
    'assistant': {
        'name': 'Ассистент',
        'perms': ['search_boats', 'add_favorites', 'book_boats',
                  'create_captain_offers', 'confirm_booking',
                  'notify_captains', 'view_all_bookings'],
    },
    'manager': {
        'name': 'Менеджер',
        'perms': ['search_boats', 'add_favorites', 'book_boats',
                  'create_captain_offers', 'create_tourist_offers',
                  'confirm_booking', 'notify_captains',
                  'view_all_bookings', 'manage_boats', 'access_admin'],
    },
    'admin': {
        'name': 'Администратор',
        'perms': ['search_boats', 'add_favorites', 'book_boats',
                  'create_captain_offers', 'create_tourist_offers',
                  'confirm_booking', 'notify_captains',
                  'view_all_bookings', 'manage_boats', 'access_admin',
                  'manage_prices'],
    },
    'superadmin': {
        'name': 'Суперадмин',
        'perms': [p[0] for p in PERMISSIONS],  # ALL permissions
    },
}


def populate_roles_and_permissions(apps, schema_editor):
    Permission = apps.get_model('accounts', 'Permission')
    Role = apps.get_model('accounts', 'Role')
    UserProfile = apps.get_model('accounts', 'UserProfile')

    # Create permissions
    perm_objects = {}
    for codename, name in PERMISSIONS:
        perm_objects[codename] = Permission.objects.create(
            codename=codename, name=name,
        )

    # Create roles and assign permissions
    role_objects = {}
    for codename, cfg in ROLES.items():
        role = Role.objects.create(
            codename=codename,
            name=cfg['name'],
            is_system=True,
        )
        role.permissions.set([perm_objects[p] for p in cfg['perms']])
        role_objects[codename] = role

    # Migrate existing profiles: CharField role → FK role_ref
    for profile in UserProfile.objects.all():
        old_role = profile.role  # CharField still exists in DB at this point
        target_codename = old_role if old_role in role_objects else 'tourist'
        profile.role_ref = role_objects[target_codename]
        profile.save(update_fields=['role_ref'])


def reverse_populate(apps, schema_editor):
    """Reverse: set CharField from role_ref, then delete roles/permissions."""
    UserProfile = apps.get_model('accounts', 'UserProfile')
    Role = apps.get_model('accounts', 'Role')
    Permission = apps.get_model('accounts', 'Permission')

    for profile in UserProfile.objects.select_related('role_ref').all():
        if profile.role_ref:
            profile.role = profile.role_ref.codename
            profile.save(update_fields=['role'])

    Role.objects.all().delete()
    Permission.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_permission_role_userprofile_role_ref'),
    ]

    operations = [
        migrations.RunPython(
            populate_roles_and_permissions,
            reverse_populate,
        ),
    ]
