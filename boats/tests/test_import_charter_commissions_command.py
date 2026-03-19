import tempfile
import zipfile
import csv
from pathlib import Path
from xml.sax.saxutils import escape

from django.core.management import call_command
from django.test import TestCase

from boats.models import Charter


def _col_ref(index):
    letters = ""
    value = index + 1
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def _build_minimal_xlsx(path: Path, rows):
    def _cell_xml(row_idx, col_idx, value):
        ref = f"{_col_ref(col_idx)}{row_idx}"
        text = escape(str(value if value is not None else ""))
        return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'

    sheet_rows_xml = []
    for row_idx, row_values in enumerate(rows, start=1):
        cells_xml = "".join(_cell_xml(row_idx, col_idx, value) for col_idx, value in enumerate(row_values))
        sheet_rows_xml.append(f'<row r="{row_idx}">{cells_xml}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        f"{''.join(sheet_rows_xml)}"
        "</sheetData>"
        "</worksheet>"
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", root_rels_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)


class ImportCharterCommissionsCommandTest(TestCase):
    def _run_with_xlsx(self, rows, **kwargs):
        with tempfile.NamedTemporaryFile(suffix=".xlsx") as tmp:
            xlsx_path = Path(tmp.name)
            _build_minimal_xlsx(xlsx_path, rows)
            call_command("import_charter_commissions", file=str(xlsx_path), **kwargs)

    def test_updates_existing_charter_commission_by_name(self):
        charter = Charter.objects.create(charter_id="charter-1", name="A-Yachts", commission=20)

        self._run_with_xlsx(
            rows=[
                ["Name", "Commission"],
                ["A-Yachts", "15%"],
            ]
        )

        charter.refresh_from_db()
        self.assertEqual(charter.commission, 15)

    def test_normalizes_charter_name_for_matching(self):
        charter = Charter.objects.create(charter_id="charter-2", name="  A   Yachts  ", commission=20)

        self._run_with_xlsx(
            rows=[
                ["Name", "Commission"],
                ["a yachts", "18%"],
            ]
        )

        charter.refresh_from_db()
        self.assertEqual(charter.commission, 18)

    def test_create_missing_creates_new_charter_when_enabled(self):
        self._run_with_xlsx(
            rows=[
                ["Name", "Commission"],
                ["New Wave Charter", "25%"],
            ],
            create_missing=True,
        )

        created = Charter.objects.get(name="New Wave Charter")
        self.assertEqual(created.commission, 25)
        self.assertEqual(created.charter_id, "new-wave-charter")

    def test_invalid_commission_does_not_update_charter(self):
        charter = Charter.objects.create(charter_id="charter-3", name="Blue Fleet", commission=20)

        self._run_with_xlsx(
            rows=[
                ["Name", "Commission"],
                ["Blue Fleet", "N/A"],
            ]
        )

        charter.refresh_from_db()
        self.assertEqual(charter.commission, 20)

    def test_decimal_commission_is_rounded_for_integer_field(self):
        charter = Charter.objects.create(charter_id="charter-4", name="Sea Group", commission=20)

        self._run_with_xlsx(
            rows=[
                ["Name", "Commission"],
                ["Sea Group", "17,7%"],
            ]
        )

        charter.refresh_from_db()
        self.assertEqual(charter.commission, 18)

    def test_matches_by_compact_name_without_spaces(self):
        charter = Charter.objects.create(charter_id="charter-5", name="Mar Geo Yachts", commission=20)

        self._run_with_xlsx(
            rows=[
                ["Name", "Commission"],
                ["margeoyachts", "19%"],
            ]
        )

        charter.refresh_from_db()
        self.assertEqual(charter.commission, 19)

    def test_ambiguous_compact_name_does_not_update_any_charter(self):
        charter_1 = Charter.objects.create(charter_id="charter-6", name="Blue Ocean", commission=20)
        charter_2 = Charter.objects.create(charter_id="charter-7", name="BlueOcean", commission=25)

        self._run_with_xlsx(
            rows=[
                ["Name", "Commission"],
                ["blu eocean", "30%"],
            ]
        )

        charter_1.refresh_from_db()
        charter_2.refresh_from_db()
        self.assertEqual(charter_1.commission, 20)
        self.assertEqual(charter_2.commission, 25)

    def test_matches_when_source_has_doo_suffix(self):
        charter = Charter.objects.create(charter_id="charter-9", name="123 Yacht Charter", commission=20)

        self._run_with_xlsx(
            rows=[
                ["Name", "Commission"],
                ["123 YACHT CHARTER d.o.o.", "15%"],
            ]
        )

        charter.refresh_from_db()
        self.assertEqual(charter.commission, 15)

    def test_matches_when_source_has_trailing_dot_token(self):
        charter = Charter.objects.create(charter_id="charter-12", name="Albatros yachting", commission=20)

        self._run_with_xlsx(
            rows=[
                ["Name", "Commission"],
                ["Albatros yachting .", "17%"],
            ]
        )

        charter.refresh_from_db()
        self.assertEqual(charter.commission, 17)

    def test_matches_when_source_has_co_ltd_suffixes(self):
        charter = Charter.objects.create(charter_id="charter-16", name="Ocean Breeze", commission=20)

        self._run_with_xlsx(
            rows=[
                ["Name", "Commission"],
                ["Ocean Breeze Co. Ltd.", "18%"],
            ]
        )

        charter.refresh_from_db()
        self.assertEqual(charter.commission, 18)

    def test_matches_when_source_has_sl_suffix(self):
        charter = Charter.objects.create(charter_id="charter-17", name="Sun Charter", commission=20)

        self._run_with_xlsx(
            rows=[
                ["Name", "Commission"],
                ["Sun Charter S.L.", "19%"],
            ]
        )

        charter.refresh_from_db()
        self.assertEqual(charter.commission, 19)

    def test_matches_when_difference_is_duplicated_letter(self):
        charter = Charter.objects.create(charter_id="charter-13", name="Albatross yachting", commission=20)

        self._run_with_xlsx(
            rows=[
                ["Name", "Commission"],
                ["Albatros yachting", "19%"],
            ]
        )

        charter.refresh_from_db()
        self.assertEqual(charter.commission, 19)

    def test_ambiguous_squashed_compact_name_is_skipped(self):
        charter_1 = Charter.objects.create(charter_id="charter-14", name="Boon Charter", commission=20)
        charter_2 = Charter.objects.create(charter_id="charter-15", name="Boonn Charter", commission=25)

        self._run_with_xlsx(
            rows=[
                ["Name", "Commission"],
                ["Bon Charter", "30%"],
            ]
        )

        charter_1.refresh_from_db()
        charter_2.refresh_from_db()
        self.assertEqual(charter_1.commission, 20)
        self.assertEqual(charter_2.commission, 25)

    def test_ambiguous_exact_name_after_doo_normalization_is_skipped(self):
        charter_1 = Charter.objects.create(charter_id="charter-10", name="Blue Sea", commission=20)
        charter_2 = Charter.objects.create(charter_id="charter-11", name="Blue Sea d.o.o.", commission=25)

        self._run_with_xlsx(
            rows=[
                ["Name", "Commission"],
                ["Blue Sea d.o.o.", "30%"],
            ]
        )

        charter_1.refresh_from_db()
        charter_2.refresh_from_db()
        self.assertEqual(charter_1.commission, 20)
        self.assertEqual(charter_2.commission, 25)

    def test_writes_loaded_and_not_loaded_reports(self):
        Charter.objects.create(charter_id="charter-8", name="A-Yachts", commission=20)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            xlsx_path = temp_dir_path / "charters.xlsx"
            loaded_report = temp_dir_path / "loaded.csv"
            not_loaded_report = temp_dir_path / "not_loaded.csv"

            _build_minimal_xlsx(
                xlsx_path,
                rows=[
                    ["Name", "Commission"],
                    ["A-Yachts", "15%"],
                    ["Unknown Charter", "17%"],
                    ["Bad Charter", "N/A"],
                ],
            )

            call_command(
                "import_charter_commissions",
                file=str(xlsx_path),
                loaded_report=str(loaded_report),
                not_loaded_report=str(not_loaded_report),
            )

            self.assertTrue(loaded_report.exists())
            self.assertTrue(not_loaded_report.exists())

            with loaded_report.open("r", encoding="utf-8-sig", newline="") as f:
                loaded_rows = list(csv.DictReader(f))
            with not_loaded_report.open("r", encoding="utf-8-sig", newline="") as f:
                not_loaded_rows = list(csv.DictReader(f))

            self.assertEqual(len(loaded_rows), 1)
            self.assertEqual(loaded_rows[0]["status"], "updated")
            self.assertEqual(loaded_rows[0]["source_name"], "A-Yachts")

            self.assertEqual(len(not_loaded_rows), 2)
            reasons = {row["reason"] for row in not_loaded_rows}
            self.assertIn("not_found", reasons)
            self.assertTrue(any("некорректная комиссия" in row["reason"] for row in not_loaded_rows))

    def test_skips_rows_with_default_20_commission(self):
        Charter.objects.create(charter_id="charter-18", name="Default Charter", commission=15)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            xlsx_path = temp_dir_path / "charters.xlsx"
            loaded_report = temp_dir_path / "loaded.csv"
            not_loaded_report = temp_dir_path / "not_loaded.csv"

            _build_minimal_xlsx(
                xlsx_path,
                rows=[
                    ["Name", "Commission"],
                    ["Default Charter", "20%"],
                    ["Unknown Default", "20%"],
                    ["A-Yachts", "15%"],
                ],
            )

            Charter.objects.create(charter_id="charter-19", name="A-Yachts", commission=20)

            call_command(
                "import_charter_commissions",
                file=str(xlsx_path),
                loaded_report=str(loaded_report),
                not_loaded_report=str(not_loaded_report),
            )

            with loaded_report.open("r", encoding="utf-8-sig", newline="") as f:
                loaded_rows = list(csv.DictReader(f))
            with not_loaded_report.open("r", encoding="utf-8-sig", newline="") as f:
                not_loaded_rows = list(csv.DictReader(f))

            # В отчетах остаётся только строка с комиссией != 20
            self.assertEqual(len(loaded_rows), 1)
            self.assertEqual(loaded_rows[0]["source_name"], "A-Yachts")
            self.assertEqual(len(not_loaded_rows), 0)

            # Комиссия 20 не должна менять текущую кастомную комиссию
            default_charter = Charter.objects.get(charter_id="charter-18")
            self.assertEqual(default_charter.commission, 15)
