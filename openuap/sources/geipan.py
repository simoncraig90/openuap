"""GEIPAN (CNES, France) case catalogue loader.

Two input shapes are accepted, both dropped under data/raw/rr0/ or data/raw/geipan/:

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
import os
from typing import Iterator

from ..normalize import clean_text, make_date, parse_date
from .base import make_record

SOURCES = {
    "geipan": dict(
        name="GEIPAN case catalogue", publisher="CNES / GEIPAN (France)",
        url="https://www.cnes-geipan.fr/fr/recherche/cas",
        license="French public data (CNES). Full export available from the GEIPAN site; this build uses fragments mirrored at rr0.org (GFDL).",
        access_type="public", coverage="France and overseas départements, 1937-present, ~3,000 cases (partial in mirror)",
        fetched_from="https://github.com/RR0/rr0.org (time/**/GEIPAN_Catalogue*.csv)",
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


def load(raw_dir: str) -> Iterator[dict]:
    seen: dict[str, dict] = {}
    files = []
    for sub in ("geipan", "rr0"):
        base = os.path.join(raw_dir, sub)
        files += glob.glob(os.path.join(base, "**", "GEIPAN*.csv"), recursive=True)
        files += glob.glob(os.path.join(base, "*.csv")) if sub == "geipan" else []
    for p in sorted(set(files)):
        with open(p, encoding="utf-8-sig") as f:
            head = f.readline()
        rows = _official_rows(p) if ";" in head and "id_cas" in head else _rr0_rows(p)
        for item in rows:
            prev = seen.get(item["id"])
            # Prefer the row with a real description (official export) over a bare fragment.
            if prev is None or (not prev["description"] and item["rec"]["description"]):
                seen[item["id"]] = item["rec"]
    yield from seen.values()
