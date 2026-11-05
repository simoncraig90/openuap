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
