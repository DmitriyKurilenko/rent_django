from django.contrib import admin
from django.utils.html import format_html
from .models import CaptainBrand, Permission, Role, UserProfile


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ['codename', 'name']
    search_fields = ['codename', 'name']
    ordering = ['codename']

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ['codename', 'name', 'is_system', 'get_permissions_list']
    list_filter = ['is_system']
    search_fields = ['codename', 'name']
    filter_horizontal = ['permissions']
    ordering = ['codename']

    def get_permissions_list(self, obj):
        return ', '.join(obj.permissions.values_list('codename', flat=True))
    get_permissions_list.short_description = 'Разрешения'

    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_system:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'get_role_badge', 'assigned_staff', 'phone', 'created_at']
    list_filter = ['role_ref', 'created_at']
    search_fields = ['user__username', 'user__email', 'phone']
    ordering = ['-created_at']
    raw_id_fields = ['assigned_staff']

    fieldsets = (
        ('Пользователь', {
            'fields': ('user', 'role_ref')
        }),
        ('Контакты', {
            'fields': ('phone',)
        }),
        ('Чат', {
            'fields': ('assigned_staff', 'telegram_chat_id'),
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
            'assistant': '#10b981',  # green
            'manager': '#f59e0b',    # orange
            'admin': '#ef4444',      # red
            'superadmin': '#dc2626', # dark red
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
            return self.readonly_fields + ['role_ref']
        return self.readonly_fields


@admin.register(CaptainBrand)
class CaptainBrandAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'is_default', 'phone', 'email', 'created_at']
    list_filter = ['is_default', 'created_at']
    search_fields = ['name', 'owner__username', 'owner__email']
    ordering = ['owner', '-is_default', 'name']
    readonly_fields = ['created_at']

    fieldsets = (
        ('Основное', {'fields': ('owner', 'name', 'logo', 'primary_color', 'tagline', 'is_default')}),
        ('Контакты', {'fields': ('phone', 'email', 'website', 'telegram', 'whatsapp')}),
        ('Дополнительно', {'fields': ('footer_text', 'created_at')}),
    )
