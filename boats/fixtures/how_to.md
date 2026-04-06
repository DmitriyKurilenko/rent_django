# Дамп и загрузка лодок

## Дамп (split по моделям)
```bash
docker compose exec web python manage.py dump_parsed_boats --split
```

## Загрузка директории
```bash
docker compose exec web python manage.py load_parsed_boats boats/fixtures/split/
```

## Загрузка одного файла
```bash
docker compose exec web python manage.py load_parsed_boats boats/fixtures/parsed_boats.json
```

## Опции загрузки
- `--skip-existing` — пропустить существующие записи
- `--batch-size 200` — размер батча (default: 200)
- `--dry-run` — только подсчитать записи