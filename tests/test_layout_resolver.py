"""Synthetic only: approved routes resolved against native blank vendor exports."""
import sys
import json
import hashlib
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
from xml.etree import ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from test_simulator import NS, REL, PKG, write_csv
from workbook_mapping_lab.layout_resolver import resolve_layout, write_private_layout
from workbook_mapping_lab.writer import populate, main as writer_main
from workbook_mapping_lab.simulator import WorkbookSnapshot


def make_vendor(path, *, row=11, second=False, occupied=False, include_details=True):
    wb=ET.Element("{"+NS+"}workbook",{"xmlns:r":REL})
    sheets=ET.SubElement(wb,"{"+NS+"}sheets")
    all_sheets=["Base"]+(["Related Details"] if include_details else [])
    for n,name in enumerate(all_sheets,1):
        ET.SubElement(sheets,"{"+NS+"}sheet",{
            "name":name,"sheetId":str(n),"{"+REL+"}id":"rId"+str(n)})
    links=ET.Element("{"+PKG+"}Relationships")
    for n in range(1,len(all_sheets)+1):
        ET.SubElement(links,"{"+PKG+"}Relationship",{
            "Id":"rId"+str(n),"Type":REL+"/worksheet",
            "Target":f"worksheets/sheet{n}.xml"})
    with ZipFile(path,"w") as z:
        z.writestr("xl/workbook.xml",ET.tostring(wb))
        z.writestr("xl/_rels/workbook.xml.rels",ET.tostring(links))
        for i,name in enumerate(all_sheets,1):
            root=ET.Element("{"+NS+"}worksheet")
            data=ET.SubElement(root,"{"+NS+"}sheetData")
            for r in ([row,row+1] if second and name=="Related Details" else [row]):
                this=ET.SubElement(data,"{"+NS+"}row",{"r":str(r)})
                c=ET.SubElement(this,"{"+NS+"}c",{"r":"A"+str(r),"t":"inlineStr"})
                ET.SubElement(ET.SubElement(c,"{"+NS+"}is"),"{"+NS+"}t").text=(
                    "Deposits from related parties" if name=="Related Details" else "Long-term loans")
                val=ET.SubElement(this,"{"+NS+"}c",{"r":"B"+str(r)})
                if occupied:ET.SubElement(val,"{"+NS+"}v").text="45"
            z.writestr(f"xl/worksheets/sheet{i}.xml",ET.tostring(root))


class ResolverTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.vendor=self.root/"vendor.xlsx"
        self.route=[{"field_id":"RELATED","section":"BS-L","sheet":"Related Details",
                     "caption":"Deposits from related parties",
                     "anchor_column":"A","amount_column":"B"}]
        make_vendor(self.vendor)

    def test_resolves_unchanged_exact_export(self):
        untouched=self.vendor.read_bytes()
        result=resolve_layout(str(self.vendor),self.route)
        self.assertEqual(result["status"],"READY")
        self.assertEqual(result["layout"][0]["cell"],"B11")
        self.assertEqual(self.vendor.read_bytes(),untouched)

    def test_follows_rows_when_vendor_moves_them(self):
        make_vendor(self.vendor,row=37)
        result=resolve_layout(str(self.vendor),self.route)
        self.assertEqual(result["status"],"READY")
        self.assertEqual(result["layout"][0]["cell"],"B37")

    def test_refuses_missing_detail_sheets(self):
        make_vendor(self.vendor,include_details=False)
        result=resolve_layout(str(self.vendor),self.route)
        self.assertEqual(result["status"],"BLOCKED")
        self.assertIn("REQUIRED_VENDOR_SHEET_ABSENT",
                      [x["code"] for x in result["exceptions"]])

    def test_refuses_ambiguous_same_name(self):
        make_vendor(self.vendor,second=True)
        result=resolve_layout(str(self.vendor),self.route)
        self.assertEqual(result["status"],"BLOCKED")
        self.assertIn("CAPTION_NOT_UNIQUE_OR_ABSENT",
                      [x["code"] for x in result["exceptions"]])

    def test_refuses_occupied_vendor_cell(self):
        make_vendor(self.vendor,occupied=True)
        result=resolve_layout(str(self.vendor),self.route)
        self.assertEqual(result["status"],"BLOCKED")
        self.assertIn("VENDOR_DESTINATION_OCCUPIED",
                      [x["code"] for x in result["exceptions"]])

    def test_unchanged_vendor_package_when_filling_with_writer(self):
        result=resolve_layout(str(self.vendor),self.route)
        layout=self.root/"resolved.csv"
        write_private_layout(result,str(layout))
        rows=self.root/"amounts.csv"
        write_csv(rows,("field_id","section","amount"),[("RELATED","BS-L","4380")])
        out=self.root/"checked.xlsx"
        result=populate(str(self.vendor),str(layout),str(rows),str(out))
        self.assertEqual(result["status"],"PASS")
        with WorkbookSnapshot(out) as final:
            self.assertEqual(final.cell("Related Details","B11")["value"],"4380")
        with ZipFile(self.vendor) as before,ZipFile(out) as after:
            self.assertEqual(before.namelist(),after.namelist())
            changes=[p for p in before.namelist() if before.read(p)!=after.read(p)]
            self.assertEqual(changes,["xl/worksheets/sheet2.xml"])

    def test_duplicate_field_and_target_refused(self):
        result=resolve_layout(str(self.vendor),self.route+self.route)
        self.assertEqual(result["status"],"BLOCKED")
        self.assertIn("DUPLICATE_OR_BLANK_FIELD_ID",[x["code"] for x in result["exceptions"]])

    def secure_writer_cli_args(self):
        profile=self.root/"reviewed_entity.json"
        profile.write_text(json.dumps({
            "version":1,"entity_key":"synthetic-entity",
            "assessment_year":"2026-27","itr_form":"ITR-6",
            "template_sha256":hashlib.sha256(self.vendor.read_bytes()).hexdigest(),
            "fields":[{
                **self.route[0],"applicability":"required",
            }],
        }),encoding="utf-8")
        resolved=resolve_layout(str(self.vendor),self.route)
        layout=self.root/"layout.csv"
        write_private_layout(resolved,str(layout))
        values=self.root/"values.csv"
        write_csv(values,("field_id","section","amount"),[("RELATED","BS-L","4380")])
        output=self.root/"writer_checked.xlsx"
        return ["writer", "--template",str(self.vendor),
            "--layout",str(layout),"--values",str(values),
            "--output",str(output),"--entity-schema-profile",str(profile),
            "--entity-key","synthetic-entity","--assessment-year","2026-27",
            "--itr-form","ITR-6"]

    def test_writer_cli_requires_reviewed_entity_schema(self):
        args=self.secure_writer_cli_args()
        with patch.object(sys,"argv",args[:-8]):
            with redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as error:
                writer_main()
        self.assertEqual(error.exception.code,2)
        self.assertFalse((self.root/"writer_checked.xlsx").exists())

    def test_writer_cli_runs_after_exact_schema_preflight(self):
        args=self.secure_writer_cli_args()
        with patch.object(sys,"argv",args):
            with redirect_stdout(io.StringIO()):
                writer_main()
        with WorkbookSnapshot(self.root/"writer_checked.xlsx") as output:
            self.assertEqual(output.cell("Related Details","B11")["value"],"4380")

    def test_writer_cli_rejects_wrong_entity_before_creating_copy(self):
        args=self.secure_writer_cli_args()
        args[args.index("--entity-key")+1]="different-entity"
        with patch.object(sys,"argv",args):
            with self.assertRaisesRegex(ValueError,"IDENTITY_OR_YEAR_MISMATCH"):
                writer_main()
        self.assertFalse((self.root/"writer_checked.xlsx").exists())


if __name__=="__main__":
    unittest.main()
