"""Read-only query layer shared by the CLI, the MCP server and the Claude agent.

Every entry point here opens the database read-only, refuses anything but a
single SELECT/WITH statement, and caps rows and execution time, so it is safe
to hand to an LLM.
"""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import time
from typing import Any, Optional

from .db import DEFAULT_DB

MAX_ROWS = 500
MAX_SECONDS = 20.0
MAX_CELL_CHARS = 2000

_GROUPABLE = {"year", "month", "source_key", "event_type", "country", "country_code", "region", "shape",
              "classification", "date_precision", "credibility", "strangeness", "city"}


class _ROConnection(sqlite3.Connection):
    """sqlite3.Connection that can carry a per-query deadline (the base class has no __dict__)."""
    _openuap_deadline: dict


def db_path() -> str:
    return os.environ.get("OPENUAP_PATH", DEFAULT_DB)


def open_readonly(path: Optional[str] = None) -> sqlite3.Connection:
    path = path or db_path()
    if not os.path.exists(path):
        raise FileNotFoundError(f"database not found at {path}; run `openuap build` first or set OPENUAP_PATH")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False, factory=_ROConnection)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = 1")

    def authorizer(action, arg1, arg2, dbname, trigger):
        # Allow reads, functions and transaction bookkeeping; deny every write/DDL/ATTACH.
        if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE):
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_PRAGMA and str(arg1).lower() in ("table_info", "table_xinfo", "index_list", "index_info", "foreign_key_list", "query_only", "data_version"):
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    con.set_authorizer(authorizer)
    deadline = {"t": None}

    def progress():
        if deadline["t"] and time.monotonic() > deadline["t"]:
            return 1
        return 0

    con.set_progress_handler(progress, 10000)
    con._openuap_deadline = deadline  # type: ignore[attr-defined]
    return con


def _truncate(v):
    if isinstance(v, str) and len(v) > MAX_CELL_CHARS:
        return v[:MAX_CELL_CHARS] + f"… [+{len(v) - MAX_CELL_CHARS} chars]"
    return v


def _run(con: sqlite3.Connection, sql: str, params=(), limit: int = MAX_ROWS) -> dict:
    con._openuap_deadline["t"] = time.monotonic() + MAX_SECONDS  # type: ignore[attr-defined]
    t0 = time.monotonic()
    try:
        cur = con.execute(sql, params)
        rows = cur.fetchmany(limit + 1)
    except sqlite3.OperationalError as e:
        if "interrupted" in str(e).lower():
            raise TimeoutError(f"query exceeded {MAX_SECONDS:.0f}s") from e
        raise
    finally:
        con._openuap_deadline["t"] = None  # type: ignore[attr-defined]
    cols = [d[0] for d in cur.description] if cur.description else []
    truncated = len(rows) > limit
    rows = rows[:limit]
    return {"columns": cols, "rows": [[_truncate(v) for v in r] for r in rows], "row_count": len(rows),
            "truncated": truncated, "elapsed_ms": round((time.monotonic() - t0) * 1000)}


_FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|vacuum|reindex|pragma)\b", re.I)


def run_sql(sql: str, limit: int = 200, path: Optional[str] = None) -> dict:
    """Execute one read-only SELECT. A LIMIT is appended if the statement has none."""
    s = sql.strip().rstrip(";").strip()
    if ";" in s:
        raise ValueError("one statement at a time")
    if not re.match(r"^(select|with|explain)\b", s, re.I):
        raise ValueError("only SELECT / WITH queries are allowed")
    if _FORBIDDEN.search(s):
        raise ValueError("statement contains a forbidden keyword")
    limit = max(1, min(int(limit), MAX_ROWS))
    if not re.search(r"\blimit\b\s+\d+\s*$", s, re.I) and not s.lower().startswith("explain"):
        s = f"SELECT * FROM ({s}) LIMIT {limit + 1}"
    con = open_readonly(path)
    try:
        out = _run(con, s, (), limit)
    finally:
        con.close()
    out["sql"] = s
    return out


def _fts_query(text: str) -> str:
    """Turn free text into a safe FTS5 query: quoted tokens, implicit AND, OR/NOT passthrough, trailing * allowed."""
    toks = []
    for raw in re.findall(r'"[^"]+"|\S+', text):
        if raw.upper() in ("OR", "AND", "NOT"):
            toks.append(raw.upper())
            continue
        prefix = raw.endswith("*")
        w = raw.strip('"*').replace('"', "")
        if not w:
            continue
        toks.append(f'"{w}"' + ("*" if prefix else ""))
    return " ".join(toks) or '""'


def _filters(where: list, params: list, *, year_from=None, year_to=None, country=None, source=None,
             event_type=None, shape=None, classification=None, has_coords=None, min_credibility=None):
    if year_from is not None:
        where.append("e.year >= ?"); params.append(int(year_from))
    if year_to is not None:
        where.append("e.year <= ?"); params.append(int(year_to))
    if country:
        c = country.strip()
        if len(c) == 2:
            where.append("e.country_code = ?"); params.append(c.upper())
        else:
            where.append("(e.country LIKE ? OR e.location_text LIKE ?)"); params += [f"%{c}%", f"%{c}%"]
    if source:
        keys = [k.strip() for k in source.split(",") if k.strip()]
        where.append(f"e.source_key IN ({','.join('?' * len(keys))})"); params += keys
    if event_type:
        where.append("e.event_type = ?"); params.append(event_type)
    if shape:
        where.append("e.shape LIKE ?"); params.append(f"%{shape.lower()}%")
    if classification:
        where.append("e.classification LIKE ?"); params.append(f"%{classification}%")
    if has_coords:
        where.append("e.latitude IS NOT NULL")
    if min_credibility is not None:
        where.append("e.credibility >= ?"); params.append(int(min_credibility))


_EVENT_COLS = ("e.id, e.source_key, e.source_record_id, e.event_type, e.date_iso, e.date_text, e.date_precision, e.time_text, "
               "e.location_text, e.city, e.region, e.country, e.country_code, e.latitude, e.longitude, e.shape, "
               "e.duration_text, e.classification, e.credibility, e.strangeness, e.summary, e.url")


def search(text: str = "", limit: int = 25, path: Optional[str] = None, include_description: bool = False, **filters) -> dict:
    """Full-text search with optional structured filters. Empty `text` means filter-only, newest first."""
    where, params = [], []
    _filters(where, params, **filters)
    limit = max(1, min(int(limit), MAX_ROWS))
    cols = _EVENT_COLS + (", e.description" if include_description else "")
    if text and text.strip():
        q = _fts_query(text)
        sql = (f"SELECT {cols}, bm25(events_fts, 5.0, 3.0, 2.0, 1.0, 1.0) AS rank, "
               f"snippet(events_fts, 0, '[', ']', '…', 24) AS snippet "
               f"FROM events_fts JOIN events e ON e.id = events_fts.rowid WHERE events_fts MATCH ? "
               + (" AND " + " AND ".join(where) if where else "") + f" ORDER BY rank LIMIT {limit + 1}")
        params = [q] + params
    else:
        sql = (f"SELECT {cols} FROM events e " + ("WHERE " + " AND ".join(where) if where else "")
               + f" ORDER BY e.date_iso DESC LIMIT {limit + 1}")
    con = open_readonly(path)
    try:
        out = _run(con, sql, params, limit)
    finally:
        con.close()
    out["query"] = {"text": text, **{k: v for k, v in filters.items() if v is not None}}
    return out


def get_event(event_id: int, path: Optional[str] = None) -> Optional[dict]:
    con = open_readonly(path)
    try:
        r = con.execute("SELECT * FROM events WHERE id = ?", (int(event_id),)).fetchone()
        if not r:
            return None
        d = dict(r)
        for k in ("refs", "tags", "extra"):
            try:
                d[k] = json.loads(d[k]) if d[k] else None
            except (TypeError, ValueError):
                pass
        links = con.execute(
            "SELECT CASE WHEN l.event_id_a = ? THEN l.event_id_b ELSE l.event_id_a END AS other_id, l.score, l.reason, "
            "e.source_key, e.summary FROM event_links l JOIN events e ON e.id = (CASE WHEN l.event_id_a = ? THEN l.event_id_b ELSE l.event_id_a END) "
            "WHERE l.event_id_a = ? OR l.event_id_b = ? ORDER BY l.score DESC LIMIT 20",
            (event_id, event_id, event_id, event_id)).fetchall()
        d["probable_duplicates"] = [dict(x) for x in links]
        src = con.execute("SELECT name, publisher, license, url FROM sources WHERE source_key = ?", (d["source_key"],)).fetchone()
        d["source"] = dict(src) if src else None
        return d
    finally:
        con.close()


def nearby(lat: float, lon: float, radius_km: float = 50, limit: int = 50, path: Optional[str] = None, **filters) -> dict:
    """Events with coordinates within radius_km of a point (bounding box in SQL, haversine in Python)."""
    lat, lon, radius_km = float(lat), float(lon), min(float(radius_km), 2000.0)
    dlat = radius_km / 111.0
    dlon = radius_km / max(1e-6, 111.0 * math.cos(math.radians(lat)))
    where = ["e.latitude BETWEEN ? AND ?", "e.longitude BETWEEN ? AND ?"]
    params = [lat - dlat, lat + dlat, lon - dlon, lon + dlon]
    _filters(where, params, **filters)
    sql = f"SELECT {_EVENT_COLS} FROM events e WHERE " + " AND ".join(where) + " LIMIT 5000"
    con = open_readonly(path)
    try:
        out = _run(con, sql, params, 5000)
    finally:
        con.close()
    ci = {c: i for i, c in enumerate(out["columns"])}
    rows = []
    for r in out["rows"]:
        d = 6371 * 2 * math.asin(math.sqrt(
            math.sin(math.radians(r[ci["latitude"]] - lat) / 2) ** 2
            + math.cos(math.radians(lat)) * math.cos(math.radians(r[ci["latitude"]]))
            * math.sin(math.radians(r[ci["longitude"]] - lon) / 2) ** 2))
        if d <= radius_km:
            rows.append(r + [round(d, 1)])
    rows.sort(key=lambda r: r[-1])
    limit = max(1, min(int(limit), MAX_ROWS))
    return {"columns": out["columns"] + ["distance_km"], "rows": rows[:limit], "row_count": min(len(rows), limit),
            "truncated": len(rows) > limit, "center": [lat, lon], "radius_km": radius_km}


def stats(group_by: str = "year", path: Optional[str] = None, limit: int = 200, **filters) -> dict:
    """COUNT(*) grouped by one of the whitelisted columns."""
    cols = [c.strip() for c in group_by.split(",")]
    for c in cols:
        if c not in _GROUPABLE:
            raise ValueError(f"group_by must be one of {sorted(_GROUPABLE)}")
    where, params = [], []
    _filters(where, params, **filters)
    g = ", ".join(f"e.{c}" for c in cols)
    sql = (f"SELECT {g}, COUNT(*) AS n FROM events e " + ("WHERE " + " AND ".join(where) if where else "")
           + f" GROUP BY {g} ORDER BY " + ("n DESC" if cols != ["year"] and cols != ["month"] else g)
           + f" LIMIT {min(int(limit), MAX_ROWS) + 1}")
    con = open_readonly(path)
    try:
        return _run(con, sql, params, min(int(limit), MAX_ROWS))
    finally:
        con.close()


def describe(path: Optional[str] = None) -> str:
    """Human/LLM-readable description of the schema, sources and query conventions."""
    con = open_readonly(path)
    try:
        meta = {k: v for k, v in con.execute("SELECT key, value FROM meta")}
        srcs = con.execute("SELECT source_key, name, record_count, coverage, access_type FROM sources ORDER BY record_count DESC").fetchall()
        ddl = [r[0] for r in con.execute("SELECT sql FROM sqlite_master WHERE type IN ('table','view') AND sql IS NOT NULL AND name NOT LIKE 'events_fts%' AND name NOT LIKE 'sqlite_%'")]
        yr = con.execute("SELECT MIN(year), MAX(year), COUNT(*) FROM events WHERE year IS NOT NULL").fetchone()
        types = con.execute("SELECT event_type, COUNT(*) FROM events GROUP BY 1 ORDER BY 2 DESC").fetchall()
    finally:
        con.close()
    lines = [f"openuap v{meta.get('openuap_version')} built {meta.get('built_at')}: {int(meta.get('event_count', 0)):,} events, "
             f"years {yr[0]}–{yr[1]} ({yr[2]:,} dated).", "",
             "EVENT TYPES: " + ", ".join(f"{t}={n:,}" for t, n in types), "",
             "SOURCES (source_key: name — records — coverage — access):"]
    for s in srcs:
        lines.append(f"  {s[0]}: {s[1]} — {s[2]:,} — {s[3]} — {s[4]}")
    lines += ["", "SCHEMA:"] + ddl + ["",
        "CONVENTIONS:",
        "- date_iso is zero-padded and sortable (YYYY, YYYY-MM or YYYY-MM-DD); check date_precision before day-level math.",
        "- Hatch records use literal years, so year 70 really is AD 70.",
        "- Full-text: SELECT ... FROM events_fts JOIN events e ON e.id = events_fts.rowid WHERE events_fts MATCH 'triangle AND silent'.",
        "- tags is a JSON array; use json_each(e.tags) or the event_tags table. Hatch tag codes: MIL military observers, RDR radar, "
        "PHT photo, TRC physical traces, EME electromagnetic effects, CE3/CE4 close encounters, NLT night lights, SCR saucer, CIG cigar, DLT delta.",
        "- event_links pairs records from different sources that probably describe the same incident (score 0.5–1.0).",
        "- nuclear_tests rows are context, not UFO reports: exclude event_type='nuclear_test' unless correlating.",
        "- NUFORC mirror descriptions are truncated to ~130 chars; GEIPAN mirror rows mostly lack narrative text.",
    ]
    return "\n".join(lines)


def to_markdown(result: dict, max_rows: int = 50) -> str:
    cols = result.get("columns") or []
    rows = result.get("rows") or []
    if not cols:
        return "(no columns)"
    def cell(v):
        s = "" if v is None else str(v)
        s = s.replace("\n", " ").replace("|", "\\|")
        return s if len(s) <= 120 else s[:117] + "…"
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows[:max_rows]:
        out.append("| " + " | ".join(cell(v) for v in r) + " |")
    if len(rows) > max_rows:
        out.append(f"… {len(rows) - max_rows} more rows")
    if result.get("truncated"):
        out.append("(result truncated at limit)")
    return "\n".join(out)
