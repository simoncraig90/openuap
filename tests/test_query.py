"""Query-layer tests; skipped when the database has not been built."""
import os
import pytest

from openuap import query

pytestmark = pytest.mark.skipif(not os.path.exists(query.db_path()), reason="database not built")


def test_run_sql_select_only():
    for bad in ("DELETE FROM events", "SELECT 1; SELECT 2", "PRAGMA writable_schema=1", "ATTACH 'x' AS y", "ANALYZE", "BEGIN"):
        with pytest.raises(ValueError):
            query.run_sql(bad)


def test_run_sql_limit_and_shape():
    r = query.run_sql("SELECT id, source_key FROM events", limit=5)
    assert r["columns"] == ["id", "source_key"] and r["row_count"] == 5 and r["truncated"] is True


def test_load_extension_blocked():
    import sqlite3
    with pytest.raises(sqlite3.OperationalError):
        query.run_sql("SELECT load_extension('x')")


def test_search_fts_and_filters():
    r = query.search("triangle", year_from=1990, year_to=1999, country="US", limit=10)
    assert r["row_count"] > 0 and "snippet" in r["columns"]
    ci = {c: i for i, c in enumerate(r["columns"])}
    assert all(1990 <= int(row[ci["date_iso"]][:4]) <= 1999 and row[ci["country_code"]] == "US" for row in r["rows"])
    r2 = query.search("", source="geipan", limit=5)
    assert r2["row_count"] == 5


def test_nearby_and_stats_and_event():
    r = query.nearby(33.39, -104.52, 60, limit=5)
    assert r["row_count"] > 0 and r["columns"][-1] == "distance_km"
    s = query.stats("shape", country="US", year_from=1990, year_to=1999, limit=5)
    assert s["columns"] == ["shape", "n"]
    with pytest.raises(ValueError):
        query.stats("description")
    first = query.run_sql("SELECT id FROM events WHERE source_key='bluebook_unknowns' LIMIT 1")["rows"][0][0]
    e = query.get_event(first)
    assert e["classification"] == "Blue Book unknown" and "probable_duplicates" in e and e["source"]["name"]
