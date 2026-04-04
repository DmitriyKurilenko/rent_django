# Production initialization: S3, CDN and ParsedBoat

Краткие инструкции для подготовки продакшен-окружения после парсинга.

## S3 / CDN — важные детали

- Ключи в бакете формируются как `<boat_id>/<filename>` (без лишних префиксов `boats/`). Это даёт CDN-URL вида `https://<cdn-host>/yachts/<boat_id>/<filename>`.
- При загрузке объекты помечаются `public-read`, чтобы CDN и пользователи могли сразу получить к ним доступ.
- Content-Type определяется автоматически по расширению и указывается при загрузке.

## Массовая загрузка локальных изображений в S3

Команда для проверки (dry-run) и фактической загрузки уже скачанных локально изображений:

```bash
# Dry-run — посмотреть, что будет загружено
docker-compose exec web python manage.py upload_existing_images_to_s3 --dry-run

# Если всё ок — загрузить, пропуская уже существующие в бакете файлы
docker-compose exec web python manage.py upload_existing_images_to_s3 --skip-existing
```

Параметры:
- `--dry-run` — показать план, не загружая файлы
- `--skip-existing` — пропустить объекты, которые уже есть в бакете

## Экспорт `ParsedBoat` (дамп для продакшен БД)

Чтобы подготовить JSON-дамп текущих записей `ParsedBoat`:

```bash
# По умолчанию создаст boats/fixtures/parsed_boats.json
docker-compose exec web python manage.py dump_parsed_boats

# Или явно указать путь
docker-compose exec web python manage.py dump_parsed_boats --output boats/fixtures/parsed_boats.json
```

Загрузить дамп в продакшен:

```bash
python manage.py loaddata boats/fixtures/parsed_boats.json
```

Примечание: дамп не зависит от наличия изображений в S3, но удобнее загружать изображения заранее (см. раздел "Массовая загрузка").

---

Если хотите, могу вставить эти инструкции в `README.md` или обновить `BOAT_PARSING_GUIDE.md` напрямую — скажите, куда предпочитаете разместить их.
