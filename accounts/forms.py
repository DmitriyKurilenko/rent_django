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

        if commit:
            profile.save()
        return profile
