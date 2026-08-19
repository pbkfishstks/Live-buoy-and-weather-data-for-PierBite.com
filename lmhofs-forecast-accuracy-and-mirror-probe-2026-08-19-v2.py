#!/usr/bin/env python3
# PIERBITE probe | 2026-08-19 | v2 | R59 Fix B - forecast accuracy + mirror feasibility
#
# WHAT THIS IS
# ------------
# A READ-ONLY diagnostic. It writes nothing, changes nothing, commits
# nothing, and is not part of the live site. It exists to answer
# questions that cannot be answered from a development sandbox, because
# NOAA is only reachable from inside GitHub Actions.
#
# WHY IT EXISTS
# -------------
# Probe v1 (2026-08-18) proved that an older model run's FORECAST file
# can be read when the newest run is missing. But the number it came
# back with was 64.4F on a day the same node's nowcast said 73.5F.
# A 9F gap. Until that gap is EXPLAINED, no production code gets
# written on top of it.
#
# There are exactly three explanations and they lead to three completely
# different decisions:
#
#   (1) WRONG TIME SLICE. "fNNN" may not mean "cycle time + NNN hours",
#       or index [0] inside the file may not be the hour we think it is.
#       If so the reach-back is reading the wrong moment and the fix is
#       a code fix - the idea itself is fine.
#
#   (2) GENUINE FORECAST DRIFT. The forecast really was that wrong.
#       If so the reach-back is only trustworthy out to some number of
#       hours, and this probe measures that number instead of guessing.
#
#   (3) REAL UPWELLING. Sheboygan nearshore water genuinely moved 9F.
#       If so the forecast is fine and the comparison was never
#       apples-to-apples.
#
# HOW IT SETTLES THIS
# -------------------
# It stops trusting filenames and reads the VALID TIME out of the file
# itself, printed as a real date and time. Then it runs a lead-time
# sweep: one fixed target hour, the model's own nowcast for that hour as
# truth, and forecasts for that SAME hour made 6, 12, 18, 24, 30, 36, 42
# and 48 hours earlier. Same node, same hour, only the lead time varies.
#
# That produces the one thing needed to write rung 3 honestly: a table of
# error against reach-back distance.
#
# IT ALSO RE-ASKS TWO QUESTIONS PROBE v1 ANSWERED BADLY
# -----------------------------------------------------
# Probe v1 listed the cloud mirror with a 40-key alphabetical listing and
# reported "0 keys for today". That was a BAD QUERY, not evidence the
# mirror is stale - recorded honestly at the time. This version asks with
# an explicit dated prefix. It also measures real file size and tests
# whether byte-range reads work, because a mirror that only serves whole
# multi-gigabyte files is not a usable second route.
#
# Standard library only, matching fetch_data.py. No new dependencies.
# No writes. No schedule. Manual button only.

import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

UA = "PierBiteDotCom (contact: pierbite project owner)"
TIMEOUT = 60

# Frozen mesh nodes, copied from the live fetch_data.py LMHOFS_NODES.
# Two nodes, not six - this probe measures forecast behaviour, and two
# piers 40 miles apart is enough to show whether a result is general or
# a local fluke, at half the request count.
PROBE_NODES = [
    ("two_rivers", 23983),
    ("sheboygan", 20022),
]

# Exactly as production builds them (LMHOFS_BASE_DIR / LMHOFS_FIELDS_FILE).
PRIMARY_DIR = ("https://opendap.co-ops.nos.noaa.gov/thredds/dodsC/"
               "NOAA/LMHOFS/MODELS/{yyyy}/{mm}/{dd}/")
NOWCAST_FILE = "lmhofs.t{cycle}z.{yyyymmdd}.fields.n000.nc"
FORECAST_FILE = "lmhofs.t{cycle}z.{yyyymmdd}.fields.f{lead:03d}.nc"

# The lead times swept. Every one is a multiple of 6, so the run that
# produces it always lands exactly on a real 00/06/12/18 model cycle.
LEAD_HOURS = [6, 12, 18, 24, 30, 36, 42, 48]

MIRROR_BUCKET = "https://noaa-ofs-pds.s3.amazonaws.com"

NUMBER = re.compile(r"[-+]?\d*\.\d+(?:[eE][-+]?\d+)?|[-+]?\d+(?:[eE][-+]?\d+)?")
BRACKETS = re.compile(r"\[[^\]]*\]")
DIVIDER = re.compile(r"^-{3,}\s*$", re.MULTILINE)
UNITS_SINCE = re.compile(
    r'units\s+"?\s*(second|minute|hour|day)s?\s+since\s+'
    r'(\d{4})-(\d{1,2})-(\d{1,2})[ T]?(\d{1,2})?:?(\d{1,2})?:?(\d{1,2})?',
    re.IGNORECASE)
TIMESTRING = re.compile(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})")


# =====================================================================
# PLUMBING - proven helpers carried over from probe v1 unchanged, so
# this probe's results are directly comparable with that run's.
# =====================================================================

def get(url, max_bytes=200000, timeout=TIMEOUT, method="GET", headers=None):
    """One request. Returns (ok, status_or_error, text). Never raises.

    Every failure returns the error text VERBATIM so it can be pasted
    back into chat. An earlier probe swallowed its error text and cost a
    full round trip to find out what actually went wrong (C15).
    """
    hdrs = {"User-Agent": UA}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(max_bytes) if method != "HEAD" else b""
            return True, resp.getcode(), (raw.decode("utf-8", errors="replace"),
                                          dict(resp.headers))
    except Exception as err:  # noqa: BLE001 - any failure means "not available"
        return False, str(err), ("", {})


def opendap_raw(file_url, query):
    """Fetch an OPeNDAP .ascii reply. Returns (ok, status, tail_text)."""
    esc = query.replace("[", "%5B").replace("]", "%5D")
    url = "%s.ascii?%s" % (file_url, esc)
    ok, status, (body, _hdrs) = get(url, max_bytes=16000)
    if not ok:
        return False, status, ""
    parts = DIVIDER.split(body)
    tail = parts[-1] if len(parts) > 1 else "\n".join(body.splitlines()[1:])
    return True, status, tail


def opendap_value(file_url, query):
    """Read one NUMBER from an OPeNDAP .ascii endpoint."""
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


def sane_water_c(value):
    """Lake Michigan water in Celsius. Catches error codes and junk."""
    return value is not None and -3.0 <= value <= 32.0


def hr(ch="-"):
    print(ch * 70)


# =====================================================================
# VALID-TIME READER - the heart of this probe.
#
# Two independent ways to learn when a file is actually valid. They are
# both attempted and both printed, because if they DISAGREE that is
# itself the answer to the whole investigation.
#
#   METHOD A - "Times": FVCOM files usually carry a literal text
#              timestamp variable. No arithmetic, no assumptions.
#   METHOD B - "time" + units: a number plus a "<unit> since <epoch>"
#              string parsed out of the file's own .das attributes.
# =====================================================================

def read_units_epoch(file_url):
    """Parse the time variable's epoch and unit from the file's .das."""
    ok, status, (body, _h) = get(file_url + ".das", max_bytes=60000)
    if not ok:
        return None, None, "das unreachable (%s)" % status
    m = UNITS_SINCE.search(body)
    if not m:
        return None, None, "no 'units ... since ...' found in .das"
    unit = m.group(1).lower()
    y, mo, d = int(m.group(2)), int(m.group(3)), int(m.group(4))
    hh = int(m.group(5) or 0)
    mi = int(m.group(6) or 0)
    ss = int(m.group(7) or 0)
    try:
        epoch = datetime(y, mo, d, hh, mi, ss, tzinfo=timezone.utc)
    except ValueError as err:
        return None, None, "epoch in .das is not a real date (%s)" % err
    return unit, epoch, "ok"


def valid_time_from_times_var(file_url):
    """METHOD A - read the literal text timestamp, if the file has one."""
    for var in ("Times[0]", "Times[0][0:25]"):
        ok, status, tail = opendap_raw(file_url, var)
        if not ok:
            continue
        m = TIMESTRING.search(tail)
        if m:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                            int(m.group(4)), int(m.group(5)),
                            tzinfo=timezone.utc), "ok"
    return None, "no readable Times variable"


def valid_time_from_time_var(file_url):
    """METHOD B - numeric time plus the epoch declared in the .das."""
    unit, epoch, note = read_units_epoch(file_url)
    if epoch is None:
        return None, note
    raw, vnote = opendap_value(file_url, "time[0]")
    if raw is None:
        return None, "time[0] unreadable (%s)" % vnote
    factor = {"second": 1.0, "minute": 60.0,
              "hour": 3600.0, "day": 86400.0}[unit]
    try:
        return epoch + timedelta(seconds=raw * factor), "ok (%s since %s)" % (
            unit, epoch.strftime("%Y-%m-%d"))
    except OverflowError as err:
        return None, "time value out of range (%s)" % err


def valid_time(file_url):
    """Best available valid time, with both methods reported."""
    t_a, note_a = valid_time_from_times_var(file_url)
    t_b, note_b = valid_time_from_time_var(file_url)
    agree = None
    if t_a is not None and t_b is not None:
        agree = abs((t_a - t_b).total_seconds()) <= 90
    chosen = t_a if t_a is not None else t_b
    return chosen, {"times_var": t_a, "times_note": note_a,
                    "time_var": t_b, "time_note": note_b, "agree": agree}


def file_url_for(run_dt, lead):
    """Build the exact URL production would build. lead=None -> nowcast."""
    base = PRIMARY_DIR.format(yyyy=run_dt.strftime("%Y"),
                              mm=run_dt.strftime("%m"),
                              dd=run_dt.strftime("%d"))
    if lead is None:
        name = NOWCAST_FILE.format(cycle=run_dt.strftime("%H"),
                                   yyyymmdd=run_dt.strftime("%Y%m%d"))
    else:
        name = FORECAST_FILE.format(cycle=run_dt.strftime("%H"),
                                    yyyymmdd=run_dt.strftime("%Y%m%d"),
                                    lead=lead)
    return base + name


def show_times(label, url, info):
    print("    %s" % label)
    print("      url ........ %s" % url)
    a = info["times_var"]
    b = info["time_var"]
    print("      Times var .. %s   (%s)"
          % (a.strftime("%Y-%m-%d %H:%MZ") if a else "unreadable",
             info["times_note"]))
    print("      time var ... %s   (%s)"
          % (b.strftime("%Y-%m-%d %H:%MZ") if b else "unreadable",
             info["time_note"]))
    if info["agree"] is True:
        print("      the two methods AGREE")
    elif info["agree"] is False:
        print("      *** THE TWO METHODS DISAGREE - do not trust either ***")


# =====================================================================
# PART 1 - does the filename tell the truth about the valid time?
#
# Production reads temp[0][0][node] from an n000 file and treats it as
# "now". This part checks that belief against the file itself. If n000
# is NOT valid at its own cycle time, that is a finding about live
# production code, not just about the reach-back idea.
# =====================================================================

def part1_filename_truth(target):
    print("\n" + "=" * 70)
    print("PART 1 - DOES THE FILENAME TELL THE TRUTH?")
    print("=" * 70)
    print("Reading the valid time OUT OF each file instead of trusting")
    print("that 'fNNN' means 'cycle time plus NNN hours'.\n")

    verdicts = {}

    print("  A. NOWCAST n000 from the %s cycle" % target.strftime("%Y-%m-%d %HZ"))
    n_url = file_url_for(target, None)
    n_time, n_info = valid_time(n_url)
    show_times("expected valid time: %s" % target.strftime("%Y-%m-%d %H:%MZ"),
               n_url, n_info)
    if n_time is None:
        print("      RESULT: could not read a valid time at all.")
        verdicts["nowcast"] = None
    else:
        off = (n_time - target).total_seconds() / 3600.0
        print("      RESULT: file says %s -> %+.1f h from its own cycle time"
              % (n_time.strftime("%Y-%m-%d %H:%MZ"), off))
        if abs(off) <= 0.51:
            print("      => n000 IS valid at its cycle time. Production's")
            print("         assumption is CORRECT.")
        else:
            print("      => n000 IS NOT valid at its cycle time. This affects")
            print("         LIVE PRODUCTION, not just the reach-back.")
        verdicts["nowcast"] = off
    print()

    print("  B. FORECAST f024 from the cycle 24 hours earlier")
    run = target - timedelta(hours=24)
    f_url = file_url_for(run, 24)
    f_time, f_info = valid_time(f_url)
    show_times("expected valid time: %s" % target.strftime("%Y-%m-%d %H:%MZ"),
               f_url, f_info)
    if f_time is None:
        print("      RESULT: could not read a valid time at all.")
        verdicts["forecast"] = None
    else:
        off = (f_time - target).total_seconds() / 3600.0
        print("      RESULT: file says %s -> %+.1f h from the hour we wanted"
              % (f_time.strftime("%Y-%m-%d %H:%MZ"), off))
        if abs(off) <= 0.51:
            print("      => 'fNNN' DOES mean 'cycle + NNN hours'.")
            print("         EXPLANATION 1 (wrong time slice) IS RULED OUT.")
        else:
            print("      *** 'fNNN' DOES NOT mean 'cycle + NNN hours'. ***")
            print("         EXPLANATION 1 IS CONFIRMED - probe v1 compared")
            print("         two different moments and the 9F gap is an")
            print("         artefact, not a model error.")
        verdicts["forecast"] = off

    return verdicts


# =====================================================================
# PART 2 - THE BLOCKER. Error against reach-back distance.
#
# One fixed hour. The model's own nowcast for that hour is truth.
# Forecasts for that SAME hour, made 6 to 48 hours earlier, are the
# test. Only the lead time changes, so anything left over IS drift.
# =====================================================================

def part2_lead_sweep(target):
    print("\n" + "=" * 70)
    print("PART 2 - THE BLOCKER: how wrong is a forecast, by how far back?")
    print("=" * 70)
    print("Target hour (fixed for every row): %s"
          % target.strftime("%Y-%m-%d %H:%MZ"))
    print("Truth = that hour's own nowcast, which is what production reads.\n")

    truth = {}
    t_url = file_url_for(target, None)
    print("  Establishing truth from %s" % t_url)
    for name, node in PROBE_NODES:
        val, note = opendap_value(t_url, "temp[0][0][%d]" % node)
        if val is not None and sane_water_c(val):
            truth[name] = c_to_f(val)
            print("    %-12s node %-6d truth = %.2fF" % (name, node, c_to_f(val)))
        else:
            truth[name] = None
            print("    %-12s node %-6d TRUTH UNAVAILABLE (%s)"
                  % (name, node, note))

    if not any(v is not None for v in truth.values()):
        print("\n  Cannot proceed - no truth reading. Everything below would")
        print("  be meaningless. Re-run when the target cycle is available.")
        return []

    print()
    hr()
    print("  %-6s %-18s %-10s %-10s %-10s %-10s"
          % ("lead", "valid time in file", "TwoRiv", "err", "Sheboygan", "err"))
    hr()

    rows = []
    for lead in LEAD_HOURS:
        run = target - timedelta(hours=lead)
        url = file_url_for(run, lead)
        vt, vinfo = valid_time(url)

        if vt is None:
            print("  f%03d   %-18s  file unreadable" % (lead, "-"))
            print("         %s" % url)
            print("         Times: %s | time: %s"
                  % (vinfo["times_note"], vinfo["time_note"]))
            rows.append({"lead": lead, "valid": None})
            continue

        offset = (vt - target).total_seconds() / 3600.0
        row = {"lead": lead, "valid": vt, "offset_h": offset, "url": url}
        cells = []
        for name, node in PROBE_NODES:
            val, note = opendap_value(url, "temp[0][0][%d]" % node)
            if val is not None and sane_water_c(val):
                f = c_to_f(val)
                row[name] = f
                if truth.get(name) is not None:
                    err = f - truth[name]
                    row[name + "_err"] = err
                    cells.append("%.2fF" % f)
                    cells.append("%+.2f" % err)
                else:
                    cells.append("%.2fF" % f)
                    cells.append("n/a")
            else:
                row[name] = None
                cells.append("--")
                cells.append("(%s)" % note[:8])

        flag = "" if abs(offset) <= 0.51 else "  <-- WRONG HOUR"
        print("  f%03d   %-18s %-10s %-10s %-10s %-10s%s"
              % (lead, vt.strftime("%m-%d %H:%MZ"),
                 cells[0], cells[1], cells[2], cells[3], flag))
        rows.append(row)

    hr()
    print()

    usable = [r for r in rows
              if r.get("valid") is not None and abs(r.get("offset_h", 99)) <= 0.51]
    misaligned = [r for r in rows
                  if r.get("valid") is not None and abs(r.get("offset_h", 0)) > 0.51]

    if misaligned:
        print("  %d file(s) were valid at the WRONG HOUR. That alone explains"
              % len(misaligned))
        print("  a large apparent error and must be fixed before any")
        print("  conclusion about drift is drawn.")
        print()

    errs = []
    for r in usable:
        for name, _node in PROBE_NODES:
            if r.get(name + "_err") is not None:
                errs.append((r["lead"], name, r[name + "_err"]))

    if not errs:
        print("  VERDICT: no aligned forecast readings were obtained.")
        print("           Rung 3 stays unproven. Do NOT build it yet.")
        return rows

    worst = max(abs(e[2]) for e in errs)
    print("  VERDICT - measured error at the SAME hour, same node:")
    for lead in LEAD_HOURS:
        this = [e for e in errs if e[0] == lead]
        if this:
            print("    reach back %2dh -> worst error %+.2fF"
                  % (lead, max(this, key=lambda e: abs(e[2]))[2]))
    print()
    print("  Largest error anywhere in the sweep: %.2fF" % worst)
    if worst < 1.5:
        print("  => Forecast reach-back is ACCURATE. The 9F gap probe v1 saw")
        print("     was NOT drift. Rung 3 is safe to build.")
    elif worst < 4.0:
        print("  => Forecast reach-back drifts moderately. Rung 3 is buildable")
        print("     but should be capped at the shortest lead that stays")
        print("     inside tolerance, and labelled FORECAST, never MODELED.")
    else:
        print("  => Forecast reach-back drifts BADLY at these lead times.")
        print("     Rung 3 must be capped hard or dropped. Decide from the")
        print("     per-lead table above, not from this one line.")
    return rows


# =====================================================================
# PART 3 - is the water itself moving fast enough to explain 9F?
#
# Cheap, and it settles explanation (3) directly. If the nowcast series
# swings several degrees a day on its own, then a forecast that misses
# by several degrees is not a broken forecast - it is a lake doing what
# this whole website exists to report.
# =====================================================================

def part3_real_movement(target):
    print("\n" + "=" * 70)
    print("PART 3 - HOW FAST IS THE WATER ACTUALLY MOVING?")
    print("=" * 70)
    print("Nowcast-only series. No forecasts. This is measured reality.\n")

    series = {name: [] for name, _ in PROBE_NODES}
    for back in (0, 12, 24, 36, 48):
        run = target - timedelta(hours=back)
        url = file_url_for(run, None)
        line = "  %s  " % run.strftime("%m-%d %HZ")
        for name, node in PROBE_NODES:
            val, note = opendap_value(url, "temp[0][0][%d]" % node)
            if val is not None and sane_water_c(val):
                f = c_to_f(val)
                series[name].append(f)
                line += "%-12s %6.2fF   " % (name, f)
            else:
                line += "%-12s   --      " % name
        print(line)

    print()
    for name, _node in PROBE_NODES:
        vals = series[name]
        if len(vals) >= 2:
            swing = max(vals) - min(vals)
            print("  %-12s swing across the last 48h: %.2fF" % (name, swing))
            if swing >= 5.0:
                print("               that is a real, large nearshore swing -")
                print("               upwelling is a live explanation here.")
    return series


# =====================================================================
# PART 4 - the cloud mirror, asked properly this time.
#
# Probe v1's "0 keys for today" came from an alphabetical 40-key listing
# that started in July. That was a bad query, not a stale mirror. This
# asks with an explicit dated prefix, then measures whether the files are
# a realistic thing to fetch hourly.
# =====================================================================

def part4_mirror(target):
    print("\n" + "=" * 70)
    print("PART 4 - CLOUD MIRROR, RE-ASKED WITH A DATED PREFIX")
    print("=" * 70)
    print("Probe v1's query was wrong, not its subject. Asking again.\n")

    sample_key = None
    for back in (0, 1):
        day = (target - timedelta(days=back)).strftime("%Y%m%d")
        prefix = "lmhofs.%s/" % day
        url = "%s/?list-type=2&max-keys=1000&prefix=%s" % (MIRROR_BUCKET, prefix)
        print("  Prefix: %s" % prefix)
        print("    %s" % url)
        ok, status, (body, _h) = get(url, max_bytes=300000)
        if not ok:
            print("    UNREACHABLE - %s\n" % status)
            continue
        keys = re.findall(r"<Key>([^<]+)</Key>", body)
        fields = [k for k in keys if ".fields." in k]
        print("    keys under this prefix ....... %d" % len(keys))
        print("    of those, 'fields' files ..... %d" % len(fields))
        if fields:
            print("    sample:")
            for k in fields[:4]:
                print("      %s" % k)
            if sample_key is None:
                sample_key = fields[0]
        elif keys:
            print("    sample (non-fields):")
            for k in keys[:4]:
                print("      %s" % k)
        print()

    if sample_key is None:
        print("  VERDICT: no dated fields files found on the mirror.")
        print("           The mirror rung (rung 4) gets DROPPED, not forced.")
        return False

    print("  Measuring one real file: %s" % sample_key)
    file_url = "%s/%s" % (MIRROR_BUCKET, sample_key)
    ok, status, (_b, hdrs) = get(file_url, method="HEAD")
    size_mb = None
    if ok:
        try:
            size_mb = int(hdrs.get("Content-Length", 0)) / (1024.0 * 1024.0)
        except (TypeError, ValueError):
            size_mb = None
        print("    HTTP status ............ %s" % status)
        print("    Content-Length ......... %s"
              % ("%.1f MB" % size_mb if size_mb else "not reported"))
        print("    Accept-Ranges .......... %s"
              % hdrs.get("Accept-Ranges", "not reported"))
    else:
        print("    HEAD FAILED - %s" % status)

    ok2, status2, (body2, hdrs2) = get(file_url, max_bytes=2048,
                                       headers={"Range": "bytes=0-1023"})
    ranged = ok2 and str(status2) == "206"
    print("    byte-range read ........ %s"
          % ("WORKS (HTTP 206)" if ranged else "did not return 206 (%s)" % status2))
    if ok2 and body2[:3] in ("CDF", "\x89HD"):
        print("    first bytes look like a real NetCDF header")

    print()
    if ranged and (size_mb is None or size_mb < 400):
        print("  VERDICT: mirror is USABLE as a second route. Range reads work,")
        print("           so a single node can be pulled without downloading")
        print("           the whole file.")
        return True
    print("  VERDICT: mirror EXISTS but is not cheaply readable "
          "(size %s, ranges %s)."
          % ("%.1f MB" % size_mb if size_mb else "unknown",
             "yes" if ranged else "no"))
    print("           Per D193 the mirror rung gets DROPPED rather than forced.")
    return False


# =====================================================================

def choose_target():
    """Newest 00/06/12/18 cycle at least 3 hours old.

    3 hours of margin because NOAA publishes a cycle some time after its
    nominal hour. Every lead in the sweep is a multiple of 6 hours before
    this, so every one lands on a real cycle, and 48 hours back is well
    inside NOAA's 30-day retention.
    """
    now = datetime.now(timezone.utc)
    t = (now - timedelta(hours=3)).replace(minute=0, second=0, microsecond=0)
    while t.hour % 6 != 0:
        t -= timedelta(hours=1)
    return t


def main():
    print("=" * 70)
    print("PIERBITE - R59 FIX B RESEARCH PROBE  v2")
    print("Forecast accuracy + mirror feasibility")
    print("Run at %s" % datetime.now(timezone.utc).isoformat())
    print("READ-ONLY. Writes nothing. Commits nothing. Changes nothing.")
    print("=" * 70)

    target = choose_target()
    print("\nTarget hour for every comparison: %s"
          % target.strftime("%Y-%m-%d %H:%MZ"))
    print("Nodes probed: %s"
          % ", ".join("%s(%d)" % (n, i) for n, i in PROBE_NODES))

    v1 = part1_filename_truth(target)
    rows = part2_lead_sweep(target)
    part3_real_movement(target)
    mirror = part4_mirror(target)

    print("\n" + "=" * 70)
    print("SUMMARY - what this run established")
    print("=" * 70)

    fc = v1.get("forecast")
    if fc is None:
        print("  Q1 does fNNN mean cycle+NNN? ..... COULD NOT TELL")
    elif abs(fc) <= 0.51:
        print("  Q1 does fNNN mean cycle+NNN? ..... YES (time slice was fine)")
    else:
        print("  Q1 does fNNN mean cycle+NNN? ..... NO, off by %+.1f h" % fc)

    aligned = [r for r in rows
               if r.get("valid") is not None
               and abs(r.get("offset_h", 99)) <= 0.51]
    errs = [abs(r[n + "_err"]) for r in aligned for n, _ in PROBE_NODES
            if r.get(n + "_err") is not None]
    if errs:
        print("  Q2 worst same-hour forecast error  %.2fF over %d readings"
              % (max(errs), len(errs)))
    else:
        print("  Q2 worst same-hour forecast error  NOT MEASURED")

    print("  Q3 mirror usable as second route . %s"
          % ("YES" if mirror else "NO / dropped"))
    print()
    print("  Copy this ENTIRE output back into the chat.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
