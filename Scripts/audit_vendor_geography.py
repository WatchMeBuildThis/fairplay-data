#!/usr/bin/env python3
"""Build a fail-closed geography audit for the FairPlay vendor feed.

This script deliberately distinguishes a coordinate that is syntactically valid
from one that has been independently verified.  It never changes vendors.json.
Instead, it produces a machine-readable audit and a human review queue.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


FAIR_BOUNDS = (-93.19, -93.15, 44.96, 45.00)
EARTH_RADIUS_M = 6_371_000.0
DEFAULT_VERIFIED_TOLERANCE_M = 25.0
CORRIDOR_HALF_WIDTH_M = 30.0
CORRIDOR_CONFLICT_M = 60.0

# The fairground grid is close enough to east/west avenues and north/south
# streets for a conservative perpendicular-distance screen.  The centerlines
# are learned from the feed's densest band; they are never used to move a pin.
ROAD_AXES = {
    "west dan patch": "lat",
    "dan patch": "lat",
    "carnes": "lat",
    "judson": "lat",
    "murphy": "lat",
    "lee": "lat",
    "randall": "lat",
    "wright": "lat",
    "liggett": "lon",
    "chambers": "lon",
    "nelson": "lon",
    "underwood": "lon",
    "cooper": "lon",
    "clough": "lon",
    "cosgrove": "lon",
}


def normalize(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(str(value or "")))
    text = text.lower().replace("&", " and ")
    text = re.sub(r"\bavenues?\b", "ave", text)
    text = re.sub(r"\bstreets?\b", "st", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def canonical_location(value: Any) -> str:
    """Normalize harmless wording variants without erasing geographic detail."""
    text = normalize(value)
    return re.sub(r"\b(at|in|inside|outside|near|by|on) the\b", r"\1", text)


def parse_coordinate(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    try:
        lon, lat = map(float, value)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lon) and math.isfinite(lat)):
        return None
    return lon, lat


def candidate_coordinate(record: dict[str, Any]) -> tuple[float, float] | None:
    """Coordinate used for review, whether published or deliberately withheld."""
    return parse_coordinate(record.get("coordinates")) or parse_coordinate(
        record.get("withheld_coordinates")
    )


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    dlon, dlat = lon2 - lon1, lat2 - lat1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def load_json(path: Path | None, default: Any) -> Any:
    if path is None or not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def in_fair_bounds(coord: tuple[float, float]) -> bool:
    min_lon, max_lon, min_lat, max_lat = FAIR_BOUNDS
    lon, lat = coord
    return min_lon < lon < max_lon and min_lat < lat < max_lat


@dataclass(frozen=True)
class Issue:
    code: str
    severity: str
    detail: str
    distance_m: float | None = None


SEVERITY_WEIGHT = {"critical": 100, "high": 50, "medium": 20, "low": 5}


def issue_dict(issue: Issue) -> dict[str, Any]:
    result: dict[str, Any] = {
        "code": issue.code,
        "severity": issue.severity,
        "detail": issue.detail,
    }
    if issue.distance_m is not None:
        result["distance_m"] = round(issue.distance_m, 1)
    return result


def verification_groups(sources: Iterable[dict[str, Any]]) -> set[str]:
    return {
        str(source.get("publisher_group") or "").strip()
        for source in sources
        if str(source.get("publisher_group") or "").strip()
    }


def directions_conflict(a: dict[str, Any], b: dict[str, Any]) -> bool:
    a_loc = canonical_location(a.get("booth_location") or a.get("directions"))
    b_loc = canonical_location(b.get("booth_location") or b.get("directions"))
    if not a_loc or not b_loc:
        return False
    return a_loc != b_loc


def road_mentions(location: str) -> list[str]:
    text = normalize(location)
    mentions = []
    for road in ROAD_AXES:
        candidate = text
        if road == "dan patch":
            candidate = candidate.replace("west dan patch", "")
        if re.search(rf"\b{re.escape(road)}\b", candidate):
            mentions.append(road)
    return mentions


def primary_roads(location: str) -> list[str]:
    text = normalize(location)
    mentions = road_mentions(text)
    if "corner" in text:
        return mentions[:2]
    side_match = re.search(r"\b(?:north|south|east|west) side of (.+?)(?: between| at| outside|$)", text)
    if side_match:
        segment = side_match.group(1)
        return [road for road in mentions if re.search(rf"\b{re.escape(road)}\b", segment)][:1]
    if len(mentions) == 2 and (" at " in f" {text} " or " and " in f" {text} "):
        return mentions
    return []


def axis_meters(axis: str) -> float:
    return 111_000.0 if axis == "lat" else 111_000.0 * math.cos(math.radians(44.98))


def build_road_models(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    samples: dict[str, list[float]] = defaultdict(list)
    for record in records:
        coord = candidate_coordinate(record)
        if not coord:
            continue
        lon, lat = coord
        for road in road_mentions(record.get("booth_location") or record.get("directions") or ""):
            samples[road].append(lat if ROAD_AXES[road] == "lat" else lon)

    models: dict[str, dict[str, Any]] = {}
    for road, values in samples.items():
        axis = ROAD_AXES[road]
        meter_scale = axis_meters(axis)
        best: list[float] = []
        for center in values:
            band = [value for value in values if abs(value - center) * meter_scale <= CORRIDOR_HALF_WIDTH_M]
            if len(band) > len(best):
                best = band
        sample_count = len(values)
        inlier_ratio = len(best) / sample_count if sample_count else 0.0
        reliable = sample_count >= 8 and len(best) >= 4 and inlier_ratio >= 0.25
        models[road] = {
            "axis": axis,
            "center": sum(best) / len(best) if best else None,
            "sample_count": sample_count,
            "inlier_count": len(best),
            "inlier_ratio": round(inlier_ratio, 3),
            "reliable_for_screening": reliable,
        }
    return models


def street_corridor_issues(record: dict[str, Any], models: dict[str, dict[str, Any]]) -> list[Issue]:
    coord = candidate_coordinate(record)
    if not coord:
        return []
    lon, lat = coord
    issues = []
    for road in primary_roads(record.get("booth_location") or record.get("directions") or ""):
        model = models.get(road) or {}
        if not model.get("reliable_for_screening"):
            continue
        value = lat if model["axis"] == "lat" else lon
        distance = abs(value - float(model["center"])) * axis_meters(model["axis"])
        if distance > CORRIDOR_CONFLICT_M:
            issues.append(
                Issue(
                    "written_street_corridor_conflict",
                    "medium",
                    f"Heuristic: pin is {distance:.1f} m perpendicular to the feed-learned {road.title()} corridor; manual review required",
                    distance,
                )
            )
    return issues


def duplicate_coordinate_issues(records: list[dict[str, Any]]) -> dict[str, list[Issue]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        coord = candidate_coordinate(record)
        if coord:
            groups[(f"{coord[0]:.7f}", f"{coord[1]:.7f}")].append(record)

    result: dict[str, list[Issue]] = defaultdict(list)
    for group in groups.values():
        if len(group) < 2:
            continue
        locations = {canonical_location(x.get("booth_location") or x.get("directions")) for x in group}
        locations.discard("")
        if len(locations) > 1:
            ids = sorted(str(x.get("id")) for x in group)
            detail = f"Exact coordinate is shared by vendors with different written locations: {', '.join(ids)}"
            for record in group:
                result[str(record.get("id"))].append(
                    Issue("duplicate_coordinate_location_conflict", "high", detail)
                )
    return result


def exact_location_issues(records: list[dict[str, Any]]) -> dict[str, list[Issue]]:
    """Flag only tight location descriptions, not long street segments or large venues."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        location = canonical_location(record.get("booth_location") or record.get("directions"))
        if location:
            groups[location].append(record)

    result: dict[str, list[Issue]] = defaultdict(list)
    for location, group in groups.items():
        coords = [(record, candidate_coordinate(record)) for record in group]
        coords = [(record, coord) for record, coord in coords if coord]
        if len(coords) < 2:
            continue
        is_tight = "corner" in location or "next to" in location or "outside" in location
        if not is_tight:
            continue
        for record, coord in coords:
            nearest = min(
                (haversine_m(coord, other_coord) for other, other_coord in coords if other is not record),
                default=0.0,
            )
            if nearest > 55.0:
                result[str(record.get("id"))].append(
                    Issue(
                        "same_written_location_spread",
                        "high",
                        f"No peer with the same tight written location is within 55 m (nearest {nearest:.1f} m)",
                        nearest,
                    )
                )
    return result


def build_audit(
    records: list[dict[str, Any]],
    baseline_records: list[dict[str, Any]],
    verification_config: dict[str, Any],
) -> dict[str, Any]:
    baseline = {str(record.get("id")): record for record in baseline_records}
    verifications = verification_config.get("vendors", {})
    ids = [str(record.get("id")) for record in records]
    duplicate_ids = {vendor_id for vendor_id, count in Counter(ids).items() if count > 1}
    duplicate_issues = duplicate_coordinate_issues(records)
    location_issues = exact_location_issues(records)
    road_models = build_road_models(records)

    rows: list[dict[str, Any]] = []
    for record in records:
        vendor_id = str(record.get("id"))
        coord_value = record.get("coordinates")
        coord = parse_coordinate(coord_value)
        withheld_value = record.get("withheld_coordinates")
        withheld_coord = parse_coordinate(withheld_value)
        review_coord = coord or withheld_coord
        issues: list[Issue] = []

        if vendor_id in duplicate_ids:
            issues.append(Issue("duplicate_vendor_id", "critical", "Vendor id occurs more than once"))
        if coord_value is None and withheld_value is not None:
            if withheld_coord is None:
                issues.append(Issue(
                    "malformed_withheld_coordinate",
                    "critical",
                    "Withheld candidate is not a finite [longitude, latitude] pair",
                ))
            elif not in_fair_bounds(withheld_coord):
                issues.append(Issue(
                    "withheld_coordinate_outside_fair_bounds",
                    "critical",
                    "Withheld candidate is outside the configured fairgrounds envelope",
                ))
            else:
                issues.append(Issue(
                    "coordinate_withheld",
                    "low",
                    "Candidate is preserved for review but is not published to the app map",
                ))
        elif coord_value is None:
            issues.append(Issue("missing_coordinate", "critical", "No coordinate is published"))
        elif coord is None:
            issues.append(Issue("malformed_coordinate", "critical", "Coordinate is not a finite [longitude, latitude] pair"))
        elif not in_fair_bounds(coord):
            issues.append(Issue("outside_fair_bounds", "critical", "Coordinate is outside the configured fairgrounds envelope"))

        popup = record.get("popupHtml") or ""
        popup_norm = normalize(popup)
        name_norm = normalize(record.get("name"))
        location_norm = normalize(record.get("booth_location") or record.get("directions"))
        if popup and ((name_norm and name_norm not in popup_norm) or (location_norm and location_norm not in popup_norm)):
            issues.append(Issue("popup_record_mismatch", "high", "Map popup does not match this record's name and location"))

        issues.extend(duplicate_issues.get(vendor_id, []))
        issues.extend(location_issues.get(vendor_id, []))
        issues.extend(street_corridor_issues(record, road_models))

        baseline_distance = None
        old_coord = parse_coordinate(baseline.get(vendor_id, {}).get("coordinates"))
        if review_coord and old_coord:
            baseline_distance = haversine_m(review_coord, old_coord)
            if baseline_distance > 40.0:
                issues.append(
                    Issue(
                        "large_change_from_baseline",
                        "medium",
                        f"Coordinate moved {baseline_distance:.1f} m from the pre-fix snapshot; review evidence",
                        baseline_distance,
                    )
                )

        verification = verifications.get(vendor_id)
        status = "unverified"
        confidence = "none"
        evidence_groups: set[str] = set()
        verification_distance = None
        if verification:
            target = parse_coordinate(verification.get("coordinates"))
            sources = verification.get("sources") or []
            evidence_groups = verification_groups(sources)
            claimed_status = str(verification.get("status") or "unverified")
            tolerance = float(verification.get("tolerance_m") or DEFAULT_VERIFIED_TOLERANCE_M)
            if review_coord and target:
                verification_distance = haversine_m(review_coord, target)
            if claimed_status == "verified":
                if len(evidence_groups) < 2:
                    issues.append(Issue("insufficient_independent_evidence", "high", "Verified status requires at least two publisher groups"))
                elif verification_distance is None or verification_distance > tolerance:
                    issues.append(
                        Issue(
                            "verified_coordinate_conflict",
                            "critical",
                            f"Feed coordinate does not match verified coordinate within {tolerance:.0f} m",
                            verification_distance,
                        )
                    )
                else:
                    status = "verified"
                    confidence = str(verification.get("confidence") or "high")
                    issues = [
                        issue
                        for issue in issues
                        if issue.code != "same_written_location_spread"
                    ]
            elif claimed_status == "approximate" and coord and target and verification_distance <= tolerance:
                status = "approximate"
                confidence = str(verification.get("confidence") or "medium")

        if coord is None:
            status = "withheld" if withheld_coord else "missing"
            confidence = "none"
        if any(issue.severity == "critical" for issue in issues) and status != "missing":
            status = "conflict"
            confidence = "none"

        compass_eligible = status == "verified" and not any(
            issue.severity in {"critical", "high"} for issue in issues
        )
        if not verification:
            issues.append(Issue("no_independent_verification", "low", "No curated independent coordinate evidence is recorded"))

        risk_score = min(100, sum(SEVERITY_WEIGHT[issue.severity] for issue in issues))
        priority = "critical" if risk_score >= 100 else "high" if risk_score >= 50 else "medium" if risk_score >= 20 else "low"
        row = {
            "id": vendor_id,
            "name": record.get("name") or "",
            "booth_location": record.get("booth_location") or record.get("directions") or "",
            "coordinates": list(coord) if coord else None,
            "map_ref": record.get("map_ref"),
            "coordinate_status": status,
            "confidence": confidence,
            "compass_eligible": compass_eligible,
            "evidence_publisher_groups": sorted(evidence_groups),
            "baseline_change_m": round(baseline_distance, 1) if baseline_distance is not None else None,
            "verification_distance_m": round(verification_distance, 1) if verification_distance is not None else None,
            "risk_score": risk_score,
            "review_priority": priority,
            "issues": [issue_dict(issue) for issue in issues],
        }
        if withheld_coord:
            row["withheld_coordinates"] = list(withheld_coord)
        rows.append(row)

    rows.sort(key=lambda row: (-row["risk_score"], row["name"].lower(), row["id"]))
    status_counts = Counter(row["coordinate_status"] for row in rows)
    priority_counts = Counter(row["review_priority"] for row in rows)
    issue_counts = Counter(issue["code"] for row in rows for issue in row["issues"])
    summary = {
        "record_count": len(records),
        "expected_record_count": verification_config.get("expected_record_count"),
        "record_count_matches": verification_config.get("expected_record_count") in (None, len(records)),
        "unique_id_count": len(set(ids)),
        "coordinate_status_counts": dict(sorted(status_counts.items())),
        "compass_eligible_count": sum(bool(row["compass_eligible"]) for row in rows),
        "review_priority_counts": dict(sorted(priority_counts.items())),
        "issue_counts": dict(sorted(issue_counts.items())),
        "policy": {
            "compass_requires": "coordinate_status=verified, >=2 publisher groups, and no high/critical issue",
            "official_site_independence": "Directions, GeoJSON, mapRef, and official map count as one publisher group",
            "audit_script_mutates_feed": False,
            "status_fields_published": all(
                "coordinate_status" in record and "compass_eligible" in record
                for record in records
            ),
        },
        "road_models": road_models,
    }
    return {"schema_version": 1, "summary": summary, "vendors": rows}


def integrity_failures(report: dict[str, Any], config: dict[str, Any]) -> list[tuple[str, str]]:
    failures: list[tuple[str, str]] = []
    if not report["summary"].get("record_count_matches", True):
        failures.append(("feed", "record_count_mismatch"))
    known_missing = {str(value) for value in config.get("known_missing_coordinate_ids", [])}
    known_missing.update(str(value) for value in config.get("quarantined_coordinate_ids", []))
    always_fatal = {
        "duplicate_vendor_id",
        "malformed_coordinate",
        "outside_fair_bounds",
        "malformed_withheld_coordinate",
        "withheld_coordinate_outside_fair_bounds",
        "popup_record_mismatch",
    }
    for row in report["vendors"]:
        for issue in row["issues"]:
            if issue["code"] in always_fatal:
                failures.append((row["id"], issue["code"]))
            elif issue["code"] == "missing_coordinate" and row["id"] not in known_missing:
                failures.append((row["id"], issue["code"]))
    return failures


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "review_priority", "risk_score", "id", "name", "coordinate_status", "compass_eligible",
        "longitude", "latitude", "booth_location", "map_ref", "baseline_change_m",
        "verification_distance_m", "issue_codes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            coord = row.get("coordinates") or row.get("withheld_coordinates") or [None, None]
            writer.writerow({
                "review_priority": row["review_priority"],
                "risk_score": row["risk_score"],
                "id": row["id"],
                "name": row["name"],
                "coordinate_status": row["coordinate_status"],
                "compass_eligible": str(bool(row["compass_eligible"])).lower(),
                "longitude": coord[0],
                "latitude": coord[1],
                "booth_location": row["booth_location"],
                "map_ref": row.get("map_ref") or "",
                "baseline_change_m": row.get("baseline_change_m"),
                "verification_distance_m": row.get("verification_distance_m"),
                "issue_codes": "|".join(issue["code"] for issue in row["issues"]),
            })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vendors", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--verifications", type=Path, default=Path("location_verifications.json"))
    parser.add_argument("--json-output", type=Path, default=Path("audit/vendor-location-audit.json"))
    parser.add_argument("--csv-output", type=Path, default=Path("audit/vendor-location-review.csv"))
    parser.add_argument("--strict-integrity", action="store_true", help="Fail only on structural critical issues, not merely unverified rows")
    args = parser.parse_args()

    records = load_json(args.vendors, [])
    baseline = load_json(args.baseline, [])
    config = load_json(args.verifications, {"vendors": {}})
    if not isinstance(records, list):
        raise SystemExit("vendors input must contain a JSON array")

    report = build_audit(records, baseline, config)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_csv(args.csv_output, report["vendors"])
    print(json.dumps(report["summary"], indent=2))

    if args.strict_integrity:
        if integrity_failures(report, config):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
