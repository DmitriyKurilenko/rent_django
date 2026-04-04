# 💻 Примеры кода для многоязычной архитектуры

## 1️⃣ Settings.py Configuration

```python
# boat_rental/settings.py

# ============ LANGUAGES ============
LANGUAGES = [
    ('ru', 'Русский'),
    ('en', 'English'),
    ('de', 'Deutsch'),
    ('fr', 'Français'),
    ('es', 'Español'),
]

LANGUAGE_CODE = 'ru'  # Default language
LOCALE_PATHS = [BASE_DIR / 'locale']

# ============ MIDDLEWARE ============
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',  # ← IMPORTANT! After Session
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# ============ TEMPLATES ============
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n',  # ← Add this
            ],
        },
    },
]

# ============ INSTALLED APPS ============
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sitemaps',  # ← Add this
    'accounts',
    'boats',
]
```

---

## 2️⃣ URL Configuration

```python
# boat_rental/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf.urls.i18n import i18n_patterns
from django.contrib.sitemaps.views import sitemap
from django.http import HttpResponse
from boats.sitemaps import BoatSitemap, StaticSitemap

# Sitemaps dictionary
sitemaps = {
    'boats': BoatSitemap,
    'static': StaticSitemap,
}

# Non-i18n patterns (same for all languages)
urlpatterns = [
    path('admin/', admin.site.urls),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path('robots.txt', lambda request: HttpResponse("User-agent: *\nDisallow: /admin/", content_type="text/plain")),
]

# i18n patterns (with language prefix)
urlpatterns += i18n_patterns(
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('', include('boats.urls')),
    prefix_default_language=True,  # Include language prefix even for default (ru)
)
```

---

## 3️⃣ Sitemap Implementation

```python
# boats/sitemaps.py

from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from boats.models import ParsedBoat

class BoatSitemap(Sitemap):
    """
    Generates sitemap for all boats across all languages.
    Django automatically adds language prefix from i18n_patterns.
    """
    changefreq = 'weekly'
    priority = 0.8

    def items(self):
        return ParsedBoat.objects.all()

    def location(self, item):
        # reverse() automatically includes language prefix from i18n_patterns
        return reverse('boat_detail', args=[item.slug])

    def lastmod(self, item):
        return item.updated_at  # If your model has this field


class StaticSitemap(Sitemap):
    """
    Generates sitemap for static pages (index, search, etc)
    """
    changefreq_map = {
        'index': 'daily',
        'search': 'weekly',
        'favorites': 'monthly',
    }
    
    priority_map = {
        'index': 1.0,
        'search': 0.9,
        'favorites': 0.7,
    }

    def items(self):
        return ['index', 'search', 'favorites']

    def location(self, item):
        return reverse(item)

    def changefreq(self, item):
        return self.changefreq_map.get(item, 'weekly')

    def priority(self, item):
        return self.priority_map.get(item, 0.8)
```

---

## 4️⃣ Views with Language Detection

```python
# boats/views.py

from django.shortcuts import get_object_or_404
from django.utils.translation import get_language
from boats.models import ParsedBoat, BoatDescription, BoatDetails

# Language mapping: Django i18n code → Internal code
LANG_MAP = {
    'ru': 'ru_RU',
    'en': 'en_EN',
    'de': 'de_DE',
    'fr': 'fr_FR',
    'es': 'es_ES',
}

def boat_detail_api(request, boat_id):
    """
    Returns localized boat data based on current language.
    
    URL Examples:
    - /ru/boat/bavaria-cruiser-46/ → Returns Russian data
    - /en/boat/bavaria-cruiser-46/ → Returns English data
    - /de/boot/bavaria-cruiser-46/ → Returns German data
    """
    
    # 1. Get current language from URL prefix (set by LocaleMiddleware)
    current_lang = get_language()  # 'ru', 'en', 'de', 'fr', 'es'
    
    # 2. Map to internal language code
    lang_code = LANG_MAP.get(current_lang, 'ru_RU')
    
    # 3. Get boat from ParsedBoat (same for all languages)
    parsed_boat = get_object_or_404(ParsedBoat, slug=boat_id)
    
    # 4. Get description in CURRENT LANGUAGE
    boat_description = get_object_or_404(
        BoatDescription,
        boat=parsed_boat,
        language=lang_code  # ← KEY: Filter by language!
    )
    
    # 5. Get details in CURRENT LANGUAGE
    boat_details = get_object_or_404(
        BoatDetails,
        boat=parsed_boat,
        language=lang_code  # ← KEY: Filter by language!
    )
    
    # 6. Build response data
    data = {
        'id': parsed_boat.boat_id,
        'slug': parsed_boat.slug,
        'title': boat_description.title,
        'description': boat_description.description,
        'location': boat_description.location,
        'manufacturer': parsed_boat.manufacturer,
        'model': parsed_boat.model,
        'year': parsed_boat.year,
        'equipment': boat_details.equipment,
        'cockpit': boat_details.cockpit,
        'entertainment': boat_details.entertainment,
        'gallery': parsed_boat.boatgallery_set.values('image_url'),
    }
    
    return JsonResponse(data)


def language_selector(request, language_code):
    """
    Redirects to the same page in a different language.
    
    Usage: <a href="{% url 'language_selector' language_code='en' %}">English</a>
    """
    from django.utils.translation import activate
    from django.http import HttpResponseRedirect
    
    activate(language_code)
    response = HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))
    response.set_cookie('django_language', language_code)
    return response
```

---

## 5️⃣ Template Examples

```html
<!-- boats/detail.html -->

{% load i18n %}

<!DOCTYPE html>
<html lang="{{ LANGUAGE_CODE }}">
<head>
    <meta charset="UTF-8">
    <title>{% trans "Boat Details" %} - {{ boat.title }}</title>
    
    <!-- Canonical tag for current language -->
    <link rel="canonical" href="https://{{ request.get_host }}{{ request.path }}" />
    
    <!-- Alternate language tags for SEO -->
    <link rel="alternate" hreflang="ru" href="https://{{ request.get_host }}/ru/boat/{{ boat.slug }}/" />
    <link rel="alternate" hreflang="en" href="https://{{ request.get_host }}/en/boat/{{ boat.slug }}/" />
    <link rel="alternate" hreflang="de" href="https://{{ request.get_host }}/de/boot/{{ boat.slug }}/" />
    <link rel="alternate" hreflang="fr" href="https://{{ request.get_host }}/fr/bateau/{{ boat.slug }}/" />
    <link rel="alternate" hreflang="es" href="https://{{ request.get_host }}/es/bote/{{ boat.slug }}/" />
</head>
<body>
    <!-- LANGUAGE SELECTOR -->
    <div class="language-selector">
        <a href="/ru/boat/{{ boat.slug }}/">🇷🇺 Русский</a>
        <a href="/en/boat/{{ boat.slug }}/">🇬🇧 English</a>
        <a href="/de/boot/{{ boat.slug }}/">🇩🇪 Deutsch</a>
        <a href="/fr/bateau/{{ boat.slug }}/">🇫🇷 Français</a>
        <a href="/es/bote/{{ boat.slug }}/">🇪🇸 Español</a>
    </div>

    <!-- BOAT DETAILS -->
    <div class="boat-detail">
        <h1>{{ boat_description.title }}</h1>
        
        <p>{% trans "Location" %}: {{ boat_description.location }}</p>
        
        <p>{% trans "Description" %}:</p>
        <p>{{ boat_description.description }}</p>
        
        <!-- EQUIPMENT SECTION (LOCALIZED) -->
        <section class="equipment">
            <h2>{% trans "Equipment" %}</h2>
            {% if boat_details.equipment %}
                <ul>
                {% for item in boat_details.equipment %}
                    <li>{{ item.name }}</li>  {# Already in current language from DB #}
                {% endfor %}
                </ul>
            {% else %}
                <p>{% trans "No equipment listed" %}</p>
            {% endif %}
        </section>
        
        <!-- COCKPIT SECTION (LOCALIZED) -->
        <section class="cockpit">
            <h2>{% trans "Cockpit" %}</h2>
            {% if boat_details.cockpit %}
                <ul>
                {% for item in boat_details.cockpit %}
                    <li>{{ item.name }}</li>  {# Already in current language from DB #}
                {% endfor %}
                </ul>
            {% endif %}
        </section>
        
        <!-- ENTERTAINMENT SECTION (LOCALIZED) -->
        <section class="entertainment">
            <h2>{% trans "Entertainment" %}</h2>
            {% if boat_details.entertainment %}
                <ul>
                {% for item in boat_details.entertainment %}
                    <li>{{ item.name }}</li>  {# Already in current language from DB #}
                {% endfor %}
                </ul>
            {% endif %}
        </section>
        
        <!-- GALLERY (SAME FOR ALL LANGUAGES) -->
        <section class="gallery">
            <h2>{% trans "Gallery" %}</h2>
            {% for image in gallery %}
                <img src="{{ image.image_url }}" alt="{{ boat_description.title }}" />
            {% endfor %}
        </section>
        
        <!-- ACTION BUTTONS -->
        <div class="actions">
            <button>{% trans "Book Now" %}</button>
            <button>{% trans "Add to Favorites" %}</button>
            <button>{% trans "Contact Owner" %}</button>
        </div>
    </div>
    
    <!-- BREADCRUMBS WITH LANGUAGE -->
    <nav class="breadcrumbs">
        <a href="{% url 'index' %}">{% trans "Home" %}</a> /
        <a href="{% url 'search' %}">{% trans "Search" %}</a> /
        <span>{{ boat_description.title }}</span>
    </nav>
</body>
</html>
```

---

## 6️⃣ Translation Files

```gettext
# locale/ru/LC_MESSAGES/django.po

#: boats/views.py
msgid "Boat Details"
msgstr "Детали лодки"

msgid "Location"
msgstr "Местоположение"

msgid "Description"
msgstr "Описание"

msgid "Equipment"
msgstr "Оборудование"

msgid "Cockpit"
msgstr "Кокпит"

msgid "Entertainment"
msgstr "Развлечения"

msgid "Gallery"
msgstr "Галерея"

msgid "Book Now"
msgstr "Забронировать"

msgid "Add to Favorites"
msgstr "Добавить в избранное"

msgid "Remove from Favorites"
msgstr "Убрать из избранного"

msgid "Contact Owner"
msgstr "Связаться с владельцем"

msgid "Home"
msgstr "Главная"

msgid "Search"
msgstr "Поиск"

msgid "No equipment listed"
msgstr "Оборудование не указано"
```

```gettext
# locale/en/LC_MESSAGES/django.po

msgid "Boat Details"
msgstr "Boat Details"

msgid "Location"
msgstr "Location"

msgid "Description"
msgstr "Description"

msgid "Equipment"
msgstr "Equipment"

msgid "Cockpit"
msgstr "Cockpit"

msgid "Entertainment"
msgstr "Entertainment"

msgid "Gallery"
msgstr "Gallery"

msgid "Book Now"
msgstr "Book Now"

msgid "Add to Favorites"
msgstr "Add to Favorites"

msgid "Remove from Favorites"
msgstr "Remove from Favorites"

msgid "Contact Owner"
msgstr "Contact Owner"

msgid "Home"
msgstr "Home"

msgid "Search"
msgstr "Search"

msgid "No equipment listed"
msgstr "No equipment listed"
```

---

## 7️⃣ Compilation Script

```python
# compile_messages.py

import os
from pathlib import Path
import polib

BASE_DIR = Path(__file__).resolve().parent
LOCALE_PATH = BASE_DIR / 'locale'

LANGUAGES = ['ru', 'en', 'de', 'fr', 'es']

def compile_messages():
    """
    Compile .po files to .mo files for all supported languages.
    Uses polib library (pure Python, no GNU gettext required).
    """
    print("📦 Compiling translation files...")
    
    for lang in LANGUAGES:
        po_file = LOCALE_PATH / lang / 'LC_MESSAGES' / 'django.po'
        mo_file = LOCALE_PATH / lang / 'LC_MESSAGES' / 'django.mo'
        
        if not po_file.exists():
            print(f"⚠️  {lang}: .po file not found at {po_file}")
            continue
        
        try:
            # Load .po file
            po = polib.pofile(str(po_file))
            
            # Save as .mo file
            po.save_as_mofile(str(mo_file))
            
            print(f"✅ {lang}: django.po → django.mo")
        except Exception as e:
            print(f"❌ {lang}: Error - {str(e)}")
    
    print("✅ Translation compilation complete!")

if __name__ == '__main__':
    compile_messages()
```

---

## 8️⃣ Parser with Language Support

```python
# boats/parser.py (relevant section)

SUPPORTED_LANGUAGES = ['ru_RU', 'en_EN', 'de_DE', 'fr_FR', 'es_ES']

def parse_boataround_url(url, save_to_db=True):
    """
    Parses boat details from boataround.com for a specific language.
    
    Args:
        url: Base URL like https://www.boataround.com/ru/yachta/bavaria-cruiser-46/
        save_to_db: Whether to save to database
    
    Returns:
        dict with boat_data
    """
    language = extract_language_from_url(url)  # 'ru_RU', 'en_EN', etc.
    
    # ... parsing logic ...
    
    boat_data = {
        'boat_info': {
            'title': 'Bavaria Cruiser 46',
            'location': 'Marina di Procida',
            # ... localized data ...
        },
        'equipment': [
            {'name': 'Кондиционер'},  # Localized name
            {'name': 'Кофемашина'},
        ],
        'cockpit': [
            # ... more localized items ...
        ],
    }
    
    if save_to_db:
        save_to_cache(boat_data, language)
    
    return boat_data
```

---

## 9️⃣ Database Models (for reference)

```python
# boats/models.py (relevant sections)

class ParsedBoat(models.Model):
    """One record per boat (language-agnostic)"""
    boat_id = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)
    manufacturer = models.CharField(max_length=200)
    model = models.CharField(max_length=200)
    year = models.IntegerField()
    source_url = models.URLField()


class BoatDescription(models.Model):
    """5 records per boat (one per language)"""
    LANGUAGE_CHOICES = [
        ('ru_RU', 'Russian'),
        ('en_EN', 'English'),
        ('de_DE', 'German'),
        ('fr_FR', 'French'),
        ('es_ES', 'Spanish'),
    ]
    
    boat = models.ForeignKey(ParsedBoat, on_delete=models.CASCADE)
    language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES)
    title = models.CharField(max_length=500)
    description = models.TextField()
    location = models.CharField(max_length=300)
    marina = models.CharField(max_length=300)
    
    class Meta:
        unique_together = ('boat', 'language')


class BoatDetails(models.Model):
    """5 records per boat (one per language)"""
    LANGUAGE_CHOICES = [
        ('ru_RU', 'Russian'),
        ('en_EN', 'English'),
        ('de_DE', 'German'),
        ('fr_FR', 'French'),
        ('es_ES', 'Spanish'),
    ]
    
    boat = models.ForeignKey(ParsedBoat, on_delete=models.CASCADE)
    language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES)
    cockpit = models.JSONField(default=list)  # [{name: "...", ...}, ...]
    entertainment = models.JSONField(default=list)
    equipment = models.JSONField(default=list)
    
    class Meta:
        unique_together = ('boat', 'language')
```

---

## 🔟 Testing the Setup

```python
# test_i18n.py

from django.test import TestCase, Client
from boats.models import ParsedBoat, BoatDescription, BoatDetails

class MultiLanguageTestCase(TestCase):
    """Test multi-language setup"""
    
    def setUp(self):
        # Create test boat
        self.boat = ParsedBoat.objects.create(
            boat_id='test-boat-123',
            slug='test-boat',
            manufacturer='Bavaria',
            model='Cruiser 46',
            year=2017,
        )
        
        # Create descriptions in all languages
        BoatDescription.objects.create(
            boat=self.boat,
            language='ru_RU',
            title='Баварский крейсер',
            description='Русское описание',
            location='Марина',
        )
        
        BoatDescription.objects.create(
            boat=self.boat,
            language='en_EN',
            title='Bavaria Cruiser',
            description='English description',
            location='Marina',
        )
    
    def test_russian_boat_detail(self):
        """Test Russian boat details"""
        client = Client()
        response = client.get('/ru/boat/test-boat/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Баварский крейсер')
    
    def test_english_boat_detail(self):
        """Test English boat details"""
        client = Client()
        response = client.get('/en/boat/test-boat/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bavaria Cruiser')
```

---

✅ **Все готово для работы с многоязычной архитектурой!**
