from django.shortcuts import render, redirect
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
        'favorites_count': Favorite.objects.filter(user=request.user).count(),
        'bookings_count': Booking.objects.filter(user=request.user).count(),
    }
    
    # Add boats count if user can manage boats
    if request.user.profile.can_manage_boats:
        from boats.models import Boat
        context['boats_count'] = Boat.objects.filter(owner=request.user).count()
    
    # Add offers count if user can create offers
    if request.user.profile.can_create_offers:
        if request.user.profile.role == 'admin':
            context['offers_count'] = Offer.objects.count()
        else:
            context['offers_count'] = Offer.objects.filter(created_by=request.user).count()
    
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
