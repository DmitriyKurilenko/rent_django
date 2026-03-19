import re
import csv
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from boats.models import Charter


class Command(BaseCommand):
    help = "Импортирует комиссии чартерных компаний из XLSX файла"
    LEGAL_SUFFIXES = {
        "doo",
        "ltd",
        "limited",
        "co",
        "company",
        "sl",
        "srl",
        "sro",
        "llc",
        "inc",
        "gmbh",
        "plc",
        "bv",
        "nv",
        "oy",
        "ab",
        "as",
        "aps",
        "spa",
        "sa",
        "ag",
        "pte",
    }

    NAME_HEADER_ALIASES = {
        "name",
        "charter",
        "charter name",
        "company",
        "название",
        "чартер",
        "компания",
    }
    COMMISSION_HEADER_ALIASES = {
        "commission",
        "commission (%)",
        "комиссия",
        "комиссия (%)",
    }

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default="charters.xlsx",
            help="Путь к XLSX файлу (по умолчанию: charters.xlsx)",
        )
        parser.add_argument(
            "--create-missing",
            action="store_true",
            help="Создавать чартеры, которых нет в БД",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показать изменения без записи в БД",
        )
        parser.add_argument(
            "--loaded-report",
            default="",
            help="Путь к CSV-отчету по загруженным строкам",
        )
        parser.add_argument(
            "--not-loaded-report",
            default="",
            help="Путь к CSV-отчету по незагруженным строкам",
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"]).expanduser()
        create_missing = bool(options["create_missing"])
        dry_run = bool(options["dry_run"])
        loaded_report_path, not_loaded_report_path = self._resolve_report_paths(
            file_path=file_path,
            loaded_report_option=options.get("loaded_report", ""),
            not_loaded_report_option=options.get("not_loaded_report", ""),
        )

        if not file_path.exists():
            raise CommandError(f"Файл не найден: {file_path}")
        if file_path.suffix.lower() != ".xlsx":
            raise CommandError(f"Ожидается .xlsx файл, получен: {file_path.name}")

        headers, rows = self._read_xlsx(file_path)
        if not headers:
            raise CommandError("XLSX не содержит заголовков (первая строка пуста)")

        name_header = self._resolve_header(headers, self.NAME_HEADER_ALIASES)
        commission_header = self._resolve_header(headers, self.COMMISSION_HEADER_ALIASES)

        if not name_header or not commission_header:
            raise CommandError(
                "Не найдены обязательные колонки. "
                f"Нужны Name/Commission (или алиасы), найдено: {headers}"
            )

        (
            charter_by_name,
            ambiguous_exact_keys,
            charter_by_compact_name,
            ambiguous_compact_keys,
            charter_by_squashed_compact_name,
            ambiguous_squashed_compact_keys,
        ) = self._build_charter_indexes()
        stats = {
            "processed": 0,
            "updated": 0,
            "created": 0,
            "unchanged": 0,
            "missing": 0,
            "ambiguous": 0,
            "invalid": 0,
            "skipped_default_commission": 0,
        }
        loaded_rows = []
        not_loaded_rows = []

        for row in rows:
            row_number = row["__row__"]
            raw_name = str(row.get(name_header, "")).strip()
            clean_name = self._clean_name(raw_name)
            raw_commission = row.get(commission_header, "")

            if not clean_name:
                continue

            stats["processed"] += 1

            try:
                commission_value, was_rounded = self._parse_commission(raw_commission)
            except ValueError as exc:
                stats["invalid"] += 1
                reason = str(exc)
                self.stdout.write(self.style.WARNING(f"Строка {row_number}: {reason}"))
                not_loaded_rows.append(
                    self._build_not_loaded_row(
                        row_number=row_number,
                        raw_name=clean_name,
                        raw_commission=raw_commission,
                        reason=reason,
                    )
                )
                continue

            if was_rounded:
                self.stdout.write(
                    self.style.WARNING(
                        f"Строка {row_number}: комиссия '{raw_commission}' округлена до {commission_value}%"
                    )
                )

            if commission_value == 20:
                stats["skipped_default_commission"] += 1
                continue

            normalized_name = self._normalize_name(clean_name)
            if normalized_name in ambiguous_exact_keys:
                stats["ambiguous"] += 1
                reason = "ambiguous_exact_name"
                self.stdout.write(
                    self.style.WARNING(
                        f"Строка {row_number}: неоднозначное совпадение по имени '{clean_name}' после нормализации"
                    )
                )
                not_loaded_rows.append(
                    self._build_not_loaded_row(
                        row_number=row_number,
                        raw_name=clean_name,
                        raw_commission=raw_commission,
                        reason=reason,
                        details="multiple charters share normalized key",
                    )
                )
                continue

            charter = charter_by_name.get(normalized_name)
            if charter is None:
                compact_name = self._normalize_compact_name(clean_name)
                if compact_name in ambiguous_compact_keys:
                    stats["ambiguous"] += 1
                    reason = "ambiguous_compact_name"
                    self.stdout.write(
                        self.style.WARNING(
                            f"Строка {row_number}: неоднозначное совпадение по имени '{clean_name}' после удаления пробелов"
                        )
                    )
                    not_loaded_rows.append(
                        self._build_not_loaded_row(
                            row_number=row_number,
                            raw_name=clean_name,
                            raw_commission=raw_commission,
                            reason=reason,
                            details="multiple charters share compact key",
                        )
                    )
                    continue
                charter = charter_by_compact_name.get(compact_name)
                if charter is None:
                    squashed_compact_name = self._normalize_squashed_compact_name(clean_name)
                    if squashed_compact_name in ambiguous_squashed_compact_keys:
                        stats["ambiguous"] += 1
                        reason = "ambiguous_squashed_compact_name"
                        self.stdout.write(
                            self.style.WARNING(
                                f"Строка {row_number}: неоднозначное совпадение по имени '{clean_name}' после схлопывания повторов"
                            )
                        )
                        not_loaded_rows.append(
                            self._build_not_loaded_row(
                                row_number=row_number,
                                raw_name=clean_name,
                                raw_commission=raw_commission,
                                reason=reason,
                                details="multiple charters share squashed compact key",
                            )
                        )
                        continue
                    charter = charter_by_squashed_compact_name.get(squashed_compact_name)

            if charter:
                if charter.commission == commission_value:
                    stats["unchanged"] += 1
                    loaded_rows.append(
                        self._build_loaded_row(
                            row_number=row_number,
                            raw_name=clean_name,
                            raw_commission=raw_commission,
                            status="unchanged",
                            charter=charter,
                            previous_commission=charter.commission,
                            new_commission=commission_value,
                            was_rounded=was_rounded,
                        )
                    )
                    continue

                previous_commission = charter.commission
                if not dry_run:
                    charter.commission = commission_value
                    charter.save()
                stats["updated"] += 1
                loaded_rows.append(
                    self._build_loaded_row(
                        row_number=row_number,
                        raw_name=clean_name,
                        raw_commission=raw_commission,
                        status="dry_run_update" if dry_run else "updated",
                        charter=charter,
                        previous_commission=previous_commission,
                        new_commission=commission_value,
                        was_rounded=was_rounded,
                    )
                )
                continue

            if create_missing:
                if not dry_run:
                    charter = Charter.objects.create(
                        charter_id=self._build_unique_charter_id(raw_name),
                        name=clean_name,
                        commission=commission_value,
                    )
                    existing_exact = charter_by_name.get(normalized_name)
                    if existing_exact and existing_exact.id != charter.id:
                        ambiguous_exact_keys.add(normalized_name)
                        charter_by_name.pop(normalized_name, None)
                    elif normalized_name not in ambiguous_exact_keys:
                        charter_by_name[normalized_name] = charter
                    compact_key = self._normalize_compact_name(clean_name)
                    existing_compact = charter_by_compact_name.get(compact_key)
                    if existing_compact and existing_compact.id != charter.id:
                        ambiguous_compact_keys.add(compact_key)
                        charter_by_compact_name.pop(compact_key, None)
                    elif compact_key not in ambiguous_compact_keys and compact_key not in charter_by_compact_name:
                        charter_by_compact_name[compact_key] = charter
                    squashed_compact_key = self._normalize_squashed_compact_name(clean_name)
                    existing_squashed = charter_by_squashed_compact_name.get(squashed_compact_key)
                    if existing_squashed and existing_squashed.id != charter.id:
                        ambiguous_squashed_compact_keys.add(squashed_compact_key)
                        charter_by_squashed_compact_name.pop(squashed_compact_key, None)
                    elif (
                        squashed_compact_key not in ambiguous_squashed_compact_keys
                        and squashed_compact_key not in charter_by_squashed_compact_name
                    ):
                        charter_by_squashed_compact_name[squashed_compact_key] = charter
                stats["created"] += 1
                loaded_rows.append(
                        self._build_loaded_row(
                            row_number=row_number,
                            raw_name=clean_name,
                            raw_commission=raw_commission,
                            status="dry_run_create" if dry_run else "created",
                            charter=charter,
                        previous_commission="",
                        new_commission=commission_value,
                        was_rounded=was_rounded,
                    )
                )
            else:
                stats["missing"] += 1
                not_loaded_rows.append(
                    self._build_not_loaded_row(
                        row_number=row_number,
                        raw_name=clean_name,
                        raw_commission=raw_commission,
                        reason="not_found",
                    )
                )

        self._write_csv_report(
            path=loaded_report_path,
            fieldnames=[
                "row",
                "source_name",
                "source_commission",
                "status",
                "charter_id",
                "charter_name",
                "previous_commission",
                "new_commission",
                "was_rounded",
            ],
            rows=loaded_rows,
        )
        self._write_csv_report(
            path=not_loaded_report_path,
            fieldnames=[
                "row",
                "source_name",
                "source_commission",
                "reason",
                "details",
            ],
            rows=not_loaded_rows,
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Импорт комиссий завершен "
                f"(dry-run={dry_run}, create-missing={create_missing})."
            )
        )
        self.stdout.write(f"Обработано строк: {stats['processed']}")
        self.stdout.write(f"Обновлено: {stats['updated']}")
        self.stdout.write(f"Создано: {stats['created']}")
        self.stdout.write(f"Без изменений: {stats['unchanged']}")
        self.stdout.write(f"Не найдено в БД: {stats['missing']}")
        self.stdout.write(f"Неоднозначных совпадений: {stats['ambiguous']}")
        self.stdout.write(f"Невалидных строк: {stats['invalid']}")
        self.stdout.write(f"Пропущено (комиссия 20%): {stats['skipped_default_commission']}")
        self.stdout.write(f"Отчет загружено: {loaded_report_path}")
        self.stdout.write(f"Отчет не загружено: {not_loaded_report_path}")

    @staticmethod
    def _resolve_report_paths(file_path: Path, loaded_report_option: str, not_loaded_report_option: str):
        if loaded_report_option:
            loaded_report_path = Path(loaded_report_option).expanduser()
        else:
            loaded_report_path = file_path.with_name(f"{file_path.stem}_loaded.csv")

        if not_loaded_report_option:
            not_loaded_report_path = Path(not_loaded_report_option).expanduser()
        else:
            not_loaded_report_path = file_path.with_name(f"{file_path.stem}_not_loaded.csv")

        return loaded_report_path, not_loaded_report_path

    @staticmethod
    def _write_csv_report(path: Path, fieldnames, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as report_file:
            writer = csv.DictWriter(report_file, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    @staticmethod
    def _build_loaded_row(
        row_number,
        raw_name,
        raw_commission,
        status,
        charter,
        previous_commission,
        new_commission,
        was_rounded,
    ):
        return {
            "row": row_number,
            "source_name": raw_name,
            "source_commission": raw_commission,
            "status": status,
            "charter_id": getattr(charter, "charter_id", "") if charter else "",
            "charter_name": Command._clean_name(getattr(charter, "name", "")) if charter else "",
            "previous_commission": previous_commission,
            "new_commission": new_commission,
            "was_rounded": int(bool(was_rounded)),
        }

    @staticmethod
    def _build_not_loaded_row(row_number, raw_name, raw_commission, reason, details=""):
        return {
            "row": row_number,
            "source_name": raw_name,
            "source_commission": raw_commission,
            "reason": reason,
            "details": details,
        }

    def _build_charter_indexes(self):
        exact_index = {}
        ambiguous_exact_keys = set()
        compact_index = {}
        ambiguous_compact_keys = set()
        squashed_compact_index = {}
        ambiguous_squashed_compact_keys = set()
        for charter in Charter.objects.all():
            key = self._normalize_name(charter.name)
            if key:
                if key in ambiguous_exact_keys:
                    pass
                elif key in exact_index and exact_index[key].id != charter.id:
                    ambiguous_exact_keys.add(key)
                    exact_index.pop(key, None)
                elif key not in exact_index:
                    exact_index[key] = charter

            compact_key = self._normalize_compact_name(charter.name)
            if not compact_key:
                continue
            if compact_key in ambiguous_compact_keys:
                continue
            if compact_key in compact_index and compact_index[compact_key].id != charter.id:
                ambiguous_compact_keys.add(compact_key)
                compact_index.pop(compact_key, None)
                continue
            compact_index[compact_key] = charter

            squashed_compact_key = self._normalize_squashed_compact_name(charter.name)
            if not squashed_compact_key:
                continue
            if squashed_compact_key in ambiguous_squashed_compact_keys:
                continue
            if (
                squashed_compact_key in squashed_compact_index
                and squashed_compact_index[squashed_compact_key].id != charter.id
            ):
                ambiguous_squashed_compact_keys.add(squashed_compact_key)
                squashed_compact_index.pop(squashed_compact_key, None)
                continue
            squashed_compact_index[squashed_compact_key] = charter

        return (
            exact_index,
            ambiguous_exact_keys,
            compact_index,
            ambiguous_compact_keys,
            squashed_compact_index,
            ambiguous_squashed_compact_keys,
        )

    def _resolve_header(self, headers, aliases):
        normalized_to_original = {
            self._normalize_header(header): header for header in headers if str(header).strip()
        }
        for alias in aliases:
            if alias in normalized_to_original:
                return normalized_to_original[alias]
        return None

    @staticmethod
    def _normalize_header(value):
        return " ".join(str(value or "").strip().lower().split())

    @staticmethod
    def _clean_name(value):
        normalized = " ".join(str(value or "").strip().split())
        normalized = re.sub(r"(?<!\w)d\s*\.?\s*o\s*\.?\s*o\s*\.?(?!\w)", " doo ", normalized, flags=re.IGNORECASE)
        normalized = " ".join(normalized.split()).strip()
        # Убираем "висящую" пунктуацию-токены после чистки суффиксов, например: "Albatros yachting ."
        tokens = [token for token in normalized.split() if not re.fullmatch(r"[.,;:]+", token)]
        # Убираем цепочки хвостовых юр. суффиксов: "... Co. Ltd.", "... S.L.", "... LLC" и т.п.
        while tokens and re.sub(r"[^a-z0-9]+", "", tokens[-1].lower()) in Command.LEGAL_SUFFIXES:
            tokens.pop()
        normalized = " ".join(tokens).strip()
        # Срезаем завершающую пунктуацию у последнего токена: "yachting." -> "yachting"
        normalized = re.sub(r"[.,;:]+$", "", normalized)
        return normalized.strip()

    @staticmethod
    def _normalize_name(value):
        return Command._clean_name(value).lower()

    @staticmethod
    def _normalize_compact_name(value):
        return "".join(Command._normalize_name(value).split())

    @staticmethod
    def _normalize_squashed_compact_name(value):
        compact = Command._normalize_compact_name(value)
        return re.sub(r"(.)\1+", r"\1", compact)

    def _build_unique_charter_id(self, name):
        base = slugify(name) or "charter"
        candidate = base
        counter = 2
        while Charter.objects.filter(charter_id=candidate).exists():
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    def _parse_commission(self, raw_value):
        value = str(raw_value or "").strip()
        if not value:
            raise ValueError("пустое значение комиссии")

        match = re.search(r"-?\d+(?:[.,]\d+)?", value)
        if not match:
            raise ValueError(f"некорректная комиссия '{value}'")

        number = Decimal(match.group(0).replace(",", "."))
        rounded_number = number.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        commission = int(rounded_number)
        if commission < 0 or commission > 100:
            raise ValueError(f"комиссия вне диапазона 0..100: '{value}'")

        return commission, number != rounded_number

    def _read_xlsx(self, file_path: Path):
        with zipfile.ZipFile(file_path) as zf:
            sheet_path = self._resolve_first_sheet_path(zf)
            shared_strings = self._read_shared_strings(zf)
            rows = self._read_sheet_rows(zf, sheet_path, shared_strings)

        if not rows:
            return [], []

        headers = [str(v).strip() for v in rows[0]]
        records = []
        for row_index, row in enumerate(rows[1:], start=2):
            full_row = list(row) + [""] * max(0, len(headers) - len(row))
            if not any(str(cell).strip() for cell in full_row):
                continue
            records.append(
                {
                    "__row__": row_index,
                    **{headers[i]: str(full_row[i]).strip() for i in range(len(headers))},
                }
            )
        return headers, records

    def _resolve_first_sheet_path(self, zf: zipfile.ZipFile):
        workbook_xml = ET.fromstring(zf.read("xl/workbook.xml"))
        ns = {
            "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
            "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        }

        first_sheet = workbook_xml.find("a:sheets/a:sheet", ns)
        if first_sheet is None:
            raise CommandError("XLSX не содержит листов")

        relationship_id = first_sheet.attrib.get(f"{{{ns['r']}}}id")
        if not relationship_id:
            raise CommandError("Не удалось определить relationship id для первого листа")

        rels_xml = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rel_ns = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
        for rel in rels_xml.findall("r:Relationship", rel_ns):
            if rel.attrib.get("Id") != relationship_id:
                continue
            target = rel.attrib.get("Target", "")
            if target.startswith("/"):
                return target.lstrip("/")
            return f"xl/{target}" if not target.startswith("xl/") else target

        raise CommandError("Не удалось определить путь к первому листу")

    def _read_shared_strings(self, zf: zipfile.ZipFile):
        shared_strings_path = "xl/sharedStrings.xml"
        if shared_strings_path not in zf.namelist():
            return []

        ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        root = ET.fromstring(zf.read(shared_strings_path))
        values = []
        for string_item in root.findall("a:si", ns):
            text_nodes = string_item.findall(".//a:t", ns)
            values.append("".join(node.text or "" for node in text_nodes))
        return values

    def _read_sheet_rows(self, zf: zipfile.ZipFile, sheet_path, shared_strings):
        ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        root = ET.fromstring(zf.read(sheet_path))

        rows = []
        for row in root.findall(".//a:sheetData/a:row", ns):
            values_by_col = {}
            max_col = -1
            for cell in row.findall("a:c", ns):
                ref = cell.attrib.get("r", "")
                col_index = self._column_index_from_ref(ref)
                if col_index < 0:
                    continue
                values_by_col[col_index] = self._cell_to_value(cell, shared_strings, ns)
                max_col = max(max_col, col_index)

            if max_col < 0:
                rows.append([])
                continue

            row_values = [""] * (max_col + 1)
            for col_index, value in values_by_col.items():
                row_values[col_index] = value
            rows.append(row_values)

        return rows

    @staticmethod
    def _column_index_from_ref(ref: str):
        if not ref:
            return -1
        letters = "".join(ch for ch in ref if ch.isalpha()).upper()
        if not letters:
            return -1
        index = 0
        for char in letters:
            index = index * 26 + (ord(char) - ord("A") + 1)
        return index - 1

    @staticmethod
    def _cell_to_value(cell, shared_strings, ns):
        cell_type = cell.attrib.get("t")

        if cell_type == "inlineStr":
            text_nodes = cell.findall(".//a:t", ns)
            return "".join(node.text or "" for node in text_nodes).strip()

        value_node = cell.find("a:v", ns)
        raw_value = value_node.text if value_node is not None else ""

        if cell_type == "s":
            try:
                index = int(raw_value)
                return shared_strings[index] if index < len(shared_strings) else ""
            except (TypeError, ValueError):
                return ""

        if cell_type == "b":
            return "true" if raw_value == "1" else "false"

        return str(raw_value or "").strip()
