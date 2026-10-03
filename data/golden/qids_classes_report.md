# `make qids` and `make classes` — run of 2026-10-03

## make classes — 2 mismatches in data/rules/classes.csv

| Class QID | Wikidata label now | classes.csv expects | Likely cause |
|---|---|---|---|
| Q1370598 | structure of worship | place of worship | label change |
| Q5119 | capital city | capital | label change |

Not edited; the owner decides whether to update `expected_label` or investigate.

## make qids — data/golden/qid_candidates.csv

184 positive golden rows resolved to candidates (1,763 candidate rows). Nothing was accepted automatically.

| Per golden row | Count |
|---|---|
| exactly one strong nearby candidate (`unique`) | 74 |
| several strong nearby candidates (`ambiguous`) | 103 |
| only weak nearby candidates (`near`) | 1 |
| nothing nearby (`far` only / none) | 6 |

Nothing nearby: G016 Sacred Valley (Ollantaytambo), G018 Lake Titicaca (Puno), G023 Iquitos, G048 Dead Sea (Jordan shore), G053 Karak Castle, G125 Camino de Santiago.

`unique` rows where the label did not match the expected name (check these before accepting):
G040 Q636774 Valle dei Templi; G056 Q1217726 Ngorongoro Conservation Area (14 km); G066 Q856665 Gombe National Park;
G073 Q6562520 Wadi Elrayan (15 km); G089 Q219279 (no English label); G091 Q977740 Amotape Hills National Park (20 km);
G093 Q1404282 Kondoa Rock Art Sites; G147 Q13947 Centre-Val de Loire (58 km, likely wrong for "Loire Valley"); G162 Q501726 Dune of Pilat.

## Next step (owner)
Write `data/golden/qid_decisions.csv` (`golden_id,qid,decision,note`), then `python -m atlas.qids apply`.

## How it was run
No `make` on this machine, so the Python modules were run directly. The Wikidata SPARQL service was rate-limiting to 1 request/min
(outage), so the UNESCO-ID lookup used the normal search API (`haswbstatement:P757=<id>`) instead; same result for the check made (WHS 89 → Q1100964).
Repo code is unchanged.
