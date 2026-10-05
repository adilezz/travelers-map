# M1 extraction plan

Written 5 October 2026. M1 is the backbone: pinned inputs, the Wikidata prototype subset for the nine countries, the other small sources, the `asset` table and the registry. Nothing is minted until the landmark gate passes on real QIDs (D21); the golden set now has all 184 QIDs (D27), so the gate can run as soon as a first bundle exists.

## Done when

1. Every input is pinned in `data/inputs/MANIFEST.json` with a snapshot date and a SHA-256, and `make pin-check` passes.
2. A first bundle for the nine countries exists and `make verify` runs every gate that can run, with `G-LANDMARK` and `G-IDENT` on real QIDs.
3. `G-LANDMARK` is at least 95 % with zero regression rows missed. Only then is the registry committed and ids minted.
4. The numbers the plan guessed (rows per family, run time, size) are replaced by measured ones in this file.

## Stages

| Stage | What | Tool | Where | Output | Pinned as |
|---|---|---|---|---|---|
| S0 | Pin inputs by hash | `atlas.snapshot` | anywhere | manifest entries | every source |
| S1 | **Wikidata discovery**: for each of nine countries, items with a coordinate, grouped by the 24 classes in `classes.csv` and by sitelink band (40+, 15 to 39, 8 to 14); cities of 100,000 or more; every item with a World Heritage or protected-area id; airports, stations, ferry terminals. 693 paged queries | `atlas.extract` (done, tested on recorded responses) | needs `query.wikidata.org` | JSONL per query with the query text, run time and row count, then Parquet per family | `wikidata_sparql` |
| S2 | **Wikidata details** for the candidates that survive S1: labels and aliases in the needed languages, located-in and part-of, capital and inception dates, heritage designations, the site's official URL, redirect targets for merged items | `atlas.details` (next) | needs `www.wikidata.org` | Parquet | `wikidata_sparql` |
| S3a | World Heritage list | already local (`whs_properties.csv`); add the criteria and serial-component table from the UNESCO XML | `whc.unesco.org` | asset rows | `unesco_whs` |
| S3b | Protected areas (IUCN, polygons) | WDPA download for the nine countries (login and terms on the site, so the owner downloads) | owner | asset rows, restricted | `wdpa` |
| S3c | Ramsar, GeoNames, Natural Earth, geoBoundaries | direct downloads, megabytes | `rsis.ramsar.org`, `download.geonames.org`, Natural Earth and geoBoundaries hosts | asset rows and the land and admin-1 polygons | one entry each |
| S3d | OpenStreetMap regional extracts for the nine countries | Geofabrik, a few GB, filtered to tourism, historic, natural, place and transport tags | `download.geofabrik.de` | asset rows, restricted (ODbL) | `osm` |
| S4 | Pageviews: 12 monthly files, kept only for candidate titles | stream and filter | `dumps.wikimedia.org` (large files, so the laptop or a rented machine) | 12 monthly values per title | `wikipedia_pageviews` |
| S5 | Admission R1 to R6, notability *N*, tiers, kinds, edges, nodes | pipeline stages (M2) | anywhere | first bundle | build manifest |
| S6 | Registry: mint ids for the admitted places | `atlas.minting` after `G-LANDMARK` passes | anywhere | `place_registry.parquet`, committed | git |

## Order and effort

1. **S1 first, today.** It is the only stage that decides what the golden set can be matched against. About 693 queries at a polite one or two seconds each; I estimate 30 to 90 minutes if the public endpoint behaves, and the run is resumable.
2. **S2 and S3a** while S1 runs: the details module and the UNESCO serial table need no network.
3. **S3b to S3d**, one source at a time, each pinned as it lands.
4. **S4 last**, because it is the biggest download and only matters for *N* and tiers.
5. Then M2: the first bundle, `make verify`, and only then the registry.

## Where it runs

Wikidata cannot be reached from the Claude container today (the proxy answers 403), so two routes work:

- **Preferred:** in the environment settings (cloud environment menu in the session title bar, then Edit, Network access, Custom), add these allowed hosts: `query.wikidata.org`, `www.wikidata.org`, `download.geonames.org`, `download.geofabrik.de`, `rsis.ramsar.org`, `whc.unesco.org`, and the Natural Earth and geoBoundaries download hosts. Then I run S1 to S3 myself, and nothing has to travel through git. Pageviews and the full dump stay off this route: they are too large.
- **Fallback:** the owner runs `make extract` and `make extract-pack` on the laptop (about an hour), and pushes the Parquet files, which `data/raw/` keeps out of git by default. If the total is under about 50 MB, add them with `git add -f data/raw/wikidata/<date>/*.parquet`; if larger, upload them as a release asset and send the link.

## Risks and how the plan answers them

| Risk | Answer |
|---|---|
| The public endpoint times out or rate-limits | Small paged queries, backoff on 429 and 5xx, resumable files; a failed query is listed and retried alone |
| Items with no `P17` (country) are missed | S2 adds a second pass by located-in (`P131`) for the golden places and a recall check; a golden place missing from S1 fails the run loudly |
| Sitelink counts drift between runs | Every file records its run time; the subset and a later full dump are different pinned inputs, and `G-ID` with the previous bundle checks that ids do not move |
| The class table is unverified | S1 is organised by class, so a wrong class costs one file; the table is reviewed against the first rows before S5 |
| Volume in villages (Türkiye, France, Italy) | The sitelink floor of 8 keeps the village class small; below it only R3, R1 or an anchor can admit a place, and those have their own queries |
| Western Sahara | Items under Q6250 are extracted with Morocco and carry `disputed: ESH` (D-ruling in document 4 §7) |
| Licence | WDPA and OSM stay `restricted`; a shareable bundle excludes them by gate |

## Commands (from the repository root)

```
make extract-plan                  # what would be asked; nothing sent
make extract OUT=data/raw/wikidata/2026-10-05
make extract-pack OUT=data/raw/wikidata/2026-10-05    # checks completeness, writes Parquet, pins
make pin-check
```
