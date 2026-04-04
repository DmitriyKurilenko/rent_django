# 🔗 Быстрая справка по многоязычной архитектуре

## 📍 Где искать код

| Компонент | Файл | Строки | Описание |
|-----------|------|--------|---------|
| **i18n Config** | `boat_rental/settings.py` | 46-56, 81-87, 133-145 | LANGUAGES, LocaleMiddleware, LOCALE_PATHS |
| **URL Routing** | `boat_rental/urls.py` | 1-25 | i18n_patterns, Sitemap, sitemaps dict |
| **Views** | `boats/views.py` | 1-20, 320-380 | Imports, boat_detail_api с LANG_MAP |
| **Sitemap** | `boats/sitemaps.py` | Весь файл | BoatSitemap, StaticSitemap классы |
| **Translations** | `locale/{lang}/LC_MESSAGES/django.po` | Все | msgid/msgstr пары для UI |
| **Parser** | `boats/parser.py` | ~1243 | SUPPORTED_LANGUAGES list |
| **Compilation** | `compile_messages.py` | Весь файл | .po → .mo компиляция |

---

## 🎯 Основные концепции

### 1️⃣ URL Routing Flow
```
Request: /ru/boat/bavaria-cruiser-46/
         ↓
    LocaleMiddleware парсит /ru/
         ↓
    request.LANGUAGE_CODE = 'ru'
         ↓
    i18n_patterns роутит на правильный view
         ↓
    boat_detail_api(request, boat_id) вызывается
         ↓
    View делает get_language() → 'ru'
         ↓
    Смотрит LANG_MAP['ru'] → 'ru_RU'
         ↓
    Запрашивает BoatDescription where language='ru_RU'
         ↓
    Возвращает русские данные
```

### 2️⃣ Database Query Pattern
```python
# ✅ ПРАВИЛЬНО (получит только русские данные)
boat = BoatDescription.objects.get(
    boat__slug='bavaria-cruiser-46',
    language='ru_RU'  # ← Обязательно фильтровать по языку!
)

# ❌ НЕПРАВИЛЬНО (вернет первую попавшуюся запись)
boat = BoatDescription.objects.get(boat__slug='bavaria-cruiser-46')
```

### 3️⃣ Template Pattern
```html
{% load i18n %}

{# Переводимые строки (из .po файлов) #}
<h1>{% trans "Boat Details" %}</h1>

{# Локализованные данные из БД #}
<h2>{{ boat_description.title }}</h2>  {# "Bavaria Cruiser 46" на текущем языке #}

{# Блоки с контекстом #}
{% blocktrans with name=boat.manufacturer %}
  This yacht is manufactured by {{ name }}
{% endblocktrans %}
```

### 4️⃣ Language Map (ВАЖНО!)
```python
LANG_MAP = {
    'ru': 'ru_RU',    # Django lang code → Internal lang code
    'en': 'en_EN',
    'de': 'de_DE',
    'fr': 'fr_FR',
    'es': 'es_ES',
}
```

---

## 🛠️ Частые операции

### Добавить новый язык
1. Добавить в SUPPORTED_LANGUAGES в `boats/parser.py`
2. Добавить в LANGUAGES в `boat_rental/settings.py`
3. Добавить в LANG_MAP в `boats/views.py`
4. Создать `locale/{lang}/LC_MESSAGES/` директорию
5. Создать `django.po` файл с msgid/msgstr
6. Запустить `python compile_messages.py`

### Обновить переводы
```bash
# 1. Отредактировать locale/{lang}/LC_MESSAGES/django.po
# msgid "Boat Details"
# msgstr "Детали лодки"

# 2. Скомпилировать
python compile_messages.py

# 3. Перезагрузить Django (автоматически подхватит .mo файлы)
```

### Перепарсить лодку на всех языках
```bash
docker-compose exec web python manage.py parse_boats_parallel --workers 1 --max-pages 1
# Автоматически парсит SUPPORTED_LANGUAGES и сохраняет в BoatDescription/BoatDetails
```

### Проверить, какие языки в БД
```bash
docker-compose exec web python manage.py shell
>>> from boats.models import BoatDescription
>>> BoatDescription.objects.values('language').distinct()
<QuerySet [{'language': 'ru_RU'}, {'language': 'en_EN'}, ...]>
```

---

## 🚨 Common Pitfalls

### ❌ Забыли LocaleMiddleware
```python
# settings.py
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    # ← LocaleMiddleware ДОЛЖНА быть здесь! (после Session, перед Common)
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
]
```

### ❌ Забыли i18n_patterns
```python
# urls.py - НЕПРАВИЛЬНО (работает, но без локализации)
urlpatterns = [
    path('boat/<slug:boat_id>/', boat_detail_api),
]

# urls.py - ПРАВИЛЬНО (с языковыми префиксами)
urlpatterns = i18n_patterns(
    path('boat/<slug:boat_id>/', boat_detail_api),
    prefix_default_language=True,
)
```

### ❌ Вернули не правильный язык
```python
# НЕПРАВИЛЬНО - всегда русский!
boat = BoatDescription.objects.get(
    boat__slug='bavaria-cruiser-46',
    language='ru_RU'  # ← HARDCODED! Это ошибка!
)

# ПРАВИЛЬНО - текущий язык
current_lang = get_language()  # 'ru', 'en', etc.
lang_code = LANG_MAP[current_lang]
boat = BoatDescription.objects.get(
    boat__slug='bavaria-cruiser-46',
    language=lang_code  # ← Зависит от URL!
)
```

### ❌ Забыли скомпилировать .po
```bash
# Отредактировали locale/ru/LC_MESSAGES/django.po
# Но забыли скомпилировать!

# Результат: Изменения не видны в приложении!

# Решение:
python compile_messages.py
```

---

## 📊 Data Structure Example

```
ParsedBoat: "bavaria-cruiser-46"
├─ BoatDescription (ru_RU)
│  ├─ title: "Парусная яхта Bavaria Cruiser 46"
│  ├─ description: "Комфортная 3-кабинная..."
│  └─ location: "Марина ди Процида"
├─ BoatDescription (en_EN)
│  ├─ title: "Sailing Yacht Bavaria Cruiser 46"
│  ├─ description: "Comfortable 3-cabin..."
│  └─ location: "Marina di Procida"
├─ BoatDescription (de_DE)
│  ├─ title: "Segelschiff Bayern Cruiser 46"
│  ├─ description: "Komfortabler 3-Kabinen..."
│  └─ location: "Marina di Procida"
├─ BoatDescription (fr_FR)
│  ├─ title: "Voilier Bavière Croiseur 46"
│  ├─ description: "Confortable 3-cabines..."
│  └─ location: "Marina di Procida"
└─ BoatDescription (es_ES)
   ├─ title: "Velero Bavaria Crucero 46"
   ├─ description: "Cómodo velero de 3..."
   └─ location: "Marina di Procida"

├─ BoatDetails (ru_RU)
│  ├─ cockpit: [{name: "Кондиционер"}, {name: "Кофемашина"}]
│  └─ equipment: [{name: "Автопилот"}]
├─ BoatDetails (en_EN)
│  ├─ cockpit: [{name: "Air conditioning"}, {name: "Coffee machine"}]
│  └─ equipment: [{name: "Autopilot"}]
... (de, fr, es)

└─ BoatGallery
   ├─ image_url: "https://cdn2.prvms.ru/..."
   ├─ image_url: "https://cdn2.prvms.ru/..."
   └─ ... (фото одинаковые для всех языков!)
```

---

## 🔍 Debugging Checklist

Если лодка не отображается на нужном языке:

1. ✅ Проверить URL: `/ru/boat/bavaria-cruiser-46/` или `/en/boat/...`?
2. ✅ Проверить `request.LANGUAGE_CODE` в view
3. ✅ Проверить LANG_MAP маппинг
4. ✅ Проверить, есть ли BoatDescription для этого language
   ```bash
   docker-compose exec web python manage.py shell
   >>> from boats.models import BoatDescription
   >>> BoatDescription.objects.filter(boat__slug='bavaria-cruiser-46', language='ru_RU')
   # Должна быть 1 запись
   ```
5. ✅ Проверить, что .po файлы скомпилированы в .mo
   ```bash
   ls locale/ru/LC_MESSAGES/
   # Должны быть: django.po и django.mo
   ```

---

## 📝 Шпаргалка команд

```bash
# Парсить 5 лодок (все языки)
docker-compose exec web python manage.py parse_boats_parallel --workers 1 --max-pages 1

# Парсить 100 лодок асинхронно
docker-compose exec web python manage.py parse_boats_parallel --workers 5

# Скомпилировать переводы
python compile_messages.py

# Проверить какие языки в БД
docker-compose exec web python manage.py shell
>>> from boats.models import BoatDescription
>>> BoatDescription.objects.values('language').distinct()

# Очистить все лодки
docker-compose exec web python manage.py shell
>>> from boats.models import ParsedBoat; ParsedBoat.objects.all().delete()

# Проверить sitemap
docker-compose exec web python manage.py shell
>>> from boats.sitemaps import BoatSitemap
>>> sitemap = BoatSitemap()
>>> len(sitemap.items())  # Сколько лодок в sitemap

# Запустить локально
docker-compose up -d
docker-compose logs -f web
```

---

✅ **Всё, что нужно для работы с многоязычностью!**
