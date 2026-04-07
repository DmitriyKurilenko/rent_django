"""
Add granular permissions for price breakdown, manager assignment,
delete bookings/offers, contract creation, and client access.
"""

from django.db import migrations


NEW_PERMISSIONS = [
    ('view_price_breakdown', 'Расшифровка цен'),
    ('assign_managers', 'Назначение менеджеров'),
    ('delete_bookings', 'Удаление бронирований'),
    ('delete_offers', 'Удаление чужих офферов'),
    ('create_contracts', 'Создание договоров'),
    ('view_all_clients', 'Просмотр всех клиентов'),
]

# Role → new permissions to add
ROLE_NEW_PERMS = {
    'captain': ['create_contracts'],
    'assistant': ['create_contracts', 'view_all_clients'],
    'manager': [
        'view_price_breakdown', 'delete_bookings',
        'create_contracts', 'view_all_clients',
    ],
    'admin': [
        'view_price_breakdown', 'assign_managers',
        'delete_bookings', 'delete_offers',
        'create_contracts', 'view_all_clients',
    ],
    'superadmin': [p[0] for p in NEW_PERMISSIONS],
}


def add_permissions(apps, schema_editor):
    Permission = apps.get_model('accounts', 'Permission')
    Role = apps.get_model('accounts', 'Role')

    perm_objects = {}
    for codename, name in NEW_PERMISSIONS:
        perm_objects[codename], _ = Permission.objects.get_or_create(
            codename=codename, defaults={'name': name},
        )

    for role_codename, perm_codenames in ROLE_NEW_PERMS.items():
        try:
            role = Role.objects.get(codename=role_codename)
        except Role.DoesNotExist:
            continue
        for pc in perm_codenames:
            role.permissions.add(perm_objects[pc])


def remove_permissions(apps, schema_editor):
    Permission = apps.get_model('accounts', 'Permission')
    for codename, _ in NEW_PERMISSIONS:
        Permission.objects.filter(codename=codename).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_remove_userprofile_role'),
    ]

    operations = [
        migrations.RunPython(add_permissions, remove_permissions),
    ]
