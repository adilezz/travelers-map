# Travelers World Map

A traveler's atlas of the Earth, and a wall to hang it on.

This is a **personal** project. The first idea, and still the heart, is a printed world map, about 3 × 2 m, with the borders of territories, a magnetic piece for each territory and pins for cities and places, so the owner can *see physically* where they have been and where they may go next. A web atlas is the second rendering of the same database.

The question the product answers is not "how many countries have you visited?" but **which kinds of place have you never been to?**

> Still unseen in Egypt: desert and dry plains, holy places and pilgrimage.

## Status

Version 2, started 1 October 2026 in this clean repository. The v1 attempt lives in the archived `travelers-world-map` repository; the reasons it was retired are in [docs/decisions.md](docs/decisions.md).

| Milestone | State |
|---|---|
| **M0** Specs, ground truth, gates as code | **Done**: 5 specification documents, a 106-row golden set, 16 gates, 116 tests |
| M1 Backbone: pinned inputs, Wikidata filter, registry, asset table | **Started.** Built and tested offline: input pinning, id minting, the QID resolver and class checker. Waiting on: the owner's H1 and a local run of `make qids` and `make classes` |
| M2 Places: candidates, resolution, admission, names | |
| M3 Rank and kinds | |
| M4 Printed map | |
| M5 Web atlas | |

The first prototype covers five countries (Egypt, Peru, Italy, Jordan, Tanzania) and must pass its golden set before the world is built.

## Start here

```bash
pip install duckdb pytest ruff     # Python 3.11+
make test                          # 95 tests; must always pass
make lint
make verify                        # expected to fail: there is no bundle yet
make verify BUNDLE=path/to/bundle ARGS=--prototype
```

`make verify` exits 1 until a published bundle passes **every** gate; the `make: *** Error 1` it prints is that exit status, not a crash. Nothing is publishable while any gate is failing or pending.

## Read in this order

| Document | What it settles |
|---|---|
| [01 The place model](docs/01-place-model.md) | What a place is, how it is admitted, ranked into tiers, and given kinds |
| [02 Database architecture](docs/02-database-architecture.md) | Storage, identity, pipeline stages, sources, schema, milestones |
| [03 Validation](docs/03-validation.md) | Golden set, holdout, the gates, and the threat model they defend against |
| [04 The printed map](docs/04-printed-map.md) | The wall map: pieces, pins, selection, disputed-territory rulings, editions |
| [05 Web atlas](docs/05-web-atlas.md) | The web product (carried over from v1; rewritten in M5) |
| [decisions](docs/decisions.md) | Why v2 exists and every decision taken, with its reason |

## Repository

```
docs/            the specifications and the decision log
data/            small, versioned inputs: golden set, holdout, rules, anchors, registry, scope
  golden/        ground truth written before the pipeline
  holdout/       the independent test set (owner-written, then frozen by hash)
  inputs/        pinned source manifest and the UNESCO property list
pipeline/atlas/  the gates, matcher, bundle and registry readers, schema, verify command
pipeline/tests/  unit tests, adversarial fixtures, mutation suite
```

Large raw inputs (the Wikidata dump and others) are not in git. `data/inputs/MANIFEST.json` pins each one by hash.

## Rules the product will not break

- The accent colour means **visited** and nothing else.
- No completion percentage for a country; no points, badges or streaks.
- No numeric score anywhere: tiers (Icon, Major, Notable, Local), never a world ranking.
- Kinds are shape and label, never colour; each carries a reason you can read.
- `place_id` is opaque and permanent. A rebuild that reuses an id for a different place is a failed build.
- The owner's rulings (anchors, vetoes, disputed territories) always beat the algorithm.
- A travel history is private and never a public profile.
