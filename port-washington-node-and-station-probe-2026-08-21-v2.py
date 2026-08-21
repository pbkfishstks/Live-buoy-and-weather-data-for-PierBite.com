#!/usr/bin/env python3
# PIERBITE probe | 2026-08-21 15:20 UTC | port-washington-node-and-station | v2
# Read-only. Standard library only. Writes nothing, anywhere.
#
# PURPOSE
# Gather every unknown that fetch_data.py v24 (the Port Washington pier
# entry) needs, in ONE GitHub Actions run, so no second research trip is
# required:
#
#   1. The LMHOFS nearshore mesh node for Port Washington, derived from
#      the breakwater light's published position - NOT hand-picked.
#      (C19 / D63: node positions are never written by hand.)
#   2. Proof the derivation method is correct, by re-deriving all SIX
#      existing frozen nodes and requiring an exact match against the
#      numbers live in production today.
#   3. That the new node returns a real water temperature (not a land
#      cell, not NaN).
#   4. The NWS marine zone LMZ644's own published label.
#   5. What water-temperature variables GLOS station 250 actually
#      publishes, read from ERDDAP metadata rather than assumed, plus
#      its most recent reading and how old it is.
#
# WHY THE SELF-CHECK IN STAGE 3 IS THE POINT
# A nearest-node search will always return SOME node. The number it
# prints looks equally confident whether the method is right or wrong.
# The only way to know the method works is to run it against answers
# that are already known to be correct. The six frozen nodes in
# production are exactly that. If all six come back identical, the
# Port Washington number produced by the same code in the same run is
# trustworthy. If even one differs, NOTHING from this run should be
# used - see the FAIL path in Stage 3.
#
# WHAT CHANGED IN v2 - AND WHY IT MATTERS MORE THAN THE FIX
# v1 failed its own Stage 3 self-check in GitHub Actions. The cause was
# in this file, not in NOAA: parse_floats() scanned the WHOLE OPeNDAP
# .ascii response with a plain number regex.
#
# An OPeNDAP .ascii response looks like this:
#
#     Dataset {
#         Float32 lon[node = 90806];
#     } lmhofs.t12z.20260821.fields.n006.nc;
#     ---------------------------------------------
#     lon[90806]
#     272.4, 272.5, 272.6, ...
#
# Everything above the "---" divider is a HEADER, and it is full of
# numbers - 32 from "Float32", 90806 from the dimension, 12 and
# 20260821 and 6 from the filename, 90806 again from the "lon[90806]"
# line. v1 collected all six of those as if they were coordinates,
# which pushed every real value six places to the right and silently
# shifted EVERY node index by six.
#
# The fix is not clever: it is the parser that already existed and was
# already proven, from lmhofs-water-temp-probe-2026-07-25-v6.py, copied
# verbatim rather than reimplemented. It splits on the divider first,
# then strips [...] brackets, then reads numbers. v1's real mistake was
# rewriting a working function from scratch when the working one was
# sitting in the repository.
#
# LESSON WORTH KEEPING: the Stage 3 self-check is what caught this. A
# nearest-node search returns a confident-looking number whether the
# parser is right or wrong. Re-deriving six ALREADY-KNOWN answers is
# the only thing that could tell the difference, and it did. Never
# remove that stage to save time.
#
# COORDINATE SOURCE, STATED PLAINLY
# Port Washington Breakwater Light: 43.38527 N, -87.85965 W.
# Two independent published sources agree to five decimal places
# (Wikipedia's USCG-sourced entry, and Lighthousefriends). This is the
# NORTH breakwater light at the harbour entrance - the primary salmon
# shore spot. It is NOT the same as GLOS station 250's position
# (43.316649, -87.828347), which sits about 5.2 miles offshore to the
# south-southeast. Those two were conflated in an earlier handoff note;
# writing the station's position in as the pier's would have placed the
# pier five miles out in the lake and then reported its wind station as
# "at_pier". Do not merge them.

import json
import math
import re
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------
# Constants copied from the live fetch_data.py v22 so this probe
# reads EXACTLY what production reads. If production changes, this
# probe is stale and must be re-checked before being trusted.
# ---------------------------------------------------------------

LMHOFS_BASE_DIR = (
    "https://opendap.co-ops.nos.noaa.gov/thredds/dodsC/"
    "NOAA/LMHOFS/MODELS/{yyyy}/{mm}/{dd}/"
)
LMHOFS_FIELDS_FILE = "lmhofs.t{cycle}z.{yyyy}{mm}{dd}.fields.n006.nc"
LMHOFS_CYCLES = ["18", "12", "06", "00"]
LMHOFS_EXPECTED_NODE_COUNT = 90806
LMHOFS_MAX_NODE_DRIFT_MI = 2.0

# The six frozen nodes currently live in production. Used ONLY as the
# self-check target in Stage 3. Never edited by this probe.
LIVE_FROZEN_NODES = {
    "sheboygan": 20022,
    "manitowoc": 21438,
    "two_rivers": 23983,
    "kewaunee": 28542,
    "algoma": 28904,
    "sturgeon_bay": 31190,
}

# The six pier positions currently live in production.
LIVE_PIER_COORDS = {
    "sheboygan": (43.748595, -87.694910),
    "manitowoc": (44.091354, -87.643820),
    "two_rivers": (44.147061, -87.565680),
    "kewaunee": (44.457285, -87.493085),
    "algoma": (44.608423, -87.433597),
    "sturgeon_bay": (44.792050, -87.309627),
}

# The candidate new pier.
PW_NAME = "Port Washington Breakwater / Lighthouse"
PW_LAT = 43.38527
PW_LON = -87.85965

# GLOS Seagull ERDDAP - same host and dataset-naming pattern the live
# wind fetcher already uses.
GLOS_DAS_URL = "https://seagull-erddap.glos.org/erddap/tabledap/obs_{ods}.das"
GLOS_CSV_URL = ("https://seagull-erddap.glos.org/erddap/tabledap/"
                "obs_{ods}.csv?{cols}&time>={start}&time<={end}")
# ERDDAP's orderByMax("time") returns exactly one row - the most recent
# in the WHOLE dataset - with no time filter needed. The parentheses and
# quotes must be percent-encoded or the server rejects the address.
GLOS_LATEST_URL = ("https://seagull-erddap.glos.org/erddap/tabledap/"
                   "obs_{ods}.csv?{cols}&orderByMax%28%22time%22%29")
PW_GLOS_DATASET = 250

NWS_ZONE_TEXT_URL = ("https://tgftp.nws.noaa.gov/data/forecasts/marine/"
                     "near_shore/lm/{zone_lower}.txt")
PW_ZONE = "LMZ644"

USER_AGENT = "pierbite-probe (read-only station survey)"
GRID_TIMEOUT = 180
NORMAL_TIMEOUT = 30

FAILURES = []


# ---------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------

def banner(text):
    print()
    print("=" * 68)
    print(text)
    print("=" * 68)


def fail(stage, message):
    FAILURES.append("%s: %s" % (stage, message))
    print("  FAIL - %s" % message)


def haversine_miles(lat1, lon1, lat2, lon2):
    """Great-circle distance in statute miles. Same formula and same
    Earth radius the live file uses, so distances printed here are
    directly comparable to distances the site publishes."""
    radius = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2)
    return 2 * radius * math.asin(math.sqrt(a))


def fetch(url, timeout=NORMAL_TIMEOUT, max_chars=None):
    """GET a URL. Returns (ok, text). On an HTTP error the RESPONSE BODY
    is returned, not the reason phrase - ERDDAP leaves the reason blank
    and puts its real message in the body, which cost this project three
    probe versions to discover once already."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            if max_chars:
                text = text[:max_chars]
            return True, text
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")[:800]
        except Exception:
            body = ""
        return False, "HTTP %s - %s" % (e.code, body.strip() or "(empty body)")
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)


# Copied verbatim from lmhofs-water-temp-probe-2026-07-25-v6.py, which
# derived the six frozen nodes now live in production. Do not "simplify"
# these - see the v2 note at the top of this file for what happens.
_NUMBER = re.compile(r"[-+]?\d*\.\d+(?:[eE][-+]?\d+)?|[-+]?\d+(?:[eE][-+]?\d+)?")
_BRACKETS = re.compile(r"\[[^\]]*\]")
_DIVIDER = re.compile(r"^-{3,}\s*$", re.MULTILINE)


def parse_floats(text):
    """Pull the DATA numbers out of an OPeNDAP .ascii response.

    Three steps, each load-bearing:
      1. Split on the "---" divider and keep only what follows it. The
         header above that line declares types, dimensions and the
         filename, all of which contain digits.
      2. Blank out anything inside square brackets, so an index label
         like "lon[90806]" cannot contribute 90806 as a value.
      3. Only then read numbers.

    Skipping step 1 or 2 does not raise an error. It silently offsets
    every index in the array, which is far worse."""
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


# ---------------------------------------------------------------
# STAGE 1 - find a live LMHOFS run
# ---------------------------------------------------------------

def stage1_find_run():
    banner("STAGE 1  -  Find a published LMHOFS nowcast run")
    print("Walking back through cycles until a file answers. This is the")
    print("same walk production does, reading the same n006 file.")
    print()
    now = datetime.now(timezone.utc)
    for day_offset in (0, 1):
        day = now - timedelta(days=day_offset)
        for cycle in LMHOFS_CYCLES:
            run_time = datetime(day.year, day.month, day.day,
                                int(cycle), 0, 0, tzinfo=timezone.utc)
            if run_time > now:
                continue
            parts = {"yyyy": day.strftime("%Y"), "mm": day.strftime("%m"),
                     "dd": day.strftime("%d"), "cycle": cycle}
            url = (LMHOFS_BASE_DIR.format(**parts)
                   + LMHOFS_FIELDS_FILE.format(**parts))
            print("  trying %sz on %s ..." % (cycle, day.strftime("%Y-%m-%d")))
            ok, body = fetch(url + ".dds", max_chars=4000)
            if ok and "Dataset" in body:
                age = (now - run_time).total_seconds() / 3600.0
                print("  FOUND - run %s, %.1f hours old" %
                      (run_time.isoformat(), age))
                return url, body
    fail("STAGE 1", "no LMHOFS run answered. Nothing downstream can run.")
    return None, None


# ---------------------------------------------------------------
# STAGE 2 - mesh integrity
# ---------------------------------------------------------------

def stage2_mesh_check(dds_text):
    banner("STAGE 2  -  Mesh integrity (guards against renumbering)")
    print("A frozen node index is only meaningful while the mesh has the")
    print("same shape. If NOAA renumbers, node 23983 still returns a")
    print("temperature - just from somewhere else in the lake. So the")
    print("node count is checked before any index is trusted.")
    print()
    node_count = None
    for name, size in re.findall(r"(\w+)\s*=\s*(\d+)", dds_text):
        if name.lower().startswith("node"):
            node_count = int(size)
            break
    if node_count is None:
        fail("STAGE 2", "the file no longer declares a node dimension")
        return False
    print("  nodes declared: %s" % f"{node_count:,}")
    print("  expected:       %s" % f"{LMHOFS_EXPECTED_NODE_COUNT:,}")
    if node_count != LMHOFS_EXPECTED_NODE_COUNT:
        fail("STAGE 2",
             "MESH CHANGED. Every frozen node in production is now suspect. "
             "Stop and investigate before using anything from this run.")
        return False
    print("  PASS - mesh unchanged")
    return True


# ---------------------------------------------------------------
# STAGE 3 - derive nodes, and prove the method on known answers
# ---------------------------------------------------------------

def stage3_derive_nodes(url):
    banner("STAGE 3  -  Derive mesh nodes  (with self-check + adversarial)")
    print("Downloading all %s node positions. Slow, and deliberately so -" %
          f"{LMHOFS_EXPECTED_NODE_COUNT:,}")
    print("this runs ONCE in a probe. Production never does this; it uses")
    print("the frozen index this stage prints.")
    print()

    ok, body = fetch(url + ".ascii?lon", timeout=GRID_TIMEOUT)
    if not ok:
        fail("STAGE 3", "could not download longitudes: %s" % body)
        return None
    lons = parse_floats(body)
    print("  longitudes read: %s" % f"{len(lons):,}")

    ok, body = fetch(url + ".ascii?lat", timeout=GRID_TIMEOUT)
    if not ok:
        fail("STAGE 3", "could not download latitudes: %s" % body)
        return None
    lats = parse_floats(body)
    print("  latitudes read:  %s" % f"{len(lats):,}")

    n = min(len(lons), len(lats))
    if n < LMHOFS_EXPECTED_NODE_COUNT:
        fail("STAGE 3",
             "expected %s coordinate pairs, got %s. Truncated download - "
             "do not trust any node index from this run."
             % (f"{LMHOFS_EXPECTED_NODE_COUNT:,}", f"{n:,}"))
        return None
    lons, lats = lons[:n], lats[:n]

    # LMHOFS publishes longitude in 0-360 form. Anything reading it must
    # subtract 360 or every node lands on the wrong side of the planet.
    if min(lons) > 180:
        print("  converting longitudes from 0-360 to -180/+180 form")
        lons = [x - 360.0 for x in lons]

    def nearest(lat, lon):
        best_i, best_d = -1, 1e18
        for i in range(n):
            dlat = lats[i] - lat
            dlon = (lons[i] - lon) * 0.71   # cos(45 deg), fine for RANKING
            d = dlat * dlat + dlon * dlon
            if d < best_d:
                best_d, best_i = d, i
        return best_i

    # ---- SELF-CHECK: re-derive the six nodes already in production ----
    print()
    print("SELF-CHECK - re-deriving the six nodes already live in")
    print("production. All six must come back identical. This is what")
    print("makes the Port Washington answer below trustworthy.")
    print()
    print("%-14s %-10s %-10s %-9s %s" %
          ("PIER", "LIVE NODE", "DERIVED", "DIST", "VERDICT"))
    print("-" * 68)

    mismatches = 0
    for pid in sorted(LIVE_FROZEN_NODES):
        plat, plon = LIVE_PIER_COORDS[pid]
        i = nearest(plat, plon)
        dist = haversine_miles(plat, plon, lats[i], lons[i])
        expected = LIVE_FROZEN_NODES[pid]
        match = (i == expected)
        if not match:
            mismatches += 1
        print("%-14s %-10d %-10d %6.3f mi  %s" %
              (pid, expected, i, dist, "match" if match else "*** MISMATCH ***"))

    print()
    if mismatches:
        fail("STAGE 3",
             "%d of 6 known nodes did not reproduce. The derivation method "
             "or the mesh is wrong. DO NOT USE the Port Washington number "
             "from this run." % mismatches)
        return None
    print("  PASS - all six known nodes reproduced exactly.")

    # ---- ADVERSARIAL: swapped lat/lon must give an absurd answer ----
    print()
    print("ADVERSARIAL CHECK - feeding the Port Washington coordinates in")
    print("BACKWARDS on purpose. A healthy search should return something")
    print("obviously ridiculous. If this looks reasonable, the distance")
    print("maths is broken and nothing here can be trusted.")
    bad_i = nearest(PW_LON, PW_LAT)          # deliberately swapped
    bad_d = haversine_miles(PW_LAT, PW_LON, lats[bad_i], lons[bad_i])
    print("  swapped input -> node %d, %.0f miles away" % (bad_i, bad_d))
    if bad_d < 100:
        fail("STAGE 3",
             "swapped coordinates produced a plausible %.1f mi result. "
             "The distance calculation is not doing what it claims." % bad_d)
        return None
    print("  PASS - correctly absurd.")

    # ---- THE ACTUAL ANSWER ----
    print()
    print("PORT WASHINGTON - derived from the breakwater light position")
    print()
    pw_i = nearest(PW_LAT, PW_LON)
    pw_dist = haversine_miles(PW_LAT, PW_LON, lats[pw_i], lons[pw_i])
    print("  pier point used : %.5f, %.5f  (%s)" % (PW_LAT, PW_LON, PW_NAME))
    print("  nearest node    : %d" % pw_i)
    print("  node position   : %.5f, %.5f" % (lats[pw_i], lons[pw_i]))
    print("  distance        : %.3f mi  (%d ft)" % (pw_dist, int(pw_dist * 5280)))
    print("  drift guard     : %.1f mi allowed" % LMHOFS_MAX_NODE_DRIFT_MI)

    if pw_dist > LMHOFS_MAX_NODE_DRIFT_MI:
        fail("STAGE 3",
             "the nearest node is %.3f mi from the breakwater - beyond the "
             "%.1f mi guard. Production would refuse this reading. Port "
             "Washington cannot use LMHOFS as configured."
             % (pw_dist, LMHOFS_MAX_NODE_DRIFT_MI))
    else:
        print("  PASS - inside the guard.")

    return {"index": pw_i,
            "node_lat": round(lats[pw_i], 5),
            "node_lon": round(lons[pw_i], 5),
            "distance_mi": round(pw_dist, 3)}


# ---------------------------------------------------------------
# STAGE 4 - does that node hold real water?
# ---------------------------------------------------------------

def stage4_read_temperature(url, node_info):
    banner("STAGE 4  -  Read the new node's temperature")
    if not node_info:
        print("  SKIPPED - Stage 3 did not produce a node.")
        return
    print("A node index that lands on a dry cell or a masked cell will")
    print("still return something. Reading it now proves it holds real")
    print("water before any config is written around it.")
    print()
    idx = node_info["index"]
    # temp[time][siglay][node] - surface layer is siglay 0.
    query = ".ascii?temp[0:1:0][0:1:0][%d:1:%d]" % (idx, idx)
    ok, body = fetch(url + query, max_chars=2000)
    if not ok:
        fail("STAGE 4", "could not read temperature: %s" % body)
        return
    values = parse_floats(body)
    # The response echoes the index numbers too; the temperature is the
    # last plausible-looking value.
    candidates = [v for v in values if -5.0 < v < 40.0]
    if not candidates:
        fail("STAGE 4",
             "no plausible temperature came back. Raw response: %s"
             % body[:300].replace("\n", " "))
        return
    celsius = candidates[-1]
    fahrenheit = celsius * 9.0 / 5.0 + 32.0
    print("  surface temperature: %.2f C  =  %.1f F" % (celsius, fahrenheit))
    if fahrenheit < 32.0 or fahrenheit > 90.0:
        fail("STAGE 4",
             "%.1f F is outside anything Lake Michigan does. Suspect the "
             "node is not in open water." % fahrenheit)
    else:
        print("  PASS - a believable Lake Michigan surface temperature.")


# ---------------------------------------------------------------
# STAGE 5 - the marine zone label
# ---------------------------------------------------------------

def stage5_zone_label():
    banner("STAGE 5  -  NWS marine zone %s" % PW_ZONE)
    print("Reading the zone's own published text. The label goes into the")
    print("ZONES dict verbatim rather than being typed from memory - and")
    print("note this is LMZ644, NOT the similarly-named LMZ643, which is")
    print("Sheboygan's zone and would show Port Washington the wrong")
    print("forecast entirely.")
    print()
    url = NWS_ZONE_TEXT_URL.format(zone_lower=PW_ZONE.lower())
    ok, body = fetch(url, max_chars=3000)
    if not ok:
        fail("STAGE 5", "could not read the zone product: %s" % body)
        return
    lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
    print("  first 12 lines of the product, verbatim:")
    print()
    for line in lines[:12]:
        print("    | %s" % line)
    print()
    print("  Read the zone NAME off the lines above and use it exactly.")
    print("  PASS - product retrieved.")


# ---------------------------------------------------------------
# STAGE 6 - what does GLOS 250 actually publish?
# ---------------------------------------------------------------

def stage6_glos_station():
    banner("STAGE 6  -  GLOS station %d - real variables and freshness"
           % PW_GLOS_DATASET)
    print("An earlier note says station 250 carries water temperature with")
    print("a real thermocline. That is worth having, but the live file has")
    print("NO code path that reads water temperature from GLOS - only wind.")
    print("So this stage establishes what is actually there, from ERDDAP's")
    print("own metadata rather than assumption, for a LATER change.")
    print()

    das_url = GLOS_DAS_URL.format(ods=PW_GLOS_DATASET)
    ok, body = fetch(das_url, max_chars=20000)
    if not ok:
        fail("STAGE 6", "could not read the .das metadata: %s" % body)
        return

    variables = re.findall(r"^\s{4}(\w+)\s*\{", body, re.MULTILINE)
    variables = [v for v in variables if v.lower() != "nc_global"]
    print("  variables published by obs_%d:" % PW_GLOS_DATASET)
    for v in sorted(set(variables)):
        print("    - %s" % v)
    print()

    temp_vars = [v for v in set(variables)
                 if "temp" in v.lower() and "air" not in v.lower()]
    if not temp_vars:
        print("  NOTE: no water-temperature variable found in the metadata.")
        print("  That contradicts the earlier note and should be settled")
        print("  before any GLOS water-temperature work is planned.")
        return
    print("  water-temperature candidates: %s" % ", ".join(sorted(temp_vars)))

    # Units, read rather than assumed.
    for tv in sorted(temp_vars):
        m = re.search(r"%s\s*\{(.*?)\n\s{4}\}" % re.escape(tv), body, re.S)
        if m:
            units = re.search(r'units\s+"([^"]+)"', m.group(1))
            depth = re.search(r'(?:depth|z)\s+"?([-\d.]+)"?', m.group(1))
            print("    %s units=%s%s" % (
                tv,
                units.group(1) if units else "(not declared)",
                "  depth=%s" % depth.group(1) if depth else ""))

    # Most recent row in the whole dataset, no time filter.
    print()
    print("  Asking ERDDAP for the single most recent row (orderByMax):")
    cols = "time," + sorted(temp_vars)[0]
    latest_url = GLOS_LATEST_URL.format(ods=PW_GLOS_DATASET, cols=cols)
    ok, body = fetch(latest_url, max_chars=4000)
    if not ok:
        fail("STAGE 6", "orderByMax query failed: %s" % body)
        return
    rows = [ln for ln in body.strip().split("\n") if ln]
    if len(rows) < 3:
        fail("STAGE 6", "no data row came back. Response: %s" % body[:200])
        return
    cells = rows[2].split(",")
    stamp = cells[0]
    print("    %s" % rows[2])
    try:
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - when).total_seconds() / 86400.0
        print("    last reading is %.1f days old" % age_days)
        if age_days > 7:
            fail("STAGE 6",
                 "station %d has not reported in %.1f days. Treat it as "
                 "OFFLINE regardless of what any status field claims - "
                 "a platform_event of 'activated' meant nothing on buoy "
                 "45218 for 248 days." % (PW_GLOS_DATASET, age_days))
        else:
            print("    PASS - the station is genuinely reporting.")
    except ValueError:
        fail("STAGE 6", "could not parse the timestamp: %s" % stamp)


# ---------------------------------------------------------------
# Summary
# ---------------------------------------------------------------

def main():
    print("PIERBITE - Port Washington node & station probe - v2")
    print("Run at %s" % datetime.now(timezone.utc).isoformat())
    print("READ-ONLY. This script writes no files and changes nothing.")

    url, dds = stage1_find_run()
    node_info = None
    if url:
        if stage2_mesh_check(dds):
            node_info = stage3_derive_nodes(url)
            stage4_read_temperature(url, node_info)
    stage5_zone_label()
    stage6_glos_station()

    banner("SUMMARY")
    if node_info and not any(f.startswith("STAGE 3") for f in FAILURES):
        print("Port Washington LMHOFS node, ready for fetch_data.py v24:")
        print()
        print('    LMHOFS_NODES["port_washington"] = %d' % node_info["index"])
        print()
        print("    node position : %.5f, %.5f"
              % (node_info["node_lat"], node_info["node_lon"]))
        print("    distance      : %.3f mi from the breakwater light"
              % node_info["distance_mi"])
        print()
        print("Pier coordinates to write into PIERS:")
        print('    "lat": %.5f,' % PW_LAT)
        print('    "lon": %.5f,' % PW_LON)
        print()
        print("Do NOT use 43.316649 / -87.828347 here - that is GLOS")
        print("station 250's own position, about 5.2 miles offshore.")
    else:
        print("No node number should be taken from this run.")

    print()
    if FAILURES:
        print("%d CHECK(S) FAILED:" % len(FAILURES))
        for f in FAILURES:
            print("  - %s" % f)
        print()
        print("Do not write v24 until these are understood.")
        sys.exit(1)
    print("ALL CHECKS PASSED.")
    sys.exit(0)


if __name__ == "__main__":
    main()
