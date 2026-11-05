"""Natural-language questions against openuap, answered by Claude with tool use.

    openuap ask "Which US states had the most triangle sightings in the 1990s?"

Needs ANTHROPIC_API_KEY (or an `ant auth login` profile). The model only gets
read-only tools, so it cannot modify the database.
"""
from __future__ import annotations

import json
import sys
from typing import Optional

import anthropic
from anthropic import beta_tool

from . import query

MODEL = "claude-opus-5-5"

SYSTEM = """You are an analyst with read-only access to openuap, a consolidated SQLite database of UFO/UAP reports
compiled from many public catalogues. Answer the user's question using the tools. Rules:
- Start from the schema notes below; prefer query_sql for counts, trends and joins, search_events for narrative lookups.
- Check date_precision before day-level reasoning and exclude event_type='nuclear_test' unless the user asks about it.
- Report numbers exactly as returned, name the source_key(s) the answer rests on, and say when coverage is partial
  (the NUFORC mirror ends in 2014 and GEIPAN rows are a fragment).
- Keep the final answer concise; include a small table when it helps. Do not invent records.

SCHEMA NOTES
{schema}
"""


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


@beta_tool
def query_sql(sql: str, limit: int = 200) -> str:
    """Run one read-only SELECT/WITH statement against openuap (max 500 rows). Returns JSON with columns and rows, or an error to fix.

    Args:
        sql: A single SELECT or WITH statement. Tables: events, sources, event_tags, event_links, events_fts (FTS5).
        limit: Maximum rows to return.
    """
    try:
        return _j(query.run_sql(sql, limit=limit))
    except Exception as e:  # noqa: BLE001 - surface SQL mistakes to the model
        return _j({"error": f"{type(e).__name__}: {e}"})


@beta_tool
def search_events(text: str = "", limit: int = 25, year_from: Optional[int] = None, year_to: Optional[int] = None,
                  country: Optional[str] = None, source: Optional[str] = None, shape: Optional[str] = None,
                  include_description: bool = False) -> str:
    """Full-text search over event narratives with optional filters.

    Args:
        text: Words to match (implicit AND; OR/NOT and "phrases" allowed). Empty means filter-only, newest first.
        limit: Maximum rows.
        year_from: Earliest year.
        year_to: Latest year.
        country: ISO-2 code such as US or FR, or a country-name fragment.
        source: Comma-separated source_keys to restrict to.
        shape: Shape fragment (triangle, disc, light...).
        include_description: Return the full description column too.
    """
    try:
        return _j(query.search(text, limit=limit, year_from=year_from, year_to=year_to, country=country, source=source,
                               shape=shape, include_description=include_description))
    except Exception as e:  # noqa: BLE001
        return _j({"error": f"{type(e).__name__}: {e}"})


@beta_tool
def get_event(event_id: int) -> str:
    """Full record for one event id, with refs, tags, source licence and probable duplicates.

    Args:
        event_id: The events.id value.
    """
    r = query.get_event(event_id)
    return _j(r if r else {"error": f"no event {event_id}"})


@beta_tool
def events_near(latitude: float, longitude: float, radius_km: float = 50, limit: int = 50) -> str:
    """Events with coordinates within radius_km of a point, nearest first.

    Args:
        latitude: Decimal degrees.
        longitude: Decimal degrees.
        radius_km: Search radius in kilometres (max 2000).
        limit: Maximum rows.
    """
    return _j(query.nearby(latitude, longitude, radius_km, limit=limit))


TOOLS = [query_sql, search_events, get_event, events_near]


def ask(question: str, model: str = MODEL, verbose: bool = False, max_iterations: int = 12) -> str:
    client = anthropic.Anthropic()
    system = SYSTEM.format(schema=query.describe())
    runner = client.beta.messages.tool_runner(
        model=model,
        max_tokens=16000,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        tools=TOOLS,
        messages=[{"role": "user", "content": question}],
        max_iterations=max_iterations,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",  # re-run on a fallback model if a safety classifier declines
    )
    final = None
    for message in runner:
        final = message
        if verbose:
            for block in message.content:
                if block.type == "tool_use":
                    print(f"[tool] {block.name} {json.dumps(block.input)[:300]}", file=sys.stderr)
    if final is None:
        return "(no response)"
    if final.stop_reason == "refusal":
        return "The model declined to answer this question."
    return "\n".join(b.text for b in final.content if b.type == "text").strip()
