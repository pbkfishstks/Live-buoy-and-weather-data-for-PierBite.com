"""
PierBite.com - WATER TREND TRANSFORM DERIVATION
Built 2026-07-28 ~14:20 UTC | v1 | Phase 1.3c Step 2

WHAT THIS DOES
--------------
Reads calibration/nearshore_water_history_30d.csv (committed by Step 1)
and DERIVES the constants for a new score_water() trend term:

    - a saturating (tanh) curve, so no real event ever hits a hard
      wall and every extreme stays distinguishable from every other
      extreme (D108)
    - an asymmetric cooling:warming range, cooling favoured, because
      the base curve already prices the water's level and penalising
      warming a second time double-counts it (D107)

This script does not touch fetch_data.py and does not touch data.json.
It only reads the committed CSV and prints numbers. THE CONSTANTS IT
PRINTS ARE WHAT GOES INTO fetch_data.py v13 (Step 3) - they are not
copied from here automatically, and Step 3 must be built by hand
using the values this script reports, so there is one deliberate
human-reviewed step between "the data says X" and "the site does X".

WHY A SANITY GATE COMES FIRST
------------------------------
The whole point of committing the calibration CSV (D110) was so the
162-sample figures already recorded in project memory - median 6.77F,
90th percentile 14.65F, max 19.01F - are independently re-derivable,
not re-typed. If this script's OWN reconstruction of the 162 samples
does not match those figures, the reader is wrong, and every constant
downstream of it would be wrong too. So this script REFUSES to derive
anything if the sanity gate fails - it prints the mismatch and stops.

THE TRANSFORM
--------------
Two branches, both saturating, split at change_72h_f = 0:

    cooling (change_72h_f < 0, water getting colder):
        trend = COOL_MAX * tanh(-change_72h_f / K_COOL)

    warming (change_72h_f > 0, water getting warmer):
        trend = -WARM_MAX * tanh(change_72h_f / K_WARM)

    no data:
        trend = 0   (unchanged from the live formula)

tanh(x) approaches but never reaches 1, so trend never hits COOL_MAX
or -WARM_MAX exactly - there is no hard wall, and a -19F event always
scores strictly higher than a -9F event, however close both get to
the ceiling. This is what "no pegging" means for a saturating curve;
it is a different guarantee than the old clamp's "pegs 6% of the time
at 0.9x" - here the pegging rate is not lowered, it is architecturally
zero.

K_COOL and K_WARM are each chosen so that the 90th-percentile REAL
change on that side of zero maps to 90% of that side's saturation
(tanh(x) = 0.9 -> x = atanh(0.9) ~= 1.4722). Calibrating to the 90th
percentile rather than the median or the max was a deliberate choice:
calibrating to the median would leave most real events barely using
the available range; calibrating to the max would make the 90th
percentile (i.e. most of the real distribution) sit in the flattest,
least-discriminating part of the curve. The 90th percentile keeps the
bulk of real events on the steep, discriminating part of the curve
while still leaving room for the rare larger event to register as
larger.

COOL_MAX and WARM_MAX (the two range ceilings) are set from the
committed decisions, not derived numerically:
  - D107 requires the trend's TOTAL range to stay materially smaller
    than the base curve's own range (base spans 3-82, ~79 points).
  - D107 requires cooling favoured, warming real but modest.
  - This script derives the COOLING:WARMING RATIO from the data (the
    relative spread of real cooling vs real warming events) rather
    than assuming a fixed ratio, then scales both ends to fit a total
    range roughly a quarter of the base curve's - clearly a modifier,
    not a co-equal factor.

VALIDATION PERFORMED BEFORE ANY CONSTANT IS TRUSTED
----------------------------------------------------
1. Sanity gate against the committed handoff figures (162 / 6.77 /
   14.65 / 19.01), described above.
2. Monotonicity check: trend(a) > trend(b) whenever a is colder than
   b, checked pairwise across all 162 real samples, not assumed from
   the shape of tanh.
3. Zero-pegging check: no output value, across all 162 real samples,
   equals COOL_MAX or -WARM_MAX exactly (would indicate a saturation
   bug, e.g. tanh receiving an argument large enough to round to 1.0
   in floating point).
4. Range check: trend's total span across the 162 real samples is
   compared against the base curve's own range and reported as a
   ratio, so the "materially smaller" requirement in D107 is a
   printed number, not an assertion.
"""

import csv
import datetime as dt
import math
import os
import statistics

INPUT_FILE = os.path.join("calibration", "nearshore_water_history_30d.csv")

# ---------------------------------------------------------------
# Sanity-gate targets - the figures already recorded in project
# memory from the earlier probe series, now independently re-checked.
# ---------------------------------------------------------------
EXPECTED_SAMPLE_COUNT = 162
EXPECTED_MEDIAN_ABS = 6.77
EXPECTED_P90_ABS = 14.65
EXPECTED_MAX_ABS = 19.01
GATE_TOLERANCE = 0.05  # allow half a hundredth of a degree of rounding drift

# ---------------------------------------------------------------
# Fixed points from committed decisions (D107, D109) - not derived.
# ---------------------------------------------------------------
BASE_CURVE_RANGE = 82 - 3  # score_water()'s own base is clamped 3-82

# D107: trend's total range stays materially smaller than the base
# curve's. One quarter of the base range is the target ceiling for
# COOL_MAX + WARM_MAX combined.
TARGET_TOTAL_RANGE = round(BASE_CURVE_RANGE * 0.25, 1)

# Saturation target for the calibration percentile: tanh(x) = 0.9
SATURATION_FRACTION = 0.9
SATURATION_ARG = math.atanh(SATURATION_FRACTION)  # ~= 1.4722

# D107's cooling:warming RANGE ratio - THIS IS A POLICY CHOICE, NOT A
# DATA-DERIVED NUMBER, and an earlier version of this script got that
# distinction wrong. It used the ratio of real event MAGNITUDES
# (cooling 90th pct vs warming 90th pct) to split COOL_MAX/WARM_MAX -
# but event magnitude is a fact about this particular month's weather,
# not a statement about how much fishing value a cooling event carries
# relative to a warming one. In this dataset warming events happened
# to run slightly LARGER than cooling events (ratio 0.94), so that
# approach produced WARM_MAX > COOL_MAX - warming favoured, the exact
# opposite of D107. Caught by this script's own validation output
# before being carried into Step 3; see the handoff for the account.
#
# K_COOL / K_WARM below ARE correctly data-derived - they only
# calibrate how quickly each side saturates relative to its own real
# event sizes, which is a legitimate use of the data. Only the MAX
# ceilings needed to be policy-set instead.
#
# Default chosen here: mirror the MAGNITUDE of the asymmetry already
# shipped in the live formula (warming:cooling = 20:12 = 1.667x) but
# flip which side is favoured, per D107. This is not arbitrary - it is
# grounded in a number the project already shipped - but it is still a
# judgement call, not a measurement, and should be confirmed rather
# than treated as derived. See Open Question 0d in the handoff: it
# remains unverified whether Paul ever deliberately chose the original
# 20:12 split in the first place.
COOLING_TO_WARMING_RANGE_RATIO = 20.0 / 12.0  # ~= 1.667, cooling favoured


def c_to_f(celsius):
    return celsius * 9.0 / 5.0 + 32.0


def load_pier_series(rows):
    """pier_key -> {date_str: temp_f}, excluding the open-lake context node."""
    series = {}
    for row in rows:
        if row["pier_key"] == "open_lake_45210":
            continue
        if not row["temp_f"]:
            continue
        series.setdefault(row["pier_key"], {})[row["date_utc"]] = float(row["temp_f"])
    return series


def build_72h_changes(series):
    """List of (pier_key, date, change_f) where change_f = today - 3 days ago.

    Positive = warming. Negative = cooling. Matches the sign convention
    of change_72h_f already used throughout fetch_data.py and this
    project's handoff.
    """
    changes = []
    for pier, by_date in series.items():
        for date_str, temp in by_date.items():
            day = dt.date.fromisoformat(date_str)
            prev_str = (day - dt.timedelta(days=3)).isoformat()
            if prev_str in by_date:
                changes.append((pier, date_str, temp - by_date[prev_str]))
    return changes


def percentile(sorted_values, frac):
    """Nearest-rank percentile, matching the method used when the
    162-sample figures were first reported (int(frac * len))."""
    if not sorted_values:
        return None
    idx = int(frac * len(sorted_values))
    idx = min(idx, len(sorted_values) - 1)
    return sorted_values[idx]


def run_sanity_gate(changes):
    print("-" * 68)
    print("STEP A - SANITY GATE")
    print("-" * 68)
    print("Re-deriving the 162-sample figures already on record, to prove")
    print("this script's reconstruction of the dataset is correct BEFORE")
    print("trusting anything it derives from it.")
    print()

    abs_changes = sorted(abs(c) for _, _, c in changes)
    n = len(abs_changes)
    # NOTE: median uses statistics.median (true median - averages the two
    # middle values when n is even), NOT the nearest-rank percentile()
    # helper below. A first version of this script used nearest-rank for
    # the median too and it failed this exact gate: n=162 is even, so the
    # true median averages ranks 81 and 82 (6.662 and 6.888 -> 6.775),
    # while nearest-rank int(0.5*162)=81 grabbed only the single upper
    # value (6.888). The mismatch was caught by the gate itself before
    # any constant was derived from it - see the handoff for the account.
    median = statistics.median(abs_changes)
    p90 = percentile(abs_changes, 0.90)
    mx = abs_changes[-1] if abs_changes else None

    checks = [
        ("sample count", n, EXPECTED_SAMPLE_COUNT, 0),
        ("median |change|", median, EXPECTED_MEDIAN_ABS, GATE_TOLERANCE),
        ("90th percentile |change|", p90, EXPECTED_P90_ABS, GATE_TOLERANCE),
        ("max |change|", mx, EXPECTED_MAX_ABS, GATE_TOLERANCE),
    ]

    all_ok = True
    for label, got, expected, tol in checks:
        ok = abs(got - expected) <= tol
        all_ok = all_ok and ok
        mark = "OK" if ok else "MISMATCH"
        print("  %-28s got=%-10s expected=%-10s  [%s]" % (label, got, expected, mark))

    print()
    if not all_ok:
        print("SANITY GATE FAILED. Refusing to derive any constants.")
        print("The dataset reconstruction does not match the figures already")
        print("recorded in project memory. Fix the reader before proceeding -")
        print("do NOT hand-adjust the expected values to make this pass.")
    else:
        print("SANITY GATE PASSED. Proceeding to derive transform constants.")
    print()
    return all_ok, abs_changes


def derive_constants(changes):
    print("-" * 68)
    print("STEP B - DERIVING THE TRANSFORM")
    print("-" * 68)

    cooling = sorted(-c for _, _, c in changes if c < 0)   # positive magnitudes
    warming = sorted(c for _, _, c in changes if c > 0)    # positive magnitudes

    cool_p90 = percentile(cooling, 0.90)
    warm_p90 = percentile(warming, 0.90)

    print("Real cooling events (72h colder): %d samples, 90th pct = %.2f F"
          % (len(cooling), cool_p90))
    print("Real warming events (72h warmer): %d samples, 90th pct = %.2f F"
          % (len(warming), warm_p90))
    print()

    # The DATA-DERIVED event-magnitude ratio is reported for visibility
    # only - it is NOT used to split the range ceilings. See the note
    # above COOLING_TO_WARMING_RANGE_RATIO for why using it that way is
    # a bug: it measures event size, not fishing value.
    event_ratio = cool_p90 / warm_p90
    print("Cooling:warming 90th-percentile EVENT-SIZE ratio = %.3f" % event_ratio)
    print("(informational only - NOT used to set the range split, see note")
    print(" in the source above COOLING_TO_WARMING_RANGE_RATIO)")
    print()

    # Split TARGET_TOTAL_RANGE between COOL_MAX and WARM_MAX using the
    # POLICY ratio (D107), not the event-size ratio.
    ratio = COOLING_TO_WARMING_RANGE_RATIO
    cool_share = ratio / (1.0 + ratio)
    warm_share = 1.0 / (1.0 + ratio)
    cool_max = round(TARGET_TOTAL_RANGE * cool_share, 2)
    warm_max = round(TARGET_TOTAL_RANGE * warm_share, 2)

    print("D107 requires the trend's total range to stay materially")
    print("smaller than the base curve's (%d points) - target set at 25%%"
          % BASE_CURVE_RANGE)
    print("of that: %.1f points, split by the POLICY ratio %.3f (D107 -"
          % (TARGET_TOTAL_RANGE, ratio))
    print("cooling favoured, mirroring the live formula's 20:12 magnitude")
    print("but on the opposite side).")
    print()
    print("  COOL_MAX (max points gained from cooling) = %.2f" % cool_max)
    print("  WARM_MAX (max points lost from warming)    = %.2f" % warm_max)
    print("  Total range = %.2f (vs base curve's %d - ratio %.1f%%)"
          % (cool_max + warm_max, BASE_CURVE_RANGE,
             100 * (cool_max + warm_max) / BASE_CURVE_RANGE))
    print()

    # K_COOL / K_WARM: chosen so the 90th percentile REAL event maps to
    # 90% saturation on its side of the curve.
    k_cool = round(cool_p90 / SATURATION_ARG, 3)
    k_warm = round(warm_p90 / SATURATION_ARG, 3)

    print("Saturation constants (90th-percentile real event -> 90%% of its")
    print("side's range, via tanh(x)=0.9 at x=%.4f):" % SATURATION_ARG)
    print("  K_COOL = %.3f" % k_cool)
    print("  K_WARM = %.3f" % k_warm)
    print()

    # D107 COMPLIANCE CHECK - this is the exact bug this script shipped
    # with once already. Refuse to hand off constants that don't
    # actually favour cooling, no matter how the ratio above was
    # computed or edited in the future.
    if cool_max <= warm_max:
        raise SystemExit(
            "D107 VIOLATION: COOL_MAX (%.2f) is not greater than WARM_MAX "
            "(%.2f). The trend must favour cooling. Refusing to print "
            "constants. Check COOLING_TO_WARMING_RANGE_RATIO." % (cool_max, warm_max)
        )
    print("D107 compliance check: COOL_MAX (%.2f) > WARM_MAX (%.2f) - PASS"
          % (cool_max, warm_max))
    print()

    return {
        "cool_max": cool_max,
        "warm_max": warm_max,
        "k_cool": k_cool,
        "k_warm": k_warm,
        "cooling_p90": cool_p90,
        "warming_p90": warm_p90,
        "event_size_ratio": event_ratio,
        "policy_ratio": ratio,
    }


def trend_transform(change_72h_f, const):
    """The proposed new trend function. change_72h_f: positive=warmer,
    negative=colder, same sign convention as the live formula."""
    if change_72h_f is None:
        return 0.0
    if change_72h_f < 0:
        return const["cool_max"] * math.tanh(-change_72h_f / const["k_cool"])
    if change_72h_f > 0:
        return -const["warm_max"] * math.tanh(change_72h_f / const["k_warm"])
    return 0.0


def validate_transform(changes, const):
    print("-" * 68)
    print("STEP C - VALIDATING THE DERIVED TRANSFORM AGAINST ALL 162 SAMPLES")
    print("-" * 68)

    outputs = [(pier, date, chg, trend_transform(chg, const)) for pier, date, chg in changes]

    # 1. Zero-pegging check: no output should equal a ceiling exactly.
    pegged = [o for o in outputs if o[3] == const["cool_max"] or o[3] == -const["warm_max"]]
    print("Pegged at a ceiling exactly (should be 0): %d of %d"
          % (len(pegged), len(outputs)))

    # 2. Monotonicity: colder change -> output strictly >= warmer change's.
    sorted_by_change = sorted(outputs, key=lambda o: o[2])  # coldest first
    mono_breaks = 0
    for i in range(1, len(sorted_by_change)):
        prev_out = sorted_by_change[i - 1][3]
        this_out = sorted_by_change[i][3]
        prev_chg = sorted_by_change[i - 1][2]
        this_chg = sorted_by_change[i][2]
        if this_chg > prev_chg and this_out > prev_out + 1e-9:
            mono_breaks += 1
    print("Monotonicity violations (colder should never score lower): %d"
          % mono_breaks)

    # 3. Extremes stay distinguishable: compare the two coldest events.
    coldest_two = sorted(outputs, key=lambda o: o[2])[:2]
    if len(coldest_two) == 2 and coldest_two[0][2] != coldest_two[1][2]:
        d = abs(coldest_two[0][3] - coldest_two[1][3])
        print("Two coldest real events (%.2fF and %.2fF) produce outputs"
              % (coldest_two[0][2], coldest_two[1][2]))
        print("  %.3f apart (should be > 0 - old clamp made this 0.000)" % d)

    # 4. Range actually used
    trend_vals = [o[3] for o in outputs]
    print()
    print("Trend output range actually produced by real data: %.2f to %.2f"
          % (min(trend_vals), max(trend_vals)))
    print("Ceilings available: -%.2f to +%.2f (never reached exactly, by design)"
          % (const["warm_max"], const["cool_max"]))

    # 5. Worked example - same three piers used in the original handoff
    #    demonstration, so the improvement is directly comparable.
    print()
    print("Worked example, 2026-07-21 (same piers used in the original")
    print("handoff comparison against the live 2.4x clamp formula):")
    example = {"Sheboygan": -9.20, "Manitowoc": -6.30, "Two Rivers": -5.20}
    old_clamped = lambda c: max(-20, min(12, 2.4 * -c))
    print("  %-14s %10s %14s %14s" % ("Pier", "72h change", "OLD (2.4x)", "NEW (tanh)"))
    for name, chg in example.items():
        old_val = old_clamped(chg)
        new_val = trend_transform(chg, const)
        print("  %-14s %10.2f %14.2f %14.2f" % (name, chg, old_val, new_val))
    print("  The old formula gave all three an identical +12.00.")
    print("  The new transform keeps them ordered by how much each pier")
    print("  actually cooled - discrimination restored (D108).")
    print()

    return len(pegged) == 0 and mono_breaks == 0


def main():
    print("=" * 68)
    print("PIERBITE WATER TREND TRANSFORM DERIVATION - v1 (2026-07-28)")
    print("Reading:", INPUT_FILE)
    print("=" * 68)
    print()

    if not os.path.exists(INPUT_FILE):
        print("FAILED: %s not found. Run Step 1's probe workflow first." % INPUT_FILE)
        return 1

    with open(INPUT_FILE, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    series = load_pier_series(rows)
    print("Piers found in CSV: %s" % ", ".join(sorted(series.keys())))
    changes = build_72h_changes(series)
    print("72-hour comparisons reconstructed: %d" % len(changes))
    print()

    gate_ok, _ = run_sanity_gate(changes)
    if not gate_ok:
        return 1

    const = derive_constants(changes)
    valid = validate_transform(changes, const)

    print("-" * 68)
    print("FINAL CONSTANTS FOR fetch_data.py v13 (Step 3)")
    print("-" * 68)
    print("Derived %s from calibration/nearshore_water_history_30d.csv"
          % dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    print()
    print("TREND_COOL_MAX = %.2f" % const["cool_max"])
    print("TREND_WARM_MAX = %.2f" % const["warm_max"])
    print("TREND_K_COOL   = %.3f" % const["k_cool"])
    print("TREND_K_WARM   = %.3f" % const["k_warm"])
    print()
    print("def score_water_trend(change_72h_f):")
    print("    if change_72h_f is None:")
    print("        return 0.0")
    print("    if change_72h_f < 0:")
    print("        return TREND_COOL_MAX * math.tanh(-change_72h_f / TREND_K_COOL)")
    print("    if change_72h_f > 0:")
    print("        return -TREND_WARM_MAX * math.tanh(change_72h_f / TREND_K_WARM)")
    print("    return 0.0")
    print()

    if valid:
        print("RESULT: PASS - zero pegging, zero monotonicity violations across")
        print("        all 162 real samples. Safe to carry into Step 3.")
    else:
        print("RESULT: FAILED VALIDATION - do not carry these constants into")
        print("        Step 3. Inspect the pegging/monotonicity counts above.")
    print("=" * 68)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
