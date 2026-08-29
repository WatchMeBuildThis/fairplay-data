#!/usr/bin/env python3
"""Build a 278-pin feed for the shipping client without changing app code.

The App Store build treats every non-null ``coordinates`` value as both a map
pin and a compass/walking target. It ignores the audit status fields. This
publisher therefore fills every record while replacing unresolved candidates
that conflict with the fair's written location by more than 30 m.

Priority:

1. reviewed verified/approximate coordinates from the evidence ledger;
2. existing candidates within 30 m of deterministic written geometry;
3. a projection onto the written corner, street segment/corridor, or named
   venue for unresolved geometry conflicts;
4. a bundled fallback only when explicitly configured for a source-missing
   record whose current written zone agrees.

Direction-derived points are honest approximations, not few-feet verification.
The script records their method and displacement in a separate change log.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


EARTH_RADIUS_M = 6_371_008.8
FAIR_BOUNDS = (-93.19, -93.15, 44.96, 45.00)
STREET_SUFFIXES = {"avenue", "street", "road", "place", "drive"}
SIDE_OFFSET_M = 9.0
CORNER_OFFSET_M = 10.0

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
    return (
        math.radians(lon) * EARTH_RADIUS_M * math.cos(math.radians(origin_lat)),
        math.radians(lat) * EARTH_RADIUS_M,
    )


def local_lon_lat(point: tuple[float, float], origin_lat: float = 44.982) -> tuple[float, float]:
    x, y = point
    return (
        math.degrees(x / (EARTH_RADIUS_M * math.cos(math.radians(origin_lat)))),
        math.degrees(y / EARTH_RADIUS_M),
    )


def distance(left: tuple[float, float], right: tuple[float, float]) -> float:
    x1, y1 = local_xy(left)
    x2, y2 = local_xy(right)
    return math.hypot(x2 - x1, y2 - y1)


def parse_coordinate(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    try:
        point = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(item) for item in point):
        return None
    return point


def in_fair_bounds(point: tuple[float, float]) -> bool:
    min_lon, max_lon, min_lat, max_lat = FAIR_BOUNDS
    return min_lon < point[0] < max_lon and min_lat < point[1] < max_lat


def geometry_for(element: dict[str, Any]) -> list[tuple[float, float]]:
    return [
        (float(point["lon"]), float(point["lat"]))
        for point in element.get("geometry") or []
        if "lon" in point and "lat" in point
    ]


def build_roads(osm: dict[str, Any]) -> dict[str, list[list[tuple[float, float]]]]:
    roads: dict[str, list[list[tuple[float, float]]]] = defaultdict(list)
    for element in osm.get("elements") or []:
        tags = element.get("tags") or {}
        if element.get("type") == "way" and tags.get("highway") and tags.get("name"):
            geometry = geometry_for(element)
            if geometry:
                roads[str(tags["name"])].append(geometry)
    return dict(roads)


def is_named_place(element: dict[str, Any]) -> bool:
    tags = element.get("tags") or {}
    if tags.get("highway"):
        return False
    return any(tags.get(key) for key in (
        "amenity", "building", "historic", "leisure", "office", "place", "shop", "tourism"
    ))


def build_named_features(osm: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    features: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for element in osm.get("elements") or []:
        name = str((element.get("tags") or {}).get("name") or "")
        if name and is_named_place(element):
            enriched = dict(element)
            enriched["_geometry"] = geometry_for(element)
            features[name].append(enriched)
    return dict(features)


def road_base(name: str) -> str:
    tokens = normalize(name).split()
    if tokens and tokens[-1] in STREET_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def street_mentions(text: str, roads: dict[str, list]) -> list[str]:
    normalized = normalize(text)
    aliases: list[tuple[int, str, str]] = []
    for name in roads:
        for alias in {normalize(name), road_base(name)}:
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
    result: list[str] = []
    for _, _, name in matches:
        if name not in result:
            result.append(name)
    return result


def point_segment_projection(
    point: tuple[float, float] | None,
    start: tuple[float, float],
    end: tuple[float, float],
) -> tuple[float, float]:
    ax, ay = local_xy(start)
    bx, by = local_xy(end)
    if point is None:
        return local_lon_lat(((ax + bx) / 2, (ay + by) / 2))
    px, py = local_xy(point)
    dx, dy = bx - ax, by - ay
    if not dx and not dy:
        return start
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return local_lon_lat((ax + t * dx, ay + t * dy))


def nearest_polyline_projection(
    point: tuple[float, float],
    geometries: list[list[tuple[float, float]]],
) -> tuple[float, float] | None:
    candidates: list[tuple[float, tuple[float, float]]] = []
    for geometry in geometries:
        for start, end in zip(geometry, geometry[1:]):
            projected = point_segment_projection(point, start, end)
            candidates.append((distance(point, projected), projected))
    return min(candidates, default=(0, None), key=lambda item: item[0])[1]


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
    q_minus_p = q[0] - p[0], q[1] - p[1]
    t = (q_minus_p[0] * s[1] - q_minus_p[1] * s[0]) / cross
    return local_lon_lat((p[0] + t * r[0], p[1] + t * r[1]))


def road_points(roads: dict[str, list], name: str) -> list[tuple[float, float]]:
    return [point for geometry in roads.get(name, []) for point in geometry]


def road_intersection(
    roads: dict[str, list], left: str, right: str
) -> tuple[float, float] | None:
    left_points = road_points(roads, left)
    right_points = road_points(roads, right)
    if not left_points or not right_points:
        return None
    separation, a, b = min(
        ((distance(a, b), a, b) for a in left_points for b in right_points),
        key=lambda value: value[0],
    )
    if separation <= 20:
        return (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    extrapolated: list[tuple[float, tuple[float, float]]] = []
    for left_geometry in roads.get(left, []):
        for left_segment in zip(left_geometry, left_geometry[1:]):
            for right_geometry in roads.get(right, []):
                for right_segment in zip(right_geometry, right_geometry[1:]):
                    point = infinite_line_intersection(*left_segment, *right_segment)
                    if not point:
                        continue
                    left_projection = point_segment_projection(point, *left_segment)
                    right_projection = point_segment_projection(point, *right_segment)
                    gap = max(distance(point, left_projection), distance(point, right_projection))
                    if gap <= 100:
                        extrapolated.append((gap, point))
    return min(extrapolated, default=(0, None), key=lambda item: item[0])[1]


def offset(point: tuple[float, float], east_m: float = 0, north_m: float = 0) -> tuple[float, float]:
    x, y = local_xy(point)
    return local_lon_lat((x + east_m, y + north_m))


def directional_offset(text: str, corner: bool = False) -> tuple[float, float]:
    value = normalize(text)
    amount = CORNER_OFFSET_M if corner else SIDE_OFFSET_M
    if corner:
        east = amount if re.search(r"\b(?:north|south)?east(?:ern)?\s+corner\b", value) else (
            -amount if re.search(r"\b(?:north|south)?west(?:ern)?\s+corner\b", value) else 0.0
        )
        north = amount if re.search(r"\bnorth(?:east|west|ern)?\s+corner\b", value) else (
            -amount if re.search(r"\bsouth(?:east|west|ern)?\s+corner\b", value) else 0.0
        )
    else:
        east = amount if re.search(r"\b(?:east side|east of|just east)\b", value) else (
            -amount if re.search(r"\b(?:west side|west of|just west)\b", value) else 0.0
        )
        north = amount if re.search(r"\b(?:north side|north of|just north)\b", value) else (
            -amount if re.search(r"\b(?:south side|south of|just south)\b", value) else 0.0
        )
    return east, north


def named_feature(
    text: str, features: dict[str, list[dict[str, Any]]]
) -> tuple[str, dict[str, Any]] | None:
    normalized = normalize(text)
    for alias, canonical in sorted(NAMED_ALIASES.items(), key=lambda item: -len(item[0])):
        if normalize(alias) in normalized and features.get(canonical):
            return canonical, features[canonical][0]
    tokens = set(normalized.split())
    candidates: list[tuple[int, int, str, dict[str, Any]]] = []
    for name, matches in features.items():
        name_tokens = {token for token in normalize(name).split() if len(token) >= 3 and token != "the"}
        if len(name_tokens) >= 2 and name_tokens.issubset(tokens):
            candidates.append((len(name_tokens), len(name), name, matches[0]))
    if not candidates:
        return None
    _, _, name, feature = max(candidates)
    return name, feature


def feature_anchor(text: str, feature: dict[str, Any]) -> tuple[float, float] | None:
    geometry = feature.get("_geometry") or []
    if not geometry:
        if feature.get("center"):
            return float(feature["center"]["lon"]), float(feature["center"]["lat"])
        if "lon" in feature and "lat" in feature:
            return float(feature["lon"]), float(feature["lat"])
        return None
    points = geometry[:-1] if len(geometry) > 2 and geometry[0] == geometry[-1] else geometry
    projected = [local_xy(point) for point in points]
    xs, ys = [p[0] for p in projected], [p[1] for p in projected]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    value = normalize(text)

    horizontal = 0.5
    vertical = 0.5
    west = bool(re.search(r"\b(?:west side|west wall|west section|western|northwest|southwest)\b", value))
    east = bool(re.search(r"\b(?:east side|east wall|east section|eastern|northeast|southeast)\b", value))
    south = bool(re.search(r"\b(?:south side|south wall|south section|southern|southwest|southeast)\b", value))
    north = bool(re.search(r"\b(?:north side|north wall|north section|northern|northwest|northeast)\b", value))
    if west:
        horizontal = 0.08 if "outside" not in value else -0.04
    elif east:
        horizontal = 0.92 if "outside" not in value else 1.04
    if south:
        vertical = 0.08 if "outside" not in value else -0.04
    elif north:
        vertical = 0.92 if "outside" not in value else 1.04

    # A section without a wall is less extreme than a corner/wall.
    if "section" in value and "wall" not in value and "corner" not in value:
        if west:
            horizontal = 0.25
        elif east:
            horizontal = 0.75
        if south:
            vertical = 0.25
        elif north:
            vertical = 0.75
    return local_lon_lat((
        min_x + horizontal * (max_x - min_x),
        min_y + vertical * (max_y - min_y),
    ))


def derive_written_candidate(
    location: str,
    old: tuple[float, float] | None,
    anchor_kind: str,
    roads: dict[str, list],
    features: dict[str, list[dict[str, Any]]],
) -> tuple[tuple[float, float] | None, str]:
    streets = street_mentions(location, roads)
    normalized = normalize(location)

    named = named_feature(location, features)
    prefer_named = (
        anchor_kind == "named_place_or_building"
        or not old
        or bool(re.search(r"\b(?:outside|inside|in)\b.*\b(?:building|market|bazaar|coliseum|center)\b", normalized))
    )
    if prefer_named and named:
        point = feature_anchor(location, named[1])
        if point:
            return point, f"written_named_place:{named[0]}"

    if (anchor_kind == "street_corner" or "corner" in normalized) and len(streets) >= 2:
        point = road_intersection(roads, streets[0], streets[1])
        if point:
            return offset(point, *directional_offset(location, corner=True)), "written_street_corner"

    if (anchor_kind == "street_segment" or "between" in normalized) and len(streets) >= 3:
        start = road_intersection(roads, streets[0], streets[1])
        end = road_intersection(roads, streets[0], streets[2])
        if start and end:
            point = point_segment_projection(old, start, end)
            return offset(point, *directional_offset(location)), "written_street_segment_projection"

    if streets and old:
        point = nearest_polyline_projection(old, roads.get(streets[0], []))
        if point:
            return offset(point, *directional_offset(location)), "written_street_corridor_projection"

    if named:
        point = feature_anchor(location, named[1])
        if point:
            return point, f"written_named_place:{named[0]}"
    return None, "unresolved"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="reviewed feed containing coordinates or withheld_coordinates")
    parser.add_argument("--publish-base", type=Path,
                        help="live feed whose non-location content and record order must be preserved")
    parser.add_argument("--verifications", type=Path, required=True)
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--osm", type=Path, required=True)
    parser.add_argument("--bundled-fallback", type=Path,
                        help="shipping bundle used only for explicitly configured fallback IDs")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--change-log", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()

    if args.source.resolve() == args.output.resolve():
        raise SystemExit("refusing to overwrite source feed")
    candidate_vendors = json.loads(args.source.read_text(encoding="utf-8"))
    vendors = (
        json.loads(args.publish_base.read_text(encoding="utf-8"))
        if args.publish_base
        else json.loads(args.source.read_text(encoding="utf-8"))
    )
    candidates_by_id = {str(row.get("id") or ""): row for row in candidate_vendors}
    published_ids = [str(row.get("id") or "") for row in vendors]
    if set(published_ids) != set(candidates_by_id) or len(published_ids) != len(candidates_by_id):
        raise SystemExit("publish base and reviewed source do not contain the same unique vendor IDs")
    original_public_coordinates = {
        str(row.get("id") or ""): parse_coordinate(row.get("coordinates"))
        for row in vendors
    }
    original_groups: dict[tuple[float, float], list[str]] = defaultdict(list)
    for vendor_id, point in original_public_coordinates.items():
        if point:
            original_groups[(round(point[0], 7), round(point[1], 7))].append(vendor_id)
    original_duplicate_sets = {
        frozenset(group) for group in original_groups.values() if len(group) > 1
    }
    ledger = json.loads(args.verifications.read_text(encoding="utf-8")).get("vendors") or {}
    with args.geometry.open(newline="", encoding="utf-8") as handle:
        geometry_rows = {row["id"]: row for row in csv.DictReader(handle)}
    osm = json.loads(args.osm.read_text(encoding="utf-8"))
    roads = build_roads(osm)
    features = build_named_features(osm)

    fallback_by_id: dict[str, dict[str, Any]] = {}
    if args.bundled_fallback:
        fallback_by_id = {
            str(row.get("id") or ""): row
            for row in json.loads(args.bundled_fallback.read_text(encoding="utf-8"))
        }
    # The current source has no point for the separate Mighty Midway Fresh
    # French Fries record. Its shipping-bundle point is inside Midway and the
    # public exact result belongs to the other Judson record, so this is the
    # only explicitly allowed bundled fallback.
    allowed_bundle_fallbacks = {"2340.1"}
    # Ball Park Cafe was manually corrected against Google's exact result on
    # the current fair day. Its street-centerline discrepancy is known and is
    # weaker than that booth-level corroboration.
    preserve_reviewed_geometry_conflicts = {"616.1"}

    changes: list[dict[str, Any]] = []
    method_counts: Counter[str] = Counter()
    primary_methods: dict[str, str] = {}
    for vendor in vendors:
        vendor_id = str(vendor.get("id") or "")
        if not vendor_id or vendor_id not in geometry_rows:
            raise SystemExit(f"missing id or geometry row: {vendor_id!r}")
        reviewed = candidates_by_id[vendor_id]
        geometry = geometry_rows[vendor_id]
        ledger_entry = ledger.get(vendor_id) or {}
        ledger_status = str(ledger_entry.get("status") or "")
        ledger_point = parse_coordinate(ledger_entry.get("coordinates"))
        old = (
            ledger_point
            if ledger_status in {"verified", "approximate"} and ledger_point
            else parse_coordinate(reviewed.get("coordinates") or reviewed.get("withheld_coordinates"))
        )
        location_check = str(geometry.get("location_check") or "")
        anchor_kind = str(geometry.get("anchor_kind") or "")

        point = old
        method = "reviewed_evidence" if ledger_status in {"verified", "approximate"} else "existing_within_30m"
        if vendor_id in allowed_bundle_fallbacks:
            point = parse_coordinate((fallback_by_id.get(vendor_id) or {}).get("coordinates"))
            method = "shipping_bundle_zone_fallback"
        should_derive = (
            vendor_id not in allowed_bundle_fallbacks
            and ledger_status != "verified"
            and not (
                ledger_status == "approximate"
                and location_check != "reject_over_30m"
            )
            and vendor_id not in preserve_reviewed_geometry_conflicts
            and (old is None or location_check == "reject_over_30m")
        )
        if should_derive:
            source_hint = old or parse_coordinate(reviewed.get("quarantined_coordinates"))
            point, method = derive_written_candidate(
                str(reviewed.get("booth_location") or reviewed.get("directions") or ""),
                source_hint,
                anchor_kind,
                roads,
                features,
            )

        if point is None and vendor_id in allowed_bundle_fallbacks:
            point = parse_coordinate((fallback_by_id.get(vendor_id) or {}).get("coordinates"))
            method = "shipping_bundle_zone_fallback"
        if point is None:
            raise SystemExit(f"{vendor_id}: unable to construct a complete pin")
        if not in_fair_bounds(point):
            raise SystemExit(f"{vendor_id}: candidate outside fair bounds: {point}")

        previous_public = parse_coordinate(vendor.get("coordinates"))
        if previous_public != point:
            vendor["coordinates"] = [
                f"{point[0]:.10f}".rstrip("0").rstrip("."),
                f"{point[1]:.10f}".rstrip("0").rstrip("."),
            ]
        vendor.pop("withheld_coordinates", None)
        vendor.pop("withheld_reason", None)
        vendor.pop("quarantined_coordinates", None)
        vendor.pop("quarantine_reason", None)
        if ledger_status == "verified":
            vendor["coordinate_status"] = "verified"
            vendor["compass_eligible"] = True
        else:
            vendor["coordinate_status"] = "approximate"
            vendor["compass_eligible"] = False
        method_counts[method] += 1
        primary_methods[vendor_id] = method
        if previous_public != point:
            changes.append({
                "id": vendor_id,
                "name": vendor.get("name") or "",
                "booth_location": vendor.get("booth_location") or "",
                "old_coordinates": list(previous_public) if previous_public else None,
                "new_coordinates": list(point),
                "displacement_m": round(distance(previous_public, point), 1) if previous_public else None,
                "method": method,
                "previous_location_check": location_check,
                "anchor_kind": anchor_kind,
            })

    # The source scrape assigned many vendors the exact same point even when
    # their descriptions only say they share a wall, corner, or broad street
    # segment. Separate newly-created overlaps by 4 m so every map annotation
    # can be selected, while preserving exact duplicates already present in the
    # live feed (which may represent deliberately shared booths/operators).
    final_groups: dict[tuple[float, float], list[dict[str, Any]]] = defaultdict(list)
    for vendor in vendors:
        point = parse_coordinate(vendor.get("coordinates"))
        if point:
            final_groups[(round(point[0], 7), round(point[1], 7))].append(vendor)
    change_by_id = {str(change["id"]): change for change in changes}
    deconflicted_groups = 0
    deconflicted_pins = 0
    for group in final_groups.values():
        if len(group) < 2:
            continue
        group_ids = frozenset(str(vendor.get("id") or "") for vendor in group)
        if group_ids in original_duplicate_sets:
            continue
        deconflicted_groups += 1
        ordered = sorted(group, key=lambda vendor: str(vendor.get("id") or ""))
        base = parse_coordinate(ordered[0].get("coordinates"))
        if not base:
            raise SystemExit("unexpected blank point during overlap separation")
        for index, vendor in enumerate(ordered):
            angle = 2 * math.pi * index / len(ordered)
            point = offset(base, 4.0 * math.cos(angle), 4.0 * math.sin(angle))
            if not in_fair_bounds(point):
                point = offset(base, 2.0 * math.cos(angle), 2.0 * math.sin(angle))
            vendor_id = str(vendor.get("id") or "")
            vendor["coordinates"] = [
                f"{point[0]:.10f}".rstrip("0").rstrip("."),
                f"{point[1]:.10f}".rstrip("0").rstrip("."),
            ]
            previous_public = original_public_coordinates[vendor_id]
            change = change_by_id.get(vendor_id)
            if not change:
                change = {
                    "id": vendor_id,
                    "name": vendor.get("name") or "",
                    "booth_location": vendor.get("booth_location") or "",
                    "old_coordinates": list(previous_public) if previous_public else None,
                    "previous_location_check": geometry_rows[vendor_id].get("location_check") or "",
                    "anchor_kind": geometry_rows[vendor_id].get("anchor_kind") or "",
                }
                changes.append(change)
                change_by_id[vendor_id] = change
            change["new_coordinates"] = list(point)
            change["displacement_m"] = (
                round(distance(previous_public, point), 1) if previous_public else None
            )
            change["method"] = primary_methods[vendor_id] + "+stable_4m_separation"
            deconflicted_pins += 1

    ids = [str(vendor.get("id") or "") for vendor in vendors]
    nonnull = sum(parse_coordinate(vendor.get("coordinates")) is not None for vendor in vendors)
    if len(vendors) != 278 or len(set(ids)) != 278 or nonnull != 278:
        raise SystemExit(f"completion gate failed: records={len(vendors)} unique={len(set(ids))} pins={nonnull}")

    summary = {
        "record_count": len(vendors),
        "unique_id_count": len(set(ids)),
        "published_pin_count": nonnull,
        "verified_pin_count": sum(vendor.get("coordinate_status") == "verified" for vendor in vendors),
        "approximate_pin_count": sum(vendor.get("coordinate_status") == "approximate" for vendor in vendors),
        "changed_or_filled_count": len(changes),
        "deconflicted_overlap_group_count": deconflicted_groups,
        "deconflicted_pin_count": deconflicted_pins,
        "method_counts": dict(method_counts),
        "outside_fair_count": 0,
        "shipping_client_warning": "Every non-null coordinate is compass-enabled by the current App Store binary, regardless of audit status fields.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(vendors, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.change_log.write_text(json.dumps(changes, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
