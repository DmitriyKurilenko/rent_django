"""
Tests for boats forms
"""
from django.test import TestCase
from boats.forms import SearchForm, BoatForm
from boats.models import Boat
from django.contrib.auth.models import User


class SearchFormTest(TestCase):
    """Tests для SearchForm"""
    
    def test_search_form_valid_empty(self):
        """Test SearchForm with empty data (all fields optional)"""
        form = SearchForm(data={})
        self.assertTrue(form.is_valid())
    
    def test_search_form_valid_with_data(self):
        """Test SearchForm with valid data"""
        form_data = {
            'location': 'Греция',
            'boat_type': 'sailboat',
            'min_capacity': 4,
            'max_price': 5000
        }
        form = SearchForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_search_form_invalid_capacity(self):
        """Test SearchForm with invalid capacity"""
        form_data = {
            'min_capacity': -1  # Negative not allowed
        }
        form = SearchForm(data=form_data)
        self.assertFalse(form.is_valid())
    
    def test_search_form_invalid_price(self):
        """Test SearchForm with invalid price"""
        form_data = {
            'max_price': -100  # Negative not allowed
        }
        form = SearchForm(data=form_data)
        self.assertFalse(form.is_valid())


class BoatFormTest(TestCase):
    """Tests для BoatForm"""
    
    def setUp(self):
        """Setup для каждого теста"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_boat_form_valid(self):
        """Test BoatForm with valid data"""
        form_data = {
            'name': 'Test Boat',
            'boat_type': 'sailboat',
            'description': 'Test description',
            'location': 'Test Location',
            'capacity': 4,
            'length': 10.5,
            'year': 2020,
            'price_per_day': 1000.00,
            'available': True,
            'cabins': 2,
            'bathrooms': 1,
            'has_skipper': False
        }
        form = BoatForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_boat_form_missing_required_field(self):
        """Test BoatForm with missing required field"""
        form_data = {
            'name': 'Test Boat',
            # 'boat_type' is missing
            'description': 'Test description',
            'location': 'Test Location',
            'capacity': 4,
            'length': 10.5,
            'year': 2020,
            'price_per_day': 1000.00,
        }
        form = BoatForm(data=form_data)
        self.assertFalse(form.is_valid())
    
    def test_boat_form_creates_instance(self):
        """Test BoatForm creates boat instance"""
        form_data = {
            'owner': self.user,
            'name': 'Created Boat',
            'boat_type': 'motorboat',
            'description': 'Created via form',
            'location': 'Form Location',
            'capacity': 6,
            'length': 12.0,
            'year': 2021,
            'price_per_day': 1500.00,
            'available': True,
            'cabins': 3,
            'bathrooms': 2,
            'has_skipper': True
        }
        form = BoatForm(data=form_data)
        if form.is_valid():
            boat = form.save(commit=False)
            boat.owner = self.user
            boat.save()
            
            self.assertEqual(boat.name, 'Created Boat')
            self.assertEqual(boat.boat_type, 'motorboat')
            self.assertEqual(boat.capacity, 6)
            self.assertTrue(boat.has_skipper)
