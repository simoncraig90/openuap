"""Shared record construction for loaders."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Optional

from ..normalize import ParsedDate, parse_date, summarize

EVENT_COLUMNS = [
    "source_key", "source_record_id", "event_type",
    "date_text", "date_iso", "year", "month", "day", "date_precision", "date_approx", "time_text",
    "location_text", "city", "region", "country", "country_code", "latitude", "longitude", "geo_precision",
    "shape", "duration_text", "duration_seconds", "classification", "credibility", "strangeness",
    "summary", "description", "witnesses", "url", "refs", "tags", "extra", "content_hash",
]


def _as_list(v) -> list:
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [x for x in v if x not in (None, "")]
    return [v]


def _scalar(v):
    """Collapse lists/dicts that some sources put in scalar fields into a string."""
    if isinstance(v, (list, tuple)):
        return "; ".join(str(x) for x in v if x not in (None, "")) or None
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False)
    return v


def make_record(source_key: str, *, source_record_id: Optional[str] = None, event_type: str = "sighting",
                date: Optional[ParsedDate] = None, date_text: Optional[str] = None, time_text=None,
                location_text=None, city=None, region=None, country=None, country_code=None,
                latitude=None, longitude=None, geo_precision=None, shape=None, duration_text=None,
                duration_seconds=None, classification=None, credibility=None, strangeness=None,
                summary=None, description=None, witnesses=None, url=None,
                refs: Iterable[Any] = (), tags: Iterable[str] = (), extra: Optional[dict] = None) -> dict:
    """Assemble one normalised event row. Dates can be passed pre-parsed or as text."""
    time_text, location_text, city, region, shape, duration_text, classification, summary, description, witnesses, url = (
        _scalar(v) for v in (time_text, location_text, city, region, shape, duration_text, classification, summary, description, witnesses, url))
    if date is None:
        date = parse_date(date_text)
    row = {c: None for c in EVENT_COLUMNS}
    row.update(date.as_row())
    if date_text is not None:
        row["date_text"] = date_text
    if latitude is not None and longitude is not None and geo_precision is None:
        geo_precision = "source"
    if latitude is None or longitude is None:
        latitude = longitude = None
        geo_precision = geo_precision or "none"
    row.update({
        "source_key": source_key, "source_record_id": source_record_id, "event_type": event_type,
        "time_text": time_text, "location_text": location_text, "city": city, "region": region,
        "country": country, "country_code": country_code, "latitude": latitude, "longitude": longitude,
        "geo_precision": geo_precision, "shape": shape, "duration_text": duration_text,
        "duration_seconds": duration_seconds, "classification": classification, "credibility": credibility,
        "strangeness": strangeness, "summary": summary or summarize(description), "description": description,
        "witnesses": witnesses, "url": url,
        "refs": json.dumps(_as_list(refs), ensure_ascii=False),
        "tags": json.dumps(sorted(set(_as_list(tags))), ensure_ascii=False),
        "extra": json.dumps(extra or {}, ensure_ascii=False, default=str),
    })
    key = source_record_id if source_record_id else "|".join(str(row[c] or "") for c in ("date_text", "location_text", "description", "time_text"))
    row["content_hash"] = hashlib.sha1(f"{source_key}::{key}".encode("utf-8")).hexdigest()
    return row
