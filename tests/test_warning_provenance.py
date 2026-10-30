"""Synthetic M4.3a rules: exact coordinates, periods and tolerance provenance."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from test_advisories import workbook
from workbook_mapping_lab.advisories import evaluate_evidence_rules


class WarningProvenanceTests(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        root = Path(root.name)
        self.previous_fs = root / "previous_fs.xlsx"
        self.previous_return = root / "previous_return.xlsx"
        self.current_return = root / "current_return.xlsx"
        workbook(self.previous_fs, {
            "Synthetic ITR3 support": {"D5": 20, "E5": 15, "F5": 5},
            "Synthetic ITR6 support": {"C9": 9, "D9": 6},
        })
        workbook(self.previous_return, {
            "Synthetic ITR3 disclosure": {"B5": 70},
            "Synthetic ITR6 disclosure": {"B9": 20},
        })
        workbook(self.current_return, {"Current synthetic form": {"D8": 55}})
        self.paths = {
            "previous_fs": str(self.previous_fs),
            "previous_return": str(self.previous_return),
            "current_return": str(self.current_return),
        }
        self.itr3_rule = {
            "code": "SYNTH_ITR3_AGEING", "title": "Ageing comparison",
            "source_kind": "previous_fs", "source_sheet": "Synthetic ITR3 support",
            "source_cells": ["D5", "E5", "F5"],
            "target_kind": "previous_return", "target_sheet": "Synthetic ITR3 disclosure",
            "target_cell": "B5", "tolerance": "5", "period": "Previous year",
        }

    def test_warns_with_each_source_amount_and_exact_tolerance(self):
        found = evaluate_evidence_rules(self.paths, [self.itr3_rule])
        self.assertEqual(len(found), 1)
        warning = found[0]
        self.assertEqual(warning["difference"], "30")
        self.assertEqual(warning["tolerance"], "5")
        self.assertEqual(warning["period"], "Previous year")
        self.assertEqual(warning["source_period"], "Previous year")
        self.assertEqual(warning["target_period"], "Previous year")
        self.assertEqual([(e["sheet"], e["cell"], e["amount"])
                          for e in warning["evidence"]], [
            ("Synthetic ITR3 support", "D5", "20"),
            ("Synthetic ITR3 support", "E5", "15"),
            ("Synthetic ITR3 support", "F5", "5"),
            ("Synthetic ITR3 disclosure", "B5", "70"),
        ])
        self.assertFalse(warning["blocking"])

    def test_cross_year_roles_derive_comparison_periods(self):
        rule = dict(self.itr3_rule, code="CROSS_YEAR",
                    target_kind="current_return", target_sheet="Current synthetic form",
                    target_cell="D8", period="Previous year to Current year")
        result = evaluate_evidence_rules(self.paths, [rule])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["period"], "Previous year to Current year")
        self.assertEqual(result[0]["source_period"], "Previous year")
        self.assertEqual(result[0]["target_period"], "Current year")

    def test_conflicting_declared_period_rejected_before_evaluation(self):
        rule = dict(self.itr3_rule, target_kind="current_return",
                    target_sheet="Current synthetic form", target_cell="D8")
        with self.assertRaisesRegex(ValueError, "period conflicts"):
            evaluate_evidence_rules(self.paths, [rule])

    def test_missing_workbook_keeps_unverified_coordinates_and_tolerance(self):
        paths = dict(self.paths, previous_fs="")
        found = evaluate_evidence_rules(paths, [self.itr3_rule])
        self.assertEqual(len(found), 1)
        warning = found[0]
        self.assertEqual(warning["code"], "SYNTH_ITR3_AGEING_UNVERIFIED")
        self.assertEqual(warning["severity"], "Info")
        self.assertEqual(warning["tolerance"], "5")
        self.assertEqual([e["cell"] for e in warning["evidence"]],
                         ["D5", "E5", "F5", "B5"])
        self.assertTrue(all("amount" not in e for e in warning["evidence"]))
        self.assertFalse(warning["blocking"])

    def test_nonnumeric_evidence_stays_unverified(self):
        workbook(self.previous_return, {
            "Synthetic ITR3 disclosure": {"B5": "unknown"},
        })
        found = evaluate_evidence_rules(self.paths, [self.itr3_rule])
        self.assertEqual(found[0]["severity"], "Info")
        self.assertEqual(found[0]["evidence"][-1]["cell"], "B5")
        self.assertNotIn("difference", found[0]["evidence"][-1])

    def test_independently_reviewed_synthetic_form_rules(self):
        rule6 = {
            "code": "SYNTH_ITR6_DETAIL", "title": "Independent form disclosure",
            "source_kind": "previous_fs", "source_sheet": "Synthetic ITR6 support",
            "source_cells": ["C9", "D9"], "target_kind": "previous_return",
            "target_sheet": "Synthetic ITR6 disclosure", "target_cell": "B9",
            "tolerance": "0",
        }
        result = evaluate_evidence_rules(self.paths, [self.itr3_rule, rule6])
        self.assertEqual({w["code"] for w in result},
                         {"SYNTH_ITR3_AGEING", "SYNTH_ITR6_DETAIL"})
        self.assertEqual([w["difference"] for w in result], ["30", "5"])
        self.assertEqual([w["tolerance"] for w in result], ["5", "0"])
        self.assertEqual([w["evidence"][-1]["sheet"] for w in result],
                         ["Synthetic ITR3 disclosure", "Synthetic ITR6 disclosure"])


if __name__ == "__main__":
    unittest.main()
