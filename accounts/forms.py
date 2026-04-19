from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import CaptainBrand, Role, UserProfile
from boats.forms import DaisyUIMixin


class RegisterForm(DaisyUIMixin, UserCreationForm):
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
                    'role_ref': Role.objects.get(codename=role),
                    'phone': self.cleaned_data['phone'],
                }
            )
        return user


class ProfileUpdateForm(DaisyUIMixin, forms.ModelForm):
    first_name = forms.CharField(max_length=30, required=False, label='Имя')
    last_name = forms.CharField(max_length=30, required=False, label='Фамилия')

    class Meta:
        model = UserProfile
        fields = ['phone']

    def __init__(self, *args, **kwargs):
        user = kwargs['instance'].user if 'instance' in kwargs else None
        super().__init__(*args, **kwargs)
        if user:
            self.fields['first_name'].initial = user.first_name
            self.fields['last_name'].initial = user.last_name

    def save(self, commit=True):
        profile = super().save(commit=False)
        user = profile.user
        user.first_name = self.cleaned_data.get('first_name', user.first_name)
        user.last_name = self.cleaned_data.get('last_name', user.last_name)
        if commit:
            user.save(update_fields=['first_name', 'last_name'])
            profile.save(update_fields=['phone'])
        return profile


class CaptainBrandForm(DaisyUIMixin, forms.ModelForm):
    class Meta:
        model = CaptainBrand
        fields = [
            'name', 'logo', 'primary_color', 'tagline',
            'phone', 'email', 'website', 'telegram', 'whatsapp',
            'footer_text', 'is_default',
        ]
        widgets = {
            'primary_color': forms.TextInput(attrs={'type': 'color', 'class': 'h-10 w-20 cursor-pointer rounded border border-base-300 p-1'}),
            'footer_text': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'name': 'Название компании',
            'logo': 'Логотип',
            'primary_color': 'Основной цвет',
            'tagline': 'Слоган',
            'phone': 'Телефон',
            'email': 'Email',
            'website': 'Сайт',
            'telegram': 'Telegram',
            'whatsapp': 'WhatsApp',
            'footer_text': 'Текст в подвале оффера',
            'is_default': 'Использовать по умолчанию',
        }
