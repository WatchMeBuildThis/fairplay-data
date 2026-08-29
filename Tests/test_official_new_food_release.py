import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "archive/vendors-2026-08-29-before-new-food-ordering.json"
RELEASE_FEED = ROOT / "archive/vendors-2026-08-29-before-three-remote-pin-corrections.json"


class OfficialNewFoodReleaseTests(unittest.TestCase):
    def test_builder_reproduces_committed_feed_and_audit_files(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            output = temporary / "vendors.json"
            changes = temporary / "changes.json"
            summary = temporary / "summary.json"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "Scripts/prioritize_official_new_foods.py"),
                    "--source", str(BASELINE),
                    "--output", str(output),
                    "--change-log", str(changes),
                    "--summary-output", str(summary),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(output.read_bytes(), RELEASE_FEED.read_bytes())
            self.assertEqual(
                json.loads(changes.read_text()),
                json.loads((ROOT / "audit/vendor-official-new-food-changes-2026-08-29.json").read_text()),
            )
            self.assertEqual(
                json.loads(summary.read_text()),
                json.loads((ROOT / "audit/vendor-official-new-food-summary-2026-08-29.json").read_text()),
            )

    def test_release_validator_accepts_committed_feed(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "validation.json"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "Scripts/validate_official_new_food_release.py"),
                    "--baseline", str(BASELINE),
                    "--candidate", str(RELEASE_FEED),
                    "--output", str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            result = json.loads(output.read_text())
            self.assertEqual(result["release_gate"], "pass")
            self.assertEqual(result["record_count"], 278)
            self.assertEqual(result["official_new_food_vendor_count"], 33)
            self.assertEqual(
                result["official_vendors_with_every_new_food_first_and_visible"], 33
            )
            self.assertTrue(result["pin_fields_preserved"])
            self.assertTrue(result["unrelated_fields_preserved"])


if __name__ == "__main__":
    unittest.main()
