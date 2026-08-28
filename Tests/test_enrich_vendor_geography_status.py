import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "Scripts" / "enrich_vendor_geography_status.py"
SPEC = importlib.util.spec_from_file_location("enrich_vendor_geography_status", MODULE_PATH)
ENRICH = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = ENRICH
SPEC.loader.exec_module(ENRICH)


class GeographyStatusEnrichmentTests(unittest.TestCase):
    def test_adds_status_and_compass_decision(self):
        records = [{"id": "1", "name": "One"}]
        audit = {"vendors": [{
            "id": "1",
            "coordinate_status": "verified",
            "compass_eligible": True,
        }]}
        result = ENRICH.enrich_records(records, audit)
        self.assertEqual(result[0]["coordinate_status"], "verified")
        self.assertTrue(result[0]["compass_eligible"])

    def test_rejects_feed_audit_id_drift(self):
        with self.assertRaises(ValueError):
            ENRICH.enrich_records([{"id": "1"}], {"vendors": []})


if __name__ == "__main__":
    unittest.main()
