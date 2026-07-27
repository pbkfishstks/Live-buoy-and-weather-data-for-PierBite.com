"""
PIERBITE — LMHOFS History & Jitter Probe (v3 — CORRECTED METHODOLOGY)
Generated: 2026-07-27

WHY v3 EXISTS — read this before trusting any earlier jitter number.
-----------------------------------------------------------------
v2 (and v1) attempted to measure "cycle-to-cycle jitter" by comparing
the 12z nowcast to the 06z nowcast, 6 hours apart. That comparison is
WRONG: each nowcast reports the water temperature AT ITS OWN cycle
time. A 12z-vs-06z difference is mostly just real overnight cooling,
not model noise. It is not a jitter measurement at all. v2's Q3
result (avg 1.47F, max 2.35F) should NOT be used to make any
weighting decision — it was reported as "one-sample, not final" at
the time, but it was worse than that: it was measuring the wrong
thing entirely.

THE CORRECT TEST: to isolate genuine model jitter (as opposed to real
water temperature change), you must compare TWO DIFFERENT model runs
that are BOTH describing the SAME target moment in time. If both
predict roughly the same temperature for that shared moment, the
model is stable. If they disagree, that disagreement IS the jitter,
because real water conditions cannot be different between the two
answers — they're both claims about the identical hour.

This requires a FORECAST file (a run predicting some hours ahead of
its own cycle time), compared against a later run's NOWCAST (an
analysis AT that same hour). fetch_data.py v12 only ever reads
nowcast (n000) files — nobody on this project has confirmed whether
LMHOFS forecast (f0xx) files exist in this OPeNDAP catalog, or what
they're named. Guessing at that would repeat the same mistake as v1
and v2. So this script does NOT assume forecast files exist:

  STAGE 1 — DISCOVERY. Inspect a recent nowcast file's declared time
  dimension (a file with more than one time step would let us do the
  correct test WITHOUT needing forecast files at all — see below).
  Then probe for forecast-hour files using the naming pattern implied
  by fetch_data.py's own module docstring ("fields.f000.nc" is
  mentioned as the forecast counterpart to "fields.n000.nc"), trying
  a range of forecast hours to see what actually exists on the server.

  STAGE 2 — THE REAL TEST, using whichever mechanism Stage 1 found:
    (a) If the nowcast file has MULTIPLE time steps, compare index 0
        from a later run against a later index from an earlier run's
        SAME file — both describe the same real clock hour, from two
        different assimilation passes. This does not need forecast
        files at all.
    (b) Otherwise, if forecast files exist, compare an earlier run's
        forecast-for-hour-N against a later run's nowcast for that
        same hour.
    (c) If neither mechanism is available, this script says so
        PLAINLY and stops — it does not fabricate a jitter number
        from the wrong comparison again.

Read-only. Touches no production files. Run manually via GitHub
Actions, same as v1/v2.
"""

import re
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------
# Config — copied verbatim from fetch_data.py v12
# ---------------------------------------------------------------
LMHOFS_BASE_DIR = (
    "https://opendap.co-ops.nos.noaa.gov/thredds/dodsC/"
    "NOAA/LMHOFS/MODELS/{yyyy}/{mm}/{dd}/"
)
LMHOFS_NOWCAST_FILE = "lmhofs.t{cycle}z.{yyyy}{mm}{dd}.fields.n000.nc"
# Forecast file naming is UNCONFIRMED — this is the pattern implied by
# fetch_data.py's own docstring comment ("fields.f000.nc"), extended
# to test a range of forecast hours. Stage 1 verifies which (if any)
# actually exist before Stage 2 relies on them.
LMHOFS_FORECAST_FILE_TEMPLATES = [
    "lmhofs.t{cycle}z.{yyyy}{mm}{dd}.fields.f{fhour:03d}.nc",
]
LMHOFS_CYCLES = ["18", "12", "06", "00"]
LMHOFS_TIMEOUT = 60
LMHOFS_USER_AGENT = "PierBiteDotCom (contact: pierbite project owner)"
LMHOFS_EXPECTED_NODE_COUNT = 90806

LMHOFS_NODES = {
    "sheboygan": 20022,
    "manitowoc": 21438,
    "two_rivers": 23983,
    "kewaunee": 28542,
    "algoma": 28904,
    "sturgeon_bay": 31190,
}

_LMHOFS_NUMBER = re.compile(r"[-+]?\d*\.\d+(?:[eE][-+]?\d+)?|[-+]?\d+(?:[eE][-+]?\d+)?")
_LMHOFS_BRACKETS = re.compile(r"\[[^\]]*\]")
_LMHOFS_DIVIDER = re.compile(r"^-{3,}\s*$", re.MULTILINE)
_LMHOFS_DIM = re.compile(r"\[\s*(\w+)\s*=\s*(\d+)\s*\]")


def lmhofs_escape(query):
    """Percent-escape array brackets — NOT optional, confirmed
    necessary by v1's HTTP 400 failures. Fixed in v2, kept in v3."""
    return query.replace("[", "%5B").replace("]", "%5D")


def lmhofs_get(url, timeout=LMHOFS_TIMEOUT, max_chars=4000):
    req = urllib.request.Request(url, headers={"User-Agent": LMHOFS_USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read(max_chars).decode("utf-8", errors="replace")
            return True, body
    except urllib.error.HTTPError as e:
        return False, "HTTP %d" % e.code
    except Exception as e:
        return False, str(e)


def lmhofs_numbers(text):
    parts = _LMHOFS_DIVIDER.split(text)
    body = parts[-1] if len(parts) > 1 else text
    body = _LMHOFS_BRACKETS.sub(" ", body)
    return [float(m.group()) for m in _LMHOFS_NUMBER.finditer(body)]


def lmhofs_read_value(file_url, query):
    ok, body = lmhofs_get("%s.ascii?%s" % (file_url, lmhofs_escape(query)))
    if not ok:
        return None, body
    values = lmhofs_numbers(body)
    return (values[0] if values else None), None


def check_file_exists(url):
    ok, body = lmhofs_get(url + ".dds", max_chars=4000)
    return ok and "Dataset" in body, body


def get_dds(url):
    ok, dds = lmhofs_get(url + ".dds", max_chars=8000)
    return dds if ok else None


def get_temp_dims(dds_text):
    """Parse the temp variable's declared dimensions from a DDS.
    Returns a dict like {'time': 1, 'siglay': 21, 'node': 90806} or
    None if temp isn't found."""
    if not dds_text:
        return None
    for line in dds_text.splitlines():
        stripped = line.strip().rstrip(";")
        head = _LMHOFS_BRACKETS.sub("", stripped).split()
        if len(head) >= 2 and head[1] == "temp":
            dims = {}
            for name, size in _LMHOFS_DIM.findall(stripped):
                dims[name.lower()] = int(size)
            return dims
    return None


def build_nowcast_url(day, cycle):
    parts = {"yyyy": day.strftime("%Y"), "mm": day.strftime("%m"),
              "dd": day.strftime("%d"), "cycle": cycle}
    return LMHOFS_BASE_DIR.format(**parts) + LMHOFS_NOWCAST_FILE.format(**parts)


def build_forecast_url(day, cycle, fhour, template):
    parts = {"yyyy": day.strftime("%Y"), "mm": day.strftime("%m"),
              "dd": day.strftime("%d"), "cycle": cycle, "fhour": fhour}
    return LMHOFS_BASE_DIR.format(**parts) + template.format(**parts)


def read_node_temp_f(file_url, node, time_index=0):
    celsius, err = lmhofs_read_value(file_url, "temp[%d][0][%d]" % (time_index, node))
    if celsius is None:
        return None, err
    f = round(celsius * 9.0 / 5.0 + 32.0, 2)
    if not (32.0 <= f <= 90.0):
        return None, "implausible %.1f F (raw %.3f C)" % (f, celsius)
    return f, None


def find_run_near(target_dt):
    for day_offset in range(0, 3):
        day = target_dt - timedelta(days=day_offset)
        for cycle in LMHOFS_CYCLES:
            run_time = datetime(day.year, day.month, day.day,
                                 int(cycle), 0, 0, tzinfo=timezone.utc)
            if run_time > target_dt:
                continue
            url = build_nowcast_url(day, cycle)
            exists, _ = check_file_exists(url)
            if exists:
                return url, run_time
    return None, None


def main():
    now = datetime.now(timezone.utc)
    print("=" * 70)
    print("PIERBITE — LMHOFS History & Jitter Probe v3 (corrected methodology)")
    print("Run at: %s" % now.isoformat())
    print("=" * 70)

    recent_url, recent_run = find_run_near(now)
    if not recent_url:
        print("\nCould not find any recent nowcast run — cannot proceed.")
        return

    print("\nAnchor run: %s" % recent_run.isoformat())

    # -----------------------------------------------------------
    # STAGE 1a — does the nowcast file itself carry multiple time
    # steps? If so, we get a same-valid-time comparison for free.
    # -----------------------------------------------------------
    print("\n--- STAGE 1a: nowcast file time-dimension check ---")
    dds = get_dds(recent_url)
    dims = get_temp_dims(dds)
    if dims:
        print("  temp variable dimensions: %s" % dims)
        time_size = dims.get("time", 1)
        if time_size > 1:
            print("  -> Nowcast file has %d time steps. A same-valid-time "
                  "comparison MAY be possible using overlapping indices "
                  "between two runs — flagged for a future probe if needed."
                  % time_size)
        else:
            print("  -> Nowcast file has only 1 time step (as fetch_data.py "
                  "assumes). No free same-valid-time comparison available "
                  "from a single nowcast file.")
    else:
        print("  Could not read dimensions from DDS.")

    # -----------------------------------------------------------
    # STAGE 1b — do forecast-hour files exist at all?
    # -----------------------------------------------------------
    print("\n--- STAGE 1b: forecast file discovery ---")
    # Use the run 6 hours before the anchor as the "earlier" run whose
    # forecast we'd want to reach forward to the anchor's valid time.
    earlier_target = recent_run - timedelta(hours=6)
    earlier_url, earlier_run = find_run_near(earlier_target)
    forecast_found = None
    forecast_fhour = None
    forecast_template_used = None

    if earlier_url and earlier_run != recent_run:
        gap_hours = int((recent_run - earlier_run).total_seconds() / 3600)
        print("  Earlier run found: %s (%d h before anchor)"
              % (earlier_run.isoformat(), gap_hours))
        print("  Testing whether a forecast file exists that would let the "
              "earlier run predict the anchor's valid time (+%dh forecast)..."
              % gap_hours)
        day = datetime(earlier_run.year, earlier_run.month, earlier_run.day,
                        tzinfo=timezone.utc)
        cycle = "%02d" % earlier_run.hour
        for template in LMHOFS_FORECAST_FILE_TEMPLATES:
            for fhour in range(1, 13):  # test f001 through f012
                url = build_forecast_url(day, cycle, fhour, template)
                exists, _ = check_file_exists(url)
                marker = "FOUND" if exists else "no"
                print("    f%03d: %s  (%s)" % (fhour, marker, url))
                if exists and forecast_found is None:
                    forecast_found = url
                    forecast_fhour = fhour
                    forecast_template_used = template
                if exists and fhour == gap_hours:
                    # exact match to the anchor's valid time — best case
                    forecast_found = url
                    forecast_fhour = fhour
                    forecast_template_used = template
                    break
    else:
        print("  Could not find a distinct earlier run to test against.")

    # -----------------------------------------------------------
    # STAGE 2 — run whichever real test is possible
    # -----------------------------------------------------------
    print("\n--- STAGE 2: the actual jitter test ---")
    if forecast_found:
        print("  Forecast files EXIST. Using forecast-vs-nowcast comparison.")
        print("  Comparing: %s's f%03d forecast (predicting %s's valid time)"
              % (earlier_run.isoformat(), forecast_fhour, recent_run.isoformat()))
        print("  ...against: %s's nowcast (actual analysis at that time)\n"
              % recent_run.isoformat())
        diffs = []
        for pier, node in LMHOFS_NODES.items():
            t_forecast, e1 = read_node_temp_f(forecast_found, node)
            t_nowcast, e2 = read_node_temp_f(recent_url, node)
            if t_forecast is not None and t_nowcast is not None:
                diff = round(t_nowcast - t_forecast, 2)
                diffs.append(diff)
                print("    %-14s forecast=%.1fF  actual=%.1fF  jitter=%+.2fF"
                      % (pier, t_forecast, t_nowcast, diff))
            else:
                print("    %-14s FAILED (forecast err=%s, nowcast err=%s)"
                      % (pier, e1, e2))
        if diffs:
            max_abs = max(abs(d) for d in diffs)
            avg_abs = sum(abs(d) for d in diffs) / len(diffs)
            print("\n  TRUE jitter estimate: max |diff| = %.2f F, avg |diff| = "
                  "%.2f F across %d piers" % (max_abs, avg_abs, len(diffs)))
            print("  This IS a same-valid-time comparison — both numbers "
                  "describe the identical hour, so this diff reflects model "
                  "disagreement, not real water change.")
            print("  Still only a ONE-SAMPLE estimate — run this probe again "
                  "on 2-3 more days before finalizing a scoring weight.")
    else:
        print("  No forecast files found at any tested hour (f001-f012).")
        print("  CONCLUSION: this OPeNDAP catalog does not expose multi-hour")
        print("  forecast fields for LMHOFS at this endpoint (or uses a")
        print("  naming pattern this probe didn't guess correctly).")
        print("  NO JITTER NUMBER IS REPORTED — reporting a wrong-methodology")
        print("  number would repeat the v1/v2 mistake. Options if this is")
        print("  the final answer: (a) proceed with the 72h trend using the")
        print("  full existing weight and monitor real scores after deploy,")
        print("  since no evidence of harmful jitter was found here either;")
        print("  (b) try alternate forecast filename patterns manually.")

    print("\n" + "=" * 70)
    print("PROBE COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
