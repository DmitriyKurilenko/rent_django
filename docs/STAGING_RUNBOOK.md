# Staging Runbook (1-page)

Операционный runbook для пробного деплоя и первичной валидации в staging.

## 1) Поднять окружение
- `docker-compose -f docker-compose.prod.yml up -d --build`
- `docker-compose -f docker-compose.prod.yml ps`

Ожидаем: `db`, `redis`, `web`, `celery_worker`, `nginx` в состоянии `healthy`/`up`.

## 2) Инициализация Django
- `docker-compose -f docker-compose.prod.yml exec web python manage.py migrate --noinput`
- `docker-compose -f docker-compose.prod.yml exec web python manage.py collectstatic --noinput`
- `docker-compose -f docker-compose.prod.yml exec web python manage.py check --deploy`

Ожидаем: `System check identified no issues`.

## 3) Smoke-тесты (обязательные)
- Регистрация и логин.
- Поиск лодки и открытие карточки лодки.
- Создание оффера по роли (captain/tourist permissions).
- Бронирование с карточки лодки.
- Бронирование из оффера (author/manager).
- `my-bookings`: manager фильтр `author_q`, confirm/cancel.
- `offers_list`: copy/open/delete.

## 4) Проверка Celery
- `docker-compose -f docker-compose.prod.yml logs -f celery_worker`

Ожидаем: задачи выполняются, нет постоянных `retry`/`Traceback`.

## 5) Проверка логов
- `docker-compose -f docker-compose.prod.yml logs --tail=200 web`
- `docker-compose -f docker-compose.prod.yml logs --tail=200 nginx`

Ожидаем: нет повторяющихся 500/502.

## 6) Rollback (если smoke не пройден)
- `docker-compose -f docker-compose.prod.yml down`
- Вернуть предыдущий стабильный образ/коммит.
- Повторить шаги 1–2 и минимальный smoke.

## 7) Критерий готовности
Staging готов к пробному релизу, если:
- deploy-check проходит,
- все smoke-тесты зелёные,
- за 30–60 минут нет критических ошибок в логах.
