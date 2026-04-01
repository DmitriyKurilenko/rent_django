#!/bin/bash
# Скрипт для управления фоновыми задачами на сервере

case "$1" in
  charters)
    echo "Запуск обновления чартеров в фоне..."
    docker compose exec -d web sh -c "python manage.py update_charters --all > /tmp/update_charters.log 2>&1"
    echo "Готово. Лог: /tmp/update_charters.log"
    ;;

  meta)
    echo "Запуск обновления метаданных в фоне..."
    docker compose exec -d web sh -c "python manage.py parse_boats_parallel --skip-existing --no-cache > /tmp/parse_meta.log 2>&1"
    echo "Готово. Лог: /tmp/parse_meta.log"
    ;;

  status)
    echo "=== Проверка процессов ==="
    echo ""
    echo "--- update_charters ---"
    docker compose exec web pgrep -af update_charters || echo "Не запущен"
    echo ""
    echo "--- parse_boats_parallel ---"
    docker compose exec web pgrep -af parse_boats || echo "Не запущен"
    echo ""
    echo "=== Состояние данных ==="
    docker compose exec web python manage.py check_data_status
    ;;

  log-charters)
    docker compose exec web tail -50 /tmp/update_charters.log
    ;;

  log-meta)
    docker compose exec web tail -50 /tmp/parse_meta.log
    ;;

  log-charters-full)
    docker compose exec web cat /tmp/update_charters.log
    ;;

  log-meta-full)
    docker compose exec web cat /tmp/parse_meta.log
    ;;

  *)
    echo "Использование: ./server_tasks.sh <команда>"
    echo ""
    echo "Команды:"
    echo "  charters         - Запустить обновление чартеров в фоне"
    echo "  meta             - Запустить обновление метаданных в фоне"
    echo "  status           - Проверить процессы и состояние данных"
    echo "  log-charters     - Последние 50 строк лога чартеров"
    echo "  log-meta         - Последние 50 строк лога метаданных"
    echo "  log-charters-full - Полный лог чартеров"
    echo "  log-meta-full    - Полный лог метаданных"
    ;;
esac
