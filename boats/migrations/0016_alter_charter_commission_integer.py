from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('boats', '0015_set_default_commission_for_existing_charters'),
    ]

    operations = [
        migrations.AlterField(
            model_name='charter',
            name='commission',
            field=models.IntegerField(
                default=20,
                help_text='Процент комиссии, добавляемый к итоговой цене',
                verbose_name='Комиссия (%)',
            ),
        ),
    ]
