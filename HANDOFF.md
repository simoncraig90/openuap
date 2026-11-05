# HANDOFF

Last updated: 2026-11-05 (session 1, cloud) — milestone 2.

## State
- `main` holds the initial import (commit cfba5a8). It was pushed directly to main before the
  no-push-to-main rule was given; nothing has been pushed to main since.
- Branch `handoff-docs`: HANDOFF.md only. Branch `dev` (built on it): CI workflow, CLAUDE.md, gazetteer geocoding,
  NUFORC id fix, loader fixture tests, build-step tests. Not merged; needs your go.
- Database builds in ~20 s from `openuap fetch` + `openuap build` (145,394 events, 159 MB, git-ignored).

## What works (tested in this session)
- `openuap build` end to end on the 22 sources listed in README.md.
- CLI: `search`, `sql`, `stats`, `near`, `event`, `describe`.
- MCP server over stdio, exercised with a real `mcp` client: all six tools and the schema resource.
- Read-only guards in `openuap/query.py` block writes, multi-statements, pragmas and `load_extension`.
- `pytest tests` passes (31 tests). Red-proof evidence:
  - normalize/query (14 tests): five planted faults (month/day swap, duration unit dropped, state->US mapping removed,
    select-only check removed, FTS filters dropped) each made at least one test fail; two tests had to be tightened
    first because faults 4 and 5 initially stayed green.
  - loaders (14 cases): each fault planted in sources/nuforc.py or sources/geipan.py failed its test (Sonnet agent report).
  - build steps (3 tests): same-source guard, propagation threshold, gazetteer ambiguity each proved red.
- Gazetteer geocoding (`db.gazetteer_geocode`) adds coordinates to 7,779 chronology records (geo_precision='gazetteer');
  with linked propagation (1,942) un-geocoded events fall from 36,189 to 28,410.

## Not tested
- `openuap ask` (Claude tool-runner agent): no API key in the container. Only the tool schemas and the
  missing-credentials error path were exercised.
- `openuap fetch` as a whole: only the single-file download helper and the rr0 sparse clone commands were run.
- The NUFORC JSONL loader and GEIPAN official-CSV loader now have fixture tests, but have still not been run on a
  real export file.

## Known gaps
- NUFORC data is the 2014 planetsig mirror; NUFORC ToS forbids scraping. Needs an official export.
- GEIPAN is a 398-case fragment (cnes-geipan.fr blocked from the cloud container). Full export is ~3,000.
- Blocked hosts from the cloud container: nuforc.org, cnes-geipan.fr, data.gouv.fr, kaggle.com,
  huggingface.co, archive.org, catalog.archives.gov.
- Chronology sources (Johnson, Eberhart, Overmeire) have few coordinates; ~1,900 were filled from links.

## Open items
1. Guards in `query.py` (SQL whitelist, row cap, timeout, authorizer) predate the standing rules.
   Recommend: keep them, because they are what makes handing the DB to an LLM safe; your call.
2. `openuap ask` unverified live. Recommend: run one question with a key before relying on it.
3. Licensing: most sources are research-use only (see `sources` table). Recommend: keep the repo private
   until the NUFORC mirror is replaced by an official export.

## How to run
See README.md. MCP config and CLI examples are there.
4. Pushed the initial import straight to `main` before the no-push-to-main rule arrived. Recommend: leave it,
   because it is the empty repo's first commit and rewriting main is destructive; say if you want it moved.
5. Gazetteer medoid can be ~10-20 km off for large cities. Recommend: accept, because the sources themselves are
   city-level; mark with geo_precision='gazetteer' (done) so analyses can exclude it.
