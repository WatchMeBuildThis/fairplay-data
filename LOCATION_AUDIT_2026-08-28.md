# Vendor Location Forensic Audit — 2026-08-28

> Historical investigation snapshot. Its counts describe the initial forensic
> pass, not the current live-feed safety state. See
> `LOCATION_REMEDIATION_2026-08-28.md` and
> `EMERGENCY_PIN_SAFETY_2026-08-28.md` for current totals and publication
> policy.

## Status

- Live feed: **278 vendors / 278 unique ids**
- Minnesota State Fair food finder: **278 vendors**
- Invalid coordinate shapes or out-of-fairground ranges: **0**
- Missing coordinates: **2** (the official pages publish an empty GeoJSON array)
- Exact duplicate-coordinate groups: **6**
  - 5 are confirmed co-located booths with the same written location and map reference
  - 1 is an unresolved generic Mighty Midway placement
- Empty menu arrays: **16**; the scraper fix is committed, but these records still need a controlled content refresh
- Independently verified booth pins: **4**
- Approximate venue-center pins: **1**
- Not yet independently verified: **271**
- Compass-eligible under the new fail-closed policy: **4**

The app reads the live file at:
`https://raw.githubusercontent.com/WatchMeBuildThis/fairplay-data/main/vendors.json`

## Recovery points

- `archive/vendors-2026-08-28-before-location-fix.json`
- `archive/vendors-2026-08-28-before-forensic-audit.json`

Both are immutable copies committed before their corresponding correction batches.

## Root causes

1. The scraper selected `geo[0]` on multi-location vendor pages, assigning the first sibling booth's feature to every sibling.
2. Selecting by hidden feature id alone is also unsafe. On the live Dairy Bar / Fresh Squeezed page, ids `244.1` and `244.2` are swapped relative to the visible vendor names and directions.
3. The fair site's GeoJSON coordinates are not consistently registered to the fair map. Several features sharing one `mapRef` publish points separated by roughly a block.
4. The food site changed its menu markup from `ul.textcolumns` to `div.item-details > ul`; the previous selector produces false empty-menu records.
5. One current listing, `5754.3` Funnel Cakes & Elephant Ears, was absent from the feed.
6. A single affine conversion from printed-map pixels to latitude/longitude is not safe across the whole sheet. The printed map is visually compressed in the north, so a transform that fits the center can drift by a block near Murphy/Lee.

## Corrections published

### Independently verified pins

- `616.1` Ball Park Cafe / Garlic Fries
- `10093.1` Giggles' Campfire Grill
- `154.1` Mike's Hamburgers
- `1872.1` Andy's Grille

Approximate, not booth-level verified:

- `215.1` Simply Nuts & More (Lee & Rose Warner Coliseum venue center)

### Multi-location/map-reference corrections

These changes are **provisional**. They repaired demonstrably mismatched sibling records, but most are based on the fair's `mapRef` and an affine calibration rather than independent booth-level evidence. They must not be counted as independently verified or used as control points for a new transform.

- `9642.1`, `9642.2`
- `5733.1`, `5733.2`
- `244.1`, `244.2`
- `3759.1`, `3759.2`
- `5754.1`, `5754.2`
- `1509.2`, `1509.3`
- `2084.1`, `2084.2`
- `3276.1`, `3276.2`
- `5581.1`, `5581.2`
- `5052.1`, `5052.2`, `5052.3`

Added missing record:

- `5754.3` Funnel Cakes & Elephant Ears

Mike's Hamburgers was confirmed against its Google Maps place pin; the prior source coordinate was approximately 458 feet away from the written Carnes/Nelson location. Andy's Grille was confirmed against its vendor-published 1774 Carnes Ave address and independent place pin; its prior source coordinate was approximately 249 feet away.

The map-reference transform's small residuals at selected anchors do not prove global accuracy. The northern map distortion and `mapRef`/written-direction conflicts make the batch a review queue, not a verified set.

## Automated forensic audit

`Scripts/audit_vendor_geography.py` now produces a full 278-row audit without editing the live feed. It checks:

- missing, malformed, duplicate, or out-of-bounds coordinates;
- name/location popup mismatches;
- exact coordinates shared by different written locations;
- tight written-location groups whose pins are separated by more than 55 m;
- coordinate changes greater than 40 m from the pre-fix snapshot;
- medium-priority street-corridor conflicts learned from repeated written directions;
- explicit evidence provenance and compass eligibility.

Current queue:

- **2 critical** missing-coordinate records;
- **23 high-priority** internal location conflicts;
- **113 medium-priority** reviews, including provisional map-reference changes and heuristic street-corridor conflicts;
- **140 low-priority** rows with no automated conflict but no independent verification yet.

The 115 street-corridor flags are heuristic leads, not 115 proven bad pins. The source feed is contaminated, so its learned road model cannot serve as independent evidence.

## Scraper safeguards

The scraper on `rebuild/cleanup` now:

- matches multi-feature pages by visible vendor name and written directions, with hidden id as a lower-weight tie-breaker;
- omits ambiguous matches instead of guessing;
- retains `map_ref` for auditability;
- reads both legacy and current menu markup.

## Remaining source-data gaps

- `2340.1` Fresh French Fries: official page has no directions and `data-geojson="[]"`.
- `3645.1` The Mouth Trap Cheese Curds: official page has no directions and `data-geojson="[]"`.
- `2607.1` / `3394.1`: both use the same generic Mighty Midway point; booth-level evidence is not yet sufficient to split them safely.
- 16 current records have empty `items` arrays. The live page check of `1509.3` confirms this is stale scrape output, not an empty menu. A low-rate refresh with the corrected selector is required.

## Decision

A blind full scrape must **not** replace the live feed: it would re-import the fair site's misregistered coordinates. The safe refresh path is:

1. scrape visible content with the hardened feature matcher;
2. retain and validate `map_ref`;
3. reject ambiguous or empty source geometry;
4. merge only records that pass count, id, coordinate, popup/name/location, and duplicate-group checks;
5. preserve independently verified coordinate overrides.

No further bulk coordinate change should be promoted until it appears in `location_verifications.json` with two publisher groups and passes the generated audit. The fair's directions, GeoJSON, `mapRef`, printed map, and official app collectively count as one publisher group.
