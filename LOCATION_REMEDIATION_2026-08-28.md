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
| 2021.1 | Cafe Caribe | -93.1738652, 44.9797356 | Fair directions + vendor address + Google place pin |
| 2336.1 | French Meadow Bakery & Cafe | -93.1712263, 44.9801274 | Fair directions + vendor address + Google place pin |
| 2770.1 | All You Can Drink Milk | -93.1733688, 44.9786946 | Fair directions + operator location + Google place pin |
| 256.1 | O'Gara's at the Fair | -93.1684059, 44.9809198 | Fair directions + independent venue coverage + Google place/address |
| 3450.1 | The Hangar | -93.1702407, 44.9873662 | Fair directions + operator venue page + Google place/address |
| 1968.1 | The Blue Barn | -93.1760875, 44.9811063 | Fair directions + operator location + Google place/address |
| 212.1 | Blue Moon Dine-In Theater | -93.1740994, 44.9800146 | Fair directions + independent venue coverage + Google place/address |
| 3684.1 | Hamline Church Dining Hall | -93.1698412, 44.9814379 | Fair directions + church venue history + Google place/address |
| 1416.1 | LuLu's Public House | -93.1776071, 44.9812286 | Fair directions + independent venue documentation + Google place/address |
| 198.1 | Mancini's al Fresco | -93.1716697, 44.9801006 | Fair directions + operator venue page + Google place/address |
| 2878.1 | Minnesota Farmers Union Coffee Shop | -93.1685723, 44.9814844 | Fair directions + operator address + Google place/address |
| 3231.1 | Salem Lutheran Church Dining Hall | -93.1678234, 44.9845954 | Fair directions + independent venue coverage + Google place/address |
| 2924.1 | Turkey to Go | -93.1733812, 44.9789745 | Fair directions + operator-group address + Google place/address |
| 1457.1 | Dino's Gyros | -93.1710869, 44.9801130 | Fair directions + vendor location + Google place/address |
| 252.1 | The Peg | -93.1693102, 44.9790698 | Fair directions + independent venue coverage + Google place/address |
| 3101.1 | The Produce Exchange | -93.1707570, 44.9800641 | Fair directions + independent venue coverage + Google place/address |
| 12335.1 | Carl's Gizmo | -93.1692506, 44.9813316 | Fair directions + Google place/address |
| 7099.1 | Carousel BBQ | -93.1749722, 44.9806423 | Fair directions + Google place pin |
| 2084.1 | CinnieSmiths | -93.1693875, 44.9871474 | Fair directions + Google place pin |
| 4752.1 | Fluffy's Hand Cut Donuts | -93.1747099, 44.9800099 | Fair directions + Google place pin |
| 7741.1 | Jive Turkey BBQ | -93.1701194, 44.9867755 | Fair directions + Google place/address |
| 2710.1 | The Lunch Box | -93.1689096, 44.9816333 | Fair directions + Google place/address |
| 1548.1 | Minneapple Pie | -93.1716182, 44.9787774 | Fair directions + Google place pin |
| 4072.1 | Minnesota Wine Country | -93.1708926, 44.9793878 | Fair directions + Google place/address |
| 3404.1 | Root Beer Hut | -93.1736472, 44.9800207 | Fair directions + Google place/address |
| 3276.1 | Shanghai Henri's | -93.1693112, 44.9784212 | Fair directions + Google place pin |
| 3792.1 | Tiny Tim Donuts | -93.1737502, 44.9800518 | Fair directions + Google place pin |
| 1952.1 | Big Fat Bacon | -93.1708786, 44.9809673 | Fair directions + operator site + Google place/address |
| 10347.1 | Greater Tater | -93.1756477, 44.9792492 | Fair directions + operator location + Google place/address |
| 3217.1 | RC's BBQ | -93.1748973, 44.9811008 | Fair directions + operator profile + Google place/address |
| 5754.1 | Rick's Pizza | -93.1682909, 44.9814558 | Fair directions + Google place/address |
| 11056.1 | Roon's Savories | -93.1752848, 44.9781329 | Fair directions + operator location + Google place/address |
| 3239.1 | The Sandwich Stop | -93.1733813, 44.9789745 | Fair directions + Google place/address |
| 9260.1 | The Strawberry Patch | -93.1756591, 44.9792484 | Fair directions + Google place/address |
| 3983.1 | Sweet Martha's Cookie Jar (Carnes) | -93.1715896, 44.9797695 | Fair directions + operator site + Google place/address |
| 12742.1 | 1919 Root Beer | -93.1703352, 44.9809803 | Fair directions + operator location + Google place/address |
| 2348.1 | The Frontier | -93.1747221, 44.9797269 | Fair directions + operator profile + Google place/address |
| 3060.1 | Pickle Dog | -93.1750532, 44.9797389 | Fair directions + operator profile + Google place/address |
| 10877.1 | Midway Mens Club | -93.1702901, 44.9816890 | Fair directions + operator location + Google place/address |
| 3398.1 | Summer Lakes Boat House | -93.1707496, 44.9840099 | Fair directions + operator location + Google place/address |
| 3790.1 | The Hideaway Speakeasy | -93.1738435, 44.9812464 | Fair directions + operator location + Google place/address |
| 12663.1 | dodopop | -93.1689113, 44.9814170 | Fair directions + operator fair page + exact Google fairgrounds place pin |
| 2437.1 | Green Mill | -93.1688826, 44.9841057 | Fair directions + exact Green Mill State Fair Pizza Truck place pin |
| 2582.1 | Java Jive | -93.1750625, 44.9806875 | Fair directions + exact 1805 W Dan Patch address and plus code |
| 7388.1 | Afro Deli & Grill | -93.1694400, 44.9803502 | Fair directions + operator site + exact Food Building east-wall place pin |
| 5146.1 | BABA'S | -93.1708125, 44.9846875 | Fair directions + exact 1500-1520 Underwood address and plus code |
| 2067.1 | Charcoal Hut | -93.1690625, 44.9785625 | Fair directions + exact 1646 Judson address and plus code |
| 3386.1 | Strawberries 'N Creme | -93.1707470, 44.9840020 | Fair directions + exact, distinct Google place pin |

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

## Fifty-record verification batch 01

The first 50 unverified medium-priority records were reviewed on 2026-08-29.
Three exact, independently supported booth positions were corrected; 47 were
left unverified because the available results were generic, duplicated,
off-site, building-level, or otherwise not record-specific. The complete
record-by-record decision trail is in
`audit/vendor-verification-batch-2026-08-29-50-01.csv`.

The second 50-record batch reviewed the remaining 34 unverified medium-priority
records and the next 16 low-priority records. Four exact positions were
corrected and 46 records remained unverified because no record-specific booth
pin was available. Its decision trail is in
`audit/vendor-verification-batch-2026-08-29-50-02.csv`.

## Audit state after remediation

- 278 total vendor records; 278 unique IDs
- 62 verified and compass-eligible
- 2 approximate and compass-ineligible
- 12 missing/quarantined and compass-ineligible
- 202 present but not independently verified and compass-ineligible
- 83 street-corridor heuristic leads remain; these are review
  prompts, not proven errors and were not used to move pins
- No unquarantined high-priority peer-location conflicts remain

This is not a claim that 100% of coordinates are correct. It is a controlled
state in which proven corrections are published, directly conflicting pins are
blocked, and every remaining coordinate is labeled according to its evidence.
