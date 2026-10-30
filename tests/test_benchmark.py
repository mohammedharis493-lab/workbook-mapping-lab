"""Synthetic field-level comparison tests. No actual customer workbook."""
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from test_simulator import xlsx,write_csv
from workbook_mapping_lab.writer import populate
from workbook_mapping_lab.benchmark import compare_reference


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        base=Path(t.name)
        self.blank=base/"blank.xlsx"
        self.generated=base/"generated.xlsx"
        self.reference=base/"reference.xlsx"
        self.layout=base/"layout.csv"
        self.values=base/"amounts.csv"
        xlsx(self.blank)
        xlsx(self.reference,filled=True)
        # An independent source file may share field values but not be
        # bit-identical to our generated output.
        with ZipFile(self.reference,"a") as z:
            z.writestr("docProps/synthetic-mark.xml","<independent>true</independent>")
        self.layout_rows=[
            ("B-CASH","BS-A","Balance Sheet","B1","A1","Cash"),
            ("B-LOAN","BS-L","Balance Sheet","B2","A2","Loans"),
            ("P-AUDIT","PL-E","Profit & Loss Account","B1","A1","Audit fees"),
            ("P-OTHER","PL-E","Profit & Loss Account","B2","A2","Registration costs"),
        ]
        write_csv(self.layout,("field_id","section","sheet","cell","anchor_cell","anchor_text"),
                  self.layout_rows)
        write_csv(self.values,("field_id","section","amount"),[
            ("B-CASH","BS-A","100"),("B-LOAN","BS-L","200"),
            ("P-AUDIT","PL-E","90"),("P-OTHER","PL-E","30"),
        ])
        populate(str(self.blank),str(self.layout),str(self.values),str(self.generated))

    def test_all_selected_fields_match(self):
        r=compare_reference(str(self.generated),str(self.reference),str(self.layout))
        self.assertEqual(r["status"],"MATCHED_SELECTED_FIELDS")
        self.assertEqual(r["matching_fields"],4)
        self.assertEqual(r["differing_fields"],0)

    def test_mismatch_is_reported_by_field(self):
        write_csv(self.values,("field_id","section","amount"),[
            ("B-CASH","BS-A","101"),("B-LOAN","BS-L","200"),
            ("P-AUDIT","PL-E","90"),("P-OTHER","PL-E","30"),
        ])
        second=self.generated.parent/"generated_2.xlsx"
        populate(str(self.blank),str(self.layout),str(self.values),str(second))
        r=compare_reference(str(second),str(self.reference),str(self.layout))
        self.assertEqual(r["differing_fields"],1)
        self.assertEqual(r["matching_fields"],3)
        self.assertEqual([x["field_id"] for x in r["exceptions"]
                          if x["code"]=="AMOUNT_OR_CLASSIFICATION_MISMATCH"],["B-CASH"])

    def test_reference_field_missing_fails(self):
        omitted=[r for r in self.layout_rows if r[0]!="P-AUDIT"]
        changed=[*omitted,("P-AUDIT","PL-E","Profit & Loss Account","B1","A99","Nonexistent fee")]
        alt=self.generated.parent/"wrong_layout.csv"
        write_csv(alt,("field_id","section","sheet","cell","anchor_cell","anchor_text"),changed)
        r=compare_reference(str(self.generated),str(self.reference),str(alt))
        self.assertEqual(r["status"],"DIFFERENCES_OR_BLOCKERS")
        self.assertIn("GENERATED_LABEL_CHANGED",[e["code"] for e in r["exceptions"]])

    def test_same_file_not_independent_reference(self):
        result=compare_reference(str(self.generated),str(self.generated),str(self.layout))
        self.assertIn("IDENTICAL_FILES_NOT_INDEPENDENT_REFERENCE",
                      [x["code"] for x in result["exceptions"]])

    def test_invalid_tolerance_blocked(self):
        with self.assertRaises(ValueError):
            compare_reference(str(self.generated),str(self.reference),str(self.layout),
                              tolerance="-1")


if __name__=="__main__":
    unittest.main()
