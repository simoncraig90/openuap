"""Build the SQLite database from the loaders."""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import sqlite3
import sys
import time
from collections import defaultdict

from . import __version__
from .sources import LOADERS
from .sources.base import EVENT_COLUMNS

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")
DEFAULT_DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "openuap.sqlite")
DEFAULT_RAW = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw")


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_schema(con: sqlite3.Connection) -> None:
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        con.executescript(f.read())


def _insert_sql() -> str:
    cols = ", ".join(EVENT_COLUMNS)
    qs = ", ".join("?" for _ in EVENT_COLUMNS)
    return f"INSERT OR IGNORE INTO events ({cols}) VALUES ({qs})"


def build(db_path: str = DEFAULT_DB, raw_dir: str = DEFAULT_RAW, only: list[str] | None = None,
          log=print) -> dict:
    """(Re)build the database from data/raw. Returns per-source counts."""
    t0 = time.time()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    tmp = db_path + ".building"
    for p in (tmp, tmp + "-wal", tmp + "-shm"):
        if os.path.exists(p):
            os.remove(p)
    con = connect(tmp)
    init_schema(con)
    con.execute("PRAGMA synchronous = OFF")
    counts: dict[str, int] = defaultdict(int)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    sql = _insert_sql()

    for mod in LOADERS:
        for key, meta in mod.SOURCES.items():
            if only and key not in only:
                continue
            con.execute(
                "INSERT OR REPLACE INTO sources (source_key, name, publisher, url, license, access_type, coverage, fetched_from, fetched_at, notes) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (key, meta["name"], meta.get("publisher"), meta.get("url"), meta.get("license"), meta.get("access_type"),
                 meta.get("coverage"), meta.get("fetched_from"), now, meta.get("notes")),
            )
        batch = []
        n_mod = 0
        for rec in mod.load(raw_dir):
            if only and rec["source_key"] not in only:
                continue
            batch.append(tuple(rec[c] for c in EVENT_COLUMNS))
            counts[rec["source_key"]] += 1
            n_mod += 1
            if len(batch) >= 5000:
                con.executemany(sql, batch)
                batch.clear()
        if batch:
            con.executemany(sql, batch)
        con.commit()
        log(f"  {mod.__name__.rsplit('.', 1)[-1]:<10} {n_mod:>7,} records")

    # Flatten tags.
    con.execute("DELETE FROM event_tags")
    con.execute(
        "INSERT OR IGNORE INTO event_tags(event_id, tag) "
        "SELECT e.id, j.value FROM events e, json_each(e.tags) j WHERE e.tags IS NOT NULL AND e.tags != '[]'"
    )
    # Real counts (after INSERT OR IGNORE dedupe).
    for (k, n) in con.execute("SELECT source_key, COUNT(*) FROM events GROUP BY source_key"):
        con.execute("UPDATE sources SET record_count=? WHERE source_key=?", (n, k))
    con.execute("DELETE FROM sources WHERE record_count = 0 AND source_key NOT IN ('nuforc','geipan')")
    con.commit()

    log("  linking probable duplicates across sources…")
    n_links = link_duplicates(con)
    log(f"  {n_links:,} candidate links")

    n_geo = propagate_coordinates(con)
    log(f"  {n_geo:,} events geocoded from linked records")

    log("  building full-text index…")
    con.execute("INSERT INTO events_fts(events_fts) VALUES('rebuild')")
    total = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    for k, v in {"built_at": now, "openuap_version": __version__, "event_count": str(total),
                 "sqlite_version": sqlite3.sqlite_version}.items():
        con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?,?)", (k, v))
    con.commit()
    con.execute("PRAGMA journal_mode = DELETE")
    con.execute("VACUUM")
    con.execute("ANALYZE")
    con.close()
    for p in (db_path, db_path + "-wal", db_path + "-shm"):
        if os.path.exists(p):
            os.remove(p)
    os.replace(tmp, db_path)
    log(f"  {total:,} events in {db_path} ({os.path.getsize(db_path)/1e6:.1f} MB, {time.time()-t0:.1f}s)")
    return dict(counts)


# ----------------------------------------------------------------- duplicate linking

_STOP = {"afb", "air", "force", "base", "near", "north", "south", "east", "west", "city", "county", "the", "of", "de", "la", "le", "les", "saint", "st", "mt", "mount", "lake", "fort", "ft"}


def _loc_tokens(*texts) -> set[str]:
    toks = set()
    for t in texts:
        if not t:
            continue
        for w in re.findall(r"[a-zà-ÿ]{3,}", str(t).lower()):
            if w not in _STOP:
                toks.add(w)
    return toks


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    return 12742 * math.asin(math.sqrt(a))


def link_duplicates(con: sqlite3.Connection, max_group: int = 400) -> int:
    """Link records from *different* sources that share an exact day and a place token or are within 40 km."""
    con.execute("DELETE FROM event_links")
    rows = con.execute(
        "SELECT id, source_key, date_iso, city, location_text, latitude, longitude, country_code FROM events "
        "WHERE date_precision = 'day' AND event_type NOT IN ('nuclear_test','aerospace','document','historical','meta') "
        "ORDER BY date_iso"
    ).fetchall()
    groups: dict[str, list] = defaultdict(list)
    for r in rows:
        groups[r[2]].append(r)
    links = []
    for day, items in groups.items():
        if len(items) < 2 or len(items) > max_group:
            continue
        toks = [_loc_tokens(it[3], it[4]) for it in items]
        for i in range(len(items)):
            a = items[i]
            for j in range(i + 1, len(items)):
                b = items[j]
                if a[1] == b[1]:
                    continue  # same source: not a cross-source duplicate
                if a[7] and b[7] and a[7] != b[7]:
                    continue
                shared = toks[i] & toks[j]
                score, reason = 0.0, None
                if shared:
                    score, reason = 0.7 + min(0.3, 0.1 * len(shared)), f"same day; place tokens {sorted(shared)[:3]}"
                elif a[5] is not None and b[5] is not None:
                    d = _haversine_km(a[5], a[6], b[5], b[6])
                    if d <= 40:
                        score, reason = max(0.5, 0.9 - d / 100), f"same day; {d:.0f} km apart"
                if score:
                    links.append((a[0], b[0], round(score, 2), reason))
    con.executemany("INSERT OR IGNORE INTO event_links(event_id_a, event_id_b, score, reason) VALUES (?,?,?,?)", links)
    con.commit()
    return len(links)


def propagate_coordinates(con: sqlite3.Connection, min_score: float = 0.9) -> int:
    """Copy lat/lon onto un-geocoded events from a strongly linked record (same day, same place tokens)."""
    rows = con.execute(
        "SELECT t.id, s.latitude, s.longitude FROM event_links l "
        "JOIN events t ON t.id = l.event_id_a JOIN events s ON s.id = l.event_id_b "
        "WHERE l.score >= ? AND t.latitude IS NULL AND s.latitude IS NOT NULL "
        "UNION SELECT t.id, s.latitude, s.longitude FROM event_links l "
        "JOIN events t ON t.id = l.event_id_b JOIN events s ON s.id = l.event_id_a "
        "WHERE l.score >= ? AND t.latitude IS NULL AND s.latitude IS NOT NULL", (min_score, min_score)).fetchall()
    seen = {}
    for tid, lat, lon in rows:
        seen.setdefault(tid, (lat, lon))
    con.executemany("UPDATE events SET latitude=?, longitude=?, geo_precision='linked' WHERE id=? AND latitude IS NULL",
                    [(lat, lon, tid) for tid, (lat, lon) in seen.items()])
    con.commit()
    return len(seen)


if __name__ == "__main__":
    build(*(sys.argv[1:3]))
