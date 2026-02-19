from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns
from django.contrib.sitemaps.views import sitemap
from django.http import JsonResponse
from boats.sitemaps import BoatSitemap, StaticSitemap


def health_check(request):
    return JsonResponse({'status': 'ok'})

# Sitemaps dictionary
sitemaps = {
    'boats': BoatSitemap,
    'static': StaticSitemap,
}

# Non-i18n patterns
urlpatterns = [
    path('health/', health_check),
    path('admin/', admin.site.urls),
    path('i18n/', include('django.conf.urls.i18n')),  # Language switcher
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path('robots.txt', lambda request: __import__('django.http').HttpResponse(
        "User-agent: *\nDisallow: /admin/\nSitemap: /sitemap.xml\n", 
        content_type="text/plain"
    )),
]

# i18n patterns (с префиксом языка)
# ⭐ ВАЖНО: admin ИСКЛЮЧЕН из i18n_patterns, так как панель администратора не переводится
urlpatterns += i18n_patterns(
    path('accounts/', include('accounts.urls')),
    path('', include('boats.urls')),
    prefix_default_language=True,  # /ru/, /en/, /de/, /fr/, /es/
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

