import unittest

from Scripts.compare_vendor_osm import comparison_rows, name_similarity


class CompareVendorOsmTests(unittest.TestCase):
    def test_name_normalization_handles_fair_suffix_and_punctuation(self):
        self.assertEqual(name_similarity("Andy's Grille", "Andys Grille"), 1.0)
        self.assertGreaterEqual(name_similarity("Lulu's Public House", "Lulus Public House"), 0.99)

    def test_exact_named_place_is_advisory_and_keeps_field_check(self):
        vendors = [
            {
                "id": "1",
                "name": "Ball Park Cafe",
                "coordinate_status": "withheld",
                "withheld_coordinates": [-93.17, 44.98],
                "booth_location": "East side of Underwood St.",
            }
        ]
        osm = {
            "elements": [
                {
                    "type": "node",
                    "id": 10,
                    "lon": -93.1701,
                    "lat": 44.9801,
                    "tags": {"name": "Ball Park Cafe", "addr:housenumber": "1312", "addr:street": "Underwood Street"},
                }
            ]
        }
        row = comparison_rows(vendors, osm)[0]
        self.assertEqual(row["match_class"], "exact_named_place")
        self.assertEqual(row["few_feet_field_check"], "required")
        self.assertEqual(row["osm_address"], "1312 Underwood Street")

    def test_duplicate_exact_names_are_ambiguous(self):
        vendors = [{"id": "1", "name": "Fresh French Fries", "coordinate_status": "missing", "booth_location": "At Midway"}]
        osm = {
            "elements": [
                {"type": "way", "id": 1, "center": {"lon": -93.17, "lat": 44.98}, "tags": {"name": "Fresh French Fries"}},
                {"type": "way", "id": 2, "center": {"lon": -93.18, "lat": 44.99}, "tags": {"name": "Fresh French Fries"}},
            ]
        }
        row = comparison_rows(vendors, osm)[0]
        self.assertEqual(row["match_class"], "ambiguous_exact_name")
        self.assertEqual(row["osm_name_match_count"], 2)

    def test_same_name_vendor_records_cannot_share_one_osm_identity(self):
        vendors = [
            {"id": "1", "name": "Pronto Pups", "coordinate_status": "withheld", "withheld_coordinates": [-93.17, 44.98]},
            {"id": "2", "name": "Pronto Pups", "coordinate_status": "withheld", "withheld_coordinates": [-93.171, 44.981]},
        ]
        osm = {
            "elements": [
                {"type": "way", "id": 1, "center": {"lon": -93.17, "lat": 44.98}, "tags": {"name": "Pronto Pups"}}
            ]
        }
        rows = comparison_rows(vendors, osm)
        self.assertTrue(all(row["match_class"] == "ambiguous_vendor_identity" for row in rows))
        self.assertTrue(all(row["vendor_same_name_count"] == 2 for row in rows))


if __name__ == "__main__":
    unittest.main()
