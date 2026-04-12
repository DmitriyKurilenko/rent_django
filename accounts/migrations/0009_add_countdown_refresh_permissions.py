"""
Add permissions for countdown timer and force-refresh controls
in quick offer creation.
"""

from django.db import migrations


NEW_PERMISSIONS = [
    ('use_countdown', 'Таймер обратного отсчёта в офферах'),
    ('use_force_refresh', 'Обновление данных при создании оффера'),
]

# Role → new permissions to add
ROLE_NEW_PERMS = {
    'captain': ['use_countdown'],
    'assistant': ['use_countdown', 'use_force_refresh'],
    'manager': ['use_countdown', 'use_force_refresh'],
    'admin': ['use_countdown', 'use_force_refresh'],
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
        ('accounts', '0008_add_granular_permissions'),
    ]

    operations = [
        migrations.RunPython(add_permissions, remove_permissions),
    ]
