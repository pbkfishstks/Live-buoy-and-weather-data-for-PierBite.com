"""
================================================================
PierBite.com - WATER TEMPERATURE MODEL CHECK
File: water-temperature-model-check-2026-07-25-v4.py
Created: 2026-07-25 | v4
================================================================

WHAT THIS SCRIPT DOES (plain English)

We want to start using NOAA's LMHOFS computer model for water
temperature at each pier, because the single offshore buoy we use
today is telling all six piers the same wrong number.

Before we trust a computer model, we should check it against a real
thermometer. There is exactly one place on Lake Michigan where we
can do that: buoy 45210, which floats 26 miles offshore and reports
its own measured water temperature every hour.

So this script does two jobs in one run:

  PART 1 - THE HONESTY TEST
    Ask the model "what is the water temperature at buoy 45210's
    exact location?" and compare that to what the buoy's own
    thermometer says. If they are close, the model is trustworthy.

  PART 2 - THE SIX PIERS, WITH CONFIRMED COORDINATES
    Look up the model's water temperature at each of the six pier
    locations Paul confirmed on the map on 2026-07-25.

THIS SCRIPT ONLY READS AND REPORTS. It writes nothing, changes
nothing, and cannot break the live site.

It uses only Python's built-in libraries - no pip install needed.
================================================================
"""

import json
import math
import re
import ssl
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

# ----------------------------------------------------------------
# CONFIRMED PIER COORDINATES
# Confirmed by Paul against a map on 2026-07-25. These are the
# pier structures themselves (the concrete walkways anglers stand
# on), NOT the town centers and NOT the old satellite sample points
# that are currently sitting in fetch_data.py.
# ----------------------------------------------------------------
PIERS = [
    ("Sheboygan",    43.748595, -87.694910, "South Pier"),
    ("Manitowoc",    44.091354, -87.643820, "South Pier Light"),
    ("Two Rivers",   44.147061, -87.565680, "Two Rivers Breakwall"),
    ("Kewaunee",     44.457285, -87.493085, "Kewaunee Pierhead Lighthouse"),
    ("Algoma",       44.608423, -87.433597, "City of Algoma Marina piers"),
    ("Sturgeon Bay", 44.792050, -87.309627, "Ship Canal Pierhead Lighthouse"),
]

# The old coordinates currently living in fetch_data.py, so the
# report can show how far off they were. None = not present there.
OLD_COORDS = {
    "Sheboygan":    (43.7495, -87.6927),
    "Manitowoc":    (44.0955, -87.6608),
    "Two Rivers":   (44.1499, -87.5698),
    "Kewaunee":     (44.4589, -87.5094),
    "Algoma":       (44.6086, -87.4350),
    "Sturgeon Bay": None,
}

NDBC_BUOY = "45210"
NDBC_TEXT_URL = "https://www.ndbc.noaa.gov/data/realtime2/{s}.txt"
NDBC_TABLE_URL = "https://www.ndbc.noaa.gov/data/stations/station_table.txt"

THREDDS_CATALOG = (
    "https://opendap.co-ops.nos.noaa.gov/thredds/catalog"
    "/NOAA/LMHOFS/MODELS/{y}/{m}/{d}/catalog.xml"
)
THREDDS_DODS = (
    "https://opendap.co-ops.nos.noaa.gov/thredds/dodsC"
    "/NOAA/LMHOFS/MODELS/{y}/{m}/{d}/{fname}"
)

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


def log(msg=""):
    print(msg, flush=True)


def http_get(url, timeout=180):
    req = urllib.request.Request(
        url, headers={"User-Agent": "PierBite-LMHOFS-Probe/4.0"}
    )
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
        return r.read().decode("utf-8", errors="replace")


def c_to_f(c):
    return c * 9.0 / 5.0 + 32.0


def miles_between(lat1, lon1, lat2, lon2):
    """Great-circle distance in statute miles."""
    r = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ----------------------------------------------------------------
# OPeNDAP ASCII PARSING
#
# MECHANISM NOTE (this is the bug that broke probe v1):
# NOAA's OPeNDAP server returns a header block, then a line of
# dashes, then the data. Inside the data section it puts the
# VARIABLE NAME on one line and the NUMBERS on the following
# line(s). Index labels like [0][0] are mixed in too.
#
# The fix used here is deliberately blunt and therefore safe:
# throw away everything before the dashed line, delete anything
# inside square brackets, then keep every remaining token that
# successfully converts to a float. Variable names fail the float
# conversion and are silently dropped.
# ----------------------------------------------------------------
def opendap_values(url):
    text = http_get(url)
    parts = re.split(r"-{10,}", text, maxsplit=1)
    body = parts[1] if len(parts) > 1 else text
    body = re.sub(r"\[[^\]]*\]", " ", body)
    out = []
    for tok in re.split(r"[,\s]+", body):
        if not tok:
            continue
        try:
            out.append(float(tok))
        except ValueError:
            continue
    return out


def opendap_raw(url):
    return http_get(url)


# ----------------------------------------------------------------
# STEP 1 - What does the real buoy thermometer say?
# ----------------------------------------------------------------
def read_buoy_temperature():
    log("STEP 1 - Reading buoy %s's own thermometer" % NDBC_BUOY)
    log("-" * 64)
    try:
        text = http_get(NDBC_TEXT_URL.format(s=NDBC_BUOY), timeout=60)
    except Exception as e:
        log("  FAILED to reach NDBC: %s" % e)
        return None, None

    lines = [l for l in text.splitlines() if l.strip()]
    header = None
    for l in lines:
        if l.startswith("#") and "WTMP" in l:
            header = l.lstrip("#").split()
            break
    if header is None:
        log("  FAILED: could not find the WTMP column in the buoy file.")
        return None, None

    try:
        wtmp_i = header.index("WTMP")
    except ValueError:
        log("  FAILED: WTMP column missing.")
        return None, None

    for l in lines:
        if l.startswith("#"):
            continue
        f = l.split()
        if len(f) <= wtmp_i:
            continue
        raw = f[wtmp_i]
        if raw in ("MM", "999.0", "99.0"):
            continue
        try:
            c = float(raw)
        except ValueError:
            continue
        try:
            obs = datetime(
                int(f[0]), int(f[1]), int(f[2]), int(f[3]), int(f[4]),
                tzinfo=timezone.utc,
            )
        except Exception:
            obs = None
        log("  Buoy %s measured water temperature: %.1f C  =  %.1f F"
            % (NDBC_BUOY, c, c_to_f(c)))
        if obs:
            log("  Observed at: %s UTC" % obs.strftime("%Y-%m-%d %H:%M"))
        return c, obs

    log("  FAILED: no usable water temperature rows in the last readings.")
    return None, None


# ----------------------------------------------------------------
# STEP 2 - Where exactly is buoy 45210?
# ----------------------------------------------------------------
def find_buoy_location():
    log()
    log("STEP 2 - Finding buoy %s's exact position" % NDBC_BUOY)
    log("-" * 64)
    try:
        text = http_get(NDBC_TABLE_URL, timeout=60)
    except Exception as e:
        log("  Could not download NDBC's station table: %s" % e)
        return None, None

    for line in text.splitlines():
        if not line.startswith(NDBC_BUOY):
            continue
        m = re.search(
            r"(\d+\.\d+)\s*([NS])\s+(\d+\.\d+)\s*([EW])", line
        )
        if m:
            lat = float(m.group(1)) * (1 if m.group(2) == "N" else -1)
            lon = float(m.group(3)) * (1 if m.group(4) == "E" else -1)
            log("  Position from NDBC station table: %.4f, %.4f" % (lat, lon))
            return lat, lon

    log("  Buoy %s was not found in NDBC's station table." % NDBC_BUOY)
    return None, None


# ----------------------------------------------------------------
# STEP 3 - Find today's LMHOFS model file
# ----------------------------------------------------------------
def find_model_file():
    log()
    log("STEP 3 - Locating the newest LMHOFS model file")
    log("-" * 64)
    now = datetime.now(timezone.utc)

    for back in (0, 1, 2):
        day = now - timedelta(days=back)
        cat = THREDDS_CATALOG.format(
            y=day.strftime("%Y"), m=day.strftime("%m"), d=day.strftime("%d")
        )
        log("  Checking %s ..." % day.strftime("%Y-%m-%d"))
        try:
            xml = http_get(cat, timeout=90)
        except Exception as e:
            log("    catalog unavailable (%s)" % e)
            continue

        names = re.findall(r'name="([^"]+\.nc)"', xml)
        names = sorted(set(names))
        if not names:
            log("    catalog reached but listed no .nc files")
            continue

        log("    %d files listed. Sample of what NOAA publishes here:" % len(names))
        for n in names[:6]:
            log("      %s" % n)
        if len(names) > 6:
            log("      ... (%d more)" % (len(names) - 6))

        fields = [n for n in names if "fields" in n and "nowcast" in n]
        if not fields:
            fields = [n for n in names if "fields" in n]
        if not fields:
            log("    no 'fields' file here - this day is unusable")
            continue

        chosen = sorted(fields)[-1]
        url = THREDDS_DODS.format(
            y=day.strftime("%Y"), m=day.strftime("%m"),
            d=day.strftime("%d"), fname=chosen,
        )
        log("    USING: %s" % chosen)
        return url, chosen

    log("  FAILED: no usable LMHOFS file found in the last 3 days.")
    return None, None


# ----------------------------------------------------------------
# STEP 4 - Read the model grid
# ----------------------------------------------------------------
def load_grid(base_url):
    log()
    log("STEP 4 - Reading the model's map of Lake Michigan")
    log("-" * 64)

    try:
        dds = opendap_raw(base_url + ".dds")
    except Exception as e:
        log("  FAILED to read the file description: %s" % e)
        return None

    log("  Variables NOAA reports in this file:")
    for line in dds.splitlines():
        s = line.strip()
        if s and not s.startswith(("Dataset", "}", "{")):
            log("    %s" % s)

    m = re.search(r"lon\[\s*node\s*=\s*(\d+)\s*\]", dds)
    if not m:
        m = re.search(r"Float\d+\s+lon\[[^=]*=\s*(\d+)\s*\]", dds)
    if not m:
        log("  FAILED: could not work out how many grid points this file has.")
        return None
    n_nodes = int(m.group(1))
    log("  Grid points (nodes) in this model: %s" % f"{n_nodes:,}")

    log("  Downloading longitude values ...")
    lons = opendap_values(base_url + ".ascii?lon")
    log("  Downloading latitude values ...")
    lats = opendap_values(base_url + ".ascii?lat")

    if len(lons) != n_nodes or len(lats) != n_nodes:
        log("  WARNING: expected %d values, got %d lon / %d lat."
            % (n_nodes, len(lons), len(lats)))
        n = min(len(lons), len(lats))
        if n == 0:
            log("  FAILED: no coordinates came back.")
            return None
        lons, lats = lons[:n], lats[:n]
        n_nodes = n

    # LMHOFS publishes longitude as 0-360 in some files.
    if lons and min(lons) > 180:
        log("  Converting longitudes from 0-360 to -180/+180 form.")
        lons = [x - 360.0 for x in lons]

    log("  Grid loaded. Longitude range %.3f to %.3f, latitude range %.3f to %.3f"
        % (min(lons), max(lons), min(lats), max(lats)))

    depths = None
    if re.search(r"\bh\[", dds):
        log("  Downloading water depth at every grid point ...")
        try:
            depths = opendap_values(base_url + ".ascii?h")
            if len(depths) < n_nodes:
                depths = None
        except Exception as e:
            log("  (depth unavailable: %s)" % e)

    return {"lons": lons, "lats": lats, "n": n_nodes, "depths": depths, "dds": dds}


def nearest_node(grid, lat, lon):
    best_i, best_d = -1, 1e18
    lons, lats = grid["lons"], grid["lats"]
    for i in range(grid["n"]):
        dlat = lats[i] - lat
        dlon = (lons[i] - lon) * 0.71  # cos(45 deg), good enough for ranking
        d = dlat * dlat + dlon * dlon
        if d < best_d:
            best_d, best_i = d, i
    return best_i


# ----------------------------------------------------------------
# STEP 5 - Read water temperature at one grid point
# ----------------------------------------------------------------
def surface_temp_at_node(base_url, node_index, time_index):
    url = (base_url + ".ascii?temp[%d:1:%d][0:1:0][%d:1:%d]"
           % (time_index, time_index, node_index, node_index))
    vals = opendap_values(url)
    vals = [v for v in vals if -5.0 < v < 45.0]
    return vals[-1] if vals else None


def last_time_index(base_url, dds):
    m = re.search(r"time\s*=\s*(\d+)", dds)
    if not m:
        m = re.search(r"\[\s*time\s*=\s*(\d+)\s*\]", dds)
    n = int(m.group(1)) if m else 1
    return n - 1, n


def model_timestamp(base_url, time_index):
    try:
        raw = opendap_raw(
            base_url + ".ascii?Times[%d:1:%d][0:1:25]" % (time_index, time_index)
        )
        m = re.search(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2})", raw)
        if m:
            return m.group(1).replace("T", " ")
    except Exception:
        pass
    return None


# ----------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------
def main():
    log("=" * 64)
    log("PierBite - LMHOFS VALIDATION PROBE v4")
    log("Run started %s UTC" % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))
    log("=" * 64)
    log()

    buoy_c, buoy_time = read_buoy_temperature()
    buoy_lat, buoy_lon = find_buoy_location()

    base_url, fname = find_model_file()
    if not base_url:
        log()
        log("STOPPING. The model file could not be found, so nothing else")
        log("in this probe can run. Nothing was changed.")
        sys.exit(1)

    grid = load_grid(base_url)
    if not grid:
        log()
        log("STOPPING. The model grid could not be read. Nothing was changed.")
        sys.exit(1)

    t_index, t_count = last_time_index(base_url, grid["dds"])
    stamp = model_timestamp(base_url, t_index)
    log()
    log("  This file holds %d time step(s). Using the newest one (index %d)."
        % (t_count, t_index))
    if stamp:
        log("  That time step represents: %s UTC" % stamp)

    # ---------------- PART 1 ----------------
    log()
    log("=" * 64)
    log("PART 1 - THE HONESTY TEST")
    log("Does the model agree with a real thermometer?")
    log("=" * 64)

    if buoy_lat is None or buoy_c is None:
        log("  Could not run the test - the buoy position or reading is missing.")
        log("  PART 2 will still run.")
        verdict = None
    else:
        i = nearest_node(grid, buoy_lat, buoy_lon)
        glat, glon = grid["lats"][i], grid["lons"][i]
        dist = miles_between(buoy_lat, buoy_lon, glat, glon)
        mc = surface_temp_at_node(base_url, i, t_index)

        log("  Buoy position .............. %.4f, %.4f" % (buoy_lat, buoy_lon))
        log("  Nearest model grid point ... %.4f, %.4f  (%.2f miles away)"
            % (glat, glon, dist))
        if grid["depths"]:
            log("  Water depth there .......... %.1f ft"
                % (grid["depths"][i] * 3.28084))
        log()
        if mc is None:
            log("  The model returned no temperature at this point.")
            verdict = None
        else:
            diff = c_to_f(mc) - c_to_f(buoy_c)
            log("  REAL THERMOMETER (buoy) .... %.1f F" % c_to_f(buoy_c))
            log("  MODEL SAYS ................. %.1f F" % c_to_f(mc))
            log("  DIFFERENCE ................. %+.1f F" % diff)
            log()
            a = abs(diff)
            if a <= 2.0:
                verdict = "PASS"
                log("  VERDICT: PASS. Within 2 degrees of a real measurement.")
                log("  The model can be trusted at the piers.")
            elif a <= 4.0:
                verdict = "ACCEPTABLE"
                log("  VERDICT: ACCEPTABLE. Within 4 degrees.")
                log("  Usable, but the site should label it Modeled, never Measured.")
            else:
                verdict = "FAIL"
                log("  VERDICT: FAIL. More than 4 degrees off a real measurement.")
                log("  Do NOT wire this into the live site yet. Stop and re-plan.")

    # ---------------- PART 2 ----------------
    log()
    log("=" * 64)
    log("PART 2 - THE SIX PIERS (confirmed coordinates)")
    log("=" * 64)
    log()

    results = []
    for name, plat, plon, label in PIERS:
        i = nearest_node(grid, plat, plon)
        glat, glon = grid["lats"][i], grid["lons"][i]
        dist = miles_between(plat, plon, glat, glon)
        depth_ft = grid["depths"][i] * 3.28084 if grid["depths"] else None
        mc = surface_temp_at_node(base_url, i, t_index)
        f = c_to_f(mc) if mc is not None else None

        log("%s  (%s)" % (name.upper(), label))
        log("  pier at ................ %.6f, %.6f" % (plat, plon))
        old = OLD_COORDS.get(name)
        if old:
            moved = miles_between(plat, plon, old[0], old[1])
            log("  old coords in backend .. %.4f, %.4f  (%.2f miles away)"
                % (old[0], old[1], moved))
        else:
            log("  old coords in backend .. none on file")
        log("  model grid point ....... %.4f, %.4f  (%.2f miles / %d ft from pier)"
            % (glat, glon, dist, int(dist * 5280)))
        if depth_ft is not None:
            log("  water depth there ...... %.1f ft" % depth_ft)
        if f is not None:
            log("  MODEL WATER TEMP ....... %.1f F" % f)
        else:
            log("  MODEL WATER TEMP ....... unavailable")
        log()

        results.append({
            "pier": name,
            "pier_lat": plat,
            "pier_lon": plon,
            "node_index": i,
            "node_lat": round(glat, 5),
            "node_lon": round(glon, 5),
            "distance_miles": round(dist, 3),
            "depth_ft": round(depth_ft, 1) if depth_ft is not None else None,
            "water_temp_f": round(f, 1) if f is not None else None,
        })

    good = [r["water_temp_f"] for r in results if r["water_temp_f"] is not None]
    log("-" * 64)
    if good:
        log("Spread across the six piers: %.1f F  (coldest %.1f, warmest %.1f)"
            % (max(good) - min(good), min(good), max(good)))
        if buoy_c is not None:
            log("Offshore buoy for comparison: %.1f F" % c_to_f(buoy_c))
            log("Average pier is %.1f F colder than the buoy the site uses today."
                % (c_to_f(buoy_c) - (sum(good) / len(good))))
    log("-" * 64)

    payload = {
        "probe": "water-temperature-model-check-v4",
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "model_file": fname,
        "model_time_index": t_index,
        "model_timestamp": stamp,
        "buoy_id": NDBC_BUOY,
        "buoy_lat": buoy_lat,
        "buoy_lon": buoy_lon,
        "buoy_measured_f": round(c_to_f(buoy_c), 1) if buoy_c is not None else None,
        "validation_verdict": verdict,
        "piers": results,
    }

    log()
    log("=" * 64)
    log("MACHINE-READABLE RESULT (copy this whole block back to Claude)")
    log("=" * 64)
    log(json.dumps(payload, indent=2))
    log("=" * 64)
    log("Probe finished. Nothing was written or changed.")


if __name__ == "__main__":
    main()
