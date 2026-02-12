# Generated manually on 2026-02-02

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('boats', '0008_parsedboat_boat_data'),
    ]

    operations = [
        # First, remove old unique_together constraint (references 'boat' field)
        migrations.AlterUniqueTogether(
            name='favorite',
            unique_together=set(),
        ),
        
        # Now safe to remove old boat field
        migrations.RemoveField(
            model_name='favorite',
            name='boat',
        ),
        
        # Add new fields (nullable first to avoid data migration issues)
        migrations.AddField(
            model_name='favorite',
            name='parsed_boat',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='favorited_by',
                to='boats.parsedboat',
                null=True,
                blank=True,
            ),
        ),
        migrations.AddField(
            model_name='favorite',
            name='boat_slug',
            field=models.CharField(
                db_index=True,
                max_length=255,
                verbose_name='Slug лодки',
                default='unknown',
                blank=True,
            ),
        ),
        migrations.AddField(
            model_name='favorite',
            name='boat_id',
            field=models.CharField(
                db_index=True,
                max_length=100,
                verbose_name='ID лодки',
                default='',
                blank=True,
            ),
        ),
        
        # Set new unique_together
        migrations.AlterUniqueTogether(
            name='favorite',
            unique_together={('user', 'boat_slug')},
        ),
        
        # Add indexes
        migrations.AddIndex(
            model_name='favorite',
            index=models.Index(fields=['user', 'boat_slug'], name='boats_favor_user_id_boat_sl_idx'),
        ),
        migrations.AddIndex(
            model_name='favorite',
            index=models.Index(fields=['user', 'created_at'], name='boats_favor_user_id_created_idx'),
        ),
    ]
