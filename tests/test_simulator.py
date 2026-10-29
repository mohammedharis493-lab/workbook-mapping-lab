"""Synthetic tests; never inspect or publish real client data in CI."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from workbook_mapping_lab.simulator import WorkbookSnapshot, review

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


def xlsx(path: Path, *, filled=False, bad_formula=False, bad_anchor=False):
    book = ET.Element("{" + NS + "}workbook", {"xmlns:r": REL})
    sheets = ET.SubElement(book, "{" + NS + "}sheets")
    for i, name in enumerate(("Balance Sheet", "Profit & Loss Account"), start=1):
        ET.SubElement(sheets, "{" + NS + "}sheet",
                      {"name": name, "sheetId": str(i), "{" + REL + "}id": "rId" + str(i)})
    links = ET.Element("{" + PKG + "}Relationships")
    for i in (1, 2):
        ET.SubElement(links, "{" + PKG + "}Relationship", {
            "Id": "rId" + str(i),
            "Type": REL + "/worksheet",
            "Target": "worksheets/sheet" + str(i) + ".xml"})
    with ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", ET.tostring(book, encoding="utf-8"))
        z.writestr("xl/_rels/workbook.xml.rels", ET.tostring(links, encoding="utf-8"))
        for i in (1, 2):
            root = ET.Element("{" + NS + "}worksheet")
            data = ET.SubElement(root, "{" + NS + "}sheetData")
            labels = ("Cash", "Loans") if i == 1 else ("Audit fees", "Registration costs")
            for r, name in enumerate(labels, start=1):
                row = ET.SubElement(data, "{" + NS + "}row", {"r": str(r)})
                label = ET.SubElement(row, "{" + NS + "}c",
                                      {"r": "A" + str(r), "t": "inlineStr"})
                ET.SubElement(ET.SubElement(label, "{" + NS + "}is"), "{" + NS + "}t").text = (
                    "Incorrect" if bad_anchor and i == 1 and r == 1 else name)
                if filled or (bad_formula and i == 1 and r == 1):
                    target = ET.SubElement(row, "{" + NS + "}c", {"r": "B" + str(r)})
                    if bad_formula and i == 1 and r == 1:
                        ET.SubElement(target, "{" + NS + "}f").text = "1+2"
                    else:
                        ET.SubElement(target, "{" + NS + "}v").text = str(
                            (100, 200)[r-1] if i == 1 else (90, 30)[r-1])
            z.writestr("xl/worksheets/sheet" + str(i) + ".xml",
                       ET.tostring(root, encoding="utf-8"))


def write_csv(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(cols)
        writer.writerows(rows)


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.template = self.root / "synthetic-template.xlsx"
        xlsx(self.template)
        self.layout = self.root / "layout.csv"
        self.values = self.root / "mapped.csv"
        self.controls = self.root / "controls.csv"
        self.columns = ("field_id", "section", "sheet", "cell", "anchor_cell", "anchor_text")
        self.rows = [
            ("BS-CASH", "BS", "Balance Sheet", "B1", "A1", "Cash"),
            ("BS-LOANS", "BS", "Balance Sheet", "B2", "A2", "Loans"),
            ("PL-AUDIT", "PL", "Profit & Loss Account", "B1", "A1", "Audit fees"),
            ("PL-OTHER", "PL", "Profit & Loss Account", "B2", "A2", "Registration costs"),
        ]
        write_csv(self.layout, self.columns, self.rows)
        write_csv(self.values, ("field_id", "section", "amount"),
                  [("BS-CASH", "BS", 100), ("BS-LOANS", "BS", 200),
                   ("PL-AUDIT", "PL", 90), ("PL-OTHER", "PL", 30)])
        write_csv(self.controls, ("section", "total"), [("BS", 300), ("PL", 120)])

    def run_review(self, **overrides):
        return review(str(overrides.pop("template", self.template)),
                      str(self.layout), str(self.values),
                      controls=str(self.controls), **overrides)

    def test_synthetic_virtual_import_and_totals(self):
        result = self.run_review()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["virtual_reexported_field_count"], 4)
        self.assertEqual(result["control_total_count"], 2)
        with WorkbookSnapshot(self.template) as wb:
            self.assertEqual(wb.inventory()["sheet_count"], 2)
            self.assertEqual(wb.cell("Balance Sheet", "A1")["value"], "Cash")

    def test_original_template_never_modified(self):
        with WorkbookSnapshot(self.template) as wb:
            before = wb.sha256
        self.run_review()
        with WorkbookSnapshot(self.template) as wb:
            self.assertEqual(before, wb.sha256)

    def test_compare_separately_filled_workbook(self):
        filled = self.root / "filled.xlsx"
        xlsx(filled, filled=True)
        result = self.run_review(filled=str(filled))
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["mode"], "filled-workbook-compare")

    def test_wrong_anchor_is_blocked(self):
        file = self.root / "bad-anchor.xlsx"
        xlsx(file, bad_anchor=True)
        result = self.run_review(template=file)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("ANCHOR_MISMATCH", [e["code"] for e in result["errors"]])

    def test_formula_target_is_blocked(self):
        file = self.root / "formula.xlsx"
        xlsx(file, bad_formula=True)
        result = self.run_review(template=file)
        self.assertIn("FORMULA_TARGET", [e["code"] for e in result["errors"]])

    def test_unknown_target_sheet_is_blocked(self):
        changed = self.rows.copy()
        changed[0] = ("BS-CASH", "BS", "Unknown Sheet", "B1", "A1", "Cash")
        write_csv(self.layout, self.columns, changed)
        result = self.run_review()
        self.assertIn("MISSING_TEMPLATE_SHEET", [e["code"] for e in result["errors"]])

    def test_control_difference_is_blocked(self):
        write_csv(self.controls, ("section", "total"), [("BS", 300), ("PL", 130)])
        self.assertIn("CONTROL_TOTAL_MISMATCH",
                      [e["code"] for e in self.run_review()["errors"]])

    def test_duplicate_destination_is_blocked(self):
        write_csv(self.layout, self.columns, self.rows + [
            ("BS-DUPLICATE", "BS", "Balance Sheet", "B1", "A1", "Cash")])
        self.assertIn("DUPLICATE_TARGET_CELL",
                      [e["code"] for e in self.run_review()["errors"]])


    def test_missing_package_metadata_blocks(self):
        from zipfile import ZipFile
        with ZipFile(self.template, "a") as archive:
            archive.writestr("docProps/core.xml", "<synthetic-metadata/>")
        filled = self.root / "filled-missing-metadata.xlsx"
        xlsx(filled, filled=True)
        result = self.run_review(filled=str(filled))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("MISSING_PACKAGE_PARTS",
                      [e["code"] for e in result["errors"]])

    def test_untouched_cell_change_blocks(self):
        filled = self.root / "filled-wrong-label.xlsx"
        xlsx(filled, filled=True, bad_anchor=True)
        result = self.run_review(filled=str(filled))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("UNEXPECTED_CELL_CHANGE",
                      [e["code"] for e in result["errors"]])

    def test_import_into_nonempty_template_blocks(self):
        populated = self.root / "already-filled.xlsx"
        xlsx(populated, filled=True)
        result = self.run_review(template=populated)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("NONEMPTY_TARGET",
                      [e["code"] for e in result["errors"]])


if __name__ == "__main__":
    unittest.main()
