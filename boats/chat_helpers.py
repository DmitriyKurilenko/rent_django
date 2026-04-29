"""Helpers для чата: назначение ответственного, доступ к тредам."""
from typing import Optional

from django.contrib.auth.models import User
from django.core.cache import cache


def get_available_staff() -> list:
    """Возвращает список активных manager+assistant, отсортированный по pk."""
    return list(
        User.objects.filter(
            is_active=True,
            profile__role_ref__codename__in=['manager', 'assistant'],
        ).order_by('pk').distinct()
    )


def assign_staff_for_new_thread(initiator: User) -> Optional[User]:
    """Round-robin по доступным staff. Возвращает None если staff нет.

    Использует Redis-счётчик 'chat_rr_counter' для атомарного распределения.
    Если у инициатора уже есть assigned_staff — использует его.
    """
    profile = getattr(initiator, 'profile', None)
    if profile and profile.assigned_staff_id:
        return profile.assigned_staff

    staff = get_available_staff()
    if not staff:
        return None

    counter_key = 'chat_rr_counter'
    try:
        new_idx = cache.incr(counter_key)
    except ValueError:
        cache.set(counter_key, 1, timeout=None)
        new_idx = 1

    return staff[(new_idx - 1) % len(staff)]


def can_access_thread(user: User, thread) -> bool:
    """Проверка доступа к треду."""
    if not user.is_authenticated:
        return False
    if thread.participants.filter(pk=user.pk).exists():
        return True
    profile = getattr(user, 'profile', None)
    if profile and profile.role in ('admin', 'superadmin'):
        return True
    return False


def can_initiate_thread_with(initiator: User, target: User) -> bool:
    """Может ли initiator открыть тред с target."""
    if initiator == target or not initiator.is_authenticated:
        return False
    init_profile = getattr(initiator, 'profile', None)
    target_profile = getattr(target, 'profile', None)
    if not init_profile or not target_profile:
        return False

    INTERNAL = ('manager', 'assistant', 'admin', 'superadmin')

    if init_profile.role in INTERNAL:
        return True

    if init_profile.assigned_staff_id == target.pk:
        return True

    if init_profile.assigned_staff_id is None and target_profile.role in ('manager', 'assistant'):
        return True

    return False
