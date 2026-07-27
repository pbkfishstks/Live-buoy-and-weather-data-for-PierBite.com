"""
PIERBITE — LMHOFS History & Jitter Probe
Generated: 2026-07-27

PURPOSE (Phase 1.3c, decision D96 / risk R32)
-----------------------------------------------
fetch_data.py v12 reads exactly ONE LMHOFS model run (the newest usable
one) and publishes no 72-hour water-temperature trend for a MODELED
reading. Phase 1.3c will rebuild that trend from an OLDER LMHOFS run.

Before writing any scoring code, this probe answers three open
questions that fetch_data.py cannot safely assume:

  Q1. RETENTION — does NOAA's THREDDS server still have a run from
      ~72 hours ago? The /{yyyy}/{mm}/{dd}/ folder structure implies
      old days exist, but nobody has confirmed how far back, or
      whether it's a hard cutoff or a slow gap in coverage.

  Q2. NODE STABILITY OVER TIME — do the six FROZEN node indices from
      LMHOFS_NODES (derived 2026-07-25, v6 probe) still return sane,
      plausible temperatures in an OLDER file? The mesh could in
      principle differ run-to-run even though node count is checked
      per-run in production (R21). This probe checks node count AND
      plausibility on the older file too.

  Q3. CYCLE-TO-CYCLE JITTER — LMHOFS re-initializes the model at each
      cycle (00/06/12/18 UTC). A 72h-ago-to-now delta will include
      some amount of model "reboot" noise on top of real water
      change. This probe estimates that noise by comparing TWO
      CONSECUTIVE cycles (6 hours apart) at the same node, where real
      water temperature change is small — so most of any swing seen
      is jitter, not signal. This number will inform whether the
      Phase 1.3c trend factor should use the full 2.4x weight
      score_water() currently applies to a buoy-measured 72h trend,
      or a damped weight.

This script does NOT touch fetch_data.py and does NOT modify
production data. It is a read-only diagnostic, run once via GitHub
Actions (same pattern as lmhofs-water-temp-probe-2026-07-25-v6.py),
with results reported in the workflow log for a human (or a future
Claude session) to read.

USAGE
-----
Run as a one-off GitHub Actions job, or locally if NOAA is reachable
from that environment. Prints a plain-text report. Exits 0 whether or
not older data was found — this is a diagnostic, not a pass/fail gate.
"""

import re
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------
# Config — copied verbatim from fetch_data.py v12 (LMHOFS section)
# so this probe reads the exact same six nodes the same way.
# ---------------------------------------------------------------
LMHOFS_BASE_DIR = (
    "https://opendap.co-ops.nos.noaa.gov/thredds/dodsC/"
    "NOAA/LMHOFS/MODELS/{yyyy}/{mm}/{dd}/"
)
LMHOFS_FIELDS_FILE = "lmhofs.t{cycle}z.{yyyy}{mm}{dd}.fields.n000.nc"
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

# How far back to test for retention. 30/14/7/3/1 days gives a clear
# picture of whether there's a hard cutoff or a gradual gap.
RETENTION_TEST_DAYS_AGO = [30, 14, 7, 3, 1]

_LMHOFS_NUMBER = re.compile(r"[-+]?\d*\.\d+(?:[eE][-+]?\d+)?|[-+]?\d+(?:[eE][-+]?\d+)?")
_LMHOFS_BRACKETS = re.compile(r"\[[^\]]*\]")
_LMHOFS_DIVIDER = re.compile(r"^-{3,}\s*$", re.MULTILINE)
_LMHOFS_DIM = re.compile(r"\[\s*(\w+)\s*=\s*(\d+)\s*\]")


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
    ok, body = lmhofs_get("%s.ascii?%s" % (file_url, query))
    if not ok:
        return None, body
    values = lmhofs_numbers(body)
    return (values[0] if values else None), None


def check_file_exists(url):
    """HEAD-style existence check via .dds (small, fast, no data pull)."""
    ok, body = lmhofs_get(url + ".dds", max_chars=4000)
    return ok and "Dataset" in body, body


def check_node_count(file_url):
    ok, dds = lmhofs_get(file_url + ".dds", max_chars=8000)
    if not ok:
        return None, dds
    node_count = None
    for line in dds.splitlines():
        stripped = line.strip().rstrip(";")
        head = _LMHOFS_BRACKETS.sub("", stripped).split()
        if len(head) >= 2 and head[1] == "temp":
            for name, size in _LMHOFS_DIM.findall(stripped):
                if name.lower().startswith("node"):
                    node_count = int(size)
    return node_count, None


def build_url(dt, cycle):
    parts = {"yyyy": dt.strftime("%Y"), "mm": dt.strftime("%m"),
              "dd": dt.strftime("%d"), "cycle": cycle}
    return LMHOFS_BASE_DIR.format(**parts) + LMHOFS_FIELDS_FILE.format(**parts)


def read_node_temp_f(file_url, node):
    celsius, err = lmhofs_read_value(file_url, "temp[0][0][%d]" % node)
    if celsius is None:
        return None, err
    f = round(celsius * 9.0 / 5.0 + 32.0, 2)
    if not (32.0 <= f <= 90.0):
        return None, "implausible %.1f F (raw %.3f C)" % (f, celsius)
    return f, None


def find_run_near(target_dt):
    """Find the closest usable run AT OR BEFORE target_dt, walking
    backwards through cycles/days the same way production does,
    just anchored at an arbitrary historical point instead of 'now'."""
    for day_offset in range(0, 3):
        day = target_dt - timedelta(days=day_offset)
        for cycle in LMHOFS_CYCLES:
            run_time = datetime(day.year, day.month, day.day,
                                 int(cycle), 0, 0, tzinfo=timezone.utc)
            if run_time > target_dt:
                continue
            url = build_url(day, cycle)
            exists, _ = check_file_exists(url)
            if exists:
                return url, run_time
    return None, None


def main():
    now = datetime.now(timezone.utc)
    print("=" * 70)
    print("PIERBITE — LMHOFS History & Jitter Probe")
    print("Run at: %s" % now.isoformat())
    print("=" * 70)

    # -----------------------------------------------------------
    # Q1 — RETENTION
    # -----------------------------------------------------------
    print("\n--- Q1: RETENTION (how far back does NOAA keep runs?) ---")
    retention_results = []
    for days_ago in RETENTION_TEST_DAYS_AGO:
        target = now - timedelta(days=days_ago)
        url, run_time = find_run_near(target)
        if url:
            print("  %3d days ago: FOUND  run=%s  url=%s"
                  % (days_ago, run_time.isoformat(), url))
            retention_results.append((days_ago, True, run_time))
        else:
            print("  %3d days ago: NOT FOUND (no file within 3-day backward walk)"
                  % days_ago)
            retention_results.append((days_ago, False, None))

    # Narrow in on exactly 72 hours, since that's what Phase 1.3c needs.
    target_72h = now - timedelta(hours=72)
    url_72h, run_time_72h = find_run_near(target_72h)
    print("\n  Exact 72h-ago target (%s):" % target_72h.isoformat())
    if url_72h:
        actual_age = (now - run_time_72h).total_seconds() / 3600.0
        print("    FOUND run at %s (%.1f h old, %.1f h off from exact 72h target)"
              % (run_time_72h.isoformat(), actual_age, abs(actual_age - 72)))
    else:
        print("    NOT FOUND — Phase 1.3c cannot use a fixed 72h lookup as-is "
              "if this keeps failing; would need a shorter/adaptive window.")

    # -----------------------------------------------------------
    # Q2 — NODE STABILITY on the 72h-ago file (if found)
    # -----------------------------------------------------------
    print("\n--- Q2: NODE STABILITY on older file ---")
    if url_72h:
        node_count, err = check_node_count(url_72h)
        if node_count is None:
            print("  Could not read node count: %s" % err)
        elif node_count != LMHOFS_EXPECTED_NODE_COUNT:
            print("  MISMATCH: expected %d nodes, older file has %d. "
                  "Frozen node indices may not be trustworthy this far back."
                  % (LMHOFS_EXPECTED_NODE_COUNT, node_count))
        else:
            print("  OK: older file has %d nodes, matches current mesh." % node_count)

        print("  Per-pier readings from the 72h-ago run:")
        for pier, node in LMHOFS_NODES.items():
            temp_f, err = read_node_temp_f(url_72h, node)
            if temp_f is not None:
                print("    %-14s node %5d -> %5.1f F" % (pier, node, temp_f))
            else:
                print("    %-14s node %5d -> FAILED (%s)" % (pier, node, err))
    else:
        print("  Skipped — no 72h-ago file found.")

    # -----------------------------------------------------------
    # Q3 — CYCLE-TO-CYCLE JITTER
    # Compare two CONSECUTIVE cycles (6h apart) at each node. Real
    # water temp barely moves in 6h, so most of the swing here is
    # model jitter/reinitialization noise, not signal.
    # -----------------------------------------------------------
    print("\n--- Q3: CYCLE-TO-CYCLE JITTER (6h apart, same-ish conditions) ---")
    # Use the most recent two available cycles found during retention scan.
    recent_url, recent_run = find_run_near(now)
    if recent_url:
        prior_target = recent_run - timedelta(hours=6)
        prior_url, prior_run = find_run_near(prior_target)
        if prior_url and prior_run != recent_run:
            print("  Comparing %s vs %s" % (recent_run.isoformat(), prior_run.isoformat()))
            diffs = []
            for pier, node in LMHOFS_NODES.items():
                t1, e1 = read_node_temp_f(recent_url, node)
                t2, e2 = read_node_temp_f(prior_url, node)
                if t1 is not None and t2 is not None:
                    diff = round(t1 - t2, 2)
                    diffs.append(diff)
                    print("    %-14s now=%.1fF  6h-prior=%.1fF  diff=%+.2fF"
                          % (pier, t1, t2, diff))
                else:
                    print("    %-14s FAILED (now err=%s, prior err=%s)" % (pier, e1, e2))
            if diffs:
                max_abs = max(abs(d) for d in diffs)
                avg_abs = sum(abs(d) for d in diffs) / len(diffs)
                print("\n  Jitter summary: max |diff| = %.2f F, avg |diff| = %.2f F "
                      "across %d piers" % (max_abs, avg_abs, len(diffs)))
                print("  (This is a ONE-SAMPLE estimate. Real jitter should be "
                      "assessed over several days before trusting a weight "
                      "decision — treat this as a first look, not a final number.)")
        else:
            print("  Could not find a distinct prior cycle 6h back to compare.")
    else:
        print("  Could not find a current run to anchor the jitter comparison.")

    print("\n" + "=" * 70)
    print("PROBE COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
