from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('boats', '0016_alter_charter_commission_integer'),
    ]

    operations = [
        migrations.AddField(
            model_name='offer',
            name='branding_mode',
            field=models.CharField(
                choices=[
                    ('default', 'Стандартный брендинг'),
                    ('no_branding', 'Без брендинга'),
                    ('custom_branding', 'Кастомный брендинг (заглушка)'),
                ],
                default='default',
                help_text='Стандартный, без брендинга, или кастомный брендинг (заглушка)',
                max_length=20,
                verbose_name='Режим брендинга',
            ),
        ),
    ]
