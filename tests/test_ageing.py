"""Only invented financial figures. Tests for rolling ageing versus return bands."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from workbook_mapping_lab.ageing import check_rollforward, itr_ageing

OLD={"under_1":15, "from_1_to_2":25, "from_2_to_3":35, "over_3":45}
NEW={"under_1":52, "from_1_to_2":15, "from_2_to_3":25, "over_3":80}

class AgeingTests(unittest.TestCase):
    def test_rolling_method(self):
        result=check_rollforward(OLD,NEW,current_year_new=52)
        self.assertEqual(result["status"],"ROLLFORWARD_MATCH")
        self.assertEqual(result["expected_rolled_prior"]["over_3"],80)
        self.assertEqual(result["itr_under_1"],52)
        self.assertEqual(result["itr_over_1"],120)
        self.assertEqual(result["current_total"],172)
        self.assertTrue(result["total_continuity_matches"])

    def test_more_than_one_is_all_three_older_buckets(self):
        result=itr_ageing({"under_1":"42.50","from_1_to_2":"11.25",
                           "from_2_to_3":"31.25","over_3":"8.50"})
        self.assertEqual(str(result["over_1"]),"51.00")
        self.assertEqual(str(result["total"]),"93.50")

    def test_missing_bucket_is_not_assumed_zero(self):
        with self.assertRaises(ValueError):
            itr_ageing({"under_1":4,"from_1_to_2":3,"over_3":2})
        with self.assertRaises(ValueError):
            itr_ageing({**NEW,"over_3":"NaN"})

    def test_older_bucket_mismatch_is_reviewed(self):
        changed={**NEW,"over_3":70}
        result=check_rollforward(OLD,changed,current_year_new=52)
        self.assertEqual(result["status"],"REQUIRES_REVIEW")
        self.assertEqual(result["difference_by_bucket"]["over_3"],-10)

    def test_payments_can_explain_lower_ageing(self):
        payments={"under_1":3,"from_1_to_2":6,"from_2_to_3":9,"over_3":12}
        current={"under_1":14,"from_1_to_2":12,"from_2_to_3":19,"over_3":59}
        result=check_rollforward(OLD,current,settlements_of_prior=payments,current_year_new=14)
        self.assertEqual(result["status"],"ROLLFORWARD_MATCH")
        self.assertTrue(result["total_continuity_matches"])

    def test_settlements_cannot_exceed_prior(self):
        payments={"under_1":16,"from_1_to_2":0,"from_2_to_3":0,"over_3":0}
        with self.assertRaises(ValueError):
            check_rollforward(OLD,NEW,settlements_of_prior=payments)

    def test_new_balance_discrepancy_is_reviewed(self):
        result=check_rollforward(OLD,NEW,current_year_new=51)
        self.assertEqual(result["status"],"REQUIRES_REVIEW")
        self.assertFalse(result["current_new_matches"])
        self.assertFalse(result["total_continuity_matches"])

    def test_historic_data_is_not_required_to_aggregate_current(self):
        result=itr_ageing(NEW)
        self.assertEqual(result["under_1"]+result["over_1"],result["total"])

if __name__=="__main__":
    unittest.main()
