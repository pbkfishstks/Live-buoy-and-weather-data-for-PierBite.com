#!/usr/bin/env python3
# PIERBITE probe | 2026-08-19 | v3 | R59 Fix B - ALIGNED forecast accuracy
#
# READ-ONLY. Writes nothing, commits nothing, changes nothing.
#
# WHY v3 EXISTS
# -------------
# Probe v2 proved two things and broke itself on the first one.
#
#   PROVED: the "n000" nowcast file is valid SIX HOURS BEFORE the cycle
#   time in its own filename. Two independent methods inside the file
#   agreed. Live production reads n000 and treats it as the cycle time,
#   so every water temperature on the site is six hours older than the
#   code's age arithmetic believes.
#
#   PROVED: "fNNN" DOES mean "cycle time plus NNN hours". Forecast files
#   are labelled honestly.
#
#   BROKE: probe v2's own lead sweep used n000 as its TRUTH reading.
#   So it compared a truth valid at 00Z against forecasts valid at 06Z
#   and called the difference "forecast error". Those numbers are a
#   CEILING, not a measurement, and this probe replaces them.
#
# THE TELL THAT SOMETHING WAS WRONG
# ---------------------------------
# v2's error did not grow with lead time: -1.57F reaching back 6 hours,
# -1.03F reaching back 48 hours. Real forecast drift ALWAYS grows with
# distance. A flat error is the fingerprint of a fixed offset - exactly
# what a six-hour misalignment produces. This probe removes the offset
# and measures what is actually left.
#
# WHAT IT DOES
# ------------
# PART A - inventory the nowcast files (n000 through n008) and read the
#          real valid time of each. This answers a LIVE PRODUCTION
#          question: is there a fresher nowcast file that would give the
#          site six hours back for free?
#
# PART B - the lead sweep again, with truth chosen by measured valid
#          time rather than by filename, across ALL SIX piers.
#
# Standard library only. No new dependencies. No schedule.

import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

UA = "PierBiteDotCom (contact: pierbite project owner)"
TIMEOUT = 60

# All six frozen mesh nodes, copied from live fetch_data.py LMHOFS_NODES.
# Six this time, not two - this is the measurement the build decision
# rests on, so a result that holds at one pier is not good enough.
PROBE_NODES = [
    ("sheboygan", 20022),
    ("manitowoc", 21438),
    ("two_rivers", 23983),
    ("kewaunee", 28542),
    ("algoma", 28904),
    ("sturgeon_bay", 31190),
]

PRIMARY_DIR = ("https://opendap.co-ops.nos.noaa.gov/thredds/dodsC/"
               "NOAA/LMHOFS/MODELS/{yyyy}/{mm}/{dd}/")
NOWCAST_FILE = "lmhofs.t{cycle}z.{yyyymmdd}.fields.n{lead:03d}.nc"
FORECAST_FILE = "lmhofs.t{cycle}z.{yyyymmdd}.fields.f{lead:03d}.nc"

NOWCAST_INDICES = [0, 1, 2, 3, 4, 5, 6, 7, 8]
LEAD_HOURS = [6, 12, 18, 24, 30, 36, 42, 48]

NUMBER = re.compile(r"[-+]?\d*\.\d+(?:[eE][-+]?\d+)?|[-+]?\d+(?:[eE][-+]?\d+)?")
BRACKETS = re.compile(r"\[[^\]]*\]")
DIVIDER = re.compile(r"^-{3,}\s*$", re.MULTILINE)
UNITS_SINCE = re.compile(
    r'units\s+"?\s*(second|minute|hour|day)s?\s+since\s+'
    r'(\d{4})-(\d{1,2})-(\d{1,2})[ T]?(\d{1,2})?:?(\d{1,2})?:?(\d{1,2})?',
    re.IGNORECASE)
TIMESTRING = re.compile(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})")


# ---------------------------------------------------------------
# PLUMBING - carried over unchanged from probes v1 and v2 so results
# stay directly comparable across all three runs.
# ---------------------------------------------------------------

def get(url, max_bytes=200000, timeout=TIMEOUT):
    """One request. Returns (ok, status_or_error, text). Never raises.

    Failures return the error text VERBATIM so it can be pasted back
    into chat. An earlier probe swallowed its error text and cost a full
    round trip to find out what had gone wrong (C15).
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, resp.getcode(), resp.read(max_bytes).decode(
                "utf-8", errors="replace")
    except Exception as err:  # noqa: BLE001 - any failure means "not available"
        return False, str(err), ""


def opendap_raw(file_url, query):
    esc = query.replace("[", "%5B").replace("]", "%5D")
    ok, status, body = get("%s.ascii?%s" % (file_url, esc), max_bytes=16000)
    if not ok:
        return False, status, ""
    parts = DIVIDER.split(body)
    return True, status, (parts[-1] if len(parts) > 1
                          else "\n".join(body.splitlines()[1:]))


def opendap_value(file_url, query):
    ok, status, tail = opendap_raw(file_url, query)
    if not ok:
        return None, str(status)
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


def sane_water_c(v):
    return v is not None and -3.0 <= v <= 32.0


def read_units_epoch(file_url):
    ok, status, body = get(file_url + ".das", max_bytes=60000)
    if not ok:
        return None, None, "das unreachable (%s)" % status
    m = UNITS_SINCE.search(body)
    if not m:
        return None, None, "no 'units ... since ...' in .das"
    try:
        epoch = datetime(int(m.group(2)), int(m.group(3)), int(m.group(4)),
                         int(m.group(5) or 0), int(m.group(6) or 0),
                         int(m.group(7) or 0), tzinfo=timezone.utc)
    except ValueError as err:
        return None, None, "epoch is not a real date (%s)" % err
    return m.group(1).lower(), epoch, "ok"


def valid_time(file_url):
    """Measured valid time. Two methods; disagreement is itself a result."""
    t_a = None
    for var in ("Times[0]", "Times[0][0:25]"):
        ok, _s, tail = opendap_raw(file_url, var)
        if ok:
            m = TIMESTRING.search(tail)
            if m:
                t_a = datetime(int(m.group(1)), int(m.group(2)),
                               int(m.group(3)), int(m.group(4)),
                               int(m.group(5)), tzinfo=timezone.utc)
                break

    t_b, note_b = None, ""
    unit, epoch, note = read_units_epoch(file_url)
    if epoch is None:
        note_b = note
    else:
        raw, vnote = opendap_value(file_url, "time[0]")
        if raw is None:
            note_b = "time[0] unreadable (%s)" % vnote
        else:
            factor = {"second": 1.0, "minute": 60.0,
                      "hour": 3600.0, "day": 86400.0}[unit]
            try:
                t_b = epoch + timedelta(seconds=raw * factor)
            except OverflowError as err:
                note_b = "time out of range (%s)" % err

    agree = None
    if t_a and t_b:
        agree = abs((t_a - t_b).total_seconds()) <= 90
    return (t_a or t_b), {"a": t_a, "b": t_b, "agree": agree, "note": note_b}


def nowcast_url(run_dt, idx):
    return PRIMARY_DIR.format(yyyy=run_dt.strftime("%Y"),
                              mm=run_dt.strftime("%m"),
                              dd=run_dt.strftime("%d")) + NOWCAST_FILE.format(
        cycle=run_dt.strftime("%H"), yyyymmdd=run_dt.strftime("%Y%m%d"), lead=idx)


def forecast_url(run_dt, lead):
    return PRIMARY_DIR.format(yyyy=run_dt.strftime("%Y"),
                              mm=run_dt.strftime("%m"),
                              dd=run_dt.strftime("%d")) + FORECAST_FILE.format(
        cycle=run_dt.strftime("%H"), yyyymmdd=run_dt.strftime("%Y%m%d"), lead=lead)


# ---------------------------------------------------------------
# PART A - what nowcast files exist, and when is each one valid?
#
# Production reads n000 today. If a higher-numbered nowcast file exists
# and is valid at the cycle time, the live site can be six hours fresher
# for the cost of one constant.
# ---------------------------------------------------------------

def part_a_nowcast_inventory(cycle):
    print("\n" + "=" * 70)
    print("PART A - NOWCAST FILE INVENTORY")
    print("=" * 70)
    print("Cycle under test: %s" % cycle.strftime("%Y-%m-%d %HZ"))
    print("Production currently reads n000 and treats it as the cycle time.")
    print("Checking every nowcast file and its MEASURED valid time.\n")

    found = {}
    for idx in NOWCAST_INDICES:
        url = nowcast_url(cycle, idx)
        vt, info = valid_time(url)
        if vt is None:
            print("  n%03d   absent or unreadable" % idx)
            continue
        offset = (vt - cycle).total_seconds() / 3600.0
        agree = ("" if info["agree"] is not False
                 else "   *** methods disagree ***")
        print("  n%03d   valid %s   %+5.1f h from cycle time%s"
              % (idx, vt.strftime("%Y-%m-%d %H:%MZ"), offset, agree))
        found[idx] = vt

    print()
    if not found:
        print("  VERDICT: no nowcast files readable. Nothing else can run.")
        return found

    at_cycle = [i for i, t in found.items() if abs((t - cycle).total_seconds()) <= 900]
    freshest = max(found.items(), key=lambda kv: kv[1])
    print("  Production reads .......... n000, valid %s"
          % found.get(0, "unreadable"))
    print("  Freshest file available ... n%03d, valid %s"
          % (freshest[0], freshest[1].strftime("%Y-%m-%d %H:%MZ")))
    gain = (freshest[1] - found[0]).total_seconds() / 3600.0 if 0 in found else 0
    if gain >= 1.0:
        print()
        print("  *** LIVE SITE FINDING: switching production from n000 to")
        print("      n%03d would make every water temperature %.0f HOURS"
              % (freshest[0], gain))
        print("      FRESHER, with no other change. ***")
    if at_cycle:
        print("  File(s) valid exactly at the cycle time: %s"
              % ", ".join("n%03d" % i for i in sorted(at_cycle)))
    else:
        print("  NOTE: no nowcast file is valid exactly at the cycle time.")
    return found


# ---------------------------------------------------------------
# PART B - the lead sweep, with truth chosen by MEASURED valid time.
#
# Truth is whichever nowcast file actually reads back as valid at the
# target hour - not whichever filename looks right. That single change
# is the whole point of this probe.
# ---------------------------------------------------------------

def find_truth_file(target):
    """Locate a nowcast file MEASURED to be valid at exactly `target`."""
    print("  Locating a truth file genuinely valid at %s"
          % target.strftime("%Y-%m-%d %H:%MZ"))
    for cyc_shift in (0, 6, 12):
        cycle = target + timedelta(hours=cyc_shift)
        for idx in NOWCAST_INDICES:
            url = nowcast_url(cycle, idx)
            vt, _info = valid_time(url)
            if vt is not None and abs((vt - target).total_seconds()) <= 900:
                print("    MATCH: %s cycle, n%03d -> valid %s"
                      % (cycle.strftime("%m-%d %HZ"), idx,
                         vt.strftime("%Y-%m-%d %H:%MZ")))
                return url, cycle, idx
    print("    NO MATCH - could not find any nowcast valid at the target hour.")
    return None, None, None


def part_b_aligned_sweep(target):
    print("\n" + "=" * 70)
    print("PART B - ALIGNED LEAD SWEEP (this replaces probe v2's Part 2)")
    print("=" * 70)
    print("Target hour, fixed for every row: %s\n"
          % target.strftime("%Y-%m-%d %H:%MZ"))

    t_url, t_cycle, t_idx = find_truth_file(target)
    if t_url is None:
        print("\n  Cannot proceed. Everything below would be meaningless.")
        return []

    print("\n  Truth readings (all six piers):")
    truth = {}
    for name, node in PROBE_NODES:
        val, note = opendap_value(t_url, "temp[0][0][%d]" % node)
        if val is not None and sane_water_c(val):
            truth[name] = c_to_f(val)
            print("    %-13s node %-6d %.2fF" % (name, node, c_to_f(val)))
        else:
            truth[name] = None
            print("    %-13s node %-6d UNAVAILABLE (%s)" % (name, node, note))

    if not any(v is not None for v in truth.values()):
        print("\n  No truth readings at all. Stopping.")
        return []

    print()
    print("  Each row: a forecast for that SAME hour, made N hours earlier.")
    print("  Only the lead time changes. Anything left over IS drift.\n")

    header = "  %-6s %-16s" % ("lead", "valid time")
    for name, _n in PROBE_NODES:
        header += " %8s" % name[:8]
    print(header)
    print("  " + "-" * (len(header) - 2))

    rows = []
    for lead in LEAD_HOURS:
        run = target - timedelta(hours=lead)
        url = forecast_url(run, lead)
        vt, vinfo = valid_time(url)
        if vt is None:
            print("  f%03d   UNREADABLE      %s" % (lead, vinfo["note"][:40]))
            print("         %s" % url)
            continue
        offset = (vt - target).total_seconds() / 3600.0
        row = {"lead": lead, "valid": vt, "offset_h": offset}
        line = "  f%03d   %-16s" % (lead, vt.strftime("%m-%d %H:%MZ"))
        for name, node in PROBE_NODES:
            val, _note = opendap_value(url, "temp[0][0][%d]" % node)
            if val is not None and sane_water_c(val) and truth.get(name) is not None:
                err = c_to_f(val) - truth[name]
                row[name] = err
                line += " %+8.2f" % err
            else:
                line += " %8s" % "--"
        if abs(offset) > 0.51:
            line += "   <-- WRONG HOUR"
        print(line)
        rows.append(row)

    print("  " + "-" * (len(header) - 2))
    print("  (numbers are ERRORS in F: forecast minus truth, same hour)\n")

    aligned = [r for r in rows if abs(r.get("offset_h", 99)) <= 0.51]
    all_errs = [abs(r[n]) for r in aligned for n, _x in PROBE_NODES if n in r]
    if not all_errs:
        print("  VERDICT: nothing aligned. Rung 3 stays unproven.")
        return rows

    print("  VERDICT - true forecast error, correctly aligned:")
    growing = []
    for lead in LEAD_HOURS:
        this = [abs(r[n]) for r in aligned if r["lead"] == lead
                for n, _x in PROBE_NODES if n in r]
        if this:
            print("    reach back %2dh -> worst %.2fF   average %.2fF"
                  % (lead, max(this), sum(this) / len(this)))
            growing.append((lead, max(this)))

    worst = max(all_errs)
    print()
    print("  Worst error anywhere: %.2fF across %d readings"
          % (worst, len(all_errs)))

    if len(growing) >= 4:
        early = sum(e for _l, e in growing[:2]) / 2.0
        late = sum(e for _l, e in growing[-2:]) / 2.0
        print("  Short reach-backs average %.2fF; long ones average %.2fF."
              % (early, late))
        if late > early * 1.6:
            print("  => Error GROWS with distance. That is genuine forecast")
            print("     drift. Cap rung 3 at the last lead inside tolerance.")
        else:
            print("  => Error does NOT grow with distance. Reach-back is")
            print("     equally trustworthy at 48h as at 6h.")

    if worst < 1.0:
        print("  => Rung 3 is SAFE to build across the full 48-hour window.")
    elif worst < 2.5:
        print("  => Rung 3 is buildable. Label it FORECAST, never MODELED,")
        print("     and publish the lead time so a visitor can see it.")
    else:
        print("  => Rung 3 needs a hard cap. Choose it from the table above.")
    return rows


def choose_target():
    """Newest 00/06/12/18 cycle at least 9 hours old.

    9 hours, not 3, so the cycle SIX HOURS AFTER the target is also
    already published - that later cycle is where a correctly-aligned
    truth file lives, given what probe v2 measured about n000.
    """
    t = (datetime.now(timezone.utc) - timedelta(hours=9)).replace(
        minute=0, second=0, microsecond=0)
    while t.hour % 6 != 0:
        t -= timedelta(hours=1)
    return t


def main():
    print("=" * 70)
    print("PIERBITE - R59 FIX B RESEARCH PROBE  v3")
    print("Aligned forecast accuracy + nowcast freshness")
    print("Run at %s" % datetime.now(timezone.utc).isoformat())
    print("READ-ONLY. Writes nothing. Commits nothing. Changes nothing.")
    print("=" * 70)

    target = choose_target()
    print("\nTarget hour: %s" % target.strftime("%Y-%m-%d %H:%MZ"))
    print("Piers probed: all six")

    part_a_nowcast_inventory(target)
    part_b_aligned_sweep(target)

    print("\n" + "=" * 70)
    print("Copy this ENTIRE output back into the chat.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
