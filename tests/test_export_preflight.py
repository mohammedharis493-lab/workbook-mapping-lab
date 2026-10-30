"""Synthetic native-export completeness and UI gate tests."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from test_layout_resolver import make_vendor
from test_simulator import xlsx, write_csv
from test_template_contract import previous_with_detail
from workbook_mapping_lab.export_preflight import preflight_export
from workbook_mapping_lab.review_browser import Workspace


class ExportPreflightTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        self.current=root/"current.xlsx"
        self.previous=root/"previous.xlsx"
        self.routes=root/"routes.csv"
        write_csv(self.routes,
                  ("field_id","section","sheet","caption","anchor_column","amount_column"),
                  [("RELATED","BS-L-DETAIL","Related Details",
                    "Deposits from related parties","A","B")])

    def test_detects_previously_used_detail_sheet_missing(self):
        previous_with_detail(self.previous)
        xlsx(self.current)
        before=(self.previous.read_bytes(),self.current.read_bytes())
        result=preflight_export(str(self.current),str(self.previous))
        self.assertEqual(result["status"],"INCOMPLETE_OFFICIAL_EXPORT")
        self.assertIn("Borrowing details",result["missing_sheets"])
        self.assertEqual((self.previous.read_bytes(),self.current.read_bytes()),before)

    def test_detects_required_route_sheet_missing(self):
        make_vendor(self.current,include_details=False)
        result=preflight_export(str(self.current),routes_file=str(self.routes))
        self.assertEqual(result["status"],"INCOMPLETE_OFFICIAL_EXPORT")
        self.assertEqual(result["detail_fields_resolved"],0)
        self.assertIn("Related Details",result["missing_configured_sheets"])

    def test_checks_real_existing_blank_vendor_cells(self):
        make_vendor(self.current)
        make_vendor(self.previous)
        before=self.current.read_bytes()
        result=preflight_export(str(self.current),str(self.previous),str(self.routes))
        self.assertEqual(result["status"],"READY_FOR_REVIEW")
        self.assertEqual(result["detail_fields_resolved"],1)
        self.assertFalse(result["missing_sheets"])
        self.assertEqual(self.current.read_bytes(),before)

    def test_missing_evidence_is_not_marked_ready(self):
        make_vendor(self.current)
        result=preflight_export(str(self.current))
        self.assertEqual(result["status"],"NEEDS_REVIEW")
        self.assertFalse(result["historical_coverage_checked"])

    def test_non_native_import_extension_is_rejected(self):
        path=self.current.with_suffix(".xlsm")
        path.write_bytes(b"test only")
        with self.assertRaisesRegex(ValueError,"xlsx"):
            preflight_export(str(path))

    def test_browser_preflight_does_not_approve_or_modify_workbooks(self):
        make_vendor(self.current,include_details=False)
        w=Workspace()
        w.set_config({"template":str(self.current),"detail_routes":str(self.routes)})
        before=self.current.read_bytes()
        state=w.check_template_readiness()
        self.assertEqual(state["latest_preflight"]["status"],"INCOMPLETE_OFFICIAL_EXPORT")
        self.assertIsNone(w.review)
        self.assertEqual(w.warnings,[])
        self.assertEqual(self.current.read_bytes(),before)


if __name__=="__main__":
    unittest.main()
