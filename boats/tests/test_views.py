"""
Tests for boats views
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from boats.models import Boat


class BoatViewsTest(TestCase):
    """Tests для views в boats app"""
    
    def setUp(self):
        """Setup для каждого теста"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.boat = Boat.objects.create(
            owner=self.user,
            name='Test Boat',
            boat_type='sailboat',
            description='Test description',
            location='Test Location',
            capacity=4,
            length=10.5,
            year=2020,
            price_per_day=1000.00,
            available=True
        )
    
    def test_home_view_GET(self):
        """Test home view with GET request"""
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boats/home.html')
        self.assertIn('form', response.context)
        self.assertIn('featured_boats', response.context)
        self.assertIn('destinations', response.context)
    
    def test_boat_detail_view_GET(self):
        """Test boat detail view"""
        response = self.client.get(
            reverse('boat_detail', kwargs={'pk': self.boat.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boats/detail.html')
        self.assertEqual(response.context['boat'], self.boat)
    
    def test_boat_detail_view_not_found(self):
        """Test boat detail view with non-existent boat"""
        response = self.client.get(
            reverse('boat_detail', kwargs={'pk': 9999})
        )
        self.assertEqual(response.status_code, 404)
    
    def test_boat_search_view_GET(self):
        """Test boat search view"""
        response = self.client.get(reverse('boat_search'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('form', response.context)


class BoatAuthenticationTest(TestCase):
    """Tests для аутентификации в views"""
    
    def setUp(self):
        """Setup для каждого теста"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.boat = Boat.objects.create(
            owner=self.user,
            name='Test Boat',
            boat_type='sailboat',
            description='Test description',
            location='Test Location',
            capacity=4,
            length=10.5,
            year=2020,
            price_per_day=1000.00,
            available=True
        )
    
    def test_favorites_list_requires_login(self):
        """Test that favorites list requires login"""
        response = self.client.get(reverse('favorites_list'))
        self.assertEqual(response.status_code, 302)  # Redirect
        self.assertTrue(response.url.startswith('/'))
    
    def test_favorites_list_authenticated(self):
        """Test favorites list for authenticated user"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('favorites_list'))
        self.assertEqual(response.status_code, 200)
