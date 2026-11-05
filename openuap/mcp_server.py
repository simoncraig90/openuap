"""MCP server exposing openuap to Claude Desktop, Claude Code, or any MCP client.

Run:   openuap serve            (stdio transport)
or:    python -m openuap.mcp_server
Set OPENUAP_PATH to point at a database other than data/openuap.sqlite.
"""
from __future__ import annotations

import json
from typing import Optional

from mcp.server.mcpserver import MCPServer

from . import query

server = MCPServer(
    name="openuap",
    instructions=(
        "Consolidated UFO/UAP event database (SQLite). Call describe_database first to learn the schema and "
        "source licences, then use search_events for text questions, query_sql for anything analytical, "
        "events_near for geography and get_event for full records. Always cite source_key and, when present, url."
    ),
)


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


@server.tool()
def describe_database() -> str:
    """Schema, sources (with licences and record counts), event types and query conventions. Call this first."""
    return query.describe()


@server.tool()
def search_events(text: str = "", limit: int = 25, year_from: Optional[int] = None, year_to: Optional[int] = None,
                  country: Optional[str] = None, source: Optional[str] = None, event_type: Optional[str] = None,
                  shape: Optional[str] = None, classification: Optional[str] = None, has_coords: Optional[bool] = None,
                  min_credibility: Optional[int] = None, include_description: bool = False) -> str:
    """Full-text search over event narratives with optional filters.

    text: words to match (implicit AND; use OR, NOT, "quoted phrases", prefix*). Empty text = filter only.
    country: ISO-2 code (US, FR) or a name fragment. source: comma-separated source_keys.
    Returns JSON {columns, rows, row_count, truncated}.
    """
    try:
        return _j(query.search(text, limit=limit, year_from=year_from, year_to=year_to, country=country, source=source,
                               event_type=event_type, shape=shape, classification=classification, has_coords=has_coords,
                               min_credibility=min_credibility, include_description=include_description))
    except Exception as e:  # noqa: BLE001
        return _j({"error": f"{type(e).__name__}: {e}"})


@server.tool()
def query_sql(sql: str, limit: int = 200) -> str:
    """Run one read-only SELECT/WITH statement against the database (max 500 rows, 20 s).

    Tables: events, sources, event_tags, event_links, events_fts (FTS5). Views: v_sightings, v_events_per_year, v_country_counts.
    """
    try:
        return _j(query.run_sql(sql, limit=limit))
    except (ValueError, TimeoutError) as e:
        return _j({"error": str(e)})
    except Exception as e:  # sqlite errors back to the model so it can fix the SQL
        return _j({"error": f"{type(e).__name__}: {e}"})


@server.tool()
def get_event(event_id: int) -> str:
    """Full record for one event id, including refs, tags, extra fields, source licence and probable duplicates in other sources."""
    r = query.get_event(event_id)
    return _j(r if r else {"error": f"no event {event_id}"})


@server.tool()
def events_near(latitude: float, longitude: float, radius_km: float = 50, limit: int = 50,
                year_from: Optional[int] = None, year_to: Optional[int] = None, source: Optional[str] = None,
                event_type: Optional[str] = None) -> str:
    """Events with coordinates within radius_km of a point, nearest first."""
    try:
        return _j(query.nearby(latitude, longitude, radius_km, limit=limit, year_from=year_from, year_to=year_to,
                               source=source, event_type=event_type))
    except Exception as e:  # noqa: BLE001
        return _j({"error": f"{type(e).__name__}: {e}"})


@server.tool()
def event_stats(group_by: str = "year", year_from: Optional[int] = None, year_to: Optional[int] = None,
                country: Optional[str] = None, source: Optional[str] = None, event_type: Optional[str] = None,
                shape: Optional[str] = None, limit: int = 200) -> str:
    """COUNT(*) grouped by year, month, source_key, event_type, country, country_code, region, shape, classification, credibility, strangeness or city (comma-separate for multiple)."""
    try:
        return _j(query.stats(group_by, limit=limit, year_from=year_from, year_to=year_to, country=country,
                              source=source, event_type=event_type, shape=shape))
    except ValueError as e:
        return _j({"error": str(e)})


@server.resource("openuap://schema", name="openuap schema", mime_type="text/plain")
def schema_resource() -> str:
    return query.describe()


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
