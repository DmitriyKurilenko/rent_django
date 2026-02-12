from decimal import Decimal

from django.db import migrations


def set_default_commission(apps, schema_editor):
    Charter = apps.get_model('boats', 'Charter')
    Charter.objects.filter(commission=Decimal('0.00')).update(commission=Decimal('20.00'))


def reverse_default_commission(apps, schema_editor):
    Charter = apps.get_model('boats', 'Charter')
    Charter.objects.filter(commission=Decimal('20.00')).update(commission=Decimal('0.00'))


class Migration(migrations.Migration):

    dependencies = [
        ('boats', '0014_alter_charter_commission_default'),
    ]

    operations = [
        migrations.RunPython(set_default_commission, reverse_default_commission),
    ]
