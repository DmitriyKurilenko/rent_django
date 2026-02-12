from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'
    verbose_name = 'Учетные записи'
    
    def ready(self):
        import accounts.models  # Импортируем сигналы
