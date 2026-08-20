#!/usr/bin/env python3
# PIERBITE | GLOS Probe v3 | 2026-08-20T14:12:28Z | v1
# Repo root filename (GitHub, prefix removed per D211): glos-probe-v3-2026-08-20-v1.py
# Local archive filename (Paul's machine):             Scripts_glos-probe-v3-2026-08-20-v1.py
#
# PURPOSE - answers, in priority order:
#   1. Q-45218-LIVE (PRIMARY) - is Shipwreck Sentinel (org_platform_id 45218,
#      obs_dataset_id 576) actually reporting right now? A real timestamped
#      reading settles this - GLOS metadata alone does not (D234).
#   2. Q-NESHOTAH-FRESH - does Neshotah (obs_dataset_id 598) carry >=72h of
#      real wind history (REPLACE KMTW) or less (SUPPLEMENT it)?
#   3. Q-PLATFORM-EVENT-FRESHNESS - does GLOS's platform_event field
#      ("activated") actually track whether a station is currently reporting,
#      for all three targets?
#   Also measures Port Washington (obs_dataset_id 250) wind + water temp,
#   needed for the future fetch_data.py v23 pier entry.
#
# READ-ONLY. Standard library only (json, re, sys, statistics, urllib,
# datetime). Never writes to disk. Never calls git/shell/subprocess.
#
# Runs inside GitHub Actions because this project's dev sandbox cannot reach
# seagull.glos.org (same allowlist restriction that blocked every earlier
# NDBC/NOAA probe here) - not because the API needs a login. It doesn't.
#
# TRAPS THIS SCRIPT IS WRITTEN AROUND (see PIERBITE project memory):
#   - D232: the GeoJSON key is `org_platform_id`, NOT `platform_id`.
#   - D239: ERDDAP shadows every real variable with QC-flag variables
#     (_test, _aggregate, gross_range, spike, rate_of_change, flat_line).
#     A plain substring match on "wind" pulls QC flags, not wind.
#   - D236: temperatures come back from ERDDAP in KELVIN.
#   - R88: not every GLOS platform is in ERDDAP (obs_310 -> 404). JSON API
#     /api/v1/obs is the fallback.
#   - D233: every probe must carry a check that would catch its OWN failure
#     mode. See self_check_* functions below.

import json
import re
import statistics
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

GEOJSON_URL = "https://seagull-api.glos.org/api/v1/obs-datasets.geojson"
JSON_OBS_URL = "https://seagull-api.glos.org/api/v1/obs?startDate={start}&obsDatasetId={ods}"
DAS_URL = "https://seagull-erddap.glos.org/erddap/tabledap/obs_{ods}.das"
CSV_URL = "https://seagull-erddap.glos.org/erddap/tabledap/obs_{ods}.csv?{cols}&time>={start}"

QC_EXCLUDE_SUBSTRINGS = (
    "_test", "_aggregate", "gross_range", "spike", "rate_of_change", "flat_line",
)

# Plausibility bounds for the self-check (D233). If a converted reading falls
# outside these, the units/parsing path is suspect - print WARNING, never
# silently accept. Wide enough for genuine Lake Michigan weather extremes.
WATER_TEMP_F_BOUNDS = (28.0, 90.0)
AIR_TEMP_F_BOUNDS = (-30.0, 110.0)
WIND_MPH_BOUNDS = (0.0, 90.0)

# History window requested. Long enough to prove or disprove 72h of real
# Neshotah wind history even if there are reporting gaps inside it.
HISTORY_DAYS_BACK = 6

TARGETS = [
    {
        "key": "shipwreck_sentinel_45218",
        "ods": 576,
        "org_id": "45218",
        "pier": "Sheboygan",
        "claimed_distance_mi": 3.7,
        "primary": True,
    },
    {
        "key": "neshotah",
        "ods": 598,
        "org_id": "NESHOTAH",
        "pier": "Two Rivers",
        "claimed_distance_mi": 0.6,
        "primary": False,
    },
    {
        "key": "port_washington",
        "ods": 250,
        "org_id": "SPOT-30952C",
        "pier": "Port Washington",
        "claimed_distance_mi": 5.0,
        "primary": False,
    },
]


# ----------------------------------------------------------------------
# Network layer - the only functions that touch the wire. Everything else
# is a pure function so it can be unit-tested offline without a network.
# ----------------------------------------------------------------------

def http_get(url, timeout=25):
    """Return (status_code, body_text_or_None, error_str_or_None).
    Never raises - every caller gets a clean tri-state result instead of
    having to wrap every single request in its own try/except."""
    req = urllib.request.Request(url, headers={"User-Agent": "pierbite-glos-probe-v3"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace"), None
    except urllib.error.HTTPError as e:
        return e.code, None, f"HTTPError {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return None, None, f"URLError: {e.reason}"
    except Exception as e:  # noqa: BLE001 - a probe must never crash mid-run
        return None, None, f"Unexpected error: {e}"


# ----------------------------------------------------------------------
# Pure parsing / conversion functions - unit-testable offline.
# ----------------------------------------------------------------------

def kelvin_to_f(k):
    return (k - 273.15) * 9.0 / 5.0 + 32.0


def ms_to_mph(v):
    return v * 2.23694


def is_qc_flag(varname):
    lname = varname.lower()
    return any(bad in lname for bad in QC_EXCLUDE_SUBSTRINGS)


def parse_das_variables(das_text):
    """Parse an ERDDAP .das response into {var_name: {"units":..,"standard_name":..}}.
    Only reads the top-level `s { ... }` block (the per-row variables), not
    NC_GLOBAL. Returns {} on unparseable input rather than raising."""
    if not das_text:
        return {}
    # Isolate the "s { ... }" section, stop before NC_GLOBAL.
    body = das_text.split("NC_GLOBAL", 1)[0]
    blocks = re.findall(r"^  (\S+) \{(.*?)\n  \}", body, flags=re.S | re.M)
    out = {}
    for name, block in blocks:
        units_m = re.search(r'String units "([^"]*)"', block)
        std_m = re.search(r'String standard_name "([^"]*)"', block)
        out[name] = {
            "units": units_m.group(1) if units_m else None,
            "standard_name": std_m.group(1) if std_m else None,
        }
    return out


def select_real_variables(das_vars):
    """Split a parsed .das variable dict into real (non-QC-flag) categories.
    Returns dict with keys: wind, water_temp, water_depth, air_temp, other."""
    result = {"wind": [], "water_temp": [], "water_depth": [], "air_temp": [], "other": []}
    for name, meta in das_vars.items():
        if name == "time" or is_qc_flag(name):
            continue
        std = (meta.get("standard_name") or "").lower()
        if name.endswith("_fixed_depth") or std == "depth":
            result["water_depth"].append(name)
        elif std.startswith("wind"):
            result["wind"].append(name)
        elif std == "sea_water_temperature" or name.startswith("sea_water_temperature"):
            result["water_temp"].append(name)
        elif std == "air_temperature":
            result["air_temp"].append(name)
        else:
            result["other"].append(name)
    return result


def parse_erddap_csv(csv_text):
    """Parse an ERDDAP .csv response (header row, units row, data rows).
    Returns (columns, rows) where rows is a list of dicts, values are
    floats/None/str-for-time. Returns ([], []) on empty/unparseable input."""
    if not csv_text:
        return [], []
    lines = [ln for ln in csv_text.strip().split("\n") if ln != ""]
    if len(lines) < 3:
        return [], []
    columns = lines[0].split(",")
    rows = []
    for line in lines[2:]:  # skip header + units row
        cells = line.split(",")
        row = {}
        for col, cell in zip(columns, cells):
            if col == "time":
                row[col] = cell
            elif cell in ("", "NaN"):
                row[col] = None
            else:
                try:
                    row[col] = float(cell)
                except ValueError:
                    row[col] = None
        rows.append(row)
    return columns, rows


def parse_iso(ts):
    ts = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(ts)


def estimate_cadence_minutes(timestamps):
    """Median gap between consecutive distinct sorted timestamps, in minutes.
    Returns None if fewer than 2 distinct timestamps."""
    uniq = sorted(set(timestamps))
    if len(uniq) < 2:
        return None
    gaps = [(uniq[i + 1] - uniq[i]).total_seconds() / 60.0 for i in range(len(uniq) - 1)]
    return statistics.median(gaps)


# ----------------------------------------------------------------------
# Self-checks (D233) - each one exists to catch a specific failure mode
# a previous probe in this project actually shipped.
# ----------------------------------------------------------------------

def self_check_no_qc_leak(selected_vars, all_das_vars):
    """Guards against D239's failure: a substring match pulling QC flags in
    under a real-sounding category. Fails loudly if any selected variable
    name matches the exclude list."""
    problems = []
    for category, names in selected_vars.items():
        for n in names:
            if is_qc_flag(n):
                problems.append(f"{category}:{n}")
    return (len(problems) == 0, problems)


def self_check_plausibility(label, value_f, bounds):
    lo, hi = bounds
    ok = (value_f is not None) and (lo <= value_f <= hi)
    return ok


def self_check_platform_distinctness(var_sets_by_target):
    """Guards against D232's failure: three platforms all returning the
    SAME variable set would mean we've hit a global catalogue again, not
    per-platform data. Real platforms here are known to differ (598 has
    no water sensor; 576 has 16 depth-tagged water sensors; 250 has fewer)."""
    sets_as_frozensets = [frozenset(v) for v in var_sets_by_target.values() if v]
    if len(sets_as_frozensets) < 2:
        return True, "only one target had data - distinctness check skipped"
    all_identical = len(set(sets_as_frozensets)) == 1
    if all_identical:
        return False, "ALL TARGETS RETURNED IDENTICAL VARIABLE SETS - possible catalogue leak, distrust results"
    return True, f"{len(set(sets_as_frozensets))} distinct variable sets across {len(sets_as_frozensets)} targets"


# ----------------------------------------------------------------------
# GeoJSON lookup
# ----------------------------------------------------------------------

def find_platform_by_ods(geojson_obj, ods):
    """Return the properties dict of the feature whose obs_dataset_id == ods,
    or None. Confirms platform_event and platform_name straight from GLOS's
    own catalogue rather than trusting anything cached in project memory."""
    if not geojson_obj:
        return None
    for feature in geojson_obj.get("features", []):
        props = feature.get("properties", {})
        if props.get("obs_dataset_id") == ods:
            return props
    return None


# ----------------------------------------------------------------------
# Per-target analysis
# ----------------------------------------------------------------------

def analyze_target(target, geojson_obj, now_utc, http_get_fn=http_get):
    ods = target["ods"]
    result = {
        "key": target["key"], "ods": ods, "pier": target["pier"],
        "geojson_found": False, "platform_event": None, "platform_name": None,
        "das_ok": False, "das_error": None, "selected_vars": {},
        "csv_ok": False, "csv_error": None,
        "newest_reading_utc": None, "age_hours": None,
        "span_hours_returned": None, "cadence_minutes": None,
        "readings_f": [], "readings_other": [],
        "plausibility_warnings": [],
        "verdict_live": "UNKNOWN",
        "verdict_platform_event_matches": "UNKNOWN",
    }

    props = find_platform_by_ods(geojson_obj, ods)
    if props:
        result["geojson_found"] = True
        result["platform_event"] = props.get("platform_event")
        result["platform_name"] = props.get("platform_name")

    das_status, das_text, das_err = http_get_fn(DAS_URL.format(ods=ods))
    if das_status != 200 or not das_text:
        result["das_error"] = das_err or f"HTTP {das_status}"
        # Fallback path per D238/R88: platform exists in GeoJSON but not ERDDAP.
        result["verdict_live"] = "INCONCLUSIVE - not in ERDDAP, JSON API fallback not water/wind-typed"
        return result
    result["das_ok"] = True

    das_vars = parse_das_variables(das_text)
    selected = select_real_variables(das_vars)
    result["selected_vars"] = selected

    ok, problems = self_check_no_qc_leak(selected, das_vars)
    if not ok:
        result["das_error"] = f"SELF-CHECK FAILED: QC-flag leak in {problems}"
        result["verdict_live"] = "INVALID - QC-flag leak, do not trust"
        return result

    cols = ["time"] + selected["wind"] + selected["water_temp"] + selected["water_depth"] + selected["air_temp"]
    cols = list(dict.fromkeys(cols))  # de-dupe, preserve order
    if len(cols) <= 1:
        result["csv_error"] = "no real (non-QC) variables found for this platform"
        result["verdict_live"] = "INCONCLUSIVE - no measurable variables after QC filtering"
        return result

    start_iso = (now_utc - timedelta(days=HISTORY_DAYS_BACK)).strftime("%Y-%m-%dT%H:%M:%SZ")
    csv_status, csv_text, csv_err = http_get_fn(
        CSV_URL.format(ods=ods, cols=",".join(cols), start=start_iso)
    )
    if csv_status != 200 or not csv_text:
        result["csv_error"] = csv_err or f"HTTP {csv_status}"
        result["verdict_live"] = "NOT LIVE - no data returned for the requested window"
        return result
    result["csv_ok"] = True

    columns, rows = parse_erddap_csv(csv_text)
    if not rows:
        result["csv_error"] = "CSV parsed but contained zero data rows"
        result["verdict_live"] = "NOT LIVE - zero rows in requested window"
        return result

    timestamps = []
    for r in rows:
        if r.get("time"):
            try:
                timestamps.append(parse_iso(r["time"]))
            except ValueError:
                continue
    if not timestamps:
        result["csv_error"] = "no parseable timestamps in returned rows"
        result["verdict_live"] = "NOT LIVE - unparseable time column"
        return result

    newest_ts = max(timestamps)
    oldest_ts = min(timestamps)
    result["newest_reading_utc"] = newest_ts.isoformat()
    result["age_hours"] = round((now_utc - newest_ts).total_seconds() / 3600.0, 2)
    result["span_hours_returned"] = round((newest_ts - oldest_ts).total_seconds() / 3600.0, 2)
    result["cadence_minutes"] = estimate_cadence_minutes(timestamps)

    newest_row = max(
        (r for r in rows if r.get("time") and parse_iso(r["time"]) == newest_ts),
        key=lambda r: r["time"],
    )

    for var in selected["wind"]:
        raw = newest_row.get(var)
        if raw is None:
            continue
        unit = (das_vars.get(var, {}) or {}).get("units", "")
        if unit and "m s" in unit.replace("-1", "").replace("^-1", ""):
            mph = ms_to_mph(raw)
            plausible = self_check_plausibility(var, mph, WIND_MPH_BOUNDS)
            result["readings_f"].append((var, round(mph, 1), "mph", raw, unit, plausible))
            if not plausible:
                result["plausibility_warnings"].append(f"{var}: {mph:.1f} mph out of expected range")
        else:
            result["readings_other"].append((var, raw, unit))

    for var in selected["water_temp"]:
        raw = newest_row.get(var)
        if raw is None:
            continue
        depth_var = var + "_fixed_depth"
        depth_m = newest_row.get(depth_var)
        f_val = kelvin_to_f(raw)
        plausible = self_check_plausibility(var, f_val, WATER_TEMP_F_BOUNDS)
        result["readings_f"].append((var, round(f_val, 1), "F", raw, "K", plausible, depth_m))
        if not plausible:
            result["plausibility_warnings"].append(f"{var}: {f_val:.1f} F out of expected range")

    for var in selected["air_temp"]:
        raw = newest_row.get(var)
        if raw is None:
            continue
        f_val = kelvin_to_f(raw)
        plausible = self_check_plausibility(var, f_val, AIR_TEMP_F_BOUNDS)
        result["readings_f"].append((var, round(f_val, 1), "F", raw, "K", plausible))
        if not plausible:
            result["plausibility_warnings"].append(f"{var}: {f_val:.1f} F out of expected range")

    # PRIMARY VERDICT for this target - conservative thresholds, stated so
    # the reasoning is visible, not just the label.
    if result["age_hours"] <= 6:
        result["verdict_live"] = "LIVE"
    elif result["age_hours"] <= 48:
        result["verdict_live"] = f"REPORTING BUT STALE ({result['age_hours']}h old)"
    else:
        result["verdict_live"] = f"NOT LIVE - newest reading is {result['age_hours']}h old"

    if result["geojson_found"]:
        event = result["platform_event"]
        if event == "activated" and result["age_hours"] <= 6:
            result["verdict_platform_event_matches"] = "MATCHES - activated and reporting recently"
        elif event == "activated" and result["age_hours"] > 6:
            result["verdict_platform_event_matches"] = (
                f"MISMATCH - GLOS says 'activated' but newest reading is {result['age_hours']}h old"
            )
        else:
            result["verdict_platform_event_matches"] = f"platform_event='{event}', age={result['age_hours']}h"

    return result


# ----------------------------------------------------------------------
# Report printing
# ----------------------------------------------------------------------

def print_target_report(target, result):
    print("=" * 72)
    print(f"TARGET: {target['key']}  (obs_dataset_id={target['ods']}, pier={target['pier']})")
    print("=" * 72)
    print(f"GeoJSON found:      {result['geojson_found']}")
    print(f"platform_name:      {result['platform_name']}")
    print(f"platform_event:     {result['platform_event']}")
    print(f"ERDDAP .das OK:     {result['das_ok']}  (error: {result['das_error']})")
    if result["selected_vars"]:
        for cat, names in result["selected_vars"].items():
            if names:
                print(f"  {cat}: {names}")
    print(f"ERDDAP .csv OK:     {result['csv_ok']}  (error: {result['csv_error']})")
    print(f"Newest reading UTC: {result['newest_reading_utc']}")
    print(f"Age (hours):        {result['age_hours']}")
    print(f"Span returned (h):  {result['span_hours_returned']}  (requested {HISTORY_DAYS_BACK*24}h)")
    print(f"Cadence (minutes):  {result['cadence_minutes']}")
    if result["readings_f"]:
        print("Latest converted readings:")
        for reading in result["readings_f"]:
            if len(reading) == 7:
                var, conv, unit, raw, raw_unit, plausible, depth_m = reading
                depth_str = f", depth={depth_m}m" if depth_m is not None else ""
                flag = "" if plausible else "  <-- IMPLAUSIBLE, SEE WARNING"
                print(f"    {var}: {conv} {unit}  (raw {raw} {raw_unit}{depth_str}){flag}")
            else:
                var, conv, unit, raw, raw_unit, plausible = reading
                flag = "" if plausible else "  <-- IMPLAUSIBLE, SEE WARNING"
                print(f"    {var}: {conv} {unit}  (raw {raw} {raw_unit}){flag}")
    if result["plausibility_warnings"]:
        print("PLAUSIBILITY WARNINGS:")
        for w in result["plausibility_warnings"]:
            print(f"    WARNING: {w}")
    print(f"VERDICT (reporting status):   {result['verdict_live']}")
    print(f"VERDICT (platform_event vs actual): {result['verdict_platform_event_matches']}")
    print()


def main():
    now_utc = datetime.now(timezone.utc)
    print(f"PIERBITE GLOS Probe v3 - run started {now_utc.isoformat()}")
    print()

    geo_status, geo_text, geo_err = http_get(GEOJSON_URL)
    geojson_obj = None
    if geo_status == 200 and geo_text:
        try:
            geojson_obj = json.loads(geo_text)
            print(f"GeoJSON fetched OK: {len(geojson_obj.get('features', []))} platforms.")
        except json.JSONDecodeError as e:
            print(f"GeoJSON fetched but failed to parse: {e}")
    else:
        print(f"GeoJSON fetch FAILED: status={geo_status} error={geo_err}")
    print()

    all_results = {}
    var_sets_for_distinctness = {}
    for target in TARGETS:
        result = analyze_target(target, geojson_obj, now_utc)
        all_results[target["key"]] = result
        print_target_report(target, result)
        flat_vars = []
        for names in (result.get("selected_vars") or {}).values():
            flat_vars.extend(names)
        var_sets_for_distinctness[target["key"]] = flat_vars

    dist_ok, dist_msg = self_check_platform_distinctness(var_sets_for_distinctness)
    print("=" * 72)
    print("SELF-CHECK: cross-platform variable-set distinctness (D233)")
    print(f"  {'PASS' if dist_ok else 'FAIL'}: {dist_msg}")
    print("=" * 72)
    print()

    print("=" * 72)
    print("SUMMARY - ANSWERS TO THE QUEUED QUESTIONS")
    print("=" * 72)
    r576 = all_results.get("shipwreck_sentinel_45218", {})
    print(f"Q-45218-LIVE (PRIMARY): {r576.get('verdict_live', 'UNKNOWN')}")
    print(f"  platform_event vs actual: {r576.get('verdict_platform_event_matches', 'UNKNOWN')}")

    r598 = all_results.get("neshotah", {})
    span = r598.get("span_hours_returned")
    if span is not None and span >= 72:
        neshotah_verdict = f"REPLACE KMTW - {span}h of real history returned (>=72h)"
    elif span is not None:
        neshotah_verdict = f"SUPPLEMENT KMTW ONLY - only {span}h of real history returned (<72h)"
    else:
        neshotah_verdict = "UNKNOWN - no usable history returned"
    print(f"Q-NESHOTAH-FRESH: {neshotah_verdict}")

    r250 = all_results.get("port_washington", {})
    print(f"Port Washington reporting status: {r250.get('verdict_live', 'UNKNOWN')}")

    print()
    print("Q-PLATFORM-EVENT-FRESHNESS (all targets):")
    for key, r in all_results.items():
        print(f"  {key}: {r.get('verdict_platform_event_matches', 'UNKNOWN')}")
    print()
    print("Run complete.")


if __name__ == "__main__":
    main()
