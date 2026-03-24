from django.contrib import admin
from .models import (
    Boat, Favorite, Booking, Review, Offer, ParsedBoat, Charter,
    BoatTechnicalSpecs, BoatDescription, BoatPrice, BoatGallery, BoatDetails,
    ContractTemplate, Contract, Client, ContractOTP,
)


@admin.register(Charter)
class CharterAdmin(admin.ModelAdmin):
    list_display = ['name', 'charter_id', 'commission', 'boats_count', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'charter_id']
    list_editable = ['commission']
    readonly_fields = ['charter_id', 'created_at', 'updated_at']
    
    def boats_count(self, obj):
        """Количество лодок у чартера"""
        return obj.boats.count()
    boats_count.short_description = 'Лодок'
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('charter_id', 'name', 'logo')
        }),
        ('Комиссия', {
            'fields': ('commission',),
            'description': 'Процент комиссии, добавляемый к итоговой цене'
        }),
        ('Метаданные', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Boat)
class BoatAdmin(admin.ModelAdmin):
    list_display = ['name', 'boat_type', 'location', 'capacity', 'price_per_day', 'available', 'owner', 'created_at']
    list_filter = ['boat_type', 'available', 'location', 'created_at']
    search_fields = ['name', 'location', 'description']
    list_editable = ['available']
    ordering = ['-created_at']


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ['user', 'get_boat_title', 'boat_slug', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username', 'boat_slug', 'parsed_boat__slug']
    readonly_fields = ['boat_slug', 'boat_id']
    
    def get_boat_title(self, obj):
        """Получить название лодки из parsed_boat"""
        return obj.get_boat_title()
    get_boat_title.short_description = 'Лодка'


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['boat', 'user', 'start_date', 'end_date', 'guests', 'status', 'total_price', 'created_at']
    list_filter = ['status', 'created_at', 'start_date']
    search_fields = ['boat__name', 'user__username']
    list_editable = ['status']


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['boat', 'user', 'rating', 'created_at']
    list_filter = ['rating', 'created_at']
    search_fields = ['boat__name', 'user__username', 'comment']


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ['uuid', 'get_offer_type_badge', 'title', 'created_by', 'check_in', 'check_out', 'total_price', 'currency', 'is_active', 'views_count', 'created_at']
    list_filter = ['offer_type', 'is_active', 'currency', 'created_at', 'created_by']
    search_fields = ['uuid', 'title', 'created_by__username']
    list_editable = ['is_active']
    readonly_fields = ['uuid', 'views_count', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    def get_offer_type_badge(self, obj):
        """Отображение типа оффера с цветным badge"""
        from django.utils.html import format_html
        colors = {
            'tourist': '#2196F3',  # синий
            'captain': '#8b5cf6',  # фиолетовый
        }
        icons = {
            'tourist': '⛵',
            'captain': '⚓',
        }
        color = colors.get(obj.offer_type, '#6b7280')
        icon = icons.get(obj.offer_type, '🚢')
        
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px; font-weight: bold;">{} {}</span>',
            color,
            icon,
            obj.get_offer_type_display()
        )
    
    get_offer_type_badge.short_description = 'Тип'
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('uuid', 'created_by', 'offer_type', 'source_url', 'title', 'description')
        }),
        ('Даты', {
            'fields': ('check_in', 'check_out', 'expires_at')
        }),
        ('Цены', {
            'fields': ('total_price', 'original_price', 'discount', 'currency')
        }),
        ('Настройки', {
            'fields': ('show_countdown', 'notifications', 'notes', 'is_active')
        }),
        ('Данные', {
            'fields': ('boat_data',),
            'classes': ('collapse',)
        }),
        ('Метаданные', {
            'fields': ('views_count', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ParsedBoat)
class ParsedBoatAdmin(admin.ModelAdmin):
    list_display = ['boat_id', 'manufacturer', 'model', 'year', 'charter', 'parse_count', 'last_parse_success', 'last_parsed']
    list_filter = ['last_parse_success', 'manufacturer', 'charter', 'last_parsed']
    search_fields = ['boat_id', 'slug', 'manufacturer', 'model', 'charter__name']
    readonly_fields = ['boat_id', 'created_at', 'updated_at', 'last_parsed', 'parse_count']
    ordering = ['-last_parsed']
    
    fieldsets = (
        ('Идентификация', {
            'fields': ('boat_id', 'slug', 'source_url')
        }),
        ('Чартер', {
            'fields': ('charter',)
        }),
        ('Основная информация', {
            'fields': ('manufacturer', 'model', 'year')
        }),
        ('Статистика', {
            'fields': ('last_parsed', 'parse_count', 'last_parse_success')
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(BoatTechnicalSpecs)
class BoatTechnicalSpecsAdmin(admin.ModelAdmin):
    list_display = ['boat', 'length', 'beam', 'cabins', 'berths', 'toilets', 'max_speed']
    list_filter = ['cabins', 'berths', 'toilets']
    search_fields = ['boat__manufacturer', 'boat__model', 'boat__slug']
    readonly_fields = ['boat']


@admin.register(BoatDescription)
class BoatDescriptionAdmin(admin.ModelAdmin):
    list_display = ['boat', 'language', 'title']
    list_filter = ['language']
    search_fields = ['boat__slug', 'title', 'location']


@admin.register(BoatPrice)
class BoatPriceAdmin(admin.ModelAdmin):
    list_display = ['boat', 'currency', 'price_per_day', 'updated_at']
    list_filter = ['currency', 'updated_at']
    search_fields = ['boat__slug']


@admin.register(BoatGallery)
class BoatGalleryAdmin(admin.ModelAdmin):
    list_display = ['boat', 'order', 'cdn_url']
    list_filter = ['boat']
    search_fields = ['boat__slug']
    ordering = ['boat', 'order']


@admin.register(BoatDetails)
class BoatDetailsAdmin(admin.ModelAdmin):
    list_display = ['boat', 'language']
    list_filter = ['language']
    search_fields = ['boat__slug']


@admin.register(ContractTemplate)
class ContractTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'contract_type', 'is_active', 'updated_at']
    list_filter = ['contract_type', 'is_active']
    search_fields = ['name']


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ['contract_number', 'status', 'created_by', 'signer', 'booking', 'signed_at', 'created_at']
    list_filter = ['status', 'created_at', 'signed_at']
    search_fields = ['contract_number', 'created_by__username', 'signer__username', 'uuid']
    readonly_fields = ['uuid', 'sign_token', 'document_hash', 'sign_ip', 'sign_user_agent', 'signed_at', 'created_at', 'updated_at']
    ordering = ['-created_at']

    fieldsets = (
        ('Основная информация', {
            'fields': ('uuid', 'contract_number', 'status', 'template')
        }),
        ('Связи', {
            'fields': ('booking', 'offer', 'created_by', 'signer')
        }),
        ('Документы', {
            'fields': ('document_file', 'signed_file', 'document_hash')
        }),
        ('Данные договора', {
            'fields': ('contract_data',),
            'classes': ('collapse',)
        }),
        ('Подписание', {
            'fields': ('signature_data', 'signed_at', 'sign_ip', 'sign_user_agent', 'sign_token', 'expires_at'),
            'classes': ('collapse',)
        }),
        ('Метаданные', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ContractOTP)
class ContractOTPAdmin(admin.ModelAdmin):
    list_display = ['contract', 'code', 'phone', 'delivery_method', 'is_verified', 'attempts', 'created_at', 'expires_at']
    list_filter = ['delivery_method', 'is_verified']
    search_fields = ['contract__contract_number', 'phone']
    readonly_fields = ['created_at']


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'phone', 'email', 'created_by', 'created_at']
    list_filter = ['created_at']
    search_fields = ['last_name', 'first_name', 'middle_name', 'phone', 'email', 'passport_number']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['created_by', 'user']

    fieldsets = (
        ('ФИО', {
            'fields': ('last_name', 'first_name', 'middle_name')
        }),
        ('Контакты', {
            'fields': ('phone', 'email')
        }),
        ('Документы', {
            'fields': ('passport_number', 'passport_issued_by', 'passport_date', 'address'),
            'classes': ('collapse',)
        }),
        ('Связи', {
            'fields': ('created_by', 'user')
        }),
        ('Дополнительно', {
            'fields': ('notes', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def full_name(self, obj):
        return obj.full_name
    full_name.short_description = 'ФИО'
