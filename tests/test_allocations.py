"""Only invented amounts. Regression tests for account-level mapping."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from workbook_mapping_lab.allocations import plan_allocations, ready_to_release

SOURCES = [
    {"source_id":"CASH", "section":"BS-A", "caption":"Petty cash", "amount":"12", "unit":"thousands"},
    {"source_id":"BANK", "section":"BS-A", "caption":"Bank account", "amount":"8000"},
    {"source_id":"STOCK", "section":"BS-A", "caption":"Stock", "amount":"1.25", "unit":"lakhs"},
    {"source_id":"CAP", "section":"BS-L", "caption":"Capital", "amount":"100000"},
    {"source_id":"LOAN", "section":"BS-L", "caption":"Borrowings", "amount":"45000"},
    {"source_id":"SALES", "section":"PL-I", "caption":"Revenue", "amount":"2", "unit":"lakhs"},
    {"source_id":"OPS", "section":"PL-E", "caption":"Services", "amount":"60000"},
    {"source_id":"GENERAL", "section":"PL-E", "caption":"Other expenses", "amount":"90000"},
]
TARGETS = [
    {"field_id":"B-CASH", "section":"BS-A", "caption":"Cash and bank"},
    {"field_id":"B-STOCK", "section":"BS-A", "caption":"Inventories"},
    {"field_id":"B-CAP", "section":"BS-L", "caption":"Capital"},
    {"field_id":"B-LOANS", "section":"BS-L", "caption":"Borrowings"},
    {"field_id":"P-REVENUE", "section":"PL-I", "caption":"Revenue"},
    {"field_id":"P-COST", "section":"PL-E", "caption":"Operational expenses"},
    {"field_id":"P-OTHER", "section":"PL-E", "caption":"General expenses"},
]
RULES = [
    {"source_id":"CASH", "field_id":"B-CASH", "approved":"yes"},
    {"source_id":"BANK", "field_id":"B-CASH", "approved":"yes"},
    {"source_id":"STOCK", "field_id":"B-STOCK", "approved":"yes"},
    {"source_id":"CAP", "field_id":"B-CAP", "approved":"yes"},
    {"source_id":"LOAN", "field_id":"B-LOANS", "approved":"yes"},
    {"source_id":"SALES", "field_id":"P-REVENUE", "approved":"yes"},
    {"source_id":"OPS", "field_id":"P-COST", "approved":"yes", "portion":"0.7"},
    {"source_id":"OPS", "field_id":"P-OTHER", "approved":"yes", "portion":"0.3"},
    {"source_id":"GENERAL", "field_id":"P-OTHER", "approved":"yes"},
]
CONTROLS = [
    {"section":"BS-A", "amount":"145000"},
    {"section":"BS-L", "amount":"145000"},
    {"section":"PL-I", "amount":"200000"},
    {"section":"PL-E", "amount":"150000"},
]

def work(sources=None, rules=None, targets=None, controls=None):
    return plan_allocations(sources if sources is not None else SOURCES,
        rules if rules is not None else RULES, targets if targets is not None else TARGETS,
        expected_totals=controls if controls is not None else CONTROLS)

class AllocationTests(unittest.TestCase):
    def test_many_to_one_split_and_unit_scaling(self):
        output, issues, trace = work()
        self.assertTrue(ready_to_release(issues))
        lookup = {x["field_id"]:x["amount"] for x in output}
        self.assertEqual(lookup["B-CASH"], "20000")
        self.assertEqual(lookup["B-STOCK"], "125000.00")
        self.assertEqual(lookup["P-COST"], "42000.0")
        self.assertEqual(lookup["P-OTHER"], "108000.0")
        self.assertEqual(len(trace), 9)

    def test_unapproved_rule_is_not_applied(self):
        rules = [r for r in RULES if r["source_id"] != "STOCK"] + [
            {"source_id":"STOCK", "field_id":"B-STOCK", "approved":"no"}]
        _, issues, _ = work(rules=rules)
        self.assertFalse(ready_to_release(issues))
        self.assertIn("UNMAPPED_OR_NOT_APPROVED", [x["issue"] for x in issues])
        self.assertIn("SOURCE_COVERAGE_DIFFERENCE", [x["issue"] for x in issues])

    def test_new_source_is_exception(self):
        src = SOURCES + [{"source_id":"NEW", "section":"PL-E", "caption":"New charge", "amount":"25"}]
        _, issues, _ = work(sources=src, controls=None)
        self.assertIn("UNMAPPED_OR_NOT_APPROVED", [x["issue"] for x in issues])

    def test_split_not_full_allocation_blocks(self):
        rules = [r if r.get("source_id") != "OPS" or r.get("field_id") != "P-OTHER"
                 else {**r, "portion":"0.29"} for r in RULES]
        _, issues, _ = work(rules=rules)
        self.assertIn("SPLIT_NOT_100_PERCENT", [x["issue"] for x in issues])

    def test_opposite_sign_only_if_explicitly_approved(self):
        rules = [({**r, "sign":"reverse"} if r["source_id"] == "CAP" else r) for r in RULES]
        output, issues, trace = work(rules=rules)
        self.assertFalse(issues)
        self.assertEqual({x["field_id"]:x["amount"] for x in output}["B-CAP"], "-100000")
        self.assertEqual(next(x for x in trace if x["source_id"]=="CAP")["sign"], "reverse")

    def test_cross_section_blocks(self):
        rules=[({**r, "field_id":"B-CASH"} if r["source_id"] == "CAP" else r) for r in RULES]
        _, issues, _ = work(rules=rules)
        self.assertIn("CROSS_SECTION_MAPPING", [x["issue"] for x in issues])

    def test_bad_units_and_nonfinite_numbers_are_blocked(self):
        for unit, amount in (("dollars","100"),("rupees","NaN"),("rupees","Infinity")):
            src=[({**s,"unit":unit,"amount":amount} if s["source_id"] == "STOCK" else s) for s in SOURCES]
            _, issues, _=work(sources=src)
            self.assertIn("INVALID_SOURCE_AMOUNT_OR_UNIT", [x["issue"] for x in issues])

    def test_duplicated_source_or_target_is_blocked(self):
        _, issues, _=work(sources=SOURCES+[SOURCES[0]])
        self.assertIn("DUPLICATE_OR_BLANK_SOURCE_ID", [x["issue"] for x in issues])
        _, issues, _=work(targets=TARGETS+[TARGETS[0]])
        self.assertIn("DUPLICATE_OR_BLANK_TARGET_ID", [x["issue"] for x in issues])

    def test_duplicate_rule_target_blocks(self):
        _, issues, _=work(rules=RULES+[RULES[0]])
        self.assertIn("DUPLICATE_RULE_TARGET", [x["issue"] for x in issues])

    def test_unauthorised_field_and_missing_prior_source_blocks(self):
        _, issues, _=work(rules=RULES+[{"source_id":"CASH","field_id":"UNKNOWN","approved":"yes"}])
        self.assertIn("TARGET_NOT_IN_TEMPLATE", [x["issue"] for x in issues])
        _, issues, _=work(rules=RULES+[{"source_id":"OLD","field_id":"B-CASH","approved":"yes"}])
        self.assertIn("APPROVED_SOURCE_NOT_PRESENT", [x["issue"] for x in issues])

    def test_control_total_difference_blocks(self):
        controls=[{**c,"amount":"140000"} if c["section"]=="BS-A" else c for c in CONTROLS]
        _, issues, _=work(controls=controls)
        self.assertIn("SOURCE_CONTROL_MISMATCH", [x["issue"] for x in issues])

    def test_amount_signs_and_precision(self):
        src=[({**s,"amount":"-100000"} if s["source_id"]=="CAP" else s) for s in SOURCES]
        out, issues, _=work(sources=src,controls=[{**c,"amount":"-100000"} if c["section"]=="BS-L" else c for c in CONTROLS])
        self.assertIn("SOURCE_CONTROL_MISMATCH", [x["issue"] for x in issues])
        self.assertEqual({x["field_id"]:x["amount"] for x in out}["B-CAP"], "-100000")

if __name__=="__main__":
    unittest.main()
