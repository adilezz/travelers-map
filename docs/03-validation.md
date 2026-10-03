# Travelers World Map — Validation and Ground Truth

Document 3 of the v2 set. Version 2.0, 1 October 2026.

A model that is tuned and judged on the same examples measures only the tuner's memory. This document defines the ground truth, the gates that stop a bad build, the reports that inform a good one, and how the checks avoid fooling themselves.

---

## 1. Principles

1. **Ground truth is written before the model runs and frozen.** Changing it after seeing results is allowed only by a dated, explained revision, never to make a build pass.
2. **Two sets, never mixed.** The *golden set* is used for development and tuning. The *holdout* is touched only at release; it is never used to set a threshold or a rule.
3. **Right entity, not nearest anything.** A landmark passes only if the right place exists, with a correct name, at the right position. v1 would have passed "something within 60 km".
4. **Measure uncertainty.** Every rate carries a Wilson 95 % interval; a gate compares the interval's **lower bound** to the threshold when n is small.
5. **No gate is a warning in a log.** A gate fails the build. A report is read and argued with.
6. **Gates run on the published bundle**, the same files the client fetches.

## 2. Ground truth

### 2.1 Golden set — `data/golden/golden.csv` (≈ 300 rows)

Written by the owner with assistance, before pipeline code runs. Columns: `golden_id, country, expected_name, aliases, row_kind, type, lat, lon, tol_km, min_tier, max_tier, kinds_expected, whs_id, qid, qid_status, relation, target_id, regression, evidence, note`. `tol_km` is at most 8 km for sites, at most 12 km for settlements (a large city's anchor is its centre), and up to 60 km only for `area` and `route` places, where the anchor is a visiting point and not a centroid; a place with a UNESCO or WDPA footprint is matched by id or footprint where the registry point is far from the anchor. Every addition to the set must carry `evidence` (a UNESCO property id, a protected-area id, a Wikidata item with at least 40 sitelinks, or a settlement of at least 100,000) and a check that the v1 database lacked it.

Composition (stratified, so no region or kind dominates):

- 5–8 *icons* per country for ~35 representative countries across every region, with at least 40 % outside Europe and North America.
- Every *kind* represented by at least 15 places.
- The hard cases from the v1 review, as permanent regression tests: Machu Picchu, Petra, Wadi Rum, Delphi, Santorini, Mont-Saint-Michel, Torres del Paine, Salar de Uyuni, Cairo, Johannesburg, Kyoto, Kathmandu Valley, Florence above Belluno, Paris above Lourdes, Giza / Luxor / Abu Simbel at the top of Egypt.
- Microstates and island nations (Maldives, Vanuatu, Luxembourg, Seychelles, Singapore, Bhutan, Fiji).
- Serial sites, routes and large areas (Dolomites, Camino de Santiago, Great Barrier Reef, Great Wall).
- Negative and relational rows (`row_kind`): `negative` rows state what must not happen — a **true serial component** of a property is not a separate pin (`component_of`), a place must not outrank another (`not_above`, tier strictly lower), a town must not carry a landmark's evidence (`not_credited`); nested monuments (the Colosseum, the Uffizi, Sagrada Familia, Hagia Sophia) and absorbed neighbours (Saqqara into Giza) are `negative` `component_of` rows: they must not exist as separate places (D25).

### 2.2 Holdout — `data/holdout/` (≈ 300 rows)

Built so it is **not correlated with the seeding signal**:

- **H1 Hand-listed travel picks (100):** typed by the owner from their own travel knowledge, **disjoint from the golden set**, written before any pipeline output is seen and then frozen. Source recorded per row. For the five-country prototype H1 holds **20 rows per prototype country** (the bundle can only be judged on countries it contains); a world build needs a world H1 across other countries. Rows should deliberately include what a heritage-led pipeline overlooks: towns, trails, beaches, markets, food and everyday places, not only monuments. Instructions: `data/holdout/README.md`.
- **H2 Wikivoyage "See" leaders (100):** the destinations a community of travelers ranks first. Reported **separately** because it is partly correlated with Wikidata attention.
- **H3 Stratified random draw (100):** a random draw from the published database, stratified by region and tier, for *precision* review (2.4).

H1 is the honest recall measure. H2 is a cross-check with a known bias. H3 estimates false positives.

### 2.3 Kind labels — `data/golden/kind_labels.csv`

300 places stratified across the fourteen kinds, hand-labelled with 1–3 kinds and a reason by the owner. A **second annotator** — an independent pass, human or model — labels the same sample blind; the disagreements are listed and resolved in writing. Cohen's κ is reported. A model's labels are data frozen in the file; they are never recomputed in a build.

### 2.4 Precision review

On each release, 100 places from H3 are shown to the owner with name, type, position and tier. Each is marked *right*, *wrong entity*, *wrong place*, *wrong name*, *should not exist*. Gate G-PRECISION requires ≥ 95 % *right*.

## 3. Gates (block publication)

| Gate | Asserts |
|---|---|
| **G-SCHEMA** | Every place is structurally valid (types, ranges, evidence, kinds); an empty bundle fails. Gates run on records that pass this, and any gate that crashes is a failure |
| **G-LANDMARK** | ≥ 95 % of golden rows resolve to the **right entity** (QID match, or alias plus type while QIDs are being resolved), with the anchor within the row's `tol_km`, with `name_en` matching the expected name or a listed alias; zero failures among the regression rows in 2.1 |
| **G-HOLDOUT** | At least 100 rows, **disjoint from the golden set**, **frozen by hash** (`data/freeze.json`); recall lower bound ≥ 0.85 (release only) |
| **G-PRECISION** | ≥ 95 % *right* on at least 100 reviewed places, each row linked to a distinct place in this bundle |
| **G-TIER** | Every golden `min_tier` is met; the ordering tests hold (Florence > Belluno, Paris > Lourdes, Egypt's top three are among Giza, Luxor, Abu Simbel, Cairo) |
| **G-KIND** | Every place has 1–3 kinds; per-kind precision ≥ 0.90 on the labelled sample (lower bound ≥ 0.85); no kind on > 25 % or < 1 % of places; every kind exists in the world; no country lacks a kind it materially has |
| **G-ID** | `place_id` unique; none reused for a different place; none lost without a registry status; registry and bundle agree |
| **G-IDENT** | No two active places share a QID; every `merged_into` chain resolves; every v1 id in the crosswalk resolves |
| **G-NAMES** | No raw QID, markup, control characters, mojibake, or name > 60 characters; every place has `name_en`; `name_local` present where the country's script differs |
| **G-COUNT** | The manifest's total and per-country counts equal the files exactly |
| **G-COVER** | Every state in the **committed** `data/scope.json` has ≥ 5 places and every dependency ≥ 2 (R5), or a committed exemption; no place lies outside the scope |
| **G-STRUCT** (pending, M2) | Against `data/golden/structure.csv`: parent chains correct for every golden place (Machu Picchu never under Quillabamba), known `serves` cases hold, `part_of` is acyclic, no node more than 150 km from every place, stay coverage equals the fraction actually sourced and buckets agree with the owner in ≥ 80 % of rows |
| **G-PAIRS** (pending, M3) | Pairwise agreement of the ranking (tier, then N) with the confirmed pairs in `data/holdout/pairs.csv`, whose truth is official visitor statistics, not Wikipedia: at least 85 % of pairs overall and 80 % in each region, reported by region; a ±50 % sensitivity test on the weights of N reports how many tiers flip |
| **G-REGION** | Every place has exactly one `region_id`; each country's regions union to its land within the documented tolerance; no region or piece crosses an international border |
| **G-DISPUTE** | Every disputed alias resolves per document 4 §7; no unruled case is silently drawn |
| **G-PRINT** | The print selection satisfies spacing, quota and override rules (document 4 §6) at the chosen edition |
| **G-INTEGRITY** | Files match the hashes recorded in the manifest (detects corruption and tampering; it does not prove reproducibility) |
| **G-DETERMINISM** | **Pending (M2).** A second build from the same pinned manifest reproduces every output hash |
| **G-CHURN** | Places changing id, tier, name or position (> 1 km) against the previous build ≤ 2 %, unless the build cites a cause listed in the committed `data/changelog.json` |
| **G-EVIDENCE** | Every kind has evidence assets; every place has ≥ 1 `place_asset` with provenance; no `name_distance` link below 0.8 reached the bundle |

### 3.1 How gates report

Every gate returns whether it passed, **how many things it checked** (`n`), and **how many checks it skipped**. A skipped check is a failure unless the build is declared a prototype (`--prototype`): a green run must be distinguishable from a vacuous one. Gates that cannot yet run are listed as **pending** and count as failures. `make verify --json` writes the structured results.

### 3.2 Threat model

The adversary is the pipeline's own author — or an agent tuning it — who can see the golden set and wants the gates green. The gates therefore:

- **fail closed**: malformed input or a crash is a failure;
- **never read their scope, exemptions or causes from the bundle** they judge; those are committed files;
- match **one-to-one** and flag duplicates, so a landmark cannot be satisfied twice or by a clone;
- keep the **holdout disjoint and frozen**, so tuning on it is detectable;
- are themselves **mutation-tested**: the suite breaks a perfect bundle in the ways a pipeline might (drop places, shift them, swap tiers, duplicate ids, empty it) and asserts the right gate fails, and a test fails if any gate has no test that trips it.

Known limit: the golden set is partly circular with the seeding signal (about half its rows rest on UNESCO ids, which rule R1 admits). Only the owner-written holdout H1 measures recall independently, which is why it must be written and frozen before the pipeline is tuned.

## 4. Reports (read, not blocking)

- **Bias audit.** Place counts and tier shares by region, language of article, type and country income class; places per country regressed on area, population and recognition count. A systematic deficit is a defect to be investigated, not a finding to be filed.
- **Rank sensitivity.** Perturb the weights in *N* (± 25 %) and recompute tiers; report Kendall's τ against the baseline, per country, and list places whose tier moves two levels. Fragile tiers are inspected by hand.
- **External rank check.** Kendall's τ of the tier order against two external orderings (Wikipedia pageviews alone; the Wikivoyage "See" order) for each golden country. Disagreement is a prompt to look, not an error.
- **Redundancy.** Mean kind overlap within each country's printed selection against a ranking baseline held to the same spacing.
- **Evidence depth.** Countries flagged `thin`, so the interface never presents a data gap as a poor country.
- **Review queue.** Candidates with a single weak signal, for the owner to promote or ignore.
- **Name review.** Places that failed G-NAMES and the fix applied.
- **Expert review.** For selected countries, someone who lives there or knows it well answers one question: *does this set represent your country?*

## 5. Anticipated failure modes the validation must catch

| Failure | Caught by |
|---|---|
| A landmark rolled into a town (v1's root cause) | G-LANDMARK, regression rows |
| An obscure place crowned by normalisation | G-TIER ordering tests, external rank check |
| Everything is "wildlife" | G-KIND distribution gates |
| Dataset popularity bias | Bias audit, H1 vs H2 gap |
| Overfitting to the golden set | H1 holdout touched only at release |
| One annotator's taste | Second annotator, κ |
| Silent identity loss | G-ID, G-IDENT, registry |
| A refresh that quietly reshuffles the world | G-CHURN, `diff.json` |

## 6. Process

1. M0 writes the golden set, holdout files, and the gates as **failing tests**.
2. Development tunes against the golden set only.
3. A release candidate runs all gates; the holdout and the precision review run once.
4. A failure is fixed in the model or rules, not by editing the truth. A change to the golden set is a dated revision with a reason.
5. The release record keeps the gate results, intervals, and the signed-off precision review.
