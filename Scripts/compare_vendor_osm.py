#!/usr/bin/env python3
"""Compare every vendor coordinate candidate with a local Overpass JSON export.

This script is deliberately advisory.  It never edits ``vendors.json`` and it
never marks a coordinate verified.  OpenStreetMap can independently corroborate
a named permanent place or expose a large disagreement, but most temporary fair
booths still need an entrance-level field observation.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path


EARTH_RADIUS_M = 6_371_008.8
GENERIC_TOKENS = {
    "at",
    "fair",
    "food",
    "minnesota",
    "mn",
    "of",
    "state",
    "the",
}


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().replace("&", " and ")
    value = value.replace("'s", "s")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    tokens = [token for token in value.split() if token not in GENERIC_TOKENS]
    return " ".join(tokens)


def name_similarity(left: str, right: str) -> float:
    left_norm = normalize_name(left)
    right_norm = normalize_name(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    left_tokens = set(left_norm.split())
    right_tokens = set(right_norm.split())
    union = left_tokens | right_tokens
    token_score = len(left_tokens & right_tokens) / len(union) if union else 0.0
    sequence_score = SequenceMatcher(None, left_norm, right_norm).ratio()
    containment_score = 0.92 if left_norm in right_norm or right_norm in left_norm else 0.0
    return max(token_score, sequence_score, containment_score)


def distance_m(left: tuple[float, float], right: tuple[float, float]) -> float:
    lon1, lat1 = map(math.radians, left)
    lon2, lat2 = map(math.radians, right)
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def coordinates_for_element(element: dict) -> tuple[float, float] | None:
    if element.get("type") == "node" and "lon" in element and "lat" in element:
        return float(element["lon"]), float(element["lat"])
    center = element.get("center")
    if isinstance(center, dict) and "lon" in center and "lat" in center:
        return float(center["lon"]), float(center["lat"])
    return None


def coordinates_for_vendor(vendor: dict) -> tuple[float, float] | None:
    value = vendor.get("coordinates") or vendor.get("withheld_coordinates")
    if not isinstance(value, list) or len(value) != 2:
        return None
    return float(value[0]), float(value[1])


def osm_url(element: dict) -> str:
    return f"https://www.openstreetmap.org/{element['type']}/{element['id']}"


def address_for_element(element: dict) -> str:
    tags = element.get("tags", {})
    parts = [tags.get("addr:housenumber", ""), tags.get("addr:street", "")]
    return " ".join(part for part in parts if part).strip()


def classify(best: dict | None, exact_count: int, vendor_name_count: int) -> str:
    if not best:
        return "no_named_place_match"
    if vendor_name_count > 1 and best["name_score"] >= 0.82:
        return "ambiguous_vendor_identity"
    if exact_count > 1:
        return "ambiguous_exact_name"
    if best["name_score"] == 1.0 and (best["distance_m"] is None or best["distance_m"] <= 150):
        return "exact_named_place"
    if best["name_score"] >= 0.82 and (best["distance_m"] is None or best["distance_m"] <= 150):
        return "strong_named_place"
    if best["name_score"] >= 0.70 and (best["distance_m"] is None or best["distance_m"] <= 250):
        return "possible_named_place"
    return "no_named_place_match"


def comparison_rows(vendors: list[dict], osm: dict) -> list[dict]:
    places = []
    for element in osm.get("elements", []):
        name = element.get("tags", {}).get("name")
        coordinates = coordinates_for_element(element)
        if name and coordinates:
            places.append((element, name, coordinates))

    vendor_name_counts: dict[str, int] = {}
    for vendor in vendors:
        normalized = normalize_name(vendor.get("name", ""))
        vendor_name_counts[normalized] = vendor_name_counts.get(normalized, 0) + 1

    rows = []
    for vendor in vendors:
        vendor_coordinates = coordinates_for_vendor(vendor)
        matches = []
        for element, place_name, place_coordinates in places:
            similarity = name_similarity(vendor.get("name", ""), place_name)
            separation = distance_m(vendor_coordinates, place_coordinates) if vendor_coordinates else None
            if similarity < 0.55:
                continue
            distance_score = 0.0 if separation is None else max(0.0, 1.0 - separation / 400.0)
            matches.append(
                {
                    "element": element,
                    "name": place_name,
                    "coordinates": place_coordinates,
                    "name_score": similarity,
                    "distance_m": separation,
                    "rank_score": similarity * 0.85 + distance_score * 0.15,
                }
            )

        matches.sort(
            key=lambda match: (
                -match["rank_score"],
                match["distance_m"] if match["distance_m"] is not None else float("inf"),
                match["name"],
            )
        )
        best = matches[0] if matches else None
        exact_count = sum(
            1 for match in matches if match["name_score"] == 1.0 and (match["distance_m"] is None or match["distance_m"] <= 500)
        )
        vendor_name_count = vendor_name_counts.get(normalize_name(vendor.get("name", "")), 0)
        match_class = classify(best, exact_count, vendor_name_count)
        booth_location = vendor.get("booth_location", "")
        needs_field_check = vendor.get("coordinate_status") != "verified" or any(
            token in booth_location.lower()
            for token in ("inside", "in the ", "building", "coliseum", "midway", "kidway", "grandstand")
        )

        row = {
            "id": vendor.get("id", ""),
            "name": vendor.get("name", ""),
            "coordinate_status": vendor.get("coordinate_status", ""),
            "booth_location": booth_location,
            "candidate_longitude": vendor_coordinates[0] if vendor_coordinates else "",
            "candidate_latitude": vendor_coordinates[1] if vendor_coordinates else "",
            "match_class": match_class,
            "vendor_same_name_count": vendor_name_count,
            "osm_name_match_count": exact_count,
            "osm_type": best["element"]["type"] if best else "",
            "osm_id": best["element"]["id"] if best else "",
            "osm_name": best["name"] if best else "",
            "osm_address": address_for_element(best["element"]) if best else "",
            "osm_longitude": best["coordinates"][0] if best else "",
            "osm_latitude": best["coordinates"][1] if best else "",
            "name_score": round(best["name_score"], 4) if best else "",
            "candidate_to_osm_m": round(best["distance_m"], 1) if best and best["distance_m"] is not None else "",
            "osm_url": osm_url(best["element"]) if best else "",
            "few_feet_field_check": "required" if needs_field_check else "recommended",
        }
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vendors", required=True, type=Path)
    parser.add_argument("--osm", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    vendors = json.loads(args.vendors.read_text())
    osm = json.loads(args.osm.read_text())
    if not isinstance(vendors, list):
        raise SystemExit("vendors input must be a JSON array")
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing output: {args.output}")

    rows = comparison_rows(vendors, osm)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
