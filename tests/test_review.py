"""Synthetic-only unit tests for review decisions and historical suggestions."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from test_simulator import xlsx
from workbook_mapping_lab.learning import propose_mappings
from workbook_mapping_lab.review import ReviewSession,require_private_directory


class ReviewTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.rows=[
            {"source_id":"SOURCE1","section":"BS-A","caption":"Cash",
             "amount":"100","unit":"rupees","risk":"","notice":"FORMULA_CACHED_VALUE"},
            {"source_id":"SOURCE2","section":"BS-A","caption":"New payment balance",
             "amount":"35","unit":"rupees","risk":""},
        ]
        self.layout=[
            {"field_id":"CASH","section":"BS-A","caption":"Cash","sheet":"Statement","cell":"B1",
             "anchor_cell":"A1","anchor_text":"Cash"},
            {"field_id":"OTHER","section":"BS-A","caption":"Other","sheet":"Statement","cell":"B2",
             "anchor_cell":"A2","anchor_text":"Loans"},
        ]

    def test_approved_rule_reused_and_unmapped_flagged(self):
        previous=[{"source_id":"SOURCE1","field_id":"CASH","approved":"yes"}]
        session=ReviewSession(self.rows,[],self.layout,previous)
        self.assertEqual(session.entries["SOURCE1"]["review_status"],"REUSED")
        self.assertEqual(session.unresolved(),["SOURCE2"])
        report=session.save_review(str(self.root))
        self.assertEqual(report["status"],"BLOCKED")
        self.assertTrue(Path(report["report"]).exists())

    def test_suggested_mapping_does_not_self_approve(self):
        guess=[{"source_id":"SOURCE1","suggested_field_id":"CASH"}]
        session=ReviewSession(self.rows,[],self.layout,suggestions=guess)
        self.assertEqual(session.entries["SOURCE1"]["review_status"],"SUGGESTED")
        self.assertEqual(len(session.unresolved()),2)
        session.approve("SOURCE1","CASH")
        session.approve("SOURCE2","OTHER")
        self.assertEqual(session.unresolved(),[])
        self.assertEqual(session.save_review(str(self.root))["status"],"PASS")

    def test_mismatched_section_and_risk_require_approval(self):
        rows=[{**self.rows[0],"risk":"POSSIBLE_TOTAL_OR_DISCLOSURE"}]
        guess=[{"source_id":"SOURCE1","suggested_field_id":"CASH"}]
        session=ReviewSession(rows,[],self.layout,suggestions=guess)
        self.assertEqual(session.entries["SOURCE1"]["target_hint"],"CASH")
        with self.assertRaises(ValueError):
            session.approve("SOURCE1","CASH")
        session.approve("SOURCE1","CASH",acknowledge_risks=True)
        self.assertEqual(session.unresolved(),[])
        with self.assertRaises(ValueError):
            session.approve("SOURCE1","UNKNOWN")

    def test_global_extraction_errors_always_block_export(self):
        issues=[{"issue":"PERIOD_HEADER_MISMATCH","source_id":"","detail":"Wrong year"}]
        session=ReviewSession(self.rows,issues,self.layout)
        session.approve("SOURCE1","CASH")
        session.approve("SOURCE2","OTHER")
        report=session.save_review(str(self.root))
        self.assertEqual(report["status"],"BLOCKED")
        data=json.loads(Path(report["report"]).read_text(encoding="utf8"))
        self.assertIn("PERIOD_HEADER_MISMATCH",[x["issue"] for x in data["exceptions"]])

    def test_reject_public_repository_output(self):
        public=Path(__file__).resolve().parents[1]/"not-a-private-folder"
        with self.assertRaises(ValueError):
            require_private_directory(str(public))

    def test_historic_suggestions_match_values_not_row_numbers(self):
        previous=self.root/"previous_target.xlsx"
        xlsx(previous,filled=True)
        sources=[
            {"source_id":"X","section":"BS-A","caption":"Cash",
             "previous_amount":"100.40"},
            {"source_id":"Z","section":"BS-A","caption":"Other",
             "previous_amount":"0"},
        ]
        layout=[
            {"field_id":"CASH","section":"BS-A","sheet":"Balance Sheet","cell":"B1",
             "anchor_cell":"A1","anchor_text":"Cash"},
            {"field_id":"OTHER","section":"BS-A","sheet":"Balance Sheet","cell":"B2",
             "anchor_cell":"A2","anchor_text":"Loans"},
        ]
        suggestions,errors=propose_mappings(sources,str(previous),layout)
        self.assertFalse(errors)
        self.assertEqual(suggestions[0]["suggested_field_id"],"CASH")
        self.assertEqual(suggestions[0]["status"],"SUGGESTED_REVIEW_REQUIRED")
        self.assertEqual(suggestions[1]["status"],"ZERO_AMOUNT_REQUIRES_REVIEW")


if __name__=="__main__":
    unittest.main()
