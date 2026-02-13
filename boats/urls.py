from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('boats/search/', views.boat_search, name='boat_search'),
    path('boats/api/autocomplete/', views.autocomplete_api, name='autocomplete_api'),
    path('boat/<int:pk>/', views.boat_detail, name='boat_detail'),  # Для локальных лодок
    path('boat/<str:boat_id>/', views.boat_detail_api, name='boat_detail_api'),  # Для API лодок
    path('boat/<str:boat_slug>/favorite/', views.toggle_favorite, name='toggle_favorite'),  # Toggle favorite
    path('boat/<str:boat_slug>/book/', views.book_boat, name='book_boat'),  # Прямое бронирование
    path('boat/<int:pk>/booking/', views.create_booking, name='create_booking'),
    path('boat/<int:pk>/review/', views.add_review, name='add_review'),
    path('favorites/', views.favorites_list, name='favorites_list'),
    path('my-bookings/', views.my_bookings, name='my_bookings'),
    path('bookings/<int:booking_id>/delete/', views.delete_booking, name='delete_booking'),
    path('bookings/<int:booking_id>/status/', views.update_booking_status, name='update_booking_status'),
    path('bookings/<int:booking_id>/assign/', views.assign_booking_manager, name='assign_booking_manager'),
    path('manage-boats/', views.manage_boats, name='manage_boats'),
    path('create-boat/', views.create_boat, name='create_boat'),
    
    # Офферы
    path('offers/', views.offers_list, name='offers_list'),
    path('offers/create/', views.create_offer, name='create_offer'),
    path('offers/<uuid:uuid>/', views.offer_detail, name='offer_detail'),
    path('offers/<uuid:uuid>/delete/', views.delete_offer, name='delete_offer'),
    path('offers/<uuid:uuid>/book/', views.book_offer, name='book_offer'),
    path('offer/<uuid:uuid>/', views.offer_view, name='offer_view'),
    
    # Быстрое создание оффера
    path('boat/<str:boat_slug>/create-offer/', views.quick_create_offer, name='quick_create_offer'),

    # Информационные страницы
    path('terms/', views.terms, name='terms'),
    path('privacy/', views.privacy, name='privacy'),
    path('contacts/', views.contacts, name='contacts'),
]
