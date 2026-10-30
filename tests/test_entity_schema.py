"""Synthetic entity-specific ITR profiles: no cross-entity field leakage."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from test_layout_resolver import make_vendor
from workbook_mapping_lab.entity_schema import (
    inspect_entity_profile, load_entity_profile
)


class EntitySchemaTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.alpha = self.root / "alpha_vendor.xlsx"
        self.beta = self.root / "beta_vendor.xlsx"
        make_vendor(self.alpha, row=11, include_details=True)
        make_vendor(self.beta, row=26, include_details=False)
        self.alpha_before = self.alpha.read_bytes()
        self.beta_before = self.beta.read_bytes()

    def profile(self, path, entity_key, fields):
        return {
            "version": 1,
            "entity_key": entity_key,
            "assessment_year": "2026-27",
            "itr_form": "ITR-6",
            "template_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "fields": fields,
        }

    def field(self, key, sheet, caption, applicability):
        return {
            "field_id": key,
            "section": "BS-L",
            "sheet": sheet,
            "caption": caption,
            "anchor_column": "A",
            "amount_column": "B",
            "applicability": applicability,
        }

    def check(self, path, profile, entity="entity-a", ay="2026-27"):
        return inspect_entity_profile(
            str(path), profile, expected_entity_key=entity,
            expected_assessment_year=ay, expected_itr_form="ITR-6",
        )

    def test_two_entities_same_form_and_year_have_different_subcomponents(self):
        alpha_profile=self.profile(self.alpha, "entity-a", [
            self.field("LOANS", "Base", "Long-term loans", "required"),
            self.field("RELATED", "Related Details", "Deposits from related parties", "required")
        ])
        beta_profile=self.profile(self.beta, "entity-b", [
            self.field("LOANS", "Base", "Long-term loans", "required"),
            self.field("RELATED", "Related Details", "Deposits from related parties", "not_applicable"),
        ])
        result_a=self.check(self.alpha, alpha_profile)
        result_b=self.check(self.beta, beta_profile, entity="entity-b")
        self.assertEqual(result_a["status"], "READY_FOR_MAPPING_REVIEW")
        self.assertEqual(result_b["status"], "READY_FOR_MAPPING_REVIEW")
        self.assertEqual(result_a["resolved_fields"], 2)
        self.assertEqual(result_b["resolved_fields"], 1)
        self.assertEqual({x["sheet"] for x in result_b["candidate_layout"]}, {"Base"})
        self.assertEqual(self.alpha.read_bytes(), self.alpha_before)
        self.assertEqual(self.beta.read_bytes(), self.beta_before)

    def test_profile_from_other_entity_must_not_be_applied(self):
        alpha_profile=self.profile(self.alpha, "entity-a", [
            self.field("RELATED", "Related Details", "Deposits from related parties", "required")
        ])
        with self.assertRaisesRegex(ValueError,"IDENTITY_OR_YEAR_MISMATCH"):
            self.check(self.alpha,alpha_profile,entity="entity-b")
        with self.assertRaisesRegex(ValueError,"TEMPLATE_CHANGED"):
            self.check(self.beta,alpha_profile)

    def test_previous_assessment_year_not_silently_reused(self):
        profile=self.profile(self.alpha,"entity-a",[
            self.field("LOANS","Base","Long-term loans","required")
        ])
        with self.assertRaisesRegex(ValueError,"IDENTITY_OR_YEAR_MISMATCH"):
            self.check(self.alpha,profile,ay="2027-28")

    def test_optional_absence_is_warning_not_required_field_error(self):
        profile=self.profile(self.beta,"entity-a",[
            self.field("LOANS","Base","Long-term loans","required"),
            self.field("RELATED","Related Details","Deposits from related parties","optional"),
        ])
        r=self.check(self.beta,profile)
        self.assertEqual(r["status"],"READY_FOR_MAPPING_REVIEW")
        self.assertEqual(r["blocking_exceptions"],[])
        self.assertEqual(r["optional_field_notices"][0]["code"],"REQUIRED_VENDOR_SHEET_ABSENT")
        self.assertEqual(r["resolved_fields"],1)

    def test_required_field_missing_blocks(self):
        profile=self.profile(self.beta,"entity-a",[
            self.field("RELATED","Related Details","Deposits from related parties","required")
        ])
        r=self.check(self.beta,profile)
        self.assertEqual(r["status"],"BLOCKED_REQUIRED_FIELD")
        self.assertIn("REQUIRED_VENDOR_SHEET_ABSENT",
                      [x["code"] for x in r["blocking_exceptions"]])

    def test_uncertain_applicability_not_assumed_zero(self):
        profile=self.profile(self.beta,"entity-a",[
            self.field("LOANS","Base","Long-term loans","required"),
            self.field("RELATED","Related Details","Deposits from related parties","review"),
        ])
        r=self.check(self.beta,profile)
        self.assertEqual(r["status"],"NEEDS_APPLICABILITY_REVIEW")
        self.assertEqual(len(r["applicability_review"]),1)
        self.assertEqual({x["field_id"] for x in r["candidate_layout"]},{"LOANS"})

    def test_only_private_validated_profiles_accepted(self):
        profile=self.profile(self.alpha,"entity-a",[
            self.field("LOANS","Base","Long-term loans","required")
        ])
        private=self.root/"private_profile.json"
        private.write_text(json.dumps(profile),encoding="utf-8")
        loaded=load_entity_profile(str(private))
        self.assertEqual(self.check(self.alpha,loaded)["resolved_fields"],1)
        profile["fields"][0]["applicability"]="guessed"
        private.write_text(json.dumps(profile))
        with self.assertRaisesRegex(ValueError,"applicability"):
            load_entity_profile(str(private))

    def test_different_rows_resolved_from_each_native_export(self):
        # Vendor may relocate labels between assessment-year exports.
        make_vendor(self.beta,row=31,include_details=True)
        profile=self.profile(self.beta,"entity-b",[
            self.field("RELATED","Related Details","Deposits from related parties","required")
        ])
        out=self.check(self.beta,profile,entity="entity-b")
        self.assertEqual(out["candidate_layout"][0]["cell"],"B31")


if __name__ == "__main__":
    unittest.main()
