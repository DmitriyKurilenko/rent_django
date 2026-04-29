"""Tests for accounts/signals.py — auto-assignment of assigned_staff."""
from django.test import TestCase
from django.contrib.auth.models import User

from boats.models import Booking
from accounts.models import Role, UserProfile


def make_user(username, role='tourist'):
    user = User.objects.create_user(username=username, password='pass')
    role_obj = Role.objects.filter(codename=role).first()
    if role_obj:
        UserProfile.objects.filter(pk=user.profile.pk).update(role_ref=role_obj)
        user.profile.refresh_from_db()
    return user


class AssignedStaffSignalTest(TestCase):
    def setUp(self):
        self.tourist = make_user('sig_tourist', 'tourist')
        self.manager = make_user('sig_manager', 'manager')
        self.manager2 = make_user('sig_manager2', 'manager')

    def _make_booking(self, user, manager=None):
        return Booking.objects.create(
            user=user,
            assigned_manager=manager,
            start_date='2025-01-01',
            end_date='2025-01-07',
            guests=2,
            total_price=1000,
            status='pending',
        )

    def test_assigned_staff_set_when_manager_assigned(self):
        booking = self._make_booking(self.tourist, manager=self.manager)
        self.tourist.profile.refresh_from_db()
        self.assertEqual(self.tourist.profile.assigned_staff, self.manager)

    def test_assigned_staff_not_cleared_when_no_manager(self):
        self.tourist.profile.assigned_staff = self.manager
        self.tourist.profile.save()
        booking = self._make_booking(self.tourist, manager=None)
        self.tourist.profile.refresh_from_db()
        self.assertEqual(self.tourist.profile.assigned_staff, self.manager)

    def test_assigned_staff_updated_on_manager_change(self):
        booking = self._make_booking(self.tourist, manager=self.manager)
        self.tourist.profile.refresh_from_db()
        self.assertEqual(self.tourist.profile.assigned_staff, self.manager)

        booking.assigned_manager = self.manager2
        booking.save()
        self.tourist.profile.refresh_from_db()
        self.assertEqual(self.tourist.profile.assigned_staff, self.manager2)
