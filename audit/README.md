# Vendor geography audit

`vendors.json` is the live feed. The audit never edits it.

Run:

```bash
python3 Scripts/audit_vendor_geography.py vendors.json \
  --baseline archive/vendors-2026-08-28-before-location-fix.json
```

The baseline above is deliberately fixed. Do not replace it with the newest
batch archive when regenerating the committed audit: a rolling baseline erases
older coordinate moves from the review history. Batch archives are recovery
points; the pre-location-fix snapshot is the forensic comparison baseline.

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

## Source refresh and identity gate

The fair's numeric suffix is not a sufficient identity key. Before merging a
new scrape, compare each source page using the tuple of visible vendor name,
written directions, menu fingerprint, and source URL/id. Treat any id-to-name
or id-to-location reassignment as a blocking identity-drift review. Preserve
the app's stable id until bundled photos, favorites, and other id-keyed state
have an explicit migration.

For pages that publish multiple GeoJSON features, select a feature by visible
name and written directions. Use the hidden feature id only as a lower-weight
tie-breaker, and omit geometry when the best match is ambiguous. Never merge a
fresh scrape directly over `vendors.json`; write a candidate copy and compare:

- total count, unique ids, and added/removed ids;
- id/name/directions identity tuples;
- coordinate changes over 40 m;
- popup/name/location agreement;
- missing, malformed, duplicate, and out-of-bounds coordinates;
- menu regressions, especially newly empty `items` arrays;
- verified overrides and quarantined coordinates.

After regenerating the audit with the fixed baseline, the committed JSON and
CSV must have no diff. CI enforces this so a passing integrity check cannot
coexist with stale or rolling-baseline review artifacts.

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

## Emergency app-feed safety copy

Older app builds and the current map view may still display any non-null
`coordinates` value even when navigation is ineligible. Before every remaining
candidate has booth-level evidence, publish a fail-closed copy that contains
only verified coordinates:

```bash
python3 Scripts/prepare_safe_vendor_feed.py vendors.json \
  --output audit/vendors-safe-candidate.json
```

The publisher never overwrites its input. It moves every unverified or
approximate value to `withheld_coordinates`, sets the app-facing coordinate to
`null`, and leaves the vendor, menu, written directions, and review candidate
intact. The geography audit continues to analyze withheld candidates, but they
cannot appear as app map pins or drive older navigation code.
