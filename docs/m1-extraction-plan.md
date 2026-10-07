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

## First result (5 October)

The owner's first S1 run produced 35,642 distinct QIDs (class 88,485 rows, institutional 13,755, nodes 7,580, big cities 1,468) in 2.4 MB of Parquet. Measured against the golden set, **145 of 184 golden QIDs (79 %) were found**; the floor is 95 % (`make recall`, report in `data/golden/s1_recall.md`). The misses showed one defect in the queries, not in the data: most Spanish and French cities (Madrid, Seville, Valencia, Marseille...) and several Italian towns were missing because their Wikidata classes ("municipality of Spain", "commune of France") are not subclasses of the classes in `classes.csv`, so a class-bound query never saw them. Fix, already in `atlas.extract`: two class-free families (`popall`, every item with 100,000 inhabitants; `attention`, every item with 40 or more sitelinks, keeping its classes) so that rule R2 and R3 are not limited by the class table. The extraction must be re-run for these 36 new queries (the old ones are skipped); then `make recall` again. A golden place still missing after that is a finding about the golden evidence (for example Imlil, which probably has fewer than 15 sitelinks) and is recorded, not patched.

Only the Parquet files are pinned; the JSONL files are local intermediates.

### Second result, a wrong diagnosis, and the real cause

After the class-free families, 174 of 184 golden QIDs were found (94.6 %, just under the 95 % floor). I first blamed a missing country (`P17`) on the ten misses and wrote a `locatedin` family. **That diagnosis was wrong**: I had inferred it from the S2 details, which show "located in" parents, without reading the items' country claims. The owner's check of the ten items in Wikidata showed every one has a country and a coordinate, and the `locatedin` queries timed out on France, Spain and Italy and added about one row. The family is removed.

The real cause is the sitelink floor. The ten misses have 6 to 32 sitelinks (Dalt Vila 6; Todgha Gorge 15; Imlil 15; Kerak Castle 20; Erg Chebbi 23; Gavarnie 24; Ölüdeniz 25; Umm Qais 26; Colca Canyon 28; Sacred Valley 32), below the attention floor of 40, and their classes (castle, canyon, cirque, oasis) are not in the class table. Admission rule R4 admits an item with 15 or more sitelinks plus one independent signal, so the extraction must reach 15 whatever the class: `attention` now has two more bands, 25 to 39 and 15 to 24 (18 more queries; volume is larger, so France, Spain and Italy may need the paging to run longer).

Two findings were about the golden set, not the queries. The owner ruled on 6 October (D31): the Ibiza row now names the World Heritage property (item `Q52631`, type area), and the Gavarnie cirque belongs to France with the transboundary property as evidence on it. The text below is the question as it was put:

- **Dalt Vila (G141)** has 6 sitelinks, and its World Heritage item is the island item `Q52631` ("Ibiza", property 417, 104 sitelinks). A pipeline that admits World Heritage properties by id (R1) will produce a place for Ibiza, not for Dalt Vila. Either the row should name the property, or it is a known miss.
- **Gavarnie (G159)**: the cirque (`Q1093112`, 24 sitelinks) will now be found, but the World Heritage property it belongs to is `Q3411434` ("Pyrénées – Mont Perdu", property 773), which Wikidata lists under both France and Spain. Under D25 a part of a serial property is an asset of the property's place; which of the two is the golden place needs a ruling.

### The France split (6 October)

The public endpoint cuts a query at 60 seconds. France's `attention` band 25 to 39 returned a 504 whole, and again for its 35 to 39 part, so the owner assembled the file from the slices 25 to 29, 30 to 34 and 35 to 39 by hand. That is now in the code (`SPLITS` in `atlas.extract`): the job keeps the same file name and is asked as three slices that are joined into it, with the slice queries recorded in the file's header. A fresh run elsewhere therefore no longer fails the same way, and the Parquet and the pins do not change. If another band times out, add it to `SPLITS`.

After the second run the recall is **184 of 184** (`data/golden/s1_recall.md`).

### Finding: ordinary municipalities clear R2 (6 October)

With the attention floor at 15, the S1 files hold 13,729 French communes, 7,727 Italian comuni and 3,075 Spanish municipalities **with 40 or more sitelinks**, the threshold of admission rule R2. An ordinary French commune has 33 to 45 sitelinks (the count peaks at 36 to 38): bot-generated Wikipedias (Cebuano, Swedish, Waray and others) give almost every municipality a baseline of about 35 articles. So R2 as written would admit about 24,000 ordinary municipalities from three countries, which is exactly the v1 failure (towns as places), and the sitelink term in the notability value *N* is dominated by that baseline. Paris has about 300; the real discriminating range is above 60 (734 in France), where Mont-Saint-Michel and Chamonix sit.

The fix cannot be a bigger threshold alone. Next step, built and waiting for the owner's run: `make profile` fetches **which** Wikipedias carry each of the 85,776 candidates (about 1,700 requests), so the signal can be recomputed from the editions that humans actually write (for example the 20 to 30 largest, non-bot editions) and calibrated against the golden set, H1 and the pairs file. Decisions that follow (the R2 threshold, the form of the sitelink term in *N*, whether R2 should look at class-relative rank) wait for that evidence.

### Calibration result (7 October): a class-relative signal works

The profiles show that the bot baseline is the whole story for ordinary municipalities: a commune has an article in about 25 Wikipedias (French, German, English, Spanish, Ukrainian, Polish, Cebuano, Swedish, Waray and so on) before anyone has written anything about it. `atlas.signal` therefore scores each item by **discrimination** D, the sum over its Wikipedias of (1 minus the share of its class that has that Wikipedia), and ranks it **within its class in its country** (the classes with at least 1,000 members). Result on the real data (`data/golden/s1_signal.md`, `make signal`): admitting the top 2 % of each municipal class by D admits 1,028 municipalities (France 748, Italy 156, Spain 124) instead of about 24,000, and all 33 golden municipalities are admitted (the lowest is Alberobello, at the 98.1st percentile; at the top 1 % Alberobello and Orvieto would fall out). **The owner chose 3 % on 7 October (D32) for a safety margin: 1,543 municipalities (France 1,122, Italy 235, Spain 186), all 33 golden ones admitted**. A plain absolute threshold cannot do this: Toubkal, Imlil and Todgha Gorge have the same D as an ordinary commune, but they are not in a mass class, so the plain floors apply to them.

Proposed rule R2 (for the owner's approval, then document 1 section 5): an item of a mass class is admitted by attention only in the top 2 % of its class in its country by D; any other item with 15 or more sitelinks keeps the plain floor (40 for R2, 15 with one independent signal for R4). Pageviews (S4) will refine this for municipalities, so S4 shrinks to a few thousand titles through the Wikimedia per-article API instead of 45 GB of monthly dumps.

## S2: details (built 5 October)

`atlas.details` selects the QIDs worth describing (15 or more sitelinks, 100,000 or more inhabitants, a World Heritage or protected-area id, a transport node, or a golden place): 24,875 QIDs, about 500 requests of 50. For each it keeps English and local labels and aliases, the English description, instance-of, located-in, part-of, heritage designations, capital-of with an "ended" flag (current against former capital), inception and dissolution years, the official site, the English Wikipedia title (the key to pageviews), and `redirected_to` when Wikidata has merged the item since the extraction. Resumable; failed batches are listed. Commands: `make details`, then `make details-pack`.

## First admission pass (7 October)

`python -m atlas.admit` builds `build/first` (git-ignored): 3,732 places (FRA 1,489, ITA 865, ESP 522, TUR 416, EGY 152, PER 93, MAR 87, TZA 73, JOR 35). G-LANDMARK is 155 of 184 (84.2 %); `data/golden/first_pass.md` lists the 29 misses: 21 have no place-like class in `data/rules/types.csv` (regions, valleys, canyons, oases, islands), 8 fall below the floors (no independent signal for R4, WDPA not yet ingested). Next: owner runs `make classlabels`, the typing table is widened, absorption (D25) and kind rules follow, then S3 (WDPA, Wikivoyage) and S4 (pageviews). Ids stay provisional until G-LANDMARK passes.

## Order and effort

1. **S1 first, today.** It is the only stage that decides what the golden set can be matched against. About 693 queries at a polite one or two seconds each; I estimate 30 to 90 minutes if the public endpoint behaves, and the run is resumable.
2. **S2 and S3a** while S1 runs: the details module and the UNESCO serial table need no network.
3. **S3b to S3d**, one source at a time, each pinned as it lands.
4. **S4 last**, because it is the biggest download and only matters for *N* and tiers.
5. Then M2: the first bundle, `make verify`, and only then the registry.

## Where it runs (decided 5 October 2026, D30)

| Work | Where | Cost |
|---|---|---|
| **Prototype**: S1 to S3 for the nine countries, S2 details, small sources | **The owner's laptop** | $0 |
| **World build**: the full Wikidata dump, pageviews, planet-scale OSM if a gate demands it | **A Hetzner Cloud CAX41, rented by the hour for the job and deleted afterwards** | about €1 to 5 for the run (estimate; see below) |

Why the CAX41: 16 ARM vCPU and 32 GB RAM at a few cents an hour, the best quality for the price of the options compared on 5 October. Python, `orjson`, `lbzip2` and DuckDB all run on ARM. Hetzner repriced its cloud on 15 June 2026 (the x86 dedicated line rose by more than 100 %), so any figure older than that is wrong; check the live price in the console before creating the server. A CCX33 (x86, 8 dedicated vCPU, about $0.25 an hour) is the fallback if an ARM build of a tool is missing. Other options considered and not chosen: AWS spot (interruptible), Vultr and OVHcloud (about $0.31 to 0.33 an hour), Oracle's free tier (cut to 2 cores and 12 GB in June 2026, too slow).

### Laptop runbook (prototype)

From the repository root, on a machine that can reach `query.wikidata.org`:

```
git pull
pip install duckdb                         # the only dependency beyond the standard library
make extract-plan                          # optional: read the first query
make extract OUT=data/raw/wikidata/2026-10-05
make extract-pack OUT=data/raw/wikidata/2026-10-05   # checks completeness, writes Parquet, pins
```

`make extract` is resumable: if it stops, run the same command and only the unfinished queries are sent. It prints one line per query and a failed list at the end. Expect 30 to 90 minutes if the public endpoint behaves. The raw files stay out of git (`data/raw/`). When the run is complete, push the manifest and the Parquet files:

```
git add data/inputs/MANIFEST.json
git add -f data/raw/wikidata/2026-10-05/*.parquet    # if the total is under about 50 MB
git commit -m "Wikidata prototype extraction, 2026-10-05" && git push
```

If the Parquet files are larger, upload them as a release asset and send the link instead. Then I run S2 and the rest from the committed files.

### World-build runbook (later, on the CAX41)

Not started until the prototype bundle passes `G-LANDMARK`. Outline, to be turned into a script and tested before any server is created:

1. Create the server in the Hetzner console (CAX41, an EU location, Ubuntu, 100 GB of disk is enough because the dump is streamed and never stored) with your SSH key. Note the hourly price shown.
2. Install `lbzip2`, `curl`, Python and DuckDB. Stream the dump through `curl | lbzip2 -dc | filter` so the 90 to 110 GB file is never written to disk; the filter keeps only items with a coordinate or a World Heritage or protected-area id, and writes Parquet.
3. Stream the 12 monthly pageview files the same way, keeping only candidate titles.
4. Copy the filtered Parquet and the manifest back to the laptop, pin them, and **delete the server the same day**. A server left running is the only way this costs real money.

The estimate of 4 to 12 billable hours is mine, not a measurement; the first run replaces it here. The truthy N-Triples dump is smaller (about 35 to 39 GB) but may lack sitelink counts; check before choosing it.

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
