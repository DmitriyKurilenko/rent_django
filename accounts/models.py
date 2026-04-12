from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class Permission(models.Model):
    """Разрешение, назначаемое ролям"""
    codename = models.CharField('Код', max_length=50, unique=True, db_index=True)
    name = models.CharField('Название', max_length=100)

    class Meta:
        verbose_name = 'Разрешение'
        verbose_name_plural = 'Разрешения'
        ordering = ['codename']

    def __str__(self):
        return f'{self.codename} — {self.name}'


class Role(models.Model):
    """Роль пользователя с набором разрешений"""
    codename = models.CharField('Код', max_length=20, unique=True, db_index=True)
    name = models.CharField('Название', max_length=50)
    permissions = models.ManyToManyField(
        Permission, blank=True, related_name='roles', verbose_name='Разрешения'
    )
    is_system = models.BooleanField(
        'Системная', default=False,
        help_text='Системные роли нельзя удалить'
    )

    class Meta:
        verbose_name = 'Роль'
        verbose_name_plural = 'Роли'
        ordering = ['codename']

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    """Профиль пользователя с ролью"""

    SUBSCRIPTION_CHOICES = [
        ('free', 'Бесплатная'),
        ('standard', 'Стандарт (500 ₽/мес)'),
        ('advanced', 'Продвинутая'),
    ]

    # Legacy — оставлены для обратной совместимости (шаблоны, тесты)
    ROLE_CHOICES = [
        ('tourist', 'Турист'),
        ('captain', 'Капитан'),
        ('assistant', 'Ассистент'),
        ('manager', 'Менеджер'),
        ('admin', 'Администратор'),
        ('superadmin', 'Суперадмин'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role_ref = models.ForeignKey(
        Role, on_delete=models.PROTECT, related_name='profiles',
        verbose_name='Роль', null=True,
    )
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

    # =========================================================================
    # role property — обратная совместимость с шаблонами и views
    # profile.role == 'captain' продолжает работать
    # =========================================================================

    @property
    def role(self):
        """Возвращает codename роли (str). Совместимо с profile.role == 'captain'."""
        if self.role_ref_id:
            return self.role_ref.codename
        return 'tourist'

    @role.setter
    def role(self, value):
        """Устанавливает роль по codename. Совместимо с profile.role = 'captain'."""
        if isinstance(value, Role):
            self.role_ref = value
        else:
            try:
                self.role_ref = Role.objects.get(codename=value)
            except Role.DoesNotExist:
                pass

    def get_role_display(self):
        """Человекочитаемое название роли."""
        if self.role_ref_id:
            return self.role_ref.name
        return 'Турист'

    def save(self, *args, **kwargs):
        # Авто-назначение роли по подписке для tourist/captain
        if self.role_ref_id and self.role in ['tourist', 'captain']:
            if self.subscription_plan == 'free':
                self.role = 'tourist'
            elif self.subscription_plan in ['standard', 'advanced']:
                self.role = 'captain'
        # Если role_ref не задан — ставим tourist
        if not self.role_ref_id:
            tourist_role = Role.objects.filter(codename='tourist').first()
            if tourist_role:
                self.role_ref = tourist_role
        super().save(*args, **kwargs)

    # =========================================================================
    # Свойства для проверки ролей — обратная совместимость
    # =========================================================================

    @property
    def is_tourist(self):
        return self.role == 'tourist'

    @property
    def is_captain(self):
        return self.role == 'captain'

    @property
    def is_assistant(self):
        return self.role == 'assistant'

    @property
    def is_manager(self):
        return self.role == 'manager'

    @property
    def is_admin_role(self):
        return self.role == 'admin'

    @property
    def is_superadmin(self):
        return self.role == 'superadmin'

    # Legacy
    @property
    def is_client(self):
        return self.is_tourist

    @property
    def is_agent(self):
        return self.is_captain

    # =========================================================================
    # Система разрешений
    # =========================================================================

    _perm_cache = None

    def has_perm(self, codename):
        """Проверяет наличие разрешения у роли пользователя."""
        if not self.role_ref_id:
            return False
        if self._perm_cache is None:
            self._perm_cache = set(
                self.role_ref.permissions.values_list('codename', flat=True)
            )
        return codename in self._perm_cache

    def clear_perm_cache(self):
        self._perm_cache = None

    # =========================================================================
    # Методы проверки прав — делегируют в has_perm()
    # =========================================================================

    def can_search_boats(self):
        return self.has_perm('search_boats')

    def can_add_to_favorites(self):
        return self.has_perm('add_favorites')

    def can_book_boats(self):
        return self.has_perm('book_boats')

    def can_create_captain_offers(self):
        return self.has_perm('create_captain_offers')

    def can_create_tourist_offers(self):
        return self.has_perm('create_tourist_offers')

    def can_create_offers(self):
        return self.can_create_captain_offers() or self.can_create_tourist_offers()

    def can_confirm_booking(self):
        return self.has_perm('confirm_booking')

    def can_notify_captains(self):
        return self.has_perm('notify_captains')

    def can_see_all_bookings(self):
        return self.has_perm('view_all_bookings')

    def can_manage_boats(self):
        return self.has_perm('manage_boats')

    def can_access_admin_panel(self):
        return self.has_perm('access_admin')

    def can_manage_charters(self):
        return self.has_perm('manage_charters')

    def can_manage_prices(self):
        return self.has_perm('manage_prices')

    def can_view_price_breakdown(self):
        return self.has_perm('view_price_breakdown')

    def can_assign_managers(self):
        return self.has_perm('assign_managers')

    def can_delete_bookings(self):
        return self.has_perm('delete_bookings')

    def can_delete_offers(self):
        return self.has_perm('delete_offers')

    def can_create_contracts(self):
        return self.has_perm('create_contracts')

    def can_view_all_clients(self):
        return self.has_perm('view_all_clients')

    def can_use_countdown(self):
        return self.has_perm('use_countdown')

    def can_use_force_refresh(self):
        return self.has_perm('use_force_refresh')

    def can_use_no_branding(self):
        return self.subscription_plan == 'advanced' or self.has_perm('no_branding')

    def can_use_custom_branding(self):
        return self.subscription_plan == 'advanced' or self.has_perm('custom_branding')

    def get_allowed_offer_types(self):
        """Возвращает список типов офферов, доступных пользователю."""
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
