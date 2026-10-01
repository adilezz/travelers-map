-- The owner's own state (document 2 section 4.1). A SEPARATE store from the shared place
-- database: it is never rebuilt, never shipped in a bundle, and is keyed to place_id only
-- (follow merged_into chains in the registry). There are deliberately no foreign keys into
-- the shared schema, and no review or recommendation data about places belongs here either:
-- these are the owner's own experiences.

CREATE TABLE visit (
  visit_id VARCHAR PRIMARY KEY,
  place_id VARCHAR NOT NULL,
  date_from DATE, date_to DATE,
  precision VARCHAR NOT NULL DEFAULT 'unknown'
    CHECK (precision IN ('day','month','season','year','unknown')),
  source VARCHAR NOT NULL DEFAULT 'manual'
    CHECK (source IN ('manual','photo','takeout','gpx','import')),
  party VARCHAR,
  rating INTEGER CHECK (rating BETWEEN 1 AND 5),
  note VARCHAR, photo_refs VARCHAR[], track_ref VARCHAR,
  created TIMESTAMP DEFAULT current_timestamp,
  CHECK (date_to IS NULL OR date_from IS NULL OR date_to >= date_from)
);

CREATE TABLE wishlist (
  place_id VARCHAR PRIMARY KEY, priority INTEGER CHECK (priority BETWEEN 1 AND 5),
  why_note VARCHAR, added DATE DEFAULT current_date
);

CREATE TABLE visit_candidate (
  candidate_id VARCHAR PRIMARY KEY, place_id VARCHAR NOT NULL,
  evidence JSON NOT NULL, confidence DOUBLE NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  status VARCHAR NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','rejected')),
  created TIMESTAMP DEFAULT current_timestamp
);
