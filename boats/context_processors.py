from boats.models import Notification


def notifications(request):
    """Inject unread notification count for authenticated users."""
    if request.user.is_authenticated:
        return {
            'unread_notifications_count': Notification.objects.filter(
                recipient=request.user, is_read=False,
            ).count(),
        }
    return {}
