from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('boats', '0020_add_price_adjustment_to_offer'),
    ]

    operations = [
        migrations.CreateModel(
            name='PriceSettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('extra_discount_max', models.IntegerField(default=5, help_text='Условная доп. скидка при additional_discount < commission чартера', verbose_name='Макс. доп. скидка (%)')),
                ('tourist_insurance_rate', models.DecimalField(decimal_places=4, default=Decimal('0.1000'), help_text='Страховка депозита = total_price × rate', max_digits=6, verbose_name='Ставка страхования (доля)')),
                ('tourist_insurance_min', models.DecimalField(decimal_places=2, default=Decimal('400.00'), max_digits=8, verbose_name='Мин. страховка (EUR)')),
                ('tourist_turkey_base', models.DecimalField(decimal_places=2, default=Decimal('4400.00'), max_digits=8, verbose_name='Базовая цена Турция (EUR)')),
                ('tourist_seychelles_base', models.DecimalField(decimal_places=2, default=Decimal('4500.00'), max_digits=8, verbose_name='Базовая цена Сейшелы (EUR)')),
                ('tourist_default_base', models.DecimalField(decimal_places=2, default=Decimal('4500.00'), max_digits=8, verbose_name='Базовая цена по умолчанию (EUR)')),
                ('tourist_praslin_extra', models.DecimalField(decimal_places=2, default=Decimal('400.00'), max_digits=8, verbose_name='Надбавка за Praslin Marina (EUR)')),
                ('tourist_length_extra', models.DecimalField(decimal_places=2, default=Decimal('200.00'), max_digits=8, verbose_name='Надбавка за длину >14.2 м (EUR)')),
                ('tourist_cook_price', models.DecimalField(decimal_places=2, default=Decimal('1400.00'), max_digits=8, verbose_name='Стоимость повара (EUR)')),
                ('tourist_turkey_dish_base', models.DecimalField(decimal_places=2, default=Decimal('150.00'), max_digits=8, verbose_name='Питание Турция EUR/чел')),
                ('tourist_seychelles_dish_base', models.DecimalField(decimal_places=2, default=Decimal('210.00'), max_digits=8, verbose_name='Питание Сейшелы EUR/чел')),
                ('tourist_default_dish_base', models.DecimalField(decimal_places=2, default=Decimal('210.00'), max_digits=8, verbose_name='Питание по умолчанию EUR/чел')),
                ('tourist_max_double_cabins_free', models.IntegerField(default=4, verbose_name='Бесплатных двойных кают (Сейшелы)')),
                ('tourist_double_cabin_extra', models.DecimalField(decimal_places=2, default=Decimal('180.00'), max_digits=8, verbose_name='Надбавка за доп. двойную каюту (EUR)')),
                ('tourist_catamaran_length_extra', models.DecimalField(decimal_places=2, default=Decimal('500.00'), max_digits=8, verbose_name='Надбавка длина катамарана Турция (EUR)')),
                ('tourist_sailing_length_extra', models.DecimalField(decimal_places=2, default=Decimal('300.00'), max_digits=8, verbose_name='Надбавка длина парусной яхты Турция (EUR)')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Обновлено')),
            ],
            options={
                'verbose_name': 'Настройки цен',
                'verbose_name_plural': 'Настройки цен',
            },
        ),
    ]
