# Vendor geography audit

`vendors.json` is the live feed. The audit never edits it.

Run:

```bash
python3 Scripts/audit_vendor_geography.py vendors.json \
  --baseline archive/vendors-2026-08-28-before-location-fix.json
```

Outputs:

- `vendor-location-audit.json`: full machine-readable evidence/status report.
- `vendor-location-review.csv`: priority-sorted review queue for all vendors.

Policy:

- A coordinate is **verified** only when a reviewed coordinate agrees with the feed and has evidence from at least two publisher groups.
- The Minnesota State Fair's directions, GeoJSON, `mapRef`, PDF map, and official app are all one publisher group. They cannot confirm one another independently.
- Only `verified` rows are compass-eligible. `approximate`, `unverified`, `missing`, and `conflict` rows must fall back to written directions.
- Automated conflict flags are review leads, not automatic coordinate replacements.
- A conservative street-corridor screen learns the densest coordinate band for repeatedly named fairground streets. Because the source feed itself is contaminated, these are medium-priority heuristic leads only; they never invalidate independent verification or move a pin.
- CI fails on count drift, duplicate IDs, malformed/out-of-bounds coordinates, popup mismatches, and any newly missing coordinate. The two source-known missing IDs are explicit exceptions and remain critical in the review report.

Add reviewed evidence to `location_verifications.json`, rerun the audit, inspect the diff, and only then promote a coordinate change to the live feed.
