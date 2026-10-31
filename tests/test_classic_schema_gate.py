"""Headless Classic UI contract: schema preflight precedes any copy-write."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from workbook_mapping_lab.build_integrity import BuildInputGuard
from workbook_mapping_lab.review_gui import REVIEW_INPUT_KEYS, ReviewDesk


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
            "folder":"synthetic-private-folder",
            "source":"synthetic-fs.xlsx",
            "previous":"",
            "profile":"synthetic-extraction-profile.json",
            "prior_rules":"",
            "previous_target":"",
            "source_controls":"synthetic-source-controls.csv",
            "output_controls":"synthetic-target-controls.csv",
            "companion_details":"",
            "output":"synthetic-output.xlsx",
        }
        return SimpleNamespace(
            review=SimpleNamespace(unresolved=lambda:[]),
            latest_saved={"status":"PASS","sources":"approved-sources.csv",
                          "rules":"approved-rules.csv"},
            _file=lambda key,required=True:settings[key],
            _require_fresh_review_inputs=Mock(),
            _show_error=lambda error:errors.append(str(error)),
        ),errors

    def test_classic_review_pin_rejects_same_path_content_change(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"synthetic-source.xlsx"
            source.write_bytes(b"original synthetic figures")
            selected={key:"" for key in REVIEW_INPUT_KEYS}
            selected["source"]=str(source)
            desk=SimpleNamespace(
                review=object(),latest_saved={"status":"PASS"},
                _review_input_paths=dict(selected),
                _review_input_guard=BuildInputGuard(selected.values()),
                _file=lambda key,required=True:selected[key],
            )
            self.assertIsNone(ReviewDesk._require_fresh_review_inputs(desk))
            source.write_bytes(b"changed synthetic figures")
            with self.assertRaisesRegex(ValueError,"REVIEW_INPUT_CHANGED"):
                ReviewDesk._require_fresh_review_inputs(desk)
            self.assertIsNone(desk.review)
            self.assertIsNone(desk.latest_saved)
            self.assertIsNone(desk._review_input_guard)

    def test_classic_review_pin_accepts_identical_bytes_but_rejects_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"synthetic-source.xlsx"
            source.write_bytes(b"stable approved synthetic evidence")
            selected={key:"" for key in REVIEW_INPUT_KEYS}
            selected["source"]=str(source)
            desk=SimpleNamespace(
                review=object(),latest_saved={"status":"PASS"},
                _review_input_paths=dict(selected),
                _review_input_guard=BuildInputGuard(selected.values()),
                _file=lambda key,required=True:selected[key],
            )
            source.write_bytes(b"stable approved synthetic evidence")
            self.assertIsNone(ReviewDesk._require_fresh_review_inputs(desk))
            source.unlink()
            with self.assertRaisesRegex(ValueError,"REVIEW_INPUT_CHANGED"):
                ReviewDesk._require_fresh_review_inputs(desk)
            self.assertIsNone(desk.latest_saved)

    def test_classic_extraction_establishes_the_review_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"synthetic-source.xlsx"
            profile=Path(directory)/"profile.json"
            layout=Path(directory)/"layout.csv"
            source.write_bytes(b"source at review extraction")
            profile.write_bytes(b"reviewed profile")
            layout.write_bytes(b"reviewed layout")
            selected={key:"" for key in REVIEW_INPUT_KEYS}
            selected.update({"source":str(source),"profile":str(profile),
                             "layout":str(layout)})
            errors=[]
            desk=SimpleNamespace(
                review=object(),latest_saved={"status":"PASS"},
                _review_input_paths=None,_review_input_guard=None,
                _file=lambda key,required=True:selected[key],
                _show_error=lambda error:errors.append(str(error)),
                _draw_rows=Mock(),refresh_warnings=Mock(),
                status=SimpleNamespace(set=Mock()),
            )
            with patch("workbook_mapping_lab.review_gui.load_profile",return_value={"ranges":[]}):
                with patch("workbook_mapping_lab.review_gui.load_csv",return_value=[]):
                    with patch("workbook_mapping_lab.review_gui.extract_profile",
                               return_value=([],[])):
                        ReviewDesk.load_selected(desk)
            self.assertEqual(errors,[])
            self.assertIsNotNone(desk.review)
            self.assertIsNotNone(desk._review_input_guard)
            source.write_bytes(b"source changed after review extraction")
            with self.assertRaisesRegex(ValueError,"REVIEW_INPUT_CHANGED"):
                ReviewDesk._require_fresh_review_inputs(desk)

    def test_classic_review_pin_rejects_path_swap_even_if_contents_match(self):
        with tempfile.TemporaryDirectory() as directory:
            original=Path(directory)/"original.xlsx"
            replacement=Path(directory)/"replacement.xlsx"
            original.write_bytes(b"same example contents")
            replacement.write_bytes(b"same example contents")
            selected={key:"" for key in REVIEW_INPUT_KEYS}
            selected["source"]=str(original)
            desk=SimpleNamespace(
                review=object(),latest_saved={"status":"PASS"},
                _review_input_paths=dict(selected),
                _review_input_guard=BuildInputGuard(selected.values()),
                _file=lambda key,required=True:selected[key],
            )
            selected["source"]=str(replacement)
            with self.assertRaisesRegex(ValueError,"REVIEW_INPUT_CHANGED"):
                ReviewDesk._require_fresh_review_inputs(desk)
            self.assertIsNone(desk.review)

    def test_classic_export_blocks_stale_review_before_creating_csv(self):
        desk,errors=self.fake_desk()
        desk.review=SimpleNamespace(save_review=Mock())
        desk._require_fresh_review_inputs.side_effect=ValueError("REVIEW_INPUT_CHANGED")
        ReviewDesk.export_review(desk)
        desk.review.save_review.assert_not_called()
        self.assertEqual(errors,["REVIEW_INPUT_CHANGED"])

    def test_classic_export_invalidates_review_if_source_changes_during_save(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"synthetic-source.xlsx"
            source.write_bytes(b"reviewed synthetic evidence")
            selected={key:"" for key in REVIEW_INPUT_KEYS}
            selected["source"]=str(source)
            errors=[]
            artifacts={
                "report":Path(directory)/"review_exceptions.json",
                "sources":Path(directory)/"review_sources.csv",
                "rules":Path(directory)/"review_rules.csv",
            }
            def mutate_while_saving(*args,**kwargs):
                artifacts["report"].write_text('{"status":"PASS"}',encoding="utf-8")
                artifacts["sources"].write_text("old approved figures",encoding="utf-8")
                artifacts["rules"].write_text("old approved mappings",encoding="utf-8")
                source.write_bytes(b"changed after approved export started")
                return {"status":"PASS",**{
                    key:str(path) for key,path in artifacts.items()
                }}
            desk=SimpleNamespace(
                review=SimpleNamespace(save_review=mutate_while_saving),
                latest_saved=None,
                _review_input_paths=dict(selected),
                _review_input_guard=BuildInputGuard(selected.values()),
                _file=lambda key,required=True:directory if key=="folder" else selected[key],
                _show_error=lambda error:errors.append(str(error)),
            )
            desk._require_fresh_review_inputs=lambda:ReviewDesk._require_fresh_review_inputs(desk)
            ReviewDesk.export_review(desk)
            self.assertEqual(len(errors),1)
            self.assertIn("REVIEW_INPUT_CHANGED",errors[0])
            self.assertIsNone(desk.latest_saved)
            self.assertIsNone(desk.review)
            self.assertFalse(any(path.exists() for path in artifacts.values()))

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

    def test_classic_build_blocks_change_during_confirmation(self):
        desk,errors=self.fake_desk()
        desk._require_fresh_review_inputs.side_effect=[
            None,ValueError("REVIEW_INPUT_CHANGED")
        ]
        with patch("workbook_mapping_lab.review_gui.require_approved_entity_schema"):
            with patch("workbook_mapping_lab.review_gui.messagebox.askyesno",
                       return_value=True):
                with patch("workbook_mapping_lab.review_gui.controlled_build") as build:
                    ReviewDesk.build_copy(desk)
        build.assert_not_called()
        self.assertEqual(errors,["REVIEW_INPUT_CHANGED"])

    def test_classic_build_rechecks_schema_and_inputs_before_release(self):
        desk,errors=self.fake_desk()

        def simulated_pipeline(**kwargs):
            kwargs["before_release"]()

        with patch("workbook_mapping_lab.review_gui.require_approved_entity_schema") as gate:
            with patch("workbook_mapping_lab.review_gui.messagebox.askyesno",
                       return_value=True):
                with patch("workbook_mapping_lab.review_gui.BuildInputGuard") as pinned:
                    with patch("workbook_mapping_lab.review_gui.require_private_directory",
                               return_value=Path("synthetic-private")):
                        with patch("workbook_mapping_lab.review_gui.controlled_build",
                                   side_effect=simulated_pipeline):
                            pinned.return_value.verify.side_effect=ValueError("BUILD_INPUT_CHANGED")
                            ReviewDesk.build_copy(desk)
        self.assertEqual(gate.call_count,2)
        pinned.return_value.verify.assert_called_once()
        self.assertEqual(errors,["BUILD_INPUT_CHANGED"])


if __name__=="__main__":
    unittest.main()
