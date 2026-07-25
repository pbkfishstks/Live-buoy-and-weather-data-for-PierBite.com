"""
PIERBITE — LMHOFS NEARSHORE WATER TEMPERATURE PROBE
Created: 2026-07-25 | v2 | Diagnostic only

WHAT CHANGED SINCE v1
---------------------
v1 succeeded at the thing that mattered most: it proved NOAA's
LMHOFS model is reachable from a free GitHub Action. It found a
live model file in about 10 seconds and got the file to list its
own contents.

v1 then failed on a bug of mine. My routine for pulling numbers out
of NOAA's reply assumed the variable name and its numbers sat on the
same line of text. NOAA puts the name on one line and the numbers on
the following line, so my reader found nothing and stopped. That was
my error, not a problem with the data source.

Three fixes and additions in v2:

  1. REWRITTEN NUMBER READER. Instead of matching line by line, v2
     locates the divider NOAA prints between the header and the data,
     takes everything after it, removes bracketed index labels, and
     reads every number in what remains. This does not depend on
     where line breaks fall.

  2. RAW OUTPUT PRINTED. v2 prints the first part of NOAA's actual
     reply before trying to interpret it. If the reader fails again,
     the reason will be visible in the log instead of requiring
     another round trip.

  3. THE REAL QUESTION GETS ANSWERED. v1 revealed the stations file
     holds only 48 points, covering both Lake Michigan AND Lake
     Huron. That is a very small number for a very large area. If the
     nearest of those 48 to a PierBite pier is 30 miles away, this
     route solves nothing — it would trade one distant source for
     another.

     So v2 checks BOTH available routes and reports which one is
     good enough:

       ROUTE A - the stations file. 48 official points. Small and
                 fast, but only useful if one happens to sit near
                 each pier.

       ROUTE B - the full model grid. About 90,806 points, spaced
                 roughly 100 meters apart near shore. Certain to have
                 a point at every pier. Costs more to set up, and
                 that setup is a one-time job whose result gets
                 written down permanently.

SAFETY — UNCHANGED FROM v1
--------------------------
Read-only. Does not modify data.json. Does not modify fetch_data.py.
Cannot affect the live site. If it fails, nothing breaks.
"""

import json
import math
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------

BASE_DIR = (
    "https://opendap.co-ops.nos.noaa.gov/thredds/dodsC/"
    "NOAA/LMHOFS/MODELS/{yyyy}/{mm}/{dd}/"
)
STATIONS_FILE = "lmhofs.t{cycle}z.{yyyy}{mm}{dd}.stations.nowcast.nc"
FIELDS_FILE = "lmhofs.t{cycle}z.{yyyy}{mm}{dd}.fields.n000.nc"

CYCLES = ["18", "12", "06", "00"]
DAYS_BACK = 3

TIMEOUT_SHORT = 60
TIMEOUT_LONG = 240  # the full grid coordinate lists are large
USER_AGENT = "PierBiteDotCom LMHOFS probe (diagnostic, read-only)"

# How close a model point must be for us to call it "at the pier."
GOOD_ENOUGH_MILES = 3.0

# PROVISIONAL pier coordinates.
# Four came from coordinates already in the live fetch_data.py (its
# satellite sample points, chosen at harbor mouths and pier heads).
# Two Rivers and Sturgeon Bay are ESTIMATES and are NOT verified.
# Exact pier-end coordinates are a separate task that must be done
# before anything reaches the public site. Distances printed below
# would expose a badly wrong coordinate immediately.
PIERS = {
    "two_rivers":   {"name": "Two Rivers",   "lat": 44.1540, "lon": -87.5640, "verified": False},
    "manitowoc":    {"name": "Manitowoc",    "lat": 44.0955, "lon": -87.6608, "verified": True},
    "sheboygan":    {"name": "Sheboygan",    "lat": 43.7495, "lon": -87.6927, "verified": True},
    "kewaunee":     {"name": "Kewaunee",     "lat": 44.4589, "lon": -87.5094, "verified": True},
    "algoma":       {"name": "Algoma",       "lat": 44.6086, "lon": -87.4350, "verified": True},
    "sturgeon_bay": {"name": "Sturgeon Bay", "lat": 44.7950, "lon": -87.3140, "verified": False},
}

BUOY_45210 = {"name": "NDBC 45210 (Rawley Point East)", "lat": 44.0550, "lon": -87.0500}
CURRENT_SITE_TEMP_F = 68.0  # what all six piers show today


# ---------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------

def banner(text):
    print()
    print("=" * 70)
    print(text)
    print("=" * 70)


def fetch_text(url, timeout=TIMEOUT_SHORT, max_chars=None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        return False, "HTTP %s" % e.code
    except urllib.error.URLError as e:
        return False, "connection failed: %s" % e.reason
    except Exception as e:  # noqa: BLE001
        return False, "unexpected error: %s" % e
    text = raw.decode("utf-8", errors="replace")
    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars] + "\n... (truncated)"
    return True, text


def haversine_miles(lat1, lon1, lat2, lon2):
    """Great-circle distance in statute miles. No distance in this
    project is ever typed by hand."""
    r = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def c_to_f(c):
    return c * 9.0 / 5.0 + 32.0


_NUMBER = re.compile(r"[-+]?\d*\.\d+(?:[eE][-+]?\d+)?|[-+]?\d+(?:[eE][-+]?\d+)?")
_BRACKETS = re.compile(r"\[[^\]]*\]")
_DIVIDER = re.compile(r"^-{3,}\s*$", re.MULTILINE)


def data_section(text):
    """Return just the numeric portion of an OPeNDAP ASCII reply.

    NOAA prints a header describing the request, then a line of
    dashes, then the data. Splitting on that divider is far more
    reliable than trying to match variable names line by line — which
    is exactly where v1 went wrong.
    """
    parts = _DIVIDER.split(text)
    if len(parts) > 1:
        return parts[-1]
    # No divider found: drop the first line (the declaration) and
    # keep the rest.
    lines = text.splitlines()
    return "\n".join(lines[1:]) if len(lines) > 1 else text


def parse_floats(text):
    """Read every number out of an OPeNDAP ASCII data section."""
    body = _BRACKETS.sub(" ", data_section(text))
    out = []
    for m in _NUMBER.finditer(body):
        try:
            out.append(float(m.group()))
        except ValueError:
            pass
    return out


def parse_strings(text):
    """Read quoted station names out of an OPeNDAP ASCII reply."""
    body = data_section(text)
    quoted = re.findall(r'"([^"]*)"', body)
    if quoted:
        return [s.strip() for s in quoted if s.strip()]
    names = []
    for line in body.splitlines():
        line = line.strip()
        if not line or _NUMBER.fullmatch(line):
            continue
        for piece in line.split(","):
            piece = piece.strip().strip('"')
            if piece and not _NUMBER.fullmatch(piece):
                names.append(piece)
    return names


def normalise_lons(lons):
    """Great Lakes longitudes are sometimes published as 0-360."""
    return [(v - 360.0) if v > 180.0 else v for v in lons]


def pick(varnames, options):
    lowered = {n.lower(): n for n in varnames}
    for o in options:
        if o in lowered:
            return lowered[o]
    return None


def parse_dds(dds):
    """Pull variable names out of a DDS block."""
    names = []
    for line in dds.splitlines():
        line = line.strip().rstrip(";")
        if not line or line.startswith(("Dataset", "{", "}")):
            continue
        cleaned = _BRACKETS.sub(" ", line)
        parts = cleaned.split()
        if len(parts) >= 2:
            names.append(parts[1])
    return sorted(set(names))


# ---------------------------------------------------------------
# STAGE 1 — locate a live model run
# ---------------------------------------------------------------

def stage1_find_run():
    banner("STAGE 1  —  Locate a live LMHOFS model run")
    print("LMHOFS publishes four runs a day (00z, 06z, 12z, 18z).")
    print("Working backwards from now until one answers.\n")

    now = datetime.now(timezone.utc)
    for day_offset in range(DAYS_BACK + 1):
        day = now - timedelta(days=day_offset)
        for cycle in CYCLES:
            parts = {
                "yyyy": day.strftime("%Y"),
                "mm": day.strftime("%m"),
                "dd": day.strftime("%d"),
                "cycle": cycle,
            }
            url = BASE_DIR.format(**parts) + STATIONS_FILE.format(**parts)
            label = "%s  %sz" % (day.strftime("%Y-%m-%d"), cycle)
            ok, body = fetch_text(url + ".dds", max_chars=200)
            if ok and "Dataset" in body:
                print("  FOUND   %s" % label)
                return parts
            print("  absent  %s   (%s)" % (label, body if not ok else "no dataset header"))

    print("\nFAIL — no model run responded.")
    return None


# ---------------------------------------------------------------
# STAGE 2 — ROUTE A: the 48-station file
# ---------------------------------------------------------------

def stage2_route_a(parts):
    banner("ROUTE A  —  The 48-station file")
    print("This file is small and fast. The question is whether any of")
    print("its 48 points sit close enough to a PierBite pier to be")
    print("worth using.\n")

    url = BASE_DIR.format(**parts) + STATIONS_FILE.format(**parts)

    ok, dds = fetch_text(url + ".dds", max_chars=8000)
    if not ok:
        print("FAIL — could not read structure: %s" % dds)
        return None
    varnames = parse_dds(dds)
    print("Variables: %s\n" % ", ".join(varnames))

    lat_var = pick(varnames, ["lat", "latitude"])
    lon_var = pick(varnames, ["lon", "longitude"])
    name_var = pick(varnames, ["name_station", "station_name", "names"])
    temp_var = pick(varnames, ["temp", "temperature"])

    if not lat_var or not lon_var:
        print("FAIL — no latitude/longitude variables found.")
        return None

    ok_lat, lat_raw = fetch_text("%s.ascii?%s" % (url, lat_var))
    if not ok_lat:
        print("FAIL — could not read latitudes: %s" % lat_raw)
        return None

    print("Raw reply from NOAA (first 400 characters), so any parsing")
    print("problem is visible rather than guessed at:")
    print("-" * 70)
    print(lat_raw[:400])
    print("-" * 70)

    ok_lon, lon_raw = fetch_text("%s.ascii?%s" % (url, lon_var))
    if not ok_lon:
        print("FAIL — could not read longitudes: %s" % lon_raw)
        return None

    lats = parse_floats(lat_raw)
    lons = normalise_lons(parse_floats(lon_raw))
    print("\nRead %d latitudes and %d longitudes." % (len(lats), len(lons)))
    if not lats or len(lats) != len(lons):
        print("FAIL — counts empty or mismatched.")
        return None

    names = []
    if name_var:
        ok_n, name_raw = fetch_text("%s.ascii?%s" % (url, name_var))
        if ok_n:
            names = parse_strings(name_raw)
    if len(names) != len(lats):
        names = ["station #%d" % i for i in range(len(lats))]

    print("\nAll %d model stations:" % len(lats))
    print("%-4s %-34s %10s %11s" % ("#", "NAME", "LAT", "LON"))
    print("-" * 70)
    for i, (la, lo, nm) in enumerate(zip(lats, lons, names)):
        print("%-4d %-34s %10.4f %11.4f" % (i, nm[:34], la, lo))

    banner("ROUTE A  —  Distance from each pier to its nearest station")
    print("For reference, every pier currently uses buoy 45210:\n")
    for pier in PIERS.values():
        d = haversine_miles(pier["lat"], pier["lon"], BUOY_45210["lat"], BUOY_45210["lon"])
        print("  %-14s  %5.1f mi from buoy 45210" % (pier["name"], d))

    print()
    print("%-14s %-32s %10s" % ("PIER", "NEAREST MODEL STATION", "DISTANCE"))
    print("-" * 70)
    matches = {}
    for pid, pier in PIERS.items():
        best_i, best_d = None, None
        for i, (la, lo) in enumerate(zip(lats, lons)):
            d = haversine_miles(pier["lat"], pier["lon"], la, lo)
            if best_d is None or d < best_d:
                best_i, best_d = i, d
        matches[pid] = {"index": best_i, "distance_miles": best_d, "station": names[best_i]}
        print("%-14s %-32s %7.2f mi" % (pier["name"], names[best_i][:32], best_d))

    worst = max(m["distance_miles"] for m in matches.values())
    print()
    if worst <= GOOD_ENOUGH_MILES:
        print("ROUTE A IS GOOD ENOUGH — worst match is %.2f miles." % worst)
        verdict = "good"
    else:
        print("ROUTE A IS NOT GOOD ENOUGH — worst match is %.2f miles." % worst)
        print("A reading that far away is not this pier's water. Using it")
        print("would repeat the exact mistake the site is trying to fix.")
        verdict = "too_far"

    if temp_var:
        print("\nReading temperatures anyway, to confirm the values are real:")
        read_temps(url, temp_var, matches, len(lats))

    return {"verdict": verdict, "worst_miles": worst, "matches": matches}


def read_temps(url, temp_var, matches, n_points):
    """Read water temperature at matched points. Tries the common
    dimension orders rather than assuming one."""
    print("%-14s %-12s %-12s %s" % ("PIER", "MODEL", "SITE SHOWS", "DIFFERENCE"))
    print("-" * 70)
    got = {}
    for pid, m in matches.items():
        idx = m["index"]
        value = None
        for query in ("%s[0][0][%d]" % (temp_var, idx),
                      "%s[0][%d]" % (temp_var, idx),
                      "%s[0][%d][0]" % (temp_var, idx)):
            ok, txt = fetch_text("%s.ascii?%s" % (url, query), max_chars=3000)
            if not ok:
                continue
            vals = parse_floats(txt)
            if vals:
                value = vals[-1]
                break
        if value is None:
            print("%-14s  could not read" % PIERS[pid]["name"])
            continue
        f = c_to_f(value)
        if not (25.0 <= f <= 90.0):
            print("%-14s  implausible %.1fF (raw %.3f)" % (PIERS[pid]["name"], f, value))
            continue
        got[pid] = round(f, 1)
        print("%-14s %6.1f F     %6.1f F     %+5.1f F" % (
            PIERS[pid]["name"], f, CURRENT_SITE_TEMP_F, f - CURRENT_SITE_TEMP_F))
    if got:
        spread = max(got.values()) - min(got.values())
        print("\nSpread across piers: %.1f F" % spread)
    return got


# ---------------------------------------------------------------
# STAGE 3 — ROUTE B: the full model grid
# ---------------------------------------------------------------

def stage3_route_b(parts):
    banner("ROUTE B  —  The full model grid (~90,000 points)")
    print("This is the high-resolution option: model points spaced")
    print("roughly 100 metres apart near the shoreline. Reading the")
    print("coordinate list is a ONE-TIME job. Once we know which point")
    print("sits at each pier, that point's number gets written down and")
    print("every future update fetches six values and nothing more.\n")

    url = BASE_DIR.format(**parts) + FIELDS_FILE.format(**parts)

    ok, dds = fetch_text(url + ".dds", max_chars=8000)
    if not ok:
        print("FAIL — could not read structure: %s" % dds)
        return None
    varnames = parse_dds(dds)
    print("Variables: %s\n" % ", ".join(varnames[:50]))

    lat_var = pick(varnames, ["lat", "latitude"])
    lon_var = pick(varnames, ["lon", "longitude"])
    temp_var = pick(varnames, ["temp", "temperature"])
    if not lat_var or not lon_var:
        print("FAIL — no latitude/longitude variables found.")
        return None

    print("Downloading the coordinate list. This is the slow step and")
    print("happens only once, ever.\n")

    ok_lat, lat_raw = fetch_text("%s.ascii?%s" % (url, lat_var), timeout=TIMEOUT_LONG)
    if not ok_lat:
        print("FAIL — could not read grid latitudes: %s" % lat_raw)
        return None
    ok_lon, lon_raw = fetch_text("%s.ascii?%s" % (url, lon_var), timeout=TIMEOUT_LONG)
    if not ok_lon:
        print("FAIL — could not read grid longitudes: %s" % lon_raw)
        return None

    lats = parse_floats(lat_raw)
    lons = normalise_lons(parse_floats(lon_raw))
    print("Read %d grid latitudes and %d longitudes." % (len(lats), len(lons)))
    if not lats or len(lats) != len(lons):
        print("FAIL — counts empty or mismatched.")
        return None

    print()
    print("%-14s %-12s %s" % ("PIER", "GRID POINT", "DISTANCE"))
    print("-" * 70)
    matches = {}
    for pid, pier in PIERS.items():
        best_i, best_d = None, None
        for i, (la, lo) in enumerate(zip(lats, lons)):
            d = haversine_miles(pier["lat"], pier["lon"], la, lo)
            if best_d is None or d < best_d:
                best_i, best_d = i, d
        matches[pid] = {"index": best_i, "distance_miles": round(best_d, 3)}
        flag = "" if pier["verified"] else "   (pier coords provisional)"
        print("%-14s #%-11d %7.3f mi%s" % (pier["name"], best_i, best_d, flag))

    worst = max(m["distance_miles"] for m in matches.values())
    print()
    if worst <= GOOD_ENOUGH_MILES:
        print("ROUTE B IS GOOD ENOUGH — worst match is %.3f miles." % worst)
    else:
        print("ROUTE B worst match is %.3f miles, which is unexpected for" % worst)
        print("a 100-metre grid. Suspect a pier coordinate is wrong.")

    temps = {}
    if temp_var:
        print("\nReading temperatures at those grid points:\n")
        temps = read_temps(url, temp_var, matches, len(lats))

    return {"worst_miles": worst, "matches": matches, "temps": temps}


# ---------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------

def main():
    banner("PIERBITE — LMHOFS PROBE v2")
    print("Run at: %s UTC" % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    print()
    print("READ-ONLY. Does not modify data.json or fetch_data.py and")
    print("cannot affect the live site.")
    print()
    print("v1 already proved NOAA's model is reachable. This run answers")
    print("the follow-up question: is there a model point close enough to")
    print("each pier to be honestly called that pier's water?")

    parts = stage1_find_run()
    if not parts:
        banner("RESULT — no model run available right now")
        print("Try again in a few hours before drawing conclusions.")
        return 1

    route_a = stage2_route_a(parts)
    route_b = None
    if not route_a or route_a["verdict"] != "good":
        print("\nRoute A did not clear the bar. Testing Route B.")
        route_b = stage3_route_b(parts)
    else:
        print("\nRoute A cleared the bar. Testing Route B anyway, for")
        print("comparison — knowing both costs one extra minute now and")
        print("saves guessing later.")
        route_b = stage3_route_b(parts)

    banner("RESULT — WHICH ROUTE PIERBITE SHOULD USE")
    if route_a:
        print("Route A (48 stations): worst pier match %.2f miles" % route_a["worst_miles"])
    else:
        print("Route A (48 stations): failed")
    if route_b:
        print("Route B (full grid):   worst pier match %.3f miles" % route_b["worst_miles"])
    else:
        print("Route B (full grid):   failed")

    print()
    if route_a and route_a["verdict"] == "good":
        print("RECOMMENDATION: Route A. It is simpler, smaller, and close")
        print("enough. Prefer the simpler option when it genuinely works.")
    elif route_b and route_b["worst_miles"] <= GOOD_ENOUGH_MILES:
        print("RECOMMENDATION: Route B. The 48-station file is too sparse")
        print("along this shoreline, but the full grid puts a model point")
        print("within walking distance of every pier.")
        print()
        print("Grid point numbers to write down permanently:")
        print(json.dumps(
            {k: v["index"] for k, v in route_b["matches"].items()},
            indent=2, sort_keys=True))
    else:
        print("RECOMMENDATION: neither route cleared the bar today. Do not")
        print("build on this yet. The distances above are the evidence.")

    print()
    print("REMINDER: Two Rivers and Sturgeon Bay pier coordinates are")
    print("still provisional and must be verified before anything here")
    print("reaches the public site.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
