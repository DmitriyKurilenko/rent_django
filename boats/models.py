from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
import uuid


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
        unique_together = ('user', 'boat_slug')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'boat_slug']),
            models.Index(fields=['user', 'created_at']),
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


class Booking(models.Model):
    """Бронирование лодки"""
    
    STATUS_CHOICES = [
        ('pending', 'Ожидает'),
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
    
    # Цена
    total_price = models.DecimalField('Итого', max_digits=10, decimal_places=2)
    currency = models.CharField('Валюта', max_length=3, default='EUR')
    
    # boat_data deprecated - используем связанные таблицы
    boat_data = models.JSONField('Данные лодки', default=dict)
    
    # Сообщение от туриста
    message = models.TextField('Сообщение', blank=True)
    
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
        """Первое изображение из галереи"""
        parsed_boat = self.get_parsed_boat()
        if parsed_boat:
            # Берем из BoatGallery
            first_photo = parsed_boat.gallery.first()
            if first_photo:
                return first_photo.cdn_url
        
        # Fallback на boat_data
        if self.boat_data:
            images = self.boat_data.get('images', [])
            if images:
                return images[0].get('thumb') or images[0].get('main_img')
        
        # Fallback на offer.boat_data
        if self.offer and self.offer.boat_data:
            images = self.offer.boat_data.get('images', [])
            if images:
                return images[0].get('thumb') or images[0].get('main_img')
        
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
        unique_together = ('boat', 'user')
        ordering = ['-created_at']
    
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
    
    # Дополнительная информация
    title = models.CharField('Заголовок', max_length=300, blank=True)
    description = models.TextField('Описание', blank=True)
    notes = models.TextField('Заметки', blank=True, help_text='Внутренние заметки, не видны клиенту')
    
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
    
    # Статистика
    parse_count = models.IntegerField('Раз парсили', default=1)
    last_parse_success = models.BooleanField('Последний парсинг успешен', default=True)
    
    class Meta:
        verbose_name = 'Лодка (базовая информация)'
        verbose_name_plural = 'Лодки (базовая информация)'
        ordering = ['-last_parsed']
        indexes = [
            models.Index(fields=['boat_id']),
            models.Index(fields=['slug']),
            models.Index(fields=['last_parsed']),
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
        unique_together = ('boat', 'language')
        indexes = [
            models.Index(fields=['boat', 'language']),
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
        unique_together = ('boat', 'currency')
        indexes = [
            models.Index(fields=['boat', 'currency']),
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
        unique_together = ('boat', 'language')
        indexes = [
            models.Index(fields=['boat', 'language']),
        ]
    
    def __str__(self):
        return f"{self.boat} - {self.get_language_display()} (details)"
