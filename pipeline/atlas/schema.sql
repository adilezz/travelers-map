-- Travelers World Map v2 schema (document 2 section 4).
-- Geometry is stored as GeoJSON text so the schema needs no extension; M4 may move it to
-- the DuckDB spatial extension.

CREATE TABLE source (
  source_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, version VARCHAR, url VARCHAR,
  sha256 VARCHAR, licence VARCHAR, restricted BOOLEAN DEFAULT FALSE,
  redistributable BOOLEAN DEFAULT TRUE,  -- a gate keeps non-redistributable sources out of a shareable bundle
  retrieved DATE
);

CREATE TABLE asset (          -- one row per source record, with its own provenance
  asset_id VARCHAR PRIMARY KEY, source_id VARCHAR NOT NULL REFERENCES source(source_id),
  source_key VARCHAR NOT NULL, role VARCHAR, class VARCHAR, name VARCHAR,
  geom VARCHAR, lat DOUBLE, lon DOUBLE, attrs JSON,
  licence VARCHAR, source_url VARCHAR NOT NULL, retrieved DATE NOT NULL,
  snapshot DATE                                          -- date of the source snapshot this row came from
);

CREATE TABLE place (
  place_id VARCHAR PRIMARY KEY,
  type VARCHAR NOT NULL CHECK (type IN ('settlement','site','area','route')),
  name_en VARCHAR NOT NULL, name_local VARCHAR, country_iso3 VARCHAR NOT NULL, admin1_id VARCHAR,
  lat DOUBLE NOT NULL, lon DOUBLE NOT NULL, footprint VARCHAR,
  tier VARCHAR NOT NULL CHECK (tier IN ('Icon','Major','Notable','Local')),
  tier_reason VARCHAR, why VARCHAR,
  evidence_depth VARCHAR CHECK (evidence_depth IN ('rich','thin')),
  qid VARCHAR, osm_id VARCHAR, geonames_id VARCHAR, wdpa_id VARCHAR, whs_id VARCHAR, wikipedia VARCHAR,
  near_place_id VARCHAR, disputed VARCHAR,
  status VARCHAR NOT NULL DEFAULT 'active', minted_build VARCHAR NOT NULL
);

CREATE TABLE place_asset (
  place_id VARCHAR NOT NULL REFERENCES place(place_id),
  asset_id VARCHAR NOT NULL REFERENCES asset(asset_id),
  link_method VARCHAR NOT NULL
    CHECK (link_method IN ('qid','external_tag','containment','name_distance','owner')),
  confidence DOUBLE NOT NULL CHECK (confidence BETWEEN 0 AND 1), role VARCHAR,
  PRIMARY KEY (place_id, asset_id)
);

CREATE TABLE place_alias (
  place_id VARCHAR NOT NULL REFERENCES place(place_id), alias VARCHAR NOT NULL, lang VARCHAR,
  kind VARCHAR CHECK (kind IN ('endonym','exonym','translit','former'))
);

CREATE TABLE place_kind (
  place_id VARCHAR NOT NULL REFERENCES place(place_id),
  kind VARCHAR NOT NULL CHECK (kind IN ('capital','old_town','seaside','maritime','mountain','desert','forest',
    'water','volcanic','wildlife','sacred','rural','metropolis','ruins')),
  rule_id VARCHAR NOT NULL, strength DOUBLE NOT NULL,
  evidence_asset_ids VARCHAR[] NOT NULL CHECK (len(evidence_asset_ids) > 0),
  PRIMARY KEY (place_id, kind)
);

CREATE TABLE place_metric (
  place_id VARCHAR PRIMARY KEY REFERENCES place(place_id),
  sitelinks INTEGER, pageviews_12m BIGINT,
  pageviews_monthly INTEGER[],          -- the twelve monthly values, for seasonality of interest
  recognition DOUBLE, size_term DOUBLE, n_raw DOUBLE
);

-- Structure layer (document 1 section 4.3, document 2 section 4.2). Typed, sourced, time-valid edges.
-- part_of      src lies inside dst (Colosseum part_of Rome); a DAG, a place may have more than one parent
-- gateway_of   src is the town through which dst is reached (Aguas Calientes gateway_of Machu Picchu)
-- day_trip_from src is a separate destination reached from dst in a day (Versailles day_trip_from Paris); never containment
-- near         src and dst are neighbours a traveller thinks of together; weakest relation
CREATE TABLE place_edge (
  src_id VARCHAR NOT NULL REFERENCES place(place_id),
  dst_id VARCHAR NOT NULL REFERENCES place(place_id),
  relation VARCHAR NOT NULL CHECK (relation IN ('part_of','gateway_of','day_trip_from','near')),
  method VARCHAR NOT NULL CHECK (method IN ('wikidata','osm_containment','footprint','owner','rule')),
  confidence DOUBLE NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  source_asset_id VARCHAR REFERENCES asset(asset_id),
  restricted BOOLEAN NOT NULL DEFAULT FALSE,        -- derived from a restricted source (OSM, WDPA): kept out of a shareable bundle
  valid_from DATE, valid_to DATE,
  PRIMARY KEY (src_id, dst_id, relation),
  CHECK (src_id <> dst_id)
);

-- Transport nodes are not places and never enter admission or tiers (document 2 section 4.2).
CREATE TABLE node (
  node_id VARCHAR PRIMARY KEY CHECK (regexp_matches(node_id, '^nd_[0-9a-hjkmnp-tv-z]{10}$')),  -- permanent, own registry
  node_type VARCHAR NOT NULL CHECK (node_type IN ('airport','port','ferry_terminal','rail_station','bus_terminal')),
  name VARCHAR NOT NULL, country_iso3 VARCHAR NOT NULL, lat DOUBLE NOT NULL, lon DOUBLE NOT NULL,
  iata VARCHAR, icao VARCHAR, station_code VARCHAR, qid VARCHAR, osm_id VARCHAR,
  importance VARCHAR CHECK (importance IN ('international','national','regional','local')),
  status VARCHAR NOT NULL DEFAULT 'active', restricted BOOLEAN NOT NULL DEFAULT FALSE,
  source_asset_id VARCHAR REFERENCES asset(asset_id), snapshot DATE
);
-- "serves", never "nearest": the relation names the node a traveller really uses (Petra served by Aqaba, Zanzibar by ZNZ and the Stone Town ferry).
CREATE TABLE place_node (
  place_id VARCHAR NOT NULL REFERENCES place(place_id),
  node_id VARCHAR NOT NULL REFERENCES node(node_id),
  relation VARCHAR NOT NULL CHECK (relation IN ('in','serves')),   -- in = the node lies inside the place
  mode VARCHAR NOT NULL CHECK (mode IN ('air','rail','sea','road')),
  distance_km DOUBLE NOT NULL CHECK (distance_km >= 0),            -- straight line, a floor; road or rail time is never stored
  method VARCHAR NOT NULL CHECK (method IN ('wikidata','osm_containment','distance_rule','owner')),
  confidence DOUBLE NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  restricted BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (place_id, node_id, mode)
);

-- Reserved for later milestones (document 2 section 4.1); empty until then.
CREATE TABLE place_crossref (
  place_id VARCHAR NOT NULL REFERENCES place(place_id), scheme VARCHAR NOT NULL, value VARCHAR NOT NULL,
  valid_from DATE, valid_to DATE, PRIMARY KEY (place_id, scheme, value)
);
CREATE TABLE place_text (
  place_id VARCHAR NOT NULL REFERENCES place(place_id), lang VARCHAR NOT NULL,
  kind VARCHAR NOT NULL CHECK (kind IN ('why','tip','summary')), text VARCHAR NOT NULL,
  source_asset_id VARCHAR REFERENCES asset(asset_id), model VARCHAR, frozen_build VARCHAR,
  PRIMARY KEY (place_id, lang, kind)
);
CREATE TABLE place_season (
  place_id VARCHAR NOT NULL REFERENCES place(place_id),
  month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12), score DOUBLE, source VARCHAR NOT NULL,
  PRIMARY KEY (place_id, month, source)
);
CREATE TABLE travel_effort (
  place_id VARCHAR NOT NULL REFERENCES place(place_id), from_hub VARCHAR NOT NULL, hours DOUBLE,
  mode VARCHAR, source VARCHAR NOT NULL
);
-- Typical time at a place: a labelled estimate, never advice. A bucket and a range, never minutes; absent means unknown, not short.
-- Only Icon and Major places get one, and only from the owner or a source's own words (Wikivoyage text); never a sum of children.
CREATE TABLE place_stay (
  place_id VARCHAR PRIMARY KEY REFERENCES place(place_id),
  stay_bucket VARCHAR NOT NULL CHECK (stay_bucket IN ('hours','half_day','day','multi_day')),
  hours_min DOUBLE, hours_max DOUBLE CHECK (hours_max IS NULL OR hours_min IS NULL OR hours_max >= hours_min),
  method VARCHAR NOT NULL CHECK (method IN ('owner','source_text')),
  confidence VARCHAR NOT NULL CHECK (confidence IN ('high','medium','low')),
  source VARCHAR NOT NULL, snapshot DATE
);
-- Pointers out, never copies: opening hours, tickets and advisories stay with their owners.
CREATE TABLE place_link (
  place_id VARCHAR NOT NULL REFERENCES place(place_id),
  rel VARCHAR NOT NULL CHECK (rel IN ('official','tickets','authority','advisory')),
  url VARCHAR NOT NULL, retrieved DATE NOT NULL, PRIMARY KEY (place_id, rel, url)
);

-- Experiences and facts that never drive admission, tier or the kind cap (document 1 section 7.4).
CREATE TABLE place_activity (
  place_id VARCHAR NOT NULL REFERENCES place(place_id), activity VARCHAR NOT NULL,
  rule_id VARCHAR NOT NULL, strength DOUBLE NOT NULL,
  evidence_asset_ids VARCHAR[] NOT NULL CHECK (len(evidence_asset_ids) > 0),
  PRIMARY KEY (place_id, activity)
);
CREATE TABLE place_event (
  place_id VARCHAR NOT NULL REFERENCES place(place_id), event_qid VARCHAR NOT NULL,
  month_start INTEGER CHECK (month_start BETWEEN 1 AND 12), month_end INTEGER CHECK (month_end BETWEEN 1 AND 12),
  recurrence VARCHAR, source VARCHAR NOT NULL
);
CREATE TABLE place_visitors (
  place_id VARCHAR NOT NULL REFERENCES place(place_id), year INTEGER NOT NULL, count BIGINT NOT NULL,
  source VARCHAR NOT NULL, source_url VARCHAR NOT NULL   -- official statistics only; never reviews
);
CREATE TABLE place_advisory (
  place_id VARCHAR, country_iso3 VARCHAR, level VARCHAR NOT NULL, issuer VARCHAR NOT NULL,
  issued DATE NOT NULL, source_url VARCHAR NOT NULL       -- a dated, sourced fact; never our own score
);
CREATE TABLE place_access (
  place_id VARCHAR PRIMARY KEY REFERENCES place(place_id),
  effort_class VARCHAR CHECK (effort_class IN ('easy','moderate','demanding','expedition')),
  elevation_m DOUBLE, ascent_m DOUBLE, trail_distance_km DOUBLE, permit_required BOOLEAN,
  wheelchair VARCHAR CHECK (wheelchair IN ('yes','limited','no')),   -- absent means unknown, never 'no'
  source VARCHAR NOT NULL
);
CREATE TABLE place_facet (
  place_id VARCHAR NOT NULL REFERENCES place(place_id), facet VARCHAR NOT NULL, value VARCHAR NOT NULL,
  source VARCHAR NOT NULL                                  -- escape hatch for any later key/value dimension
);

CREATE TABLE merge_log (build VARCHAR, loser_key VARCHAR, survivor_place_id VARCHAR, method VARCHAR, reason VARCHAR);
CREATE TABLE split_log (build VARCHAR, place_id VARCHAR, new_place_id VARCHAR, reason VARCHAR);
CREATE TABLE review_queue (build VARCHAR, candidate_key VARCHAR, signals JSON, reason VARCHAR);

CREATE TABLE territory (
  territory_id VARCHAR PRIMARY KEY, iso3 VARCHAR, sovereign_iso3 VARCHAR,
  kind VARCHAR CHECK (kind IN ('state','dependency','disputed','uninhabited')),
  display_policy VARCHAR CHECK (display_policy IN ('own_piece','dissolve','omit')),
  ruling_ref VARCHAR, geom VARCHAR
);
CREATE TABLE region (region_id VARCHAR PRIMARY KEY, territory_id VARCHAR REFERENCES territory(territory_id), name VARCHAR, geom VARCHAR);
CREATE TABLE piece (
  piece_id VARCHAR, edition INTEGER, territory_id VARCHAR REFERENCES territory(territory_id),
  name VARCHAR, geom VARCHAR, printable BOOLEAN, place_ids VARCHAR[], PRIMARY KEY (piece_id, edition)
);
CREATE TABLE print_selection (
  edition INTEGER, place_id VARCHAR REFERENCES place(place_id), hole_lat DOUBLE, hole_lon DOUBLE,
  reason VARCHAR, pinned_by VARCHAR, PRIMARY KEY (edition, place_id)
);
CREATE TABLE print_override (place_id VARCHAR, action VARCHAR CHECK (action IN ('force_in','force_out','swap')), note VARCHAR);

CREATE TABLE build (
  build_id VARCHAR PRIMARY KEY, started TIMESTAMP, manifest_sha VARCHAR, git_commit VARCHAR,
  params JSON, gates JSON
);
