from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    """Профиль пользователя с ролью"""

    SUBSCRIPTION_CHOICES = [
        ('free', 'Бесплатная'),
        ('standard', 'Стандарт (500 ₽/мес)'),
        ('advanced', 'Продвинутая'),
    ]
    
    ROLE_CHOICES = [
        ('tourist', 'Турист'),           # Поиск, просмотр, избранное
        ('captain', 'Капитан'),          # + Капитанский оффер
        ('manager', 'Менеджер'),         # + Туристический оффер
        ('admin', 'Администратор'),      # Все права
        ('superadmin', 'Суперадмин'),    # Максимальные права (управление чартерами)
    ]
    
    # Legacy роли для обратной совместимости (будут мигрированы)
    LEGACY_ROLE_MAPPING = {
        'client': 'tourist',
        'agent': 'captain',
        'manager': 'manager',
        'admin': 'admin',
    }
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField('Роль', max_length=20, choices=ROLE_CHOICES, default='tourist')
    subscription_plan = models.CharField('Подписка', max_length=20, choices=SUBSCRIPTION_CHOICES, default='free')
    phone = models.CharField('Телефон', max_length=20, blank=True)
    bio = models.TextField('О себе', blank=True)
    avatar = models.ImageField('Аватар', upload_to='avatars/', blank=True, null=True)
    created_at = models.DateTimeField('Дата регистрации', auto_now_add=True)
    
    class Meta:
        verbose_name = 'Профиль пользователя'
        verbose_name_plural = 'Профили пользователей'
    
    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    def save(self, *args, **kwargs):
        if self.role in ['tourist', 'captain']:
            if self.subscription_plan == 'free':
                self.role = 'tourist'
            elif self.subscription_plan in ['standard', 'advanced']:
                self.role = 'captain'
        super().save(*args, **kwargs)
    
    # =========================================================================
    # Свойства для проверки ролей
    # =========================================================================
    
    @property
    def is_tourist(self):
        """Турист - базовая роль"""
        return self.role == 'tourist'
    
    @property
    def is_captain(self):
        """Капитан - может создавать капитанские офферы"""
        return self.role == 'captain'
    
    @property
    def is_manager(self):
        """Менеджер - может создавать туристические офферы"""
        return self.role == 'manager'
    
    @property
    def is_admin_role(self):
        """Администратор - все права"""
        return self.role == 'admin'
    
    @property
    def is_superadmin(self):
        """Суперадминистратор - максимальные права"""
        return self.role == 'superadmin'
    
    # Legacy properties для обратной совместимости
    @property
    def is_client(self):
        """Legacy: client → tourist"""
        return self.is_tourist
    
    @property
    def is_agent(self):
        """Legacy: agent → captain"""
        return self.is_captain
    
    # =========================================================================
    # Методы проверки прав доступа
    # =========================================================================
    
    def can_search_boats(self):
        """Может искать лодки (все роли)"""
        return True
    
    def can_add_to_favorites(self):
        """Может добавлять в избранное (все роли)"""
        return True

    def can_book_boats(self):
        """Может бронировать лодки с детальной страницы"""
        return self.role in ['tourist', 'captain', 'agent']
    
    def can_create_captain_offers(self):
        """Может создавать капитанские (агентские) офферы"""
        return self.role in ['captain', 'manager', 'superadmin']
    
    def can_create_tourist_offers(self):
        """Может создавать туристические офферы (только manager и superadmin)"""
        return self.role in ['manager', 'superadmin']
    
    def can_create_offers(self):
        """Может создавать офферы согласно доступным типам"""
        return self.can_create_captain_offers() or self.can_create_tourist_offers()
    
    def can_manage_boats(self):
        """Может управлять лодками (manager, admin)"""
        return self.role in ['manager', 'admin']
    
    def can_see_all_bookings(self):
        """Может видеть все бронирования (только manager)"""
        return self.role == 'manager'
    
    def can_access_admin_panel(self):
        """Может заходить в админку (manager, admin, superadmin)"""
        return self.role in ['manager', 'admin', 'superadmin']
    
    def can_manage_charters(self):
        """Может управлять чартерными компаниями (только superadmin)"""
        return self.role == 'superadmin'

    def can_use_no_branding(self):
        """Может использовать режим без брендинга в офферах"""
        return self.subscription_plan == 'advanced' or self.role in ['admin', 'superadmin']

    def can_use_custom_branding(self):
        """Может использовать кастомный брендинг в офферах"""
        return self.subscription_plan == 'advanced' or self.role in ['admin', 'superadmin']
    
    def get_allowed_offer_types(self):
        """
        Возвращает список типов офферов, которые может создавать пользователь.
        
        Returns:
            list: ['tourist', 'captain'] или []
        """
        allowed = []
        
        if self.can_create_tourist_offers():
            allowed.append('tourist')
        
        if self.can_create_captain_offers():
            allowed.append('captain')
        
        return allowed


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Автоматическое создание профиля при создании пользователя"""
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Автоматическое сохранение профиля"""
    if hasattr(instance, 'profile'):
        instance.profile.save()
