from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
import uuid
from uuid import uuid4 as _uuid4


class Charter(models.Model):
    """Чартерная компания"""
    
    charter_id = models.CharField('ID чартера', max_length=100, unique=True, db_index=True)
    name = models.CharField('Название', max_length=200)
    logo = models.CharField('Логотип (путь)', max_length=500, blank=True)
    commission = models.IntegerField(
        'Комиссия (%)',
        default=20,
        help_text='Процент комиссии, добавляемый к итоговой цене'
    )
    
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    # Рейтинг из API
    rank_score = models.FloatField('Рейтинг', null=True, blank=True)
    rank_place = models.IntegerField('Место в рейтинге', null=True, blank=True)
    rank_out_of = models.IntegerField('Всего в рейтинге', null=True, blank=True)
    rank_reviews_count = models.IntegerField('Кол-во отзывов', null=True, blank=True)
    
    class Meta:
        verbose_name = 'Чартерная компания'
        verbose_name_plural = 'Чартерные компании'
        ordering = ['name']
        indexes = [
            models.Index(fields=['charter_id']),
        ]
    
    def __str__(self):
        return f"{self.name} (комиссия: {self.commission}%)"


class Boat(models.Model):
    """Модель лодки"""
    
    BOAT_TYPES = [
        ('sailboat', 'Парусная яхта'),
        ('motorboat', 'Моторная лодка'),
        ('catamaran', 'Катамаран'),
        ('yacht', 'Яхта'),
        ('speedboat', 'Катер'),
    ]
    
    owner = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='boats',
        verbose_name='Владелец',
        null=True,
        blank=True
    )
    name = models.CharField('Название', max_length=200)
    boat_type = models.CharField('Тип', max_length=20, choices=BOAT_TYPES)
    description = models.TextField('Описание')
    location = models.CharField('Местоположение', max_length=200)
    capacity = models.IntegerField('Вместимость (чел.)')
    length = models.DecimalField('Длина (м)', max_digits=5, decimal_places=2)
    year = models.IntegerField('Год выпуска')
    price_per_day = models.DecimalField('Цена/день (₽)', max_digits=10, decimal_places=2)
    image = models.ImageField('Фото', upload_to='boats/', blank=True, null=True)
    available = models.BooleanField('Доступна', default=True)
    
    # Дополнительные характеристики
    cabins = models.IntegerField('Кают', default=0)
    bathrooms = models.IntegerField('Санузлов', default=0)
    has_skipper = models.BooleanField('Шкипер', default=False)
    
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    
    class Meta:
        verbose_name = 'Лодка'
        verbose_name_plural = 'Лодки'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} - {self.location}"
    
    def get_absolute_url(self):
        return reverse('boat_detail', kwargs={'pk': self.pk})


class Favorite(models.Model):
    """Избранные лодки"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorites')
    parsed_boat = models.ForeignKey('ParsedBoat', on_delete=models.CASCADE, related_name='favorited_by', null=True, blank=True)
    boat_slug = models.CharField('Slug лодки', max_length=255, db_index=True, default='unknown', blank=True)
    boat_id = models.CharField('ID лодки', max_length=100, db_index=True, default='', blank=True)
    created_at = models.DateTimeField('Добавлено', auto_now_add=True)
    
    class Meta:
        verbose_name = 'Избранное'
        verbose_name_plural = 'Избранное'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'boat_slug']),
            models.Index(fields=['user', 'created_at']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['user', 'boat_slug'], name='unique_user_boat_slug'),
        ]
    
    def __str__(self):
        boat_title = self.parsed_boat.boat_data.get('boat_info', {}).get('title', 'Unknown') if self.parsed_boat else self.boat_slug
        return f"{self.user.username} - {boat_title}"
    
    def get_boat_title(self):
        """Получить название лодки из boat_data"""
        if self.parsed_boat and self.parsed_boat.boat_data:
            return self.parsed_boat.boat_data.get('boat_info', {}).get('title', self.boat_slug)
        return self.boat_slug
    
    def get_boat_image(self):
        """Получить первое изображение лодки"""
        if self.parsed_boat and self.parsed_boat.boat_data:
            images = self.parsed_boat.boat_data.get('images', [])
            if images and len(images) > 0:
                return images[0].get('thumb') or images[0].get('main_img')
        return None


class Client(models.Model):
    """Клиент (турист) — заказчик агента/капитана"""

    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='created_clients',
        verbose_name='Создал (агент/капитан)'
    )

    # Опциональная связь с зарегистрированным пользователем
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='client_profile',
        verbose_name='Аккаунт пользователя'
    )

    # ФИО
    last_name = models.CharField('Фамилия', max_length=100)
    first_name = models.CharField('Имя', max_length=100)
    middle_name = models.CharField('Отчество', max_length=100, blank=True)

    # Контакты
    email = models.EmailField('Email', blank=True)
    phone = models.CharField('Телефон', max_length=30)

    # Документы
    passport_number = models.CharField('Номер паспорта', max_length=50, blank=True)
    passport_issued_by = models.CharField('Кем выдан', max_length=200, blank=True)
    passport_date = models.DateField('Дата выдачи', null=True, blank=True)
    address = models.TextField('Адрес', blank=True)

    # Заметки агента
    notes = models.TextField('Заметки', blank=True)

    # Метаданные
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Клиент'
        verbose_name_plural = 'Клиенты'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_by', '-created_at']),
            models.Index(fields=['last_name', 'first_name']),
        ]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        parts = [self.last_name, self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        return ' '.join(parts)

    @property
    def short_name(self):
        """Фамилия И.О."""
        result = self.last_name
        if self.first_name:
            result += f' {self.first_name[0]}.'
        if self.middle_name:
            result += f'{self.middle_name[0]}.'
        return result


class Booking(models.Model):
    """Бронирование лодки"""
    
    STATUS_CHOICES = [
        ('pending', 'Ожидает'),
        ('option', 'На опции'),
        ('confirmed', 'Подтверждено'),
        ('cancelled', 'Отменено'),
        ('completed', 'Завершено'),
    ]
    
    # Старая связь (опциональная, для обратной совместимости)
    boat = models.ForeignKey(Boat, on_delete=models.CASCADE, related_name='bookings', null=True, blank=True)
    
    # Новая связь с оффером (основная)
    offer = models.ForeignKey('Offer', on_delete=models.CASCADE, related_name='bookings', null=True, blank=True)
    
    # Ссылка на ParsedBoat для прямых бронирований
    parsed_boat = models.ForeignKey('ParsedBoat', on_delete=models.SET_NULL, related_name='bookings', null=True, blank=True)
    
    # Пользователь (турист)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    
    # Даты
    start_date = models.DateField('Дата начала')
    end_date = models.DateField('Дата окончания')
    guests = models.IntegerField('Гостей', default=1)
    
    # Статус
    status = models.CharField('Статус', max_length=20, choices=STATUS_CHOICES, default='pending')
    option_until = models.DateField('Опция действует до', null=True, blank=True)
    
    # Цена
    total_price = models.DecimalField('Итого', max_digits=10, decimal_places=2)
    currency = models.CharField('Валюта', max_length=3, default='EUR')
    
    # boat_data deprecated - используем связанные таблицы
    boat_data = models.JSONField('Данные лодки', default=dict)
    
    # Сообщение от туриста
    message = models.TextField('Сообщение', blank=True)
    
    # Клиент (турист)
    client = models.ForeignKey(
        'Client', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='bookings',
        verbose_name='Клиент'
    )

    # Ответственный менеджер
    assigned_manager = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assigned_bookings',
        verbose_name='Ответственный менеджер'
    )

    # Метаданные
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Бронирование'
        verbose_name_plural = 'Бронирования'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['offer']),
            models.Index(fields=['client']),
        ]
    
    def __str__(self):
        return f"{self.boat_title} - {self.user.username} ({self.start_date})"
    
    def get_parsed_boat(self):
        """Получить ParsedBoat из offer или напрямую"""
        if self.parsed_boat:
            return self.parsed_boat
        if self.offer:
            # Получаем ParsedBoat из оффера по boat_id
            from boats.models import ParsedBoat
            try:
                return ParsedBoat.objects.get(boat_id=self.offer.boat_data.get('boat_id'))
            except ParsedBoat.DoesNotExist:
                return None
        return None
    
    @property
    def boat_title(self):
        """Название лодки из связанных таблиц"""
        parsed_boat = self.get_parsed_boat()
        if parsed_boat:
            # Берем из BoatDescription на текущем языке
            from django.utils.translation import get_language
            lang_map = {'ru': 'ru_RU', 'en': 'en_EN', 'de': 'de_DE', 'es': 'es_ES', 'fr': 'fr_FR'}
            lang = lang_map.get(get_language()[:2], 'en_EN')
            
            description = parsed_boat.descriptions.filter(language=lang).first()
            if description:
                return description.title
        
        # Fallback на boat_data если есть
        if self.boat_data:
            title = self.boat_data.get('boat_info', {}).get('title', '')
            if title:
                return title
        
        # Fallback на offer.boat_data
        if self.offer and self.offer.boat_data:
            return self.offer.boat_data.get('boat_info', {}).get('title', '')
        
        if self.boat:
            return self.boat.name
        
        return 'Без названия'
    
    @property
    def boat_image(self):
        """CDN превью или None (шаблон покажет заглушку).
        Если view предзагрузил _cached_preview — используем без запроса."""
        if hasattr(self, '_cached_preview'):
            return self._cached_preview
        parsed_boat = self.get_parsed_boat()
        if parsed_boat and parsed_boat.preview_cdn_url:
            return parsed_boat.preview_cdn_url
        return None
    
    @property
    def location(self):
        """Локация из связанных таблиц - город, регион, страна"""
        parsed_boat = self.get_parsed_boat()
        if parsed_boat:
            # Берем из BoatDescription на текущем языке
            from django.utils.translation import get_language
            lang_map = {'ru': 'ru_RU', 'en': 'en_EN', 'de': 'de_DE', 'es': 'es_ES', 'fr': 'fr_FR'}
            lang = lang_map.get(get_language()[:2], 'en_EN')
            
            description = parsed_boat.descriptions.filter(language=lang).first()
            if description:
                # Формируем полную локацию: Marina / City, Region, Country
                parts = []
                if description.marina:
                    parts.append(description.marina)
                if description.city:
                    parts.append(description.city)
                if description.region and description.region != description.city:
                    parts.append(description.region)
                if description.country:
                    parts.append(description.country)
                
                if parts:
                    return ', '.join(parts)
        
        # Fallback на boat_data
        if self.boat_data:
            location = self.boat_data.get('boat_info', {}).get('location', '')
            if location:
                return location
        
        # Fallback на offer.boat_data
        if self.offer and self.offer.boat_data:
            return self.offer.boat_data.get('boat_info', {}).get('location', '')
        
        return ''


class Notification(models.Model):
    """Уведомление пользователя о событии в системе."""

    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='Получатель',
    )
    booking = models.ForeignKey(
        'Booking', on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='notifications',
        verbose_name='Бронирование',
    )
    message = models.TextField('Текст уведомления')
    is_read = models.BooleanField('Прочитано', default=False)
    created_at = models.DateTimeField('Создано', auto_now_add=True)

    class Meta:
        verbose_name = 'Уведомление'
        verbose_name_plural = 'Уведомления'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', '-created_at']),
            models.Index(fields=['recipient', 'is_read']),
        ]

    def __str__(self):
        return f"[{self.recipient.username}] {self.message[:60]}"


class Review(models.Model):
    """Отзыв о лодке"""
    
    boat = models.ForeignKey(Boat, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews')
    rating = models.IntegerField('Оценка', choices=[(i, i) for i in range(1, 6)])
    comment = models.TextField('Комментарий')
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    
    class Meta:
        verbose_name = 'Отзыв'
        verbose_name_plural = 'Отзывы'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['boat', 'user'], name='unique_boat_user_review'),
        ]
    
    def __str__(self):
        return f"{self.boat.name} - {self.user.username} ({self.rating}★)"


class Offer(models.Model):
    """Коммерческое предложение для клиента"""
    
    OFFER_TYPE_CHOICES = [
        ('tourist', 'Туристический'),    # Красивый, упрощенный
        ('captain', 'Капитанский'),      # Детальный, вся информация
    ]

    BRANDING_MODE_CHOICES = [
        ('default', 'Стандартный брендинг'),
        ('no_branding', 'Без брендинга'),
        ('custom_branding', 'Кастомный брендинг (заглушка)'),
    ]
    
    # Идентификация
    uuid = models.UUIDField('UUID', default=uuid.uuid4, editable=False, unique=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_offers', verbose_name='Создал')
    
    # Тип оффера
    offer_type = models.CharField(
        'Тип оффера',
        max_length=20,
        choices=OFFER_TYPE_CHOICES,
        default='tourist',
        help_text='Туристический - красивый UI. Капитанский - детальная информация.'
    )

    # Режим брендинга
    branding_mode = models.CharField(
        'Режим брендинга',
        max_length=20,
        choices=BRANDING_MODE_CHOICES,
        default='default',
        help_text='Стандартный, без брендинга, или кастомный брендинг (заглушка)'
    )
    
    # Клиент
    client = models.ForeignKey(
        'Client', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='offers',
        verbose_name='Клиент'
    )

    # URL источника (используем TextField вместо URLField чтобы поддерживать длинные URLs с параметрами)
    source_url = models.TextField('URL источника', max_length=2000, help_text='URL лодки с boataround.com (включает параметры checkIn и checkOut)')
    
    # Даты
    check_in = models.DateField('Дата заезда')
    check_out = models.DateField('Дата выезда')
    
    # Информация о лодке (JSON)
    boat_data = models.JSONField('Данные лодки', default=dict)
    
    # Цены
    total_price = models.DecimalField('Итоговая цена', max_digits=10, decimal_places=2)
    original_price = models.DecimalField('Оригинальная цена', max_digits=10, decimal_places=2, null=True, blank=True)
    discount = models.DecimalField('Скидка', max_digits=10, decimal_places=2, default=0)
    currency = models.CharField('Валюта', max_length=3, default='EUR')
    price_adjustment = models.DecimalField(
        'Корректировка цены', max_digits=10, decimal_places=2, default=0,
        help_text='Положительное значение — наценка, отрицательное — скидка'
    )

    # Дополнительная информация
    title = models.CharField('Заголовок', max_length=300, blank=True)
    description = models.TextField('Описание', blank=True)
    notes = models.TextField('Заметки', blank=True, help_text='Внутренние заметки, не видны клиенту')
    
    # 5 составляющих базовой цены (для туристического оффера)
    price_captain = models.DecimalField('Капитан', max_digits=10, decimal_places=2, default=0)
    price_fuel = models.DecimalField('Топливо', max_digits=10, decimal_places=2, default=0)
    price_moorings = models.DecimalField('Стоянки', max_digits=10, decimal_places=2, default=0)
    price_transit_cleaning = models.DecimalField('Транзит лог и клининг', max_digits=10, decimal_places=2, default=0)
    price_trips_markup = models.DecimalField('Наценка Трипс', max_digits=10, decimal_places=2, default=0)

    # Дополнительные услуги (для туристического оффера)
    has_meal = models.BooleanField('Включено питание', default=False, help_text='Только для туристических офферов')
    
    # Настройки отображения
    show_countdown = models.BooleanField('Показать таймер', default=True)
    notifications = models.JSONField('Уведомления', default=list, blank=True)
    
    # Метаданные
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    expires_at = models.DateTimeField('Действителен до', null=True, blank=True)
    
    # Статистика
    views_count = models.IntegerField('Просмотров', default=0)
    is_active = models.BooleanField('Активен', default=True)
    
    class Meta:
        verbose_name = 'Оффер'
        verbose_name_plural = 'Офферы'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['uuid']),
            models.Index(fields=['offer_type']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"[{self.get_offer_type_display()}] {self.uuid} - {self.title or self.boat_data.get('boat_info', {}).get('title', 'Без названия')}"
    
    def is_tourist_offer(self):
        """Туристический оффер"""
        return self.offer_type == 'tourist'
    
    def is_captain_offer(self):
        """Капитанский оффер"""
        return self.offer_type == 'captain'
    
    def get_template_name(self):
        """Возвращает имя шаблона в зависимости от типа"""
        if self.is_captain_offer():
            return 'boats/offer_captain.html'
        return 'boats/offer_tourist.html'
    
    def get_absolute_url(self):
        return reverse('offer_view', kwargs={'uuid': self.uuid})
    
    def get_short_url(self):
        """Возвращает короткую ссылку"""
        from django.contrib.sites.models import Site
        domain = Site.objects.get_current().domain
        return f"https://{domain}/offer/{self.uuid}/"
    
    def increment_views(self):
        """Увеличивает счетчик просмотров"""
        self.views_count += 1
        self.save(update_fields=['views_count'])


class ParsedBoat(models.Model):
    """Основная информация о лодке с boataround.com"""
    
    # Идентификация
    boat_id = models.CharField('ID лодки', max_length=100, unique=True, db_index=True)
    slug = models.CharField('Slug', max_length=200, db_index=True, unique=True)
    source_url = models.URLField('URL источника', max_length=500, blank=True)
    
    # Чартерная компания
    charter = models.ForeignKey(
        Charter, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='boats',
        verbose_name='Чартерная компания'
    )
    
    # Базовая информация
    manufacturer = models.CharField('Производитель', max_length=100, blank=True)
    model = models.CharField('Модель', max_length=100, blank=True)
    year = models.IntegerField('Год выпуска', null=True, blank=True)
    
    # Кэшированные данные парсинга
    boat_data = models.JSONField('Кэшированные данные', default=dict, blank=True)
    
    # Метаданные
    last_parsed = models.DateTimeField('Последний парсинг', auto_now=True)
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    
    # Превью на CDN (для быстрой загрузки в поиске)
    preview_cdn_url = models.URLField('Превью на CDN', max_length=500, blank=True, default='')

    # Статистика
    parse_count = models.IntegerField('Раз парсили', default=1)
    last_parse_success = models.BooleanField('Последний парсинг успешен', default=True)

    # Данные из API (поиск)
    category = models.CharField('Категория', max_length=100, blank=True, default='')
    category_slug = models.CharField('Slug категории', max_length=100, blank=True, default='', db_index=True)
    flag = models.CharField('Флаг страны', max_length=10, blank=True, default='')
    reviews_score = models.FloatField('Рейтинг', null=True, blank=True)
    total_reviews = models.IntegerField('Всего отзывов', null=True, blank=True)
    latitude = models.FloatField('Широта', null=True, blank=True)
    longitude = models.FloatField('Долгота', null=True, blank=True)
    prepayment = models.IntegerField('Предоплата (%)', null=True, blank=True)
    sail = models.CharField('Парус', max_length=200, blank=True, default='')
    newboat = models.BooleanField('Новая лодка', default=False)
    usp = models.JSONField('USP (уникальные преимущества)', default=list, blank=True)

    class Meta:
        verbose_name = 'Лодка (базовая информация)'
        verbose_name_plural = 'Лодки (базовая информация)'
        ordering = ['-last_parsed']
        indexes = [
            models.Index(fields=['boat_id']),
            models.Index(fields=['slug']),
            models.Index(fields=['last_parsed']),
            models.Index(fields=['category_slug']),
        ]
    
    def __str__(self):
        return f"{self.manufacturer} {self.model} ({self.boat_id})"


class BoatTechnicalSpecs(models.Model):
    """Технические параметры лодки (для фильтрации)"""
    
    boat = models.OneToOneField(ParsedBoat, on_delete=models.CASCADE, related_name='technical_specs')
    
    # Размеры и параметры (индексированы для быстрого поиска)
    length = models.FloatField('Длина (м)', null=True, blank=True, db_index=True)
    beam = models.FloatField('Ширина (м)', null=True, blank=True)
    draft = models.FloatField('Осадка (м)', null=True, blank=True)
    
    # Вместимость (индексированы)
    cabins = models.IntegerField('Кабины', null=True, blank=True, db_index=True)
    berths = models.IntegerField('Спальных мест (max)', null=True, blank=True, db_index=True)
    toilets = models.IntegerField('Туалеты', null=True, blank=True, db_index=True)
    
    # Емкости
    fuel_capacity = models.IntegerField('Топливо (л)', null=True, blank=True)
    water_capacity = models.IntegerField('Вода (л)', null=True, blank=True)
    waste_capacity = models.IntegerField('Сточные воды (л)', null=True, blank=True)
    
    # Двигатель
    max_speed = models.FloatField('Макс скорость (узлы)', null=True, blank=True)
    engine_power = models.IntegerField('Мощность (л.с.)', null=True, blank=True)
    number_engines = models.IntegerField('Количество двигателей', null=True, blank=True)
    engine_type = models.CharField('Тип двигателя', max_length=50, blank=True)
    fuel_type = models.CharField('Тип топлива', max_length=50, blank=True)
    
    # Другое
    renovated_year = models.IntegerField('Год ремонта', null=True, blank=True)
    sail_renovated_year = models.IntegerField('Год ремонта парусов', null=True, blank=True)

    # Разбивка кают (из API)
    allowed_people = models.IntegerField('Разрешено гостей', null=True, blank=True)
    single_cabins = models.IntegerField('Одноместные каюты', null=True, blank=True)
    double_cabins = models.IntegerField('Двухместные каюты', null=True, blank=True)
    triple_cabins = models.IntegerField('Трёхместные каюты', null=True, blank=True)
    quadruple_cabins = models.IntegerField('Четырёхместные каюты', null=True, blank=True)
    cabins_with_bunk_bed = models.IntegerField('Каюты с двухъярус. кроватью', null=True, blank=True)
    saloon_sleeps = models.IntegerField('Спальных мест в салоне', null=True, blank=True)
    crew_sleeps = models.IntegerField('Спальных мест экипажа', null=True, blank=True)
    total_engine_power = models.IntegerField('Суммарная мощность (л.с.)', null=True, blank=True)
    cruising_consumption = models.FloatField('Расход на крейс. скорости', null=True, blank=True)
    
    class Meta:
        verbose_name = 'Технические параметры'
        verbose_name_plural = 'Технические параметры'
    
    def __str__(self):
        return f"{self.boat} - {self.length}м, {self.cabins} кабин"


class BoatDescription(models.Model):
    """Описание лодки на разных языках"""
    
    LANGUAGE_CHOICES = [
        ('ru_RU', 'Русский'),
        ('en_EN', 'English'),
        ('en_US', 'English (US)'),
        ('en_GB', 'English (UK)'),
        ('es_ES', 'Español'),
        ('de_DE', 'Deutsch'),
        ('fr_FR', 'Français'),
        ('it_IT', 'Italiano'),
        ('pt_PT', 'Português'),
        ('nl_NL', 'Nederlands'),
        ('pl_PL', 'Polski'),
        ('tr_TR', 'Türkçe'),
    ]
    
    boat = models.ForeignKey(ParsedBoat, on_delete=models.CASCADE, related_name='descriptions')
    language = models.CharField('Язык', max_length=10, choices=LANGUAGE_CHOICES)
    
    title = models.CharField('Название', max_length=300)
    description = models.TextField('Описание')
    location = models.CharField('Локация', max_length=200, blank=True)
    marina = models.CharField('Марина', max_length=200, blank=True)
    country = models.CharField('Страна', max_length=100, blank=True)
    region = models.CharField('Регион/Область', max_length=100, blank=True)
    city = models.CharField('Город', max_length=100, blank=True)
    
    class Meta:
        verbose_name = 'Описание'
        verbose_name_plural = 'Описания'
        indexes = [
            models.Index(fields=['boat', 'language']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['boat', 'language'], name='unique_boat_description_language'),
        ]
    
    def __str__(self):
        return f"{self.boat} - {self.get_language_display()}"


class BoatPrice(models.Model):
    """Цены лодки в разных валютах"""
    
    CURRENCY_CHOICES = [
        ('EUR', '€ EUR'),
        ('USD', '$ USD'),
        ('GBP', '£ GBP'),
        ('RUB', '₽ RUB'),
        ('TRY', '₺ TRY'),
        ('CZK', 'Kč CZK'),
        ('PLN', 'zł PLN'),
        ('SEK', 'kr SEK'),
        ('NOK', 'kr NOK'),
        ('DKK', 'kr DKK'),
    ]
    
    boat = models.ForeignKey(ParsedBoat, on_delete=models.CASCADE, related_name='prices')
    currency = models.CharField('Валюта', max_length=3, choices=CURRENCY_CHOICES)
    
    price_per_day = models.DecimalField('Цена/день', max_digits=12, decimal_places=2)
    price_per_week = models.DecimalField('Цена/неделя', max_digits=12, decimal_places=2, null=True, blank=True)
    
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    
    class Meta:
        verbose_name = 'Цена'
        verbose_name_plural = 'Цены'
        indexes = [
            models.Index(fields=['boat', 'currency']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['boat', 'currency'], name='unique_boat_price_currency'),
        ]
    
    def __str__(self):
        return f"{self.boat} - {self.price_per_day} {self.currency}"


class BoatGallery(models.Model):
    """Галерея фото лодки"""
    
    boat = models.ForeignKey(ParsedBoat, on_delete=models.CASCADE, related_name='gallery')
    
    cdn_url = models.URLField('URL фото на CDN', max_length=500)
    order = models.IntegerField('Порядок', default=0)
    
    class Meta:
        verbose_name = 'Фото'
        verbose_name_plural = 'Фото'
        ordering = ['order']
        indexes = [
            models.Index(fields=['boat', 'order']),
        ]
    
    def __str__(self):
        return f"{self.boat} - Photo #{self.order}"


class BoatDetails(models.Model):
    """Доп. детали лодки (extras, adds, not_included) на разных языках"""
    
    LANGUAGE_CHOICES = [
        ('ru_RU', 'Русский'),
        ('en_EN', 'English'),
        ('en_US', 'English (US)'),
        ('en_GB', 'English (UK)'),
        ('es_ES', 'Español'),
        ('de_DE', 'Deutsch'),
        ('fr_FR', 'Français'),
        ('it_IT', 'Italiano'),
        ('pt_PT', 'Português'),
        ('nl_NL', 'Nederlands'),
        ('pl_PL', 'Polski'),
        ('tr_TR', 'Türkçe'),
    ]
    
    boat = models.ForeignKey(ParsedBoat, on_delete=models.CASCADE, related_name='details')
    language = models.CharField('Язык', max_length=10, choices=LANGUAGE_CHOICES)
    
    # JSON поля с деталями
    extras = models.JSONField('Опции (extras)', default=list)
    additional_services = models.JSONField('Доп. услуги', default=list)
    delivery_extras = models.JSONField('Опции доставки', default=list)
    not_included = models.JSONField('Не включено в цену', default=list)
    
    # Оборудование из API filter (multi-language support)
    cockpit = models.JSONField('Оборудование кокпита', default=list)
    entertainment = models.JSONField('Развлечения', default=list)
    equipment = models.JSONField('Оборудование', default=list)
    
    class Meta:
        verbose_name = 'Доп. детали'
        verbose_name_plural = 'Доп. детали'
        indexes = [
            models.Index(fields=['boat', 'language']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['boat', 'language'], name='unique_boat_details_language'),
        ]
    
    def __str__(self):
        return f"{self.boat} - {self.get_language_display()} (details)"


class PriceSettings(models.Model):
    """Глобальные настройки цен — синглтон (pk=1)."""

    # ---- Общие (поисковик + агентский оффер) --------------------------------
    extra_discount_max = models.IntegerField(
        'Макс. доп. скидка (%)',
        default=5,
        help_text='Условная доп. скидка при additional_discount < commission чартера',
    )
    agent_commission_pct = models.IntegerField(
        'Комиссия агента (% от комиссии чартера)',
        default=50,
        help_text='Доля агента от комиссии чартера. 50 = агент получает половину комиссии.',
    )

    # ---- Туристический оффер ------------------------------------------------
    tourist_turkey_base = models.DecimalField(
        'Базовая цена Турция (EUR) (deprecated)', max_digits=8, decimal_places=2, default=Decimal('4400.00'),
    )
    tourist_seychelles_base = models.DecimalField(
        'Базовая цена Сейшелы (EUR) (deprecated)', max_digits=8, decimal_places=2, default=Decimal('4500.00'),
    )
    tourist_default_base = models.DecimalField(
        'Базовая цена по умолчанию (EUR) (deprecated)', max_digits=8, decimal_places=2, default=Decimal('4500.00'),
    )

    # ---- 5 составляющих базовой цены (заменяют tourist_*_base) ----
    # Турция
    tourist_captain_turkey = models.DecimalField(
        'Капитан Турция (EUR)', max_digits=8, decimal_places=2, default=Decimal('880.00'),
    )
    tourist_fuel_turkey = models.DecimalField(
        'Топливо Турция (EUR)', max_digits=8, decimal_places=2, default=Decimal('880.00'),
    )
    tourist_moorings_turkey = models.DecimalField(
        'Стоянки Турция (EUR)', max_digits=8, decimal_places=2, default=Decimal('880.00'),
    )
    tourist_transit_cleaning_turkey = models.DecimalField(
        'Транзит лог и клининг Турция (EUR)', max_digits=8, decimal_places=2, default=Decimal('880.00'),
    )
    tourist_trips_markup_turkey = models.DecimalField(
        'Наценка Трипс Турция (EUR)', max_digits=8, decimal_places=2, default=Decimal('880.00'),
    )
    # Сейшелы
    tourist_captain_seychelles = models.DecimalField(
        'Капитан Сейшелы (EUR)', max_digits=8, decimal_places=2, default=Decimal('900.00'),
    )
    tourist_fuel_seychelles = models.DecimalField(
        'Топливо Сейшелы (EUR)', max_digits=8, decimal_places=2, default=Decimal('900.00'),
    )
    tourist_moorings_seychelles = models.DecimalField(
        'Стоянки Сейшелы (EUR)', max_digits=8, decimal_places=2, default=Decimal('900.00'),
    )
    tourist_transit_cleaning_seychelles = models.DecimalField(
        'Транзит лог и клининг Сейшелы (EUR)', max_digits=8, decimal_places=2, default=Decimal('900.00'),
    )
    tourist_trips_markup_seychelles = models.DecimalField(
        'Наценка Трипс Сейшелы (EUR)', max_digits=8, decimal_places=2, default=Decimal('900.00'),
    )
    # По умолчанию
    tourist_captain_default = models.DecimalField(
        'Капитан по умолчанию (EUR)', max_digits=8, decimal_places=2, default=Decimal('900.00'),
    )
    tourist_fuel_default = models.DecimalField(
        'Топливо по умолчанию (EUR)', max_digits=8, decimal_places=2, default=Decimal('900.00'),
    )
    tourist_moorings_default = models.DecimalField(
        'Стоянки по умолчанию (EUR)', max_digits=8, decimal_places=2, default=Decimal('900.00'),
    )
    tourist_transit_cleaning_default = models.DecimalField(
        'Транзит лог и клининг по умолчанию (EUR)', max_digits=8, decimal_places=2, default=Decimal('900.00'),
    )
    tourist_trips_markup_default = models.DecimalField(
        'Наценка Трипс по умолчанию (EUR)', max_digits=8, decimal_places=2, default=Decimal('900.00'),
    )
    tourist_praslin_extra = models.DecimalField(
        'Надбавка за Praslin Marina (EUR)', max_digits=8, decimal_places=2, default=Decimal('400.00'),
    )
    # ---- Страхование (per-region) ----
    tourist_insurance_rate_turkey = models.DecimalField(
        'Ставка страхования Турция', max_digits=6, decimal_places=4, default=Decimal('0.1000'),
    )
    tourist_insurance_rate_seychelles = models.DecimalField(
        'Ставка страхования Сейшелы', max_digits=6, decimal_places=4, default=Decimal('0.1000'),
    )
    tourist_insurance_rate_default = models.DecimalField(
        'Ставка страхования по умолчанию', max_digits=6, decimal_places=4, default=Decimal('0.1000'),
    )
    tourist_insurance_min_turkey = models.DecimalField(
        'Мин. страховка Турция (EUR)', max_digits=8, decimal_places=2, default=Decimal('400.00'),
    )
    tourist_insurance_min_seychelles = models.DecimalField(
        'Мин. страховка Сейшелы (EUR)', max_digits=8, decimal_places=2, default=Decimal('400.00'),
    )
    tourist_insurance_min_default = models.DecimalField(
        'Мин. страховка по умолчанию (EUR)', max_digits=8, decimal_places=2, default=Decimal('400.00'),
    )
    # ---- Повар (per-region) ----
    tourist_cook_price_turkey = models.DecimalField(
        'Повар Турция (EUR)', max_digits=8, decimal_places=2, default=Decimal('1400.00'),
    )
    tourist_cook_price_seychelles = models.DecimalField(
        'Повар Сейшелы (EUR)', max_digits=8, decimal_places=2, default=Decimal('1400.00'),
    )
    tourist_cook_price_default = models.DecimalField(
        'Повар по умолчанию (EUR)', max_digits=8, decimal_places=2, default=Decimal('1400.00'),
    )
    # ---- Питание (per-region, уже были) ----
    tourist_turkey_dish_base = models.DecimalField(
        'Питание Турция EUR/чел', max_digits=8, decimal_places=2, default=Decimal('150.00'),
    )
    tourist_seychelles_dish_base = models.DecimalField(
        'Питание Сейшелы EUR/чел', max_digits=8, decimal_places=2, default=Decimal('210.00'),
    )
    tourist_default_dish_base = models.DecimalField(
        'Питание по умолчанию EUR/чел', max_digits=8, decimal_places=2, default=Decimal('210.00'),
    )
    # ---- Надбавки (per-region) ----
    tourist_length_extra_turkey = models.DecimalField(
        'Надбавка длина >14.2 м Турция (EUR)', max_digits=8, decimal_places=2, default=Decimal('200.00'),
    )
    tourist_length_extra_seychelles = models.DecimalField(
        'Надбавка длина >14.2 м Сейшелы (EUR)', max_digits=8, decimal_places=2, default=Decimal('200.00'),
    )
    tourist_length_extra_default = models.DecimalField(
        'Надбавка длина >14.2 м по умолчанию (EUR)', max_digits=8, decimal_places=2, default=Decimal('200.00'),
    )
    tourist_catamaran_length_extra_turkey = models.DecimalField(
        'Надбавка катамаран >13.8 м Турция (EUR)', max_digits=8, decimal_places=2, default=Decimal('500.00'),
    )
    tourist_catamaran_length_extra_seychelles = models.DecimalField(
        'Надбавка катамаран >13.8 м Сейшелы (EUR)', max_digits=8, decimal_places=2, default=Decimal('500.00'),
    )
    tourist_catamaran_length_extra_default = models.DecimalField(
        'Надбавка катамаран >13.8 м по умолчанию (EUR)', max_digits=8, decimal_places=2, default=Decimal('500.00'),
    )
    tourist_sailing_length_extra_turkey = models.DecimalField(
        'Надбавка парусная >13.8 м Турция (EUR)', max_digits=8, decimal_places=2, default=Decimal('300.00'),
    )
    tourist_sailing_length_extra_seychelles = models.DecimalField(
        'Надбавка парусная >13.8 м Сейшелы (EUR)', max_digits=8, decimal_places=2, default=Decimal('300.00'),
    )
    tourist_sailing_length_extra_default = models.DecimalField(
        'Надбавка парусная >13.8 м по умолчанию (EUR)', max_digits=8, decimal_places=2, default=Decimal('300.00'),
    )
    tourist_double_cabin_extra_turkey = models.DecimalField(
        'Доп. двойная каюта Турция (EUR)', max_digits=8, decimal_places=2, default=Decimal('180.00'),
    )
    tourist_double_cabin_extra_seychelles = models.DecimalField(
        'Доп. двойная каюта Сейшелы (EUR)', max_digits=8, decimal_places=2, default=Decimal('180.00'),
    )
    tourist_double_cabin_extra_default = models.DecimalField(
        'Доп. двойная каюта по умолчанию (EUR)', max_digits=8, decimal_places=2, default=Decimal('180.00'),
    )
    tourist_max_double_cabins_free_turkey = models.IntegerField(
        'Бесплатных двойных кают Турция', default=4,
    )
    tourist_max_double_cabins_free_seychelles = models.IntegerField(
        'Бесплатных двойных кают Сейшелы', default=4,
    )
    tourist_max_double_cabins_free_default = models.IntegerField(
        'Бесплатных двойных кают по умолчанию', default=4,
    )

    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Настройки цен'
        verbose_name_plural = 'Настройки цен'

    def __str__(self):
        return 'Настройки цен'

    def save(self, *args, **kwargs):
        self.pk = 1
        # Prevent IntegrityError when called via objects.create() (which passes force_insert=True)
        kwargs.pop('force_insert', None)
        self._state.adding = not type(self).objects.filter(pk=1).exists()
        super().save(*args, **kwargs)
        self._flush_pricing_caches()

    @staticmethod
    def _flush_pricing_caches():
        """Clear settings cache and search price consensus keys."""
        from django.core.cache import cache
        cache.delete('price_settings')
        try:
            redis_client = cache._cache.get_client()
            prefix = ':1:search_price_consensus:*'
            for key in redis_client.scan_iter(match=prefix, count=500):
                redis_client.delete(key)
        except Exception:
            pass

    @classmethod
    def get_settings(cls):
        """Получить настройки из кэша (5 мин) или БД."""
        from django.core.cache import cache
        settings = cache.get('price_settings')
        if settings is None:
            settings, _ = cls.objects.prefetch_related('country_configs').get_or_create(pk=1)
            cache.set('price_settings', settings, 300)
        return settings


# ---------- Pricing fields common to every country ----------
COUNTRY_PRICE_FIELDS = [
    # (field_name, verbose_label, field_type)
    ('captain', 'Капитан (EUR)', 'decimal'),
    ('fuel', 'Топливо (EUR)', 'decimal'),
    ('moorings', 'Стоянки (EUR)', 'decimal'),
    ('transit_cleaning', 'Транзит лог и клининг (EUR)', 'decimal'),
    ('trips_markup', 'Наценка Трипс (EUR)', 'decimal'),
    ('insurance_rate', 'Ставка страхования', 'decimal'),
    ('insurance_min', 'Мин. страховка (EUR)', 'decimal'),
    ('dish_base', 'Питание EUR/чел', 'decimal'),
    ('cook_price', 'Повар (EUR)', 'decimal'),
    ('length_extra', 'Длина >14.2 м (EUR)', 'decimal'),
    ('catamaran_length_extra', 'Катамаран >13.8 м (EUR)', 'decimal'),
    ('sailing_length_extra', 'Парусная >13.8 м (EUR)', 'decimal'),
    ('double_cabin_extra', 'Доп. двойная каюта (EUR)', 'decimal'),
    ('max_double_cabins_free', 'Бесплатных двойных кают', 'int'),
    ('praslin_extra', 'Марина Praslin (EUR)', 'decimal'),
]


class CountryPriceConfig(models.Model):
    """Per-country pricing config for tourist offers."""

    price_settings = models.ForeignKey(
        PriceSettings, on_delete=models.CASCADE, related_name='country_configs',
    )
    country_name = models.CharField('Название', max_length=100)
    country_code = models.SlugField('Код (slug)', max_length=60, unique=True)
    match_names = models.TextField(
        'Алиасы для матчинга',
        blank=True, default='',
        help_text='Через запятую: turkey, турция',
    )
    is_default = models.BooleanField('Профиль по умолчанию', default=False)
    sort_order = models.IntegerField('Порядок', default=0)

    # ---- pricing fields ----
    captain = models.DecimalField('Капитан (EUR)', max_digits=8, decimal_places=2, default=Decimal('900.00'))
    fuel = models.DecimalField('Топливо (EUR)', max_digits=8, decimal_places=2, default=Decimal('900.00'))
    moorings = models.DecimalField('Стоянки (EUR)', max_digits=8, decimal_places=2, default=Decimal('900.00'))
    transit_cleaning = models.DecimalField('Транзит лог и клининг (EUR)', max_digits=8, decimal_places=2, default=Decimal('900.00'))
    trips_markup = models.DecimalField('Наценка Трипс (EUR)', max_digits=8, decimal_places=2, default=Decimal('900.00'))
    insurance_rate = models.DecimalField('Ставка страхования', max_digits=6, decimal_places=4, default=Decimal('0.1000'))
    insurance_min = models.DecimalField('Мин. страховка (EUR)', max_digits=8, decimal_places=2, default=Decimal('400.00'))
    dish_base = models.DecimalField('Питание EUR/чел', max_digits=8, decimal_places=2, default=Decimal('210.00'))
    cook_price = models.DecimalField('Повар (EUR)', max_digits=8, decimal_places=2, default=Decimal('1400.00'))
    length_extra = models.DecimalField('Длина >14.2 м (EUR)', max_digits=8, decimal_places=2, default=Decimal('200.00'))
    catamaran_length_extra = models.DecimalField('Катамаран >13.8 м (EUR)', max_digits=8, decimal_places=2, default=Decimal('500.00'))
    sailing_length_extra = models.DecimalField('Парусная >13.8 м (EUR)', max_digits=8, decimal_places=2, default=Decimal('300.00'))
    double_cabin_extra = models.DecimalField('Доп. двойная каюта (EUR)', max_digits=8, decimal_places=2, default=Decimal('180.00'))
    max_double_cabins_free = models.IntegerField('Бесплатных двойных кают', default=4)
    praslin_extra = models.DecimalField('Марина Praslin (EUR)', max_digits=8, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        verbose_name = 'Ценовой профиль страны'
        verbose_name_plural = 'Ценовые профили стран'
        ordering = ['sort_order', 'country_name']

    def __str__(self):
        default_tag = ' (по умолч.)' if self.is_default else ''
        return f'{self.country_name}{default_tag}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        PriceSettings._flush_pricing_caches()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        PriceSettings._flush_pricing_caches()

    def get_match_list(self):
        """Return lowered alias list for country matching."""
        return [a.strip().lower() for a in self.match_names.split(',') if a.strip()]


class ContractTemplate(models.Model):
    """Шаблон договора (агентский, капитанский и т.д.)"""

    CONTRACT_TYPE_CHOICES = [
        ('agent_rental', 'Агентский договор аренды'),
        ('captain_services', 'Договор капитанских услуг'),
    ]

    name = models.CharField('Название', max_length=200)
    contract_type = models.CharField('Тип договора', max_length=30, choices=CONTRACT_TYPE_CHOICES, unique=True)
    template_content = models.TextField('Содержимое шаблона', help_text='Django template markup для генерации PDF')
    is_active = models.BooleanField('Активен', default=True)
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Шаблон договора'
        verbose_name_plural = 'Шаблоны договоров'

    def __str__(self):
        return f"{self.name} ({self.get_contract_type_display()})"


class Contract(models.Model):
    """Экземпляр договора с возможностью онлайн-подписания"""

    STATUS_CHOICES = [
        ('draft', 'Черновик'),
        ('sent', 'Отправлен'),
        ('viewed', 'Просмотрен'),
        ('signed', 'Подписан'),
        ('rejected', 'Отклонён'),
        ('expired', 'Истёк'),
    ]

    # Идентификация
    uuid = models.UUIDField('UUID', default=uuid.uuid4, editable=False, unique=True)
    contract_number = models.CharField('Номер договора', max_length=50, unique=True)

    # Связи
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='contracts', verbose_name='Бронирование')
    offer = models.ForeignKey(Offer, on_delete=models.SET_NULL, null=True, blank=True, related_name='contracts', verbose_name='Оффер')
    template = models.ForeignKey(ContractTemplate, on_delete=models.PROTECT, verbose_name='Шаблон')

    # Стороны договора
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_contracts', verbose_name='Создатель (агент)')
    signer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='contracts_to_sign', verbose_name='Подписант (клиент)')
    client = models.ForeignKey(
        'Client', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='contracts',
        verbose_name='Клиент'
    )

    # Данные договора (snapshot)
    contract_data = models.JSONField('Данные договора', default=dict, help_text='ФИО, паспорт, условия и т.д.')

    # Документы
    document_file = models.FileField('PDF документ', upload_to='contracts/documents/', blank=True)
    signed_file = models.FileField('Подписанный PDF', upload_to='contracts/signed/', blank=True)

    # Статус
    status = models.CharField('Статус', max_length=20, choices=STATUS_CHOICES, default='draft')

    # Подписание
    signature_data = models.TextField('Данные подписи (base64)', blank=True)
    signed_at = models.DateTimeField('Дата подписания', null=True, blank=True)

    # Аудит-лог подписания
    sign_ip = models.GenericIPAddressField('IP подписания', null=True, blank=True)
    sign_user_agent = models.TextField('User-Agent подписания', blank=True)
    document_hash = models.CharField('SHA-256 хэш документа', max_length=64, blank=True)

    # Токен для подписания без авторизации
    sign_token = models.UUIDField('Токен подписания', default=_uuid4, unique=True)
    expires_at = models.DateTimeField('Действителен до')

    # Метаданные
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Договор'
        verbose_name_plural = 'Договоры'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['uuid']),
            models.Index(fields=['sign_token']),
            models.Index(fields=['status']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f"Договор {self.contract_number} — {self.get_status_display()}"

    def get_absolute_url(self):
        return reverse('contract_detail', kwargs={'uuid': self.uuid})

    @staticmethod
    def generate_contract_number():
        """Генерирует номер договора: AG-{year}-{seq:05d}"""
        import datetime
        year = datetime.date.today().year
        last = Contract.objects.filter(
            contract_number__startswith=f'AG-{year}-'
        ).order_by('-contract_number').first()
        if last:
            try:
                seq = int(last.contract_number.split('-')[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1
        return f'AG-{year}-{seq:05d}'

    def is_expired(self):
        from django.utils import timezone
        return self.expires_at and self.expires_at < timezone.now()

    def can_be_signed(self):
        return self.status in ('sent', 'viewed') and not self.is_expired()


class ContractOTP(models.Model):
    """Одноразовый код для подписания договора"""

    DELIVERY_CHOICES = [
        ('sms', 'SMS'),
    ]

    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='otp_codes')
    code = models.CharField('Код', max_length=6)
    phone = models.CharField('Телефон', max_length=30)
    delivery_method = models.CharField('Способ доставки', max_length=20, choices=DELIVERY_CHOICES, default='sms')
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    expires_at = models.DateTimeField('Истекает')
    attempts = models.PositiveIntegerField('Попытки ввода', default=0)
    is_verified = models.BooleanField('Подтверждён', default=False)

    MAX_ATTEMPTS = 5
    CODE_LIFETIME_SECONDS = 300  # 5 минут

    class Meta:
        verbose_name = 'OTP код договора'
        verbose_name_plural = 'OTP коды договоров'
        ordering = ['-created_at']

    def __str__(self):
        return f"OTP {self.code} для {self.contract.contract_number}"

    def is_expired(self):
        from django.utils import timezone
        return self.expires_at < timezone.now()

    def is_valid(self):
        return not self.is_expired() and not self.is_verified and self.attempts < self.MAX_ATTEMPTS

    @classmethod
    def generate_code(cls):
        import random
        return f'{random.randint(100000, 999999)}'

    @classmethod
    def create_for_contract(cls, contract, phone, delivery_method='sms'):
        from django.utils import timezone
        from datetime import timedelta
        # Деактивируем предыдущие неиспользованные коды
        cls.objects.filter(contract=contract, is_verified=False).update(
            expires_at=timezone.now()
        )
        return cls.objects.create(
            contract=contract,
            code=cls.generate_code(),
            phone=phone,
            delivery_method=delivery_method,
            expires_at=timezone.now() + timedelta(seconds=cls.CODE_LIFETIME_SECONDS),
        )


class ParseJob(models.Model):
    """Задание на парсинг лодок. Хранит параметры запуска и отчёт о выполнении."""

    MODE_CHOICES = [
        ('api', 'Только API-метаданные'),
        ('html', 'Только HTML-парсинг'),
        ('full', 'Полный (API + HTML)'),
    ]

    STATUS_CHOICES = [
        ('pending', 'В очереди'),
        ('collecting', 'Сбор slug\'ов'),
        ('running', 'Выполняется'),
        ('completed', 'Завершено'),
        ('failed', 'Ошибка'),
        ('partial', 'Частично'),
        ('cancelled', 'Отменено'),
    ]

    # Идентификация
    job_id = models.UUIDField('ID задания', default=_uuid4, editable=False, unique=True)

    # Параметры запуска
    mode = models.CharField('Режим', max_length=10, choices=MODE_CHOICES, default='full')
    destination = models.CharField('Направление', max_length=100, blank=True, default='')
    max_pages = models.IntegerField('Макс. страниц', null=True, blank=True)
    batch_size = models.IntegerField('Размер батча', default=50)
    skip_existing = models.BooleanField('Пропускать существующие', default=False)

    # Статус
    status = models.CharField('Статус', max_length=20, choices=STATUS_CHOICES, default='pending')
    celery_task_id = models.CharField('Celery Task ID', max_length=255, blank=True, default='')

    # Счётчики (обновляются атомарно из Celery-задач)
    total_slugs = models.IntegerField('Всего slug\'ов', default=0)
    total_batches = models.IntegerField('Всего батчей', default=0)
    batches_done = models.IntegerField('Батчей выполнено', default=0)
    processed = models.IntegerField('Обработано', default=0)
    success = models.IntegerField('Успешно', default=0)
    failed = models.IntegerField('Ошибки', default=0)
    skipped = models.IntegerField('Пропущено', default=0)

    # Отчёты
    errors = models.JSONField('Список ошибок', default=list, blank=True)
    summary = models.TextField('Краткий отчёт', blank=True, default='')
    detailed_log = models.TextField('Подробный лог', blank=True, default='')

    # Метаданные
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='parse_jobs', verbose_name='Кто запустил',
    )
    started_at = models.DateTimeField('Начало', null=True, blank=True)
    finished_at = models.DateTimeField('Завершение', null=True, blank=True)
    created_at = models.DateTimeField('Создано', auto_now_add=True)

    class Meta:
        verbose_name = 'Задание парсинга'
        verbose_name_plural = 'Задания парсинга'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['job_id']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f"[{self.get_mode_display()}] {self.job_id} — {self.get_status_display()}"

    @property
    def progress_pct(self):
        if self.total_slugs == 0:
            return 0
        return round(self.processed * 100 / self.total_slugs, 1)

    @property
    def duration_seconds(self):
        if not self.started_at:
            return None
        end = self.finished_at or __import__('django').utils.timezone.now()
        return (end - self.started_at).total_seconds()

    def append_log(self, line: str):
        """Добавляет строку в detailed_log (без перезагрузки объекта)."""
        from django.utils import timezone
        ts = timezone.now().strftime('%H:%M:%S')
        entry = f"[{ts}] {line}\n"
        ParseJob.objects.filter(pk=self.pk).update(
            detailed_log=models.functions.Concat(
                models.F('detailed_log'), models.Value(entry),
            )
        )

    def append_error(self, slug: str, error: str):
        """Добавляет ошибку в JSON-список errors атомарно."""
        from django.db.models import F
        from django.db.models.functions import JSONObject
        # Для PostgreSQL используем raw update, чтобы не перезаписать конкурентные ошибки.
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE boats_parsejob SET errors = errors || %s::jsonb WHERE id = %s",
                [__import__('json').dumps([{'slug': slug, 'error': error}]), self.pk],
            )
