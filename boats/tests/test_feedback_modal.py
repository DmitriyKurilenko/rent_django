"""
Tests for feedback modal: feedback_submit endpoint and role-based booking button visibility.
"""
import json
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import translation

from boats.models import Feedback, ParsedBoat, Offer
from accounts.models import Role, UserProfile


def url(name, **kwargs):
    with translation.override('ru'):
        return reverse(name, kwargs=kwargs if kwargs else None)


def make_user(username, role):
    user = User.objects.create_user(username=username, password='pass')
    UserProfile.objects.filter(pk=user.profile.pk).update(
        role_ref=Role.objects.get(codename=role),
    )
    user.profile.refresh_from_db()
    return user


class FeedbackSubmitViewTest(TestCase):
    """Tests for the feedback_submit AJAX endpoint."""

    def setUp(self):
        self.client = Client()
        self.submit_url = url('feedback_submit')

    def test_valid_post_returns_ok_and_creates_feedback(self):
        """POST with valid data returns {'ok': True} and saves Feedback to DB."""
        with patch('boats.tasks.send_feedback_notification') as mock_task:
            mock_task.delay.return_value = None
            resp = self.client.post(self.submit_url, {
                'name': 'Иван',
                'email': 'ivan@example.com',
                'message': 'Хочу арендовать яхту',
            })
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data.get('ok'))
        self.assertEqual(Feedback.objects.count(), 1)
        fb = Feedback.objects.get()
        self.assertEqual(fb.name, 'Иван')
        self.assertEqual(fb.email, 'ivan@example.com')

    def test_missing_required_field_returns_400_and_errors(self):
        """POST without email returns 400 with field errors and no Feedback created."""
        resp = self.client.post(self.submit_url, {
            'name': 'Иван',
            'message': 'Привет',
        })
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.content)
        self.assertIn('errors', data)
        self.assertIn('email', data['errors'])
        self.assertEqual(Feedback.objects.count(), 0)

    def test_get_returns_405(self):
        """GET request returns 405 Method Not Allowed."""
        resp = self.client.get(self.submit_url)
        self.assertEqual(resp.status_code, 405)

    def test_anonymous_post_succeeds(self):
        """Endpoint is accessible without authentication (no login_required)."""
        with patch('boats.tasks.send_feedback_notification') as mock_task:
            mock_task.delay.return_value = None
            resp = self.client.post(self.submit_url, {
                'name': 'Аноним',
                'email': 'anon@example.com',
                'message': 'Запрос',
            })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(json.loads(resp.content).get('ok'))

    def test_celery_task_called_with_feedback_pk(self):
        """On success, send_feedback_notification.delay is called with the new Feedback pk."""
        with patch('boats.tasks.send_feedback_notification') as mock_task:
            mock_task.delay.return_value = None
            self.client.post(self.submit_url, {
                'name': 'Тест',
                'email': 'test@example.com',
                'message': 'Тест сообщения',
            })
            fb = Feedback.objects.get()
            mock_task.delay.assert_called_once_with(fb.pk)

    def test_optional_phone_field_accepted(self):
        """POST with phone field saves phone value."""
        with patch('boats.tasks.send_feedback_notification') as mock_task:
            mock_task.delay.return_value = None
            self.client.post(self.submit_url, {
                'name': 'Тест',
                'phone': '+79001234567',
                'email': 'test@example.com',
                'message': 'Тест',
            })
        fb = Feedback.objects.get()
        self.assertEqual(fb.phone, '+79001234567')


class FeedbackFormContextProcessorTest(TestCase):
    """feedback_form is injected into every page via context processor."""

    def test_home_page_has_feedback_form_in_context(self):
        resp = self.client.get(url('home'))
        self.assertIn('feedback_form', resp.context)

    def test_home_page_renders_feedbackModal(self):
        resp = self.client.get(url('home'))
        self.assertContains(resp, 'feedbackModal')


class CanMakeInternalBookingTest(TestCase):
    """UserProfile.can_make_internal_booking() returns correct values per role."""

    def _profile(self, role):
        user = make_user(f'user_{role}', role)
        return user.profile

    def test_manager_can_make_internal_booking(self):
        self.assertTrue(self._profile('manager').can_make_internal_booking())

    def test_assistant_can_make_internal_booking(self):
        self.assertTrue(self._profile('assistant').can_make_internal_booking())

    def test_admin_can_make_internal_booking(self):
        self.assertTrue(self._profile('admin').can_make_internal_booking())

    def test_superadmin_can_make_internal_booking(self):
        self.assertTrue(self._profile('superadmin').can_make_internal_booking())

    def test_tourist_cannot_make_internal_booking(self):
        self.assertFalse(self._profile('tourist').can_make_internal_booking())

    def test_captain_cannot_make_internal_booking(self):
        self.assertFalse(self._profile('captain').can_make_internal_booking())


class DetailPageBookingButtonTest(TestCase):
    """Booking button on detail page routes by role."""

    def setUp(self):
        self.client = Client()
        self.boat = ParsedBoat.objects.create(
            boat_id='test-001',
            slug='test-boat-001',
            source_url='https://boataround.com/yacht/test-boat-001',
        )
        self.detail_url = url('boat_detail_api', boat_id=self.boat.boat_id)

    def test_tourist_sees_feedbackModal_button(self):
        user = make_user('tourist_btn', 'tourist')
        self.client.force_login(user)
        resp = self.client.get(self.detail_url)
        content = resp.content.decode()
        self.assertIn('feedbackModal', content)

    def test_manager_sees_bookingModal_button(self):
        user = make_user('manager_btn', 'manager')
        self.client.force_login(user)
        resp = self.client.get(self.detail_url)
        content = resp.content.decode()
        self.assertIn('bookingModal', content)


class OfferViewCanBookFromOfferTest(TestCase):
    """can_book_from_offer is True only for internal roles."""

    def setUp(self):
        self.client = Client()
        self.author = make_user('offer_author', 'captain')
        self.offer = Offer.objects.create(
            created_by=self.author,
            offer_type='tourist',
            title='Test Offer',
            source_url='https://www.boataround.com/ru/yachta/test-boat/?checkIn=2026-06-01&checkOut=2026-06-08',
            check_in='2026-06-01',
            check_out='2026-06-08',
            boat_data={'slug': 'test-boat', 'images': []},
            total_price=1000,
            currency='EUR',
        )
        self.offer_url = url('offer_view', uuid=str(self.offer.uuid))

    def test_manager_has_can_book_from_offer(self):
        mgr = make_user('mgr_offer', 'manager')
        self.client.force_login(mgr)
        resp = self.client.get(self.offer_url)
        self.assertTrue(resp.context.get('can_book_from_offer'))

    def test_captain_author_has_can_book_from_offer(self):
        """Автор оффера всегда может забронировать, независимо от роли."""
        self.client.force_login(self.author)
        resp = self.client.get(self.offer_url)
        self.assertTrue(resp.context.get('can_book_from_offer'))

    def test_non_author_captain_does_not_have_can_book_from_offer(self):
        """Капитан, не являющийся автором, не видит кнопку прямого бронирования."""
        other_captain = make_user('other_captain', 'captain')
        self.client.force_login(other_captain)
        resp = self.client.get(self.offer_url)
        self.assertFalse(resp.context.get('can_book_from_offer'))
