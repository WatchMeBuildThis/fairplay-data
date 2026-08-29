#!/usr/bin/env python3
"""Release gate for a data-only bingo prompt expansion."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


MAX_PROMPT_LENGTH = 26
MIN_PROMPT_COUNT = 40


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--additions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def decode_string_array(path: Path, label: str, errors: list[str]) -> list[Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"{label} is not readable JSON: {error}")
        return []
    if not isinstance(value, list):
        errors.append(f"{label} must be a top-level JSON array")
        return []
    if not all(isinstance(item, str) for item in value):
        errors.append(f"{label} must contain strings only")
    return value


def duplicate_keys(items: list[str]) -> list[str]:
    keys = [item.strip().lower() for item in items]
    counts = Counter(keys)
    return sorted(key for key, count in counts.items() if key and count > 1)


def main() -> None:
    args = parse_args()
    errors: list[str] = []
    baseline_raw = decode_string_array(args.baseline, "baseline", errors)
    candidate_raw = decode_string_array(args.candidate, "candidate", errors)
    additions_raw = decode_string_array(args.additions, "additions", errors)

    baseline = [item for item in baseline_raw if isinstance(item, str)]
    candidate = [item for item in candidate_raw if isinstance(item, str)]
    additions = [item for item in additions_raw if isinstance(item, str)]

    for label, items in (
        ("baseline", baseline),
        ("candidate", candidate),
        ("additions", additions),
    ):
        if any(not item.strip() for item in items):
            errors.append(f"{label} contains a blank prompt")
        if any(item != item.strip() for item in items):
            errors.append(f"{label} contains leading or trailing whitespace")
        duplicates = duplicate_keys(items)
        if duplicates:
            errors.append(f"{label} contains case-insensitive duplicates: {duplicates}")

    if len(candidate) < MIN_PROMPT_COUNT:
        errors.append(
            f"candidate has {len(candidate)} prompts; shipping validation requires at least {MIN_PROMPT_COUNT}"
        )
    if candidate != baseline + additions:
        errors.append("candidate is not the unchanged baseline followed by the approved additions")

    combined_duplicates = duplicate_keys(baseline + additions)
    if combined_duplicates:
        errors.append(f"additions collide with the baseline: {combined_duplicates}")

    overlong = [
        {"prompt": prompt, "length": len(prompt)}
        for prompt in candidate
        if len(prompt) > MAX_PROMPT_LENGTH
    ]
    if overlong:
        errors.append(f"candidate contains prompts longer than {MAX_PROMPT_LENGTH} characters")

    result = {
        "release_gate": "pass" if not errors else "fail",
        "baseline_prompt_count": len(baseline),
        "approved_addition_count": len(additions),
        "candidate_prompt_count": len(candidate),
        "candidate_unique_prompt_count": len({item.lower() for item in candidate}),
        "maximum_prompt_length": max(map(len, candidate), default=0),
        "shipping_minimum_prompt_count": MIN_PROMPT_COUNT,
        "display_target_maximum_length": MAX_PROMPT_LENGTH,
        "existing_prompt_order_preserved": candidate[:len(baseline)] == baseline,
        "overlong_prompts": overlong,
        "errors": errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
