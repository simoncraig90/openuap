"""Command-line entry point: python -m openuap <command>  (or `openuap` once installed)."""
from __future__ import annotations

import argparse
import json
import sys

from . import query
from .db import DEFAULT_DB, DEFAULT_RAW


def _print(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    else:
        print(query.to_markdown(result))
        if result.get("elapsed_ms") is not None:
            print(f"\n{result['row_count']} rows in {result['elapsed_ms']} ms")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="openuap", description="Consolidated UFO/UAP database")
    p.add_argument("--db", default=None, help=f"database path (default $OPENUAP_PATH or {DEFAULT_DB})")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("fetch", help="download raw source files into data/raw")
    s.add_argument("--raw", default=DEFAULT_RAW)

    s = sub.add_parser("build", help="(re)build the SQLite database from data/raw")
    s.add_argument("--raw", default=DEFAULT_RAW)
    s.add_argument("--only", help="comma-separated source_keys to load")

    s = sub.add_parser("describe", help="print schema, sources and conventions")

    s = sub.add_parser("search", help="full-text search")
    s.add_argument("text", nargs="?", default="")
    for f in ("year-from", "year-to"):
        s.add_argument(f"--{f}", type=int)
    for f in ("country", "source", "event-type", "shape", "classification"):
        s.add_argument(f"--{f}")
    s.add_argument("--limit", type=int, default=25)
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("sql", help="run a read-only SELECT")
    s.add_argument("sql")
    s.add_argument("--limit", type=int, default=200)
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("event", help="show one event by id")
    s.add_argument("id", type=int)

    s = sub.add_parser("near", help="events near a point")
    s.add_argument("lat", type=float)
    s.add_argument("lon", type=float)
    s.add_argument("--km", type=float, default=50)
    s.add_argument("--limit", type=int, default=50)
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("stats", help="counts grouped by a column")
    s.add_argument("group_by", nargs="?", default="year")
    for f in ("year-from", "year-to"):
        s.add_argument(f"--{f}", type=int)
    for f in ("country", "source", "event-type", "shape"):
        s.add_argument(f"--{f}")
    s.add_argument("--limit", type=int, default=200)
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("serve", help="run the MCP server on stdio")

    s = sub.add_parser("ask", help="ask a natural-language question (needs ANTHROPIC_API_KEY)")
    s.add_argument("question")
    s.add_argument("--model", default=None)
    s.add_argument("-v", "--verbose", action="store_true")

    a = p.parse_args(argv)
    if a.db:
        import os
        os.environ["OPENUAP_PATH"] = a.db

    if a.cmd == "fetch":
        from .fetch import fetch_all
        fetch_all(a.raw)
    elif a.cmd == "build":
        from .db import build
        build(query.db_path(), a.raw, only=a.only.split(",") if a.only else None)
    elif a.cmd == "describe":
        print(query.describe())
    elif a.cmd == "search":
        _print(query.search(a.text, limit=a.limit, year_from=a.year_from, year_to=a.year_to, country=a.country,
                            source=a.source, event_type=a.event_type, shape=a.shape, classification=a.classification), a.json)
    elif a.cmd == "sql":
        try:
            _print(query.run_sql(a.sql, limit=a.limit), a.json)
        except (ValueError, TimeoutError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
    elif a.cmd == "event":
        r = query.get_event(a.id)
        print(json.dumps(r, ensure_ascii=False, indent=1, default=str) if r else f"no event {a.id}")
    elif a.cmd == "near":
        _print(query.nearby(a.lat, a.lon, a.km, limit=a.limit), a.json)
    elif a.cmd == "stats":
        _print(query.stats(a.group_by, limit=a.limit, year_from=a.year_from, year_to=a.year_to, country=a.country,
                           source=a.source, event_type=a.event_type, shape=a.shape), a.json)
    elif a.cmd == "serve":
        from .mcp_server import main as serve
        serve()
    elif a.cmd == "ask":
        from .ask import ask, MODEL
        import anthropic
        try:
            print(ask(a.question, model=a.model or MODEL, verbose=a.verbose))
        except (anthropic.AuthenticationError, TypeError) as e:
            if isinstance(e, TypeError) and "authentication" not in str(e).lower():
                raise
            print("error: no valid Anthropic credentials. Set ANTHROPIC_API_KEY or run `ant auth login`.", file=sys.stderr)
            return 2
        except anthropic.APIConnectionError as e:
            print(f"error: could not reach the Anthropic API ({e})", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
