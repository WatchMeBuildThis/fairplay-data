#!/usr/bin/env python3
"""Check every vendor candidate against its written fair location and OSM geometry.

The result is a deterministic review aid, not a geocoder and not an automatic
publisher.  It answers whether the current candidate is close to the street
corner, street segment, or named venue described by the fair.  It deliberately
does not invent a replacement point when the description cannot be parsed.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path


EARTH_RADIUS_M = 6_371_008.8
CONSISTENT_M = 15.0
REJECT_M = 30.0
STREET_SUFFIXES = {"avenue", "street", "road", "place", "drive"}

NAMED_ALIASES = {
    "ag hort building": "Agriculture Horticulture Building",
    "agriculture horticulture building": "Agriculture Horticulture Building",
    "coliseum": "Lee & Rose Warner Coliseum",
    "food building": "Food Building",
    "international bazaar": "International Bazaar",
    "kidway": "Kidway Lot",
    "merch market": "Merchandise Mart",
    "merchandise mart": "Merchandise Mart",
    "mighty midway": "Midway Lot",
    "progress center": "Eco Experience Progress Center",
    "the garden": "Treasure Island | The Garden",
}


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().replace("&", " and ")
    value = re.sub(r"\baves?\.?\b|\bavenues?\b", " avenue ", value)
    value = re.sub(r"\bsts?\.?\b|\bstreets?\b", " street ", value)
    value = re.sub(r"\brds?\.?\b|\broads?\b", " road ", value)
    value = re.sub(r"\bw\.?\s+", "west ", value)
    value = re.sub(r"\be\.?\s+", "east ", value)
    value = re.sub(r"\bn\.?\s+", "north ", value)
    value = re.sub(r"\bs\.?\s+", "south ", value)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def local_xy(point: tuple[float, float], origin_lat: float = 44.982) -> tuple[float, float]:
    lon, lat = point
    x = math.radians(lon) * EARTH_RADIUS_M * math.cos(math.radians(origin_lat))
    y = math.radians(lat) * EARTH_RADIUS_M
    return x, y


def local_lon_lat(point: tuple[float, float], origin_lat: float = 44.982) -> tuple[float, float]:
    x, y = point
    lon = math.degrees(x / (EARTH_RADIUS_M * math.cos(math.radians(origin_lat))))
    lat = math.degrees(y / EARTH_RADIUS_M)
    return lon, lat


def lon_lat(point: dict) -> tuple[float, float]:
    return float(point["lon"]), float(point["lat"])


def distance(left: tuple[float, float], right: tuple[float, float]) -> float:
    x1, y1 = local_xy(left)
    x2, y2 = local_xy(right)
    return math.hypot(x2 - x1, y2 - y1)


def point_segment_distance(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> float:
    px, py = local_xy(point)
    ax, ay = local_xy(start)
    bx, by = local_xy(end)
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def point_polyline_distance(point: tuple[float, float], geometry: list[tuple[float, float]]) -> float:
    if not geometry:
        return float("inf")
    if len(geometry) == 1:
        return distance(point, geometry[0])
    return min(point_segment_distance(point, a, b) for a, b in zip(geometry, geometry[1:]))


def point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    if len(polygon) < 4:
        return False
    x, y = local_xy(point)
    projected = [local_xy(value) for value in polygon]
    inside = False
    previous = projected[-1]
    for current in projected:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y):
            crossing = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing:
                inside = not inside
        previous = current
    return inside


def feature_distance(point: tuple[float, float], feature: dict) -> float:
    geometry = feature.get("_geometry", [])
    if feature.get("tags", {}).get("building") and point_in_polygon(point, geometry):
        return 0.0
    if geometry:
        return point_polyline_distance(point, geometry)
    center = feature.get("center")
    if center:
        return distance(point, lon_lat(center))
    if "lon" in feature and "lat" in feature:
        return distance(point, (float(feature["lon"]), float(feature["lat"])))
    return float("inf")


def candidate_for(vendor: dict) -> tuple[float, float] | None:
    value = vendor.get("coordinates") or vendor.get("withheld_coordinates")
    if not isinstance(value, list) or len(value) != 2:
        return None
    return float(value[0]), float(value[1])


def geometry_for(element: dict) -> list[tuple[float, float]]:
    return [lon_lat(point) for point in element.get("geometry", [])]


def road_base(name: str) -> str:
    tokens = normalize(name).split()
    if tokens and tokens[-1] in STREET_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def build_roads(osm: dict) -> dict[str, list[list[tuple[float, float]]]]:
    roads: dict[str, list[list[tuple[float, float]]]] = {}
    for element in osm.get("elements", []):
        tags = element.get("tags", {})
        if element.get("type") != "way" or not tags.get("highway") or not tags.get("name"):
            continue
        geometry = geometry_for(element)
        if geometry:
            roads.setdefault(tags["name"], []).append(geometry)
    return roads


def street_mentions(text: str, roads: dict[str, list]) -> list[str]:
    normalized = normalize(text)
    aliases = []
    for name in roads:
        full = normalize(name)
        base = road_base(name)
        for alias in {full, base}:
            if alias:
                aliases.append((len(alias), alias, name))
    aliases.sort(reverse=True)

    matches: list[tuple[int, int, str]] = []
    used: list[tuple[int, int]] = []
    for _, alias, name in aliases:
        for match in re.finditer(rf"\b{re.escape(alias)}\b", normalized):
            span = match.span()
            if any(not (span[1] <= prior[0] or span[0] >= prior[1]) for prior in used):
                continue
            used.append(span)
            matches.append((span[0], span[1], name))
    matches.sort()
    result = []
    for _, _, name in matches:
        if name not in result:
            result.append(name)
    return result


def road_points(roads: dict[str, list[list[tuple[float, float]]]], name: str) -> list[tuple[float, float]]:
    return [point for geometry in roads.get(name, []) for point in geometry]


def infinite_line_intersection(
    left_start: tuple[float, float],
    left_end: tuple[float, float],
    right_start: tuple[float, float],
    right_end: tuple[float, float],
) -> tuple[float, float] | None:
    p = local_xy(left_start)
    r = tuple(b - a for a, b in zip(p, local_xy(left_end)))
    q = local_xy(right_start)
    s = tuple(b - a for a, b in zip(q, local_xy(right_end)))
    cross = r[0] * s[1] - r[1] * s[0]
    lengths = math.hypot(*r) * math.hypot(*s)
    if not lengths or abs(cross) / lengths < 0.15:
        return None
    q_minus_p = (q[0] - p[0], q[1] - p[1])
    t = (q_minus_p[0] * s[1] - q_minus_p[1] * s[0]) / cross
    return local_lon_lat((p[0] + t * r[0], p[1] + t * r[1]))


def road_intersection(roads: dict[str, list], left: str, right: str) -> tuple[tuple[float, float], float] | None:
    left_points = road_points(roads, left)
    right_points = road_points(roads, right)
    if not left_points or not right_points:
        return None
    best = min(
        ((distance(a, b), a, b) for a in left_points for b in right_points),
        key=lambda value: value[0],
    )
    separation, a, b = best
    if separation <= 20:
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), separation

    # OSM sometimes stops a fairground road centerline before the named cross
    # street. Extrapolate local segment directions only across a small gap;
    # this recovers the documented grid intersection without geocoding a pin.
    extrapolated = []
    for left_geometry in roads.get(left, []):
        for left_segment in zip(left_geometry, left_geometry[1:]):
            for right_geometry in roads.get(right, []):
                for right_segment in zip(right_geometry, right_geometry[1:]):
                    intersection = infinite_line_intersection(*left_segment, *right_segment)
                    if not intersection:
                        continue
                    left_gap = point_segment_distance(intersection, *left_segment)
                    right_gap = point_segment_distance(intersection, *right_segment)
                    if max(left_gap, right_gap) <= 100:
                        extrapolated.append((left_gap + right_gap, intersection))
    if not extrapolated:
        return None
    gap, intersection = min(extrapolated, key=lambda value: value[0])
    return intersection, gap


def named_feature(text: str, features_by_name: dict[str, list[dict]]) -> tuple[str, dict] | None:
    normalized = normalize(text)
    for alias, canonical in sorted(NAMED_ALIASES.items(), key=lambda item: -len(item[0])):
        if normalize(alias) in normalized and canonical in features_by_name:
            return canonical, features_by_name[canonical][0]

    candidates = []
    text_tokens = set(normalized.split())
    for name, features in features_by_name.items():
        tokens = {token for token in normalize(name).split() if len(token) >= 3 and token != "the"}
        if len(tokens) >= 2 and tokens.issubset(text_tokens):
            candidates.append((len(tokens), len(name), name, features[0]))
    if not candidates:
        return None
    _, _, name, feature = max(candidates)
    return name, feature


def is_named_place(element: dict) -> bool:
    """Return whether an OSM feature belongs in the venue/building matcher.

    Roads are parsed separately. Including them here lets a phrase such as
    "north side of Randall Ave." select one arbitrary road way as a venue and
    creates a block-scale false positive.
    """

    tags = element.get("tags", {})
    if tags.get("highway"):
        return False
    return any(
        tags.get(key)
        for key in (
            "amenity",
            "building",
            "historic",
            "leisure",
            "office",
            "place",
            "shop",
            "tourism",
        )
    )


def classify(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "unparsed"
    if value <= CONSISTENT_M:
        return "consistent_with_written_location"
    if value <= REJECT_M:
        return "manual_review_15_to_30m"
    return "reject_over_30m"


def check_vendor(vendor: dict, roads: dict[str, list], features_by_name: dict[str, list[dict]]) -> dict:
    point = candidate_for(vendor)
    location = vendor.get("booth_location") or vendor.get("directions") or ""
    if not point:
        value = None
        anchor_kind = "none"
        anchor = "No coordinate candidate"
    else:
        streets = street_mentions(location, roads)
        normalized = normalize(location)
        named = named_feature(location, features_by_name)
        value = None
        anchor_kind = "unparsed"
        anchor = ""

        if "corner" in normalized and len(streets) >= 2:
            result = road_intersection(roads, streets[0], streets[1])
            if result:
                intersection, _ = result
                value = distance(point, intersection)
                anchor_kind = "street_corner"
                anchor = f"{streets[0]} & {streets[1]}"
        elif "between" in normalized and len(streets) >= 3:
            first = road_intersection(roads, streets[0], streets[1])
            second = road_intersection(roads, streets[0], streets[2])
            if first and second:
                value = point_segment_distance(point, first[0], second[0])
                anchor_kind = "street_segment"
                anchor = f"{streets[0]} between {streets[1]} and {streets[2]}"
        elif named:
            name, feature = named
            value = feature_distance(point, feature)
            anchor_kind = "named_place_or_building"
            anchor = name
        elif streets:
            geometries = roads.get(streets[0], [])
            if geometries:
                value = min(point_polyline_distance(point, geometry) for geometry in geometries)
                anchor_kind = "street_corridor"
                anchor = streets[0]

    check = classify(value)
    coordinate_status = vendor.get("coordinate_status", "")
    if not point:
        publication_decision = "no_coordinate_candidate"
    elif coordinate_status == "verified" and check == "reject_over_30m":
        publication_decision = "reopen_verified_before_next_publish"
    elif coordinate_status == "verified":
        publication_decision = "retain_verified"
    elif check == "reject_over_30m":
        publication_decision = "keep_withheld_priority_review"
    else:
        publication_decision = "manual_evidence_required"

    return {
        "id": vendor.get("id", ""),
        "name": vendor.get("name", ""),
        "coordinate_status": coordinate_status,
        "booth_location": location,
        "candidate_longitude": point[0] if point else "",
        "candidate_latitude": point[1] if point else "",
        "anchor_kind": anchor_kind,
        "anchor": anchor,
        "constraint_distance_m": round(value, 1) if value is not None and math.isfinite(value) else "",
        "location_check": check,
        "publication_decision": publication_decision,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vendors", required=True, type=Path)
    parser.add_argument("--osm", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary-output", type=Path)
    args = parser.parse_args()

    if args.output.exists() or (args.summary_output and args.summary_output.exists()):
        raise SystemExit("refusing to overwrite an existing output")
    vendors = json.loads(args.vendors.read_text())
    osm = json.loads(args.osm.read_text())
    roads = build_roads(osm)
    features_by_name: dict[str, list[dict]] = {}
    for element in osm.get("elements", []):
        name = element.get("tags", {}).get("name")
        if not name or not is_named_place(element):
            continue
        enriched = dict(element)
        enriched["_geometry"] = geometry_for(element)
        features_by_name.setdefault(name, []).append(enriched)

    rows = [check_vendor(vendor, roads, features_by_name) for vendor in vendors]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    if args.summary_output:
        summary = {
            "record_count": len(rows),
            "thresholds_m": {"consistent_max": CONSISTENT_M, "reject_above": REJECT_M},
            "location_check_counts": dict(Counter(row["location_check"] for row in rows)),
            "anchor_kind_counts": dict(Counter(row["anchor_kind"] for row in rows)),
            "coordinate_status_counts": dict(Counter(row["coordinate_status"] for row in rows)),
            "verified_location_check_counts": dict(
                Counter(
                    row["location_check"]
                    for row in rows
                    if row["coordinate_status"] == "verified"
                )
            ),
            "verified_over_30m_ids": [
                row["id"]
                for row in rows
                if row["coordinate_status"] == "verified"
                and row["location_check"] == "reject_over_30m"
            ],
            "policy": "Geometry conflicts reopen verification and prioritize review; they never verify or move a pin automatically.",
        }
        args.summary_output.write_text(json.dumps(summary, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
