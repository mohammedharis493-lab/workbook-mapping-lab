"""Synthetic M2 native export discovery and explicit human review."""
import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from test_layout_resolver import make_vendor
from test_simulator import xlsx,write_csv
from workbook_mapping_lab.schema_discovery import (
    discover_entity_fields, reviewed_profile, save_private_profile, set_candidate_decision
)
from workbook_mapping_lab.entity_schema import load_entity_profile

class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.native=self.root/"native.xlsx"
        xlsx(self.native)
        self.layout=self.root/"approved.csv"
        write_csv(self.layout,("field_id","section","sheet","cell","anchor_cell","anchor_text"),[
            ("CASH","BS-A","Balance Sheet","B1","A1","Cash"),
            ("LOANS","BS-L","Balance Sheet","B2","A2","Loans"),
        ])
    def scan(self,layout=True):
        return discover_entity_fields(str(self.native),str(self.layout) if layout else "")
    def approve(self,scan,which=None):
        for c in scan["candidates"]:
            if which is None or c["field_id"] in which:
                set_candidate_decision(scan,candidate_id=c["candidate_id"],
                    selected=True,field_id=c["field_id"],
                    section=c["section"] or "BS-L",applicability="required")
    def manifest(self,scan,layout=True):
        return reviewed_profile(scan,entity_key="Entity A",assessment_year="2026-27",
            itr_form="ITR-6",native_template=str(self.native),
            layout_path=str(self.layout) if layout else "")

    def test_scan_requires_individual_reviews_and_preserves_original(self):
        before=self.native.read_bytes();r=self.scan()
        self.assertEqual(r["candidate_count"],4)
        self.assertEqual(r["matched_existing_layout"],2)
        self.assertTrue(all(not x["reviewed"] for x in r["candidates"]))
        self.assertTrue(all(x["applicability"]=="review" for x in r["candidates"]))
        self.assertEqual(self.native.read_bytes(),before)
        with self.assertRaisesRegex(ValueError,"explicit applicability"):self.manifest(r)

    def test_save_only_reviewed_fields_with_no_overwrite(self):
        r=self.scan();self.approve(r,{"CASH","LOANS"})
        profile=self.manifest(r)
        self.assertEqual(len(profile["fields"]),2)
        self.assertEqual(profile["candidate_coverage"]["omitted"],2)
        path=self.root/"private"/"reviewed.json"
        save_private_profile(profile,str(path))
        self.assertEqual(load_entity_profile(str(path))["fields"],profile["fields"])
        with self.assertRaises(FileExistsError):save_private_profile(profile,str(path))

    def test_missing_approved_field_must_not_be_omitted(self):
        r=self.scan();self.approve(r,{"CASH"})
        for row in r["candidates"]:
            if row["field_id"]=="LOANS":
                set_candidate_decision(r,candidate_id=row["candidate_id"],selected=False)
        with self.assertRaisesRegex(ValueError,"not represented"):self.manifest(r)

    def test_incomplete_scan_must_not_pass(self):
        r=discover_entity_fields(str(self.native),limit=1)
        self.assertTrue(r["truncated"]);self.assertEqual(r["returned_count"],1)
        self.approve(r)
        with self.assertRaisesRegex(ValueError,"safe candidate limit"):self.manifest(r,False)

    def test_template_changed_before_export_blocks(self):
        r=self.scan(False);self.approve(r,{"CAND_Z"})  # no selections
        c=r["candidates"][0]
        set_candidate_decision(r,candidate_id=c["candidate_id"],selected=True,
            field_id="CASH",section="BS-A",applicability="required")
        make_vendor(self.native,row=37)
        with self.assertRaisesRegex(ValueError,"Template changed"):self.manifest(r,False)

    def test_other_entity_template_discovery_is_different(self):
        a=self.scan(False)
        make_vendor(self.native,row=21,include_details=True)
        b=self.scan(False)
        self.assertNotEqual(a["template_sha256"],b["template_sha256"])
        self.assertNotEqual({x["sheet"] for x in a["candidates"]},
                            {x["sheet"] for x in b["candidates"]})
        self.assertTrue(any(x["amount_cell"]=="B21" for x in b["candidates"]))

    def test_duplicated_caption_preserves_distinct_cell_identity(self):
        make_vendor(self.native,second=True)
        r=self.scan(False)
        copies=[x for x in r["candidates"] if x["sheet"]=="Related Details"]
        self.assertEqual(len(copies),2)
        self.assertNotEqual(copies[0]["candidate_id"],copies[1]["candidate_id"])

    def test_occupied_value_cannot_be_suggested(self):
        make_vendor(self.native,occupied=True)
        self.assertEqual(self.scan(False)["candidate_count"],0)

    def test_undecided_applicability_and_duplicate_ids_fail(self):
        r=self.scan(False);one,two=r["candidates"][:2]
        with self.assertRaisesRegex(ValueError,"Applicability must be decided"):
            set_candidate_decision(r,candidate_id=one["candidate_id"],selected=True,
                field_id="X",section="BS-A",applicability="review")
        for field in (one,two):
            set_candidate_decision(r,candidate_id=field["candidate_id"],
                selected=True,field_id="SAME",section="BS-A",applicability="required")
        with self.assertRaisesRegex(ValueError,"Duplicate field IDs"):self.manifest(r,False)

if __name__=="__main__":unittest.main()

