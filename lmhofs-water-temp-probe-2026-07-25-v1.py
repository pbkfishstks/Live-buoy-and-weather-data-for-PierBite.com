"""
PIERBITE — LMHOFS NEARSHORE WATER TEMPERATURE PROBE
Created: 2026-07-25 | v1 | Diagnostic only

WHAT THIS IS
------------
This is a TEST. It is not part of the live site.

It does not touch data.json.
It does not change fetch_data.py.
It does not publish anything to the website.
It only reads public NOAA data and prints what it finds to the
GitHub Actions log, so a human can read the results.

If this script fails, nothing on PierBite.com breaks.

WHY IT EXISTS
-------------
Right now every PierBite pier shows the water temperature from a
single buoy (NDBC 45210) that floats about 26 miles offshore in
roughly 475 feet of water. Six piers spread across ~100 miles of
Wisconsin shoreline all display that one number as if it were their
own. On 2026-07-25 that number was 68.0F for all six, which tripped
the warm-water score cap and pinned all six piers to a score of 44.

NOAA runs a model called LMHOFS (Lake Michigan and Huron Operational
Forecast System) that produces water temperature at a resolution of
roughly 100 meters near the shoreline. If PierBite can read that
model, each pier can finally have its own water temperature instead
of borrowing a mid-lake buoy.

The open question this probe answers: can a free GitHub Action
actually reach that model and pull a usable number, without
downloading enormous files or installing scientific libraries?

HOW IT ANSWERS THAT
-------------------
NOAA publishes LMHOFS on a THREDDS/OPeNDAP server. OPeNDAP allows
partial reads: you can ask a server for a description of a file, or
for a few specific numbers inside it, instead of downloading the
whole thing. This script uses only Python's built-in urllib, so
there is nothing to install.

It runs in five stages and prints results after each one:

  STAGE 1  Find the newest LMHOFS "stations" file that exists.
  STAGE 2  Ask that file to describe itself (its variable list).
  STAGE 3  Read the model's station coordinates.
  STAGE 4  Find which model station sits nearest each PierBite pier.
  STAGE 5  Read the actual water temperature at those stations.

Every stage prints PASS or FAIL with the reason. Nothing is assumed;
variable names are discovered from the file itself rather than
guessed, because a guess that happens to work today can silently
break later.
"""

import json
import math
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------

THREDDS_BASE = (
    "https://opendap.co-ops.nos.noaa.gov/thredds/dodsC/"
    "NOAA/LMHOFS/MODELS/{yyyy}/{mm}/{dd}/"
    "lmhofs.t{cycle}z.{yyyy}{mm}{dd}.stations.nowcast.nc"
)

# LMHOFS runs four times a day. Newest first.
CYCLES = ["18", "12", "06", "00"]

# How many days back to look before giving up.
DAYS_BACK = 3

REQUEST_TIMEOUT_SECONDS = 60
USER_AGENT = "PierBiteDotCom LMHOFS probe (diagnostic, read-only)"

# PROVISIONAL pier coordinates.
#
# IMPORTANT HONESTY NOTE: four of these six came from coordinates
# already present in the live fetch_data.py (its GLSEA satellite
# points, which were chosen deliberately at harbor mouths and pier
# heads). Two Rivers and Sturgeon Bay are ESTIMATES made for this
# probe and have NOT been surveyed or verified.
#
# That is acceptable here because this probe's job is only to answer
# "does the data source work at all." Exact pier-end coordinates are
# a separate task and must be verified before anything ships to the
# public site. The probe prints the distance from each pier to its
# nearest model station, so a badly wrong coordinate would show up
# immediately as an implausible distance.
PIERS = {
    "two_rivers":   {"name": "Two Rivers",   "lat": 44.1540, "lon": -87.5640, "verified": False},
    "manitowoc":    {"name": "Manitowoc",    "lat": 44.0955, "lon": -87.6608, "verified": True},
    "sheboygan":    {"name": "Sheboygan",    "lat": 43.7495, "lon": -87.6927, "verified": True},
    "kewaunee":     {"name": "Kewaunee",     "lat": 44.4589, "lon": -87.5094, "verified": True},
    "algoma":       {"name": "Algoma",       "lat": 44.6086, "lon": -87.4350, "verified": True},
    "sturgeon_bay": {"name": "Sturgeon Bay", "lat": 44.7950, "lon": -87.3140, "verified": False},
}

# For comparison: the mid-lake buoy currently feeding every pier.
BUOY_45210 = {"name": "NDBC 45210 (Rawley Point East)", "lat": 44.0550, "lon": -87.0500}


# ---------------------------------------------------------------
# SMALL HELPERS
# ---------------------------------------------------------------

def banner(text):
    print()
    print("=" * 70)
    print(text)
    print("=" * 70)


def fetch_text(url, max_chars=None):
    """Fetch a URL as text. Returns (ok, text_or_error_message)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        return False, "HTTP %s" % e.code
    except urllib.error.URLError as e:
        return False, "connection failed: %s" % e.reason
    except Exception as e:  # noqa: BLE001 - probe should never crash the job
        return False, "unexpected error: %s" % e
    text = raw.decode("utf-8", errors="replace")
    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars] + "\n... (truncated)"
    return True, text


def haversine_miles(lat1, lon1, lat2, lon2):
    """Great-circle distance in statute miles between two points.

    This is the standard formula for distance on a sphere. It is used
    here so that no distance in this project is ever hand-typed.
    """
    earth_radius_miles = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * earth_radius_miles * math.asin(math.sqrt(a))


def c_to_f(celsius):
    return celsius * 9.0 / 5.0 + 32.0


def parse_opendap_ascii_floats(text, varname):
    """Pull the numeric values for one variable out of an OPeNDAP
    .ascii response.

    OPeNDAP's ASCII format puts a header block, then lines that begin
    with the variable name (sometimes with bracketed indices) followed
    by comma-separated numbers. Rather than assume one exact layout,
    this collects every number found on lines mentioning the variable.
    """
    values = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or varname not in stripped:
            continue
        if "," not in stripped:
            continue
        # Everything after the first comma is data.
        _, _, payload = stripped.partition(",")
        for piece in payload.split(","):
            piece = piece.strip()
            if not piece:
                continue
            try:
                values.append(float(piece))
            except ValueError:
                pass
    return values


# ---------------------------------------------------------------
# STAGE 1 — find the newest available LMHOFS stations file
# ---------------------------------------------------------------

def stage1_find_newest_file():
    banner("STAGE 1  —  Find the newest LMHOFS stations file")
    print("LMHOFS publishes four model runs a day (00z, 06z, 12z, 18z).")
    print("Working backwards from now until a file responds.\n")

    now = datetime.now(timezone.utc)
    attempts = 0

    for day_offset in range(DAYS_BACK + 1):
        day = now - timedelta(days=day_offset)
        for cycle in CYCLES:
            url = THREDDS_BASE.format(
                yyyy=day.strftime("%Y"),
                mm=day.strftime("%m"),
                dd=day.strftime("%d"),
                cycle=cycle,
            )
            attempts += 1
            label = "%s  %sz" % (day.strftime("%Y-%m-%d"), cycle)
            ok, body = fetch_text(url + ".dds", max_chars=200)
            if ok and "Dataset" in body:
                print("  FOUND   %s" % label)
                print("\nUsing this file:")
                print("  %s" % url)
                return url
            print("  absent  %s   (%s)" % (label, body if not ok else "no dataset header"))

    print("\nFAIL — no LMHOFS stations file responded after %d attempts." % attempts)
    return None


# ---------------------------------------------------------------
# STAGE 2 — ask the file to describe itself
# ---------------------------------------------------------------

def stage2_describe(url):
    banner("STAGE 2  —  Ask the file what is inside it")
    print("Requesting the DDS (Dataset Descriptor Structure). This is a")
    print("small text description of every variable in the file. It costs")
    print("almost nothing to fetch and tells us the real variable names")
    print("instead of guessing at them.\n")

    ok, dds = fetch_text(url + ".dds", max_chars=6000)
    if not ok:
        print("FAIL — could not read the file description: %s" % dds)
        return None

    print(dds)

    names = []
    for line in dds.splitlines():
        line = line.strip().rstrip(";")
        if not line or line.startswith(("Dataset", "{", "}")):
            continue
        parts = line.replace("[", " ").split()
        if len(parts) >= 2:
            names.append(parts[1])

    print("\nPASS — file described itself successfully.")
    print("Variables detected: %s" % ", ".join(sorted(set(names))[:40]))
    return sorted(set(names))


# ---------------------------------------------------------------
# STAGE 3 — read the model's station coordinates
# ---------------------------------------------------------------

def stage3_station_coords(url, varnames):
    banner("STAGE 3  —  Read the model's station coordinates")
    print("The stations file holds a fixed list of points NOAA reports on.")
    print("Reading their latitude and longitude so we can find which ones")
    print("sit closest to each PierBite pier.\n")

    lat_candidates = [n for n in varnames if n.lower() in ("lat", "latitude", "y")]
    lon_candidates = [n for n in varnames if n.lower() in ("lon", "longitude", "x")]

    if not lat_candidates or not lon_candidates:
        print("FAIL — could not identify latitude/longitude variables.")
        print("       Looked for: lat/latitude/y and lon/longitude/x")
        print("       Available:  %s" % ", ".join(varnames[:40]))
        return None

    lat_var, lon_var = lat_candidates[0], lon_candidates[0]
    print("Using latitude variable:  %s" % lat_var)
    print("Using longitude variable: %s" % lon_var)

    ok_lat, lat_text = fetch_text("%s.ascii?%s" % (url, lat_var))
    ok_lon, lon_text = fetch_text("%s.ascii?%s" % (url, lon_var))

    if not ok_lat or not ok_lon:
        print("\nFAIL — could not read coordinates.")
        print("  latitude:  %s" % ("ok" if ok_lat else lat_text))
        print("  longitude: %s" % ("ok" if ok_lon else lon_text))
        return None

    lats = parse_opendap_ascii_floats(lat_text, lat_var)
    lons = parse_opendap_ascii_floats(lon_text, lon_var)

    if not lats or not lons or len(lats) != len(lons):
        print("\nFAIL — coordinate lists were empty or mismatched.")
        print("  latitude values read:  %d" % len(lats))
        print("  longitude values read: %d" % len(lons))
        return None

    # OPeNDAP sometimes reports Great Lakes longitudes as 0-360.
    lons = [(v - 360.0) if v > 180.0 else v for v in lons]

    print("\nPASS — read %d model station coordinates." % len(lats))
    print("  latitude range:  %.4f to %.4f" % (min(lats), max(lats)))
    print("  longitude range: %.4f to %.4f" % (min(lons), max(lons)))
    return list(zip(lats, lons))


# ---------------------------------------------------------------
# STAGE 4 — match each pier to its nearest model station
# ---------------------------------------------------------------

def stage4_match_piers(coords):
    banner("STAGE 4  —  Match each pier to its nearest model station")
    print("For each pier, measuring the distance to every model station")
    print("and keeping the closest one. Distances are calculated, never")
    print("typed in by hand.\n")

    print("For comparison, the buoy currently feeding ALL SIX piers:")
    for pid, pier in PIERS.items():
        d = haversine_miles(pier["lat"], pier["lon"], BUOY_45210["lat"], BUOY_45210["lon"])
        print("  %-14s is %5.1f miles from buoy 45210" % (pier["name"], d))
    print()

    matches = {}
    print("%-14s %-10s %-22s %s" % ("PIER", "COORDS", "NEAREST MODEL STATION", "DISTANCE"))
    print("-" * 70)
    for pid, pier in PIERS.items():
        best_index, best_dist = None, None
        for i, (slat, slon) in enumerate(coords):
            d = haversine_miles(pier["lat"], pier["lon"], slat, slon)
            if best_dist is None or d < best_dist:
                best_index, best_dist = i, d
        matches[pid] = {"index": best_index, "distance_miles": best_dist}
        flag = "" if pier["verified"] else "  (pier coords PROVISIONAL)"
        print("%-14s %-10s #%-21d %5.2f mi%s" % (
            pier["name"],
            "ok" if pier["verified"] else "prov.",
            best_index,
            best_dist,
            flag,
        ))

    worst = max(m["distance_miles"] for m in matches.values())
    print()
    if worst > 15:
        print("WARNING — the worst match is %.1f miles away. That is far" % worst)
        print("          enough to suspect a coordinate or units problem.")
    else:
        print("PASS — every pier matched a model station within %.1f miles." % worst)
    return matches


# ---------------------------------------------------------------
# STAGE 5 — read the actual water temperature
# ---------------------------------------------------------------

def stage5_read_temps(url, varnames, matches):
    banner("STAGE 5  —  Read the actual water temperature")
    print("This is the number that matters. Reading the surface water")
    print("temperature at each pier's matched model station.\n")

    temp_candidates = [n for n in varnames if n.lower() in ("temp", "temperature", "water_temp")]
    if not temp_candidates:
        print("FAIL — no temperature variable found.")
        print("       Available: %s" % ", ".join(varnames[:40]))
        return None
    temp_var = temp_candidates[0]
    print("Using temperature variable: %s\n" % temp_var)

    results = {}
    print("%-14s %-12s %-12s %s" % ("PIER", "MODEL TEMP", "SITE SHOWS", "DIFFERENCE"))
    print("-" * 70)
    for pid, match in matches.items():
        idx = match["index"]
        # Ask only for this one station, surface layer, latest time step.
        query = "%s.ascii?%s[0][0][%d]" % (url, temp_var, idx)
        ok, text = fetch_text(query, max_chars=4000)
        if not ok:
            # Some files order dimensions differently; try a simpler slice.
            query = "%s.ascii?%s[0][%d]" % (url, temp_var, idx)
            ok, text = fetch_text(query, max_chars=4000)
        if not ok:
            print("%-14s FAILED (%s)" % (PIERS[pid]["name"], text))
            continue

        values = parse_opendap_ascii_floats(text, temp_var)
        if not values:
            print("%-14s no value returned" % PIERS[pid]["name"])
            continue

        temp_c = values[0]
        temp_f = c_to_f(temp_c)
        # Sanity: a Great Lakes surface temp outside this range is wrong.
        if not (25.0 <= temp_f <= 90.0):
            print("%-14s IMPLAUSIBLE %.1fF (raw %.3f) — check units" % (
                PIERS[pid]["name"], temp_f, temp_c))
            continue

        results[pid] = {
            "temp_f": round(temp_f, 1),
            "temp_c": round(temp_c, 2),
            "distance_miles": round(match["distance_miles"], 2),
        }
        print("%-14s %6.1f F     %6.1f F     %+5.1f F" % (
            PIERS[pid]["name"], temp_f, 68.0, temp_f - 68.0))

    print()
    if not results:
        print("FAIL — no temperatures could be read.")
        return None

    spread = max(r["temp_f"] for r in results.values()) - min(r["temp_f"] for r in results.values())
    print("PASS — read %d of %d piers." % (len(results), len(PIERS)))
    print()
    print("SPREAD ACROSS PIERS: %.1f degrees F" % spread)
    if spread < 0.5:
        print("  All piers nearly identical. Either the lake really is")
        print("  uniform today, or the model stations matched are too far")
        print("  apart to differ. Worth a second look.")
    else:
        print("  The piers genuinely differ. This is what the site needs:")
        print("  six real numbers instead of one number copied six times.")
    return results


# ---------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------

def main():
    banner("PIERBITE — LMHOFS NEARSHORE WATER TEMPERATURE PROBE")
    print("Run at: %s UTC" % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    print()
    print("This is a READ-ONLY diagnostic. It does not modify data.json,")
    print("does not modify fetch_data.py, and cannot affect the live site.")

    url = stage1_find_newest_file()
    if not url:
        banner("RESULT — CANNOT REACH LMHOFS")
        print("No model file responded. This does not necessarily mean the")
        print("route is impossible; NOAA may be mid-publish, or the server")
        print("may be briefly down. Try again in a few hours before")
        print("concluding anything.")
        return 1

    varnames = stage2_describe(url)
    if not varnames:
        banner("RESULT — FILE FOUND BUT UNREADABLE")
        print("The file exists but would not describe itself. Stopping here")
        print("rather than guessing at its contents.")
        return 1

    coords = stage3_station_coords(url, varnames)
    if not coords:
        banner("RESULT — PARTIAL")
        print("The file was found and described itself, but its coordinates")
        print("could not be read. The variable names printed in STAGE 2 are")
        print("the next thing to inspect.")
        return 1

    matches = stage4_match_piers(coords)
    results = stage5_read_temps(url, varnames, matches)

    banner("RESULT")
    if results:
        print("SUCCESS — LMHOFS nearshore water temperature is reachable")
        print("from a free GitHub Action using only built-in Python.")
        print()
        print("Machine-readable summary:")
        print(json.dumps(results, indent=2, sort_keys=True))
        print()
        print("NEXT STEP: verify the two provisional pier coordinates")
        print("(Two Rivers, Sturgeon Bay) before any of this reaches the")
        print("public site.")
        return 0

    print("PARTIAL — the file was reachable and described itself, and pier")
    print("matching worked, but temperatures could not be extracted. The")
    print("STAGE 2 variable list is the place to look next.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
