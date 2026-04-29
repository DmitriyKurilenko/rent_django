from django.db.models.signals import post_save
from django.dispatch import receiver
from boats.models import Booking


@receiver(post_save, sender=Booking)
def sync_assigned_staff(sender, instance, **kwargs):
    """При назначении менеджера на бронирование — обновляем assigned_staff клиента."""
    if not instance.assigned_manager_id:
        return
    user = instance.user
    if not user or not hasattr(user, 'profile'):
        return
    profile = user.profile
    if profile.assigned_staff_id != instance.assigned_manager_id:
        profile.assigned_staff_id = instance.assigned_manager_id
        profile.save(update_fields=['assigned_staff'])
