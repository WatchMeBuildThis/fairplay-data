import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).parents[1] / "Scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT_PATH = SCRIPTS / "audit_official_app_snapshot.py"
SPEC = importlib.util.spec_from_file_location("audit_official_app_snapshot", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class OfficialAppSnapshotAuditTests(unittest.TestCase):
    def test_app_percentages_reproduce_bridge_map_ref(self) -> None:
        coordinate = MODULE.official_map_coordinate(
            {"left2": "64.6470588235", "top2": "56.9772727273"}
        )
        expected = MODULE.MapPerspective().unproject(x=2198, y=1893)
        self.assertAlmostEqual(coordinate[0], expected[0], places=10)
        self.assertAlmostEqual(coordinate[1], expected[1], places=10)

    def test_catalog_uses_exact_vendor_url_id(self) -> None:
        catalog = MODULE.food_catalog(
            [{"cat": "Food", "vendors": [{"u": "https://www.mnstatefair.org/vendor/2065.1", "f": "Chan's"}]}]
        )
        self.assertEqual(list(catalog), ["2065.1"])

    def test_missing_official_location_is_not_close(self) -> None:
        self.assertEqual(MODULE.priority(None, False), "official_app_map_missing")

    def test_snapshot_download_rejects_an_unexpected_host(self) -> None:
        with self.assertRaises(ValueError):
            MODULE.download_json("https://example.com/956_master.txt")


if __name__ == "__main__":
    unittest.main()
