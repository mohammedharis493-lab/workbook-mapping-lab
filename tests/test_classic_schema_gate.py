"""Headless Classic UI contract: schema preflight precedes any copy-write."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from workbook_mapping_lab.review_gui import ReviewDesk


class ClassicSchemaGateTests(unittest.TestCase):
    def fake_desk(self):
        errors=[]
        settings={
            "template":"synthetic-template.xlsx",
            "layout":"synthetic-layout.csv",
            "entity_schema_profile":"synthetic-reviewed-profile.json",
            "entity_key":"synthetic-entity",
            "assessment_year":"2026-27",
            "itr_form":"ITR-6",
        }
        return SimpleNamespace(
            review=SimpleNamespace(unresolved=lambda:[]),
            latest_saved={"status":"PASS"},
            _file=lambda key,required=True:settings[key],
            _show_error=lambda error:errors.append(str(error)),
        ),errors

    def test_classic_build_refuses_schema_failure_before_confirmation(self):
        desk,errors=self.fake_desk()
        with patch("workbook_mapping_lab.review_gui.require_approved_entity_schema",
                   side_effect=ValueError("ENTITY_SCHEMA_LAYOUT_MISMATCH")) as gate:
            with patch("workbook_mapping_lab.review_gui.messagebox.askyesno") as ask:
                with patch("workbook_mapping_lab.review_gui.controlled_build") as build:
                    ReviewDesk.build_copy(desk)
        gate.assert_called_once()
        ask.assert_not_called()
        build.assert_not_called()
        self.assertEqual(errors,["ENTITY_SCHEMA_LAYOUT_MISMATCH"])

    def test_classic_build_still_requires_confirmation_after_valid_schema(self):
        desk,errors=self.fake_desk()
        with patch("workbook_mapping_lab.review_gui.require_approved_entity_schema",
                   return_value={"status":"READY_FOR_MAPPING_REVIEW"}) as gate:
            with patch("workbook_mapping_lab.review_gui.messagebox.askyesno",
                       return_value=False) as ask:
                with patch("workbook_mapping_lab.review_gui.controlled_build") as build:
                    ReviewDesk.build_copy(desk)
        gate.assert_called_once()
        ask.assert_called_once()
        build.assert_not_called()
        self.assertEqual(errors,[])


if __name__=="__main__":
    unittest.main()
