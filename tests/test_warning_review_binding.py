"""Synthetic-only regression tests for evidence-bound advisory decisions."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from test_advisories import workbook
from workbook_mapping_lab.advisories import advisory, warning_review_key
from workbook_mapping_lab.review_browser import Workspace


class WarningReviewBindingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.fs = root / "prior_fs.xlsx"
        self.itr = root / "prior_return.xlsx"
        self.itr_cells = {
            "A4": "Trade Creditors o/s for more than 1 year",
            "A5": "Others", "B5": 70, "A6": "Total", "B6": 70,
        }
        workbook(self.fs, {"New Disclosure": {
            "A5": "(i) MSME", "C4": "Less than 1 yr.",
            "C5": 30, "D5": 20, "E5": 15, "F5": 5,
            "G5": 70, "G2": "Figures in INR",
        }})
        self.rewrite_return()
        self.workspace = Workspace()
        self.workspace.set_config({"previous": str(self.fs),
                                   "previous_target": str(self.itr)})

    def rewrite_return(self):
        workbook(self.itr, {"Creditors": self.itr_cells})

    def review_ageing(self):
        self.workspace.refresh_warnings()
        index = next(i for i, item in enumerate(self.workspace.warnings)
                     if item["code"] == "PRIOR_CREDITOR_AGE_CLASSIFICATION")
        self.workspace.warning_decision({"index": index,
                                         "acknowledged": True,
                                         "note": "Invoice dates checked"})
        return index

    def test_unchanged_evidence_keeps_review_after_refresh(self):
        index = self.review_ageing()
        self.workspace.refresh_warnings()
        self.assertTrue(self.workspace.data()["warnings"][index]["acknowledged"])
        self.assertEqual(self.workspace.data()["warnings"][index]["reviewer_note"],
                         "Invoice dates checked")
        self.assertFalse(self.workspace.data()["warnings"][index]["blocking"])

    def test_unrelated_cell_change_invalidates_review_even_if_warning_same(self):
        index = self.review_ageing()
        original_code = self.workspace.warnings[index]["code"]
        self.itr_cells["Z20"] = "New explanatory footnote"
        self.rewrite_return()
        self.workspace.refresh_warnings()
        found = next(x for x in self.workspace.data()["warnings"]
                     if x["code"] == original_code)
        self.assertFalse(found["acknowledged"])
        self.assertNotIn("reviewer_note", found)
        self.assertFalse(self.workspace.decisions)

    def test_switching_entity_or_workbook_clears_old_review(self):
        self.review_ageing()
        self.workspace.set_config({"entity_key": "a-second-entity"})
        self.assertEqual(self.workspace.decisions, {})
        self.review_ageing()
        other = self.itr.with_name("second_copy.xlsx")
        other.write_bytes(self.itr.read_bytes())
        self.workspace.set_config({"previous_target": str(other)})
        self.workspace.refresh_warnings()
        self.assertFalse(any(w["acknowledged"] for w in
                             self.workspace.data()["warnings"]))

    def test_rule_content_change_invalidates_review(self):
        self.review_ageing()
        rules = self.itr.with_name("rules.json")
        rules.write_text(json.dumps({"version": 1, "checks": []}), encoding="utf-8")
        self.workspace.set_config({"advisory_rules": str(rules)})
        self.workspace.refresh_warnings()
        self.assertFalse(any(w["acknowledged"] for w in
                             self.workspace.data()["warnings"]))

    def test_fingerprint_excludes_decision_flags_but_tracks_evidence(self):
        item = advisory("SYNTHETIC", "Synthetic finding", "Explain", "Review",
                        evidence=[{"sheet": "A", "cell": "B3", "amount": "5"}])
        key = warning_review_key(item, "source-digest")
        self.assertEqual(key, warning_review_key(dict(item, acknowledged=True,
                                                      reviewer_note="checked"), "source-digest"))
        self.assertNotEqual(key, warning_review_key(dict(item, difference="1"),
                                                    "source-digest"))
        self.assertNotEqual(key, warning_review_key(item, "other-digest"))


if __name__ == "__main__":
    unittest.main()
