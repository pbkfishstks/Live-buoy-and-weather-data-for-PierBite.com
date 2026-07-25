"""
PIERBITE — LMHOFS WATER TEMPERATURE PROBE
Created: 2026-07-25 | v3 | Diagnostic only

WHAT v2 SETTLED
---------------
v2 answered the big question. Route B — NOAA's full model grid of
90,806 points — has a water point within walking distance of every
PierBite pier:

    Sheboygan       565 ft        Kewaunee      2,761 ft
    Algoma        1,061 ft        Two Rivers    2,946 ft
    Sturgeon Bay  1,109 ft        Manitowoc     3,918 ft

Compare that to buoy 45210, which sits 26.6 miles offshore and
currently supplies the water temperature for all six piers at once.

Route A (the 48-station file) was tested and rejected: its nearest
point to a PierBite pier was 45.49 miles away. Testing both was
worth the extra minute — assuming the simpler route would work would
have produced something no better than what the site has now.

WHAT v2 FAILED AT, AND WHY
--------------------------
v2 found the right grid points but could not read a temperature from
any of them. It printed "could not read" six times and discarded the
reason NOAA gave. That was a flaw in how I wrote it: a diagnosable
problem was turned into a shrug.

The leading suspicion is that NOAA's server rejects square brackets
in a web address unless they are written in escaped form (%5B and
%5D rather than [ and ]). Many servers of this type do. But that is
a suspicion, not a finding, and v3 is built to prove or disprove it
rather than assume it.

WHAT v3 DOES DIFFERENTLY
------------------------
  1. NOTHING IS SWALLOWED. Every failed attempt prints the exact
     error NOAA returned, plus the exact address that was tried.

  2. IT ASKS THE FILE FOR ITS OWN SHAPE. Rather than guessing that
     temperature is arranged as [time][layer][point], v3 reads the
     file's own description, finds the temperature entry, and reads
     off its real dimensions and their sizes. The request is then
     built from that, not from my memory of how these files usually
     look.

  3. IT TESTS BOTH ADDRESS STYLES. Escaped brackets and plain
     brackets, and reports which one the server accepts. That answer
     gets written into the project notes so nobody rediscovers it.

  4. IT CHECKS THE WATER IS REAL. Before trusting a temperature, v3
     reads the model's water depth at each point. A depth of zero
     would mean the point is on land and the whole match is wrong.

  5. IT IS FAST. The six grid points are already known, so v3 skips
     the slow 90,806-point download entirely. It re-reads only those
     six coordinates, to confirm they still land where v2 said.

SAFETY — UNCHANGED
------------------
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
FIELDS_FILE = "lmhofs.t{cycle}z.{yyyy}{mm}{dd}.fields.n000.nc"

CYCLES = ["18", "12", "06", "00"]
DAYS_BACK = 3
TIMEOUT = 90
USER_AGENT = "PierBiteDotCom LMHOFS probe (diagnostic, read-only)"

# Grid points identified by probe v2 on 2026-07-25.
# These were derived from the pier coordinates below. If a pier
# coordinate is wrong, its grid point is wrong too — which is why
# all six coordinates still require verification.
GRID_POINTS = {
    "two_rivers":   24195,
    "manitowoc":    21439,
    "sheboygan":    20329,
    "kewaunee":     28276,
    "algoma":       28904,
    "sturgeon_bay": 31190,
}

# Pier coordinates. NONE of these should be treated as verified.
#
# An earlier version of this probe marked four of them "verified"
# because they already existed in the live fetch_data.py. That was
# wrong: inherited is not the same as checked. No one has confirmed
# any of these against a map. Correcting that label here rather than
# letting it quietly propagate.
PIERS = {
    "two_rivers":   {"name": "Two Rivers",   "lat": 44.1540, "lon": -87.5640},
    "manitowoc":    {"name": "Manitowoc",    "lat": 44.0955, "lon": -87.6608},
    "sheboygan":    {"name": "Sheboygan",    "lat": 43.7495, "lon": -87.6927},
    "kewaunee":     {"name": "Kewaunee",     "lat": 44.4589, "lon": -87.5094},
    "algoma":       {"name": "Algoma",       "lat": 44.6086, "lon": -87.4350},
    "sturgeon_bay": {"name": "Sturgeon Bay", "lat": 44.7950, "lon": -87.3140},
}

BUOY_45210_TEMP_F = 68.0  # the single reading all six piers show today
BUOY_45210_MILES = 26.6


# ---------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------

def banner(text):
    print()
    print("=" * 70)
    print(text)
    print("=" * 70)


def fetch(url, timeout=TIMEOUT, max_chars=None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            body = e.read().decode("utf-8", errors="replace").strip()
            if body:
                detail = " | server said: %s" % body.replace("\n", " ")[:200]
        except Exception:  # noqa: BLE001
            pass
        return False, "HTTP %s%s" % (e.code, detail)
    except urllib.error.URLError as e:
        return False, "connection failed: %s" % e.reason
    except Exception as e:  # noqa: BLE001
        return False, "unexpected error: %s" % e
    text = raw.decode("utf-8", errors="replace")
    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars] + "\n... (truncated)"
    return True, text


def escape_brackets(query):
    return query.replace("[", "%5B").replace("]", "%5D")


def haversine_miles(lat1, lon1, lat2, lon2):
    r = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def c_to_f(c):
    return c * 9.0 / 5.0 + 32.0


def m_to_ft(m):
    return m * 3.28084


_NUMBER = re.compile(r"[-+]?\d*\.\d+(?:[eE][-+]?\d+)?|[-+]?\d+(?:[eE][-+]?\d+)?")
_BRACKETS = re.compile(r"\[[^\]]*\]")
_DIVIDER = re.compile(r"^-{3,}\s*$", re.MULTILINE)
_DIM = re.compile(r"\[\s*(\w+)\s*=\s*(\d+)\s*\]")


def parse_floats(text):
    parts = _DIVIDER.split(text)
    body = parts[-1] if len(parts) > 1 else "\n".join(text.splitlines()[1:])
    body = _BRACKETS.sub(" ", body)
    out = []
    for m in _NUMBER.finditer(body):
        try:
            out.append(float(m.group()))
        except ValueError:
            pass
    return out


def find_declaration(dds, varname):
    """Find the line in the file description that declares one
    variable, and read off its dimensions and their sizes."""
    for line in dds.splitlines():
        stripped = line.strip().rstrip(";")
        if not stripped:
            continue
        head = _BRACKETS.sub("", stripped).split()
        if len(head) >= 2 and head[1] == varname:
            dims = [(n, int(s)) for n, s in _DIM.findall(stripped)]
            return stripped, dims
    return None, None


# ---------------------------------------------------------------
# STAGE 1 — locate a live model run
# ---------------------------------------------------------------

def stage1_find_run():
    banner("STAGE 1  —  Locate a live LMHOFS model run")
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
            url = BASE_DIR.format(**parts) + FIELDS_FILE.format(**parts)
            label = "%s  %sz" % (day.strftime("%Y-%m-%d"), cycle)
            ok, body = fetch(url + ".dds", max_chars=200)
            if ok and "Dataset" in body:
                print("  FOUND   %s" % label)
                print("\n  %s" % url)
                return url
            print("  absent  %s   (%s)" % (label, body if not ok else "no header"))
    print("\nFAIL — no model run responded.")
    return None


# ---------------------------------------------------------------
# STAGE 2 — learn the real shape of the temperature data
# ---------------------------------------------------------------

def stage2_learn_shape(url):
    banner("STAGE 2  —  Ask the file how its temperature data is arranged")
    print("Not guessing. Reading the file's own description and taking")
    print("the dimensions from it.\n")

    ok, dds = fetch(url + ".dds", max_chars=60000)
    if not ok:
        print("FAIL — could not read description: %s" % dds)
        return None

    shapes = {}
    for var in ("temp", "h", "lat", "lon", "time", "siglay"):
        decl, dims = find_declaration(dds, var)
        if decl:
            shapes[var] = dims
            print("  %s" % decl)
        else:
            print("  %-8s NOT FOUND" % var)

    if "temp" not in shapes:
        print("\nFAIL — no temperature variable in this file.")
        return None

    print("\nTemperature dimensions, in order:")
    for name, size in shapes["temp"]:
        print("    %-10s size %d" % (name, size))
    return shapes


# ---------------------------------------------------------------
# STAGE 3 — determine which address style the server accepts
# ---------------------------------------------------------------

def stage3_address_style(url, shapes):
    banner("STAGE 3  —  Find out which address style NOAA's server accepts")
    print("v2 failed here and threw away the reason. This time both")
    print("styles are tried and the exact server response is printed.\n")

    lat_dims = shapes.get("lat")
    if not lat_dims:
        print("FAIL — no latitude variable to test with.")
        return None
    test_index = GRID_POINTS["sheboygan"]
    plain = "lat[%d]" % test_index

    for style_name, query in (("ESCAPED  (%5B / %5D)", escape_brackets(plain)),
                              ("PLAIN    ([ / ])", plain)):
        full = "%s.ascii?%s" % (url, query)
        print("Trying %s" % style_name)
        print("  %s" % full)
        ok, body = fetch(full, max_chars=600)
        if ok:
            values = parse_floats(body)
            print("  SUCCESS — server returned: %s" % (values if values else "no numbers"))
            print()
            print("  Raw reply:")
            for line in body.splitlines()[:8]:
                print("    %s" % line)
            print()
            print("MECHANISM CONFIRMED: NOAA's OPeNDAP server accepts the")
            print("%s style. Record this in the project notes." % style_name.split()[0])
            return "escaped" if "ESCAPED" in style_name else "plain"
        print("  FAILED — %s\n" % body)

    print("FAIL — neither address style worked. The failure text above is")
    print("the evidence; do not build anything until it is understood.")
    return None


# ---------------------------------------------------------------
# STAGE 4 — confirm the points are in real water
# ---------------------------------------------------------------

def stage4_confirm_water(url, shapes, style):
    banner("STAGE 4  —  Confirm each grid point sits in real water")
    print("Reading the model's water depth at each point. A depth at or")
    print("near zero would mean the point is on land and the match is")
    print("wrong. Also re-reading each point's coordinates to confirm")
    print("they still land where probe v2 said they did.\n")

    if "h" not in shapes:
        print("SKIPPED — this file has no depth variable.")
        return {}

    def ask(query):
        q = escape_brackets(query) if style == "escaped" else query
        ok, body = fetch("%s.ascii?%s" % (url, q), max_chars=1500)
        if not ok:
            return None, body
        vals = parse_floats(body)
        return (vals[-1] if vals else None), None

    print("%-14s %-8s %10s %10s %12s" % ("PIER", "POINT", "LAT", "LON", "DEPTH"))
    print("-" * 70)
    results = {}
    for pid, idx in GRID_POINTS.items():
        pier = PIERS[pid]
        lat, err_lat = ask("lat[%d]" % idx)
        lon, err_lon = ask("lon[%d]" % idx)
        depth, err_h = ask("h[%d]" % idx)

        if lat is None or lon is None:
            print("%-14s #%-7d could not read coordinates (%s)" % (
                pier["name"], idx, err_lat or err_lon))
            continue
        if lon > 180.0:
            lon -= 360.0

        dist = haversine_miles(pier["lat"], pier["lon"], lat, lon)
        depth_txt = "%.1f ft" % m_to_ft(depth) if depth is not None else "unknown"
        print("%-14s #%-7d %10.4f %10.4f %12s" % (
            pier["name"], idx, lat, lon, depth_txt))
        results[pid] = {
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "depth_ft": round(m_to_ft(depth), 1) if depth is not None else None,
            "distance_miles": round(dist, 3),
        }
        if depth is not None and depth <= 0.5:
            print("    WARNING — depth is %.2f m. This point may be on land." % depth)

    return results


# ---------------------------------------------------------------
# STAGE 5 — read the temperatures
# ---------------------------------------------------------------

def stage5_read_temps(url, shapes, style, water):
    banner("STAGE 5  —  Read the water temperature at each pier")
    print("Building the request from the dimensions the file reported in")
    print("Stage 2, rather than from an assumption about their order.\n")

    dims = shapes["temp"]
    n_points = None
    for name, size in shapes.get("lat", []):
        n_points = size
    if n_points is None:
        n_points = 90806

    # Work out what to put in each slot of the request.
    slots, explain = [], []
    for name, size in dims:
        low = name.lower()
        if size == n_points:
            slots.append(None)  # filled per pier
            explain.append("%s -> the pier's grid point" % name)
        elif low.startswith("time"):
            slots.append(size - 1)
            explain.append("%s -> %d (most recent)" % (name, size - 1))
        elif low.startswith("sig"):
            slots.append(0)
            explain.append("%s -> 0 (surface layer)" % name)
        else:
            slots.append(0)
            explain.append("%s -> 0" % name)

    for line in explain:
        print("  %s" % line)
    if None not in slots:
        print("\nFAIL — could not identify which dimension is the grid point.")
        return {}

    print()
    print("%-14s %-11s %-11s %-11s %s" % (
        "PIER", "MODEL", "SITE SHOWS", "DIFFERENCE", "DEPTH"))
    print("-" * 70)

    results = {}
    for pid, idx in GRID_POINTS.items():
        filled = [str(idx if s is None else s) for s in slots]
        query = "temp" + "".join("[%s]" % s for s in filled)
        if style == "escaped":
            query = escape_brackets(query)
        ok, body = fetch("%s.ascii?%s" % (url, query), max_chars=2000)
        if not ok:
            print("%-14s FAILED — %s" % (PIERS[pid]["name"], body))
            continue
        vals = parse_floats(body)
        if not vals:
            print("%-14s no number in reply" % PIERS[pid]["name"])
            continue
        temp_c = vals[-1]
        temp_f = c_to_f(temp_c)
        if not (25.0 <= temp_f <= 90.0):
            print("%-14s implausible %.1f F (raw %.3f) — check units" % (
                PIERS[pid]["name"], temp_f, temp_c))
            continue
        depth = water.get(pid, {}).get("depth_ft")
        results[pid] = {"temp_f": round(temp_f, 1), "depth_ft": depth}
        print("%-14s %6.1f F    %6.1f F    %+6.1f F    %s" % (
            PIERS[pid]["name"], temp_f, BUOY_45210_TEMP_F,
            temp_f - BUOY_45210_TEMP_F,
            "%.0f ft" % depth if depth else "?"))

    if results:
        temps = [r["temp_f"] for r in results.values()]
        spread = max(temps) - min(temps)
        print()
        print("Read %d of %d piers." % (len(results), len(GRID_POINTS)))
        print("Spread across piers: %.1f degrees F" % spread)
        if spread < 0.5:
            print("  Nearly identical today. That may simply be the truth")
            print("  on a calm day. It is not proof of a problem, but it is")
            print("  worth re-running after a westerly blow, when upwelling")
            print("  should push the piers apart.")
        else:
            print("  The piers genuinely differ. This is the entire point:")
            print("  six real numbers instead of one number copied six times.")
    return results


# ---------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------

def main():
    banner("PIERBITE — LMHOFS PROBE v3")
    print("Run at: %s UTC" % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    print()
    print("READ-ONLY. Cannot affect the live site.")
    print()
    print("Settled by v2: Route B (the full model grid) puts a water point")
    print("within %s of every pier, versus %.1f miles for the buoy" % (
        "3,918 feet", BUOY_45210_MILES))
    print("currently feeding all six.")
    print()
    print("Open from v2: temperatures would not read, and v2 discarded the")
    print("reason. This run recovers that reason and fixes it.")

    url = stage1_find_run()
    if not url:
        return 1

    shapes = stage2_learn_shape(url)
    if not shapes:
        return 1

    style = stage3_address_style(url, shapes)
    if not style:
        banner("RESULT — STOPPED")
        print("The server rejected both address styles. The exact errors are")
        print("printed above. Nothing should be built until they are")
        print("understood.")
        return 1

    water = stage4_confirm_water(url, shapes, style)
    temps = stage5_read_temps(url, shapes, style, water)

    banner("RESULT")
    if temps and len(temps) == len(GRID_POINTS):
        print("SUCCESS — every pier now has its own water temperature,")
        print("read from a model point within walking distance, using only")
        print("built-in Python on a free GitHub Action.")
    elif temps:
        print("PARTIAL — %d of %d piers returned a temperature." % (
            len(temps), len(GRID_POINTS)))
        print("The failures above show their own reasons.")
    else:
        print("FAILED — no temperatures could be read. The errors above are")
        print("the evidence.")

    print()
    print("Settings that worked, for the project notes:")
    print(json.dumps({
        "address_style": style,
        "grid_points": GRID_POINTS,
        "confirmed_points": water,
        "temperatures_f": {k: v["temp_f"] for k, v in temps.items()},
    }, indent=2, sort_keys=True))

    print()
    print("STILL OUTSTANDING: none of the six pier coordinates has been")
    print("verified against a map. The grid points above were calculated")
    print("from them, so an unverified coordinate means an unverified")
    print("grid point. This must be settled before anything reaches the")
    print("public site.")
    return 0 if temps else 1


if __name__ == "__main__":
    sys.exit(main())
