# Django i18n Integration - Полная многоязычная поддержка

## 🌍 Что было сделано

### 1. **Settings Configuration**
✅ Настроены параметры i18n в `settings.py`:
- `LANGUAGE_CODE = 'ru-ru'` - язык по умолчанию
- `LANGUAGES` - список поддерживаемых языков (ru, en, de, fr, es)
- `LOCALE_PATHS` - путь к файлам переводов
- `USE_I18N = True` - включена интернационализация

### 2. **Middleware**
✅ Добавлено `LocaleMiddleware`:
```python
'django.middleware.locale.LocaleMiddleware',  # После SessionMiddleware
```
Функция: автоматически определяет язык из:
- URL prefix (`/ru/`, `/en/`, `/de/`, `/fr/`, `/es/`)
- Cookie
- Accept-Language header

### 3. **URL Routing с i18n_patterns**
✅ Обновлены URLs в `boat_rental/urls.py`:
```python
urlpatterns += i18n_patterns(
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('', include('boats.urls')),
    prefix_default_language=True,
)
```

Результат: все URLs автоматически получают префикс языка:
- `/ru/` - Русский
- `/en/` - Английский
- `/de/` - Немецкий
- `/fr/` - Французский
- `/es/` - Испанский

### 4. **Sitemap для SEO**
✅ Создан `boats/sitemaps.py` с:
- **BoatSitemap** - все лодки на каждом языке
- **StaticSitemap** - статические страницы
- **Автоматический генератор URL** с правильными префиксами языков

Доступ:
- `/sitemap.xml` - основной sitemap
- `/robots.txt` - robots.txt

### 5. **View с поддержкой языков**
✅ Обновлена функция `boat_detail_api` в `boats/views.py`:
```python
def boat_detail_api(request, boat_id):
    current_lang = get_language()  # Получаем текущий язык
    
    # Маппируем Django языки (ru, en) в наши коды (ru_RU, en_EN)
    lang_code = LANG_MAP.get(current_lang, 'ru_RU')
    
    # Получаем локализованные данные из БД
    boat_desc = BoatDescription.objects.get(..., language=lang_code)
    boat_details = BoatDetails.objects.get(..., language=lang_code)
```

### 6. **Translation Files**
✅ Созданы `.po` файлы для всех 5 языков:
```
locale/
├── ru/LC_MESSAGES/django.po → django.mo
├── en/LC_MESSAGES/django.po → django.mo
├── de/LC_MESSAGES/django.po → django.mo
├── fr/LC_MESSAGES/django.po → django.mo
└── es/LC_MESSAGES/django.po → django.mo
```

Переводы включают:
- Navigation (Home, Search, Favorites)
- Boat details (Equipment, Services, Price)
- Actions (Book Now, Add to Favorites)
- Messages (Error, Success)

---

## 🚀 Как использовать

### **В Templates (HTML)**

```html
{% load i18n %}

<!-- Переводить текст -->
<h1>{% trans "Boat Details" %}</h1>

<!-- Множественные формы -->
<p>{% blocktrans count boats=boat_count %}
  1 boat available
{% plural %}
  {{ boats }} boats available
{% endblocktrans %}</p>

<!-- Переключение языков -->
<a href="/ru{% url 'boat_detail' boat.slug %}">Русский</a>
<a href="/en{% url 'boat_detail' boat.slug %}">English</a>
<a href="/de{% url 'boat_detail' boat.slug %}">Deutsch</a>
<a href="/fr{% url 'boat_detail' boat.slug %}">Français</a>
<a href="/es{% url 'boat_detail' boat.slug %}">Español</a>
```

### **В Python коде**

```python
from django.utils.translation import gettext as _
from django.utils.translation import get_language

# Получить текущий язык
current_lang = get_language()  # 'ru', 'en', 'de', 'fr', 'es'

# Перевести текст
message = _("Boat not found")

# Условный перевод
plural_message = ngettext(
    "1 booking",
    "%(count)d bookings",
    booking_count
) % {'count': booking_count}
```

### **В JavaScript**

```javascript
// Переключение языка
document.querySelectorAll('[data-lang]').forEach(link => {
  link.addEventListener('click', function() {
    const lang = this.dataset.lang;
    window.location.href = `/${lang}${window.location.pathname}`;
  });
});
```

---

## 📊 URL Examples

### Русский язык (по умолчанию)
- `/ru/` - главная (Русский)
- `/ru/boat/bavaria-cruiser-46/` - лодка на русском
- `/ru/search/` - поиск на русском
- `/ru/sitemap.xml` - sitemap для русского

### Английский язык
- `/en/` - главная (English)
- `/en/boat/bavaria-cruiser-46/` - boat in English
- `/en/search/` - search in English
- `/en/sitemap.xml` - sitemap for English

### Немецкий язык
- `/de/` - Startseite (Deutsch)
- `/de/boot/bavaria-cruiser-46/` - Boot auf Deutsch
- `/de/sitemap.xml` - Sitemap für Deutsch

И аналогично для Французского (`/fr/`) и Испанского (`/es/`)

---

## 🔧 Обслуживание переводов

### Добавить новый перевод
1. Отредактировать `.po` файл в `locale/<lang>/LC_MESSAGES/django.po`
2. Компилировать переводы:
   ```bash
   docker-compose exec -T web python compile_messages.py
   # Или перезагрузить контейнер
   docker-compose restart web
   ```

### Обновить все переводы после добавления новых строк
1. Найти все `_()` и `{% trans %}` в коде
2. Создать новый `.pot` файл:
   ```bash
   docker-compose exec -T web python manage.py makemessages -a
   ```
3. Обновить `.po` файлы и заново компилировать

### Компиляция .po → .mo
```bash
# Локально (если установлен gettext)
cd /Users/hvosdt/Documents/dev/rent_django
python compile_messages.py

# В Docker контейнере
docker-compose exec -T web python compile_messages.py
```

---

## ✅ Проверка работы

Протестируйте несколько URL:

```bash
# Русский
curl http://localhost:8000/ru/boat/bavaria-cruiser-46/

# Английский
curl http://localhost:8000/en/boat/bavaria-cruiser-46/

# Немецкий
curl http://localhost:8000/de/boot/bavaria-cruiser-46/

# Французский
curl http://localhost:8000/fr/bateau/bavaria-cruiser-46/

# Испанский
curl http://localhost:8000/es/bote/bavaria-cruiser-46/

# Sitemap
curl http://localhost:8000/sitemap.xml
```

Каждая версия должна возвращать локализованные данные для той лодки на том языке!

---

## 📚 Технический стек

| Компонент | Назначение |
|-----------|-----------|
| `LocaleMiddleware` | Автоматическое определение языка |
| `i18n_patterns` | URL префиксы для языков |
| `BoatDescription` | Локализованные описания |
| `BoatDetails` | Локализованное оборудование/услуги |
| `.po файлы` | Переводы UI строк |
| `Sitemap` | SEO для каждого языка |
| `polib` | Компиляция .po в .mo |

---

## 🎯 Next Steps

Если нужны дополнительные улучшения:

1. **Хлебные крошки (Breadcrumbs)** с указанием языка
2. **Language Selector Component** в шапке сайта
3. **Per-Language Analytics** (Google Analytics язык)
4. **Auto-redirect** по Accept-Language header
5. **Caching** переводов для производительности
6. **Crowdin Integration** для управления переводами командой

---

✅ **Система полностью готова к использованию!**

Каждый запрос на `/ru/`, `/en/`, `/de/`, `/fr/`, `/es/` автоматически будет получать локализованные данные.
