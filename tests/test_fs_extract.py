"""Synthetic XLSX extraction tests. No client sheets or financial figures."""
import sys
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from workbook_mapping_lab.fs_extract import (
    canonical_caption, extract_profile, numeric, scan_sheet, validate_profile)
from workbook_mapping_lab.simulator import WorkbookSnapshot

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


def make_xlsx(path, rows):
    root = ET.Element("{"+NS+"}workbook", {"xmlns:r":REL})
    sheets=ET.SubElement(root,"{"+NS+"}sheets")
    ET.SubElement(sheets,"{"+NS+"}sheet",{
        "name":"Statement","sheetId":"1","{"+REL+"}id":"rId1"})
    links=ET.Element("{"+PKG+"}Relationships")
    ET.SubElement(links,"{"+PKG+"}Relationship",{
        "Id":"rId1","Type":REL+"/worksheet","Target":"worksheets/sheet1.xml"})
    xml=ET.Element("{"+NS+"}worksheet")
    data=ET.SubElement(xml,"{"+NS+"}sheetData")
    for row_num, values in sorted(rows.items()):
        row=ET.SubElement(data,"{"+NS+"}row",{"r":str(row_num)})
        for col,value in values.items():
            if value is None: continue
            if isinstance(value,(int,float)):
                cell=ET.SubElement(row,"{"+NS+"}c",{"r":col+str(row_num)})
                ET.SubElement(cell,"{"+NS+"}v").text=str(value)
            else:
                cell=ET.SubElement(row,"{"+NS+"}c",{"r":col+str(row_num),"t":"inlineStr"})
                ET.SubElement(ET.SubElement(cell,"{"+NS+"}is"),"{"+NS+"}t").text=str(value)
    with ZipFile(path,"w") as z:
        z.writestr("xl/workbook.xml",ET.tostring(root,encoding="utf8"))
        z.writestr("xl/_rels/workbook.xml.rels",ET.tostring(links,encoding="utf8"))
        z.writestr("xl/worksheets/sheet1.xml",ET.tostring(xml,encoding="utf8"))


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.now=self.root/"now.xlsx"
        self.before=self.root/"before.xlsx"
        self.rows={
            1:{"A":"Statement 2026"},
            2:{"A":"Share capital","C":125,"D":110},
            3:{"A":"Liabilities","C":45,"D":48},
            4:{"A":"Cash and Bank","C":170,"D":158},
            5:{"A":"TOTAL","C":170,"D":158},
            6:{"A":"Bank costs","C":15,"D":12},
            7:{"A":"Audit expenses","C":22,"D":20},
            8:{"A":"Audit expenses","C":1,"D":0},
            9:{"A":"New expenses","C":7,"D":0},
        }
        make_xlsx(self.now,self.rows)
        prior={2:{"A":"Share capital","C":110},
               3:{"A":"Liabilities","C":48},
               4:{"A":"Cash and Bank","C":158},
               6:{"A":"Bank costs","C":12},
               7:{"A":"Audit expenses","C":20},
               8:{"A":"Audit expenses","C":0}}
        make_xlsx(self.before,prior)
        self.profile={"format":1,"ranges":[{
            "sheet":"Statement","section":"BS-L",
            "caption_column":"A","current_column":"C","previous_column":"D",
            "selected_rows":[2,3],
            "period_header_cell":"A1","period_header_contains":"2026",
            "unit":"rupees",
        },{
            "sheet":"Statement","section":"BS-A",
            "caption_column":"A","current_column":"C","previous_column":"D",
            "selected_rows":[4],"unit":"rupees",
        },{
            "sheet":"Statement","section":"PL-E",
            "caption_column":"A","current_column":"C","previous_column":"D",
            "selected_rows":[6,7,9],"unit":"rupees",
        }]}

    def test_profile_selects_only_details(self):
        result,issues=extract_profile(str(self.now),self.profile,
                                     previous_workbook_path=str(self.before))
        self.assertEqual(len(result),6)
        self.assertEqual(next(x["amount"] for x in result if x["caption"]=="Cash and Bank"),"170")
        self.assertTrue(all(x["sheet"]=="Statement" for x in result))
        self.assertIn("NOT_FOUND_IN_PRIOR_FS",[i["issue"] for i in issues])
        self.assertNotIn("TOTAL",[i["source_id"] for i in result])

    def test_candidate_scan_marks_totals_and_no_autoapprovals(self):
        with WorkbookSnapshot(self.now) as w:
            rows=scan_sheet(w,"Statement",start_row=2,end_row=9)
        self.assertEqual(len(rows),8)
        total=next(r for r in rows if r["caption"]=="TOTAL")
        self.assertIn("POSSIBLE_TOTAL_OR_DISCLOSURE",total["risk"])
        self.assertTrue(all(r["status"]=="UNREVIEWED" for r in rows))

    def test_period_header_drift_blocks(self):
        self.profile["ranges"][0]["period_header_contains"]="2025"
        _,issues=extract_profile(str(self.now),self.profile)
        self.assertIn("PERIOD_HEADER_MISMATCH",[i["issue"] for i in issues])

    def test_duplicate_caption_is_flagged(self):
        self.profile["ranges"][2]["selected_rows"]=[6,7,8,9]
        _,issues=extract_profile(str(self.now),self.profile)
        self.assertIn("DUPLICATE_CAPTION",[i["issue"] for i in issues])

    def test_mismatched_prior_column_is_flagged(self):
        rows=dict(self.rows)
        rows[6]={"A":"Bank costs","C":15,"D":11}
        make_xlsx(self.now,rows)
        _,issues=extract_profile(str(self.now),self.profile,
                                  previous_workbook_path=str(self.before))
        self.assertIn("PREVIOUS_COLUMN_DISAGREES_WITH_PRIOR_FS",[i["issue"] for i in issues])

    def test_invalid_profile_or_missing_row_is_blocked(self):
        self.profile["ranges"][0]["selected_rows"]=[999]
        _,issues=extract_profile(str(self.now),self.profile)
        self.assertIn("MISSING_CAPTION_OR_AMOUNT",[i["issue"] for i in issues])
        self.profile["ranges"][0]["selected_rows"]=[2,2]
        with self.assertRaises(ValueError):
            validate_profile(self.profile)

    def test_decimal_parser_rejects_headers(self):
        self.assertIsNone(numeric("₹ 45,000"))
        self.assertIsNone(numeric("Balance"))
        self.assertIsNone(numeric("NaN"))
        self.assertEqual(str(numeric("12,345.60")),"12345.60")
        self.assertEqual(canonical_caption("  Bank Balance/ Accounts "),"bank-balance-accounts")


if __name__=="__main__":
    unittest.main()
