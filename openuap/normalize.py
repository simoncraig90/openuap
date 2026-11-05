"""Normalisation helpers shared by every loader.

Everything here is pure: text in, structured values out. Loaders call these so
that dates, coordinates, durations and country names end up in one shape no
matter how messy the source was.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, asdict
from typing import Optional

# --------------------------------------------------------------------------- dates

_MONTHS = {
    "january": 1, "jan": 1, "janvier": 1,
    "february": 2, "feb": 2, "février": 2, "fevrier": 2,
    "march": 3, "mar": 3, "mars": 3,
    "april": 4, "apr": 4, "avril": 4,
    "may": 5, "mai": 5,
    "june": 6, "jun": 6, "juin": 6,
    "july": 7, "jul": 7, "juillet": 7,
    "august": 8, "aug": 8, "août": 8, "aout": 8,
    "september": 9, "sep": 9, "sept": 9, "septembre": 9,
    "october": 10, "oct": 10, "octobre": 10,
    "november": 11, "nov": 11, "novembre": 11,
    "december": 12, "dec": 12, "décembre": 12, "decembre": 12,
}
_SEASONS = {"spring": 4, "summer": 7, "fall": 10, "autumn": 10, "winter": 1}
_QUALIFIERS = ("early", "mid", "late", "circa", "ca.", "c.", "about", "around", "approx", "approximately")
_PRECISION_RANK = {"day": 0, "month": 1, "season": 2, "year": 3, "decade": 4, "century": 5, "unknown": 9}


@dataclass
class ParsedDate:
    date_text: Optional[str]
    date_iso: Optional[str]      # zero-padded, sortable: 1952-07-19 / 1952-07 / 1952
    year: Optional[int]
    month: Optional[int]
    day: Optional[int]
    precision: str               # day | month | season | year | decade | century | unknown
    approximate: bool

    def as_row(self) -> dict:
        d = asdict(self)
        d["date_precision"] = d.pop("precision")
        d["date_approx"] = 1 if d.pop("approximate") else 0
        return d


def _iso(year, month=None, day=None) -> str:
    s = f"{year:04d}"
    if month:
        s += f"-{month:02d}"
        if day:
            s += f"-{day:02d}"
    return s


def _days_in_month(year: int, month: int) -> int:
    if month == 2:
        leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        return 29 if leap else 28
    return 30 if month in (4, 6, 9, 11) else 31


def make_date(year: Optional[int], month: Optional[int] = None, day: Optional[int] = None,
              text: Optional[str] = None, approximate: bool = False, precision: Optional[str] = None) -> ParsedDate:
    """Build a ParsedDate from already-separated components, validating ranges."""
    if year is None or year <= 0 or year > 2100:
        return ParsedDate(text, None, None, None, None, "unknown", approximate)
    if month is not None and not (1 <= month <= 12):
        month, day = None, None
    if month is not None and day is not None and not (1 <= day <= _days_in_month(year, month)):
        day = None
    if precision is None:
        precision = "day" if day else ("month" if month else "year")
    return ParsedDate(text, _iso(year, month, day), year, month, day, precision, approximate)


_RE_NUMERIC = re.compile(r"^(-?\d{1,2})/(-?\d{1,2})/(\d{1,4})$")        # M/D/YYYY  (Hatch uses literal years, so 70 == AD 70)
_RE_MONTH_YEAR = re.compile(r"^(\d{1,2})/(\d{1,4})$")                   # M/YYYY (or M/YY, literal year)
_RE_YEAR = re.compile(r"^(\d{1,4})$")
_RE_DECADE = re.compile(r"^(\d{3,4})0'?s$")
_RE_ISO = re.compile(r"^(\d{4})(?:-(\d{1,2}|NaN))?(?:-(\d{1,2}|NaN))?(?:[ T].*)?$", re.I)
_RE_WORD_DATE = re.compile(r"^(?:(\d{1,2})\s+)?([A-Za-zéû\.]+)\s+(\d{3,4})$")  # 24 June 1947 / June 1947
_RE_US_WORD_DATE = re.compile(r"^([A-Za-z\.]+)\s+(\d{1,2}),?\s+(\d{3,4})$")   # June 24, 1947


def parse_date(text) -> ParsedDate:
    """Parse the many date spellings found across UFO catalogues.

    Handles M/D/YYYY, M/YYYY, YYYY, ISO forms, 'Summer 1952', 'Late 7/1952',
    "1950's", 'June 24, 1947', '(approximate)' suffixes, and GEIPAN's '1970-NaN'.
    Two-digit years are taken literally (Hatch's database really does contain AD 70).
    """
    if text is None:
        return ParsedDate(None, None, None, None, None, "unknown", False)
    raw = str(text).strip()
    s = raw
    approx = False
    precision_override = None

    s = html.unescape(s)
    if "(approximate)" in s.lower() or s.lower().startswith(("circa", "ca.", "c.", "about", "around", "approx")):
        approx = True
    s = re.sub(r"\(approximate\)", "", s, flags=re.I).strip()
    s = re.sub(r"^(circa|ca\.|c\.|about|around|approximately|approx\.?)\s+", "", s, flags=re.I).strip()
    s = s.rstrip("?").strip()
    if s.endswith("?"):
        approx = True

    # Qualifiers such as Early/Mid/Late keep the month or year but mark approximate.
    m = re.match(r"^(early|mid|late)\s+(.*)$", s, re.I)
    if m:
        approx = True
        s = m.group(2).strip()

    # Seasons.
    m = re.match(r"^(spring|summer|fall|autumn|winter)\s+(?:of\s+)?(\d{3,4})$", s, re.I)
    if m:
        year = int(m.group(2))
        return make_date(year, _SEASONS[m.group(1).lower()], None, raw, True, "season")

    m = _RE_DECADE.match(s)
    if m:
        return make_date(int(m.group(1)) * 10, None, None, raw, True, "decade")

    m = re.match(r"^(\d{1,2})(st|nd|rd|th)\s+century$", s, re.I)
    if m:
        return make_date((int(m.group(1)) - 1) * 100 + 1, None, None, raw, True, "century")

    m = _RE_NUMERIC.match(s)
    if m:
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        mo = mo if mo > 0 else None
        d = d if d > 0 else None
        return make_date(y, mo, d, raw, approx)

    m = _RE_MONTH_YEAR.match(s)
    if m:
        return make_date(int(m.group(2)), int(m.group(1)), None, raw, approx)

    m = _RE_YEAR.match(s)
    if m:
        return make_date(int(m.group(1)), None, None, raw, approx)

    m = _RE_ISO.match(s)
    if m:
        y = int(m.group(1))
        mo = int(m.group(2)) if m.group(2) and m.group(2).lower() != "nan" else None
        d = int(m.group(3)) if m.group(3) and m.group(3).lower() != "nan" else None
        return make_date(y, mo, d, raw, approx)

    m = _RE_WORD_DATE.match(s)
    if m and m.group(2).lower().strip(".") in _MONTHS:
        d = int(m.group(1)) if m.group(1) else None
        return make_date(int(m.group(3)), _MONTHS[m.group(2).lower().strip(".")], d, raw, approx)

    m = _RE_US_WORD_DATE.match(s)
    if m and m.group(1).lower().strip(".") in _MONTHS:
        return make_date(int(m.group(3)), _MONTHS[m.group(1).lower().strip(".")], int(m.group(2)), raw, approx)

    # Last resort: a 4-digit year anywhere in the string.
    m = re.search(r"\b(1[0-9]{3}|20[0-9]{2})\b", s)
    if m:
        return make_date(int(m.group(1)), None, None, raw, True, "year")
    return ParsedDate(raw, None, None, None, None, "unknown", approx)


# ------------------------------------------------------------------- coordinates

def parse_latlong(text) -> tuple[Optional[float], Optional[float]]:
    """'31.766668 35.233335' or '31.76, 35.23' -> (lat, lon). Rejects (0,0) and out-of-range."""
    if not text:
        return None, None
    m = re.match(r"^\s*(-?\d+(?:\.\d+)?)[ ,;]+(-?\d+(?:\.\d+)?)\s*$", str(text))
    if not m:
        return None, None
    lat, lon = float(m.group(1)), float(m.group(2))
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None, None
    return lat, lon


def to_float(v) -> Optional[float]:
    try:
        f = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return f


def to_int(v) -> Optional[int]:
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------- durations

_DUR_UNITS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
}


def parse_duration_seconds(text) -> Optional[int]:
    """Best-effort free-text duration ('45 minutes', '1-2 hrs', '20 seconds') to seconds."""
    if not text:
        return None
    s = str(text).lower().replace("~", "").strip()
    m = re.search(r"(\d+(?:\.\d+)?)(?:\s*-\s*(\d+(?:\.\d+)?))?\s*([a-z]+)", s)
    if not m:
        return None
    unit = m.group(3)
    if unit not in _DUR_UNITS:
        return None
    a = float(m.group(1))
    b = float(m.group(2)) if m.group(2) else a
    return int(((a + b) / 2) * _DUR_UNITS[unit])


# ---------------------------------------------------------------------- countries

_COUNTRY_TO_CODE = {
    "afghanistan": "AF",
    "alaska": "US",
    "albania": "AL",
    "andorra": "AD",
    "angola": "AO",
    "antarctica": "AQ",
    "antigua": "AG",
    "armenia": "AM",
    "aruba": "AW",
    "azerbaijan": "AZ",
    "azores": "PT",
    "bahamas": "BS",
    "bahrain": "BH",
    "bangladesh": "BD",
    "barbados": "BB",
    "belarus": "BY",
    "belize": "BZ",
    "benin": "BJ",
    "bermuda": "BM",
    "bhutan": "BT",
    "bosnia": "BA",
    "botswana": "BW",
    "brunei": "BN",
    "burkina faso": "BF",
    "burma": "MM",
    "burundi": "BI",
    "cambodia": "KH",
    "cameroon": "CM",
    "canary islands": "ES",
    "cape verde": "CV",
    "cayman islands": "KY",
    "central african republic": "CF",
    "ceylon": "LK",
    "chad": "TD",
    "channel islands": "GB",
    "comoros": "KM",
    "congo": "CG",
    "cook islands": "CK",
    "costa rica": "CR",
    "curacao": "CW",
    "cyprus": "CY",
    "djibouti": "DJ",
    "dominica": "DM",
    "dominican republic": "DO",
    "east timor": "TL",
    "ecuador": "EC",
    "el salvador": "SV",
    "equatorial guinea": "GQ",
    "eritrea": "ER",
    "estonia": "EE",
    "ethiopia": "ET",
    "falkland islands": "FK",
    "faroe islands": "FO",
    "fiji": "FJ",
    "formosa": "TW",
    "french guiana": "GF",
    "french polynesia": "PF",
    "gabon": "GA",
    "gambia": "GM",
    "georgia (country)": "GE",
    "ghana": "GH",
    "gibraltar": "GI",
    "greenland": "GL",
    "grenada": "GD",
    "guadeloupe": "GP",
    "guam": "GU",
    "guatemala": "GT",
    "guinea": "GN",
    "guyana": "GY",
    "haiti": "HT",
    "hawaii": "US",
    "honduras": "HN",
    "hong kong": "HK",
    "iceland": "IS",
    "isle of man": "IM",
    "ivory coast": "CI",
    "jamaica": "JM",
    "jordan": "JO",
    "kazakhstan": "KZ",
    "kiribati": "KI",
    "kosovo": "XK",
    "kuwait": "KW",
    "kyrgyzstan": "KG",
    "laos": "LA",
    "latvia": "LV",
    "lebanon": "LB",
    "lesotho": "LS",
    "liberia": "LR",
    "libya": "LY",
    "liechtenstein": "LI",
    "lithuania": "LT",
    "luxembourg": "LU",
    "macedonia": "MK",
    "madagascar": "MG",
    "madeira": "PT",
    "malawi": "MW",
    "maldives": "MV",
    "mali": "ML",
    "malta": "MT",
    "manchuria": "CN",
    "marshall islands": "MH",
    "martinique": "MQ",
    "mauritania": "MR",
    "mauritius": "MU",
    "micronesia": "FM",
    "moldova": "MD",
    "monaco": "MC",
    "mongolia": "MN",
    "montenegro": "ME",
    "mozambique": "MZ",
    "myanmar": "MM",
    "namibia": "NA",
    "nauru": "NR",
    "nepal": "NP",
    "new caledonia": "NC",
    "nicaragua": "NI",
    "niger": "NE",
    "okinawa": "JP",
    "oman": "OM",
    "palau": "PW",
    "panama": "PA",
    "paraguay": "PY",
    "persia": "IR",
    "qatar": "QA",
    "reunion": "RE",
    "rhodesia": "ZW",
    "rwanda": "RW",
    "samoa": "WS",
    "san marino": "SM",
    "sao tome": "ST",
    "senegal": "SN",
    "seychelles": "SC",
    "siberia": "RU",
    "sierra leone": "SL",
    "singapore": "SG",
    "slovakia": "SK",
    "slovenia": "SI",
    "solomon islands": "SB",
    "somalia": "SO",
    "sri lanka": "LK",
    "st kitts": "KN",
    "st lucia": "LC",
    "st vincent": "VC",
    "sudan": "SD",
    "suriname": "SR",
    "swaziland": "SZ",
    "syria": "SY",
    "tahiti": "PF",
    "tajikistan": "TJ",
    "tanzania": "TZ",
    "tibet": "CN",
    "togo": "TG",
    "tonga": "TO",
    "trinidad": "TT",
    "turkmenistan": "TM",
    "turks and caicos": "TC",
    "tuvalu": "TV",
    "uganda": "UG",
    "united arab emirates": "AE",
    "uzbekistan": "UZ",
    "vanuatu": "VU",
    "vatican": "VA",
    "virgin islands": "VI",
    "western sahara": "EH",
    "yemen": "YE",
    "zaire": "CD",
    "zambia": "ZM",
    "zimbabwe": "ZW",

    "united states": "US", "usa": "US", "u.s.a.": "US", "u.s.": "US", "us": "US", "united states of america": "US",
    "canada": "CA", "mexico": "MX", "brazil": "BR", "brasil": "BR", "argentina": "AR", "chile": "CL", "peru": "PE",
    "colombia": "CO", "venezuela": "VE", "uruguay": "UY", "bolivia": "BO", "cuba": "CU", "puerto rico": "PR",
    "united kingdom": "GB", "uk": "GB", "u.k.": "GB", "great britain": "GB", "england": "GB", "scotland": "GB",
    "wales": "GB", "northern ireland": "GB", "ireland": "IE", "france": "FR", "germany": "DE", "west germany": "DE",
    "east germany": "DE", "italy": "IT", "spain": "ES", "portugal": "PT", "belgium": "BE", "netherlands": "NL",
    "holland": "NL", "switzerland": "CH", "austria": "AT", "sweden": "SE", "norway": "NO", "denmark": "DK",
    "finland": "FI", "iceland": "IS", "poland": "PL", "czechoslovakia": "CZ", "czech republic": "CZ", "hungary": "HU",
    "romania": "RO", "bulgaria": "BG", "greece": "GR", "turkey": "TR", "yugoslavia": "RS", "serbia": "RS",
    "croatia": "HR", "russia": "RU", "ussr": "RU", "soviet union": "RU", "u.s.s.r.": "RU", "ukraine": "UA",
    "israel": "IL", "palestine": "PS", "egypt": "EG", "iran": "IR", "iraq": "IQ", "saudi arabia": "SA",
    "south africa": "ZA", "nigeria": "NG", "kenya": "KE", "morocco": "MA", "algeria": "DZ", "tunisia": "TN",
    "india": "IN", "pakistan": "PK", "china": "CN", "japan": "JP", "south korea": "KR", "korea": "KR",
    "north korea": "KP", "taiwan": "TW", "philippines": "PH", "indonesia": "ID", "malaysia": "MY", "thailand": "TH",
    "vietnam": "VN", "australia": "AU", "new zealand": "NZ", "papua new guinea": "PG",
}
_CODE_TO_NAME = {
    "AD": "Andorra",
    "AE": "United Arab Emirates",
    "AF": "Afghanistan",
    "AG": "Antigua and Barbuda",
    "AL": "Albania",
    "AM": "Armenia",
    "AO": "Angola",
    "AQ": "Antarctica",
    "AR": "Argentina",
    "AT": "Austria",
    "AU": "Australia",
    "AW": "Aruba",
    "AZ": "Azerbaijan",
    "BA": "Bosnia and Herzegovina",
    "BB": "Barbados",
    "BD": "Bangladesh",
    "BE": "Belgium",
    "BF": "Burkina Faso",
    "BG": "Bulgaria",
    "BH": "Bahrain",
    "BI": "Burundi",
    "BJ": "Benin",
    "BM": "Bermuda",
    "BN": "Brunei",
    "BO": "Bolivia",
    "BR": "Brazil",
    "BS": "Bahamas",
    "BT": "Bhutan",
    "BW": "Botswana",
    "BY": "Belarus",
    "BZ": "Belize",
    "CA": "Canada",
    "CD": "DR Congo",
    "CF": "Central African Republic",
    "CG": "Congo",
    "CH": "Switzerland",
    "CI": "Ivory Coast",
    "CK": "Cook Islands",
    "CL": "Chile",
    "CM": "Cameroon",
    "CN": "China",
    "CO": "Colombia",
    "CR": "Costa Rica",
    "CU": "Cuba",
    "CV": "Cape Verde",
    "CW": "Curaçao",
    "CY": "Cyprus",
    "CZ": "Czech Republic",
    "DE": "Germany",
    "DJ": "Djibouti",
    "DK": "Denmark",
    "DM": "Dominica",
    "DO": "Dominican Republic",
    "DZ": "Algeria",
    "EC": "Ecuador",
    "EE": "Estonia",
    "EG": "Egypt",
    "EH": "Western Sahara",
    "ER": "Eritrea",
    "ES": "Spain",
    "ET": "Ethiopia",
    "FI": "Finland",
    "FJ": "Fiji",
    "FK": "Falkland Islands",
    "FM": "Micronesia",
    "FO": "Faroe Islands",
    "FR": "France",
    "GA": "Gabon",
    "GB": "United Kingdom",
    "GD": "Grenada",
    "GE": "Georgia",
    "GF": "French Guiana",
    "GH": "Ghana",
    "GI": "Gibraltar",
    "GL": "Greenland",
    "GM": "Gambia",
    "GN": "Guinea",
    "GP": "Guadeloupe",
    "GQ": "Equatorial Guinea",
    "GR": "Greece",
    "GT": "Guatemala",
    "GU": "Guam",
    "GY": "Guyana",
    "HK": "Hong Kong",
    "HN": "Honduras",
    "HR": "Croatia",
    "HT": "Haiti",
    "HU": "Hungary",
    "ID": "Indonesia",
    "IE": "Ireland",
    "IL": "Israel",
    "IM": "Isle of Man",
    "IN": "India",
    "IQ": "Iraq",
    "IR": "Iran",
    "IS": "Iceland",
    "IT": "Italy",
    "JM": "Jamaica",
    "JO": "Jordan",
    "JP": "Japan",
    "KE": "Kenya",
    "KG": "Kyrgyzstan",
    "KH": "Cambodia",
    "KI": "Kiribati",
    "KM": "Comoros",
    "KN": "Saint Kitts and Nevis",
    "KP": "North Korea",
    "KR": "South Korea",
    "KW": "Kuwait",
    "KY": "Cayman Islands",
    "KZ": "Kazakhstan",
    "LA": "Laos",
    "LB": "Lebanon",
    "LC": "Saint Lucia",
    "LI": "Liechtenstein",
    "LK": "Sri Lanka",
    "LR": "Liberia",
    "LS": "Lesotho",
    "LT": "Lithuania",
    "LU": "Luxembourg",
    "LV": "Latvia",
    "LY": "Libya",
    "MA": "Morocco",
    "MC": "Monaco",
    "MD": "Moldova",
    "ME": "Montenegro",
    "MG": "Madagascar",
    "MH": "Marshall Islands",
    "MK": "North Macedonia",
    "ML": "Mali",
    "MM": "Myanmar",
    "MN": "Mongolia",
    "MQ": "Martinique",
    "MR": "Mauritania",
    "MT": "Malta",
    "MU": "Mauritius",
    "MV": "Maldives",
    "MW": "Malawi",
    "MX": "Mexico",
    "MY": "Malaysia",
    "MZ": "Mozambique",
    "NA": "Namibia",
    "NC": "New Caledonia",
    "NE": "Niger",
    "NG": "Nigeria",
    "NI": "Nicaragua",
    "NL": "Netherlands",
    "NO": "Norway",
    "NP": "Nepal",
    "NR": "Nauru",
    "NZ": "New Zealand",
    "OM": "Oman",
    "PA": "Panama",
    "PE": "Peru",
    "PF": "French Polynesia",
    "PG": "Papua New Guinea",
    "PH": "Philippines",
    "PK": "Pakistan",
    "PL": "Poland",
    "PR": "Puerto Rico",
    "PS": "Palestine",
    "PT": "Portugal",
    "PW": "Palau",
    "PY": "Paraguay",
    "QA": "Qatar",
    "RE": "Réunion",
    "RO": "Romania",
    "RS": "Serbia",
    "RU": "Russia",
    "RW": "Rwanda",
    "SA": "Saudi Arabia",
    "SB": "Solomon Islands",
    "SC": "Seychelles",
    "SD": "Sudan",
    "SE": "Sweden",
    "SG": "Singapore",
    "SI": "Slovenia",
    "SK": "Slovakia",
    "SL": "Sierra Leone",
    "SM": "San Marino",
    "SN": "Senegal",
    "SO": "Somalia",
    "SR": "Suriname",
    "ST": "São Tomé and Príncipe",
    "SV": "El Salvador",
    "SY": "Syria",
    "SZ": "Eswatini",
    "TC": "Turks and Caicos",
    "TD": "Chad",
    "TG": "Togo",
    "TH": "Thailand",
    "TJ": "Tajikistan",
    "TL": "East Timor",
    "TM": "Turkmenistan",
    "TN": "Tunisia",
    "TO": "Tonga",
    "TR": "Turkey",
    "TT": "Trinidad and Tobago",
    "TV": "Tuvalu",
    "TW": "Taiwan",
    "TZ": "Tanzania",
    "UA": "Ukraine",
    "UG": "Uganda",
    "US": "United States",
    "UY": "Uruguay",
    "UZ": "Uzbekistan",
    "VA": "Vatican City",
    "VC": "Saint Vincent",
    "VE": "Venezuela",
    "VI": "US Virgin Islands",
    "VN": "Vietnam",
    "VU": "Vanuatu",
    "WS": "Samoa",
    "XK": "Kosovo",
    "YE": "Yemen",
    "ZA": "South Africa",
    "ZM": "Zambia",
    "ZW": "Zimbabwe",

    "US": "United States", "CA": "Canada", "MX": "Mexico", "BR": "Brazil", "AR": "Argentina", "CL": "Chile",
    "GB": "United Kingdom", "IE": "Ireland", "FR": "France", "DE": "Germany", "IT": "Italy", "ES": "Spain",
    "PT": "Portugal", "BE": "Belgium", "NL": "Netherlands", "CH": "Switzerland", "AT": "Austria", "SE": "Sweden",
    "NO": "Norway", "DK": "Denmark", "FI": "Finland", "RU": "Russia", "IL": "Israel", "ZA": "South Africa",
    "IN": "India", "CN": "China", "JP": "Japan", "AU": "Australia", "NZ": "New Zealand", "PE": "Peru",
    "CO": "Colombia", "VE": "Venezuela", "UY": "Uruguay", "PR": "Puerto Rico", "PL": "Poland", "GR": "Greece",
    "TR": "Turkey", "EG": "Egypt", "IR": "Iran", "PK": "Pakistan", "KR": "South Korea", "PH": "Philippines",
    "ID": "Indonesia", "TH": "Thailand", "VN": "Vietnam", "UA": "Ukraine", "HU": "Hungary", "RO": "Romania",
    "CZ": "Czech Republic", "PS": "Palestine",
}
_US_STATES = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me",
    "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa",
    "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy", "dc",
}
_CA_PROV = {"ab", "bc", "mb", "nb", "nl", "ns", "nt", "nu", "on", "pe", "qc", "sk", "yt", "ont", "que"}
_US_STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO",
    "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME",
    "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS", "missouri": "MO",
    "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM",
    "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN",
    "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC", "washington dc": "DC", "washington d.c.": "DC",
}
_CA_PROV_NAMES = {
    "alberta": "AB", "british columbia": "BC", "manitoba": "MB", "new brunswick": "NB", "newfoundland": "NL",
    "nova scotia": "NS", "ontario": "ON", "quebec": "QC", "québec": "QC", "saskatchewan": "SK", "yukon": "YT",
    "labrador": "NL", "northwest territories": "NT",
}


def normalize_country(name_or_code, region: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
    """Return (country_name, iso2_code). Accepts names ('USA'), codes ('us'), or nothing plus a US state."""
    code = None
    if name_or_code:
        s = str(name_or_code).strip()
        low = s.lower()
        if len(s) == 2 and s.upper() in _CODE_TO_NAME:
            code = s.upper()
        elif low in _COUNTRY_TO_CODE:
            code = _COUNTRY_TO_CODE[low]
        else:
            return s, None  # keep the name even without a code
    if code is None and region:
        r = str(region).strip().lower().rstrip(".")
        if r in _US_STATES or r in _US_STATE_NAMES:
            code = "US"
        elif r in _CA_PROV or r in _CA_PROV_NAMES:
            code = "CA"
    if code is None:
        return None, None
    return _CODE_TO_NAME.get(code, code), code


def is_us_state(region) -> bool:
    r = str(region or "").strip().lower()
    return r in _US_STATES or r in _US_STATE_NAMES


def _is_region(tok: str) -> bool:
    t = tok.strip().lower().rstrip(".")
    return t in _US_STATES or t in _US_STATE_NAMES or t in _CA_PROV or t in _CA_PROV_NAMES


def _is_country(tok: str) -> bool:
    t = tok.strip().lower().rstrip(".")
    return t in _COUNTRY_TO_CODE or (len(t) == 2 and t.upper() in _CODE_TO_NAME and t.upper() not in {"IN", "ID", "ME", "OR", "PA", "DE", "CO", "AR", "AL"})


def parse_location(location) -> dict:
    """Split a free-text place into city/region/country using comma tokens.

    'Dai-el-Aouagri, Morocco' -> country Morocco; 'Near Goose Bay, Labrador' -> region NL, Canada;
    'Levelland, Texas' -> region Texas, US; 'USA, Chattanooga (Tennessee)' -> US / Tennessee.
    Returns {city, region, country, country_code}. Unknown pieces stay in city/region unchanged.
    """
    out = {"city": None, "region": None, "country": None, "country_code": None}
    if not location:
        return out
    text = str(location).strip()
    # Overmeire style: 'USA, Chattanooga (Tennessee)' -> country first, region in parentheses.
    m = re.match(r"^([^,]+),\s*(.+?)\s*\(([^)]+)\)\s*$", text)
    if m and _is_country(m.group(1)):
        country, code = normalize_country(m.group(1))
        out.update(city=m.group(2).strip(), region=m.group(3).strip(), country=country, country_code=code)
        return out
    parts = [p.strip() for p in re.split(r",|;", text) if p.strip()]
    if not parts:
        return out
    if len(parts) == 1:
        tok = parts[0]
        if _is_country(tok):
            out["country"], out["country_code"] = normalize_country(tok)
        else:
            out["city"] = tok.title() if tok.isupper() else tok
        return out
    last = parts[-1]
    if _is_country(last):
        out["country"], out["country_code"] = normalize_country(last)
        parts = parts[:-1]
    if parts and _is_region(parts[-1]):
        out["region"] = parts[-1]
        if not out["country_code"]:
            out["country"], out["country_code"] = normalize_country(None, parts[-1])
        parts = parts[:-1]
    elif parts and len(parts) >= 2 and out["country_code"]:
        out["region"] = parts[-1]
        parts = parts[:-1]
    if parts:
        city = ", ".join(parts)
        out["city"] = city.title() if city.isupper() else city
    elif out["region"] and not out["city"]:
        pass
    return out


# ----------------------------------------------------------------------- text

_RE_BAD_ENTITY = re.compile(r"&#(\d+)(?!;)")


def clean_text(text) -> Optional[str]:
    """Unescape HTML entities (including NUFORC's semicolon-less '&#44'), collapse whitespace."""
    if text is None:
        return None
    s = str(text)
    s = _RE_BAD_ENTITY.sub(lambda m: chr(int(m.group(1))) if int(m.group(1)) < 0x110000 else m.group(0), s)
    s = html.unescape(s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s).strip()
    return s or None


def summarize(text, n: int = 240) -> Optional[str]:
    if not text:
        return None
    s = re.sub(r"\s+", " ", str(text)).strip()
    if len(s) <= n:
        return s
    cut = s[: n - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut + "…"


def split_city_region(location) -> tuple[Optional[str], Optional[str]]:
    """'BELLINGHAM, WA' -> ('Bellingham', 'WA'); 'Norfolk, VA' -> ('Norfolk', 'VA'); 'PALESTINE' -> ('Palestine', None)."""
    if not location:
        return None, None
    parts = [p.strip() for p in str(location).split(",") if p.strip()]
    if not parts:
        return None, None
    city = parts[0]
    region = parts[1] if len(parts) > 1 else None
    if city.isupper():
        city = city.title()
    return city or None, region or None
