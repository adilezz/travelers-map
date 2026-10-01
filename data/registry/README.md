# Registry

`place_registry.parquet` is the append-only identity registry (document 2 §3.2). It is empty until M2 mints ids.

Columns: `place_id`, `keys[]` (`qid:Q…`, `wdpa:…`, `whs:…`, `geonames:…`, `osm:…`), `status` (`active`, `retired`, `merged_into:<id>`, `split_from:<id>`), `minted_build`, `last_seen_build`, `tombstone_reason`.

`v1_crosswalk.csv` maps every v1 id to its v2 `place_id`, or to `none` with a reason (built in M2). The v1 ids come from the archived v1 repository.
