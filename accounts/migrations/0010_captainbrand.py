from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_add_countdown_refresh_permissions'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CaptainBrand',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='Название компании')),
                ('logo', models.ImageField(blank=True, null=True, upload_to='brands/logos/', verbose_name='Логотип')),
                ('primary_color', models.CharField(
                    default='#3B82F6',
                    help_text='Например: #3B82F6',
                    max_length=7,
                    verbose_name='Основной цвет (HEX)',
                )),
                ('tagline', models.CharField(blank=True, max_length=300, verbose_name='Слоган')),
                ('phone', models.CharField(blank=True, max_length=30, verbose_name='Телефон')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name='Email')),
                ('website', models.URLField(blank=True, verbose_name='Сайт')),
                ('telegram', models.CharField(blank=True, max_length=100, verbose_name='Telegram (username или ссылка)')),
                ('whatsapp', models.CharField(blank=True, max_length=30, verbose_name='WhatsApp (номер)')),
                ('footer_text', models.TextField(blank=True, verbose_name='Текст в подвале оффера')),
                ('is_default', models.BooleanField(default=False, verbose_name='По умолчанию')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('owner', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='brands',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Владелец',
                )),
            ],
            options={
                'verbose_name': 'Бренд капитана',
                'verbose_name_plural': 'Бренды капитанов',
                'ordering': ['-is_default', 'name'],
            },
        ),
    ]
