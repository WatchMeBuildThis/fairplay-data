import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "Scripts" / "prepare_safe_vendor_feed.py"
SPEC = importlib.util.spec_from_file_location("prepare_safe_vendor_feed", MODULE_PATH)
SAFE_FEED = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = SAFE_FEED
SPEC.loader.exec_module(SAFE_FEED)


def vendor(vendor_id, status, eligible, coordinates):
    return {
        "id": vendor_id,
        "name": f"Vendor {vendor_id}",
        "coordinate_status": status,
        "compass_eligible": eligible,
        "coordinates": coordinates,
    }


class PrepareSafeVendorFeedTests(unittest.TestCase):
    def test_preserves_verified_coordinate(self):
        source = [vendor("verified", "verified", True, [-93.17, 44.98])]
        result, changes = SAFE_FEED.prepare_safe_feed(source)
        self.assertEqual(result[0]["coordinates"], [-93.17, 44.98])
        self.assertTrue(result[0]["compass_eligible"])
        self.assertNotIn("withheld_coordinates", result[0])
        self.assertEqual(changes, [])

    def test_withholds_unverified_coordinate_without_deleting_it(self):
        source = [vendor("candidate", "unverified", False, [-93.171, 44.981])]
        result, changes = SAFE_FEED.prepare_safe_feed(source)
        self.assertIsNone(result[0]["coordinates"])
        self.assertEqual(result[0]["withheld_coordinates"], [-93.171, 44.981])
        self.assertEqual(result[0]["coordinate_status"], "withheld")
        self.assertFalse(result[0]["compass_eligible"])
        self.assertEqual([change["id"] for change in changes], ["candidate"])
        self.assertEqual(source[0]["coordinates"], [-93.171, 44.981])

    def test_withholds_approximate_coordinate(self):
        source = [vendor("approximate", "approximate", False, [-93.172, 44.982])]
        result, _ = SAFE_FEED.prepare_safe_feed(source)
        self.assertIsNone(result[0]["coordinates"])
        self.assertEqual(result[0]["withheld_coordinates"], [-93.172, 44.982])

    def test_reopens_verified_coordinate_with_geometry_conflict(self):
        source = [vendor("verified", "verified", True, [-93.17, 44.98])]
        result, changes = SAFE_FEED.prepare_safe_feed(source, {"verified"})
        self.assertIsNone(result[0]["coordinates"])
        self.assertEqual(result[0]["withheld_coordinates"], [-93.17, 44.98])
        self.assertEqual(result[0]["coordinate_status"], "withheld")
        self.assertIn("more than 30 m", result[0]["withheld_reason"])
        self.assertEqual(changes[0]["reason"], "geometry_conflict_over_30m")

    def test_leaves_already_missing_coordinate_missing(self):
        source = [vendor("missing", "missing", False, None)]
        result, changes = SAFE_FEED.prepare_safe_feed(source)
        self.assertIsNone(result[0]["coordinates"])
        self.assertNotIn("withheld_coordinates", result[0])
        self.assertEqual(changes, [])

    def test_rejects_duplicate_ids(self):
        source = [
            vendor("duplicate", "unverified", False, [-93.17, 44.98]),
            vendor("duplicate", "unverified", False, [-93.17, 44.98]),
        ]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            SAFE_FEED.prepare_safe_feed(source)

    def test_rejects_unsafe_verified_coordinate(self):
        source = [vendor("verified", "verified", True, [-120, 10])]
        with self.assertRaisesRegex(ValueError, "verified navigation coordinate"):
            SAFE_FEED.prepare_safe_feed(source)


if __name__ == "__main__":
    unittest.main()
