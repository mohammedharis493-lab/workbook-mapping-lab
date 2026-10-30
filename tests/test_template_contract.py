"""Invented workbook fixtures for exact exported-template coverage checks."""
import sys
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from test_simulator import NS,REL,PKG,xlsx
from workbook_mapping_lab.template_contract import detail_coverage,require_coverage


def previous_with_detail(path: Path, *, detail_amount="125"):
    wb=ET.Element("{"+NS+"}workbook",{"xmlns:r":REL})
    sheets=ET.SubElement(wb,"{"+NS+"}sheets")
    for i,name in enumerate(("Balance Sheet","Profit & Loss Account","Borrowing details"),1):
        ET.SubElement(sheets,"{"+NS+"}sheet",{
            "name":name,"sheetId":str(i),"{"+REL+"}id":"rId"+str(i)})
    links=ET.Element("{"+PKG+"}Relationships")
    for i in range(1,4):
        ET.SubElement(links,"{"+PKG+"}Relationship",{
            "Id":"rId"+str(i),"Type":REL+"/worksheet",
            "Target":"worksheets/sheet"+str(i)+".xml"})
    with ZipFile(path,"w") as z:
        z.writestr("xl/workbook.xml",ET.tostring(wb))
        z.writestr("xl/_rels/workbook.xml.rels",ET.tostring(links))
        for i in (1,2,3):
            xml=ET.Element("{"+NS+"}worksheet")
            data=ET.SubElement(xml,"{"+NS+"}sheetData")
            if i==3:
                for row_num,label,value in [(4,"Related deposits",detail_amount),
                                            (5,"Total",detail_amount)]:
                    row=ET.SubElement(data,"{"+NS+"}row",{"r":str(row_num)})
                    c=ET.SubElement(row,"{"+NS+"}c",{"r":"A"+str(row_num),"t":"inlineStr"})
                    ET.SubElement(ET.SubElement(c,"{"+NS+"}is"),"{"+NS+"}t").text=label
                    v=ET.SubElement(row,"{"+NS+"}c",{"r":"B"+str(row_num)})
                    ET.SubElement(v,"{"+NS+"}v").text=value
            z.writestr("xl/worksheets/sheet"+str(i)+".xml",ET.tostring(xml))


class ContractTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        self.current=root/"current.xlsx"
        self.previous=root/"previous.xlsx"
        xlsx(self.current)
        previous_with_detail(self.previous)

    def test_missing_used_detail_blocks(self):
        result=detail_coverage(str(self.previous),str(self.current))
        self.assertEqual(result["status"],"BLOCKED_INCOMPLETE_VENDOR_TEMPLATE")
        self.assertEqual(result["missing_active_detail_sheets"][0]["sheet"],"Borrowing details")
        self.assertEqual(result["missing_active_detail_sheets"][0]["prior_item_count"],1)
        with self.assertRaisesRegex(ValueError,"Borrowing details"):
            require_coverage(str(self.previous),str(self.current))

    def test_zero_detail_does_not_generate_false_block(self):
        previous_with_detail(self.previous,detail_amount="0")
        result=detail_coverage(str(self.previous),str(self.current))
        self.assertEqual(result["status"],"READY_FOR_REVIEW")

    def test_identical_previous_current_file_cannot_count(self):
        with self.assertRaises(ValueError):
            detail_coverage(str(self.current),str(self.current))

    def test_vendor_structure_never_modified_by_check(self):
        before=self.current.read_bytes()
        detail_coverage(str(self.previous),str(self.current))
        self.assertEqual(self.current.read_bytes(),before)


if __name__=="__main__":
    unittest.main()
