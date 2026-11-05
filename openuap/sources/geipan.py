"""GEIPAN (CNES, France) case catalogue loader.

Three input shapes are accepted:

0. The compact geocoded JSON built by domw99/Gods-Eye-UAPs from GEIPAN's bulk CSVs
   (public/data/geipan.json -> data/raw/geipan/geipan_godseye.json): full catalogue, ~2,770 cases,
   communes geocoded with GeoNames (CC BY 4.0). Fields:
   id, lat, lon, precision(2=commune,1=department,0=none), place, zone, dept, year, month, day, utc,
   localTime, class, witnesses, short, summary.

1. The official export from https://www.cnes-geipan.fr/fr/recherche/cas (semicolon CSV):
   cas_classification;...;id_cas;cas_numEtude;cas_nom_dossier;cas_zone_type;cas_zone_code;cas_AAAA;cas_MM;cas_JJ;...
2. Monthly fragments mirrored in the RR0 repository (comma CSV):
   caseNumber,url,city,zoneType,zoneCode,dateTime,postTime,classification

Classification: A = fully explained, B = probably explained, C = not enough data,
D = unexplained after investigation (D1 = few data, D2 = strong data).
"""
from __future__ import annotations

import csv
import glob
import json
import os
from typing import Iterator

from ..normalize import clean_text, make_date, parse_date
from .base import make_record

SOURCES = {
    "geipan": dict(
        name="GEIPAN case catalogue", publisher="CNES / GEIPAN (France)",
        url="https://www.cnes-geipan.fr/fr/recherche/cas",
        license="French public data (CNES). Bulk CSVs: https://cnes-geipan.fr/sites/default/files/Base_de_donn%C3%A9es_des_cas.csv. "
                "Geocoded JSON via domw99/Gods-Eye-UAPs (MIT; GeoNames CC BY 4.0). Fragments via rr0.org (GFDL).",
        access_type="public", coverage="France and overseas départements, 1937-2018, ~2,770 cases",
        fetched_from="https://raw.githubusercontent.com/domw99/Gods-Eye-UAPs/main/public/data/geipan.json",
    )
}
_CLASS_MEANING = {"A": "explained", "B": "probably explained", "C": "insufficient data", "D": "unexplained",
                  "D1": "unexplained (weak data)", "D2": "unexplained (strong data)"}
_OVERSEAS = {"971": "Guadeloupe", "972": "Martinique", "973": "Guyane", "974": "La Réunion", "976": "Mayotte",
             "975": "Saint-Pierre-et-Miquelon", "987": "Polynésie française", "988": "Nouvelle-Calédonie"}


def _case_url(case_id: str) -> str:
    return f"https://www.cnes-geipan.fr/fr/cas/{case_id}"


def _official_rows(path: str) -> Iterator[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for r in reader:
            cid = (r.get("id_cas") or "").strip()
            if not cid:
                continue
            y, m, d = (int(r[k]) if (r.get(k) or "").strip().isdigit() else None for k in ("cas_AAAA", "cas_MM", "cas_JJ"))
            date = make_date(y, m, d, text="-".join(str(x) for x in (y, m, d) if x))
            cls = (r.get("cas_classification") or "").strip().upper() or None
            dept = (r.get("cas_zone_code") or "").strip() or None
            desc = clean_text(r.get("cas_resume_web") or r.get("cas_resume"))
            yield {"id": cid, "rec": make_record(
                "geipan", source_record_id=cid, event_type="sighting", date=date, date_text=date.date_text,
                location_text=clean_text(r.get("cas_nom_dossier") or r.get("cas_zone_nom")),
                city=clean_text(r.get("cas_nom_dossier")), region=_OVERSEAS.get(dept, dept),
                country="France", country_code="FR", classification=cls,
                summary=_CLASS_MEANING.get(cls or "", None) if not desc else None, description=desc,
                url=_case_url(cid),
                extra={"class_meaning": _CLASS_MEANING.get(cls or ""), "num_etude": r.get("cas_numEtude"),
                       "date_maj": r.get("cas_date_maj"), "zone_type": r.get("cas_zone_type"),
                       "consistance": r.get("cas_consistance_calc"), "etrangete": r.get("cas_etrangete_calc")},
            )}


def _rr0_rows(path: str) -> Iterator[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "caseNumber" not in reader.fieldnames:
            return
        for r in reader:
            cid = (r.get("caseNumber") or "").strip()
            if not cid:
                continue
            date = parse_date(r.get("dateTime"))
            cls = (r.get("classification") or "").strip().upper() or None
            dept = (r.get("zoneCode") or "").strip() or None
            city = clean_text(r.get("city"))
            yield {"id": cid, "rec": make_record(
                "geipan", source_record_id=cid, event_type="sighting", date=date, date_text=r.get("dateTime"),
                location_text=city, city=city, region=_OVERSEAS.get(dept, dept), country="France", country_code="FR",
                classification=cls, summary=f"GEIPAN case {cid}, classification {cls} ({_CLASS_MEANING.get(cls or '', 'n/a')})",
                url=_case_url(cid),
                extra={"class_meaning": _CLASS_MEANING.get(cls or ""), "zone_type": r.get("zoneType"),
                       "post_time": r.get("postTime")},
            )}


_GE_PRECISION = {2: "city", 1: "region", 0: "none"}


def _godseye_rows(path: str) -> Iterator[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    fields = data.get("fields") or []
    idx = {name.split("(")[0]: i for i, name in enumerate(fields)}
    required = ("id", "lat", "lon", "precision", "place", "zone", "dept", "year", "month", "day", "class", "summary")
    if any(k not in idx for k in required):
        return
    for row in data.get("records", []):
        g = lambda k: row[idx[k]] if idx.get(k) is not None and idx[k] < len(row) else None
        cid = g("id")
        if not cid:
            continue
        y, m, d = (int(v) if isinstance(v, (int, float)) else None for v in (g("year"), g("month"), g("day")))
        date = make_date(y, m, d, text="-".join(str(x) for x in (y, m, d) if x))
        cls = (g("class") or "").strip().upper() or None
        prec = _GE_PRECISION.get(g("precision"), "none")
        lat, lon = (g("lat"), g("lon")) if prec != "none" else (None, None)
        dept = str(g("dept")) if g("dept") is not None else None
        region = g("zone") or _OVERSEAS.get(dept, dept)
        wit = g("witnesses")
        yield {"id": cid, "rec": make_record(
            "geipan", source_record_id=cid, event_type="sighting", date=date, date_text=date.date_text,
            time_text=g("localTime") or None, location_text=", ".join(x for x in (g("place"), region) if x) or None,
            city=g("place") or None, region=region, country="France", country_code="FR",
            latitude=lat, longitude=lon, geo_precision=prec, classification=cls,
            summary=clean_text(g("short")) or None, description=clean_text(g("summary")) or clean_text(g("short")),
            witnesses=str(int(wit)) if isinstance(wit, (int, float)) else None, url=_case_url(cid),
            extra={"class_meaning": _CLASS_MEANING.get(cls or ""), "dept": dept, "utc": g("utc"),
                   "geocoder": "GeoNames via Gods-Eye-UAPs"},
        )}


def load(raw_dir: str) -> Iterator[dict]:
    seen: dict[str, dict] = {}
    files = []
    for sub in ("geipan", "rr0"):
        base = os.path.join(raw_dir, sub)
        files += glob.glob(os.path.join(base, "**", "GEIPAN*.csv"), recursive=True)
        files += glob.glob(os.path.join(base, "*.csv")) if sub == "geipan" else []
    files += glob.glob(os.path.join(raw_dir, "geipan", "*.json"))
    for p in sorted(set(files)):
        if p.endswith(".json"):
            rows = _godseye_rows(p)
        else:
            with open(p, encoding="utf-8-sig") as f:
                head = f.readline()
            rows = _official_rows(p) if ";" in head and "id_cas" in head else _rr0_rows(p)
        for item in rows:
            prev = seen.get(item["id"])
            # Prefer the row with a real description (official export) over a bare fragment.
            if prev is None or (not prev["description"] and item["rec"]["description"]):
                seen[item["id"]] = item["rec"]
    yield from seen.values()
