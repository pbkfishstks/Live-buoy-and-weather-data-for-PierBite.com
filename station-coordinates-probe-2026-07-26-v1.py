"""
PierBite.com - STATION COORDINATES PROBE - 2026-07-26 - v1
==========================================================

WHAT THIS IS
------------
A read-only diagnostic. It does not touch the website, does not write
data.json, and cannot change anything. It looks up the official
published latitude / longitude / depth for every weather and buoy
station PierBite currently uses, then computes the real distance from
each pier to each station it actually reads.

WHY IT EXISTS
-------------
Phase 1.2 of the backend rebuild requires real lat/lon/depth/distance
for every station in the config. Project rule: "A descriptive string
in config is not evidence." Buoy 45210 was labelled "Two Rivers /
Manitowoc area buoy" for months while actually sitting 26.6 miles
offshore in 475 ft of water. Hand-writing coordinates from memory is
how that happened. This probe fetches them from NOAA instead.

Claude's sandbox is firewalled from NOAA (403 on api.weather.gov and
ndbc.noaa.gov), so this must run inside GitHub Actions - the same
environment production code runs in. That is project decision D61 /
constraint C14.

MECHANISM FACTS LEARNED / RELIED ON (keep these with the code)
--------------------------------------------------------------
1. Two independent NOAA sources publish station positions, and they
   are CROSS-CHECKED here rather than trusted individually:
     a) NWS API   https://api.weather.gov/stations/{id}
        Returns GeoJSON. Coordinates arrive as [LON, LAT] - longitude
        FIRST. Reversing them silently puts Wisconsin in the Indian
        Ocean, so the order is asserted, not assumed.
     b) NDBC table https://www.ndbc.noaa.gov/data/stations/station_table.txt
        Pipe-delimited text, one row per station. The LOCATION column
        holds a string like "44.055 N 87.050 W (...)". South and West
        must be converted to NEGATIVE degrees.
2. NOAA endpoints reject requests with no User-Agent. Every request
   here sends one. (This is why a bare urlopen 403s.)
3. Buoy water depth is NOT in the station table. It appears only in
   the HTML of the station page, as "Water depth: 145 m". Parsed
   best-effort; a miss is reported, never silently dropped.
4. Diagnostic code never discards an error message (constraint C15).
   Every failure prints the full server response and the exact URL
   that was tried.

WHAT TO DO WITH THE OUTPUT
--------------------------
Scroll to the block marked MACHINE-READABLE RESULT at the very bottom
and send that whole block back to Claude. Those numbers get frozen
into fetch_data.py. Nothing else in the output needs to be read.
"""

import json
import re
import ssl
import urllib.request
import urllib.error
from math import radians, sin, cos, asin, sqrt

USER_AGENT = "PierBiteDotCom station-coordinates-probe (contact: pierbite project owner)"

NWS_STATION_URL = "https://api.weather.gov/stations/{sid}"
NDBC_TABLE_URL = "https://www.ndbc.noaa.gov/data/stations/station_table.txt"
NDBC_PAGE_URL = "https://www.ndbc.noaa.gov/station_page.php?station={sid}"

# ---------------------------------------------------------------
# The six pier positions. VERIFIED by Paul against a map on
# 2026-07-25 (project decision D63). Algoma is the City Marina by
# design - there is no separate pier landmark there.
# ---------------------------------------------------------------
PIERS = {
    "sheboygan":    {"name": "Sheboygan",    "lat": 43.748595, "lon": -87.694910},
    "manitowoc":    {"name": "Manitowoc",    "lat": 44.091354, "lon": -87.643820},
    "two_rivers":   {"name": "Two Rivers",   "lat": 44.147061, "lon": -87.565680},
    "kewaunee":     {"name": "Kewaunee",     "lat": 44.457285, "lon": -87.493085},
    "algoma":       {"name": "Algoma",       "lat": 44.608423, "lon": -87.433597},
    "sturgeon_bay": {"name": "Sturgeon Bay", "lat": 44.792050, "lon": -87.309627},
}

# ---------------------------------------------------------------
# Every station ID that appears in the live fetch_data.py config,
# read directly from the deployed file - not from memory.
#   kind "water" = feeds water temperature
#   kind "wind"  = feeds the 72-hour wind history
# ---------------------------------------------------------------
STATIONS_TO_LOOK_UP = [
    ("45210", "water", "buoy - currently labelled 'Two Rivers / Manitowoc area buoy', believed to be Rawley Point East"),
    ("45002", "water", "buoy - currently labelled 'Washington Island area buoy', Sturgeon Bay's independent backup"),
    ("SGNW3", "water", "Sheboygan station - reports wind and air, water-temp field currently empty"),
    ("KMTW",  "wind",  "Manitowoc Airport - shared by Two Rivers AND Manitowoc"),
    ("KSBM",  "wind",  "Sheboygan County Memorial Airport"),
    ("KWNW3", "wind",  "Kewaunee MET station - also borrowed by Algoma"),
    ("KSUE",  "wind",  "Door County Cherryland Airport, Sturgeon Bay"),
    ("AGMW3", "wind",  "Algoma City Marina - DORMANT since approx 2017"),
    ("0Y2W3", "wind",  "Sturgeon Bay CG Station - DORMANT"),
    ("C58W3", "wind",  "Two Rivers CG Station - DORMANT"),
]

# Which stations each pier actually reads today, so distances are
# computed for the pairs that appear on the live site.
PIER_STATION_PAIRS = {
    "two_rivers":   [("45210", "own water buoy"), ("KMTW", "own wind"), ("C58W3", "dormant local wind")],
    "manitowoc":    [("45210", "own water buoy"), ("KMTW", "own wind")],
    "sheboygan":    [("SGNW3", "own station"), ("KSBM", "own wind"), ("45210", "BORROWED water")],
    "kewaunee":     [("KWNW3", "own wind"), ("45210", "BORROWED water")],
    "algoma":       [("AGMW3", "dormant own wind"), ("KWNW3", "BORROWED wind"), ("45210", "BORROWED water")],
    "sturgeon_bay": [("0Y2W3", "dormant own wind"), ("KSUE", "own wind"),
                     ("45210", "BORROWED water"), ("45002", "independent backup water")],
}


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------
def http_get(url, timeout=45):
    """Fetch a URL with a User-Agent. Returns (text, error_string)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read().decode("utf-8", errors="replace"), None
    except urllib.error.HTTPError as err:
        body = ""
        try:
            body = err.read().decode("utf-8", errors="replace")[:600]
        except Exception:
            body = "(could not read error body)"
        return None, "HTTP %s - %s | body: %s" % (err.code, err.reason, body)
    except Exception as err:
        return None, "%s: %s" % (type(err).__name__, err)


def miles_between(lat1, lon1, lat2, lon2):
    """Great-circle distance in statute miles."""
    r_miles = 3958.7613
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r_miles * asin(sqrt(a))


def parse_ndbc_location(text):
    """
    Turn NDBC's LOCATION column into signed decimal degrees.
    Example input: "44.055 N 87.050 W (44 3'18\" N 87 3'0\" W)"
    S and W must become NEGATIVE.
    """
    m = re.search(r"([-\d.]+)\s*([NS])\s+([-\d.]+)\s*([EW])", text)
    if not m:
        return None, None, "LOCATION string did not match expected pattern: %r" % text[:120]
    lat = float(m.group(1))
    lon = float(m.group(3))
    if m.group(2).upper() == "S":
        lat = -lat
    if m.group(4).upper() == "W":
        lon = -lon
    return lat, lon, None


def lookup_via_nws(sid):
    """NWS API. Returns (lat, lon, elevation_m, error)."""
    url = NWS_STATION_URL.format(sid=sid)
    text, err = http_get(url)
    if err:
        return None, None, None, "%s -> %s" % (url, err)
    try:
        obj = json.loads(text)
    except Exception as e:
        return None, None, None, "%s -> could not parse JSON: %s" % (url, e)

    geom = obj.get("geometry") or {}
    coords = geom.get("coordinates")
    if not coords or len(coords) < 2:
        return None, None, None, "%s -> no geometry.coordinates in response" % url

    # MECHANISM: GeoJSON is [LON, LAT]. Assert it, don't assume it.
    lon, lat = float(coords[0]), float(coords[1])
    if not (40.0 <= lat <= 49.0 and -93.0 <= lon <= -83.0):
        return None, None, None, (
            "%s -> coordinates outside the Great Lakes box, so the "
            "[lon,lat] order may have changed at NOAA's end. Raw value: %r" % (url, coords)
        )

    elev = None
    props = obj.get("properties") or {}
    elev_obj = props.get("elevation") or {}
    if isinstance(elev_obj, dict) and elev_obj.get("value") is not None:
        elev = float(elev_obj["value"])
    return lat, lon, elev, None


def load_ndbc_table():
    """Download the NDBC station table once. Returns (dict, error)."""
    text, err = http_get(NDBC_TABLE_URL)
    if err:
        return {}, "%s -> %s" % (NDBC_TABLE_URL, err)

    rows = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 7:
            continue
        rows[parts[0].strip().upper()] = {"name": parts[4], "location_raw": parts[6]}
    return rows, None


def lookup_depth(sid):
    """Best-effort water depth from the NDBC station page HTML."""
    url = NDBC_PAGE_URL.format(sid=sid)
    text, err = http_get(url)
    if err:
        return None, None, "%s -> %s" % (url, err)
    m = re.search(r"[Ww]ater depth:\s*([\d.]+)\s*m", text)
    if not m:
        return None, None, "%s -> page fetched OK but no 'Water depth: N m' text found" % url
    metres = float(m.group(1))
    return metres, metres * 3.280839895, None


# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------
def main():
    print("=" * 74)
    print("PIERBITE STATION COORDINATES PROBE - v1 - 2026-07-26")
    print("Read-only. Touches nothing. Looks up where each station actually is.")
    print("=" * 74)

    print("\n" + "-" * 74)
    print("STEP 1 - Download the NDBC station table (one request, all buoys)")
    print("-" * 74)
    ndbc_rows, ndbc_err = load_ndbc_table()
    if ndbc_err:
        print("  COULD NOT LOAD NDBC TABLE:")
        print("  " + ndbc_err)
        print("  Continuing anyway - the NWS API is an independent second source.")
    else:
        print("  OK - parsed %d station rows from the NDBC table." % len(ndbc_rows))

    results = {}

    print("\n" + "-" * 74)
    print("STEP 2 - Look up each station in BOTH sources and cross-check")
    print("-" * 74)

    for sid, kind, note in STATIONS_TO_LOOK_UP:
        print("\n  STATION %s  (%s)" % (sid, kind))
        print("    context: %s" % note)

        entry = {"station_id": sid, "kind": kind}

        # --- Source A: NWS API
        nws_lat, nws_lon, nws_elev, nws_err = lookup_via_nws(sid)
        if nws_err:
            print("    NWS API   : FAILED")
            print("                %s" % nws_err)
        else:
            print("    NWS API   : lat %.6f   lon %.6f%s"
                  % (nws_lat, nws_lon,
                     ("   elevation %.1f m" % nws_elev) if nws_elev is not None else ""))

        # --- Source B: NDBC table
        ndbc_lat = ndbc_lon = None
        row = ndbc_rows.get(sid.upper())
        if row is None:
            print("    NDBC table: station ID not present in the table")
        else:
            ndbc_lat, ndbc_lon, loc_err = parse_ndbc_location(row["location_raw"])
            if loc_err:
                print("    NDBC table: FAILED to parse position")
                print("                %s" % loc_err)
            else:
                print("    NDBC table: lat %.6f   lon %.6f   name: %s"
                      % (ndbc_lat, ndbc_lon, row["name"]))
                entry["ndbc_name"] = row["name"]

        # --- Cross-check the two sources against each other
        chosen_lat = chosen_lon = None
        source_used = None
        if nws_lat is not None and ndbc_lat is not None:
            gap = miles_between(nws_lat, nws_lon, ndbc_lat, ndbc_lon)
            print("    CROSS-CHECK: the two sources are %.3f miles apart" % gap)
            if gap > 1.0:
                print("    *** WARNING: sources disagree by more than 1 mile. "
                      "Do NOT freeze this one without a human look. ***")
                entry["disagreement_mi"] = round(gap, 3)
            chosen_lat, chosen_lon, source_used = nws_lat, nws_lon, "nws_api (agreed with ndbc)"
        elif nws_lat is not None:
            chosen_lat, chosen_lon, source_used = nws_lat, nws_lon, "nws_api (only source)"
        elif ndbc_lat is not None:
            chosen_lat, chosen_lon, source_used = ndbc_lat, ndbc_lon, "ndbc_table (only source)"
        else:
            print("    RESULT    : NO POSITION FOUND IN EITHER SOURCE")
            entry["error"] = "no position found in either source"
            results[sid] = entry
            continue

        entry["lat"] = round(chosen_lat, 6)
        entry["lon"] = round(chosen_lon, 6)
        entry["source"] = source_used
        if nws_elev is not None:
            entry["elevation_m"] = round(nws_elev, 1)

        # --- Water depth, buoys only, best effort
        if kind == "water":
            d_m, d_ft, d_err = lookup_depth(sid)
            if d_err:
                print("    DEPTH     : not found - %s" % d_err)
            else:
                print("    DEPTH     : %.1f m  (%.0f ft)" % (d_m, d_ft))
                entry["water_depth_m"] = round(d_m, 1)
                entry["water_depth_ft"] = round(d_ft, 0)

        results[sid] = entry

    # ------------------------------------------------------------
    print("\n" + "-" * 74)
    print("STEP 3 - Real distance from each pier to each station it reads")
    print("-" * 74)

    distances = {}
    for pier_key, pairs in PIER_STATION_PAIRS.items():
        pier = PIERS[pier_key]
        print("\n  %s pier  (%.6f, %.6f)" % (pier["name"], pier["lat"], pier["lon"]))
        distances[pier_key] = {}
        for sid, role in pairs:
            st = results.get(sid, {})
            if "lat" not in st:
                print("    %-6s %-24s  NO POSITION - cannot compute" % (sid, role))
                continue
            mi = miles_between(pier["lat"], pier["lon"], st["lat"], st["lon"])
            print("    %-6s %-24s  %7.2f miles" % (sid, role, mi))
            distances[pier_key][sid] = round(mi, 2)

    # ------------------------------------------------------------
    print("\n" + "-" * 74)
    print("STEP 4 - Sanity checks against numbers already verified")
    print("-" * 74)

    def check(what, got, expect_low, expect_high):
        if got is None:
            print("  %-46s NOT AVAILABLE" % what)
            return
        ok = expect_low <= got <= expect_high
        print("  %-46s %7.2f   expected %.1f-%.1f   %s"
              % (what, got, expect_low, expect_high, "PASS" if ok else "*** MISMATCH ***"))

    check("Two Rivers pier -> buoy 45210 (miles)",
          distances.get("two_rivers", {}).get("45210"), 25.5, 27.5)
    check("Two Rivers pier -> KMTW airport (miles)",
          distances.get("two_rivers", {}).get("KMTW"), 5.0, 6.5)
    check("Buoy 45210 water depth (feet)",
          results.get("45210", {}).get("water_depth_ft"), 440.0, 500.0)

    print("\n  (The first two come from the 2026-07-25 session and the third from")
    print("   the honesty rebuild plan. If any says MISMATCH, stop and tell Claude.)")

    # ------------------------------------------------------------
    print("\n\n" + "=" * 74)
    print("MACHINE-READABLE RESULT - COPY EVERYTHING BELOW THIS LINE")
    print("=" * 74)
    print(json.dumps({
        "probe": "station-coordinates-probe-2026-07-26-v1",
        "pier_coordinates_used": PIERS,
        "stations": results,
        "pier_to_station_miles": distances,
    }, indent=2, sort_keys=True))
    print("=" * 74)
    print("END OF MACHINE-READABLE RESULT")
    print("=" * 74)


if __name__ == "__main__":
    main()
