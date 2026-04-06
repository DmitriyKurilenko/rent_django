"""
Remove old 'role' CharField from UserProfile.
The role property on the model delegates to role_ref FK.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_populate_roles_permissions'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='userprofile',
            name='role',
        ),
    ]
