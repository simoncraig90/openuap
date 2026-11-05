-- openuap: consolidated UFO/UAP event database (SQLite + FTS5)
PRAGMA journal_mode = WAL;
PRAGMA page_size = 8192;

CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT
);

-- One row per upstream catalogue. Licensing and provenance live here so an AI
-- answering questions can cite where a record came from and what it may be used for.
CREATE TABLE IF NOT EXISTS sources (
  source_key    TEXT PRIMARY KEY,     -- short id used in events.source_key
  name          TEXT NOT NULL,
  publisher     TEXT,
  url           TEXT,
  license       TEXT,                 -- human-readable licence / permission note
  access_type   TEXT,                 -- public | public-mirror | restricted | licensed
  coverage      TEXT,                 -- e.g. "worldwide, 1800-2014"
  record_count  INTEGER DEFAULT 0,
  fetched_from  TEXT,                 -- file or URL actually ingested
  fetched_at    TEXT,
  notes         TEXT
);

CREATE TABLE IF NOT EXISTS events (
  id                INTEGER PRIMARY KEY,
  source_key        TEXT NOT NULL REFERENCES sources(source_key),
  source_record_id  TEXT,             -- identifier inside the source (case number, index)
  event_type        TEXT,             -- sighting | close_encounter | document | historical | nuclear_test | other
  -- when
  date_text         TEXT,             -- as written in the source
  date_iso          TEXT,             -- sortable: YYYY-MM-DD, YYYY-MM or YYYY
  year              INTEGER,
  month             INTEGER,
  day               INTEGER,
  date_precision    TEXT,             -- day | month | season | year | decade | century | unknown
  date_approx       INTEGER DEFAULT 0,
  time_text         TEXT,             -- local time as written ("20:30", "~18:00", "2:30 PM EDT")
  -- where
  location_text     TEXT,             -- as written
  city              TEXT,
  region            TEXT,             -- state / province / département
  country           TEXT,             -- normalised name
  country_code      TEXT,             -- ISO 3166-1 alpha-2 where known
  latitude          REAL,
  longitude         REAL,
  geo_precision     TEXT,             -- source | city | region | country | none
  -- what
  shape             TEXT,
  duration_text     TEXT,
  duration_seconds  INTEGER,
  classification    TEXT,             -- source's own class (GEIPAN A/B/C/D, "Blue Book unknown", ...)
  credibility       INTEGER,          -- Hatch 0-9 scale when available
  strangeness       INTEGER,          -- Hatch 0-9 scale when available
  summary           TEXT,             -- short one-liner
  description       TEXT,             -- full text (Markdown allowed)
  witnesses         TEXT,
  url               TEXT,             -- link to the original record when one exists
  refs              TEXT,             -- JSON array of citations
  tags              TEXT,             -- JSON array of tags (Hatch attribute codes etc.)
  extra             TEXT,             -- JSON object of source-specific leftovers
  content_hash      TEXT              -- sha1 of (source_key, source_record_id or content) for idempotent rebuilds
);
CREATE INDEX IF NOT EXISTS ix_events_source   ON events(source_key);
CREATE INDEX IF NOT EXISTS ix_events_date     ON events(date_iso);
CREATE INDEX IF NOT EXISTS ix_events_year     ON events(year);
CREATE INDEX IF NOT EXISTS ix_events_country  ON events(country_code, region);
CREATE INDEX IF NOT EXISTS ix_events_geo      ON events(latitude, longitude);
CREATE INDEX IF NOT EXISTS ix_events_shape    ON events(shape);
CREATE INDEX IF NOT EXISTS ix_events_type     ON events(event_type);
CREATE UNIQUE INDEX IF NOT EXISTS ux_events_hash ON events(content_hash);

-- Flattened tags for cheap GROUP BY / filtering.
CREATE TABLE IF NOT EXISTS event_tags (
  event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  tag      TEXT NOT NULL,
  PRIMARY KEY (event_id, tag)
);
CREATE INDEX IF NOT EXISTS ix_event_tags_tag ON event_tags(tag);

-- Pairs of records from different sources that probably describe the same incident.
CREATE TABLE IF NOT EXISTS event_links (
  event_id_a INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  event_id_b INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  score      REAL NOT NULL,           -- 0..1 heuristic confidence
  reason     TEXT,
  PRIMARY KEY (event_id_a, event_id_b)
);
CREATE INDEX IF NOT EXISTS ix_event_links_b ON event_links(event_id_b);

-- Full-text search over the narrative fields (external-content FTS5 table).
CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
  description, summary, location_text, shape, tags,
  content='events', content_rowid='id', tokenize='unicode61 remove_diacritics 2'
);

-- Convenience views -------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_sightings AS
  SELECT * FROM events
  WHERE event_type IN ('sighting', 'close_encounter', 'blue_book_unknown');

CREATE VIEW IF NOT EXISTS v_events_per_year AS
  SELECT year, source_key, COUNT(*) AS n
  FROM events WHERE year IS NOT NULL
  GROUP BY year, source_key;

CREATE VIEW IF NOT EXISTS v_country_counts AS
  SELECT COALESCE(country, '(unknown)') AS country, country_code, COUNT(*) AS n
  FROM events GROUP BY country, country_code ORDER BY n DESC;
