import unittest

from Scripts.build_public_map_review_batch import build_rows


class BuildPublicMapReviewBatchTests(unittest.TestCase):
    def test_selects_only_unreviewed_nonverified_records(self):
        vendors = [
            {"id": "1", "name": "One", "coordinate_status": "withheld", "detail_url": "official-1"},
            {"id": "2", "name": "Two", "coordinate_status": "missing", "detail_url": "official-2"},
            {"id": "3", "name": "Three", "coordinate_status": "verified"},
        ]
        geometry = {
            "1": {"location_check": "reject_over_30m"},
            "2": {"location_check": "unparsed"},
            "3": {"location_check": "consistent_with_written_location"},
        }
        config = {
            "reviewed_on": "2026-08-29",
            "expected_count": 1,
            "eligible_coordinate_statuses": ["withheld", "missing"],
            "default_reasons": {"unparsed": "no precise pin"},
            "exceptions": {},
        }
        rows = build_rows(vendors, geometry, {"1"}, config)
        self.assertEqual([row["id"] for row in rows], ["2"])
        self.assertEqual(rows[0]["outcome"], "insufficient_evidence")

    def test_expected_count_detects_population_drift(self):
        with self.assertRaisesRegex(ValueError, "review selection changed"):
            build_rows(
                [{"id": "1", "coordinate_status": "withheld"}],
                {"1": {"location_check": "unparsed"}},
                set(),
                {
                    "reviewed_on": "2026-08-29",
                    "expected_count": 2,
                    "default_reasons": {"unparsed": "reason"},
                },
            )


if __name__ == "__main__":
    unittest.main()
