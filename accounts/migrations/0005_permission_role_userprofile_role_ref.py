"""
Add Permission and Role models, add role_ref FK to UserProfile.
Old 'role' CharField kept for data migration in 0006.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_sync_roles_from_subscription'),
    ]

    operations = [
        migrations.CreateModel(
            name='Permission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codename', models.CharField(db_index=True, max_length=50, unique=True, verbose_name='Код')),
                ('name', models.CharField(max_length=100, verbose_name='Название')),
            ],
            options={
                'verbose_name': 'Разрешение',
                'verbose_name_plural': 'Разрешения',
                'ordering': ['codename'],
            },
        ),
        migrations.CreateModel(
            name='Role',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codename', models.CharField(db_index=True, max_length=20, unique=True, verbose_name='Код')),
                ('name', models.CharField(max_length=50, verbose_name='Название')),
                ('is_system', models.BooleanField(default=False, help_text='Системные роли нельзя удалить', verbose_name='Системная')),
                ('permissions', models.ManyToManyField(blank=True, related_name='roles', to='accounts.permission', verbose_name='Разрешения')),
            ],
            options={
                'verbose_name': 'Роль',
                'verbose_name_plural': 'Роли',
                'ordering': ['codename'],
            },
        ),
        migrations.AddField(
            model_name='userprofile',
            name='role_ref',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='profiles',
                to='accounts.role',
                verbose_name='Роль',
            ),
        ),
    ]
