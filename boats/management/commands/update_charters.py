"""
Management command: присваивает чартерные компании лодкам из API.

Сканирует API Boataround, для каждой лодки:
- Находит соответствующий ParsedBoat в БД
- Создаёт/обновляет Charter из API-данных
- Привязывает charter к ParsedBoat

По умолчанию обновляет только лодки без чартера (--only-missing).
С флагом --all обновляет все лодки.
"""
import sys
import time

from django.core.management.base import BaseCommand
from requests.exceptions import ConnectionError, Timeout

from boats.boataround_api import BoataroundAPI
from boats.models import Charter, ParsedBoat

MAX_RETRIES = 5
RETRY_DELAYS = [10, 30, 60, 120, 300]  # секунды между попытками


class Command(BaseCommand):
    help = "Присваивает чартерные компании лодкам из API Boataround"

    def add_arguments(self, parser):
        parser.add_argument(
            "--destination",
            default=None,
            help="Направление (slug). Без указания — весь каталог.",
        )
        parser.add_argument(
            "--max-pages",
            type=int,
            default=None,
            help="Максимум страниц API для сканирования.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            dest="update_all",
            help="Обновить чартер у ВСЕХ лодок (по умолчанию — только без чартера).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показать изменения без записи в БД.",
        )

    def handle(self, *args, **options):
        destination = options["destination"]
        max_pages = options["max_pages"]
        update_all = options["update_all"]
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("=== DRY RUN ==="))

        # Статистика до старта
        total_boats = ParsedBoat.objects.count()
        without_charter = ParsedBoat.objects.filter(charter__isnull=True).count()
        self.stdout.write(
            f"Лодок в БД: {total_boats}, без чартера: {without_charter}"
        )

        if not update_all and without_charter == 0:
            self.stdout.write(self.style.SUCCESS("Все лодки уже имеют чартер."))
            return

        # Slugs лодок, которым нужен чартер
        if update_all:
            target_slugs = set(
                ParsedBoat.objects.values_list("slug", flat=True)
            )
        else:
            target_slugs = set(
                ParsedBoat.objects.filter(charter__isnull=True).values_list(
                    "slug", flat=True
                )
            )

        self.stdout.write(f"Целевых лодок для обновления: {len(target_slugs)}")

        # Сканируем API
        self.stdout.write("Сканирование API...")
        charter_data = {}  # slug -> {charter_id, charter_name, charter_logo, charter_rank}
        page = 1
        total_pages_api = None
        scanned = 0
        label = destination or "весь каталог"

        while True:
            retries = 0
            results = None

            while retries <= MAX_RETRIES:
                try:
                    results = BoataroundAPI.search(
                        destination=destination,
                        page=page,
                        limit=18,
                        lang="en_EN",
                    )
                    break  # Успех — выходим из retry-цикла
                except (ConnectionError, Timeout, OSError) as e:
                    retries += 1
                    if retries > MAX_RETRIES:
                        self.stderr.write(
                            self.style.ERROR(
                                f"\n✗ Стр.{page}: {MAX_RETRIES} попыток "
                                f"исчерпано, пропускаю. Ошибка: {e}"
                            )
                        )
                        results = None
                        break
                    delay = RETRY_DELAYS[min(retries - 1, len(RETRY_DELAYS) - 1)]
                    self.stderr.write(
                        self.style.WARNING(
                            f"\n⚠ Стр.{page}: сетевая ошибка ({e}). "
                            f"Попытка {retries}/{MAX_RETRIES} через {delay}с..."
                        )
                    )
                    time.sleep(delay)
                except Exception as e:
                    self.stderr.write(
                        self.style.ERROR(
                            f"\n✗ Стр.{page}: непредвиденная ошибка: {e}"
                        )
                    )
                    results = None
                    break

            if not results or not results.get("boats"):
                if retries > MAX_RETRIES:
                    # Сетевая ошибка — пробуем следующую страницу
                    page += 1
                    if max_pages and page > max_pages:
                        break
                    continue
                # Пустой ответ — конец каталога
                break

            if total_pages_api is None:
                total_pages_api = int(results.get("totalPages") or 1)

            for boat in results["boats"]:
                slug = boat.get("slug")
                if not slug:
                    continue
                charter_id = boat.get("charter_id", "")
                charter_name = boat.get("charter", "")
                if not charter_id or not charter_name:
                    continue

                # Собираем данные только для целевых лодок
                if slug in target_slugs:
                    charter_data[slug] = {
                        "charter_id": charter_id,
                        "charter_name": charter_name,
                        "charter_logo": boat.get("charter_logo", ""),
                        "charter_rank": boat.get("charter_rank", {}),
                    }

            scanned += len(results["boats"])

            # Прогресс
            effective_total = total_pages_api
            if max_pages and max_pages > 0:
                effective_total = min(effective_total, max_pages)

            if page % 10 == 0 or page == 1:
                sys.stdout.write(
                    f"\r   🔍 {label}... стр. {page}/{effective_total}, "
                    f"найдено чартеров для целевых: {len(charter_data)}"
                )
                sys.stdout.flush()

            if page >= effective_total:
                break

            page += 1

        self.stdout.write(
            f"\n   Просканировано: {scanned} лодок, {page} стр."
        )
        self.stdout.write(
            f"   Найдено чартеров для целевых лодок: {len(charter_data)}"
        )

        if not charter_data:
            self.stdout.write(
                self.style.WARNING("Нет данных для обновления.")
            )
            return

        # Применяем чартеры
        charter_cache = {}  # charter_id -> Charter instance
        updated = 0
        created_charters = 0

        for slug, data in charter_data.items():
            charter_id = data["charter_id"]
            charter_name = data["charter_name"]

            # Получаем или создаём Charter
            if charter_id not in charter_cache:
                rank = data.get("charter_rank", {})
                charter_obj, was_created = Charter.objects.update_or_create(
                    charter_id=charter_id,
                    defaults={
                        "name": charter_name,
                        "logo": data.get("charter_logo", ""),
                        "rank_score": rank.get("score"),
                        "rank_place": rank.get("place"),
                        "rank_out_of": rank.get("out_of"),
                        "rank_reviews_count": rank.get("count"),
                    },
                )
                charter_cache[charter_id] = charter_obj
                if was_created:
                    created_charters += 1

            charter_obj = charter_cache[charter_id]

            if dry_run:
                self.stdout.write(
                    f"  [DRY] {slug} → {charter_name} "
                    f"(комиссия: {charter_obj.commission}%)"
                )
            else:
                ParsedBoat.objects.filter(slug=slug).update(charter=charter_obj)

            updated += 1

        # Итоги
        after_without = ParsedBoat.objects.filter(charter__isnull=True).count()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Итоги ==="))
        self.stdout.write(f"  Чартеров создано: {created_charters}")
        self.stdout.write(
            f"  Уникальных чартеров использовано: {len(charter_cache)}"
        )
        self.stdout.write(f"  Лодок обновлено: {updated}")
        self.stdout.write(f"  Без чартера осталось: {after_without}")

        if after_without > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"  ⚠ {after_without} лодок остались без чартера "
                    "(нет в API или API не вернул charter_id)."
                )
            )
