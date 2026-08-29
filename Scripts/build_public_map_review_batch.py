#!/usr/bin/env python3
"""Build a reproducible public-map review batch from an explicit review config.

The config declares the completed review population, default outcomes by
geometry class, and record-specific exceptions. This script records decisions;
it never changes vendor coordinates or verification status.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
from pathlib import Path
from typing import Any


FIELDS = [
    "batch_position",
    "id",
    "name",
    "outcome",
    "old_coordinates",
    "new_coordinates",
    "delta_m",
    "reason",
    "official_url",
    "independent_url",
    "reviewed_on",
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def prior_reviewed_ids(pattern: str, excluded: set[str] | None = None) -> set[str]:
    reviewed: set[str] = set()
    excluded = {str(Path(value)) for value in (excluded or set())}
    for filename in sorted(glob.glob(pattern)):
        if str(Path(filename)) in excluded:
            continue
        with Path(filename).open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                vendor_id = str(row.get("id") or "").strip()
                if vendor_id:
                    reviewed.add(vendor_id)
    return reviewed


def coordinate_text(value: Any) -> str:
    if not isinstance(value, list) or len(value) != 2:
        return ""
    return f"{value[0]} {value[1]}"


def build_rows(
    vendors: list[dict[str, Any]],
    geometry_rows: dict[str, dict[str, str]],
    reviewed_ids: set[str],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    eligible = set(config.get("eligible_coordinate_statuses") or ["withheld", "missing"])
    defaults = config.get("default_reasons") or {}
    exceptions = config.get("exceptions") or {}
    selected = [
        vendor
        for vendor in vendors
        if str(vendor.get("id") or "") not in reviewed_ids
        and str(vendor.get("coordinate_status") or "") in eligible
    ]
    expected_count = int(config.get("expected_count") or 0)
    if expected_count and len(selected) != expected_count:
        raise ValueError(f"review selection changed: expected {expected_count}, found {len(selected)}")

    selected_ids = {str(vendor.get("id") or "") for vendor in selected}
    unknown_exceptions = sorted(set(exceptions) - selected_ids)
    if unknown_exceptions:
        raise ValueError(f"config exceptions are outside the selected batch: {unknown_exceptions}")

    rows: list[dict[str, Any]] = []
    for position, vendor in enumerate(selected, start=1):
        vendor_id = str(vendor.get("id") or "")
        geometry = geometry_rows.get(vendor_id)
        if not geometry:
            raise ValueError(f"missing geometry row for {vendor_id}")
        location_check = geometry.get("location_check") or "unparsed"
        reason = defaults.get(location_check) or defaults.get("default")
        if not reason:
            raise ValueError(f"no default reason for geometry class {location_check!r}")
        exception = exceptions.get(vendor_id) or {}
        rows.append({
            "batch_position": position,
            "id": vendor_id,
            "name": vendor.get("name") or "",
            "outcome": exception.get("outcome") or "insufficient_evidence",
            "old_coordinates": exception.get("old_coordinates", ""),
            "new_coordinates": exception.get("new_coordinates", ""),
            "delta_m": exception.get("delta_m", 0),
            "reason": exception.get("reason") or reason,
            "official_url": vendor.get("detail_url") or f"https://www.mnstatefair.org/vendor/{vendor_id}/",
            "independent_url": exception.get("independent_url", ""),
            "reviewed_on": config["reviewed_on"],
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendors", type=Path, default=Path("vendors.json"))
    parser.add_argument(
        "--geometry",
        type=Path,
        default=Path("audit/vendor-written-location-geometry-2026-08-29.csv"),
    )
    parser.add_argument(
        "--prior-batch-glob",
        default="audit/vendor-verification-batch-*.csv",
    )
    parser.add_argument("--review-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing output: {args.output}")
    vendors = load_json(args.vendors)
    if not isinstance(vendors, list):
        raise SystemExit("vendors input must be a JSON array")
    with args.geometry.open(newline="", encoding="utf-8") as handle:
        geometry_rows = {row["id"]: row for row in csv.DictReader(handle)}
    config = load_json(args.review_config)
    try:
        rows = build_rows(
            vendors,
            geometry_rows,
            prior_reviewed_ids(
                args.prior_batch_glob,
                set(config.get("exclude_prior_batches") or []),
            ),
            config,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"output": str(args.output), "record_count": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
