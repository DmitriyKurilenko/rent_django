from django.db import migrations


def sync_roles_from_subscription(apps, schema_editor):
    UserProfile = apps.get_model('accounts', 'UserProfile')

    UserProfile.objects.filter(
        role='tourist',
        subscription_plan__in=['standard', 'advanced']
    ).update(role='captain')

    UserProfile.objects.filter(
        role='captain',
        subscription_plan='free'
    ).update(role='tourist')


def reverse_sync_roles_from_subscription(apps, schema_editor):
    # Безопасный no-op rollback: не меняем исторические роли обратно,
    # чтобы не затирать ручные изменения администраторов.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_userprofile_subscription_plan'),
    ]

    operations = [
        migrations.RunPython(sync_roles_from_subscription, reverse_sync_roles_from_subscription),
    ]
