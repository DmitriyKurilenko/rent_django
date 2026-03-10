from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden
from .forms import RegisterForm, ProfileUpdateForm


def register_view(request):
    """Регистрация нового пользователя"""
    if request.user.is_authenticated:
        return redirect('home')
    
    valid_plans = {'free', 'standard', 'advanced'}
    selected_plan = request.GET.get('plan', 'free')
    if selected_plan not in valid_plans:
        selected_plan = 'free'

    if request.method == 'POST':
        post_data = request.POST.copy()
        if not post_data.get('subscription_plan'):
            post_data['subscription_plan'] = selected_plan

        form = RegisterForm(post_data)
        if form.is_valid():
            user = form.save()

            subscription_plan = form.cleaned_data.get('subscription_plan', 'free')
            role = 'tourist' if subscription_plan == 'free' else 'captain'
            user.profile.subscription_plan = subscription_plan
            user.profile.role = role
            user.profile.save(update_fields=['subscription_plan', 'role'])

            login(request, user)
            messages.success(request, f'Добро пожаловать, {user.username}!')
            return redirect('profile')
    else:
        form = RegisterForm(initial={'subscription_plan': selected_plan})
    
    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    """Вход пользователя"""
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, f'Добро пожаловать, {user.username}!')
            next_url = request.GET.get('next', 'home')
            return redirect(next_url)
        else:
            messages.error(request, 'Неверное имя пользователя или пароль')
    
    return render(request, 'accounts/login.html')


def logout_view(request):
    """Выход пользователя"""
    logout(request)
    messages.info(request, 'Вы вышли из системы')
    return redirect('home')


@login_required
def profile_view(request):
    """Просмотр и редактирование профиля"""
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user.profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Профиль обновлен!')
            return redirect('profile')
    else:
        form = ProfileUpdateForm(instance=request.user.profile)
    
    # Get stats for dashboard
    from boats.models import Favorite, Booking, Offer
    
    context = {
        'form': form,
        # .count() использует индекс, быстро даже при большом объёме
        'favorites_count': Favorite.objects.filter(user=request.user).count(),
        'bookings_count': Booking.objects.filter(user=request.user).count(),
    }
    # Если потребуется выводить списки — использовать select_related/prefetch_related
    # Пример: Favorite.objects.filter(user=request.user).select_related('parsed_boat')[:20]
    if request.user.profile.can_manage_boats:
        from boats.models import Boat
        context['boats_count'] = Boat.objects.filter(owner=request.user).count()
    if request.user.profile.can_create_offers:
        if request.user.profile.role == 'admin':
            context['offers_count'] = Offer.objects.count()
        else:
            context['offers_count'] = Offer.objects.filter(created_by=request.user).count()
    if request.user.profile.can_manage_prices():
        from boats.models import PriceSettings
        ps = PriceSettings.get_settings()
        context['price_searcher_fields'] = [
            (f, l, t, getattr(ps, f)) for f, l, t in PRICE_FIELDS if not f.startswith('tourist_')
        ]
        context['price_tourist_fields'] = [
            (f, l, t, getattr(ps, f)) for f, l, t in PRICE_FIELDS if f.startswith('tourist_')
        ]
    return render(request, 'accounts/profile.html', context)


@login_required
def charters_management_view(request):
    """Управление комиссиями чартеров (только для superadmin)"""
    if not request.user.profile.can_manage_charters():
        return HttpResponseForbidden('Доступ запрещен')

    from boats.models import Charter

    query = request.GET.get('q', '').strip()

    if request.method == 'POST':
        charter_id = request.POST.get('charter_id')
        commission_raw = request.POST.get('commission')

        try:
            commission = int(str(commission_raw).strip())
        except (TypeError, ValueError):
            messages.error(request, 'Комиссия должна быть целым числом')
            return redirect('charters_management')

        if commission < 0 or commission > 100:
            messages.error(request, 'Комиссия должна быть от 0 до 100')
            return redirect('charters_management')

        charter = Charter.objects.filter(id=charter_id).first()
        if not charter:
            messages.error(request, 'Чартер не найден')
            return redirect('charters_management')

        charter.commission = commission
        charter.save(update_fields=['commission', 'updated_at'])
        messages.success(request, f'Комиссия для {charter.name} обновлена: {commission}%')
        return redirect('charters_management')

    charters = Charter.objects.all().order_by('name')
    if query:
        charters = charters.filter(name__icontains=query)

    context = {
        'charters': charters,
        'charters_count': charters.count(),
        'query': query,
    }
    return render(request, 'accounts/charters_management.html', context)


PRICE_FIELDS = [
    # (field_name, label, field_type)  — field_type: 'decimal' | 'int'
    # --- Общие ---
    ('extra_discount_max', 'Макс. доп. скидка — поисковик + агент (%)', 'int'),
    # --- Туристический оффер ---
    ('tourist_insurance_rate', 'Ставка страхования (доля, напр. 0.10)', 'decimal'),
    ('tourist_insurance_min', 'Мин. страховка (EUR)', 'decimal'),
    ('tourist_turkey_base', 'Базовая цена Турция (EUR)', 'decimal'),
    ('tourist_seychelles_base', 'Базовая цена Сейшелы (EUR)', 'decimal'),
    ('tourist_default_base', 'Базовая цена по умолчанию (EUR)', 'decimal'),
    ('tourist_praslin_extra', 'Надбавка за Praslin Marina (EUR)', 'decimal'),
    ('tourist_length_extra', 'Надбавка за длину >14.2 м (EUR)', 'decimal'),
    ('tourist_cook_price', 'Стоимость повара (EUR)', 'decimal'),
    ('tourist_turkey_dish_base', 'Питание Турция EUR/чел', 'decimal'),
    ('tourist_seychelles_dish_base', 'Питание Сейшелы EUR/чел', 'decimal'),
    ('tourist_default_dish_base', 'Питание по умолчанию EUR/чел', 'decimal'),
    ('tourist_max_double_cabins_free', 'Бесплатных двойных кают Сейшелы (шт)', 'int'),
    ('tourist_double_cabin_extra', 'Надбавка за доп. двойную каюту (EUR)', 'decimal'),
    ('tourist_catamaran_length_extra', 'Надбавка длина катамарана Турция (EUR)', 'decimal'),
    ('tourist_sailing_length_extra', 'Надбавка длина парусной яхты Турция (EUR)', 'decimal'),
]


@login_required
def price_settings_view(request):
    """Настройки цен (только admin и superadmin)."""
    if not request.user.profile.can_manage_prices():
        return HttpResponseForbidden('Доступ запрещен')

    from boats.models import PriceSettings
    settings_obj, _ = PriceSettings.objects.get_or_create(pk=1)

    errors = {}
    if request.method == 'POST':
        updates = {}
        for field, label, ftype in PRICE_FIELDS:
            raw = request.POST.get(field, '').strip()
            if not raw:
                errors[field] = f'{label}: обязательное поле'
                continue
            try:
                if ftype == 'int':
                    updates[field] = int(raw)
                else:
                    updates[field] = Decimal(raw)
            except (ValueError, InvalidOperation):
                errors[field] = f'{label}: неверное значение «{raw}»'

        if not errors:
            for field, value in updates.items():
                setattr(settings_obj, field, value)
            settings_obj.save()
            messages.success(request, 'Настройки цен сохранены')
            return redirect(reverse('profile') + '?tab=prices')

    # Build list of (field, label, ftype, current_value) for the template
    price_fields_with_values = [
        (field, label, ftype, getattr(settings_obj, field))
        for field, label, ftype in PRICE_FIELDS
    ]

    context = {
        'settings': settings_obj,
        'price_fields': price_fields_with_values,
        'errors': errors,
    }
    return render(request, 'accounts/price_settings.html', context)
