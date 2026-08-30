#!/usr/bin/env python3
# PIERBITE probe | 2026-08-30 | st-joseph-node-and-station | v1
# Read-only. Standard library only. Writes nothing, anywhere.
#
# PURPOSE
# St. Joseph, Michigan is the candidate EAST-SHORE trial pier. Every
# existing PierBite pier is on the Wisconsin (west) shore. This probe
# gathers, in ONE GitHub Actions run, every unknown a St. Joseph pier
# entry would need, and - just as importantly - CHECKS THE CLAIMS the
# project memory currently records as fact but has never measured:
#
#   MEMORY CLAIM 1: "GLOS station SJOM4 at the pier is dead."
#   MEMORY CLAIM 2: "KBEH airport (~3.5 miles) is the planned wind
#                    source."
#
# Neither has been verified by a run. Stage 6 and Stage 7 test them.
# If SJOM4 turns out to be alive, that is a BETTER answer than KBEH
# and the plan changes. If KBEH is not 3.5 miles away, the published
# distance would be wrong on the live site. Both are worth knowing
# before any code is written.
#
# WHAT THIS PROBE ESTABLISHES
#   1. The LMHOFS nearshore mesh node for St. Joseph, derived from the
#      North Pier lighthouse position - NOT hand-picked. (C19 / D63.)
#   2. Proof the derivation method is correct, by re-deriving all SEVEN
#      nodes already known to be right and requiring exact matches.
#   3. That the new node returns a real water temperature.
#   4. WHICH NWS marine zone St. Joseph belongs to - see the big note
#      below, this is genuinely ambiguous and must not be guessed.
#   5. Whether NDBC station SJOM4 is alive or dead, measured.
#   6. Whether KBEH publishes wind, how fresh it is, and how far it
#      actually is from the pier.
#
# LINEAGE - THIS FILE IS A COPY, NOT A REWRITE
# Stages 1-4 and every helper below are copied VERBATIM from
# port-washington-node-and-station-probe-2026-08-21-v4.py, which passed
# all critical checks and confirmed node 17831 on two independent runs.
# Only the pier constants and Stages 5-7 differ.
#
# That file's own history is the reason for this rule. Its v1, v2 and
# v3 each failed for the SAME cause: rewriting a helper that already
# existed and was already proven.
#   v1: rewrote an OPeNDAP number parser -> every node index shifted 6.
#   v2: rewrote an OPeNDAP request without the bracket escape -> 400.
#   v3: rewrote a .das parser -> a confident, WRONG, negative finding
#       about a live station.
# Three failures, one cause. So: parse_floats(), lmhofs_escape(),
# haversine_miles() and fetch() below are byte-for-byte the versions
# that worked. Do not "simplify" them.
#
# The Port Washington probe also carried normalize_das() and
# parse_das(), for reading GLOS ERDDAP metadata. Those are NOT in this
# file, because St. Joseph's station is an NDBC station and is read
# from NDBC's plain-text realtime feed instead - a different format
# needing a different reader. If a later version of this probe ever
# needs to query GLOS ERDDAP, copy those two functions across from the
# Port Washington file rather than writing new ones.
#
# =====================================================================
# THE MARINE ZONE IS AMBIGUOUS AT ST. JOSEPH - READ THIS
# =====================================================================
# Every Wisconsin pier sits comfortably inside one NWS nearshore zone.
# St. Joseph does not. It sits exactly ON the boundary between two
# zones, issued by two DIFFERENT forecast offices:
#
#   LMZ043  "New Buffalo MI to St Joseph MI"    - NWS Northern Indiana
#   LMZ844  "St Joseph to South Haven MI"       - NWS Grand Rapids
#
# St. Joseph is the named endpoint of BOTH. Picking the wrong one would
# show the pier a forecast for water it is not standing next to, and
# the error would be invisible - both products are real, both mention
# St. Joseph by name, and both look correct at a glance. This is the
# same failure mode as LMZ643-vs-LMZ644 at Port Washington, except that
# there the wrong zone was obviously a different town.
#
# Stage 5 therefore fetches BOTH products and prints both headers side
# by side. It deliberately does NOT choose. A human reads the two and
# decides, and the decision gets written down with its reason.
#
# The north pier is on the NORTH side of the river mouth, which argues
# for LMZ844 (Grand Rapids, waters northward). That is a reasonable
# prior, not evidence. Do not let it substitute for reading Stage 5.
#
# =====================================================================
# COORDINATE SOURCE, STATED PLAINLY
# =====================================================================
# St. Joseph North Pier Lighthouse: 42.11608 N, -86.49362 W.
# Two independent published sources agree:
#   Lighthousefriends  42.11608 / -86.49362
#   us-lighthouses     42.11600 / -86.49400
# Wikipedia's coarser figure (42.12 / -86.49) is consistent with both.
# The two precise sources differ by about 20 metres, well inside the
# mesh spacing, so either would pick the same node. The more precise of
# the two is used.
#
# This is the NORTH pier - the fishable one, reached from Tiscornia
# Park. It is NOT the south pier and NOT the onshore 1832 light site.
#
# WHAT THIS PROBE DOES NOT KNOW
# The live fetch_data.py was not available to this file when it was
# written, so Stage 7 does NOT copy production's airport-wind fetcher -
# it uses the public NWS API directly. That breaks this project's own
# "copy the existing helper" rule, and it is called out here rather
# than hidden: Stage 7 is ADVISORY ONLY. Its findings tell you whether
# KBEH has usable wind at all; they do NOT tell you that production's
# fetcher can read it. Cross-check against fetch_data.py before writing
# any St. Joseph wind config.

import json
import math
import re
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------
# Constants copied from the live fetch_data.py so this probe reads
# EXACTLY what production reads. If production changes, this probe
# is stale and must be re-checked before being trusted.
# ---------------------------------------------------------------

LMHOFS_BASE_DIR = (
    "https://opendap.co-ops.nos.noaa.gov/thredds/dodsC/"
    "NOAA/LMHOFS/MODELS/{yyyy}/{mm}/{dd}/"
)
LMHOFS_FIELDS_FILE = "lmhofs.t{cycle}z.{yyyy}{mm}{dd}.fields.n006.nc"
LMHOFS_CYCLES = ["18", "12", "06", "00"]
LMHOFS_EXPECTED_NODE_COUNT = 90806
LMHOFS_MAX_NODE_DRIFT_MI = 2.0

# The nodes already known to be correct. The six frozen in production
# plus Port Washington's 17831, which two independent probe runs
# derived identically on 2026-08-21 and 2026-08-30. Used ONLY as the
# self-check target in Stage 3. Never edited by this probe.
LIVE_FROZEN_NODES = {
    "sheboygan": 20022,
    "manitowoc": 21438,
    "two_rivers": 23983,
    "kewaunee": 28542,
    "algoma": 28904,
    "sturgeon_bay": 31190,
    "port_washington": 17831,
}

LIVE_PIER_COORDS = {
    "sheboygan": (43.748595, -87.694910),
    "manitowoc": (44.091354, -87.643820),
    "two_rivers": (44.147061, -87.565680),
    "kewaunee": (44.457285, -87.493085),
    "algoma": (44.608423, -87.433597),
    "sturgeon_bay": (44.792050, -87.309627),
    "port_washington": (43.38527, -87.85965),
}

# The candidate new pier - east shore.
SJ_NAME = "St. Joseph North Pier Lighthouse"
SJ_LAT = 42.11608
SJ_LON = -86.49362

# NWS nearshore marine zone text products. BOTH are fetched; see the
# ambiguity note at the top of this file.
NWS_ZONE_TEXT_URL = ("https://tgftp.nws.noaa.gov/data/forecasts/marine/"
                     "near_shore/lm/{zone_lower}.txt")
SJ_ZONE_CANDIDATES = [
    ("LMZ043", "New Buffalo MI to St Joseph MI  (NWS Northern Indiana)"),
    ("LMZ844", "St Joseph to South Haven MI     (NWS Grand Rapids)"),
]

# NDBC realtime feed. SJOM4 is an NDBC-format station id (5 chars,
# M4 = Michigan), NOT a GLOS Seagull obs_<number> dataset - so it is
# probed at NDBC, not at ERDDAP. Getting that wrong would produce a
# 404 and a false "station is dead" conclusion.
NDBC_REALTIME_URL = "https://www.ndbc.noaa.gov/data/realtime2/{sid}.txt"
SJ_NDBC_STATION = "SJOM4"

# NWS API - used for KBEH only, and only advisorily. See the caveat
# at the top of this file.
NWS_API_STATION = "https://api.weather.gov/stations/{sid}"
NWS_API_LATEST = "https://api.weather.gov/stations/{sid}/observations/latest"
SJ_AIRPORT = "KBEH"
SJ_AIRPORT_CLAIMED_MI = 3.5

USER_AGENT = "pierbite-probe (read-only station survey)"
GRID_TIMEOUT = 180
NORMAL_TIMEOUT = 30

FAILURES = []          # CRITICAL - the node cannot be trusted
ADVISORIES = []        # non-fatal - supplementary research only

# THIS IS A FIRST RUN. There is no previous St. Joseph node to
# reproduce, so there is no reproducibility check in Stage 3 - and its
# absence is stated rather than quietly skipped. ONE clean run is NOT
# enough to freeze a node into fetch_data.py. Port Washington was
# frozen only after two independent runs agreed. St. Joseph must clear
# the same bar: run this probe a second time on a different day, on a
# different LMHOFS cycle, and require the same number.


# ---------------------------------------------------------------
# Small helpers - copied verbatim from the Port Washington v4 probe
# ---------------------------------------------------------------

def banner(text):
    print()
    print("=" * 68)
    print(text)
    print("=" * 68)


def fail(stage, message):
    """CRITICAL - something that makes the node number untrustworthy."""
    FAILURES.append("%s: %s" % (stage, message))
    print("  FAIL (critical) - %s" % message)


def advise(stage, message):
    """ADVISORY - supplementary research that did not come back. Does
    NOT fail the run. Stages 5, 6 and 7 gather context for a LATER
    change; they cannot invalidate a node index derived and
    self-checked in Stage 3, and must never be allowed to hide one."""
    ADVISORIES.append("%s: %s" % (stage, message))
    print("  NOTE (advisory) - %s" % message)


def lmhofs_escape(query):
    """Percent-escape array brackets. NOT optional.

    NOAA's THREDDS server runs on Tomcat, which returns HTTP 400 for a
    raw "[" or "]" anywhere in a query string. Copied from the live
    fetch_data.py rather than rewritten - rewriting it is what broke
    the Port Washington probe's v2. This hides well: requests with no
    brackets (?lat, ?lon) work either way, so code looks healthy right
    up until the first real data slice."""
    return query.replace("[", "%5B").replace("]", "%5D")


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
# these - see the lineage note at the top of this file.
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

    # ---- SELF-CHECK: re-derive the nodes already known to be right ----
    print()
    print("SELF-CHECK - re-deriving the %d nodes already known to be"
          % len(LIVE_FROZEN_NODES))
    print("correct. All of them must come back identical. This is what")
    print("makes the St. Joseph answer below trustworthy.")
    print()
    print("NOTE ON EAST SHORE: every known node below is on the WISCONSIN")
    print("side. St. Joseph is the first east-shore point this method has")
    print("been asked for. The self-check proves the method, not that the")
    print("mesh is equally dense on the Michigan shore - Stage 3's drift")
    print("guard and Stage 4's temperature read cover that.")
    print()
    print("%-18s %-10s %-10s %-9s %s" %
          ("PIER", "KNOWN NODE", "DERIVED", "DIST", "VERDICT"))
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
        print("%-18s %-10d %-10d %6.3f mi  %s" %
              (pid, expected, i, dist, "match" if match else "*** MISMATCH ***"))

    print()
    if mismatches:
        fail("STAGE 3",
             "%d of %d known nodes did not reproduce. The derivation method "
             "or the mesh is wrong. DO NOT USE the St. Joseph number from "
             "this run." % (mismatches, len(LIVE_FROZEN_NODES)))
        return None
    print("  PASS - all %d known nodes reproduced exactly."
          % len(LIVE_FROZEN_NODES))

    # ---- ADVERSARIAL: swapped lat/lon must give an absurd answer ----
    print()
    print("ADVERSARIAL CHECK - feeding the St. Joseph coordinates in")
    print("BACKWARDS on purpose. A healthy search should return something")
    print("obviously ridiculous. If this looks reasonable, the distance")
    print("maths is broken and nothing here can be trusted.")
    bad_i = nearest(SJ_LON, SJ_LAT)          # deliberately swapped
    bad_d = haversine_miles(SJ_LAT, SJ_LON, lats[bad_i], lons[bad_i])
    print("  swapped input -> node %d, %.0f miles away" % (bad_i, bad_d))
    if bad_d < 100:
        fail("STAGE 3",
             "swapped coordinates produced a plausible %.1f mi result. "
             "The distance calculation is not doing what it claims." % bad_d)
        return None
    print("  PASS - correctly absurd.")

    # ---- THE ACTUAL ANSWER ----
    print()
    print("ST. JOSEPH - derived from the North Pier lighthouse position")
    print()
    sj_i = nearest(SJ_LAT, SJ_LON)
    sj_dist = haversine_miles(SJ_LAT, SJ_LON, lats[sj_i], lons[sj_i])
    print("  pier point used : %.5f, %.5f  (%s)" % (SJ_LAT, SJ_LON, SJ_NAME))
    print("  nearest node    : %d" % sj_i)
    print("  node position   : %.5f, %.5f" % (lats[sj_i], lons[sj_i]))
    print("  distance        : %.3f mi  (%d ft)" % (sj_dist, int(sj_dist * 5280)))
    print("  drift guard     : %.1f mi allowed" % LMHOFS_MAX_NODE_DRIFT_MI)

    print()
    print("  REPRODUCIBILITY - THERE IS NONE YET. This is the FIRST run")
    print("  for St. Joseph, so there is no previous number to agree")
    print("  with. Port Washington was frozen only after two independent")
    print("  runs matched. Do NOT write this number into fetch_data.py")
    print("  until a second run, on a different day and cycle, produces")
    print("  the identical index.")

    if sj_dist > LMHOFS_MAX_NODE_DRIFT_MI:
        fail("STAGE 3",
             "the nearest node is %.3f mi from the pier - beyond the %.1f mi "
             "guard. Production would refuse this reading. St. Joseph cannot "
             "use LMHOFS as configured."
             % (sj_dist, LMHOFS_MAX_NODE_DRIFT_MI))
    else:
        print()
        print("  PASS - inside the guard.")

    return {"index": sj_i,
            "node_lat": round(lats[sj_i], 5),
            "node_lon": round(lons[sj_i], 5),
            "distance_mi": round(sj_dist, 3)}


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
    query = lmhofs_escape(".ascii?temp[0:1:0][0:1:0][%d:1:%d]" % (idx, idx))
    print("  escaped query: %s" % query)
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
# STAGE 5 - WHICH marine zone? (deliberately does not choose)
# ---------------------------------------------------------------

def stage5_zone_label():
    banner("STAGE 5  -  NWS marine zone - TWO CANDIDATES, NOT ONE")
    print("St. Joseph sits ON the boundary between two nearshore zones,")
    print("issued by two different forecast offices. It is the named")
    print("endpoint of BOTH. Picking the wrong one shows the pier a")
    print("forecast for water it is not standing next to, and the error")
    print("is invisible - both products are real and both say the words")
    print("'St Joseph'.")
    print()
    print("This stage does NOT decide. It prints both so a human can.")
    print()

    retrieved = 0
    for zone, description in SJ_ZONE_CANDIDATES:
        print("-" * 68)
        print("CANDIDATE %s  -  %s" % (zone, description))
        print("-" * 68)
        url = NWS_ZONE_TEXT_URL.format(zone_lower=zone.lower())
        ok, body = fetch(url, max_chars=3000)
        if not ok:
            advise("STAGE 5",
                   "could not read %s: %s" % (zone, body))
            print()
            continue
        retrieved += 1
        lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
        for line in lines[:14]:
            print("    | %s" % line)
        print()

    if retrieved == 0:
        advise("STAGE 5",
               "neither candidate zone product could be read. The zone "
               "question is still open.")
        return

    print("=" * 68)
    print("DECISION REQUIRED - do not skip this")
    print("=" * 68)
    print("Read the two products above and pick the zone whose stated")
    print("water actually fronts the NORTH pier at 42.11608 / -86.49362.")
    print()
    print("The pier is on the NORTH side of the river mouth, which is a")
    print("reason to lean toward LMZ844 (Grand Rapids, waters northward).")
    print("That is a PRIOR, not evidence. The products above are the")
    print("evidence. Write the chosen zone into the memory document")
    print("together with the sentence that justified it, so the next")
    print("session does not re-litigate this.")
    print()
    print("  PASS - %d of %d candidate products retrieved."
          % (retrieved, len(SJ_ZONE_CANDIDATES)))


# ---------------------------------------------------------------
# STAGE 6 - is SJOM4 actually dead? (tests a memory claim)
# ---------------------------------------------------------------

def stage6_ndbc_station():
    banner("STAGE 6  -  NDBC station %s - alive or dead?" % SJ_NDBC_STATION)
    print("The project memory records, as settled fact, that the station")
    print("at the St. Joseph pier is dead. That has never been measured.")
    print("This stage measures it.")
    print()
    print("WHY THE OUTCOME MATTERS EITHER WAY:")
    print("  DEAD  - confirms the plan to fall back to KBEH airport wind,")
    print("          about 3.5 miles inland, which must then be labelled")
    print("          honestly on the site as a non-pier reading.")
    print("  ALIVE - a live sensor AT the pier beats an airport 3.5 miles")
    print("          away, and the whole St. Joseph wind plan changes.")
    print("          Do not discard this finding because it is")
    print("          inconvenient.")
    print()
    print("%s is an NDBC-format id, so it is probed at NDBC's realtime"
          % SJ_NDBC_STATION)
    print("feed - NOT at GLOS ERDDAP. Asking ERDDAP for it would 404 and")
    print("look exactly like 'the station is dead'. It is not the same")
    print("thing.")
    print()

    url = NDBC_REALTIME_URL.format(sid=SJ_NDBC_STATION)
    print("  fetching: %s" % url)
    ok, body = fetch(url, max_chars=6000)

    if not ok:
        print()
        print("  Response: %s" % body)
        print()
        if "404" in body:
            print("  READ THIS CAREFULLY. A 404 means NDBC publishes no")
            print("  realtime file for %s right now. That is CONSISTENT"
                  % SJ_NDBC_STATION)
            print("  with the station being dead, but it is not the same")
            print("  as proof - NDBC also drops the file for seasonal")
            print("  stations that are simply out of the water, and for")
            print("  stations whose id was retyped wrong.")
            advise("STAGE 6",
                   "%s returned 404 at NDBC realtime2. Consistent with the "
                   "'dead station' claim in memory, but confirm the id and "
                   "check the NDBC station page before recording it as "
                   "settled." % SJ_NDBC_STATION)
        else:
            advise("STAGE 6",
                   "%s could not be read: %s" % (SJ_NDBC_STATION, body))
        return

    lines = [ln.rstrip() for ln in body.split("\n") if ln.strip()]
    if len(lines) < 3:
        advise("STAGE 6",
               "%s returned a file with fewer than 3 lines - a header with "
               "no observations. Treat as not reporting."
               % SJ_NDBC_STATION)
        print("  raw: %s" % body[:300].replace("\n", " | "))
        return

    print()
    print("  first 5 lines of the realtime file, verbatim:")
    print()
    for line in lines[:5]:
        print("    | %s" % line)
    print()

    # NDBC realtime2 format: line 0 is column names beginning with #YY,
    # line 1 is units, line 2 onward are observations, newest first.
    header = lines[0].lstrip("#").split()
    newest = lines[2].split()
    if len(newest) < 5:
        advise("STAGE 6",
               "the newest row of %s has too few fields to read a "
               "timestamp." % SJ_NDBC_STATION)
        return

    try:
        yy, mm, dd, hh, mn = (int(newest[0]), int(newest[1]), int(newest[2]),
                              int(newest[3]), int(newest[4]))
        when = datetime(yy, mm, dd, hh, mn, tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - when).total_seconds() / 3600.0
        print("  newest observation : %s" % when.isoformat())
        print("  age                : %.1f hours" % age_hours)
        print()
        if age_hours <= 6:
            print("  *** %s IS REPORTING. ***" % SJ_NDBC_STATION)
            print("  The memory document's claim that this station is dead")
            print("  is CONTRADICTED by this run. Do not proceed with the")
            print("  KBEH plan until this is resolved. Correct the memory")
            print("  document either way.")
            advise("STAGE 6",
                   "%s IS reporting (%.1f h old). This contradicts the "
                   "recorded claim that it is dead. The St. Joseph wind "
                   "source decision must be reopened."
                   % (SJ_NDBC_STATION, age_hours))
        else:
            print("  Not reporting recently. Consistent with 'dead', though")
            print("  a long gap can also mean seasonal removal.")
            advise("STAGE 6",
                   "%s last reported %.1f hours ago. Consistent with the "
                   "'dead station' claim." % (SJ_NDBC_STATION, age_hours))
    except (ValueError, IndexError) as e:
        advise("STAGE 6",
               "could not parse the newest timestamp from %s: %s"
               % (SJ_NDBC_STATION, e))
        return

    # What does it actually measure?
    wind_cols = [c for c in header if c.upper() in ("WDIR", "WSPD", "GST")]
    print("  wind columns present : %s"
          % (", ".join(wind_cols) if wind_cols else "(none)"))
    if not wind_cols:
        advise("STAGE 6",
               "%s publishes no WDIR/WSPD columns, so even if it is alive "
               "it cannot supply wind." % SJ_NDBC_STATION)

    print()
    print("  (station coordinates are not in the realtime file; if this")
    print("   station is alive, get its position from its NDBC station")
    print("   page and compute the real pier distance before publishing")
    print("   any 'at pier' claim - see Q-WIND-LOCALITY-THRESHOLD.)")


# ---------------------------------------------------------------
# STAGE 7 - KBEH airport wind (ADVISORY ONLY - see caveat at top)
# ---------------------------------------------------------------

def stage7_airport_wind():
    banner("STAGE 7  -  %s airport wind  (ADVISORY ONLY)" % SJ_AIRPORT)
    print("CAVEAT, STATED UP FRONT: this stage does NOT use production's")
    print("airport-wind fetcher, because fetch_data.py was not available")
    print("to this file when it was written. It queries the public NWS")
    print("API directly instead.")
    print()
    print("That breaks this project's own 'copy the existing helper'")
    print("rule - the rule whose violation caused three consecutive")
    print("failures in the Port Washington probe. So the result below")
    print("tells you whether %s HAS usable wind. It does NOT tell you"
          % SJ_AIRPORT)
    print("that production can read it. Cross-check against")
    print("fetch_data.py before writing any St. Joseph wind config.")
    print()

    # --- station metadata: where is it, really? ---
    url = NWS_API_STATION.format(sid=SJ_AIRPORT)
    ok, body = fetch(url, max_chars=8000)
    if not ok:
        advise("STAGE 7",
               "could not read %s station metadata: %s" % (SJ_AIRPORT, body))
    else:
        try:
            data = json.loads(body)
            coords = data.get("geometry", {}).get("coordinates", [])
            name = data.get("properties", {}).get("name", "(no name given)")
            if len(coords) >= 2:
                alon, alat = float(coords[0]), float(coords[1])
                dist = haversine_miles(SJ_LAT, SJ_LON, alat, alon)
                print("  station name    : %s" % name)
                print("  station position: %.5f, %.5f" % (alat, alon))
                print("  distance to pier: %.2f mi" % dist)
                print("  memory claims   : ~%.1f mi" % SJ_AIRPORT_CLAIMED_MI)
                print()
                if abs(dist - SJ_AIRPORT_CLAIMED_MI) > 1.0:
                    print("  The recorded ~%.1f mi is off by more than a mile."
                          % SJ_AIRPORT_CLAIMED_MI)
                    print("  Publish the MEASURED distance, not the")
                    print("  remembered one.")
                    advise("STAGE 7",
                           "%s is %.2f mi from the pier, not the ~%.1f mi "
                           "recorded in memory. Correct the memory document."
                           % (SJ_AIRPORT, dist, SJ_AIRPORT_CLAIMED_MI))
                else:
                    print("  PASS - measured distance agrees with the note.")
            else:
                advise("STAGE 7",
                       "%s metadata had no coordinates." % SJ_AIRPORT)
        except (ValueError, TypeError) as e:
            advise("STAGE 7",
                   "could not parse %s metadata: %s" % (SJ_AIRPORT, e))

    # --- latest observation: is there wind, and how fresh? ---
    print()
    url = NWS_API_LATEST.format(sid=SJ_AIRPORT)
    ok, body = fetch(url, max_chars=8000)
    if not ok:
        advise("STAGE 7",
               "could not read %s latest observation: %s" % (SJ_AIRPORT, body))
        return
    try:
        props = json.loads(body).get("properties", {})
    except (ValueError, TypeError) as e:
        advise("STAGE 7", "could not parse %s observation: %s"
               % (SJ_AIRPORT, e))
        return

    stamp = props.get("timestamp")
    wdir = (props.get("windDirection") or {}).get("value")
    wspd = (props.get("windSpeed") or {}).get("value")
    wunit = (props.get("windSpeed") or {}).get("unitCode", "?")

    print("  timestamp       : %s" % stamp)
    print("  windDirection   : %s" % wdir)
    print("  windSpeed       : %s  (%s)" % (wspd, wunit))
    print()

    if wspd is None and wdir is None:
        advise("STAGE 7",
               "%s's latest observation carries neither wind speed nor "
               "direction. It cannot be a wind source as-is."
               % SJ_AIRPORT)
        return

    if stamp:
        try:
            when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            age_hours = ((datetime.now(timezone.utc) - when)
                         .total_seconds() / 3600.0)
            print("  age             : %.1f hours" % age_hours)
            if age_hours > 3:
                advise("STAGE 7",
                       "%s's newest observation is %.1f hours old. An hourly "
                       "wind history built from this would have gaps."
                       % (SJ_AIRPORT, age_hours))
            else:
                print("  PASS - %s is reporting current wind." % SJ_AIRPORT)
        except ValueError:
            advise("STAGE 7", "could not parse timestamp: %s" % stamp)

    print()
    print("  REMEMBER Q-LIGHT-WIND-FLOOR: some stations never emit exactly")
    print("  0.0 mph, so the calm-hour fix does nothing for them. Whether")
    print("  %s does is a separate question this stage does not answer."
          % SJ_AIRPORT)
    print("  Do not assign a threshold without evidence from the archive.")


# ---------------------------------------------------------------
# Summary
# ---------------------------------------------------------------

def main():
    print("PIERBITE - St. Joseph MI node & station probe - v1")
    print("Run at %s" % datetime.now(timezone.utc).isoformat())
    print("READ-ONLY. This script writes no files and changes nothing.")
    print()
    print("FIRST east-shore pier ever probed for this project.")

    url, dds = stage1_find_run()
    node_info = None
    if url:
        if stage2_mesh_check(dds):
            node_info = stage3_derive_nodes(url)
            stage4_read_temperature(url, node_info)
    stage5_zone_label()
    stage6_ndbc_station()
    stage7_airport_wind()

    banner("SUMMARY")
    if node_info and not any(f.startswith("STAGE 3") for f in FAILURES):
        print("St. Joseph LMHOFS node - CANDIDATE, NOT YET SAFE TO FREEZE:")
        print()
        print('    LMHOFS_NODES["st_joseph"] = %d   # NEEDS A SECOND RUN'
              % node_info["index"])
        print()
        print("    node position : %.5f, %.5f"
              % (node_info["node_lat"], node_info["node_lon"]))
        print("    distance      : %.3f mi from the North Pier lighthouse"
              % node_info["distance_mi"])
        print()
        print("Pier coordinates to write into PIERS:")
        print('    "lat": %.5f,' % SJ_LAT)
        print('    "lon": %.5f,' % SJ_LON)
        print()
        print("WHY 'NOT YET SAFE TO FREEZE': this is one run. Port")
        print("Washington's node was written into production only after")
        print("two independent runs derived it identically. Run this probe")
        print("again on a different day, against a different LMHOFS cycle,")
        print("and require the same index before touching fetch_data.py.")
        print()
        print("STILL UNDECIDED after this run:")
        print("  - The marine zone. Stage 5 printed two candidates on")
        print("    purpose and did not choose. Read them and decide.")
        print("  - The wind source, if Stage 6 found %s alive."
              % SJ_NDBC_STATION)
    else:
        print("No node number should be taken from this run.")

    print()
    if ADVISORIES:
        print("%d ADVISORY NOTE(S) - supplementary research only."
              % len(ADVISORIES))
        print("These do NOT affect the node number above, but several of")
        print("them may contradict what the memory document currently")
        print("records as fact. Read them.")
        for a in ADVISORIES:
            print("  - %s" % a)
        print()

    if FAILURES:
        print("%d CRITICAL CHECK(S) FAILED:" % len(FAILURES))
        for f in FAILURES:
            print("  - %s" % f)
        print()
        print("Do not write any St. Joseph config until these are")
        print("understood.")
        sys.exit(1)

    print("ALL CRITICAL CHECKS PASSED.")
    if ADVISORIES:
        print("Advisory notes above are worth reading but block nothing.")
    sys.exit(0)


if __name__ == "__main__":
    main()
