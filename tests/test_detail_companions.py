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


if __name__=="__main__":
    unittest.main()
