from django.contrib import admin
from django.utils.html import format_html
from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'get_role_badge', 'phone', 'created_at']
    list_filter = ['role', 'created_at']
    search_fields = ['user__username', 'user__email', 'phone']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Пользователь', {
            'fields': ('user', 'role')
        }),
        ('Контакты', {
            'fields': ('phone',)
        }),
        ('Дополнительно', {
            'fields': ('bio', 'avatar')
        }),
        ('Системная информация', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at']
    
    def get_role_badge(self, obj):
        """Отображение роли с цветным badge"""
        colors = {
            'tourist': '#3b82f6',    # blue
            'captain': '#8b5cf6',    # purple
            'manager': '#f59e0b',    # orange
            'admin': '#ef4444',      # red
        }
        color = colors.get(obj.role, '#6b7280')
        
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_role_display()
        )
    
    get_role_badge.short_description = 'Роль'
    
    def get_readonly_fields(self, request, obj=None):
        """Пользователи не могут менять свою роль через админку"""
        if obj and obj.user == request.user:
            return self.readonly_fields + ['role']
        return self.readonly_fields


# Добавляем описание ролей в help_text админки
UserProfile._meta.get_field('role').help_text = """
<b>Роли пользователей:</b><br>
• <b>Турист</b> - базовая роль. Поиск лодок, просмотр, добавление в избранное.<br>
• <b>Капитан</b> - может создавать капитанские офферы (детальные, со всей информацией).<br>
• <b>Менеджер</b> - может создавать туристические и капитанские офферы, управлять лодками.<br>
• <b>Администратор</b> - полный доступ ко всем функциям системы.
"""
