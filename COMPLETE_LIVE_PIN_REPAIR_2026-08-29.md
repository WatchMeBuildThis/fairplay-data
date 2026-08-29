# Complete live pin repair — 2026-08-29

## Recommended production action

Publish the reviewed `vendors.json` from this branch only after the final diff
and release-gate artifacts are accepted. Do not merge the earlier fail-closed
feed: that feed preserves every Directory record but the current App Store
binary would display only 56 map pins.

This branch is a data-only repair. It does not modify `bingo_squares.json` and
does not require an App Store release.

## What changes

- All 278 vendor IDs remain present and in the same order.
- All 278 records have app-decodable `[longitude, latitude]` coordinates inside
  the state fair envelope.
- 157 coordinates differ from the current live feed: 12 blanks are filled, 7
  points move 15–30 m, 53 move 30–100 m, and 85 move more than 100 m.
- The large corrections are expected: many original scraped coordinates were
  generic or repeated points that contradicted the vendor's current written
  street, corner, building, Midway, or Kidway location.
- 56 coordinates satisfy the evidence ledger's verified policy. The remaining
  222 are explicitly marked `approximate` and stay in the continuing field-
  verification queue.
- Seventeen newly created exact-overlap groups were separated by a stable 4 m
  offset so each annotation can be selected. Four exact-overlap groups already
  in production are preserved because they are shared-stand/operator records.
- Vendor identity, menus, photos, categories, descriptions, and record order
  are byte-for-byte equivalent as parsed JSON after excluding location audit
  fields.

The original production feed is preserved at
`archive/vendors-2026-08-29-before-complete-pin-repair.json` for review or an
immediate rollback.

## Important shipping-client side effect

The current App Store client ignores `coordinate_status` and
`compass_eligible`. Every non-null coordinate is used for:

1. the map pin;
2. compass bearing and distance;
3. the “Take me there” action; and
4. Apple Maps walking directions.

That means the 222 approximate points are usable navigation targets in the
shipping binary even though their audit metadata says otherwise. The chosen
emergency tradeoff is complete in-fair map coverage using the best written-
location geometry available, rather than blank pins. A later app release should
honor `compass_eligible` and display a distinct approximate-location state.

## How the candidate was constructed

The builder applies this deterministic hierarchy:

1. retain independently reviewed evidence-ledger coordinates;
2. retain existing candidates that are within 30 m of the written constraint
   or have a corroborating exact OSM identity/building constraint;
3. replace greater-than-30 m conflicts with a point on the named street
   segment, street corner quadrant, building wall/section, or named fair zone;
4. restore the separate Mighty Midway Fresh French Fries record from the
   shipping app's bundled point, because the online exact result belongs to its
   other Judson Avenue stand;
5. fill every remaining blank from its written location; and
6. separate newly generated exact overlaps by 4 m.

Ball Park Cafe is intentionally retained at its manual correction. That point
is about 5 m from Google's exact place cell; the automated 36.4 m warning comes
from a simplified street-centerline model and is weaker than the booth-level
corroboration.

The geometry summary contains six greater-than-30 m automated flags. Five are
vendors described only as “At Mighty Midway” or “At Kidway”; their candidates
are inside those large zone polygons, while the checker measures distance to a
polygon edge. The sixth is Ball Park Cafe as explained above. No verified
coordinate is greater than 30 m from its applicable modeled constraint.

## Reproducible build and release gates

Run from the repository root. Use a temporary output so the builder cannot
overwrite its source:

```bash
python3 Scripts/build_complete_live_pin_feed.py \
  --source archive/vendors-2026-08-29-before-complete-pin-repair.json \
  --publish-base archive/vendors-2026-08-29-before-complete-pin-repair.json \
  --verifications location_verifications.json \
  --geometry audit/vendor-written-location-geometry-source-2026-08-29.csv \
  --osm audit/osm-fairgrounds-full-geometry-2026-08-28.json \
  --bundled-fallback audit/vendor-bundled-zone-fallbacks-2026-08-29.json \
  --output /tmp/vendors-complete-pin-candidate.json \
  --change-log /tmp/vendor-complete-pin-changes.json \
  --summary-output /tmp/vendor-complete-pin-build-summary.json
```

The generated candidate and change log must exactly reproduce `vendors.json`
and `audit/vendor-complete-pin-changes-2026-08-29.json`. Then run:

```bash
python3 Scripts/validate_live_pin_release.py \
  --live archive/vendors-2026-08-29-before-complete-pin-repair.json \
  --candidate vendors.json \
  --change-log audit/vendor-complete-pin-changes-2026-08-29.json \
  --output /tmp/vendor-complete-pin-release-validation.json

python3 Scripts/check_written_location_geometry.py \
  --vendors vendors.json \
  --osm audit/osm-fairgrounds-full-geometry-2026-08-28.json \
  --output /tmp/vendor-complete-pin-geometry.csv \
  --summary-output /tmp/vendor-complete-pin-geometry-summary.json

python3 -m unittest discover -s Tests -v
```

The release validator must report `release_gate: pass`, 278 decodable pins, 278
inside-fair pins, preserved non-location content and record order, and zero new
exact-overlap groups. The committed candidate was also compiled and decoded
against the shipping app's actual `Vendor.swift` model: 278 vendors and 278
coordinate pairs decoded successfully.

## Rollout and rollback behavior

Merging this branch to `main` replaces the raw GitHub `vendors.json` consumed by
the app. A newly launched app first shows its bundled or previously cached feed,
then fetches and atomically caches a valid, nonempty remote feed in the
background. An already-running app does not continuously poll; it normally
needs a process relaunch before it requests the update. GitHub's raw-content
cache may add a short propagation delay.

If a production problem is observed, restore
`archive/vendors-2026-08-29-before-complete-pin-repair.json` as `vendors.json`,
run the same release integrity checks, and publish that single-file rollback.

## Continuing verification process

During the remaining fair days, field observations should record vendor ID,
GPS point, timestamp, entrance/booth photo, and observer in
`location_verifications.json`. Re-run the geometry screen and release gate for
every batch. Promote only independently corroborated or on-site points to
`verified`; do not treat repetition among the fair website, GeoJSON, PDF map,
and official app as independent evidence because they share one publisher.
