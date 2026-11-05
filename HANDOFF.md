# HANDOFF

Last updated: 2026-11-05 (session 1, cloud).

## State
- `main` holds the initial import (commit cfba5a8). It was pushed directly to main before the
  no-push-to-main rule was given; nothing has been pushed to main since.
- Branch `handoff-docs`: this file.
- Database builds in ~20 s from `openuap fetch` + `openuap build` (145,394 events, 159 MB, git-ignored).

## What works (tested in this session)
- `openuap build` end to end on the 22 sources listed in README.md.
- CLI: `search`, `sql`, `stats`, `near`, `event`, `describe`.
- MCP server over stdio, exercised with a real `mcp` client: all six tools and the schema resource.
- Read-only guards in `openuap/query.py` block writes, multi-statements, pragmas and `load_extension`.
- `pytest tests` passes (14 tests). These tests were NOT proved red by planting faults.

## Not tested
- `openuap ask` (Claude tool-runner agent): no API key in the container. Only the tool schemas and the
  missing-credentials error path were exercised.
- `openuap fetch` as a whole: only the single-file download helper and the rr0 sparse clone commands were run.
- The NUFORC JSONL loader (official-export format) and the GEIPAN official-CSV loader: written against
  the documented column layouts, never run on a real file.

## Known gaps
- NUFORC data is the 2014 planetsig mirror; NUFORC ToS forbids scraping. Needs an official export.
- GEIPAN is a 398-case fragment (cnes-geipan.fr blocked from the cloud container). Full export is ~3,000.
- Blocked hosts from the cloud container: nuforc.org, cnes-geipan.fr, data.gouv.fr, kaggle.com,
  huggingface.co, archive.org, catalog.archives.gov.
- Chronology sources (Johnson, Eberhart, Overmeire) have few coordinates; ~1,900 were filled from links.

## Open items
1. Guards in `query.py` (SQL whitelist, row cap, timeout, authorizer) predate the standing rules.
   Recommend: keep them, because they are what makes handing the DB to an LLM safe; your call.
2. Tests not proved red. Recommend: plant one fault per test file and confirm failure in the next pass.
3. `openuap ask` unverified live. Recommend: run one question with a key before relying on it.
4. Licensing: most sources are research-use only (see `sources` table). Recommend: keep the repo private
   until the NUFORC mirror is replaced by an official export.

## How to run
See README.md. MCP config and CLI examples are there.
