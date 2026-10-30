"""Synthetic M4.3b checks for built-in, layout-gated creditor warnings."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from test_advisories import workbook
from workbook_mapping_lab.advisories import check_creditor_ageing


class DefaultWarningProvenanceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.prior_fs = root / "prior_fs.xlsx"
        self.prior_itr = root / "prior_itr.xlsx"
        self.current_fs = root / "current_fs.xlsx"
        self.previous = {
            "A5": "(i) MSME", "C4": "Less than 1 yr.", "G2": "Figures in INR",
            "C5": 30, "D5": 20, "E5": 15, "F5": 5, "G5": 70,
        }
        self.current = {
            "A5": "(i) MSME", "C4": "Less than 1 yr.",
            "C5": 40, "D5": 1, "E5": 20, "F5": 20, "G5": 110,
        }
        workbook(self.prior_fs, {"New Disclosure": self.previous})
        workbook(self.prior_itr, {"Creditors": {
            "A4": "Trade Creditors o/s for more than 1 year", "A5": "Others",
            "B4": 0, "B5": 70, "B6": 70,
        }})
        self.rebuild_current()

    def rebuild_current(self):
        workbook(self.current_fs, {"New Disclosure": self.current})

    def warnings(self):
        return {w["code"]: w for w in check_creditor_ageing(
            str(self.prior_fs), str(self.prior_itr), current_fs=str(self.current_fs))}

    def test_historical_default_comparison_lists_all_original_amount_cells(self):
        item = self.warnings()["PRIOR_CREDITOR_AGE_CLASSIFICATION"]
        self.assertEqual(item["tolerance"], "0")
        self.assertEqual(item["source_period"], "Previous year")
        self.assertEqual(item["target_period"], "Previous year")
        self.assertEqual([(x["cell"], x["amount"]) for x in item["evidence"]],
                         [("C5", "30"), ("D5", "20"), ("E5", "15"),
                          ("F5", "5"), ("G5", "70"), ("B4", "0"), ("B5", "70")])

    def test_current_total_mismatch_lists_each_current_numeric_evidence_cell(self):
        item = self.warnings()["CURRENT_FS_AGEING_TOTAL_MISMATCH"]
        self.assertEqual(item["difference"], "-29")
        self.assertEqual(item["tolerance"], "0")
        self.assertEqual(item["source_period"], "Current year")
        self.assertEqual(item["target_period"], "Current year")
        self.assertEqual([(x["cell"], x["amount"]) for x in item["evidence"]],
                         [("C5", "40"), ("D5", "1"), ("E5", "20"),
                          ("F5", "20"), ("G5", "110")])

    def test_missing_current_worksheet_is_explicitly_unverified(self):
        workbook(self.current_fs, {"Different form layout": {"C5": 100}})
        found = self.warnings()
        self.assertEqual(found["CURRENT_FS_AGEING_NOT_FOUND"]["severity"], "Info")
        self.assertNotIn("CURRENT_FS_AGEING_TOTAL_MISMATCH", found)
        self.assertNotIn("AGEING_ROLLFORWARD_NEEDS_SUPPORT", found)

    def test_mismatching_current_layout_never_compares_numeric_cells(self):
        self.current["A5"] = "Trade receivables - different form"
        self.rebuild_current()
        found = self.warnings()
        item = found["CURRENT_FS_AGEING_LAYOUT_UNRECOGNISED"]
        self.assertEqual(item["severity"], "Info")
        self.assertEqual([x["cell"] for x in item["evidence"]], ["A5", "C4"])
        self.assertNotIn("CURRENT_FS_AGEING_TOTAL_MISMATCH", found)

    def test_missing_numeric_current_bucket_does_not_assume_zero(self):
        self.current.pop("F5")
        self.rebuild_current()
        found = self.warnings()
        item = found["CURRENT_FS_AGEING_INCOMPLETE"]
        self.assertEqual(item["severity"], "Info")
        self.assertEqual([x["cell"] for x in item["evidence"]],
                         ["C5", "D5", "E5", "F5", "G5"])
        self.assertTrue(all("amount" not in x for x in item["evidence"]))
        self.assertNotIn("AGEING_ROLLFORWARD_NEEDS_SUPPORT", found)

    def test_heuristic_rollforward_stays_advisory_and_cross_year_labelled(self):
        item = self.warnings()["AGEING_ROLLFORWARD_NEEDS_SUPPORT"]
        self.assertEqual(item["period"], "Previous year to Current year")
        self.assertEqual(item["source_period"], "Previous year")
        self.assertEqual(item["target_period"], "Current year")
        self.assertEqual([(x["cell"], x["amount"]) for x in item["evidence"]],
                         [("C5", "30"), ("D5", "20"), ("E5", "15"),
                          ("F5", "5"), ("D5", "1"), ("E5", "20"), ("F5", "20")])
        self.assertFalse(item["blocking"])
        self.assertNotIn("tolerance", item)


if __name__ == "__main__":
    unittest.main()
