"""
Tests for boats app
"""
from django.test import TestCase
from django.contrib.auth.models import User
from boats.models import Boat


class BoatModelTest(TestCase):
    """Tests для модели Boat"""
    
    @classmethod
    def setUpTestData(cls):
        """Setup test data"""
        cls.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        cls.boat = Boat.objects.create(
            owner=cls.user,
            name='Test Boat',
            boat_type='sailboat',
            description='Test description',
            location='Test Location',
            capacity=4,
            length=10.5,
            year=2020,
            price_per_day=1000.00,
            available=True,
            cabins=2,
            bathrooms=1,
            has_skipper=False
        )
    
    def test_boat_creation(self):
        """Test that boat was created correctly"""
        self.assertEqual(self.boat.name, 'Test Boat')
        self.assertEqual(self.boat.boat_type, 'sailboat')
        self.assertEqual(self.boat.capacity, 4)
        self.assertTrue(self.boat.available)
    
    def test_boat_str_representation(self):
        """Test __str__ method"""
        expected = f"{self.boat.name} - {self.boat.location}"
        self.assertEqual(str(self.boat), expected)
    
    def test_boat_get_absolute_url(self):
        """Test get_absolute_url method"""
        url = self.boat.get_absolute_url()
        # URL имеет префикс языка из i18n_patterns
        self.assertIn('boat/1/', url)
    
    def test_boat_owner_relationship(self):
        """Test ForeignKey relationship to User"""
        self.assertEqual(self.boat.owner, self.user)
        self.assertIn(self.boat, self.user.boats.all())
    
    def test_boat_meta_verbose_name(self):
        """Test Meta verbose_name"""
        self.assertEqual(str(Boat._meta.verbose_name), 'Лодка')
        self.assertEqual(str(Boat._meta.verbose_name_plural), 'Лодки')
    
    def test_boat_ordering(self):
        """Test model ordering"""
        # Create another boat
        boat2 = Boat.objects.create(
            owner=self.user,
            name='Second Boat',
            boat_type='motorboat',
            description='Test 2',
            location='Test Location 2',
            capacity=6,
            length=12.0,
            year=2021,
            price_per_day=1500.00
        )
        
        # Check ordering by -created_at
        boats = Boat.objects.all()
        self.assertEqual(boats[0], boat2)  # Most recent first
        self.assertEqual(boats[1], self.boat)
