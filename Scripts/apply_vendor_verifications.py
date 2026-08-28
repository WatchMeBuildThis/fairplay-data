#!/usr/bin/env python3
"""Apply evidence-qualified vendor coordinates to an explicit feed copy.

Scraped coordinates are candidates, not proof. This script only applies
verification records that pass the repository's independent-evidence policy.
It does not calculate coordinates or edit the evidence ledger.
"""

from __future__ import annotations

import argparse
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any


FAIR_BOUNDS = (-93.19, -93.15, 44.96, 45.00)


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


def in_fair_bounds(coordinate: tuple[float, float]) -> bool:
    min_lon, max_lon, min_lat, max_lat = FAIR_BOUNDS
    lon, lat = coordinate
    return min_lon < lon < max_lon and min_lat < lat < max_lat


def evidence_groups(sources: Any) -> set[str]:
    if not isinstance(sources, list):
        return set()
    return {
        str(source.get("publisher_group") or "").strip()
        for source in sources
        if isinstance(source, dict) and str(source.get("publisher_group") or "").strip()
    }


def validate_verification(vendor_id: str, verification: Any) -> tuple[float, float]:
    if not isinstance(verification, dict):
        raise ValueError(f"{vendor_id}: verification must be an object")
    if verification.get("status") != "verified":
        raise ValueError(f"{vendor_id}: only status=verified can be applied")
    coordinate = parse_coordinate(verification.get("coordinates"))
    if coordinate is None or not in_fair_bounds(coordinate):
        raise ValueError(f"{vendor_id}: verified coordinate is malformed or outside fair bounds")
    groups = evidence_groups(verification.get("sources"))
    if len(groups) < 2:
        raise ValueError(f"{vendor_id}: verified coordinate requires at least two publisher groups")
    if not str(verification.get("method") or "").strip():
        raise ValueError(f"{vendor_id}: verification method is required")
    if not str(verification.get("verified_on") or "").strip():
        raise ValueError(f"{vendor_id}: verified_on date is required")
    return coordinate


def apply_verifications(
    records: list[dict[str, Any]],
    config: dict[str, Any],
    selected_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not selected_ids:
        raise ValueError("At least one vendor id must be selected")
    result = deepcopy(records)
    by_id: dict[str, dict[str, Any]] = {}
    for record in result:
        vendor_id = str(record.get("id") or "")
        if not vendor_id or vendor_id in by_id:
            raise ValueError(f"Feed contains a missing or duplicate vendor id: {vendor_id!r}")
        by_id[vendor_id] = record

    ledger = config.get("vendors")
    if not isinstance(ledger, dict):
        raise ValueError("Verification ledger must contain a vendors object")
    missing_feed = sorted(selected_ids - set(by_id))
    missing_ledger = sorted(selected_ids - set(ledger))
    if missing_feed or missing_ledger:
        raise ValueError(f"Selected id mismatch; missing_feed={missing_feed}, missing_ledger={missing_ledger}")

    changes: list[dict[str, Any]] = []
    for vendor_id in sorted(selected_ids):
        coordinate = validate_verification(vendor_id, ledger[vendor_id])
        record = by_id[vendor_id]
        old_coordinate = record.get("coordinates")
        new_coordinate = [coordinate[0], coordinate[1]]
        record["coordinates"] = new_coordinate
        record.pop("quarantined_coordinates", None)
        record.pop("quarantine_reason", None)
        changes.append({
            "id": vendor_id,
            "name": record.get("name") or "",
            "old_coordinates": old_coordinate,
            "new_coordinates": new_coordinate,
            "changed": old_coordinate != new_coordinate,
        })

    if len(result) != len(records) or {str(row.get("id")) for row in result} != set(by_id):
        raise ValueError("Feed identity changed during verification apply")
    return result, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vendors", type=Path)
    parser.add_argument("--verifications", type=Path, default=Path("location_verifications.json"))
    parser.add_argument("--vendor-id", action="append", dest="vendor_ids", required=True,
                        help="Vendor id to apply; repeat for a reviewed batch")
    parser.add_argument("--output", type=Path, required=True,
                        help="Explicit output copy; cannot overwrite the input")
    args = parser.parse_args()

    if args.vendors.resolve() == args.output.resolve():
        raise SystemExit("Refusing to overwrite the input; write a reviewable copy first")
    records = json.loads(args.vendors.read_text(encoding="utf-8"))
    config = json.loads(args.verifications.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise SystemExit("vendors input must contain a JSON array")

    try:
        updated, changes = apply_verifications(records, config, set(args.vendor_ids))
    except ValueError as error:
        raise SystemExit(str(error)) from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "changes": changes}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
