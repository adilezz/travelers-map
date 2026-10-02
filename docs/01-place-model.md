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

### 2.1 Purpose and size

The database serves three uses at three sizes (decided 1 October 2026):

| Use | Size |
|---|---|
| The printed wall map | About 1,000 to 3,000 pins, never more than 3,000, chosen from the atlas (document 4) |
| The web atlas and trip planner | About 15,000 to 25,000 places |
| The database itself | Every place that clears admission, **including Local-tier places beyond the atlas**; it may grow past 100,000 |

These are targets the admission rules are tuned toward, not quotas. Every build reports the size it reached and why.

### 2.2 What makes a place good

A good place is **known, visited and evidenced. It is not recommended.**

- **Known.** Many independent language communities wrote about it, and institutions recognised it (UNESCO, protected-area designation, national registers).
- **Visited.** People actually go: official visitor statistics where they exist, and current attention (pageviews).
- **Evidenced.** Every claim a place makes (why it is here, its tier, its kinds) traces to a stored, checkable source (document 2 §4).
- **Not recommended.** No review site, rating, blogger ranking or "best of" list is used to admit, rank, tier, tag or describe a place. The map exists so that nobody's taste, including the database's, decides where the owner goes. Whether Metz was awful and Lille wonderful is the owner's own experience: it lives in the personal layer (visits, ratings, notes), never in the shared database.

Attention measures are not opinions, but they are biased; section 6.2 says how that is handled.

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
| P10 | Evidence, not recommendation | No review, rating or "best of" source touches admission, tier, kind or text. |
| P11 | The owner's experience is a separate layer | Visits, ratings and notes live in the owner store, keyed to `place_id`; they never alter the shared database (document 2 §4.1). |

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
- **A monument inside a place is an asset of that place, never a place.** Decided 2 October 2026 (D25), replacing the earlier "either is fine" ruling. The Colosseum is evidence on Rome, the Uffizi on Florence, Karnak, Luxor Temple and the Valley of the Kings on Luxor. An asset has no pin and no stay row; its time counts inside its parent's stay. The same holds for the parts of a serial or multi-part property (the pyramid fields, the component sites of a World Heritage property).
- **Nearby places of the same kind are absorbed** into the more famous one (§5.2). Places whose kind differs stay separate and are linked by a typed edge.
- **Structure is stored as typed edges, never as a column** (document 2 §4.2): `part_of` (inside), `gateway_of` (the town through which a destination is reached), `day_trip_from` (a separate destination reached in a day: Versailles from Paris, Pompeii from Naples) and `near`. A day trip is **not** containment. Which nested destinations become places is settled by the nested-destination test on the golden set (`data/golden/structure.csv`); until then D5 stands. Sub-destinations are shown in a city's detailed view and are kept out of the printed hole budget unless they are Icons.
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

### 5.2 Absorption

Merging (5.1) joins records of one destination. Absorption joins *neighbouring destinations that a traveller treats as one*. Decided 2 October 2026 (D25), from the owner's verification of the structure table (`data/golden/structure.csv`):

- A candidate within about 25 km of a more famous place, **of the same kind** (and, where one exists, of the same World Heritage property), becomes an asset of that place. The merged place keeps the famous name and pin. Examples: Saqqara and Memphis into Giza; Herculaneum into Pompeii; Ostia Antica into Rome; Aguas Calientes into Machu Picchu; Wadi Musa into Petra.
- A neighbour whose **kind diverges** stays a separate place and is linked: Giza is a day trip from Cairo (desert necropolis against megacity); Pompeii is a day trip from Naples (buried Roman town against living city); Tivoli from Rome; the Dead Sea from Amman.
- Typed edges are for places within about 60 km. A longer link needs a stated transport basis in its note (Abu Simbel from Aswan, a convoy or a flight). Where the ruling is not obvious it is logged in the structure table with its reason.
- A town that is only a gateway on the real access path is a `gateway_of` edge, never credited with the destination's evidence (Moshi for Kilimanjaro, Arusha and Karatu for the northern parks). Quillabamba is on no access path to Machu Picchu: a negative row.

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

Official **visitor statistics** (annual visitors) are a candidate input. They are measured in M3 and enter *N* only if the bias audit shows they help; reviews and ratings never do (section 2.2).

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

The product sentence — *still unseen: desert and dry plains, holy places and pilgrimage* — is only true if kinds are true. A kind says **what a place is** (never what you do there, section 7.4). In v2 a kind is **evidence-linked**: it exists on a place only because a named rule fired on stored evidence, and the rule is shown.

### 7.1 The fourteen kinds

Stored as stable slugs; the labels are plain-language proposals for the interface (owner to confirm).

| Slug | Label | A place carries it when… |
|---|---|---|
| `capital` | Capital cities, past and present | It is the **current capital** of a sovereign state (Rome, Cairo, Amman), or a **former seat of an empire or sovereign state** (Cusco, Chan Chan, Florence 1865–71, the Republic of Venice). Seats of sub-state provinces and duchies do not count |
| `old_town` | Historic centres | Historic urban fabric is protected or inscribed (UNESCO "historic centre / old town", national historic-district class), and people live in it |
| `seaside` | Beaches & coast | A beach, scenic coast, cliff, fjord, island, reef or lagoon: the sea as the setting. Resort coasts (Dahab, Amalfi Coast, Cinque Terre) |
| `maritime` | Port & harbour cities | A port or harbour is the character: harbour cities, trading ports, lighthouse and quay heritage (Venice, Stone Town, Alexandria, Aqaba) |
| `mountain` | Mountains | A mountain landscape: relief of 1,000 m or more within 10 km, or a summit of 2,500 m or more in the footprint |
| `desert` | Desert & dry plains | Desert, dune, salt flat, or steppe and dry grassland (arid climate and sparse cover) |
| `forest` | Forest & jungle | Forest or rainforest is the primary setting (tree cover over half of a 10 km buffer, or a protected forest) |
| `water` | Lakes, rivers & waterfalls | **Freshwater**: a lake, river, delta, wetland or waterfall of 5 km² or more is the destination or its principal setting (not "a town on a river"). Sea and lagoons are `seaside` |
| `volcanic` | Volcanic & geothermal | A volcano, caldera, geyser or geothermal field is part of the place itself |
| `wildlife` | National parks & wildlife | The place **is** a strict protected area (IUCN Ia, Ib, II, IV, national park, reserve) or one covers 50 % or more of its footprint. A city beside a park is not wildlife |
| `sacred` | Holy places & pilgrimage | A **living faith**: a pilgrimage destination, or a religious complex in worship use that is the reason to go (Saint Catherine's, Lalibela, Assisi) |
| `rural` | Countryside & villages | Farmland, vineyards, terraces and villages valued for agrarian or vernacular life (over 60 % cropland or pasture, low density, no city of 50,000 nearby) |
| `metropolis` | Big modern cities | Population of 1,000,000 or more, or an urban area of 300 km², or a world city |
| `ruins` | Ruins & ancient sites | Excavated or standing remains of a civilisation **no longer living there**: archaeological site, ruin, necropolis, ancient city, castle, fortification, prehistoric or palaeontological site. A temple nobody worships in is `ruins` (Karnak, Abydos) |

### 7.2 Rules

- Each kind is derived by **rule rows** in `data/rules/kinds.csv` (rule id, kind, source, test, strength, role, excludes, rationale). Rules read stored assets and geometry; they never read a place's name.
- A **strength** is the rule's estimated precision (0–1): the chance that a place firing it is a clean, defining member of the kind. Because every kind uses the same definition, strengths are comparable across kinds. Initial values are guesses (`calibrated = no`); they are calibrated against the hand-labelled sample in M3 (30 or more labelled places per rule, rounded to 0.05).
- Several rules for one kind combine by **noisy-or over distinct sources**: only the best rule from each source counts, so five correlated Wikidata subclasses cannot inflate a kind. The result is capped at 0.95. A kind needs **at least one core rule** (a support rule adds strength but cannot create a kind alone) and a combined strength of **0.50 or more**.
- A place that has a kind must be able to say why: `place_kind` stores the rules and the evidence assets, and the sheet shows it ("Nature — Ramsar wetland").
- A place whose evidence admits it but fires no kind rule is a **build failure**: it signals an incomplete rule table, not a fallback.
- Kinds are shape and label, never colour, in the interface.

### 7.3 Overlaps and ties

The overlaps are settled by **rules, as data**, so every decision is reproducible and every cut is recorded.

**Pair rules** (`data/rules/kind_pairs.csv`): when both kinds qualify and a condition holds, one is dropped.

| Overlap | Rule | Example |
|---|---|---|
| `sacred` vs `ruins` | `sacred` means a living faith, `ruins` a dead one. If the **place itself** is in worship or pilgrimage use, keep `sacred`; otherwise keep `ruins` | Saint Catherine's Monastery: sacred. Karnak, Abydos, Machu Picchu: ruins |
| `seaside` vs `maritime` | Both can be true. A real port city (200,000 or more) with **no beach within 2 km** is `maritime` only | Venice: maritime. Aqaba, with a beach and a port: both |
| `water` vs `seaside` | Sea, lagoon and brackish water belong to `seaside`; `water` is freshwater | Aqaba Marine Reserve: seaside, not water |
| `wildlife` vs `rural` | A strict protected area over half the footprint with under 30 % farmland is `wildlife` only; with more farmland both stand | Serengeti: wildlife. A park with farms: both |
| `forest` vs `rural` | Half or more tree cover is `forest` | |
| `metropolis` vs `rural` | A big modern city is not the countryside | |
| `capital` vs `old_town` | Independent: political role and urban fabric. Both can apply | Rome, Florence |

**The cap of three** is applied last. Kinds are ordered by, in turn:

1. combined strength, in steps of 0.05 (strengths within 0.05 count as equal);
2. the number of **independent sources** behind it;
3. the **priority order** below;
4. the slug, so the order is total and no two kinds can ever tie completely.

Priority, used only to break ties: `sacred`, `ruins`, `volcanic`, `desert`, `wildlife`, `mountain`, `seaside`, `maritime`, `forest`, `water`, `capital`, `old_town`, `rural`, `metropolis`. The principle: distinctive character first; political role, urban fabric and general land use last, because those describe almost every place. The first three kept are the place's kinds; the rest are stored as **cut kinds with the reason** (`cap`, `pair:…`, `excluded_by:…`, `below_threshold`). A place is flagged `crowded` when its fourth kind was within 0.10 of its third, so such places are reviewed; the order is never changed by hand, the rules are.

Examples (strengths are the initial guesses): **Rome** keeps `capital` (0.90), `old_town` (0.85), `metropolis` (0.85) and cuts `ruins` (0.80) by the cap, flagged crowded. **Kilimanjaro** keeps `volcanic`, `wildlife`, `mountain` (equal strengths, ordered by priority) and cuts `forest`. **Venice** keeps `maritime`, `old_town`, `capital` and drops `seaside` by the port-city rule.

### 7.4 Experiences are not kinds

What you **do** is a separate dimension. The test: if removing the verb leaves a sensible noun (beach, volcano, old town), it is a kind; if it needs a verb or a date (dive, ski, taste, festival), it is an **experience**.

- **Experiences** (`place_activity`) are a controlled vocabulary of about thirty tags, listed in `data/rules/activities.csv`: diving, snorkelling, surfing, sailing, kayaking and rafting, whale watching, trekking, climbing, skiing, via ferrata, cycling, scenic drives, rail journeys, safari, birdwatching, stargazing, caving, canyoning, wine, food and cuisine, markets, festivals, crafts, hot springs, wellness, museums and art, architecture, memorials and dark heritage, literary and film places, theme parks, cruises. They are many-to-many, **never drive admission, tier or the three-kind cap**, and carry evidence like kinds. Free sources: OpenStreetMap tags, Wikidata classes and events, UNESCO intangible heritage, protected-area and bird-area designations. Wikivoyage supplies only the existence of a section, never its prose or ranking. Reviews and ratings never.
- **Events** (`place_event`): festivals and recurring events with a Wikidata item, a location and a month range.
- **Effort and access** (`place_access`, `travel_effort`): effort class (easy, moderate, demanding, expedition), elevation, ascent, trail length, permit, wheelchair access (OpenStreetMap; absent means unknown, never "no"). This is what separates Kilimanjaro from a museum in Cairo.
- **Season** (`place_season`) from sourced climate and visitor-interest data. **Visitor load** (`place_visitors`): official statistics only. **Advisories** (`place_advisory`): a government advisory as a dated, sourced fact with its issuer, never our own score.
- The product sentence stays **about kinds only**: *still unseen: desert and dry plains, holy places and pilgrimage*. Experiences may get a second, separate sentence ("never yet: diving, skiing") once their evidence is real.

### 7.5 Validation

Kinds are proven on a **hand-labelled stratified sample** with a second annotator, not by plausibility (document 3). Gates: per-kind precision ≥ 0.90 (lower bound ≥ 0.85), no kind on more than 25 % or fewer than 1 % of places, every kind present in the world, and no country missing a kind it materially has.

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
| `near_place_id` | Gateway settlement or sibling (the typed edges in document 2 §4.2 are the full form) |
| `typical_stay` | Icon and Major only: a bucket (`hours`, `half_day`, `day`, `multi_day`) with an optional hour range, a method (`owner` or `source_text`) and a confidence. A labelled estimate, never a recommendation, never a sum of children; absent means unknown, not short |
| transport nodes | Airports, ports, ferry terminals and stations that **serve** the place (`serves`, with mode and a straight-line distance). Nodes are not places and never enter admission or tiers |
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
