#!/usr/bin/env python3
# PIERBITE probe | 2026-08-18 | v1 | R59 Fix B research probe
#
# WHAT THIS IS
# ------------
# A READ-ONLY diagnostic. It writes nothing, changes nothing, and is
# not part of the live site. It exists to answer questions that cannot
# be answered from a development sandbox, because NOAA is only
# reachable from inside GitHub Actions.
#
# IT ANSWERS TWO QUESTIONS
#
# QUESTION 1 (the important one) — when LMHOFS "goes down", is the
# MODEL down, or is only the one server we read from down? If a second
# route to the same model exists, that is a far better fix than
# substituting a worse thermometer 26 miles offshore. This probe tries
# every alternate route it can find and reports which ones work.
#
# QUESTION 2 — which water-temperature stations near the six piers are
# actually alive, how stale are they, and which have been pulled from
# the water? This feeds R59, and it is also exactly the data the
# planned "Buoy Status" board on the site would need.
#
# DELIBERATELY NOT GUESSING: for the cloud mirrors this probe LISTS the
# bucket and reads the real directory listings rather than assuming a
# path pattern. A guessed path that 404s would look identical to a
# mirror that does not exist, and those are very different answers.
#
# Standard library only, matching fetch_data.py. No new dependencies.

import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

UA = "PierBiteDotCom (contact: pierbite project owner)"
TIMEOUT = 60

# The node this probe reads. Sheboygan, 0.02 mi from the pier. Frozen
# in fetch_data.py; used here only to prove a route returns a real,
# sane temperature rather than an empty or error body.
TEST_NODE = 20022
TEST_PIER = "sheboygan"

PRIMARY_DIR = ("https://opendap.co-ops.nos.noaa.gov/thredds/dodsC/"
               "NOAA/LMHOFS/MODELS/{yyyy}/{mm}/{dd}/")
NOWCAST_FILE = "lmhofs.t{cycle}z.{yyyy}{mm}{dd}.fields.n000.nc"
CYCLES = ["18", "12", "06", "00"]

# Candidate independent mirrors of the SAME model output. These are
# probed, not trusted — the point is to find out which are real.
NODD_BUCKETS = [
    "https://noaa-nos-ofs-pds.s3.amazonaws.com",
    "https://noaa-ofs-pds.s3.amazonaws.com",
]
NOMADS_ROOTS = [
    "https://nomads.ncep.noaa.gov/pub/data/nccf/com/nos/prod/",
    "https://nomads.ncep.noaa.gov/pub/data/nccf/com/nos/v3.6/",
]

# Water-temperature stations worth knowing about. "role" records why
# each one is in this list so a future reader does not have to guess.
STATIONS = [
    ("45210", "Rawley Point East - open lake, 26 mi offshore", "IN USE - every pier's current fallback"),
    ("45002", "North Michigan - Washington Island area",       "IN USE - Sturgeon Bay second fallback"),
    ("SGNW3", "Sheboygan shore station",                        "IN USE for wind; water temp field is empty"),
    ("KWNW3", "Kewaunee MET",                                   "IN USE for wind; checking for water temp"),
    ("45218", "WSCNMS Sheboygan nearshore buoy",                "CANDIDATE - appears retired/seasonal"),
    ("PWAW3", "Port Washington",                                "CANDIDATE - relevant to future Port Washington pier"),
    ("45013", "Atwater Park, Milwaukee",                        "CANDIDATE - nearest southern nearshore buoy"),
    ("45199", "Salmon Unlimited Wisconsin",                     "CANDIDATE - location unknown, worth identifying"),
    ("MLWW3", "Port of Milwaukee",                              "CANDIDATE - harbor station"),
    ("NPDW3", "Northport Pier at Death's Door",                 "CANDIDATE - north of Sturgeon Bay"),
    ("45214", "South Michigan Spotter",                         "CONTEXT - open lake reference"),
]

NUMBER = re.compile(r"[-+]?\d*\.\d+(?:[eE][-+]?\d+)?|[-+]?\d+(?:[eE][-+]?\d+)?")
BRACKETS = re.compile(r"\[[^\]]*\]")
DIVIDER = re.compile(r"^-{3,}\s*$", re.MULTILINE)


def get(url, max_bytes=200000, timeout=TIMEOUT):
    """One request. Returns (ok, status_or_error, text). Never raises."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(max_bytes)
            code = resp.getcode()
    except Exception as err:  # noqa: BLE001 - any failure means "not available"
        return False, str(err), ""
    return True, code, raw.decode("utf-8", errors="replace")


def opendap_value(file_url, query):
    """Read one value from an OPeNDAP .ascii endpoint."""
    esc = query.replace("[", "%5B").replace("]", "%5D")
    ok, status, body = get("%s.ascii?%s" % (file_url, esc), max_bytes=16000)
    if not ok:
        return None, str(status)
    parts = DIVIDER.split(body)
    tail = parts[-1] if len(parts) > 1 else "\n".join(body.splitlines()[1:])
    tail = BRACKETS.sub(" ", tail)
    vals = []
    for m in NUMBER.finditer(tail):
        try:
            vals.append(float(m.group()))
        except ValueError:
            pass
    if not vals:
        return None, "reply contained no numbers"
    return vals[-1], "ok"


def c_to_f(c):
    return c * 9.0 / 5.0 + 32.0


def sane_water_c(value):
    """Lake Michigan water in Celsius. Catches error codes and junk."""
    return value is not None and -3.0 <= value <= 32.0


def hr():
    print("-" * 68)


# ---------------------------------------------------------------
# PART 1 — the primary route, as production uses it today.
# Establishes the baseline: which cycles exist right now.
# ---------------------------------------------------------------
def probe_primary():
    print("\n" + "=" * 68)
    print("PART 1 - PRIMARY ROUTE (what fetch_data.py uses today)")
    print("=" * 68)
    print("Server: opendap.co-ops.nos.noaa.gov (NOAA CO-OPS THREDDS)")
    print("Walking back through model cycles, newest first.\n")

    now = datetime.now(timezone.utc)
    found = []
    for day_offset in range(0, 3):
        day = now - timedelta(days=day_offset)
        for cycle in CYCLES:
            run = day.replace(hour=int(cycle), minute=0, second=0, microsecond=0)
            if run > now:
                continue
            age = (now - run).total_seconds() / 3600.0
            if age > 48:
                continue
            base = PRIMARY_DIR.format(yyyy=day.strftime("%Y"),
                                      mm=day.strftime("%m"),
                                      dd=day.strftime("%d"))
            fname = NOWCAST_FILE.format(cycle=cycle,
                                        yyyy=day.strftime("%Y"),
                                        mm=day.strftime("%m"),
                                        dd=day.strftime("%d"))
            url = base + fname
            val, note = opendap_value(url, "temp[0][0][%d]" % TEST_NODE)
            if val is not None and sane_water_c(val):
                print("  FOUND  %s %sz  age %4.1fh  %s = %.1fF"
                      % (day.strftime("%Y-%m-%d"), cycle, age, TEST_PIER, c_to_f(val)))
                found.append((run, age, url, c_to_f(val)))
            else:
                print("  absent %s %sz  age %4.1fh  (%s)"
                      % (day.strftime("%Y-%m-%d"), cycle, age, note))
            if len(found) >= 2:
                break
        if len(found) >= 2:
            break

    print()
    if found:
        run, age, url, f = found[0]
        print("VERDICT: primary route is WORKING. Newest run %.1f hours old."
              % age)
        if age > 36:
            print("         NOTE: that is past the 36-hour refusal cliff -")
            print("         production would be refusing this reading today.")
    else:
        print("VERDICT: primary route returned NOTHING usable.")
        print("         This is the R59 failure condition, live right now.")
    return found


# ---------------------------------------------------------------
# PART 2 — alternate route A: an older run's FORECAST covers now.
#
# The nowcast file (n000) is only the moment the run was made. Every
# run also publishes forecast hours. If the newest run is missing but
# yesterday's exists, that older run's forecast for the CURRENT hour
# is still a nearshore model value for this pier - far closer than a
# buoy 26 miles out. Same server, so this does not survive a server
# outage, but it does survive a missed or delayed run, which is the
# more common failure.
# ---------------------------------------------------------------
def probe_forecast_reach():
    print("\n" + "=" * 68)
    print("PART 2 - ALTERNATE A: forecast hours from an older run")
    print("=" * 68)
    print("Question: if today's run is missing, can an older run's")
    print("forecast still cover the current hour?\n")

    now = datetime.now(timezone.utc)
    tested = 0
    working = 0
    for day_offset in (1, 2):
        day = now - timedelta(days=day_offset)
        for cycle in ("12", "00"):
            run = day.replace(hour=int(cycle), minute=0, second=0, microsecond=0)
            lead = int((now - run).total_seconds() / 3600.0)
            if lead < 1 or lead > 47:
                continue
            base = PRIMARY_DIR.format(yyyy=day.strftime("%Y"),
                                      mm=day.strftime("%m"),
                                      dd=day.strftime("%d"))
            fname = ("lmhofs.t%sz.%s.fields.f%03d.nc"
                     % (cycle, day.strftime("%Y%m%d"), lead))
            val, note = opendap_value(base + fname, "temp[0][0][%d]" % TEST_NODE)
            tested += 1
            if val is not None and sane_water_c(val):
                working += 1
                print("  WORKS  run %s %sz, forecast hour f%03d -> %.1fF"
                      % (day.strftime("%Y-%m-%d"), cycle, lead, c_to_f(val)))
            else:
                print("  no     run %s %sz, forecast hour f%03d (%s)"
                      % (day.strftime("%Y-%m-%d"), cycle, lead, note))

    print()
    if working:
        print("VERDICT: forecast reach-back WORKS (%d of %d tested)."
              % (working, tested))
        print("         A missed run need not drop a pier to the offshore buoy.")
    else:
        print("VERDICT: forecast reach-back did NOT work on any file tested.")
        print("         Either the naming differs or the files are not kept.")
    return working > 0


# ---------------------------------------------------------------
# PART 3 — alternate route B: independent cloud mirrors.
#
# These would survive a full CO-OPS server outage. The bucket is
# LISTED rather than guessed, so "no mirror" and "wrong path" cannot
# be confused with each other.
# ---------------------------------------------------------------
def probe_mirrors():
    print("\n" + "=" * 68)
    print("PART 3 - ALTERNATE B: independent cloud mirrors")
    print("=" * 68)
    print("Listing real directory contents - not guessing paths.\n")

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    any_found = False

    for bucket in NODD_BUCKETS:
        print("  Bucket: %s" % bucket)
        url = bucket + "/?list-type=2&max-keys=40&prefix=lmhofs"
        ok, status, body = get(url, max_bytes=60000)
        if not ok:
            print("    unreachable (%s)\n" % status)
            continue
        keys = re.findall(r"<Key>([^<]+)</Key>", body)
        if not keys:
            print("    reachable, but no keys under prefix 'lmhofs'")
            ok2, _, body2 = get(bucket + "/?list-type=2&max-keys=25",
                                max_bytes=60000)
            if ok2:
                tops = sorted({k.split("/")[0]
                               for k in re.findall(r"<Key>([^<]+)</Key>", body2)})
                if tops:
                    print("    top-level prefixes present: %s"
                          % ", ".join(tops[:12]))
            print()
            continue
        any_found = True
        print("    FOUND %d keys. Sample:" % len(keys))
        for k in keys[:8]:
            print("      %s" % k)
        todays = [k for k in keys if today in k]
        print("    keys mentioning today (%s): %d" % (today, len(todays)))
        print()

    for root in NOMADS_ROOTS:
        print("  NOMADS: %s" % root)
        ok, status, body = get(root, max_bytes=60000)
        if not ok:
            print("    unreachable (%s)\n" % status)
            continue
        dirs = sorted(set(re.findall(r'href="(lmhofs[^"]*)"', body)))
        if dirs:
            any_found = True
            print("    FOUND lmhofs directories: %s" % ", ".join(dirs[:8]))
        else:
            other = sorted(set(re.findall(r'href="([a-z0-9]+ofs[^"]*)"', body)))
            print("    reachable, no lmhofs dir. Other OFS present: %s"
                  % (", ".join(other[:8]) if other else "none"))
        print()

    print()
    if any_found:
        print("VERDICT: at least one independent mirror EXISTS.")
        print("         Worth designing a real second route against it.")
        print("         NOTE: mirrors serve whole NetCDF files, not OPeNDAP")
        print("         subsets, so download size must be measured before")
        print("         this is treated as a drop-in replacement.")
    else:
        print("VERDICT: no usable independent mirror found from here.")
        print("         Do not assume one exists - design around this.")
    return any_found


# ---------------------------------------------------------------
# PART 4 — station status survey.
#
# Doubles as the data source for the planned "Buoy Status" board.
# The status rule used here is the clean, documented one:
#   realtime2 file present + recent reading -> ACTIVE
#   realtime2 file present + old reading    -> OFFLINE for N hours
#   realtime2 file missing (404)            -> NOT DEPLOYED / RETIRED
# ---------------------------------------------------------------
def probe_stations():
    print("\n" + "=" * 68)
    print("PART 4 - STATION STATUS SURVEY")
    print("=" * 68)
    print("Also the data model for the planned Buoy Status board.\n")

    now = datetime.now(timezone.utc)
    results = []

    for sid, label, role in STATIONS:
        url = "https://www.ndbc.noaa.gov/data/realtime2/%s.txt" % sid
        ok, status, body = get(url, max_bytes=40000)
        entry = {"station": sid, "label": label, "role": role}

        if not ok:
            # A 404 means NDBC genuinely publishes no live feed for this
            # station - retired, or pulled from the water. ANY OTHER
            # error (403, timeout, DNS, 5xx) means the CHECK failed, not
            # the buoy. Reporting those as "retired" would be a false
            # diagnosis, so they are kept strictly separate.
            if "404" in str(status):
                entry["status"] = "NOT DEPLOYED / RETIRED"
                entry["detail"] = "NDBC publishes no live feed (404)"
            else:
                entry["status"] = "CHECK FAILED"
                entry["detail"] = ("could not reach NDBC (%s) - this says "
                                   "nothing about the buoy" % status)
            entry["water_temp_f"] = None
            results.append(entry)
            print("  %-7s %-24s %s" % (sid, label[:24], entry["status"]))
            continue

        lines = [ln for ln in body.splitlines() if ln and not ln.startswith("#")]
        header = [ln for ln in body.splitlines() if ln.startswith("#")]
        if not lines or not header:
            entry["status"] = "NO DATA"
            entry["detail"] = "feed present but empty"
            entry["water_temp_f"] = None
            results.append(entry)
            print("  %-7s %-24s NO DATA (feed empty)" % (sid, label[:24]))
            continue

        cols = header[0].lstrip("#").split()
        newest = lines[0].split()
        try:
            obs = datetime(int(newest[0]), int(newest[1]), int(newest[2]),
                           int(newest[3]), int(newest[4]), tzinfo=timezone.utc)
            age = (now - obs).total_seconds() / 3600.0
        except (ValueError, IndexError):
            obs, age = None, None

        wtmp_f = None
        wtmp_ever = False
        if "WTMP" in cols:
            idx = cols.index("WTMP")
            if len(newest) > idx and newest[idx] not in ("MM", "999.0", "99.0"):
                try:
                    wtmp_f = c_to_f(float(newest[idx]))
                except ValueError:
                    wtmp_f = None
            for ln in lines[:200]:
                p = ln.split()
                if len(p) > idx and p[idx] not in ("MM", "999.0", "99.0"):
                    wtmp_ever = True
                    break

        if age is None:
            status_txt = "UNKNOWN AGE"
        elif age <= 3:
            status_txt = "ACTIVE"
        elif age <= 48:
            status_txt = "OFFLINE %.0fh" % age
        else:
            status_txt = "STALE %.0f days" % (age / 24.0)

        entry["status"] = status_txt
        entry["age_hours"] = round(age, 1) if age is not None else None
        entry["water_temp_f"] = round(wtmp_f, 1) if wtmp_f is not None else None
        entry["has_water_sensor"] = wtmp_ever
        entry["detail"] = "last obs %s" % (obs.isoformat() if obs else "unknown")
        results.append(entry)

        temp_txt = ("%.1fF" % wtmp_f) if wtmp_f is not None else (
            "no reading now" if wtmp_ever else "NO WATER SENSOR")
        print("  %-7s %-24s %-14s water: %s"
              % (sid, label[:24], status_txt, temp_txt))

    print()
    usable = [r for r in results
              if r.get("water_temp_f") is not None
              and isinstance(r.get("age_hours"), float)
              and r["age_hours"] <= 3]
    failed = [r for r in results if r.get("status") == "CHECK FAILED"]
    retired = [r for r in results if r.get("status") == "NOT DEPLOYED / RETIRED"]

    print("VERDICT: %d station(s) reporting usable water temperature now."
          % len(usable))
    for r in usable:
        print("         %s - %s (%.1fF)"
              % (r["station"], r["label"], r["water_temp_f"]))
    if retired:
        print("         %d station(s) confirmed retired / not deployed: %s"
              % (len(retired), ", ".join(r["station"] for r in retired)))
    if failed:
        print()
        print("         WARNING: %d station(s) could NOT be checked (%s)."
              % (len(failed), ", ".join(r["station"] for r in failed)))
        print("         Those are UNKNOWN, not retired. Treat this run as")
        print("         incomplete and re-run before drawing conclusions.")
    elif len(usable) <= 2:
        print()
        print("         If that list is only the offshore buoys, it confirms")
        print("         there is no nearshore sensor network to fall back on,")
        print("         and Fix B must protect the MODEL rather than replace it.")
    return results


def main():
    print("=" * 68)
    print("PIERBITE - R59 FIX B RESEARCH PROBE  v1")
    print("Run at %s" % datetime.now(timezone.utc).isoformat())
    print("READ-ONLY. Writes nothing. Changes nothing.")
    print("=" * 68)

    primary = probe_primary()
    forecast_ok = probe_forecast_reach()
    mirror_ok = probe_mirrors()
    stations = probe_stations()

    print("\n" + "=" * 68)
    print("SUMMARY - what this run established")
    print("=" * 68)
    print("  Primary OPeNDAP route working ....... %s"
          % ("YES" if primary else "NO"))
    print("  Forecast reach-back available ....... %s"
          % ("YES" if forecast_ok else "NO"))
    print("  Independent cloud mirror found ...... %s"
          % ("YES" if mirror_ok else "NO"))
    live = [s for s in stations
            if s.get("water_temp_f") is not None
            and isinstance(s.get("age_hours"), float)
            and s["age_hours"] <= 3]
    print("  Stations with live water temp ....... %d" % len(live))
    print()
    print("  Copy this entire output back into the chat.")
    print("=" * 68)

    print("\n--- MACHINE-READABLE STATION BLOCK (for the Buoy Status board) ---")
    print(json.dumps(stations, indent=1))

    return 0


if __name__ == "__main__":
    sys.exit(main())
