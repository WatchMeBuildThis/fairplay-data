# Vendor geography audit

`vendors.json` is the live feed. Audit scripts never edit it in place.

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
- CI fails on count drift, duplicate IDs, malformed/out-of-bounds coordinates, popup mismatches, and any newly missing coordinate. Source-missing and deliberately quarantined IDs are explicit exceptions and remain critical in the review report.

Add reviewed evidence to `location_verifications.json`, rerun the audit, inspect the diff, and only then promote a coordinate change to the live feed.

## Independent verification and safe apply

Treat scraped map coordinates as candidates. A coordinate may be marked
`verified` only when all of these are true:

1. The vendor ID/name is an exact match, including the specific fair location.
2. The candidate agrees with the fair's current written directions or address.
3. At least one independent publisher group confirms the place/address/pin.
4. For indoor, multi-location, temporary, or ambiguous booths, a dated on-site
   observation (preferably a GPS point plus photo) resolves the ambiguity.
5. The evidence, method, date, coordinate, and distinct publisher groups are
   recorded in `location_verifications.json`.

The fair website's directions, GeoJSON, map, `mapRef`, PDF, and app are a
single publisher group. Repetition across those sources is not independent
confirmation. A search result or geocoder result alone is not verification.

Apply a reviewed batch to a separate copy:

```bash
python3 Scripts/apply_vendor_verifications.py vendors.json \
  --vendor-id 2021.1 --vendor-id 2336.1 \
  --output audit/vendors-reviewed-batch.json
```

Then run the audit against that copy, inspect every coordinate diff, enrich the
status fields, rerun strict integrity and tests, and only then replace the live
`vendors.json`. The updater refuses approximate candidates, unknown IDs,
out-of-bounds coordinates, and evidence with fewer than two publisher groups.

Before publishing the feed, copy the audited status into each vendor record:

```bash
python3 Scripts/enrich_vendor_geography_status.py vendors.json \
  audit/vendor-location-audit.json --output vendors.json
```

App versions that support these fields must use `compass_eligible`, not the
mere presence of a coordinate, for compass and walking-directions features.

## Official rendered-pin comparison

The official vendor pages contain both a GeoJSON Point and a `mapRef`. The
State Fair's current map JavaScript gives `mapRef` precedence, interpreting it
as a y-x pixel reference on the 2026 map and converting the user's GPS position
into that same map space. Therefore the GeoJSON Point is not necessarily the
pin a visitor sees in the official finder.

Build a cached, advisory comparison against the officially rendered pins:

```bash
python3 Scripts/audit_official_map_refs.py vendors.json \
  --cache-dir audit/cache/official-vendor-pages-2026 \
  --output audit/official-map-ref-comparison-2026.csv
```

The script selects only a feature whose `properties.id` exactly matches the
vendor ID. It never edits `vendors.json`; review high-distance rows alongside
the written directions and independent evidence before changing a live pin.
The fair website, official map, GeoJSON, `mapRef`, PDF, and official app remain
one publisher group and do not independently verify one another.

The Grandstand-powered official app also exposes a much more efficient bulk
source. Its master manifest points to versioned vendor and location snapshots;
the 2026 Food group links all 278 records to exact `mnstatefair.org` vendor IDs.
Grandstand's `left2`/`top2` percentages normalize to the same positions as the
website's `mapRef`, avoiding hundreds of rate-limited detail-page requests.

Fetch the current manifest-selected snapshots and compare them with:

```bash
python3 Scripts/audit_official_app_snapshot.py vendors.json \
  --manifest-url \
  --cache-dir audit/cache/official-app-2026 \
  --output audit/official-app-pin-comparison-2026.csv \
  --summary-output audit/official-app-pin-summary-2026.json
```

For a fully offline/reproducible rerun, replace `--manifest-url` and
`--cache-dir` with `--official-vendors` and `--official-locations` paths to the
cached versioned snapshots.

Treat this as the preferred official bulk candidate source. Preserve field or
independently verified overrides, and never replace all live coordinates from
the official snapshot without reviewing the ranked conflicts.

## Current App Store client and complete-pin release gate

The currently released client does not yet enforce `compass_eligible`. Every
non-null coordinate becomes a map annotation, compass target, distance, and
Apple Maps walking destination. The normal fail-closed policy above therefore
cannot both protect navigation and display all 278 pins in that binary.

For the time-critical 2026-08-29 repair, `vendors.json` contains 56
evidence-verified points and 222 clearly labeled best-available approximate
points. This restores all 278 annotations without changing vendor, menu, photo,
category, or record-order content. It is an emergency availability choice, not
a claim that every temporary booth has entrance-level GPS verification.

Before any complete-pin candidate is published, run the builder and release
validator documented in `COMPLETE_LIVE_PIN_REPAIR_2026-08-29.md`. The release
gate requires all 278 unique records and pins, fair-bounds containment, exact
non-location content preservation, no new exact overlaps, and a complete
coordinate change log.
