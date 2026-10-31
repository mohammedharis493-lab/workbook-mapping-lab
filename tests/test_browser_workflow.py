"""Synthetic browser-workspace acceptance: FS -> review -> original export copy."""
import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from test_fs_extract import make_xlsx
from test_simulator import xlsx, write_csv
from test_manual_benchmark import native
from workbook_mapping_lab.review_browser import Workspace
from workbook_mapping_lab.simulator import WorkbookSnapshot


class BrowserWorkflowTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.fs=self.root/"fs.xlsx"
        self.template=self.root/"native.xlsx"
        self.output=self.root/"checked.xlsx"
        make_xlsx(self.fs,{
            1:{"A":"Statement 2026"},
            2:{"A":"Cash","C":100,"D":95},
            3:{"A":"Loans","C":100,"D":110},
            4:{"A":"Audit expenses","C":90,"D":85},
            5:{"A":"Registration costs","C":30,"D":25},
        })
        xlsx(self.template)
        self.profile=self.root/"profile.json"
        profile={"format":1,"ranges":[
            {"sheet":"Statement","section":section,
             "caption_column":"A","current_column":"C","previous_column":"D",
             "selected_rows":rows,"unit":"rupees",
             "period_header_cell":"A1","period_header_contains":"2026"}
            for section,rows in [("BS-A",[2]),("BS-L",[3]),("PL-E",[4,5])]
        ]}
        self.profile.write_text(json.dumps(profile),encoding="utf-8")
        self.layout=self.root/"layout.csv"
        write_csv(self.layout,
                  ("field_id","section","sheet","cell","anchor_cell","anchor_text"),[
            ("B-CASH","BS-A","Balance Sheet","B1","A1","Cash"),
            ("B-LOAN","BS-L","Balance Sheet","B2","A2","Loans"),
            ("P-AUDIT","PL-E","Profit & Loss Account","B1","A1","Audit fees"),
            ("P-OTHER","PL-E","Profit & Loss Account","B2","A2","Registration costs"),
        ])
        self.source_controls=self.root/"controls_fs.csv"
        self.output_controls=self.root/"controls_target.csv"
        write_csv(self.source_controls,("section","amount"),[
            ("BS-A",100),("BS-L",100),("PL-E",120)])
        write_csv(self.output_controls,("section","total"),[
            ("BS-A",100),("BS-L",100),("PL-E",120)])
        self.entity_manifest=self.root/"entity_schema_private.json"
        import csv
        with self.layout.open(encoding="utf-8", newline="") as file:
            layout_rows=list(csv.DictReader(file))
        fields=[{
            "field_id":line["field_id"],"section":line["section"],
            "sheet":line["sheet"],"caption":line["anchor_text"],
            "anchor_column":"A","amount_column":"B","applicability":"required",
        } for line in layout_rows]
        self.entity_manifest.write_text(json.dumps({
            "version":1,"entity_key":"synthetic-company",
            "assessment_year":"2026-27","itr_form":"ITR-6",
            "template_sha256":hashlib.sha256(self.template.read_bytes()).hexdigest(),
            "fields":fields,
        }),encoding="utf-8")
        self.w=Workspace()
        self.w.set_config({
            "source":str(self.fs),"profile":str(self.profile),
            "layout":str(self.layout),"folder":str(self.root/"private"),
            "template":str(self.template),"output":str(self.output),
            "source_controls":str(self.source_controls),
            "output_controls":str(self.output_controls),
            "entity_key":"synthetic-company",
            "assessment_year":"2026-27",
            "itr_form":"ITR-6",
            "entity_schema_profile":str(self.entity_manifest),
        })

    def test_full_review_and_copy_while_optional_warning_is_unreviewed(self):
        template_bytes=self.template.read_bytes()
        fs_bytes=self.fs.read_bytes()
        state=self.w.extract()
        self.assertEqual(len(state["entries"]),4)
        self.assertEqual(len(state["unresolved"]),4)
        self.assertEqual(state["issues"],[])
        self.assertTrue(all(w["blocking"] is False for w in state["warnings"]))
        by_caption={"Cash":"B-CASH","Loans":"B-LOAN",
                    "Audit expenses":"P-AUDIT","Registration costs":"P-OTHER"}
        for item in state["entries"]:
            self.w.approve({"source_id":item["source_id"],
                            "field_id":by_caption[item["caption"]]})
        self.assertEqual(self.w.data()["unresolved"],[])
        review=self.w.save_review()
        self.assertEqual(review["result"]["status"],"PASS")
        result=self.w.build()
        self.assertEqual(result["result"]["status"],"PASS")
        with WorkbookSnapshot(self.output) as generated:
            self.assertEqual(generated.cell("Balance Sheet","B1")["value"],"100")
            self.assertEqual(generated.cell("Balance Sheet","B2")["value"],"100")
            self.assertEqual(generated.cell("Profit & Loss Account","B1")["value"],"90")
            self.assertEqual(generated.cell("Profit & Loss Account","B2")["value"],"30")
        self.assertEqual(self.template.read_bytes(),template_bytes)
        self.assertEqual(self.fs.read_bytes(),fs_bytes)
        self.assertTrue(all(not w["blocking"] for w in self.w.warnings))

    def test_read_only_completed_return_benchmark_after_approved_build(self):
        self.w.extract()
        targets={"Cash":"B-CASH","Loans":"B-LOAN",
                 "Audit expenses":"P-AUDIT","Registration costs":"P-OTHER"}
        for item in self.w.data()["entries"]:
            self.w.approve({"source_id":item["source_id"],
                            "field_id":targets[item["caption"]]})
        self.w.save_review()
        result=self.w.build()
        self.assertEqual(result["result"]["status"],"PASS")
        reference=self.root/"manual_reference.xlsm"
        native(reference,["Part A-BS","Part P-L"],{
            "Part A-BS":{"A9":"Cash holdings","E9":100,
                         "A10":"Loans received","E10":100},
            "Part P-L":{"A11":"Audit costs","E11":90,
                        "A12":"Registration","E12":30},
        })
        compare=self.root/"comparison.csv"
        write_csv(compare,(
            "field_id","expected_amount","generated_sheet","generated_label",
            "generated_value_col","manual_sheet","manual_label","manual_value_col",
            "manual_label_cell"),[
            ("CASH",100,"Balance Sheet","Cash","B","Part A-BS","Cash holdings","E","A9"),
            ("LOAN",100,"Balance Sheet","Loans","B","Part A-BS","Loans received","E","A10"),
            ("AUDIT",90,"Profit & Loss Account","Audit fees","B","Part P-L","Audit costs","E","A11"),
            ("FEES",30,"Profit & Loss Account","Registration costs","B","Part P-L","Registration","E","A12"),
        ])
        before=self.output.read_bytes(),reference.read_bytes()
        self.w.set_config({"benchmark_generated":str(self.output),
                           "completed_reference":str(reference),
                           "benchmark_contract":str(compare)})
        result=self.w.benchmark_completed()["latest_benchmark"]
        self.assertEqual(result["status"],"ALL_CONFIGURED_FIELDS_MATCH")
        self.assertEqual(result["fully_matched"],4)
        self.assertEqual(result["unavailable_targets"],0)
        self.assertTrue(Path(result["private_report"]).exists())
        self.assertEqual(before,(self.output.read_bytes(),reference.read_bytes()))

    def test_native_import_checker_is_read_only_and_saves_private_report(self):
        ref=self.root/"independent.xlsm"
        native(ref,["ITR BS"],{"ITR BS":{
            "A10":"Cash holdings","E10":100,
            "A11":"Loans","E11":100
        }},hidden_sheets=("ITR BS",))
        contract=self.root/"intake_private.csv"
        write_csv(contract,(
            "field_id","expected_amount","generated_sheet","generated_label",
            "generated_value_col","manual_sheet","manual_label",
            "manual_value_col","manual_label_cell"),[
            ("CASH",100,"Balance Sheet","Cash","B","ITR BS","Cash holdings","E","A10"),
            ("LOAN",100,"Balance Sheet","Loans","B","ITR BS","Loans","E","A11")
        ])
        before=self.template.read_bytes(),ref.read_bytes()
        self.w.set_config({
            "completed_reference":str(ref),"benchmark_contract":str(contract)
        })
        r=self.w.check_native_import_intake()["latest_import_intake"]
        self.assertEqual(r["status"],"READY_FOR_ACCOUNTANT_MAPPING_REVIEW")
        self.assertEqual(r["field_count"],2)
        self.assertEqual(r["import_cells_available"],2)
        self.assertTrue(Path(r["private_report"]).exists())
        self.assertFalse(self.output.exists())
        self.assertEqual(before,(self.template.read_bytes(),ref.read_bytes()))

    def test_replacement_export_checked_without_changing_selected_template(self):
        ref=self.root/"independent.xlsm"
        native(ref,["ITR BS"],{"ITR BS":{"A10":"Cash","E10":100}})
        contract=self.root/"intake.csv"
        write_csv(contract,(
            "field_id","expected_amount","generated_sheet","generated_label",
            "generated_value_col","manual_sheet","manual_label",
            "manual_value_col","manual_label_cell"),[
            ("CASH",100,"Balance Sheet","Cash","B","ITR BS","Cash","E","A10")
        ])
        replacement=self.root/"replacement.xlsx"
        replacement.write_bytes(self.template.read_bytes())
        self.w.set_config({
            "intake_template":str(replacement),
            "completed_reference":str(ref),"benchmark_contract":str(contract)
        })
        result=self.w.check_native_import_intake()["latest_import_intake"]
        self.assertEqual(result["import_cells_available"],1)
        self.assertEqual(self.w.config["template"],str(self.template))
        self.assertIsNone(self.w.latest_saved)

    def test_browser_discovers_reviewed_profile_and_checked_build(self):
        untouched=self.template.read_bytes()
        state=self.w.discover_entity_candidates()
        scan=state["entity_discovery"]
        self.assertEqual(scan["matched_existing_layout"],4)
        self.assertTrue(all(not item["reviewed"] for item in scan["candidates"]))
        selected=[item for item in scan["candidates"] if item["selected"]]
        self.assertEqual(len(selected),4)
        for item in selected:
            updated=self.w.review_entity_candidate({
                "candidate_id":item["candidate_id"],
                "selected":True,
                "field_id":item["field_id"],
                "section":item["section"],
                "applicability":"required",
            })
        created=self.w.export_entity_candidate_profile()
        self.assertTrue(Path(created["path"]).exists())
        self.assertEqual(created["latest_entity_schema"]["status"],"READY_FOR_MAPPING_REVIEW")
        self.assertEqual(self.template.read_bytes(),untouched)
        self.w.extract()
        mapping={"Cash":"B-CASH","Loans":"B-LOAN",
                 "Audit expenses":"P-AUDIT","Registration costs":"P-OTHER"}
        for entry in self.w.data()["entries"]:
            self.w.approve({"source_id":entry["source_id"],
                            "field_id":mapping[entry["caption"]]})
        self.w.save_review()
        result=self.w.build()
        self.assertEqual(result["result"]["status"],"PASS")
        self.assertEqual(self.template.read_bytes(),untouched)

    def test_browser_discovery_export_fails_when_fields_are_unreviewed(self):
        data=self.w.discover_entity_candidates()
        self.assertTrue(data["entity_discovery"]["matched_existing_layout"])
        with self.assertRaisesRegex(ValueError,"explicit applicability"):
            self.w.export_entity_candidate_profile()
        self.assertEqual(self.w.config["entity_schema_profile"],str(self.entity_manifest))

    def test_browser_discovery_invalidated_when_target_template_changes(self):
        data=self.w.discover_entity_candidates()
        self.assertIsNotNone(data["entity_discovery"])
        other=self.root/"different.xlsx"
        other.write_bytes(self.template.read_bytes())
        self.w.set_config({"template":str(other)})
        self.assertIsNone(self.w.entity_discovery)
        with self.assertRaisesRegex(ValueError,"Scan"):
            self.w.export_entity_candidate_profile()

    def test_missing_schema_blocks_even_after_approved_mapping(self):
        self.w.extract()
        destinations={"Cash":"B-CASH","Loans":"B-LOAN",
                      "Audit expenses":"P-AUDIT","Registration costs":"P-OTHER"}
        for line in self.w.data()["entries"]:
            self.w.approve({"source_id":line["source_id"],
                            "field_id":destinations[line["caption"]]})
        self.w.save_review()
        self.w.config["entity_schema_profile"]=""
        with self.assertRaisesRegex(ValueError,"entity schema profile"):
            self.w.build()
        self.assertFalse(self.output.exists())

    def test_other_entity_cannot_build(self):
        self.w.extract()
        destinations={"Cash":"B-CASH","Loans":"B-LOAN",
                      "Audit expenses":"P-AUDIT","Registration costs":"P-OTHER"}
        for line in self.w.data()["entries"]:
            self.w.approve({"source_id":line["source_id"],
                            "field_id":destinations[line["caption"]]})
        self.w.save_review()
        self.w.config["entity_key"]="different-company"
        with self.assertRaisesRegex(ValueError,"IDENTITY_OR_YEAR_MISMATCH"):
            self.w.build()
        self.assertFalse(self.output.exists())

    def test_no_build_without_explicit_review_and_saved_controls(self):
        state=self.w.extract()
        self.assertEqual(len(state["unresolved"]),4)
        with self.assertRaisesRegex(ValueError,"approval"):
            self.w.build()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.template.read_bytes()==b"")

    def _review_all_synthetic_entries(self):
        self.w.extract()
        destinations={"Cash":"B-CASH","Loans":"B-LOAN",
                      "Audit expenses":"P-AUDIT","Registration costs":"P-OTHER"}
        for row in self.w.data()["entries"]:
            self.w.approve({"source_id":row["source_id"],
                            "field_id":destinations[row["caption"]]})

    def test_changed_same_path_financials_invalidate_saved_approval(self):
        """A reused filename does not make an altered source approved."""
        self._review_all_synthetic_entries()
        self.assertEqual(self.w.save_review()["result"]["status"],"PASS")
        make_xlsx(self.fs,{
            1:{"A":"Statement 2026"},2:{"A":"Cash","C":101,"D":95},
            3:{"A":"Loans","C":100,"D":110},
            4:{"A":"Audit expenses","C":90,"D":85},
            5:{"A":"Registration costs","C":30,"D":25},
        })
        with self.assertRaisesRegex(ValueError,"REVIEW_INPUT_CHANGED"):
            self.w.build()
        self.assertIsNone(self.w.review)
        self.assertIsNone(self.w.latest_saved)
        self.assertFalse(self.output.exists())

    def test_changed_same_path_layout_blocks_review_export(self):
        self._review_all_synthetic_entries()
        with self.layout.open("a",encoding="utf-8") as stream:
            stream.write("\n")
        with self.assertRaisesRegex(ValueError,"REVIEW_INPUT_CHANGED"):
            self.w.save_review()
        self.assertIsNone(self.w.review)

    def test_identical_same_path_bytes_remain_eligible(self):
        self._review_all_synthetic_entries()
        content=self.fs.read_bytes()
        self.fs.write_bytes(content)
        self.assertEqual(self.w.save_review()["result"]["status"],"PASS")
        self.assertEqual(self.w.build()["result"]["status"],"PASS")

    def test_missing_reviewed_input_never_builds(self):
        self._review_all_synthetic_entries()
        self.w.save_review()
        self.fs.unlink()
        with self.assertRaisesRegex(ValueError,"REVIEW_INPUT_CHANGED"):
            self.w.build()
        self.assertFalse(self.output.exists())

    def test_switching_previous_target_invalidates_existing_review(self):
        self._review_all_synthetic_entries()
        self.assertIsNotNone(self.w.review)
        self.w.set_config({"previous_target":str(self.root/"new_reference.xlsx")})
        self.assertIsNone(self.w.review)
        self.assertIsNone(self.w._review_input_sha256)


if __name__=="__main__":
    unittest.main()


