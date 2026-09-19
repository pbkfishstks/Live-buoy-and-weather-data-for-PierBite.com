<!-- PIERBITE PROJECT MEMORY | 2026-09-19 (written ~15:00 Central / 20:00 UTC) | v62 | Session diagnosed a wind-history problem on the Two Rivers and Port Washington pages. Paul noticed the individual Two Rivers page showed only ~29-30 hours of wind history while the Compare page appeared to show ~72. Investigated with live data.json + the live fetch_data.py (found already at v29, not v28 as older memory said). ROOT CAUSES (all verified against live data/code): (1) The two GLOS Seagull stations that feed Two Rivers (Neshotah Park, key trw) and Port Washington (key pww) stopped reporting ~43 hours before data.json was generated, so only ~29 hours of readings fall inside the backend's 73-hour lookback. (2) MOST IMPORTANT: the backend labels every hourly wind row "hours_ago" counting back from the station's LAST reading, not from the current time - so for a dead station the "0 hours ago" bar is really ~43h old and the "29 hours ago" bar is really ~72h old. (3) The pier-page chart draws those ~30 bars stretched across a full "LAST 72 HOURS OF WIND" width with axis labels (3 DAYS AGO / 2 DAYS AGO / YESTERDAY / 44H AGO) that do not match the data; the wind score and "past 30 hours" wording also count from the last reading. The Compare page uses the SAME 30 hours but draws a short strip at its real length (Paul: more accurate) - my early guess that it used a different data source was WRONG. A full backup of the GitHub repo was made before any change. NO code has been changed or deployed this session. Supersedes v61 - delete Memory_PIERBITE_PROJECT_MEMORY_2026-09-18_v61.md from Project Files and upload this one. -->

# PIERBITE PROJECT MEMORY - 2026-09-19 v62

**THIS IS THE CURRENT REVISION. It supersedes v61.**
Nothing deleted - additive by design. Everything below the divider line
is v61, preserved byte-for-byte.

## Project Overview

Unchanged from v61 (below). PierBite.com: seven Wisconsin Lake Michigan pier
pages on one long Carrd page; Python backend `fetch_data.py` runs hourly in
GitHub Actions and writes `data.json`; Carrd Code Embed boxes fetch it.
Paul is non-technical; Claude writes all code and deployment steps.

## Current Status

- **NEW PROBLEM (this session), diagnosed, NOT fixed:** wind-history charts
  and wind scoring for Two Rivers and Port Washington are built on wind data
  that is 2-3 days old, and the "hours ago" labels claim otherwise. Paul:
  he "can't do anything with the app until this is fixed" and has said
  "we need to do, we will do" - i.e. he approved proceeding.
- **Live backend is `fetch_data.py` v29** (2026-09-16, LMHOFS endpoint
  failover), 190,046 bytes, MD5 `4fb57fcff5f6ea2f7eb440c6bd9f9243`, verified
  by clone of the GitHub repo (commit `ac622d8230cf995b1aa8cd6bb05bd66a59261e84`,
  2026-09-19 19:05 UTC). Older memory that says "v28 live" is OUT OF DATE.
  Next backend versions are therefore **v30** and **v31**.
- Backup of the entire repo taken before any change (see Completed Work).
- Everything carried from v61 is unchanged and still unconfirmed: the 9 files
  delivered in v61 (7 x ALL PIERS button fix, `pbhh1` v10 "seven piers",
  `pbpick` v4, `pbcm2a` v3) are still NOT confirmed live by Paul; Sturgeon Bay
  template-parity rebuild not started; Manitowoc/Port Washington/Kewaunee/
  Algoma template-parity files pending live confirmation.

## Completed Work (this session)

1. Diagnosed the 29-vs-72-hour difference with live data (details in
   Technical Details). Corrected my own mistaken early guess about the
   Compare page after Paul's screenshots.
2. Built and verified a full backup: `pierbite-backup-before-wind-fix-2026-09-19.zip`
   (12 MB, 66 files: whole repo incl. `fetch_data.py`, `.github/workflows/fetch.yml`,
   `data.json`, `photos.json`, images, probe scripts) plus a manifest and
   `wind-history-problem-findings-2026-09-19.md`. Zip integrity tested; saved
   `fetch_data.py` matched the live one by MD5. Paul should keep the zip
   somewhere permanent (suggest `C:\PBK\PbkMain\websites\Claude_Pierbite\Current\Backups\`).
   Carrd site is NOT in that zip (Paul's Carrd backup duplicate is the safety net).

## Work In Progress

- Nothing half-built. v30 has been planned but NO code written. A handoff
  was done before building on purpose (see Reasoning Ledger).

## Remaining Tasks

1. **Backend v30 (Opus, `fetch_data.py`):** anchor `hours_ago` to the run time
   (`now`), not the station's last reading, in BOTH `fetch_station_history()`
   (NWS airports) and `fetch_glos_wind_history()` (GLOS Seagull). Loop
   `for h in range(72, -1, -1)` with `target = now - timedelta(hours=h)`;
   keep the existing 30-minute matching tolerance and `observed_at_utc`.
   Nothing else changes (D146). Header comment must say v30.
2. **Backend v31 (Opus):** dead-station cutoff. Use the EXISTING `wind_history`
   fallback chain (config ~line 2354; Algoma already uses
   `[("agw", None), ("kww", "Kewaunee")]`). Today chain selection (~line 3336)
   picks the first entry with `available` history even if it is days old.
   Add: a non-borrowed history whose last reading is older than a cutoff is
   skipped when a later chain entry exists. Add fallback entries for
   Two Rivers (candidate: `("mtw", "Manitowoc Airport")`, which it used before
   v21) and Port Washington (candidate: `KSBM` Sheboygan Airport - Paul must
   confirm the neighbor). Fix "over the past N hours" wording so it reflects
   real elapsed time. Cutoff hours: to be chosen and justified when built
   (existing `STALE_AFTER_HOURS` is 3).
3. **Front end (Sonnet):** Two Rivers/Port Washington Pier B chart and the
   Compare Piers strips must draw a TRUE 72-hour window ending at the current
   time, each bar at its real age, with an explicit labeled empty gap where
   no readings exist (e.g. "No readings since Sep 17, 6:40 PM"), true axis
   labels, and sentence counts that say how many real hours they cover.
   Needs Paul to upload the current code of each pier's Pier B box and the
   Compare Piers box(es) as .txt (D343). All 7 Pier B boxes share the pattern;
   Pier B boxes are byte-tight (750-1,250 bytes margin) so split, don't minify.
4. Check `data.json` after deploy: cache-busted curl, MD5 + bytes, confirm
   `station_history.trw.hourly` hours_ago values are true, then trigger the
   workflow once by hand.
5. Investigate WHY the two Seagull stations stopped (station down vs fetch
   failing). Claude's sandbox gets HTTP 403 from the ERDDAP server, so Paul
   (or a Cloudflare/other route) may need to check
   `https://seagull-erddap.glos.org/erddap/` for datasets 598 (Neshotah) and
   the Port Washington dataset.
6. All v61 remaining tasks stay open (confirm 9 files live, retire old boxes,
   Sturgeon Bay rebuild, Compare Piers NOAA LMHOFS attribution, St. Joseph probe #2).

## Decisions Log

*(New entries this session - D449 onward. Direction approved by Paul; exact
details finalized when each version is built.)*

- **D449 - Anchor `hours_ago` to run time, not last reading (v30).** Why: the
  code's own comment says "for each whole hour back from now" but the code
  used `latest["time"]`; wrong whenever a station is late or dead. Fixing it
  at the source (backend) means every consumer gets true labels ("backend
  thinks, frontend displays"). Alternative considered: have the front end
  correct labels using `observed_at_utc`; rejected because it would need
  changes in 7+ boxes and the scoring code would stay wrong.
- **D450 - Stale stations must not count as "measured" wind (v31).** Fall back
  through the existing chain to a real neighbor labeled ESTIMATED, then to the
  zone forecast labeled FORECAST. Why: a 43-hour-old wind is not a
  measurement; the labels (ESTIMATED/FORECAST) already exist and are already
  explained to visitors; needs no new concepts. Alternative rejected: keep
  `LIVE_STALE` scoring - honest about age but still gives 30% of the score to
  2-3-day-old wind.
- **D451 - Charts draw a true 72-hour window with a labeled gap.** Why: stretching
  30 bars over a "72 hours" header (current pier pages) misleads; hiding the
  short data hides the outage; a labeled gap shows what is known and unknown.
  Paul explicitly said the Compare page's short strip is "more accurate" and
  disliked the pier-page chart.
- **D452 - Order: backend v30 -> backend v31 -> front end.** Why: the front end
  should be built against true labels once; doing it first would double-count
  the shift. v30 alone is safe because the current chart code already ignores
  the hour numbers and draws array order (to be re-verified from the Pier B
  code before shipping).
- **D453 - Back up before changing anything.** Done (zip above). Standing
  practice for risky changes.
- **D454 - Model routing correction.** `ways-of-working` says Opus for
  `fetch_data.py` backend work and Sonnet for front end. Claude wrongly told
  Paul "Sonnet" for the backend fix earlier this session; corrected here.
  v30/v31 -> Opus. Front-end chart rebuild -> Sonnet.
- **D455 - Handoff before building v30.** Reasons: project rule says backend
  work belongs on Opus (needs a new chat anyway); the diagnosis is long and
  must not be lost; the backup already exists so it is a clean checkpoint.

## Reasoning Ledger

- **Why "hours ago from the last reading" was a silent bug:** it is correct
  when the last reading is ~1h old (Kewaunee 1.3h) and wrong only when a
  station dies - so it stayed invisible until Seagull stations went quiet. The
  page did already warn "Reading 43 hours old" / "Latest reading 44 hours ago
  - not current", so the front end knew the true age; the chart just did not use it.
- **Why 29 hours, not 72:** the backend asks for now-73h to now; the dead
  station only has data in the early part of that window. The window slides
  forward one hour every hour while the last reading stays fixed, so the
  visible data shrinks by an hour per hour - the chart would have been empty in
  about 29 more hours.
- **Why the Compare page looked "better":** same 30 hours of data, but it draws
  the strip at its real (short) length instead of stretching it. It still says
  "1 of the last 30 hours", which is the same misleading wording.
- **Why not just widen/lengthen the lookback:** the data does not exist; the
  station has no readings after Sep 17 ~18:40 Central.
- **Why the wind score matters here:** Wind/Upwelling is 30% of the Bite Index.
  Two Rivers wind factor 35, Port Washington 21, both tagged `LIVE_STALE`; the
  "recent 12 hours" penalty test also counts from the last reading, so it was
  really testing hours 43-55 ago. Overall live scores at the time: Two Rivers 53,
  Port Washington 36 (Sheboygan 30).
- **Why my early Compare-page guess was wrong:** I inferred a different data
  source without seeing the code. Lesson: don't guess a page's data source;
  the screenshot showed it was the same data drawn differently.

## Technical Details

- **Data facts (live `data.json` generated 2026-09-19T19:05:08Z):**
  station_history 73 points (72h): `mtw` Manitowoc Airport, `KSBM` Sheboygan
  Airport, `KSUE` Sturgeon Bay Airport, `kww` Kewaunee MET (72). 30 points
  (hours_ago 29..0, ~29 h): `trw` Neshotah Park (last reading 2026-09-17T23:40Z,
  43.4 h old) and `pww` Port Washington Met (last 23:30Z, 43.6 h old).
  Dormant, no data: `agw` Algoma, `sbcg` Sturgeon Bay CG, `trcg` Two Rivers CG.
- **Code locations in `fetch_data.py` v29:** `fetch_station_history()` ~line 1560
  (downsample loop ~1620-1628); `fetch_glos_wind_history()` ~line 1657 (loop
  ~1723-1729; ERDDAP URL template line 1652; three 24-h chunks from now-73h);
  `STALE_AFTER_HOURS = 3` line 2317; `wind_history` chain config ~2354
  (Two Rivers `[("trw", None)]`, Manitowoc `[("mtw", None)]`, Sheboygan
  `[("KSBM", None)]`, Kewaunee `[("kww", None)]`, Algoma `[("agw", None), ("kww",
  "Kewaunee")]`, Sturgeon Bay `[("sbcg", None), ("KSUE", None)]`);
  `score_wind()` ~line 2923 (uses `hours_ago <= 12` for "recent", flags
  `LIVE_STALE` when older than `STALE_AFTER_HOURS`); chain selection ~3336
  ("first history source with real data wins"); `hours` in explain facts = row
  count (line ~2913).
- **The bug, in mechanism terms:** `target = latest["time"] - timedelta(hours=h)`
  in both history functions, with `max_hours = min(actual_hours_covered, 72)`.
  `hours_ago` therefore means "hours before the last reading". Should be
  `target = now - timedelta(hours=h)` with `h` from 72 down to 0.
- **Side effect to test in v30:** for healthy stations the newest row may
  become `hours_ago = 1` (e.g. Kewaunee's last reading is ~77 min old) and a
  late-reporting station could lose a bar because of the 30-minute matching
  tolerance. Compare old vs new output on realistic data before shipping;
  confirm no unexpected score movement.
- **Validation plan for v30:** `py_compile`; import with mocked network to run
  both functions against synthetic dead-station and healthy-station readings;
  diff old vs new on the same input; scoring before/after; byte count + MD5;
  cache-busted curl of `data.json` after Paul deploys; manual workflow run.
- **Environment facts learned:** Claude's sandbox can `git clone` the GitHub
  repo and fetch `raw.githubusercontent.com`, but `api.github.com` is
  rate-limited and the GLOS ERDDAP server returns HTTP 403 (cannot test the
  station feed directly from the sandbox). Workflow `fetch.yml` runs
  `python fetch_data.py` hourly at minute 0 (actual runs land around :05).
- **Front-end facts (from Paul's screenshots):** Two Rivers page shows header
  "LAST 72 HOURS OF WIND", ~30 stretched bars, axis "3 DAYS AGO / 2 DAYS AGO /
  YESTERDAY / 44H AGO", text "5 of the last 30 hours had wind from the
  favourable south-to-west band", warnings "Reading 43 hours old" and "Latest
  reading 44 hours ago - not current". Compare page rows show 73-bar strips for
  healthy piers and ~30-bar strips for Port Washington and Two Rivers.

## Design Decisions

- True 72-hour window ending "now"; each bar at its real age; empty, labeled
  gap (with the date/time of the last reading) where there is no data; axis
  labels computed from real time; sentence text counts only real hours and says
  the period covered. Applies to the pier pages AND the Compare page.
- Keep the existing stale warnings ("Reading N hours old").

## User Preferences

Unchanged from v61, plus: Paul wants action, not options ("we need to do, we
will do. Just start telling me what to do"); he dislikes visuals that do not
reflect reality ("does not really reflect what 72 hours are"); use tokens
carefully; small edits only; no artifacts unless useful; tell him the model
before each task; he wants a compact summary if a chat gets long.

## Constraints

Unchanged from v61. Restated: one backend change per version (D146); full
replacement files only, delivered as a downloadable file (never printed as
snippets); never reconstruct code from memory (D343); Carrd embeds hard limit
16,384 bytes with 300-500 byte margin; never guess platform UI; verify before
stating diagnoses.

## Risks

- Until v30/v31 ship, Two Rivers and Port Washington show misleading charts and
  a wind score built on 2-3-day-old wind (tagged `LIVE_STALE`).
- The visible history shrinks one hour per hour; in about a day both charts
  go empty and the pier falls back to the forecast anyway.
- v30 tolerance edge cases (see Technical Details); v31 cutoff/neighbor choice
  is a judgment call; front-end edits touch 7+ tight boxes.
- Unknown whether the Seagull stations are down or the fetch is failing.
- Same failure could recur for any station that dies (Algoma's own station has
  been dead since ~2017 and already uses a neighbor).

## Open Questions

- Which neighbor stations should Two Rivers and Port Washington fall back to?
  (candidates: Manitowoc Airport `mtw`; Sheboygan Airport `KSBM`.)
- What cutoff (hours) should trigger the fallback?
- Are the GLOS Seagull stations down, or is the fetch failing?
- Where exactly does the Compare page code live (box name)? It draws the same data.

## Future Ideas

Unchanged from v61. New: add an automatic health check that flags any station
whose last reading is older than a set number of hours in `data.json`.

## Next Session Instructions

**Model: Opus** (backend `fetch_data.py` per `ways-of-working`; switch to Sonnet
later for the front-end chart boxes).

**Exact prompt for Paul to paste into a new chat:**

> Continuing PIERBITE. Read Memory_PIERBITE_PROJECT_MEMORY_2026-09-19_v62.md
> in full before doing anything - it replaces v61. Tell me what you understand
> the current state to be, and confirm which model you are.
>
> Current state: the live backend is fetch_data.py v29 (NOT v28). We found the
> Two Rivers and Port Washington wind stations (GLOS Seagull) stopped reporting
> ~43 hours before the last data.json, so only ~29 hours of history exist, AND
> the backend labels "hours ago" counting back from the station's LAST reading
> instead of from the current time - so the pier-page chart ("LAST 72 HOURS OF
> WIND") is stretched and its labels are wrong, and the wind score/text also
> count from the last reading. A full repo backup was taken (zip saved on my
> computer). Nothing has been changed yet. I approved the plan: v30 = anchor
> hours_ago to run time in both history functions (one change only); v31 =
> dead-station cutoff using the existing wind_history fallback chain
> (neighbor station labeled ESTIMATED, then forecast) plus wording fix; then
> the front end draws a true 72-hour window with a labeled gap on all pier
> pages and the Compare page. Start by cloning/fetching the live fetch_data.py
> and verifying MD5 4fb57fcff5f6ea2f7eb440c6bd9f9243, then build v30, test it
> with mocked data, and give me the file plus deployment steps. I can't use the
> app until this is fixed.

**Reminder for Paul:** after uploading this file, delete
`Memory_PIERBITE_PROJECT_MEMORY_2026-09-18_v61.md` from Project Files.

---

# === EVERYTHING BELOW THIS LINE IS PRESERVED UNCHANGED FROM v61 ===

<!-- PIERBITE PROJECT MEMORY | 2026-09-18 | v61 | Session picked up after a subscription lapse (no handoff had been done since v60 on 2026-09-12). Confirmed with Paul: the Photo Gallery caption bug (v60's open item) was fully resolved across all piers in an off-procedure session between v60 and this one -- marked CLOSED here. This session's actual work was two related navigation fixes, both requested by Paul from screenshots/dictation: (1) the "ALL PIERS" button on every pier page was linking to href="#top" (top of page) instead of jumping down to the "Pick Your Pier" list -- fixed on ALL 7 piers, one Code Embed box at a time, since Carrd boxes are fully isolated and each pier duplicates this button in its own box (same structural pattern that caused the v60 caption bug to be pier-by-pier). (2) The home page's "Pick Your Pier" list box and the Conditions Map box both got a small new "back to home" link added (href="#home"), since visitors can land deep in the page via anchor links with no way back to the top; the Conditions Map box was already near Carrd's byte limit so this addition was kept intentionally minimal and the new margin is now tight. Also fixed: home page hero text said "six" piers, corrected to "seven" (stale since Sturgeon Bay was added). NONE of this session's 9 delivered files have been confirmed live by Paul yet -- all pending verification. Supersedes v60 -- delete Memory_PIERBITE_PROJECT_MEMORY_2026-09-12_v60.md from Project Files and upload this one. -->

# PIERBITE PROJECT MEMORY - 2026-09-18 v61

**THIS IS THE CURRENT REVISION. It supersedes v60.**
Nothing deleted — additive by design. Everything below this v61 section is
preserved byte-for-byte from v60.

## Project Overview

PierBite.com — seven Wisconsin Lake Michigan pier fishing-conditions
pages (Port Washington, Sheboygan, Manitowoc, Two Rivers, Kewaunee, Algoma,
Sturgeon Bay), all rendered as **one single long Carrd page** with piers
reached via anchor links rather than separate pages. Paul is non-technical
and relies entirely on Claude for all code. Carrd Pro Plus frontend +
Python/GitHub Actions backend. Paul is separately building a companion app
in ChatGPT — a different codebase, not connected to this Carrd site or its
Code Embed boxes; issues in one do not carry over to the other.

## Current Status

- **Photo Gallery caption bug (from v60): CLOSED.** Paul confirmed this was
  fully resolved across all piers in a session that happened outside the
  normal handoff procedure, between v60 and this session. No further action
  needed on this — do not carry it forward as a remaining task.
- **ALL PIERS button fix: code delivered for all 7 piers, NOT YET CONFIRMED
  LIVE.** Every pier's own "Pier A" box had `href="#top"` hardcoded into its
  header bar; all 7 have been rewritten with `href="#bite"` instead. Paul
  has not yet pasted these into Carrd or confirmed them working.
- **Home page hero text fix: code delivered, NOT YET CONFIRMED LIVE.**
  "six Lake Michigan fishing piers" → "seven"; "All six, scored" → "All
  seven, scored" in box `pbhh1` (now v10).
- **Two new "back to home" links: code delivered, NOT YET CONFIRMED LIVE.**
  Added to the Pick Your Pier box (`pbpick` v4) and the Conditions Map box
  (`pbcm2a` v3), both linking to `href="#home"`.
- All template-parity and confirmation status carried from v59/v60 is
  otherwise unchanged (see preserved sections below) — Manitowoc/Port
  Washington/Kewaunee/Algoma template-parity files still pending Paul's
  live confirmation from a prior session; Sturgeon Bay's template-parity
  rebuild has still not been started; Two Rivers and Sheboygan pier reports
  are the only fully confirmed-live piers from that earlier work.

## Completed Work (this session)

- Confirmed with Paul (direct statement, authoritative) that the v60 Photo
  Gallery caption bug is fully resolved on all piers — closed out
- Diagnosed the "ALL PIERS" button bug by reading Paul's actual live code
  for two piers (Port Washington `pbpwa`, Sheboygan `pbsha`) rather than
  guessing — confirmed the button hardcodes `href="#top"` inside each
  pier's own header bar, duplicated per pier (not a shared box)
- Delivered `href="#top"` → `href="#bite"` fix for all 7 piers:
  Port Washington (`pbpwa` → v4), Sheboygan (`pbsha` → v10),
  Manitowoc (`pbmta` → v11), Two Rivers (`pbtra` → v11),
  Kewaunee (`pbkwa` → v10), Algoma (`pbaga` → v9),
  Sturgeon Bay (`pbsba` → v9)
- Verified the home page's live text via direct web fetch (not guessed)
  before editing — confirmed "six" appeared in two places
- Delivered home page hero text fix (`pbhh1` → v10): "six" → "seven" piers,
  in both the hero paragraph and the Pick Your Pier tile subtext
- Delivered "back to home" link addition to Pick Your Pier box
  (`pbpick` → v4), placed right above "SOUTH TO NORTH" per Paul's request
- Delivered "back to home" link addition to Conditions Map box
  (`pbcm2a` → v3) — Paul explicitly required NO other changes to this box
  since it was "working perfectly"; confirmed the addition kept the
  existing script/map logic fully untouched, only new HTML/CSS added

## Work In Progress

- None mid-task as of this handoff. All 9 files from this session
  (7 pier boxes + hero + Pick Your Pier + Conditions Map — actually 9 total
  counting each pier separately) have been delivered as complete
  replacement files. Nothing is half-finished.

## Remaining Tasks

1. **Paste and confirm all 9 files from this session are live**, in
   whatever order is convenient for Paul:
   - `pbhh1` v10 (home hero, "seven piers" text)
   - `pbpwa` v4, `pbsha` v10, `pbmta` v11, `pbtra` v11, `pbkwa` v10,
     `pbaga` v9, `pbsba` v9 (all 7 piers' ALL PIERS button → `#bite`)
   - `pbpick` v4 (Pick Your Pier — "back to home" link)
   - `pbcm2a` v3 (Conditions Map — "back to home" link)
   For each: confirm the click/behavior actually works on the live site,
   not just that Carrd accepted the paste.
2. All remaining tasks carried from v59/v60 are still open and untouched
   this session (see preserved section below): confirming
   Manitowoc/Port Washington/Kewaunee/Algoma's earlier template-parity
   files live, deleting each pier's retired old boxes, starting Sturgeon
   Bay's template-parity rebuild.

## Decisions Log

*(New entries this session — D443 onward.)*

- **D443 (Photo Gallery caption bug closed):** Paul confirmed directly that
  this was resolved in an off-procedure session between v60 and this one.
  Trusted as authoritative over any memory entry that still shows it open,
  per the standing rule from D405.
- **D444 (ALL PIERS button bug — root cause):** Every pier's own header bar
  hardcodes `<a class="bl" href="#top">ALL PIERS</a>` inside that pier's
  own Code Embed box — it is NOT a shared button, it is duplicated 7 times
  (once per pier), the same structural pattern that made the v60 caption
  bug pier-by-pier rather than site-wide. Confirmed by reading two piers'
  actual live code (Port Washington, Sheboygan) before assuming the other
  five matched.
- **D445 (fix target: `#bite`, not `#home`):** The home page's Pick Your
  Pier list has Carrd Element ID `bite` (set in that section's own Settings
  panel, not written in any code). All 7 pier's ALL PIERS buttons now point
  there instead of `#top`.
- **D446 (home page "seven piers" text was stale):** The hero text and
  Pick Your Pier tile subtext both still said "six" after Sturgeon Bay was
  added as the 7th pier. Confirmed via direct `web_fetch` of the live site
  before editing, not assumed from memory.
- **D447 (back-to-home links added to two mid-page boxes):** Both the Pick
  Your Pier box and the Conditions Map box live partway down the home page
  and are also reachable directly via anchor link (`#bite`, and presumably
  a future map anchor) with no way back to the top. Paul requested a small
  "back to home" link on each, `href="#home"` — this relies on the home
  page's top section already having Carrd Element ID `home` (confirmed via
  the site's existing main nav, which already uses `#home`; no new Carrd
  setup needed).
- **D448 (Conditions Map box — minimal-change constraint):** Paul stated
  explicitly, repeatedly, that this box was "working perfectly" and that
  NO structure, script, or existing CSS should be touched — only the new
  home link added. Honored: only new HTML (one wrapping row) and new CSS
  (two new classes) were added; every existing line is byte-identical to
  the v2 Paul provided. Because this box was already near Carrd's
  16,384-byte limit (v2 had ~190 bytes of headroom), the new link's label
  and CSS were kept intentionally terse ("HOME" not "BACK TO HOME", short
  class names) rather than trimming any existing code to make room — per
  the standing rule, minifying existing code to fit is not acceptable;
  splitting into an adjacent box is the correct move if more room is ever
  needed here.

## Reasoning Ledger

- **Why the ALL PIERS fix had to be applied to all 7 boxes individually,
  not once:** Carrd Code Embed boxes are fully isolated with no shared
  state or shared code between them (standing platform constraint, first
  documented for the Buoy Watch two-box system). Each pier's header bar,
  including its ALL PIERS button, is pasted independently into that pier's
  own box, so a bug or a fix in one never propagates to another.
- **Why `#bite` was chosen over reconstructing a "home" destination:** Paul
  described the desired behavior as "back to the page with all the piers
  in it," and the site's existing Pick Your Pier section is exactly that
  page-within-the-page, already reachable at `#bite`. No new section or
  Carrd Element ID needed to be created — reusing the existing anchor was
  the minimal, lowest-risk fix.
- **Why the Conditions Map addition was kept so small:** the box had almost
  no byte margin left before this change. Any addition that wasn't
  deliberately minimized risked pushing the box over Carrd's hard limit,
  which would have broken the box entirely rather than just failed to add
  the feature — so caution here was about not breaking something that was
  explicitly described as working perfectly, not just about adding the
  link.

## Technical Details

- **ALL PIERS button, exact fix (identical across all 7 pier boxes):**
  `<a class="bl" href="#top">ALL PIERS</a>` → `<a class="bl" href="#bite">ALL PIERS</a>`
  — the only functional change in every pier file this session; each
  pier's own KEY, BUOY_KEY, and pier-specific display-fix functions
  (stationName(), waveSub() variants, etc.) were preserved verbatim.
- **Byte sizes after this session's fixes** (all well clear of the
  16,384-byte Carrd limit except where noted):
  `pbhh1` v10: 11,947 bytes · `pbpwa` v4: 11,770 · `pbsha` v10: 11,375 ·
  `pbmta` v11: 11,317 · `pbtra` v11: 11,663 · `pbkwa` v10: 11,262 ·
  `pbaga` v9: 11,255 · `pbsba` v9: 11,273 · `pbpick` v4: 10,594 ·
  `pbcm2a` v3: 15,752 (only 632 bytes free — the one box to watch;
  see D448).
- **Home page Element IDs relied on by these fixes:**
  `home` = top of home page (pre-existing, used by the site's main nav —
  confirmed live via `web_fetch`, not assumed); `bite` = the Pick Your
  Pier section (pre-existing, used by the home hero's own "Pick your pier"
  tile per D145-era work).
- **Conditions Map new markup (box `pbcm2a` v3):** the "Surface
  temperature" kicker line was wrapped in a new `.pbcm2-tr` flex row
  alongside a new `<a class="pbcm2-hm" href="#home">&uarr; HOME</a>` link,
  right-aligned via `justify-content:space-between`. No other div, class,
  or script line in the box was altered from Paul's pasted v2.
- **Pick Your Pier new markup (box `pbpick` v4):** a new
  `<div class="hml"><a href="#home">&uarr; BACK TO HOME</a></div>` line
  was inserted between the live-data badge and the `.pph` title row, so it
  renders right above the existing "SOUTH TO NORTH" label. New CSS class
  `.hml` added; nothing else in the box changed from v3.
- All technical details preserved from v59/v60 remain valid and are
  carried forward unchanged in the preserved section below.

## Design Decisions

- **"Back to home" link style:** small, right-aligned, uppercase-tracked
  text link in the site's brand green (`var(--lake)` / `var(--lime)`
  depending on the box's existing variable name), consistent with the
  existing "SOUTH TO NORTH" and "ALL PIERS" label styling already used
  elsewhere on the site — no new visual language introduced.
- All design decisions preserved from v59/v60 remain valid and are carried
  forward unchanged in the preserved section below.

## User Preferences

Unchanged from v60/v52. Confirmed again this session: Paul wants complete
replacement files only (never snippets), a plain-English filename for every
delivered file, a timestamp/version comment inside every file, and byte
counts always checked and reported before delivery.

## Constraints

Unchanged from v60/v52. Key ones, restated:
- Carrd Code Embed hard limit: 16,384 bytes. Target 300–500 byte minimum
  margin — `pbcm2a` v3 is currently below that target at 632 bytes free
  and should be watched.
- Full replacement files only — no diffs, no snippets.
- Every filename must include the literal live Carrd box ID.
- One backend change per session, verify before building anything else.
- Never reconstruct code from memory — always require the actual pasted
  source file before editing it (this session: waited for Paul to paste
  each pier's actual code rather than assuming all 7 matched the first
  two).
- When a box is explicitly described as "working perfectly," treat that as
  a hard constraint against touching anything beyond the specific request
  (new this session, from the Conditions Map fix — see D448).

## Risks

- **`pbcm2a` (Conditions Map, Box 1) now has very little byte margin left
  (632 bytes).** Any future change to this box should be planned with that
  in mind — a small text change may be fine, but anything larger should
  probably go into a new adjacent box (`pbcm2c` or similar) rather than
  risk pushing this one over the limit.
- **None of this session's 9 files have been confirmed live yet.** Until
  Paul pastes and checks each one, treat the ALL PIERS button fix, the
  "seven piers" text fix, and both new home links as undeployed.
- All risks carried from v59/v60 are otherwise unchanged (see preserved
  section below) — St. Joseph MI probe still pending a second run; Compare
  Piers NOAA LMHOFS attribution still silently missing.

## Open Questions

- Paul mentioned, while working on the separate ChatGPT-built app, that
  "Sheboygan seemed to be an issue" but couldn't recall specifics. This is
  in the ChatGPT app's own codebase, not pierbite.com/Carrd, so it has no
  bearing on this project unless Paul brings back specifics that turn out
  to matter here too. Not tracked as an action item — just noted in case
  Paul raises it again.

## Future Ideas

Unchanged from v59/v60 (see preserved section below).

## Next Session Instructions

**Exact prompt for Paul to paste into a new chat:**

> Continuing PIERBITE. Read Memory_PIERBITE_PROJECT_MEMORY_2026-09-18_v61.md
> in full before doing anything — this is the current file, it replaces v60.
> Tell me what you understand the current state to be. Confirm model
> identity.
>
> Current state: the v60 Photo Gallery caption bug is CLOSED (Paul
> confirmed it was fixed in an off-procedure session). This session (v61)
> fixed two navigation issues, all 9 files delivered but NOT YET CONFIRMED
> LIVE: (1) the "ALL PIERS" button on all 7 piers was linking to #top
> instead of #bite (the Pick Your Pier list) — fixed on all 7 pier boxes;
> (2) home page hero text said "six" piers, corrected to "seven"; (3) small
> "back to home" links (href="#home") added to the Pick Your Pier box and
> the Conditions Map box. The Conditions Map box (pbcm2a) is now tight on
> byte space (632 bytes free) — treat future changes to it carefully, per
> the Risks section. First priority this session: confirm all 9 files are
> live and working before starting anything new.

**Reminder for Paul:** after uploading this file, delete
`Memory_PIERBITE_PROJECT_MEMORY_2026-09-12_v60.md` from Project Files.

---

# === EVERYTHING BELOW THIS LINE IS PRESERVED UNCHANGED FROM v60 ===

<!-- PIERBITE PROJECT MEMORY | 2026-09-12 | v60 | Session found and fixed a real bug unrelated to the template-parity rebuild work: Photo Gallery captions were saving correctly (visible in the admin photo-uploader's Remove tab) but never appeared on the live site. Root cause: the shared Photo Gallery pattern used on every restructured pier (originating from Sheboygan's pbphsh v3) only used the caption in two places -- the invisible img alt text, and a separate text block stacked BELOW the enlarged photo in the lightbox popup. On a tall photo, that stacked block gets pushed off the visible screen because the image itself can already fill close to full screen height. First fix attempt (captions under each thumbnail) was tried and explicitly rejected by Paul as not matching prior behavior. Correct fix (v4, confirmed working by Paul): thumbnails reverted to plain photo squares; caption now overlays the BOTTOM EDGE of the enlarged photo itself as a semi-transparent strip, so it can never be pushed off screen, and wraps for long captions. Manitowoc's pbphmn is now fixed and confirmed (v4). This same bug is present on every other pier's Photo Gallery box, including the Sheboygan master template itself (pbphsh) -- none of the others have been touched yet. Paul explicitly asked for an extensive handoff and wants this remembered because he plans to have the same fix applied to the remaining piers. Supersedes v59 -- delete Memory_PIERBITE_PROJECT_MEMORY_2026-09-11_v59.md from Project Files and upload this one. -->

# PIERBITE PROJECT MEMORY - 2026-09-12 v60

**THIS IS THE CURRENT REVISION. It supersedes v59.**
Nothing deleted — additive by design. Everything below this v60 section is
preserved byte-for-byte from v59.

## Project Overview

PierBite.com — six (possibly seven, counting Port Washington) Wisconsin Lake
Michigan pier fishing-conditions pages, all rendered as **one single long
Carrd page** with piers reached via anchor links rather than separate pages.
Paul is non-technical and relies entirely on Claude for all code. Carrd Pro
Plus frontend + Python/GitHub Actions backend. This session's work was
entirely on the frontend Photo Gallery boxes — no backend/data-pipeline
changes.

## Photo Gallery Caption Bug — Found and Fixed on Manitowoc (NEW — 2026-09-12, v60)

Paul reported (by voice dictation, described non-technically) that captions
he adds when uploading photos were not showing up on the live site, even
though he could see them if he looked in the "Remove Photo" section of his
private admin photo-uploader tool.

### Initial mix-up (resolved quickly, worth noting for future sessions)

Paul's first upload of code was the **Submit a Photo** box (`pbsap-manitowoc`)
— the small "share your photo" button/link box — not the box that actually
displays photos. This is an easy mix-up: both boxes live under similar-looking
names in Carrd's box list. Clarified the naming pattern so this doesn't
recur:
- **Submit a Photo** boxes are named `pbsap-[piername]` (e.g. `pbsap-manitowoc`)
  — just a button/link, no photos, no captions.
- **Photo Gallery** boxes are named `pbph[piercode]` (e.g. `pbphmn` = Manitowoc,
  `pbphsh` = Sheboygan, `pbphtr` = Two Rivers, `pbphpw` = Port Washington,
  `pbphkw` = Kewaunee, `pbphag` = Algoma) — this is the one that actually
  fetches and displays photos, and the one that matters for any caption bug.

### Root cause (confirmed by reading the actual code, not guessed)

Manitowoc's `pbphmn` v2 (the collapsible-restructure version, built to match
Sheboygan's `pbphsh` v3 pattern) used the caption text in exactly two places:
1. As the `alt` attribute on each thumbnail `<img>` — invisible to a sighted
   visitor, only read by screen readers.
2. As a separate `<div>` stacked **below** the enlarged photo in the lightbox
   popup (the full-screen view that opens when you click a thumbnail).

There was no line of code anywhere that printed the caption directly under
a thumbnail on the page, and — critically — the lightbox caption block could
be pushed **off the visible screen** whenever the enlarged photo was tall:
the image itself is allowed to take up to 80% of the viewport height
(`max-height:80vh`), and a caption stacked as a separate flex item after it
has nowhere left to go if the photo already fills most of the screen. This
is exactly what Paul was describing — the caption technically existed in
the code and even had a value, it just rendered somewhere he
couldn't scroll to see.

### First fix attempt — REJECTED by Paul (D439 below)

Delivered `pbphmn` v3, which added a caption line directly under each
thumbnail in the grid. Paul's response: "not really what I had before" —
this was not the previous behavior and not the fix he wanted. He clarified:
captions should show **only when a photo is enlarged**, and specifically as
an overlay **on top of the photo itself, at the bottom of it** — not as a
separate block below the thumbnail, and not as a separate block below the
enlarged image either (since that's what caused the original off-screen
problem).

### Correct fix — v4, confirmed working by Paul (D440 below)

- Reverted thumbnails to plain photo squares — no caption text under them.
- Restructured the lightbox so the image and caption sit inside one
  `position:relative` wrapper, with the caption `<div>` set to
  `position:absolute; left:0; right:0; bottom:0` and a semi-transparent dark
  background — a shaded strip pinned to the bottom edge of the photo itself,
  not a separate item stacked after it.
- This guarantees the caption is always visible regardless of how tall the
  photo is, since it's layered on top of the same box as the image rather
  than competing for leftover vertical space below it.
- Long captions wrap naturally onto a second line inside the strip (same
  underlying text-wrapping behavior Paul remembered from before).
- If a photo has no caption, no strip is shown at all — just the plain
  photo, same as always.

**File delivered:** `manitowoc-photo-gallery.html` → box `pbphmn` — v4,
6,242 bytes (well under the 16,384-byte Carrd limit, large margin, not a
tight box). **Confirmed correct and working by Paul on the live site.**

### Standing risk: this bug is site-wide, not Manitowoc-specific

Because every restructured pier's Photo Gallery box was built directly from
the Sheboygan `pbphsh` v3 pattern (per the template-parity workflow, D418),
**this exact caption-visibility bug is present on every pier's Photo Gallery
box that has gone through the collapsible restructuring** — including the
Sheboygan master template itself. None of these have been fixed yet:

- `pbphsh` (Sheboygan) — this is the **master template** every other pier's
  gallery was copied from; fixing this one first and using the corrected
  version as the new master pattern is the logical order, but Paul hasn't
  confirmed sequencing yet.
- `pbphtr` (Two Rivers)
- `pbphpw` (Port Washington)
- `pbphkw` (Kewaunee)
- `pbphag` (Algoma)

Paul explicitly said he'll need to come back and get the same fix applied
to "all my other piers" — this is a known, named, pending task, not a
surprise to rediscover later.

## Current Status

- **Manitowoc Photo Gallery (`pbphmn`):** fixed to v4, confirmed live and
  correct by Paul. Caption now overlays the bottom of the enlarged photo.
- **Sheboygan, Two Rivers, Port Washington, Kewaunee, Algoma Photo Gallery
  boxes:** all still carry the pre-fix caption behavior (caption invisible
  or off-screen when enlarging a photo). Not yet touched. Pending, one pier
  at a time, same as every other PIERBITE workflow.
- **Sturgeon Bay:** still the last of the original six standard piers not
  yet brought to template parity at all (unchanged from v59) — separate,
  larger task from the caption fix.
- All template-parity and confirmation status carried from v59 is otherwise
  unchanged (see preserved v59 section below) — Manitowoc/Port
  Washington/Kewaunee/Algoma template-parity files still pending Paul's live
  confirmation from the prior session; Two Rivers and Sheboygan pier reports
  are the only fully confirmed piers.

## Completed Work (this session)

- Diagnosed the Photo Gallery caption bug by reading the actual `pbphmn` v2
  code Paul pasted, not by guessing
- Identified and corrected an initial mix-up between the Submit a Photo box
  and the Photo Gallery box, and documented the naming pattern to prevent
  recurrence
- Delivered and then corrected the fix based on Paul's direct feedback
  (thumbnail captions rejected, moved to enlarged-photo overlay instead)
- Delivered `manitowoc-photo-gallery.html` v4 — confirmed working live

## Work In Progress

- None mid-task as of this handoff — Manitowoc's fix is fully confirmed and
  closed out. The remaining piers' fixes have not been started.

## Remaining Tasks

1. Apply the same v4-style caption-overlay fix to Sheboygan's `pbphsh` —
   likely first, since it's the master template
2. Apply the same fix to Two Rivers (`pbphtr`), Port Washington (`pbphpw`),
   Kewaunee (`pbphkw`), and Algoma (`pbphag`) — one pier at a time, Paul
   pastes the current code, Claude applies the same overlay technique
3. Confirm each fix live before moving to the next pier, same standing
   workflow as every other PIERBITE change
4. All remaining tasks carried from v59 are still open and untouched by
   this session (see preserved section below) — confirming Manitowoc/Port
   Washington/Kewaunee/Algoma's template-parity files live, deleting each
   pier's retired old boxes, starting Sturgeon Bay's template-parity rebuild

## Decisions Log

*(New entries this session — D438 onward.)*

- **D438 (Photo Gallery caption bug — root cause):** Captions save
  correctly in `photos.json` and are visible in the admin uploader's Remove
  tab, but were not visible on the live site. Root cause: the shared
  Photo Gallery pattern (originating from Sheboygan's `pbphsh` v3, copied to
  every restructured pier including Manitowoc's `pbphmn` v2) only used the
  caption as an invisible `alt` attribute and as a separate text block
  stacked below the enlarged photo in the lightbox — a block that can be
  pushed off the visible screen when the photo itself is tall enough to
  nearly fill the viewport. Confirmed by reading the actual code, not
  assumed from the symptom alone.
- **D439 (first fix attempt rejected — caption belongs on the enlarged
  photo, not the thumbnail):** Initial fix (v3) printed the caption under
  each thumbnail in the grid. Paul rejected this directly — it wasn't the
  previous behavior and wasn't what he wanted. Clarified requirement:
  caption should only appear when a photo is enlarged, as an overlay
  directly on the photo (at the bottom), not as a block under the
  thumbnail and not as a block below the enlarged image either.
- **D440 (caption-overlay fix, v4 — confirmed working):** Thumbnails
  reverted to plain photo squares. Lightbox restructured so the image and
  caption share one `position:relative` wrapper, with the caption as a
  `position:absolute; bottom:0` semi-transparent strip on the photo itself.
  This guarantees visibility regardless of photo height and lets long
  captions wrap. No caption present → no strip shown. Confirmed correct by
  Paul on Manitowoc's live site.
- **D441 (this bug is site-wide, not Manitowoc-specific):** Because every
  restructured pier's Photo Gallery box was copied from the same Sheboygan
  `pbphsh` v3 pattern, the same caption-visibility bug exists on Sheboygan,
  Two Rivers, Port Washington, Kewaunee, and Algoma's Photo Gallery boxes.
  None of these have been fixed yet. Paul explicitly confirmed he'll need
  the same fix applied to "all my other piers" in a future session — this
  is a named, tracked task, not something to rediscover later.
- **D442 (Sheboygan's `pbphsh` should become the new master reference once
  fixed):** Since `pbphsh` is the master template every other pier's
  gallery is built from, applying the v4-style fix there and using the
  corrected version as the go-forward master pattern (rather than fixing
  each pier independently from the old pattern) is the logical sequencing
  — not yet confirmed with Paul, but flagged as the sensible default.

## Reasoning Ledger

- **Why the first fix attempt (thumbnail captions) was tried before the
  eventual correct fix:** Paul's original description ("it doesn't show up
  on screen and it used to") didn't specify exactly where the caption used
  to appear — under the thumbnail, or on the enlarged photo. The
  interpretation chosen first (show it under the thumbnail, since that's
  the simplest way to guarantee it's visible without a click) turned out
  to be wrong; Paul's follow-up dictation clarified the caption belongs on
  the enlarged photo, overlaid on top of it, matching what the site used
  to do.
- **Why overlaying the caption on the image (rather than keeping it as a
  separate block below the image in the lightbox) is the more robust fix:**
  A caption stacked below the enlarged photo only has room to display if
  there's leftover vertical space after the image — for a tall photo close
  to the 80vh height cap, there often isn't any. Overlaying the caption
  directly on the image, as part of the same positioned box, removes that
  dependency entirely: the caption is guaranteed to render somewhere on
  the visible image, not in space that may or may not exist below it.
- **Why the caption-visibility bug wasn't introduced by any specific
  pier's rebuild, but is inherited from the shared master pattern:** Each
  restructured pier's Photo Gallery box was explicitly built "matching
  Sheboygan's pbphsh v3 pattern" per the template-parity workflow (D418) —
  the caption-in-lightbox-only behavior was already present in that master
  pattern before Manitowoc, Two Rivers, Port Washington, Kewaunee, or
  Algoma were ever touched. This means the bug is structural to the shared
  template, not a mistake unique to any one pier's rebuild session.

## Technical Details

- **Manitowoc Photo Gallery (`pbphmn`) is now at v4** — 6,242 bytes, well
  under the 16,384-byte Carrd limit with a large margin (not a tight box,
  unlike Pier B boxes across the site).
- **The exact CSS/structure change to replicate on every other pier's
  Photo Gallery box:** in the lightbox markup, the image and caption
  `<div>` must sit inside a shared wrapper set to `position:relative`. The
  caption `<div>` itself becomes `position:absolute; left:0; right:0;
  bottom:0;` with a semi-transparent dark background (`rgba(2,6,10,.72)`
  in Manitowoc's fix) and rounded bottom corners to match the photo's own
  corner radius. The caption should only be shown (`display:block` /
  a `.show` class) when `p.caption` is truthy for that photo — otherwise
  hidden entirely. Thumbnails in the grid should NOT show caption text —
  revert any `.cap` div under each thumbnail if a pier's gallery still has
  one from a prior attempt.
- **Box-ID naming reminder (to avoid the mix-up that happened this
  session):** Submit a Photo boxes = `pbsap-[piername]`. Photo Gallery
  boxes = `pbph[piercode]` (`pbphsh`, `pbphmn`, `pbphtr`, `pbphpw`,
  `pbphkw`, `pbphag`). Always confirm which box Paul has pasted before
  diagnosing a photo-display or caption issue — the two are easy to
  confuse from a Carrd box list alone.

## Design Decisions

- **Caption placement, confirmed final:** captions never appear under
  thumbnails in the gallery grid. Captions only appear when a photo is
  enlarged (lightbox), as a semi-transparent overlay strip on the bottom
  edge of the photo itself — this is now the standard pattern for every
  pier's Photo Gallery box, not just Manitowoc's.

## User Preferences

*(Additions this session — prior preferences preserved below, including
the full standing list in Paul's saved account preferences: brand-new to
Claude, needs plain step-by-step instructions, full replacement files
only with a downloadable file alongside every code block, timestamp
comments on every file, check the live site directly before asking for
screenshots when possible, state the most likely cause first, and always
name the most cost-effective model for the task at hand.)*

- Confirmed again: Paul describes bugs by voice dictation in everyday,
  non-technical terms (e.g. describing the admin uploader's "removed
  section" rather than naming it precisely) — patience in interpreting
  this, and asking exactly which box is involved before diagnosing, is
  necessary and was needed again this session.
- Paul wants an explicit, thorough handoff (his own words: "very
  extensive handoff") whenever he flags one — this session's handoff is
  the model for how much detail to preserve going forward, not a one-off.

## Constraints

Unchanged from v59, plus:
- Every pier's Photo Gallery box must use the corrected caption-overlay
  pattern (D440/technical detail above) going forward — this is now the
  correct master pattern, superseding the pbphsh v3 lightbox-caption
  behavior everywhere it still exists.

## Risks

- **Five Photo Gallery boxes still have the caption-visibility bug**:
  Sheboygan (`pbphsh`), Two Rivers (`pbphtr`), Port Washington (`pbphpw`),
  Kewaunee (`pbphkw`), Algoma (`pbphag`). Any photo caption uploaded for
  these piers right now will have the same problem Manitowoc had until
  each box gets the same fix.
- All risks carried from v59 remain open and unchanged (see preserved
  section below): Manitowoc still not confirmed live (four+ sessions
  running), Port Washington not yet confirmed fully clean, Kewaunee's and
  Algoma's new template-parity files not yet confirmed live, both piers'
  3 retired old boxes each still needing deletion, tight Pier B byte
  margins on Kewaunee/Algoma, Two Rivers' 3 retired old boxes still
  unconfirmed deleted, Sturgeon Bay not yet started, and all other
  standing risks in the preserved v59 section.

## Open Questions

- **Which pier's Photo Gallery should get the caption-overlay fix next?**
  Sheboygan is the logical first choice since it's the master template,
  but not yet confirmed with Paul.
- Does Paul want the corrected Sheboygan `pbphsh` to become the new
  master reference for any future pier rebuilds (including Sturgeon Bay),
  or should Sturgeon Bay's eventual Photo Gallery just get the fix applied
  directly during its own build?
- All open questions carried from v59 remain open and unchanged (see
  preserved section below).

## Future Ideas

Unchanged from v59/v56 (see preserved section below) — one global species
temperature slider, HOT PIER TODAY card, lazy-loading per pier, St.
Joseph MI as first east-shore pier.

## Next Session Instructions

**Exact prompt for Paul to paste into a new chat:**

> Continuing PIERBITE. Read Memory_PIERBITE_PROJECT_MEMORY_2026-09-12_v60.md
> in full before doing anything — this is the current file, it replaces v59.
> Tell me what you understand the current state to be. Confirm model identity.
>
> Current state: a real bug was found and fixed this session — Photo
> Gallery captions were saving correctly but not showing up on the live
> site. Root cause: the caption was only used in the image's invisible alt
> text and in a text block stacked below the enlarged photo in the
> lightbox popup — a block that could get pushed off-screen on a tall
> photo. Fixed on Manitowoc's Photo Gallery box (`pbphmn`, now v4):
> captions no longer show under thumbnails, they now overlay the bottom
> edge of the enlarged photo itself as a semi-transparent strip, which is
> always visible no matter how tall the photo is. Confirmed working by
> Paul on the live site.
>
> This same bug exists on every other pier's Photo Gallery box, because
> they were all built from the same Sheboygan `pbphsh` v3 pattern:
> Sheboygan (`pbphsh`), Two Rivers (`pbphtr`), Port Washington (`pbphpw`),
> Kewaunee (`pbphkw`), Algoma (`pbphag`). None of these have been fixed
> yet. Ask Paul which pier he wants to do next — Sheboygan first makes
> sense since it's the master template, but confirm rather than assume.
>
> When Paul pastes a pier's current Photo Gallery code: apply the same
> fix already used on Manitowoc's v4 — revert any caption text under
> thumbnails (should be plain photo squares only), and restructure the
> lightbox so the caption sits inside the same `position:relative` wrapper
> as the enlarged image, as a `position:absolute; bottom:0` semi-
> transparent overlay strip, shown only when a caption exists. Use that
> pier's own PIER_KEY/PIER_NAME and box ID — never copy Manitowoc's
> pier-specific values by mistake.
>
> Reminder on box naming (a mix-up happened this session): Submit a Photo
> boxes are `pbsap-[piername]`; Photo Gallery boxes are `pbph[piercode]`
> (`pbphsh`, `pbphmn`, `pbphtr`, `pbphpw`, `pbphkw`, `pbphag`). If Paul
> says "the photo box," confirm which one before diagnosing anything.
>
> Standing rules unchanged: full replacement files only, plain
> English filenames, timestamp + version in the internal HTML comment,
> byte size verified under Carrd's 16,384 limit before delivery, one pier
> at a time, confirm live before moving to the next. Model routing:
> Sonnet is the right choice for this kind of frontend CSS/JS fix — no
> need for Opus unless it's `fetch_data.py` backend or scoring-judgment
> work.
>
> Also still open from before this session: confirm whether Manitowoc,
> Port Washington, Kewaunee, and Algoma's template-parity files are
> confirmed live; confirm/delete each pier's retired old boxes; decide
> whether to start Sturgeon Bay's template-parity rebuild.

**Reminder for Paul:** after uploading this file, delete
`Memory_PIERBITE_PROJECT_MEMORY_2026-09-11_v59.md` from Project Files.

---

<!-- PIERBITE PROJECT MEMORY | 2026-09-11 | v59 | Session covered two more template-parity rebuilds, back to back: Kewaunee (4th pier) and Algoma (5th pier). Kewaunee: 8 old boxes brought to Sheboygan's 5-box structure. Kewaunee had never had a Photo Gallery box at all (same situation as Port Washington in v58) - built fresh as pbphkw. Sky+Lure Call, Species, and Suggestions boxes retired (5th/4th/4th occurrence of these same established patterns). Fish Cleaning made collapsible and recolored; Submit a Photo renamed pbsap-kewaunee. All 5 files passed the D427 verification checklist. Algoma: same 8-to-5 mapping, but with two real differences worth remembering. (1) Algoma's Pier B deliberately reads Kewaunee's own wind station (HKEY="kww") because Algoma's own wind station (AGMW3) has not reported since approximately 2017 - this was preserved exactly, not "corrected," since it's a real pier-specific data-source fact, not a template mismatch. (2) Algoma already had a working Photo Gallery box (pbphag, unlike Kewaunee/Port Washington) - it was restructured to the collapsible pattern and recolored in place, keeping its existing pier-specific ID, rather than being rebuilt from scratch. A real bug was caught and fixed during Algoma's own verification pass, not after delivery: the first draft of Algoma's Pier B carried over a dead waterDescription() function and several now-unused variables (label/p/h/waterDesc/windName) left over from the Temperature Break and wind-attribution logic that had already been dropped for template parity - this pushed the file's byte margin down to 223 bytes, under the 300-500 byte floor. Root-caused, the dead code was removed (not just the header comment shortened), which also caught and fixed a factual error the comment itself had made about what was preserved vs. dropped. Final Algoma Pier B margin: 1,012 bytes. Standing lesson: when restructuring a pier's Pier B to drop Temperature Break / Pier Access / bottom attribution, check for and remove the JS variables and helper functions that only existed to feed those dropped sections - don't just delete the HTML output lines. Both piers' new files are delivered but not yet confirmed live by Paul. Supersedes v58 - delete Memory_PIERBITE_PROJECT_MEMORY_2026-09-11_v58.md from Project Files and upload this one. -->

# PIERBITE PROJECT MEMORY - 2026-09-11 v59

**THIS IS THE CURRENT REVISION. It supersedes v58.**
Nothing deleted — additive by design. Everything below this v59 section is
preserved byte-for-byte from v58.

## Project Overview

PierBite.com — six (possibly seven, counting Port Washington) Wisconsin Lake
Michigan pier fishing-conditions pages, all rendered as **one single long
Carrd page** with piers reached via anchor links (`#sheboygan`,
`#manitowoc`, `#two-rivers`, `#port-washington`, `#kewaunee`, `#algoma`,
etc.) rather than separate pages. Paul is non-technical and relies
entirely on Claude for all code. Carrd Pro Plus frontend + Python/GitHub
Actions backend. Of the original six standard piers, only **Sturgeon Bay**
has not yet received the template-parity treatment as of this session.

## Kewaunee Template-Parity Rebuild (NEW — 2026-09-11, v59)

Fourth full application of the template-parity workflow (D418), after
Manitowoc (v56), Two Rivers (v57), and Port Washington (v58). Paul supplied
the old Kewaunee `.txt` dump and the Sheboygan template as the two working
files.

### Kewaunee box mapping:

| Old Kewaunee box | Old ID | Outcome |
|---|---|---|
| Pier A | `pbkwa` | Kept — DNR banner and its `.dnr` CSS rule removed (matches pbsha v9); `KEY="kewaunee"`, `BUOY_KEY=null`, `WIND_SHARED=""` preserved verbatim |
| Pier B | `pbkwb` | Kept, restructured — Sky/Moon merged into collapsible w/ forecast, using Kewaunee's own coordinates (44.4589/-87.5094, taken from the old Sky box) and station keys (`HKEY="kww"`, `ZKEY="kwz"`, `PKEY="kewaunee"`); direction-weights key table (`.dkey`), Temperature Break, Pier Access, bottom attribution line all dropped, matching pbshb v8. Kewaunee's own `UPWELLING_COMPONENT` table was already correct (copied verbatim from `fetch_data.py`, MD5 `a797f11665c6badf903959aa12b5b139`) and was preserved unchanged, not re-derived |
| Sky + Lure Call | `pb-kw4-sky` | **Retired** — same hidden "Today's Lure Call" panel pattern already found in Manitowoc/Two Rivers/Port Washington's old Sky boxes. Fourth occurrence, applied per established precedent without re-asking |
| Species | `pbkwsp` | **Retired** — no Sheboygan counterpart |
| Suggestions | `pb-kw-sug` | **Retired** — no Sheboygan counterpart |
| Fish Cleaning | `pb-kw-clean` | Kept, restructured — always-open panel converted to collapsible toggle, recolored from the old non-master values (`--im:#8fa9c1`, `--if:#5d788f`) to the master palette |
| Photo Gallery | *(did not exist)* | **Built new**, box `pbphkw` — Kewaunee never had a Photo Gallery box, same situation as Port Washington in v58. Built fresh from Sheboygan's `pbphsh` v3 pattern with Kewaunee's own pier key/name |
| Submit a Photo | `pbsap` | Kept, **renamed** to `pbsap-kewaunee` — same generic-ID collision fix as every prior pier (D416/D417), recolored to master palette, radius 10px→16px |

### Files delivered:

- `kewaunee-pier-a-report.html` → box `pbkwa` — 11,265 bytes
- `kewaunee-pier-b-report.html` → box `pbkwb` — 15,135 bytes, **1,249
  bytes margin — tight, same caution level as every other pier's rebuilt
  Pier B, flag before adding anything**
- `kewaunee-fish-cleaning-stations.html` → box `pb-kw-clean` — 3,605 bytes
- `kewaunee-photo-gallery.html` → **new** box `pbphkw` — 5,424 bytes
- `kewaunee-submit-a-photo.html` → box `pbsap-kewaunee` — 1,391 bytes

All 5 passed the D427 verification checklist (`node --check` on every
script block, CSS brace-count balance, HTML div-tag-balance count, byte
size vs. 16,384) before being delivered. **Not yet confirmed live by
Paul.**

## Algoma Template-Parity Rebuild (NEW — 2026-09-11, v59)

Fifth full application of the template-parity workflow. Two things made
this session different from Kewaunee's, both flagged to Paul before any
files were written.

### Algoma box mapping:

| Old Algoma box | Old ID | Outcome |
|---|---|---|
| Pier A | `pbaga` | Kept — DNR banner removed; `KEY="algoma"`, `BUOY_KEY=null`, `WIND_SHARED=""` preserved verbatim |
| Pier B | `pbagb` | Kept, restructured — Sky/Moon merged into collapsible w/ forecast, Algoma's own coordinates (44.6086/-87.4350). **`HKEY="kww"` preserved exactly** — Algoma deliberately reads Kewaunee's own MET station because Algoma's own wind station (AGMW3) has not reported since approximately 2017. This is a genuine pier-specific data-source fact, not a template mismatch, so it was left as-is rather than "corrected" to an Algoma-only key. The old windAttrib "borrowed from Kewaunee..." on-page attribution *display line* was dropped (matches template, same as every other pier's dropped attribution line) — but the disclosure is still visible to visitors via Pier A's Wind cell subtitle (`windSub()`'s existing "estimated, borrowed from" logic). `ZKEY="algz"`, `PKEY="algoma"` preserved |
| Sky + Lure Call | `pb-alg4-sky` | **Retired** — same Lure Call pattern, 5th occurrence |
| Species | `pbagsp` | **Retired** — no Sheboygan counterpart |
| Suggestions | `pb-alg-sug` | **Retired** — no Sheboygan counterpart |
| Fish Cleaning | `pb-alg-clean` | Kept, restructured to collapsible + recolored to master palette |
| Photo Gallery | `pbphag` | **Already existed** (unlike Kewaunee/Port Washington) — restructured from the old always-open, full-width dark-panel layout to the collapsible toggle pattern, recolored to master palette. Box ID `pbphag` kept unchanged since it was already pier-specific — no collision-ID rename needed |
| Submit a Photo | `pbsap` | Kept, renamed to `pbsap-algoma`, recolored, radius 10px→16px |

### Bug caught and fixed during this session's own verification pass (not after delivery)

The first draft of `algoma-pier-b-report.html` passed D427's checks (JS
syntax, CSS braces, div balance) but came in at only **223 bytes margin**
— below the project's 300–500 byte floor (per v55/D-notes on
`buoywatchA`). Investigated rather than just shortening the header
comment.

**Root cause:** the draft had carried over a dead `waterDescription(h)`
function and several now-unused variables (`label`, `p`, `h`,
`waterDesc`, `windName`) from the old Algoma file's Temperature Break and
wind-attribution logic — logic that had already been dropped from the
*rendered output* for template parity, but whose *supporting JS* was
never removed. This is the same class of oversight, generalized: dropping
a section's HTML doesn't automatically drop the code that only existed to
feed it.

Fixing this also surfaced a second, smaller problem: the file's own
header comment had claimed the old windAttrib "borrowed from Kewaunee..."
wording was *preserved* — it was not; that display line had been dropped
along with the rest of the bottom attribution, matching every other
rebuilt pier. The comment was corrected in the same pass.

**Fix:** removed the dead function and the five unused variables. Final
Algoma Pier B size: 15,372 bytes, **1,012 bytes margin.**

**Standing lesson (new):** when restructuring a pier's Pier B box to drop
Temperature Break, Pier Access, or the bottom attribution line to match
Sheboygan's rebuilt pbshb, explicitly check for and remove the JS helper
functions and variables that only existed to feed those now-dropped
sections — not just the HTML output lines themselves. A byte-margin
shortfall below the 300–500 floor is a good trigger to check for exactly
this, before assuming the comment or whitespace is the place to trim.

### Files delivered:

- `algoma-pier-a-report.html` → box `pbaga` — 11,207 bytes
- `algoma-pier-b-report.html` → box `pbagb` — 15,372 bytes, **1,012 bytes
  margin (after the dead-code fix above) — still tight, flag before
  adding anything**
- `algoma-fish-cleaning-stations.html` → box `pb-alg-clean` — 3,657 bytes
- `algoma-photo-gallery.html` → box `pbphag` (restructured, not new) —
  5,680 bytes
- `algoma-submit-a-photo.html` → box `pbsap-algoma` — 1,291 bytes

All 5 passed the full D427 checklist, re-run after the dead-code fix.
**Not yet confirmed live by Paul.**

## Current Status

- **Sheboygan:** master template, effectively locked.
- **Manitowoc:** still not confirmed live by Paul — this is now carried
  open across **four** sessions (v56, v57, v58, v59). Worth surfacing to
  Paul directly next session rather than just carrying it quietly again.
- **Two Rivers:** fully confirmed live (from v57).
- **Port Washington:** 7th, bonus pier. All 5 template-parity files
  delivered in v58. Paul was mid-cleanup of leftover old boxes (a
  still-live Local Suggestions section, a stray default Carrd "Text"
  placeholder) at the end of v58 — **not yet confirmed fully live/clean.**
- **Kewaunee:** all 5 template-parity files delivered this session (v59).
  **Not yet confirmed live.** 3 old boxes still need deletion once
  confirmed: `pb-kw4-sky`, `pbkwsp`, `pb-kw-sug`.
- **Algoma:** all 5 template-parity files delivered this session (v59).
  **Not yet confirmed live.** 3 old boxes still need deletion once
  confirmed: `pb-alg4-sky`, `pbagsp`, `pb-alg-sug`.
- **Sturgeon Bay:** the last of the original six standard piers. Not yet
  started — no `.txt` dump received yet.

## Decisions Log

*(New entries this session — D432 onward.)*

- **D432 (Kewaunee template-parity applied, 4th pier):** Same 8-to-5
  mapping workflow as Manitowoc/Two Rivers/Port Washington. Sky+Lure,
  Species, and Suggestions retired per established precedent without
  re-asking; flagged in the delivery message per standing rule.
- **D433 (Kewaunee Photo Gallery built new):** Kewaunee never had a
  Photo Gallery box, same situation as Port Washington in v58. Built
  fresh from Sheboygan's `pbphsh` v3 pattern rather than treated as an
  error or a missing-file problem.
- **D434 (Algoma template-parity applied, 5th pier):** Same workflow.
  Two Algoma-specific differences from the standard pattern (below)
  were flagged to Paul in the plan before any files were written, per
  the standing rule for anything that isn't pure established precedent.
- **D435 (Algoma's shared wind station preserved, not corrected):**
  `HKEY="kww"` — Algoma's Pier B deliberately reads Kewaunee's own MET
  station, because Algoma's own wind station (AGMW3) has not reported
  since approximately 2017. This is a real pier-specific data-source
  fact carried over from the old file's own comment, not a template
  mismatch or a copy-paste error, so it was left exactly as-is rather
  than "fixed" to point at an Algoma-only station that doesn't actually
  report.
- **D436 (Algoma Photo Gallery restructured in place, not rebuilt
  fresh):** Unlike Kewaunee and Port Washington, Algoma already had a
  working Photo Gallery box (`pbphag`). It was brought to the
  collapsible pattern and recolored, keeping its existing box ID since
  that ID was already pier-specific and carried no collision risk.
- **D437 (dead code left over from a dropped section must be actively
  checked for, not just the HTML):** Algoma's first Pier B draft passed
  every D427 check but had only 223 bytes of margin — under the 300–500
  byte floor. Root cause was a dead `waterDescription()` function and
  five unused variables carried over from the old file's Temperature
  Break/attribution logic, which had already been dropped from the
  rendered output but not from the supporting JS. Standing rule added:
  when a template-parity rebuild drops a section (Temperature Break,
  Pier Access, bottom attribution), explicitly check for and remove any
  JS that only existed to feed that section — the visible-output check
  alone isn't sufic ient. A margin shortfall is now a specific trigger to
  check for this class of leftover code before trimming anything else.

## Reasoning Ledger

- **Why Algoma's shared wind station was preserved rather than treated
  as suspicious:** The old file's own comment already explained the
  mechanism in detail (Algoma's AGMW3 has been dead since ~2017,
  Kewaunee's MET station is the deliberate substitute) — this is
  documented pier-specific behavior, not an unexplained anomaly. Treating
  a documented, intentional cross-pier data dependency as an error to
  "fix" would have been worse than leaving it alone; the job here was
  template-structure parity, not re-litigating settled data-source
  decisions.
- **Why the dead-code bug was caught before delivery, not after:** The
  byte-margin check (part of D427) flagged the file as unusually tight
  compared to every other pier's rebuilt Pier B (all of which landed in
  the 750–1,250 byte range). That specific numeric outlier — not a
  vague "something feels off" — was the trigger to look deeper rather
  than accept the file as verified once JS syntax and brace-balance
  passed. Passing the mechanical checks (syntax, balance) is necessary
  but not sufficient; an unusually tight margin relative to sibling
  files is itself a data point worth investigating.
- **Why removing the dead code was the right fix, not shortening the
  comment:** The first attempt was to tighten the header comment's
  wording, which recovered only about 6 bytes — nowhere near enough,
  and it would have left the real problem (genuinely dead, unused code
  bloating the delivered file) in place. Comment-trimming is a
  cosmetic lever; the actual fix had to address why the file was larger
  than its Sheboygan-parity structure justified.
- **Why fixing the dead code also required fixing the comment:** The
  dead code's original purpose (feeding Temperature Break and the
  windAttrib display line) meant the comment describing "what was
  preserved" was itself wrong once that display line was gone — it had
  claimed the attribution wording was kept when only the underlying
  wind-station choice was kept, not its old display text. The two
  fixes were linked: removing the dead code made the stale comment
  claim visibly false, which is what caught it.

## Technical Details

- **Kewaunee file sizes (all under the 16,384-byte Carrd limit):**
  `kewaunee-pier-a-report.html` 11,265 bytes; `kewaunee-pier-b-report.html`
  15,135 bytes (1,249 bytes margin); `kewaunee-fish-cleaning-stations.html`
  3,605 bytes; `kewaunee-photo-gallery.html` 5,424 bytes;
  `kewaunee-submit-a-photo.html` 1,391 bytes.
- **Kewaunee-specific keys (preserved verbatim, do not re-derive):**
  Pier A — `KEY="kewaunee"`, `BUOY_KEY=null`. Pier B — `HKEY="kww"`,
  `ZKEY="kwz"`, `PKEY="kewaunee"`. Sky/Moon — `MLAT=44.4589`,
  `MLON=-87.5094`.
- **Algoma file sizes (all under the 16,384-byte Carrd limit):**
  `algoma-pier-a-report.html` 11,207 bytes; `algoma-pier-b-report.html`
  15,372 bytes (1,012 bytes margin, after the dead-code fix — was 223
  bytes before it); `algoma-fish-cleaning-stations.html` 3,657 bytes;
  `algoma-photo-gallery.html` 5,680 bytes; `algoma-submit-a-photo.html`
  1,291 bytes.
- **Algoma-specific keys (preserved verbatim, do not re-derive):**
  Pier A — `KEY="algoma"`, `BUOY_KEY=null`. Pier B — `HKEY="kww"`
  (shared with Kewaunee — deliberate, see D435), `ZKEY="algz"`,
  `PKEY="algoma"`. Sky/Moon — `MLAT=44.6086`, `MLON=-87.4350`.
- **Dead-code pattern to check for on every remaining pier (Sturgeon
  Bay) and worth a quick look on already-delivered piers:** a
  `waterDescription(h)`-style helper function plus `label`/`p`/`h`/
  `waterDesc`/`windName` variables that only existed to feed a
  Temperature Break section and/or a bottom attribution line. If the
  old pier's file has this pattern, it needs to be dropped along with
  the HTML it fed, not just the HTML.

## Design Decisions

- No new design-token decisions this session — Kewaunee and Algoma both
  use the same master palette and radius values established in
  D413/v55, applied without deviation.

## User Preferences

*(Additions this session — prior preferences preserved below.)*

- Confirmed again: Paul wants files checked and double-checked before
  delivery, not just built and handed over — explicit instruction this
  session ("make sure they work, check and double check before you
  give me a file"). The margin-outlier catch on Algoma's Pier B is a
  concrete example of what that verification should look like in
  practice: not just running the checklist, but treating an unusual
  result (223 bytes margin vs. every sibling pier's 750–1,250) as
  something to investigate rather than accept.

## Constraints

Unchanged from v58, plus:
- When a template-parity rebuild drops a section (Temperature Break,
  Pier Access, bottom attribution) from Pier B, explicitly check for and
  remove the JS that only fed that section — not just the HTML output
  (D437).
- `pbagb` (Algoma Pier B) is now at 15,372 bytes, 1,012 bytes margin —
  tight, same caution level as every other pier's rebuilt Pier B.

## Risks

- **Manitowoc still not confirmed live, four sessions running.** Worth
  raising directly with Paul next session rather than continuing to
  carry it silently.
- **Port Washington not yet confirmed fully live/clean** — Paul was
  mid-cleanup of leftover old boxes at the end of v58.
- **Kewaunee's 3 retired boxes** (`pb-kw4-sky`, `pbkwsp`, `pb-kw-sug`)
  and **Algoma's 3 retired boxes** (`pb-alg4-sky`, `pbagsp`,
  `pb-alg-sug`) still need explicit deletion from Carrd once each
  pier's new files are confirmed working.
- **Kewaunee's `pbkwb` margin is 1,249 bytes; Algoma's `pbagb` margin is
  1,012 bytes** — both tight, flag before adding anything to either.
- **Worth a quick look on Manitowoc/Two Rivers/Port Washington's
  already-delivered Pier B files** for the same dead-code pattern found
  on Algoma (D437) — not confirmed present, but not yet checked either,
  since the pattern wasn't known to look for until this session.
- All risks carried from v58 remain open (see preserved section below):
  Two Rivers' 3 retired old boxes not yet confirmed deleted, Sheboygan
  `pbsap-sheboygan` v6 not yet independently reconfirmed, generic-ID
  collision risk on Sturgeon Bay (not yet rebuilt), buoywatchA margin,
  St. Joseph MI probe pending, Compare Piers NOAA attribution gap.

## Open Questions

- **Are Kewaunee's and Algoma's new files confirmed live and correct?**
  Neither has been confirmed yet — check first next session.
- **Were Kewaunee's and Algoma's retired old boxes deleted** from Carrd
  once confirmed? Confirm next session.
- Carried from v58: **is Port Washington fully clean and confirmed
  live?** Paul was mid-cleanup at the end of that session.
- Carried from v57/v58: **did Paul ever explicitly delete Two Rivers'
  3 retired old boxes** (`pb-tr4-sky`, `pbtrsp`, `pb-tr-sug`)? Still
  unconfirmed across three sessions now.
- **Does Paul want to move to Sturgeon Bay next** (the last of the
  original six standard piers), or confirm/clean up the four
  already-delivered template-parity piers (Manitowoc, Port Washington,
  Kewaunee, Algoma) first?
- Carried from v54/v55/v56: standalone `lure-pbsheb1sky` box on
  Sheboygan — confirm with Paul whether to delete it.

## Future Ideas

Unchanged from v56 (see preserved section below) — one global species
temperature slider, HOT PIER TODAY card, lazy-loading per pier, St.
Joseph MI as first east-shore pier.

## Next Session Instructions

**Exact prompt for Paul to paste into a new chat:**

> Continuing PIERBITE. Read Memory_PIERBITE_PROJECT_MEMORY_2026-09-11_v59.md
> in full before doing anything — this is the current file, it replaces v58.
> Tell me what you understand the current state to be. Confirm model identity.
>
> Current state: Kewaunee and Algoma were both brought to full
> template-parity this session — 5 files each delivered (Pier A, Pier B,
> Fish Cleaning, Photo Gallery, Submit a Photo). Neither pier's new files
> are confirmed live yet. Algoma's Pier B deliberately shares its wind
> station with Kewaunee (`HKEY="kww"`) because Algoma's own wind station
> has been dead since ~2017 — this is intentional, not a bug, do not
> "fix" it. Four piers now have delivered-but-unconfirmed template-parity
> files: Manitowoc (open across four sessions now — ask Paul directly),
> Port Washington (mid-cleanup of old boxes as of v58), Kewaunee, and
> Algoma. Two Rivers and Sheboygan are the only fully confirmed piers.
> Sturgeon Bay is the last of the original six standard piers and has not
> been started.
>
> Early in this session: (1) ask Paul directly whether Manitowoc is live
> yet — this has been carried open the longest, (2) check whether
> Kewaunee's and Algoma's new files are confirmed live, and if so whether
> their retired old boxes (Kewaunee: pb-kw4-sky/pbkwsp/pb-kw-sug; Algoma:
> pb-alg4-sky/pbagsp/pb-alg-sug) have been deleted, (3) check on Port
> Washington's cleanup status, (4) confirm whether Two Rivers' 3 retired
> boxes were ever deleted (open across three sessions).
>
> If Paul wants to continue the pier rebuild queue, the only pier left is
> Sturgeon Bay — confirm before starting.
>
> This is a TEMPLATE-PARITY session if Paul brings Sturgeon Bay's code,
> same workflow as every prior pier. 5 boxes: Pier A, Pier B (Sky/Moon/
> Forecast merged into one collapsible), Fish Cleaning Stations
> (collapsible), Photo Gallery (collapsible), Submit a Photo.
>
> I will paste in Sturgeon Bay's full current code as a .txt dump. Map
> every box against Sheboygan's 5. Anything without a Sheboygan
> counterpart — flag it and ask what to do with it BEFORE writing any
> files, unless it's already established precedent (dropping a hidden
> Lure Call panel, retiring Species/Suggestions boxes, a shared/borrowed
> wind station like Algoma's) — established precedent can just be applied
> and flagged in the delivery message rather than re-asked.
>
> Once scope is confirmed: rebuild the 5 template boxes using Sturgeon
> Bay's own data — its own station keys, coordinates, buoy IDs, local
> business info — never Sheboygan's. Preserve any pier-specific bug fixes
> or deliberate data-source choices found in the old code (station-label
> trimming, double-attribution fixes, a borrowed wind station, etc.)
> rather than overwriting them with Sheboygan's script or "fixing" them
> without asking. Recolor everything to the master palette (panel
> #112a3f, border #1f405b, muted text #a3bcd1, faint text #8aa2b6, link
> blue #5fb6f0, card radius 16px, toggle radius 12px). If Sturgeon Bay's
> Submit a Photo box still uses the generic "pbsap" ID, rename it to
> pbsap-sturgeonbay; if a Photo Gallery box already exists, restructure
> it in place rather than rebuilding fresh (same as Algoma this
> session); if it doesn't exist yet, build it fresh with a pier-specific
> ID from the start (same as Kewaunee/Port Washington).
>
> Before delivering ANY files (first delivery or a redelivery), run the
> verification checklist from D427: node --check on each script block,
> CSS brace-count balance, HTML div tag-balance count, byte size vs.
> 16,384 with margin stated. If a rebuilt Pier B's margin comes out
> noticeably tighter than the 750-1,250 byte range every other pier's
> rebuilt Pier B has landed in, check specifically for leftover dead
> code from dropped sections (Temperature Break, Pier Access, bottom
> attribution) before assuming the file is simply larger (D437) — this
> caught a real bug on Algoma this session.
>
> Standing rules: full replacement files only, never snippets. Filenames
> must be full plain-English names, box ID stated in the delivery
> message and the internal HTML comment. Verify every file is safely
> under Carrd's 16,384-byte limit before delivering. Name any retired
> old box explicitly so I know to delete it from Carrd. One pier at a
> time, confirm live before moving to the next.

**Reminder for Paul:** after uploading this file, delete
`Memory_PIERBITE_PROJECT_MEMORY_2026-09-11_v58.md` from Project Files.

---

# === EVERYTHING BELOW THIS LINE IS PRESERVED UNCHANGED FROM v58 ===

<!-- PIERBITE PROJECT MEMORY | 2026-09-11 | v58 | Session covered two things: (1) fixed a Two Rivers navigation bug - the pier section's Carrd Element ID was actually "#two-rivers" (hyphenated), not "#tworivers" as every prior memory entry assumed by pattern; Paul found and fixed it himself in Carrd's Settings panel. (2) Full template-parity rebuild of Port Washington - the third pier brought to Sheboygan-template parity after Manitowoc (v56) and Two Rivers (v57). Port Washington had never had a Photo Gallery or Submit a Photo box at all, so those two were built brand new rather than reformatted; Submit a Photo was given its collision-safe ID (pbsap-portwashington) from birth. Old Sky+Lure Call box retired (same hidden-lure-panel pattern as Manitowoc/Two Rivers), Species and Suggestions boxes retired (no Sheboygan counterpart), and the standalone Beach Hazard box (pb-pw-bhz) retired after Paul confirmed its info is already duplicated inside the rebuilt Pier A's own built-in hazard alert. Pier A and Pier B's pier-specific bug fixes (station-label trimming, LMHOFS double-attribution fix, no-BUOY_KEY waveSub fix) were preserved verbatim rather than overwritten by Sheboygan's script. All 5 files passed the D427 verification checklist and were delivered. Paul initially reported the live page looked like "a mess" after pasting; root cause was self-diagnosed by Paul as leftover old boxes (a still-live Local Suggestions section plus a stray default Carrd "Text" placeholder box) that he had simply forgotten to delete - not a problem with the delivered files. Paul is mid-cleanup; full Port Washington confirmation is not yet in hand. Supersedes v57 - delete Memory_PIERBITE_PROJECT_MEMORY_2026-09-11_v57.md from Project Files and upload this one. -->

# PIERBITE PROJECT MEMORY - 2026-09-11 v58

**THIS IS THE CURRENT REVISION. It supersedes v57.**
Nothing deleted — additive by design. Everything below this v58 section is
preserved byte-for-byte from v57.

## Project Overview

PierBite.com — six (possibly seven — see below, this session moves Port
Washington a long way toward "yes") Wisconsin Lake Michigan pier
fishing-conditions pages, all rendered as **one single long Carrd page**
with piers reached via anchor links (`#sheboygan`, `#manitowoc`,
`#two-rivers`, `#port-washington` presumed, etc.) rather than separate
pages. Paul is non-technical and relies entirely on Claude for all code.
Carrd Pro Plus frontend + Python/GitHub Actions backend.

## Two Rivers Navigation Bug (NEW — 2026-09-11, v58)

Paul reported the Two Rivers nav link stopped working after the v57
box-deletion/recreation work. Investigated and fixed same session.

**Root cause:** Every prior memory entry (D402 and its examples) assumed
pier anchor IDs follow a plain, no-hyphen pattern — `#tworivers`, like
`#sheboygan`, `#manitowoc`. The actual Element ID set on Two Rivers'
section container in Carrd was `#two-rivers` (hyphenated). This was
never actually verified against the live Carrd settings before now — it
had just been assumed by extrapolating from the other piers' anchors.

**Fix:** Paul opened the Two Rivers section's Settings panel in Carrd,
found the real Element ID, corrected the nav link to match, confirmed
working.

**Standing lesson (D431):** Don't assume a new or unfamiliar pier's
anchor ID follows the same naming convention as piers already
confirmed. Check the actual Element ID field in Carrd's Settings panel
for that specific section before troubleshooting further — this is the
same underlying mechanism as D402 (anchor links work via the Element ID
field on the container, not via code or container *names*), just a
reminder that pattern-matching from other piers isn't a substitute for
checking the one in question.

## Port Washington Template-Parity Rebuild (NEW — 2026-09-11, v58)

Third full application of the template-parity workflow (D418), after
Manitowoc (v56) and Two Rivers (v57). Paul supplied the old Port
Washington `.txt` dump and the Sheboygan template as the two working
files for this session.

### What Port Washington had before this session:

A standalone Beach Hazard box (`pb-pw-bhz`), Pier A (`pbpwa`), Pier B
(`pbpwb`), a combined Sky+Lure box (`pb-pw4-sky`), a Species box
(`pbpwsp`), a Suggestions box (`pb-pw-sug`), and a Fish Cleaning box
(`pb-pw-clean`). **Port Washington had no Photo Gallery box and no
Submit a Photo box at all** — unlike every other pier, these were never
built for this pier. Paul confirmed this directly rather than Claude
guessing from an incomplete-looking file.

### Port Washington box mapping (this session's worked example):

| Old Port Washington box | Old ID | Outcome |
|---|---|---|
| Beach Hazard (standalone) | `pb-pw-bhz` | **Retired** — Paul confirmed this box's info is already duplicated: the rebuilt Pier A already renders a beach-hazard alert internally (the same `.al.hz` treatment every pier's Pier A box has), making the separate box redundant |
| Pier A | `pbpwa` | Kept, rebuilt — DNR banner and its now-unused `.dnr` CSS rule removed (matches pbsha v9); Port Washington's own `stationName()` label-trim fix, `lmhofsLabel()` double-attribution fix, and no-`BUOY_KEY` `waveSub()` fix all preserved (pier-specific correctness fixes, not template structure) |
| Pier B | `pbpwb` | Kept, restructured — Sky/Moon merged into collapsible w/ forecast, using Port Washington's own coordinates (43.38527/-87.85965) and station keys (`HKEY="pww"`, `ZKEY="LMZ644"`, `PKEY="port_washington"`); direction-weights key table (`.dkey`), Temperature Break, Pier Access, the in-card "Measured at [station]" attribution line, and the bottom data-attribution line all dropped, matching pbshb v8. Port Washington's own verbatim `UPWELLING_COMPONENT` table preserved unchanged |
| Sky + Lure Call | `pb-pw4-sky` | **Retired** — same hidden "Today's Lure Call" panel pattern already found inside Manitowoc's and Two Rivers' old Sky boxes (D419/D424). Third occurrence confirms this is a systemic pattern in every pre-rebuild pier's old Sky/Lure box, not a one-off |
| Species | `pbpwsp` | **Retired** — no Sheboygan counterpart |
| Suggestions | `pb-pw-sug` | **Retired** — no Sheboygan counterpart |
| Fish Cleaning | `pb-pw-clean` | Kept, restructured — always-open panel converted to collapsible toggle, recolored to master palette, radius 14px→16px |
| Photo Gallery | *(did not exist)* | **Built new**, box `pbphpw` — no prior version to reformat; built fresh from Sheboygan's `pbphsh` v3 pattern with Port Washington's own pier key/name |
| Submit a Photo | *(did not exist)* | **Built new**, box `pbsap-portwashington` — no prior version to reformat; given the collision-safe per-pier ID from birth (same fix already retrofitted onto Sheboygan/Manitowoc/Two Rivers via D417), so this box never passes through the generic `pbsap` collision bug at all |

### Files delivered this session:

- `port-washington-pier-a-report.html` → box `pbpwa` — 11,531 bytes
- `port-washington-pier-b-report.html` → box `pbpwb` — 15,150 bytes,
  **only 1,234 bytes margin — tight, flag before adding anything to
  this box**
- `port-washington-fish-cleaning-stations.html` → box `pb-pw-clean` —
  3,450 bytes
- `port-washington-photo-gallery.html` → **new** box, ID it `pbphpw` —
  5,487 bytes
- `port-washington-submit-a-photo.html` → **new** box, ID it
  `pbsap-portwashington` — 1,445 bytes

All 5 passed the D427 pre-delivery verification checklist (`node
--check` on every script block, CSS brace-count balance, HTML
div-tag-balance count, byte size vs. 16,384) before being delivered.

**Not yet independently confirmed live by Paul.** Paul pasted the files
and reported the page looked like "a mess" — see below.

## "Mess" report — self-diagnosed, not a code bug

After pasting, Paul reported the live page looked wrong (screenshot
showed a stray Local Suggestions section and a floating, unstyled
"Text" element between boxes). Before Claude could investigate, **Paul
found the cause himself**: he had simply forgotten to delete the old
boxes (the live page still had the old Local Suggestions section
showing, plus a default empty Carrd "Text" placeholder box left over
from earlier page-building). Confirmed by Paul as "my fault," not a
defect in the delivered files.

**Standing lesson (reinforces existing pattern, not a new mechanism):**
old boxes do not disappear on their own — every template-parity rebuild
leaves the *old*, now-retired boxes still live on the page until
explicitly deleted, and a still-live old box (or a stray default
placeholder) can make a correctly-delivered rebuild look broken even
though nothing about the new code is wrong. Worth checking for leftover
un-deleted boxes and default Carrd placeholders as a first, cheap step
whenever a freshly-delivered rebuild "looks like a mess" — before
assuming the new code has a bug.

## Current Status

- **Two Rivers:** fully confirmed live from v57, nav bug found and
  fixed this session (`#two-rivers`, not `#tworivers`). Confirmed
  working.
- **Port Washington:** all 5 template-parity files delivered and
  passed verification this session. Paul is mid-cleanup of old boxes
  (Local Suggestions section + a stray "Text" placeholder found and
  being removed). **Not yet confirmed fully live/clean.**
- **Manitowoc:** unchanged from v56/v57 — 5 files delivered, still not
  confirmed live by Paul (carried open across three sessions now).
- **Sheboygan:** still the master template, effectively locked.
- **Port Washington's "is it an officially supported 7th pier"
  question:** for practical purposes, resolved this session — Paul
  had Claude apply the full template-parity treatment to it, same as
  any of the standing six piers. Not a single stated Paul confirmation
  of "yes it's official," but the working assumption going forward is
  that Port Washington is being treated as a real, permanent pier.

## Decisions Log

*(New entries this session — D428 onward.)*

- **D428 (Port Washington beach hazard box retired):** The standalone
  `pb-pw-bhz` box was retired. Paul confirmed directly that its
  information is already shown elsewhere — inside the rebuilt Pier A's
  own built-in beach-hazard alert (the `.al.hz` treatment already
  present in every pier's Pier A box, driven by `p.beach_hazard.active`
  from the same data feed `pb-pw-bhz` was separately fetching). No
  functionality lost, one fewer moving part on the page.
- **D429 (Photo Gallery / Submit a Photo built new, not reformatted):**
  Port Washington never had these two boxes. Rather than treating this
  as an error to fix retroactively, both were built fresh directly from
  the Sheboygan master pattern with Port Washington's own pier key/name
  substituted in. Submit a Photo's ID was set to the final,
  collision-safe form (`pbsap-portwashington`) immediately — it never
  existed as a generic `pbsap` box, so it skips the collision-bug
  lifecycle every other pier's Submit a Photo box went through.
- **D430 (Port Washington's own pier-specific fixes preserved, not
  overwritten):** Same principle already established for Manitowoc and
  Two Rivers (v56 Reasoning Ledger): Port Washington's `stationName()`
  label-trim fix, `lmhofsLabel()`/`lmhofsNode()` double-attribution
  fixes, and the no-`BUOY_KEY` `waveSub()` fix are pier-specific
  correctness fixes, not template structure. Copying Sheboygan's script
  wholesale over Port Washington's would have reintroduced bugs Port
  Washington had already fixed. Only HTML/CSS structure and box IDs
  were brought to parity.
- **D431 (verify anchor IDs directly, don't pattern-match from other
  piers):** Two Rivers' real anchor Element ID turned out to be
  `#two-rivers` (hyphenated), not `#tworivers` as every prior memory
  entry had assumed by extrapolating from `#sheboygan`/`#manitowoc`.
  Standing lesson: when troubleshooting a pier's nav link, check that
  specific pier's actual Element ID in Carrd's Settings panel rather
  than assuming it follows the same convention as piers already
  confirmed. This doesn't change the underlying mechanism from D402 —
  anchor links still work via the container's Element ID field, not
  code or container names — it's a reminder not to skip verifying it.

## Reasoning Ledger

- **Why the Beach Hazard box was safe to retire without a live-data
  cross-check:** Paul's own confirmation that the information is
  already duplicated was treated as sufficient — this is the kind of
  direct, unambiguous statement about the box's own content that
  D405 already establishes should be taken as authoritative over
  Claude's independent guesswork.
- **Why Photo Gallery and Submit a Photo were treated as new-build
  tasks instead of "missing file" errors:** Nothing in the uploaded
  `.txt` dump was corrupted or incomplete — Paul confirmed directly
  that Port Washington genuinely never had these two boxes built.
  Treating it as a build task (using the Sheboygan pattern as the
  starting point, same as every other box in this rebuild) was more
  accurate than treating it as recovering lost content, and avoided
  wasting a round-trip asking Paul to "find an old copy" that doesn't
  exist for these two boxes.
- **Why the reported "mess" was investigated by asking for evidence
  first, not by guessing at a code cause:** Given three sessions of
  established precedent that code passed D427 verification before
  delivery, the more likely explanation for a "looks wrong" report
  immediately after a multi-box rebuild was leftover old boxes still
  live on the page (exactly this happened with Two Rivers' Photo
  Gallery duplicate-ID bug in v57) — asking to see it, rather than
  jumping to "let me recheck the code," let Paul catch it himself
  faster than a code review would have.

## Technical Details

- **Port Washington file sizes (all under the 16,384-byte Carrd
  limit):** `port-washington-pier-a-report.html` 11,531 bytes;
  `port-washington-pier-b-report.html` 15,150 bytes (1,234 bytes
  margin — tight, same caution level as Manitowoc's `pbmtb` and Two
  Rivers' `pbtrb`: do not add content without splitting first);
  `port-washington-fish-cleaning-stations.html` 3,450 bytes;
  `port-washington-photo-gallery.html` 5,487 bytes;
  `port-washington-submit-a-photo.html` 1,445 bytes.
- **Port Washington-specific station/zone keys (preserved verbatim,
  do not re-derive):** Pier A — `KEY="port_washington"` (no
  `BUOY_KEY` — deliberately deleted per Port Washington's own
  pre-existing fix, `waveSub()` reads `h.wave_station_label` directly
  instead). Pier B — `HKEY="pww"`, `ZKEY="LMZ644"`,
  `PKEY="port_washington"`. Sky/Moon — `MLAT=43.38527`,
  `MLON=-87.85965` (same coordinates as the old Lure box used, now the
  single source for sun/moon calculations on this pier).
- **Port Washington collapsible button ID pattern (pier-specific per
  D423):** `pbpwbFcTog`/`pbpwbFcWrap`/`pbpwbFcArr` (Pier B forecast
  toggle), `pbpwCleanTog`/`pbpwCleanWrap`/`pbpwCleanArr` (Fish
  Cleaning), `pbphpwTog`/`pbphpwWrap`/`pbphpwArr` (Photo Gallery, new).
- **Two Rivers confirmed anchor ID:** `#two-rivers` (hyphenated) is the
  real, working Element ID on the Two Rivers section container in
  Carrd. Corrected there this session.

## Design Decisions

- No new design-token decisions this session — Port Washington uses
  the same master palette and radius values established in D413/v55,
  applied without deviation. Port Washington's Pier A style block was
  already on-palette before this session (same finding as Manitowoc's
  Pier A in v56) — no recolor was needed there, only the DNR banner
  removal.

## User Preferences

*(Additions this session — prior preferences preserved below.)*

- Confirmed again: Paul wants to be told plainly and specifically what
  a problem turned out to be (e.g. "the anchor was `#two-rivers` not
  `#tworivers`") rather than a vague summary — this matters for what
  gets logged in memory so the specific fact is preserved, not just
  the fact that "a bug was fixed."
- When Paul reports something looks broken right after a delivery, he
  will sometimes diagnose and fix it himself before Claude gets a
  chance to investigate — memory should still capture the root cause
  precisely once he reports it, the same as if Claude had found it.

## Constraints

Unchanged from v57, plus:
- `pbpwb` (Port Washington Pier B) is now at 15,150 bytes, 1,234 bytes
  margin — treat as tight, same caution level as Manitowoc's `pbmtb`
  and Two Rivers' `pbtrb`.
- Do not assume a pier's anchor Element ID follows another pier's
  naming pattern — verify directly in Carrd's Settings panel before
  troubleshooting a nav-link issue further (D431).

## Risks

- **Port Washington is not yet confirmed fully live/clean.** Paul is
  mid-cleanup of old boxes (Local Suggestions section, a stray "Text"
  placeholder). Until confirmed, treat Port Washington's rebuild as
  delivered-but-unverified, not done.
- **Port Washington's 3 retired boxes** (`pb-pw4-sky`, `pbpwsp`,
  `pb-pw-sug`) and the old `pb-pw-bhz` (if any leftover copy exists)
  still need explicit deletion from Carrd once the new files are
  confirmed working.
- **Port Washington's `pbpwb` margin is 1,234 bytes** — tight, flag
  before adding anything.
- **Recommended but not yet confirmed done:** a Ctrl+F duplicate-ID
  check on Port Washington's new `pbphpw` and `pbsap-portwashington`
  IDs, the same diagnostic that caught Two Rivers' Photo Gallery
  duplicate-ID bug in v57. Worth doing given Port Washington's page
  history includes at least one confirmed stray/cloned box already
  (the Two Rivers Photo Gallery duplicate found living under Port
  Washington in v57).
- All risks carried from v57 remain open (see preserved section
  below): Manitowoc's `pbmtb` margin and still-unconfirmed-live status,
  Sheboygan `pbsap-sheboygan` v6 not yet independently reconfirmed,
  generic-ID collision risk on any not-yet-rebuilt pier (Kewaunee,
  Algoma, Sturgeon Bay), buoywatchA margin, St. Joseph MI probe
  pending, Compare Piers NOAA attribution gap, Two Rivers' 3 retired
  old boxes (`pb-tr4-sky`, `pbtrsp`, `pb-tr-sug`) not yet confirmed
  deleted.

## Open Questions

- **Is Port Washington fully clean and confirmed live?** Paul is
  mid-cleanup as of end of this session — confirm next session.
- **Were Port Washington's 3 retired boxes deleted** (`pb-pw4-sky`,
  `pbpwsp`, `pb-pw-sug`), and was any leftover `pb-pw-bhz` copy found
  and removed? Confirm next session.
- Carried from v57: **did Paul ever explicitly delete Two Rivers' 3
  retired old boxes** (`pb-tr4-sky`, `pbtrsp`, `pb-tr-sug`)? Still
  unconfirmed.
- Carried from v57/v56: which pier does Paul want to do next —
  Kewaunee, Algoma, or Sturgeon Bay? (Port Washington was done this
  session as an out-of-order addition, not one of these three.)
- Carried from v54/v55/v56: standalone `lure-pbsheb1sky` box on
  Sheboygan — confirm with Paul whether to delete it now that `pbshb`
  v8 already contains Sky/Moon in its own collapsible.
- Carried from v56: does every pier currently have its own Submit a
  Photo box already pasted into Carrd, or only some piers so far?
  (Now true for Sheboygan, Manitowoc, Two Rivers, and — pending
  confirmation — Port Washington.)

## Future Ideas

Unchanged from v56 (see preserved section below) — one global species
temperature slider, HOT PIER TODAY card, lazy-loading per pier, St.
Joseph MI as first east-shore pier.

## Next Session Instructions

**Exact prompt for Paul to paste into a new chat:**

> Continuing PIERBITE. Read Memory_PIERBITE_PROJECT_MEMORY_2026-09-11_v58.md
> in full before doing anything — this is the current file, it replaces v57.
> Tell me what you understand the current state to be. Confirm model identity.
>
> Current state: Two Rivers' nav bug is fixed and confirmed working
> (`#two-rivers`, not `#tworivers` — check the real Carrd Element ID for
> any pier's anchor before assuming it matches another pier's pattern).
> Port Washington was brought to full template-parity this session — 5
> files delivered (Pier A, Pier B, Fish Cleaning, plus brand-new Photo
> Gallery and Submit a Photo boxes that didn't exist before). Port
> Washington's standalone Beach Hazard box was retired — its info is now
> shown via Pier A's own built-in hazard alert. Port Washington is
> **not yet confirmed fully live** — Paul was mid-cleanup of leftover old
> boxes (a still-live Local Suggestions section and a stray default
> Carrd "Text" placeholder) at the end of the last session. Check with
> Paul on that status first if it hasn't come up. Manitowoc's 5 files
> are still not confirmed live either (carried open across three
> sessions now) — check on that too.
>
> Two open items to resolve early in this session if possible: (1)
> confirm Port Washington's 3 retired boxes (pb-pw4-sky, pbpwsp,
> pb-pw-sug) and any leftover pb-pw-bhz copy have been deleted from
> Carrd, and (2) confirm whether Two Rivers' 3 retired boxes
> (pb-tr4-sky, pbtrsp, pb-tr-sug) were ever deleted — this has now been
> carried open across two sessions.
>
> If Paul wants to continue the pier rebuild queue, the standing choices
> are Kewaunee, Algoma, or Sturgeon Bay — confirm which.
>
> This is a TEMPLATE-PARITY session if Paul brings another pier, same
> workflow as Manitowoc/Two Rivers/Port Washington. 5 boxes: Pier A,
> Pier B (Sky/Moon/Forecast merged into one collapsible), Fish Cleaning
> Stations (collapsible), Photo Gallery (collapsible), Submit a Photo.
>
> I will paste in the next pier's full current code as a .txt dump (or,
> if a box like Photo Gallery/Submit a Photo doesn't exist yet the way
> Port Washington's didn't, tell me and I'll build it fresh from the
> Sheboygan pattern rather than expect it in the dump). Map every box
> against Sheboygan's 5 boxes. Anything without a Sheboygan counterpart
> (Species, Suggestions, old-style Lure/Sky boxes, a standalone Beach
> Hazard box like Port Washington had) — flag it and ask what to do with
> it BEFORE writing any files, unless it's already established
> precedent (dropping a hidden Lure Call panel, retiring a standalone
> Beach Hazard box once its info is confirmed duplicated elsewhere) —
> established precedent can just be applied and flagged in the delivery
> message rather than re-asked.
>
> Once scope is confirmed: rebuild the 5 template boxes using THIS
> pier's own data — its own station keys, coordinates, buoy IDs, local
> business info — never Sheboygan's. Preserve any pier-specific bug
> fixes found in the old code (station-label trimming, double-
> attribution fixes, etc.) rather than overwriting them with Sheboygan's
> script. Recolor everything to the master palette (panel #112a3f,
> border #1f405b, muted text #a3bcd1, faint text #8aa2b6, link blue
> #5fb6f0, card radius 16px, toggle radius 12px). If this pier's Submit
> a Photo box still uses the generic "pbsap" ID, rename it to
> pbsap-[piername]; if it doesn't exist yet, build it with that ID from
> the start.
>
> Before delivering ANY files (first delivery or a redelivery), run the
> verification checklist from D427: node --check on each script block,
> CSS brace-count balance, HTML div tag-balance count, byte size vs.
> 16,384 with margin stated.
>
> Before assuming a freshly-delivered rebuild has a code problem because
> the live page "looks like a mess," check for leftover un-deleted old
> boxes and stray default Carrd placeholders first — this has now
> explained two separate "looks broken" reports (Two Rivers' duplicate
> Photo Gallery box in v57, Port Washington's un-deleted Suggestions
> section and stray Text box in v58).
>
> When troubleshooting any pier's nav link, verify that pier's actual
> Element ID directly in Carrd's Settings panel — do not assume it
> follows the same naming convention as another pier's confirmed anchor
> (Two Rivers turned out to be `#two-rivers`, not the assumed
> `#tworivers`).
>
> Standing rules: full replacement files only, never snippets. Filenames
> must be full plain-English names, box ID stated in the delivery
> message and the internal HTML comment. Verify every file is safely
> under Carrd's 16,384-byte limit before delivering. Name any retired
> old box explicitly so I know to delete it from Carrd. One pier at a
> time, confirm live before moving to the next.

**Reminder for Paul:** after uploading this file, delete
`Memory_PIERBITE_PROJECT_MEMORY_2026-09-11_v57.md` from Project Files.

---

# === EVERYTHING BELOW THIS LINE IS PRESERVED UNCHANGED FROM v57 ===

<!-- PIERBITE PROJECT MEMORY | 2026-09-11 | v57 | Two Rivers template-parity session: rebuilt all 5 boxes to match Sheboygan (Pier A, Pier B w/ merged Sky/Moon/Forecast collapsible, Fish Cleaning, Photo Gallery, Submit a Photo). Two Rivers' old Sky box again hid a full Lure Call panel behind the Sky/Moon name (same pattern as Manitowoc) - dropped per established precedent. Hit and resolved TWO separate real bugs this session: (1) Two Rivers' Photo Gallery wouldn't collapse - root-caused to a leftover/duplicate Code Embed box with the same element ID (pbphtr) sitting under the Port Washington section of the page, left over from whenever Port Washington was built (apparently cloned from Two Rivers' boxes without being fully cleaned out) - fixed by Paul deleting the stray Port Washington copy. (2) Large visual gaps between Two Rivers' collapsible box buttons that didn't exist on Sheboygan/Manitowoc - extensive troubleshooting (Carrd box ID/Classes/Attributes, Style=Inline, Row spacing, Section background settings) found the code and every visible Carrd setting identical between Two Rivers and Sheboygan, so no single setting was ever identified - fixed by deleting the affected Two Rivers boxes entirely and recreating them as brand-new Embed boxes with the same code pasted in. This is now a standing troubleshooting technique (D428... actually logged as D426 below). Two Rivers is now the SECOND pier (after the Sheboygan template itself) confirmed fully live and matching master. Manitowoc's 5 files remain undelivered-to-confirmation from v56 (unchanged this session). Supersedes v56 - delete Memory_PIERBITE_PROJECT_MEMORY_2026-09-11_v56.md from Project Files and upload this one. -->

# PIERBITE PROJECT MEMORY - 2026-09-11 v57

**THIS IS THE CURRENT REVISION. It supersedes v56.**
Nothing deleted — additive by design. Everything below this v57 section is
preserved byte-for-byte from v56.

## Project Overview

PierBite.com — six (possibly seven, see Open Questions) Wisconsin Lake
Michigan pier fishing-conditions pages, all rendered as **one single long
Carrd page** with piers reached via anchor links (`#sheboygan`,
`#manitowoc`, `#tworivers`, etc.) rather than separate pages. Paul is
non-technical and relies entirely on Claude for all code. Carrd Pro Plus
frontend + Python/GitHub Actions backend.

## Two Rivers Template-Parity Rebuild (NEW — 2026-09-11, v57)

Second full application of the template-parity workflow established in
v56 (D418). Two Rivers' 5 boxes rebuilt to match Sheboygan's structure,
using Two Rivers' own data throughout.

### Two Rivers box mapping (this session's worked example):

| Old Two Rivers box | Old ID | Outcome |
|---|---|---|
| Pier A | `pbtra` | Kept — DNR banner removed (matches pbsha v9); TR's own `stationName()` label sanitizer and `waveSub()` open-lake dedup fix preserved (pier-specific data fixes, not template structure) |
| Pier B | `pbtrb` | Kept, restructured — Sky/Moon merged into collapsible w/ forecast, using TR's own coordinates (44.1499/-87.5698) and station keys (`HKEY="trw"`, `ZKEY="trz"`, `PKEY="two_rivers"`); Temp Break, direction-weights table, Pier Access, bottom attribution all dropped, matching pbshb v8 |
| Sky + Lure Call | `pb-tr4-sky` | **Retired** — same as Manitowoc, this box's name suggested pure Sky/Moon data but it also contained a full "Today's Lure Call" recommendation panel (species/wind color logic). Dropped entirely per the same precedent Paul set for Manitowoc (D419) — this happening a second time confirms it's a systemic pattern in the old Sky/Lure-style boxes, not a one-off |
| Species | `pbtrsp` | **Retired** — no Sheboygan counterpart |
| Suggestions | `pb-tr-sug` | **Retired** — no Sheboygan counterpart |
| Fish Cleaning | `pb-tr-clean` | Kept, restructured — always-open panel converted to collapsible toggle, recolored to master palette (was using non-master navy/text colors), radius 14px→16px |
| Submit a Photo | `pbsap` | Kept, **renamed** to `pbsap-tworivers` — same generic-ID collision fix as Sheboygan/Manitowoc (D417/D421-equivalent), recolored to master palette, radius 10px→16px |
| Photo Gallery | `pbphtr` | Kept, restructured — always-open converted to collapsible + lazy-loaded, same pattern as Sheboygan's `pbphsh` |

### Files delivered this session (re-delivered a second time, unchanged, after Paul deleted and recreated the boxes — see D426):

- `two-rivers-pier-a-report.html` → box `pbtra` — 11,546 bytes
- `two-rivers-pier-b-report.html` → box `pbtrb` — 15,442 bytes, **only
  942 bytes margin — tight, flag before adding anything to this box**
- `two-rivers-fish-cleaning-stations.html` → box `pb-tr-clean` — 3,985 bytes
- `two-rivers-photo-gallery.html` → box `pbphtr` — 5,447 bytes
- `two-rivers-submit-a-photo.html` → box `pbsap-tworivers` (renamed
  from `pbsap`) — 1,467 bytes

**All 5 are now confirmed live and working correctly by Paul**, including
correct collapse/expand behavior and spacing matching the Sheboygan master.

## Bug #1 this session: Photo Gallery wouldn't collapse (RESOLVED)

Two Rivers' Photo Gallery box showed its full content immediately with no
toggle button at all, even though the pasted code was verified byte-for-byte
identical to the delivered file (confirmed by having Paul paste the box's
actual contents back for direct comparison — this ruled out leftover/mixed
code as the cause).

**Root cause, confirmed by direct evidence, not guessed:** Paul searched the
live page's rendered source code for `id="pbphtr"` and found **2 matches**
instead of 1. A second, leftover copy of the old (pre-template-parity,
always-open) Two Rivers Photo Gallery box was sitting under the **Port
Washington** section of the page — almost certainly left over from whenever
Port Washington's page was built, likely cloned from Two Rivers' boxes
without being fully cleaned out afterward. Because both copies shared the
same element ID, the browser's `document.getElementById("pbphtr")` calls (and
possibly which style block won) got confused between the two, and the
Two Rivers' new toggle-based code never actually took effect visually.

**Fix:** Paul located and deleted the stray leftover Photo Gallery box under
Port Washington in Carrd. Two Rivers' own Photo Gallery began working
correctly immediately after.

**Diagnostic method used (repeatable for future duplicate-ID bugs):**
1. Rule out "leftover/mixed code in the box itself" by having the user paste
   back the box's literal current contents and diffing it against the
   delivered file.
2. Have the user open the live page, View Page Source, and use the browser's
   Find (Ctrl+F/Cmd+F) to search for the exact `id="..."` string in question.
   The match count tells you immediately whether there's a duplicate on the
   page — no need to guess or ask for a screenshot first.
3. If duplicated, search the source near the second match for identifying
   text (pier names, comments, box titles) to locate roughly where it lives.

## Bug #2 this session: Two Rivers had large gaps between collapsible box buttons (RESOLVED, cause never definitively identified)

Separate from Bug #1. Even after fixing the duplicate-ID collapse bug, Two
Rivers showed large visual gaps between the Sky/Moon & Forecast, Fish
Cleaning, Photo Gallery, and Submit a Photo buttons — gaps that did not
exist on the equivalent Sheboygan or Manitowoc boxes.

**What was ruled out, with evidence:**
- The delivered code's spacing rules (e.g. `.sec{margin-bottom:18px}`) were
  confirmed byte-for-byte identical between the Two Rivers and Sheboygan
  files — not a code difference.
- Carrd's per-box Settings panel (gear icon: ID, Classes, Attributes) has no
  height/padding/spacing field at all for these Embed elements — ruled out
  as a source of a settable difference.
- Box "Style" was confirmed "Inline" (not "iFrame") on all affected Two
  Rivers boxes — ruled out iFrame-related fixed-height behavior.
- Container/Row-level spacing settings were checked by Paul and found
  identical between Two Rivers and Sheboygan's equivalent containers.
- A leftover/orphaned empty container row between boxes (Paul's own
  suspicion, and Claude's early hypothesis) was ruled out — the "Empty"
  spacer Paul found was confirmed to be the standard spacer *between
  different piers' sections*, present identically on every pier, not
  something specific to Two Rivers.

**What actually fixed it (D426):** Paul deleted the affected Two Rivers
Embed boxes entirely (not just their code) and created brand-new Embed
boxes in their place, then pasted the same already-verified code into the
new boxes. This immediately resolved the spacing — the new boxes render
with Sheboygan-matching spacing.

**Standing conclusion:** the exact Carrd-internal mechanism was never
identified despite thorough checking of every setting exposed in Carrd's
UI. The working theory is that a Carrd Embed box/container can carry some
legacy formatting or configuration from its creation history that isn't
surfaced anywhere in its own visible settings panel (ID/Classes/Attributes/
Style) — possibly tied to how/when the box was originally created or
cloned, not to anything editable after the fact.

## Decisions Log

*(New entries this session — D424 onward.)*

- **D424 (Two Rivers Lure Call panel dropped):** Two Rivers' old Sky box
  also contained a full Lure Call recommendation panel hidden behind the
  Sky/Moon name, exactly like Manitowoc's did (D419). Dropped entirely,
  same call as Manitowoc — Paul's "same procedure as Manitowoc" instruction
  was treated as authorization to apply the same precedent without
  re-asking, since this is now an established pattern (not a first-time
  discovery requiring a stop-and-ask per D418 step 3), but it was still
  flagged explicitly in the delivery plan before any files were written.
- **D425 (duplicate/leftover box collision, broadened from D416):** D416
  established that *generic* box IDs collide across every pier's copy of
  a shared box name on the single long page. This session found a related
  but distinct failure mode: a genuinely pier-specific ID (`pbphtr`,
  already unique-looking) can still collide if a **stray leftover copy**
  of that exact box ends up duplicated elsewhere on the page — in this
  case under Port Washington, apparently left over from cloning. The
  lesson: pier-specific naming prevents collisions between *intentional*
  per-pier boxes, but does not protect against accidental duplicate/
  orphaned boxes left behind during page construction. When a box with a
  correctly-unique ID still misbehaves in a way the code can't explain,
  checking the live page's rendered source for a duplicate ID (via
  Ctrl+F/Cmd+F match count) is now the standing first diagnostic step,
  not a last resort.
- **D426 (delete-and-rebuild-fresh as a standing fix):** When a Carrd box
  behaves differently from a verified-byte-identical sibling box on another
  pier, and every setting exposed in Carrd's own UI (ID, Classes,
  Attributes, Style, Row/Section spacing) has been checked and found
  identical, the fastest reliable fix is deleting the box entirely and
  recreating it fresh, then re-pasting the same code — rather than
  continuing to hunt for a setting that may not be exposed anywhere
  visible. This resolved Two Rivers' spacing bug after the specific cause
  could not be pinned down through the UI.
- **D427 (pre-delivery verification step added):** Before re-delivering
  any files (especially after a "just give me new code" request following
  a troubleshooting session), Claude now runs a verification pass first:
  JavaScript syntax check (`node --check`), CSS brace-count balance, HTML
  div tag-balance count, and byte size vs. the 16,384 limit — rather than
  simply re-sending previously-written files unchecked. This was applied
  before re-delivering Two Rivers' files after Paul deleted and recreated
  all 5 boxes.

## Reasoning Ledger

- **Why checking the pasted box content byte-for-byte was the right first
  diagnostic step for Bug #1:** Before that check, "leftover old code
  still in the box" was a live, plausible hypothesis. Having Paul paste
  the box's actual literal contents back and diffing it character-for-
  character against the delivered file eliminated that hypothesis with
  certainty in one step, instead of several more rounds of "did you
  definitely clear it out?" back-and-forth.
- **Why the Ctrl+F source-search was more useful than another screenshot
  request:** A screenshot only shows what's rendered, not the underlying
  DOM structure. Once code-level and paste-level causes were ruled out,
  the remaining plausible cause (a literal duplicate element ID somewhere
  on the single long page) is something a screenshot cannot reveal but a
  raw source search answers in seconds with a definite number.
- **Why Bug #2 (spacing) was hard to pin down:** Every layer that was
  checked — the code itself, the box's own Carrd settings, the box's
  Style setting, the Row, the Section background — came back identical
  between Two Rivers and Sheboygan. That's consistent with the box
  carrying some non-editable legacy state from its creation/cloning
  history rather than any currently-set, currently-visible property. This
  is a plausible but unconfirmed explanation — it was never directly
  verified, only inferred from the fact that recreating the box from
  scratch fixed the issue while nothing else did.
- **Why Paul's frustration midway through Bug #2 was a legitimate signal
  to change approach:** Several specific, targeted checks in a row all
  came back "no difference found." At that point, continuing to send Paul
  hunting through more menus for an as-yet-unnamed setting was lower-value
  than just offering the practical fix (delete and rebuild) that didn't
  require first identifying the exact cause. This should generally be
  offered earlier once 2-3 specific hypotheses have been checked and
  ruled out, rather than only as a last resort after many rounds.

## Technical Details

- **Two Rivers file sizes (all under the 16,384-byte Carrd limit):**
  `two-rivers-pier-a-report.html` 11,546 bytes; `two-rivers-pier-b-report.html`
  15,442 bytes (942 bytes margin — tight, same caution as Manitowoc's pbmtb:
  do not add content without splitting first); `two-rivers-fish-cleaning-
  stations.html` 3,985 bytes; `two-rivers-photo-gallery.html` 5,447 bytes;
  `two-rivers-submit-a-photo.html` 1,467 bytes.
- **Two Rivers-specific station/zone keys (preserved verbatim, do not
  re-derive):** Pier A — `KEY="two_rivers"`, `BUOY_KEY="tr1"`. Pier B —
  `HKEY="trw"`, `ZKEY="trz"`, `PKEY="two_rivers"` (PKEY declared but unused
  in rendering, matching the same vestigial pattern already present in
  Sheboygan's pbshb v8 — not re-derived or removed, kept for structural
  consistency). Sky/Moon — `MLAT=44.1499`, `MLON=-87.5698`.
- **Two Rivers collapsible button ID pattern (pier-specific per D423):**
  `pbtrbFcTog`/`pbtrbFcWrap`/`pbtrbFcArr` (Pier B forecast toggle),
  `pbtrCleanTog`/`pbtrCleanWrap`/`pbtrCleanArr` (Fish Cleaning),
  `pbphtrTog`/`pbphtrWrap`/`pbphtrArr` (Photo Gallery).
- **Confirmed Port Washington exists as a real, built-out section in Carrd**
  (not just a label in a nav list) — it has at least one real Code Embed
  box on it (the stray leftover Photo Gallery copy). This doesn't fully
  resolve the standing Open Question about whether Port Washington is an
  officially supported seventh pier, but confirms real page infrastructure
  exists there already.
- **Standing pre-delivery verification checklist (D427), for any future
  file redelivery:** `node --check` on each extracted `<script>` block;
  count `{`/`}` in each `<style>` block and confirm equal; count `<div`/
  `</div>` in the static HTML portion and confirm equal; confirm byte size
  vs. 16,384 with margin noted.

## Design Decisions

- No new design-token decisions this session — Two Rivers uses the same
  master palette and radius values established in D413/v55, applied
  without deviation.

## User Preferences

*(Additions this session — prior preferences preserved below.)*

- Confirmed again: Paul wants the "same procedure as [prior pier]" applied
  without re-litigating settled patterns (e.g. dropping a hidden Lure Call
  panel) — but still expects it named/flagged in the delivery, not silently
  done.
- When troubleshooting stalls after 2-3 specific checks come back
  negative, Paul wants the practical fix offered sooner rather than more
  rounds of settings-hunting — confirmed via this session's friction.
- Paul wants files re-verified (not just re-sent from memory) before
  redelivery, especially after a "just start over" request — explicit
  instruction this session ("Check and double check your work before you
  give it to me").

## Constraints

Unchanged from v56, plus:
- `pbtrb` (Two Rivers Pier B) is now at 15,442 bytes, 942 bytes margin —
  treat as tight, same caution level as Manitowoc's `pbmtb`.
- Before redelivering any previously-written files, run the D427
  verification checklist rather than resending unchecked.

## Risks

- **Port Washington may contain other stray/duplicate leftover boxes**
  from whichever pier(s) it was originally cloned from, beyond the one
  Photo Gallery copy already found and removed. Not yet checked. Worth a
  quick source-search pass (Ctrl+F for other piers' box IDs) next time
  Port Washington is touched, before assuming it's clean.
- **The Bug #2 spacing root cause is unconfirmed.** The fix (delete and
  recreate) worked, but the underlying Carrd mechanism was never
  identified. If the same symptom appears on a future pier, the same
  delete-and-rebuild fix should be tried early rather than repeating the
  full settings-hunting process from this session.
- All risks carried from v56 remain open (see preserved section below):
  Manitowoc's `pbmtb` margin, Sheboygan `pbsap-sheboygan` v6 not yet
  independently reconfirmed, generic-ID collision risk on any not-yet-
  rebuilt pier, buoywatchA margin, St. Joseph MI probe pending, Compare
  Piers NOAA attribution gap.

## Open Questions

- **Did Paul ever explicitly delete Two Rivers' 3 retired old boxes**
  (`pb-tr4-sky`, `pbtrsp`, `pb-tr-sug`)? These were flagged for deletion
  in the original delivery message, but partway through this session Paul
  deleted and recreated the *restructured* boxes (Pier B, Fish Cleaning,
  Photo Gallery, Submit a Photo) to fix the spacing bug — it's not
  confirmed whether the 3 separate retired boxes were also cleaned up
  during that same pass or still need explicit deletion. Confirm next
  session.
- Carried from v56: which pier does Paul want to do next — Kewaunee,
  Algoma, or Sturgeon Bay?
- Carried from v55/v56: is Port Washington a fully supported seventh pier?
  Partially informed this session (real Carrd infrastructure confirmed to
  exist there) but still not fully resolved.
- Carried from v54/v55: standalone `lure-pbsheb1sky` box on Sheboygan —
  confirm with Paul whether to delete it now that `pbshb` v8 already
  contains Sky/Moon in its own collapsible.
- Carried from v56: does every pier currently have its own Submit a Photo
  box already pasted into Carrd, or only some piers so far?

## Future Ideas

Unchanged from v56 (see preserved section below) — one global species
temperature slider, HOT PIER TODAY card, lazy-loading per pier, St. Joseph
MI as first east-shore pier.

## Next Session Instructions

**Exact prompt for Paul to paste into a new chat:**

> Continuing PIERBITE. Read Memory_PIERBITE_PROJECT_MEMORY_2026-09-11_v57.md
> in full before doing anything — this is the current file, it replaces v56.
> Tell me what you understand the current state to be. Confirm model identity.
>
> Current state: Two Rivers is now fully confirmed live and matching the
> Sheboygan master template — all 5 boxes (Pier A, Pier B with merged
> Sky/Moon/Forecast collapsible, Fish Cleaning, Photo Gallery, Submit a
> Photo) are working correctly, including spacing. Sheboygan is still the
> master template. Manitowoc's 5 files were delivered in the prior session
> but are still not confirmed live — check with me on that first if it
> hasn't come up. Two open items to resolve early in this session if
> possible: (1) confirm whether Two Rivers' 3 retired old boxes
> (pb-tr4-sky, pbtrsp, pb-tr-sug) still need to be deleted from Carrd, and
> (2) Port Washington may have other leftover/duplicate boxes from
> whichever pier it was cloned from — worth a quick source-search check
> (Ctrl+F for other piers' box IDs on the live page) before assuming it's
> clean, since one duplicate (a stray Two Rivers Photo Gallery box) was
> already found and removed from there.
>
> This is a TEMPLATE-PARITY session, same workflow as Manitowoc and Two
> Rivers. 5 boxes: Pier A, Pier B (Sky/Moon/Forecast merged into one
> collapsible), Fish Cleaning Stations (collapsible), Photo Gallery
> (collapsible), Submit a Photo.
>
> I will paste in the next pier's full current code as a .txt dump. Map
> every box in it against Sheboygan's 5 boxes. Anything without a
> Sheboygan counterpart (Species, Suggestions, old-style Lure/Sky boxes) —
> flag it and ask what to do with it BEFORE writing any files, unless it's
> already established precedent from Manitowoc/Two Rivers (e.g. dropping a
> hidden Lure Call panel found inside an old Sky box) — established
> precedent can just be applied and flagged in the delivery message rather
> than re-asked.
>
> Once scope is confirmed: rebuild the 5 template boxes using THIS pier's
> own data — its own station keys, coordinates, buoy IDs, local business
> info — never Sheboygan's. Recolor everything to the master palette
> (panel #112a3f, border #1f405b, muted text #a3bcd1, faint text #8aa2b6,
> link blue #5fb6f0, card radius 16px, toggle radius 12px). If this pier's
> Submit a Photo box still uses the generic "pbsap" ID, rename it to
> pbsap-[piername].
>
> Before delivering ANY files (first delivery or a redelivery), run the
> verification checklist from D427: node --check on each script block,
> CSS brace-count balance, HTML div tag-balance count, byte size vs.
> 16,384 with margin stated.
>
> If something behaves differently on this pier than it does on an
> already-confirmed-working pier, despite verified-identical code: check
> for a duplicate/leftover element ID elsewhere on the page first (View
> Page Source, Ctrl+F the exact id="..." string, check the match count) —
> this found a real bug on Two Rivers. If a Carrd box's spacing or behavior
> differs from an identical sibling box despite every visible Carrd
> setting (ID/Classes/Attributes/Style/Row/Section) checking out identical,
> don't keep hunting for the exact setting — offer deleting and recreating
> the box fresh as a working fix, sooner rather than after many rounds.
>
> Standing rules: full replacement files only, never snippets. Filenames
> must be full plain-English names, box ID stated in the delivery message
> and the internal HTML comment. Verify every file is safely under Carrd's
> 16,384-byte limit before delivering. Name any retired old box explicitly
> so I know to delete it from Carrd. One pier at a time, confirm live
> before moving to the next.

**Reminder for Paul:** after uploading this file, delete
`Memory_PIERBITE_PROJECT_MEMORY_2026-09-11_v56.md` from Project Files.

---

# === EVERYTHING BELOW THIS LINE IS PRESERVED UNCHANGED FROM v56 ===

<!-- PIERBITE PROJECT MEMORY | 2026-09-11 | v56 | Manitowoc rebuild session: took Manitowoc from 8 boxes down to 5, matching the Sheboygan template exactly. Merged Manitowoc's own Sky/Moon data (its own coordinates, 44.0914/-87.6438) into a single "Sky, Moon & Forecast" collapsible on Pier B, alongside the NOAA forecast — same pattern as Sheboygan's pbshb v8. Dropped Temperature Break, the direction-weights key table, the Pier Access section, and the bottom data-attribution line from Pier B, all to match what Sheboygan's rebuild already dropped. Retired three boxes entirely: the old Sky/Lure box (which turned out to contain a full "Today's Lure Call" recommendation panel, not just Sky/Moon — Paul chose to drop that logic rather than carry it forward), the Species box, and the Suggestions box. Fish Cleaning Stations and Photo Gallery were converted from always-open to the same collapsible-toggle pattern Sheboygan uses. Submit a Photo got the same generic-ID collision fix as Sheboygan: pbsap → pbsap-manitowoc. Pier A needed no color changes (was already on the master palette) — only the DNR banner line was removed from its output, matching Sheboygan's pbsha v9. This session establishes a repeatable "bring a pier to template parity" checklist for the remaining piers (D418). Confirmed working pattern: ask before dropping/merging any box whose content goes beyond simple formatting — this surfaced the Lure Call panel, which was not obvious from the box name alone. All 5 files delivered; none yet confirmed live by Paul. Supersedes v55 — delete Memory_PIERBITE_PROJECT_MEMORY_2026-09-11_v55.md from Project Files and upload this one. -->

# PIERBITE PROJECT MEMORY - 2026-09-11 v56

**THIS IS THE CURRENT REVISION. It supersedes v55.**
Nothing deleted — additive by design. Everything below this v56 section is
preserved byte-for-byte from v55.

## Project Overview

PierBite.com — six (possibly seven, see Open Questions) Wisconsin Lake
Michigan pier fishing-conditions pages, all rendered as **one single long
Carrd page** with piers reached via anchor links (`#sheboygan`,
`#manitowoc`, etc.) rather than separate pages. Paul is non-technical and
relies entirely on Claude for all code. Carrd Pro Plus frontend +
Python/GitHub Actions backend.

## Template-Parity Rebuild Initiative (NEW — 2026-09-11, v56)

This session widened the formatting-only track from v55 into something
bigger: bringing each pier's box **structure**, not just its colors, into
parity with the Sheboygan template. This is now the standing workflow for
every remaining pier.

### Workflow established this session (D418):

1. Paul uploads the Sheboygan template file (current confirmed master)
   plus the old pier's full `.txt` code dump.
2. Claude maps every box in the old pier's file against Sheboygan's 5
   boxes: Pier A, Pier B, Fish Cleaning, Photo Gallery, Submit a Photo.
3. Any box that doesn't have a Sheboygan counterpart (Species,
   Suggestions, old-style Lure/Sky boxes) gets flagged, **not silently
   dropped** — Claude asks Paul what to do with it before writing any
   files, especially if it contains logic/content beyond simple color
   formatting. This is what surfaced the Lure Call panel hidden inside
   Manitowoc's old Sky box.
4. Once scope is confirmed, Claude delivers full replacement files for
   exactly the 5 template boxes, using the OLD pier's own data (station
   keys, coordinates, buoy IDs, local business info) — never Sheboygan's.
5. Boxes being retired are named explicitly so Paul knows to delete them
   from Carrd, not just stop pasting into them.

### Manitowoc box mapping (this session's worked example):

| Old Manitowoc box | Old ID | Outcome |
|---|---|---|
| Pier A | `pbmta` | Kept — already on master palette, only the DNR banner line removed |
| Pier B | `pbmtb` | Kept, restructured — Sky/Moon merged into collapsible w/ forecast; Temp Break, direction-weight table, Pier Access, bottom attribution all dropped |
| Sky + Lure Call | `pb-mtw4-sky` | **Retired** — Sky/Moon portion merged into Pier B; Lure Call recommendation panel dropped entirely (Paul's explicit call) |
| Species | `pbmtsp` | **Retired** — no Sheboygan counterpart |
| Suggestions | `pb-mtw-sug` | **Retired** — no Sheboygan counterpart |
| Fish Cleaning | `pb-mtw-clean` | Kept, restructured — always-open panel became a collapsible toggle, same pattern as Sheboygan's `pb-sheb-clean` |
| Submit a Photo | `pbsap` | Kept, **renamed** to `pbsap-manitowoc` — same generic-ID collision fix as Sheboygan (D416/D417) |
| Photo Gallery | `pbphmn` | Kept, restructured — always-open became collapsible + lazy-loaded, same pattern as Sheboygan's `pbphsh` |

### Files delivered this session:

- `manitowoc-pier-a-report.html` → box `pbmta` — 11,325 bytes
- `manitowoc-pier-b-report.html` → box `pbmtb` — 15,634 bytes, **only
  750 bytes margin — tight, flag before adding anything to this box**
- `manitowoc-fish-cleaning-stations.html` → box `pb-mtw-clean` — 3,272 bytes
- `manitowoc-photo-gallery.html` → box `pbphmn` — 5,372 bytes
- `manitowoc-submit-a-photo.html` → box `pbsap-manitowoc` (renamed
  from `pbsap`) — 1,402 bytes

None of these five are confirmed live yet — Paul has the files but hasn't
pasted/published/confirmed them.

## Current Status

- **Sheboygan:** template pier, essentially locked as of v55. Submit a
  Photo v6 (`pbsap-sheboygan`) still needs Paul's live confirmation —
  carried open from v55.
- **Manitowoc:** all 5 template-parity files delivered this session
  (see table above). **Not yet confirmed live.** Old boxes `pb-mtw4-sky`,
  `pbmtsp`, `pb-mtw-sug` need to be deleted from Carrd once Paul confirms
  the new files are working.
- **Remaining piers not yet touched:** Two Rivers, Kewaunee, Algoma,
  Sturgeon Bay. Port Washington status still unresolved (see Open
  Questions, carried from v54/v55).
- **Site rebuild initiative from v54** (home page redesign, hero photos,
  Compare Piers attribution fix, St. Joseph MI probe) remains unchanged
  and separate from this template-parity track.

## Completed Work (this session)

- Mapped all 8 of Manitowoc's old boxes against Sheboygan's 5-box
  template structure
- Identified that Manitowoc's old Sky box also contained a full "Lure
  Call" recommendation panel — flagged to Paul before doing any work,
  rather than silently dropping or silently keeping it
- Rebuilt Pier B's Sky/Moon/Forecast section as a single collapsible,
  using Manitowoc's own coordinates (44.0914/-87.6438), preserving all
  wind-scoring logic (`UPWELLING_COMPONENT` table) byte-for-byte
- Removed Temperature Break, direction-weights table, Pier Access, and
  bottom attribution line from Pier B, matching Sheboygan
- Converted Fish Cleaning Stations and Photo Gallery from always-open to
  collapsible-toggle, matching Sheboygan's pattern
- Applied the generic-ID collision fix to Manitowoc's Submit a Photo box
  (`pbsap` → `pbsap-manitowoc`)
- Removed the DNR banner line from Pier A's output (already on master
  colors, no recolor needed)
- Verified all 5 delivered files are safely under Carrd's 16,384-byte
  limit (Pier B is the tightest, at 750 bytes margin)

## Work In Progress

- **Waiting on Paul** to paste, publish, and confirm all 5 Manitowoc
  files on the live site
- **Waiting on Paul** to delete the 3 retired Manitowoc boxes
  (`pb-mtw4-sky`, `pbmtsp`, `pb-mtw-sug`) from Carrd once the new files
  are confirmed working

## Remaining Tasks

1. Paul confirms all 5 new Manitowoc files are live and correct
2. Paul deletes the 3 retired Manitowoc boxes from Carrd
3. Confirm `pbsap-sheboygan` v6 is live (carried open from v55)
4. Begin the same template-parity pass on the next pier (Two Rivers,
   Kewaunee, Algoma, or Sturgeon Bay — Paul's choice of order)
5. For each remaining pier: map its boxes against Sheboygan's 5, flag
   anything without a template counterpart before touching it, watch
   specifically for hidden logic bundled into an old Sky/Lure-style box
   (as happened with Manitowoc)
6. All open items carried from v54/v55 remain open and untouched by this
   track: home page redesign, hero photos, Compare Piers NOAA LMHOFS
   attribution fix, St. Joseph MI probe run #2, Port Washington status,
   Sheboygan's standalone `lure-pbsheb1sky` box deletion

## Decisions Log

*(New entries this session — D418 onward.)*

- **D418 (template-parity workflow):** Established the 5-step rebuild
  workflow above as the standing process for every remaining pier: map
  old boxes to Sheboygan's 5, flag anything without a counterpart before
  acting on it, deliver full replacement files using the old pier's own
  data, name retired boxes explicitly for deletion.
- **D419 (Lure Call panel dropped):** Manitowoc's old Sky box contained
  a full lure-color/action recommendation panel that Sheboygan's
  equivalent never had. Paul's explicit choice: drop it entirely, keep
  only Sky/Moon + Forecast, matching Sheboygan exactly. This logic
  (species-temperature matching, wind-based color suggestions) is not
  carried forward anywhere.
- **D420 (Species and Suggestions boxes dropped for Manitowoc):** Paul
  confirmed both should be dropped, matching Sheboygan's final 5-box
  structure, rather than kept and merely recolored.
- **D421 (Pier B fully restructured, not just recolored):** Paul chose
  to bring Manitowoc's Pier B in line with Sheboygan's pbshb v8 pattern
  exactly — collapsible Sky/Moon/Forecast, no Temperature Break, no
  direction-weight table, no Pier Access, no bottom attribution — rather
  than only recoloring the old layout.
- **D422 (DNR banner dropped from Manitowoc Pier A):** Sheboygan's
  pbsha v9 already removed this banner. Manitowoc's Pier A still had
  it. Removed to match, flagged explicitly in the delivery rather than
  silently dropped, since no version of this app-Paul-decision has been
  spelled out for Manitowoc before.
- **D423 (Fish Cleaning and Photo Gallery made collapsible):** Both
  boxes were always-open in the old Manitowoc code. Sheboygan's rebuilt
  versions of both are collapsible toggles. Converted Manitowoc's to
  match, same toggle/arrow pattern, unique per-box element IDs
  (`pbmtwCleanTog`/`pbmtwCleanWrap`/`pbmtwCleanArr`,
  `pbphmnTog`/`pbphmnWrap`/`pbphmnArr`) so the collapsible buttons
  themselves don't hit the same generic-ID collision class of bug as
  D416 — button IDs need to be pier-specific too, not just the outer
  box ID.

## Reasoning Ledger

- **Why Claude stopped and asked about the Lure Call panel instead of
  just merging or just dropping it:** The box name ("manitowoc-lure")
  suggested it might be pure Sky/Moon data like Sheboygan's old
  equivalent, but the actual content included a full recommendation
  engine (species detection from water temp, lure color logic from wind
  and light conditions). Silently keeping it would have broken the
  "same number of boxes as Sheboygan" goal; silently dropping it would
  have violated "don't change any logic." Since the request's own two
  goals conflicted on this specific box, asking was the only way to
  actually match Paul's intent rather than guess at it.
- **Why Pier A needed no color change:** Manitowoc's `pbmta` style block
  was checked variable-by-variable against Sheboygan's `pbsha` and the
  values were already identical (`#112a3f`/`#1f405b`/`#a3bcd1`/`#8aa2b6`/
  `#5fb6f0`) — this pier's Pier A box had already been built on the
  current palette at some earlier point, so recoloring it would have
  been a no-op. Confirmed by direct comparison, not assumed.
- **Why Manitowoc's own openlake-dedup fix was preserved instead of
  copying Sheboygan's script wholesale:** Manitowoc's `waveSub()`
  already has the Q-BUOY-OPENLAKE-DOUBLE regex fix (from its own v9,
  2026-08-30); Sheboygan's `pbsha` in the current template does NOT have
  this fix. Blindly copying Sheboygan's script over Manitowoc's would
  have reintroduced a bug Manitowoc doesn't have. Each pier's own script
  logic was preserved and only the HTML/CSS structure and box IDs were
  brought to parity — never a wholesale copy-over of one pier's code
  onto another's.
- **Why Manitowoc's own coordinates were used for Sky/Moon, not
  Sheboygan's:** The astronomical math (sunrise/sunset/moonrise/moonset)
  is generic — same formulas everywhere — but it's location-dependent.
  Manitowoc's old Sky box already had its own confirmed coordinates
  (44.0914, -87.6438), carried over verbatim into the new Pier B
  collapsible instead of Sheboygan's (43.7495, -87.6927).

## Technical Details

- **Manitowoc file sizes (all under the 16,384-byte Carrd limit):**
  `manitowoc-pier-a-report.html` 11,325 bytes; `manitowoc-pier-b-report.html`
  15,634 bytes (750 bytes margin — tight, below the 300-500 target floor
  is not the case here but it's close; do not add content to this box
  without splitting first); `manitowoc-fish-cleaning-stations.html`
  3,272 bytes; `manitowoc-photo-gallery.html` 5,372 bytes;
  `manitowoc-submit-a-photo.html` 1,402 bytes.
- **Manitowoc-specific station/zone keys (preserved verbatim, do not
  re-derive):** Pier A — `KEY="manitowoc"`, `BUOY_KEY="mt1"`. Pier B —
  `HKEY="mtw"`, `ZKEY="mtz"`, `PKEY="manitowoc"`. Sky/Moon —
  `MLAT=44.0914`, `MLON=-87.6438`.
- **Collapsible button ID pattern (established this session, applies to
  all future piers):** every collapsible box's toggle/wrap/arrow IDs
  must be pier-specific (e.g. `pbmtwCleanTog`, not a generic `CleanTog`),
  for the same reason box IDs must be pier-specific — these are literal
  DOM element IDs on a single long page, so a generic one collides
  across piers exactly like D416.

## Design Decisions

- **Template parity means box-for-box structure, not just color.**
  Confirmed this session: matching Sheboygan means matching which boxes
  exist, whether each is collapsible or always-open, and how content is
  organized inside — color and radius are only one part of "formatting
  only" work. Structural consolidation (merging Sky/Moon into Pier B,
  making Fish Cleaning/Photo Gallery collapsible) is now understood to
  be part of bringing a pier to parity, distinct from — but often
  bundled with — a pure color pass.
- **A pier's own real content and data always wins over Sheboygan's.**
  Station keys, buoy IDs, coordinates, business names/addresses, and any
  pier-specific bug fixes come from the old pier's own file, never
  copied from the Sheboygan template. Only the HTML/CSS shape and the
  color palette are shared.

## User Preferences

*(Additions this session — prior preferences preserved below.)*

- Paul wants the exact same template-parity treatment applied to every
  remaining pier, one at a time, same workflow as this Manitowoc pass.
- Confirmed: Paul wants to be asked before Claude drops or merges any
  box whose content isn't obviously just formatting (this session's
  Lure Call discovery is the reason this matters) — but Paul does not
  want to be asked about things that are already clearly established
  precedent from a prior pier (e.g. the DNR banner removal, the ID
  collision fix pattern) — those can just be done and flagged in the
  delivery message.

## Constraints

Unchanged from v55, plus:
- Every collapsible box's internal toggle/wrap/arrow element IDs must
  be pier-specific, not generic — same collision risk as box IDs
  themselves (D423).
- `pbmtb` (Manitowoc Pier B) is now at 15,634 bytes, 750 bytes margin —
  treat as tight; any future addition needs a new adjacent embed.

## Risks

- **Manitowoc's `pbmtb` margin is 750 bytes** — tighter than most boxes
  on the site. Flag before adding anything.
- **Manitowoc's 3 retired boxes are still live in Carrd** until Paul
  deletes them — no collision risk from them (they have pier-specific
  IDs already), but they're serving stale/redundant content until
  removed.
- All risks carried from v55 remain open (see preserved section below):
  Sheboygan `pbsap-sheboygan` v6 not yet confirmed live, generic-ID
  collision risk on any not-yet-rebuilt pier, buoywatchA margin,
  pbshb margin, St. Joseph MI probe pending, Compare Piers NOAA
  attribution gap.

## Open Questions

- Carried from v55: does every pier currently have its own Submit a
  Photo box already pasted into Carrd, or only Sheboygan/Manitowoc so
  far? Determines how live the collision risk currently is on
  not-yet-rebuilt piers.
- Carried from v54/v55: is Port Washington a fully supported seventh
  pier, or was its appearance in the Pick Your Pier list a mockup
  artifact? Still unresolved.
- Carried from v54/v55: standalone `lure-pbsheb1sky` box on Sheboygan —
  confirm with Paul whether to delete it now that `pbshb` v8 already
  contains Sky/Moon data in its own collapsible.
- New this session: which pier does Paul want to do next — Two Rivers,
  Kewaunee, Algoma, or Sturgeon Bay?

## Future Ideas

Unchanged from v54 (see preserved section below) — one global species
temperature slider, HOT PIER TODAY card, lazy-loading per pier,
St. Joseph MI as first east-shore pier.

## Next Session Instructions

**Exact prompt for Paul to paste into a new chat:**

> Continuing PIERBITE. Read Memory_PIERBITE_PROJECT_MEMORY_2026-09-11_v56.md
> in full before doing anything — this is the current file, it replaces v55.
> Tell me what you understand the current state to be. Confirm model identity.
>
> This is a TEMPLATE-PARITY session, same workflow as the Manitowoc pass in
> v56. Sheboygan is still the master template — 5 boxes: Pier A, Pier B
> (Sky/Moon/Forecast merged into one collapsible), Fish Cleaning Stations
> (collapsible), Photo Gallery (collapsible), Submit a Photo.
>
> I will paste in the next pier's full current code as a .txt dump. Map
> every box in it against Sheboygan's 5 boxes. Anything that doesn't have a
> Sheboygan counterpart (Species, Suggestions, old-style Lure/Sky boxes,
> anything else) — flag it to me and ask what to do with it BEFORE writing
> any files, especially if it has logic or content beyond simple color
> formatting. Do not assume an old Sky/Lure-style box is just Sky/Moon data
> — check its actual contents, the way Manitowoc's turned out to also have
> a full Lure Call panel.
>
> Once scope is confirmed: rebuild the 5 template boxes using THIS pier's
> own data — its own station keys, coordinates, buoy IDs, local business
> info — never Sheboygan's. Recolor everything to the master palette
> (panel #112a3f, border #1f405b, muted text #a3bcd1, faint text #8aa2b6,
> link blue #5fb6f0, card radius 16px, toggle radius 12px). If this pier's
> Submit a Photo box still uses the generic "pbsap" ID, rename it to
> pbsap-[piername], same fix as Sheboygan and Manitowoc.
>
> Standing rules: full replacement files only, never snippets. Filenames
> must be full plain-English names, box ID stated in the delivery message
> and the internal HTML comment. Every collapsible box's internal
> toggle/wrap/arrow element IDs must also be pier-specific, not generic.
> Verify every file is safely under Carrd's 16,384-byte limit before
> delivering. Name any retired old box explicitly so I know to delete it
> from Carrd. One pier at a time, confirm live before moving to the next.

**Reminder for Paul:** after uploading this file, delete
`Memory_PIERBITE_PROJECT_MEMORY_2026-09-11_v55.md` from Project Files.

---

# === EVERYTHING BELOW THIS LINE IS PRESERVED UNCHANGED FROM v55 ===

<!-- PIERBITE PROJECT MEMORY | 2026-09-11 | v55 | Formatting session: established site-wide "formatting only" workflow using Sheboygan pbshb v8 (Sky, Moon & Forecast) as the master color/radius reference. Recolored and radius-corrected three Sheboygan boxes: Fish Cleaning Stations, Photo Gallery, Submit a Photo — first two confirmed correct on live site via pixel-sampled screenshot, third required an additional structural fix. Discovered and root-caused a site-wide platform risk: Carrd renders all six (seven, including Port Washington) piers on one single long page reached by anchor links, so any Code Embed box using a generic, non-pier-specific element ID collides with every other pier's copy of that box — whichever copy sits later in the page DOM silently overrides the others' styling. Sheboygan's Submit a Photo box ID renamed from generic "pbsap" to unique "pbsap-sheboygan" to fix it; every other pier's Submit a Photo box (and potentially other generic-ID boxes) will need the same per-pier unique-ID treatment as each pier is rebuilt. Filename convention corrected: full plain-English filenames now required, no abbreviated internal box IDs — supersedes the older filename rule. Next: Paul will send the finalized/complete Sheboygan code as the template, then the next pier's code to begin that pier's formatting pass. Supersedes v54 — delete Memory_PIERBITE_PROJECT_MEMORY_2026-09-04_v54.md from Project Files and upload this one. -->

# PIERBITE PROJECT MEMORY - 2026-09-11 v55

**THIS IS THE CURRENT REVISION. It supersedes v54.**
Nothing deleted — additive by design. Everything below this v55 section is
preserved byte-for-byte from v54.

## Project Overview

PierBite.com — six (possibly seven, see Open Questions) Wisconsin Lake
Michigan pier fishing-conditions pages, all rendered as **one single long
Carrd page** with piers reached via anchor links (`#sheboygan`,
`#manitowoc`, etc.) rather than separate pages. This single-page
architecture is the root of a platform-level risk discovered this
session (see D416). Paul is non-technical and relies entirely on Claude
for all code. Carrd Pro Plus frontend + Python/GitHub Actions backend.

## Formatting Session Initiative (NEW — 2026-09-11)

This session opened a new, explicitly scoped **formatting-only** track
that will continue across several upcoming sessions, run in parallel to
(but separate from) the site rebuild initiative from v54.

### Scope and ground rules (D414):
- Formatting sessions touch **color and border-radius only**.
- No HTML structure changes, no JavaScript logic changes, no content
  changes — unless Paul explicitly asks for a technical change within
  that session.
- Sheboygan is the **template/master pier**. Its `pbshb` v8 (Sky, Moon &
  Forecast) box is the master color and radius reference for the entire
  site (D413).
- Workflow: Paul provides a pier's full code (per-pier `.txt` dump, same
  pattern as the v54 rebuild workflow), Claude reformats every box in
  that dump to match the master palette/radius, delivers full
  replacement files, Paul pastes and confirms. Then Paul provides the
  next pier's code and the cycle repeats.

### Master formatting reference (D413) — locked in from `pbshb` v8:

| Token | Value | Role |
|---|---|---|
| Panel background | `#112a3f` | Card/box fill |
| Panel border | `#1f405b` | Card/box border |
| Muted text | `#a3bcd1` | Secondary body text |
| Faint text | `#8aa2b6` | Labels, meta text |
| Link blue | `#5fb6f0` | Links |
| Brand green (unchanged) | `#8fd43c` | Accents, badges |
| Gold (unchanged) | `#f5b53f` | Buttons, standout elements |
| Ink (unchanged) | `#eef5fb` | Primary text |
| Card/panel border-radius | `16px` | Main content panels |
| Toggle button border-radius | `12px` | Collapsible toggle buttons (already consistent site-wide — no change needed) |

### Sheboygan boxes reformatted this session:

- **`pb-sheb-clean` → v3** (delivered as `sheboygan-fish-cleaning-stations.html`)
  — panel/border/text colors and card radius (14px→16px) corrected.
  **Confirmed correct on live site** via pixel-sampled screenshot.
- **`pbphsh` → v3** (delivered as `sheboygan-photo-gallery.html`)
  — panel/border/text colors and empty-state radius (10px→16px)
  corrected; hardcoded lightbox-close-button colors also updated to
  match. **Confirmed correct on live site** via pixel-sampled screenshot.
- **`pbsap` → v5** (delivered as `submit-a-photo.html`) — panel/border/
  text colors and card radius (10px→16px) corrected. **Superseded by
  the v6 ID fix below** — colors were correct but the box still
  rendered the old color live due to the ID collision bug.
- **`pbsap` → renamed `pbsap-sheboygan` → v6** (delivered as
  `sheboygan-submit-a-photo.html`) — same corrected colors as v5, plus
  the element ID and every CSS selector renamed from generic `pbsap` to
  unique `pbsap-sheboygan`. **Not yet confirmed live by Paul** — this
  is the current open item.

### Root cause discovered: generic box IDs collide across piers (D416)

Because the entire site is one long page with every pier's boxes
stacked on it, a Code Embed box using a **generic, non-pier-specific
element ID** — like plain `pbsap` — collides with every other pier's
copy of that same box on the page. The browser applies the style block
to *every* element with that ID, and whichever copy sits later in the
page's DOM order silently wins visually, regardless of which one Paul
actually edited. This is a **systemic risk for any shared/generic box
name**, not unique to Submit a Photo — `pbsha`, `pb-sheb-clean`, and
`pbphsh` all happened to be safe because their names are already
Sheboygan-specific, but any box built with a generic name before that
convention was consistently followed is a latent collision risk.

**How it was diagnosed (not guessed):** Paul correctly pushed back on
an initial "maybe it didn't get pasted / needs republish" explanation,
pointing out Fish Cleaning and Photo Gallery *did* update correctly, so
that explanation couldn't be the whole story. Rather than guess again,
the delivered screenshot was pixel-sampled directly with Python/PIL:
Sky/Moon/Forecast, Fish Cleaning, and Photo Gallery all rendered the
exact new hex value (`17,42,63` = `#112A3F`), while Submit a Photo
rendered the exact *old* hex value (`14,28,43` = `#0E1C2B`) — proving
the delivered file's CSS was correct and the live DOM was pulling in a
stale, colliding style block from elsewhere on the page instead of a
paste or publish failure.

### Fix applied (D417):

Sheboygan's Submit a Photo box renamed `pbsap` → `pbsap-sheboygan`
(id + every CSS selector). **Every other pier's Submit a Photo box must
get the same unique-ID treatment** — `pbsap-manitowoc`,
`pbsap-tworivers`, `pbsap-portwashington`, `pbsap-kewaunee`,
`pbsap-algoma`, `pbsap-sturgeonbay` — applied **as each pier is
rebuilt during the formatting pass**, not deferred to a separate
cleanup session.

### Filename convention corrected (D415):

Paul explicitly corrected the filename rule this session: deliverable
filenames must be **full plain-English names**
(`sheboygan-fish-cleaning-stations.html`), never abbreviated internal
Carrd box IDs (not `pbsha-2026-09-04-v9.html`-style names). This
**supersedes** the older "literal Carrd box ID in filename" rule.
The literal box ID is still always stated in the delivery message and
inside the internal HTML comment at the top of the file — it just no
longer appears in the filename itself.

## Current Status

- **Sheboygan formatting pass in progress.** Three boxes touched this
  session: Fish Cleaning and Photo Gallery confirmed correct live;
  Submit a Photo fix (v6, unique ID) delivered but not yet confirmed
  live by Paul.
- **Sheboygan Pier A (`pbsha`) and Pier B (`pbshb`)** were already
  correct from the prior session and serve as the master reference —
  not touched this session.
- **Waiting on Paul** to (1) confirm `pbsap-sheboygan` v6 is live and
  correctly colored, (2) send the finalized/complete Sheboygan code as
  the formatting template, and (3) send the next pier's code to begin
  that pier's formatting pass.
- **Site rebuild initiative from v54** (home page redesign, hero
  photos, remaining pier cleanups, Compare Piers attribution fix, St.
  Joseph MI probe) is unchanged and not part of this formatting track —
  still open, still separate work.

## Completed Work (this session)

- Reformatted `pb-sheb-clean` v3, `pbphsh` v3, and `pbsap` v5/v6 to
  match the `pbshb` v8 master palette and 16px card radius
- Diagnosed and fixed a site-wide Carrd platform bug: generic box IDs
  collide across piers on the single long page
- Renamed Sheboygan's Submit a Photo box to a unique per-pier ID
  (`pbsap-sheboygan`)
- Verified two of the three color fixes against a live screenshot using
  pixel sampling, not visual guesswork
- Corrected the project's filename convention going forward

## Remaining Tasks

1. **Confirm `pbsap-sheboygan` v6 is live** — Paul to paste, publish,
   hard refresh, and confirm the color now matches the other three
   boxes
2. **Get Sheboygan's finalized/complete code from Paul** as the locked
   formatting template
3. **Get the next pier's code from Paul** to begin that pier's
   formatting pass
4. **Apply the master palette + 16px card radius** to that pier's boxes
5. **Give that pier's Submit a Photo box (and any other generic-ID
   box found)** its own unique per-pier ID during the same pass —
   check every box name against the collision risk, not just Submit a
   Photo
6. **Repeat for remaining piers:** Manitowoc, Two Rivers, Kewaunee,
   Algoma, Sturgeon Bay (Port Washington status still unresolved —
   see Open Questions)
7. All open items carried from v54 remain open and untouched by this
   formatting track (see the preserved v54 section below for full
   detail): home page redesign, hero photos, Sheboygan Lure box
   deletion, Compare Piers NOAA LMHOFS attribution fix, St. Joseph MI
   probe run #2

## Decisions Log

*(New entries this session — D413 onward.)*

- **D413 (formatting master reference):** `pbshb` v8's Sky, Moon &
  Forecast panel treatment locked in as the site-wide color and radius
  reference: panel `#112a3f`, border `#1f405b`, muted text `#a3bcd1`,
  faint text `#8aa2b6`, link blue `#5fb6f0`, card/panel radius `16px`,
  toggle radius `12px` (already consistent). Chosen because it was
  Paul's stated master and because pier reports (`pbsha`/`pbshb`) were
  already using these exact values.
- **D414 (formatting-only session boundary):** This and upcoming
  per-pier formatting sessions are color/radius changes only. No
  structural, logic, or content changes unless Paul explicitly asks
  within that session. Consistent with the existing full-replacement-
  file discipline (D357/D361) — formatting changes still ship as full
  files, never diffs.
- **D415 (filename convention correction):** Filenames must be full
  plain-English names, never abbreviated internal box IDs. Supersedes
  the prior "literal Carrd box ID in filename" rule. Box ID is still
  required in the delivery message and the internal file comment.
- **D416 (root cause: generic box ID collisions):** Carrd's single
  long-page architecture means every pier's boxes share one DOM. A
  Code Embed using a generic, non-pier-specific element ID collides
  with every other pier's copy of that same box; DOM order (not edit
  history) determines which copy's styling wins visually. This is a
  systemic risk, not a one-off bug — any generically-named box on the
  site is a candidate for the same failure.
- **D417 (Submit a Photo unique-ID fix):** Sheboygan's Submit a Photo
  box renamed `pbsap` → `pbsap-sheboygan`. Every other pier's copy of
  this box must receive the same treatment (`pbsap-[piername]`) as
  that pier is rebuilt — not deferred to a later cleanup pass, since
  deferring it would leave the collision live and worsening as more
  piers get touched.

## Reasoning Ledger

- **Why the "wrong color" wasn't a code mistake:** The delivered file's
  CSS values were verified byte-for-byte against the Fish Cleaning and
  Photo Gallery files before responding — all three used identical
  hex values. When Paul reported it still looked wrong after a hard
  refresh, the next step was evidence, not a second guess: pixel-
  sampling his screenshot with Python/PIL showed the other three boxes
  rendering the exact new color and Submit a Photo rendering the exact
  *old* color, which is only possible if a different, un-updated style
  block for that same ID was also present on the page and winning.
- **Why Paul's pushback mattered:** Paul directly said "what you are
  telling me cannot be correct" when an initial explanation (stale
  cache / incomplete paste) didn't fit the fact that two other boxes
  *had* updated correctly. That contradiction was the clue that pointed
  toward a structural cause (ID collision) rather than a user-error
  cause — following the evidence he raised, rather than repeating the
  same category of guess, is what surfaced the real mechanism.
- **Why per-pier unique IDs rather than a shared reusable component:**
  Carrd Code Embed boxes have no scoping mechanism beyond whatever CSS
  ID prefix the box author chooses — no shadow DOM, no CSS modules, no
  Carrd-native way to say "this style only applies to this one copy."
  On a single continuous page with every pier present, uniqueness has
  to be enforced manually, box by box, or collisions are inevitable
  as more boxes get built from copy-pasted templates.

## Technical Details

- **Master palette (formatting reference), full token list:**
  `--p1`/panel bg `#112a3f`, `--p2`/panel border `#1f405b`,
  `--im`/muted text `#a3bcd1`, `--if`/faint text `#8aa2b6`,
  `--lb`/link blue `#5fb6f0`, `--lake`/brand green `#8fd43c`
  (unchanged), `--gold` `#f5b53f` (unchanged), `--ink` `#eef5fb`
  (unchanged). Card/panel border-radius `16px`. Toggle button
  border-radius `12px` (already consistent, verified across `pbshb`,
  `pb-sheb-clean`, `pbphsh` — no change was needed there).
- **Pixel verification method:** screenshot opened with Python/PIL,
  `img.getpixel((x,y))` sampled at multiple coordinates per box
  (avoiding text/icons), compared against expected hex values converted
  to RGB. This is now a standing verification technique for any future
  "the color looks wrong" report — faster and more certain than asking
  for a second screenshot and guessing visually.
- **Submit a Photo box collision, confirmed values:** old/colliding
  color `rgb(14,28,43)` = `#0E1C2B`; correct/delivered color
  `rgb(17,42,63)` = `#112A3F`. Both values confirmed present
  simultaneously in the same screenshot, at different box locations,
  which is the direct evidence for the DOM-order-wins mechanism rather
  than a publish failure.
- **File sizes this session (all well under the 16,384-byte Carrd
  limit):** `sheboygan-fish-cleaning-stations.html` 3,865 bytes;
  `sheboygan-photo-gallery.html` 5,270 bytes; `submit-a-photo.html`
  1,113 bytes (superseded); `sheboygan-submit-a-photo.html` 1,337
  bytes (current).

## Design Decisions

- **Card/panel radius standardized to 16px:** matches the master
  `pbshb` card. Fish Cleaning (was 14px), Photo Gallery empty-state box
  (was 10px), and Submit a Photo (was 10px) all corrected to match.
  Toggle buttons were already consistent at 12px across every box
  checked and were left unchanged.
- **Submit a Photo button (gold, pill-shaped, 14px radius) left as-is**
  — it's a button, not a content panel, so it wasn't held to the
  16px card-radius standard; its color (`--gold` `#f5b53f`) already
  matched the master before this session.

## User Preferences

*(Additions this session — prior preferences preserved below.)*

- This and upcoming per-pier sessions are explicitly **formatting
  only** — Paul does not want technical/logic changes bundled in
  unless he asks for them within that session.
- **Filenames must be full plain-English names, never abbreviated
  internal box IDs** — corrected explicitly by Paul this session;
  supersedes the older filename rule stored from prior sessions.
- When Claude states a diagnosis (especially "why does this look
  wrong"), it must be verified with evidence — not a plausible-
  sounding guess — before being presented as the explanation. Paul
  will push back on an explanation that doesn't fit the facts he's
  already given, and expects the next response to investigate rather
  than restate the same guess differently.

## Constraints

Unchanged from v54, plus:
- Formatting sessions are scoped to color/radius only — treat this as
  a hard boundary for this track of work, separate from the technical
  rebuild track.
- Every pier's formatting pass must include an ID-collision check for
  any generically-named box, not just a copy-paste of the palette
  fix — this is now a required step, not an optional nice-to-have.

## Risks

- **Generic box IDs are a latent, site-wide risk.** Submit a Photo was
  the first one discovered; there is no confirmation yet that it's the
  only one. Any box built before the pier-specific naming convention
  was consistently followed (see v54's Box naming decision) could have
  the same problem, invisible until either enough piers are live
  simultaneously or Paul reports a visual mismatch like this one.
- All risks carried from v54 remain open (see preserved section below):
  `buoywatchA` margin, `pbshb` margin, Sheboygan rebuild not fully
  confirmed live for the other boxes, St. Joseph MI probe pending,
  Compare Piers NOAA attribution gap.

## Open Questions

- **Does every pier currently have its own Submit a Photo box already
  pasted into Carrd, or does the live site currently only have
  Sheboygan's?** This determines whether the ID collision risk is
  currently live right now, or was latent until more piers get
  rebuilt and republished.
- Carried from v54: **Is Port Washington a fully supported seventh
  pier**, or was its appearance in the Pick Your Pier list a mockup
  artifact? Still unresolved.
- Carried from v54: standalone `lure-pbsheb1sky` box — confirm with
  Paul whether to delete it now that `pbshb` v8 already contains
  Sky/Moon data in its own collapsible.

## Future Ideas

Unchanged from v54 (see preserved section below) — one global species
temperature slider, HOT PIER TODAY card, lazy-loading per pier,
St. Joseph MI as first east-shore pier.

## Next Session Instructions

**Exact prompt for Paul to paste into a new chat:**

> Continuing PIERBITE. Read Memory_PIERBITE_PROJECT_MEMORY_2026-09-11_v55.md
> in full before doing anything — this is the current file, it replaces v54.
> Tell me what you understand the current state to be. Confirm model identity
> by quoting the system prompt verbatim.
>
> This is a FORMATTING-ONLY session. Sheboygan is the template pier — its
> pbshb v8 (Sky, Moon & Forecast) box is the master color and radius
> reference (panel #112a3f, border #1f405b, muted text #a3bcd1, faint text
> #8aa2b6, link blue #5fb6f0, card radius 16px, toggle radius 12px). I will
> paste in Sheboygan's full current code as the confirmed template, then
> paste in the next pier's code. Reformat every box in that pier's code to
> match the master palette and radius — colors and rounding only, do not
> change any HTML structure, JavaScript, or content.
>
> Important: while reformatting, check every box's element ID for the
> generic-ID collision risk (see D416/D417 in the memory file) — this site
> is one long page with every pier stacked on it, so any box using a
> non-pier-specific ID will silently collide with other piers' copies of
> that box. Give any such box (starting with Submit a Photo, if this pier
> hasn't been fixed yet) its own unique ID in the pbsap-[piername] pattern.
>
> Standing rules: full replacement files only, never snippets. Filenames
> must be full plain-English names, never abbreviated box IDs — but state
> the literal box ID in the delivery message and in the internal HTML
> comment at the top of every file. One pier at a time, confirm each is
> correct on the live site before moving to the next.

**Reminder for Paul:** after uploading this file, delete
`Memory_PIERBITE_PROJECT_MEMORY_2026-09-04_v54.md` from Project Files.

---

# === EVERYTHING BELOW THIS LINE IS PRESERVED UNCHANGED FROM v54 ===

<!-- PIERBITE PROJECT MEMORY | 2026-09-04 | v54 | Major session: buoywatchC updated with live temperature dot marker (v2). Site redesign initiative launched — new home page direction approved (ChatGPT mockup reference: "Know Before You Go" headline, lighthouse hero photo, HOT PIER TODAY card, Pick Your Pier panel). GitHub images/hero/ folder created for per-pier hero photos. Sheboygan pier cleanup begun: pbsha v9 (DNR banner removed), pbshb v8 (Temperature Break, Pier Access, direction weights key, bottom attribution line removed; NOAA forecast + Sky/Moon merged into single collapsible section). Sheboygan lure box replaced with slim Sky/Moon-only box (lure-pbsheb1sky v2). Site-wide rebuild plan established: collect all pier box code into per-pier .txt files, rebuild one pier at a time starting with Sheboygan as template. Carrd backup duplicate site created before any changes. Supersedes v53 — delete Memory_PIERBITE_PROJECT_MEMORY_2026-09-01_v53.md from Project Files and upload this one. -->

# PIERBITE PROJECT MEMORY - 2026-09-04 v54

**THIS IS THE CURRENT REVISION. It supersedes v53.**
Nothing deleted — additive by design. Everything below this v54 section is
preserved byte-for-byte from v53.

## Project Overview

PierBite.com, six Wisconsin Lake Michigan pier fishing-conditions pages.
Paul is non-technical and relies entirely on Claude for all code.
Carrd Pro Plus frontend + Python/GitHub Actions backend.

## Site Rebuild Initiative (NEW — 2026-09-04)

Paul has decided to rebuild the site from scratch on a Carrd staging site,
eliminating clutter accumulated over time. A backup duplicate of the live
site was created in Carrd before any changes were made.

### What's being CUT from every pier page:
- Lure call / Today's Lure (eliminated entirely)
- Species activity slider (eliminated entirely — one global version may come later)
- Local suggestions / Food & Coffee (eliminated entirely)
- Pier Access (moved into collapsible section inside Pier B)
- Temperature Break section (eliminated)
- DNR fishing license banner (eliminated)
- Direction weights key table (eliminated)
- Bottom attribution line in Pier B (eliminated)
- Fish cleaning station box (delete the whole Carrd box — no replacement needed)

### What's being KEPT on every pier page:
- Pier score card (Pier A)
- Wind / weather stats (Pier A)
- Beach hazard alert (Pier A)
- 72-hour wind chart + ramp/legend (Pier B)
- Sky, Moon & Forecast (collapsible — Pier B)
- Pier Access (collapsible — Pier B)
- NOAA Marine Forecast (inside collapsible — Pier B)
- Water temp / buoy box
- Webcam (where it exists)
- Submit a Photo box (untouched)
- Fish cleaning box → DELETE the Carrd box entirely

### New collapsible pattern (established Sheboygan Pier B v8):
One button labeled "Sky, Moon & Forecast" — collapsed by default.
Opens to show: sunrise/sunset/moonrise/moonset grid + moon phase icon +
NOAA forecast below. Second button "Pier Access" — also collapsible.
This pattern will be replicated to all pier pages.

### Rebuild workflow (established this session):
1. Paul copies all pier box code into a single .txt file per pier
   (one box after another, separated by dashes)
2. Paul uploads the .txt file here
3. Claude reads the comments in each block to identify boxes
4. Claude rebuilds all boxes in one session, delivers all files
5. Paul pastes each file into the correct Carrd box
6. Test one pier fully before moving to next

### Sheboygan rebuild status:
- **pbsha v9** — delivered, DNR banner removed. Goes into box `pbsha`.
- **pbshb v8** — delivered, Temperature Break + Pier Access + direction
  weights key + bottom attribution removed. Sky/Moon + NOAA forecast merged
  into single collapsible. Goes into box `pbshb`.
- **lure-pbsheb1sky v2** — delivered, slim Sky/Moon only (no lure call,
  no species chips, no disclaimer). Goes into existing lure box.
  NOTE: Paul chose pbshb v8 which already includes Sky/Moon inside the
  collapsible — the standalone lure-pbsheb1sky box may be redundant now.
  Confirm with Paul whether to delete it or keep it.
- **Suggestions box** — delete the Carrd box entirely (no replacement)
- **Species box** — delete the Carrd box entirely (no replacement)
- **Fish cleaning box** — delete the Carrd box entirely (no replacement)

### Per-pier .txt files received so far:
- `sheboygan.txt` — received and processed ✓
- All other piers — not yet received

## buoywatchC update (2026-09-04)

**buoywatchC v2** — live temperature dot/marker added to the gradient bar.
Fetches data.json, averages all six pier shore model temps, places a white
marker line at the correct position on the gradient with "XX.X°F avg" label
above it. Root cause of initial blank render: content div was outside the
`#bwc` wrapper div so CSS scoping didn't apply. Fixed in v2.
3,711 bytes, 12,673 margin.

## Home Page Redesign (NEW — 2026-09-04)

### Approved direction:
- **Headline:** "Know Before You Go." (Option C — chosen by professional
  judgment)
- **Subline:** "Live fishing conditions for six Lake Michigan piers on
  Wisconsin's west shore — scored every hour so you never drive to the wrong pier."
- **Hero photo:** One dramatic lighthouse/pier photo (master: `pierbite-hero.jpg`)
  stored in `images/hero/` GitHub folder
- **Reference mockup:** ChatGPT-generated screenshot Paul shared showing
  lighthouse background, icon strip (Wind/Water/Waves/Bite Index/Daily Outlook),
  HOT PIER TODAY card with pier photo, Pick Your Pier panel on right

### Per-pier hero photos:
- GitHub folder `images/hero/` created (via `.gitkeep` placeholder)
- Naming convention: `pierbite-hero.jpg` (master), `manitowoc-hero.jpg`,
  `sheboygan-hero.jpg`, `two-rivers-hero.jpg`, `kewaunee-hero.jpg`,
  `algoma-hero.jpg`, `sturgeon-bay-hero.jpg`, `port-washington-hero.jpg`
- Photos not yet uploaded — Paul gathering them

### Home page rebuild:
- Need Carrd layer names from live home page before building
- Paul has not yet provided the home page layers screenshot
- This is the next priority after Sheboygan pier cleanup is confirmed working

## Buoy Watch page — Code Embed boxes (confirmed live as of v53)

1. **buoywatchA** — map. v12, 16,065 bytes, 319 bytes margin. TIGHT.
2. **buoywatchD** — wind-direction arrows. v1.
3. **buoywatchC** — water-temperature legend + live temp dot. v2, 3,711 bytes.
4. **bouyb** (in bouyb container) — header + coldest-water ranking. v6.
5. **bouye** (in bouyb container) — fish/lake SVG + Back to Map. v3.

## Home page nav widget

**pbfbw** — v11, 3,828 bytes. Nav link order:
1. Why Wind = Better Bites → (#wind)
2. Water Temperature Now → (#bouyb)
3. Wind at a Glance → (#compare)
4. Buoy Watch → (#buoywatch)

## Current Status

- **Sheboygan pier cleanup in progress** — pbsha v9 + pbshb v8 delivered,
  not yet confirmed live by Paul. Three boxes to delete in Carrd.
- **Home page redesign approved** — not yet built. Needs home page layer names.
- **Hero photos** — folder created, photos not yet uploaded.
- **St. Joseph MI probe** — second run still pending.
- **Compare Piers NOAA LMHOFS attribution fix** — still outstanding.
- **Carrd backup site** — created by Paul before this session's changes.

## Completed Work (this session)

- buoywatchC v2 — live temp dot on gradient bar, CSS scoping bug fixed
- pbsha v9 — DNR banner removed
- pbshb v8 — major cleanup, collapsible Sky/Moon/Forecast section
- lure-pbsheb1sky v2 — slim Sky/Moon only box
- GitHub `images/hero/` folder created
- Home page headline direction approved: "Know Before You Go."
- Carrd backup duplicate site created
- Sheboygan .txt file received and all box IDs mapped

## Remaining Tasks

1. **Confirm Sheboygan rebuild live** — Paul needs to paste pbsha v9 +
   pbshb v8 into backup site and confirm they look correct
2. **Delete three Sheboygan boxes** — Suggestions, Species, Fish Cleaning
3. **Confirm lure box situation** — pbshb v8 already has Sky/Moon inside
   collapsible; standalone lure-pbsheb1sky may be redundant. Confirm with Paul.
4. **Home page layers screenshot** — need Paul to open home page in Carrd
   editor and screenshot the Layers panel
5. **Hero photos** — Paul to gather and upload to `images/hero/`
6. **Replicate Sheboygan cleanup to remaining 5 piers** — need .txt files
   for Manitowoc, Two Rivers, Kewaunee, Algoma, Sturgeon Bay
7. **Compare Piers NOAA LMHOFS attribution fix** — still outstanding
8. **St. Joseph MI probe run #2** — still unblocked, still not done

## Decisions Log

*(New entries this session — D406 onward.)*

- **D406 (headline choice):** "Know Before You Go." chosen over all other
  options by professional design judgment. Rationale: universally understood
  fishing phrase, the subline delivers the factual backup, together they
  solve the core problem (visitor doesn't know what site is in first 2 seconds).
- **D407 (collapsible forecast pattern):** Sky/Moon and NOAA forecast merged
  into single collapsible section in Pier B. Collapsed by default to reduce
  page length. Moon data no longer needs its own separate box — it lives
  inside Pier B's collapsible. The standalone lure box was rebuilt as a
  slim Sky/Moon-only box but may now be redundant.
- **D408 (Pier Access collapsible):** Paul initially wanted Pier Access
  added as a second collapsible in Pier B (v9). Then decided to skip it
  to keep the page shorter. pbshb v8 is the accepted version — no Pier Access.
- **D409 (fish cleaning content):** Paul decided anglers don't need to be
  told where to clean fish — they already know. Delete the fish cleaning
  Carrd box entirely, no replacement content needed.
- **D410 (rebuild workflow):** Established per-pier .txt file approach.
  Paul copies all box code into one file per pier (excluding Submit Photo
  and Fish Cleaning boxes which are either untouched or deleted).
  Claude reads box comments to identify each block, rebuilds in one session.
- **D411 (buoywatchC CSS scoping bug):** Content div was placed outside
  the `#bwc` wrapper div, so all CSS rules prefixed with `#bwc .class`
  never reached the content. Fix: move all content inside `#bwc`. This
  is the same pattern as buoywatchA. Standing rule: always verify the
  root wrapper div wraps ALL content, not just the script tag.
- **D412 (hero photo naming):** Master home page photo: `pierbite-hero.jpg`.
  Per-pier photos: `[pier-name]-hero.jpg` with hyphenated lowercase pier names.
  All stored in `images/hero/` GitHub folder.

## Reasoning Ledger

- **Why Sky/Moon was merged into Pier B instead of staying as its own box:**
  Paul's core goal is a shorter, less cluttered page. A separate box for
  moon data adds visual weight. Inside a collapsible in Pier B it takes
  zero space when closed and still delivers the data when needed.
- **Why fish cleaning content was dropped entirely:** Paul's judgment —
  experienced Lake Michigan anglers don't need directions to clean fish.
  Keeping it was adding page length with no value to the target audience.
- **Why the direction weights key was removed from Pier B:** Same principle —
  the technical weighting table (S=+1.00, WNW=+0.54, etc.) is engineering
  detail that clutters the page. The colour ramp legend (South-West /
  Neutral / North-East) still communicates the concept without the numbers.

## Technical Details

- **pbshb v8 byte count:** ~14,538 bytes, ~1,846 margin. Snug but safe.
  Do not add more content to this box without splitting first.
- **buoywatchC v2:** 3,711 bytes. Live dot position calculated by mapping
  temp through the same 7-stop gradient used in buoywatchA's tempColor().
  Stops: 32/44/51/60/67/74/85°F. Pct position uses segment-proportional
  mapping (not linear min-max) to match the actual CSS gradient stops.
- **File naming rule (reinforced):** filename must start with the literal
  Carrd box ID. Example: `pbsha-2026-09-04-v9.html`, `pbshb-2026-09-04-v8.html`.
  The box ID also appears in the internal HTML comment at the top of the
  file. **[SUPERSEDED BY v55 D415 — filenames are now full plain-English
  names, not abbreviated box IDs; box ID still required in the comment and
  delivery message only.]**

## User Preferences (additions this session)

- Paul wants file titles to include the box ID at the front AND inside
  the code comment — both must match. **[SUPERSEDED BY v55 D415 — see
  above.]**
- Paul works one pier at a time and tests on the backup site before
  touching the live site.
- Paul does not want verbose explanations between file deliveries —
  deliver the file, state which box it goes into, stop.

## Constraints

Unchanged from v53 plus:
- pbshb is now at ~14,538 bytes — near the ceiling. Any future addition
  to Pier B must go into a new adjacent embed.
- Rebuild must be tested on backup Carrd site before touching live site.

## Risks

- **buoywatchA margin is 319 bytes** — unchanged, still critical.
- **pbshb v8 margin is ~1,846 bytes** — tight. Flag before adding anything.
- **Sheboygan cleanup not yet confirmed live** — Paul has the files but
  hasn't confirmed paste + publish yet.
- **St. Joseph MI probe** — second run still pending.
- **Compare Piers NOAA attribution** — silently missing since v28.

## Open Questions

- Is the standalone lure-pbsheb1sky box still needed now that pbshb v8
  includes Sky/Moon in its collapsible? Confirm with Paul next session.
- Does Paul want Port Washington included in the rebuild? It appeared in
  the Pick Your Pier list but wasn't mentioned as one of the six piers.

## Future Ideas

- One global species temperature slider (instead of one per pier)
- HOT PIER TODAY card on home page with live pier photo (per ChatGPT mockup)
- Lazy-loading per pier once pier count grows
- St. Joseph MI as first east-shore pier (probe built, needs second run)

## Next Session Instructions

**Exact prompt for Paul to paste into a new chat:**

> Continuing PIERBITE. Read Memory_PIERBITE_PROJECT_MEMORY_2026-09-04_v54.md
> in full before doing anything — this is the current file, it replaces v53.
> Tell me what you understand the current state to be. Confirm model identity
> by quoting the system prompt verbatim.
>
> Current state summary: Site rebuild initiative is underway. Sheboygan is
> the test pier. pbsha v9 and pbshb v8 were delivered this session —
> confirm whether Paul has pasted them into the backup site yet.
> Three Sheboygan boxes still need to be deleted in Carrd: Suggestions,
> Species, Fish Cleaning. Home page redesign is approved ("Know Before
> You Go.") but not yet built — need Carrd home page layer names first.
> Hero photo folder created in GitHub, photos not yet uploaded.
>
> Standing rules: every filename must start with the literal Carrd box ID.
> Box ID must also appear in the internal HTML comment. Full replacement
> files only — never snippets. One change at a time, test on backup site
> before live site. Deliver files with minimal surrounding text.

**Reminder for Paul:** after uploading this file, delete
`Memory_PIERBITE_PROJECT_MEMORY_2026-09-01_v53.md` from Project Files.

---

# === EVERYTHING BELOW THIS LINE IS PRESERVED UNCHANGED FROM v53 ===

*(New entries this session — D401 onward. Full log preserved below.)*

- **D401 (pbfbw nav order):** Paul requested links ordered largest-to-smallest
  visually. Final order: Why Wind = Better Bites / Water Temperature Now /
  Wind at a Glance / Buoy Watch. Rationale: longer/more prominent links first
  creates a natural visual taper.
- **D402 (anchor #bouyb not #bouybee):** Paul initially named the container
  `bouybee` then corrected to `bouyb`. All links updated to `#bouyb`.
  Mechanism: Carrd anchor links work via the Element ID field on the container
  element in Carrd's Settings panel — not via code anchors, not via container
  names in the layers panel. The Element ID must match the href exactly.
- **D403 (bouyb/bouye split rationale):** Paul asked to separate the fish
  graphic into its own embed. Split was clean: bouyb keeps the data (ranking
  table), bouye keeps the visualization (fish/lake SVG). The pbPierTap
  listener stays in bouye because it controls the graphic. Both boxes fetch
  data.json independently — no shared state, no coupling.
- **D404 (Back to Map placement):** First attempt placed the link below the
  SVG div — Paul said it was "practically out of sight." Moved inside the SVG
  itself as a native SVG `<a>` + `<rect>` + `<text>` green pill in the
  bottom-left of the lake graphic. This is always visible when the graphic
  is on screen. Mechanism: SVG `<a href>` with `xlink:href` for compatibility,
  positioned at y=392 in the 430-unit-tall viewBox.
- **D405 (stale remaining-tasks corrected):** Paul confirmed email alerts
  CANCELED, Cloudflare proxy CANCELED, photo galleries DONE,
  Q-BUOY-OPENLAKE-DOUBLE already fixed. The userMemories system had not caught
  up with these completions/cancellations — always treat Paul's direct
  statement as authoritative over memory entries when they conflict.

## Reasoning Ledger

- **Why bouyb and bouye each fetch data.json independently rather than
  sharing:** Carrd Code Embed boxes are fully isolated — no shared JS scope,
  no DOM communication except via events. Each box must be self-sufficient.
  The extra fetch is negligible (data.json is tiny, GitHub raw CDN is fast).
- **Why the Back to Map button is inside the SVG rather than below it:**
  The SVG graphic fills the visible viewport when a user scrolls to bouye
  after tapping a pier dot. Anything below the SVG closing tag is below the
  fold and effectively invisible until they scroll further. Embedding the
  button inside the SVG guarantees it's always co-visible with the graphic
  that prompted the scroll.
- **Why the file naming deviation happened this session:** Claude initially
  named files with descriptive suffixes (Shared_home_feedback, Shared_bouy_b_
  watertemp) rather than the literal Carrd box ID. Paul called this out via
  screenshot. The correct pattern is confirmed: prefix = folder, then literal
  box ID, e.g. `Shared_pbfbw-2026-09-01-v11.html`, `Shared_bouyb-2026-09-01-v6.html`.

## Technical Details

*(Additions this session — full technical details preserved below.)*

- **bouyb box ID:** `bsb2` (div id inside the embed). CSS namespace `#bsb2`.
- **bouye box ID:** `bse2` (div id inside the embed). CSS namespace `#bse2`.
  Uses same CSS classes as bouyb but scoped to `#bse2` to avoid conflicts
  when both boxes are on the same page.
- **pbPierTap event flow:** buoywatchA fires `window.dispatchEvent(new
  CustomEvent('pbPierTap', {detail:{id:'m'+pierKey}}))` when a pier dot is
  clicked. bouye listens for this event and calls `xsHTML(p)` to re-render
  the cross-section for the selected pier, then smooth-scrolls to `#bsbX`.
- **Back to Map SVG link:** `<a href="#buoywatch" xlink:href="#buoywatch">
  <rect x="16" y="392" width="136" height="26" rx="13" fill="#8fd43c"/>
  <text x="84" y="410" ...>↑ BACK TO MAP</text></a>` — positioned in
  bottom-left of the 900×430 viewBox lake illustration.
- **bouyb container Element ID:** `bouyb` (set in Carrd's Settings panel
  for the container element). Home page link href="#bouyb".
- **Buoy Watch container Element ID:** `buoywatch` (pre-existing). bouye's
  Back to Map button links to `#buoywatch`.

## Design Decisions

*(Additions this session — prior design decisions preserved below.)*

- **bouyb header design:** PierBite.com logo (white "Pier" + green "Bite" +
  gray ".com", Barlow Semi Condensed bold) + "LAKE MICHIGAN WATER REPORT"
  small-caps blue label + "WATER TEMPERATURE NOW" large bold white title +
  gold (#7a5c1e) bottom border. Matches the pier page header style exactly
  (per screenshot reference Paul provided of Sturgeon Bay pier page).
- **Nav link order in pbfbw:** longest/most prominent first, tapering to
  shorter. Why Wind = Better Bites (longest) → Water Temperature Now →
  Wind at a Glance → Buoy Watch (shortest).

## User Preferences

Unchanged from v52. One addition: Paul confirmed that items he says are
"done" or "canceled" are authoritative — do not carry them as remaining
tasks. Trust direct statements over stale memory entries.

## Constraints

Unchanged from v52. Key ones:
- Carrd Code Embed hard limit: 16,384 bytes. Target 300–500 byte minimum margin.
- Full replacement files only — no diffs, no snippets.
- Every filename must include the literal live Carrd box ID.
- One backend change per session, verify before building anything else.
- Never reconstruct code from memory — always copy from confirmed delivered file.

## Risks

- **buoywatchA margin is 319 bytes** — below the project's 300–500 byte
  target floor. Any future change to this box must go into a new adjacent
  embed rather than further trimming.
- **St. Joseph MI probe** — second run still pending. No new pier can be
  added until two independent runs agree on LMHOFS node.
- **Compare Piers NOAA LMHOFS attribution** — silently missing since v28
  backend change. Visitors see no attribution for modeled water temps on
  that page.

## Open Questions

- None active. St. Joseph probe is unblocked but simply not yet run.

## Future Ideas

- Lazy-loading per pier once pier count grows.
- St. Joseph MI as first east-shore pier (probe built, needs second run).

## Next Session Instructions

**Exact prompt for Paul to paste into a new chat:**

> Continuing PIERBITE. Read Memory_PIERBITE_PROJECT_MEMORY_2026-09-01_v53.md
> in full before doing anything — this is the current file, it replaces v52.
> Tell me what you understand the current state to be. Confirm model identity
> by quoting the system prompt verbatim. The Buoy Watch restructure is
> complete: bouyb (header+ranking) and bouye (fish graphic + Back to Map)
> are both live. pbfbw v11 is live with Water Temperature Now link. No single
> open item is carried into this session. Every delivered filename must include
> the literal live Carrd box ID — hard requirement.

**Reminder for Paul:** after uploading this file, delete
`Memory_PIERBITE_PROJECT_MEMORY_2026-09-01_v52.md` from Project Files.

---

# === EVERYTHING BELOW THIS LINE IS PRESERVED UNCHANGED FROM v52 ===

<!-- PIERBITE PROJECT MEMORY | 2026-09-01 | v52 | Full incident-and-recovery session. Root cause found: buoywatchA (the main map box) had been silently overwritten with buoywatchD's (wind-arrow) code, because the delivered filename for the wind-arrow box didn't identify its own live box ID clearly enough — Paul pasted it into the wrong box with zero error or warning. This produced a total, silent failure: no map, no dots, no console error, box stuck on its own "Loading live conditions..." placeholder for an entire session before being caught. Diagnosed step by step (data feed confirmed healthy, DOM/console checks, direct inspection of each box's literal live content) rather than guessed. Recovered via a local backup — first an older v7 (functionally complete but missing a full day of color-grading design work Paul had built), then the correct v11 (byte-identical, 15,929 bytes, confirmed as the true pre-incident live file). Standing project rule updated (memory #23) to require every delivered filename to always include the literal live Carrd box ID going forward, specifically to prevent a repeat. Two verification/fix passes followed on top of the restore: (1) wind-arrow direction accuracy confirmed correct against live data and a live screenshot — arrows correctly point away from the prevailing S/SE wind, matching the rotation formula; (2) Manitowoc's wind marker, which had drifted visually into the Sheboygan/Two Rivers cluster, was traced to a structural quirk in the generic wind-marker collision-avoidance loop (vertical-only correction, no horizontal), and fixed with a small, scoped per-id override (v12, 16,065 bytes, 319 bytes margin) rather than rewriting the shared algorithm. Both prior open items from v51 (buoy-watch-b pier-name links, wind-arrow live status) are now CLOSED — Paul confirmed both working directly. Supersedes v51 - delete Memory_PIERBITE_PROJECT_MEMORY_2026-09-01_v51.md from Project Files and upload this one. -->
