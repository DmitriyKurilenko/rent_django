"""Tests for Thread, Message, MessageRead models."""
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone

from boats.models import Thread, Message, MessageRead
from accounts.models import Role, UserProfile


def make_user(username, role='tourist'):
    user = User.objects.create_user(username=username, password='pass')
    role_obj = Role.objects.filter(codename=role).first()
    if role_obj:
        UserProfile.objects.filter(pk=user.profile.pk).update(role_ref=role_obj)
        user.profile.refresh_from_db()
    return user


class ThreadModelTest(TestCase):
    def setUp(self):
        self.u1 = make_user('u1')
        self.u2 = make_user('u2')

    def test_thread_str_with_subject(self):
        t = Thread.objects.create(created_by=self.u1, subject='Вопрос по яхте')
        self.assertEqual(str(t), 'Вопрос по яхте')

    def test_thread_str_without_subject(self):
        t = Thread.objects.create(created_by=self.u1)
        self.assertIn(str(t.pk), str(t))

    def test_thread_ordering_by_last_message_at(self):
        now = timezone.now()
        from datetime import timedelta
        t_old = Thread.objects.create(created_by=self.u1, last_message_at=now - timedelta(hours=1))
        t_new = Thread.objects.create(created_by=self.u1, last_message_at=now)
        qs = Thread.objects.filter(last_message_at__isnull=False)
        self.assertEqual(qs[0], t_new)

    def test_unique_message_read_constraint(self):
        from django.db import IntegrityError
        t = Thread.objects.create(created_by=self.u1)
        msg = Message.objects.create(thread=t, sender=self.u1, body='hi')
        MessageRead.objects.create(message=msg, user=self.u2)
        with self.assertRaises(IntegrityError):
            MessageRead.objects.create(message=msg, user=self.u2)

    def test_message_ordering_by_created_at(self):
        t = Thread.objects.create(created_by=self.u1)
        m1 = Message.objects.create(thread=t, sender=self.u1, body='first')
        m2 = Message.objects.create(thread=t, sender=self.u2, body='second')
        msgs = list(t.messages.all())
        self.assertEqual(msgs[0], m1)
        self.assertEqual(msgs[1], m2)
