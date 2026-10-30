"""Synthetic regression: separate over-one-year and Others amounts."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from test_advisories import AdvisoryTests
from workbook_mapping_lab.advisories import check_creditor_ageing


class CreditorLabelTests(AdvisoryTests):
    def test_all_creditors_in_others_does_not_become_old_amount(self):
        notes=check_creditor_ageing(str(self.fs),str(self.itr))
        found=next(w for w in notes if w["code"]=="PRIOR_CREDITOR_AGE_CLASSIFICATION")
        self.assertEqual(found["difference"],"-40")
        self.assertIn("0 in its >1-year row (B4)",found["explanation"])
        self.assertIn("70 in Others (B5)",found["explanation"])
        self.assertEqual({e["cell"] for e in found["evidence"]},
                         {"C5","D5:F5","G5","B4","B5"})

    def test_correct_full_split_requires_both_rows(self):
        self.itr_data["B4"]=40
        self.itr_data["B5"]=30
        self.rebuild()
        warnings=check_creditor_ageing(str(self.fs),str(self.itr))
        self.assertNotIn("PRIOR_CREDITOR_AGE_CLASSIFICATION",
                         [w["code"] for w in warnings])

    def test_old_amount_entered_but_others_missing_is_detected(self):
        self.itr_data["B4"]=70
        self.itr_data.pop("B5",None)
        self.rebuild()
        warnings=check_creditor_ageing(str(self.fs),str(self.itr))
        selected=next(w for w in warnings if w["code"]=="PRIOR_CREDITOR_AGE_CLASSIFICATION")
        self.assertEqual(selected["difference"],"30")
        self.assertIn("70 in its >1-year row",selected["explanation"])

    def test_unrecognised_other_row_does_not_infer(self):
        self.itr_data["A5"]="Trade receivables"
        self.rebuild()
        warnings=check_creditor_ageing(str(self.fs),str(self.itr))
        self.assertEqual(warnings[0]["code"],"HISTORICAL_AGEING_LAYOUT_UNRECOGNISED")


if __name__=="__main__":
    unittest.main()
