"""
Centralized booking notification dispatch.

Handles both in-app (Notification model) and Telegram delivery.
"""
import logging

from django.contrib.auth.models import User

from boats.models import Notification
from boats.tasks import send_telegram_notification

logger = logging.getLogger(__name__)


def _get_staff_with_perm(codename, exclude_pks=None):
    """Return User queryset for staff holding a specific permission."""
    qs = User.objects.filter(
        profile__role_ref__permissions__codename=codename,
    )
    if exclude_pks:
        qs = qs.exclude(pk__in=exclude_pks)
    return qs.distinct()


def notify_new_booking(booking, created_by):
    """Notify staff about a newly created booking (in-app + Telegram)."""
    app_msg = (
        f'Новое бронирование «{booking.boat_title}» '
        f'({booking.start_date:%d.%m.%Y} — {booking.end_date:%d.%m.%Y}), '
        f'{booking.total_price} {booking.currency}. '
        f'Создал: {created_by.get_full_name() or created_by.username}'
    )
    tg_msg = (
        f'🆕 <b>Новое бронирование #{booking.id}</b>\n'
        f'Яхта: {booking.boat_title}\n'
        f'Даты: {booking.start_date:%d.%m.%Y} — {booking.end_date:%d.%m.%Y}\n'
        f'Цена: {booking.total_price} {booking.currency}\n'
        f'Создал: {created_by.get_full_name() or created_by.username}'
    )

    staff = _get_staff_with_perm('view_all_bookings', exclude_pks={created_by.pk})
    Notification.objects.bulk_create([
        Notification(recipient=u, booking=booking, message=app_msg)
        for u in staff
    ])

    send_telegram_notification.delay(tg_msg)


def notify_status_change(booking, changed_by, responsible_user, new_status, extra=''):
    """Notify responsible user + staff about a booking status change."""
    status_labels = {
        'confirmed': ('подтверждено', '✅'),
        'option': ('на опции', '⏳'),
        'cancelled': ('отменено', '❌'),
    }
    label, emoji = status_labels.get(new_status, (new_status, 'ℹ️'))
    actor = changed_by.get_full_name() or changed_by.username

    app_msg = f'Бронирование «{booking.boat_title}» {label} ({actor})'
    if extra:
        app_msg = f'Бронирование «{booking.boat_title}» {extra} ({actor})'

    tg_lines = [
        f'{emoji} <b>Бронирование #{booking.id} {label}</b>',
        f'Яхта: {booking.boat_title}',
    ]
    if extra:
        tg_lines.append(extra)
    tg_lines.append(f'Кем: {actor}')
    tg_msg = '\n'.join(tg_lines)

    notified_pks = {changed_by.pk}

    if responsible_user:
        Notification.objects.create(
            recipient=responsible_user,
            booking=booking,
            message=app_msg,
        )
        notified_pks.add(responsible_user.pk)

    staff = _get_staff_with_perm('view_all_bookings', exclude_pks=notified_pks)
    Notification.objects.bulk_create([
        Notification(recipient=u, booking=booking, message=app_msg)
        for u in staff
    ])

    send_telegram_notification.delay(tg_msg)
