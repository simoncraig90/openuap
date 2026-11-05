from openuap.normalize import parse_date, parse_latlong, parse_duration_seconds, normalize_country, parse_location, clean_text


def iso(s):
    return parse_date(s).date_iso


def test_full_dates():
    assert iso("7/19/1956") == "1956-07-19"
    assert iso("June 24, 1947") == "1947-06-24"
    assert iso("24 June 1947") == "1947-06-24"
    assert iso("2018-08-06") == "2018-08-06"
    assert iso("10/10/1949") == "1949-10-10"


def test_partial_dates():
    d = parse_date("7/1868"); assert (d.date_iso, d.precision) == ("1868-07", "month")
    d = parse_date("812"); assert (d.date_iso, d.precision) == ("0812", "year")
    d = parse_date("1970-NaN"); assert (d.date_iso, d.precision) == ("1970", "year")
    d = parse_date("Summer 1952"); assert (d.date_iso, d.precision, d.approximate) == ("1952-07", "season", True)
    d = parse_date("1950's"); assert (d.date_iso, d.precision) == ("1950", "decade")
    d = parse_date("Late 7/1952"); assert (d.date_iso, d.approximate) == ("1952-07", True)


def test_literal_two_digit_years():
    # Hatch's catalogue really contains antiquity; two-digit years are not 19xx/20xx.
    assert iso("5/21/70") == "0070-05-21"
    assert iso("4/34") == "0034-04"
    assert iso("-1/-1/66") == "0066"


def test_invalid_day_degrades():
    d = parse_date("2/30/1960"); assert (d.date_iso, d.precision) == ("1960-02", "month")
    d = parse_date("9/99/1999"); assert d.precision == "month"
    assert parse_date("unknown").precision == "unknown"
    assert parse_date(None).date_iso is None


def test_latlong():
    assert parse_latlong("31.766668 35.233335") == (31.766668, 35.233335)
    assert parse_latlong("0 0") == (None, None)
    assert parse_latlong("garbage") == (None, None)


def test_duration():
    assert parse_duration_seconds("45 minutes") == 2700
    assert parse_duration_seconds("1-2 hrs") == 5400
    assert parse_duration_seconds("20 seconds") == 20
    assert parse_duration_seconds("a while") is None


def test_country():
    assert normalize_country("USA") == ("United States", "US")
    assert normalize_country("us") == ("United States", "US")
    assert normalize_country(None, "tx") == ("United States", "US")
    assert normalize_country(None, "Texas") == ("United States", "US")
    assert normalize_country(None, "Ontario") == ("Canada", "CA")
    assert normalize_country("Atlantis") == ("Atlantis", None)


def test_parse_location():
    assert parse_location("Levelland, Texas")["country_code"] == "US"
    assert parse_location("Dai-el-Aouagri, Morocco")["country_code"] == "MA"
    loc = parse_location("USA, Chattanooga (Tennessee)")
    assert (loc["country_code"], loc["city"], loc["region"]) == ("US", "Chattanooga", "Tennessee")
    loc = parse_location("Toronto, Ontario, Canada")
    assert (loc["country_code"], loc["region"], loc["city"]) == ("CA", "Ontario", "Toronto")
    assert parse_location("BELLINGHAM, WA")["city"] == "Bellingham"
    # 'IN' / 'OR' etc. are US states, never country codes.
    assert parse_location("Gary, IN")["country_code"] == "US"


def test_clean_text():
    assert clean_text("Lackland AFB&#44 TX.  Lights &amp; turns") == "Lackland AFB, TX. Lights & turns"
    assert clean_text("&#99999999;x") is not None  # out-of-range entity does not crash
