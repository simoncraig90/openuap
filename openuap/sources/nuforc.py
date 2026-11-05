"""NUFORC (National UFO Reporting Center) loaders.

IMPORTANT LICENSING NOTE
------------------------
NUFORC's terms of service (https://nuforc.org/terms/) forbid scraping and
redistributing their data. The canonical path is to request an export from
NUFORC directly and drop it in data/raw/nuforc/.  Two formats are understood:

1. `planetsig` CSV mirror (2014 snapshot, ~88k rows, widely used on Kaggle):
   datetime,city,state,country,shape,duration_seconds,duration_text,comments,date_posted,lat,lon
   Comments are truncated to ~130 characters in that snapshot. Use for development only.
2. Line-delimited JSON in the shape produced by timothyrenner/nuforc_sightings_data
   (`text, stats, date_time, report_link, city, state, shape, duration, summary, posted`).
   Put any such file as data/raw/nuforc/*.jsonl.
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
from typing import Iterator

from ..normalize import (clean_text, normalize_country, parse_date, parse_duration_seconds, to_float, to_int,
                         is_us_state)
from .base import make_record

RAW_SUBDIR = "nuforc"
SOURCES = {
    "nuforc": dict(
        name="NUFORC sighting reports", publisher="National UFO Reporting Center",
        url="https://nuforc.org/databank/",
        license="NUFORC ToS forbids scraping/redistribution. Development mirror: planetsig/ufo-reports (2014 snapshot). "
                "Obtain an official export from NUFORC for production use.",
        access_type="public-mirror", coverage="worldwide (mostly US), 1906-2014 in mirror; to present in official export",
        fetched_from="https://raw.githubusercontent.com/planetsig/ufo-reports/master/csv-data/ufo-complete-geocoded-time-standardized.csv",
    )
}

_PLANETSIG_COLS = ["datetime", "city", "state", "country", "shape", "duration_seconds", "duration_text",
                   "comments", "date_posted", "latitude", "longitude"]
_RE_PAREN_COUNTRY = re.compile(r"\(([^)]+)\)\s*$")


def _split_datetime(s: str) -> tuple[str, str | None]:
    s = (s or "").strip()
    if " " in s:
        d, t = s.split(" ", 1)
        return d, t.strip() or None
    return s, None


def _planetsig_rows(path: str) -> Iterator[dict]:
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if len(row) < 11:
                continue
            if i == 0 and row[0].lower().startswith("datetime"):
                continue
            r = dict(zip(_PLANETSIG_COLS, row))
            date_text, time_text = _split_datetime(r["datetime"])
            city = clean_text(r["city"])
            city_disp = city.title() if city else None
            region = (r["state"] or "").strip().upper() or None
            cc = (r["country"] or "").strip().lower() or None
            country_hint = cc
            if not country_hint and city:
                m = _RE_PAREN_COUNTRY.search(city)
                if m:
                    country_hint = m.group(1).split("/")[0].strip()
            country, code = normalize_country(country_hint, region)
            if code is None and region and is_us_state(region):
                country, code = "United States", "US"
            lat, lon = to_float(r["latitude"]), to_float(r["longitude"])
            if lat is not None and lon is not None and (lat == 0 and lon == 0):
                lat = lon = None
            dur_s = to_int(r["duration_seconds"])
            if not dur_s:
                dur_s = parse_duration_seconds(r["duration_text"])
            desc = clean_text(r["comments"])
            yield make_record(
                "nuforc", source_record_id=None, event_type="sighting", date=parse_date(date_text),
                date_text=date_text, time_text=time_text,
                location_text=", ".join(x for x in (city_disp, region) if x) or None,
                city=city_disp, region=region, country=country, country_code=code,
                latitude=lat, longitude=lon, geo_precision="city" if lat is not None else "none",
                shape=(r["shape"] or "").strip().lower() or None,
                duration_text=(r["duration_text"] or "").strip() or None, duration_seconds=dur_s,
                description=desc, extra={"date_posted": r["date_posted"], "mirror": "planetsig-2014"},
            )


def _jsonl_rows(path: str) -> Iterator[dict]:
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            date_text, time_text = _split_datetime(r.get("date_time") or "")
            # NUFORC web reports use two-digit years (M/DD/YY); assume 1900s for YY>30 else 2000s.
            m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2})$", date_text)
            if m:
                yy = int(m.group(3))
                date_text = f"{m.group(1)}/{m.group(2)}/{1900 + yy if yy > 30 else 2000 + yy}"
            region = (r.get("state") or "").strip().upper() or None
            country, code = normalize_country(None, region)
            link = r.get("report_link")
            sid = None
            if link:
                mm = re.search(r"/(\d+)/?$|S(\d+)\.html", link)
                sid = next((g for g in (mm.groups() if mm else ()) if g), None)
            yield make_record(
                "nuforc", source_record_id=sid or link, event_type="sighting", date=parse_date(date_text),
                date_text=date_text, time_text=time_text,
                location_text=", ".join(x for x in ((r.get("city") or "").strip(), region or "") if x) or None,
                city=(r.get("city") or "").strip() or None, region=region, country=country, country_code=code,
                latitude=to_float(r.get("city_latitude")), longitude=to_float(r.get("city_longitude")),
                geo_precision="city" if r.get("city_latitude") else "none",
                shape=(r.get("shape") or "").strip().lower() or None,
                duration_text=(r.get("duration") or "").strip() or None,
                duration_seconds=parse_duration_seconds(r.get("duration")),
                summary=clean_text(r.get("summary")), description=clean_text(r.get("text")), url=link,
                extra={"posted": r.get("posted"), "stats": r.get("stats")},
            )


def load(raw_dir: str) -> Iterator[dict]:
    base = os.path.join(raw_dir, RAW_SUBDIR)
    if not os.path.isdir(base):
        return
    jsonl = sorted(glob.glob(os.path.join(base, "*.jsonl")) + glob.glob(os.path.join(base, "*.json")))
    if jsonl:
        for p in jsonl:
            yield from _jsonl_rows(p)
        return  # an official/full export supersedes the 2014 mirror
    for p in sorted(glob.glob(os.path.join(base, "*.csv"))):
        yield from _planetsig_rows(p)
