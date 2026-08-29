#!/usr/bin/env python3
"""Combine every vendor's geometry, evidence ledger, and review history.

The register is the completion gate for the 278-record validation workflow. A
record is covered only when it has an evidence-ledger decision or an explicit
manual/public-map review-batch decision. Geometry screening alone is not a
completed identity review.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
from collections import Counter
from pathlib import Path
from typing import Any


FIELDS = [
    "id",
    "name",
    "booth_location",
    "coordinate_status",
    "compass_eligible",
    "candidate_longitude",
    "candidate_latitude",
    "location_check",
    "constraint_distance_m",
    "ledger_status",
    "ledger_confidence",
    "publisher_groups",
    "latest_review_outcome",
    "latest_review_reason",
    "latest_reviewed_on",
    "coverage",
    "final_decision",
    "next_required_evidence",
]


def load_batches(pattern: str) -> dict[str, dict[str, str]]:
    latest: dict[str, dict[str, str]] = {}
    for filename in sorted(glob.glob(pattern)):
        with Path(filename).open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                vendor_id = str(row.get("id") or "").strip()
                if not vendor_id:
                    continue
                candidate_key = (str(row.get("reviewed_on") or ""), filename)
                current = latest.get(vendor_id)
                current_key = (
                    str(current.get("reviewed_on") or ""),
                    str(current.get("_filename") or ""),
                ) if current else ("", "")
                if candidate_key >= current_key:
                    latest[vendor_id] = {**row, "_filename": filename}
    return latest


def publisher_groups(entry: dict[str, Any] | None) -> list[str]:
    if not entry:
        return []
    return sorted({
        str(source.get("publisher_group") or "").strip()
        for source in entry.get("sources") or []
        if isinstance(source, dict) and str(source.get("publisher_group") or "").strip()
    })


def final_decision(vendor: dict[str, Any], ledger: dict[str, Any] | None) -> tuple[str, str]:
    coordinate_status = str(vendor.get("coordinate_status") or "")
    ledger_status = str((ledger or {}).get("status") or "")
    if coordinate_status == "verified" and ledger_status == "verified":
        return "publish_compass_pin", "none"
    if coordinate_status == "missing":
        return "publish_vendor_without_pin", "record-specific coordinate plus written-location agreement"
    if ledger_status == "approximate":
        return "publish_vendor_without_pin_preserve_candidate", "second coordinate publisher within 10 m or dated on-site GPS/photo"
    return "publish_vendor_without_pin_preserve_candidate", "record-specific coordinate plus independent corroboration within 10 m"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendors", type=Path, default=Path("vendors.json"))
    parser.add_argument("--verifications", type=Path, default=Path("location_verifications.json"))
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--batch-glob", default="audit/vendor-verification-batch-*.csv")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()

    vendors = json.loads(args.vendors.read_text(encoding="utf-8"))
    ledger = json.loads(args.verifications.read_text(encoding="utf-8")).get("vendors") or {}
    with args.geometry.open(newline="", encoding="utf-8") as handle:
        geometry = {row["id"]: row for row in csv.DictReader(handle)}
    batches = load_batches(args.batch_glob)

    vendor_ids = [str(vendor.get("id") or "") for vendor in vendors]
    if len(vendor_ids) != len(set(vendor_ids)):
        raise SystemExit("vendor feed contains missing or duplicate ids")
    if set(vendor_ids) != set(geometry):
        raise SystemExit("geometry register ids do not match the vendor feed")

    rows: list[dict[str, Any]] = []
    for vendor in vendors:
        vendor_id = str(vendor.get("id") or "")
        evidence = ledger.get(vendor_id)
        review = batches.get(vendor_id)
        if evidence and review:
            coverage = "ledger_and_review_batch"
        elif evidence:
            coverage = "evidence_ledger"
        elif review:
            coverage = "review_batch"
        else:
            coverage = "uncovered"
        decision, next_evidence = final_decision(vendor, evidence)
        candidate = vendor.get("coordinates") or vendor.get("withheld_coordinates") or []
        geo = geometry[vendor_id]
        rows.append({
            "id": vendor_id,
            "name": vendor.get("name") or "",
            "booth_location": vendor.get("booth_location") or vendor.get("directions") or "",
            "coordinate_status": vendor.get("coordinate_status") or "",
            "compass_eligible": str(bool(vendor.get("compass_eligible"))).lower(),
            "candidate_longitude": candidate[0] if len(candidate) == 2 else "",
            "candidate_latitude": candidate[1] if len(candidate) == 2 else "",
            "location_check": geo.get("location_check") or "",
            "constraint_distance_m": geo.get("constraint_distance_m") or "",
            "ledger_status": (evidence or {}).get("status") or "",
            "ledger_confidence": (evidence or {}).get("confidence") or "",
            "publisher_groups": "|".join(publisher_groups(evidence)),
            "latest_review_outcome": (review or {}).get("outcome") or "",
            "latest_review_reason": (review or {}).get("reason") or "",
            "latest_reviewed_on": (review or {}).get("reviewed_on") or (evidence or {}).get("verified_on") or "",
            "coverage": coverage,
            "final_decision": decision,
            "next_required_evidence": next_evidence,
        })

    uncovered = [row["id"] for row in rows if row["coverage"] == "uncovered"]
    invalid_verified = [
        row["id"] for row in rows
        if row["coordinate_status"] == "verified"
        and (row["ledger_status"] != "verified" or row["compass_eligible"] != "true")
    ]
    compass_leaks = [
        row["id"] for row in rows
        if row["coordinate_status"] != "verified" and row["compass_eligible"] == "true"
    ]
    summary = {
        "record_count": len(rows),
        "coverage_counts": dict(Counter(row["coverage"] for row in rows)),
        "coordinate_status_counts": dict(Counter(row["coordinate_status"] for row in rows)),
        "final_decision_counts": dict(Counter(row["final_decision"] for row in rows)),
        "uncovered_ids": uncovered,
        "invalid_verified_ids": invalid_verified,
        "compass_leak_ids": compass_leaks,
        "complete": not uncovered and not invalid_verified and not compass_leaks,
    }
    if args.require_complete and not summary["complete"]:
        raise SystemExit(json.dumps(summary, indent=2))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    args.summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
