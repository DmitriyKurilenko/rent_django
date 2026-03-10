"""
Tests for PriceSettings model and price calculation functions.
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.cache import cache
from django.utils import translation

from boats.models import PriceSettings
from boats.helpers import calculate_tourist_price, calculate_final_price_with_discounts
from accounts.models import UserProfile


def url(name, **kwargs):
    """Reverse using 'ru' locale to match LANGUAGES setting (LANGUAGE_CODE is 'ru-ru')."""
    with translation.override('ru'):
        return reverse(name, kwargs=kwargs if kwargs else None)


def make_user(username, role):
    user = User.objects.create_user(username=username, password='pass')
    user.profile.role = role
    # bypass subscription_plan guard for admin/superadmin
    UserProfile.objects.filter(pk=user.profile.pk).update(role=role)
    user.profile.refresh_from_db()
    return user


class PriceSettingsModelTest(TestCase):
    def setUp(self):
        cache.clear()

    def test_singleton_enforced(self):
        """save() always stores to pk=1; multiple creates result in only one row."""
        PriceSettings.objects.create()
        PriceSettings.objects.create()
        self.assertEqual(PriceSettings.objects.count(), 1)
        self.assertEqual(PriceSettings.objects.first().pk, 1)

    def test_defaults(self):
        s, _ = PriceSettings.objects.get_or_create(pk=1)
        self.assertEqual(s.extra_discount_max, 5)
        self.assertEqual(s.tourist_insurance_rate, Decimal('0.1000'))
        self.assertEqual(s.tourist_insurance_min, Decimal('400.00'))
        self.assertEqual(s.tourist_turkey_base, Decimal('4400.00'))
        self.assertEqual(s.tourist_seychelles_base, Decimal('4500.00'))
        self.assertEqual(s.tourist_default_base, Decimal('4500.00'))

    def test_get_settings_returns_singleton(self):
        s = PriceSettings.get_settings()
        self.assertIsInstance(s, PriceSettings)
        self.assertEqual(s.pk, 1)

    def test_get_settings_caches(self):
        PriceSettings.get_settings()  # populates cache
        self.assertIsNotNone(cache.get('price_settings'))

    def test_save_invalidates_cache(self):
        s = PriceSettings.get_settings()
        self.assertIsNotNone(cache.get('price_settings'))
        s.extra_discount_max = 7
        s.save()
        self.assertIsNone(cache.get('price_settings'))


class CalculateTouristPriceTest(TestCase):
    def setUp(self):
        cache.clear()
        self.settings, _ = PriceSettings.objects.get_or_create(pk=1)

    def _boat_data(self, country='france', length=12.0, max_sleeps=6, doubles=2, marina=''):
        return {
            'totalPrice': 3000,
            'price': 3000,
            'discount': 0,
            'country': country,
            'category': 'Парусная Яхта',
            'marina': marina,
            'parameters': {
                'length': length,
                'max_sleeps': max_sleeps,
                'double_cabins': doubles,
            },
        }

    def test_default_country_base_price_added(self):
        data = self._boat_data(country='france')
        result = calculate_tourist_price(data)
        # insurance + default_base at minimum
        self.assertGreater(result['total_price'], 3000)

    def test_turkey_base_price_applied(self):
        data = self._boat_data(country='turkey')
        result = calculate_tourist_price(data)
        # Turkey base (4400) != default (4500), result differs
        data_fr = self._boat_data(country='france')
        result_fr = calculate_tourist_price(data_fr)
        self.assertNotEqual(result['total_price'], result_fr['total_price'])

    def test_seychelles_cabin_surcharge(self):
        data_few = self._boat_data(country='seychelles', doubles=3)
        data_many = self._boat_data(country='seychelles', doubles=6)
        r_few = calculate_tourist_price(data_few)
        r_many = calculate_tourist_price(data_many)
        self.assertGreater(r_many['total_price'], r_few['total_price'])

    def test_praslin_extra_added(self):
        data_no = self._boat_data(country='seychelles', marina='')
        data_yes = self._boat_data(country='seychelles', marina='praslin marina')
        r_no = calculate_tourist_price(data_no)
        r_yes = calculate_tourist_price(data_yes)
        self.assertAlmostEqual(
            float(r_yes['total_price']) - float(r_no['total_price']),
            float(self.settings.tourist_praslin_extra),
            places=1,
        )

    def test_length_surcharge_above_14_2(self):
        data_short = self._boat_data(length=13.0)
        data_long = self._boat_data(length=15.0)
        r_short = calculate_tourist_price(data_short)
        r_long = calculate_tourist_price(data_long)
        self.assertGreater(r_long['total_price'], r_short['total_price'])

    def test_custom_settings_applied(self):
        """Changing PriceSettings changes calculated price."""
        data = self._boat_data(country='france')
        r_before = calculate_tourist_price(data)

        self.settings.tourist_default_base = Decimal('9000.00')
        self.settings.save()
        cache.clear()

        r_after = calculate_tourist_price(data)
        self.assertGreater(r_after['total_price'], r_before['total_price'])

    def test_zero_price_returns_zero(self):
        data = {'totalPrice': 0, 'price': 0, 'discount': 0, 'country': 'france',
                'category': '', 'marina': '', 'parameters': {}}
        result = calculate_tourist_price(data)
        self.assertEqual(result['total_price'], 0)


class CalculateFinalPriceWithDiscountsTest(TestCase):
    def setUp(self):
        cache.clear()
        self.settings, _ = PriceSettings.objects.get_or_create(pk=1)

    def _charter(self, commission):
        from boats.models import Charter
        return Charter.objects.create(
            charter_id=f'test-{commission}',
            name=f'Test {commission}',
            commission=commission,
        )

    def test_no_discount_no_commission(self):
        price = calculate_final_price_with_discounts(1000, 0, 0, charter=None)
        self.assertAlmostEqual(price, 1000.0, places=2)

    def test_discount_applied(self):
        price = calculate_final_price_with_discounts(1000, 10, 0)
        self.assertAlmostEqual(price, 900.0, places=2)

    def test_extra_discount_applied_when_additional_less_than_commission(self):
        charter = self._charter(commission=20)
        # additional_discount=0 < commission=20 → extra discount applied
        price = calculate_final_price_with_discounts(1000, 0, 0, charter=charter)
        expected_extra = min(self.settings.extra_discount_max, 20)
        self.assertAlmostEqual(price, 1000 * (1 - expected_extra / 100), places=2)

    def test_custom_extra_discount_max_applied(self):
        self.settings.extra_discount_max = 3
        self.settings.save()
        cache.clear()
        charter = self._charter(commission=20)
        price = calculate_final_price_with_discounts(1000, 0, 0, charter=charter)
        self.assertAlmostEqual(price, 1000 * (1 - 3 / 100), places=2)


class PriceSettingsViewTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        PriceSettings.objects.get_or_create(pk=1)

    def test_anonymous_redirect(self):
        resp = self.client.get(url('price_settings'))
        self.assertIn(resp.status_code, [302, 301])

    def test_tourist_forbidden(self):
        user = make_user('tourist1', 'tourist')
        self.client.force_login(user)
        resp = self.client.get(url('price_settings'))
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_access(self):
        user = make_user('admin1', 'admin')
        self.client.force_login(user)
        resp = self.client.get(url('price_settings'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'accounts/price_settings.html')

    def test_superadmin_can_access(self):
        user = make_user('super1', 'superadmin')
        self.client.force_login(user)
        resp = self.client.get(url('price_settings'))
        self.assertEqual(resp.status_code, 200)

    def test_post_saves_values(self):
        user = make_user('admin2', 'admin')
        self.client.force_login(user)
        payload = {
            'extra_discount_max': '7',
            'tourist_insurance_rate': '0.1200',
            'tourist_insurance_min': '350.00',
            'tourist_turkey_base': '4600.00',
            'tourist_seychelles_base': '4700.00',
            'tourist_default_base': '4700.00',
            'tourist_praslin_extra': '450.00',
            'tourist_length_extra': '250.00',
            'tourist_cook_price': '1500.00',
            'tourist_turkey_dish_base': '160.00',
            'tourist_seychelles_dish_base': '220.00',
            'tourist_default_dish_base': '220.00',
            'tourist_max_double_cabins_free': '3',
            'tourist_double_cabin_extra': '190.00',
            'tourist_catamaran_length_extra': '550.00',
            'tourist_sailing_length_extra': '320.00',
        }
        resp = self.client.post(url('price_settings'), data=payload)
        self.assertEqual(resp.status_code, 302)
        s = PriceSettings.objects.get(pk=1)
        self.assertEqual(s.extra_discount_max, 7)
        self.assertEqual(s.tourist_insurance_rate, Decimal('0.1200'))
        self.assertEqual(s.tourist_turkey_base, Decimal('4600.00'))

    def test_post_invalid_value_shows_error(self):
        user = make_user('admin3', 'admin')
        self.client.force_login(user)
        payload = {
            'extra_discount_max': 'not_a_number',
            'tourist_insurance_rate': '0.10',
            'tourist_insurance_min': '400',
            'tourist_turkey_base': '4400',
            'tourist_seychelles_base': '4500',
            'tourist_default_base': '4500',
            'tourist_praslin_extra': '400',
            'tourist_length_extra': '200',
            'tourist_cook_price': '1400',
            'tourist_turkey_dish_base': '150',
            'tourist_seychelles_dish_base': '210',
            'tourist_default_dish_base': '210',
            'tourist_max_double_cabins_free': '4',
            'tourist_double_cabin_extra': '180',
            'tourist_catamaran_length_extra': '500',
            'tourist_sailing_length_extra': '300',
        }
        resp = self.client.post(url('price_settings'), data=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('errors', resp.context)
        self.assertIn('extra_discount_max', resp.context['errors'])
