import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BingoReleaseTests(unittest.TestCase):
    def test_committed_bingo_expansion_passes_release_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "validation.json"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "Scripts/validate_bingo_release.py"),
                    "--baseline",
                    str(ROOT / "archive/bingo-squares-2026-08-29-before-200-prompt-expansion.json"),
                    "--candidate", str(ROOT / "bingo_squares.json"),
                    "--additions", str(ROOT / "audit/bingo-prompt-additions-2026-08-29.json"),
                    "--output", str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            result = json.loads(output.read_text())
            self.assertEqual(result["release_gate"], "pass")
            self.assertEqual(result["baseline_prompt_count"], 160)
            self.assertEqual(result["approved_addition_count"], 40)
            self.assertEqual(result["candidate_prompt_count"], 200)
            self.assertEqual(result["candidate_unique_prompt_count"], 200)
            self.assertLessEqual(result["maximum_prompt_length"], 26)
            self.assertTrue(result["existing_prompt_order_preserved"])


if __name__ == "__main__":
    unittest.main()
