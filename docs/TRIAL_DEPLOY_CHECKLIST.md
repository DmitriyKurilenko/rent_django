# Trial Deploy Checklist

Короткий чеклист для пробного деплоя (staging) текущей версии.

## 1) Подготовка кода
- Убедиться, что `DEBUG=False` и `ALLOWED_HOSTS` заполнен.
- Проверить `.env` на наличие:
  - `SECRET_KEY`
  - `DATABASE_URL`
  - `CELERY_BROKER_URL`
  - S3-переменных (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET_NAME`, `S3_ENDPOINT_URL`, `S3_REGION`)
- Убедиться, что debug endpoints полностью отключены/удалены в production build.

## 2) Инфраструктура
- Поднять сервисы: `db`, `redis`, `web`, `celery_worker`, `nginx`.
- Проверить healthchecks для PostgreSQL и Redis.
- Проверить, что наружу открыт только `nginx` (`80/443`).

## 3) Django команды
- `python manage.py migrate --noinput`
- `python manage.py collectstatic --noinput`
- `python manage.py check --deploy`

## 4) Smoke-тесты (обязательно)
- Авторизация/регистрация.
- Поиск лодок и переход на детальную страницу.
- Создание оффера (captain/tourist по ролям).
- Бронирование из карточки лодки и из оффера.
- Страница `my-bookings` (manager фильтр `author_q`, confirm/cancel).
- Страница `offers_list` (copy/open/delete actions).

## 5) Асинхронные задачи
- Проверить запуск Celery worker и выполнение задач парсинга.
- Проверить отсутствие постоянных ретраев/ошибок в логах.

## 6) Логи и мониторинг
- Включить ротацию логов (`web`, `celery`, `nginx`).
- Проверить, что нет 500/502 в `nginx` и Django логах.

## 7) Критерий готовности
Staging считается готовым, если:
- `check --deploy` проходит без критических ошибок,
- все smoke-тесты проходят,
- нет фатальных ошибок в логах в течение 30–60 минут.
