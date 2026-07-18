"""
PierBite.com — Live Data Fetcher
Fetches current buoy, marine-zone forecast, and satellite water
temperature data from public NOAA/NWS sources and writes the
combined result to data.json. No API key or paid account required.

Updated 2026-07-17: added Algoma — dormant AGMW3 wind station (wired
for automatic reactivation), shared LMZ542 marine zone codename
"algz", and a dormant GLSEA satellite point for Algoma harbor. Also
wired Sturgeon Bay's 0Y2W3 CG station dormant ahead of that pier's
build.

Updated 2026-07-17 (v5, scoring engine — rebuilt after the original
v5 session was cut off before delivery): the 0-100 Bite Index
scoring engine now lives HERE in the backend instead of being
copy-pasted into every page. Adds a finished "piers" section to
data.json (score, band, factor breakdown, honesty labels per pier),
plus "hot_piers_today", "schema_version", and "stale_after_hours".
Includes two scoring fixes: (1) a pier missing water temp from ALL
sources is capped at 55 and marked incomplete instead of stretching
its remaining factors, and (2) warm-water hard caps now apply to
satellite and estimated temps too, not just live buoy readings.
PURELY ADDITIVE: every section v4 wrote is still written unchanged
under the same keys, so no live page breaks on deploy.

Updated 2026-07-18 (v6, Sturgeon Bay final configuration): added the
KSUE wind-history station (Door County Cherryland Airport, Sturgeon
Bay) and replaced Sturgeon Bay's provisional pier entry with the
confirmed build-session decisions — zone LMZ542, KSUE as live local
wind behind the dormant canal CG station, and a corrected water
borrow chain (Two Rivers buoy, then independent northern-lake buoy
45002; the old second fallback was the same physical buoy twice).
No other pier's configuration or any output key changed.

Updated 2026-07-18 (v7, Washington Island removed): the owner decided
not to cover Washington Island — it is ferry-access only with a small
pier, so it doesn't belong in a "where should I fish today" decision.
Removed: the washington_island pier config, the K2P2 wind-history
station (island airport, used by no other pier), and marine zone
LMZ541 (used by no other pier). DELIBERATELY KEPT: buoy 45002
(northern Lake Michigan) — Sturgeon Bay depends on it as its
independent water-temp backup; its label still mentions the
Washington Island area because that is simply where the buoy floats.
Side effect (intended): the HOT PIER TODAY badge can no longer go to
Washington Island; it now falls to the best-scoring pier with LIVE
water data among the six covered piers.
"""

# File: fetch-data-v7-remove-washington-island.py
# Delivered: 2026-07-18 (v7 — Washington Island pier removed)

import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------
# 1. Buoy stations — direct sensor readings.
# ---------------------------------------------------------------
STATIONS = {
    "45210": {"label": "Two Rivers / Manitowoc area buoy", "codenames": ["tr1", "mt1"]},
    "SGNW3": {"label": "Sheboygan station"},
    "45002": {"label": "Washington Island area buoy"},
}

NDBC_URL = "https://www.ndbc.noaa.gov/data/realtime2/{station}.txt"

# ---------------------------------------------------------------
# 1c. Airport wind stations — real HOURLY HISTORY, not just current.
#     Great Lakes buoys don't measure wind, so for genuine 72-hour
#     wind trends we use the nearest continuously-reporting airport
#     weather station instead. This is real, timestamped data — not
#     a guess — but it is measured a few miles from the pier, not
#     right at the water, so it's labeled honestly on the page.
# ---------------------------------------------------------------
STATION_HISTORY = {
    "KMTW": {"label": "Manitowoc Airport", "codenames": ["trw", "mtw"]},
    "KSBM": {"label": "Sheboygan County Memorial Airport (nearest continuously-reporting wind station)"},
    "KWNW3": {"label": "Kewaunee MET station (nearest continuously-reporting wind station)", "codenames": ["kww"]},
    "KSUE": {"label": "Door County Cherryland Airport, Sturgeon Bay (nearest continuously-reporting wind station, about 7 miles from the canal pier)"},
    "AGMW3": {"label": "Algoma City Marina, WI (dormant \u2014 NOAA has not transmitted data from this station since approximately 2017; wired here so it activates automatically with no code changes if the station ever comes back online)", "codenames": ["agw"]},
    "0Y2W3": {"label": "Sturgeon Bay CG Station, WI (dormant \u2014 no data currently transmitted; wired here so it activates automatically with no code changes if the station ever comes back online)", "codenames": ["sbcg"]},
    "C58W3": {"label": "Two Rivers CG Station, WI (dormant \u2014 no data currently transmitted; wired here for completeness, though Two Rivers already has solid live coverage via buoy 45210 and KMTW)", "codenames": ["trcg"]},
}

NWS_STATION_OBS_URL = "https://api.weather.gov/stations/{station}/observations"

# ---------------------------------------------------------------
# 1b. Marine forecast zones — official NWS forecasts + alerts.
# ---------------------------------------------------------------
ZONES = {
    "LMZ543": {"label": "Two Rivers to Sheboygan WI", "codenames": ["trz", "mtz"]},
    "LMZ643": {"label": "Sheboygan to Port Washington WI"},
    "LMZ542": {"label": "Sturgeon Bay to Two Rivers WI", "codenames": ["kwz", "algz"]},
}

NWS_ZONE_TEXT_URL = "https://tgftp.nws.noaa.gov/data/forecasts/marine/near_shore/lm/{zone_lower}.txt"
NWS_ALERTS_URL = "https://api.weather.gov/alerts/active?zone={zone}"
NWS_USER_AGENT = "PierBiteDotCom (contact: pierbite project owner)"

# ---------------------------------------------------------------
# 1d. GLSEA satellite water temperature — fallback for piers with
#     no real buoy currently in the water. See the module docstring
#     above for details on the freshness check.
# ---------------------------------------------------------------
GLSEA_POINTS = {
    "manitowoc": {
        "lat": 44.0955,
        "lon": -87.6608,
        "label": "Manitowoc harbor mouth (satellite estimate — GLSEA; no buoy exists here)",
    },
    "sheboygan": {
        "lat": 43.7495,
        "lon": -87.6927,
        "label": "Sheboygan Breakwater Lighthouse, north pier (satellite estimate — GLSEA; buoy 45218 is seasonal and currently out of the water)",
    },
    "kewaunee": {
        "lat": 44.4589,
        "lon": -87.5094,
        "label": "Kewaunee Pierhead (satellite estimate — GLSEA; no buoy exists here)",
    },
    "algoma": {
        "lat": 44.6086,
        "lon": -87.4350,
        "label": "Algoma harbor mouth (satellite estimate — GLSEA; no buoy exists here; GLSEA is currently blocked by an anti-bot wall, so this will report unavailable until that's resolved)",
    },
}

GLSEA_URL_TEMPLATE = (
    "https://apps.glerl.noaa.gov/erddap/griddap/GLSEA_ACSPO_GCS.json"
    "?sst[(last)][({lat}):({lat})][({lon}):({lon})]"
)
GLSEA_USER_AGENT = "PierBiteDotCom (contact: pierbite project owner)"
GLSEA_MAX_AGE_DAYS = 5  # if the newest satellite reading is older than this, treat it as unavailable

# 16-point compass, in order, starting at North.
COMPASS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def degrees_to_compass(deg):
    """Turn a wind direction in degrees (e.g. 270) into a letter code (e.g. 'W')."""
    if deg is None:
        return None
    idx = round(deg / 22.5) % 16
    return COMPASS[idx]


def to_float(value):
    """NOAA uses 'MM' to mean 'no reading'. Turn that into a proper empty value."""
    if value in (None, "MM", ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def fetch_station(station_id):
    """Download and read one buoy's text file from NOAA."""
    url = NDBC_URL.format(station=station_id)
    with urllib.request.urlopen(url, timeout=30) as response:
        raw_text = response.read().decode("utf-8", errors="ignore")

    lines = raw_text.strip().split("\n")
    if len(lines) < 3:
        return []  # station returned nothing useful

    readings = []
    for line in lines[2:]:  # first two lines are headers, skip them
        parts = line.split()
        if len(parts) < 15:
            continue
        try:
            year, month, day, hour, minute = (int(parts[i]) for i in range(5))
            when = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
        except ValueError:
            continue

        readings.append({
            "time": when,
            "wind_dir_deg": to_float(parts[5]),
            "wind_speed_ms": to_float(parts[6]),
            "gust_ms": to_float(parts[7]),
            "wave_height_m": to_float(parts[8]),
            "water_temp_c": to_float(parts[14]),
            # PRES (index 12) and PTDY (index 17) — standard NDBC columns,
            # confirmed against a live station reading before adding this.
            "pressure_hpa": to_float(parts[12]),
            "pressure_tendency_hpa": to_float(parts[17]) if len(parts) > 17 else None,
        })

    readings.reverse()  # oldest first, newest last
    return readings


def closest_to(readings, target_time):
    """Find the reading whose timestamp is nearest to a target time."""
    if not readings:
        return None
    return min(readings, key=lambda r: abs((r["time"] - target_time).total_seconds()))


def summarize_station(station_id, readings):
    if not readings:
        return {"available": False}

    latest = readings[-1]
    ago_24h = closest_to(readings, latest["time"] - timedelta(hours=24))
    ago_72h = closest_to(readings, latest["time"] - timedelta(hours=72))

    def water_f(c):
        return round(c * 9 / 5 + 32, 1) if c is not None else None

    def wind_mph(ms):
        return round(ms * 2.23694, 1) if ms is not None else None

    def waves_ft(m):
        return round(m * 3.28084, 2) if m is not None else None

    current_water_f = water_f(latest["water_temp_c"])
    water_24h_ago_f = water_f(ago_24h["water_temp_c"]) if ago_24h else None
    water_72h_ago_f = water_f(ago_72h["water_temp_c"]) if ago_72h else None

    change_24h = (
        round(current_water_f - water_24h_ago_f, 1)
        if current_water_f is not None and water_24h_ago_f is not None
        else None
    )
    change_72h = (
        round(current_water_f - water_72h_ago_f, 1)
        if current_water_f is not None and water_72h_ago_f is not None
        else None
    )

    return {
        "available": True,
        "observed_at_utc": latest["time"].isoformat(),
        "wind_dir": degrees_to_compass(latest["wind_dir_deg"]),
        "wind_mph": wind_mph(latest["wind_speed_ms"]),
        "gust_mph": wind_mph(latest["gust_ms"]),
        "wave_ft": waves_ft(latest["wave_height_m"]),
        "water_temp_f": current_water_f,
        "water_change_24h_f": change_24h,
        "water_change_72h_f": change_72h,
        # Pressure in hPa (millibars), plus NDBC's own 3-hour tendency
        # value — a falling reading here is the classic "front's coming"
        # signal; a sharp rise right after often means the bite shuts off.
        "pressure_hpa": latest["pressure_hpa"],
        "pressure_tendency_3h_hpa": latest["pressure_tendency_hpa"],
    }


def nws_get(url):
    """Make a request to the NWS API. Requires a User-Agent header."""
    req = urllib.request.Request(url, headers={
        "User-Agent": NWS_USER_AGENT,
        "Accept": "application/geo+json",
    })
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


DIR_WORDS = {
    "north": "N", "northeast": "NE", "east": "E", "southeast": "SE",
    "south": "S", "southwest": "SW", "west": "W", "northwest": "NW",
}


def split_wind_and_wave(text):
    """Marine forecast sentences blend wind and wave info together in one
    block of prose (e.g. 'Northeast winds 10 to 15 kt. Waves 1 to 3 ft.').
    Split at the word 'Waves' so each half can be parsed on its own,
    without wave numbers leaking into the wind range or vice versa."""
    if not text:
        return "", ""
    parts = re.split(r"(?=[Ww]aves?\s)", text, maxsplit=1)
    wind_part = parts[0]
    wave_part = parts[1] if len(parts) > 1 else ""
    return wind_part, wave_part


VALID_ABBR = {"N", "NE", "E", "SE", "S", "SW", "W", "NW"}


def parse_wind_direction(wind_part):
    """Pull the wind direction from real NWS marine text, which sometimes
    uses short form ('SE wind 5 to 10 kts') and sometimes spelled-out
    ('Northeast winds 10 to 15 kt')."""
    m = re.search(r"\b([NSEW]{1,2})\s+winds?\b", wind_part)
    if m and m.group(1) in VALID_ABBR:
        return m.group(1)
    m = re.search(
        r"\b(north|northeast|east|southeast|south|southwest|west|northwest)\s+winds?\b",
        wind_part, re.IGNORECASE,
    )
    if not m:
        return None
    return DIR_WORDS.get(m.group(1).lower())


def parse_wind_speed(wind_part):
    """Turn '10 to 15 kt' into a (low_mph, high_mph) range."""
    if not wind_part:
        return (None, None)
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", wind_part)]
    if not nums:
        return (None, None)
    is_knots = "kt" in wind_part.lower() or "knot" in wind_part.lower()
    factor = 1.15078 if is_knots else 1.0
    nums = [round(n * factor, 1) for n in nums]
    return (min(nums), max(nums))


def parse_wave_height(wave_part):
    """Pull a wave height range in feet out of the wave portion of a
    forecast sentence. Handles 'Waves 1 to 3 ft', 'Waves around 2 ft',
    'Waves 1 foot or less', 'Waves calm to 1 foot'."""
    if not wave_part:
        return (None, None)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*f(?:oo|ee)?t", wave_part)
    if m:
        return (float(m.group(1)), float(m.group(2)))
    m = re.search(r"around\s+(\d+(?:\.\d+)?)\s*f(?:oo|ee)?t", wave_part)
    if m:
        v = float(m.group(1))
        return (v, v)
    m = re.search(r"(\d+(?:\.\d+)?)\s*f(?:oo|ee)?t\s+or\s+less", wave_part)
    if m:
        return (0.0, float(m.group(1)))
    m = re.search(r"calm\s+to\s+(\d+(?:\.\d+)?)\s*f(?:oo|ee)?t", wave_part)
    if m:
        return (0.0, float(m.group(1)))
    return (None, None)


def parse_zone_periods(raw_text):
    """Marine zone bulletins look like:
    .TODAY...NW wind 10 to 15 kts... Waves 2 to 4 ft... .TONIGHT...W wind...
    Split on the '.PERIODNAME...' markers into [(period_name, text), ...]."""
    pattern = r"\.([A-Z][A-Z0-9 /]{2,30}?)\.\.\.(.*?)(?=\.[A-Z][A-Z0-9 /]{2,30}?\.\.\.|\$\$|$)"
    matches = re.findall(pattern, raw_text, re.DOTALL)
    return [(name.strip(), re.sub(r"\s+", " ", text.strip())) for name, text in matches]


def fetch_zone_forecast(zone_id):
    """Get the official NWS marine forecast text bulletin for one shoreline
    zone. Reads the current (first) forecast period as before, and now also
    keeps the next few periods so the page can show whether things are
    trending better or worse over the next day or two — still real NWS
    text, not a guess, just more of it than before."""
    url = NWS_ZONE_TEXT_URL.format(zone_lower=zone_id.lower())
    req = urllib.request.Request(url, headers={"User-Agent": NWS_USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as response:
        raw_text = response.read().decode("utf-8", errors="ignore")

    periods = parse_zone_periods(raw_text)
    if not periods:
        return {"available": False}

    def parse_period(period_name, period_text):
        wind_part, wave_part = split_wind_and_wave(period_text)
        return {
            "period_name": period_name,
            "wind_dir": parse_wind_direction(wind_part),
            "wind_mph_low": parse_wind_speed(wind_part)[0],
            "wind_mph_high": parse_wind_speed(wind_part)[1],
            "wave_ft_low": parse_wave_height(wave_part)[0],
            "wave_ft_high": parse_wave_height(wave_part)[1],
            "detailed_text": period_text,
        }

    current = parse_period(*periods[0])
    upcoming = [parse_period(name, text) for name, text in periods[1:4]]

    return {
        "available": True,
        "period_name": current["period_name"],
        "wind_dir": current["wind_dir"],
        "wind_mph_low": current["wind_mph_low"],
        "wind_mph_high": current["wind_mph_high"],
        "wave_ft_low": current["wave_ft_low"],
        "wave_ft_high": current["wave_ft_high"],
        "detailed_text": current["detailed_text"],
        "upcoming": upcoming,
    }


def fetch_station_history(station_id):
    """Get real, timestamped wind readings from a continuously-reporting
    airport weather station (ASOS). Requests the last ~73 hours in three
    smaller ~24-hour chunks instead of one big request — a single large
    request risks tripping an undocumented size cap on busy stations
    (reporting every ~5 minutes) and can fail outright instead of just
    returning less data. Smaller chunks stay safely within a size that's
    already proven to work, for any station's reporting frequency.

    Still honest about whatever real window it actually receives, rather
    than assuming it always got the full 72 hours.

    It also downsamples to one clean reading per hour (nearest actual
    observation to each hour mark), instead of keeping every 5-minute
    reading, which would otherwise bloat the file with near-duplicates."""
    now = datetime.now(timezone.utc)
    chunk_bounds = [
        (now - timedelta(hours=73), now - timedelta(hours=49)),
        (now - timedelta(hours=49), now - timedelta(hours=25)),
        (now - timedelta(hours=25), now),
    ]

    raw = []
    for chunk_start, chunk_end in chunk_bounds:
        start_param = chunk_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_param = chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ")
        url = (
            NWS_STATION_OBS_URL.format(station=station_id)
            + "?start=" + start_param + "&end=" + end_param + "&limit=500"
        )
        try:
            data = nws_get(url)
        except Exception:
            continue  # this chunk failed — keep whatever the other chunks gave us
        features = data.get("features", [])

        for feat in features:
            props = feat.get("properties", {})
            ws = (props.get("windSpeed") or {}).get("value")
            wd = (props.get("windDirection") or {}).get("value")
            ts = props.get("timestamp")
            if ws is None or wd is None or ts is None:
                continue
            try:
                when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
            raw.append({
                "time": when,
                "wind_mph": round(ws * 0.621371, 1),  # station reports km/h
                "wind_dir": degrees_to_compass(wd),
            })

    if not raw:
        return {"available": False}

    raw.sort(key=lambda r: r["time"])
    latest = raw[-1]
    earliest = raw[0]
    actual_hours_covered = round((latest["time"] - earliest["time"]).total_seconds() / 3600)

    # Downsample: for each whole hour back from now, keep the single
    # real reading closest to that hour mark (skip hours with no data).
    hourly = []
    max_hours = min(actual_hours_covered, 72)
    for h in range(max_hours, -1, -1):
        target = latest["time"] - timedelta(hours=h)
        closest = min(raw, key=lambda r: abs((r["time"] - target).total_seconds()))
        if abs((closest["time"] - target).total_seconds()) <= 1800:  # within 30 min
            hourly.append({"hours_ago": h, "dir": closest["wind_dir"], "mph": closest["wind_mph"]})

    return {
        "available": True,
        "observed_at_utc": latest["time"].isoformat(),
        "current_wind_dir": latest["wind_dir"],
        "current_wind_mph": latest["wind_mph"],
        "actual_hours_covered": actual_hours_covered,
        "hourly": hourly,
    }


def fetch_zone_alerts(zone_id):
    """Check for any real, currently-active marine advisory in this zone."""
    url = NWS_ALERTS_URL.format(zone=zone_id)
    data = nws_get(url)
    features = data.get("features", [])
    if not features:
        return {"active": False}

    alert = features[0]["properties"]
    return {
        "active": True,
        "headline": alert.get("headline"),
        "event": alert.get("event"),
        "severity": alert.get("severity"),
        "effective_utc": alert.get("effective"),
        "expires_utc": alert.get("expires"),
    }


def fetch_glsea_point(lat, lon):
    """Ask NOAA's GLSEA satellite dataset for the most recent surface
    water temperature at one specific point on the lake (about a
    1.5 km grid square). This is a real satellite reading, not a
    guess — but the feed has been observed to sometimes lag by
    weeks. So every reading's age is checked here before it's ever
    handed back. If it's older than GLSEA_MAX_AGE_DAYS, this
    function returns available: False instead of a stale number,
    the same honest pattern used elsewhere in this file for missing
    marine zones."""
    url = GLSEA_URL_TEMPLATE.format(lat=lat, lon=lon)
    req = urllib.request.Request(url, headers={"User-Agent": GLSEA_USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))

    rows = data.get("table", {}).get("rows", [])
    if not rows:
        return {"available": False, "reason": "no data returned"}

    time_str, row_lat, row_lon, sst_c = rows[0]
    if sst_c is None:
        return {"available": False, "reason": "no reading at this point (likely cloud cover)"}

    observed = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
    age_days = (datetime.now(timezone.utc) - observed).total_seconds() / 86400

    if age_days > GLSEA_MAX_AGE_DAYS:
        return {
            "available": False,
            "reason": f"most recent satellite reading is {age_days:.1f} days old (limit is {GLSEA_MAX_AGE_DAYS})",
            "observed_at_utc": observed.isoformat(),
        }

    return {
        "available": True,
        "observed_at_utc": observed.isoformat(),
        "water_temp_f": round(sst_c * 9 / 5 + 32, 1),
        "age_days": round(age_days, 1),
        "grid_point_used": {"lat": row_lat, "lon": row_lon},
    }


# ---------------------------------------------------------------
# 2. SCORING ENGINE — new in v5. "The backend thinks, the
#    frontend displays."
#
#    Everything above this line is unchanged from v4. Everything
#    below computes each pier's finished 0-100 Bite Index score,
#    band, factor breakdown, and honesty labels, and publishes
#    them in a new "piers" section of data.json. The pages on the
#    site can then simply display these numbers instead of each
#    re-computing the score themselves (which is how a scoring bug
#    once had to be fixed in many separate files).
#
#    The math here is ported line-for-line from the proven Two
#    Rivers page implementation, with two deliberate fixes:
#
#    FIX 1 (the "stretch bug"): a pier with no water temperature
#    from ANY source used to quietly re-weight its remaining
#    factors up to 100%, letting a data-incomplete pier outscore a
#    complete one. Now: if no water temp exists at all, the score
#    is capped at 55 and the pier is marked "incomplete".
#
#    FIX 2: the warm-water hard caps (which push the score down
#    when the water is too warm for salmon/trout) now apply
#    whenever ANY water temperature exists — live, satellite, or
#    estimated — not only live buoy readings.
# ---------------------------------------------------------------

SCHEMA_VERSION = 1
# If data.json is older than this many hours, pages should treat
# it as stale instead of presenting old numbers as LIVE.
STALE_AFTER_HOURS = 3

# One entry per pier. Adding a future pier = adding one entry here.
#   buoy            key in output["stations"] for this pier's own buoy (or None)
#   satellite       key in output["satellite_water_temp"] for its own satellite point (or None)
#   water_fallbacks ordered borrow-chain if own sources are dark:
#                   ("station"|"satellite", key, "Name shown to the user")
#   wind_history    ordered list of output["station_history"] keys:
#                   (key, None) = the pier's own station,
#                   (key, "Name") = borrowed from a neighbor, labeled ESTIMATED
#   zone            key in output["zones"] for forecast + alerts
PIERS = {
    "two_rivers": {
        "name": "Two Rivers / Neshotah",
        "buoy": "tr1",
        "satellite": None,
        "water_fallbacks": [("station", "mt1", "Manitowoc"), ("station", "kw1", "Kewaunee")],
        "wind_history": [("trw", None)],
        "zone": "trz",
    },
    "manitowoc": {
        "name": "Manitowoc",
        "buoy": "mt1",
        "satellite": "manitowoc",
        "water_fallbacks": [],
        "wind_history": [("mtw", None)],
        "zone": "mtz",
    },
    "sheboygan": {
        "name": "Sheboygan",
        "buoy": "SGNW3",
        "satellite": "sheboygan",
        "water_fallbacks": [("station", "mt1", "Manitowoc"), ("station", "tr1", "Two Rivers")],
        "wind_history": [("KSBM", None)],
        "zone": "LMZ643",
    },
    "kewaunee": {
        "name": "Kewaunee",
        "buoy": None,
        "satellite": "kewaunee",
        "water_fallbacks": [("station", "tr1", "Two Rivers"), ("station", "mt1", "Manitowoc")],
        "wind_history": [("kww", None)],
        "zone": "kwz",
    },
    "algoma": {
        "name": "Algoma",
        "buoy": None,
        "satellite": "algoma",
        # Deliberate design decision (matches the live Algoma page):
        # every borrowed water reading is labeled "Kewaunee" —
        # Algoma borrows whatever Kewaunee itself would show.
        "water_fallbacks": [
            ("satellite", "kewaunee", "Kewaunee"),
            ("station", "tr1", "Kewaunee"),
            ("station", "mt1", "Kewaunee"),
        ],
        "wind_history": [("agw", None), ("kww", "Kewaunee")],
        "zone": "algz",
    },
    "sturgeon_bay": {
        # CONFIRMED 2026-07-18 (build session decisions, made with
        # the owner):
        # - Zone: LMZ542 "Sturgeon Bay to Two Rivers" (via algz).
        #   The canal pier sits exactly on the LMZ541/LMZ542
        #   boundary; 542 covers the water at and south of the
        #   canal where the pier fishing happens, and matches
        #   Algoma next door.
        # - Wind: KSUE (Door County Cherryland Airport, ~7 mi from
        #   the pier) treated as LIVE local wind — the exact same
        #   standard as KMTW for Two Rivers/Manitowoc and KSBM for
        #   Sheboygan. The dormant CG station at the canal itself
        #   (sbcg / 0Y2W3) stays FIRST in the chain so it takes
        #   over automatically if NOAA ever revives it.
        # - Water: the old chain listed tr1 then mt1, but those are
        #   the SAME physical buoy (45210), so the second fallback
        #   was redundant. Replaced with buoy 45002 (northern Lake
        #   Michigan) — a genuinely independent backup, honestly
        #   labeled.
        "name": "Sturgeon Bay",
        "buoy": None,
        "satellite": None,
        "water_fallbacks": [
            ("station", "tr1", "Two Rivers"),
            ("station", "45002", "Northern Lake Michigan"),
        ],
        "wind_history": [("sbcg", None), ("KSUE", None)],
        "zone": "algz",
    },
}

# Compass direction -> degrees, built from the COMPASS list above.
_COMPASS_DEG = {name: idx * 22.5 for idx, name in enumerate(COMPASS)}


def clamp(value, low, high):
    """Keep a number inside a range."""
    return max(low, min(high, value))


def westerly_component(dir_code):
    """How 'westerly' a wind direction is: W = +1 (good, offshore
    for Wisconsin's west-shore piers), E = -1 (bad, onshore).
    Unknown/missing directions count as 0 (neutral), exactly like
    the page implementation this was ported from."""
    import math
    deg = _COMPASS_DEG.get(dir_code)
    if deg is None:
        return 0.0
    return math.cos((deg - 270.0) * math.pi / 180.0)


def score_wind(history, zone_forecast, borrowed_from):
    """0-100 wind factor. Prefers real hourly history (LIVE, or
    ESTIMATED when the history belongs to a neighbor); falls back
    to the zone forecast direction (FORECAST). Ported exactly from
    the Two Rivers page, including the 'recent onshore shift'
    penalty."""
    if history and history.get("available") and history.get("hourly"):
        hourly = history["hourly"]
        comps = [westerly_component(h.get("dir")) for h in hourly]
        recent = [westerly_component(h.get("dir")) for h in hourly if h.get("hours_ago", 99) <= 12]
        j = sum(comps) / len(comps) if comps else 0.0
        z = sum(recent) / len(recent) if recent else j
        score = round(clamp(50 + 38 * j, 5, 90))
        if j > 0.25 and z < -0.1:
            score = round(clamp(score - 22, 5, 95))
        if borrowed_from:
            return {"score": score, "source": "ESTIMATED", "source_name": borrowed_from}
        return {"score": score, "source": "LIVE", "source_name": None}
    if zone_forecast and zone_forecast.get("available") and zone_forecast.get("wind_dir"):
        score = round(clamp(50 + 40 * westerly_component(zone_forecast["wind_dir"]), 5, 95))
        return {"score": score, "source": "FORECAST", "source_name": None}
    return None


def score_water(temp_f, change_72h_f):
    """0-100 water-temperature factor, ported exactly from the Two
    Rivers page: an ideal band around 50-56F, penalties as it
    warms, plus a bonus/penalty for the 72-hour trend (a dropping
    temp often signals an upwelling, which turns the bite on)."""
    if 50 <= temp_f <= 56:
        base = 72
    elif temp_f < 50:
        base = 72 - 2.2 * (50 - temp_f)
    elif temp_f <= 62:
        base = 72 - 4 * (temp_f - 56)
    else:
        base = 48 - 7 * (temp_f - 62)
    base = clamp(base, 3, 82)
    trend = clamp(2.4 * -change_72h_f, -20, 12) if change_72h_f is not None else 0
    return round(clamp(base + trend, 5, 98))


def score_waves(wave_ft, alert_active):
    """0-100 lake-conditions factor from wave height; an active
    marine advisory hard-caps it."""
    if wave_ft <= 1.5:
        score = 90
    elif wave_ft <= 3:
        score = 72
    elif wave_ft <= 5:
        score = 38
    else:
        score = 14
    if alert_active:
        score = min(score, 24)
    return round(score)


def resolve_water(pier_cfg, output):
    """Walk one pier's water-temperature source chain, most-honest
    source first: own live buoy -> own satellite point -> borrowed
    neighbor readings. Returns None if every source is dark."""
    stations = output.get("stations", {})
    sats = output.get("satellite_water_temp", {})

    buoy_key = pier_cfg.get("buoy")
    if buoy_key:
        own = stations.get(buoy_key, {})
        if own.get("available") and isinstance(own.get("water_temp_f"), (int, float)):
            return {
                "temp_f": own["water_temp_f"],
                "source": "LIVE",
                "source_name": None,
                "change_24h_f": own.get("water_change_24h_f"),
                "change_72h_f": own.get("water_change_72h_f"),
            }

    sat_key = pier_cfg.get("satellite")
    if sat_key:
        sat = sats.get(sat_key, {})
        if sat.get("available") and isinstance(sat.get("water_temp_f"), (int, float)):
            return {
                "temp_f": sat["water_temp_f"],
                "source": "SATELLITE",
                "source_name": None,
                "change_24h_f": None,
                "change_72h_f": None,
            }

    for kind, key, name in pier_cfg.get("water_fallbacks", []):
        pool = stations if kind == "station" else sats
        src = pool.get(key, {})
        if src.get("available") and isinstance(src.get("water_temp_f"), (int, float)):
            return {
                "temp_f": src["water_temp_f"],
                "source": "ESTIMATED",
                "source_name": name,
                "change_24h_f": None,
                "change_72h_f": None,
            }
    return None


def band_for(score):
    """Score band label + the site color token it maps to."""
    if score is None:
        return {"label": "Not enough data", "tone": "muted"}
    if score >= 85:
        return {"label": "Strong Setup", "tone": "good"}
    if score >= 70:
        return {"label": "Good", "tone": "good"}
    if score >= 50:
        return {"label": "Fair", "tone": "gold"}
    if score >= 30:
        return {"label": "Slow", "tone": "warn"}
    return {"label": "Poor", "tone": "bad"}


def build_piers(output):
    """Compute the finished, ready-to-display block for every pier
    from the raw sections already collected above. Makes no extra
    network requests."""
    piers_out = {}
    for pier_id, cfg in PIERS.items():
        stations = output.get("stations", {})
        zones = output.get("zones", {})
        histories = output.get("station_history", {})

        zone = zones.get(cfg["zone"], {})
        forecast = zone.get("forecast", {"available": False})
        alert = zone.get("alert", {"active": False})
        alert_active = bool(alert.get("active"))

        # --- Wind factor: first history source in the chain that
        # has real data wins; otherwise fall back to the forecast.
        wind_factor = None
        for hist_key, borrowed_from in cfg.get("wind_history", []):
            hist = histories.get(hist_key)
            if hist and hist.get("available") and hist.get("hourly"):
                wind_factor = score_wind(hist, None, borrowed_from)
                wind_headline = {
                    "dir": hist.get("current_wind_dir"),
                    "mph": hist.get("current_wind_mph"),
                    "mph_low": None,
                    "mph_high": None,
                    "source": wind_factor["source"],
                    "source_name": wind_factor.get("source_name"),
                }
                break
        else:
            wind_factor = score_wind(None, forecast, None)
            if wind_factor:
                wind_headline = {
                    "dir": forecast.get("wind_dir"),
                    "mph": None,
                    "mph_low": forecast.get("wind_mph_low"),
                    "mph_high": forecast.get("wind_mph_high"),
                    "source": "FORECAST",
                    "source_name": None,
                }
            else:
                wind_headline = {"dir": None, "mph": None, "mph_low": None,
                                 "mph_high": None, "source": None, "source_name": None}

        # --- Water factor (FIX 1 + FIX 2 live here).
        water = resolve_water(cfg, output)
        if water is not None:
            water_score = score_water(water["temp_f"], water["change_72h_f"])
        else:
            water_score = None

        # --- Waves factor: own buoy reading first, else forecast range.
        wave_ft = None
        wave_source = None
        buoy = stations.get(cfg["buoy"], {}) if cfg.get("buoy") else {}
        if buoy.get("available") and isinstance(buoy.get("wave_ft"), (int, float)):
            wave_ft = buoy["wave_ft"]
            wave_source = "LIVE"
        elif (forecast.get("available")
              and forecast.get("wave_ft_low") is not None
              and forecast.get("wave_ft_high") is not None):
            wave_ft = (forecast["wave_ft_low"] + forecast["wave_ft_high"]) / 2
            wave_source = "FORECAST"

        # --- Assemble the four factors (weights match the pages:
        # wind 30, water 30, lake conditions 20, clarity 20).
        factors = []
        if wind_factor:
            factors.append({
                "label": "Wind / Upwelling", "score": wind_factor["score"], "weight": 30,
                "source": wind_factor["source"], "source_name": wind_factor.get("source_name"),
            })
        else:
            factors.append({"label": "Wind / Upwelling", "score": None, "weight": 30,
                            "source": "MISSING", "source_name": None})
        if water_score is not None:
            factors.append({
                "label": "Water Temperature", "score": water_score, "weight": 30,
                "source": water["source"], "source_name": water["source_name"],
            })
        else:
            factors.append({"label": "Water Temperature", "score": None, "weight": 30,
                            "source": "MISSING", "source_name": None})
        if wave_ft is not None:
            factors.append({
                "label": "Lake Conditions", "score": score_waves(wave_ft, alert_active),
                "weight": 20, "source": wave_source, "source_name": None,
            })
        else:
            factors.append({"label": "Lake Conditions", "score": None, "weight": 20,
                            "source": "MISSING", "source_name": None})
        factors.append({"label": "Clarity / Storm", "score": None, "weight": 20,
                        "source": "NOT_SCORED", "source_name": None,
                        "note": "no clarity source yet"})

        # --- Weighted total over the factors that actually scored.
        scored = [f for f in factors if f["score"] is not None]
        total_weight = sum(f["weight"] for f in scored)
        score = (round(sum(f["score"] * (f["weight"] / total_weight) for f in scored))
                 if total_weight > 0 else None)

        incomplete = False
        if score is not None and water is not None:
            # FIX 2: warm-water hard caps apply to ANY temp source.
            t = water["temp_f"]
            if t >= 74:
                score = min(score, 10)
            elif t >= 72:
                score = min(score, 20)
            elif t >= 70:
                score = min(score, 28)
            elif t >= 68:
                score = min(score, 44)
        if score is not None and water is None:
            # FIX 1: no water temp from any source -> capped and
            # visibly marked incomplete, never quietly stretched.
            score = min(score, 55)
            incomplete = True

        estimated_labels = [f["label"] for f in scored if f["source"] == "ESTIMATED"]

        piers_out[pier_id] = {
            "name": cfg["name"],
            "score": score,
            "band": band_for(score),
            "incomplete": incomplete,
            "verified_count": len(scored) - len(estimated_labels),
            "factor_total": 4,
            "estimated_factors": estimated_labels,
            "factors": factors,
            "alert_active": alert_active,
            "headline": {
                "water_temp_f": water["temp_f"] if water else None,
                "water_temp_source": water["source"] if water else None,
                "water_temp_from": water["source_name"] if water else None,
                "water_change_24h_f": water["change_24h_f"] if water else None,
                "water_change_72h_f": water["change_72h_f"] if water else None,
                "wind": wind_headline,
                "wave_ft": round(wave_ft, 1) if wave_ft is not None else None,
                "wave_source": wave_source,
                "pressure_hpa": buoy.get("pressure_hpa") if buoy.get("available") else None,
                "pressure_tendency_3h_hpa": (buoy.get("pressure_tendency_3h_hpa")
                                             if buoy.get("available") else None),
            },
        }
    return piers_out


def compute_hot_piers(piers):
    """The HOT PIER TODAY badge, computed once here so the home
    page and pier pages can never disagree. Rule (decided
    2026-07-16): only piers with LIVE water-temp data can win;
    genuine ties all get the badge; if no pier has live water data
    today, nobody gets it."""
    live = {pid: p for pid, p in piers.items()
            if p["headline"]["water_temp_source"] == "LIVE" and p["score"] is not None}
    if not live:
        return []
    top = max(p["score"] for p in live.values())
    return sorted(pid for pid, p in live.items() if p["score"] == top)



def main():
    output = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stations": {},
        "zones": {},
        "station_history": {},
        "satellite_water_temp": {},
    }

    for station_id, meta in STATIONS.items():
        try:
            readings = fetch_station(station_id)
            summary = summarize_station(station_id, readings)
        except Exception as err:
            summary = {"available": False, "error": str(err)}
        summary["label"] = meta["label"]
        # A single physical station can feed more than one pier (e.g. a
        # shared buoy) — write the same reading under every codename that
        # points to it, without fetching it twice.
        for codename in meta.get("codenames", [meta.get("codename", station_id)]):
            output["stations"][codename] = summary

    for station_id, meta in STATION_HISTORY.items():
        try:
            history = fetch_station_history(station_id)
        except Exception as err:
            history = {"available": False, "error": str(err)}
        history["label"] = meta["label"]
        for codename in meta.get("codenames", [meta.get("codename", station_id)]):
            output["station_history"][codename] = history

    for zone_id, meta in ZONES.items():
        zone_result = {"label": meta["label"]}
        try:
            zone_result["forecast"] = fetch_zone_forecast(zone_id)
        except Exception as err:
            zone_result["forecast"] = {"available": False, "error": str(err)}
        try:
            zone_result["alert"] = fetch_zone_alerts(zone_id)
        except Exception as err:
            zone_result["alert"] = {"active": False, "error": str(err)}
        for codename in meta.get("codenames", [meta.get("codename", zone_id)]):
            output["zones"][codename] = zone_result

    for point_id, meta in GLSEA_POINTS.items():
        try:
            result = fetch_glsea_point(meta["lat"], meta["lon"])
        except Exception as err:
            result = {"available": False, "error": str(err)}
        result["label"] = meta["label"]
        output["satellite_water_temp"][point_id] = result

    # --- New in v5: finished per-pier scores + data-contract fields.
    # Added AFTER all raw sections so it works purely from data
    # already collected above (no extra network requests).
    output["schema_version"] = SCHEMA_VERSION
    output["stale_after_hours"] = STALE_AFTER_HOURS
    output["piers"] = build_piers(output)
    output["hot_piers_today"] = compute_hot_piers(output["piers"])

    with open("data.json", "w") as f:
        json.dump(output, f, indent=2)

    print("Wrote data.json:")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
