import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "Scripts" / "apply_vendor_verifications.py"
SPEC = importlib.util.spec_from_file_location("apply_vendor_verifications", MODULE_PATH)
APPLY = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = APPLY
SPEC.loader.exec_module(APPLY)


def verification(status="verified", groups=("official", "independent"), coordinates=None):
    return {
        "status": status,
        "coordinates": coordinates or [-93.17, 44.98],
        "method": "Reviewed exact place pin against written fair directions.",
        "verified_on": "2026-08-28",
        "sources": [{"publisher_group": group} for group in groups],
    }


class ApplyVendorVerificationsTests(unittest.TestCase):
    def test_applies_only_selected_verified_coordinate(self):
        records = [
            {"id": "1", "name": "One", "coordinates": [-93.171, 44.981]},
            {"id": "2", "name": "Two", "coordinates": [-93.172, 44.982]},
        ]
        config = {"vendors": {"1": verification(), "2": verification(coordinates=[-93.173, 44.983])}}
        result, changes = APPLY.apply_verifications(records, config, {"1"})
        self.assertEqual(result[0]["coordinates"], [-93.17, 44.98])
        self.assertEqual(result[1]["coordinates"], [-93.172, 44.982])
        self.assertEqual([change["id"] for change in changes], ["1"])

    def test_removes_quarantine_only_after_verified_apply(self):
        records = [{
            "id": "1", "coordinates": None,
            "quarantined_coordinates": [-93.18, 44.99],
            "quarantine_reason": "conflicted",
        }]
        result, _ = APPLY.apply_verifications(records, {"vendors": {"1": verification()}}, {"1"})
        self.assertNotIn("quarantined_coordinates", result[0])
        self.assertNotIn("quarantine_reason", result[0])

    def test_rejects_single_publisher_group(self):
        records = [{"id": "1", "coordinates": [-93.171, 44.981]}]
        config = {"vendors": {"1": verification(groups=("official", "official"))}}
        with self.assertRaisesRegex(ValueError, "two publisher groups"):
            APPLY.apply_verifications(records, config, {"1"})

    def test_rejects_approximate_candidate(self):
        records = [{"id": "1", "coordinates": [-93.171, 44.981]}]
        config = {"vendors": {"1": verification(status="approximate")}}
        with self.assertRaisesRegex(ValueError, "status=verified"):
            APPLY.apply_verifications(records, config, {"1"})

    def test_rejects_out_of_bounds_coordinate(self):
        records = [{"id": "1", "coordinates": [-93.171, 44.981]}]
        config = {"vendors": {"1": verification(coordinates=[0, 0])}}
        with self.assertRaisesRegex(ValueError, "outside fair bounds"):
            APPLY.apply_verifications(records, config, {"1"})

    def test_rejects_unknown_selected_id(self):
        with self.assertRaisesRegex(ValueError, "Selected id mismatch"):
            APPLY.apply_verifications([{"id": "1"}], {"vendors": {"1": verification()}}, {"2"})


if __name__ == "__main__":
    unittest.main()
