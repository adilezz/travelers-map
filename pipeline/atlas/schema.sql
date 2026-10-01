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

CREATE TABLE place_parent (
  place_id VARCHAR NOT NULL REFERENCES place(place_id),
  parent_id VARCHAR NOT NULL REFERENCES place(place_id),
  relation VARCHAR NOT NULL CHECK (relation IN ('part_of','gateway_of'))
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
CREATE TABLE place_stay (
  place_id VARCHAR PRIMARY KEY REFERENCES place(place_id), typical_stay_hours DOUBLE, source VARCHAR NOT NULL
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
