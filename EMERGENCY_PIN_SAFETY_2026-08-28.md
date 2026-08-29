# Emergency vendor-pin safety release — 2026-08-28

## Reason

The app's remote JSON updates installed clients immediately, including builds
that may render every non-null coordinate without consulting the newer
`compass_eligible` field. Automated review also confirms that a syntactically
valid Minnesota State Fair GeoJSON point can be hundreds of feet from the
written vendor location.

Ball Park Cafe is the clearest control case. The current official page exposes
`[-93.171034706645, 44.979541455913]`; today's reviewed coordinate is
`[-93.1700734, 44.9803924]`, 121.1 m (397 ft) away. Independent address/place
data identifies the permanent venue at 1312 Underwood Street and places its
center about 22.3 m (73 ft) from the reviewed point. The remaining difference
is plausible for a large café/courtyard, but an on-site entrance GPS/photo is
still the appropriate final validation.

## Data-only mitigation

The emergency feed keeps all 278 vendor/menu records but publishes coordinates
for only the 62 reviewed, compass-eligible records. It moves 204 unverified or
approximate candidates to `withheld_coordinates`, sets their app-facing
`coordinates` to `null`, and leaves the 12 already missing/quarantined records
unchanged.

Expected app behavior:

- older and current builds cannot map or navigate to a withheld candidate;
- users can still find every vendor and read the fair's written directions;
- audit tooling retains every candidate for continued verification;
- a verified coordinate can be restored individually through the evidence
  ledger and reviewed apply process.

## Recovery and verification

- Pre-mitigation copy:
  `archive/vendors-2026-08-28-before-withholding-unverified-pins.json`
- Withholding decision log:
  `audit/vendor-coordinate-withholding-2026-08-28.json`
- Tests: 24 passing
- Strict geography integrity: passing
- Expected release totals: 278 unique vendors, 62 published coordinates,
  204 withheld candidates, 12 missing/quarantined, 62 compass-eligible.

After publication, fetch the raw GitHub URL back and verify its SHA-256 and the
totals above. Rollback is a direct restoration of the dated archive if an
unexpected decoder or app-display issue appears.
