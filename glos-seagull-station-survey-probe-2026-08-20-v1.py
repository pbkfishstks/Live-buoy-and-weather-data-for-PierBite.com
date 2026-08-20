#!/usr/bin/env python3
# PIERBITE probe | 2026-08-20 | v1 | GLOS SEAGULL STATION SURVEY
#
# ============================================================================
# WHAT THIS IS
# ============================================================================
# A READ-ONLY diagnostic probe. It runs in GitHub Actions, prints a report,
# and stops. It does NOT:
#   - write data.json
#   - touch fetch_data.py
#   - change anything on the live site
#   - cost money
#
# All it does is ask the GLOS Seagull API some questions and print the
# answers. Safe to run as many times as you like. Safe to leave in the
# repository permanently.
#
# ============================================================================
# WHY THIS EXISTS
# ============================================================================
# On 2026-08-19 Paul found "Neshotah Park Met Station" on GLOS Seagull -
# a live weather station essentially ON the Two Rivers pier. Two Rivers
# currently takes its wind from Manitowoc Airport, 5.9 miles inland.
# For a site whose entire scoring model turns on westerly wind, wind
# measured at the beach beats wind measured at an inland airport.
#
# But GLOS is a data source we have never used, and three things must be
# established BEFORE any backend code is written:
#
#   1. Can we reach the API at all without a login or paid key?
#   2. What EXACTLY does NESHOTAH measure, in what UNITS?
#   3. Does GLOS give us 72 HOURS OF HISTORY, or only "right now"?
#
# Question 3 is the important one. The site's wind ribbon needs about 72
# hours of history. If GLOS is current-conditions-only, NESHOTAH cannot
# REPLACE the airport station - it can only SUPPLEMENT it. That is a
# completely different backend change, and it is far cheaper to learn it
# now than halfway through writing it.
#
# Question 2 is the dangerous one. If GLOS reports wind in metres per
# second and the site assumes knots, nothing crashes - the site just
# quietly publishes wrong wind on every pier that uses it, and wrong wind
# means wrong scores. So this probe READS THE UNITS FROM THE API rather
# than inferring them from a label. That is decision D207 applied to a new
# data source: read the fact from the file, never infer it from the name.
#
# ============================================================================
# AND WHY IT SURVEYS ALL SEVEN PIERS, NOT JUST TWO RIVERS
# ============================================================================
# GLOS aggregates stations that never appear in NDBC's feed at all. That is
# precisely why every previous search missed NESHOTAH. The same gap may be
# hiding stations near the other piers.
#
# Port Washington is included because it is already scoped as the next pier,
# and its only candidate wind station (KETB, West Bend Municipal) is 13.7
# miles inland - far worse than any existing pier's station, and unverified.
# If GLOS has something closer, that is worth knowing before Port Washington
# is built, not after.
#
# One probe run, seven piers answered.
#
# ============================================================================
# API STRUCTURE (from https://glos.org/data/faq/, read 2026-08-20)
# ============================================================================
#   /api/v1/obs-datasets.geojson          all platform locations, one call
#   /api/v1/obs-dataset-summaries         obs_dataset_id + platform_id
#   /api/v1/obs-datasets/{id}/metadata    metadata for one platform
#   /api/v1/parameters                    parameter ids + standard names
#   /api/v1/parameter-configurations      UNITS for each parameter
#   /api/v1/obs?startDate=&obsDatasetId=  historical observations
#   /api/v1/obs-latest                    latest values, ~10 min refresh
#
# Stdlib only. No pip install needed.
# ============================================================================

import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://seagull-api.glos.org"
ERDDAP = "https://seagull-erddap.glos.org/erddap"
UA = "PierBite-probe/1.0 (pierbite.com; station survey; contact via site)"
TIMEOUT = 45

# How far from a pier a GLOS platform can be and still be worth reporting.
# 25 miles is deliberately generous: Port Washington's current best
# candidate is 13.7 mi, so a tighter radius could hide something that
# still beats it.
RADIUS_MI = 25.0

# Cap on how many platforms get the expensive deep-dive treatment, so the
# probe cannot accidentally hammer a free public API.
MAX_DEEP_DIVE = 14

# Verified pier coordinates, read out of the live fetch_data.py PIERS dict
# on 2026-08-20 - NOT typed from memory.
PIERS = [
    ("Two Rivers",    44.147061, -87.565680, "KMTW  Manitowoc Airport",  44.13333, -87.68333),
    ("Manitowoc",     44.091354, -87.643820, "KMTW  Manitowoc Airport",  44.13333, -87.68333),
    ("Sheboygan",     43.748595, -87.694910, "KSBM  Sheboygan Airport",  43.77483, -87.84897),
    ("Kewaunee",      44.457285, -87.493085, "KWNW3 Kewaunee MET",       44.465,   -87.49572),
    ("Algoma",        44.608423, -87.433597, "KWNW3 Kewaunee (AGMW3 dormant)", 44.465,   -87.49572),
    ("Sturgeon Bay",  44.792050, -87.309627, "KSUE  Cherryland Airport", 44.83941, -87.42188),
    # Port Washington is NOT yet a live pier. Coordinates are the
    # breakwater light, confirmed 2026-08-19. Its listed "current" wind
    # station is a CANDIDATE ONLY and has never been verified.
    ("Port Washington (planned)", 43.3853, -87.8597, "KETB  West Bend Muni (UNVERIFIED)", 43.4222, -88.1278),
]

# Text fragments that identify a station as the Two Rivers one we are
# chasing. Matched case-insensitively against the platform name.
NESHOTAH_HINTS = ("neshotah", "two rivers")

# Parameter standard_names / labels that indicate wind or water temp.
# Deliberately broad - the probe REPORTS what it finds, it does not filter
# the truth down to what it expected to see.
WIND_HINTS = ("wind", "gust")
WATER_HINTS = ("water_temp", "sea_water_temperature", "water temperature")


# ---------------------------------------------------------------------------
# plumbing
# ---------------------------------------------------------------------------

def hr(title):
    print("\n" + "=" * 74)
    print(title)
    print("=" * 74)


def sub(title):
    print("\n" + "-" * 74)
    print(title)
    print("-" * 74)


def get(url, label, retries=2):
    """Fetch a URL and return (status, parsed_or_text, error_string)."""
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                raw = r.read()
                status = r.getcode()
            try:
                return status, json.loads(raw.decode("utf-8", "replace")), None
            except json.JSONDecodeError:
                return status, raw.decode("utf-8", "replace")[:2000], "not-json"
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:400]
            except Exception:
                pass
            if attempt < retries and e.code in (429, 500, 502, 503, 504):
                time.sleep(3 * (attempt + 1))
                continue
            return e.code, None, "HTTP %s :: %s" % (e.code, body)
        except Exception as e:
            if attempt < retries:
                time.sleep(3 * (attempt + 1))
                continue
            return None, None, "%s: %s" % (type(e).__name__, e)
    return None, None, "exhausted retries"


def haversine_mi(lat1, lon1, lat2, lon2):
    R = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def dig(obj, *keys, default=None):
    """Pull the first present key from a dict, tolerating API naming drift."""
    if not isinstance(obj, dict):
        return default
    for k in keys:
        if k in obj and obj[k] is not None:
            return obj[k]
    return default


# ---------------------------------------------------------------------------
# PART 0 - can we even get in?
# ---------------------------------------------------------------------------

def part0():
    hr("PART 0 - IS THE GLOS API REACHABLE, AND DOES IT NEED A LOGIN?")
    print("If this part fails with 401 or 403, everything below is moot and")
    print("the answer is 'GLOS needs an account' - which is a decision for")
    print("Paul, not a bug to fix.\n")

    url = API + "/api/v1/obs-datasets.geojson"
    status, data, err = get(url, "geojson")
    print("  GET %s" % url)
    print("  -> HTTP %s" % status)

    if err:
        print("  -> ERROR: %s" % err)
        if status in (401, 403):
            print("\n  VERDICT: AUTHENTICATION REQUIRED. Stop here and report this.")
        else:
            print("\n  VERDICT: UNREACHABLE. Report the error text above verbatim.")
        return None

    feats = data.get("features") if isinstance(data, dict) else None
    if not isinstance(feats, list):
        print("  -> Unexpected shape. Top-level keys: %s" % (
            list(data.keys())[:12] if isinstance(data, dict) else type(data).__name__))
        print("  -> First 800 chars of response:")
        print("     " + json.dumps(data)[:800])
        return None

    print("  -> OK. No token was sent and the request succeeded.")
    print("  -> VERDICT: PUBLIC ACCESS CONFIRMED. %d platforms returned." % len(feats))
    return feats


# ---------------------------------------------------------------------------
# PART 1 + 2 - inventory and distance ranking
# ---------------------------------------------------------------------------

def extract_platforms(feats):
    """Normalise the GeoJSON features into flat dicts."""
    out = []
    for f in feats:
        if not isinstance(f, dict):
            continue
        props = f.get("properties") or {}
        geom = f.get("geometry") or {}
        coords = geom.get("coordinates")
        lat = lon = None
        if isinstance(coords, (list, tuple)) and len(coords) >= 2:
            try:
                lon, lat = float(coords[0]), float(coords[1])
            except (TypeError, ValueError):
                lat = lon = None
        if lat is None:
            lat = dig(props, "latitude", "lat")
            lon = dig(props, "longitude", "lon", "lng")
        if lat is None or lon is None:
            continue
        out.append({
            "name": str(dig(props, "name", "platform_name", "title", "label",
                            default="(unnamed)")),
            "ods_id": dig(props, "obs_dataset_id", "id", "obsDatasetId"),
            "plat_id": dig(props, "platform_id", "platformId"),
            "lat": float(lat),
            "lon": float(lon),
            "props": props,
        })
    return out


def part12(feats):
    hr("PART 1 - FULL GLOS PLATFORM INVENTORY")
    plats = extract_platforms(feats)
    print("  Platforms with usable coordinates: %d of %d features" % (len(plats), len(feats)))

    if plats:
        print("\n  Property keys on the first platform (so future sessions know")
        print("  what this endpoint actually returns, rather than guessing):")
        print("    %s" % sorted(plats[0]["props"].keys()))

    hr("PART 2 - NEAREST GLOS PLATFORM TO EACH PIER")
    print("  'Current' = the wind station fetch_data.py uses TODAY.")
    print("  A GLOS platform is only interesting if it BEATS that distance.")
    print("")
    print("  ALGOMA NOTE: its configured first choice, AGMW3 (Algoma City")
    print("  Marina), sits 0.0 mi from the pier but is DORMANT - NOAA has not")
    print("  transmitted from it in a long time. The site therefore really")
    print("  runs on Kewaunee, 10.4 mi away. Measuring against the dormant")
    print("  station would make Algoma look unimprovable when it is actually")
    print("  the second-worst-served pier on the coast. The baseline below is")
    print("  the station Algoma ACTUALLY uses.\n")

    candidates = {}
    for pname, plat, plon, cur_label, cur_lat, cur_lon in PIERS:
        cur_mi = haversine_mi(plat, plon, cur_lat, cur_lon)
        near = []
        for p in plats:
            d = haversine_mi(plat, plon, p["lat"], p["lon"])
            if d <= RADIUS_MI:
                near.append((d, p))
        near.sort(key=lambda t: t[0])

        sub("%s   (pier at %.5f, %.5f)" % (pname, plat, plon))
        print("  Current wind source : %-36s %6.1f mi" % (cur_label, cur_mi))
        if not near:
            print("  GLOS platforms within %.0f mi: NONE" % RADIUS_MI)
            continue
        print("  GLOS platforms within %.0f mi: %d\n" % (RADIUS_MI, len(near)))
        print("    %-42s %8s  %s" % ("platform", "miles", "verdict"))
        for d, p in near[:8]:
            verdict = "BEATS current" if d < cur_mi else "farther than current"
            print("    %-42s %8.1f  %s" % (p["name"][:42], d, verdict))
            if d < cur_mi:
                key = p["ods_id"] if p["ods_id"] is not None else p["name"]
                if key not in candidates:
                    candidates[key] = {"plat": p, "for": []}
                candidates[key]["for"].append((pname, d, cur_mi))
    return plats, candidates


# ---------------------------------------------------------------------------
# PART 3 - what do the candidates actually measure, in what units
# ---------------------------------------------------------------------------

def load_units():
    """parameter_id -> unit string, best effort."""
    status, data, err = get(API + "/api/v1/parameter-configurations", "units")
    if err or not isinstance(data, (list, dict)):
        print("  (could not load parameter-configurations: %s)" % (err or "odd shape"))
        return {}
    rows = data if isinstance(data, list) else data.get("data") or []
    units = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        pid = dig(r, "parameter_id", "parameterId", "id")
        u = dig(r, "canonical_unit", "unit", "units", "canonical_unit_id",
                "canonical_unit_name")
        if pid is not None:
            units[pid] = u
    return units


def part3(candidates, units):
    hr("PART 3 - WHAT EACH CANDIDATE MEASURES, AND IN WHAT UNITS")
    print("  UNITS ARE READ FROM THE API, NOT INFERRED FROM THE LABEL.")
    print("  If GLOS reports wind in m/s and the site assumes knots, nothing")
    print("  crashes - the site just publishes wrong wind, and wrong wind")
    print("  means wrong scores on every pier that uses it.\n")

    if not candidates:
        print("  No candidate beat its pier's current station. Nothing to inspect.")
        return {}

    ranked = sorted(candidates.items(),
                    key=lambda kv: min(f[1] for f in kv[1]["for"]))[:MAX_DEEP_DIVE]
    print("  Inspecting %d platform(s).\n" % len(ranked))

    found = {}
    for key, entry in ranked:
        p = entry["plat"]
        sub("%s   (obs_dataset_id=%s, platform_id=%s)" % (
            p["name"], p["ods_id"], p["plat_id"]))
        for pier, d, cur in entry["for"]:
            print("    serves %-28s %5.1f mi  (vs %5.1f mi today)" % (pier, d, cur))

        ods = p["ods_id"]
        if ods is None:
            print("    No obs_dataset_id in the GeoJSON - cannot query parameters.")
            continue

        status, meta, err = get(API + "/api/v1/obs-datasets/%s/metadata" % ods, "meta")
        if err:
            print("    metadata: ERROR %s" % err)
        elif isinstance(meta, dict):
            interesting = {k: meta[k] for k in list(meta.keys())[:14]}
            print("    metadata keys: %s" % sorted(meta.keys())[:14])
            for k in ("platform_id", "name", "organization", "status",
                      "active", "last_updated", "description"):
                if k in meta:
                    print("      %-14s %s" % (k, str(meta[k])[:90]))
            plat_id = dig(meta, "platform_id", "platformId") or p["plat_id"]
        else:
            plat_id = p["plat_id"]

        # parameters
        purl = API + "/api/v1/parameters"
        if plat_id is not None:
            purl += "?" + urllib.parse.urlencode({"platform_id": plat_id})
        status, params, err = get(purl, "params")
        if err:
            print("    parameters: ERROR %s" % err)
            continue
        rows = params if isinstance(params, list) else (
            params.get("data") if isinstance(params, dict) else []) or []

        # If the filter was ignored we may have every parameter in Seagull.
        if plat_id is not None:
            filt = [r for r in rows if isinstance(r, dict)
                    and dig(r, "platform_id", "platformId") in (plat_id, str(plat_id))]
            if filt:
                rows = filt
            elif len(rows) > 60:
                print("    NOTE: platform_id filter appears to have been IGNORED")
                print("          (%d rows returned). Cannot attribute these" % len(rows))
                print("          parameters to this platform. Reporting nothing")
                print("          rather than reporting a guess.")
                rows = []

        if not rows:
            print("    parameters: none attributable to this platform")
            continue

        print("\n    %-34s %-8s %-16s" % ("parameter", "id", "units"))
        wind_ids, water_ids = [], []
        for r in rows[:40]:
            if not isinstance(r, dict):
                continue
            pid = dig(r, "parameter_id", "parameterId", "id")
            nm = str(dig(r, "standard_name", "name", "label", default="?"))
            u = dig(r, "canonical_unit", "unit", "units") or units.get(pid) or "?"
            print("    %-34s %-8s %-16s" % (nm[:34], str(pid), str(u)[:16]))
            low = nm.lower()
            if any(h in low for h in WIND_HINTS):
                wind_ids.append((pid, nm, u))
            if any(h in low for h in WATER_HINTS):
                water_ids.append((pid, nm, u))

        print("\n    WIND parameters found : %s" % (
            ", ".join("%s(id=%s, %s)" % (n, i, u) for i, n, u in wind_ids) or "NONE"))
        print("    WATER TEMP found      : %s" % (
            ", ".join("%s(id=%s, %s)" % (n, i, u) for i, n, u in water_ids) or "NONE"))
        if not water_ids:
            print("      ^ expected for a met station. This does NOT solve the")
            print("        water-temperature ladder; it is a WIND upgrade only.")

        found[key] = {"plat": p, "ods": ods, "plat_id": plat_id,
                      "wind": wind_ids, "water": water_ids, "for": entry["for"]}
    return found


# ---------------------------------------------------------------------------
# PART 4 - THE GO/NO-GO: is there 72 hours of history?
# ---------------------------------------------------------------------------

def part4(found):
    hr("PART 4 - THE DECIDING QUESTION: DOES GLOS GIVE US 72 HOURS OF HISTORY?")
    print("  The site's wind ribbon needs roughly 72 hours of past readings.")
    print("")
    print("  If YES -> a GLOS station can REPLACE the airport station.")
    print("  If NO  -> it can only SUPPLEMENT it (live gauge now, airport for")
    print("            the trend). That is a different backend change, and it")
    print("            is much cheaper to learn it here than halfway through")
    print("            writing fetch_data.py v21.\n")

    if not found:
        print("  No inspected platform to test. Skipping.")
        return

    # Prefer the Two Rivers / Neshotah station; else the closest thing found.
    target = None
    for key, f in found.items():
        nm = f["plat"]["name"].lower()
        if any(h in nm for h in NESHOTAH_HINTS):
            target = f
            break
    if target is None:
        target = sorted(found.values(), key=lambda f: min(x[1] for x in f["for"]))[0]
        print("  NOTE: no platform matched 'Neshotah'/'Two Rivers' by name.")
        print("        Testing the nearest candidate instead: %s\n" % target["plat"]["name"])

    p = target["plat"]
    sub("History test on: %s  (obs_dataset_id=%s)" % (p["name"], target["ods"]))

    start = (datetime.now(timezone.utc) - timedelta(days=4)).strftime("%Y-%m-%d")
    url = API + "/api/v1/obs?" + urllib.parse.urlencode({
        "startDate": start, "obsDatasetId": target["ods"]})
    print("  Asking for everything since %s (4 days, to test past the 72h mark)" % start)
    print("  GET %s\n" % url)

    status, data, err = get(url, "obs")
    if err:
        print("  ERROR: %s" % err)
        print("  VERDICT: history endpoint did not answer. Report this verbatim.")
        return

    blocks = data if isinstance(data, list) else [data]
    any_series = False
    for b in blocks:
        if not isinstance(b, dict):
            continue
        for par in b.get("parameters") or []:
            pid = dig(par, "parameter_id", "parameterId")
            obs = par.get("observations") or []
            if not obs:
                continue
            wind_ids = [i for i, _n, _u in target["wind"]]
            is_wind = pid in wind_ids
            if not is_wind and wind_ids:
                continue
            any_series = True

            stamps = []
            for o in obs:
                t = dig(o, "timestamp", "time", "datetime")
                if t is None:
                    continue
                try:
                    if isinstance(t, (int, float)):
                        stamps.append(datetime.fromtimestamp(t, timezone.utc))
                    else:
                        stamps.append(datetime.fromisoformat(str(t).replace("Z", "+00:00")))
                except (ValueError, TypeError, OSError):
                    pass
            if not stamps:
                print("  parameter_id %s: %d observations but no readable timestamps" % (pid, len(obs)))
                continue
            stamps.sort()
            span_h = (stamps[-1] - stamps[0]).total_seconds() / 3600.0
            age_h = (datetime.now(timezone.utc) - stamps[-1]).total_seconds() / 3600.0
            gaps = [(stamps[i + 1] - stamps[i]).total_seconds() / 60.0
                    for i in range(len(stamps) - 1)]
            gaps.sort()
            med = gaps[len(gaps) // 2] if gaps else float("nan")
            biggest = gaps[-1] if gaps else float("nan")

            pname = next((n for i, n, _u in target["wind"] if i == pid), "parameter %s" % pid)
            print("  %s (id=%s)" % (pname, pid))
            print("    observations returned : %d" % len(stamps))
            print("    oldest reading        : %s" % stamps[0].isoformat())
            print("    newest reading        : %s  (%.1f h ago)" % (stamps[-1].isoformat(), age_h))
            print("    span covered          : %.1f hours" % span_h)
            print("    typical gap           : %.1f minutes" % med)
            print("    largest gap           : %.1f minutes" % biggest)
            if span_h >= 72:
                print("    -> COVERS 72 HOURS. This station could REPLACE the airport.")
            else:
                print("    -> DOES NOT REACH 72 HOURS (%.1f h)." % span_h)
                print("       It can SUPPLEMENT the airport station, not replace it.")
            print("")

    if not any_series:
        print("  No wind observations came back in that window.")
        print("  Top-level shape of the response, for diagnosis:")
        print("    %s" % json.dumps(data)[:900])


# ---------------------------------------------------------------------------
# PART 5 - does the reading agree with what the site shows now?
# ---------------------------------------------------------------------------

def part5(found):
    hr("PART 5 - SANITY CHECK: DOES GLOS AGREE WITH WHAT THE SITE SHOWS NOW?")
    print("  A units mistake does not crash anything - it just makes the site")
    print("  quietly wrong. Comparing a fresh GLOS reading against the site's")
    print("  own current wind is a cheap way to catch that before it ships.\n")

    status, data, err = get(API + "/api/v1/obs-latest", "latest")
    if err:
        print("  obs-latest: ERROR %s" % err)
        return
    print("  obs-latest reachable. Response type: %s" % type(data).__name__)

    wanted = {}
    for f in found.values():
        for pid, nm, u in f["wind"]:
            # Keyed on (obs_dataset_id, parameter_id), NOT parameter_id alone.
            # Parameter ids are NOT unique across platforms - two stations can
            # both use id 180 for wind_speed. Keying on the id by itself lets
            # the last platform written silently overwrite the first, and the
            # probe then prints a real reading under the WRONG station's name.
            # That was a live bug in v1 of this file, caught by the mocked
            # run before it ever executed against real data.
            wanted[(f["ods"], pid)] = (f["plat"]["name"], nm, u)
    if not wanted:
        print("  No wind parameter ids identified, so nothing to match. Skipping.")
        return

    rows = data if isinstance(data, list) else (
        data.get("data") if isinstance(data, dict) else []) or []
    hits = 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        row_ods = dig(r, "obs_dataset_id", "obsDatasetId")
        for par in r.get("parameters") or []:
            pid = dig(par, "parameter_id", "parameterId")
            key = (row_ods, pid)
            if key not in wanted:
                continue
            for o in (par.get("observations") or [])[:1]:
                plat_nm, par_nm, unit = wanted[key]
                print("    %-30s %-22s %s %s   at %s" % (
                    plat_nm[:30], par_nm[:22],
                    dig(o, "value", "val"), unit,
                    dig(o, "timestamp", "time")))
                hits += 1
    if not hits:
        print("  No matching parameters in obs-latest (it may need filtering).")

    print("\n  Compare the numbers above against the site's own current wind:")
    print("  https://raw.githubusercontent.com/pbkfishstks/"
          "Live-buoy-and-weather-data-for-PierBite.com/main/data.json")
    print("  A GLOS wind of ~5 where the site says ~10 is the classic")
    print("  knots-vs-metres-per-second mismatch.")


# ---------------------------------------------------------------------------
# PART 6 - is ERDDAP a usable second path?
# ---------------------------------------------------------------------------

def part6(found):
    hr("PART 6 - IS ERDDAP A USABLE BACKUP ACCESS PATH?")
    print("  GLOS exposes the same data twice: the JSON API tested above, and")
    print("  an ERDDAP server. ERDDAP returns plain CSV and handles time")
    print("  ranges natively, which can be sturdier for history. Worth knowing")
    print("  which path v21 should use before v21 is written.\n")

    ods = None
    for f in found.values():
        nm = f["plat"]["name"].lower()
        if any(h in nm for h in NESHOTAH_HINTS):
            ods = f["ods"]
            break
    if ods is None and found:
        ods = list(found.values())[0]["ods"]
    if ods is None:
        print("  No obs_dataset_id available to test. Skipping.")
        return

    url = "%s/tabledap/obs_%s.das" % (ERDDAP, ods)
    print("  GET %s" % url)
    status, body, err = get(url, "erddap")
    if err and status not in (200,):
        print("  -> HTTP %s / %s" % (status, err))
        print("  -> ERDDAP path NOT confirmed for this dataset.")
        return
    text = body if isinstance(body, str) else json.dumps(body)
    print("  -> HTTP %s, %d chars returned" % (status, len(text)))
    print("  -> First 700 characters (variable names and units live here):\n")
    for line in text[:700].splitlines():
        print("     " + line)
    print("\n  -> ERDDAP path CONFIRMED reachable for obs_%s." % ods)


# ---------------------------------------------------------------------------

def main():
    print("PIERBITE - GLOS SEAGULL STATION SURVEY PROBE v1")
    print("Run at %s" % datetime.now(timezone.utc).isoformat())
    print("READ-ONLY. Writes nothing. Changes nothing. Costs nothing.")

    feats = part0()
    if feats is None:
        hr("STOPPED")
        print("The API could not be reached without credentials.")
        print("Copy everything above back into the chat.")
        return 0

    plats, candidates = part12(feats)
    units = load_units()
    found = part3(candidates, units)
    part4(found)
    part5(found)
    part6(found)

    hr("END OF PROBE")
    print("Copy this ENTIRE output back into the chat, including any errors.")
    print("Errors are data too - a clear failure is more useful than a guess.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        hr("PROBE CRASHED - THIS IS STILL USEFUL INFORMATION")
        traceback.print_exc()
        print("\nCopy the traceback above back into the chat.")
        sys.exit(0)
