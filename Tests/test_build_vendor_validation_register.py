import unittest

from Scripts.build_vendor_validation_register import final_decision, publisher_groups


class BuildVendorValidationRegisterTests(unittest.TestCase):
    def test_verified_requires_verified_ledger_for_publish_decision(self):
        decision, required = final_decision(
            {"coordinate_status": "verified"}, {"status": "verified"}
        )
        self.assertEqual(decision, "publish_compass_pin")
        self.assertEqual(required, "none")

    def test_approximate_candidate_stays_without_pin(self):
        decision, required = final_decision(
            {"coordinate_status": "withheld"}, {"status": "approximate"}
        )
        self.assertEqual(decision, "publish_vendor_without_pin_preserve_candidate")
        self.assertIn("second coordinate publisher", required)

    def test_publisher_groups_are_unique_and_sorted(self):
        groups = publisher_groups({"sources": [
            {"publisher_group": "google_maps"},
            {"publisher_group": "mnstatefair"},
            {"publisher_group": "google_maps"},
        ]})
        self.assertEqual(groups, ["google_maps", "mnstatefair"])


if __name__ == "__main__":
    unittest.main()
