from django import forms
from .models import Boat, Booking, Review, Offer


class SearchForm(forms.Form):
    """Форма поиска лодок"""
    
    location = forms.CharField(
        required=False,
        label='Местоположение',
        widget=forms.TextInput(attrs={
            'placeholder': 'Сочи, Крым, Санкт-Петербург...'
        })
    )
    boat_type = forms.ChoiceField(
        required=False,
        label='Тип',
        choices=[('', 'Все типы')] + Boat.BOAT_TYPES
    )
    min_capacity = forms.IntegerField(
        required=False,
        label='Мин. вместимость',
        min_value=1,
        widget=forms.NumberInput(attrs={'placeholder': 'Чел.'})
    )
    max_price = forms.DecimalField(
        required=False,
        label='Макс. цена/день',
        min_value=0,
        widget=forms.NumberInput(attrs={'placeholder': '₽'})
    )


class BoatForm(forms.ModelForm):
    """Форма создания/редактирования лодки"""
    
    class Meta:
        model = Boat
        fields = [
            'name', 'boat_type', 'description', 'location',
            'capacity', 'length', 'year', 'price_per_day',
            'image', 'available', 'cabins', 'bathrooms', 'has_skipper'
        ]


class BookingForm(forms.ModelForm):
    """Форма бронирования"""
    
    class Meta:
        model = Booking
        fields = ['start_date', 'end_date', 'guests', 'message']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }
    
    def __init__(self, *args, boat=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.boat = boat
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        guests = cleaned_data.get('guests')
        
        if start_date and end_date:
            if end_date <= start_date:
                raise forms.ValidationError('Дата окончания должна быть позже даты начала')
            
            # Проверка доступности
            if self.boat:
                overlapping = Booking.objects.filter(
                    boat=self.boat,
                    status__in=['pending', 'confirmed']
                ).filter(
                    start_date__lte=end_date,
                    end_date__gte=start_date
                )
                if overlapping.exists():
                    raise forms.ValidationError('Лодка уже забронирована на эти даты')
        
        if self.boat and guests:
            if guests > self.boat.capacity:
                raise forms.ValidationError(f'Максимальная вместимость: {self.boat.capacity} чел.')
        
        return cleaned_data


class ReviewForm(forms.ModelForm):
    """Форма отзыва"""
    
    class Meta:
        model = Review
        fields = ['rating', 'comment']
        widgets = {
            'rating': forms.RadioSelect(choices=[(i, '★' * i) for i in range(1, 6)]),
        }


class OfferForm(forms.ModelForm):
    """Форма создания оффера"""
    
    # Override source_url с CharField вместо URLField
    source_url = forms.CharField(
        max_length=500,
        widget=forms.TextInput(attrs={
            'placeholder': 'https://www.boataround.com/ru/yachta/...?checkIn=...&checkOut=...'
        }),
        help_text='Вставьте полную ссылку с датами заезда и выезда',
        label='Ссылка с boataround.com'
    )
    
    class Meta:
        model = Offer
        fields = ['source_url', 'offer_type', 'branding_mode', 'check_in', 'check_out', 'title', 'show_countdown', 'notes', 'has_meal', 'price_adjustment']
        widgets = {
            'offer_type': forms.RadioSelect(),
            'branding_mode': forms.Select(),
            'check_in': forms.DateInput(attrs={
                'type': 'date',
                'placeholder': 'Дата заезда'
            }),
            'check_out': forms.DateInput(attrs={
                'type': 'date',
                'placeholder': 'Дата выезда'
            }),
            'title': forms.TextInput(attrs={
                'placeholder': 'Например: Роскошная яхта на Кипре'
            }),
            'notes': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'Внутренние заметки (не видны клиенту)'
            }),
            'price_adjustment': forms.NumberInput(attrs={
                'step': '0.01',
                'placeholder': '0.00',
            }),
        }
        labels = {
            'source_url': 'Ссылка с boataround.com',
            'offer_type': 'Тип оффера',
            'branding_mode': 'Брендинг страницы оффера',
            'check_in': 'Дата заезда',
            'check_out': 'Дата выезда',
            'title': 'Заголовок оффера',
            'show_countdown': 'Показать таймер обратного отсчета',
            'notes': 'Заметки (только для вас)',
            'has_meal': 'Включено питание (только для туристических офферов)',
            'price_adjustment': 'Корректировка цены (€)',
        }
        help_texts = {
            'source_url': 'Вставьте полную ссылку с датами заезда и выезда',
            'offer_type': 'Туристический - красивый UI для клиентов. Капитанский - детальная информация для агентов.',
            'branding_mode': 'Без брендинга скрывает шапку и подвал. Кастомный брендинг пока отображается как заглушка.',
            'check_in': 'Дата начала аренды',
            'check_out': 'Дата окончания аренды',
            'show_countdown': 'Таймер создает эффект срочности',
            'has_meal': 'При включении добавляется стоимость питания к базовой цене',
            'price_adjustment': 'Положительное — наценка, отрицательное — скидка',
        }
    
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Ограничиваем выбор типа оффера в зависимости от прав пользователя
        if user and hasattr(user, 'profile'):
            allowed_types = user.profile.get_allowed_offer_types()
            self.fields['offer_type'].choices = [
                choice for choice in Offer.OFFER_TYPE_CHOICES
                if choice[0] in allowed_types
            ]

            allowed_branding_modes = ['default']
            if user.profile.can_use_no_branding():
                allowed_branding_modes.append('no_branding')
            if user.profile.can_use_custom_branding():
                allowed_branding_modes.append('custom_branding')

            self.fields['branding_mode'].choices = [
                choice for choice in Offer.BRANDING_MODE_CHOICES
                if choice[0] in allowed_branding_modes
            ]
            
            # Если доступен только один тип - скрываем выбор
            if len(allowed_types) == 1:
                self.fields['offer_type'].initial = allowed_types[0]
                self.fields['offer_type'].widget = forms.HiddenInput()

    def clean_source_url(self):
        """Кастомная валидация URL - допускаем разные форматы boataround.com"""
        source_url = self.cleaned_data.get('source_url', '').strip()
        
        if not source_url:
            raise forms.ValidationError('URL не может быть пустым')
        
        # Проверяем что это ссылка с boataround
        if 'boataround.com' not in source_url.lower():
            raise forms.ValidationError('Используйте ссылку с boataround.com')
        
        # Добавляем https:// если не указана схема
        if not source_url.startswith(('http://', 'https://')):
            source_url = 'https://' + source_url
            
        # Дополнительная проверка формата (должны быть параметры checkIn и checkOut)
        # Параметры могут быть написаны в разном регистре, ищем case-insensitive
        import re
        has_check_in = re.search(r'checkIn\s*=', source_url, re.IGNORECASE)
        has_check_out = re.search(r'checkOut\s*=', source_url, re.IGNORECASE)
        
        if not has_check_in or not has_check_out:
            raise forms.ValidationError('В URL должны быть параметры checkIn и checkOut (дата заезда и выезда)')
        
        return source_url

