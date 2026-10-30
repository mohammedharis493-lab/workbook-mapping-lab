"""Tests for nonblocking, evidence-based classification warnings. Synthetic only."""
import sys
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from test_simulator import NS,REL,PKG
from workbook_mapping_lab.advisories import check_creditor_ageing,check_advisories


def workbook(path,sheets):
    w=ET.Element("{"+NS+"}workbook",{"xmlns:r":REL})
    sh=ET.SubElement(w,"{"+NS+"}sheets")
    relations=ET.Element("{"+PKG+"}Relationships")
    with ZipFile(path,"w") as z:
        for n,(name,items) in enumerate(sheets.items(),1):
            ET.SubElement(sh,"{"+NS+"}sheet",{
                "name":name,"sheetId":str(n),"{"+REL+"}id":f"rId{n}"})
            ET.SubElement(relations,"{"+PKG+"}Relationship",{
                "Id":f"rId{n}","Type":REL+"/worksheet",
                "Target":f"worksheets/sheet{n}.xml"})
            xml=ET.Element("{"+NS+"}worksheet")
            data=ET.SubElement(xml,"{"+NS+"}sheetData")
            by_row={}
            for addr,val in items.items():
                row="".join(char for char in addr if char.isdigit())
                by_row.setdefault(int(row),[]).append((addr,val))
            for row_num,pairs in sorted(by_row.items()):
                row=ET.SubElement(data,"{"+NS+"}row",{"r":str(row_num)})
                for addr,val in pairs:
                    if isinstance(val,(int,float)):
                        node=ET.SubElement(row,"{"+NS+"}c",{"r":addr})
                        ET.SubElement(node,"{"+NS+"}v").text=str(val)
                    else:
                        node=ET.SubElement(row,"{"+NS+"}c",{"r":addr,"t":"inlineStr"})
                        ET.SubElement(ET.SubElement(node,"{"+NS+"}is"),
                                      "{"+NS+"}t").text=str(val)
            z.writestr(f"xl/worksheets/sheet{n}.xml",ET.tostring(xml))
        z.writestr("xl/workbook.xml",ET.tostring(w))
        z.writestr("xl/_rels/workbook.xml.rels",ET.tostring(relations))


class AdvisoryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.fs=self.root/"previous_fs.xlsx"
        self.itr=self.root/"previous_itr.xlsx"
        self.cy=self.root/"current_fs.xlsx"
        self.age={
            "A5":"(i) MSME","C4":"Less than 1 yr.","G2":"Figures in INR",
            "C5":30,"D5":20,"E5":15,"F5":5,"G5":70,
        }
        self.itr_data={
            "A4":"Trade Creditors o/s for more than 1 year",
            "A5":"Others","B5":70,"A6":"Total","B6":70,
        }
        self.rebuild()

    def rebuild(self):
        workbook(self.fs,{"New Disclosure":self.age})
        workbook(self.itr,{"Creditors":self.itr_data})
        workbook(self.cy,{"New Disclosure":{
            "A5":"(i) MSME","C4":"Less than 1 yr.","G2":"Figures in INR",
            "C5":40,"D5":30,"E5":20,"F5":20,"G5":110,
        }})

    def test_warns_when_full_previous_total_was_treated_as_older(self):
        result=check_advisories(str(self.fs),str(self.itr),str(self.cy))
        code={x["code"]:x for x in result}
        warning=code["PRIOR_CREDITOR_AGE_CLASSIFICATION"]
        self.assertEqual(warning["difference"],"30")
        self.assertFalse(warning["blocking"])
        self.assertFalse(warning["acknowledged"])
        self.assertIn("40",warning["explanation"])
        self.assertIn("30",warning["explanation"])
        self.assertEqual(len(warning["evidence"]),4)
        self.assertNotIn("AGEING_ROLLFORWARD_NEEDS_SUPPORT",code)

    def test_if_previous_age_classification_correct_no_warning(self):
        self.itr_data["B5"]=40
        self.rebuild()
        results=check_advisories(str(self.fs),str(self.itr))
        self.assertNotIn("PRIOR_CREDITOR_AGE_CLASSIFICATION",[x["code"] for x in results])
        self.assertNotIn("PRIOR_CREDITOR_PARENT_TOTAL_DIFFERENCE",[x["code"] for x in results])

    def test_missing_evidence_yields_info_not_error(self):
        results=check_advisories(None,None)
        self.assertEqual(results[0]["severity"],"Info")
        self.assertFalse(results[0]["blocking"])

    def test_current_ageing_difference_is_only_advisory(self):
        self.rebuild()
        workbook(self.cy,{"New Disclosure":{
            "A5":"(i) MSME","C4":"Less than 1 yr.",
            "C5":40,"D5":1,"E5":20,"F5":20,"G5":110,
        }})
        results=check_advisories(str(self.fs),str(self.itr),str(self.cy))
        names={x["code"] for x in results}
        self.assertIn("CURRENT_FS_AGEING_TOTAL_MISMATCH",names)
        self.assertIn("AGEING_ROLLFORWARD_NEEDS_SUPPORT",names)
        self.assertTrue(all(not x["blocking"] for x in results))

    def test_wrong_heading_is_not_used_as_numeric_evidence(self):
        self.itr_data["A4"]="Sundry liabilities"
        self.rebuild()
        results=check_advisories(str(self.fs),str(self.itr))
        self.assertEqual(results[0]["code"],"HISTORICAL_AGEING_LAYOUT_UNRECOGNISED")

    def test_incorrect_older_amount_with_reconciled_grand_total(self):
        self.itr_data["B5"]=62
        self.itr_data["B6"]=70
        self.rebuild()
        results=check_advisories(str(self.fs),str(self.itr))
        self.assertIn("PRIOR_CREDITOR_AGE_CLASSIFICATION",[w["code"] for w in results])
        self.assertNotIn("PRIOR_CREDITOR_PARENT_TOTAL_DIFFERENCE",[w["code"] for w in results])


if __name__=="__main__":
    unittest.main()
