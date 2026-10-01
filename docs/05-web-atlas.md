# Travelers World Map — Web atlas (carried over from v1, to be rewritten in M5)

> **Status.** This document came from the v1 repository. The product principles, sheets, accounts, trips and export requirements still stand as the starting point; the data contract (§3) is superseded by documents 1–3. References to “documents 2, 3 and 4” inside it mean the v1 design system and architecture documents, which live in the archived v1 repository and will be rewritten. It is rewritten in milestone M5, after the database passes its gates.


Document 5 of 5. Read with document 1 (the place model).

**This is the requirements document for the web atlas.** Where it conflicts with documents 2, 3, or 4, or with a coding prompt, this document wins. Documents 1 (the place model), 2 (database), 3 (validation) and 4 (printed map) govern how a place is chosen, ranked, stored, proven and printed; where this document's data contract (§3) differs, documents 1 and 6 win. Version 2 of the place model (1 October 2026) replaced the 0–100 score with tiers. Document 3 still governs tokens and type unless a section here names a different layout. Document 2 is historical.

Accepted by the owner, 23 August 2026.

---

## 1. What this product is

A traveler's atlas of the Earth that knows the difference between having been to a country and having understood it.

The database holds every place the model selected. The traveler marks what they have seen. The map answers: **which kinds of place have you never been to?**

The sentence after five marks in a country remains:

> Still unseen: desert and steppe, sacred and pilgrimage.

That sentence is the product. Accounts, layers, trips, and exports are how a traveler *uses* it. They are not a second product.

### 1.1 Two objects, one database

| | Web atlas (this MVP) | Printed map (later) |
|---|---|---|
| Holds | Every app place | A spaced subset of holes |
| Geography | Full country land, in **web regions** | Magnetic **tiles** only where holes exist |
| Constraint | Screen, bandwidth, honesty | 3,000 holes, 60 km, 160 km piece size |

Web regions are a tessellation. Printed tiles are a manufacturing subset. They share `place_id`. They do not share polygons.

### 1.2 Who it is for

Someone who travels on purpose. They are not booking a hotel this week. They are not collecting countries. They want to see the kinds of place they keep missing.

### 1.3 Who it is not for

Leaderboards, streaks, “most traveled.” Booking engines. A Google Maps replacement.

---

## 2. Principles (unchanged)

| # | Principle | Consequence |
|---|---|---|
| P1 | Breadth of kinds, not count of places | No completion percentage. No world score, no number. |
| P2 | The map is the interface | Every fact has a spatial form. The register is the same data, for keyboard and for audit. |
| P3 | Marking is one tap | No dialog. Undo is the same tap. |
| P4 | Nothing is hard-deleted | Unmark keeps notes. |
| P5 | No points, badges, streaks | The reward is the map, not a number. |
| P6 | The traveler owns the record | Export in one action, readable without this product. |
| P7 | Selecting never zooms; marking never moves the camera | The only camera move is an explicit “Show on the map.” |
| P8 | The accent means visited | `#A87B22` / `#DBA83E` on marks only. |
| P9 | Kinds are shape and label, never colour | Fourteen categorical colours are not accessible and would fight the accent. |
| P10 | Place identifiers are a migration | A rebuild that reuses an id for a different place fails the build. |

---

## 3. Data contract for MVP

The client does not ship until `make verify` (document 3) passes on the **same** bundle it loads. In summary:

1. Manifest totals equal file counts (G-COUNT).
2. Every place has 1–3 kinds, each with a rule and evidence; all fourteen kinds exist somewhere in the world (G-KIND).
3. Every place has an opaque permanent `place_id`; none is reused or lost (G-ID, G-IDENT).
4. Every place has `name_en` and, where the script differs, `name_local`; searchable aliases; no raw identifiers or markup (G-NAMES).
5. Every place has a tier (Icon / Major / Notable / Local) and a one-line `tier_reason`. **There is no numeric score.**
6. Every app place has exactly one `region_id`; the union of region polygons equals the country land within a documented tolerance (G-REGION).
7. Disputed cases follow the owner's rulings in document 4 §7; a `disputed` marker never inherits a neighbour's rule (G-DISPUTE).
8. `reach` and `best_months` are either sourced or omitted. Never a dummy.
9. Every place exports its evidence list with source, URL and retrieval date, and external ids (QID, OSM, Wikipedia) so links never depend on names.
10. The landmark acceptance set passes (G-LANDMARK).

Licence: WDPA is non-commercial; OSM is ODbL. Resolve both before revenue. Per-record provenance stays.

---

## 4. Information architecture

### 4.1 Desktop (≥ 1024 px)

Material 3 *roles*, document 3 *tokens*.

```
┌─────────────────────────────────────────────────────────────────┐
│ Top app bar: wordmark | search | account | export | theme        │
├─────────────────────────────────────────────────────────────────┤
│ Filter bar (hideable): visited | kinds | passport | density | …  │
├──────────────────────────────────┬──────────────────────────────┤
│                                  │ Side sheet (hideable)         │
│  Map  (≥ 60% at 1440px)          │ Country | Region | Place      │
│  layers FAB-group (not accent)   │ same hide control in          │
│  zoom / fullscreen               │ fullscreen                    │
│                                  │                               │
└──────────────────────────────────┴──────────────────────────────┘
```

No bottom navigation bar. The map is the navigation.

### 4.2 Mobile (< 640 px)

Map full-bleed. Filter bar is a top overlay, hideable. Sheet is a bottom sheet at peek / half / full. Mark control lives in the sheet. Layers, zoom, fullscreen top-right, 44×44, not the accent.

Fullscreen (both breakpoints): the same hide controls for filter bar and sheet. They do not disappear; they collapse to 44×44 chevrons.

### 4.3 Layers (independent toggles)

| Layer | Default | Notes |
|---|---|---|
| Basemap: own polygons | On | Always available, including offline for loaded countries. |
| Basemap: geographic raster | Off | Owner cost decision. Config URL. |
| Basemap: street raster | Off | Roads and labels, not Street View. Same cost rule. |
| Web regions | Off at world zoom; on at country zoom | Full tessellation. |
| Printed tile preview | Off | The pitched “object” view. Separate mode, not a fourth basemap. |
| Places | On | Pins. Density filter applies here. |

Geographic and street are mutually exclusive *basemaps*. Regions and places are overlays.

### 4.4 Density

A single control: **how many places to show per country** (default: all that pass other filters).

- Ranking is by tier, then notability within the country, then name (document 1 §6). No number is shown.
- The control warns: “Score is local to each country. 12 places in Malta are not 12 places in Canada.”
- Distribution is **per country**, never a global top-N (that would be a world ranking).
- The register and the map read the same cap.

### 4.5 Search

Search matches place, region, and country names.

- Choosing a hit **opens the sheet**. It does not move the camera.
- “Show on the map” (already in the sheet) is the camera move.
- Empty search results name the query and offer to clear filters.

---

## 5. The three sheets

Every sheet answers: what is here, and what have I not seen here?

### 5.1 Country

- Name, outbound links (Wikipedia; optionally a maps search).
- Entry rule if a passport is chosen. Dependencies not in the passport index: “not stated,” never inherited.
- Counts: places (after filters), marked, by kind (seen / available). **No percentage.**
- Gap sentence.
- Web regions in this country.
- Top places (capped by density).
- Bulk mark.

Disputed flag: if any place has `disputed: "ESH"` (or later codes), one line: “Some places sit in territory whose sovereignty is disputed. We do not draw that border.”

### 5.2 Web region (the tile on the web)

- Name, country, type: `region` (tessellation) vs `printed-tile` (manufacturing preview).
- Places inside, marked, by kind.
- Gap sentence scoped to the region.
- List of places.

### 5.3 Place

Document 2 §8, plus:

- Why it is here: the evidence, grouped as built heritage, natural setting and living culture, each with its source. No bars and no numbers.
- Why it is here (provenance sentence).
- Standing: the tier and its one-line reason ("World Heritage · 140 language editions").
- When to go: only if `best_months` is non-empty.
- Nearby (computed).
- Elsewhere: Open in Maps (query by coordinates), OSM, Wikipedia, Wikimedia Commons. Store a Google `place_id` if we have one; use it only to link out.
- Mark, note, date, add to trip, show on map.

---

## 6. Accounts

Local-first remains. The product works with no account.

| Action | Behaviour |
|---|---|
| Sign in (email magic link or Google OAuth) | Create or attach a user. **Merge** local visits into the server (last-write-wins per `place_id` by `marked_at`). |
| Link another provider | Same user. |
| Sign out | Local copy stays. Queue pauses. |
| Delete account | Deletes server rows and backups within a stated window. Offers an export first. |
| Sync | `visit`, `trip`, `trip_place`, `profile`. RLS. No hard delete of visits. |

No public profiles. No third-party analytics on the map.

---

## 7. Trips

Still: collect → assign to days → see connected.

MVP addition: **optional** legs from a routing provider.

- Interface: `route(from, to) → { geometry, duration?, modes[], attribution, warning? }`.
- First adapter: one of Rome2Rio, an OTP instance, or a comparable multimodal API — **chosen and paid for**, proxied by `server/`. Not called from the browser with a vendor key.
- If the adapter is missing or fails: straight line, labelled “not a route.”
- Wrong times are worse than none: show duration only with the provider's attribution, and a line that this is a sketch.
- No bookings. No collaboration in this MVP.

---

## 8. Export

Always applies the **current filters** (visited, kinds, country, density, passport, search).

### 8.1 Spreadsheet (`.xlsx`)

Columns: name, country, region, lat, lon, kinds (labels, not codes), tier, visited, visited_on, note, WHS, sources, `place_id`.

Multi-select: if the traveler has ticked rows in the register, export the tick set; otherwise the filtered set. Cap with a warning above 10,000 rows.

Readable without this product (real `.xlsx`, not HTML-in-disguise).

### 8.2 Printable map

A poster of the **current scope** (world / country / region), current filters, current density.

On open, suggest:

| Scope | Suggested size | Suggested place cap |
|---|---|---|
| World | 700 × 500 mm | 800 (or printed-hole subset) |
| Country | 400 × 500 mm | all in scope, or density cap |
| Region | 300 × 300 mm | all in scope |

The traveler may edit millimetres and place count. Alerts (not blockers) when:

- Size < A4: “This will be a diagram, not a wall map.”
- Places so dense that implied spacing < 4.5 mm at the chosen size: “Pins will overlap. Raise the size or lower the count.”
- World + all 12k places: “The wall map uses 60 km spacing and about 2,500 drilled holes against a budget of 3,000. This export will not match it.” The budget is 3,000; the count is whatever the last build achieved, and the warning quotes the build, not the budget.

Output: PDF (vector land, type as text). Accent still means visited if the traveler includes visited state; otherwise all marks are open rings.

JSON export/import of the record remains, as in document 2 §12.

---

## 9. Stack (MVP)

Unchanged from document 4 except:

| Layer | Choice |
|---|---|
| Client | Vanilla TypeScript, existing store. No framework required for MVP. A component library may wrap chrome later; the map stays MapLibre. |
| Map | MapLibre GL JS, pinned, re-spiked on upgrade. |
| Basemap | Own polygons default. Third-party raster opt-in. |
| Place files | GeoJSON now; vector tiles before ~25,000 points. |
| User service | `server/` : managed Postgres + auth, RLS. |
| Routing | Server-side provider interface. |
| Design | Document 3 tokens. Material 3 for *structure* of app bar, sheet, chips, dialogs. |

Bevelled extrusion remains parked until MapLibre grows the property. Fake the grounding shadow; do not pretend a `try/catch` rounded a corner.

---

## 10. What this MVP still does not do

| Out | Why |
|---|---|
| Native apps | Web must earn them. |
| Photo hosting | Link out. |
| Social feeds | Never, unless travelers ask. |
| Leaderboards | Never. |
| Google Maps as renderer | Terms, billing, no true interior rings. |
| Invented seasonality or reach | Hide until sourced. |
| Drawing contested borders | Dissolve + explicit rulings only. |
| Cutting blank magnetic tiles to fill the Sahara | The wall map may have empty land. The *web region layer* may not. |

---

## 11. How we will know it works

Keep document 2 §14. Add:

- Dissolve and region-coverage assertions in CI on every bundle.
- Share of searches that return nothing, by country.
- After sign-in, zero lost local marks (merge test).
- Export round-trip: XLSX columns match the filter; PDF spacing warning fires when it should.

Vanity traffic is still not a success metric.
