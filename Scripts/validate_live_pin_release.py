#!/usr/bin/env python3
"""Validate a vendors.json candidate against the currently published feed.

This is the final data-only release gate for the shipping FairPlay client. It
proves that vendor/menu/photo content and record order did not change, that all
coordinates match the app's [longitude, latitude] decoder contract, and that no
new exact pin overlap was introduced.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
from typing import Any


FAIR_BOUNDS = {
    "min_lon": -93.1835,
    "max_lon": -93.1630,
    "min_lat": 44.9750,
    "max_lat": 44.9900,
}
LOCATION_FIELDS = {
    "coordinates",
    "coordinate_status",
    "compass_eligible",
    "withheld_coordinates",
    "withheld_reason",
    "quarantined_coordinates",
    "quarantine_reason",
}
EARTH_RADIUS_M = 6_371_000.0


def parse_coordinate(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    try:
        point = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(component) for component in point):
        return None
    return point


def in_fair_bounds(point: tuple[float, float]) -> bool:
    longitude, latitude = point
    return (
        FAIR_BOUNDS["min_lon"] <= longitude <= FAIR_BOUNDS["max_lon"]
        and FAIR_BOUNDS["min_lat"] <= latitude <= FAIR_BOUNDS["max_lat"]
    )


def distance(left: tuple[float, float], right: tuple[float, float]) -> float:
    lon1, lat1 = map(math.radians, left)
    lon2, lat2 = map(math.radians, right)
    dlon, dlat = lon2 - lon1, lat2 - lat1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(value))


def content_without_location(vendor: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in vendor.items() if key not in LOCATION_FIELDS}


def duplicate_groups(vendors: list[dict[str, Any]]) -> set[frozenset[str]]:
    groups: dict[tuple[float, float], list[str]] = defaultdict(list)
    for vendor in vendors:
        point = parse_coordinate(vendor.get("coordinates"))
        if point:
            groups[(round(point[0], 7), round(point[1], 7))].append(str(vendor.get("id") or ""))
    return {frozenset(ids) for ids in groups.values() if len(ids) > 1}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--change-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    live = json.loads(args.live.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    changes = json.loads(args.change_log.read_text(encoding="utf-8"))
    errors: list[str] = []
    if not isinstance(live, list) or not isinstance(candidate, list):
        raise SystemExit("live and candidate feeds must both be JSON arrays")

    live_ids = [str(vendor.get("id") or "") for vendor in live]
    candidate_ids = [str(vendor.get("id") or "") for vendor in candidate]
    if len(candidate) != 278:
        errors.append(f"candidate record count is {len(candidate)}, expected 278")
    if len(set(candidate_ids)) != len(candidate_ids):
        errors.append("candidate contains duplicate vendor IDs")
    if candidate_ids != live_ids:
        errors.append("candidate vendor IDs or record order differ from live feed")

    content_mismatch_ids: list[str] = []
    invalid_coordinate_ids: list[str] = []
    outside_fair_ids: list[str] = []
    incompatible_coordinate_value_ids: list[str] = []
    invalid_status_ids: list[str] = []
    status_counts: Counter[str] = Counter()
    candidate_by_id = {str(vendor.get("id") or ""): vendor for vendor in candidate}
    live_by_id = {str(vendor.get("id") or ""): vendor for vendor in live}

    for vendor_id in candidate_ids:
        vendor = candidate_by_id[vendor_id]
        original = live_by_id.get(vendor_id)
        if original is None:
            continue
        if content_without_location(vendor) != content_without_location(original):
            content_mismatch_ids.append(vendor_id)
        point = parse_coordinate(vendor.get("coordinates"))
        if point is None:
            invalid_coordinate_ids.append(vendor_id)
        else:
            if not in_fair_bounds(point):
                outside_fair_ids.append(vendor_id)
            if not all(isinstance(value, (str, int, float)) and not isinstance(value, bool)
                       for value in vendor.get("coordinates", [])):
                incompatible_coordinate_value_ids.append(vendor_id)
        status = str(vendor.get("coordinate_status") or "")
        status_counts[status] += 1
        if status not in {"verified", "approximate"} or not isinstance(vendor.get("compass_eligible"), bool):
            invalid_status_ids.append(vendor_id)

    if content_mismatch_ids:
        errors.append(f"non-location content changed for {len(content_mismatch_ids)} vendors")
    if invalid_coordinate_ids:
        errors.append(f"invalid or blank coordinates for {len(invalid_coordinate_ids)} vendors")
    if outside_fair_ids:
        errors.append(f"coordinates outside fair bounds for {len(outside_fair_ids)} vendors")
    if incompatible_coordinate_value_ids:
        errors.append(
            "coordinates do not use shipping-compatible string/number values for "
            f"{len(incompatible_coordinate_value_ids)} vendors"
        )
    if invalid_status_ids:
        errors.append(f"invalid audit metadata for {len(invalid_status_ids)} vendors")

    live_duplicates = duplicate_groups(live)
    candidate_duplicates = duplicate_groups(candidate)
    new_duplicate_groups = candidate_duplicates - live_duplicates
    if new_duplicate_groups:
        errors.append(f"candidate introduces {len(new_duplicate_groups)} new exact-overlap groups")

    actual_changed_ids: list[str] = []
    filled_ids: list[str] = []
    displacement_values: list[float] = []
    displacement_buckets: Counter[str] = Counter()
    for vendor_id in candidate_ids:
        old = parse_coordinate(live_by_id[vendor_id].get("coordinates"))
        new = parse_coordinate(candidate_by_id[vendor_id].get("coordinates"))
        if old == new:
            continue
        actual_changed_ids.append(vendor_id)
        if old is None:
            filled_ids.append(vendor_id)
            displacement_buckets["filled_blank"] += 1
            continue
        if new is None:
            continue
        meters = distance(old, new)
        displacement_values.append(meters)
        if meters <= 15:
            displacement_buckets["moved_0_to_15m"] += 1
        elif meters <= 30:
            displacement_buckets["moved_15_to_30m"] += 1
        elif meters <= 100:
            displacement_buckets["moved_30_to_100m"] += 1
        else:
            displacement_buckets["moved_over_100m"] += 1

    change_ids = [str(change.get("id") or "") for change in changes]
    if len(change_ids) != len(set(change_ids)):
        errors.append("change log contains duplicate vendor IDs")
    if set(change_ids) != set(actual_changed_ids):
        errors.append("change log does not exactly match coordinate differences from live")

    summary = {
        "release_gate": "pass" if not errors else "fail",
        "errors": errors,
        "live_record_count": len(live),
        "candidate_record_count": len(candidate),
        "unique_candidate_id_count": len(set(candidate_ids)),
        "shipping_app_decodable_pin_count": len(candidate) - len(invalid_coordinate_ids),
        "inside_fair_pin_count": len(candidate) - len(invalid_coordinate_ids) - len(outside_fair_ids),
        "non_location_content_preserved": not content_mismatch_ids,
        "record_order_preserved": candidate_ids == live_ids,
        "coordinate_status_counts": dict(status_counts),
        "coordinate_change_count": len(actual_changed_ids),
        "previously_blank_filled_count": len(filled_ids),
        "displacement_buckets": dict(displacement_buckets),
        "maximum_nonblank_displacement_m": round(max(displacement_values), 1) if displacement_values else 0,
        "live_exact_overlap_group_count": len(live_duplicates),
        "candidate_exact_overlap_group_count": len(candidate_duplicates),
        "new_exact_overlap_group_count": len(new_duplicate_groups),
        "content_mismatch_ids": content_mismatch_ids,
        "invalid_coordinate_ids": invalid_coordinate_ids,
        "outside_fair_ids": outside_fair_ids,
        "new_exact_overlap_groups": [sorted(group) for group in sorted(new_duplicate_groups, key=lambda group: sorted(group))],
        "current_app_behavior_warning": (
            "The shipping app uses all 278 non-null coordinates for map pins, compass targets, "
            "distance, and Apple Maps directions; it ignores compass_eligible."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
