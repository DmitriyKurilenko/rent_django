from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('boats', '0013_charter_parsedboat_charter'),
    ]

    operations = [
        migrations.AlterField(
            model_name='charter',
            name='commission',
            field=models.DecimalField(
                decimal_places=2,
                default=20,
                help_text='Процент комиссии, добавляемый к итоговой цене',
                max_digits=5,
                verbose_name='Комиссия (%)',
            ),
        ),
    ]
