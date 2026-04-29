"""Tests for chat views."""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import translation

from boats.models import Thread, Message
from accounts.models import Role, UserProfile


def url(name, **kwargs):
    with translation.override('ru'):
        return reverse(name, kwargs=kwargs if kwargs else None)


def make_user(username, role='tourist'):
    user = User.objects.create_user(username=username, password='pass')
    role_obj = Role.objects.filter(codename=role).first()
    if role_obj:
        UserProfile.objects.filter(pk=user.profile.pk).update(role_ref=role_obj)
        user.profile.refresh_from_db()
    return user


class ChatInboxViewTest(TestCase):
    def setUp(self):
        self.user = make_user('inbox_user')
        self.other = make_user('other_user')
        self.client = Client()

    def test_inbox_requires_login(self):
        resp = self.client.get(url('chat_inbox'))
        self.assertIn(resp.status_code, [301, 302])

    def test_inbox_shows_only_user_threads(self):
        self.client.login(username='inbox_user', password='pass')
        t1 = Thread.objects.create(created_by=self.user)
        t1.participants.add(self.user)
        t2 = Thread.objects.create(created_by=self.other)
        t2.participants.add(self.other)

        resp = self.client.get(url('chat_inbox'))
        self.assertEqual(resp.status_code, 200)
        thread_ids = [item['thread'].pk for item in resp.context['thread_list']]
        self.assertIn(t1.pk, thread_ids)
        self.assertNotIn(t2.pk, thread_ids)


class ChatThreadViewTest(TestCase):
    def setUp(self):
        self.user = make_user('thread_user')
        self.outsider = make_user('outsider')
        self.client = Client()
        self.thread = Thread.objects.create(created_by=self.user)
        self.thread.participants.add(self.user)

    def test_participant_can_view_thread(self):
        self.client.login(username='thread_user', password='pass')
        resp = self.client.get(url('chat_thread', thread_id=self.thread.pk))
        self.assertEqual(resp.status_code, 200)

    def test_outsider_is_redirected(self):
        self.client.login(username='outsider', password='pass')
        resp = self.client.get(url('chat_thread', thread_id=self.thread.pk))
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, url('chat_inbox'), fetch_redirect_response=False)


class ChatCreateViewTest(TestCase):
    def setUp(self):
        self.tourist = make_user('creator', 'tourist')
        self.manager = make_user('mgr', 'manager')
        self.client = Client()

    def test_create_thread_post(self):
        self.client.login(username='creator', password='pass')
        resp = self.client.post(url('chat_create'), {
            'target_user_id': self.manager.pk,
            'subject': 'Тест',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Thread.objects.count(), 1)
        thread = Thread.objects.get()
        self.assertIn(self.tourist, thread.participants.all())
        self.assertIn(self.manager, thread.participants.all())

    def test_create_thread_get_renders_form(self):
        self.client.login(username='creator', password='pass')
        resp = self.client.get(url('chat_create'))
        self.assertEqual(resp.status_code, 200)


class ChatMessagesApiTest(TestCase):
    def setUp(self):
        self.user = make_user('api_user')
        self.outsider = make_user('api_outsider')
        self.client = Client()
        self.thread = Thread.objects.create(created_by=self.user)
        self.thread.participants.add(self.user)
        Message.objects.create(thread=self.thread, sender=self.user, body='hello')

    def test_participant_gets_messages(self):
        self.client.login(username='api_user', password='pass')
        resp = self.client.get(url('chat_messages_api', thread_id=self.thread.pk))
        self.assertEqual(resp.status_code, 200)
        import json
        data = json.loads(resp.content)
        self.assertIn('messages', data)
        self.assertEqual(len(data['messages']), 1)

    def test_outsider_gets_403(self):
        self.client.login(username='api_outsider', password='pass')
        resp = self.client.get(url('chat_messages_api', thread_id=self.thread.pk))
        self.assertEqual(resp.status_code, 403)

    def test_pagination_by_before_id(self):
        self.client.login(username='api_user', password='pass')
        resp = self.client.get(url('chat_messages_api', thread_id=self.thread.pk) + '?before_id=1')
        self.assertEqual(resp.status_code, 200)
