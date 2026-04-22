from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('boats', '0036_offer_brand'),
    ]

    operations = [
        migrations.CreateModel(
            name='Feedback',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, verbose_name='Имя')),
                ('phone', models.CharField(blank=True, default='', max_length=30, verbose_name='Телефон')),
                ('email', models.EmailField(max_length=254, verbose_name='Email')),
                ('message', models.TextField(verbose_name='Сообщение')),
                ('is_processed', models.BooleanField(default=False, verbose_name='Обработано')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Дата обращения')),
            ],
            options={
                'verbose_name': 'Обращение',
                'verbose_name_plural': 'Обращения',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='feedback',
            index=models.Index(fields=['-created_at'], name='boats_feedb_created_idx'),
        ),
        migrations.AddIndex(
            model_name='feedback',
            index=models.Index(fields=['is_processed', '-created_at'], name='boats_feedb_is_proc_idx'),
        ),
    ]
