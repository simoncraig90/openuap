"""Fixture-based tests for the NUFORC JSONL loader and the GEIPAN official-CSV loader."""
import shutil
from pathlib import Path

import pytest

from openuap.sources import geipan, nuforc

FIXTURES = Path(__file__).parent / "fixtures"


def _nuforc_records(tmp_path):
    (tmp_path / "nuforc").mkdir()
    shutil.copy(FIXTURES / "nuforc_sample.jsonl", tmp_path / "nuforc" / "nuforc_sample.jsonl")
    return list(nuforc.load(str(tmp_path)))


def test_nuforc_jsonl_record_count(tmp_path):
    assert len(_nuforc_records(tmp_path)) == 3


def test_nuforc_jsonl_two_digit_year(tmp_path):
    recs = _nuforc_records(tmp_path)
    assert [r["date_iso"] for r in recs] == ["1965-07-04", "2012-03-15", "1999-10-31"]
    assert recs[0]["time_text"] == "22:30"


def test_nuforc_jsonl_country_from_state(tmp_path):
    recs = _nuforc_records(tmp_path)
    assert {r["country_code"] for r in recs} == {"US"}
    assert recs[0]["region"] == "WI"


def test_nuforc_jsonl_source_record_id_from_query_link(tmp_path):
    recs = _nuforc_records(tmp_path)
    assert recs[0]["source_record_id"] == "12345"
    assert recs[1]["source_record_id"] == "67890"


def test_nuforc_jsonl_source_record_id_from_legacy_link(tmp_path):
    recs = _nuforc_records(tmp_path)
    assert recs[2]["source_record_id"] == "99999"


def test_nuforc_jsonl_url_description_summary_coords(tmp_path):
    recs = _nuforc_records(tmp_path)
    assert recs[0]["url"] == "https://nuforc.org/sighting/?id=12345"
    assert recs[0]["description"].startswith("Bright orange sphere hovered")
    assert recs[0]["summary"] == "Orange sphere hovers over lake"
    assert (recs[0]["latitude"], recs[0]["longitude"]) == (42.5917, -88.4334)
    assert recs[1]["latitude"] is None


def test_nuforc_jsonl_duration_seconds(tmp_path):
    recs = _nuforc_records(tmp_path)
    assert [r["duration_seconds"] for r in recs] == [1200, 5400, 45]
    assert recs[0]["duration_text"] == "20 minutes"


# ---------------------------------------------------------------- GEIPAN

def _geipan_official(tmp_path):
    (tmp_path / "geipan").mkdir()
    shutil.copy(FIXTURES / "geipan_official.csv", tmp_path / "geipan" / "geipan_official.csv")
    return {r["source_record_id"]: r for r in geipan.load(str(tmp_path))}


def test_geipan_official_count_and_url(tmp_path):
    recs = _geipan_official(tmp_path)
    assert sorted(recs) == ["2001", "2002", "2003"]
    for cid, r in recs.items():
        assert r["url"] == f"https://www.cnes-geipan.fr/fr/cas/{cid}"
        assert r["country_code"] == "FR"


def test_geipan_official_dates_and_precision(tmp_path):
    recs = _geipan_official(tmp_path)
    assert (recs["2001"]["date_iso"], recs["2001"]["date_precision"]) == ("2015-03-12", "day")
    assert (recs["2002"]["date_iso"], recs["2002"]["date_precision"]) == ("1999-07", "month")
    assert recs["2002"]["day"] is None


def test_geipan_official_region_mapping(tmp_path):
    recs = _geipan_official(tmp_path)
    assert recs["2001"]["region"] == "Martinique"
    assert recs["2002"]["region"] == "75"  # metropolitan departments pass through as codes


def test_geipan_official_classification(tmp_path):
    recs = _geipan_official(tmp_path)
    assert recs["2001"]["classification"] == "D1"
    assert recs["2002"]["classification"] == "C"
    assert recs["2003"]["classification"] == "A"


def test_geipan_official_description_from_resume_web(tmp_path):
    recs = _geipan_official(tmp_path)
    assert recs["2001"]["description"] == "Lumiere orange observee au-dessus de la mer par deux temoins."
    assert "interne" not in recs["2001"]["description"]


RR0_FRAGMENT = (
    "caseNumber,url,city,zoneType,zoneCode,dateTime,postTime,classification\n"
    "2001,https://www.cnes-geipan.fr/fr/cas/2001,Le Lamentin,departement,972,2015-03-12T00:00,2016-01-10,D1\n"
    "9999,https://www.cnes-geipan.fr/fr/cas/9999,Lyon,departement,69,2001-05-05T00:00,2002-01-01,B\n"
)


@pytest.mark.parametrize("official_dir,fragment_dir", [("geipan", "rr0/time"), ("rr0/time", "geipan")])
def test_geipan_official_wins_over_rr0_fragment(tmp_path, official_dir, fragment_dir):
    # Both orders: loader walks sorted paths, so cover official-first and fragment-first.
    od, fd = tmp_path / official_dir, tmp_path / fragment_dir
    od.mkdir(parents=True)
    fd.mkdir(parents=True)
    shutil.copy(FIXTURES / "geipan_official.csv", od / "GEIPAN_official.csv")
    (fd / "GEIPAN_Catalogue_2015.csv").write_text(RR0_FRAGMENT, encoding="utf-8")
    recs = {r["source_record_id"]: r for r in geipan.load(str(tmp_path))}
    assert sorted(recs) == ["2001", "2002", "2003", "9999"]
    assert recs["2001"]["description"].startswith("Lumiere orange")
    assert recs["9999"]["description"] is None  # fragment-only case still loaded


# ---------------------------------------------------------------- Gods-Eye GEIPAN JSON / uap-monitor feeds
import json as _json
from openuap.sources import uap_monitor as _um
from openuap.sources import nuforc as _nuforc_mod

_GE_FIELDS = ["id", "lat", "lon", "precision(2=commune,1=department,0=none)", "place", "zone", "dept", "year",
              "month", "day", "utc", "localTime", "class", "witnesses", "short", "summary"]


def _write_godseye(tmp_path):
    d = tmp_path / "geipan"; d.mkdir()
    (d / "geipan_godseye.json").write_text(_json.dumps({"fields": _GE_FIELDS, "records": [
        ["2009-07-02349", 48.8164, 2.3211, 2, "Montrouge", "Hauts-de-Seine", "92", 2009, 7, 21, "2009-07-20T22:40Z", "00:40", "B", 1, "Quatre lumières.", "Le 21 juillet 2009 ..."],
        ["1937-01-01656", 14.6358, -60.9909, 1, "Le Marigot", "Martinique", "972", 1937, None, None, None, None, "C", None, "Globe éclairé.", "Témoignage récent ..."],
        ["1999-12-00001", 0, 0, 0, "", "", None, 1999, 12, None, None, None, "D1", None, "Sans lieu.", ""],
    ]}), encoding="utf-8")
    return tmp_path


def test_godseye_geipan_records(tmp_path):
    recs = {r["source_record_id"]: r for r in geipan.load(str(_write_godseye(tmp_path)))}
    assert len(recs) == 3
    a = recs["2009-07-02349"]
    assert (a["date_iso"], a["time_text"], a["city"], a["region"], a["latitude"], a["classification"]) == \
        ("2009-07-21", "00:40", "Montrouge", "Hauts-de-Seine", 48.8164, "B")
    assert a["geo_precision"] == "city" and a["witnesses"] == "1" and a["url"].endswith("/fr/cas/2009-07-02349")
    b = recs["1937-01-01656"]
    assert (b["date_iso"], b["date_precision"], b["geo_precision"]) == ("1937", "year", "region")
    c = recs["1999-12-00001"]
    assert c["latitude"] is None and c["date_iso"] == "1999-12" and c["description"] == "Sans lieu."


def test_godseye_wins_over_rr0_fragment(tmp_path):
    _write_godseye(tmp_path)
    # Uppercase name sorts BEFORE geipan_godseye.json in the same folder, so the fragment loads first;
    # only the "richer record wins" rule makes the Gods-Eye description survive.
    frag = tmp_path / "geipan"
    (frag / "GEIPAN_Cataloguedecas.csv").write_text(
        "caseNumber,url,city,zoneType,zoneCode,dateTime,postTime,classification\n"
        "2009-07-02349,https://geipan.fr/x,MONTROUGE,(D),92,2009-07,2010-01-01,B\n", encoding="utf-8")
    recs = {r["source_record_id"]: r for r in geipan.load(str(tmp_path))}
    assert len(recs) == 3 and recs["2009-07-02349"]["description"] == "Le 21 juillet 2009 ..."


def _write_uap_monitor(tmp_path):
    d = tmp_path / "uap_monitor"; d.mkdir()
    (d / "nuforc-2020.json").write_text(_json.dumps([
        {"id": "161478", "source": "NUFORC", "occurredAt": "2020-12-31T23:30:00", "reportedAt": "2021-01-05T22:34:33",
         "postedAt": "2021-01-19T00:00:00", "location": "Damascus, MD, USA", "shape": "Fireball", "duration": "12:00",
         "observers": 2, "summary": "Red sphere.", "description": "Saw many red fireball spheres.",
         "coordinates": {"lat": 39.28844, "lng": -77.20387}, "country": "USA", "credibility": 75,
         "characteristics": ["Lights on object", "Changed color"], "status": "PENDING"},
        {"id": "161479", "source": "NUFORC", "occurredAt": "2020-06-01T00:00:00", "location": "Watford (UK/England), , United Kingdom",
         "shape": "Unknown", "duration": 5, "observers": 0, "summary": "S", "description": "", "coordinates": None, "country": "United Kingdom"},
    ]), encoding="utf-8")
    (d / "dow-pursue-1950.json").write_text(_json.dumps([
        {"id": "dow-342_flying discs 1949", "source": "DOW_PURSUE", "occurredAt": "1950-01-09T00:00:00", "location": "",
         "shape": "Unknown", "duration": "", "observers": 0, "summary": "Incident reports under FSR 200-4.",
         "description": "This file primarily contains incident reports.",
         "ref": "https://www.war.gov/medialink/ufo/release_1/x.pdf", "country": "Unknown"},
    ]), encoding="utf-8")
    (d / "dow-pursue-manifest.json").write_text("{}", encoding="utf-8")
    return tmp_path


def test_uap_monitor_nuforc_records(tmp_path):
    recs = {r["source_record_id"]: r for r in _um.load_nuforc(str(_write_uap_monitor(tmp_path)))}
    a = recs["161478"]
    assert (a["date_iso"], a["time_text"], a["city"], a["region"], a["country_code"]) == ("2020-12-31", "23:30", "Damascus", "MD", "US")
    assert (a["latitude"], a["longitude"], a["geo_precision"]) == (39.28844, -77.20387, "city")
    assert a["duration_seconds"] == 720 and a["shape"] == "fireball" and a["witnesses"] == "2"
    assert a["url"] == "https://nuforc.org/sighting/?id=161478"
    assert _json.loads(a["tags"]) == ["Changed color", "Lights on object"]
    assert _json.loads(a["extra"])["uap_monitor_credibility"] == 75
    b = recs["161479"]
    assert b["time_text"] is None and b["latitude"] is None and b["shape"] is None
    assert b["country_code"] == "GB" and b["duration_seconds"] == 300 and b["description"] == "S"


def test_uap_monitor_pursue_records(tmp_path):
    recs = list(_um.load(str(_write_uap_monitor(tmp_path))))   # load() emits PURSUE only
    assert len(recs) == 1
    r = recs[0]
    assert (r["source_key"], r["event_type"], r["date_iso"]) == ("dow_pursue", "document", "1950-01-09")
    assert r["url"] == "https://www.war.gov/medialink/ufo/release_1/x.pdf" and r["summary"] == "Incident reports under FSR 200-4."


def test_nuforc_precedence_uap_monitor_over_planetsig(tmp_path):
    _write_uap_monitor(tmp_path)
    nd = tmp_path / "nuforc"; nd.mkdir()
    (nd / "planetsig.csv").write_text(
        "10/10/1949 20:30,san marcos,tx,us,cylinder,2700,45 minutes,\"Old one\",4/27/2004,29.88,-97.94\n"
        "6/15/2020 21:00,austin,tx,us,light,60,1 minute,\"Should be skipped: 2020 is covered\",7/1/2020,30.27,-97.74\n",
        encoding="utf-8")
    recs = list(_nuforc_mod.load(str(tmp_path)))
    years = sorted(r["year"] for r in recs)
    assert years == [1949, 2020, 2020] and sum(1 for r in recs if _json.loads(r["extra"]).get("mirror") == "planetsig-2014") == 1
