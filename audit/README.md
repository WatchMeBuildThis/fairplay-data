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

Treat fair year and booth move as part of identity. A Google place with the
right vendor name can still be stale: compare its address/pin with the current
year's written segment and `Location Change` category. Preserve a stale result
as rejected evidence, never as confirmation of the moved booth. Conversely,
the fair's embedded GeoJSON can be wrong even when its visible directions are
right; reject it when independent exact-place geometry and the named landmark
agree elsewhere.

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
  --geometry-audit audit/vendor-written-location-geometry-YYYY-MM-DD.csv \
  --output audit/vendors-safe-candidate.json
```

The publisher never overwrites its input. It moves every unverified or
approximate value to `withheld_coordinates`, sets the app-facing coordinate to
`null`, and leaves the vendor, menu, written directions, and review candidate
intact. The geography audit continues to analyze withheld candidates, but they
cannot appear as app map pins or drive older navigation code.

Passing `--geometry-audit` additionally reopens and withholds any previously
verified coordinate that conflicts by more than 30 m with the fair's written
location. This is a conservative review copy, not proof that the prior point
is wrong, and it must not replace the live feed without an app smoke test.

## Independent OpenStreetMap comparison

Download one dated, fairgrounds-bounded Overpass export of named features and
keep it outside the repository. Compare all current or withheld candidates:

```bash
python3 Scripts/compare_vendor_osm.py \
  --vendors vendors.json \
  --osm ../osm-fairgrounds-named-YYYY-MM-DD.json \
  --output audit/vendor-osm-comparison-YYYY-MM-DD.csv
```

This comparison is advisory and cannot edit the feed or verification ledger.
It normalizes names, measures candidate-to-place distance, and fails closed on
both multiple OpenStreetMap features and multiple FairPlay records with the
same normalized name. Exact and strong rows are the next manual research
queue; they are not automatic coordinate replacements.

For few-feet precision, require agreement between two independent coordinate
publishers and the fair's written location. A named point or building centroid
from one map is insufficient. Indoor, temporary, multi-location,
large-footprint, or entrance-sensitive rows still require a dated on-site
observation even when public maps agree. Record both the provider-to-provider
distance and the old candidate displacement in the verification method.

## Written-location geometry gate for all records

A named-place comparison only covers vendors that public maps identify by
name. Run the geometry gate as a second, all-record screen using a dated OSM
export that includes named highways and full feature geometry:

```bash
python3 Scripts/check_written_location_geometry.py \
  --vendors vendors.json \
  --osm ../osm-fairgrounds-full-geometry-YYYY-MM-DD.json \
  --output audit/vendor-written-location-geometry-YYYY-MM-DD.csv \
  --summary-output audit/vendor-written-location-geometry-summary-YYYY-MM-DD.json
```

The checker converts the fair's written directions into one of these spatial
constraints: a street corner, the stated part of a street between two cross
streets, a named building/venue, or a street corridor. It measures the current
or withheld candidate against that constraint. A road-centerline gap in OSM
may be extrapolated by at most 100 m to recover a documented fairground grid
intersection; this only constructs the constraint and never constructs a
replacement vendor coordinate.

Review policy:

- 0-15 m: consistent with the written constraint, but not verified by that
  fact alone.
- More than 15 m through 30 m: manual review.
- More than 30 m (about 98 ft): geometry conflict; keep an unverified candidate
  withheld and reopen any previously verified record.
- When one written constraint conflicts but a second named landmark is within
  30 m, classify the row as a documented-constraint review instead of silently
  rejecting or retaining it. Verification still requires independent evidence.
- When a unique exact or strong OpenStreetMap vendor identity is within 10 m
  of an independently verified candidate, preserve it as a secondary identity
  anchor. This can expose a simplified road-centerline false alarm, but it
  cannot verify or move a pin and ambiguous or more distant identities do not
  override the written-location conflict.
- Unparsed, indoor, multi-location, and zone-only descriptions require a named
  entrance/zone or a dated on-site GPS/photo observation.

No row is promoted or moved automatically. Verification still requires exact
vendor identity, agreement with the written constraint, and coordinates from
at least two independent publisher groups within 10 m. Google Maps, a postal
address, a plus code, or an OSM feature is only one group; exact-looking place
results must be rejected when they land outside the fair's written segment.

For the next fair-day field pass, capture the vendor id/name, phone GPS point
with reported accuracy of 10 m or better, a photo showing the booth and nearby
street/building anchor, the intended public entrance for large buildings, and
the observation time. Indoor vendors should publish an entrance or building
zone rather than claim few-feet booth accuracy that GPS cannot support.

## Public-map review batches and the all-record completion gate

Record a completed public-map sweep in an explicit config. The config fixes
the expected population, default failure reasons, record-specific exact or
rejected results, displacement, and evidence URL. Generate a batch without
editing coordinates:

```bash
python3 Scripts/build_public_map_review_batch.py \
  --review-config audit/vendor-public-map-review-config-YYYY-MM-DD.json \
  --output audit/vendor-verification-batch-YYYY-MM-DD.csv
```

Then combine the evidence ledger, every review batch, the feed status, and the
written-location geometry screen into one 278-row register:

```bash
python3 Scripts/build_vendor_validation_register.py \
  --geometry audit/vendor-written-location-geometry-YYYY-MM-DD.csv \
  --output audit/vendor-location-validation-register-YYYY-MM-DD.csv \
  --summary-output audit/vendor-location-validation-register-summary-YYYY-MM-DD.json \
  --require-complete
```

`--require-complete` fails if any vendor lacks either an evidence-ledger
decision or an explicit review-batch decision, if a verified row lacks a
verified ledger entry, or if any non-verified row leaks into compass guidance.
Completeness means every record has a documented decision; it does not mean
every temporary booth has few-feet evidence.

Release sequence:

1. Preserve the pre-change feed in `archive/`.
2. Update only record-specific candidates whose identity and written geometry
   agree; keep one-source results withheld.
3. Regenerate the geometry CSV/summary and the all-record register.
4. Run the strict forensic audit and unit tests.
5. Run `prepare_safe_vendor_feed.py`; it must report zero newly withheld rows
   when the candidate already fails closed.
6. Confirm all 278 vendor records still render when `coordinates` is null.
7. Review the production diff and require an explicit merge decision.
