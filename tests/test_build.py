"""Build-step tests on a tiny in-memory database (no raw data needed)."""
import sqlite3

from openuap.db import init_schema, link_duplicates, propagate_coordinates, gazetteer_geocode
from openuap.sources.base import make_record, EVENT_COLUMNS
from openuap.normalize import parse_date


def _db(records):
    con = sqlite3.connect(":memory:")
    init_schema(con)
    for key in {r["source_key"] for r in records}:
        con.execute("INSERT INTO sources(source_key, name) VALUES (?,?)", (key, key))
    cols = ", ".join(EVENT_COLUMNS); qs = ", ".join("?" * len(EVENT_COLUMNS))
    con.executemany(f"INSERT INTO events ({cols}) VALUES ({qs})", [tuple(r[c] for c in EVENT_COLUMNS) for r in records])
    con.commit()
    return con


def _rec(source, date, loc, city=None, region=None, cc=None, lat=None, lon=None, desc="x", sid=None):
    return make_record(source, source_record_id=sid or f"{source}-{loc}-{date}", date=parse_date(date), date_text=date,
                       location_text=loc, city=city, region=region, country_code=cc, latitude=lat, longitude=lon,
                       geo_precision="city" if lat is not None else None, description=desc)


def test_link_duplicates_same_day_same_place_different_sources():
    con = _db([
        _rec("hatch", "7/19/1952", "Washington, DC", city="Washington", region="DC", cc="US", lat=38.9, lon=-77.0),
        _rec("nicap", "7/19/1952", "Washington, D.C.", city="Washington", region="DC", cc="US"),
        _rec("nicap", "7/19/1952", "Paris, France", city="Paris", cc="FR"),          # same day, other place
        _rec("hatch", "7/19/1952", "Washington, DC", city="Washington", region="DC", cc="US", sid="h2"),  # hatch-hatch pair must NOT link
    ])
    n = link_duplicates(con)
    pairs = con.execute("SELECT a.source_key, b.source_key, l.score FROM event_links l JOIN events a ON a.id=l.event_id_a JOIN events b ON b.id=l.event_id_b").fetchall()
    assert n == 2 and all(set(p[:2]) == {"hatch", "nicap"} and p[2] >= 0.7 for p in pairs)


def test_propagate_coordinates_from_strong_link():
    con = _db([
        _rec("hatch", "6/29/1954", "Goose Bay, Labrador", city="Goose Bay", region="Labrador", cc="CA", lat=53.3, lon=-60.4),
        _rec("nicap", "6/29/1954", "Near Goose Bay, Labrador", city="Near Goose Bay", region="Labrador", cc="CA"),
        _rec("dolan", "6/29/1954", "Labrador", city="Labrador", cc="CA"),   # one shared token: score 0.8, below the 0.9 bar
    ])
    link_duplicates(con)
    assert propagate_coordinates(con) == 1
    rows = {r[0]: r[1:] for r in con.execute("SELECT source_key, latitude, longitude, geo_precision FROM events")}
    assert rows["nicap"] == (53.3, -60.4, "linked") and rows["dolan"][0] is None


def test_gazetteer_uses_median_of_known_cities_and_respects_ambiguity():
    con = _db([
        _rec("nuforc", "1/1/2000", "Springfield, IL", city="Springfield", region="IL", cc="US", lat=39.8, lon=-89.6, sid="a"),
        _rec("nuforc", "1/1/2001", "Springfield, IL", city="Springfield", region="IL", cc="US", lat=39.9, lon=-89.7, sid="b"),
        _rec("nuforc", "1/1/2002", "Springfield, MO", city="Springfield", region="MO", cc="US", lat=37.2, lon=-93.3, sid="c"),
        _rec("nuforc", "1/1/2003", "Lyon", city="Lyon", cc="FR", lat=45.76, lon=4.84, sid="d"),
        # targets
        _rec("johnson", "1/1/1960", "Springfield, Illinois", city="Springfield", region="IL", cc="US", sid="t1"),
        _rec("johnson", "1/1/1961", "Springfield", city="Springfield", cc="US", sid="t2"),        # ambiguous: IL or MO
        _rec("johnson", "1/1/1962", "Lyon, France", city="Lyon", cc="FR", sid="t3"),
        _rec("johnson", "1/1/1963", "Nowhere, France", city="Nowhere", cc="FR", sid="t4"),
    ])
    assert gazetteer_geocode(con) == 2
    got = {r[0]: r[1:] for r in con.execute("SELECT source_record_id, latitude, longitude, geo_precision FROM events WHERE source_key='johnson'")}
    assert got["t1"] == (39.9, -89.7, "gazetteer")      # median of the two IL points
    assert got["t2"][0] is None                          # ambiguous key left alone
    assert got["t3"] == (45.76, 4.84, "gazetteer")
    assert got["t4"][0] is None
