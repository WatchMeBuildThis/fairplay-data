#!/usr/bin/env python3
"""Copy audited geography status into the app's vendor feed.

The location audit remains the source of truth. This small publish step makes
its fail-closed compass decision available to app versions that understand the
`coordinate_status` and `compass_eligible` fields.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def enrich_records(records: list[dict[str, Any]], audit: dict[str, Any]) -> list[dict[str, Any]]:
    statuses = {str(row["id"]): row for row in audit.get("vendors", [])}
    record_ids = {str(record.get("id")) for record in records}
    if record_ids != set(statuses):
        missing = sorted(record_ids - set(statuses))
        extra = sorted(set(statuses) - record_ids)
        raise ValueError(f"Audit/feed id mismatch; missing={missing}, extra={extra}")

    for record in records:
        status = statuses[str(record["id"])]
        record["coordinate_status"] = status["coordinate_status"]
        record["compass_eligible"] = bool(status["compass_eligible"])
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vendors", type=Path)
    parser.add_argument("audit", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    records = json.loads(args.vendors.read_text(encoding="utf-8"))
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    enriched = enrich_records(records, audit)
    args.output.write_text(json.dumps(enriched, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
