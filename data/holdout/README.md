# Holdout H1: how to write it

H1 is the one measure of recall that does not come from the same signals the pipeline uses. It only works if it stays independent. Rules:

1. **At least 100 rows that are not in the golden set, 20 per country, for the prototype: 20 each for Morocco, Spain, France, Italy and Türkiye** (decision D24; Egypt, Peru, Jordan and Tanzania are calibration countries with golden rows only). The bundle can only be judged on countries it contains.
2. **From your own knowledge.** Places you know, have been to, or would insist someone sees. Do not copy from a guidebook site, a ranking, or Wikipedia lists, and **do not use an AI assistant**: that would reintroduce the signals the pipeline uses.
3. **Disjoint from the golden set.** Do not open `data/golden/golden.csv` while writing. The gate rejects any H1 row that matches a golden row by name or location (within 1 km), so overlap is caught, but avoiding it by looking is the very thing to avoid.
4. **Do not look at pipeline output** until H1 is frozen.
5. **Mix on purpose.** At least a third of the rows should not be a monument or a heritage site: a town, a beach, a trail, a market, a food place, a viewpoint, a small village you loved. The pipeline's weakest area is the everyday traveler's place.
6. **Write in batches of 20**, one country at a time.
7. Columns are those of `H1.csv` (same as the golden set): `golden_id` (use H001…), `country`, `iso3`, `expected_name`, `aliases`, `row_kind` (`positive`), `type`, `lat`, `lon` (3 decimals from a map, good to about 1 km), `tol_km` (3 for a site, 5–8 for a settlement, 10–30 for an area), `min_tier` (use `Local` unless you are sure), `kinds_expected` (1–3 of the 14 kinds in `data/rules/kinds.csv`: capital, old_town, seaside, maritime, mountain, desert, forest, water, volcanic, wildlife, sacred, rural, metropolis, ruins), and a note on why. Leave `qid` blank.
8. **Freeze it** when done: `python -m atlas.freeze` (from `pipeline/`, with `PYTHONPATH=.`). From then on any edit is detected. To change it deliberately, delete `data/freeze.json` and say why in `docs/decisions.md`.

It is fine that this is hand work. A rough list of 100 places you care about is worth more than any amount of tuning against the golden set.

## Status (2 Oct)

The owner's first list had 150 rows (30 per country). 53 coincide with golden rows (the obvious cities: Paris, Rome, Marrakech...), which is natural but breaks the "disjoint" rule. They are kept in `H1_overlap.csv` (with the reason) as a separate, easy-recall check; `H1.csv` holds the 97 disjoint rows. On 3 Oct six more were added from the owner's list (Boumalne Dades, Debdou, Gijón, Mombeltrán, Formigal, Amasra; Imlil, Ifrane and Safranbolu were already golden rows). 103 rows now: France 24, Italy 22, Spain 20, Türkiye 19, Morocco 18. Still to add for 20 per country: Morocco +2, Türkiye +1, none of them in the golden set. Then run `python -m atlas.freeze`. Coordinates marked approximate must be checked on the map before freezing.
