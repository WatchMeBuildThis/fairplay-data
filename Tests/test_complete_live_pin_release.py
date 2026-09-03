import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CompleteLivePinReleaseTests(unittest.TestCase):
    def test_builder_reproduces_committed_feed_and_change_log(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            output = temporary / "vendors.json"
            changes = temporary / "changes.json"
            summary = temporary / "summary.json"
            live = ROOT / "archive/vendors-2026-08-29-before-complete-pin-repair.json"
            historical_verifications = temporary / "location-verifications-2026-08-29.json"
            verification_config = json.loads((ROOT / "location_verifications.json").read_text())
            verification_config["vendors"] = {
                vendor_id: verification
                for vendor_id, verification in verification_config["vendors"].items()
                if str(verification.get("verified_on") or "") <= "2026-08-29"
            }
            historical_verifications.write_text(json.dumps(verification_config))
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "Scripts/build_complete_live_pin_feed.py"),
                    "--source", str(live),
                    "--publish-base", str(live),
                    "--verifications", str(historical_verifications),
                    "--geometry", str(ROOT / "audit/vendor-written-location-geometry-source-2026-08-29.csv"),
                    "--osm", str(ROOT / "audit/osm-fairgrounds-full-geometry-2026-08-28.json"),
                    "--bundled-fallback", str(ROOT / "audit/vendor-bundled-zone-fallbacks-2026-08-29.json"),
                    "--output", str(output),
                    "--change-log", str(changes),
                    "--summary-output", str(summary),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                json.loads(output.read_text()),
                json.loads((ROOT / "archive/vendors-2026-08-29-before-new-food-ordering.json").read_text()),
            )
            self.assertEqual(
                json.loads(changes.read_text()),
                json.loads((ROOT / "audit/vendor-complete-pin-changes-2026-08-29.json").read_text()),
            )
            result = json.loads(summary.read_text())
            self.assertEqual(result["record_count"], 278)
            self.assertEqual(result["published_pin_count"], 278)
            self.assertEqual(result["changed_or_filled_count"], 157)

    def test_release_validator_accepts_committed_feed(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "validation.json"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "Scripts/validate_live_pin_release.py"),
                    "--live", str(ROOT / "archive/vendors-2026-08-29-before-complete-pin-repair.json"),
                    "--candidate", str(ROOT / "archive/vendors-2026-08-29-before-new-food-ordering.json"),
                    "--change-log", str(ROOT / "audit/vendor-complete-pin-changes-2026-08-29.json"),
                    "--output", str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            result = json.loads(output.read_text())
            self.assertEqual(result["release_gate"], "pass")
            self.assertEqual(result["shipping_app_decodable_pin_count"], 278)
            self.assertEqual(result["inside_fair_pin_count"], 278)
            self.assertTrue(result["non_location_content_preserved"])
            self.assertEqual(result["new_exact_overlap_group_count"], 0)


if __name__ == "__main__":
    unittest.main()
