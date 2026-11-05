"""URECAT - Patrick Gross's catalogue of close encounters ("Les ovnis vus de près").

Export mirrored at rr0.org: time/GrossPatrick_URECAT--Les-ovnis-vus-de-pres-.csv
Columns: url,title,basicInfo.base.sightingDate,...placeName,...country,...departmentOrState,...witnesses
"""
from __future__ import annotations

import csv
import glob
import os
from typing import Iterator

from ..normalize import clean_text, normalize_country, parse_date
from .base import make_record

SOURCES = {
    "urecat": dict(
        name="URECAT close-encounter catalogue (Patrick Gross)", publisher="Patrick Gross, ufologie.patrickgross.org",
        url="https://ufologie.patrickgross.org/ce3/", license="Author's site; index mirrored at rr0.org (GFDL). Research use.",
        access_type="public", coverage="worldwide close encounters (CE3), 1800s-2018",
        fetched_from="https://github.com/RR0/rr0.org/blob/master/time/GrossPatrick_URECAT--Les-ovnis-vus-de-pres-.csv",
    )
}


def load(raw_dir: str) -> Iterator[dict]:
    for p in sorted(glob.glob(os.path.join(raw_dir, "rr0", "**", "GrossPatrick_URECAT*.csv"), recursive=True)):
        with open(p, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            cols = {c.split(".")[-1]: c for c in (reader.fieldnames or [])}
            if "url" not in cols:
                continue
            for r in reader:
                url = (r.get("url") or "").strip()
                if not url:
                    continue
                g = lambda k: clean_text(r.get(cols.get(k, k)))
                country_raw = g("country")
                country, code = normalize_country(country_raw)
                region = g("departmentOrState")
                yield make_record(
                    "urecat", source_record_id=url.rsplit("/", 1)[-1], event_type="close_encounter",
                    date=parse_date(g("sightingDate")), date_text=g("sightingDate"),
                    location_text=", ".join(x for x in (g("placeName"), region, country_raw) if x) or None,
                    city=g("placeName"), region=region, country=country, country_code=code,
                    description=g("title"), witnesses=g("witnesses"), url=url,
                )
