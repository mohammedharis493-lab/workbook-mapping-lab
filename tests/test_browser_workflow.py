"""Synthetic browser-workspace acceptance: FS -> review -> original export copy."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from test_fs_extract import make_xlsx
from test_simulator import xlsx, write_csv
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
            ("BS-A",100),("BS-L",200),("PL-E",120)])
        self.w=Workspace()
        self.w.set_config({
            "source":str(self.fs),"profile":str(self.profile),
            "layout":str(self.layout),"folder":str(self.root/"private"),
            "template":str(self.template),"output":str(self.output),
            "source_controls":str(self.source_controls),
            "output_controls":str(self.output_controls),
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

    def test_no_build_without_explicit_review_and_saved_controls(self):
        state=self.w.extract()
        self.assertEqual(len(state["unresolved"]),4)
        with self.assertRaisesRegex(ValueError,"approval"):
            self.w.build()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.template.read_bytes()==b"")


if __name__=="__main__":
    unittest.main()
