# Travelers World Map — Database Architecture and Pipeline

Document 2 of the v2 set. Version 2.0, 1 October 2026. Reads with document 1 (the place model) and document 3 (validation).

This document is the contract for how the place database is stored, identified, built, versioned and published. Code under `pipeline/` implements it. Where code and this document disagree, this document wins and the code is wrong.

---

## 1. Constraints and strategy

The project is personal. Money and licensing do not bound the design; effort and correctness do. The cost strategy is therefore:

- **Bulk dumps, processed once, on one machine.** No per-request fees, no API in the build path.
- **Pin every input.** A build is reproducible from named snapshots.
- **Filter early.** Stream the large dumps once into small columnar files; everything after runs on a laptop in minutes.
- **One store.** One DuckDB file is the truth; every published file is generated from it.
- **Free first, paid on proof.** A paid source (an imagery licence, a routing API, a curated dataset) is added only when a gate shows free data cannot pass it.

### 1.1 Licensing posture

Personal use removes licensing as a *design* constraint, not as a *record*. Every asset still carries `source`, `source_url`, `licence` and `retrieved`, so that a future decision to share, publish or sell the atlas is a filter on the data and not a rebuild. Share-alike (OSM ODbL) and non-commercial (WDPA) sources are marked `restricted: true` in the source table. A `--shareable` build flag excludes them. The owner commits that Google Places data is **never** stored or cached; only an optional place identifier may be kept, and only to link out.

## 2. Stages

```
 0 snapshot      pin and hash raw inputs
 1 ingest        stream dumps into filtered Parquet
 2 candidates    class table → candidate entities
 3 assets        every source record → asset
 4 resolve       identity: match, merge, link (QID first)
 5 admit         rules R1–R6 → places; review queue
 6 enrich        names, aliases, geometry, admin units, links
 7 notability    N, tiers
 8 kinds         rules → place_kind; validate
 9 territories   countries, regions, printed pieces
10 print select  document 4
11 gates         document 3: any failure stops here
12 publish       bundle, manifest, report, registry commit
```

Each stage is an idempotent script that reads tables and writes tables. Nothing mutates a source file. Stages 0–1 are slow and run rarely; stages 2–12 run in minutes.

### 2.1 Snapshot (stage 0)

`inputs/MANIFEST.json` records, for each source: name, version or dump date, URL, byte size, SHA-256, licence, `restricted`. A build refuses to start if a pinned file's hash differs. Raw files live outside git (`data/raw/`); the manifest is committed.

### 2.2 Sources

| Source | Feeds | Use |
|---|---|---|
| Wikidata full dump | Candidates, QIDs, classes, sitelinks, coordinates, capitals, population, redirects | Backbone of identity |
| Wikipedia pageview dumps (12 months) | `PV` in notability | Current attention, damped |
| Wikipedia language links | `SL` | Cross-language significance |
| Wikivoyage dump | Corroboration (R4), kinds, "why go" text | Destinations and sections |
| UNESCO World Heritage List (+ criteria) | R1, `R`, kinds | Authoritative inscriptions, per-state parts |
| UNESCO intangible heritage lists, biosphere reserves, global geoparks | R1, `R`, kinds | Living culture |
| WDPA (with polygons) | R1, kinds | IUCN I–VI, full geometry, categories V and VI included |
| Ramsar Sites Information Service | R1, kinds | Wetlands |
| GeoNames (cities, `alternateNamesV2`) | Settlements, names, aliases, `name_local` | |
| OSM via regional extracts | Names, footprints, tourism density, OSM id | Planet only where a gate demands |
| Natural Earth, geoBoundaries | Land, admin-1, coastline, relief | Territories and print base |
| GHSL | Population and urban extent (context only) | Not a candidate source |
| Overture Places | Second opinion on duplicates | Never a seed |

Sources considered and **not** used as automated inputs: commercial guidebook and review sites (terms of use, and scraping is not repeatable). The owner may add what they know through `anchors.csv`.

### 2.3 Wikidata handling

- Stream the dump once; keep items that have a coordinate, or a WHS/WDPA/Ramsar identifier, and an instance-of chain reaching a class in `rules/classes.csv`. Store the filtered items as Parquet. The raw dump is never queried again.
- **Redirects and merges.** Wikidata merges items. Each snapshot's redirect table is stored; the registry (3.2) resolves any QID to its current target before matching, so a merged item never mints a second place.
- **Labels.** Keep English label, label in the country's official language(s), and aliases. A raw QID is never a name (7, gate G-NAMES).

### 2.4 Where the ingest runs

Decided 1 October 2026: **the owner's laptop first, with a SPARQL subset for the prototype; a short-lived rented machine only for the full dump.** Figures are estimates until the first real run replaces them here.

| Step | Where | Why |
|---|---|---|
| Prototype, five countries: page Wikidata's public SPARQL endpoint by country; store the results as Parquet with the query text and run date | Laptop, minutes to hours | Small, and enough to pass the golden set |
| Small sources: WDPA, Ramsar, GeoNames, UNESCO, Natural Earth, Geofabrik extracts | Laptop | Megabytes to a few GB |
| Pageviews | Laptop, filtered to candidate titles while streaming | Monthly files are large; only candidate titles are kept |
| Full Wikidata dump, for the world build | A rented machine (about 8 vCPU, 32 GB RAM, 500 GB disk, roughly a day), or the laptop if it has about 300 GB free and can run overnight | Hundreds of GB compressed; the cost is small and one-off; only the filtered Parquet comes back |
| Optional accelerator: allow the Claude cloud environment to reach named hosts | Environment settings, Network access | Lets Claude run ingest steps itself; bounded by that container's disk and run time, so suited to the prototype subset, not the full dump |

The SPARQL subset and the full dump are **different pinned inputs**. Keys are QIDs, which are stable between them, so ids minted from the subset must be unchanged when the full dump is built; G-ID with the previous bundle checks this. Sitelink counts drift on live SPARQL, so every run records its date and the values it returned.

## 3. Identity

### 3.1 `place_id`

`pl_` followed by 10 characters of Crockford base32, random, minted **once** when a place is first admitted:

```
pl_7k3m9q2x4f
```

An id encodes nothing: no country, source, version or build. It is never derived from a QID, GeoNames id or any upstream id, because those change. Prefixes can never collide because there are none.

### 3.2 The registry

`registry/place_registry.parquet` is committed to git and is the **only** source of identity. Append-only.

| Column | Meaning |
|---|---|
| `place_id` | Permanent |
| `keys[]` | Identity keys that have identified it: `qid:Q…`, `wdpa:…`, `geonames:…`, `osm:n/w/r…`. A World Heritage id is **not** an identity key: it names a property, and a serial property can back several places (Giza and Saqqara are both parts of property 86). It stays on the place as an evidence link |
| `status` | `active`, `retired`, `merged_into:<place_id>`, `split_from:<place_id>` |
| `minted_build`, `last_seen_build` | Audit |
| `tombstone_reason` | For retired |

Rules:

1. Each build resolves every admitted candidate to a registry row through its keys (QID first, then `wdpa`, `whs`, `geonames`, `osm`). A hit reuses the `place_id`; a miss mints one.
2. **A place that falls below a threshold keeps its id** with `status: retired`; if it re-qualifies later it is reactivated, not re-minted. A threshold change never changes an id.
3. A merge sets the loser to `merged_into:<survivor>`. Any visit record pointing at the loser resolves to the survivor.
4. A split mints a new id for the new part and records `split_from`; the original keeps its id.
5. An id is **never reused** for a different place, and **a key never moves to another id**: a key registered to two ids, or a place carrying a key registered to a different id, fails gate G-ID.
6. Owner state (visits, wishlist, notes, overrides) is keyed to `place_id` only and follows `merged_into` chains.

### 3.3 Crosswalk with v1

`registry/v1_crosswalk.csv` maps every v1 id (`MOR-c2555567`, …) to the v2 `place_id` that supersedes it, or to `none` with a reason. v1 ids that pointed to a town standing in for a landmark map to the landmark (Quillabamba → Machu Picchu, where it was the credited asset) *and* to the settlement if it is itself admitted. Any v1 visit record migrates through this file once.

## 4. Schema (DuckDB: `atlas.duckdb`)

```sql
source(source_id, name, version, url, sha256, licence, restricted, retrieved)

asset(asset_id, source_id, source_key, role, class, name, geom, point,
      attrs JSON, licence, source_url, retrieved)        -- every source record

place(place_id, type, name_en, name_local, country_iso3, admin1_id,
      lat, lon, footprint, tier, tier_reason, why, evidence_depth,
      qid, osm_id, geonames_id, wdpa_id, whs_id, wikipedia,
      near_place_id, disputed, status, minted_build)

place_asset(place_id, asset_id, link_method, confidence, role)
              -- link_method: qid | external_tag | containment | name_distance | owner
place_alias(place_id, alias, lang, kind)            -- kind: endonym|exonym|translit|former
place_kind(place_id, kind, rule_id, strength, evidence_asset_ids[])
place_metric(place_id, sitelinks, pageviews_12m, recognition, size_term, n_raw)
place_parent(place_id, parent_id, relation)          -- part_of | gateway_of

merge_log(build, loser_key, survivor_place_id, method, reason)
split_log(build, place_id, new_place_id, reason)
review_queue(build, candidate_key, signals, reason)

territory(territory_id, iso3, sovereign_iso3, kind, display_policy, ruling_ref, geom)
region(region_id, territory_id, name, geom)                   -- web regions, full tessellation
piece(piece_id, edition, territory_id, name, geom, printable, place_ids[])
print_selection(edition, place_id, hole_lat, hole_lon, reason, pinned_by)
print_override(place_id, action, note)               -- force_in | force_out | swap

build(build_id, started, manifest_sha, git_commit, params JSON, gates JSON)
```

Rules for the schema:

- `asset` carries **one row per source record**, with its own provenance. The v1 omission of an assets table is the reason no place could say why it existed.
- `place_asset.link_method` and `confidence` make every attachment auditable. `name_distance` matches below 0.8 confidence go to review, not to the bundle.
- `place_kind.evidence_asset_ids` is mandatory; a kind with no evidence cannot be written.
- `tier` is derived, never edited in place. Owner changes go through `anchors.csv`, `merge_overrides.csv` and `print_override.csv`.

### 4.1 Owner store and reserved tables

Decided 1 October 2026, because identity and schema are the only parts expensive to change later (the app will grow towards state-of-the-art trip planning and management).

**The owner store** holds the owner's own state in a separate file (`owner.duckdb`, or git-tracked CSVs), never inside the rebuilt `atlas.duckdb`. It is keyed to `place_id` and follows `merged_into` chains. Its schema is `pipeline/atlas/owner_schema.sql`:

| Table | Holds |
|---|---|
| `visit` | One row per visit: `visit_id, place_id, date_from, date_to, precision (day/month/season/year/unknown), source (manual/photo/takeout/gpx/import), party, rating (1–5, optional), note, photo_refs[], track_ref`. Visits are **events**: many per place, with fuzzy dates |
| `wishlist` | `place_id, priority, why_note, added` |
| `visit_candidate` | Visits suggested by photos (EXIF), Google Takeout or GPX tracks, to be accepted or rejected before they become visits: `place_id, evidence, confidence, status` |

Linking a photo or track to a place uses the place's **footprint**, not only its point, so every Icon and Major place needs a footprint polygon (an M2 target) and keeps `near_place_id`. Without it a photo at Machu Picchu snaps to the wrong town: the v1 failure again.

**Reserved shared tables** (in `schema.sql`; empty until their milestones):

| Table | Purpose |
|---|---|
| `place_crossref(place_id, scheme, value, valid_from, valid_to)` | Any future key scheme (Who's On First, a mapping provider's id) without a migration. A mapping provider's place content is never stored; only an id for linking out |
| `place_text(place_id, lang, kind, text, source_asset_id, model, frozen_build)` | Why-go text, tips and summaries, with provenance. Text written by a model is frozen data, never recomputed in a build |
| `place_season(place_id, month, score, source)` | Best months, from sourced climate and visitor data only |
| `travel_effort(place_id, from_hub, hours, mode)` | Access effort from a gateway, sourced |
| `place_stay(place_id, typical_stay_hours, source)` | Typical time needed |
| `place_activity(place_id, activity, rule_id, strength, evidence_asset_ids[])` | Experiences (dive, ski, trek, wine, festival…): what you do there, never a kind, never driving tier (document 1 §7.4) |
| `place_event`, `place_visitors`, `place_advisory`, `place_access`, `place_facet` | Dated events with a QID; **official** visitor statistics only; government advisories as dated, sourced facts with their issuer; effort class, elevation, ascent, wheelchair access; and an escape hatch for any later key/value dimension |
| `place_metric.pageviews_monthly` | Twelve monthly values, not only their sum, to see seasonality of interest |
| `asset.snapshot`, `source.redistributable` | The snapshot date on every asset; a flag a gate enforces so a shareable bundle contains no restricted source |

No review, rating or recommendation source feeds any shared table (document 1 §2.2).

## 5. Determinism

Same inputs and same parameters give byte-identical outputs.

- Inputs are pinned (2.1). Parameters live in `params.json`, hashed into the build record.
- Every sort has a total order; ties break on `place_id`, then `asset_id`. No unseeded randomness; any stochastic step takes the seed from `params.json`.
- Anything produced by a model (draft labels, text suggestions) is **data, frozen in a committed file** after review; it is never recomputed in a build.
- The build manifest records the SHA-256 of every output file.

## 6. Bundle, versions and updates

The pipeline publishes an immutable bundle:

```
bundle/<build_id>/
  manifest.json          build id, inputs, params, counts, gate results, hashes
  places/<ISO3>.json     per-country register (while the atlas is under ~25k places)
  places.geojson         point layer for the map (properties trimmed)
  regions.geojson        web regions
  territories.geojson    printed pieces for the current edition
  search.json            names, aliases, ids for client search
  report/                gate and report outputs
```

- Per-country JSON while the database is small; vector tiles when it approaches 25,000 places.
- **Incremental refresh.** A refresh is a new build from newer snapshots. `diff.json` lists added, retired, merged, renamed, re-tiered places. A **churn tripwire** stops publication if more than 2 % of places change tier or id without a recorded cause (a deliberate parameter change).
- **Rollback** is repointing the manifest.
- Refresh cadence is manual and rare (a few times a year, or when the owner decides).

## 7. Names

A place shows the name a traveler would search for.

1. `name_en` is the common English name: the Wikidata English label, then the English Wikipedia title, then GeoNames' main name. Registry titles and official long forms are aliases, not names.
2. `name_local` is preserved in the local script, never stripped.
3. Aliases include the endonym, exonyms, former names and transliterations; search matches them, accent-insensitively.
4. A name that is a raw identifier, contains markup or a control character, exceeds 60 characters, or is a protected-area designation in a local language, fails gate G-NAMES and goes to a naming review file for the owner.

## 8. Geometry

- Every place has an anchor point; `area` places may have footprints from WDPA or OSM.
- Territory and region polygons come from Natural Earth and geoBoundaries, with disputed treatment from document 4 §7.
- Web regions tessellate each country's land (every place sits in exactly one); printed pieces are a separate set. They share `place_id` and never polygons.

## 9. Repository layout

```
docs/                       the specifications and the decision log
data/
  inputs/MANIFEST.json      pinned sources; whs_properties.csv is the UNESCO list
  rules/                    classes.csv  kinds.csv  tiers.json
  anchors/                  anchors.csv  merge_overrides.csv  print_override.csv
  registry/                 place_registry.parquet  v1_crosswalk.csv
  golden/                   golden.csv  kind_labels.csv   (document 3)
  holdout/                  H1.csv  precision_review.csv   (document 3)
  scope.json  changelog.json  freeze.json                 committed, never written by a build
pipeline/atlas/             stage code, gates, schema.sql
pipeline/tests/             unit, adversarial and mutation tests
Makefile                    make test · make lint · make verify
```

`scope.json` (which countries are in the build, with any exemptions), `changelog.json` (the recorded causes that may explain large changes between builds) and `freeze.json` (the holdout's hash) are **committed inputs**. A build may not supply or edit them: a gate that reads its own scope from the bundle it is judging proves nothing.

`make verify` runs every gate against the **published bundle**, not the working directory, and any failure stops the publish.

## 10. Milestones

| Milestone | Delivers | Effort |
|---|---|---|
| M0 Docs and gates — **done, 1 Oct 2026** | These documents; golden set; schema DDL; gates as code with 47 tests; `make verify` fails until a bundle passes. Holdout H1 and the kind labels are templates the owner fills | 1 week |
| M1 Backbone | Snapshot manifest; QID resolver for the golden set (run on the owner's laptop); Wikidata prototype subset (SPARQL) to Parquet; registry (no ids minted until the landmark gate passes on real QIDs); `asset` table; WHS/WDPA/Ramsar ingested | 1 week |
| M2 Places | Candidates, resolution, admission, enrichment, names; landmark gate passes | 1–2 weeks |
| M3 Rank and kinds | Notability, tiers; kind rules; hand-labelled audit; bias audit | 1–2 weeks |
| M4 Print | Territories, regions, print selection, overrides, proof | 1–2 weeks |
| M5 Atlas | Web atlas on the bundle; migration of visits through the crosswalk | per document 5 |

The first prototype runs on **five countries — Egypt, Peru, Italy, Jordan, Tanzania** — and must pass the golden set for them before any other country is built. The world build follows only when the prototype passes.

### M0 as built

| Path | What it is |
|---|---|
| `atlas/vocab.py`, `geo.py` | The 14 kinds with labels and tie-break priority, 4 tiers, id and key formats; haversine, Wilson interval, accent folding |
| `atlas/golden.py` | Loads and validates the golden set (schema, tolerances, kinds, UNESCO ids, relation targets); requires the UNESCO list |
| `atlas/bundle.py` | Reads a bundle and validates its structure so gates never run on malformed records |
| `atlas/kinds.py` | Choosing kinds from the rules that fired: noisy-or over distinct sources, pair rules as data, total tie-break order, cut reasons, crowded flag |
| `atlas/snapshot.py` | Stage 0: pin raw inputs by SHA-256; refuse a build from anything that changed; a required source with no pin is a failure |
| `atlas/minting.py` | Mint, reuse, retire, merge and split ids by the registry rules; commit only after `G-LANDMARK` passes and every golden place has a real QID |
| `atlas/wikidata.py`, `qids.py` | A stdlib Wikidata client; proposes QIDs for the golden set and checks the class table against Wikidata labels. A QID is never accepted automatically. Run by the owner locally, tested here on recorded responses |
| `atlas/registry.py` | The registry reader (CSV or Parquet): key index, merge chains, key conflicts |
| `atlas/matching.py` | One-to-one matching of golden rows to places by ISO3, type, distance and QID or name; duplicate detection |
| `atlas/gates.py` | 16 gates plus 4 pending; each returns `n` and `skipped`; any exception is a failure |
| `atlas/verify.py`, `freeze.py` | `make verify`; freezing the holdout by hash |
| `atlas/schema.sql`, `owner_schema.sql` | The section 4 schema with CHECK constraints tied to the vocabulary, reserved tables included; and the separate owner store (4.1) |
| `data/golden/golden.csv` | 106 rows: 97 positive and 9 relational, five countries |
| `data/rules/tiers.json` | Initial admission, notability and tier parameters; `kinds.csv` holds 20 draft rules (uncalibrated), `kind_pairs.csv` the overlap rules, `activities.csv` the experience vocabulary; `classes.csv` is a header for M2 |
| `data/registry/` | Empty `place_registry.parquet` with its `keys` column |
| `pipeline/tests/` | 116 tests: an oracle bundle built from the golden set, adversarial fixtures (the v1 Quillabamba failure), a mutation suite, and a test that fails if a gate has no failing test |

Gates implemented: G-SCHEMA, G-GOLDEN, G-LANDMARK, G-TIER, G-ID, G-IDENT, G-NAMES, G-COUNT, G-KIND, G-KIND-PRECISION, G-COVER, G-EVIDENCE, G-INTEGRITY, G-CHURN, and (with `--release`) G-HOLDOUT and G-PRECISION. **Pending**, counted as failures: G-DETERMINISM (M2), G-REGION, G-DISPUTE, G-PRINT (M4). `make test` must always pass; `make verify` is expected to fail until a bundle passes.
