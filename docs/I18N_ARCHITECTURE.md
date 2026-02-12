# 🌍 Многоязычная архитектура платформы BoatRental

## 📊 Общая архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT REQUEST                           │
│              /ru/, /en/, /de/, /fr/, /es/                      │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│              LocaleMiddleware (Django)                          │
│   ✅ Determines language from URL prefix                        │
│   ✅ Sets language in request.LANGUAGE_CODE                    │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│           i18n_patterns URL Router                              │
│   /ru/boat/bavaria-cruiser-46/ → boat_detail_api(lang='ru')   │
│   /en/boat/bavaria-cruiser-46/ → boat_detail_api(lang='en')   │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│      Views (boat_detail_api in boats/views.py)                 │
│   current_lang = get_language()  # 'ru', 'en', 'de', 'fr', 'es'│
│   lang_code = LANG_MAP[current_lang]  # 'ru_RU', 'en_EN', etc. │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌──────────────────────┬──────────────────────────────────────────┐
│                      │                                          │
▼                      ▼                                          ▼
┌─────────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  BoatDescription    │ │  BoatDetails     │ │  BoatPrice       │
│  (localized data)   │ │ (equipment,      │ │ (prices in EUR)  │
│                     │ │  services)       │ │                  │
│ ru_RU, en_EN,       │ │ ru_RU, en_EN,    │ │ Fixed per boat   │
│ de_DE, fr_FR,       │ │ de_DE, fr_FR,    │ │ (not localized)  │
│ es_ES               │ │ es_ES            │ │                  │
└─────────────────────┘ └──────────────────┘ └──────────────────┘
│                                │
└───────────────────┬────────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │   Template Engine     │
        │   (boats/detail.html) │
        │                       │
        │ {% trans "..." %}     │
        │ {% load i18n %}       │
        └───────────────────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │  JSON Response/HTML   │
        │  (Localized Content)  │
        └───────────────────────┘
```

---

## 🗄️ Структура БД для локализации

### ParsedBoat (один на каждую лодку)
```python
ParsedBoat:
  - boat_id: "5c97405d8b4c877d121d8e9e" (уникальный на boataround.com)
  - slug: "bavaria-cruiser-46"
  - manufacturer: "Bavaria"
  - model: "Cruiser 46"
  - year: 2017
  - source_url: "https://www.boataround.com/..."
```

### BoatDescription (5 записей на лодку, по одной на язык)
```python
BoatDescription:
  - boat: ForeignKey(ParsedBoat)
  - language: "ru_RU" | "en_EN" | "de_DE" | "fr_FR" | "es_ES"
  - title: "Парус. яхта Баварія..."  # локализованное название
  - description: "3-кабинная парусная яхта..."  # локализованное описание
  - location: "Марина ди Процида"  # локализованное местоположение
  - marina: "Marina di Procida"  # локализованная марина
```

### BoatDetails (5 записей на лодку, по одной на язык)
```python
BoatDetails:
  - boat: ForeignKey(ParsedBoat)
  - language: "ru_RU" | "en_EN" | "de_DE" | "fr_FR" | "es_ES"
  - cockpit: [{"name": "Кондиционер"}, {"name": "Кофемашина"}, ...]
  - entertainment: [{"name": "Платформа для купания"}, ...]
  - equipment: [{"name": "Автопилот"}, ...]
  - extras: [...]  # локализованные услуги
  - additional_services: [...]
  - delivery_extras: [...]  # локализованные услуги доставки
  - not_included: [...]
```

### BoatGallery (общие для всех языков)
```python
BoatGallery:
  - boat: ForeignKey(ParsedBoat)
  - image_url: "https://cdn2.prvms.ru/yachts/..."
  - order: 1, 2, 3, ...
  
  # Фото одинаковые для всех языков (логично)
```

---

## 🌐 Маппинг языков

| Django i18n | Наш код | boataround.com | URL Prefix |
|-------------|---------|----------------|-----------|
| `ru` | `ru_RU` | `/ru/yachta/` | `/ru/` |
| `en` | `en_EN` | `/us/boat/` | `/en/` |
| `de` | `de_DE` | `/de/boot/` | `/de/` |
| `fr` | `fr_FR` | `/fr/bateau/` | `/fr/` |
| `es` | `es_ES` | `/es/bote/` | `/es/` |

Маппинг реализован в `boats/views.py`:
```python
LANG_MAP = {
    'ru': 'ru_RU',
    'en': 'en_EN',
    'de': 'de_DE',
    'fr': 'fr_FR',
    'es': 'es_ES',
}
```

---

## 🔄 Процесс загрузки лодки (Multi-language Flow)

```
1. USER REQUEST
   GET /ru/boat/bavaria-cruiser-46/
   
2. LocaleMiddleware
   ✅ Парсит prefix /ru/
   ✅ Устанавливает request.LANGUAGE_CODE = 'ru'
   
3. URL Router
   ✅ i18n_patterns выбирает правильный URL pattern
   ✅ Вызывает boat_detail_api(request, slug='bavaria-cruiser-46')
   
4. View Logic
   ```python
   current_lang = get_language()  # 'ru'
   lang_code = LANG_MAP['ru']     # 'ru_RU'
   
   # Получаем данные ДЛЯ КОНКРЕТНОГО ЯЗЫКА
   boat_desc = BoatDescription.objects.get(
       boat__slug='bavaria-cruiser-46',
       language='ru_RU'  # ← KEY: только русские данные
   )
   boat_details = BoatDetails.objects.get(
       boat__slug='bavaria-cruiser-46',
       language='ru_RU'
   )
   ```
   
5. Template Rendering
   ✅ Шаблон получает локализованные данные
   ✅ {% trans %} теги переводят UI строки (из .po файлов)
   
6. Response
   HTTP 200 OK
   Content-Type: text/html; charset=utf-8
   <h1>Bavaria Cruiser 46 | NN</h1>
   <p>3-кабинная парусная яхта...</p>
   <p>Кокпит: Кондиционер, Кофемашина...</p>
```

---

## 🎯 SEO & Sitemap

### Sitemap Структура
```
/sitemap.xml
├── /ru/boat/bavaria-cruiser-46/  (priority: 0.8, changefreq: weekly)
├── /ru/boat/lagoon-380-s2/       (priority: 0.8, changefreq: weekly)
├── /ru/search/                   (priority: 0.9, changefreq: weekly)
├── /ru/                          (priority: 1.0, changefreq: daily)
│
├── /en/boat/bavaria-cruiser-46/
├── /en/boat/lagoon-380-s2/
├── /en/search/
├── /en/
│
├── /de/boot/bavaria-cruiser-46/
├── /de/boot/lagoon-380-s2/
├── /de/search/
├── /de/
│
└── ... (fr, es аналогично)
```

### Canonical Tags (рекомендуемо добавить)
```html
<!-- Русский -->
<link rel="canonical" href="https://example.com/ru/boat/bavaria-cruiser-46/" />

<!-- Английский -->
<link rel="canonical" href="https://example.com/en/boat/bavaria-cruiser-46/" />

<!-- Альтернативные языки -->
<link rel="alternate" hreflang="ru" href="https://example.com/ru/boat/bavaria-cruiser-46/" />
<link rel="alternate" hreflang="en" href="https://example.com/en/boat/bavaria-cruiser-46/" />
<link rel="alternate" hreflang="de" href="https://example.com/de/boot/bavaria-cruiser-46/" />
<link rel="alternate" hreflang="fr" href="https://example.com/fr/bateau/bavaria-cruiser-46/" />
<link rel="alternate" hreflang="es" href="https://example.com/es/bote/bavaria-cruiser-46/" />
```

---

## 📈 Производительность & Кэширование

### Оптимизация
1. **Per-language caching** - кэшировать локализованные данные отдельно
2. **Translation caching** - Django автоматически кэширует .mo файлы
3. **Database indexing** - индекс на (boat, language) в BoatDescription/BoatDetails
4. **CDN for images** - фото (images) одинаковые, можно кэшировать глобально

### Рекомендуемая конфигурация кэша
```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://redis:6379/0',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'KEY_PREFIX': 'boatrental',
        'TIMEOUT': 60 * 60 * 24,  # 24 часа
    }
}

# Per-language cache keys
cache_key = f"boat:{slug}:{lang_code}"
```

---

## 🚀 Scalability

Если понадобится масштабировать:

### Текущий уровень (≤100k лодок)
✅ **Подходит:**
- Per-boat localization ✓
- 5 языков ✓
- PostgreSQL ✓
- Redis cache ✓

### Средний уровень (100k - 1M лодок)
Нужно добавить:
- Elasticsearch для полнотекстового поиска на разных языках
- Horizontal sharding по языкам
- Geo-location кэширование

### Большой уровень (>1M лодок)
Нужно:
- Dedicated translation service (разные сервера для каждого языка)
- GraphQL для параллельной загрузки разных языков
- Machine translation (Google Translate API) как fallback

---

## ✅ Checklist Implementation

- [x] Django i18n конфигурация
- [x] LocaleMiddleware
- [x] i18n_patterns в URLs
- [x] BoatDescription с поддержкой языков
- [x] BoatDetails с поддержкой языков
- [x] View с логикой локализации
- [x] .po файлы для 5 языков
- [x] Sitemap с поддержкой языков
- [x] compile_messages.py для разработки
- [ ] Template tags для i18n в detail.html
- [ ] Language selector в UI
- [ ] Breadcrumbs с языком
- [ ] Canonical tags в templates
- [ ] Per-language analytics

---

## 📚 Дополнительные ресурсы

- [Django i18n Documentation](https://docs.djangoproject.com/en/4.2/topics/i18n/)
- [URL Internationalization](https://docs.djangoproject.com/en/4.2/topics/i18n/translation/#how-django-discovers-language-preference)
- [Translation Management](https://docs.djangoproject.com/en/4.2/topics/i18n/translation/)

---

✅ **АРХИТЕКТУРА ПОЛНОСТЬЮ ГОТОВА!**
