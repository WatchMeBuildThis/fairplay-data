#!/usr/bin/env python3
"""Compare FairPlay pins with the pins rendered by the official Fair Finder.

The Fair Finder vendor pages expose two different location fields in embedded
``data-geojson``.  The map JavaScript prefers ``properties.mapRef`` (a y-x
pixel reference on the current fair map) over the GeoJSON Point.  This script
selects the feature whose ``properties.id`` exactly matches the requested
vendor, converts its mapRef with the State Fair's published 2026 perspective
transform, and writes an advisory comparison report.

It never edits ``vendors.json``.  Successful page downloads are cached so a
partial or repeated audit does not hammer the State Fair website.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


EARTH_RADIUS_M = 6_371_008.8
FAIR_FINDER_VENDOR_URL = "https://www.mnstatefair.org/vendor/{vendor_id}/"
USER_AGENT = "FairPlay-location-audit/1.0 (+https://github.com/WatchMeBuildThis/fairplay-data)"


@dataclass(frozen=True)
class PerspectiveConfig:
    """Values published in the official 2026 ``maps-*.js`` asset."""

    image_width: float = 3400.0
    image_height: float = 4400.0
    centerline_x: float = 1700.0
    north_east_x: float = 2824.0
    north_east_y: float = 148.0
    south_east_x: float = 3103.0
    south_east_y: float = 3659.0
    min_lat: float = 44.977307
    min_lng: float = -93.18058
    max_lat: float = 44.991625
    max_lng: float = -93.16701


class MapPerspective:
    """Python translation of the official MapPerspective pixel transform."""

    def __init__(self, config: PerspectiveConfig | None = None) -> None:
        self.config = config or PerspectiveConfig()
        config = self.config
        self.screen_height = config.south_east_y - config.north_east_y
        self.screen_width_bottom = (config.south_east_x - config.centerline_x) * 2
        self.screen_width_top = (config.north_east_x - config.centerline_x) * 2
        self.screen_additional_z = config.north_east_y
        self.screen_additional_x = config.south_east_x - self.screen_width_bottom
        self.world_width = (config.max_lng - config.min_lng) * 1_000_000
        self.world_length = (config.max_lat - config.min_lat) * 1_000_000
        self.eye_to_world = (
            self.world_width / 2
            - self.screen_width_top / 2 * self.world_length
        ) / (self.screen_width_top / 2 - self.screen_width_bottom / 2)
        self.eye_to_screen = self.eye_to_world * (
            self.screen_width_bottom / 2 / (self.world_width / 2)
        )
        self.screen_to_world = self.eye_to_world - self.eye_to_screen
        self.eye_above_world = self.screen_height / (
            (self.screen_to_world + self.world_length)
            / (self.eye_to_world + self.world_length)
            - self.screen_to_world / self.eye_to_world
        )
        self.screen_above_world = (
            self.screen_to_world * self.eye_above_world / self.eye_to_world
        )
        self.eye_z = (
            self.screen_above_world + self.screen_height - self.eye_above_world
        )
        self.eye_x = self.screen_width_bottom / 2
        self.world_z = self.screen_height + self.screen_above_world

    def unproject(self, *, x: float, y: float) -> tuple[float, float]:
        numerator = self.eye_to_screen * (self.world_z - self.eye_z)
        denominator = (
            self.config.image_height
            - y
            - self.eye_z
            - self.screen_additional_z
        )
        world_y = numerator / denominator - self.eye_to_world

        # This is the algebraic simplification of the official JavaScript's
        # convertPixelCoordinatesToLatLong method.
        relative_x = (
            (self.eye_to_world + world_y)
            * (x - self.eye_x - self.screen_additional_x)
            / self.eye_to_screen
        )
        world_x = (
            relative_x
            + self.eye_x
            - self.screen_width_bottom / 2
            + self.world_width / 2
        )
        lat = world_y / 1_000_000 + self.config.min_lat
        lng = world_x / 1_000_000 - abs(self.config.min_lng)
        return lng, lat


def distance_m(left: tuple[float, float], right: tuple[float, float]) -> float:
    lon1, lat1 = map(math.radians, left)
    lon2, lat2 = map(math.radians, right)
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    value = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(value))


def parse_coordinate(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    try:
        return float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None


def parse_map_ref(value: Any) -> tuple[float, float] | None:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*", str(value or ""))
    if not match:
        return None
    # The official JavaScript passes mapRef directly to Leaflet as [y, x].
    y, x = map(float, match.groups())
    return x, y


def embedded_features(page: str) -> list[dict[str, Any]]:
    attributes = re.findall(r'\bdata-geojson="([^"]+)"', page, flags=re.IGNORECASE)
    features: list[dict[str, Any]] = []
    for attribute in attributes:
        try:
            value = json.loads(html.unescape(attribute))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("type") == "FeatureCollection":
            value = value.get("features", [])
        if isinstance(value, list):
            features.extend(item for item in value if isinstance(item, dict))
    return features


def exact_vendor_feature(page: str, vendor_id: str) -> tuple[dict[str, Any] | None, int, int]:
    features = embedded_features(page)
    exact = [
        feature
        for feature in features
        if str((feature.get("properties") or {}).get("id")) == vendor_id
    ]
    return (exact[0] if len(exact) == 1 else None), len(features), len(exact)


def fetch_page(vendor_id: str, cache_dir: Path, delay: float, retries: int) -> tuple[str | None, str]:
    cache_path = cache_dir / f"{vendor_id}.html"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8"), "cache"

    request = urllib.request.Request(
        FAIR_FINDER_VENDOR_URL.format(vendor_id=vendor_id),
        headers={"User-Agent": USER_AGENT},
    )
    for attempt in range(retries + 1):
        if delay:
            time.sleep(delay)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                page = response.read().decode("utf-8")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(page, encoding="utf-8")
            return page, "network"
        except urllib.error.HTTPError as error:
            if error.code != 429 or attempt == retries:
                return None, f"http_{error.code}"
            retry_after = error.headers.get("Retry-After")
            wait_seconds = float(retry_after) if retry_after else min(60.0, 2 ** (attempt + 1))
            time.sleep(wait_seconds)
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt == retries:
                return None, type(error).__name__.lower()
            time.sleep(min(30.0, 2 ** (attempt + 1)))
    return None, "fetch_failed"


def comparison_row(vendor: dict[str, Any], page: str | None, source: str) -> dict[str, Any]:
    vendor_id = str(vendor.get("id") or "")
    current = parse_coordinate(vendor.get("coordinates"))
    row: dict[str, Any] = {
        "id": vendor_id,
        "name": vendor.get("name", ""),
        "coordinate_status": vendor.get("coordinate_status", ""),
        "booth_location": vendor.get("booth_location", ""),
        "official_url": FAIR_FINDER_VENDOR_URL.format(vendor_id=vendor_id),
        "page_source": source,
        "feature_count": "",
        "exact_id_feature_count": "",
        "map_ref": "",
        "map_ref_longitude": "",
        "map_ref_latitude": "",
        "current_to_map_ref_m": "",
        "current_to_map_ref_ft": "",
        "geojson_longitude": "",
        "geojson_latitude": "",
        "map_ref_to_geojson_m": "",
        "review_priority": "fetch_failed" if page is None else "",
    }
    if page is None:
        return row

    feature, feature_count, exact_count = exact_vendor_feature(page, vendor_id)
    row["feature_count"] = feature_count
    row["exact_id_feature_count"] = exact_count
    if feature is None:
        row["review_priority"] = "missing_or_ambiguous_exact_id_feature"
        return row

    properties = feature.get("properties") or {}
    raw_map_ref = properties.get("mapRef")
    map_pixel = parse_map_ref(raw_map_ref)
    geometry = feature.get("geometry") or {}
    geojson_coordinate = parse_coordinate(geometry.get("coordinates"))
    row["map_ref"] = raw_map_ref or ""
    if geojson_coordinate:
        row["geojson_longitude"], row["geojson_latitude"] = geojson_coordinate

    if map_pixel is None:
        row["review_priority"] = "missing_map_ref"
        return row

    map_coordinate = MapPerspective().unproject(x=map_pixel[0], y=map_pixel[1])
    row["map_ref_longitude"], row["map_ref_latitude"] = map_coordinate
    if current:
        separation = distance_m(current, map_coordinate)
        row["current_to_map_ref_m"] = round(separation, 1)
        row["current_to_map_ref_ft"] = round(separation * 3.28084, 1)
        if separation >= 100:
            row["review_priority"] = "critical_100m_plus"
        elif separation >= 50:
            row["review_priority"] = "high_50m_plus"
        elif separation >= 25:
            row["review_priority"] = "medium_25m_plus"
        else:
            row["review_priority"] = "close_under_25m"
    else:
        row["review_priority"] = "missing_current_coordinate"
    if geojson_coordinate:
        row["map_ref_to_geojson_m"] = round(
            distance_m(map_coordinate, geojson_coordinate), 1
        )
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vendors", type=Path)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing output: {args.output}")
    vendors = json.loads(args.vendors.read_text(encoding="utf-8"))
    if not isinstance(vendors, list):
        raise SystemExit("vendors input must be a JSON array")
    if args.limit is not None:
        vendors = vendors[: args.limit]

    rows = []
    for index, vendor in enumerate(vendors, start=1):
        vendor_id = str(vendor.get("id") or "")
        page, source = fetch_page(vendor_id, args.cache_dir, args.delay, args.retries)
        rows.append(comparison_row(vendor, page, source))
        print(f"[{index}/{len(vendors)}] {vendor_id}: {source}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
