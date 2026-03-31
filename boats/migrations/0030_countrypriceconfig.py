# Hand-written migration: create CountryPriceConfig and seed initial rows from hardcoded fields.

from decimal import Decimal
from django.db import migrations, models
import django.db.models.deletion


def seed_country_configs(apps, schema_editor):
    """Create Turkey / Seychelles / Default rows from existing PriceSettings fields."""
    PriceSettings = apps.get_model('boats', 'PriceSettings')
    CountryPriceConfig = apps.get_model('boats', 'CountryPriceConfig')

    ps = PriceSettings.objects.filter(pk=1).first()
    if ps is None:
        return

    # Turkey
    CountryPriceConfig.objects.create(
        price_settings=ps,
        country_name='Турция',
        country_code='turkey',
        match_names='turkey, турция',
        is_default=False,
        sort_order=0,
        captain=ps.tourist_captain_turkey,
        fuel=ps.tourist_fuel_turkey,
        moorings=ps.tourist_moorings_turkey,
        transit_cleaning=ps.tourist_transit_cleaning_turkey,
        trips_markup=ps.tourist_trips_markup_turkey,
        insurance_rate=ps.tourist_insurance_rate_turkey,
        insurance_min=ps.tourist_insurance_min_turkey,
        dish_base=ps.tourist_turkey_dish_base,
        cook_price=ps.tourist_cook_price_turkey,
        length_extra=ps.tourist_length_extra_turkey,
        catamaran_length_extra=ps.tourist_catamaran_length_extra_turkey,
        sailing_length_extra=ps.tourist_sailing_length_extra_turkey,
        double_cabin_extra=ps.tourist_double_cabin_extra_turkey,
        max_double_cabins_free=ps.tourist_max_double_cabins_free_turkey,
        praslin_extra=Decimal('0.00'),
    )

    # Seychelles
    CountryPriceConfig.objects.create(
        price_settings=ps,
        country_name='Сейшелы',
        country_code='seychelles',
        match_names='seychelles, сейшелы',
        is_default=False,
        sort_order=1,
        captain=ps.tourist_captain_seychelles,
        fuel=ps.tourist_fuel_seychelles,
        moorings=ps.tourist_moorings_seychelles,
        transit_cleaning=ps.tourist_transit_cleaning_seychelles,
        trips_markup=ps.tourist_trips_markup_seychelles,
        insurance_rate=ps.tourist_insurance_rate_seychelles,
        insurance_min=ps.tourist_insurance_min_seychelles,
        dish_base=ps.tourist_seychelles_dish_base,
        cook_price=ps.tourist_cook_price_seychelles,
        length_extra=ps.tourist_length_extra_seychelles,
        catamaran_length_extra=ps.tourist_catamaran_length_extra_seychelles,
        sailing_length_extra=ps.tourist_sailing_length_extra_seychelles,
        double_cabin_extra=ps.tourist_double_cabin_extra_seychelles,
        max_double_cabins_free=ps.tourist_max_double_cabins_free_seychelles,
        praslin_extra=ps.tourist_praslin_extra,
    )

    # Default
    CountryPriceConfig.objects.create(
        price_settings=ps,
        country_name='Остальные',
        country_code='default',
        match_names='',
        is_default=True,
        sort_order=99,
        captain=ps.tourist_captain_default,
        fuel=ps.tourist_fuel_default,
        moorings=ps.tourist_moorings_default,
        transit_cleaning=ps.tourist_transit_cleaning_default,
        trips_markup=ps.tourist_trips_markup_default,
        insurance_rate=ps.tourist_insurance_rate_default,
        insurance_min=ps.tourist_insurance_min_default,
        dish_base=ps.tourist_default_dish_base,
        cook_price=ps.tourist_cook_price_default,
        length_extra=ps.tourist_length_extra_default,
        catamaran_length_extra=ps.tourist_catamaran_length_extra_default,
        sailing_length_extra=ps.tourist_sailing_length_extra_default,
        double_cabin_extra=ps.tourist_double_cabin_extra_default,
        max_double_cabins_free=ps.tourist_max_double_cabins_free_default,
        praslin_extra=Decimal('0.00'),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('boats', '0029_per_region_insurance_cook_surcharges'),
    ]

    operations = [
        migrations.CreateModel(
            name='CountryPriceConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('country_name', models.CharField(max_length=100, verbose_name='Название')),
                ('country_code', models.SlugField(max_length=60, unique=True, verbose_name='Код (slug)')),
                ('match_names', models.TextField(blank=True, default='', help_text='Через запятую: turkey, турция', verbose_name='Алиасы для матчинга')),
                ('is_default', models.BooleanField(default=False, verbose_name='Профиль по умолчанию')),
                ('sort_order', models.IntegerField(default=0, verbose_name='Порядок')),
                ('captain', models.DecimalField(decimal_places=2, default=Decimal('900.00'), max_digits=8, verbose_name='Капитан (EUR)')),
                ('fuel', models.DecimalField(decimal_places=2, default=Decimal('900.00'), max_digits=8, verbose_name='Топливо (EUR)')),
                ('moorings', models.DecimalField(decimal_places=2, default=Decimal('900.00'), max_digits=8, verbose_name='Стоянки (EUR)')),
                ('transit_cleaning', models.DecimalField(decimal_places=2, default=Decimal('900.00'), max_digits=8, verbose_name='Транзит лог и клининг (EUR)')),
                ('trips_markup', models.DecimalField(decimal_places=2, default=Decimal('900.00'), max_digits=8, verbose_name='Наценка Трипс (EUR)')),
                ('insurance_rate', models.DecimalField(decimal_places=4, default=Decimal('0.1000'), max_digits=6, verbose_name='Ставка страхования')),
                ('insurance_min', models.DecimalField(decimal_places=2, default=Decimal('400.00'), max_digits=8, verbose_name='Мин. страховка (EUR)')),
                ('dish_base', models.DecimalField(decimal_places=2, default=Decimal('210.00'), max_digits=8, verbose_name='Питание EUR/чел')),
                ('cook_price', models.DecimalField(decimal_places=2, default=Decimal('1400.00'), max_digits=8, verbose_name='Повар (EUR)')),
                ('length_extra', models.DecimalField(decimal_places=2, default=Decimal('200.00'), max_digits=8, verbose_name='Длина >14.2 м (EUR)')),
                ('catamaran_length_extra', models.DecimalField(decimal_places=2, default=Decimal('500.00'), max_digits=8, verbose_name='Катамаран >13.8 м (EUR)')),
                ('sailing_length_extra', models.DecimalField(decimal_places=2, default=Decimal('300.00'), max_digits=8, verbose_name='Парусная >13.8 м (EUR)')),
                ('double_cabin_extra', models.DecimalField(decimal_places=2, default=Decimal('180.00'), max_digits=8, verbose_name='Доп. двойная каюта (EUR)')),
                ('max_double_cabins_free', models.IntegerField(default=4, verbose_name='Бесплатных двойных кают')),
                ('praslin_extra', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=8, verbose_name='Марина Praslin (EUR)')),
                ('price_settings', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='country_configs', to='boats.pricesettings')),
            ],
            options={
                'verbose_name': 'Ценовой профиль страны',
                'verbose_name_plural': 'Ценовые профили стран',
                'ordering': ['sort_order', 'country_name'],
            },
        ),
        migrations.RunPython(seed_country_configs, migrations.RunPython.noop),
    ]
