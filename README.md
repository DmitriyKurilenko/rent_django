# BoatRental

Платформа аренды яхт и катеров на Django 5.2 LTS. Интеграция с boataround.com (REST API + HTML-парсинг), ~28 000 лодок, мультиязычность (RU/EN/DE/ES/FR).

**Версия:** 0.5.3-dev

## Стек

| Слой | Технологии |
|------|------------|
| Backend | Django 5.2 LTS, Python 3.13, Celery + Redis |
| База данных | PostgreSQL 15 |
| Frontend | Alpine.js, Tailwind CSS 4, DaisyUI 5, Font Awesome |
| Парсинг | BeautifulSoup4, requests |
| Хранение | VK Cloud S3 + CDN (`cdn2.prvms.ru`) |
| Deploy | Docker Compose, Gunicorn, Nginx |

## Быстрый старт

```bash
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
# http://localhost:8000
```

## Структура проекта

```
boats/           — основное приложение (модели, вьюхи, парсер, API-клиент, Celery-таски)
accounts/        — пользователи и роли (tourist / captain / manager / admin)
templates/       — Django-шаблоны (base.html, boats/, accounts/)
static/          — CSS, JS, шрифты, изображения
locale/          — переводы (ru, en, de, es, fr)
docs/            — документация проекта
.github/         — copilot-instructions.md (архитектура для AI-агентов)
```

## Ключевые модели

| Модель | Назначение |
|--------|-----------|
| `ParsedBoat` | Кеш HTML-парсинга (boat_id, slug, boat_data JSON, preview_cdn_url) |
| `BoatTechnicalSpecs` | Индексированные характеристики (каюты, длина, скорость) |
| `BoatDescription` | Мультиязычные описания (title, location, marina, country) |
| `BoatDetails` | Оборудование/экстра/сервисы по языкам (JSON) |
| `BoatPrice` | Цены по валютам (EUR, USD, GBP, RUB и др.) |
| `BoatGallery` | Галерея фото с CDN URL |
| `Offer` | Коммерческие предложения (tourist / captain), UUID для шаринга |

## Основные команды

```bash
# Парсинг лодок (параллельно, 5 воркеров)
docker compose exec web python manage.py parse_boats_parallel --workers 5

# Парсинг конкретного направления
docker compose exec web python manage.py parse_boats_parallel --destination turkey --workers 10

# Инкрементальное обновление (пропустить существующие)
docker compose exec web python manage.py parse_boats_parallel --skip-existing --workers 5

# Массовая загрузка превью на CDN (без полного парсинга)
docker compose exec web python manage.py cache_previews --workers 5

# Бекап кеша в JSON
docker compose exec web python manage.py dump_parsed_boats --split

# Загрузка fixture
docker compose exec web python manage.py load_parsed_boats boats/fixtures/split/

# Логи Celery
docker compose logs -f celery_worker
```

## Роли пользователей

| Роль | Возможности |
|------|-------------|
| tourist | Поиск, избранное |
| captain | + Офферы для капитанов |
| manager | + Туристические офферы |
| admin | Полный доступ |

## CSS-сборка

Tailwind CSS 4 + DaisyUI 5.  Сборка — только через Docker:

```bash
docker run --rm -v "$(pwd)":/app -w /app node:18-alpine sh -c "npm install && npx tailwindcss -i assets/css/tailwind.input.css -o static/css/styles.css --minify"
```

В production CSS собирается автоматически в `Dockerfile` (stage `assets`).

## Документация

- [.github/copilot-instructions.md](.github/copilot-instructions.md) — архитектура, паттерны, ключевые файлы
- [docs/DECISIONS.md](docs/DECISIONS.md) — архитектурные решения
- [docs/DEV_LOG.md](docs/DEV_LOG.md) — лог разработки
- [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) — известные проблемы
- [docs/FAQ.md](docs/FAQ.md) — FAQ и траблшутинг
- [docs/I18N_ARCHITECTURE.md](docs/I18N_ARCHITECTURE.md) — мультиязычность
- [docs/I18N_QUICK_REFERENCE.md](docs/I18N_QUICK_REFERENCE.md) — быстрая справка i18n
- [docs/STAGING_RUNBOOK.md](docs/STAGING_RUNBOOK.md) — staging-операции
- [docs/RELEASE_NOTES.md](docs/RELEASE_NOTES.md) — история изменений (для пользователей)
- [DEPLOYMENT_CHECKLIST_FINAL.md](DEPLOYMENT_CHECKLIST_FINAL.md) — чеклист деплоя

## Лицензия

MIT — см. [LICENSE](LICENSE).
