from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import UserProfile


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    subscription_plan = forms.ChoiceField(
        choices=UserProfile.SUBSCRIPTION_CHOICES,
        initial='free',
        label='Подписка'
    )
    phone = forms.CharField(max_length=20, required=False, label='Телефон')
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2', 'subscription_plan', 'phone']
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            subscription_plan = self.cleaned_data['subscription_plan']
            role = 'tourist' if subscription_plan == 'free' else 'captain'

            UserProfile.objects.update_or_create(
                user=user,
                defaults={
                    'subscription_plan': subscription_plan,
                    'role': role,
                    'phone': self.cleaned_data['phone'],
                }
            )
        return user


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['subscription_plan', 'role', 'phone', 'bio', 'avatar']
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Администратор может изменять роли, остальные - нет
        if not self.instance.user.is_superuser:
            self.fields['role'].disabled = True

    def save(self, commit=True):
        profile = super().save(commit=False)

        # Синхронизируем роль с подпиской для обычных ролей
        # admin/superadmin/manager не затираем автоматически
        if profile.role in ['tourist', 'captain']:
            if profile.subscription_plan == 'free':
                profile.role = 'tourist'
            elif profile.subscription_plan in ['standard', 'advanced']:
                profile.role = 'captain'

        if commit:
            profile.save()
        return profile
