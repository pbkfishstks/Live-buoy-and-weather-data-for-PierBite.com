"""
PierBite.com — Live Data Fetcher
==================================================================
What this file does:
  Every time it runs, it downloads free public data from two
  different NOAA/NWS sources and saves the results into a file
  called data.json in this same repository:

  1. NDBC BUOYS — direct real-time sensor readings, but only exist
     at a handful of physical locations on the lake.

  2. NWS MARINE ZONE FORECASTS + ALERTS — official government
     forecasts and safety advisories that exist for EVERY stretch
     of shoreline, whether or not a buoy is nearby. This is real,
     named, dated forecast data — never a guess.

  No password, API key, or paid account is required for either
  source. Both are published openly by the U.S. government.

Stations currently wired up (direct buoy readings):
  45210  — Two Rivers area buoy   (water temp, wave height)
  SGNW3  — Sheboygan station      (wind)
  KWNW3  — Kewaunee station       (wind)
  45002  — Washington Island area (wind, wave height, water temp)

Marine zones currently wired up (official forecasts + alerts):
  LMZ543 — "Two Rivers to Sheboygan WI" — covers the Two Rivers pier

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
# 1b. Marine forecast zones — official NWS forecasts + alerts.
# ---------------------------------------------------------------
ZONES = {
    "LMZ543": {"label": "Two Rivers to Sheboygan WI"},
}

NWS_ZONE_TEXT_URL = "https://tgftp.nws.noaa.gov/data/forecasts/marine/near_shore/lm/{zone_lower}.txt"
NWS_ALERTS_URL = "https://api.weather.gov/alerts/active?zone={zone}"
NWS_USER_AGENT = "PierBiteDotCom (contact: pierbite project owner)"

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
    zone, and read the current (first) forecast period from it."""
    url = NWS_ZONE_TEXT_URL.format(zone_lower=zone_id.lower())
    req = urllib.request.Request(url, headers={"User-Agent": NWS_USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as response:
        raw_text = response.read().decode("utf-8", errors="ignore")

    periods = parse_zone_periods(raw_text)
    if not periods:
        return {"available": False}

    period_name, period_text = periods[0]
    wind_part, wave_part = split_wind_and_wave(period_text)

    return {
        "available": True,
        "period_name": period_name,
        "wind_dir": parse_wind_direction(wind_part),
        "wind_mph_low": parse_wind_speed(wind_part)[0],
        "wind_mph_high": parse_wind_speed(wind_part)[1],
        "wave_ft_low": parse_wave_height(wave_part)[0],
        "wave_ft_high": parse_wave_height(wave_part)[1],
        "detailed_text": period_text,
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


def main():
    output = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stations": {},
        "zones": {},
    }

    for station_id, meta in STATIONS.items():
        try:
            readings = fetch_station(station_id)
            summary = summarize_station(station_id, readings)
        except Exception as err:
            summary = {"available": False, "error": str(err)}
        summary["label"] = meta["label"]
        output["stations"][station_id] = summary

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

    with open("data.json", "w") as f:
        json.dump(output, f, indent=2)

    print("Wrote data.json:")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
