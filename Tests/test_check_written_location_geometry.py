import unittest

from Scripts.check_written_location_geometry import (
    build_roads,
    check_vendor,
    is_named_place,
    road_intersection,
)


def osm_fixture():
    return {
        "elements": [
            {
                "type": "way",
                "id": 1,
                "tags": {"name": "Dan Patch Avenue", "highway": "unclassified"},
                "geometry": [
                    {"lon": -93.172, "lat": 44.980},
                    {"lon": -93.170, "lat": 44.980},
                    {"lon": -93.168, "lat": 44.980},
                ],
            },
            {
                "type": "way",
                "id": 2,
                "tags": {"name": "Underwood Street", "highway": "unclassified"},
                "geometry": [
                    {"lon": -93.170, "lat": 44.979},
                    {"lon": -93.170, "lat": 44.980},
                    {"lon": -93.170, "lat": 44.981},
                ],
            },
            {
                "type": "way",
                "id": 3,
                "tags": {"name": "Nelson Street", "highway": "unclassified"},
                "geometry": [
                    {"lon": -93.172, "lat": 44.979},
                    {"lon": -93.172, "lat": 44.980},
                    {"lon": -93.172, "lat": 44.981},
                ],
            },
            {
                "type": "way",
                "id": 4,
                "tags": {"name": "Food Building", "building": "yes"},
                "geometry": [
                    {"lon": -93.171, "lat": 44.979},
                    {"lon": -93.170, "lat": 44.979},
                    {"lon": -93.170, "lat": 44.9795},
                    {"lon": -93.171, "lat": 44.9795},
                    {"lon": -93.171, "lat": 44.979},
                ],
            },
        ]
    }


def features(osm):
    result = {}
    for element in osm["elements"]:
        name = element.get("tags", {}).get("name")
        if name:
            copied = dict(element)
            copied["_geometry"] = [(p["lon"], p["lat"]) for p in element.get("geometry", [])]
            result.setdefault(name, []).append(copied)
    return result


class WrittenLocationGeometryTests(unittest.TestCase):
    def setUp(self):
        self.osm = osm_fixture()
        self.roads = build_roads(self.osm)
        self.features = features(self.osm)

    def test_corner_candidate_is_consistent(self):
        vendor = {
            "id": "1",
            "name": "Stand",
            "coordinate_status": "withheld",
            "withheld_coordinates": [-93.17002, 44.98002],
            "booth_location": "Southeast corner of Dan Patch Ave. & Underwood St.",
        }
        row = check_vendor(vendor, self.roads, self.features)
        self.assertEqual(row["anchor_kind"], "street_corner")
        self.assertEqual(row["location_check"], "consistent_with_written_location")

    def test_same_street_wrong_block_is_rejected_by_between_constraint(self):
        vendor = {
            "id": "2",
            "name": "Stand",
            "coordinate_status": "withheld",
            "withheld_coordinates": [-93.168, 44.980],
            "booth_location": "South side of Dan Patch Ave. between Nelson & Underwood streets",
        }
        row = check_vendor(vendor, self.roads, self.features)
        self.assertEqual(row["anchor_kind"], "street_segment")
        self.assertEqual(row["location_check"], "reject_over_30m")

    def test_verified_conflict_is_reopened_not_silently_retained(self):
        vendor = {
            "id": "2",
            "name": "Stand",
            "coordinate_status": "verified",
            "coordinates": [-93.168, 44.980],
            "booth_location": "South side of Dan Patch Ave. between Nelson & Underwood streets",
        }
        row = check_vendor(vendor, self.roads, self.features)
        self.assertEqual(row["location_check"], "reject_over_30m")
        self.assertEqual(row["publication_decision"], "reopen_verified_before_next_publish")

    def test_point_inside_named_building_is_consistent(self):
        vendor = {
            "id": "3",
            "name": "Stand",
            "coordinate_status": "withheld",
            "withheld_coordinates": [-93.1705, 44.97925],
            "booth_location": "In the Food Building, east wall",
        }
        row = check_vendor(vendor, self.roads, self.features)
        self.assertEqual(row["anchor_kind"], "named_place_or_building")
        self.assertEqual(row["constraint_distance_m"], 0.0)

    def test_nearby_named_landmark_prevents_false_rejection(self):
        vendor = {
            "id": "4",
            "name": "Stand",
            "coordinate_status": "verified",
            "coordinates": [-93.1705, 44.97925],
            "booth_location": (
                "South side of Dan Patch Ave. between Nelson & Underwood streets, "
                "next to the Food Building"
            ),
        }
        row = check_vendor(vendor, self.roads, self.features)
        self.assertEqual(row["anchor_kind"], "street_segment")
        self.assertEqual(row["secondary_named_anchor"], "Food Building")
        self.assertEqual(row["secondary_named_distance_m"], 0.0)
        self.assertEqual(row["location_check"], "manual_review_conflicting_constraints")
        self.assertEqual(
            row["publication_decision"],
            "retain_verified_with_landmark_exception_review",
        )

    def test_exact_vendor_identity_prevents_road_model_false_rejection(self):
        vendor = {
            "id": "5",
            "name": "Permanent Vendor",
            "coordinate_status": "verified",
            "coordinates": [-93.168, 44.980],
            "booth_location": "South side of Dan Patch Ave. between Nelson & Underwood streets",
        }
        identity_match = {
            "match_class": "exact_named_place",
            "osm_name": "Permanent Vendor",
            "candidate_to_osm_m": 6.2,
            "osm_url": "https://www.openstreetmap.org/way/5",
        }
        row = check_vendor(vendor, self.roads, self.features, identity_match)
        self.assertEqual(row["secondary_identity_anchor"], "Permanent Vendor")
        self.assertEqual(row["secondary_identity_distance_m"], 6.2)
        self.assertEqual(row["location_check"], "manual_review_conflicting_constraints")
        self.assertEqual(
            row["publication_decision"],
            "retain_verified_with_landmark_exception_review",
        )

    def test_possible_or_distant_identity_does_not_override_conflict(self):
        vendor = {
            "id": "6",
            "name": "Temporary Vendor",
            "coordinate_status": "verified",
            "coordinates": [-93.168, 44.980],
            "booth_location": "South side of Dan Patch Ave. between Nelson & Underwood streets",
        }
        possible_match = {
            "match_class": "possible_named_place",
            "osm_name": "Temporary Vendor Ride",
            "candidate_to_osm_m": 4.0,
            "osm_url": "https://www.openstreetmap.org/way/6",
        }
        row = check_vendor(vendor, self.roads, self.features, possible_match)
        self.assertEqual(row["location_check"], "reject_over_30m")

        distant_match = {
            "match_class": "exact_named_place",
            "osm_name": "Temporary Vendor",
            "candidate_to_osm_m": 22.0,
            "osm_url": "https://www.openstreetmap.org/way/7",
        }
        row = check_vendor(vendor, self.roads, self.features, distant_match)
        self.assertEqual(row["location_check"], "reject_over_30m")

    def test_road_is_not_a_named_place(self):
        self.assertFalse(
            is_named_place(
                {"type": "way", "tags": {"name": "Randall Avenue", "highway": "service"}}
            )
        )

    def test_building_is_a_named_place(self):
        self.assertTrue(
            is_named_place(
                {"type": "way", "tags": {"name": "Food Building", "building": "yes"}}
            )
        )

    def test_small_road_geometry_gap_can_be_extrapolated(self):
        roads = {
            "Horizontal Avenue": [[(-93.171, 44.980), (-93.169, 44.980)]],
            "Vertical Street": [[(-93.170, 44.979), (-93.170, 44.9795)]],
        }
        result = road_intersection(roads, "Horizontal Avenue", "Vertical Street")
        self.assertIsNotNone(result)
        point, gap = result
        self.assertAlmostEqual(point[0], -93.170, places=5)
        self.assertAlmostEqual(point[1], 44.980, places=5)
        self.assertGreater(gap, 50)


if __name__ == "__main__":
    unittest.main()
