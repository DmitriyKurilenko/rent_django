from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_captainbrand'),
        ('boats', '0035_alter_parsejob_mode'),
    ]

    operations = [
        migrations.AddField(
            model_name='offer',
            name='brand',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='offers',
                to='accounts.captainbrand',
                verbose_name='Бренд',
            ),
        ),
        migrations.AlterField(
            model_name='offer',
            name='branding_mode',
            field=models.CharField(
                choices=[
                    ('default', 'Стандартный брендинг'),
                    ('no_branding', 'Без брендинга'),
                    ('custom_branding', 'Кастомный брендинг'),
                ],
                default='default',
                help_text='Стандартный, без брендинга, или кастомный брендинг капитана',
                max_length=20,
                verbose_name='Режим брендинга',
            ),
        ),
    ]
