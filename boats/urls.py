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
    path('bookings/<int:booking_id>/attach-client/', views.attach_client_to_booking, name='attach_client_to_booking'),
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

    # Договоры
    path('contracts/', views.contracts_list, name='contracts_list'),
    path('contracts/create/<int:booking_id>/', views.create_contract, name='create_contract'),
    path('contracts/<uuid:uuid>/', views.contract_detail, name='contract_detail'),
    path('contracts/<uuid:uuid>/download/', views.download_contract, name='download_contract'),
    path('contracts/<uuid:uuid>/sign/<uuid:sign_token>/', views.sign_contract, name='sign_contract'),
    path('contracts/<uuid:uuid>/sign/<uuid:sign_token>/send-otp/', views.send_contract_otp, name='send_contract_otp'),

    # Клиенты
    path('clients/', views.clients_list, name='clients_list'),
    path('clients/create/', views.client_create, name='client_create'),
    path('clients/<int:pk>/', views.client_detail, name='client_detail'),
    path('clients/<int:pk>/edit/', views.client_edit, name='client_edit'),
    path('api/clients/search/', views.client_search_api, name='client_search_api'),

    # Информационные страницы
    path('terms/', views.terms, name='terms'),
    path('privacy/', views.privacy, name='privacy'),
    path('contacts/', views.contacts, name='contacts'),
]
