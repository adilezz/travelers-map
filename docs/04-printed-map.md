# Travelers World Map — The Printed Map

Document 4 of the v2 set. Version 2.0, 1 October 2026. Reads with document 1 (places) and document 2 (the database).

The printed map was the first idea and remains the heart of the project: **a wall on which the owner sees, physically, where they have been and where they may go next.**

---

## 1. The object

A large flat printed map, about 3 × 2 m, showing continents, oceans and clear country borders, with the rivers, mountains, lakes and deserts that shape travel behind them.

- **Pieces.** Magnetic pieces, one per territory (or per group of territories, §5), each a physical object that can be lifted, held and put back. The piece carries a relief of its land.
- **Pins.** Each piece is drilled at the real coordinates of the places on it. A pin pushed into a hole means *I have been here*. A different pin means *I want to go*. An empty hole is a proposal.
- **Reading.** From across the room: which continents are full, which regions are empty. Up close: which place, which kind.

The promise: if you fill every hole in a country, you will have understood that country.

## 2. One database, two renderings

The printed map is **a selection from the web layer**, never a different list. The web atlas holds every admitted place; the printed map holds the ones that fit and the owner chose. Selection removes nothing from the database. A place that does not get a hole still exists, is still markable and still counts in the atlas.

## 3. Physical constants

Parameters, not facts; they are set by a **physical prototype** (a 1:1 test plate with pins at 4.0, 4.5 and 5.0 mm spacing) before any production drilling.

| Quantity | Initial value | Derivation |
|---|---|---|
| Map area | 3.00 × 1.46 m | Inside a 3 × 2 m wall footprint |
| Projection | Equal-area (Equal Earth) | A piece's size reads as importance; area should not lie |
| Scale | ≈ 1 : 13,400,000 | 40,075 km of equator across 3.00 m |
| Ground per millimetre | ≈ 13.4 km | From scale |
| Minimum hole spacing | 4.5 mm ≈ 60 km | Pin head plus drilling tolerance |
| Registration tolerance | ± 0.5 mm ≈ 7 km | Printer plus drilling; parameter `registration_mm` |
| Minimum piece extent | 12 mm ≈ 160 km | Handling and magnet seating |
| Hole budget | 3,000 | Practical upper bound on drilling and legibility |

The budget is a **ceiling**. A build reports the count achieved and the reason it fell short; v1 used 2,486 of 3,000 because the spacing rule bound.

## 4. Pieces (territories)

### 4.1 Rules

1. Start from first-level administrative units of each state.
2. Merge a unit holding fewer than three printed places with the adjacent unit minimising added boundary length plus dissimilarity of kinds.
3. Split a unit holding more than six along second-level units.
4. A piece never crosses an international border or a contested line.
5. A piece is at least 12 mm across; smaller ones are handled as in 4.2.
6. A piece exists only where holes exist; empty land is printed but carries no piece. A wall with gaps is honest. (The web atlas, by contrast, tessellates all land into regions — document 2 §8.)
7. A piece is **named from the polygon**, never from the merge that made it: the first-level unit containing its centroid; failing that the largest settlement inside it; failing that a compass qualifier on the country. A piece named for a settlement must contain it.

### 4.2 Small states and islands

Where a state is smaller than the minimum piece (Vatican, Monaco, Singapore, Malta, most Caribbean and Pacific islands):

- **Token piece.** A 12 mm piece sits at the territory's position, larger than true scale, with a leader line to its true outline where the two disagree. Neighbouring tokens that would overlap are arranged along a straight leader, never hidden.
- **Archipelago piece.** Island groups share one piece (Maldives, Kiribati, Cook Islands) with one hole per admitted place.
- The piece list records `scale_exaggeration` so the printed legend can say so.

## 5. Pins and states

| State | Pin | Meaning |
|---|---|---|
| Empty | No pin | Not yet |
| Visited | Accent-colour pin | I have been |
| Next | Contrasting ring pin | I want to go |
| Other | None | Nothing else is encoded on the wall |

The accent means **visited** and nothing else. Kinds are never colours. A small printed glyph beside each hole (not colour) may encode the primary kind where the legend allows; the web atlas is where kinds are read in full.

## 6. Selection

### 6.1 Procedure

Inputs: the admitted places with tiers (document 1), the owner's **personal set** (visited and next), the owner's `print_override.csv`, the territory table, the physical constants.

1. **Forced.** Owner `force_in` places, then the owner's **visited and next** places, enter first. The wall must show *my* record. If a forced place sits within the spacing floor of another forced place, the pair is resolved by an **inset** (6.3) or, failing that, a *twin hole* with an explicit entry in the exception list. Forced entries are the only way the spacing floor is broken, and every break is listed.
2. **Floors.** Every sovereign state gets at least one hole (its highest-tier place); every territory that has a piece gets at least one.
3. **Quota.** Each country's quota is `clamp(round(budget · q_c / Σq), 1, 40)` with `q_c = 2.5·ln(1 + area/50,000) + 0.6·kinds + 1.2·ln(1 + recognition count)`, and a floor of six for countries with six or more kinds. (v1's quota, kept: it balances area, variety and recognition.)
4. **Greedy fill.** Remaining holes are chosen one at a time by marginal gain:

   ```
   G(i | S) = tierweight(i) · novelty(i | S) · spacing(i, S)
   ```

   `tierweight`: Icon 1.0, Major 0.6, Notable 0.3, Local 0.1. `novelty`: full value for a kind not yet on the country's selection, halving with each place already covering it. `spacing`: zero inside the floor, ramping to one at twice the floor. A candidate at the top of its country pays a reduced novelty penalty, so a world-class second-of-a-kind stays selectable.
5. **Owner veto.** `force_out` places are removed last and not replaced unless the owner asks.

The objective is monotone and submodular, so greedy selection reaches at least 63 % of the optimum.

### 6.2 What selection must not do

- Never promote a Local place over an unselected Icon in the same country within the spacing floor.
- Never drop a visited or next place for algorithmic reasons.
- Never exceed the budget; never fall silent about a country that received fewer holes than its Icons.

### 6.3 Insets

About a third of essential places lie within 60 km of another. Insets are a requirement, not an embellishment, but targeted: needed for dense regions (Kathmandu valley, the Cairo–Giza–Saqqara belt, Kyoto–Nara, the Amalfi coast, the Dolomites, Belgium and the Netherlands), not for countries that spread naturally.

| To separate places this far apart | Map width required | Or an inset at |
|---|---|---|
| 40 km | 4.5 m | 1.5× |
| 25 km | 7.2 m | 2.4× |
| 15 km | 12.0 m | 4.0× |

The build reports every conflicting pair per country with the inset magnification that would resolve it. Insets are listed in `inset` (region, magnification, frame) and become part of the edition.

## 7. Disputed territories — owner rulings

No contested border is drawn by accident. Each case needs an explicit decision, recorded in the territory table (`display_policy`, `ruling_ref`). The build warns on any unruled case and does not choose one.

Policies available: **`dissolve`** (outline merges into the administering state; places keep their coordinates and carry `disputed`), **`own_piece`** (its own piece, dotted outline, labelled *disputed*), **`omit`** (undrawn).

| Case | v1 ruling | v2 ruling | Status |
|---|---|---|---|
| Western Sahara | dissolve into Morocco | `dissolve` into Morocco (outline merges; places read Morocco, carry `disputed: ESH`) | **decided 1 Oct 2026** |
| Taiwan | unruled | `own_piece` | **decided 1 Oct 2026** (recommended default adopted) |
| Kosovo | unruled | `own_piece` | **decided 1 Oct 2026** (recommended default adopted) |
| Palestine | unruled | `own_piece` (West Bank, Gaza) | **decided 1 Oct 2026** (recommended default adopted) |
| Northern Cyprus | unruled | `dissolve` into Cyprus, dotted | **decided 1 Oct 2026** (recommended default adopted) |
| Somaliland | unruled | `dissolve` into Somalia, dotted | **decided 1 Oct 2026** (recommended default adopted) |
| Crimea | unruled | `dissolve`, dotted, labelled | **decided 1 Oct 2026** (recommended default adopted) |
| Kashmir | unruled | dotted line of control, labelled | **decided 1 Oct 2026** (recommended default adopted) |

The owner ruled on 1 October 2026: Western Sahara dissolves into Morocco, and the recommended default is adopted for the other seven. The map is the owner's, and so is every ruling; any change is a dated edit to this table. A case not listed here has no ruling: the web atlas shows its places with a "disputed" marker and **inherits no rule** from a neighbouring state, and the printed edition cannot be released until it is ruled. Each ruling is also recorded in `territory.display_policy` and `ruling_ref` (document 2 §4).

A dissolve target is matched on an **alias list**, never one string (ISO 3166-1 alpha-3, the boundary source's name, every name in place records), so a dissolve cannot silently do nothing.

## 8. Editions

A printed map is an object in time. Each print is an **edition**.

- **Edition record.** Edition number, build id, drill file, piece list, inset list, date, the exceptions list (twin holes, spacing breaks), and the set of pins at the time.
- **Frozen holes.** Once an edition is drilled, its holes are fixed. The next edition starts from them: a hole stays unless the owner removes it. New holes are additions or replacements the owner approves; a refresh never silently moves a hole.
- **Diff.** `edition_diff` lists holes added, removed, moved (with distance), renamed and re-tiered between editions.
- **Reprint.** A reprint is deliberate: a new edition from the latest build, owner-approved diff, with the old drill file kept.
- **My pins.** Because the wall shows the owner's record, an edition can be generated *for the owner's current state*. The wishlist (`next`) is how future editions grow in directions the owner cares about.

## 9. Proof and labels

- **Proof.** Before drilling, a **1:1 vector proof** (SVG/PDF) is produced at true scale with every hole, piece outline and inset. The gate G-PRINT checks spacing, piece extent, the quota, forced entries and exceptions on the proof itself, and the owner inspects a printed tile or a full-scale section.
- **Labels.** Pieces and notable places are labelled in Latin script with the local name beneath where space allows. Labels are positioned at proof time; no label covers a hole.
- **Legend.** A legend panel states the projection, the scale, the scale exaggeration of token pieces, the meaning of pin states and the disputed-territory note.
- **Print base.** Land, coastlines, relief, rivers, lakes, ranges and deserts from Natural Earth (public domain) at print resolution; vector wherever the printer allows.

## 10. Costs and effort

The printed object is the one place where money buys quality rather than convenience. Strategy: prototype small (a test plate, one region), prove spacing and magnets, then commission the full print and pieces. Digital work (selection, proof, edition files) costs only effort and is finished before any physical spend.
