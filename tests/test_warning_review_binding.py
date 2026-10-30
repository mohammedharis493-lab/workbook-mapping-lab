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
from workbook_mapping_lab.warning_journal import load_journal


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

    def prepare_journal(self):
        folder = self.itr.parent / "private_reports"
        self.workspace.set_config({
            "folder": str(folder), "entity_key": "synthetic-ltd",
            "assessment_year": "2026-27", "itr_form": "ITR-6",
        })
        self.review_ageing()
        path = Path(self.workspace.save_warning_journal()["journal"]["path"])
        return folder, path

    def test_private_journal_round_trip_restores_notes_without_approving_mappings(self):
        before = self.fs.read_bytes(), self.itr.read_bytes()
        folder, path = self.prepare_journal()
        self.assertTrue(path.is_relative_to(folder))
        fresh = Workspace()
        fresh.set_config(dict(self.workspace.config))
        report = fresh.load_warning_journal({"path": str(path)})
        self.assertEqual(report["journal"]["loaded_count"], 1)
        reviewed = [w for w in report["warnings"] if w["acknowledged"]]
        self.assertEqual(len(reviewed), 1)
        self.assertEqual(reviewed[0]["reviewer_note"], "Invoice dates checked")
        self.assertIsNone(fresh.review)
        self.assertIsNone(fresh.latest_saved)
        self.assertEqual(before, (self.fs.read_bytes(), self.itr.read_bytes()))

    def test_changed_source_bytes_block_restoration_atomically(self):
        _, path = self.prepare_journal()
        self.itr_cells["Z20"] = "Unrelated updated line"
        self.rewrite_return()
        fresh = Workspace()
        fresh.set_config(dict(self.workspace.config))
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            fresh.load_warning_journal({"path": str(path)})
        self.assertEqual(fresh.decisions, {})

    def test_different_entity_year_and_form_are_rejected(self):
        _, path = self.prepare_journal()
        for key, replacement in (("entity_key", "other"),
                                 ("assessment_year", "2027-28"),
                                 ("itr_form", "ITR-5")):
            with self.subTest(key=key):
                fresh = Workspace()
                configuration = dict(self.workspace.config)
                configuration[key] = replacement
                fresh.set_config(configuration)
                with self.assertRaisesRegex(ValueError, "does not match"):
                    fresh.load_warning_journal({"path": str(path)})
                self.assertFalse(fresh.decisions)

    def test_journal_outside_private_folder_is_not_loaded(self):
        _, path = self.prepare_journal()
        outside = path.parent.parent / "copied_report.json"
        outside.write_bytes(path.read_bytes())
        fresh = Workspace()
        fresh.set_config(dict(self.workspace.config))
        with self.assertRaisesRegex(ValueError, "inside the configured private folder"):
            fresh.load_warning_journal({"path": str(outside)})
        self.assertFalse(fresh.decisions)

    def test_tampered_or_duplicate_warning_records_are_rejected(self):
        _, path = self.prepare_journal()
        data = json.loads(path.read_text(encoding="utf-8"))
        data["decisions"].append(dict(data["decisions"][0]))
        changed = path.with_name("altered_journal.json")
        changed.write_text(json.dumps(data), encoding="utf-8")
        fresh = Workspace()
        fresh.set_config(dict(self.workspace.config))
        with self.assertRaisesRegex(ValueError, "Invalid journal decisions"):
            fresh.load_warning_journal({"path": str(changed)})
        self.assertFalse(fresh.decisions)

    def test_changed_warning_fingerprint_rejects_same_file_snapshot(self):
        folder, path = self.prepare_journal()
        changed = [dict(item, explanation="Changed check wording")
                   for item in self.workspace.warnings]
        with self.assertRaisesRegex(ValueError, "findings have changed"):
            load_journal(str(path), str(folder), dict(self.workspace.config),
                         self.workspace._warning_evidence_signature, changed)

    def test_journal_requires_explicit_entity_context(self):
        self.workspace.set_config({"folder": str(self.itr.parent / "private")})
        with self.assertRaisesRegex(ValueError, "Choose an entity identifier"):
            self.workspace.save_warning_journal()


if __name__ == "__main__":
    unittest.main()
