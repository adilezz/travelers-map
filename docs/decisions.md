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
| D3 | 13 kinds, each from a named rule over stored evidence; 1–3 per place; a place with no firing rule is a build failure | The product sentence is only true if kinds are true |
| D4 | The 13th kind, `ruins` (ancient and archaeological remains) | Nine golden rows (Pompeii, Petra, Jerash…) had no honest kind |
| D5 | Only true serial components are never separate pins; nested destinations (Colosseum, Uffizi) may be their own place or evidence on the parent, and are not tested | Owner ruling |
| D6 | Opaque permanent `place_id` from an append-only registry; never derived from an upstream id | Visit records reference ids forever |
| D7 | A World Heritage id is evidence, **not** an identity key | Found by the M0 tests: property 86 legitimately backs both Giza and Saqqara |
| D8 | Western Sahara dissolves into Morocco; Taiwan, Kosovo, Palestine get their own piece; Northern Cyprus, Somaliland and Crimea dissolve (dotted); Kashmir shows the line of control | Owner rulings (document 04 §7) |
| D9 | Personal project: licensing does not bound the design, but every record keeps its source and licence so sharing later is a filter, not a rebuild | Owner direction; cheap insurance |
| D10 | One DuckDB store; bulk dumps processed once; no per-request fees | Cost effectiveness for one person |
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
