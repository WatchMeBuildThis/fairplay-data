#!/usr/bin/env python3
"""Create an app feed that publishes only verified navigation coordinates.

The source feed doubles as an audit workspace, so unverified coordinates are
useful evidence even when they are unsafe to display. This publisher moves
those coordinates to ``withheld_coordinates`` instead of deleting them. The
app ignores the preserved candidate and sees ``coordinates: null``.

The input is never overwritten. Publish only the explicit output copy after it
passes the geography audit and a human diff review.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any


FAIR_BOUNDS = (-93.19, -93.15, 44.96, 45.00)
WITHHELD_REASON = (
    "Candidate coordinate is not independently verified for navigation; "
    "withheld from the app map pending review."
)
GEOMETRY_CONFLICT_REASON = (
    "Previously verified coordinate conflicts by more than 30 m with the fair's "
    "written location; withheld pending renewed independent verification."
)


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


def prepare_safe_feed(
    records: list[dict[str, Any]],
    reopened_verified_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    result = deepcopy(records)
    reopened_verified_ids = reopened_verified_ids or set()
    seen: set[str] = set()
    changes: list[dict[str, Any]] = []

    for record in result:
        vendor_id = str(record.get("id") or "")
        if not vendor_id or vendor_id in seen:
            raise ValueError(f"Feed contains a missing or duplicate vendor id: {vendor_id!r}")
        seen.add(vendor_id)

        status = str(record.get("coordinate_status") or "unverified")
        eligible = record.get("compass_eligible") is True
        raw_coordinate = record.get("coordinates")
        coordinate = parse_coordinate(raw_coordinate)

        reopened = vendor_id in reopened_verified_ids
        if status == "verified" and eligible and not reopened:
            if coordinate is None or not in_fair_bounds(coordinate):
                raise ValueError(
                    f"{vendor_id}: verified navigation coordinate is malformed or outside fair bounds"
                )
            record.pop("withheld_coordinates", None)
            record.pop("withheld_reason", None)
            continue

        record["compass_eligible"] = False
        if raw_coordinate is None:
            continue
        if coordinate is None or not in_fair_bounds(coordinate):
            raise ValueError(
                f"{vendor_id}: unsafe coordinate cannot be preserved because it is malformed or outside fair bounds"
            )

        record["withheld_coordinates"] = raw_coordinate
        record["withheld_reason"] = GEOMETRY_CONFLICT_REASON if reopened else WITHHELD_REASON
        record["coordinates"] = None
        record["coordinate_status"] = "withheld"
        changes.append({
            "id": vendor_id,
            "name": record.get("name") or "",
            "previous_status": status,
            "reason": "geometry_conflict_over_30m" if reopened else "not_verified",
            "withheld_coordinates": raw_coordinate,
        })

    return result, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vendors", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--change-log", type=Path,
                        help="optional JSON file listing every withheld record")
    parser.add_argument(
        "--geometry-audit",
        type=Path,
        help="optional written-location CSV; verified rows over 30 m are reopened and withheld",
    )
    args = parser.parse_args()

    if args.vendors.resolve() == args.output.resolve():
        raise SystemExit("Refusing to overwrite the input; write a reviewable copy first")

    records = json.loads(args.vendors.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise SystemExit("vendors input must contain a JSON array")

    reopened_verified_ids: set[str] = set()
    if args.geometry_audit:
        with args.geometry_audit.open(newline="", encoding="utf-8") as handle:
            audit_rows = list(csv.DictReader(handle))
        feed_ids = {str(record.get("id") or "") for record in records}
        audit_ids = {str(row.get("id") or "") for row in audit_rows}
        if audit_ids != feed_ids:
            raise SystemExit("geometry audit IDs do not exactly match the vendor feed")
        reopened_verified_ids = {
            str(row["id"])
            for row in audit_rows
            if row.get("coordinate_status") == "verified"
            and row.get("location_check") == "reject_over_30m"
        }

    try:
        safe_records, changes = prepare_safe_feed(records, reopened_verified_ids)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(safe_records, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if args.change_log:
        args.change_log.parent.mkdir(parents=True, exist_ok=True)
        args.change_log.write_text(
            json.dumps(changes, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps({
        "output": str(args.output),
        "record_count": len(safe_records),
        "published_coordinate_count": sum(
            record.get("coordinates") is not None for record in safe_records
        ),
        "withheld_coordinate_count": len(changes),
        "reopened_verified_count": len(reopened_verified_ids),
        "change_log": str(args.change_log) if args.change_log else None,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
