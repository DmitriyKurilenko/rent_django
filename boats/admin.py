from django.contrib import admin
from .models import (
    Boat, Favorite, Booking, Review, Offer, ParsedBoat, Charter,
    BoatTechnicalSpecs, BoatDescription, BoatPrice, BoatGallery, BoatDetails
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
