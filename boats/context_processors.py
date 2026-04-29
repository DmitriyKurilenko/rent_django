from boats.models import Notification
from boats.forms import FeedbackForm


def notifications(request):
    """Inject unread notification count for authenticated users."""
    if request.user.is_authenticated:
        return {
            'unread_notifications_count': Notification.objects.filter(
                recipient=request.user, is_read=False,
            ).count(),
        }
    return {}


def feedback_form(request):
    """Inject FeedbackForm instance for global feedback modal."""
    return {'feedback_form': FeedbackForm()}


def chat(request):
    """Inject unread chat message count for authenticated users."""
    if not request.user.is_authenticated:
        return {}
    from boats.models import Message, Thread
    user = request.user
    user_thread_ids = list(
        Thread.objects.filter(participants=user).values_list('pk', flat=True)
    )
    if not user_thread_ids:
        return {'unread_chat_count': 0}
    total = (
        Message.objects
        .filter(thread_id__in=user_thread_ids)
        .exclude(sender=user)
        .exclude(reads__user=user)
        .count()
    )
    return {'unread_chat_count': total}
