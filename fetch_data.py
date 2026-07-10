"""
PierBite.com — Live Data Fetcher
==================================================================
What this file does:
  Every time it runs, it downloads free public data from three
  different NOAA/NWS sources and saves the results into a file
  called data.json in this same repository:

  1. NDBC BUOYS — direct real-time sensor readings, but only exist
     at a handful of physical locations on the lake.

  2. NWS MARINE ZONE FORECASTS + ALERTS — official government
     forecasts and safety advisories that exist for EVERY stretch
     of shoreline, whether or not a buoy is nearby. This is real,
     named, dated forecast data — never a guess.

  3. GLSEA SATELLITE WATER TEMPERATURE — a NOAA satellite-based
     picture of the lake surface, used ONLY as a fallback for
     piers that have no real buoy nearby (Manitowoc, and now
     Sheboygan — see below). This feed has been observed to
     sometimes lag by weeks, so every reading is checked for
     freshness before it's used — see GLSEA_MAX_AGE_DAYS below.
     A stale reading is never shown as if it were current.

  No password, API key, or paid account is required for any of
  these sources. All are published openly by the U.S. government.

Stations currently wired up (direct buoy readings):
  45210  — Two Rivers area buoy   (water temp, wave height, pressure)
  SGNW3  — Sheboygan station      (wind + pressure only — this is a
                                    C-MAN structure-mounted station,
                                    not a buoy, and does not carry a
                                    water temp or wave sensor)
  KWNW3  — Kewaunee station       (wind only — same reason as above)
  45002  — Washington Island area (wind, wave height, water temp)

  As of this update, every station also reports current barometric
  pressure and its 3-hour trend, where the station provides it —
  same honest "available: false if missing" pattern as everything
  else here. A falling 3-hour pressure trend is a classic sign a
  front is approaching; a sharp rise right after one often means
  the bite is about to shut off.

Marine zones currently wired up (official forecasts + alerts):
  LMZ543 — "Two Rivers to Sheboygan WI" — covers the Two Rivers pier
  LMZ541 — "Rock Island Passage to Sturgeon Bay WI" — covers the
           Washington Island pier
  LMZ643 — "Sheboygan to Port Washington WI" — NEW this version,
           covers the Sheboygan pier (the pier sits at the northern
           edge of this zone, right where it meets LMZ543)

GLSEA satellite water-temp points currently wired up:
  manitowoc  — Manitowoc harbor mouth. Manitowoc has no NDBC buoy at
               all, so this is its only real water-temperature source.
  sheboygan  — NEW this version. Point sits at the Sheboygan
               Breakwater Lighthouse (end of the north pier, over
               open water) rather than any shoreline address, so the
               satellite grid cell actually lands on water. Used
               because Sheboygan's own spotter buoy (NDBC 45218) is
               seasonal and was confirmed "recovered for season" —
               out of the water — as of this update. If that buoy
               is redeployed later in the season, it can be added
               back to STATIONS and this fallback stays as a safety
               net for whenever it's pulled again.

Airport wind-history stations currently wired up (real HOURLY
history, not just a current reading — see fetch_station_history):
  KMTW — Manitowoc Airport (serves the Two Rivers pier)
  K2P2 — Washington Island Airport
  KSBM — Sheboygan County Memorial Airport — NEW this version,
         serves the Sheboygan pier's 72-hour wind trend panel.

This script only uses Python's built-in tools — nothing extra needs
to be installed for it to run.
==================================================================
"""

import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------
# 1. Buoy stations — direct sensor readings.
# ---------------------------------------------------------------
STATIONS = {
    "45210": {"label": "Two Rivers area buoy (Rawley Point East)"},
    "SGNW3": {"label": "Sheboygan station"},
    "KWNW3": {"label": "Kewaunee station"},
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
    "KMTW": {"label": "Manitowoc Airport (nearest continuously-reporting wind station)"},
    "K2P2": {"label": "Washington Island Airport (automated wind station)"},
    "KSBM": {"label": "Sheboygan County Memorial Airport (nearest continuously-reporting wind station)"},
}

NWS_STATION_OBS_URL = "https://api.weather.gov/stations/{station}/observations"

# ---------------------------------------------------------------
# 1b. Marine forecast zones — official NWS forecasts + alerts.
# ---------------------------------------------------------------
ZONES = {
    "LMZ543": {"label": "Two Rivers to Sheboygan WI"},
    "LMZ541": {"label": "Rock Island Passage to Sturgeon Bay WI"},
    "LMZ643": {"label": "Sheboygan to Port Washington WI"},
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
        output["stations"][station_id] = summary

    for station_id, meta in STATION_HISTORY.items():
        try:
            history = fetch_station_history(station_id)
        except Exception as err:
            history = {"available": False, "error": str(err)}
        history["label"] = meta["label"]
        output["station_history"][station_id] = history

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
        output["zones"][zone_id] = zone_result

    for point_id, meta in GLSEA_POINTS.items():
        try:
            result = fetch_glsea_point(meta["lat"], meta["lon"])
        except Exception as err:
            result = {"available": False, "error": str(err)}
        result["label"] = meta["label"]
        output["satellite_water_temp"][point_id] = result

    with open("data.json", "w") as f:
        json.dump(output, f, indent=2)

    print("Wrote data.json:")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
