from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_captainbrand'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='assigned_staff',
            field=models.ForeignKey(
                blank=True,
                help_text='Автоматически назначается при взятии бронирования. Меняется только админом.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='managed_clients',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Ответственный (менеджер/ассистент)',
            ),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='telegram_chat_id',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Личный chat_id для оффлайн-уведомлений из чата. Пусто — не слать в TG.',
                max_length=50,
                verbose_name='Telegram chat_id',
            ),
        ),
    ]
