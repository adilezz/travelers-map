# Tier calibration against the golden set

176 golden rows resolve to a place; the gate needs zero violations of `min_tier`, `max_tier` and `not_above`. Parameters are searched on the golden set only, never on H1.

`tiers.json` when run: **18 violations**; tier shares (1.1674898967220475, 6.847777278850471, 32.622361921867984).

- G004 Abu Simbel: Major, needs Icon+
- G015 Cusco: Major, needs Icon+
- G019 Colca Canyon: Local, needs Major+
- G037 Lake Como: Notable, needs Major+
- G060 Nyerere National Park (Selous): Local, needs Notable+
- G095 Katavi National Park: Local, needs Notable+
- G104 Erg Chebbi (Merzouga): Local, needs Major+
- G108 Toubkal: Local, needs Major+
- G113 Ouzoud Falls: Local, needs Notable+
- G130 Picos de Europa: Notable, needs Major+
- G136 Timanfaya National Park: Notable, needs Major+
- G147 Loire Valley: Notable, needs Major+
- G148 Chamonix and Mont Blanc: Notable, needs Major+
- G149 Provence (Luberon): Notable, needs Major+
- G150 French Riviera: Notable, needs Major+
- G153 Lourdes: Notable, needs Major+
- G155 Alsace Wine Route: Local, needs Notable+
- G166 Cappadocia: Major, needs Icon+

## Lowest violations (ties by the smallest Icon plus Major share)

| violations | Icon % | Major % | Notable % | protected R | pageview weight | Icon 4/6/8 steps | major next | notable p |
|---|---|---|---|---|---|---|---|---|
| 12 | 1.2 | 8.2 | 37.1 | 0.8 | 1.0 | (4, 6, 8) | 40 | 60 |
| 12 | 1.4 | 8.1 | 37.2 | 0.5 | 1.0 | (5, 7, 9) | 40 | 60 |
| 12 | 1.4 | 8.1 | 37.0 | 0.8 | 1.0 | (5, 7, 9) | 40 | 60 |
| 13 | 1.2 | 6.9 | 38.2 | 0.8 | 1.0 | (4, 6, 8) | 30 | 60 |
| 13 | 1.4 | 6.8 | 38.1 | 0.8 | 1.0 | (5, 7, 9) | 30 | 60 |
| 13 | 1.2 | 8.2 | 37.3 | 0.5 | 1.0 | (4, 6, 8) | 40 | 60 |
| 13 | 1.2 | 8.2 | 32.0 | 0.8 | 1.0 | (4, 6, 8) | 40 | 75 |
| 13 | 1.4 | 8.1 | 31.9 | 0.5 | 1.0 | (5, 7, 9) | 40 | 75 |
| 13 | 1.4 | 8.1 | 31.9 | 0.8 | 1.0 | (5, 7, 9) | 40 | 75 |
| 14 | 1.0 | 8.3 | 37.2 | 0.8 | 1.0 | (3, 5, 7) | 40 | 60 |
| 14 | 1.2 | 8.1 | 37.0 | 0.8 | 0.5 | (4, 6, 8) | 40 | 60 |
| 14 | 1.2 | 8.2 | 32.0 | 0.5 | 1.0 | (4, 6, 8) | 40 | 75 |
| 14 | 1.2 | 8.2 | 37.4 | 0.2 | 1.0 | (4, 6, 8) | 40 | 60 |
| 14 | 1.4 | 8.1 | 36.9 | 0.8 | 0.5 | (5, 7, 9) | 40 | 60 |
| 14 | 1.4 | 8.1 | 37.3 | 0.2 | 1.0 | (5, 7, 9) | 40 | 60 |

## Violations against the cost in Icon and Major places (cheapest setting per violation count)

| violations | Icon % | Major % | protected R | pageview weight | Icon steps | major next |
|---|---|---|---|---|---|---|
| 12 | 1.2 | 8.2 | 0.8 | 1.0 | (4, 6, 8) | 40 |
| 13 | 1.2 | 6.9 | 0.8 | 1.0 | (4, 6, 8) | 30 |
| 14 | 1.0 | 8.3 | 0.8 | 1.0 | (3, 5, 7) | 40 |
| 15 | 1.4 | 5.5 | 0.8 | 1.0 | (5, 7, 9) | 20 |
| 16 | 1.2 | 5.6 | 0.8 | 1.0 | (4, 6, 8) | 20 |
| 17 | 1.2 | 5.6 | 0.5 | 1.0 | (4, 6, 8) | 20 |
| 18 | 1.0 | 5.6 | 0.8 | 1.0 | (3, 5, 7) | 20 |
| 19 | 1.2 | 5.5 | 0.5 | 0.5 | (4, 6, 8) | 20 |
| 20 | 1.0 | 5.6 | 0.5 | 1.0 | (3, 5, 7) | 20 |
| 21 | 1.0 | 6.9 | 0.8 | 0.5 | (3, 5, 7) | 30 |
| 22 | 1.0 | 5.6 | 0.8 | 0.5 | (3, 5, 7) | 20 |
| 23 | 1.0 | 5.6 | 0.5 | 0.5 | (3, 5, 7) | 20 |
| 24 | 1.2 | 5.6 | 0.5 | 1.0 | (4, 6, 8) | 20 |
| 25 | 1.2 | 5.5 | 0.5 | 0.5 | (4, 6, 8) | 20 |
