"""
PIERBITE — LMHOFS Trend Signal & Noise Probe (v4)
Generated: 2026-07-27

WHY v4 EXISTS
-------------
v3 correctly measured model jitter for the first time (avg 1.90 F,
max 2.33 F) using a same-valid-time forecast-vs-nowcast comparison.
But two things about that result need addressing before any scoring
weight is chosen:

  1. THE ERROR IS SYSTEMATIC, NOT RANDOM. All six piers came back
     POSITIVE and tightly grouped (+1.33 to +2.33 F). That is a
     coherent lake-wide offset, not scatter. This matters because
     the 72-hour trend is a SUBTRACTION (temp_now - temp_72h_ago),
     and correlated systematic error largely CANCELS in a
     subtraction. So 1.90 F likely OVERSTATES the error that will
     actually reach the trend term. Damping against it would be
     damping against a number we partly mis-measured.

  2. IT WAS ONE SAMPLE, and it measured forecast error at a 6-hour
     horizon — a proxy for, not the same thing as, nowcast-to-
     nowcast noise 72 hours apart.

The decisive question was never "how noisy is the model in the
abstract" — it is "is the 72-hour signal we want to publish LARGER
than the noise riding on it?" That is a signal-to-noise question,
and it can be answered with data we already know exists: v1/v2
confirmed NOAA retains at least 30 days of runs. So instead of
waiting days for more samples, this probe reads the history.

WHAT THIS PROBE DOES
--------------------
PART 1 — SIGNAL. Reads nearshore water temperature at all six frozen
  pier nodes, once per day, for the last 30 days (12z run each day).
  From that daily series it computes every available 24h, 48h and
  72h change per pier and reports the real distribution: median,
  mean absolute, standard deviation, largest swings, and how often
  changes exceed various thresholds. This is the actual behaviour of
  the factor Phase 1.3c intends to publish.

PART 2 — NOISE. Repeats v3's same-valid-time jitter test on several
  DIFFERENT historical days, not just one, to see whether the ~1.9 F
  figure is stable or was a one-off. Also reports the SPREAD of the
  per-pier jitter values on each day, because a tight spread confirms
  the systematic-offset reading above (and therefore that much of it
  cancels in a difference), while a wide scatter would mean genuinely
  random error that does NOT cancel.

PART 3 — VERDICT. Puts signal and noise side by side so the scoring
  weight and the trend window (24h vs 48h vs 72h) can both be chosen
  from evidence rather than judgement.

Read-only. Touches no production files. Roughly 230 small OPeNDAP
requests with a polite delay between them; expect a few minutes of
runtime. Run manually via GitHub Actions, same as v1/v2/v3.
"""

import re
import time
import statistics
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
# Confirmed to exist by v3: f001 through f006 all returned FOUND.
LMHOFS_FORECAST_FILE = "lmhofs.t{cycle}z.{yyyy}{mm}{dd}.fields.f{fhour:03d}.nc"
LMHOFS_TIMEOUT = 60
LMHOFS_USER_AGENT = "PierBiteDotCom (contact: pierbite project owner)"

LMHOFS_NODES = {
    "sheboygan": 20022,
    "manitowoc": 21438,
    "two_rivers": 23983,
    "kewaunee": 28542,
    "algoma": 28904,
    "sturgeon_bay": 31190,
}

# Sample the same cycle every day so the series isn't polluted by
# time-of-day differences. 12z is mid-morning Central — a cycle that
# has reliably existed in every check so far.
DAILY_CYCLE = "12"
HISTORY_DAYS = 30

# Days back on which to repeat the jitter test (each compares that
# day's 06z +6h forecast against the same day's 12z nowcast).
JITTER_TEST_DAYS_AGO = [1, 4, 8, 15, 25]

# Be polite to NOAA's server on a several-hundred-request diagnostic.
REQUEST_DELAY_SEC = 0.15

_LMHOFS_NUMBER = re.compile(r"[-+]?\d*\.\d+(?:[eE][-+]?\d+)?|[-+]?\d+(?:[eE][-+]?\d+)?")
_LMHOFS_BRACKETS = re.compile(r"\[[^\]]*\]")
_LMHOFS_DIVIDER = re.compile(r"^-{3,}\s*$", re.MULTILINE)


def lmhofs_escape(query):
    """Percent-escape array brackets — NOT optional (v1 proved this
    with six HTTP 400s)."""
    return query.replace("[", "%5B").replace("]", "%5D")


def lmhofs_get(url, timeout=LMHOFS_TIMEOUT, max_chars=4000):
    time.sleep(REQUEST_DELAY_SEC)
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


def read_node_temp_f(file_url, node):
    """Surface temperature in F at one node, or (None, error)."""
    ok, body = lmhofs_get("%s.ascii?%s"
                           % (file_url, lmhofs_escape("temp[0][0][%d]" % node)))
    if not ok:
        return None, body
    values = lmhofs_numbers(body)
    if not values:
        return None, "no numeric value returned"
    f = round(values[0] * 9.0 / 5.0 + 32.0, 2)
    if not (32.0 <= f <= 90.0):
        return None, "implausible %.1f F" % f
    return f, None


def nowcast_url(day, cycle=DAILY_CYCLE):
    parts = {"yyyy": day.strftime("%Y"), "mm": day.strftime("%m"),
              "dd": day.strftime("%d"), "cycle": cycle}
    return LMHOFS_BASE_DIR.format(**parts) + LMHOFS_NOWCAST_FILE.format(**parts)


def forecast_url(day, cycle, fhour):
    parts = {"yyyy": day.strftime("%Y"), "mm": day.strftime("%m"),
              "dd": day.strftime("%d"), "cycle": cycle, "fhour": fhour}
    return LMHOFS_BASE_DIR.format(**parts) + LMHOFS_FORECAST_FILE.format(**parts)


def describe(values, label, unit="F"):
    """Print a compact distribution summary for a list of numbers."""
    if not values:
        print("    %-28s (no data)" % label)
        return None
    abs_vals = [abs(v) for v in values]
    stats = {
        "n": len(values),
        "median_abs": statistics.median(abs_vals),
        "mean_abs": statistics.mean(abs_vals),
        "max_abs": max(abs_vals),
        "stdev": statistics.pstdev(values) if len(values) > 1 else 0.0,
    }
    print("    %-28s n=%3d  median|Δ|=%5.2f%s  mean|Δ|=%5.2f%s  "
          "max|Δ|=%5.2f%s  sd=%5.2f"
          % (label, stats["n"], stats["median_abs"], unit,
             stats["mean_abs"], unit, stats["max_abs"], unit, stats["stdev"]))
    return stats


def main():
    now = datetime.now(timezone.utc)
    print("=" * 74)
    print("PIERBITE — LMHOFS Trend Signal & Noise Probe v4")
    print("Run at: %s" % now.isoformat())
    print("=" * 74)

    # ===========================================================
    # PART 1 — SIGNAL: 30 days of daily nearshore temperature
    # ===========================================================
    print("\n" + "-" * 74)
    print("PART 1 — SIGNAL: daily nearshore temperature, last %d days (%sz runs)"
          % (HISTORY_DAYS, DAILY_CYCLE))
    print("-" * 74)

    # series[pier] = list of (day_index, temp_f); day_index 0 = oldest
    series = {pier: {} for pier in LMHOFS_NODES}
    days_found = 0
    days_missing = []

    for back in range(HISTORY_DAYS, -1, -1):
        day = now - timedelta(days=back)
        url = nowcast_url(day)
        day_label = day.strftime("%Y-%m-%d")
        got_any = False
        for pier, node in LMHOFS_NODES.items():
            temp_f, err = read_node_temp_f(url, node)
            if temp_f is not None:
                series[pier][back] = temp_f
                got_any = True
        if got_any:
            days_found += 1
            row = "  %s  " % day_label
            row += "  ".join(
                "%s=%5.1f" % (p[:4], series[p][back]) if back in series[p]
                else "%s=  --" % p[:4]
                for p in LMHOFS_NODES
            )
            print(row)
        else:
            days_missing.append(day_label)

    print("\n  Coverage: %d of %d days returned data." % (days_found, HISTORY_DAYS + 1))
    if days_missing:
        print("  Missing days: %s" % ", ".join(days_missing))

    # ---- compute change distributions at 24 / 48 / 72 hours -----
    print("\n  Distribution of real temperature CHANGES (the signal):")
    window_stats = {}
    for hours, step in ((24, 1), (48, 2), (72, 3)):
        all_changes = []
        for pier in LMHOFS_NODES:
            pts = series[pier]
            for back in pts:
                older = back + step
                if older in pts:
                    all_changes.append(round(pts[back] - pts[older], 2))
        window_stats[hours] = describe(all_changes, "%dh changes (all piers)" % hours)

    print("\n  Per-pier 72h change detail:")
    for pier in LMHOFS_NODES:
        pts = series[pier]
        changes = [round(pts[b] - pts[b + 3], 2) for b in pts if (b + 3) in pts]
        describe(changes, pier)

    # ===========================================================
    # PART 2 — NOISE: repeat the same-valid-time jitter test
    # ===========================================================
    print("\n" + "-" * 74)
    print("PART 2 — NOISE: same-valid-time jitter, repeated across %d days"
          % len(JITTER_TEST_DAYS_AGO))
    print("-" * 74)
    print("  Each test: that day's 06z run forecasting +6h, vs that day's 12z")
    print("  nowcast. Both describe the SAME hour, so any gap is model")
    print("  disagreement, not real water change.\n")

    daily_jitter_means = []
    all_jitter_values = []

    for days_ago in JITTER_TEST_DAYS_AGO:
        day = now - timedelta(days=days_ago)
        f_url = forecast_url(day, "06", 6)
        n_url = nowcast_url(day, "12")
        diffs = []
        for pier, node in LMHOFS_NODES.items():
            t_fore, _ = read_node_temp_f(f_url, node)
            t_now, _ = read_node_temp_f(n_url, node)
            if t_fore is not None and t_now is not None:
                diffs.append(round(t_now - t_fore, 2))
        if diffs:
            all_jitter_values.extend(diffs)
            mean_signed = statistics.mean(diffs)
            mean_abs = statistics.mean([abs(d) for d in diffs])
            spread = max(diffs) - min(diffs)
            daily_jitter_means.append(mean_signed)
            print("  %s  mean signed=%+5.2fF  mean|Δ|=%5.2fF  spread=%5.2fF  %s"
                  % (day.strftime("%Y-%m-%d"), mean_signed, mean_abs, spread,
                     [("%+.2f" % d) for d in diffs]))
        else:
            print("  %s  (no data)" % day.strftime("%Y-%m-%d"))

    if all_jitter_values:
        print("\n  Across all jitter samples:")
        describe(all_jitter_values, "all per-pier jitter values")
        if len(daily_jitter_means) > 1:
            print("    Daily mean SIGNED jitter: %s"
                  % ", ".join("%+.2f" % m for m in daily_jitter_means))
            print("    -> If these signed means are consistently the same sign,")
            print("       the error is a systematic lake-wide offset that")
            print("       largely CANCELS in a temperature DIFFERENCE.")
            print("       If they flip sign day to day, the error is random")
            print("       and does NOT cancel — damping would be justified.")

    # ===========================================================
    # PART 3 — VERDICT
    # ===========================================================
    print("\n" + "-" * 74)
    print("PART 3 — SIGNAL vs NOISE")
    print("-" * 74)

    if all_jitter_values:
        noise = statistics.mean([abs(v) for v in all_jitter_values])
        print("  Measured noise (mean |jitter|):            %5.2f F" % noise)
        for hours in (24, 48, 72):
            st = window_stats.get(hours)
            if st:
                ratio = st["median_abs"] / noise if noise else float("inf")
                print("  %dh signal (median |change|): %5.2f F   "
                      "signal-to-noise = %4.2fx"
                      % (hours, st["median_abs"], ratio))
        print("\n  Reading this: a ratio comfortably above 1 means the real")
        print("  water-temperature movement is larger than model disagreement,")
        print("  and the trend can carry meaningful weight. A ratio near or")
        print("  below 1 means the factor would mostly publish model noise,")
        print("  and should be damped or given a longer window.")
    else:
        print("  No jitter samples succeeded — cannot compute a ratio.")

    print("\n" + "=" * 74)
    print("PROBE COMPLETE")
    print("=" * 74)


if __name__ == "__main__":
    main()
