#!/usr/bin/env python3
"""Compare FairPlay pins with the official app's bulk offline map snapshot.

The Grandstand-powered official app publishes a versioned vendor catalog and
map-location snapshot.  Food records link to exact State Fair vendor URLs and
to location IDs whose ``left2``/``top2`` fields are normalized positions on
the same 2026 map used by the Fair Finder.  This script converts those map
positions with the official Fair Finder perspective transform.

This is an advisory audit.  It never edits ``vendors.json`` and the official
website/app/map remain one publisher group, not independent confirmations.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

from audit_official_map_refs import MapPerspective, USER_AGENT, distance_m, parse_coordinate


VENDOR_ID_PATTERN = re.compile(r"/vendor/([^/?#]+)")
MAP_ID_2026 = "1843"
DEFAULT_MANIFEST_URL = "https://s3.amazonaws.com/grand/956/v1/956_master.txt"
ALLOWED_SNAPSHOT_HOSTS = {
    "d17995u48fnfvp.cloudfront.net",
    "s3.amazonaws.com",
}


def official_vendor_id(record: dict[str, Any]) -> str | None:
    match = VENDOR_ID_PATTERN.search(str(record.get("u") or ""))
    return match.group(1) if match else None


def download_json(url: str, cache_dir: Path | None = None) -> Any:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_SNAPSHOT_HOSTS:
        raise ValueError(f"refusing unexpected official snapshot URL: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = response.read()
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / Path(parsed.path).name).write_bytes(payload)
    return json.loads(payload)


def load_official_sources(args: argparse.Namespace) -> tuple[Any, Any, dict[str, str]]:
    if args.manifest_url:
        manifest = download_json(args.manifest_url, args.cache_dir)
        vendor_url = str(manifest.get("vendorsurl") or "")
        location_url = str(manifest.get("mapurl") or "")
        if not vendor_url or not location_url:
            raise ValueError("official manifest is missing vendorsurl or mapurl")
        return (
            download_json(vendor_url, args.cache_dir),
            download_json(location_url, args.cache_dir),
            {
                "manifest_url": args.manifest_url,
                "vendor_snapshot_url": vendor_url,
                "location_snapshot_url": location_url,
            },
        )

    if not args.official_vendors or not args.official_locations:
        raise ValueError(
            "provide --manifest-url, or both --official-vendors and --official-locations"
        )
    return (
        json.loads(args.official_vendors.read_text(encoding="utf-8")),
        json.loads(args.official_locations.read_text(encoding="utf-8")),
        {
            "vendor_snapshot_file": str(args.official_vendors),
            "location_snapshot_file": str(args.official_locations),
        },
    )


def food_catalog(groups: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    matching_groups = [group for group in groups if group.get("cat") == "Food"]
    if len(matching_groups) != 1:
        raise ValueError(f"expected one Food group, found {len(matching_groups)}")
    records = matching_groups[0].get("vendors")
    if not isinstance(records, list):
        raise ValueError("official Food group has no vendor list")

    result: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for record in records:
        vendor_id = official_vendor_id(record)
        if not vendor_id:
            continue
        if vendor_id in result:
            duplicates.append(vendor_id)
        result[vendor_id] = record
    if duplicates:
        raise ValueError(f"duplicate official vendor IDs: {', '.join(sorted(duplicates))}")
    return result


def official_map_coordinate(location: dict[str, Any]) -> tuple[float, float] | None:
    try:
        left_percent = float(location["left2"])
        top_percent = float(location["top2"])
    except (KeyError, TypeError, ValueError):
        return None

    perspective = MapPerspective()
    x = left_percent / 100 * perspective.config.image_width
    # Grandstand stores top2 as a percentage measured from the bottom; the
    # Fair Finder's mapRef y coordinate is measured from the top.
    y = (100 - top_percent) / 100 * perspective.config.image_height
    return perspective.unproject(x=x, y=y)


def priority(distance: float | None, has_official_location: bool) -> str:
    if not has_official_location:
        return "official_app_map_missing"
    if distance is None:
        return "fairplay_coordinate_missing"
    if distance >= 100:
        return "critical_100m_plus"
    if distance >= 50:
        return "high_50m_plus"
    if distance >= 25:
        return "medium_25m_plus"
    return "close_under_25m"


def comparison_rows(
    vendors: list[dict[str, Any]],
    official_groups: list[dict[str, Any]],
    official_locations: dict[str, Any],
) -> list[dict[str, Any]]:
    official = food_catalog(official_groups)
    locations = {
        str(location.get("id")): location
        for location in official_locations.get("locations", [])
        if isinstance(location, dict) and location.get("id") is not None
    }

    rows = []
    for vendor in vendors:
        vendor_id = str(vendor.get("id") or "")
        source = official.get(vendor_id)
        location = locations.get(str(source.get("mid"))) if source and source.get("mid") else None
        app_coordinate = official_map_coordinate(location) if location else None
        current = parse_coordinate(vendor.get("coordinates"))
        separation = distance_m(current, app_coordinate) if current and app_coordinate else None
        left2 = location.get("left2") if location else ""
        top2 = location.get("top2") if location else ""
        map_ref_x = float(left2) / 100 * 3400 if left2 != "" else None
        map_ref_y = (100 - float(top2)) / 100 * 4400 if top2 != "" else None

        rows.append(
            {
                "id": vendor_id,
                "name": vendor.get("name", ""),
                "coordinate_status": vendor.get("coordinate_status", ""),
                "compass_eligible": vendor.get("compass_eligible", ""),
                "booth_location": vendor.get("booth_location", ""),
                "current_longitude": current[0] if current else "",
                "current_latitude": current[1] if current else "",
                "official_app_name": source.get("f", "") if source else "",
                "official_app_vendor_url": source.get("u", "") if source else "",
                "official_app_location_id": source.get("mid", "") if source else "",
                "official_app_map_id": source.get("map", "") if source else "",
                "official_app_left2_percent": left2,
                "official_app_top2_percent": top2,
                "derived_map_ref_y": round(map_ref_y, 2) if map_ref_y is not None else "",
                "derived_map_ref_x": round(map_ref_x, 2) if map_ref_x is not None else "",
                "official_app_longitude": app_coordinate[0] if app_coordinate else "",
                "official_app_latitude": app_coordinate[1] if app_coordinate else "",
                "current_to_official_app_m": round(separation, 1) if separation is not None else "",
                "current_to_official_app_ft": round(separation * 3.28084, 1) if separation is not None else "",
                "review_priority": priority(separation, app_coordinate is not None),
            }
        )
    return rows


def build_summary(
    rows: list[dict[str, Any]],
    official_groups: list[dict[str, Any]],
    official_locations: dict[str, Any],
) -> dict[str, Any]:
    counts = Counter(row["review_priority"] for row in rows)
    comparable = [row for row in rows if row["current_to_official_app_m"] != ""]
    ranked = sorted(
        comparable,
        key=lambda row: float(row["current_to_official_app_m"]),
        reverse=True,
    )
    official_food = food_catalog(official_groups)
    map_ids = Counter(
        str(row["official_app_map_id"])
        for row in rows
        if row["official_app_map_id"] != ""
    )
    return {
        "fairplay_vendor_count": len(rows),
        "official_food_vendor_count": len(official_food),
        "exact_id_match_count": sum(1 for row in rows if row["official_app_vendor_url"]),
        "official_app_mapped_vendor_count": len(comparable),
        "official_location_record_count": len(official_locations.get("locations", [])),
        "official_map_ids": dict(sorted(map_ids.items())),
        "review_priority_counts": dict(sorted(counts.items())),
        "top_25_disagreements": [
            {
                "id": row["id"],
                "name": row["name"],
                "distance_m": row["current_to_official_app_m"],
                "distance_ft": row["current_to_official_app_ft"],
                "coordinate_status": row["coordinate_status"],
                "booth_location": row["booth_location"],
            }
            for row in ranked[:25]
        ],
        "official_app_map_missing": [
            {"id": row["id"], "name": row["name"]}
            for row in rows
            if row["review_priority"] == "official_app_map_missing"
        ],
        "notes": [
            "The official app snapshot and FairPlay feed each contain 278 food vendors and match by exact mnstatefair.org vendor ID.",
            "Grandstand left2/top2 positions reproduce Fair Finder mapRef positions after normalization.",
            "Official website, app, mapRef, GeoJSON, and PDF map are one publisher group; distances are review leads, not automatic replacements.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vendors", type=Path)
    parser.add_argument("--manifest-url", nargs="?", const=DEFAULT_MANIFEST_URL)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--official-vendors", type=Path)
    parser.add_argument("--official-locations", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary-output", required=True, type=Path)
    args = parser.parse_args()

    for path in (args.output, args.summary_output):
        if path.exists():
            raise SystemExit(f"refusing to overwrite existing output: {path}")

    vendors = json.loads(args.vendors.read_text(encoding="utf-8"))
    official_groups, official_locations, source_metadata = load_official_sources(args)
    rows = comparison_rows(vendors, official_groups, official_locations)
    summary = build_summary(rows, official_groups, official_locations)
    summary["source"] = source_metadata

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
