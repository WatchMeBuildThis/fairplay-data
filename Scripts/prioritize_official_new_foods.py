#!/usr/bin/env python3
"""Put every Official New Food at the front of its vendor's menu.

The shipping app displays only the first three ``items`` until the user taps
"Show more". Its NEW badge also compares the displayed item to
``item_details.name`` case-sensitively. This publisher fixes both data-level
issues without changing coordinates or any other vendor content.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any


OFFICIAL_NEW_FOOD_ID = 64
EXPECTED_RECORD_COUNT = 278
EXPECTED_OFFICIAL_VENDOR_COUNT = 33


def category_id(category: dict[str, Any]) -> int | None:
    value = category.get("id_cat")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def is_official_new_food_vendor(vendor: dict[str, Any]) -> bool:
    return any(
        category_id(category) == OFFICIAL_NEW_FOOD_ID
        for category in vendor.get("categories") or []
    )


def item_key(value: str) -> str:
    return value.strip().lower()


def first_character_capitalized(value: str) -> str:
    """Match String.firstCharacterCapitalized in the shipping Swift model."""
    words = value.split(" ")
    result: list[str] = []
    for word in words:
        if not word or any(character.isupper() for character in word):
            result.append(word)
        else:
            result.append(word[0].upper() + word[1:])
    return " ".join(result)


def output_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def prioritize_vendor(vendor: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    result = copy.deepcopy(vendor)
    old_items = list(vendor.get("items") or [])
    details = result.get("item_details") or []
    new_details = [detail for detail in details if detail.get("is_new") is True]
    if not new_details:
        raise ValueError(f"Official New Food vendor {vendor.get('id')} has no is_new item")
    if len(new_details) > 3:
        raise ValueError(
            f"Official New Food vendor {vendor.get('id')} has {len(new_details)} new items; "
            "the shipping preview can display only three"
        )

    item_positions: dict[str, list[int]] = {}
    for index, item in enumerate(old_items):
        item_positions.setdefault(item_key(item), []).append(index)

    new_keys: list[str] = []
    for detail in new_details:
        key = item_key(str(detail.get("name") or ""))
        if key not in item_positions:
            raise ValueError(
                f"New item {detail.get('name')!r} is absent from items for vendor {vendor.get('id')}"
            )
        if len(item_positions[key]) != 1:
            raise ValueError(
                f"New item {detail.get('name')!r} is duplicated in items for vendor {vendor.get('id')}"
            )
        if key in new_keys:
            raise ValueError(
                f"New item {detail.get('name')!r} is duplicated in item_details for vendor {vendor.get('id')}"
            )
        new_keys.append(key)

    new_key_set = set(new_keys)
    prioritized = [item for item in old_items if item_key(item) in new_key_set]
    remaining = [item for item in old_items if item_key(item) not in new_key_set]
    result["items"] = prioritized + remaining

    displayed_by_key = {
        item_key(item): first_character_capitalized(item.strip()) for item in prioritized
    }
    normalizations: list[dict[str, str]] = []
    for detail in details:
        if detail.get("is_new") is not True:
            continue
        old_name = str(detail.get("name") or "")
        display_name = displayed_by_key[item_key(old_name)]
        if old_name != display_name:
            normalizations.append({"before": old_name, "after": display_name})
            detail["name"] = display_name

    visible = [first_character_capitalized(item.strip()) for item in result["items"][:3]]
    published_new_names = [
        str(detail.get("name") or "")
        for detail in details
        if detail.get("is_new") is True
    ]
    missing_from_preview = [name for name in published_new_names if name not in visible]
    if missing_from_preview:
        raise ValueError(
            f"New items are still hidden for vendor {vendor.get('id')}: {missing_from_preview}"
        )

    change = {
        "id": vendor.get("id"),
        "name": vendor.get("name"),
        "new_foods": published_new_names,
        "items_reordered": result["items"] != old_items,
        "old_items": old_items,
        "new_items": result["items"],
        "badge_name_normalizations": normalizations,
    }
    return result, change


def build(source: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(source) != EXPECTED_RECORD_COUNT:
        raise ValueError(f"Expected {EXPECTED_RECORD_COUNT} vendor records; found {len(source)}")

    result: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    for vendor in source:
        if is_official_new_food_vendor(vendor):
            published, change = prioritize_vendor(vendor)
            result.append(published)
            changes.append(change)
        else:
            result.append(copy.deepcopy(vendor))

    if len(changes) != EXPECTED_OFFICIAL_VENDOR_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_OFFICIAL_VENDOR_COUNT} Official New Food vendors; found {len(changes)}"
        )
    return result, changes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--change-log", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.source.resolve() == args.output.resolve():
        raise SystemExit("Refusing to overwrite the source feed")

    source_bytes = args.source.read_bytes()
    source = json.loads(source_bytes)
    published, changes = build(source)
    published_bytes = output_bytes(published)

    reordered_count = sum(change["items_reordered"] for change in changes)
    normalization_count = sum(
        len(change["badge_name_normalizations"]) for change in changes
    )
    new_food_count = sum(len(change["new_foods"]) for change in changes)
    summary = {
        "record_count": len(published),
        "official_new_food_vendor_count": len(changes),
        "official_new_food_item_count": new_food_count,
        "vendors_reordered_count": reordered_count,
        "badge_name_normalization_count": normalization_count,
        "official_vendors_with_every_new_food_in_first_three": len(changes),
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "output_sha256": hashlib.sha256(published_bytes).hexdigest(),
    }

    for path in (args.output, args.change_log, args.summary_output):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(published_bytes)
    args.change_log.write_bytes(output_bytes(changes))
    args.summary_output.write_bytes(output_bytes(summary))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
