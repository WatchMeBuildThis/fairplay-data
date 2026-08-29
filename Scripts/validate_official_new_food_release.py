#!/usr/bin/env python3
"""Release gate for the data-only Official New Food ordering fix."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from prioritize_official_new_foods import (
    EXPECTED_OFFICIAL_VENDOR_COUNT,
    EXPECTED_RECORD_COUNT,
    first_character_capitalized,
    is_official_new_food_vendor,
    item_key,
    output_bytes,
    prioritize_vendor,
)


def without_menu(vendor: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in vendor.items()
        if key not in {"items", "item_details"}
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    baseline = json.loads(args.baseline.read_bytes())
    candidate = json.loads(args.candidate.read_bytes())
    errors: list[str] = []

    if len(baseline) != EXPECTED_RECORD_COUNT or len(candidate) != EXPECTED_RECORD_COUNT:
        errors.append(
            f"record count changed: baseline={len(baseline)} candidate={len(candidate)}"
        )
    baseline_ids = [vendor.get("id") for vendor in baseline]
    candidate_ids = [vendor.get("id") for vendor in candidate]
    if candidate_ids != baseline_ids:
        errors.append("vendor IDs or record order changed")

    candidate_by_id = {vendor.get("id"): vendor for vendor in candidate}
    official_count = 0
    preview_pass_count = 0
    pin_fields_preserved = True
    unrelated_fields_preserved = True

    for original in baseline:
        vendor_id = original.get("id")
        current = candidate_by_id.get(vendor_id)
        if current is None:
            continue

        for field in ("coordinates", "coordinate_status", "compass_eligible"):
            if current.get(field) != original.get(field):
                pin_fields_preserved = False
                errors.append(f"{vendor_id}: pin field {field} changed")

        if not is_official_new_food_vendor(original):
            if current != original:
                errors.append(f"{vendor_id}: non-Official-New-Food vendor changed")
                unrelated_fields_preserved = False
            continue

        official_count += 1
        expected, _ = prioritize_vendor(original)
        if current != expected:
            errors.append(f"{vendor_id}: candidate does not equal the deterministic transform")
        if without_menu(current) != without_menu(original):
            errors.append(f"{vendor_id}: a non-menu field changed")
            unrelated_fields_preserved = False
        if Counter(current.get("items") or []) != Counter(original.get("items") or []):
            errors.append(f"{vendor_id}: menu items were added, removed, or renamed")

        new_names = [
            str(detail.get("name") or "")
            for detail in current.get("item_details") or []
            if detail.get("is_new") is True
        ]
        visible = [
            first_character_capitalized(str(item).strip())
            for item in (current.get("items") or [])[:3]
        ]
        if all(name in visible for name in new_names):
            preview_pass_count += 1
        else:
            errors.append(f"{vendor_id}: one or more new foods are absent from the first three")

        new_keys = {item_key(name) for name in new_names}
        leading_keys = [item_key(item) for item in (current.get("items") or [])[:len(new_keys)]]
        if set(leading_keys) != new_keys or len(leading_keys) != len(new_keys):
            errors.append(f"{vendor_id}: new foods are not the first menu entries")

    if official_count != EXPECTED_OFFICIAL_VENDOR_COUNT:
        errors.append(
            f"Official New Food vendor count is {official_count}; expected {EXPECTED_OFFICIAL_VENDOR_COUNT}"
        )
    if preview_pass_count != EXPECTED_OFFICIAL_VENDOR_COUNT:
        errors.append(
            f"Only {preview_pass_count} Official New Food vendors pass the three-row preview gate"
        )

    result = {
        "release_gate": "pass" if not errors else "fail",
        "record_count": len(candidate),
        "official_new_food_vendor_count": official_count,
        "official_vendors_with_every_new_food_first_and_visible": preview_pass_count,
        "pin_fields_preserved": pin_fields_preserved,
        "unrelated_fields_preserved": unrelated_fields_preserved,
        "errors": errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output_bytes(result))
    print(json.dumps(result, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
