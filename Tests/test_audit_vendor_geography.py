import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "Scripts" / "audit_vendor_geography.py"
SPEC = importlib.util.spec_from_file_location("audit_vendor_geography", MODULE_PATH)
AUDIT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = AUDIT
SPEC.loader.exec_module(AUDIT)


def vendor(vendor_id, name, location, coordinates):
    return {
        "id": vendor_id,
        "name": name,
        "booth_location": location,
        "coordinates": coordinates,
        "popupHtml": f"<b>{name}</b><br>{location}",
    }


class GeographyAuditTests(unittest.TestCase):
    def test_missing_coordinate_is_critical_and_not_compass_eligible(self):
        report = AUDIT.build_audit([vendor("1", "Missing", "Somewhere", None)], [], {"vendors": {}})
        row = report["vendors"][0]
        self.assertEqual(row["coordinate_status"], "missing")
        self.assertFalse(row["compass_eligible"])
        self.assertIn("missing_coordinate", {issue["code"] for issue in row["issues"]})

    def test_strict_mode_allows_only_explicitly_known_missing_ids(self):
        report = AUDIT.build_audit([vendor("known", "Missing", "Somewhere", None)], [], {"vendors": {}})
        self.assertEqual(AUDIT.integrity_failures(report, {"known_missing_coordinate_ids": ["known"]}), [])
        self.assertEqual(AUDIT.integrity_failures(report, {"known_missing_coordinate_ids": []}), [("known", "missing_coordinate")])

    def test_verified_requires_two_publishers_and_coordinate_agreement(self):
        record = vendor("1", "Good", "Northeast corner of A & B", [-93.17, 44.98])
        config = {"vendors": {"1": {
            "status": "verified",
            "coordinates": [-93.17, 44.98],
            "sources": [
                {"publisher_group": "official"},
                {"publisher_group": "independent"},
            ],
        }}}
        row = AUDIT.build_audit([record], [], config)["vendors"][0]
        self.assertEqual(row["coordinate_status"], "verified")
        self.assertTrue(row["compass_eligible"])

    def test_duplicate_coordinate_with_conflicting_directions_is_high_risk(self):
        records = [
            vendor("1", "One", "Northwest corner of Carnes & Nelson", [-93.17, 44.98]),
            vendor("2", "Two", "Southeast corner of Lee & Cooper", [-93.17, 44.98]),
        ]
        report = AUDIT.build_audit(records, [], {"vendors": {}})
        for row in report["vendors"]:
            self.assertIn("duplicate_coordinate_location_conflict", {issue["code"] for issue in row["issues"]})

    def test_large_baseline_move_is_reviewed_not_auto_rejected(self):
        current = vendor("1", "Moved", "Location", [-93.17, 44.98])
        old = vendor("1", "Moved", "Location", [-93.18, 44.99])
        row = AUDIT.build_audit([current], [old], {"vendors": {}})["vendors"][0]
        self.assertIn("large_change_from_baseline", {issue["code"] for issue in row["issues"]})
        self.assertEqual(row["coordinate_status"], "unverified")

    def test_unique_pin_can_be_flagged_against_learned_street_corridor(self):
        records = [
            vendor(str(index), f"Anchor {index}", "North side of Carnes Ave. between Nelson & Underwood", [-93.17 + index * 0.00001, 44.9800])
            for index in range(8)
        ]
        records.append(vendor("bad", "Bad", "South side of Carnes Ave. between Chambers & Nelson", [-93.174, 44.9810]))
        report = AUDIT.build_audit(records, [], {"vendors": {}})
        row = next(row for row in report["vendors"] if row["id"] == "bad")
        self.assertIn("written_street_corridor_conflict", {issue["code"] for issue in row["issues"]})


if __name__ == "__main__":
    unittest.main()
