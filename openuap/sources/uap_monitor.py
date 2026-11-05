"""Loaders for the JSON feeds published in mhdSid/uap-monitor (MIT) under public/data/.

* nuforc-<year>.json  — NUFORC reports with full text and NUFORC ids (one array per year).
  Same ToS caveat as every NUFORC mirror: NUFORC forbids scraping/redistribution; use for research,
  and replace with an official export when you have one.
* dow-pursue-<year>.json — index of the US Department of War PURSUE Release 01 (war.gov/UFO)
  declassified files, with per-document summaries. US government records: public domain.

Record shape (both): id, source, occurredAt, reportedAt, postedAt, location, shape, duration,
observers, summary, description (+ a few extras on PURSUE rows).
"""
from __future__ import annotations

import glob
import json
import os
import re
from typing import Iterator

from ..normalize import clean_text, make_date, normalize_country, parse_duration_seconds, parse_location
from .base import make_record

RAW_SUBDIR = "uap_monitor"
REPO = "https://github.com/mhdSid/uap-monitor"

SOURCES = {
    "dow_pursue": dict(
        name="PURSUE Release 01 document index (US Department of War, war.gov/UFO)",
        publisher="US Department of War; index compiled by mhdSid/uap-monitor",
        url="https://www.war.gov/ufo/", license="US government records, public domain. Index repo MIT.",
        access_type="public", coverage="137 declassified files (FBI, DoW, NASA, State), 1945-2020s",
        fetched_from=REPO + " public/data/dow-pursue-*.json",
    ),
}

_RE_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}:\d{2})(?::\d{2})?)?")


def _split_when(s: str):
    """'2020-12-31T23:30:00' -> (ParsedDate, '23:30'). Midnight is treated as 'time unknown'."""
    m = _RE_ISO.match(s or "")
    if not m:
        return make_date(None, text=s), None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    t = m.group(4)
    if t == "00:00":
        t = None
    return make_date(y, mo, d, text=s[:10]), t


def _nuforc_duration_seconds(s: str):
    """uap-monitor stores NUFORC durations either as free text or 'MM:SS'."""
    if not s:
        return None
    s = str(s)
    if re.fullmatch(r"\d+", s.strip()):
        return int(s.strip()) * 60  # bare number: NUFORC convention is minutes
    m = re.match(r"^(\d{1,3}):(\d{2})$", s.strip())
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return parse_duration_seconds(s)


def nuforc_years(raw_dir: str) -> set[int]:
    """Years covered by nuforc-<year>.json files (used by the NUFORC loader to avoid double-loading the 2014 mirror)."""
    years = set()
    for p in glob.glob(os.path.join(raw_dir, RAW_SUBDIR, "nuforc-*.json")):
        m = re.search(r"nuforc-(\d{4})\.json$", p)
        if m:
            years.add(int(m.group(1)))
    return years


def load_nuforc(raw_dir: str) -> Iterator[dict]:
    for p in sorted(glob.glob(os.path.join(raw_dir, RAW_SUBDIR, "nuforc-*.json"))):
        if not re.search(r"nuforc-\d{4}\.json$", p):
            continue
        with open(p, encoding="utf-8") as f:
            recs = json.load(f)
        if not isinstance(recs, list):
            continue
        for r in recs:
            date, time_text = _split_when(r.get("occurredAt") or "")
            loc = parse_location(r.get("location"))
            if not loc["country_code"] and r.get("country"):
                loc["country"], loc["country_code"] = normalize_country(r.get("country"))
            coords = r.get("coordinates") or {}
            lat, lon = (coords.get("lat"), coords.get("lng")) if isinstance(coords, dict) else (None, None)
            if not (isinstance(lat, (int, float)) and isinstance(lon, (int, float))) or (lat == 0 and lon == 0):
                lat = lon = None
            desc = clean_text(r.get("description"))
            summ = clean_text(r.get("summary"))
            rid = str(r.get("id") or "").strip() or None
            yield make_record(
                "nuforc", source_record_id=rid, event_type="sighting", date=date, date_text=date.date_text,
                time_text=time_text, location_text=clean_text(r.get("location")),
                city=loc["city"], region=loc["region"], country=loc["country"], country_code=loc["country_code"],
                latitude=lat, longitude=lon, geo_precision="city" if lat is not None else None,
                shape=str(r.get("shape") or "").strip().lower().replace("unknown", "") or None,
                duration_text=str(r.get("duration") or "").strip() or None,
                duration_seconds=_nuforc_duration_seconds(str(r.get("duration") or "")),
                summary=summ, description=desc or summ,
                witnesses=str(r["observers"]) if r.get("observers") else None,
                url=f"https://nuforc.org/sighting/?id={rid}" if rid and rid.isdigit() else None,
                tags=[c for c in (r.get("characteristics") or []) if isinstance(c, str)],
                extra={"reported_at": r.get("reportedAt"), "posted_at": r.get("postedAt"), "mirror": "uap-monitor",
                       "uap_monitor_credibility": r.get("credibility"), "status": r.get("status")},
            )


def load_pursue(raw_dir: str) -> Iterator[dict]:
    for p in sorted(glob.glob(os.path.join(raw_dir, RAW_SUBDIR, "dow-pursue-*.json"))):
        if p.endswith("manifest.json"):
            continue
        with open(p, encoding="utf-8") as f:
            recs = json.load(f)
        if not isinstance(recs, list):
            continue
        for r in recs:
            date, _ = _split_when(r.get("occurredAt") or "")
            loc = parse_location(r.get("location"))
            known = {"id", "source", "occurredAt", "reportedAt", "postedAt", "location", "shape", "duration",
                     "observers", "summary", "description"}
            extra = {k: v for k, v in r.items() if k not in known}
            yield make_record(
                "dow_pursue", source_record_id=str(r.get("id")), event_type="document", date=date,
                date_text=date.date_text, location_text=clean_text(r.get("location")),
                city=loc["city"], region=loc["region"], country=loc["country"], country_code=loc["country_code"],
                summary=clean_text(r.get("summary")), description=clean_text(r.get("description")) or clean_text(r.get("summary")),
                url=extra.get("ref") or extra.get("url") or "https://www.war.gov/ufo/",
                refs=["PURSUE Release 01, https://www.war.gov/ufo/"], extra=extra,
            )


def load(raw_dir: str) -> Iterator[dict]:
    yield from load_pursue(raw_dir)
    # NUFORC rows are emitted through sources/nuforc.py so all NUFORC data shares one source_key and policy.
