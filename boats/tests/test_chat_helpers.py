"""Tests for boats/chat_helpers.py."""
from django.test import TestCase
from django.contrib.auth.models import User, AnonymousUser

from boats.models import Thread
from boats.chat_helpers import can_access_thread, can_initiate_thread_with
from accounts.models import Role, UserProfile


def make_user(username, role='tourist'):
    user = User.objects.create_user(username=username, password='pass')
    role_obj = Role.objects.filter(codename=role).first()
    if role_obj:
        UserProfile.objects.filter(pk=user.profile.pk).update(role_ref=role_obj)
        user.profile.refresh_from_db()
    return user


class CanAccessThreadTest(TestCase):
    def setUp(self):
        self.owner = make_user('owner', 'manager')
        self.other = make_user('other', 'tourist')
        self.admin = make_user('admin_u', 'admin')
        self.thread = Thread.objects.create(created_by=self.owner)
        self.thread.participants.add(self.owner)

    def test_participant_can_access(self):
        self.assertTrue(can_access_thread(self.owner, self.thread))

    def test_non_participant_cannot_access(self):
        self.assertFalse(can_access_thread(self.other, self.thread))

    def test_admin_can_access_any_thread(self):
        self.assertTrue(can_access_thread(self.admin, self.thread))

    def test_anonymous_cannot_access(self):
        anon = AnonymousUser()
        self.assertFalse(can_access_thread(anon, self.thread))


class CanInitiateThreadWithTest(TestCase):
    def setUp(self):
        self.tourist = make_user('tourist1', 'tourist')
        self.manager = make_user('mgr1', 'manager')
        self.manager2 = make_user('mgr2', 'manager')
        self.captain = make_user('captain1', 'captain')

    def test_tourist_can_write_to_assigned_staff(self):
        profile = self.tourist.profile
        profile.assigned_staff = self.manager
        profile.save()
        self.tourist.profile.refresh_from_db()
        self.assertTrue(can_initiate_thread_with(self.tourist, self.manager))

    def test_tourist_cannot_write_to_non_assigned_staff(self):
        profile = self.tourist.profile
        profile.assigned_staff = self.manager
        profile.save()
        self.tourist.profile.refresh_from_db()
        self.assertFalse(can_initiate_thread_with(self.tourist, self.manager2))

    def test_tourist_without_assigned_staff_can_write_to_manager(self):
        self.assertIsNone(self.tourist.profile.assigned_staff)
        self.assertTrue(can_initiate_thread_with(self.tourist, self.manager))

    def test_manager_can_write_to_anyone(self):
        self.assertTrue(can_initiate_thread_with(self.manager, self.tourist))
        self.assertTrue(can_initiate_thread_with(self.manager, self.captain))

    def test_cannot_write_to_self(self):
        self.assertFalse(can_initiate_thread_with(self.manager, self.manager))


class CanMakeInternalBookingTest(TestCase):
    def setUp(self):
        self.tourist = make_user('t1', 'tourist')
        self.captain = make_user('c1', 'captain')
        self.manager = make_user('m1', 'manager')
        self.assistant = make_user('a1', 'assistant')
        self.admin = make_user('adm1', 'admin')
        self.superadmin = make_user('sa1', 'superadmin')

    def test_tourist_cannot_make_internal_booking(self):
        self.assertFalse(self.tourist.profile.can_make_internal_booking())

    def test_captain_cannot_make_internal_booking(self):
        self.assertFalse(self.captain.profile.can_make_internal_booking())

    def test_manager_can_make_internal_booking(self):
        self.assertTrue(self.manager.profile.can_make_internal_booking())

    def test_assistant_can_make_internal_booking(self):
        self.assertTrue(self.assistant.profile.can_make_internal_booking())

    def test_admin_can_make_internal_booking(self):
        self.assertTrue(self.admin.profile.can_make_internal_booking())

    def test_superadmin_can_make_internal_booking(self):
        self.assertTrue(self.superadmin.profile.can_make_internal_booking())
