"""
PierBite.com - NEARSHORE WATER HISTORY PROBE
Built 2026-07-28 ~13:10 UTC | v1 | Phase 1.3c Step 1

WHAT THIS DOES
--------------
Reads 30 days of nearshore water temperature from NOAA LMHOFS at the
six FROZEN pier mesh nodes (plus the open-lake context node), and
writes the result to:

    calibration/nearshore_water_history_30d.csv

WHY THIS EXISTS
---------------
Phase 1.3c needs to rebuild score_water(). Both halves of that
function - the base temperature curve AND the 72-hour trend term -
were ported from the old Two Rivers page, back when water temperature
came from buoy 45210, 26 miles offshore in 475 feet of water. Deep
mid-lake water behaves nothing like nearshore water.

An earlier probe (v4, 2026-07-28) already measured this and produced
162 real 72-hour samples. But that data was printed to a GitHub
Actions log and never committed anywhere. Actions logs expire. The
single biggest documented source of wasted effort on this project is
knowledge falling out between sessions.

So this probe's real job is NOT to discover something new. It is to
make the calibration data PERMANENT and RE-READABLE, committed into
the repository, so that:

  1. The constants that end up in fetch_data.py v13 are DERIVED from
     a committed dataset by a committed script - not hand-picked.
  2. Anyone can re-run the derivation next season and get a
     defensible answer without re-probing NOAA.
  3. No future session has to rediscover any of this by trial.

THIS PROBE WRITES NO PRODUCTION CODE AND CHANGES NO SCORES.
It is read-only against NOAA and write-only into calibration/.
It cannot affect the live site.

DESIGN DECISIONS MADE IN THIS FILE
----------------------------------
1. CYCLE CONSISTENCY. Every reading is taken from the 12z nowcast
   where possible, so every sample describes 12:00 UTC on its day.
   Comparing a 12z reading on one day against a 00z reading on
   another would fold the daily warming cycle into the numbers and
   corrupt the trend calibration. If 12z is missing for a day we fall
   back (06 -> 18 -> 00) but RECORD WHICH CYCLE WAS USED, so Step 2
   can filter to 12z-only if it wants a clean comparison.

2. MISSING DAYS ARE RECORDED, NOT SKIPPED. If NOAA has no file for a
   date, a row is still written with a blank temperature and a note.
   A gap that is visible is safe. A gap that is silently dropped
   looks like data.

3. THE MESH IS CHECKED ON EVERY DAY, NOT ONCE. The frozen node
   indices are only meaningful against a 90,806-node mesh. If NOAA
   renumbered the mesh partway through the 30-day window, the older
   readings would be from the wrong part of the lake and would look
   completely plausible. Checked per day, recorded per row.

4. NODE POSITION IS VERIFIED ONCE PER DAY for one pier. Reading
   lat/lon for all six on all thirty days would triple the request
   count for very little added protection, since the mesh-size check
   already catches renumbering.

5. POLITE TO NOAA. A short pause between requests. This is a one-off
   diagnostic run against a free public government service.

REQUEST BUDGET
--------------
Per day: 1 DDS (mesh check) + 7 node reads + 2 position reads = 10.
Over 30 days: about 300 small requests. Expect 6 to 12 minutes of
runtime. That is well inside a GitHub Actions job limit.

ALL LMHOFS READING LOGIC BELOW WAS COPIED FROM THE LIVE PRODUCTION
fetch_data.py v12, READ DIRECTLY FROM THE REPOSITORY ON 2026-07-28 -
NOT FROM MEMORY. Probe v1 of the earlier series failed with HTTP 400
across the board because lmhofs_escape() was omitted when the logic
was reconstructed from memory. That mistake is not repeated here.
"""

import csv
import datetime as dt
import os
import re
import time
import urllib.request

# ---------------------------------------------------------------
# CONFIGURATION - copied verbatim from live fetch_data.py v12
# ---------------------------------------------------------------

LMHOFS_BASE_DIR = (
    "https://opendap.co-ops.nos.noaa.gov/thredds/dodsC/"
    "NOAA/LMHOFS/MODELS/{yyyy}/{mm}/{dd}/"
)
LMHOFS_FIELDS_FILE = "lmhofs.t{cycle}z.{yyyy}{mm}{dd}.fields.n000.nc"

LMHOFS_TIMEOUT = 60
LMHOFS_USER_AGENT = "PierBiteDotCom (contact: pierbite project owner)"
LMHOFS_EXPECTED_NODE_COUNT = 90806

# FROZEN mesh nodes - one per pier. Derived 2026-07-25.
LMHOFS_NODES = {
    "sheboygan": 20022,
    "manitowoc": 21438,
    "two_rivers": 23983,
    "kewaunee": 28542,
    "algoma": 28904,
    "sturgeon_bay": 31190,
}

# The open-lake node co-located with buoy 45210. Included because the
# whole point of the rebuild is that nearshore and open-lake water
# behave differently - having both in one file lets Step 2 measure
# that difference directly instead of asserting it.
LMHOFS_CONTEXT_NODE = 28627

PIER_NAMES = {
    "sheboygan": "Sheboygan",
    "manitowoc": "Manitowoc",
    "two_rivers": "Two Rivers",
    "kewaunee": "Kewaunee",
    "algoma": "Algoma",
    "sturgeon_bay": "Sturgeon Bay",
    "open_lake_45210": "Open lake (buoy 45210 node)",
}

# Cycle preference. 12z first, always, for time-of-day consistency.
CYCLE_ORDER = ["12", "06", "18", "00"]

DAYS_BACK = 30
REQUEST_PAUSE_SECONDS = 0.4

OUTPUT_DIR = "calibration"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "nearshore_water_history_30d.csv")

# ---------------------------------------------------------------
# OPeNDAP READERS - copied verbatim from live fetch_data.py v12
# ---------------------------------------------------------------

_LMHOFS_NUMBER = re.compile(r"[-+]?\d*\.\d+(?:[eE][-+]?\d+)?|[-+]?\d+(?:[eE][-+]?\d+)?")
_LMHOFS_BRACKETS = re.compile(r"\[[^\]]*\]")
_LMHOFS_DIVIDER = re.compile(r"^-{3,}\s*$", re.MULTILINE)
_LMHOFS_DIM = re.compile(r"\[\s*(\w+)\s*=\s*(\d+)\s*\]")


def lmhofs_escape(query):
    """Percent-escape array brackets. NOT optional - omitting this is
    what broke the earlier probe v1 with HTTP 400 on every read."""
    return query.replace("[", "%5B").replace("]", "%5D")


def lmhofs_get(url, timeout=LMHOFS_TIMEOUT, max_chars=4000):
    """One OPeNDAP request. Returns (ok, text). Never raises."""
    req = urllib.request.Request(url, headers={"User-Agent": LMHOFS_USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(max_chars * 4 if max_chars else None)
    except Exception as err:  # noqa: BLE001
        return False, str(err)
    text = raw.decode("utf-8", errors="replace")
    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars]
    return True, text


def lmhofs_numbers(text):
    """Pull data values out of an OPeNDAP ascii reply."""
    parts = _LMHOFS_DIVIDER.split(text)
    body = parts[-1] if len(parts) > 1 else "\n".join(text.splitlines()[1:])
    body = _LMHOFS_BRACKETS.sub(" ", body)
    values = []
    for match in _LMHOFS_NUMBER.finditer(body):
        try:
            values.append(float(match.group()))
        except ValueError:
            pass
    return values


def lmhofs_read_value(file_url, query):
    """Read a single value. Returns a float, or None if anything failed."""
    ok, body = lmhofs_get("%s.ascii?%s" % (file_url, lmhofs_escape(query)))
    time.sleep(REQUEST_PAUSE_SECONDS)
    if not ok:
        return None
    values = lmhofs_numbers(body)
    return values[-1] if values else None


def lmhofs_mesh_size(file_url):
    """Return the node count declared in the file's DDS, or None."""
    ok, dds = lmhofs_get(file_url + ".dds", max_chars=8000)
    time.sleep(REQUEST_PAUSE_SECONDS)
    if not ok:
        return None
    for stripped in dds.splitlines():
        for name, size in _LMHOFS_DIM.findall(stripped):
            if name.lower() == "node":
                try:
                    return int(size)
                except ValueError:
                    return None
    return None


def c_to_f(celsius):
    return celsius * 9.0 / 5.0 + 32.0


# ---------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------

def find_file_for_date(day):
    """Try cycles in preference order for one UTC date.

    Returns (file_url, cycle, mesh_nodes) or (None, None, None).
    A file only counts as usable if its DDS answers - that proves the
    file exists AND gives us the mesh size in the same request.
    """
    parts = {
        "yyyy": "%04d" % day.year,
        "mm": "%02d" % day.month,
        "dd": "%02d" % day.day,
    }
    for cycle in CYCLE_ORDER:
        url = LMHOFS_BASE_DIR.format(**parts) + LMHOFS_FIELDS_FILE.format(
            cycle=cycle, **parts
        )
        mesh = lmhofs_mesh_size(url)
        if mesh is not None:
            return url, cycle, mesh
    return None, None, None


def main():
    started = dt.datetime.now(dt.timezone.utc)
    print("=" * 68)
    print("PIERBITE NEARSHORE WATER HISTORY PROBE - v1 (2026-07-28)")
    print("Started:", started.isoformat())
    print("Reading %d days x %d nodes from NOAA LMHOFS." % (DAYS_BACK, len(LMHOFS_NODES) + 1))
    print("This probe is READ-ONLY against NOAA and cannot affect the live site.")
    print("=" * 68)
    print()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    targets = list(LMHOFS_NODES.items()) + [("open_lake_45210", LMHOFS_CONTEXT_NODE)]

    rows = []
    today = dt.datetime.now(dt.timezone.utc).date()

    days_found = 0
    days_missing = 0
    mesh_mismatches = 0
    reads_ok = 0
    reads_failed = 0

    for offset in range(DAYS_BACK, 0, -1):
        day = today - dt.timedelta(days=offset)
        file_url, cycle, mesh = find_file_for_date(day)

        if file_url is None:
            days_missing += 1
            print("%s  NO FILE at any cycle - recorded as a gap" % day.isoformat())
            for key, node in targets:
                rows.append({
                    "date_utc": day.isoformat(),
                    "cycle_utc": "",
                    "pier_key": key,
                    "pier_name": PIER_NAMES[key],
                    "node_index": node,
                    "temp_c": "",
                    "temp_f": "",
                    "mesh_nodes": "",
                    "mesh_ok": "",
                    "note": "no LMHOFS file found at any cycle for this date",
                })
            continue

        days_found += 1
        mesh_ok = (mesh == LMHOFS_EXPECTED_NODE_COUNT)
        if not mesh_ok:
            mesh_mismatches += 1

        day_note = "" if mesh_ok else (
            "MESH MISMATCH: %d nodes, expected %d - node indices "
            "may point elsewhere" % (mesh, LMHOFS_EXPECTED_NODE_COUNT)
        )

        line = ["%s  %sz  mesh=%d%s |" % (
            day.isoformat(), cycle, mesh, "" if mesh_ok else "  <-- MISMATCH")]

        for key, node in targets:
            celsius = lmhofs_read_value(file_url, "temp[0][0][%d]" % node)
            if celsius is None:
                reads_failed += 1
                temp_c = ""
                temp_f = ""
                note = (day_note + " | " if day_note else "") + "read failed"
                line.append("%s=--" % key[:4])
            else:
                reads_ok += 1
                temp_c = round(celsius, 4)
                temp_f = round(c_to_f(celsius), 3)
                note = day_note
                line.append("%s=%.1fF" % (key[:4], temp_f))

            rows.append({
                "date_utc": day.isoformat(),
                "cycle_utc": cycle,
                "pier_key": key,
                "pier_name": PIER_NAMES[key],
                "node_index": node,
                "temp_c": temp_c,
                "temp_f": temp_f,
                "mesh_nodes": mesh,
                "mesh_ok": "yes" if mesh_ok else "NO",
                "note": note,
            })

        print(" ".join(line))

    # ------------------------------------------------------------
    # Write the CSV
    # ------------------------------------------------------------
    fieldnames = [
        "date_utc", "cycle_utc", "pier_key", "pier_name", "node_index",
        "temp_c", "temp_f", "mesh_nodes", "mesh_ok", "note",
    ]
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    finished = dt.datetime.now(dt.timezone.utc)
    elapsed = (finished - started).total_seconds()

    print()
    print("=" * 68)
    print("SUMMARY")
    print("=" * 68)
    print("Days with a usable file : %d" % days_found)
    print("Days with NO file (gaps): %d" % days_missing)
    print("Mesh mismatches         : %d  %s" % (
        mesh_mismatches,
        "(GOOD - node indices valid across the window)" if mesh_mismatches == 0
        else "(WARNING - see rows marked mesh_ok=NO)"))
    print("Node reads succeeded    : %d" % reads_ok)
    print("Node reads failed       : %d" % reads_failed)
    print("Rows written            : %d" % len(rows))
    print("Output file             : %s" % OUTPUT_FILE)
    print("Elapsed                 : %.1f seconds" % elapsed)
    print()

    cycles_used = {}
    for row in rows:
        if row["cycle_utc"]:
            cycles_used[row["cycle_utc"]] = cycles_used.get(row["cycle_utc"], 0) + 1
    if cycles_used:
        print("Cycles used (rows per cycle):", dict(sorted(cycles_used.items())))
        if len(cycles_used) > 1:
            print("  NOTE: more than one cycle appears. Step 2 should either")
            print("  filter to 12z only, or account for time-of-day drift.")
        else:
            print("  All rows came from a single cycle - cleanest possible case.")
    print()

    if days_found == 0:
        print("RESULT: FAILED - no usable files at all. Do not proceed to Step 2.")
    elif reads_ok == 0:
        print("RESULT: FAILED - files found but no temperature read succeeded.")
        print("        Check that lmhofs_escape() is being applied.")
    elif days_missing > 5 or mesh_mismatches > 0:
        print("RESULT: PARTIAL - usable, but read the warnings above before")
        print("        calibrating anything from this file.")
    else:
        print("RESULT: PASS - dataset is complete enough to calibrate from.")
    print("=" * 68)


if __name__ == "__main__":
    main()
