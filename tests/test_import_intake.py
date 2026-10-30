"""M3 original blank import XLSX coverage vs independently completed ITR6."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from test_layout_resolver import make_vendor
from test_manual_benchmark import native
from test_simulator import write_csv
from workbook_mapping_lab.import_intake import inspect_native_import_coverage


class NativeIntakeTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.native = self.root / "native_import.xlsx"
        self.manual = self.root / "independent_ITR6.xlsm"
        self.contract = self.root / "reviewed_private_comparison.csv"
        make_vendor(self.native, include_details=True, row=11)
        self.manual_rows = {"Part A-BS": {
            "A12": "Related-party deposit", "E12": 300,
            "A13": "Trade creditors over one year", "E13": 100,
        }}
        native(self.manual, ["Part A-BS"], self.manual_rows, hidden_sheets=("Part A-BS",))
        self.contract_rows = [
            ("RELATED", "300", "Related Details", "Deposits from related parties", "B",
             "Part A-BS", "Related-party deposit", "E", "A12")
        ]
        self.save_contract()

    def save_contract(self):
        write_csv(self.contract, (
            "field_id", "expected_amount", "generated_sheet", "generated_label",
            "generated_value_col", "manual_sheet", "manual_label",
            "manual_value_col", "manual_label_cell"
        ), self.contract_rows)

    def inspect(self):
        return inspect_native_import_coverage(
            str(self.native), str(self.manual), str(self.contract)
        )

    def test_real_blank_native_slot_and_hidden_reference_are_ready_for_review(self):
        before = [hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (self.native, self.manual, self.contract)]
        report = self.inspect()
        self.assertEqual(report["status"], "READY_FOR_ACCOUNTANT_MAPPING_REVIEW")
        self.assertEqual(report["import_cells_available"], 1)
        self.assertEqual(report["import_cells_unavailable"], 0)
        self.assertEqual(report["reference_mismatches"], 0)
        self.assertEqual(report["rows"][0]["native_target"]["cell"], "B11")
        self.assertEqual(report["rows"][0]["completed_reference"]["cell"], "E12")
        self.assertEqual(before,[hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (self.native,self.manual,self.contract)])

    def test_missing_native_detail_sheet_blocks_despite_matching_ITR_amount(self):
        make_vendor(self.native,include_details=False)
        report=self.inspect()
        self.assertEqual(report["status"],"BLOCKED_NATIVE_IMPORT_TARGETS")
        self.assertEqual(report["import_cells_unavailable"],1)
        self.assertEqual(report["reference_mismatches"],0)
        self.assertEqual(report["rows"][0]["native_exceptions"][0]["code"],
                         "REQUIRED_VENDOR_SHEET_ABSENT")
        self.assertIn("Never reconstruct vendor worksheets",
                      report["rows"][0]["next_action"])

    def test_independently_completed_return_disagrees_with_fs(self):
        self.manual_rows["Part A-BS"]["E12"]=250
        native(self.manual,["Part A-BS"],self.manual_rows,hidden_sheets=("Part A-BS",))
        report=self.inspect()
        self.assertEqual(report["status"],"NEEDS_REFERENCE_REVIEW")
        self.assertEqual(report["import_cells_available"],1)
        self.assertEqual(report["reference_mismatches"],1)
        self.assertEqual(report["rows"][0]["completed_reference_status"],
                         "REFERENCE_DIFFERS_FROM_FS")

    def test_native_writable_target_must_be_unambiguous(self):
        make_vendor(self.native,second=True)
        report=self.inspect()
        self.assertEqual(report["status"],"BLOCKED_NATIVE_IMPORT_TARGETS")
        self.assertIn("CAPTION_NOT_UNIQUE_OR_ABSENT",
                      [x["code"] for x in report["rows"][0]["native_exceptions"]])

    def test_occupied_or_missing_blank_vendor_cell_rejected(self):
        make_vendor(self.native,occupied=True)
        report=self.inspect()
        self.assertEqual(report["import_cells_unavailable"],1)
        self.assertIn("VENDOR_DESTINATION_OCCUPIED",
                      [x["code"] for x in report["rows"][0]["native_exceptions"]])

    def test_manual_hidden_sheet_without_approved_anchor_requires_review(self):
        self.contract_rows[0] = (
            "RELATED", "300", "Related Details", "Deposits from related parties", "B",
            "Part A-BS", "Related-party deposit", "E", ""
        )
        self.save_contract()
        report=self.inspect()
        self.assertEqual(report["status"],"NEEDS_REFERENCE_REVIEW")
        self.assertEqual(report["rows"][0]["completed_reference_status"],
                         "REFERENCE_HIDDEN_SHEET")

    def test_two_field_contract_one_available_one_missing(self):
        self.contract_rows.append((
            "CREDITOR", "100", "Missing Creditors", "Trade creditors over one year", "B",
            "Part A-BS", "Trade creditors over one year", "E", "A13",
        ))
        self.save_contract()
        report=self.inspect()
        self.assertEqual(report["field_count"],2)
        self.assertEqual(report["import_cells_available"],1)
        self.assertEqual(report["import_cells_unavailable"],1)
        self.assertEqual(report["reference_mismatches"],0)
        self.assertEqual(report["ready_for_accountant_review"],1)

    def test_wrong_format_and_same_workbook_rejected(self):
        with self.assertRaisesRegex(ValueError,"original XLSX"):
            inspect_native_import_coverage(str(self.manual),str(self.native),str(self.contract))
        with self.assertRaisesRegex(ValueError,"same file"):
            inspect_native_import_coverage(str(self.native),str(self.native),str(self.contract))

    def test_wrong_existing_anchor_on_reference_is_detected(self):
        self.contract_rows[0] = (
            "RELATED", "300", "Related Details", "Deposits from related parties", "B",
            "Part A-BS", "Related-party deposit", "E", "A13"
        )
        self.save_contract()
        report=self.inspect()
        self.assertEqual(report["rows"][0]["completed_reference_status"],
                         "REFERENCE_APPROVED_ANCHOR_CHANGED")

    def test_duplicate_field_ids_do_not_create_misleading_count(self):
        self.contract_rows.append(self.contract_rows[0])
        self.save_contract()
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            self.inspect()


if __name__=="__main__":
    unittest.main()
