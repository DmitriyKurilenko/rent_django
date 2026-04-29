from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('boats', '0038_rename_boats_feedb_created_idx_boats_feedb_created_100f32_idx_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Thread',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('subject', models.CharField(blank=True, default='', max_length=200, verbose_name='Тема')),
                ('last_message_at', models.DateTimeField(blank=True, db_index=True, null=True, verbose_name='Последнее сообщение')),
                ('is_closed', models.BooleanField(default=False, verbose_name='Закрыт')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создан')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Обновлён')),
                ('booking', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='chat_threads', to='boats.booking', verbose_name='Бронирование')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='created_threads', to=settings.AUTH_USER_MODEL, verbose_name='Автор')),
                ('participants', models.ManyToManyField(related_name='chat_threads', to=settings.AUTH_USER_MODEL, verbose_name='Участники')),
            ],
            options={
                'verbose_name': 'Тред',
                'verbose_name_plural': 'Треды',
                'ordering': ['-last_message_at', '-created_at'],
                'indexes': [
                    models.Index(fields=['-last_message_at'], name='boats_threa_last_me_idx'),
                    models.Index(fields=['booking'], name='boats_threa_booking_idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='Message',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('body', models.TextField(verbose_name='Текст')),
                ('is_system', models.BooleanField(default=False, verbose_name='Системное')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Создано')),
                ('sender', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='sent_messages', to=settings.AUTH_USER_MODEL, verbose_name='Отправитель')),
                ('thread', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='boats.thread', verbose_name='Тред')),
            ],
            options={
                'verbose_name': 'Сообщение',
                'verbose_name_plural': 'Сообщения',
                'ordering': ['created_at'],
                'indexes': [
                    models.Index(fields=['thread', 'created_at'], name='boats_messa_thread__idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='MessageRead',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('read_at', models.DateTimeField(auto_now_add=True, verbose_name='Прочитано')),
                ('message', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reads', to='boats.message')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='message_reads', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Отметка прочтения',
                'verbose_name_plural': 'Отметки прочтения',
                'indexes': [
                    models.Index(fields=['user', 'read_at'], name='boats_messa_user_id_idx'),
                ],
                'constraints': [
                    models.UniqueConstraint(fields=['message', 'user'], name='unique_message_user_read'),
                ],
            },
        ),
    ]
