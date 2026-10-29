import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from workbook_mapping_lab.mapping import discover, apply, load_csv

ROOT = Path(__file__).resolve().parents[1]/"fixtures"/"synthetic"

class MappingTests(unittest.TestCase):
    def test_discovery_never_approves(self):
        s = load_csv(ROOT/"previous_fs.csv", ("source_id", "section", "caption", "amount"))
        w = load_csv(ROOT/"previous_target.csv", ("field_id", "section", "caption", "amount"))
        matches = discover(s,w)
        self.assertEqual(len(matches), 4)
        self.assertTrue(all(m["approved"] == "no" for m in matches))

    def test_apply_approved_and_flag_new(self):
        s = load_csv(ROOT/"current_fs.csv", ("source_id", "section", "caption", "amount"))
        r = load_csv(ROOT/"approved_rules.csv", ("source_id", "field_id", "approved"))
        t = load_csv(ROOT/"target_fields.csv", ("field_id", "section", "caption"))
        mapped, issues = apply(s,r,t)
        self.assertEqual({x['field_id']:x['amount'] for x in mapped}['PL-AUDIT-FEE'], '11400')
        self.assertEqual([x['issue'] for x in issues],['UNMAPPED_CURRENT_SOURCE'])
        self.assertEqual(issues[0]['source_id'],'PL-NEW')

    def test_incorrect_target_blocks_output(self):
        s = [{"source_id":"PL-AUDIT","amount":"2","section":"PL","caption":"Audit"}]
        r = [{"source_id":"PL-AUDIT","field_id":"MISSING","approved":"yes"}]
        m, e = apply(s,r,[])
        self.assertEqual(m, [])
        self.assertIn('TARGET_NOT_IN_TEMPLATE', [i['issue'] for i in e])

if __name__ == '__main__': unittest.main()


