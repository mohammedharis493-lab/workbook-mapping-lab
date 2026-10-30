"""Synthetic cross-check of parent totals and vendor subsidiary worksheet values."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from workbook_mapping_lab.detail_companions import add_companion_fields


class CompanionTests(unittest.TestCase):
    def setUp(self):
        self.values=[{"field_id":"CREDITORS","section":"BS-L","amount":"150"},
                     {"field_id":"LOAN","section":"BS-L","amount":"400"}]
        self.layout=[{"field_id":"CREDITORS","section":"BS-L","sheet":"Balance Sheet","anchor_text":"Trade creditors"},
                     {"field_id":"LOAN","section":"BS-L","sheet":"Balance Sheet","anchor_text":"Borrowings"},
                     {"field_id":"OVER_ONE","section":"BS-L-DETAIL","sheet":"Creditors","anchor_text":"Over one year"},
                     {"field_id":"UNDER_ONE","section":"BS-L-DETAIL","sheet":"Creditors","anchor_text":"Others"},
                     {"field_id":"RELATED","section":"BS-L-DETAIL","sheet":"Borrowings","anchor_text":"Related deposits"}]
        self.details=[{"parent_field_id":"CREDITORS","detail_field_id":"OVER_ONE","amount":"125"},
                      {"parent_field_id":"CREDITORS","detail_field_id":"UNDER_ONE","amount":"25"},
                      {"parent_field_id":"LOAN","detail_field_id":"RELATED","amount":"400"}]

    def test_children_do_not_inflate_balance_sheet_total(self):
        augmented,errors=add_companion_fields(self.values,self.layout,self.details,"exact")
        self.assertFalse(errors)
        self.assertEqual(len(augmented),5)
        self.assertEqual(sum(float(x["amount"]) for x in augmented
                             if x["section"]=="BS-L"),550)
        self.assertEqual(sum(float(x["amount"]) for x in augmented
                             if x["section"]=="BS-L-DETAIL"),550)

    def test_children_must_equal_parent(self):
        self.details[1]["amount"]="30"
        _,errors=add_companion_fields(self.values,self.layout,self.details,"exact")
        self.assertIn("COMPANION_CHILDREN_DO_NOT_SUM_TO_PARENT",
                      [i["issue"] for i in errors])

    def test_duplicate_child_is_rejected(self):
        _,errors=add_companion_fields(self.values,self.layout,self.details+[self.details[0]],"exact")
        self.assertIn("COMPANION_CHILD_MISSING_OR_DUPLICATE",[i["issue"] for i in errors])

    def test_wrong_statement_section_is_rejected(self):
        self.layout[2]["section"]="PL-E-DETAIL"
        _,errors=add_companion_fields(self.values,self.layout,self.details,"exact")
        self.assertIn("COMPANION_CHILD_SECTION_INCORRECT",[i["issue"] for i in errors])


class DetailEndToEndTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        from test_layout_resolver import make_vendor
        from test_simulator import write_csv
        self.write_csv=write_csv
        self.blank=self.root/"native_export.xlsx"
        make_vendor(self.blank)
        self.source=self.root/"source.csv"
        self.rules=self.root/"rules.csv"
        self.layout=self.root/"layout.csv"
        self.control=self.root/"source_control.csv"
        self.output_control=self.root/"output_control.csv"
        self.details=self.root/"details.csv"
        write_csv(self.source,("source_id","section","caption","amount"),[
            ("RELATED","BS-L","Related loans",500)])
        write_csv(self.rules,("source_id","field_id","approved"),[
            ("RELATED","PARENT","yes")])
        write_csv(self.layout,("field_id","section","sheet","cell","anchor_cell","anchor_text"),[
            ("PARENT","BS-L","Base","B11","A11","Long-term loans"),
            ("CHILD","BS-L-DETAIL","Related Details","B11","A11","Deposits from related parties"),
        ])
        write_csv(self.control,("section","amount"),[("BS-L",500)])
        write_csv(self.output_control,("section","total"),[("BS-L",500)])

    def build(self, amount="500"):
        from workbook_mapping_lab.pipeline import controlled_build
        self.write_csv(self.details,("parent_field_id","detail_field_id","amount"),[
            ("PARENT","CHILD",amount)])
        return controlled_build(
            source=str(self.source),rules=str(self.rules),
            layout=str(self.layout),template=str(self.blank),
            source_controls=str(self.control),output_controls=str(self.output_control),
            output=str(self.root/"checked.xlsx"),
            exception_report=str(self.root/"exceptions.json"),
            companion_details=str(self.details))

    def test_native_export_parent_and_child_filled_once(self):
        from workbook_mapping_lab.simulator import WorkbookSnapshot
        result=self.build()
        self.assertEqual(result["status"],"PASS")
        self.assertEqual(result["mapped_field_count"],2)
        self.assertEqual(result["sections"],{"BS-L":"500"})
        with WorkbookSnapshot(self.root/"checked.xlsx") as b:
            self.assertEqual(b.cell("Base","B11")["value"],"500")
            self.assertEqual(b.cell("Related Details","B11")["value"],"500")

    def test_mismatched_child_blocks_import_copy(self):
        result=self.build(amount="499")
        self.assertEqual(result["status"],"BLOCKED")
        self.assertFalse((self.root/"checked.xlsx").exists())
        self.assertIn("COMPANION_CHILDREN_DO_NOT_SUM_TO_PARENT",
                      [x["issue"] for x in result["exceptions"]])


if __name__=="__main__":
    unittest.main()
