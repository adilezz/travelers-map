# Decision log

Every significant decision, with the reason, so a future reader (including the owner) does not have to reconstruct it. Newest last. Dates are 2026.

## Why v2 exists (1 Oct)

A measured review of the v1 place database (12,050 places) found one root cause: **v1 built places from towns and attached every landmark to the nearest town within 60 km.** Machu Picchu shipped as "Quillabamba", Petra as "Ma'an", Delphi as "Livadeiá"; Santorini was absent; Cairo was merged into Giza. Only 54 % of 180 well-known landmarks had a place within 10 km. Scores normalised to each country's maximum crowned obscure places (Egypt's number one was a Faiyum village; Italy's number two was Belluno, above Florence). Kinds were so broad that "Wildlife & wilderness" sat on 54 % of places, cities included. The living-culture pillar was unscored in 194 of 234 countries. Identifiers collided (CHI = China and Chile) and embedded upstream ids. There was no assets table and no per-record provenance.

The model on paper was careful; the output was not provable. v2 keeps the good principles (one database, two renderings; no world ranking; nothing ships unproven) and replaces the mechanism.

## Decisions

| # | Decision | Reason |
|---|---|---|
| D1 | A place is a destination a person says "I went there" about; source records are *evidence*, linked by identity, never attached to the nearest town | The v1 root cause |
| D2 | No numeric score; four tiers (Icon, Major, Notable, Local) from absolute notability **and** within-country rank, taking the higher | Fairness to the Global South without a world ranking |
| D3 | 13 kinds, each from a named rule over stored evidence; 1–3 per place; a place with no firing rule is a build failure (relaxed by D26) | The product sentence is only true if kinds are true |
| D4 | The 13th kind, `ruins` (ancient and archaeological remains) | Nine golden rows (Pompeii, Petra, Jerash…) had no honest kind |
| D5 | Only true serial components are never separate pins; nested destinations (Colosseum, Uffizi) may be their own place or evidence on the parent, and are not tested (superseded by D25) | Owner ruling |
| D6 | Opaque permanent `place_id` from an append-only registry; never derived from an upstream id | Visit records reference ids forever |
| D7 | A World Heritage id is evidence, **not** an identity key | Found by the M0 tests: property 86 legitimately backs both Giza and Saqqara |
| D8 | Western Sahara dissolves into Morocco; Taiwan, Kosovo, Palestine get their own piece; Northern Cyprus, Somaliland and Crimea dissolve (dotted); Kashmir shows the line of control | Owner rulings (document 04 §7) |
| D9 | Personal project: licensing does not bound the design, but every record keeps its source and licence so sharing later is a filter, not a rebuild | Owner direction; cheap insurance |
| D10 | One DuckDB store; bulk dumps processed once; no per-request fees | Cost effectiveness for one person |
| D12 | Purpose and size: wall map about 1–3k pins (ceiling 3,000); atlas about 15–25k places; the database holds every admitted place including Local, and may pass 100k | Owner agreed, 1 Oct; sizes follow purpose |
| D13 | A good place is **known, visited and evidenced, not recommended**: no review, rating or "best of" source touches admission, tier, kind or text; the owner's own experience (Metz vs Lille) lives in a personal layer | Owner decision, 1 Oct: the map must never trust someone else's taste |
| D14 | The owner's state (visits as events with fuzzy dates, wishlist, photo/Takeout/GPX candidates) is a separate store keyed to `place_id`; shared tables are reserved now for crossrefs, text, seasons, travel effort and stay time; footprints required for Icon and Major places | Owner decision, 1 Oct (follow the Expansionist): the app will grow towards state-of-the-art trip planning; identity and schema are the expensive things to change |
| D15 | Ingest runs on the owner's laptop first (SPARQL subset for the nine prototype countries; small sources locally); a rented machine only for the full Wikidata dump; optionally allow the Claude cloud environment to reach named hosts | Speed and cost; the subset and the dump are different pinned inputs |
| D16 | The holdout H1 is owner-written, disjoint from the golden set and not AI-assisted: 20 rows for each of Morocco, Spain, France, Italy and Türkiye (the countries the owner knows), mixing non-heritage places on purpose | An AI-listed holdout would reintroduce the signals the pipeline uses |

| D17 | `capital` includes current capitals (Rome) as well as former seats of empires or sovereign states | Owner decision, 1 Oct |
| D18 | `coast` is split into `seaside` (beaches and scenic coast) and `maritime` (port and harbour cities): 14 kinds | Owner decision, 1 Oct: a beach town and a port are different experiences |
| D19 | Overlaps and ties are decided by data rules: `sacred` = a living faith, `ruins` = a dead one; seaside/maritime by port-city rule; wildlife over rural when a strict protected area dominates; the cap of three orders by strength (steps of 0.05), then independent sources, then a fixed priority, then slug; cut kinds and reasons are stored | Panel of sub-agents (geographer, data engineer, outsider, expansionist, auditor), 1 Oct; deterministic and auditable |
| D20 | What you do is a separate dimension (experiences/activities, events, effort and access, season, visitors, advisories); the product sentence stays about kinds | Owner asked to include the Outsider's and Expansionist's lists; kinds say what a place IS |
| D21 | M1 builds first what needs neither the owner nor Wikidata: input pinning, id minting, QID resolver and class checker (run locally by the owner, tested on recorded responses). No id is minted, and the registry is not committed, until `G-LANDMARK` passes with every golden place carrying a resolved QID | Identity is permanent; a mis-resolved QID would be permanent too |
| D22 | Printed-map tiles are cut by recursive balanced subdivision: static country borders, straight dynamic cuts placed in the gaps between neighbouring places, each landmass on its own, stop at 6 places or when no valid cut exists | Owner's idea, 2 Oct; prototyped on the golden places. Stays a proposal until the open points in document 04 §4.1a are settled |
| D23 | The planner layer is typed rows, not columns: `place_edge` (`part_of`, `gateway_of`, `day_trip_from`, `near`), `node` with its own permanent ids and `place_node` (`serves`, never "nearest"), and `place_stay` as a bucket for Icon and Major only, never "recommended", never computed or summed. Reserved: seasons, cost, accessibility, lodging, media. Refused: reviews, ratings, live prices and hours, timetables, routes, itineraries in the shared database. New pending gate `G-STRUCT` | Owner proposal of 2 Oct, reviewed by a five-advisor council; accepted by the owner |
| D24 | The prototype grows to nine countries: Egypt, Peru, Jordan, Tanzania (calibration, golden only) and Morocco, Spain, France, Italy, Türkiye (golden and owner-written H1, 20 rows each). Golden rows for the four new countries were drafted by sub-agents with UNESCO ids checked against the local list; QIDs and several sitelink/population evidence claims are still to verify | Owner decision, 2 Oct: H1 is better from places the owner knows; the four calibration countries keep geographic and kind diversity (desert, wildlife, volcano, Amazon) |
| D25 | Nested monuments are assets of their parent, never places (the Colosseum on Rome, the Uffizi on Florence, Karnak and the Valley of the Kings on Luxor); neighbouring places of the same kind within about 25 km are absorbed into the more famous one, which keeps its name and pin; places of a different kind stay separate and are linked by typed edges (≤ 60 km). Replaces the "either is fine" half of D5. The 40-row structure table was verified by the owner (2 Oct) with 41 further rows added and several rows rejected or reworked | Owner ruling, 2 Oct |
| D26 | Kinds are completed for every city by a fallback rule (population ≥ 100,000, `metropolis`, used only when no other kind survives); a place may still carry no kind in rare cases, with a stated reason, under 2 % of the bundle. Replaces "no firing rule is a build failure" in D3 | Owner decision, 3 Oct |
| D27 | Golden QIDs: 184 of 184 positive rows carry a Wikidata QID (3 Oct). 160 came from the owner's local `make qids` run with a name-and-sitelink rule; 24 contested rows were settled by a five-advisor vote in which every advisor had to find web-search evidence (majority 3/5 or better on every row; the evidence is search-result summaries, not opened item pages). The row's first-named destination (or the UNESCO property item when it names the property) is the target. Duplicate detection now also counts a second place matching a row by name under another QID. Record: `data/golden/qid_decisions.csv` | Owner delegation, 3 Oct; to be re-checked when `make qids` is re-run with full Wikidata access |
| D11 | A new repository for v2, with only the specs, golden set and re-written gates carried over | The v1 pipeline and app were to be replaced anyway; avoids confusion |

## M0 review (1 Oct) and what changed

A five-advisor review of the first M0 found it a sound skeleton but a weak judge. Confirmed by reproduction, then fixed in this repository:

| Finding | Fix |
|---|---|
| Gates crashed on malformed input instead of failing | Every gate is wrapped: an exception is a failure. `G-SCHEMA` validates the bundle first |
| `recorded_cause` in the bundle's own manifest bypassed `G-CHURN` | A cause counts only if listed in committed `data/changelog.json` |
| `G-COVER` read its scope and exemptions from the bundle | Scope and exemptions come from committed `data/scope.json` |
| Relational checks matched on a country-name string; a place under another label evaded them | Matching is by ISO3; a relational row fails if its country has no places or its target is unresolved |
| Matching was not one-to-one; duplicates of a landmark passed | One-to-one assignment; a duplicate fails `G-LANDMARK` |
| `not_credited` checked nothing when the target had no UNESCO id | Compares all shared evidence keys and fails closed when the target is missing |
| The registry was a stub; "an id is never reused for a different key" was untestable | The registry has `keys[]`; `G-ID` enforces key ownership |
| `G-DETERMINISM` only compared files to the build's own hashes | Renamed `G-INTEGRITY`; real determinism is a pending gate (M2) |
| The oracle bundle was a tautology | Kept as a fixture, plus adversarial fixtures (the Quillabamba failure) and a mutation suite; a test fails if a gate has no test that trips it |
| Gates skipped checks silently on small n | Every gate reports `n` and `skipped`; a skip fails unless the build is declared `--prototype` |
| The holdout could be edited or reused | Must be ≥ 100 rows, disjoint from the golden set, and frozen by hash |
| Precision review trusted self-reported verdicts | Rows must link to unique places in the bundle |

Known limits, accepted for now: the golden set is partly circular with the seeding signal (51 of 97 positives rest on UNESCO ids); only the owner-written holdout H1 breaks that, and it must be written and frozen before M2. All golden QIDs are blank until Wikidata can be reached from an unrestricted machine.
