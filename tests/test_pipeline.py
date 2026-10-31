"""End-to-end examples use made-up values and ephemeral blank templates."""
import json
import hashlib
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from test_simulator import xlsx, write_csv
from workbook_mapping_lab.pipeline import controlled_build, main as pipeline_main
from workbook_mapping_lab.simulator import WorkbookSnapshot


class PipelineTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.template=self.root/"blank.xlsx"
        xlsx(self.template)
        self.source=self.root/"source.csv"
        self.rules=self.root/"rules.csv"
        self.layout=self.root/"layout.csv"
        self.source_controls=self.root/"source_controls.csv"
        self.output_controls=self.root/"output_controls.csv"
        self.output=self.root/"approved.xlsx"
        self.report=self.root/"report.json"
        self.sources=[
            ("CASH1","BS-A","Till","40.00","rupees"),
            ("CASH2","BS-A","Bank","60.00","rupees"),
            ("LOAN","BS-L","Borrowing","100.00","rupees"),
            ("AUDIT","PL-E","Audit expenses","90","rupees"),
            ("OTHER","PL-E","Other fees","30","rupees"),
        ]
        self.rules_rows=[
            ("CASH1","B-CASH","yes","1","keep"),
            ("CASH2","B-CASH","yes","1","keep"),
            ("LOAN","B-LOAN","yes","1","keep"),
            ("AUDIT","P-AUDIT","yes","1","keep"),
            ("OTHER","P-OTHER","yes","1","keep"),
        ]
        self.layout_rows=[
            ("B-CASH","BS-A","Balance Sheet","B1","A1","Cash"),
            ("B-LOAN","BS-L","Balance Sheet","B2","A2","Loans"),
            ("P-AUDIT","PL-E","Profit & Loss Account","B1","A1","Audit fees"),
            ("P-OTHER","PL-E","Profit & Loss Account","B2","A2","Registration costs"),
        ]
        self.write_inputs()

    def write_inputs(self):
        write_csv(self.source,("source_id","section","caption","amount","unit"),self.sources)
        write_csv(self.rules,("source_id","field_id","approved","portion","sign"),self.rules_rows)
        write_csv(self.layout,("field_id","section","sheet","cell","anchor_cell","anchor_text"),self.layout_rows)
        write_csv(self.source_controls,("section","amount"),
            [("BS-A","100"),("BS-L","100"),("PL-E","120")])
        write_csv(self.output_controls,("section","total"),
            [("BS-A","100"),("BS-L","100"),("PL-E","120")])

    def build(self,rounding="exact"):
        return controlled_build(
            source=str(self.source),rules=str(self.rules),
            layout=str(self.layout),template=str(self.template),
            source_controls=str(self.source_controls),output_controls=str(self.output_controls),
            output=str(self.output),exception_report=str(self.report),rounding=rounding)

    def test_synthetic_full_pipeline(self):
        result=self.build()
        self.assertEqual(result["status"],"PASS")
        self.assertEqual(result["mapped_field_count"],4)
        self.assertTrue(self.output.exists())
        self.assertTrue(self.report.exists())
        with WorkbookSnapshot(self.output) as book:
            self.assertEqual(book.cell("Balance Sheet","B1")["value"],"100.00")
        with WorkbookSnapshot(self.template) as original:
            self.assertEqual(original.cell("Balance Sheet","B1")["value"],"")

    def test_exception_blocks_output_and_audits(self):
        self.sources.append(("NEW","PL-E","New charge","15","rupees"))
        self.write_inputs()
        result=self.build()
        self.assertEqual(result["status"],"BLOCKED")
        self.assertFalse(self.output.exists())
        self.assertTrue(self.report.exists())
        self.assertIn("UNMAPPED_OR_NOT_APPROVED", [i["issue"] for i in result["exceptions"]])

    def test_controls_block_unbalanced_bs(self):
        self.sources[2]=("LOAN","BS-L","Borrowing","105.00","rupees")
        self.write_inputs()
        result=self.build()
        self.assertEqual(result["status"],"BLOCKED")
        self.assertFalse(self.output.exists())
        self.assertIn("SOURCE_CONTROL_MISMATCH", [i["issue"] for i in result["exceptions"]])

    def test_half_up_rounding_requires_matching_control(self):
        self.sources[0]=("CASH1","BS-A","Till","40.49","rupees")
        self.sources[1]=("CASH2","BS-A","Bank","59.51","rupees")
        self.sources[2]=("LOAN","BS-L","Borrowing","100.0","rupees")
        self.write_inputs()
        result=self.build(rounding="whole_rupees")
        self.assertEqual(result["status"],"PASS")
        with WorkbookSnapshot(self.output) as filled:
            self.assertEqual(filled.cell("Balance Sheet","B1")["value"],"100")

    def test_nonapproved_rule_does_not_leak_to_writer(self):
        self.rules_rows[4]=("OTHER","P-OTHER","no","1","keep")
        self.write_inputs()
        result=self.build()
        self.assertEqual(result["status"],"BLOCKED")
        self.assertFalse(self.output.exists())

    def secure_cli_args(self):
        schema=self.root/"private_entity_schema.json"
        schema.write_text(json.dumps({
            "version":1,"entity_key":"synthetic-entity",
            "assessment_year":"2026-27","itr_form":"ITR-6",
            "template_sha256":hashlib.sha256(self.template.read_bytes()).hexdigest(),
            "fields":[{
                "field_id":fid,"section":section,"sheet":sheet,"caption":caption,
                "anchor_column":"A","amount_column":"B","applicability":"required",
            } for fid,section,sheet,cell,anchor,caption in self.layout_rows],
        }),encoding="utf-8")
        return ["pipeline",
            "--source",str(self.source),"--rules",str(self.rules),
            "--layout",str(self.layout),"--template",str(self.template),
            "--source-controls",str(self.source_controls),
            "--output-controls",str(self.output_controls),
            "--output",str(self.output),"--exception-report",str(self.report),
            "--entity-schema-profile",str(schema),
            "--entity-key","synthetic-entity", "--assessment-year","2026-27",
            "--itr-form","ITR-6",
        ]

    def test_cli_build_requires_explicit_entity_schema(self):
        args=self.secure_cli_args()
        with patch.object(sys,"argv",args[:-8]):
            with redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as error:
                pipeline_main()
        self.assertEqual(error.exception.code,2)
        self.assertFalse(self.output.exists())

    def test_cli_build_uses_private_schema_preflight(self):
        with patch.object(sys,"argv",self.secure_cli_args()):
            with redirect_stdout(io.StringIO()):
                pipeline_main()
        self.assertTrue(self.output.exists())
        self.assertTrue(self.report.exists())

    def test_cli_cross_entity_profile_fails_before_any_output(self):
        args=self.secure_cli_args()
        args[args.index("--entity-key")+1]="another-entity"
        with patch.object(sys,"argv",args):
            with self.assertRaisesRegex(ValueError,"IDENTITY_OR_YEAR_MISMATCH"):
                pipeline_main()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.report.exists())


if __name__ == "__main__":
    unittest.main()
