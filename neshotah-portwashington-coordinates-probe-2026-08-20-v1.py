#!/usr/bin/env python3
# PIERBITE | Neshotah + Port Washington Coordinates Probe | 2026-08-20T20:15:00Z | v1
# Repo root filename (GitHub, prefix removed per D211): neshotah-portwashington-coordinates-probe-2026-08-20-v1.py
# Local archive filename (Paul's machine):             Scripts_neshotah-portwashington-coordinates-probe-2026-08-20-v1.py
#
# PURPOSE (Q-NESHOTAH-COORDS, R89):
#   Read the exact published lat/lon for two GLOS Seagull platforms straight
#   from the source, so fetch_data.py v22 can fill in STATION_HISTORY["NESHOTAH"]
#   without guessing (D14/D63 - never publish an unverified position).
#     1. Neshotah Park Met Station (obs_dataset_id 598) - Two Rivers wind.
#        Fixes wind_locality: "unknown" on the live site (D247/R89).
#     2. Port Washington, WI, USA (obs_dataset_id 250) - needed for the
#        future fetch_data.py v24 pier entry, captured here at no extra cost.
#
# WHY THIS IS A SMALL, LOW-RISK PROBE, NOT A NEW INVESTIGATION:
#   The GLOS investigation (Q-45218-LIVE, Q-NESHOTAH-FRESH) is CLOSED. This
#   probe does not re-open it. It reads ONE field (geometry.coordinates,
#   GeoJSON [lon, lat]) from the same public catalogue endpoint every prior
#   GLOS probe already used, and does not touch ERDDAP, wind, or water data.
#
# READ-ONLY. Standard library only (json, math, sys, urllib). Never writes
# to disk. Never calls git/shell/subprocess.
#
# Runs inside GitHub Actions because this project's dev sandbox cannot reach
# seagull-api.glos.org (same allowlist restriction as every earlier NDBC/GLOS
# probe here) - not because the API needs a login. It doesn't; it's public.
#
# SELF-CHECK (D233 - every probe must carry a check that would catch its own
# failure mode): each platform's coordinates are compared, by real-world
# distance, against that pier's own known location. A swapped lat/lon, a
# wrong platform match, or a units mistake would show up as a wildly wrong
# distance instead of silently passing through as two plausible-looking
# numbers.

import json
import math
import sys
import urllib.error
import urllib.request

GEOJSON_URL = "https://seagull-api.glos.org/api/v1/obs-datasets.geojson"

# Known pier locations, already live in fetch_data.py / project memory -
# used ONLY for the sanity check below, never written anywhere.
TARGETS = [
    {
        "key": "NESHOTAH",
        "ods": 598,
        "expected_name_contains": "neshotah",
        "pier_label": "Two Rivers pier",
        "pier_lat": 44.147061,
        "pier_lon": -87.565680,
        "max_plausible_mi": 5.0,  # prior probes measured ~0.6 mi
    },
    {
        "key": "PORT_WASHINGTON",
        "ods": 250,
        "expected_name_contains": "port washington",
        "pier_label": "Port Washington breakwater light",
        "pier_lat": 43.3853,
        "pier_lon": -87.8597,
        "max_plausible_mi": 10.0,  # prior probes measured ~5.0 mi
    },
]


def http_get(url, timeout=25):
    """Return (status_code, body_text_or_None, error_str_or_None).
    Never raises - same tri-state pattern as every prior PIERBITE probe."""
    req = urllib.request.Request(url, headers={"User-Agent": "pierbite-coords-probe-v1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace"), None
    except urllib.error.HTTPError as e:
        try:
            body_snippet = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            body_snippet = ""
        detail = body_snippet.strip() or (e.reason or "")
        return e.code, None, f"HTTPError {e.code}: {detail}"
    except urllib.error.URLError as e:
        return None, None, f"URLError: {e.reason}"
    except Exception as e:  # noqa: BLE001 - a probe must never crash mid-run
        return None, None, f"Unexpected error: {e}"


def haversine_miles(lat1, lon1, lat2, lon2):
    r_miles = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r_miles * math.asin(math.sqrt(a))


def find_platform_by_ods(geojson_obj, ods):
    """Same lookup pattern as glos-probe-v3: match on obs_dataset_id (NOT
    org_platform_id - D232), and pull geometry.coordinates as [lon, lat]."""
    if not geojson_obj:
        return None, None
    for feature in geojson_obj.get("features", []):
        props = feature.get("properties", {})
        if props.get("obs_dataset_id") == ods:
            geom = feature.get("geometry", {}) or {}
            coords = geom.get("coordinates")
            return props, coords
    return None, None


def analyze_target(target, geojson_obj):
    key = target["key"]
    ods = target["ods"]
    print(f"\n=== {key} (obs_dataset_id {ods}) ===")

    props, coords = find_platform_by_ods(geojson_obj, ods)

    if props is None:
        print(f"  FAIL: no feature with obs_dataset_id == {ods} found in the GeoJSON catalogue.")
        return {"key": key, "ok": False, "lat": None, "lon": None}

    platform_name = props.get("platform_name", "")
    platform_event = props.get("platform_event")
    print(f"  platform_name  : {platform_name!r}")
    print(f"  platform_event : {platform_event!r}")

    expected = target["expected_name_contains"]
    if expected not in (platform_name or "").lower():
        print(f"  WARNING: platform_name does not contain expected text {expected!r} - "
              f"verify this is really the right platform before trusting its coordinates.")

    if not coords or len(coords) < 2:
        print(f"  FAIL: no usable geometry.coordinates on this feature: {coords!r}")
        return {"key": key, "ok": False, "lat": None, "lon": None}

    lon, lat = coords[0], coords[1]  # GeoJSON order is [lon, lat]
    print(f"  coordinates (GeoJSON [lon, lat]) : [{lon}, {lat}]")
    print(f"  lat = {lat}")
    print(f"  lon = {lon}")

    dist_mi = haversine_miles(lat, lon, target["pier_lat"], target["pier_lon"])
    print(f"  distance to {target['pier_label']} : {dist_mi:.2f} mi "
          f"(plausible ceiling for this probe: {target['max_plausible_mi']} mi)")

    ok = dist_mi <= target["max_plausible_mi"]
    if not ok:
        print(f"  WARNING: distance exceeds the plausible ceiling. Do NOT use these "
              f"coordinates without manually re-checking the GLOS platform page for "
              f"obs_{ods} first - this could mean a lat/lon swap, a wrong platform "
              f"match, or a units problem.")
    else:
        print("  Self-check PASSED: distance to the known pier is plausible.")

    return {"key": key, "ok": ok, "lat": lat, "lon": lon, "distance_mi": round(dist_mi, 2)}


def main():
    print("PIERBITE Neshotah + Port Washington Coordinates Probe v1")
    print(f"Fetching: {GEOJSON_URL}\n")

    status, text, err = http_get(GEOJSON_URL)
    if status != 200 or not text:
        print(f"FAIL: could not fetch GeoJSON catalogue. status={status} error={err}")
        sys.exit(1)

    try:
        geojson_obj = json.loads(text)
    except Exception as e:
        print(f"FAIL: GeoJSON did not parse as JSON: {e}")
        sys.exit(1)

    n_features = len(geojson_obj.get("features", []))
    print(f"Catalogue fetched OK: {n_features} platforms listed.\n")

    results = [analyze_target(t, geojson_obj) for t in TARGETS]

    print("\n=== SUMMARY (copy this block back to Claude) ===")
    all_ok = True
    for r in results:
        status_word = "OK" if r["ok"] else "NEEDS REVIEW"
        print(f"{r['key']}: lat={r.get('lat')}, lon={r.get('lon')}, "
              f"distance_mi={r.get('distance_mi')}, self_check={status_word}")
        if not r["ok"]:
            all_ok = False

    print("\nOverall:", "ALL SELF-CHECKS PASSED" if all_ok else "AT LEAST ONE SELF-CHECK FAILED - see WARNING lines above")


if __name__ == "__main__":
    main()
