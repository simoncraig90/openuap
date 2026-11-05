# openuap — a consolidated, AI-queryable UFO/UAP event database

One SQLite file (`data/openuap.sqlite`, ~160 MB) that merges 22 public UFO/UAP
catalogues into a single `events` table with normalised dates, places and
coordinates, full-text search, cross-source duplicate links, and provenance and
licence notes for every record. It ships with:

* an **MCP server** so Claude Desktop, Claude Code or any MCP client can query it with tools;
* a **`openuap ask`** command that lets Claude answer natural-language questions with read-only tool use;
* a **CLI** (`search`, `sql`, `stats`, `near`, `event`) for humans and scripts.

Everything the AI touches is read-only: single SELECT statements, 500-row cap, 20-second timeout,
SQLite authorizer blocking writes, pragmas and extensions.

## Current contents (build of 2026-11-05, milestone 3)

| source_key | What it is | Records | Access / licence |
|---|---|---:|---|
| `nuforc` | NUFORC public sighting reports: full text, ids and coordinates 1950-2026 via the uap-monitor mirror, pre-1950 via the planetsig snapshot | 156,452 | ToS forbids scraping/redistribution; mirrors are for research, request an official export for production |
| `hatch` | Larry Hatch *U* database, 18k curated worldwide cases, geocoded, credibility/strangeness scores | 18,116 | Family permission for research use (via NUFOHRC) |
| `johnson` | Dr Donald Johnson "On This Day" chronology | 8,689 | Author unreachable; research use |
| `eberhart` | Eberhart, *UFOs and Intelligence: A Timeline* (CUFOS) | 7,901 | Author permission (2025), non-commercial |
| `nicap` | NICAP quality-screened case database | 5,489 | Likely public domain |
| `overmeire` | Van Overmeire chronology | 3,693 | Not copyrighted |
| `rr0_chronology` | RR0 French chronology (Jérôme Beau) | 3,376 | GFDL |
| `nuclear_tests` | All known nuclear explosions 1945-1998 (**context, not UFO reports**) | 2,041 | Academic |
| `urecat` | Patrick Gross close-encounter catalogue | 1,385 | GFDL mirror |
| `geldreich_majestic` | R. Geldreich original research timeline | 1,088 | Attribution |
| `magonia` | Vallée, *Passport to Magonia* landing catalogue | 923 | Research use |
| `anon_pdf_2023` | Anonymous 2023 UAP timeline | 617 | Public domain |
| `bluebook_unknowns` | USAF Project Blue Book official "unknowns" (Berliner) | 584 | Public domain |
| `hall_ufo_evidence` | R. Hall, *The UFO Evidence* vol. 2 | 493 | Research use |
| `wonders_in_the_sky` | Vallée & Aubeck pre-1880 catalogue | 478 | Research use |
| `geipan` | GEIPAN (CNES) full catalogue, classification A-D, communes geocoded | 2,770 | French public data; geocoded build from Gods-Eye-UAPs (MIT, GeoNames CC BY) |
| `dow_pursue` | US Department of War PURSUE Release 01 declassified-file index with summaries | 137 | Public domain |
| `rife_pre_roswell`, `scully`, `dolan`, `adams_choppers`, `fawcett_hostile`, `trace_cases` | smaller book-derived chronologies | 1,260 | see `sources` table |

Total **215,492 events**, years 34–2026. About 19,000 cross-source duplicate pairs are recorded in
`event_links`; linked matches and a city gazetteer built from geocoded records add coordinates to ~10,000 chronology rows.

Every row keeps `source_key`, `source_record_id`, `refs` and `url`, and the `sources` table carries the
licence text, so an AI answer can always say where a claim came from. **Read the licence column
before any commercial use**: most catalogues allow research use only.

## Quick start

```bash
pip install -e .            # installs the `openuap` command (needs Python 3.10+, mcp>=2, anthropic)
openuap fetch                 # downloads the open sources (GitHub) into data/raw/   (~75 MB)
openuap build                 # ~20 s -> data/openuap.sqlite
openuap describe              # schema, sources, conventions
openuap search "triangle silent" --year-from 1985 --year-to 1995
openuap sql "SELECT year, COUNT(*) n FROM events WHERE shape='triangle' GROUP BY year ORDER BY n DESC LIMIT 10"
openuap stats shape --country US --year-from 1990 --year-to 1999
openuap near 33.39 -104.52 --km 60          # Roswell
openuap event 50601                         # full record with refs, tags and probable duplicates
```

`openuap fetch` cannot reach nuforc.org or cnes-geipan.fr from every network and NUFORC forbids
scraping, so those two loaders also accept files you obtain yourself:

* NUFORC: an official export as line-delimited JSON in `data/raw/nuforc/*.jsonl`
  (fields `text, stats, date_time, report_link, city, state, shape, duration, summary, posted`);
  it supersedes the 2014 mirror automatically.
* GEIPAN: the full catalogue is fetched automatically (Gods-Eye-UAPs build). The CNES bulk CSV
  (`cnes-geipan.fr/sites/default/files/Base_de_donn%C3%A9es_des_cas.csv`) is also accepted in `data/raw/geipan/`.

Then run `openuap build` again.

## Using it from Claude (MCP)

Claude Desktop (`claude_desktop_config.json`) or any MCP client:

```json
{
  "mcpServers": {
    "openuap": {
      "command": "openuap",
      "args": ["serve"],
      "env": { "OPENUAP_PATH": "/absolute/path/to/openuap/data/openuap.sqlite" }
    }
  }
}
```

Claude Code:

```bash
claude mcp add openuap -e OPENUAP_PATH=/absolute/path/to/openuap/data/openuap.sqlite -- openuap serve
```

Tools exposed: `describe_database`, `search_events`, `query_sql`, `get_event`, `events_near`, `event_stats`,
plus the `openuap://schema` resource. The server instructions tell the model to call `describe_database`
first and to cite `source_key`/`url`.

## Asking questions in plain language

```bash
export ANTHROPIC_API_KEY=...
openuap ask "Which US states had the most triangle sightings in the 1990s, and how does Hatch compare with NUFORC?"
openuap ask -v "Were there Blue Book unknowns within 100 km of a nuclear test site in the same year?"
```

`openuap ask` runs Claude Opus 5.5 with the same read-only tools through the SDK tool runner, with the
server-side refusal fallback enabled. Use `--model` to pick another model.

## Schema in one minute

* `events` — one row per record. Key columns: `date_iso` (sortable `YYYY`, `YYYY-MM` or `YYYY-MM-DD`),
  `date_precision`, `year`, `time_text`, `location_text`, `city`, `region`, `country`, `country_code`,
  `latitude`/`longitude` + `geo_precision` (`source`, `city`, `linked`, `gazetteer`, `none`), `shape`, `duration_seconds`, `classification`,
  `credibility`/`strangeness` (Hatch), `summary`, `description`, `refs` (JSON), `tags` (JSON), `extra` (JSON).
* `event_type` — `sighting`, `close_encounter`, `crash_retrieval`, `mutilation`, `document`, `historical`,
  `aerospace`, `ufology`, `nuclear_test`. The view `v_sightings` filters to the first two.
* `sources` — name, publisher, url, licence, access_type, coverage, record_count.
* `event_tags` — flattened tags (Hatch attribute codes: `MIL`, `RDR` radar, `PHT` photo, `TRC` traces, `EME` EM effects, …).
* `event_links` — probable same-incident pairs across sources (`score` 0.5–1.0, `reason`).
* `events_fts` — FTS5 index over description, summary, location, shape, tags:
  `SELECT e.* FROM events_fts JOIN events e ON e.id = events_fts.rowid WHERE events_fts MATCH 'radar AND pilot'`.

Caveats an analyst should know: NUFORC rows before 1950 come from a snapshot with ~130-character descriptions;
GEIPAN narratives are in French; chronology sources (Johnson, Eberhart, Overmeire)
rarely have coordinates except where linked to a geocoded record; Hatch dates are literal, so year 70 is AD 70.

## Layout

```
openuap/
  normalize.py      dates, coordinates, durations, countries, place parsing
  schema.sql        tables, indexes, FTS, views
  sources/          one loader per catalogue family (geldreich, nuforc, geipan, urecat, uap_monitor)
  fetch.py          downloads raw files (GitHub only)
  db.py             build pipeline, duplicate linking, coordinate propagation
  query.py          read-only query API shared by CLI, MCP and ask
  mcp_server.py     MCP server (stdio)
  ask.py            Claude tool-runner agent
  cli.py            command line
tests/              pytest suite (normaliser + query guards)
data/raw/           downloaded sources (git-ignored)
data/openuap.sqlite   the built database (git-ignored)
```

## Adding a source

Create `openuap/sources/<name>.py` exposing `SOURCES = {source_key: {...metadata}}` and
`load(raw_dir)` yielding `make_record(...)` dicts (see `sources/base.py`), then append the module to
`LOADERS` in `sources/__init__.py`. Candidates not yet included: MUFON CMS (members only),
Enigma Labs (proprietary), UK MoD files and AARO releases (PDF scans, need extraction), PURSUE full-text (only the index is in),
Canadian CADORS, Blue Book full microfilm index (Fold3), FOTOCAT.
