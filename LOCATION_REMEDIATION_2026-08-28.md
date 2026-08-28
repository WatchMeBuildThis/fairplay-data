# Vendor location remediation — 2026-08-28

## Production decision

Navigation now fails closed. A vendor may drive the compass and walking-
directions action only when `compass_eligible` is `true`, which requires a
reviewed coordinate supported by at least two publisher groups. Unverified
coordinates remain visible on the directory map in compatible app versions.

For the currently released app, 11 directly conflicting coordinates were set
to `null` so it cannot point users toward a disputed pin. Their original values
remain in `quarantined_coordinates` and Git history. Written booth directions
remain present.

## Independently verified corrections

| ID | Vendor | Published coordinate (lon, lat) | Evidence |
|---|---|---:|---|
| 210.1 | Al's Subs & Malt Shop | -93.1718193, 44.9803951 | Fair directions + Google place/address |
| 1932.1 | Bayou Bob's Gator Shack | -93.1717340, 44.9807911 | Fair directions + Google place/address |
| 216.1 | Coasters | -93.1750531, 44.9797389 | Fair directions + Google place/address |
| 2112.1 | Corn Roast | -93.1716163, 44.9808717 | Fair directions + Google place/address |
| 2142.1 | Cream Puffs | -93.1760149, 44.9805332 | Fair directions + Google place/address |
| 225.1 | Donna's Bar-B-Q | -93.1755381, 44.9784136 | Fair directions + Google place/address |
| 2776.1 | Miller's Flavored Cheese Curds | -93.1719291, 44.9801338 | Fair directions + Google place pin |
| 3089.1 | The Perfect Pickle | -93.1755182, 44.9806751 | Fair directions + vendor site + Google place/address |
| 3127.1 | Que Viet Concessions | -93.1688966, 44.9807643 | Fair directions + Google place pin |
| 3340.1 | Spaghetti Eddies | -93.1688970, 44.9807323 | Fair directions + Google place pin |

Mouth Trap Cheese Curds (`3645.1`) was restored at
`-93.1699704, 44.9802432`. It remains **approximate** and compass-ineligible:
independent sources agree it is in the Food Building, but only one place
publisher exposes a booth-level pin.

Fresh French Fries (`2340.1`) now has the corrected written location “At Mighty
Midway” but remains coordinate-missing. A Google place result maps the other
Judson Avenue booth, so copying it would knowingly collapse two locations.

## Quarantined disputed coordinates

The following 11 records had direct peer-location conflicts and no independent
booth pin. Their coordinates are intentionally withheld pending verification:

- 2069.1 Crutchees Cheese on a Stick
- 2120.3 L & B Cotton Candy
- 2561.1 Isabel Burke's Taffy
- 3008.1 Oven Fresh Brownies
- 3115.1 Pronto Pups
- 3280.1 Elm's Shaved Ice
- 3340.2 Deep Fried Batter Dipped Twinkies & Buckeyes
- 3745.1 Danielson's & Daughters Onion Rings
- 5910.1 Pickle Barrel Sirloin Tips
- 6135.1 About a Foot Long Hot Dog
- 11505.1 Chocolate Strawberry Cup

## Audit state after remediation

- 278 total vendor records; 278 unique IDs
- 14 verified and compass-eligible
- 2 approximate and compass-ineligible
- 12 missing/quarantined and compass-ineligible
- 250 present but not independently verified and compass-ineligible
- 103 medium-priority street-corridor heuristic leads remain; these are review
  prompts, not proven errors and were not used to move pins
- No unquarantined high-priority peer-location conflicts remain

This is not a claim that 100% of coordinates are correct. It is a controlled
state in which proven corrections are published, directly conflicting pins are
blocked, and every remaining coordinate is labeled according to its evidence.
