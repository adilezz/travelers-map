# Travelers World Map — The Place Model

Document 1 of the v2 set. Version 2.0, 1 October 2026. Replaces the v1 specification, which lives in the archived v1 repository.

This document defines **what a place is**, how one is admitted, how it is ranked, and what kind of place it is. Where the places live and how they are built is document 2; how they are proven right is document 3; the physical map is document 4.

---

## 1. Why v2 exists

The v1 model was careful on paper and wrong in the output. A measured review of the published v1 bundle (1 October 2026; kept in the archived v1 repository) found one root cause:

> **v1 built places from towns, and attached every landmark to the nearest town.**

A World Heritage site within 60 km of any settlement could never become a place. Machu Picchu shipped as "Quillabamba", Petra as "Ma'an", Delphi as "Livadeiá", Santorini was absent, Cairo was merged into Giza. Only 54 % of 180 well-known landmarks had a place within 10 km. Scores normalised to each country's maximum crowned obscure places (a Faiyum village was Egypt's number one). Kinds were assigned from signals so broad that 54 % of places, cities included, were "Wildlife & wilderness".

v2 keeps v1's good ideas — one database with two renderings, no world ranking, no points or percentages — and replaces the mechanism that produced places.

## 2. The object, and who it is for

It is a **personal** product. The owner wants to *see physically* where they have been in the world and where they should or may travel next.

- A printed world map, about 3 × 2 m, with the borders of territories.
- One magnetic piece per territory, lifted out and put back.
- Pins for cities and places, pushed into holes drilled at real coordinates.
- A web atlas that holds the whole database and the owner's record, and feeds the printed map.

The test of every decision in this document: **standing in front of the wall, with a pin in hand, does the pin say a place I would recognise, in the right spot?** One wrong famous pin and the whole map loses trust.

## 3. Principles

| # | Principle | Consequence |
|---|---|---|
| P1 | One database, two renderings | The printed map filters; it never removes a place from the database. |
| P2 | A place is a thing a person says "I went there" about | Not a town that happens to be nearby; not a dataset row. |
| P3 | Evidence, not assertion | Every place, every kind and every tier traces to stored evidence. |
| P4 | Landmarks are first-class | A site is never absorbed into a nearby town. |
| P5 | No world ranking, no points | Tiers, never a 0–100 number; tiers are per country as well as global. |
| P6 | Absence of data is not low value | A country the data barely reached is *unscored*, never *poor*. |
| P7 | The owner decides | Anchors, vetoes and territory rulings always beat the algorithm. |
| P8 | Identity is permanent | A `place_id` is minted once and never reused (document 2). |
| P9 | Nothing ships unproven | Gates in document 3 block publication. |

## 4. What a place is

A **place** is a named, visitable destination with one anchor point and, optionally, a footprint. It is the unit of "I have been there".

### 4.1 Types

| Type | Is | Examples |
|---|---|---|
| `settlement` | A city, town or village visited as a settlement | Florence, Kyoto, Chefchaouen |
| `site` | A monument, archaeological or religious complex, or other built landmark | Machu Picchu, Petra, Angkor, Giza plateau |
| `area` | A park, reserve, island, range, desert, wetland or landscape | Serengeti, Santorini, Torres del Paine, Dolomites |
| `route` | A long path with one anchor | Camino de Santiago, Trans-Siberian |

`area` and `route` places are pinned at an **anchor point** chosen for visiting (a park's main gate or best-known centre, a route's start or best-known stage), never at an arbitrary centroid. The sheet and the map say what the pin is: "Dolomites — area".

### 4.2 Evidence is not a place

The rows the sources provide — a UNESCO inscription, a protected-area polygon, a Wikidata item, an OSM object, an intangible-heritage element — are **assets**. An asset is evidence *for* a place. It is never a place by itself, and it is never silently attached to the nearest town. Assets link to places by identity (shared Wikidata item, containment, explicit mapping), recorded with the method and a confidence (document 2).

### 4.3 Hubs, parts and nesting

- **Serial and multi-part properties are one place.** A World Heritage property with forty components is one place with forty asset parts. Parts get pins only if the owner opts in.
- **Genuine nesting is allowed but never required.** When a part is itself a destination — the Giza plateau contains the Sphinx; Florence contains the Uffizi; Rome contains the Colosseum — it may exist as its own place (if it clears the admission rule by itself) or stay as evidence on its parent. Both are correct, and validation does not test either way (document 3 §2.1). **Only true serial components are never separate:** the parts of a serial or multi-part property (the pyramid fields, the component sites of a World Heritage property) are assets of one place, and a pin on one is an error.
- **A town beside a site is a link, not a merge.** `near_place_id` records that Aguas Calientes is the gateway to Machu Picchu. Both can exist. Neither absorbs the other.
- **Suburbs are not places.** A suburb is admitted only if it is a destination in its own right.

## 5. Admission

A candidate is any item with a coordinate (or representative point) and a place-like class from the curated class table (`data/rules/classes.csv`), plus every source record with a place-like meaning. It is **admitted** by the first rule that fires:

| Rule | Condition (initial values) |
|---|---|
| R1 Institutional | World Heritage property; IUCN Ia–II protected area ≥ 100 km²; UNESCO biosphere core, global geopark; Ramsar site ≥ 100 km² |
| R2 Attention | Wikipedia sitelinks ≥ 40 |
| R3 City | Population ≥ 100,000 (metropolis anchor) |
| R4 Corroborated | Sitelinks ≥ 15 **and** one independent signal (a Wikivoyage destination article, an intangible-heritage location, a national top-tier designation, an IUCN III–V area, high OSM tourism density) |
| R5 Country floor | The top five by notability *N* in each sovereign state; the top two in each dependency and territory |
| R6 Owner anchor | Listed in `data/anchors/anchors.csv` |

Anything that fails every rule is **not published**. Candidates with a single weak signal go to a review queue (`review_queue.csv`) that the owner may promote with an anchor. A place never enters because it is a town of a given size.

All thresholds are initial values. They are tuned only against the **golden set** and never against the holdout (document 3), and every change is recorded in the build manifest.

### 5.1 Merging duplicates

One real destination often exists as several records. Resolution runs in this order and logs every decision to `merge_log`:

1. Same Wikidata item (including items merged or redirected since the last snapshot).
2. A Wikidata link carried by another source (`wikidata` tag in OSM, GeoNames cross-reference, a WHS-to-QID table).
3. Same normalised name within 5 km, or a name-similar candidate contained in the other's footprint.
4. Owner decision (`merge_overrides.csv`).

The survivor is the record with the most sitelinks. Merges are reversible: a `split_log` records every unmerge, and neither changes a `place_id` except by the rules in document 2.

## 6. Notability and tiers

### 6.1 Notability *N*

*N* is an absolute, internal quantity used to order places. It is never shown as a number and never ranks the world for display.

```
N = log10(1 + SL) + 0.5 · log10(1 + PV/1000) + R + C

SL  language editions of Wikipedia carrying the item
PV  Wikipedia pageviews, summed over the 12 latest complete months, all languages
R   recognition points, capped at 1.5
      World Heritage 1.0 · IUCN Ia–II 0.4 · Ramsar / geopark / biosphere 0.3
      intangible heritage located here 0.3 · national top-tier designation 0.2
C   settlement size, capped at 0.3:  0.15 · log10(pop / 100,000), pop ≥ 100,000
```

Sitelinks count how many separate language communities independently thought the place worth an article, which no single authority controls. Pageviews add current attention and are damped and windowed so a news spike cannot crown a place.

### 6.2 Fairness against popularity bias

Sitelinks and pageviews favour English-language, Western, urban and religious subjects, and under-reward nature and living culture in the Global South. v2 corrects for this rather than pretending it away:

1. Recognition points *R* come from **globally adjudicated** sources, not from article counts.
2. Tiers are assigned by **two routes and take the higher** — a global anchor and a within-country rank (6.3) — so a country's best places are never crushed by another continent's attention.
3. A **bias audit** (document 3) reports tier share and place counts by region, language and type on every build; a systematic deficit is a defect.
4. **Absence is not penalty.** Living-culture evidence (intangible heritage, pilgrimage, cuisine, markets, crafts) can only *raise* a place via R or support its kinds. A country the harvest did not reach is flagged `evidence_depth: thin`, never scored down.

### 6.3 Tiers

| Tier | Meaning | Initial rule |
|---|---|---|
| **Icon** | A traveler would name it unprompted | *N* ≥ global p99 of admitted places, **or** top 3 in its country (top 1 where the country has fewer than 10 places) |
| **Major** | Worth planning a trip around | *N* ≥ global p95, **or** next 10 in its country (next 3 under 10 places) |
| **Notable** | Worth a detour | *N* ≥ global p75, **or** top 40 % of its country |
| **Local** | Worth knowing | The rest |

A tier is shown with a one-line reason ("World Heritage · 140 language editions"), never as a number or rank. Tiers order the register and drive the density control and the print selection. A **regional cap** keeps a town from outranking the recognised hub of its own region: a place never takes a tier above that of an admitted place that contains it or is its parent.

## 7. Kinds of place

The product sentence — *still unseen: desert and steppe, sacred and pilgrimage* — is only true if kinds are true. In v2 a kind is **evidence-linked**: it exists on a place only because a named rule fired on stored evidence, and the rule is shown.

### 7.1 The thirteen kinds

Stored as stable slugs; the interface shows labels.

| Slug | Label | A place carries it when… |
|---|---|---|
| `capital` | Imperial & historic capital | It is or was the seat of an empire or sovereign state (Wikidata capital statements with dates, class "imperial capital"). Sub-state ducal and provincial seats do not count unless the place is Icon tier |
| `old_town` | Living old town | Historic urban fabric is protected or inscribed (WHS "historic centre / old town", national historic-district class), and people live in it |
| `coast` | Coast & sea | The place or its footprint touches the sea (distance to coastline ≤ 2 km) or is an island, reef or lagoon; a river port is not coastal |
| `mountain` | High mountain | Footprint or anchor in a range with relief ≥ 1,500 m within 15 km, or a named peak or glacier is part of it |
| `desert` | Desert & steppe | Anchor lies in desert, dune, saltflat or steppe land cover, or the place is classed as such |
| `forest` | Forest & jungle | Forest or rainforest is the primary setting (protected forest, WHS forest, forest land-cover share ≥ 50 % of footprint) |
| `water` | Lake & river | A lake, river, delta, wetland or waterfall is the destination or its principal setting (not "a town on a river") |
| `volcanic` | Volcanic & geothermal | A volcano, caldera, geyser or geothermal field is part of it |
| `wildlife` | Wildlife & wilderness | The place **is** a protected area (IUCN Ia–IV, national park, reserve) or **contains** one overlapping ≥ 50 % of its footprint. A city beside a park is not wildlife |
| `sacred` | Sacred & pilgrimage | A pilgrimage destination, or a religious complex that is the reason to go (WHS religious class, major pilgrimage Wikidata classes) |
| `rural` | Rural vernacular & agrarian | A landscape, village or region valued for agrarian or vernacular life (cultural landscapes, wine/terrace/rice landscapes, vernacular-architecture classes) |
| `metropolis` | Modern metropolis | Settlement with population ≥ 1,000,000, or recognised as a world city or modern urban icon |
| `ruins` | Ancient & archaeological sites | The place is, or is centred on, excavated or standing remains of a civilisation no longer living there: Wikidata archaeological site, ruin, necropolis, ancient city, castle or fortification, prehistoric or palaeontological site; WHS cultural criteria (i)–(iv) with no continuing urban fabric. A living historic centre stays `old_town`; a place may carry both when it has both (Luxor) |

### 7.2 Rules

- Each kind is derived by **rule rows** in `data/rules/kinds.csv` (rule id → class, tag, criterion or geometry test → kind, strength). Rules read stored assets and geometry; they never read a place's name.
- A place carries **1 to 3 kinds**: the strongest by rule strength. A place with no firing rule is a **build failure**, not a fallback: it signals an incomplete rule table.
- A place that has a kind must be able to say why: `place_kind` stores the rule and the evidence assets, and the sheet shows it ("Nature — Ramsar wetland").
- Kinds are shape and label, never colour, in the interface.

### 7.3 Validation

Kinds are proven on a **hand-labelled stratified sample** with a second annotator, not by plausibility (document 3). Gates: per-kind precision ≥ 0.90, no kind on more than 25 % of places or fewer than 1 %, every kind present in the world, and no country missing a kind it materially has.

## 8. What a place record holds

| Field | Notes |
|---|---|
| `place_id` | Opaque, permanent (document 2) |
| `type` | `settlement`, `site`, `area`, `route` |
| `name_en`, `name_local`, `aliases[]` | Common English name first; local script preserved; transliterations and alternates searchable. Never a raw identifier, markup, a registry title or a transliteration standard's output when a common name exists |
| `country`, `admin1`, `disputed` | Administering state; first-level unit; disputed marker where one applies |
| `lat`, `lon`, `footprint?` | Anchor point and optional geometry |
| `tier`, `tier_reason` | Never a number |
| `kinds[]` with `rule`, `evidence` | 1–3 |
| `why` | One line a person can read |
| `evidence[]` | Assets: source, source id, URL, retrieved, role |
| `qid`, `osm_id`, `geonames_id`, `wdpa_id`, `whs_id`, `wikipedia` | External identity, so links and re-matching never rely on names |
| `near_place_id` | Gateway settlement or sibling |
| `best_months[]`, `reach` | Present only when sourced; otherwise omitted, never dummy |
| `evidence_depth` | `rich` or `thin` |

`score` (0–100) is **removed**. Pillar scores are retired as a ranking engine; the three evidence families — built heritage, natural setting, living culture — survive only as the grouping of evidence in "why it is here".

## 9. Countries and territories

- Every sovereign state has at least five places; every dependency and territory at least two, per R5.
- The database has a `territory` table with `sovereign`, `kind` (state, dependency, disputed, uninhabited), `display_policy` and a ruling reference. Uninhabited and research territories (Bouvet, Heard Island, Antarctica) are listed and may be shown, but receive no country floor.
- Disputed territories follow the owner's rulings in document 4 §7. Until a ruling exists the build **warns** and does not choose.
- Country names are standard short English names; `The Netherlands` becomes `Netherlands`.

## 10. What changed from v1

| v1 | v2 |
|---|---|
| Places from towns; assets attach to the nearest town ≤ 60 km | Places are destinations; assets are evidence linked by identity |
| Sites absorbed into settlements | A site is never absorbed |
| Score 0–100, country-max = 100 | Tiers (Icon/Major/Notable/Local), absolute notability inside, per-country rank as one route |
| Three-pillar power mean | Retired as ranking; kept as evidence grouping |
| Kinds from broad signals, no validation | Evidence-linked rules, hand-labelled validation, hard gates |
| IDs from GeoNames/GHSL/WDPA, colliding prefixes | Opaque permanent ids with a registry |
| No assets table | `asset` and `place_asset` with provenance |
| Print hole budget filtered the web | Print selected from the web layer by document 4 |
