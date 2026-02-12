"""
Sitemap для всех языков и лодок
Каждый язык получит свой sitemap
"""
from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.utils.translation import activate, get_language
from boats.models import ParsedBoat


class BoatSitemap(Sitemap):
    """
    Sitemap для всех лодок на текущем языке
    """
    changefreq = 'weekly'
    priority = 0.8
    protocol = 'https'
    
    def items(self):
        """Возвращает все лодки"""
        return ParsedBoat.objects.all().order_by('-id')
    
    def location(self, item):
        """URL для каждой лодки на текущем языке"""
        # URLs автоматически будут с префиксом языка благодаря i18n_patterns
        return reverse('boat_detail', kwargs={'slug': item.slug})
    
    def lastmod(self, item):
        """Последнее изменение"""
        return item.last_parse_time or item.created_at
    
    def priority(self, item):
        """Приоритет (более новые лодки - выше приоритет)"""
        # Можно добавить логику: популярные лодки выше
        return 0.8


class StaticSitemap(Sitemap):
    """
    Sitemap для статических страниц (главная, поиск и т.д.)
    """
    changefreq = 'monthly'
    priority = 1.0
    protocol = 'https'
    
    def items(self):
        """Список статических страниц"""
        return [
            {'name': 'index', 'priority': 1.0, 'changefreq': 'daily'},
            {'name': 'search', 'priority': 0.9, 'changefreq': 'weekly'},
            {'name': 'favorites', 'priority': 0.7, 'changefreq': 'monthly'},
        ]
    
    def location(self, item):
        """URL статической страницы"""
        return reverse(item['name'])
    
    def changefreq(self, item):
        return item['changefreq']
    
    def priority(self, item):
        return item['priority']
