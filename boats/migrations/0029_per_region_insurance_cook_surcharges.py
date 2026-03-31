# Hand-written migration: split 8 single-value PriceSettings fields into per-region (turkey/seychelles/default).

from decimal import Decimal
from django.db import migrations, models


def copy_old_values_to_regions(apps, schema_editor):
    """Copy existing single-value settings to all 3 region variants."""
    PriceSettings = apps.get_model('boats', 'PriceSettings')
    for ps in PriceSettings.objects.all():
        for suffix in ('_turkey', '_seychelles', '_default'):
            setattr(ps, f'tourist_insurance_rate{suffix}', ps.tourist_insurance_rate)
            setattr(ps, f'tourist_insurance_min{suffix}', ps.tourist_insurance_min)
            setattr(ps, f'tourist_cook_price{suffix}', ps.tourist_cook_price)
            setattr(ps, f'tourist_length_extra{suffix}', ps.tourist_length_extra)
            setattr(ps, f'tourist_catamaran_length_extra{suffix}', ps.tourist_catamaran_length_extra)
            setattr(ps, f'tourist_sailing_length_extra{suffix}', ps.tourist_sailing_length_extra)
            setattr(ps, f'tourist_double_cabin_extra{suffix}', ps.tourist_double_cabin_extra)
            setattr(ps, f'tourist_max_double_cabins_free{suffix}', ps.tourist_max_double_cabins_free)
        ps.save()


class Migration(migrations.Migration):

    dependencies = [
        ('boats', '0028_offer_price_captain_offer_price_fuel_and_more'),
    ]

    operations = [
        # --- Step 1: Add per-region fields ---
        # Insurance rate
        migrations.AddField(model_name='pricesettings', name='tourist_insurance_rate_turkey',
            field=models.DecimalField(decimal_places=4, default=Decimal('0.1000'), max_digits=6, verbose_name='Ставка страхования Турция')),
        migrations.AddField(model_name='pricesettings', name='tourist_insurance_rate_seychelles',
            field=models.DecimalField(decimal_places=4, default=Decimal('0.1000'), max_digits=6, verbose_name='Ставка страхования Сейшелы')),
        migrations.AddField(model_name='pricesettings', name='tourist_insurance_rate_default',
            field=models.DecimalField(decimal_places=4, default=Decimal('0.1000'), max_digits=6, verbose_name='Ставка страхования по умолчанию')),
        # Insurance min
        migrations.AddField(model_name='pricesettings', name='tourist_insurance_min_turkey',
            field=models.DecimalField(decimal_places=2, default=Decimal('400.00'), max_digits=8, verbose_name='Мин. страховка Турция (EUR)')),
        migrations.AddField(model_name='pricesettings', name='tourist_insurance_min_seychelles',
            field=models.DecimalField(decimal_places=2, default=Decimal('400.00'), max_digits=8, verbose_name='Мин. страховка Сейшелы (EUR)')),
        migrations.AddField(model_name='pricesettings', name='tourist_insurance_min_default',
            field=models.DecimalField(decimal_places=2, default=Decimal('400.00'), max_digits=8, verbose_name='Мин. страховка по умолчанию (EUR)')),
        # Cook price
        migrations.AddField(model_name='pricesettings', name='tourist_cook_price_turkey',
            field=models.DecimalField(decimal_places=2, default=Decimal('1400.00'), max_digits=8, verbose_name='Повар Турция (EUR)')),
        migrations.AddField(model_name='pricesettings', name='tourist_cook_price_seychelles',
            field=models.DecimalField(decimal_places=2, default=Decimal('1400.00'), max_digits=8, verbose_name='Повар Сейшелы (EUR)')),
        migrations.AddField(model_name='pricesettings', name='tourist_cook_price_default',
            field=models.DecimalField(decimal_places=2, default=Decimal('1400.00'), max_digits=8, verbose_name='Повар по умолчанию (EUR)')),
        # Length extra
        migrations.AddField(model_name='pricesettings', name='tourist_length_extra_turkey',
            field=models.DecimalField(decimal_places=2, default=Decimal('200.00'), max_digits=8, verbose_name='Надбавка длина >14.2 м Турция (EUR)')),
        migrations.AddField(model_name='pricesettings', name='tourist_length_extra_seychelles',
            field=models.DecimalField(decimal_places=2, default=Decimal('200.00'), max_digits=8, verbose_name='Надбавка длина >14.2 м Сейшелы (EUR)')),
        migrations.AddField(model_name='pricesettings', name='tourist_length_extra_default',
            field=models.DecimalField(decimal_places=2, default=Decimal('200.00'), max_digits=8, verbose_name='Надбавка длина >14.2 м по умолчанию (EUR)')),
        # Catamaran length extra
        migrations.AddField(model_name='pricesettings', name='tourist_catamaran_length_extra_turkey',
            field=models.DecimalField(decimal_places=2, default=Decimal('500.00'), max_digits=8, verbose_name='Надбавка катамаран >13.8 м Турция (EUR)')),
        migrations.AddField(model_name='pricesettings', name='tourist_catamaran_length_extra_seychelles',
            field=models.DecimalField(decimal_places=2, default=Decimal('500.00'), max_digits=8, verbose_name='Надбавка катамаран >13.8 м Сейшелы (EUR)')),
        migrations.AddField(model_name='pricesettings', name='tourist_catamaran_length_extra_default',
            field=models.DecimalField(decimal_places=2, default=Decimal('500.00'), max_digits=8, verbose_name='Надбавка катамаран >13.8 м по умолчанию (EUR)')),
        # Sailing length extra
        migrations.AddField(model_name='pricesettings', name='tourist_sailing_length_extra_turkey',
            field=models.DecimalField(decimal_places=2, default=Decimal('300.00'), max_digits=8, verbose_name='Надбавка парусная >13.8 м Турция (EUR)')),
        migrations.AddField(model_name='pricesettings', name='tourist_sailing_length_extra_seychelles',
            field=models.DecimalField(decimal_places=2, default=Decimal('300.00'), max_digits=8, verbose_name='Надбавка парусная >13.8 м Сейшелы (EUR)')),
        migrations.AddField(model_name='pricesettings', name='tourist_sailing_length_extra_default',
            field=models.DecimalField(decimal_places=2, default=Decimal('300.00'), max_digits=8, verbose_name='Надбавка парусная >13.8 м по умолчанию (EUR)')),
        # Double cabin extra
        migrations.AddField(model_name='pricesettings', name='tourist_double_cabin_extra_turkey',
            field=models.DecimalField(decimal_places=2, default=Decimal('180.00'), max_digits=8, verbose_name='Доп. двойная каюта Турция (EUR)')),
        migrations.AddField(model_name='pricesettings', name='tourist_double_cabin_extra_seychelles',
            field=models.DecimalField(decimal_places=2, default=Decimal('180.00'), max_digits=8, verbose_name='Доп. двойная каюта Сейшелы (EUR)')),
        migrations.AddField(model_name='pricesettings', name='tourist_double_cabin_extra_default',
            field=models.DecimalField(decimal_places=2, default=Decimal('180.00'), max_digits=8, verbose_name='Доп. двойная каюта по умолчанию (EUR)')),
        # Max double cabins free
        migrations.AddField(model_name='pricesettings', name='tourist_max_double_cabins_free_turkey',
            field=models.IntegerField(default=4, verbose_name='Бесплатных двойных кают Турция')),
        migrations.AddField(model_name='pricesettings', name='tourist_max_double_cabins_free_seychelles',
            field=models.IntegerField(default=4, verbose_name='Бесплатных двойных кают Сейшелы')),
        migrations.AddField(model_name='pricesettings', name='tourist_max_double_cabins_free_default',
            field=models.IntegerField(default=4, verbose_name='Бесплатных двойных кают по умолчанию')),

        # --- Step 2: Copy old values to new per-region fields ---
        migrations.RunPython(copy_old_values_to_regions, migrations.RunPython.noop),

        # --- Step 3: Remove old single-value fields ---
        migrations.RemoveField(model_name='pricesettings', name='tourist_insurance_rate'),
        migrations.RemoveField(model_name='pricesettings', name='tourist_insurance_min'),
        migrations.RemoveField(model_name='pricesettings', name='tourist_cook_price'),
        migrations.RemoveField(model_name='pricesettings', name='tourist_length_extra'),
        migrations.RemoveField(model_name='pricesettings', name='tourist_catamaran_length_extra'),
        migrations.RemoveField(model_name='pricesettings', name='tourist_sailing_length_extra'),
        migrations.RemoveField(model_name='pricesettings', name='tourist_double_cabin_extra'),
        migrations.RemoveField(model_name='pricesettings', name='tourist_max_double_cabins_free'),
    ]
