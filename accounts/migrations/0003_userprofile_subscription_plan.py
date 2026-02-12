from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_alter_userprofile_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='subscription_plan',
            field=models.CharField(
                choices=[
                    ('free', 'Бесплатная'),
                    ('standard', 'Стандарт (500 ₽/мес)'),
                    ('advanced', 'Продвинутая'),
                ],
                default='free',
                max_length=20,
                verbose_name='Подписка',
            ),
        ),
    ]
