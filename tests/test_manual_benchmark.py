"""Synthetic comparison of two DIFFERENT workbook layouts."""
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from test_simulator import NS, REL, PKG, write_csv
from workbook_mapping_lab.manual_benchmark import compare_completed_return

def native(path, sheet_names, rows, *, hidden_sheets=()):
    root=ET.Element("{"+NS+"}workbook",{"xmlns:r":REL})
    sheets=ET.SubElement(root,"{"+NS+"}sheets")
    relations=ET.Element("{"+PKG+"}Relationships")
    with ZipFile(path,"w") as z:
        for num,name in enumerate(sheet_names,1):
            ET.SubElement(sheets,"{"+NS+"}sheet",{
                "name":name,"sheetId":str(num),"{"+REL+"}id":"rId"+str(num),
                "state":"hidden" if name in hidden_sheets else "visible"})
            ET.SubElement(relations,"{"+PKG+"}Relationship",{
                "Id":"rId"+str(num),"Type":REL+"/worksheet",
                "Target":f"worksheets/sheet{num}.xml"})
            sheet=ET.Element("{"+NS+"}worksheet")
            data=ET.SubElement(sheet,"{"+NS+"}sheetData")
            by_row={}
            for address,value in rows.get(name,{}).items():
                digits="".join(x for x in address if x.isdigit())
                by_row.setdefault(int(digits),[]).append((address,value))
            for num_row,cells in sorted(by_row.items()):
                row=ET.SubElement(data,"{"+NS+"}row",{"r":str(num_row)})
                for address,value in cells:
                    if isinstance(value,(int,float)):
                        cell=ET.SubElement(row,"{"+NS+"}c",{"r":address})
                        ET.SubElement(cell,"{"+NS+"}v").text=str(value)
                    else:
                        cell=ET.SubElement(row,"{"+NS+"}c",{"r":address,"t":"inlineStr"})
                        ET.SubElement(ET.SubElement(cell,"{"+NS+"}is"),
                                      "{"+NS+"}t").text=str(value)
            z.writestr(f"xl/worksheets/sheet{num}.xml",ET.tostring(sheet))
        z.writestr("xl/workbook.xml",ET.tostring(root))
        z.writestr("xl/_rels/workbook.xml.rels",ET.tostring(relations))


class ManualBenchmarkTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base=Path(tmp.name)
        self.gen=base/"source_export.xlsx"
        self.ref=base/"manual_completed.xlsm"
        self.rules=base/"private_contract.csv"
        native(self.gen,["Balance Sheet"],{"Balance Sheet":{
            "A4":"Borrowings","B4":300,
            "A5":"Trade payables","B5":100}})
        native(self.ref,["Part A-BS"],{"Part A-BS":{
            "A12":"Related-party deposits","E12":300,
            "A13":"Trade creditors due over 1 year","E13":100}})
        self.rows=[
            ("LOAN","300","Balance Sheet","Borrowings","B",
             "Part A-BS","Related-party deposits","E"),
            ("CREDITOR","100","Balance Sheet","Trade payables","B",
             "Part A-BS","Trade creditors due over 1 year","E"),
        ]
        self.save()

    def save(self):
        write_csv(self.rules,("field_id","expected_amount","generated_sheet",
                  "generated_label","generated_value_col","manual_sheet",
                  "manual_label","manual_value_col"),self.rows)

    def test_cross_workbook_layout_all_fields_match_with_approved_contract(self):
        before=self.gen.read_bytes(),self.ref.read_bytes()
        result=compare_completed_return(str(self.gen),str(self.ref),str(self.rules))
        self.assertEqual(result["status"],"ALL_CONFIGURED_FIELDS_MATCH")
        self.assertEqual(result["fully_matched"],2)
        self.assertEqual(result["generated_target_unavailable"],0)
        self.assertEqual(before,(self.gen.read_bytes(),self.ref.read_bytes()))

    def test_missing_native_detail_sheet_is_not_mistaken_for_pass(self):
        self.rows[0]=("LOAN","300","Deposits details","Deposits from related","B",
             "Part A-BS","Related-party deposits","E")
        self.save()
        result=compare_completed_return(str(self.gen),str(self.ref),str(self.rules))
        self.assertEqual(result["fully_matched"],1)
        self.assertEqual(result["generated_target_unavailable"],1)
        self.assertIn("GENERATED_FIELD_MISSING_SHEET",result["details"][0]["checks"])

    def test_fs_amount_disagrees_with_manually_completed_reference(self):
        self.rows[0]=("LOAN","250","Balance Sheet","Borrowings","B",
             "Part A-BS","Related-party deposits","E")
        self.save()
        result=compare_completed_return(str(self.gen),str(self.ref),str(self.rules))
        self.assertIn("MANUAL_RETURN_DIFFERS_FROM_FS",result["details"][0]["checks"])
        self.assertIn("GENERATED_AMOUNT_DIFFERS_FROM_FS",result["details"][0]["checks"])

    def test_duplicate_reference_caption_blocks_ambiguous_manual_field(self):
        native(self.ref,["Part A-BS"],{"Part A-BS":{
            "A12":"Related-party deposits","E12":300,
            "A14":"Related-party deposits","E14":300,
            "A13":"Trade creditors due over 1 year","E13":100}})
        result=compare_completed_return(str(self.gen),str(self.ref),str(self.rules))
        self.assertIn("MANUAL_FIELD_LABEL_AMBIGUOUS",result["details"][0]["checks"])

    def test_exact_label_prevents_inaccurate_parent_mapping(self):
        self.rows[0]=("LOAN","300","Balance Sheet","Deposits from related","B",
             "Part A-BS","Related-party deposits","E")
        self.save()
        result=compare_completed_return(str(self.gen),str(self.ref),str(self.rules))
        self.assertIn("GENERATED_FIELD_LABEL_MISSING",result["details"][0]["checks"])

    def test_explicit_approved_cell_disambiguates_repeated_captions(self):
        native(self.ref,["Part A-BS"],{"Part A-BS":{
            "A12":"Other","E12":300,
            "A14":"Other","E14":100,
            "A13":"Trade creditors due over 1 year","E13":100}})
        self.rows[0]=("LOAN","300","Balance Sheet","Borrowings","B",
             "Part A-BS","Other","E")
        self.save()
        # The privately approved A12 anchor must prove the exact row.
        with self.rules.open("r",encoding="utf-8") as fh:
            original=fh.read()
        import csv
        with self.rules.open("r",encoding="utf-8",newline="") as f:
            rows=list(csv.DictReader(f))
        rows[0]["manual_label_cell"]="A12"
        rows[1]["manual_label_cell"]="A13"
        with self.rules.open("w",encoding="utf-8",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]))
            writer.writeheader();writer.writerows(rows)
        result=compare_completed_return(str(self.gen),str(self.ref),str(self.rules))
        self.assertEqual(result["fully_matched"],2)

    def test_approved_anchor_caption_change_is_not_silently_accepted(self):
        import csv
        with self.rules.open("r",encoding="utf-8",newline="") as f:
            rows=list(csv.DictReader(f))
        rows[0]["manual_label_cell"]="A13"
        with self.rules.open("w",encoding="utf-8",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]))
            writer.writeheader();writer.writerows(rows)
        result=compare_completed_return(str(self.gen),str(self.ref),str(self.rules))
        self.assertIn("MANUAL_FIELD_APPROVED_ANCHOR_CHANGED",result["details"][0]["checks"])

    def test_hidden_manual_reference_with_approved_anchor_can_be_read(self):
        native(self.ref,["Part A-BS"],{"Part A-BS":{
            "A12":"Related-party deposits","E12":300,
            "A13":"Trade creditors due over 1 year","E13":100}},
            hidden_sheets=("Part A-BS",))
        import csv
        with self.rules.open("r",encoding="utf-8",newline="") as f:
            data=list(csv.DictReader(f))
        data[0]["manual_label_cell"]="A12"
        data[1]["manual_label_cell"]="A13"
        with self.rules.open("w",encoding="utf-8",newline="") as f:
            wr=csv.DictWriter(f,fieldnames=list(data[0]));wr.writeheader();wr.writerows(data)
        results=compare_completed_return(str(self.gen),str(self.ref),str(self.rules))
        self.assertEqual(results["fully_matched"],2)

    def test_hidden_manual_sheet_without_approved_anchor_is_not_used(self):
        native(self.ref,["Part A-BS"],{"Part A-BS":{
            "A12":"Related-party deposits","E12":300,
            "A13":"Trade creditors due over 1 year","E13":100}},
            hidden_sheets=("Part A-BS",))
        result=compare_completed_return(str(self.gen),str(self.ref),str(self.rules))
        self.assertIn("MANUAL_FIELD_HIDDEN_SHEET",result["details"][0]["checks"])

    def test_duplicate_field_ids_block(self):
        self.rows[1]=("LOAN","100","Balance Sheet","Trade payables","B",
             "Part A-BS","Trade creditors due over 1 year","E")
        self.save()
        with self.assertRaises(ValueError):
            compare_completed_return(str(self.gen),str(self.ref),str(self.rules))

    def test_nonfinite_expected_amount_rejected(self):
        self.rows[0]=("LOAN","NaN","Balance Sheet","Borrowings","B",
             "Part A-BS","Related-party deposits","E")
        self.save()
        with self.assertRaises(ValueError):
            compare_completed_return(str(self.gen),str(self.ref),str(self.rules))

if __name__=="__main__":
    unittest.main()
