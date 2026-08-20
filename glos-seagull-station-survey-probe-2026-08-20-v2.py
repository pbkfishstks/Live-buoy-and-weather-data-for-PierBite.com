#!/usr/bin/env python3
# PIERBITE probe | 2026-08-20 | v2 | GLOS SEAGULL STATION SURVEY
#
# ============================================================================
# WHAT THIS IS
# ============================================================================
# A READ-ONLY diagnostic probe. Runs in GitHub Actions, prints a report,
# stops. Writes nothing. Changes nothing on the live site. Costs nothing.
#
# ============================================================================
# WHY THERE IS A v2 - v1 PRODUCED A CONFIDENT WRONG ANSWER
# ============================================================================
# v1 established the things that matter most and they still stand:
#   - GLOS is fully public. 617 platforms. No key, no login, no cost.
#   - FIVE of the seven piers have a closer wind station available.
#
# But v1's PART 3 was wrong, and wrong in the most dangerous way: it looked
# right. Every single platform came back with an IDENTICAL 41-parameter
# list. A wave buoy and a beach weather station do not have identical
# sensors. That list was the GLOBAL Seagull parameter catalogue, not any
# one platform's sensors.
#
# ROOT CAUSE, stated plainly so it is not rediscovered later:
#   The GeoJSON does NOT contain a field called "platform_id". It contains
#   "org_platform_id". v1 filtered /api/v1/parameters on "platform_id",
#   found nothing to filter on, and so received the entire catalogue.
#
# v1 HAD A GUARD FOR EXACTLY THIS and the guard's threshold was set wrong -
# it only fired above 60 rows, and the catalogue is 41 rows. So it stayed
# silent while the bad data flowed through.
#
# WHAT THAT COST: v1 reported that Neshotah Park Met Station has a
# sea_water_temperature sensor. It does not - Paul already knew that from
# looking at the station himself. Had he not known, this probe would have
# fed a false water-temperature source into the most sensitive number on
# the site. This is why D207 exists ("read the fact from the source, never
# infer it from the name") and this is that rule being broken by its own
# author. Recorded, not buried.
#
# v1's PART 4 was invalid for the same reason - it filtered the history
# response using those bogus parameter ids and threw away real data. The
# raw dump proved data WAS there: 20-minute cadence, current to the hour.
#
# ============================================================================
# WHAT v2 DOES DIFFERENTLY
# ============================================================================
# It stops asking the JSON API a question it answers ambiguously, and reads
# two sources that are unambiguous:
#
#   1. THE GEOJSON'S OWN "parameters" FIELD. v1's output revealed the
#      per-platform property keys are:
#         body_of_water, obs_dataset_id, org_platform_id, parameters,
#         platform_event, platform_name, platform_type
#      "parameters" is per-platform - the authoritative sensor list, and it
#      was already in data v1 downloaded and ignored.
#
#   2. ERDDAP. v1 proved the ERDDAP path works and returns proper metadata.
#      An ERDDAP ".das" gives every variable's real name, standard_name and
#      UNITS, and the global attributes usually carry time_coverage_start /
#      time_coverage_end - which answers the 72-hour history question
#      directly rather than by inference. Then a ".csv" request returns the
#      actual readings under NAMED COLUMNS, so no parameter-id guessing is
#      possible at all.
#
# Also fixed: /api/v1/obs-latest returned HTTP 403 "Missing Authentication
# Token" in v1. It is dropped. /api/v1/obs works fine unauthenticated and
# ERDDAP is better anyway.
#
# ============================================================================
# THE OPEN QUESTION THIS PROBE MUST SETTLE
# ============================================================================
# "GLATOS Sam River 1" ranked as Sturgeon Bay's closest option at 3.7 mi.
# The name suggests a RIVER station, possibly inland. If so its 3.7 mi is
# WORSE than the airport's 6.4 mi for lake wind, not better - sheltered
# inland wind is not pier wind. Distance alone is not quality.
#
# The GeoJSON carries "body_of_water" and "platform_type" per platform.
# v2 reads both and reports them, so this is decided on evidence.
#
# The same test protects every other candidate: "Shipwreck Sentinel" and
# the various "*, WI, USA" entries are equally unverified.
#
# Stdlib only. No pip install needed.
# ============================================================================

import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://seagull-api.glos.org"
ERDDAP = "https://seagull-erddap.glos.org/erddap"
DATA_JSON = ("https://raw.githubusercontent.com/pbkfishstks/"
             "Live-buoy-and-weather-data-for-PierBite.com/main/data.json")
UA = "PierBite-probe/2.0 (pierbite.com; station survey)"
TIMEOUT = 45

RADIUS_MI = 25.0
MAX_DEEP_DIVE = 12       # platforms that get the ERDDAP metadata read
MAX_HISTORY_TESTS = 5    # platforms that get the full history pull

# Verified pier coordinates, read from the live fetch_data.py PIERS dict.
# The "current" station for each is what fetch_data.py ACTUALLY uses today.
PIERS = [
    ("Two Rivers",    44.147061, -87.565680, "KMTW  Manitowoc Airport",  44.13333, -87.68333),
    ("Manitowoc",     44.091354, -87.643820, "KMTW  Manitowoc Airport",  44.13333, -87.68333),
    ("Sheboygan",     43.748595, -87.694910, "KSBM  Sheboygan Airport",  43.77483, -87.84897),
    ("Kewaunee",      44.457285, -87.493085, "KWNW3 Kewaunee MET",       44.465,   -87.49572),
    # AGMW3 sits 0.0 mi from the Algoma pier but is DORMANT. Measuring
    # against a dead station would make Algoma look unimprovable when it
    # actually runs on Kewaunee, 10.4 mi away.
    ("Algoma",        44.608423, -87.433597, "KWNW3 Kewaunee (AGMW3 dead)", 44.465, -87.49572),
    ("Sturgeon Bay",  44.792050, -87.309627, "KSUE  Cherryland Airport", 44.83941, -87.42188),
    ("Port Washington (planned)", 43.3853, -87.8597, "KETB  West Bend Muni (UNVERIFIED)", 43.4222, -88.1278),
]

WIND_HINTS = ("wind", "gust")
WATER_HINTS = ("sea_water_temperature", "water_temp", "water temperature")


def hr(t):
    print("\n" + "=" * 76)
    print(t)
    print("=" * 76)


def sub(t):
    print("\n" + "-" * 76)
    print(t)
    print("-" * 76)


def get(url, retries=2, want_text=False):
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                raw = r.read()
                status = r.getcode()
            text = raw.decode("utf-8", "replace")
            if want_text:
                return status, text, None
            try:
                return status, json.loads(text), None
            except json.JSONDecodeError:
                return status, text[:3000], "not-json"
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:300]
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


def haversine_mi(a, b, c, d):
    R = 3958.7613
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = math.radians(c - a), math.radians(d - b)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def dig(o, *keys, **kw):
    default = kw.get("default")
    if not isinstance(o, dict):
        return default
    for k in keys:
        if k in o and o[k] is not None:
            return o[k]
    return default


def names_from_parameters(params):
    """The GeoJSON 'parameters' field - shape unknown, so handle every
    plausible form and never silently return an empty list as if it were
    a confirmed 'no sensors'."""
    out = []
    if isinstance(params, list):
        for p in params:
            if isinstance(p, str):
                out.append(p)
            elif isinstance(p, dict):
                n = dig(p, "standard_name", "name", "parameter", "label",
                        "parameter_name")
                if n:
                    out.append(str(n))
                else:
                    out.append(json.dumps(p)[:60])
            else:
                out.append(str(p))
    elif isinstance(params, dict):
        for k, v in params.items():
            n = dig(v, "standard_name", "name") if isinstance(v, dict) else None
            out.append(str(n or k))
    elif isinstance(params, str):
        out = [s.strip() for s in params.split(",") if s.strip()]
    return out


# ---------------------------------------------------------------------------

def part0():
    hr("PART 0 - REACHABILITY (re-confirming v1's finding)")
    url = API + "/api/v1/obs-datasets.geojson"
    status, data, err = get(url)
    print("  GET %s\n  -> HTTP %s" % (url, status))
    if err:
        print("  -> ERROR: %s" % err)
        return None
    feats = data.get("features") if isinstance(data, dict) else None
    if not isinstance(feats, list):
        print("  -> Unexpected shape: %s" % json.dumps(data)[:600])
        return None
    print("  -> PUBLIC ACCESS CONFIRMED. %d platforms." % len(feats))
    return feats


def extract(feats):
    out = []
    for f in feats:
        if not isinstance(f, dict):
            continue
        pr = f.get("properties") or {}
        g = f.get("geometry") or {}
        c = g.get("coordinates")
        lat = lon = None
        if isinstance(c, (list, tuple)) and len(c) >= 2:
            try:
                lon, lat = float(c[0]), float(c[1])
            except (TypeError, ValueError):
                lat = lon = None
        if lat is None:
            lat, lon = dig(pr, "latitude", "lat"), dig(pr, "longitude", "lon")
        if lat is None or lon is None:
            continue
        out.append({
            "name": str(dig(pr, "platform_name", "name", default="(unnamed)")),
            "ods": dig(pr, "obs_dataset_id"),
            "org_id": dig(pr, "org_platform_id"),
            "ptype": dig(pr, "platform_type", default="?"),
            "water": dig(pr, "body_of_water", default="?"),
            "event": dig(pr, "platform_event"),
            "params_raw": pr.get("parameters"),
            "params": names_from_parameters(pr.get("parameters")),
            "lat": float(lat), "lon": float(lon),
            "props": pr,
        })
    return out


def part1(feats):
    hr("PART 1 - READING THE PER-PLATFORM SENSOR LIST THAT v1 IGNORED")
    plats = extract(feats)
    print("  Platforms with coordinates: %d\n" % len(plats))

    # PROOF the parameters field is per-platform and not one shared catalogue.
    # If every platform reports the same sensor count, this field is as
    # useless as v1's was, and this probe must say so rather than proceed.
    sizes = {}
    for p in plats:
        sizes[len(p["params"])] = sizes.get(len(p["params"]), 0) + 1
    print("  Sensor-count distribution across all platforms:")
    for n in sorted(sizes)[:14]:
        print("    %3d sensors : %d platforms" % (n, sizes[n]))
    distinct = len(sizes)
    if distinct <= 1:
        print("\n  *** WARNING: every platform reports the SAME sensor count.")
        print("      That is the v1 failure signature. Treat PART 3 as")
        print("      UNVERIFIED and rely on ERDDAP (PART 4) instead.")
    else:
        print("\n  -> %d different sensor counts. This field IS per-platform." % distinct)
        print("     (v1's list was identical for every platform - that was the bug.)")

    ex = next((p for p in plats if p["params"]), None)
    if ex:
        print("\n  Raw shape of 'parameters' on one real platform (%s),"
              % ex["name"][:40])
        print("  so future sessions know what this field actually looks like:")
        print("    " + json.dumps(ex["params_raw"])[:700])

    print("\n  Platform types seen: %s" % sorted(
        set(str(p["ptype"]) for p in plats))[:12])
    print("  Bodies of water seen: %s" % sorted(
        set(str(p["water"]) for p in plats))[:12])
    return plats


def part2(plats):
    hr("PART 2 - NEAREST GLOS PLATFORM TO EACH PIER, WITH QUALITY CONTEXT")
    print("  DISTANCE ALONE IS NOT QUALITY. A river gauge 3 miles away can")
    print("  be worse than an airport 6 miles away, because sheltered inland")
    print("  wind is not pier wind. 'body of water' and 'type' are printed")
    print("  next to every candidate so the choice is made on evidence.\n")

    cands = {}
    for nm, la, lo, cur_lab, cla, clo in PIERS:
        cur = haversine_mi(la, lo, cla, clo)
        near = sorted(
            ((haversine_mi(la, lo, p["lat"], p["lon"]), p) for p in plats),
            key=lambda t: t[0])
        near = [t for t in near if t[0] <= RADIUS_MI]

        sub("%s   (pier %.5f, %.5f)" % (nm, la, lo))
        print("  Today: %-34s %6.1f mi" % (cur_lab, cur))
        if not near:
            print("  No GLOS platform within %.0f mi." % RADIUS_MI)
            continue
        print("")
        print("  %-38s %6s  %-16s %-16s %s"
              % ("platform", "miles", "body of water", "type", "sensors"))
        for d, p in near[:7]:
            mark = "<<" if d < cur else "  "
            print("%s %-38s %6.1f  %-16s %-16s %d"
                  % (mark, p["name"][:38], d, str(p["water"])[:16],
                     str(p["ptype"])[:16], len(p["params"])))
            if d < cur:
                key = p["ods"] if p["ods"] is not None else p["name"]
                cands.setdefault(key, {"p": p, "for": []})
                cands[key]["for"].append((nm, d, cur))
        print("\n  ('<<' = closer than what the site uses today)")
    return cands


def part3(cands):
    hr("PART 3 - WHAT EACH CANDIDATE ACTUALLY MEASURES (per-platform)")
    print("  Read from each platform's OWN parameters field. If these lists")
    print("  differ from one another, the field is real. If they are all")
    print("  identical, PART 1 has already flagged it as untrustworthy.\n")
    if not cands:
        print("  No candidate beats its pier's current station.")
        return {}
    ranked = sorted(cands.items(), key=lambda kv: min(f[1] for f in kv[1]["for"]))
    for key, e in ranked[:MAX_DEEP_DIVE]:
        p = e["p"]
        sub("%s  (obs_dataset_id=%s, org_platform_id=%s)"
            % (p["name"], p["ods"], p["org_id"]))
        for pier, d, cur in e["for"]:
            print("    serves %-28s %5.1f mi   (vs %5.1f mi today)" % (pier, d, cur))
        print("    position    : %.5f, %.5f" % (p["lat"], p["lon"]))
        print("    body of water: %s" % p["water"])
        print("    platform type: %s" % p["ptype"])
        if p["event"]:
            print("    platform_event: %s" % json.dumps(p["event"])[:200])
        sensors = p["params"]
        print("    sensors (%d): %s" % (len(sensors), ", ".join(sensors[:20]) or "NONE LISTED"))
        low = " ".join(sensors).lower()
        print("    HAS WIND        : %s" % ("YES" if any(h in low for h in WIND_HINTS) else "no"))
        print("    HAS WATER TEMP  : %s" % ("YES" if any(h in low for h in WATER_HINTS) else "no"))
    return dict(ranked[:MAX_DEEP_DIVE])


# ---------------------------------------------------------------------------
# ERDDAP - the authoritative source for variable names and units
# ---------------------------------------------------------------------------

def normalize_das(text):
    """Put each structural token on its own line WITHOUT breaking quoted
    strings apart.

    ERDDAP's .das is usually pretty-printed one attribute per line, but
    nothing guarantees it. A line-oriented parser silently returns NOTHING
    on a compact response, and 'no variables found' looks exactly like
    'no sensors on this platform' - a false negative that would be very
    easy to believe. So the text is normalised first.

    Quote-awareness matters: a 'summary' attribute can legitimately
    contain braces or semicolons, and splitting inside one would corrupt
    every variable after it.
    """
    out, in_q, prev = [], False, ""
    for ch in text:
        if ch == '"' and prev != "\\":
            in_q = not in_q
            out.append(ch)
        elif not in_q and ch in "{};":
            out.append("\n" + ch + "\n" if ch != ";" else ";\n")
        else:
            out.append(ch)
        prev = ch
    return "".join(out)


def parse_das(text):
    """Pull {variable: {attr: value}} out of an ERDDAP .das response.
    The .das format is braces and quoted strings, not JSON, so it is
    walked rather than parsed as something it is not."""
    varmap, cur, depth, pending = {}, None, 0, None
    for raw in normalize_das(text).splitlines():
        s = raw.strip()
        if not s:
            continue
        if s == "{":
            depth += 1
            if depth >= 2 and pending and pending != "s":
                cur = pending
                varmap.setdefault(cur, {})
            pending = None
            continue
        if s == "}":
            depth -= 1
            cur = None
            pending = None
            continue
        if s == ";":
            continue
        m = re.match(r'^(\w+)\s+(\w+)\s+(.*?);?$', s)
        if m and cur:
            _typ, attr, val = m.groups()
            val = val.strip().rstrip(";").strip()
            varmap[cur][attr] = val.strip('"')
            continue
        # A bare word here is the name of the block whose "{" comes next.
        if re.match(r'^[\w.]+$', s):
            pending = s
    return varmap


def part4(found):
    hr("PART 4 - ERDDAP: REAL VARIABLE NAMES, REAL UNITS, REAL TIME COVERAGE")
    print("  This is the definitive source. ERDDAP publishes each variable's")
    print("  units, and its global attributes normally carry the dataset's")
    print("  time coverage - which answers the 72-hour question directly")
    print("  instead of by inference.\n")
    print("  UNITS MATTER MORE THAN ANYTHING ELSE HERE. If GLOS reports wind")
    print("  in metres per second and the site assumes knots, nothing breaks")
    print("  - the site just publishes wrong wind, and wrong wind means wrong")
    print("  scores on every pier that uses it.\n")

    out = {}
    for key, e in list(found.items())[:MAX_DEEP_DIVE]:
        p = e["p"]
        if p["ods"] is None:
            continue
        sub("%s  (ERDDAP dataset obs_%s)" % (p["name"], p["ods"]))
        status, text, err = get("%s/tabledap/obs_%s.das" % (ERDDAP, p["ods"]),
                                want_text=True)
        if err and status != 200:
            print("    .das unavailable: HTTP %s %s" % (status, err))
            continue
        # want_text should give a string, but a server can always return
        # something unexpected (a JSON error body, an HTML error page).
        # Coercing here means a surprise costs one skipped platform instead
        # of killing the whole probe run.
        if not isinstance(text, str):
            text = json.dumps(text)[:3000]
        vm = parse_das(text)
        if not vm:
            print("    Could not parse .das. First 400 chars:")
            print("    " + text[:400].replace("\n", "\n    "))
            continue

        glob = vm.get("NC_GLOBAL", {})
        for k in ("time_coverage_start", "time_coverage_end", "institution",
                  "title", "summary"):
            if k in glob:
                print("    %-20s %s" % (k, str(glob[k])[:80]))

        wind_vars, water_vars, others = [], [], []
        for v, attrs in vm.items():
            if v in ("NC_GLOBAL", "s"):
                continue
            sn = attrs.get("standard_name", v)
            un = attrs.get("units", "?")
            low = (v + " " + sn).lower()
            row = (v, sn, un)
            if any(h in low for h in WIND_HINTS):
                wind_vars.append(row)
            elif any(h in low for h in WATER_HINTS):
                water_vars.append(row)
            else:
                others.append(row)

        print("\n    %-26s %-30s %s" % ("variable", "standard_name", "UNITS"))
        for v, sn, un in wind_vars:
            print("  W %-26s %-30s %s" % (v[:26], sn[:30], un))
        for v, sn, un in water_vars:
            print("  T %-26s %-30s %s" % (v[:26], sn[:30], un))
        for v, sn, un in others[:10]:
            print("    %-26s %-30s %s" % (v[:26], sn[:30], un))

        print("\n    WIND variables      : %d" % len(wind_vars))
        print("    WATER TEMP variables: %d" % len(water_vars))
        if not water_vars:
            print("      ^ no water thermometer here. Wind upgrade only -")
            print("        this does NOT touch the water-temperature ladder.")
        out[key] = {"p": p, "wind": wind_vars, "water": water_vars,
                    "for": e["for"], "glob": glob}
    return out


def part5(erd):
    hr("PART 5 - THE DECIDING QUESTION: IS THERE 72 HOURS OF WIND HISTORY?")
    print("  Pulled from ERDDAP as CSV with NAMED COLUMNS, so the")
    print("  parameter-id confusion that invalidated v1's answer cannot")
    print("  happen here - each column arrives labelled.\n")
    print("  YES -> a GLOS station can REPLACE the airport station.")
    print("  NO  -> it can only SUPPLEMENT it (live now, airport for trend),")
    print("         which is a materially different backend change.\n")

    if not erd:
        print("  Nothing to test.")
        return

    start = (datetime.now(timezone.utc) - timedelta(days=4)
             ).strftime("%Y-%m-%dT%H:%M:%SZ")
    tested = 0
    for key, e in erd.items():
        if tested >= MAX_HISTORY_TESTS:
            break
        p, winds = e["p"], e["wind"]
        if not winds:
            continue
        tested += 1
        cols = ["time"] + [w[0] for w in winds[:3]]
        url = ("%s/tabledap/obs_%s.csv?%s&time%%3E=%s"
               % (ERDDAP, p["ods"], "%2C".join(cols),
                  urllib.parse.quote(start)))
        sub("%s  - wind history" % p["name"])
        print("  GET %s\n" % url)
        status, text, err = get(url, want_text=True)
        if err and status != 200:
            print("  ERDDAP CSV failed: HTTP %s %s" % (status, err))
            print("  Falling back to the JSON API for this platform.")
            jurl = API + "/api/v1/obs?" + urllib.parse.urlencode({
                "startDate": (datetime.now(timezone.utc) - timedelta(days=4)
                              ).strftime("%Y-%m-%d"),
                "obsDatasetId": p["ods"]})
            st2, data, er2 = get(jurl)
            if er2 or not isinstance(data, (list, dict)):
                print("  JSON API also failed: %s" % (er2 or "unexpected shape"))
                continue
            blocks = data if isinstance(data, list) else [data]
            for b in blocks:
                for par in (b.get("parameters") or []) if isinstance(b, dict) else []:
                    obs = par.get("observations") or []
                    if not obs:
                        continue
                    ts = []
                    for o in obs:
                        t = dig(o, "timestamp", "time")
                        try:
                            ts.append(datetime.fromisoformat(
                                str(t).replace("Z", "+00:00")))
                        except (ValueError, TypeError):
                            pass
                    if len(ts) < 2:
                        continue
                    ts.sort()
                    span = (ts[-1] - ts[0]).total_seconds() / 3600
                    print("    parameter_id %s: %d obs, span %.1f h, newest %s"
                          % (dig(par, "parameter_id"), len(ts), span,
                             ts[-1].isoformat()))
            continue

        lines = [l for l in (text if isinstance(text, str) else "").splitlines()
                 if l.strip()]
        if len(lines) < 3:
            print("  Only %d usable lines returned - no series to measure." % len(lines))
            print("  " + (text if isinstance(text, str) else json.dumps(text))[:300])
            continue
        header = lines[0].split(",")
        units_row = lines[1].split(",") if len(lines) > 1 else []
        print("  columns : %s" % header)
        print("  UNITS   : %s      <-- THIS IS THE NUMBER THAT MATTERS" % units_row)

        stamps, vals = [], {}
        for row in lines[2:]:
            cells = row.split(",")
            if len(cells) != len(header):
                continue
            try:
                t = datetime.fromisoformat(cells[0].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            stamps.append(t)
            for i, h in enumerate(header[1:], start=1):
                try:
                    vals.setdefault(h, []).append(float(cells[i]))
                except (ValueError, IndexError):
                    pass
        if len(stamps) < 2:
            print("  Not enough readings to measure.")
            continue
        stamps.sort()
        span = (stamps[-1] - stamps[0]).total_seconds() / 3600
        age = (datetime.now(timezone.utc) - stamps[-1]).total_seconds() / 3600
        gaps = sorted((stamps[i + 1] - stamps[i]).total_seconds() / 60
                      for i in range(len(stamps) - 1))
        med = gaps[len(gaps) // 2]
        print("\n  readings       : %d" % len(stamps))
        print("  oldest         : %s" % stamps[0].isoformat())
        print("  newest         : %s   (%.1f h ago)" % (stamps[-1].isoformat(), age))
        print("  span covered   : %.1f hours" % span)
        print("  typical gap    : %.1f minutes" % med)
        print("  largest gap    : %.1f minutes" % gaps[-1])
        for h, vv in vals.items():
            if vv:
                print("  %-22s min %.2f  max %.2f  latest %.2f"
                      % (h, min(vv), max(vv), vv[-1]))
        if span >= 72:
            print("\n  -> COVERS 72 HOURS. This station CAN REPLACE the airport.")
        else:
            print("\n  -> ONLY %.1f HOURS. It can SUPPLEMENT, not replace." % span)
        if age > 3:
            print("  -> CAUTION: newest reading is %.1f h old. Check reliability." % age)


def part6(erd):
    hr("PART 6 - SANITY CHECK AGAINST THE SITE'S OWN CURRENT WIND")
    print("  A units mistake does not crash anything. It just makes the site")
    print("  quietly wrong. Comparing against what PierBite publishes right")
    print("  now is the cheapest way to catch it before any code changes.\n")
    status, data, err = get(DATA_JSON + "?nocache=" + str(int(time.time())))
    if err or not isinstance(data, dict):
        print("  Could not read the live data.json: %s" % (err or "unexpected shape"))
        return
    piers = data.get("piers") or {}
    if not isinstance(piers, dict) or not piers:
        print("  data.json carried no 'piers' block to compare against.")
        return
    print("  What PierBite shows at this moment:\n")
    print("    %-16s %-10s %s" % ("pier", "wind", "source"))
    for k, v in piers.items():
        h = (v.get("headline") or {}) if isinstance(v, dict) else {}
        print("    %-16s %-10s %s"
              % (str(k)[:16], str(h.get("wind_mph", "?")),
                 str(h.get("wind_station_label", "?"))[:44]))
    print("\n  Compare against the ERDDAP 'latest' values printed in PART 5.")
    print("  If GLOS units are m s-1, multiply by 2.237 to get mph before")
    print("  comparing. A factor-of-two mismatch is the classic tell.")


def main():
    print("PIERBITE - GLOS SEAGULL STATION SURVEY PROBE v2")
    print("Run at %s" % datetime.now(timezone.utc).isoformat())
    print("READ-ONLY. Writes nothing. Changes nothing. Costs nothing.")
    print("Supersedes v1, whose PART 3 and PART 4 were INVALID - see header.")

    feats = part0()
    if feats is None:
        hr("STOPPED - could not reach the API")
        return 0
    plats = part1(feats)
    cands = part2(plats)
    found = part3(cands)
    erd = part4(found)
    part5(erd)
    part6(erd)

    hr("END OF PROBE v2")
    print("Copy this ENTIRE output back into the chat, errors included.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        hr("PROBE CRASHED - STILL USEFUL, COPY THE TRACEBACK")
        traceback.print_exc()
        sys.exit(0)
