"""
PIERBITE - LMHOFS WATER TEMPERATURE PROBE
File:    lmhofs-water-temp-probe-2026-07-25-v6.py
Created: 2026-07-25 | v6 | Diagnostic only, read-only

LINEAGE - read this before changing anything
--------------------------------------------
v1  proved NOAA's server is reachable from a free GitHub Action.
v2  proved Route B (the full 90,806-point model grid) puts a water
    point within walking distance of every pier. Route A (the sparse
    48-station file) was tested and REJECTED - nearest point to any
    PierBite pier was 45.49 miles. Do not revisit Route A.
v3  recovered the reason v2 could not read temperatures, tested both
    web-address styles, and successfully read all six piers.
v6  is v3 with three changes and nothing else rewritten:
      (a) the six pier coordinates are now VERIFIED, so the grid
          points must be recomputed from them;
      (b) an honesty test against buoy 45210's real thermometer;
      (c) a check that we are reading the surface, not the lake bed.

v4 and v5 were a parallel rebuild that duplicated v3's work. They are
abandoned. This file is the line that continues.

MECHANISM FACTS ALREADY ESTABLISHED - do not rediscover these
-------------------------------------------------------------
1. NOAA's THREDDS server runs on Tomcat. Tomcat rejects RAW square
   brackets in a web address with "HTTP 400 Bad Request". OPeNDAP
   slice requests are full of brackets, so they must be sent escaped
   as %5B and %5D. Requests with no brackets (like "?lon") work
   either way, which is why this bug hides so well. Stage 3 still
   tests both styles and prints the winner - keep that.

2. NOAA does NOT put the word "nowcast" in the field filenames. The
   real pattern is:
       lmhofs.t18z.20260725.fields.n000.nc   <- nowcast (past)
       lmhofs.t18z.20260725.fields.f000.nc   <- forecast (future)
   We want the "n" files. We are reporting what the lake IS doing.

3. OPeNDAP ASCII replies put the variable NAME on one line and the
   NUMBERS on the following line(s), separated by a line of dashes.
   parse_floats() below handles this. It is the reason v1 failed.

4. Adding ".dds" to any OPeNDAP address returns a small text
   description of the file's contents without downloading any data.

SAFETY - UNCHANGED FROM v3
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
FIELDS_FILE = "lmhofs.t{cycle}z.{yyyy}{mm}{dd}.fields.n000.nc"

CYCLES = ["18", "12", "06", "00"]
DAYS_BACK = 3
TIMEOUT = 90
GRID_TIMEOUT = 300
USER_AGENT = "PierBiteDotCom LMHOFS probe (diagnostic, read-only)"

NDBC_BUOY = "45210"
NDBC_TEXT_URL = "https://www.ndbc.noaa.gov/data/realtime2/{s}.txt"
NDBC_TABLE_URL = "https://www.ndbc.noaa.gov/data/stations/station_table.txt"

# ---------------------------------------------------------------
# PIER COORDINATES - VERIFIED 2026-07-25
#
# v3 carried unverified coordinates and said so plainly. Paul checked
# all six against a map on 2026-07-25 and confirmed them. These are
# the pier structures anglers actually stand on.
#
# Algoma note: the confirmed point is the City of Algoma Marina.
# There is no separate pier landmark there - the marina IS where the
# piers are. That is intentional, not an approximation.
# ---------------------------------------------------------------
PIERS = {
    "sheboygan":    {"name": "Sheboygan",    "lat": 43.748595, "lon": -87.694910,
                     "where": "South Pier"},
    "manitowoc":    {"name": "Manitowoc",    "lat": 44.091354, "lon": -87.643820,
                     "where": "South Pier Light"},
    "two_rivers":   {"name": "Two Rivers",   "lat": 44.147061, "lon": -87.565680,
                     "where": "Two Rivers Breakwall"},
    "kewaunee":     {"name": "Kewaunee",     "lat": 44.457285, "lon": -87.493085,
                     "where": "Kewaunee Pierhead Lighthouse"},
    "algoma":       {"name": "Algoma",       "lat": 44.608423, "lon": -87.433597,
                     "where": "City of Algoma Marina"},
    "sturgeon_bay": {"name": "Sturgeon Bay", "lat": 44.792050, "lon": -87.309627,
                     "where": "Ship Canal Pierhead Lighthouse"},
}

# Grid points found by v2 from the OLD unverified coordinates.
# Kept only so this run can show what changed. v6 recomputes them.
OLD_GRID_POINTS = {
    "two_rivers":   24195,
    "manitowoc":    21439,
    "sheboygan":    20329,
    "kewaunee":     28276,
    "algoma":       28904,
    "sturgeon_bay": 31190,
}

BUOY_45210_MILES = 26.6


# ---------------------------------------------------------------
# HELPERS  (unchanged from v3 - proven)
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
# STAGE 1 - locate a live model run  (unchanged from v3)
# ---------------------------------------------------------------

def stage1_find_run():
    banner("STAGE 1  -  Locate a live LMHOFS model run")
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
                if day_offset > 0:
                    print("  NOTE - this data is %d day(s) old." % day_offset)
                print("\n  %s" % url)
                return url, day_offset
            print("  absent  %s   (%s)" % (label, body if not ok else "no header"))
    print("\nFAIL - no model run responded.")
    return None, None


# ---------------------------------------------------------------
# STAGE 2 - learn the real shape of the data  (unchanged from v3)
# ---------------------------------------------------------------

def stage2_learn_shape(url):
    banner("STAGE 2  -  Ask the file how its temperature data is arranged")
    print("Not guessing. Reading the file's own description and taking")
    print("the dimensions from it.\n")

    ok, dds = fetch(url + ".dds", max_chars=60000)
    if not ok:
        print("FAIL - could not read description: %s" % dds)
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
        print("\nFAIL - no temperature variable in this file.")
        return None

    print("\nTemperature dimensions, in order:")
    for name, size in shapes["temp"]:
        print("    %-10s size %d" % (name, size))
    return shapes


# ---------------------------------------------------------------
# STAGE 3 - which address style does the server accept?
# Kept from v3. Now tests with point 0, which always exists, instead
# of a grid point (v6 has not calculated those yet at this stage).
# ---------------------------------------------------------------

def stage3_address_style(url, shapes):
    banner("STAGE 3  -  Find out which address style NOAA's server accepts")
    print("Tomcat rejects raw square brackets. This stage proves which")
    print("form works rather than trusting the note at the top.\n")

    if not shapes.get("lat"):
        print("FAIL - no latitude variable to test with.")
        return None
    plain = "lat[0]"

    for style_name, query in (("ESCAPED  (%5B / %5D)", escape_brackets(plain)),
                              ("PLAIN    ([ / ])", plain)):
        full = "%s.ascii?%s" % (url, query)
        print("Trying %s" % style_name)
        print("  %s" % full)
        ok, body = fetch(full, max_chars=600)
        if ok:
            values = parse_floats(body)
            print("  SUCCESS - server returned: %s" % (values if values else "no numbers"))
            print()
            print("MECHANISM CONFIRMED: NOAA's OPeNDAP server accepts the")
            print("%s style. This is already in the notes at the top of" % style_name.split()[0])
            print("this file. If it ever changes, update that note.")
            return "escaped" if "ESCAPED" in style_name else "plain"
        print("  FAILED - %s\n" % body)

    print("FAIL - neither address style worked. The failure text above is")
    print("the evidence; do not build anything until it is understood.")
    return None


# ---------------------------------------------------------------
# STAGE 4 - NEW IN v6
# Recompute the grid points from the VERIFIED pier coordinates.
#
# This is the slow part: it downloads all 90,806 point positions
# once. Production code must NEVER do this - it uses the frozen
# numbers this stage prints at the end.
# ---------------------------------------------------------------

def stage4_recompute_points(url, buoy_pos):
    banner("STAGE 4  -  Recompute grid points from the VERIFIED coordinates")
    print("v2 calculated its grid points from coordinates nobody had")
    print("checked. Those coordinates have now been verified against a")
    print("map, and two of them moved almost a mile. So the grid points")
    print("have to be worked out again from the corrected positions.")
    print()
    print("Downloading all point positions. This takes a minute or two.")
    print("It happens ONCE. The live site will use the frozen numbers")
    print("printed at the end of this run and never download this again.")
    print()

    ok, body = fetch(url + ".ascii?lon", timeout=GRID_TIMEOUT)
    if not ok:
        print("FAIL - could not download longitudes: %s" % body)
        return None
    lons = parse_floats(body)
    print("  longitudes read: %s" % f"{len(lons):,}")

    ok, body = fetch(url + ".ascii?lat", timeout=GRID_TIMEOUT)
    if not ok:
        print("FAIL - could not download latitudes: %s" % body)
        return None
    lats = parse_floats(body)
    print("  latitudes read:  %s" % f"{len(lats):,}")

    n = min(len(lons), len(lats))
    if n == 0:
        print("FAIL - no coordinates came back.")
        return None
    lons, lats = lons[:n], lats[:n]

    if min(lons) > 180:
        print("  converting longitudes from 0-360 to -180/+180 form")
        lons = [x - 360.0 for x in lons]

    def nearest(lat, lon):
        best_i, best_d = -1, 1e18
        for i in range(n):
            dlat = lats[i] - lat
            dlon = (lons[i] - lon) * 0.71   # cos(45 deg), fine for ranking
            d = dlat * dlat + dlon * dlon
            if d < best_d:
                best_d, best_i = d, i
        return best_i

    print()
    print("%-14s %-9s %-9s %10s" % ("PIER", "OLD PT", "NEW PT", "DIST TO PIER"))
    print("-" * 70)

    points = {}
    for pid, pier in PIERS.items():
        i = nearest(pier["lat"], pier["lon"])
        dist = haversine_miles(pier["lat"], pier["lon"], lats[i], lons[i])
        old = OLD_GRID_POINTS.get(pid)
        flag = "" if old == i else "  <- CHANGED"
        print("%-14s %-9s %-9d %6.3f mi (%d ft)%s" % (
            pier["name"], old if old is not None else "-", i,
            dist, int(dist * 5280), flag))
        points[pid] = {
            "index": i,
            "node_lat": round(lats[i], 5),
            "node_lon": round(lons[i], 5),
            "distance_miles": round(dist, 3),
        }

    if buoy_pos:
        i = nearest(buoy_pos[0], buoy_pos[1])
        dist = haversine_miles(buoy_pos[0], buoy_pos[1], lats[i], lons[i])
        print("%-14s %-9s %-9d %6.3f mi (%d ft)" % (
            "buoy " + NDBC_BUOY, "-", i, dist, int(dist * 5280)))
        points["_buoy"] = {
            "index": i,
            "node_lat": round(lats[i], 5),
            "node_lon": round(lons[i], 5),
            "distance_miles": round(dist, 3),
        }

    return points


# ---------------------------------------------------------------
# STAGE 5 - confirm the points sit in real water  (from v3 stage 4)
# ---------------------------------------------------------------

def ask_value(url, style, query):
    q = escape_brackets(query) if style == "escaped" else query
    ok, body = fetch("%s.ascii?%s" % (url, q), max_chars=2000)
    if not ok:
        return None, body
    vals = parse_floats(body)
    return (vals[-1] if vals else None), None


def stage5_confirm_water(url, shapes, style, points):
    banner("STAGE 5  -  Confirm each grid point sits in real water")
    print("A depth at or near zero would mean the point is on land and")
    print("the whole match is wrong.\n")

    if "h" not in shapes:
        print("SKIPPED - this file has no depth variable.")
        return

    print("%-16s %-9s %12s" % ("POINT", "INDEX", "DEPTH"))
    print("-" * 70)
    for pid, info in points.items():
        label = "buoy " + NDBC_BUOY if pid == "_buoy" else PIERS[pid]["name"]
        depth, err = ask_value(url, style, "h[%d]" % info["index"])
        if depth is None:
            print("%-16s #%-8d could not read (%s)" % (label, info["index"], err))
            continue
        info["depth_ft"] = round(m_to_ft(depth), 1)
        print("%-16s #%-8d %9.1f ft" % (label, info["index"], m_to_ft(depth)))
        if depth <= 0.5:
            print("    WARNING - depth is %.2f m. This point may be on land." % depth)


# ---------------------------------------------------------------
# STAGE 6 - NEW IN v6: are we reading the surface or the lake bed?
#
# The model stacks 20 layers of water at every point. We read layer 0
# and call it the surface. If that were backwards we would publish
# BOTTOM temperature as surface temperature - and it would look
# perfectly reasonable while being completely wrong.
#
# Layer depths are stored as negative fractions: about -0.025 means
# "just under the surface", about -0.975 means "almost on the bed".
# ---------------------------------------------------------------

def stage6_surface_check(url, shapes, style, points):
    banner("STAGE 6  -  Confirm layer 0 is the SURFACE, not the lake bed")
    if "siglay" not in shapes:
        print("SKIPPED - this file has no layer-depth variable.")
        return None

    idx = points["two_rivers"]["index"]
    val, err = ask_value(url, style, "siglay[0][%d]" % idx)
    if val is None:
        print("Could not read the layer depth (%s)." % err)
        print("Treat surface-vs-bottom as UNCONFIRMED.")
        return None

    print("Layer 0 sits at %.3f, where 0 is the surface and -1 is the bed." % val)
    if val > -0.25:
        print("VERDICT: OK - layer 0 is the surface. Safe to use.")
        return True
    print("VERDICT: WARNING - layer 0 looks like the LAKE BED.")
    print("Do NOT publish these numbers as surface temperature.")
    return False


# ---------------------------------------------------------------
# STAGE 7 - read the temperatures  (from v3 stage 5)
# ---------------------------------------------------------------

def build_slots(shapes):
    dims = shapes["temp"]
    n_points = None
    for _name, size in shapes.get("lat", []):
        n_points = size
    if n_points is None:
        n_points = 90806

    slots, explain = [], []
    for name, size in dims:
        low = name.lower()
        if size == n_points:
            slots.append(None)  # filled per point
            explain.append("%s -> the grid point" % name)
        elif low.startswith("time"):
            slots.append(size - 1)
            explain.append("%s -> %d (most recent)" % (name, size - 1))
        elif low.startswith("sig"):
            slots.append(0)
            explain.append("%s -> 0 (surface layer)" % name)
        else:
            slots.append(0)
            explain.append("%s -> 0" % name)
    return slots, explain


def read_temp_at(url, style, slots, index):
    filled = [str(index if s is None else s) for s in slots]
    query = "temp" + "".join("[%s]" % s for s in filled)
    if style == "escaped":
        query = escape_brackets(query)
    ok, body = fetch("%s.ascii?%s" % (url, query), max_chars=2000)
    if not ok:
        return None, body
    vals = parse_floats(body)
    if not vals:
        return None, "no number in reply"
    f = c_to_f(vals[-1])
    if not (25.0 <= f <= 90.0):
        return None, "implausible %.1f F (raw %.3f) - check units" % (f, vals[-1])
    return f, None


def stage7_read_temps(url, shapes, style, points):
    banner("STAGE 7  -  Read the water temperature at each pier")
    slots, explain = build_slots(shapes)
    for line in explain:
        print("  %s" % line)
    if None not in slots:
        print("\nFAIL - could not identify which dimension is the grid point.")
        return {}

    print()
    print("%-14s %-10s %-10s %s" % ("PIER", "MODEL", "DEPTH", "MODEL POINT DISTANCE"))
    print("-" * 70)

    temps = {}
    for pid, info in points.items():
        if pid == "_buoy":
            continue
        f, err = read_temp_at(url, style, slots, info["index"])
        if f is None:
            print("%-14s FAILED - %s" % (PIERS[pid]["name"], err))
            continue
        temps[pid] = f
        print("%-14s %6.1f F   %6s ft   %.3f mi (%d ft)" % (
            PIERS[pid]["name"], f,
            info.get("depth_ft", "?"),
            info["distance_miles"], int(info["distance_miles"] * 5280)))

    if temps:
        vals = list(temps.values())
        spread = max(vals) - min(vals)
        print()
        print("Read %d of %d piers. Spread across piers: %.1f degrees F"
              % (len(temps), len(PIERS), spread))
        if spread < 0.5:
            print("  Nearly identical today. That may simply be the truth on")
            print("  a calm day. Re-run after a westerly blow, when upwelling")
            print("  should push the piers apart.")
        else:
            print("  The piers genuinely differ. This is the entire point:")
            print("  six real numbers instead of one number copied six times.")
    return temps, slots


# ---------------------------------------------------------------
# STAGE 8 - NEW IN v6: the honesty test
#
# Buoy 45210 is the only place on this lake where the model can be
# checked against a real thermometer in the water. If the model
# agrees with it there, the model is worth trusting at the piers.
# ---------------------------------------------------------------

def read_buoy_temp():
    ok, text = fetch(NDBC_TEXT_URL.format(s=NDBC_BUOY), timeout=60)
    if not ok:
        return None, None
    lines = [l for l in text.splitlines() if l.strip()]
    header = None
    for l in lines:
        if l.startswith("#") and "WTMP" in l:
            header = l.lstrip("#").split()
            break
    if not header or "WTMP" not in header:
        return None, None
    i = header.index("WTMP")
    for l in lines:
        if l.startswith("#"):
            continue
        f = l.split()
        if len(f) <= i or f[i] in ("MM", "999.0", "99.0"):
            continue
        try:
            c = float(f[i])
        except ValueError:
            continue
        stamp = "%s-%s-%s %s:%s UTC" % (f[0], f[1], f[2], f[3], f[4])
        return c, stamp
    return None, None


def read_buoy_position():
    ok, text = fetch(NDBC_TABLE_URL, timeout=60)
    if not ok:
        return None
    for line in text.splitlines():
        if not line.startswith(NDBC_BUOY):
            continue
        m = re.search(r"(\d+\.\d+)\s*([NS])\s+(\d+\.\d+)\s*([EW])", line)
        if m:
            lat = float(m.group(1)) * (1 if m.group(2) == "N" else -1)
            lon = float(m.group(3)) * (1 if m.group(4) == "E" else -1)
            return lat, lon
    return None


def stage8_honesty_test(url, style, slots, points, buoy_c, buoy_stamp):
    banner("STAGE 8  -  THE HONESTY TEST: model versus real thermometer")
    if buoy_c is None or "_buoy" not in points:
        print("SKIPPED - buoy reading or position unavailable.")
        return None

    info = points["_buoy"]
    print("Buoy %s is the one place on this lake where the model can be" % NDBC_BUOY)
    print("checked against an actual thermometer sitting in the water.")
    print()
    print("  Buoy observed at ......... %s" % buoy_stamp)
    print("  Nearest model point ...... #%d, %.3f miles away"
          % (info["index"], info["distance_miles"]))
    if "depth_ft" in info:
        print("  Water depth there ........ %.1f ft" % info["depth_ft"])
    print()

    model_f, err = read_temp_at(url, style, slots, info["index"])
    if model_f is None:
        print("  Could not read the model there (%s)." % err)
        return None

    real_f = c_to_f(buoy_c)
    diff = model_f - real_f
    print("  REAL THERMOMETER ......... %.1f F" % real_f)
    print("  MODEL SAYS ............... %.1f F" % model_f)
    print("  DIFFERENCE ............... %+.1f F" % diff)
    print()

    a = abs(diff)
    if a <= 2.0:
        print("  VERDICT: PASS. Within 2 degrees of a real measurement.")
        print("  The model is trustworthy at the piers.")
        return "PASS"
    if a <= 4.0:
        print("  VERDICT: ACCEPTABLE. Within 4 degrees.")
        print("  Usable, but the site must label it Modeled, never Measured.")
        return "ACCEPTABLE"
    print("  VERDICT: FAIL. More than 4 degrees off a real measurement.")
    print("  Do NOT wire this into the live site. Stop and re-plan.")
    return "FAIL"


# ---------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------

def main():
    banner("PIERBITE - LMHOFS PROBE v6")
    print("Run at: %s UTC" % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    print()
    print("READ-ONLY. Cannot affect the live site.")
    print()
    print("Continues v3. v4 and v5 were an abandoned parallel rebuild.")
    print("New here: verified pier coordinates, recomputed grid points,")
    print("a surface-versus-bottom check, and a test of the model against")
    print("buoy %s's real thermometer." % NDBC_BUOY)

    banner("STAGE 0  -  Read buoy %s (the real thermometer)" % NDBC_BUOY)
    buoy_c, buoy_stamp = read_buoy_temp()
    if buoy_c is None:
        print("  Could not read the buoy. The honesty test will be skipped.")
    else:
        print("  Measured water temperature: %.1f C  =  %.1f F"
              % (buoy_c, c_to_f(buoy_c)))
        print("  Observed at: %s" % buoy_stamp)
    buoy_pos = read_buoy_position()
    if buoy_pos:
        print("  Buoy position: %.4f, %.4f" % buoy_pos)
    else:
        print("  Could not find the buoy's position.")

    url, age_days = stage1_find_run()
    if not url:
        return 1

    shapes = stage2_learn_shape(url)
    if not shapes:
        return 1

    style = stage3_address_style(url, shapes)
    if not style:
        banner("RESULT - STOPPED")
        print("The server rejected both address styles. The exact errors are")
        print("printed above. Nothing should be built until they are")
        print("understood.")
        return 1

    points = stage4_recompute_points(url, buoy_pos)
    if not points:
        return 1

    stage5_confirm_water(url, shapes, style, points)
    surface_ok = stage6_surface_check(url, shapes, style, points)
    temps, slots = stage7_read_temps(url, shapes, style, points)
    verdict = stage8_honesty_test(url, style, slots, points, buoy_c, buoy_stamp)

    banner("RESULT")
    if temps and len(temps) == len(PIERS):
        print("SUCCESS - every pier has its own water temperature, read from")
        print("a model point within walking distance, using only built-in")
        print("Python on a free GitHub Action.")
    elif temps:
        print("PARTIAL - %d of %d piers returned a temperature."
              % (len(temps), len(PIERS)))
    else:
        print("FAILED - no temperatures could be read.")

    print()
    print("-" * 70)
    print("FREEZE THESE INTO THE HANDOFF. Copy this whole block.")
    print("Production code uses these numbers and must NEVER download the")
    print("90,806-point grid again.")
    print("-" * 70)
    print(json.dumps({
        "probe": "lmhofs-water-temp-probe-2026-07-25-v6",
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "model_file": url.rsplit("/", 1)[-1],
        "model_data_age_days": age_days,
        "address_style_that_works": style,
        "layer_0_is_surface": surface_ok,
        "temp_request_slots": slots,
        "grid_points": {k: v["index"] for k, v in points.items()},
        "grid_point_detail": points,
        "buoy_measured_f": round(c_to_f(buoy_c), 1) if buoy_c is not None else None,
        "honesty_verdict": verdict,
        "temperatures_f": {k: round(v, 1) for k, v in temps.items()},
    }, indent=2, sort_keys=True))
    print("-" * 70)
    return 0 if temps else 1


if __name__ == "__main__":
    sys.exit(main())
