"""
PierBite.com — Live Data Fetcher
Fetches current buoy, marine-zone forecast, and satellite water
temperature data from public NOAA/NWS sources and writes the
combined result to data.json. No API key or paid account required.
"""

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
    "K2P2": {"label": "Washington Island Airport (automated wind station)"},
    "KSBM": {"label": "Sheboygan County Memorial Airport (nearest continuously-reporting wind station)"},
    "KWNW3": {"label": "Kewaunee MET station (nearest continuously-reporting wind station)", "codenames": ["kww"]},
}

NWS_STATION_OBS_URL = "https://api.weather.gov/stations/{station}/observations"

# ---------------------------------------------------------------
# 1b. Marine forecast zones — official NWS forecasts + alerts.
# ---------------------------------------------------------------
ZONES = {
    "LMZ543": {"label": "Two Rivers to Sheboygan WI", "codenames": ["trz", "mtz"]},
    "LMZ541": {"label": "Rock Island Passage to Sturgeon Bay WI"},
    "LMZ643": {"label": "Sheboygan to Port Washington WI"},
    "LMZ565": {"label": "Sturgeon Bay to Two Rivers WI", "codenames": ["kwz"]},
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
}

GLSEA_URL_TEMPLATE = (
    "https://apps.glerl.noaa.gov/erddap/griddap/GLSEA_ACSPO_GCS.json"
    "?sst[(last)][({lat}):({lat})][({lon}):({lon})]"
)
GLSEA_USER_AGENT = "PierBiteDotCom (contact: pierbite project owner)"
GLSEA_MAX_AGE_DAYS = 5  # if the newest satellite reading is older than this, treat it as unavailable

# 16-point compass, in order, starting at North.
COMPASS = [
