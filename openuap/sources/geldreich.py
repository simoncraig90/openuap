"""Loader for the JSON timelines in Richard Geldreich's `ufo_data` repository.

https://github.com/richgel999/ufo_data  (bin/*.json)

The repository converts many independent catalogues to one JSON shape:
    {date, desc, location?, time?, ref, source, source_id, type?, attributes?, key_vals?}
We keep each catalogue as its own `source_key` so licensing stays traceable.
"""
from __future__ import annotations

import json
import os
import re
from typing import Iterator

from ..normalize import (clean_text, normalize_country, parse_date, parse_latlong, parse_location, split_city_region,
                         to_int, to_float, make_date)
from .base import make_record

RAW_SUBDIR = "geldreich"
REPO_URL = "https://github.com/richgel999/ufo_data"
RAW_BASE = "https://raw.githubusercontent.com/richgel999/ufo_data/main/bin/"

# file -> (source_key, metadata)
FILES = {
    "hatch_udb.json": ("hatch", dict(
        name="Larry Hatch *U* UFO Database", publisher="Larry Hatch (1994-2002); JSON conversion by R. Geldreich",
        url="https://github.com/richgel999/ufo_data/blob/main/bin/hatch_udb.json",
        license="Copyright Larry Hatch 1994-2002. Family verbally permitted use (via D. Marler, NUFOHRC). Non-commercial research use; attribute.",
        access_type="public-mirror", coverage="worldwide, antiquity-2002, ~18k curated cases")),
    "eberhart.json": ("eberhart", dict(
        name="UFOs and Intelligence: A Timeline (George M. Eberhart)", publisher="George M. Eberhart / CUFOS",
        url="https://cufos.org/resources/ufo-timeline/",
        license="Copyright 2022 G. M. Eberhart. Inclusion permitted by author (email 2025-05-12). Non-commercial.",
        access_type="public-mirror", coverage="worldwide, antiquity-2022, chronology of UFO/intelligence events")),
    "johnson.json": ("johnson", dict(
        name="Dr. Donald A. Johnson 'On This Day' chronology", publisher="Donald A. Johnson / ufoinfo.com",
        url="https://web.archive.org/web/http://www.ufoinfo.com/onthisday/calendar.html",
        license="Copyright 2012 D. A. Johnson. Author not reachable; treat as research/non-commercial only.",
        access_type="public-mirror", coverage="worldwide, 1400s-2012")),
    "overmeire.json": ("overmeire", dict(
        name="Godelieve Van Overmeire chronology (translated from French)", publisher="G. Van Overmeire (1935-2021)",
        url="https://web.archive.org/web/20060107070423/http://users.skynet.be/sky84985/chrono.html",
        license="Explicitly not copyrighted by author.", access_type="public-mirror",
        coverage="worldwide, antiquity-2000s, Belgian/French emphasis")),
    "nicap_db.json": ("nicap", dict(
        name="NICAP case database", publisher="National Investigations Committee on Aerial Phenomena (defunct 1980)",
        url="http://www.nicap.org/NSID/NSID_DBListingbyDate.pdf",
        license="Unknown; organisation defunct since 1980, likely public domain.", access_type="public-mirror",
        coverage="worldwide, 1860-1980, quality-screened cases")),
    "rr0.json": ("rr0_chronology", dict(
        name="RR0 French chronology (Jérôme Beau), translated", publisher="rr0.org",
        url="https://rr0.org/", license="GNU Free Documentation License", access_type="public",
        coverage="worldwide, antiquity-2023")),
    "anon_pdf.json": ("anon_pdf_2023", dict(
        name="Anonymous 2023 UAP timeline PDF", publisher="Anonymous",
        url="https://github.com/richgel999/ufo_data/blob/main/bin/anon_pdf.md",
        license="Public domain (each event marked PUBLIC DOMAIN in original).", access_type="public",
        coverage="US government / disclosure events 1940s-2023")),
    "maj2.json": ("geldreich_majestic", dict(
        name="Majestic timeline (R. Geldreich original research)", publisher="Richard Geldreich Jr.",
        url=REPO_URL, license="Copyright 2023 R. Geldreich. Commercial use permitted with attribution.",
        access_type="public", coverage="US government/UFO history events, 1940s-2023")),
    "magonia.json": ("magonia", dict(
        name="Passport to Magonia landing catalogue (Jacques Vallée)", publisher="Jacques Vallée (1969/1993)",
        url="https://web.archive.org/web/20120415100852/http://www.ufoinfo.com/magonia/magonia.shtml",
        license="Book copyright 1993; data widely republished. Research use only.", access_type="public-mirror",
        coverage="worldwide close encounters/landings, 1868-1968")),
    "ancient.json": ("wonders_in_the_sky", dict(
        name="Wonders in the Sky (Vallée & Aubeck) pre-1880 catalogue", publisher="J. Vallée & C. Aubeck (2009)",
        url="https://archive.org/details/JacquesValleeChrisAubeckWondersInTheSkyUnexplainedAerialObjectsFromAntiquityToModernTimes",
        license="Book copyright 2009. Research use only.", access_type="public-mirror",
        coverage="worldwide, antiquity-1879")),
    "bb_unknowns.json": ("bluebook_unknowns", dict(
        name="Project Blue Book 'Unknowns' (Don Berliner compilation)", publisher="USAF Project Blue Book / Don Berliner (FUFOR)",
        url="https://github.com/richgel999/uap_resources/blob/main/bluebook_uncensored_unknowns_don_berliner.pdf",
        license="US government records (public domain); compilation by D. Berliner.", access_type="public",
        coverage="USAF cases officially left 'unidentified', 1947-1969")),
    "scully.json": ("scully", dict(
        name="Frank Scully-era newspaper clippings timeline", publisher="compiled by R. Geldreich",
        url=REPO_URL, license="Newspaper excerpts 1947-1950; compilation CC-style per repo README.",
        access_type="public", coverage="US press coverage 1947-1950")),
    "ufo_evidence_hall.json": ("hall_ufo_evidence", dict(
        name="The UFO Evidence vol. 2 (Richard H. Hall) case list", publisher="Richard H. Hall / NICAP",
        url="https://www.amazon.com/UFO-Evidence-Richard-Hall/dp/0760706271",
        license="Book copyright 2001. Research use only.", access_type="public-mirror",
        coverage="worldwide, 1947-1990s, selected cases")),
    "mut.json": ("adams_choppers", dict(
        name="Mystery helicopters and animal mutilations (Thomas R. Adams)", publisher="Thomas R. Adams (1991)",
        url="https://ia801409.us.archive.org/33/items/adams-thomas-choppers-and-the-choppers-1/",
        license="Copyright 1991; contact efforts ongoing per repo. Research use only.", access_type="public-mirror",
        coverage="US, 1960s-1991")),
    "dolan.json": ("dolan", dict(
        name="UFOs and the National Security State chronology (Richard Dolan)", publisher="Richard M. Dolan (2009)",
        url="https://archive.org/details/ufosnationalsecu00dola/mode/2up",
        license="Book appendix copyright 2009. Research use only.", access_type="public-mirror",
        coverage="worldwide military/government cases 1941-1973")),
    "hostile.json": ("fawcett_hostile", dict(
        name="The Flying Saucers are Hostile! (George D. Fawcett, 1961)", publisher="George D. Fawcett",
        url="https://archive.org/details/the_flying_saucers_are_hostile_george_d_fawcett_1961/mode/2up",
        license="Unknown copyright status (1961 pulp manuscript).", access_type="public-mirror",
        coverage="worldwide, 1940s-1961")),
    "trace.json": ("trace_cases", dict(
        name="Physical trace cases (misc.)", publisher="compiled by R. Geldreich", url=REPO_URL,
        license="See repository README.", access_type="public", coverage="selected trace cases")),
    "nuclear_tests.json": ("nuclear_tests", dict(
        name="Worldwide nuclear explosions (context dataset)", publisher="Yang, North, Romney & Richards (Columbia)",
        url="https://www.ldeo.columbia.edu/~richards/my_papers/WW_nuclear_tests_IASPEI_HB.pdf",
        license="Academic dataset; context only, not UFO reports.", access_type="public",
        coverage="all known nuclear tests 1945-2017")),
}
# Nine chapter files from Philip Rife's "It Didn't Start with Roswell" share one source.
for _i in range(1, 10):
    FILES[f"pre_roswell_chap{_i}.json"] = ("rife_pre_roswell", dict(
        name="It Didn't Start with Roswell (Philip L. Rife, 2001)", publisher="Philip L. Rife",
        url="https://archive.org/details/it-didnt-start-with-roswell-50-years-of-amazing-ufo-crashes-close-encounters-and",
        license="Book copyright 2001; summaries only. Research use only.", access_type="public-mirror",
        coverage="pre-1947 cases, worldwide"))

ENRICHMENT_FILES = ["eberhart_openai.json", "openai_results.json"]   # LLM-extracted locations/names

SOURCES = {}
for _fn, (_key, _meta) in FILES.items():
    SOURCES.setdefault(_key, dict(_meta, fetched_from=RAW_BASE + _fn))

_TYPE_MAP = {
    "sighting": "sighting", "ufo sighting": "sighting", "ufo sightings": "sighting",
    "ufo collision": "sighting", "crash retrieval": "crash_retrieval",
    "nuclear test": "nuclear_test", "mystery helicopter/mutilation related": "mutilation",
    "historical event": "historical", "rocket launch": "aerospace", "aerospace": "aerospace",
    "ufological event": "ufology", "letter": "document", "newspaper article": "document",
    "interview": "document", "version": "meta",
}


_SIGHTING_WORDS = ("sighting", "encounter", "ufo", "abduction", "landing", "ce2", "ce3", "ce4", "creature", "radar",
                   "photo", "shootdown", "pursuit", "foo fighter", "airship", "airplane", "mystery helicopter",
                   "anomalous", "entity", "alien", "contact", "chase", "collision", "video")
_DOCUMENT_WORDS = ("memo", "letter", "report", "article", "statement", "briefing", "hearing", "testimony", "publication",
                   "book", "document", "interview", "telegram", "teletype", "message", "note", "paper", "release",
                   "manual", "regulation", "communique", "filing", "lawsuit", "court", "poll", "bulletin", "notice",
                   "speech", "speach", "lecture", "presentation", "conference", "broadcast", "radio", "tv", "movie",
                   "documentary", "news", "press", "website", "debate", "proceedings", "transcript", "recording",
                   "legislation", "law", "amendment", "resolution", "sheet", "guide", "forum", "symposium", "meeting")


def _norm_type(t, default: str) -> str:
    """Collapse free-form source types into a small vocabulary; the raw value is kept in extra.source_type."""
    if isinstance(t, list):
        t = t[0] if t else None
    if not t:
        return default
    raw = str(t).lower().strip()
    if raw in _TYPE_MAP:
        return _TYPE_MAP[raw]
    if "mutilation" in raw:
        return "mutilation"
    if "crash" in raw and ("retrieval" in raw or "recovery" in raw):
        return "crash_retrieval"
    if any(w in raw for w in _SIGHTING_WORDS):
        return "sighting"
    if any(w in raw for w in _DOCUMENT_WORDS):
        return "document"
    if raw in ("atomic", "nuclear test"):
        return "nuclear_test" if default == "nuclear_test" else "historical"
    return "historical"


def _load_json(path):
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                return v
        return []
    return data


def _load_enrichment(raw_dir) -> dict:
    """source_id -> {locations:[...], names:[...], index:[...]}."""
    out = {}
    for fn in ENRICHMENT_FILES:
        p = os.path.join(raw_dir, RAW_SUBDIR, fn)
        if not os.path.exists(p):
            continue
        for r in _load_json(p):
            sid = r.get("event_source_id")
            if sid:
                out[sid] = {k: r.get(k) or [] for k in ("locations", "names", "index")}
    return out


_HATCH_LOCALE_TAG = re.compile(r"^([A-Z]{2,4}):")


def _hatch_record(r: dict) -> dict:
    kv = r.get("key_vals") or {}
    lat, lon = parse_latlong(kv.get("LatLong"))
    city, region = split_city_region(r.get("location"))
    if kv.get("State/Prov") and kv["State/Prov"] != "Unknown":
        region = kv["State/Prov"]
    country, code = normalize_country(kv.get("Country"), region)
    attrs = r.get("attributes") or []
    tags = []
    for a in attrs:
        m = _HATCH_LOCALE_TAG.match(a)
        tags.append(m.group(1) if m else a)
    dur_min = to_float(kv.get("Duration"))
    dur_s = int(dur_min * 60) if dur_min and dur_min > 0 else None
    date = parse_date(r.get("date"))
    desc = clean_text(r.get("desc"))
    return make_record(
        "hatch", source_record_id=r.get("source_id"), event_type="sighting", date=date, date_text=r.get("date"),
        time_text=r.get("time") or None, location_text=r.get("location"), city=city, region=region,
        country=country, country_code=code, latitude=lat, longitude=lon, geo_precision="city" if lat else "none",
        duration_text=f"{dur_min:g} min" if dur_min else None, duration_seconds=dur_s,
        credibility=to_int(kv.get("Credibility")), strangeness=to_int(kv.get("Strangeness")),
        description=desc, refs=r.get("ref"), tags=tags,
        extra={"hatch_desc": kv.get("HatchDesc"), "locale": kv.get("Locale"), "elev_m": kv.get("Elev"),
               "rel_alt": kv.get("RelAlt"), "attributes": attrs},
    )


def _generic_record(source_key: str, r: dict, default_type: str, enrich: dict) -> dict | None:
    etype = _norm_type(r.get("type"), default_type)
    if etype == "meta":
        return None
    sid = r.get("source_id")
    e = enrich.get(sid, {}) if sid else {}
    location = r.get("location")
    if isinstance(location, list):
        location = "; ".join(str(x) for x in location if x) or None
    if not location and e.get("locations"):
        location = e["locations"][0]
    kv = r.get("key_vals") or {}
    lat, lon = parse_latlong(kv.get("LatLong") or (location if source_key == "nuclear_tests" else None))
    if source_key == "nuclear_tests":
        country, code = normalize_country(kv.get("NukeCountry"))
        city = region = None
    else:
        loc = parse_location(location)
        city, region, country, code = loc["city"], loc["region"], loc["country"], loc["country_code"]
    date = parse_date(r.get("date"))
    desc = clean_text(r.get("desc"))
    extra = {k: v for k, v in kv.items()} if kv else {}
    if r.get("type") and etype != str(r.get("type")).lower():
        extra["source_type"] = r.get("type")
    if e:
        extra["extracted_locations"] = e.get("locations")
        extra["extracted_names"] = e.get("names")
    if r.get("see_also"):
        extra["see_also"] = r["see_also"]
    classification = None
    if source_key == "bluebook_unknowns":
        classification = "Blue Book unknown"
        etype = "sighting"
    return make_record(
        source_key, source_record_id=sid, event_type=etype, date=date, date_text=r.get("date"),
        time_text=r.get("time") or None, location_text=location, city=city, region=region,
        country=country, country_code=code, latitude=lat, longitude=lon,
        classification=classification, description=desc, refs=r.get("ref"), extra=extra,
    )


def load(raw_dir: str) -> Iterator[dict]:
    base = os.path.join(raw_dir, RAW_SUBDIR)
    enrich = _load_enrichment(raw_dir)
    for fn, (source_key, meta) in FILES.items():
        path = os.path.join(base, fn)
        if not os.path.exists(path):
            continue
        default_type = "nuclear_test" if source_key == "nuclear_tests" else ("historical" if source_key in ("geldreich_majestic", "anon_pdf_2023", "scully", "eberhart") else "sighting")
        for r in _load_json(path):
            if source_key == "hatch":
                yield _hatch_record(r)
            else:
                rec = _generic_record(source_key, r, default_type, enrich)
                if rec:
                    yield rec
