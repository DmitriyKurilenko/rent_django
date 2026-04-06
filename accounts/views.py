from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
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
            user.profile.save(update_fields=['subscription_plan', 'role_ref'])

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
            next_url = request.GET.get('next', '')
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
            return redirect('home')
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
    if request.user.profile.can_manage_boats():
        from boats.models import Boat
        context['boats_count'] = Boat.objects.filter(owner=request.user).count()
    if request.user.profile.can_create_offers():
        if request.user.profile.can_see_all_bookings():
            context['offers_count'] = Offer.objects.count()
        else:
            context['offers_count'] = Offer.objects.filter(created_by=request.user).count()
    if request.user.profile.can_create_captain_offers():
        from boats.models import PriceSettings as _PS
        context['agent_commission_info'] = {
            'pct': _PS.get_settings().agent_commission_pct,
        }
    if request.user.profile.can_manage_prices():
        from boats.models import PriceSettings, COUNTRY_PRICE_FIELDS
        ps = PriceSettings.get_settings()
        context['price_searcher_fields'] = [
            (f, l, t, getattr(ps, f)) for f, l, t in PRICE_FIELDS if not f.startswith('tourist_')
        ]
        context['pv'] = {f: getattr(ps, f) for f, l, t in PRICE_FIELDS}
        context['country_configs'] = list(ps.country_configs.all())
        context['country_price_fields'] = COUNTRY_PRICE_FIELDS
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
        return redirect('charters_management')

    charters = Charter.objects.all().order_by('name')
    if query:
        charters = charters.filter(name__icontains=query)

    total_count = charters.count()

    page_sizes = [10, 50, 100]
    try:
        per_page = int(request.GET.get('per_page', 50))
    except (TypeError, ValueError):
        per_page = 50
    if per_page not in page_sizes:
        per_page = 50

    paginator = Paginator(charters, per_page)
    page_num = request.GET.get('page', 1)
    charters_page = paginator.get_page(page_num)

    context = {
        'charters': charters_page,
        'charters_count': total_count,
        'query': query,
        'per_page': per_page,
        'page_sizes': page_sizes,
    }
    return render(request, 'accounts/charters_management.html', context)


PRICE_FIELDS = [
    # (field_name, label, field_type)  — field_type: 'decimal' | 'int'
    # --- Общие ---
    ('extra_discount_max', 'Макс. доп. скидка — поисковик + агент (%)', 'int'),
    ('agent_commission_pct', 'Комиссия агента (% от комиссии чартера)', 'int'),
]


@login_required
def price_settings_view(request):
    """Настройки цен (только admin и superadmin)."""
    if not request.user.profile.can_manage_prices():
        return HttpResponseForbidden('Доступ запрещен')

    from boats.models import PriceSettings, CountryPriceConfig, COUNTRY_PRICE_FIELDS

    settings_obj, _ = PriceSettings.objects.prefetch_related('country_configs').get_or_create(pk=1)

    errors = {}
    action = request.POST.get('action', 'save_prices')

    if request.method == 'POST':
        if action == 'add_country':
            name = request.POST.get('new_country_name', '').strip()
            code = request.POST.get('new_country_code', '').strip().lower()
            match = request.POST.get('new_match_names', '').strip()
            if not name or not code:
                messages.error(request, 'Укажите название и код страны')
            elif CountryPriceConfig.objects.filter(country_code=code).exists():
                messages.error(request, f'Страна с кодом «{code}» уже существует')
            else:
                max_sort = (
                    CountryPriceConfig.objects.filter(is_default=False)
                    .order_by('-sort_order').values_list('sort_order', flat=True).first()
                ) or 0
                CountryPriceConfig.objects.create(
                    price_settings=settings_obj,
                    country_name=name,
                    country_code=code,
                    match_names=match,
                    sort_order=max_sort + 1,
                )
                messages.success(request, f'Страна «{name}» добавлена')
            return redirect(reverse('profile') + '?tab=prices')

        if action == 'delete_country':
            cid = request.POST.get('country_id')
            cc = CountryPriceConfig.objects.filter(pk=cid).first()
            if cc and cc.is_default:
                messages.error(request, 'Нельзя удалить профиль по умолчанию')
            elif cc:
                name = cc.country_name
                cc.delete()
                messages.success(request, f'Страна «{name}» удалена')
            return redirect(reverse('profile') + '?tab=prices')

        # action == 'save_prices'
        # Global fields
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

        # Country config fields: cc_{id}_{field}
        cc_updates = {}  # {config_id: {field: value}}
        for cc in settings_obj.country_configs.all():
            cc_updates[cc.pk] = {}
            for fname, flabel, ftype in COUNTRY_PRICE_FIELDS:
                key = f'cc_{cc.pk}_{fname}'
                raw = request.POST.get(key, '').strip()
                if not raw:
                    errors[key] = f'{cc.country_name} — {flabel}: обязательное поле'
                    continue
                try:
                    if ftype == 'int':
                        cc_updates[cc.pk][fname] = int(raw)
                    else:
                        cc_updates[cc.pk][fname] = Decimal(raw)
                except (ValueError, InvalidOperation):
                    errors[key] = f'{cc.country_name} — {flabel}: неверное значение «{raw}»'
            # Also save meta fields
            meta_name = request.POST.get(f'cc_{cc.pk}_country_name', '').strip()
            meta_match = request.POST.get(f'cc_{cc.pk}_match_names', '').strip()
            if meta_name:
                cc_updates[cc.pk]['_country_name'] = meta_name
            if meta_match is not None:
                cc_updates[cc.pk]['_match_names'] = meta_match

        if not errors:
            for field, value in updates.items():
                setattr(settings_obj, field, value)
            settings_obj.save()
            for cc in settings_obj.country_configs.all():
                changed = False
                for fname, value in cc_updates.get(cc.pk, {}).items():
                    if fname == '_country_name':
                        cc.country_name = value
                        changed = True
                    elif fname == '_match_names':
                        cc.match_names = value
                        changed = True
                    else:
                        setattr(cc, fname, value)
                        changed = True
                if changed:
                    cc.save()
            messages.success(request, 'Настройки цен сохранены')
            return redirect(reverse('profile') + '?tab=prices')

    # Reload after possible changes
    settings_obj = PriceSettings.objects.prefetch_related('country_configs').get(pk=1)
    country_configs = list(settings_obj.country_configs.all())

    pv = {f: getattr(settings_obj, f) for f, l, t in PRICE_FIELDS}

    context = {
        'settings': settings_obj,
        'price_fields': [(f, l, t, getattr(settings_obj, f)) for f, l, t in PRICE_FIELDS],
        'pv': pv,
        'country_configs': country_configs,
        'country_price_fields': COUNTRY_PRICE_FIELDS,
        'errors': errors,
    }
    return render(request, 'accounts/price_settings.html', context)
