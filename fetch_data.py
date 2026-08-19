"""
PierBite.com — Live Data Fetcher
Fetches current buoy, marine-zone forecast, and satellite water
temperature data from public NOAA/NWS sources and writes the
combined result to data.json. No API key or paid account required.

Updated 2026-08-19 (v20, decisions D204/D205/D207): the LMHOFS nowcast
file this script reads changed from fields.n000.nc to fields.n006.nc.
n000 is valid SIX HOURS BEFORE the model cycle it belongs to; n006 is
valid AT the cycle. Production had been reading n000 while publishing
the cycle time beside it, so every water temperature on the site was six
hours older than it claimed, and the D82 age thresholds (disclose at 12h,
refuse at 36h) each understated true data age by six hours. This is a
one-constant change: LMHOFS_FIELDS_FILE feeds BOTH read sites, so the
72-hour trend shifts at both ends and its measured window is unchanged.
No score, weight, factor, key, or threshold value was touched — the same
numbers now mean what they say. See the constant's own comment for the
full mechanism and for why it must never be split into two constants.

Updated 2026-08-03 (v19, decision D182): score_wind() now returns
"LIVE_STALE" instead of "LIVE" when a non-borrowed wind reading is
older than STALE_AFTER_HOURS (3h) — the same threshold already
published to the frontend in v17. Fixes the actual root cause behind
R71/D173: the green "Measured" dot was hardcoded from source code
alone with zero age check, so a stale-but-real reading and a
fresh one were visually identical. ESTIMATED (borrowed) readings are
untouched — that tier already has its own distinct meaning and this
does not overload it. FORECAST and unavailable branches are untouched.
No score, weight, or factor changed — this only relabels the source
string a frontend uses to choose a dot color.

Updated 2026-08-02 (v18, decision D173, closes R71): wind_headline now
carries "observed_at_utc" and "age_hours" for every pier, in every
branch (measured / forecast / unavailable). Fixes a real honesty gap:
previously a 9-hour-old wind reading displayed as a filled "Measured"
dot with no way for the frontend to know it was stale — the object had
no timestamp of any kind even though the station_history record it was
built from carried one one line away. PURELY ADDITIVE: two new keys
only, no existing key removed or changed, no scoring or tier logic
touched. observed_at_utc is null on forecast/unavailable branches
because there is no real observation to timestamp in those cases.

Updated 2026-07-17: added Algoma — dormant AGMW3 wind station (wired
for automatic reactivation), shared LMZ542 marine zone codename
"algz", and a dormant GLSEA satellite point for Algoma harbor. Also
wired Sturgeon Bay's 0Y2W3 CG station dormant ahead of that pier's
build.

Updated 2026-07-17 (v5, scoring engine — rebuilt after the original
v5 session was cut off before delivery): the 0-100 Bite Index
scoring engine now lives HERE in the backend instead of being
copy-pasted into every page. Adds a finished "piers" section to
data.json (score, band, factor breakdown, honesty labels per pier),
plus "hot_piers_today", "schema_version", and "stale_after_hours".
Includes two scoring fixes: (1) a pier missing water temp from ALL
sources is capped at 55 and marked incomplete instead of stretching
its remaining factors, and (2) warm-water hard caps now apply to
satellite and estimated temps too, not just live buoy readings.
PURELY ADDITIVE: every section v4 wrote is still written unchanged
under the same keys, so no live page breaks on deploy.

Updated 2026-07-18 (v6, Sturgeon Bay final configuration): added the
KSUE wind-history station (Door County Cherryland Airport, Sturgeon
Bay) and replaced Sturgeon Bay's provisional pier entry with the
confirmed build-session decisions — zone LMZ542, KSUE as live local
wind behind the dormant canal CG station, and a corrected water
borrow chain (Two Rivers buoy, then independent northern-lake buoy
45002; the old second fallback was the same physical buoy twice).
No other pier's configuration or any output key changed.

Updated 2026-07-18 (v7, Washington Island removed): the owner decided
not to cover Washington Island — it is ferry-access only with a small
pier, so it doesn't belong in a "where should I fish today" decision.
Removed: the washington_island pier config, the K2P2 wind-history
station (island airport, used by no other pier), and marine zone
LMZ541 (used by no other pier). DELIBERATELY KEPT: buoy 45002
(northern Lake Michigan) — Sturgeon Bay depends on it as its
independent water-temp backup; its label still mentions the
Washington Island area because that is simply where the buoy floats.
Side effect (intended): the HOT PIER TODAY badge can no longer go to
Washington Island; it now falls to the best-scoring pier with LIVE
water data among the six covered piers.

Updated 2026-07-22 (v8, warm-water cap now visible to the frontend):
the warm-water hard cap (FIX 2 above) was already lowering scores
correctly, but the JSON gave the frontend no way to tell "this pier's
true score is 44" apart from "this pier's score was pulled DOWN to
44 by the warm-water cap." On a day when water is warm along the
whole coast, every pier can legitimately land on the same capped
number, which looked like fake/static data to a site visitor even
though it was real. Added a new "capped" object to each pier's
output — {"active": true/false, "reason": "..."} — set only when the
cap actually changed the score (not just because the pier happens to
be warm). PURELY ADDITIVE: no existing key's value changes, this is
one new key per pier.

Updated 2026-07-24 (v9, wave curve + real Storm/Clarity factor +
Beach Hazards Statement banner — decided after direct discussion
with the owner about why scores clustered around 40 on ordinary bad
days, and after the owner spotted a live bug via screenshot: a calm
1.3ft day scored the same "Lake Conditions: 24" as a genuinely rough
day, because ANY active marine alert force-capped Lake Conditions to
24 regardless of actual wave height):

  FIX A — alerts were only ever fetching the FIRST active alert per
  zone. A Small Craft Advisory and a Beach Hazards Statement often
  fire at the same time for the same event (one is for boaters, one
  is for swimmers/piers) — the old code could silently drop one of
  them. fetch_zone_alerts() now returns every active alert. The old
  single-alert shape (zone["alert"] = {"active", "headline", "event",
  "severity", "effective_utc", "expires_utc"}) is left completely
  unchanged for backward compatibility — it is still the FIRST alert
  found, same as before. NEW, additive: zone["alerts"] = a full list
  of every active alert, in the same shape, plus a "description"
  field (the raw NWS text) on each one.

  FIX B — NEW: zone["beach_hazard"] — a dedicated object, separate
  from the Bite Index score entirely, populated only when a real NWS
  "Beach Hazards Statement" is active for that zone. Includes the
  official headline, the raw description text, and (when the NWS
  text follows its usual "Waves X to Y ft" pattern) a parsed
  wave_range_ft. This is specifically the NWS product built for
  shore/pier danger (as opposed to Small Craft Advisory / Gale
  Warning, which are calibrated for boaters) — confirmed against
  real NWS Beach Hazards Statement text before building this, not
  assumed. Surfaced on the frontend as its own banner, NOT folded
  into the score.

  FIX C — Lake Conditions (waves) scoring replaced. OLD: a flat
  4-tier lookup (<=1.5ft=90, <=3ft=72, <=5ft=38, anything above
  5ft=14 no matter how much above), PLUS a blunt rule that forced
  the score down to 24 whenever ANY alert was active, regardless of
  actual wave height (this is the bug the owner's screenshot caught
  live — 1.3ft waves scoring a "24" only because a Small Craft
  Advisory happened to be active). NEW: score_waves() is now a
  smooth curve that keeps responding as waves get worse all the way
  up past 12ft, and the alert-based override is REMOVED — Lake
  Conditions now honestly reflects the real measured/forecast wave
  height only. Safety messaging for rough conditions is handled by
  the Small Craft Advisory banner (unchanged, already live) and the
  new Beach Hazards banner (FIX B) instead of by silently distorting
  the score.

  FIX D — the Clarity/Storm factor (20% of the score's weight) was
  defined in the factor list from day one but NEVER actually
  computed — every pier's score has only ever really been an average
  of 3 factors out of the intended 4. NEW: score_storm_severity()
  turns this on for real, using the worst currently-active
  boater/fishing-relevant marine alert for that zone (Small Craft
  Advisory, Gale Warning, Storm Warning, Dense Fog/Smoke) — using the
  full alerts list from FIX A, not just the first alert. Beach
  Hazards Statements are DELIBERATELY excluded from this factor —
  they're about swim/pier safety, not fishing quality, and are
  represented by their own banner (FIX B) instead.

  NOTE ON SCORES CHANGING: FIX C and FIX D are an intentional,
  discussed change to the actual score values (not just new fields)
  — bad days will now score meaningfully lower than before, and every
  score is now a real 4-factor average instead of a 3-factor one.
  This was decided deliberately with the owner, not a side effect.
  The JSON *structure* itself remains additive: no key was removed or
  renamed, "alert" (singular, first-found) still works exactly as
  before for anything still reading it.

Updated 2026-07-26 (v10, station geography - Phase 1.2 of the honesty
rebuild). This release adds NO new data source and changes NO score. It
answers one question the site could not previously answer: WHERE is each
number actually measured, and how far is that from the pier?

  WHY IT MATTERED - buoy 45210 was labelled "Two Rivers / Manitowoc area
  buoy" and all six piers read it. NOAA's own station table calls it
  "Rawley Point East, WI". It floats 26 miles off Two Rivers in 475 ft of
  water, and Sturgeon Bay - 52 miles away - displays its reading as
  Sturgeon Bay's water temperature. None of that was visible in the code
  or on the site. Decision D14 requires a real distance on every measured
  value, computed by the backend and never hand-written. Until now the
  backend had no coordinates to compute from.

  WHAT CHANGED
  1. Every station in STATIONS and STATION_HISTORY carries its real
     published lat/lon. NOT typed from memory - fetched from NOAA by
     station-coordinates-probe-2026-07-26-v1.py, run inside GitHub
     Actions on 2026-07-26, cross-checked between two NOAA sources.
  2. Every pier in PIERS carries its verified lat/lon (confirmed against
     a map by the owner on 2026-07-25, decision D63).
  3. NEW haversine_miles() computes real great-circle distances.
  4. Buoy 45210 relabelled to its true NOAA name.
  5. KSUE's label had "about 7 miles from the canal pier" hand-written
     into it. The real computed distance is 6.4 mi. The hand-written
     figure is removed - distance now comes from calculation, per D14.
  6. Removed a DEAD reference: Two Rivers' water_fallbacks listed a
     source codenamed "kw1" that is defined nowhere in STATIONS. It
     silently resolved to nothing on every run while making the config
     look as though Two Rivers had a Kewaunee backup. It had none.
  7. resolve_water() now also reports WHICH source it used, so the
     distance to that specific source can be computed.

  NEW OUTPUT KEYS (all additive - no existing key changes value):
    stations.<code>.lat / .lon / .water_depth_ft
    station_history.<code>.lat / .lon
    piers.<pier>.coordinates                          {lat, lon}
    piers.<pier>.headline.water_temp_station_label
    piers.<pier>.headline.water_temp_distance_mi
    piers.<pier>.headline.wind_station_label
    piers.<pier>.headline.wind_distance_mi

  WHY DISTANCE LIVES ON THE PIER, NOT THE STATION: one station can serve
  two piers at different distances. KMTW is 5.9 mi from Two Rivers and
  3.5 mi from Manitowoc. A single distance stored on the station would be
  wrong for one of them.

  MECHANISM FACT - for BUOYS trust the NDBC station table, not the NWS
  API. The NWS API rounds buoy positions to one decimal place: it
  reported 45210 at 44.100/-87.100 when the true position is
  44.055/-87.050, a 4-mile error. For LAND AIRPORT stations the reverse
  holds - the NWS API gives full precision and the NDBC table does not
  list them at all.

  SECOND MECHANISM FACT - the "elevation" the NWS API returns for a lake
  buoy (about 176 m) is the LAKE SURFACE height above sea level, NOT the
  water depth under the buoy. Publishing it as depth would look entirely
  plausible and be completely wrong.

Updated 2026-07-27 (v11, Phase 1.3a - NEARSHORE WATER TEMPERATURE FROM
LMHOFS). This is the release the whole honesty rebuild was building
toward. It changes what number the site publishes, on purpose.

  THE PROBLEM IT FIXES - all six piers read their water temperature
  from ONE buoy: NDBC 45210, "Rawley Point East", floating 26 miles off
  Two Rivers in 475 feet of open water. Sturgeon Bay displayed that
  same reading from 52 miles away. Deep open lake and a 7-foot-deep
  pier are not the same body of water. Measured 2026-07-25, the buoy
  read roughly 12-18 F WARMER than the actual nearshore temperature at
  the piers. Because the scoring engine applies a tiered warm-water cap,
  that single wrong number pinned every pier on the site to an identical
  score - 44 for weeks, then 28, then 44 again - which looked to a
  visitor like fabricated data. It was real. It was just measured in the
  wrong place.

  THE FIX - NOAA's Lake Michigan-Huron Operational Forecast System
  (LMHOFS) is a 3D hydrodynamic model on an unstructured mesh of 90,806
  nodes, with roughly 50 m resolution along the shoreline. It simulates
  upwelling, which is the exact phenomenon this site exists to report.
  Six mesh nodes - one per pier, the closest 0.012 mi and the farthest
  0.249 mi from the pier itself - now supply water temperature ahead of
  any buoy in the chain.

  THIS IS LABELLED "MODELED", NEVER "MEASURED" (project constraint C13,
  decision D64). It was validated against buoy 45210's own thermometer
  on 2026-07-25 and agreed within 2 F. Validation raised confidence in
  the model. It did not turn a simulation into a thermometer.

  WHAT CHANGED
  1. NEW fetch_lmhofs() - locates a live model run, reads temperature
     plus each node's OWN published lat/lon, and computes the real
     pier-to-node distance from those fetched coordinates. Nothing is
     hand-written, not even the node positions (C19).
  2. resolve_water() now tries LMHOFS FIRST, ahead of the local buoy.
     New source tier "MODELED" / source_kind "model".
  3. STALENESS POLICY (decision D82) - under 12 h: normal. 12 to 36 h:
     still used, and the model run age is published so a page can
     disclose it. Over 36 h, or unreachable: LMHOFS is skipped entirely
     and the pier falls through to its existing chain with the real
     distance shown. Rationale: 12 h absorbs one or two missed NOAA
     cycles invisibly; beyond 36 h the model is describing a different
     weather regime, because upwelling can set up and collapse inside a
     single day. Falling through to a clearly-labelled distant buoy is
     more honest than six piers all reporting "unknown".
  4. compute_hot_piers() now accepts MODELED as well as LIVE (D83).
     WITHOUT THIS THE BADGE VANISHES SITEWIDE THE MOMENT THIS DEPLOYS -
     silently, with nothing in the logs, because no pier would report
     LIVE water any more. Found by tracing the consequence before
     deploying rather than after.
  5. verified_count FIXED (risk R26). It was computed as "scored factors
     minus ESTIMATED factors", so a FORECAST factor counted as verified
     - and a MODELED one would have too. The frontend prints this number
     as "N of 4 factors measured live". Sheboygan was claiming 3 when
     only 1 factor was genuinely measured. It now counts ONLY factors
     whose source is literally LIVE. THIS LOWERS THE NUMBER ON FOUR
     PIERS TODAY. That is a correction, not a regression.
  6. NEW headline keys wave_station_label and wave_distance_mi (D86).
     The Two Rivers pier boxes are already written to consume them.
  7. NEW output["open_lake_context"] - buoy 45210's reading published
     BESIDE the nearshore model value, with the gap between them. The
     buoy stops being a temperature source here but keeps earning its
     place: that gap is the visible evidence of upwelling. Costs no
     extra request; the buoy is fetched anyway.
  8. NEW validate_config() - every codename referenced by a pier is
     checked against the config that defines it. The dead "kw1"
     reference removed in v10 had resolved silently to nothing for
     months and NOTHING FAILED, because nothing could. Findings are
     printed and published under output["config_warnings"]. Deliberately
     warns rather than aborts: a stale-but-correct data.json beats an
     outage.

  MECHANISM FACT - NOAA's THREDDS server runs on Tomcat, which rejects
  raw "[" and "]" in a query string with HTTP 400. Array slice requests
  MUST be percent-escaped as %5B / %5D. This hides well: requests with
  no brackets (?lat, ?lon) succeed either way, so code can look healthy
  right up until it asks for a data slice.

  SECOND MECHANISM FACT - NOAA does NOT put the word "nowcast" in the
  FIELDS filenames. "fields.n000.nc" is the nowcast (what happened);
  "fields.f000.nc" is the forecast. Only the much smaller stations files
  carry "nowcast" in the name. Filtering fields files on "nowcast"
  matches nothing at all.

  SECOND MECHANISM FACT, PART TWO (v20) - A NOWCAST FILE IS NOT VALID AT
  ITS OWN CYCLE TIME. The nnn in fields.nNNN.nc is an hour offset into a
  run that covers the six hours ENDING at the cycle. n000 is valid six
  hours BEFORE the cycle time; n006 is valid AT it. This is invisible
  from the filename and from the directory listing, and it was wrong in
  production for months. STANDING RULE (D207): valid time is READ FROM
  THE FILE - the Times variable, or the numeric time variable against
  the epoch in the .das - and NEVER inferred from a filename.

  THIRD MECHANISM FACT - siglay index 0 is the SURFACE layer, confirmed
  by measurement on 2026-07-25 rather than assumed (D65). Index 0 could
  just as plausibly have been the lake bed, and would have returned a
  perfectly believable cold number.

  FOURTH MECHANISM FACT - the file may publish longitude in 0-360 form.
  Any code reading a node's longitude must subtract 360 when the value
  exceeds 180, or the point lands in central Asia.

  GUARD AGAINST SILENT MESH RENUMBERING (risk R21) - a frozen node index
  is only meaningful while NOAA's mesh has the same shape. If the node
  count is no longer 90,806, the indices point somewhere else entirely
  and would return a plausible temperature from the wrong place. Two
  layers of defence: (a) the file's own DDS is read once per run and the
  node count checked; (b) every node's own lat/lon is fetched and the
  distance to its pier verified against LMHOFS_MAX_NODE_DRIFT_MI. Either
  check failing means the reading is refused, not published.

  DELIBERATELY NOT IN THIS RELEASE (v11)
  - The warm-water cap still applies to any temperature source. Once
    real nearshore values (53.8-58.6 F on 2026-07-25) replace the buoy,
    no cap tier should fire at all and the cap should simply stop
    mattering. Restricting it to nearshore readings is Phase 1.3b, a
    SEPARATE deploy (D84, C5), because it only has any effect on days
    when the model is stale and a pier has fallen back to the buoy.
  - The 72-hour water temperature trend is None for a MODELED reading.
    Note carefully that the trend it replaces was measured at the
    deep-water buoy, where the nearshore upwelling this site reports
    does not happen - so this drops a spurious input rather than a real
    one. Rebuilding it as a genuine nearshore trend from older model
    runs is Phase 1.3c.

Updated 2026-07-27 (v12, Phase 1.3b — warm-water cap restricted to
nearshore readings): the cap block now checks water["source"] ==
"MODELED" before applying any of the four warm-water tiers. Previously
it fired on ANY source, including LIVE (the own buoy, 26-52 mi
offshore in deep water) and ESTIMATED (a neighboring pier's station).
A warm reading from open water or a neighbor's shoreline says nothing
true about temperature at THIS pier, so it must not suppress this
pier's score. NO EFFECT ON TODAY'S LIVE SCORES - real MODELED
nearshore temperatures (53.8-58.6 F) sit well under the 68 F floor, so
the cap was already firing nowhere per v11's own validation. This
deploy only changes behavior on a future day when LMHOFS is stale
(>36h, D82) AND a pier has fallen back to its buoy AND that buoy reads
>=68 F - previously that fallback reading would have wrongly capped
the score; now it will not. PURELY ADDITIVE: no output key added,
removed, or renamed; only the internal firing condition of the
existing "capped" object changed (D18, D84).

Updated 2026-07-29 (v14, Phase 1.3c — REAL NEARSHORE 72-HOUR TREND +
CALIBRATED SATURATING TREND CURVE):

  VERSION NOTE: there is no deployed v13. A v13 was built earlier the
  same day, failed its own 30-day replay (the warming side was sized
  too small and the total trend range was capped below what v12
  already used), and was corrected before it ever reached production.
  The number was retired rather than reused so that two different
  files can never share one version.

  WHAT CHANGED, IN ONE SENTENCE: piers now get a real 72-hour water
  temperature trend, read from the LMHOFS run three days earlier at the
  SAME frozen mesh node, and that trend is scored with a saturating
  curve calibrated against 30 days of committed real data instead of a
  multiplier-and-clamp that was calibrated for a buoy 26 miles offshore.

  WHY BOTH HALVES SHIP TOGETHER (D105). Before this version,
  water_change_72h_f was None on every pier, so the trend term
  contributed exactly zero to every score. Replacing the curve without
  supplying the data would change nothing; supplying the data without
  replacing the curve would feed real nearshore numbers into a formula
  that pegs at its clamp 57% of the time against exactly that data.
  Either half alone is a defective intermediate state.

  THE OLD FORMULA AND WHY IT WAS WRONG. It was
  clamp(2.4 * -change_72h_f, -20, 12), ported from the Two Rivers page
  when water temperature came from buoy 45210 in 475 feet of open
  water. Deep mid-lake water barely upwells, so 72-hour swings out
  there are small and a 2.4x multiplier never hit its limits. Nearshore
  water is a different animal. Measured against 162 real 72-hour
  changes from the committed calibration set, that formula pegs at a
  clamp limit 92 times — 57% — with 62 samples stuck at +12 and 30
  stuck at -20. Past the clamp every value is IDENTICAL: a -19F
  upwelling and a -9F cooling scored exactly the same. The site lost
  discrimination precisely on the biggest events of the season.

  THE NEW CURVE. Two saturating branches, no hard clamp:

      cooling:  TREND_COOL_MAX * tanh(-change / TREND_K_COOL)
      warming: -TREND_WARM_MAX * tanh( change / TREND_K_WARM)

  tanh approaches but never reaches 1, so the ceilings are asymptotes.
  The pegging rate is not merely lowered, it is architecturally zero: a
  -19F event always scores strictly above a -18.7F one. Verified across
  all 162 real samples (0 pegged, 0 monotonicity violations) and
  against a synthetic -50F input, which returns 15.999 against a 16.0
  ceiling.

  WHERE THE FOUR CONSTANTS COME FROM — THEY WERE TUNED AGAINST THE
  30-DAY REPLAY, NOT CHOSEN BY ARGUMENT (D119).

  An earlier draft of this version set them by reasoning: COOL_MAX
  16.0, WARM_MAX 5.0, K_COOL 9.611, K_WARM 10.221, with the K values
  calibrated so each side's 90th-percentile real event reached 90%
  saturation. Replayed against the real 27-day record it was roughly a
  WASH against the live formula — better on cooling days, clearly
  worse on warming days. Two mistakes caused that.

  MISTAKE 1, the warming side. It was shrunk to 5.0 on the argument
  that the base curve already prices warm water, so penalising warming
  again would be double-counting. That is true of how warm the water
  IS and false of how FAST it is warming — different facts, and only
  the first was tested. On 2026-07-06 all six piers were warming at
  speeds between +2.9F and +10.1F and the shrunken range could barely
  separate them: the gap between the fastest- and slowest-warming pier
  fell from 13 points under the live formula to 2.

  MISTAKE 2, the total range. It was capped at 25% of the base curve's
  79 points on the reasoning that the trend must stay "materially
  smaller" than the base. Nobody checked that the LIVE formula already
  used 40% (-20 to +12 = 32 points). A constraint tighter than the
  system being replaced guarantees weaker discrimination, and it did.

  THE OBJECTIVE WAS ALSO WRONG AT FIRST. The first replay scored
  candidates on raw spread — the gap between the best and worst pier.
  That is gameable by outliers. On 2026-07-06 the live formula shows a
  16-point spread while TYING two piers at 52; a candidate showing an
  11-point spread gave all six piers distinct, correctly ordered
  scores. Ties are what actually hurt a visitor choosing a pier, so the
  final tuning scored candidates on tied pairs, searched over the real
  27-day record.

  RESULT of the tuned constants against the live formula, measured
  over 27 days x 6 piers = 162 real scores:

      tied pairs        80 -> 37    (more than halved)
      distinct scores  4.48 -> 5.11 out of 6 per day
      total range        32 -> 34   (essentially unchanged, so the
                                     trend does not start dominating)

  On the three days where the base curve goes quiet, distinct scores
  out of six went 3 -> 6 (2026-07-26), 4 -> 6 (2026-07-27) and held at
  5 (2026-07-06, where the live formula's wider spread concealed a
  two-pier tie).

  THE SHAPE IS DELIBERATE. Cooling is favoured 1.83:1 by range but is
  the SHALLOWER curve (2.00 pts/F near zero against warming's 2.40).
  Warming responds fast and then levels off, because large warming is
  already priced heavily by the base curve and charging it twice is
  the original error; early warming is the part the base curve cannot
  see. Cooling has no such backstop — a 19F crash really is better
  than a 9F one all the way up — so its curve keeps climbing.

  THE BASE TEMPERATURE CURVE IS DELIBERATELY UNCHANGED (D109). A
  mid-analysis claim that it was also broken came from ONE day of live
  data and was withdrawn: across the committed 30 days its median
  spread across the six piers is 21.7 points, only 24% of readings fall
  in the flat 50-56F plateau, and only 3 of 30 days go quiet. Live data
  on 2026-07-29 independently reconfirmed it — a 20.0-point spread
  across a 10.7F temperature range. Do not rebuild it.

  HOW THE 72-HOUR-AGO READING IS FOUND (D118). LMHOFS publishes at 00,
  06, 12 and 18 UTC, and 72 hours is exactly twelve 6-hour cycles — so
  the run 72 hours before any valid cycle is ITSELF a valid cycle time,
  and an exact match should be the normal case, not the lucky one.
  When the exact run is missing, this version accepts the nearest
  available run within ONE CYCLE either side (66h or 78h) and PUBLISHES
  the real window in history_window_hours. Beyond one cycle it gives up
  and reports no trend.

  THREE THINGS THAT DELIBERATELY DO NOT HAPPEN HERE. (1) The measured
  change is NEVER scaled to a nominal 72 hours. Multiplying a 66-hour
  change by 72/66 would assume water temperature moves linearly over
  three days; upwelling is episodic, which is the entire reason this
  site exists. Scaling would turn a measurement into a guess wearing a
  measurement's clothes. (2) No pier ever borrows another pier's trend.
  A pier whose history is unavailable reports change_72h_f = None and
  receives a trend contribution of exactly zero. (3) The historical
  file gets its OWN mesh check. The frozen node indices are only
  meaningful against a 90,806-node mesh, and a renumbered older file
  would return a completely plausible temperature from the wrong part
  of the lake.

  INSTRUMENTED ON PURPOSE. history_match records "exact", "adjacent"
  or "none" on every run. There is solid evidence for 12z availability
  (30 of 30 days in the calibration set) but NO evidence either way for
  00z, 06z and 18z. Rather than assume, this version measures: after a
  week of runs, data.json itself will say how often the fallback fires.

  COST: roughly 9 extra small OPeNDAP requests per hourly run, against
  a free public NOAA service.

  EXPECT SCORES TO MOVE ON ALL SIX PIERS THE MOMENT THIS DEPLOYS. The
  trend term currently contributes zero everywhere. That is the point
  of the change, and it is why the 30-day replay (Step 4) belongs
  before deployment rather than after.

Updated 2026-07-31 (v15, D133 — Manitowoc's false own-buoy claim on
mt1 removed):

  THE PROBLEM. Buoy 45210 (26 mi offshore, deep water) is published
  under TWO codenames: "tr1" and "mt1" - same sensor, same instant,
  same reading, always. Two Rivers has always used "tr1" as its own
  designated buoy, which is a settled, unquestioned decision (D63/D64)
  and is NOT changed by this update. Manitowoc's config separately
  listed "mt1" - the SAME underlying buoy - as ITS OWN buoy too. That
  meant this one physical reading got labeled LIVE/own-buoy by BOTH
  Two Rivers AND Manitowoc, while Sheboygan, Kewaunee, and Algoma all
  borrowed that identical reading through their own water_fallbacks
  chains and honestly labeled it ESTIMATED. Same number, same instant,
  three different honesty labels depending only on which pier's
  config was asked.

  THE FIX. Manitowoc's "buoy" field is now None. It falls through the
  same resolve_water() chain every other pier already uses: LMHOFS
  model first, then its own satellite point, then an honestly-labeled
  ESTIMATED water_fallbacks entry (added - was empty before, so a
  satellite gap used to mean an unnecessary hard stop), then Unknown
  if every source is genuinely dark. Verified against live data.json:
  this is a no-op today (LMHOFS resolves for Manitowoc at 60.1F) and
  correctly falls through to an honest ESTIMATED/"Two Rivers" reading
  in a simulated LMHOFS-and-satellite-down test.

  A DIRECT CONSEQUENCE, FIXED IN THE SAME PASS. Once Manitowoc no
  longer treats mt1 as its own, three other piers' fallback labels
  that said "estimated, borrowed from Manitowoc" would have become
  false the moment this deployed - Manitowoc's own page would show a
  different source than what those piers claimed to be borrowing FROM
  Manitowoc. Two Rivers, Sheboygan, and Kewaunee's water_fallbacks
  entries that reference "mt1" are relabeled "Open Lake Buoy" instead
  - naming what the source actually is rather than attributing it to
  a pier that never owned it. Algoma's fallback labels are UNCHANGED
  on purpose - Algoma's "always says Kewaunee" wording is a separate,
  deliberate design decision (documented in its own PIERS entry) about
  mirroring whatever Kewaunee's page shows, not a literal source
  attribution, and is not affected by this issue. Sturgeon Bay's "Two
  Rivers" label is also unchanged - it is accurate, since Two Rivers
  genuinely still owns tr1.

  NOT FIXED HERE, FLAGGED FOR LATER: Two Rivers' own water_fallbacks
  entry (mt1/Open Lake Buoy) is functionally dead - if tr1 goes dark,
  mt1 (the identical live fetch) goes dark at the same instant, so
  this fallback can never actually fire. Pre-existing, unrelated to
  D133, and out of scope for this single-change pass (C5).

  ALSO CONFIRMED THIS PASS: the live frontend's null-source fallback
  text reads "Source pending," not "Unknown" - inconsistent with the
  documented four-tier system (D12) but NOT broken (no blank render,
  no crash, no "undefined"). Flagged for a separate, future wording
  decision; not touched here.

Updated 2026-07-31 (v16, Phase 1.5 - decision D137): THE SATELLITE
  (GLSEA) SOURCE TIER IS RETIRED AND REMOVED. This is a deletion, not
  a repair, and it was chosen deliberately over the two alternatives
  (fix it via a different provider such as GLOS, or leave it in
  place).

  WHY IT WAS DELETED RATHER THAN FIXED:

  1. It has never produced a reading in production. Every GLSEA point
     reported available:false on every run inspected, and all four
     returned the SAME reason string - "no reading at this point
     (likely cloud cover)" - simultaneously. Four separate points on
     four different stretches of coast do not cloud over identically;
     that is a systemic failure. The feed is understood to sit behind
     an anti-bot wall.

  2. Even if it worked perfectly, it would now be the WORSE number.
     A GLSEA grid cell is roughly 1.5 km across. Since v11 every pier
     draws water temperature from an LMHOFS nearshore node 0.01-0.25
     MILES from the pier. Falling back from the model to the satellite
     would mean falling back to a less relevant reading, which is the
     opposite of what a fallback is for.

  3. It was an advertised source tier that had never once worked
     (risk R18). The site's entire premise is that it does not
     overstate what it knows. Publishing a Satellite tier that can
     never fire was the clearest remaining violation of that.

  WHAT THIS CHANGES ON A NORMAL DAY: nothing. The tier never fired,
  so removing it cannot change any score, any label, or any number.
  Verified by full six-pier regression before delivery.

  WHAT THIS CHANGES ON A BAD DAY: nothing either - because the tier
  did not work on bad days before this change. It is worth being
  explicit, though, that on a day LMHOFS goes stale (>36h, D82) a
  pier now falls straight from the model to its offshore buoy or a
  borrowed reading. That gap is PRE-EXISTING and is not created by
  this change; it is simply no longer disguised by a tier that was
  never going to catch anything.

  KEPT ON PURPOSE: output["satellite_water_temp"] still exists as a
  permanently empty dict. Any older Carrd embed that still reads that
  key gets an empty object instead of a crash. It can be deleted once
  every pier box is confirmed clean.

Updated 2026-07-31 (v17, Phase 1.7 - decision D144): THE FOUR
  VISITOR-FACING SOURCE TIERS (D12) ARE NOW PUBLISHED. LABELS ONLY.
  NO SCORE, ANYWHERE, MOVES BY ONE POINT.

  This adds three new keys next to every existing "source" field -
  "tier", "tier_symbol" and "locality" - and changes nothing else.
  Every pre-existing key keeps its pre-existing value. The internal
  codes (LIVE / MODELED / ESTIMATED / FORECAST / MISSING) are
  UNCHANGED and still drive every calculation; the new keys are a
  presentation layer sitting beside them, so the backend keeps
  thinking in precise engineering terms while the frontend gets
  plain words a visitor can read.

  THE ONE REAL JUDGMENT CALL, AND WHY IT WENT THE WAY IT DID (D144):

  ESTIMATED maps to Measured, not to Modeled.

  ESTIMATED means a real thermometer or anemometer, reading real
  water or real air, RIGHT NOW - just standing at a neighbouring
  pier instead of this one. Calling that "Modeled" would tell a
  visitor an instrument reading is a computer simulation. That is
  false, and it would also wreck the Modeled tier by filling it with
  two unrelated kinds of number, so "Modeled" would stop meaning
  anything.

  This follows the precedent already set by D139: THE TIER DESCRIBES
  HOW A NUMBER WAS OBTAINED, NEVER WHETHER IT IS ABOUT THE RIGHT
  PLACE. Instrument, model, forecast, nothing. That is the whole
  question the tier answers.

  "Is it about the right place?" is a real and separate question,
  and it is answered by two fields that already existed and were
  simply not being used together: the station label and the
  distance-to-pier. That is why "locality" is added here -
  at_pier / borrowed / area / unknown - so a frontend physically
  cannot render a bare "Measured" dot on a reading that came from
  eleven miles up the coast without also saying so.

  THE HONESTY GUARD: a Measured tier on a station-backed field
  (water, wind, waves) whose distance is None is emitted with
  locality "unknown" and prints a warning to the run log. A real
  measurement we cannot place is still a real measurement - so it is
  NOT downgraded to Unknown, which would be its own lie in the other
  direction - but it is never allowed to look located when it isn't.
  As of the audit run on 2026-07-31 there are ZERO such cases: every
  LIVE and ESTIMATED value on all six piers already carries a
  distance. The guard is defensive, for a future station added
  without coordinates.

  NOT CHANGED HERE, ON PURPOSE: the Clarity / Storm factor still
  reports source "LIVE" when no storm alert is active, which still
  counts it toward verified_count. That is arguably right (the NWS
  alert feed genuinely was read just now) and arguably wrong ("no
  alert" is not a measurement of anything). Either way it would
  change a number visitors see, so it is a SEPARATE decision and a
  SEPARATE deploy - see risk R63. One backend change at a time.
"""

# File: fetch-data-2026-07-31-v17-visitor-facing-source-tiers.py
# Delivered: 2026-07-31 (v17 — Phase 1.7, D144: publishes the four
#            visitor-facing source tiers from D12 as three new keys
#            beside every existing "source" field — "tier",
#            "tier_symbol", "locality". ESTIMATED maps to Measured,
#            not Modeled — see the header for the reasoning. Adds an
#            honesty guard so a Measured value with no known distance
#            reports locality "unknown" instead of looking local.
#            PURELY ADDITIVE: no key removed, no key renamed, no
#            existing value changed, no score moved. Verified by
#            byte-level side-by-side regression against v16 across
#            live data and four failure scenarios.)
# Supersedes: the v16 file (2026-07-31, Phase 1.5 satellite retirement)
#
# File: fetch-data-2026-07-31-v15-mt1-manitowoc-honesty-fix.py
# Delivered: 2026-07-31 (v15 — D133: removed Manitowoc's false claim
#            on mt1 as its own buoy; it now falls through the same
#            LMHOFS -> satellite -> honest-fallback -> Unknown chain
#            as every other pier. Relabeled the "mt1" fallback used by
#            Two Rivers, Sheboygan, and Kewaunee from "Manitowoc" to
#            "Open Lake Buoy" so those labels stay true now that
#            Manitowoc no longer owns it. Algoma and Sturgeon Bay
#            untouched. No output KEY added, removed, or renamed;
#            same shape as v14, different values on a bad-data day
#            only. Verified: no-op today, confirmed against live
#            data.json.)
# Supersedes: the v14 file (2026-07-29, Phase 1.3c trend fix) — no
#            renamed copy of it exists in this project's records, so
#            it isn't cited here by filename to avoid guessing one.

import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt, tanh

# ---------------------------------------------------------------
# 1. Buoy stations — direct sensor readings.
# ---------------------------------------------------------------
#     v10: every entry now carries its REAL published position, fetched
#     from NOAA (see the module docstring). Buoy positions come from the
#     NDBC station table because the NWS API rounds them.
STATIONS = {
    # NOAA's station table names this "Rawley Point East, WI (269)". It
    # is NOT a Two Rivers or Manitowoc buoy - it floats 26 miles off Two
    # Rivers in deep open water, and all six piers currently read it.
    # The old label hid that completely.
    "45210": {
        "label": "Rawley Point East buoy (NDBC 45210) \u2014 open lake, deep water",
        "codenames": ["tr1", "mt1"],
        "lat": 44.055,
        "lon": -87.050,
        # 145 m, verified during the 2026-07-24 honesty investigation.
        # This is WATER DEPTH. Do not confuse it with the ~176 m
        # "elevation" the NWS API reports, which is the lake surface
        # height above sea level.
        "water_depth_ft": 475,
    },
    # 0.26 mi from the Sheboygan pier - genuinely local. Reports wind and
    # air temperature, but its water-temperature field is empty, which is
    # why Sheboygan currently borrows water from 38 miles away.
    "SGNW3": {
        "label": "Sheboygan, WI shore station (NDBC SGNW3)",
        "lat": 43.749,
        "lon": -87.693,
        "water_depth_ft": None,
    },
    # NOAA's table: "NORTH MICHIGAN - Halfway between North Manitou and
    # Washington Islands." The existing label was accurate, so it stays.
    "45002": {
        "label": "North Michigan buoy (NDBC 45002) \u2014 Washington Island area",
        "lat": 45.344,
        "lon": -86.411,
        # Not published in any machine-readable form NOAA gave us.
        # Left unknown rather than guessed.
        "water_depth_ft": None,
    },
}

NDBC_URL = "https://www.ndbc.noaa.gov/data/realtime2/{station}.txt"

# ---------------------------------------------------------------
# 1c. Airport wind stations — real HOURLY HISTORY, not just current.
#     Great Lakes buoys don't measure wind, so for genuine 72-hour
#     wind trends we use the nearest continuously-reporting airport
#     weather station instead. This is real, timestamped data — not
#     a guess — but it is measured a few miles from the pier, not
#     right at the water, so it's labeled honestly on the page.
# ---------------------------------------------------------------
#     v10: real published positions added. Airport positions come from
#     the NWS API (full precision); the dormant shore stations are not
#     in the NWS API at all and come from the NDBC station table.
STATION_HISTORY = {
    # 5.9 mi from the Two Rivers pier, 3.5 mi from the Manitowoc pier -
    # a good illustration of why distance must be stored per PIER, not
    # per station.
    "KMTW": {"label": "Manitowoc Airport", "codenames": ["trw", "mtw"],
             "lat": 44.13333, "lon": -87.68333},
    "KSBM": {"label": "Sheboygan County Memorial Airport (nearest continuously-reporting wind station)",
             "lat": 43.77483, "lon": -87.84897},
    # 0.55 mi from the Kewaunee pier - a genuinely local wind reading,
    # closer to the water than any airport station on this coast.
    "KWNW3": {"label": "Kewaunee MET station (nearest continuously-reporting wind station)", "codenames": ["kww"],
              "lat": 44.465, "lon": -87.49572},
    # v10: the phrase "about 7 miles from the canal pier" was removed
    # from this label. It was hand-written; the real computed distance
    # is 6.4 mi. Distance now comes from the calculation (D14).
    "KSUE": {"label": "Door County Cherryland Airport, Sturgeon Bay (nearest continuously-reporting wind station)",
             "lat": 44.83941, "lon": -87.42188},
    # The three dormant stations below all sit essentially ON their
    # piers - AGMW3 0.04 mi, 0Y2W3 0.21 mi, C58W3 0.15 mi. If NOAA ever
    # revives any of them it would instantly become the best wind source
    # on that pier. They stay wired for exactly that reason.
    "AGMW3": {"label": "Algoma City Marina, WI (dormant \u2014 NOAA has not transmitted data from this station since approximately 2017; wired here so it activates automatically with no code changes if the station ever comes back online)", "codenames": ["agw"],
              "lat": 44.608, "lon": -87.433},
    "0Y2W3": {"label": "Sturgeon Bay CG Station, WI (dormant \u2014 no data currently transmitted; wired here so it activates automatically with no code changes if the station ever comes back online)", "codenames": ["sbcg"],
              "lat": 44.794, "lon": -87.313},
    "C58W3": {"label": "Two Rivers CG Station, WI (dormant \u2014 no data currently transmitted; wired here for completeness, though Two Rivers already has solid live coverage via buoy 45210 and KMTW)", "codenames": ["trcg"],
              "lat": 44.146, "lon": -87.563},
}

NWS_STATION_OBS_URL = "https://api.weather.gov/stations/{station}/observations"

# ---------------------------------------------------------------
# 1b. Marine forecast zones — official NWS forecasts + alerts.
# ---------------------------------------------------------------
ZONES = {
    "LMZ543": {"label": "Two Rivers to Sheboygan WI", "codenames": ["trz", "mtz"]},
    "LMZ643": {"label": "Sheboygan to Port Washington WI"},
    "LMZ542": {"label": "Sturgeon Bay to Two Rivers WI", "codenames": ["kwz", "algz"]},
}

NWS_ZONE_TEXT_URL = "https://tgftp.nws.noaa.gov/data/forecasts/marine/near_shore/lm/{zone_lower}.txt"
NWS_ALERTS_URL = "https://api.weather.gov/alerts/active?zone={zone}"
NWS_USER_AGENT = "PierBiteDotCom (contact: pierbite project owner)"

# ---------------------------------------------------------------
# 1d. GLSEA satellite water temperature - RETIRED 2026-07-31 (v16,
#     Phase 1.5, decision D137).
#
#     This tier is gone, deliberately, and this note exists so nobody
#     rebuilds it by accident. Three reasons, in order of weight:
#
#     1. It never worked in production. Every GLSEA point reported
#        available:false on every run inspected, all four returning
#        the identical "likely cloud cover" reason - a systemic
#        failure, not weather. The feed sits behind an anti-bot wall.
#     2. Even working perfectly it would be WORSE than what replaced
#        it. A GLSEA cell is ~1.5 km across. The LMHOFS nodes now
#        supplying every pier sit 0.01-0.25 miles from the pier
#        itself. Falling back from the model to the satellite would
#        be falling back to a less relevant number.
#     3. It was an advertised source tier that had never once
#        produced a reading (logged as risk R18). On a site whose
#        entire premise is not overstating what it knows, that was
#        the clearest remaining honesty violation.
#
#     If a future nearshore backup is ever wanted for the >36h
#     stale-LMHOFS case, build it as a new, tested source - do not
#     resurrect GLSEA.
# ---------------------------------------------------------------

# ---------------------------------------------------------------
# 1e. LMHOFS — NOAA Lake Michigan–Huron Operational Forecast System.
#     NEW in v11. This is the primary water-temperature source.
#
#     A 3D hydrodynamic model on an unstructured mesh of 90,806 nodes,
#     roughly 50 m resolution along the shoreline. Unlike a buoy 26
#     miles out in deep water, it actually simulates the nearshore
#     upwelling this site exists to report.
#
#     THE NODE INDICES BELOW ARE FROZEN. They were derived once, on
#     2026-07-25, by downloading the full 90,806-point coordinate grid
#     inside a diagnostic probe and finding the nearest mesh node to
#     each verified pier position. That download does NOT happen here
#     and must never be added to production code — each pier costs one
#     small request precisely because these numbers are already known.
#     Re-derive them only by re-running lmhofs-water-temp-probe-
#     2026-07-25-v6.py, which lives in this repository.
# ---------------------------------------------------------------
LMHOFS_BASE_DIR = (
    "https://opendap.co-ops.nos.noaa.gov/thredds/dodsC/"
    "NOAA/LMHOFS/MODELS/{yyyy}/{mm}/{dd}/"
)
# nNNN = NOWCAST hour. fNNN would be the forecast. NOAA does not put
# the word "nowcast" anywhere in this filename — see the module
# docstring.
#
# WHY n006 AND NOT n000 (v20, decision D204/D205 — READ THIS BEFORE
# CHANGING IT BACK). A nowcast run does not describe a single instant.
# It covers the SIX HOURS ENDING AT ITS OWN CYCLE TIME, one file per
# hour, n000 through n006. So for the 18z run:
#
#     n000  is valid at 12:00 UTC   (six hours BEFORE the cycle)
#     n006  is valid at 18:00 UTC   (exactly AT the cycle)
#
# Production read n000 from v11 until 2026-08-19, which meant every
# water temperature on the site was six hours older than the run_time
# published beside it, and both age thresholds below silently
# understated true data age by six hours. Confirmed by two independent
# methods inside the file that agreed — the Times text variable and the
# numeric time variable checked against the epoch declared in the
# file's own .das — not inferred from the filename (D207).
#
# THIS CONSTANT IS USED AT BOTH READ SITES: lmhofs_find_run() for
# today's value and lmhofs_find_run_near() for the far end of the
# 72-hour trend. That is deliberate and load-bearing. Because both ends
# shift by the same six hours, the measured trend window is unchanged.
# If anyone ever splits this into two constants, the published
# "72-hour trend" becomes a 66- or 78-hour change wearing a 72-hour
# label. Do not split it.
LMHOFS_FIELDS_FILE = "lmhofs.t{cycle}z.{yyyy}{mm}{dd}.fields.n006.nc"

# Model cycles are published at 00, 06, 12 and 18 UTC, but the newest
# one is not always there. Walk backwards until something answers.
LMHOFS_CYCLES = ["18", "12", "06", "00"]

# Staleness policy — decision D82. See the module docstring for the
# reasoning; these two numbers ARE that decision, in code.
LMHOFS_DISCLOSE_AGE_HOURS = 12   # older than this: still used, age published
LMHOFS_MAX_AGE_HOURS = 36        # older than this: refused entirely


# ---------------------------------------------------------------
# 72-HOUR HISTORY LOOKUP — Phase 1.3c, decision D118.
#
# 72 hours is exactly twelve 6-hour cycles, so the run 72 hours before
# any valid cycle is itself a valid cycle time. An exact match is the
# expected case. These two numbers describe what to do when it is not.
# ---------------------------------------------------------------
LMHOFS_HISTORY_HOURS = 72        # the trend window this site reports
LMHOFS_HISTORY_TOLERANCE_HOURS = 6   # one cycle either side, then give up

# ---------------------------------------------------------------
# WATER TREND TRANSFORM — Phase 1.3c, decisions D114 and D116.
#
# Derived 2026-07-29 from calibration/nearshore_water_history_30d.csv
# (210 rows, 30 days x 7 nodes, committed to this repository by
# nearshore-water-history-probe-2026-07-28-v1.py on 2026-07-28).
#
# IF THESE NUMBERS ARE EVER CHANGED, THE DERIVATION MUST BE RE-RUN AND
# RE-COMMITTED. A committed derivation script that disagrees with the
# constants in production is worse than no script at all, because it
# looks authoritative while being wrong (risk R39/R46).
#
# TUNED AGAINST THE 30-DAY REPLAY (D119), not chosen by argument.
#
# An earlier draft of this version set these by reasoning alone —
# COOL_MAX 16.0 / WARM_MAX 5.0 / K_COOL 9.611 / K_WARM 10.221 — and the
# replay showed it was roughly a WASH against the live formula: better
# on cooling days, clearly worse on warming days. Two mistakes caused
# that, both recorded so they are not repeated.
#
# MISTAKE 1: the warming side was shrunk on a double-count argument
# ("the base curve already prices warm water"). True for how warm the
# water IS; false for how FAST it is warming. Those are different
# facts, and only the first was checked. On 2026-07-06 all six piers
# were warming at speeds from +2.9F to +10.1F, and the shrunken
# warming range could barely tell them apart.
#
# MISTAKE 2: the total trend range was capped at 25% of the base
# curve's 79 points, without ever checking that the LIVE formula
# already used 40% (-20 to +12 = 32 points). The "safe" constraint was
# tighter than the system it was replacing, which guaranteed weaker
# discrimination.
#
# These four numbers are now the outcome of a search over the real
# 27-day record, scored on how often two piers get the SAME number —
# the thing that actually hurts a visitor choosing a pier. Raw spread
# was rejected as the objective because it is gameable by outliers:
# the live formula shows a bigger spread on 2026-07-06 while tying two
# piers at 52, which is worse, not better.
#
# RESULT vs the live formula, over 27 days x 6 piers:
#   tied pairs        80 -> 37   (more than halved)
#   distinct scores  4.48 -> 5.11 out of 6 per day
#   total range        32 -> 34   (essentially unchanged, so the trend
#                                  does not start dominating the base)
TREND_COOL_MAX = 22.0
TREND_K_COOL = 11.0      # slope 2.00 pts/F near zero
TREND_WARM_MAX = 12.0
TREND_K_WARM = 5.0       # slope 2.40 pts/F near zero

# Ratio 1.83:1 cooling-favoured by RANGE (D107) — cooling keeps growing
# where warming levels off. That shape is deliberate and matches the
# double-count logic correctly this time: early warming is real
# information the base curve cannot see, so the warming curve is steep
# at first; large warming is already priced heavily by the base curve,
# so the warming curve flattens rather than charging twice. Cooling has
# no such backstop — a 19F crash really is better than a 9F one all the
# way up — so the cooling curve keeps climbing.

LMHOFS_TIMEOUT = 60
LMHOFS_USER_AGENT = "PierBiteDotCom (contact: pierbite project owner)"

# The mesh size this configuration was frozen against. If NOAA ever
# renumbers or refines the mesh, every index below silently points
# somewhere else — and would return a completely plausible temperature
# from the wrong part of the lake. Checked on every run (risk R21).
LMHOFS_EXPECTED_NODE_COUNT = 90806

# Second layer of the same defence: how far a node is allowed to sit
# from its pier before the reading is refused. Every frozen node is
# currently within 0.25 mi, so 2 miles is generous enough never to fire
# on ordinary mesh refinement, and tight enough to catch renumbering.
LMHOFS_MAX_NODE_DRIFT_MI = 2.0

# FROZEN — one mesh node per pier. Derived 2026-07-25 from verified
# pier coordinates (D63). Distances at derivation: Manitowoc 63 ft,
# Sheboygan 106 ft, Kewaunee 396 ft, Sturgeon Bay 797 ft, Algoma
# 866 ft, Two Rivers 1,315 ft.
LMHOFS_NODES = {
    "sheboygan": 20022,
    "manitowoc": 21438,
    "two_rivers": 23983,
    "kewaunee": 28542,
    "algoma": 28904,
    "sturgeon_bay": 31190,
}

# The model node co-located with buoy 45210 (0.538 mi from the buoy).
# Not a pier — this is the open-lake comparison point that makes the
# nearshore-vs-open-lake gap visible. See open_lake_context below.
LMHOFS_CONTEXT_NODE = 28627

# 16-point compass, in order, starting at North.
COMPASS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def degrees_to_compass(deg):
    """Turn a wind direction in degrees (e.g. 270) into a letter code (e.g. 'W')."""
    if deg is None:
        return None
    idx = round(deg / 22.5) % 16
    return COMPASS[idx]


def to_float(value):
    """NOAA uses 'MM' to mean 'no reading'. Turn that into a proper empty value."""
    if value in (None, "MM", ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def fetch_station(station_id):
    """Download and read one buoy's text file from NOAA."""
    url = NDBC_URL.format(station=station_id)
    with urllib.request.urlopen(url, timeout=30) as response:
        raw_text = response.read().decode("utf-8", errors="ignore")

    lines = raw_text.strip().split("\n")
    if len(lines) < 3:
        return []  # station returned nothing useful

    readings = []
    for line in lines[2:]:  # first two lines are headers, skip them
        parts = line.split()
        if len(parts) < 15:
            continue
        try:
            year, month, day, hour, minute = (int(parts[i]) for i in range(5))
            when = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
        except ValueError:
            continue

        readings.append({
            "time": when,
            "wind_dir_deg": to_float(parts[5]),
            "wind_speed_ms": to_float(parts[6]),
            "gust_ms": to_float(parts[7]),
            "wave_height_m": to_float(parts[8]),
            "water_temp_c": to_float(parts[14]),
            # PRES (index 12) and PTDY (index 17) — standard NDBC columns,
            # confirmed against a live station reading before adding this.
            "pressure_hpa": to_float(parts[12]),
            "pressure_tendency_hpa": to_float(parts[17]) if len(parts) > 17 else None,
        })

    readings.reverse()  # oldest first, newest last
    return readings


def closest_to(readings, target_time):
    """Find the reading whose timestamp is nearest to a target time."""
    if not readings:
        return None
    return min(readings, key=lambda r: abs((r["time"] - target_time).total_seconds()))


def summarize_station(station_id, readings):
    if not readings:
        return {"available": False}

    latest = readings[-1]
    ago_24h = closest_to(readings, latest["time"] - timedelta(hours=24))
    ago_72h = closest_to(readings, latest["time"] - timedelta(hours=72))

    def water_f(c):
        return round(c * 9 / 5 + 32, 1) if c is not None else None

    def wind_mph(ms):
        return round(ms * 2.23694, 1) if ms is not None else None

    def waves_ft(m):
        return round(m * 3.28084, 2) if m is not None else None

    current_water_f = water_f(latest["water_temp_c"])
    water_24h_ago_f = water_f(ago_24h["water_temp_c"]) if ago_24h else None
    water_72h_ago_f = water_f(ago_72h["water_temp_c"]) if ago_72h else None

    change_24h = (
        round(current_water_f - water_24h_ago_f, 1)
        if current_water_f is not None and water_24h_ago_f is not None
        else None
    )
    change_72h = (
        round(current_water_f - water_72h_ago_f, 1)
        if current_water_f is not None and water_72h_ago_f is not None
        else None
    )

    return {
        "available": True,
        "observed_at_utc": latest["time"].isoformat(),
        "wind_dir": degrees_to_compass(latest["wind_dir_deg"]),
        "wind_mph": wind_mph(latest["wind_speed_ms"]),
        "gust_mph": wind_mph(latest["gust_ms"]),
        "wave_ft": waves_ft(latest["wave_height_m"]),
        "water_temp_f": current_water_f,
        "water_change_24h_f": change_24h,
        "water_change_72h_f": change_72h,
        # Pressure in hPa (millibars), plus NDBC's own 3-hour tendency
        # value — a falling reading here is the classic "front's coming"
        # signal; a sharp rise right after often means the bite shuts off.
        "pressure_hpa": latest["pressure_hpa"],
        "pressure_tendency_3h_hpa": latest["pressure_tendency_hpa"],
    }


def nws_get(url):
    """Make a request to the NWS API. Requires a User-Agent header."""
    req = urllib.request.Request(url, headers={
        "User-Agent": NWS_USER_AGENT,
        "Accept": "application/geo+json",
    })
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


DIR_WORDS = {
    "north": "N", "northeast": "NE", "east": "E", "southeast": "SE",
    "south": "S", "southwest": "SW", "west": "W", "northwest": "NW",
}


def split_wind_and_wave(text):
    """Marine forecast sentences blend wind and wave info together in one
    block of prose (e.g. 'Northeast winds 10 to 15 kt. Waves 1 to 3 ft.').
    Split at the word 'Waves' so each half can be parsed on its own,
    without wave numbers leaking into the wind range or vice versa."""
    if not text:
        return "", ""
    parts = re.split(r"(?=[Ww]aves?\s)", text, maxsplit=1)
    wind_part = parts[0]
    wave_part = parts[1] if len(parts) > 1 else ""
    return wind_part, wave_part


VALID_ABBR = {"N", "NE", "E", "SE", "S", "SW", "W", "NW"}


def parse_wind_direction(wind_part):
    """Pull the wind direction from real NWS marine text, which sometimes
    uses short form ('SE wind 5 to 10 kts') and sometimes spelled-out
    ('Northeast winds 10 to 15 kt')."""
    m = re.search(r"\b([NSEW]{1,2})\s+winds?\b", wind_part)
    if m and m.group(1) in VALID_ABBR:
        return m.group(1)
    m = re.search(
        r"\b(north|northeast|east|southeast|south|southwest|west|northwest)\s+winds?\b",
        wind_part, re.IGNORECASE,
    )
    if not m:
        return None
    return DIR_WORDS.get(m.group(1).lower())


def parse_wind_speed(wind_part):
    """Turn '10 to 15 kt' into a (low_mph, high_mph) range."""
    if not wind_part:
        return (None, None)
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", wind_part)]
    if not nums:
        return (None, None)
    is_knots = "kt" in wind_part.lower() or "knot" in wind_part.lower()
    factor = 1.15078 if is_knots else 1.0
    nums = [round(n * factor, 1) for n in nums]
    return (min(nums), max(nums))


def parse_wave_height(wave_part):
    """Pull a wave height range in feet out of the wave portion of a
    forecast sentence. Handles 'Waves 1 to 3 ft', 'Waves around 2 ft',
    'Waves 1 foot or less', 'Waves calm to 1 foot'."""
    if not wave_part:
        return (None, None)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*f(?:oo|ee)?t", wave_part)
    if m:
        return (float(m.group(1)), float(m.group(2)))
    m = re.search(r"around\s+(\d+(?:\.\d+)?)\s*f(?:oo|ee)?t", wave_part)
    if m:
        v = float(m.group(1))
        return (v, v)
    m = re.search(r"(\d+(?:\.\d+)?)\s*f(?:oo|ee)?t\s+or\s+less", wave_part)
    if m:
        return (0.0, float(m.group(1)))
    m = re.search(r"calm\s+to\s+(\d+(?:\.\d+)?)\s*f(?:oo|ee)?t", wave_part)
    if m:
        return (0.0, float(m.group(1)))
    return (None, None)


def parse_zone_periods(raw_text):
    """Marine zone bulletins look like:
    .TODAY...NW wind 10 to 15 kts... Waves 2 to 4 ft... .TONIGHT...W wind...
    Split on the '.PERIODNAME...' markers into [(period_name, text), ...]."""
    pattern = r"\.([A-Z][A-Z0-9 /]{2,30}?)\.\.\.(.*?)(?=\.[A-Z][A-Z0-9 /]{2,30}?\.\.\.|\$\$|$)"
    matches = re.findall(pattern, raw_text, re.DOTALL)
    return [(name.strip(), re.sub(r"\s+", " ", text.strip())) for name, text in matches]


def fetch_zone_forecast(zone_id):
    """Get the official NWS marine forecast text bulletin for one shoreline
    zone. Reads the current (first) forecast period as before, and now also
    keeps the next few periods so the page can show whether things are
    trending better or worse over the next day or two — still real NWS
    text, not a guess, just more of it than before."""
    url = NWS_ZONE_TEXT_URL.format(zone_lower=zone_id.lower())
    req = urllib.request.Request(url, headers={"User-Agent": NWS_USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as response:
        raw_text = response.read().decode("utf-8", errors="ignore")

    periods = parse_zone_periods(raw_text)
    if not periods:
        return {"available": False}

    def parse_period(period_name, period_text):
        wind_part, wave_part = split_wind_and_wave(period_text)
        return {
            "period_name": period_name,
            "wind_dir": parse_wind_direction(wind_part),
            "wind_mph_low": parse_wind_speed(wind_part)[0],
            "wind_mph_high": parse_wind_speed(wind_part)[1],
            "wave_ft_low": parse_wave_height(wave_part)[0],
            "wave_ft_high": parse_wave_height(wave_part)[1],
            "detailed_text": period_text,
        }

    current = parse_period(*periods[0])
    upcoming = [parse_period(name, text) for name, text in periods[1:4]]

    return {
        "available": True,
        "period_name": current["period_name"],
        "wind_dir": current["wind_dir"],
        "wind_mph_low": current["wind_mph_low"],
        "wind_mph_high": current["wind_mph_high"],
        "wave_ft_low": current["wave_ft_low"],
        "wave_ft_high": current["wave_ft_high"],
        "detailed_text": current["detailed_text"],
        "upcoming": upcoming,
    }


def fetch_station_history(station_id):
    """Get real, timestamped wind readings from a continuously-reporting
    airport weather station (ASOS). Requests the last ~73 hours in three
    smaller ~24-hour chunks instead of one big request — a single large
    request risks tripping an undocumented size cap on busy stations
    (reporting every ~5 minutes) and can fail outright instead of just
    returning less data. Smaller chunks stay safely within a size that's
    already proven to work, for any station's reporting frequency.

    Still honest about whatever real window it actually receives, rather
    than assuming it always got the full 72 hours.

    It also downsamples to one clean reading per hour (nearest actual
    observation to each hour mark), instead of keeping every 5-minute
    reading, which would otherwise bloat the file with near-duplicates."""
    now = datetime.now(timezone.utc)
    chunk_bounds = [
        (now - timedelta(hours=73), now - timedelta(hours=49)),
        (now - timedelta(hours=49), now - timedelta(hours=25)),
        (now - timedelta(hours=25), now),
    ]

    raw = []
    for chunk_start, chunk_end in chunk_bounds:
        start_param = chunk_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_param = chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ")
        url = (
            NWS_STATION_OBS_URL.format(station=station_id)
            + "?start=" + start_param + "&end=" + end_param + "&limit=500"
        )
        try:
            data = nws_get(url)
        except Exception:
            continue  # this chunk failed — keep whatever the other chunks gave us
        features = data.get("features", [])

        for feat in features:
            props = feat.get("properties", {})
            ws = (props.get("windSpeed") or {}).get("value")
            wd = (props.get("windDirection") or {}).get("value")
            ts = props.get("timestamp")
            if ws is None or wd is None or ts is None:
                continue
            try:
                when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
            raw.append({
                "time": when,
                "wind_mph": round(ws * 0.621371, 1),  # station reports km/h
                "wind_dir": degrees_to_compass(wd),
            })

    if not raw:
        return {"available": False}

    raw.sort(key=lambda r: r["time"])
    latest = raw[-1]
    earliest = raw[0]
    actual_hours_covered = round((latest["time"] - earliest["time"]).total_seconds() / 3600)

    # Downsample: for each whole hour back from now, keep the single
    # real reading closest to that hour mark (skip hours with no data).
    hourly = []
    max_hours = min(actual_hours_covered, 72)
    for h in range(max_hours, -1, -1):
        target = latest["time"] - timedelta(hours=h)
        closest = min(raw, key=lambda r: abs((r["time"] - target).total_seconds()))
        if abs((closest["time"] - target).total_seconds()) <= 1800:  # within 30 min
            hourly.append({"hours_ago": h, "dir": closest["wind_dir"], "mph": closest["wind_mph"]})

    return {
        "available": True,
        "observed_at_utc": latest["time"].isoformat(),
        "current_wind_dir": latest["wind_dir"],
        "current_wind_mph": latest["wind_mph"],
        "actual_hours_covered": actual_hours_covered,
        "hourly": hourly,
    }


# ---------------------------------------------------------------
# NEW in v9 — Beach Hazards Statement wave-range parsing.
# Real NWS Beach Hazards Statement text follows a consistent pattern,
# e.g. "...Waves 4 to 6 ft expected." Reuses the same wave-height
# regex already proven against real marine-zone forecast text
# (parse_wave_height), rather than writing a second parser.
# ---------------------------------------------------------------
def parse_beach_hazard_wave_range(description):
    """Pull a (low_ft, high_ft) wave range out of a Beach Hazards
    Statement's raw NWS description text, if the text follows the
    usual pattern. Returns (None, None) if it can't find one — never
    guesses a number that isn't actually in the text."""
    if not description:
        return (None, None)
    m = re.search(r"waves?\s+(?:of\s+)?(?:around\s+)?(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*f(?:oo|ee)?t",
                  description, re.IGNORECASE)
    if m:
        return (float(m.group(1)), float(m.group(2)))
    return (None, None)


def fetch_zone_alerts(zone_id):
    """Check for real, currently-active NWS alerts in this zone.

    FIX A (v9): the old version only ever looked at the FIRST alert
    NOAA returned and discarded the rest. A Small Craft Advisory (for
    boaters) and a Beach Hazards Statement (for swimmers/piers) often
    fire at the same time for the same weather event — dropping one
    silently is a real gap. This now walks every active alert.

    Returns a dict with:
      - "active": True/False (any alert active at all)
      - "headline"/"event"/"severity"/"effective_utc"/"expires_utc":
        the FIRST active alert's fields, in the EXACT same shape as
        before v9 — unchanged, for backward compatibility with
        anything already reading zone["alert"].
      - "alerts": NEW — every active alert, each with the same fields
        plus "description" (the raw NWS text body).
      - "beach_hazard": NEW — a dedicated object, {"active": False} if
        no Beach Hazards Statement is active, otherwise the real
        headline/description plus a parsed wave_range_ft when the
        text contains one. Kept separate from the score entirely —
        this is safety information, not a fishing-quality input.
    """
    url = NWS_ALERTS_URL.format(zone=zone_id)
    data = nws_get(url)
    features = data.get("features", [])

    if not features:
        return {
            "active": False,
            "alerts": [],
            "beach_hazard": {"active": False},
        }

    alerts = []
    for feat in features:
        props = feat.get("properties", {})
        alerts.append({
            "headline": props.get("headline"),
            "event": props.get("event"),
            "severity": props.get("severity"),
            "effective_utc": props.get("effective"),
            "expires_utc": props.get("expires"),
            "description": props.get("description"),
        })

    first = alerts[0]

    beach_hazard = {"active": False}
    for a in alerts:
        event = (a.get("event") or "").lower()
        if "beach hazard" in event:
            low_ft, high_ft = parse_beach_hazard_wave_range(a.get("description"))
            beach_hazard = {
                "active": True,
                "headline": a.get("headline"),
                "description": a.get("description"),
                "wave_range_ft": [low_ft, high_ft] if low_ft is not None else None,
                "effective_utc": a.get("effective_utc"),
                "expires_utc": a.get("expires_utc"),
            }
            break  # one Beach Hazards Statement is enough to show the banner

    return {
        "active": True,
        "headline": first.get("headline"),
        "event": first.get("event"),
        "severity": first.get("severity"),
        "effective_utc": first.get("effective_utc"),
        "expires_utc": first.get("expires_utc"),
        "alerts": alerts,
        "beach_hazard": beach_hazard,
    }


# ---------------------------------------------------------------
# 1f. LMHOFS READERS — new in v11.
#
#     Everything below talks to NOAA's OPeNDAP server. Three rules
#     govern this code and each one cost real time to learn:
#
#     1. Brackets in the query string MUST be percent-escaped. Tomcat
#        returns HTTP 400 for raw "[" and "]". Requests without
#        brackets succeed either way, so this failure hides until the
#        first actual data slice.
#     2. Never download a whole variable. OPeNDAP serves partial
#        reads — one node's temperature is a few bytes, and the full
#        grid is 187.9 MB.
#     3. Trust nothing about the file's shape. Read its own
#        description and check it.
# ---------------------------------------------------------------

# Matches any number in an OPeNDAP ascii reply, including exponent form.
_LMHOFS_NUMBER = re.compile(r"[-+]?\d*\.\d+(?:[eE][-+]?\d+)?|[-+]?\d+(?:[eE][-+]?\d+)?")
# "[0][0][23983]" style index echoes, stripped before numbers are read.
_LMHOFS_BRACKETS = re.compile(r"\[[^\]]*\]")
# The "---------" divider OPeNDAP prints between header and payload.
_LMHOFS_DIVIDER = re.compile(r"^-{3,}\s*$", re.MULTILINE)
# "[node = 90806]" style dimension declarations inside a DDS.
_LMHOFS_DIM = re.compile(r"\[\s*(\w+)\s*=\s*(\d+)\s*\]")


def lmhofs_escape(query):
    """Percent-escape array brackets. NOT optional — see rule 1 above."""
    return query.replace("[", "%5B").replace("]", "%5D")


def lmhofs_get(url, timeout=LMHOFS_TIMEOUT, max_chars=4000):
    """One OPeNDAP request. Returns (ok, text). Never raises."""
    req = urllib.request.Request(url, headers={"User-Agent": LMHOFS_USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(max_chars * 4 if max_chars else None)
    except Exception as err:  # noqa: BLE001 - any failure means "not available"
        return False, str(err)
    text = raw.decode("utf-8", errors="replace")
    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars]
    return True, text


def lmhofs_numbers(text):
    """Pull the data values out of an OPeNDAP ascii reply.

    The reply repeats the variable name and its index positions before
    the payload, so the index numbers themselves would otherwise be
    read as data. Strip the brackets, then take everything after the
    divider line.
    """
    parts = _LMHOFS_DIVIDER.split(text)
    body = parts[-1] if len(parts) > 1 else "\n".join(text.splitlines()[1:])
    body = _LMHOFS_BRACKETS.sub(" ", body)
    values = []
    for match in _LMHOFS_NUMBER.finditer(body):
        try:
            values.append(float(match.group()))
        except ValueError:
            pass
    return values


def lmhofs_read_value(file_url, query):
    """Read a single value. Returns a float, or None if anything failed."""
    ok, body = lmhofs_get("%s.ascii?%s" % (file_url, lmhofs_escape(query)))
    if not ok:
        return None
    values = lmhofs_numbers(body)
    return values[-1] if values else None


def lmhofs_find_run():
    """Locate the newest usable model run.

    Walks backwards 18z -> 12z -> 06z -> 00z, then to previous days,
    and STOPS as soon as a candidate would be older than
    LMHOFS_MAX_AGE_HOURS. That stopping rule is decision D82 expressed
    as control flow: there is no point finding a run we would refuse.

    Returns (file_url, run_time_utc, age_hours) or (None, None, None).
    """
    now = datetime.now(timezone.utc)
    for day_offset in range(0, 3):
        day = now - timedelta(days=day_offset)
        for cycle in LMHOFS_CYCLES:
            run_time = datetime(day.year, day.month, day.day,
                                int(cycle), 0, 0, tzinfo=timezone.utc)
            if run_time > now:
                continue  # a cycle later today that has not happened yet
            age_hours = (now - run_time).total_seconds() / 3600.0
            if age_hours > LMHOFS_MAX_AGE_HOURS:
                return None, None, None  # D82: too old to be worth using
            parts = {"yyyy": day.strftime("%Y"), "mm": day.strftime("%m"),
                     "dd": day.strftime("%d"), "cycle": cycle}
            url = LMHOFS_BASE_DIR.format(**parts) + LMHOFS_FIELDS_FILE.format(**parts)
            ok, body = lmhofs_get(url + ".dds", max_chars=4000)
            if ok and "Dataset" in body:
                return url, run_time, round(age_hours, 1)
    return None, None, None


def lmhofs_find_run_near(target_time, tolerance_hours=LMHOFS_HISTORY_TOLERANCE_HOURS):
    """Locate the model run closest to a target time in the past.

    DELIBERATELY NOT lmhofs_find_run(). That function walks backwards
    from NOW and refuses anything older than LMHOFS_MAX_AGE_HOURS (36)
    — so a run from 72 hours ago is disqualified by its own stopping
    rule. The two functions answer different questions: "what is the
    newest usable run?" versus "what ran at roughly this moment?".
    Reusing the first for the second would silently always return None.

    Candidates are every published cycle within tolerance_hours of the
    target, tried nearest-first, so an exact match always wins when one
    exists. Returns (file_url, run_time_utc, offset_hours) where
    offset_hours is SIGNED and real — negative means the run found is
    older than the target. Returns (None, None, None) if nothing inside
    the tolerance answers.

    The caller publishes the real window rather than assuming 72 hours,
    and NEVER scales the measured change to a nominal 72 (D118).
    """
    candidates = []
    span_days = int(tolerance_hours // 24) + 2
    for day_offset in range(-span_days, span_days + 1):
        day = target_time + timedelta(days=day_offset)
        for cycle in LMHOFS_CYCLES:
            run_time = datetime(day.year, day.month, day.day,
                                int(cycle), 0, 0, tzinfo=timezone.utc)
            offset = (run_time - target_time).total_seconds() / 3600.0
            if abs(offset) <= tolerance_hours + 1e-9:
                candidates.append((abs(offset), offset, run_time, cycle, day))

    # Nearest first, so an exact match (offset 0.0) is always preferred.
    candidates.sort(key=lambda c: c[0])

    for _, offset, run_time, cycle, day in candidates:
        parts = {"yyyy": day.strftime("%Y"), "mm": day.strftime("%m"),
                 "dd": day.strftime("%d"), "cycle": cycle}
        url = LMHOFS_BASE_DIR.format(**parts) + LMHOFS_FIELDS_FILE.format(**parts)
        ok, body = lmhofs_get(url + ".dds", max_chars=4000)
        if ok and "Dataset" in body:
            return url, run_time, round(offset, 2)
    return None, None, None


def lmhofs_check_mesh(file_url):
    """Confirm the mesh still has the shape the frozen indices assume.

    Risk R21. A frozen node index means nothing if NOAA renumbers the
    mesh — node 23983 would still return a temperature, it would just
    be somewhere else in the lake. Returns (ok, node_count, message).
    """
    ok, dds = lmhofs_get(file_url + ".dds", max_chars=8000)
    if not ok:
        return False, None, "could not read the file description: %s" % dds
    node_count = None
    for line in dds.splitlines():
        stripped = line.strip().rstrip(";")
        head = _LMHOFS_BRACKETS.sub("", stripped).split()
        if len(head) >= 2 and head[1] == "temp":
            for name, size in _LMHOFS_DIM.findall(stripped):
                if name.lower().startswith("node"):
                    node_count = int(size)
    if node_count is None:
        return False, None, "the file no longer declares a node dimension on temp"
    if node_count != LMHOFS_EXPECTED_NODE_COUNT:
        return False, node_count, (
            "mesh size changed: expected %d nodes, found %d. The frozen node "
            "indices are no longer trustworthy. Re-run the LMHOFS probe."
            % (LMHOFS_EXPECTED_NODE_COUNT, node_count)
        )
    return True, node_count, None


def lmhofs_read_node(file_url, node, expect_lat, expect_lon, expect_label):
    """Read one mesh node: temperature, plus its own published position.

    The position is not decoration. Reading it here means the distance
    published on the site is computed from coordinates NOAA supplied on
    this very run — nothing is hand-written (C19) — and it doubles as
    the per-node half of the R21 drift check.

    A position read that fails is NOT fatal: the temperature is still
    published, marked position_verified false, with no distance. A
    missing distance is honest; a wrong one is not (C22).
    """
    result = {
        "available": False, "node": node, "water_temp_f": None,
        "node_lat": None, "node_lon": None, "distance_mi": None,
        "position_verified": False, "error": None,
    }

    # temp[time=0][siglay=0][node]. siglay 0 is the SURFACE layer —
    # confirmed by measurement 2026-07-25 (D65), not assumed.
    celsius = lmhofs_read_value(file_url, "temp[0][0][%d]" % node)
    if celsius is None:
        result["error"] = "no temperature returned for node %d" % node
        return result
    fahrenheit = round(celsius * 9.0 / 5.0 + 32.0, 1)
    # Lake Michigan sanity band. A value outside it means the units or
    # the layer are not what we think, so publish nothing.
    if not (32.0 <= fahrenheit <= 90.0):
        result["error"] = ("implausible %.1f F (raw %.3f C) for node %d — refusing"
                           % (fahrenheit, celsius, node))
        return result

    node_lat = lmhofs_read_value(file_url, "lat[%d]" % node)
    node_lon = lmhofs_read_value(file_url, "lon[%d]" % node)
    if node_lon is not None and node_lon > 180:
        node_lon -= 360.0  # the file may publish 0–360 longitudes

    if node_lat is not None and node_lon is not None:
        distance = haversine_miles(expect_lat, expect_lon, node_lat, node_lon)
        if distance is not None and distance > LMHOFS_MAX_NODE_DRIFT_MI:
            result["error"] = (
                "node %d is %.2f mi from %s, past the %.1f mi limit. The mesh may "
                "have been renumbered — refusing this reading rather than "
                "publishing a temperature from the wrong place."
                % (node, distance, expect_label, LMHOFS_MAX_NODE_DRIFT_MI)
            )
            return result
        result["node_lat"] = round(node_lat, 5)
        result["node_lon"] = round(node_lon, 5)
        result["distance_mi"] = distance
        result["position_verified"] = True
    else:
        # Temperature is good; we simply cannot prove where it came from.
        result["error"] = "node position unavailable — distance not published"

    result["available"] = True
    result["water_temp_f"] = fahrenheit
    return result


def fetch_lmhofs():
    """Read nearshore water temperature for all six piers, once.

    Roughly 20 small requests total. Returns a block that is always
    present in data.json, even when unavailable, so a page can always
    tell the difference between "the model says nothing today" and
    "this key does not exist".
    """
    block = {
        "available": False,
        "model": "NOAA Lake Michigan–Huron Operational Forecast System (LMHOFS)",
        "source_tier": "MODELED",
        "run_time_utc": None,
        "run_age_hours": None,
        "stale": False,
        "disclose_age": False,
        "mesh_node_count": None,
        # 72-hour history (Phase 1.3c, D118). Always present so a page
        # can tell "no trend today" apart from "this key does not exist".
        "history_run_time_utc": None,
        "history_window_hours": None,   # the REAL gap, never assumed 72
        "history_match": "none",        # "exact" | "adjacent" | "none"
        "history_error": None,
        "points": {},
        "error": None,
    }

    file_url, run_time, age_hours = lmhofs_find_run()
    if file_url is None:
        block["error"] = (
            "no LMHOFS run published within the last %d hours — piers fall back "
            "to their existing water sources (D82)" % LMHOFS_MAX_AGE_HOURS
        )
        return block

    block["run_time_utc"] = run_time.isoformat()
    block["run_age_hours"] = age_hours
    # D82 middle band: still used, but the age is published so a page
    # can say so out loud rather than quietly presenting old numbers.
    block["disclose_age"] = age_hours >= LMHOFS_DISCLOSE_AGE_HOURS

    mesh_ok, node_count, mesh_msg = lmhofs_check_mesh(file_url)
    block["mesh_node_count"] = node_count
    if not mesh_ok:
        block["error"] = mesh_msg
        return block

    for pier_id, node in LMHOFS_NODES.items():
        pier_cfg = PIERS.get(pier_id, {})
        block["points"][pier_id] = lmhofs_read_node(
            file_url, node, pier_cfg.get("lat"), pier_cfg.get("lon"),
            "the %s pier" % pier_cfg.get("name", pier_id),
        )

    # The open-lake comparison node, beside buoy 45210.
    buoy_geo = STATION_GEO.get("tr1", {})
    block["points"]["open_lake_45210"] = lmhofs_read_node(
        file_url, LMHOFS_CONTEXT_NODE, buoy_geo.get("lat"), buoy_geo.get("lon"),
        "buoy 45210",
    )


    # -----------------------------------------------------------
    # 72-HOUR HISTORY (Phase 1.3c, D118)
    #
    # Read the SAME frozen nodes from the run three days earlier and
    # difference them. Runs after the current points so that a failure
    # here can never cost us today's temperatures — the trend is an
    # enhancement, and a pier with no history still reports its
    # temperature normally and simply receives a trend of zero.
    # -----------------------------------------------------------
    target = run_time - timedelta(hours=LMHOFS_HISTORY_HOURS)
    hist_url, hist_time, offset_hours = lmhofs_find_run_near(target)

    if hist_url is None:
        block["history_error"] = (
            "no LMHOFS run found within %d hours of %d hours before the "
            "current run — no trend reported (D118)"
            % (LMHOFS_HISTORY_TOLERANCE_HOURS, LMHOFS_HISTORY_HOURS)
        )
    else:
        # The historical file gets its OWN mesh check. A renumbered
        # older mesh would return a completely plausible temperature
        # from the wrong part of the lake, and differencing it against
        # a correct current reading would manufacture a trend out of
        # nothing — the most dangerous possible failure here.
        hist_mesh_ok, hist_nodes, hist_mesh_msg = lmhofs_check_mesh(hist_url)
        if not hist_mesh_ok:
            block["history_error"] = "historical run rejected: %s" % hist_mesh_msg
        else:
            window = round((run_time - hist_time).total_seconds() / 3600.0, 2)
            block["history_run_time_utc"] = hist_time.isoformat()
            block["history_window_hours"] = window
            block["history_match"] = (
                "exact" if abs(offset_hours) < 1e-6 else "adjacent"
            )

            for pier_id, node in LMHOFS_NODES.items():
                point = block["points"].get(pier_id, {})
                if not point.get("available"):
                    continue
                pier_cfg = PIERS.get(pier_id, {})
                past = lmhofs_read_node(
                    hist_url, node, pier_cfg.get("lat"), pier_cfg.get("lon"),
                    "the %s pier" % pier_cfg.get("name", pier_id),
                )
                if not past.get("available"):
                    continue
                then_f = past.get("water_temp_f")
                now_f = point.get("water_temp_f")
                if not isinstance(then_f, (int, float)):
                    continue
                if not isinstance(now_f, (int, float)):
                    continue
                # Positive = warmed over the window. Negative = cooled.
                # The REAL window is published alongside; this number is
                # never scaled to a nominal 72 hours (D118).
                point["water_temp_72h_ago_f"] = then_f
                point["water_change_72h_f"] = round(now_f - then_f, 2)

    block["available"] = any(p.get("available") for p in block["points"].values())
    if not block["available"]:
        block["error"] = "a model run was found but no node returned a usable value"
    return block


def build_open_lake_context(output):
    """The nearshore-versus-open-lake gap, published as one object.

    Buoy 45210 stops being a temperature source in v11, but it keeps
    earning its place. The difference between a 7-foot-deep pier and
    475 feet of open water 26 miles out is not noise — it is the
    upwelling this whole site is about, expressed as a number. It is
    also the plainest possible answer to a visitor asking why the
    site's temperatures changed.
    """
    context = {
        "available": False,
        "buoy_label": None, "buoy_temp_f": None, "buoy_distance_mi": None,
        "model_open_lake_temp_f": None,
        "nearshore_temp_f": None, "nearshore_pier": None,
        "gap_f": None,
        "note": None,
    }
    buoy = output.get("stations", {}).get("tr1", {})
    if buoy.get("available") and isinstance(buoy.get("water_temp_f"), (int, float)):
        context["buoy_label"] = buoy.get("label")
        context["buoy_temp_f"] = buoy.get("water_temp_f")
        tr = PIERS.get("two_rivers", {})
        context["buoy_distance_mi"] = haversine_miles(
            tr.get("lat"), tr.get("lon"), buoy.get("lat"), buoy.get("lon"))

    model = output.get("model_water_temp", {}).get("points", {})
    open_lake = model.get("open_lake_45210", {})
    if open_lake.get("available"):
        context["model_open_lake_temp_f"] = open_lake.get("water_temp_f")

    near = model.get("two_rivers", {})
    if near.get("available"):
        context["nearshore_temp_f"] = near.get("water_temp_f")
        context["nearshore_pier"] = PIERS.get("two_rivers", {}).get("name")

    if context["nearshore_temp_f"] is not None and context["buoy_temp_f"] is not None:
        context["gap_f"] = round(context["buoy_temp_f"] - context["nearshore_temp_f"], 1)
        context["available"] = True
        context["note"] = (
            "Open-lake and nearshore water are not the same water. This is the "
            "difference between a reading taken at the pier and one taken in deep "
            "water offshore."
        )
    return context


def validate_config():
    """Check that every codename a pier references actually exists.

    Risk R25. In v10 a dead reference to a station codenamed "kw1" was
    found in Two Rivers' fallback chain. No such station was defined
    anywhere. It had resolved silently to nothing on every run for
    months, and nothing failed — because nothing could. The config
    merely LOOKED as though Two Rivers had a Kewaunee backup.

    Warns rather than aborts, deliberately: a stale but correct
    data.json is better for a visitor than no data.json at all.
    """
    warnings = []
    for pier_id, cfg in PIERS.items():
        buoy = cfg.get("buoy")
        if buoy and buoy not in STATION_GEO:
            warnings.append("%s: buoy codename '%s' is not defined in STATIONS"
                            % (pier_id, buoy))
        for kind, key, _name in cfg.get("water_fallbacks", []):
            # v16: only "station" fallbacks exist now that the
            # satellite tier is retired (D137). Any other kind is a
            # config error and is reported as one rather than
            # silently resolving to nothing.
            if kind != "station":
                warnings.append("%s: water fallback '%s' has unsupported kind '%s'"
                                % (pier_id, key, kind))
                continue
            if key not in STATION_GEO:
                warnings.append("%s: water fallback '%s' (%s) is not defined anywhere"
                                % (pier_id, key, kind))
        for hist_key, _borrowed in cfg.get("wind_history", []):
            if hist_key not in HISTORY_GEO:
                warnings.append("%s: wind history codename '%s' is not defined in "
                                "STATION_HISTORY" % (pier_id, hist_key))
        zone = cfg.get("zone")
        zone_keys = set()
        for zone_id, meta in ZONES.items():
            for codename in meta.get("codenames", [meta.get("codename", zone_id)]):
                zone_keys.add(codename)
        if zone and zone not in zone_keys:
            warnings.append("%s: zone codename '%s' is not defined in ZONES"
                            % (pier_id, zone))
        if pier_id not in LMHOFS_NODES:
            warnings.append("%s: no LMHOFS grid node is configured for this pier"
                            % pier_id)
    return warnings


# ---------------------------------------------------------------
# 2. SCORING ENGINE — new in v5. "The backend thinks, the
#    frontend displays."
#
#    The math here is ported line-for-line from the proven Two
#    Rivers page implementation, with fixes applied over time (see
#    module docstring above for the full dated history).
# ---------------------------------------------------------------

SCHEMA_VERSION = 1
# If data.json is older than this many hours, pages should treat
# it as stale instead of presenting old numbers as LIVE.
STALE_AFTER_HOURS = 3

# One entry per pier. Adding a future pier = adding one entry here.
#   buoy            key in output["stations"] for this pier's own buoy (or None)
#   water_fallbacks ordered borrow-chain if own sources are dark:
#                   ("station", key, "Name shown to the user")
#                   v16: the "satellite" kind is retired - see D137.
#   wind_history    ordered list of output["station_history"] keys:
#                   (key, None) = the pier's own station,
#                   (key, "Name") = borrowed from a neighbor, labeled ESTIMATED
#   zone            key in output["zones"] for forecast + alerts
#   lat / lon       v10: the pier's own verified position. All six were
#                   confirmed against a map by the owner on 2026-07-25
#                   (decision D63). Algoma's point is the City Marina
#                   BY DESIGN - there is no separate pier landmark
#                   there, the marina is where the piers are. Do not
#                   "correct" it.
PIERS = {
    "two_rivers": {
        "name": "Two Rivers / Neshotah",
        "lat": 44.147061,
        "lon": -87.565680,
        "buoy": "tr1",
        # v10: the second entry used to be ("station", "kw1", "Kewaunee").
        # No station anywhere in STATIONS carries the codename "kw1", so
        # that fallback silently resolved to nothing on every single run
        # while making the config look as though Two Rivers had a
        # Kewaunee backup. It never did. Removed.
        # 2026-07-31 (D133/v15): label changed from "Manitowoc" to "Open
        # Lake Buoy". mt1 was never Manitowoc's reading - it is buoy
        # 45210 under a second codename, the same offshore instrument
        # this pier's own "tr1" reads. Attributing it to a pier misled;
        # naming the actual source does not. (In practice this fallback
        # never fires: tr1 and mt1 are the same live fetch, so if tr1
        # goes dark mt1 is dark at the same instant. Left as-is; fixing
        # that redundancy is a separate, later change, not this one.)
        "water_fallbacks": [("station", "mt1", "Open Lake Buoy")],
        "wind_history": [("trw", None)],
        "zone": "trz",
    },
    "manitowoc": {
        "name": "Manitowoc",
        "lat": 44.091354,
        "lon": -87.643820,
        # 2026-07-31 (D133/v15): "buoy" used to be "mt1". mt1 is buoy
        # 45210, 26 miles offshore - the SAME reading Sheboygan,
        # Kewaunee, and Algoma all borrow through their own
        # water_fallbacks and honestly label ESTIMATED. Manitowoc was
        # the only pier calling this exact same reading its own LIVE
        # buoy. Same sensor, same instant, two different honesty
        # labels depending only on which pier's config was asked.
        # Removed so Manitowoc falls through the same chain as
        # everyone else: LMHOFS model -> (no own buoy) -> own
        # satellite -> water_fallbacks below -> Unknown.
        "buoy": None,
        # Was empty. Manitowoc's satellite point goes dark on cloudy
        # days (confirmed live 2026-07-31: unavailable, "likely cloud
        # cover") and now has nothing to fall back to if LMHOFS also
        # has a gap - it would show Unknown when a real, honestly-
        # labeled reading is available. tr1 (buoy 45210, Two Rivers'
        # own designated buoy) is a genuine, currently-live source;
        # borrowing it and saying so is honest, not a workaround.
        "water_fallbacks": [("station", "tr1", "Two Rivers")],
        "wind_history": [("mtw", None)],
        "zone": "mtz",
    },
    "sheboygan": {
        "name": "Sheboygan",
        "lat": 43.748595,
        "lon": -87.694910,
        "buoy": "SGNW3",
        # 2026-07-31 (D133/v15): mt1 relabeled from "Manitowoc" to "Open
        # Lake Buoy" - see the note on Two Rivers' identical fallback
        # above for why.
        "water_fallbacks": [("station", "mt1", "Open Lake Buoy"), ("station", "tr1", "Two Rivers")],
        "wind_history": [("KSBM", None)],
        "zone": "LMZ643",
    },
    "kewaunee": {
        "name": "Kewaunee",
        "lat": 44.457285,
        "lon": -87.493085,
        "buoy": None,
        # 2026-07-31 (D133/v15): mt1 relabeled from "Manitowoc" to "Open
        # Lake Buoy" - see the note on Two Rivers' identical fallback
        # above for why.
        "water_fallbacks": [("station", "tr1", "Two Rivers"), ("station", "mt1", "Open Lake Buoy")],
        "wind_history": [("kww", None)],
        "zone": "kwz",
    },
    "algoma": {
        "name": "Algoma",
        # City of Algoma Marina - confirmed by the owner as the correct
        # point. There is no separate pier landmark at Algoma.
        "lat": 44.608423,
        "lon": -87.433597,
        "buoy": None,
        # Deliberate design decision (matches the live Algoma page):
        # every borrowed water reading is labeled "Kewaunee" —
        # Algoma borrows whatever Kewaunee itself would show.
        "water_fallbacks": [
            ("station", "tr1", "Kewaunee"),
            ("station", "mt1", "Kewaunee"),
        ],
        "wind_history": [("agw", None), ("kww", "Kewaunee")],
        "zone": "algz",
    },
    "sturgeon_bay": {
        # CONFIRMED 2026-07-18 (build session decisions, made with
        # the owner):
        # - Zone: LMZ542 "Sturgeon Bay to Two Rivers" (via algz).
        #   The canal pier sits exactly on the LMZ541/LMZ542
        #   boundary; 542 covers the water at and south of the
        #   canal where the pier fishing happens, and matches
        #   Algoma next door.
        # - Wind: KSUE (Door County Cherryland Airport, ~7 mi from
        #   the pier) treated as LIVE local wind — the exact same
        #   standard as KMTW for Two Rivers/Manitowoc and KSBM for
        #   Sheboygan. The dormant CG station at the canal itself
        #   (sbcg / 0Y2W3) stays FIRST in the chain so it takes
        #   over automatically if NOAA ever revives it.
        # - Water: the old chain listed tr1 then mt1, but those are
        #   the SAME physical buoy (45210), so the second fallback
        #   was redundant. Replaced with buoy 45002 (northern Lake
        #   Michigan) — a genuinely independent backup, honestly
        #   labeled.
        "name": "Sturgeon Bay",
        "lat": 44.792050,
        "lon": -87.309627,
        "buoy": None,
        "water_fallbacks": [
            ("station", "tr1", "Two Rivers"),
            ("station", "45002", "Northern Lake Michigan"),
        ],
        "wind_history": [("sbcg", None), ("KSUE", None)],
        "zone": "algz",
    },
}

# Compass direction -> degrees, built from the COMPASS list above.
_COMPASS_DEG = {name: idx * 22.5 for idx, name in enumerate(COMPASS)}


# ---------------------------------------------------------------
# v10 - REAL DISTANCE. Project decision D14: every measured value
# shown on the site must carry a distance, computed here in the
# backend and never hand-written into a label. This is the function
# that makes that possible.
# ---------------------------------------------------------------
EARTH_RADIUS_MILES = 3958.7613


def haversine_miles(lat1, lon1, lat2, lon2):
    """Great-circle distance in statute miles between two points.

    Returns None if any coordinate is missing, so a station without a
    recorded position produces "no distance" rather than a wrong one.
    """
    if None in (lat1, lon1, lat2, lon2):
        return None
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = (sin(d_lat / 2) ** 2
         + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2)
    return round(2 * EARTH_RADIUS_MILES * asin(sqrt(a)), 2)


def _geo_by_codename(config):
    """Flatten a station config into codename -> {lat, lon, label, ...}.

    One physical station can answer to several codenames (buoy 45210 is
    both "tr1" and "mt1"), so every codename gets the same position.
    """
    out = {}
    for station_id, meta in config.items():
        entry = {
            "station_id": station_id,
            "label": meta.get("label"),
            "lat": meta.get("lat"),
            "lon": meta.get("lon"),
            "water_depth_ft": meta.get("water_depth_ft"),
        }
        for codename in meta.get("codenames", [meta.get("codename", station_id)]):
            out[codename] = entry
    return out


STATION_GEO = _geo_by_codename(STATIONS)
HISTORY_GEO = _geo_by_codename(STATION_HISTORY)


def distance_from_pier(pier_cfg, geo_map, codename):
    """Miles from this pier to the station behind `codename`."""
    station = geo_map.get(codename)
    if not station:
        return None
    return haversine_miles(pier_cfg.get("lat"), pier_cfg.get("lon"),
                           station.get("lat"), station.get("lon"))


def clamp(value, low, high):
    """Keep a number inside a range."""
    return max(low, min(high, value))


def westerly_component(dir_code):
    """How 'westerly' a wind direction is: W = +1 (good, offshore
    for Wisconsin's west-shore piers), E = -1 (bad, onshore).
    Unknown/missing directions count as 0 (neutral), exactly like
    the page implementation this was ported from."""
    import math
    deg = _COMPASS_DEG.get(dir_code)
    if deg is None:
        return 0.0
    return math.cos((deg - 270.0) * math.pi / 180.0)


def score_wind(history, zone_forecast, borrowed_from, now=None):
    """0-100 wind factor. Prefers real hourly history (LIVE, or
    LIVE_STALE past STALE_AFTER_HOURS, or ESTIMATED when the history
    belongs to a neighbor); falls back to the zone forecast direction
    (FORECAST). Ported exactly from the Two Rivers page, including the
    'recent onshore shift' penalty.

    v19 (D182): a non-borrowed reading older than STALE_AFTER_HOURS
    returns LIVE_STALE instead of LIVE, so the frontend can render a
    visually distinct dot for "real reading, but running late" instead
    of showing the same filled dot as a fresh one. Borrowed (ESTIMATED)
    readings are not affected — that source value already carries its
    own distinct meaning and staleness there would overload it."""
    if history and history.get("available") and history.get("hourly"):
        hourly = history["hourly"]
        comps = [westerly_component(h.get("dir")) for h in hourly]
        recent = [westerly_component(h.get("dir")) for h in hourly if h.get("hours_ago", 99) <= 12]
        j = sum(comps) / len(comps) if comps else 0.0
        z = sum(recent) / len(recent) if recent else j
        score = round(clamp(50 + 38 * j, 5, 90))
        if j > 0.25 and z < -0.1:
            score = round(clamp(score - 22, 5, 95))
        if borrowed_from:
            return {"score": score, "source": "ESTIMATED", "source_name": borrowed_from}
        age_hours = None
        obs_iso = history.get("observed_at_utc")
        if obs_iso and now is not None:
            age_hours = (now - datetime.fromisoformat(obs_iso)).total_seconds() / 3600.0
        if age_hours is not None and age_hours > STALE_AFTER_HOURS:
            return {"score": score, "source": "LIVE_STALE", "source_name": None}
        return {"score": score, "source": "LIVE", "source_name": None}
    if zone_forecast and zone_forecast.get("available") and zone_forecast.get("wind_dir"):
        score = round(clamp(50 + 40 * westerly_component(zone_forecast["wind_dir"]), 5, 95))
        return {"score": score, "source": "FORECAST", "source_name": None}
    return None


def score_water_trend(change_72h_f):
    """The 72-hour trend contribution, in score points.

    Two saturating branches, no hard clamp (D108, D116). tanh
    approaches but never reaches 1, so TREND_COOL_MAX and
    TREND_WARM_MAX are asymptotes rather than walls: a -19F event
    always scores strictly above a -18.7F one, however close both get
    to the ceiling. That is a stronger guarantee than a low pegging
    rate — the pegging rate here is architecturally zero.

    Cooling is favoured 3.20:1 over warming, deliberately (D107).
    The base curve above already prices how warm the water IS, so a
    large warming penalty here would charge a pier twice for one fact.
    What the base curve CANNOT see is how fast the water is moving:
    two piers both sitting at 52F are not the same pier if one dropped
    9F getting there and the other has been stable all week.

    None means this pier has no usable history. It returns exactly
    zero — never a borrowed value from another pier or another window.
    """
    if change_72h_f is None:
        return 0.0
    if change_72h_f < 0:
        return TREND_COOL_MAX * tanh(-change_72h_f / TREND_K_COOL)
    if change_72h_f > 0:
        return -TREND_WARM_MAX * tanh(change_72h_f / TREND_K_WARM)
    return 0.0


def score_water(temp_f, change_72h_f):
    """0-100 water-temperature factor.

    BASE CURVE — unchanged, and deliberately so (D109). An ideal band
    around 50-56F with penalties as it warms. Measured across 30 days
    of committed nearshore data it discriminates well: median spread
    across the six piers is 21.7 points, and only 3 of 30 days go
    quiet. Do not rebuild it on the evidence of a single flat day.

    TREND — replaced in v13. The old term was
    clamp(2.4 * -change_72h_f, -20, 12), calibrated for a buoy 26
    miles offshore and pegging at a clamp on 57% of real nearshore
    samples, which made every large upwelling score identically. See
    score_water_trend() and the module docstring.
    """
    if 50 <= temp_f <= 56:
        base = 72
    elif temp_f < 50:
        base = 72 - 2.2 * (50 - temp_f)
    elif temp_f <= 62:
        base = 72 - 4 * (temp_f - 56)
    else:
        base = 48 - 7 * (temp_f - 62)
    base = clamp(base, 3, 82)
    trend = score_water_trend(change_72h_f)
    return round(clamp(base + trend, 5, 98))


def _interp(x, x0, x1, y0, y1):
    """Straight-line interpolation between two points. Used by the
    v9 wave curve so scores change smoothly between breakpoints
    instead of jumping in flat steps."""
    t = (x - x0) / (x1 - x0)
    return y0 + t * (y1 - y0)


def score_waves(wave_ft):
    """0-100 Lake Conditions factor from wave height.

    REPLACED in v9. OLD version was a flat 4-tier lookup where
    anything past 5ft scored a fixed 14 no matter how much rougher
    it got (6ft and 20ft scored identically), PLUS it force-capped
    the score to 24 whenever ANY marine alert was active — even a
    calm day under a Small Craft Advisory would score like a rough
    one. Both of those were caught directly from a live screenshot
    (2026-07-24): a real 1.3ft, calm day scored "24" only because an
    advisory happened to be active elsewhere in the forecast window.

    NEW: a smooth curve that keeps responding all the way past 12ft,
    and NO alert-based override — this factor now reflects real,
    measured or forecast wave height ONLY. Safety messaging for
    rough/dangerous conditions is handled separately by the Small
    Craft Advisory banner (unchanged) and the new Beach Hazards
    Statement banner — not by silently distorting this score."""
    if wave_ft <= 1.5:
        return 90
    if wave_ft <= 3:
        return round(_interp(wave_ft, 1.5, 3, 90, 72))
    if wave_ft <= 5:
        return round(_interp(wave_ft, 3, 5, 72, 38))
    if wave_ft <= 8:
        return round(_interp(wave_ft, 5, 8, 38, 14))
    if wave_ft <= 12:
        return round(_interp(wave_ft, 8, 12, 14, 2))
    return 2


# NEW in v9 — the Storm/Clarity factor. This slot has existed in
# every pier's factor list since v5 but was NEVER computed (always
# scored None) — every score has really only ever been a 3-factor
# average, not the intended 4. Turned on for real here.
#
# Deliberately built from the FULL alerts list (FIX A), not just the
# first alert, and deliberately EXCLUDES Beach Hazards Statements —
# those are about swim/pier safety, not fishing quality, and are
# shown to visitors via their own separate banner instead.
_STORM_SEVERITY_KEYWORDS = [
    ("storm warning", 10),
    ("hurricane", 2),
    ("gale", 25),
    ("small craft", 55),
    ("dense fog", 65),
    ("dense smoke", 65),
]


def score_storm_clarity(alerts):
    """0-100 Storm/Clarity factor. Looks at every active alert for
    the zone (not just the first) and returns the WORST match among
    boater/fishing-relevant alert types. Beach Hazards Statements are
    intentionally ignored here — see module docstring FIX D."""
    if not alerts:
        return 90, None
    worst_score = 90
    worst_event = None
    for a in alerts:
        event = (a.get("event") or "").lower()
        if "beach hazard" in event:
            continue  # handled by the separate beach_hazard banner, not this score
        for keyword, sc in _STORM_SEVERITY_KEYWORDS:
            if keyword in event and sc < worst_score:
                worst_score = sc
                worst_event = a.get("event")
    return worst_score, worst_event


def resolve_water(pier_id, pier_cfg, output):
    """Walk one pier's water-temperature source chain, most-honest
    source first.

    v11 order: LMHOFS nearshore model -> own live buoy -> own satellite
    point -> borrowed neighbor readings. Returns None if every source
    is dark.

    WHY THE MODEL OUTRANKS A REAL THERMOMETER. It looks backwards, and
    it is the central judgement of this release. A measurement is only
    better than a simulation if it is a measurement OF THE RIGHT THING.
    Buoy 45210 is a genuine, accurate, well-maintained thermometer
    reading water 26 miles offshore and 475 feet deep — water an angler
    standing on a pier will never fish. LMHOFS estimates the water
    actually at the pier. So the model wins, and it is labelled MODELED
    every single time so nobody mistakes the estimate for a reading
    (C13, D64).
    """
    stations = output.get("stations", {})

    model = output.get("model_water_temp", {})
    if model.get("available"):
        point = model.get("points", {}).get(pier_id, {})
        if point.get("available") and isinstance(point.get("water_temp_f"), (int, float)):
            return {
                "temp_f": point["water_temp_f"],
                "source": "MODELED",
                "source_name": None,
                "source_key": pier_id,
                "source_kind": "model",
                # v13 (Phase 1.3c): a REAL nearshore 72-hour trend, read
                # from the run three days earlier at this same frozen
                # node. Replaces a trend that used to be measured at the
                # DEEP-WATER buoy, where the nearshore upwelling this
                # site reports does not occur.
                #
                # None here is meaningful and safe: it means this pier's
                # history was unavailable, and score_water() gives a
                # trend contribution of exactly zero. No pier ever
                # borrows another pier's trend (no-borrowing rule).
                #
                # 24h is still None — the site reports a 72-hour window
                # and does not claim a 24-hour one it has not calibrated.
                "change_24h_f": None,
                "change_72h_f": point.get("water_change_72h_f"),
            }

    buoy_key = pier_cfg.get("buoy")
    if buoy_key:
        own = stations.get(buoy_key, {})
        if own.get("available") and isinstance(own.get("water_temp_f"), (int, float)):
            return {
                "temp_f": own["water_temp_f"],
                "source": "LIVE",
                "source_name": None,
                # v10: which source actually supplied this reading, so
                # the distance to THAT source can be computed.
                "source_key": buoy_key,
                "source_kind": "station",
                "change_24h_f": own.get("water_change_24h_f"),
                "change_72h_f": own.get("water_change_72h_f"),
            }

    for kind, key, name in pier_cfg.get("water_fallbacks", []):
        # v16 (D137): only station fallbacks exist. Anything else is
        # skipped rather than resolved against a pool that no longer
        # exists - validate_config() reports it as a config error.
        if kind != "station":
            continue
        src = stations.get(key, {})
        if src.get("available") and isinstance(src.get("water_temp_f"), (int, float)):
            return {
                "temp_f": src["water_temp_f"],
                "source": "ESTIMATED",
                "source_name": name,
                "source_key": key,
                "source_kind": kind,
                "change_24h_f": None,
                "change_72h_f": None,
            }
    return None


def band_for(score):
    """Score band label + the site color token it maps to."""
    if score is None:
        return {"label": "Not enough data", "tone": "muted"}
    if score >= 85:
        return {"label": "Strong Setup", "tone": "good"}
    if score >= 70:
        return {"label": "Good", "tone": "good"}
    if score >= 50:
        return {"label": "Fair", "tone": "gold"}
    if score >= 30:
        return {"label": "Slow", "tone": "warn"}
    return {"label": "Poor", "tone": "bad"}


# -----------------------------------------------------------------
# v17 (Phase 1.7, decision D144) - VISITOR-FACING SOURCE TIERS.
#
# The left column is what the backend thinks. The right column is
# what a visitor reads. They are deliberately different vocabularies:
# the backend needs precision, the visitor needs plain words.
#
#   LIVE       -> Measured  (an instrument, at this pier)
#   ESTIMATED  -> Measured  (an instrument, at a neighbouring pier)
#   MODELED    -> Modeled   (NOAA's LMHOFS simulation, at this pier)
#   FORECAST   -> Forecast  (NWS prediction for an area)
#   MISSING    -> Unknown   (nothing resolved - say so plainly)
#
# ESTIMATED sitting under Measured is the deliberate call. See D144
# in the header. The short version: it IS a measurement, and the
# thing that makes it different - that it was taken somewhere else -
# is carried by "locality" and by the distance figure, not by
# pretending a thermometer is a simulation.
#
# Symbols are the ones fixed by D12 and must not be re-picked here:
#   Measured (filled) / Modeled (half) / Forecast (quarter) /
#   Unknown (hollow).
SOURCE_TIERS = {
    "LIVE":       {"tier": "Measured", "symbol": "\u25CF", "locality": "at_pier"},
    "LIVE_STALE": {"tier": "Measured", "symbol": "\u25CF", "locality": "at_pier"},   # v19 (D182) — genuinely a measurement, tier unchanged; only the frontend dot rendering distinguishes it from fresh LIVE
    "ESTIMATED":  {"tier": "Measured", "symbol": "\u25CF", "locality": "borrowed"},
    "MODELED":   {"tier": "Modeled",  "symbol": "\u25D0", "locality": "at_pier"},
    "FORECAST":  {"tier": "Forecast", "symbol": "\u25D4", "locality": "area"},
    "MISSING":   {"tier": "Unknown",  "symbol": "\u25CB", "locality": None},
}


def source_tier_block(code, distance_mi=None, expect_distance=False,
                      what=None, pier_id=None):
    """Translate one internal source code into the three
    visitor-facing keys. Pure function - reads nothing, writes
    nothing, and cannot affect any score.

    expect_distance=True marks a STATION-BACKED field (water, wind,
    waves), i.e. one where a real instrument implies a real place.
    Passing True turns on the honesty guard described in the header:
    a Measured reading we cannot locate is reported with locality
    "unknown" rather than being allowed to look like it came from
    the pier. It keeps its Measured tier, because it genuinely is a
    measurement - understating it would be a lie in the other
    direction.

    An unrecognised code falls to Unknown rather than raising. A new
    code appearing here should surface as an honest "Unknown" on the
    page, never as a crashed build."""
    entry = SOURCE_TIERS.get(code)
    if entry is None:
        print("WARNING: unrecognised source code %r (%s%s) - "
              "reporting as Unknown."
              % (code, pier_id or "?", "/" + what if what else ""))
        entry = SOURCE_TIERS["MISSING"]
    locality = entry["locality"]
    if entry["tier"] == "Measured" and expect_distance and distance_mi is None:
        print("WARNING: %s %s is Measured but has no distance-to-pier. "
              "Reporting locality 'unknown'. Check that its station has "
              "coordinates in config."
              % (pier_id or "?", what or "value"))
        locality = "unknown"
    return {
        "tier": entry["tier"],
        "tier_symbol": entry["symbol"],
        "locality": locality,
    }


def build_piers(output):
    """Compute the finished, ready-to-display block for every pier
    from the raw sections already collected above. Makes no extra
    network requests."""
    piers_out = {}
    model_block = output.get("model_water_temp", {})
    now = datetime.now(timezone.utc)   # v18 (D173) — single reference time for wind_headline age_hours
    for pier_id, cfg in PIERS.items():
        stations = output.get("stations", {})
        zones = output.get("zones", {})
        histories = output.get("station_history", {})

        zone = zones.get(cfg["zone"], {})
        forecast = zone.get("forecast", {"available": False})
        alert = zone.get("alert", {"active": False})
        alert_active = bool(alert.get("active"))
        all_alerts = zone.get("alerts", [])
        beach_hazard = zone.get("beach_hazard", {"active": False})

        # --- Wind factor: first history source in the chain that
        # has real data wins; otherwise fall back to the forecast.
        wind_factor = None
        wind_hist_key = None   # v10: which station actually supplied wind
        for hist_key, borrowed_from in cfg.get("wind_history", []):
            hist = histories.get(hist_key)
            if hist and hist.get("available") and hist.get("hourly"):
                wind_factor = score_wind(hist, None, borrowed_from, now)   # v19 (D182) — now passed for staleness check
                obs_iso = hist.get("observed_at_utc")   # v18 (D173)
                wind_headline = {
                    "dir": hist.get("current_wind_dir"),
                    "mph": hist.get("current_wind_mph"),
                    "mph_low": None,
                    "mph_high": None,
                    "source": wind_factor["source"],
                    "source_name": wind_factor.get("source_name"),
                    "observed_at_utc": obs_iso,   # v18 (D173)
                    "age_hours": (
                        round((now - datetime.fromisoformat(obs_iso)).total_seconds() / 3600.0, 1)
                        if obs_iso else None
                    ),   # v18 (D173)
                }
                wind_hist_key = hist_key
                break
        else:
            wind_factor = score_wind(None, forecast, None)
            if wind_factor:
                wind_headline = {
                    "dir": forecast.get("wind_dir"),
                    "mph": None,
                    "mph_low": forecast.get("wind_mph_low"),
                    "mph_high": forecast.get("wind_mph_high"),
                    "source": "FORECAST",
                    "source_name": None,
                    "observed_at_utc": None,   # v18 (D173) — forecast has no observation timestamp
                    "age_hours": None,   # v18 (D173)
                }
            else:
                wind_headline = {"dir": None, "mph": None, "mph_low": None,
                                 "mph_high": None, "source": None, "source_name": None,
                                 "observed_at_utc": None, "age_hours": None}   # v18 (D173)

        # --- Water factor.
        water = resolve_water(pier_id, cfg, output)
        if water is not None:
            water_score = score_water(water["temp_f"], water["change_72h_f"])
        else:
            water_score = None

        # --- Waves factor: own buoy reading first, else forecast range.
        # v9: score_waves() no longer takes alert_active — see FIX C.
        wave_ft = None
        wave_source = None
        buoy = stations.get(cfg["buoy"], {}) if cfg.get("buoy") else {}
        if buoy.get("available") and isinstance(buoy.get("wave_ft"), (int, float)):
            wave_ft = buoy["wave_ft"]
            wave_source = "LIVE"
        elif (forecast.get("available")
              and forecast.get("wave_ft_low") is not None
              and forecast.get("wave_ft_high") is not None):
            wave_ft = (forecast["wave_ft_low"] + forecast["wave_ft_high"]) / 2
            wave_source = "FORECAST"

        # --- NEW in v9: Storm/Clarity factor, actually computed now.
        storm_score, storm_event = score_storm_clarity(all_alerts)

        # --- NEW in v10: where these numbers physically came from, and
        # how far that is from this pier. Satellite points are grid
        # cells rather than instruments, so they get a label but no
        # distance - claiming a distance to a model cell would be the
        # same kind of false precision this release exists to remove.
        water_station_label = None
        water_distance_mi = None
        if water is not None:
            if water.get("source_kind") == "model":
                # v11. The distance was computed from the coordinates
                # NOAA published for this node on THIS run — see
                # lmhofs_read_node(). Note the label carries no distance
                # in its text: distance travels in its own field so it
                # can never go stale inside a sentence (C19, D87).
                point = (output.get("model_water_temp", {})
                         .get("points", {}).get(water.get("source_key"), {}))
                water_station_label = (
                    "NOAA LMHOFS nearshore model \u2014 grid node %s"
                    % point.get("node")
                )
                water_distance_mi = point.get("distance_mi")
            elif water.get("source_kind") == "station":
                geo = STATION_GEO.get(water.get("source_key"))
                if geo:
                    water_station_label = geo.get("label")
                    water_distance_mi = distance_from_pier(
                        cfg, STATION_GEO, water["source_key"])

        # v11 (D86): the wave number gets the same treatment every other
        # number now gets — say where it came from. A buoy reading gets
        # the buoy's real label and a computed distance. A forecast gets
        # the marine zone's name and NO distance, because a zone forecast
        # covers a stretch of coastline rather than a point, so there is
        # nothing honest to measure a distance to (C22).
        wave_station_label = None
        wave_distance_mi = None
        if wave_source == "LIVE" and cfg.get("buoy"):
            wave_geo = STATION_GEO.get(cfg["buoy"])
            if wave_geo:
                wave_station_label = wave_geo.get("label")
                wave_distance_mi = distance_from_pier(cfg, STATION_GEO, cfg["buoy"])
        elif wave_source == "FORECAST":
            wave_station_label = (
                "NWS marine forecast \u2014 %s" % zone.get("label")
                if zone.get("label") else "NWS marine forecast"
            )

        wind_station_label = None
        wind_distance_mi = None
        if wind_hist_key:
            geo = HISTORY_GEO.get(wind_hist_key)
            if geo:
                wind_station_label = geo.get("label")
                wind_distance_mi = distance_from_pier(
                    cfg, HISTORY_GEO, wind_hist_key)

        # --- Assemble the four factors (weights: wind 30, water 30,
        # lake conditions 20, clarity/storm 20 — all four now
        # genuinely scored as of v9, not three out of four).
        factors = []
        if wind_factor:
            factors.append({
                "label": "Wind / Upwelling", "score": wind_factor["score"], "weight": 30,
                "source": wind_factor["source"], "source_name": wind_factor.get("source_name"),
            })
        else:
            factors.append({"label": "Wind / Upwelling", "score": None, "weight": 30,
                            "source": "MISSING", "source_name": None})
        if water_score is not None:
            factors.append({
                "label": "Water Temperature", "score": water_score, "weight": 30,
                "source": water["source"], "source_name": water["source_name"],
            })
        else:
            factors.append({"label": "Water Temperature", "score": None, "weight": 30,
                            "source": "MISSING", "source_name": None})
        if wave_ft is not None:
            factors.append({
                "label": "Lake Conditions", "score": score_waves(wave_ft),
                "weight": 20, "source": wave_source, "source_name": None,
            })
        else:
            factors.append({"label": "Lake Conditions", "score": None, "weight": 20,
                            "source": "MISSING", "source_name": None})
        factors.append({
            "label": "Clarity / Storm", "score": storm_score, "weight": 20,
            "source": "FORECAST" if storm_event else "LIVE",
            "source_name": storm_event,
            "note": None if storm_event else "no active storm-relevant alert",
        })

        # --- Weighted total over the factors that actually scored.
        scored = [f for f in factors if f["score"] is not None]
        total_weight = sum(f["weight"] for f in scored)
        score = (round(sum(f["score"] * (f["weight"] / total_weight) for f in scored))
                 if total_weight > 0 else None)

        incomplete = False
        capped = {"active": False, "reason": None}
        # v12 — Phase 1.3b (D18, D84). The cap now fires ONLY on a
        # MODELED reading — the LMHOFS nearshore node actually at the
        # pier. It does NOT fire on LIVE (the own buoy, 26-52 mi
        # offshore), SATELLITE, or ESTIMATED (borrowed from a
        # neighboring pier's station). A warm reading from open water
        # or a neighbor's station says nothing true about temperature
        # at THIS pier's shoreline, so it must not silently suppress
        # this pier's score. Deliberately conservative: on a day
        # LMHOFS is stale (>36h, see D82) and a pier falls back to its
        # buoy, the cap simply does not apply to that fallback reading
        # rather than guessing whether it would have. Most days this
        # changes nothing (real nearshore temps are 53.8-58.6 F, well
        # under the 68 F floor) — it only matters on stale-model days,
        # which is why it ships as its own deploy (C5).
        if score is not None and water is not None and water["source"] == "MODELED":
            t = water["temp_f"]
            uncapped_score = score
            if t >= 74:
                score = min(score, 10)
            elif t >= 72:
                score = min(score, 20)
            elif t >= 70:
                score = min(score, 28)
            elif t >= 68:
                score = min(score, 44)
            if score < uncapped_score:
                capped = {
                    "active": True,
                    "reason": "Score capped \u2014 water is too warm for strong salmon and trout activity right now.",
                }
        if score is not None and water is None:
            # No water temp from any source -> capped and visibly
            # marked incomplete, never quietly stretched.
            score = min(score, 55)
            incomplete = True

        estimated_labels = [f["label"] for f in scored if f["source"] == "ESTIMATED"]

        # v11 — RISK R26, and a second bug found while fixing it.
        # This was "scored factors minus ESTIMATED factors", which meant
        # a FORECAST factor counted as verified, and a MODELED one would
        # have too. The frontend prints this number as "N of 4 factors
        # measured live". On 2026-07-27 Sheboygan was publishing 3 when
        # exactly one of its factors was genuinely measured. A factor is
        # now counted only when its source is literally LIVE. This
        # LOWERS the number on several piers. The lower number is true.
        verified_count = len([f for f in scored if f["source"] == "LIVE"])

        # v17 (D144). Add the three visitor-facing keys to every
        # factor. Done HERE, after verified_count and
        # estimated_labels are computed, so it is impossible for
        # this block to influence either of them - both read
        # f["source"], which is not touched.
        #
        # Clarity / Storm is the only factor with no station behind
        # it, so it passes expect_distance=False and is exempt from
        # the distance guard. The other three are station-backed.
        _factor_distance = {
            "Wind / Upwelling": (wind_distance_mi, True),
            "Water Temperature": (water_distance_mi, True),
            "Lake Conditions": (wave_distance_mi, True),
            "Clarity / Storm": (None, False),
        }
        for f in factors:
            _dist, _expect = _factor_distance.get(f["label"], (None, False))
            f.update(source_tier_block(
                f["source"], distance_mi=_dist, expect_distance=_expect,
                what=f["label"], pier_id=pier_id))

        piers_out[pier_id] = {
            "name": cfg["name"],
            "score": score,
            "band": band_for(score),
            "incomplete": incomplete,
            "capped": capped,
            "verified_count": verified_count,
            "factor_total": 4,
            "estimated_factors": estimated_labels,
            "factors": factors,
            "alert_active": alert_active,
            # NEW in v9: pier-level pass-through so the frontend never
            # has to dig into the raw zones section to build the
            # Beach Hazards banner — matches the existing pattern
            # used for "capped".
            "beach_hazard": beach_hazard,
            "coordinates": {"lat": cfg.get("lat"), "lon": cfg.get("lon")},
            "headline": {
                "water_temp_f": water["temp_f"] if water else None,
                "water_temp_source": water["source"] if water else None,
                "water_temp_from": water["source_name"] if water else None,
                # v10 (D14): the station actually behind this reading,
                # and how far it is from THIS pier. Computed, never
                # hand-written. None when the source has no recorded
                # position - "no distance" beats a wrong distance.
                "water_temp_station_label": water_station_label,
                "water_temp_distance_mi": water_distance_mi,
                # v17 (D144). Visitor-facing translation of
                # water_temp_source, which is left exactly as it was.
                # A missing source is normalised to "MISSING" so the
                # honest word "Unknown" is published rather than a
                # null the frontend has to interpret.
                **{("water_temp_" + k): v for k, v in source_tier_block(
                    (water["source"] if water else None) or "MISSING",
                    distance_mi=water_distance_mi, expect_distance=True,
                    what="water temperature", pier_id=pier_id).items()},
                # v11 (D82). Repeated here on purpose: a pier box should
                # be able to disclose how old the model run is without
                # reaching into a different top-level section. Both are
                # None whenever the reading did not come from the model.
                "water_temp_model_run_utc": (
                    model_block.get("run_time_utc")
                    if water and water.get("source_kind") == "model" else None),
                "water_temp_model_age_hours": (
                    model_block.get("run_age_hours")
                    if water and water.get("source_kind") == "model" else None),
                "water_temp_model_disclose_age": (
                    bool(model_block.get("disclose_age"))
                    if water and water.get("source_kind") == "model" else False),
                "water_change_24h_f": water["change_24h_f"] if water else None,
                "water_change_72h_f": water["change_72h_f"] if water else None,
                "wind": wind_headline,
                "wind_station_label": wind_station_label,
                "wind_distance_mi": wind_distance_mi,
                # v17 (D144). Flat keys, matching the existing
                # wind_station_label / wind_distance_mi pattern,
                # rather than reaching inside the nested "wind" dict
                # that the pier boxes already read.
                **{("wind_" + k): v for k, v in source_tier_block(
                    wind_headline.get("source") or "MISSING",
                    distance_mi=wind_distance_mi, expect_distance=True,
                    what="wind", pier_id=pier_id).items()},
                "wave_ft": round(wave_ft, 1) if wave_ft is not None else None,
                "wave_source": wave_source,
                # v11 (D86). The Two Rivers pier boxes were already
                # written to read these and were correctly showing no
                # wave distance at all because they did not yet exist.
                "wave_station_label": wave_station_label,
                "wave_distance_mi": wave_distance_mi,
                # v17 (D144).
                **{("wave_" + k): v for k, v in source_tier_block(
                    wave_source or "MISSING",
                    distance_mi=wave_distance_mi, expect_distance=True,
                    what="waves", pier_id=pier_id).items()},
                "pressure_hpa": buoy.get("pressure_hpa") if buoy.get("available") else None,
                "pressure_tendency_3h_hpa": (buoy.get("pressure_tendency_3h_hpa")
                                             if buoy.get("available") else None),
            },
        }
    return piers_out


# v11 (D83). The badge originally required LIVE water, because the
# alternative at the time was a borrowed reading from another pier and
# a badge based on borrowed data means nothing. MODELED is a different
# thing entirely: it is this pier's own water, estimated at this pier.
#
# THIS LINE IS WHY THE CHANGE MATTERS. Once water becomes MODELED, a
# LIVE-only rule matches no pier at all, and the badge disappears from
# the home page and all six pier pages — with no error, nothing in the
# logs, and nothing visibly broken. It would simply stop existing. That
# was found by tracing the consequence of the source change before
# deploying it, not by noticing it missing afterwards.
HOT_PIER_ELIGIBLE_WATER_SOURCES = ("LIVE", "MODELED")


def compute_hot_piers(piers):
    """The HOT PIER TODAY badge, computed once here so the home
    page and pier pages can never disagree. Rule (decided
    2026-07-16, amended v11 by D83): only piers whose water temp is
    the pier's OWN — measured live or modelled at the pier — can win.
    A borrowed reading still cannot. Genuine ties all get the badge;
    if no pier qualifies today, nobody gets it."""
    live = {pid: p for pid, p in piers.items()
            if p["headline"]["water_temp_source"] in HOT_PIER_ELIGIBLE_WATER_SOURCES
            and p["score"] is not None}
    if not live:
        return []
    top = max(p["score"] for p in live.values())
    return sorted(pid for pid, p in live.items() if p["score"] == top)



def main():
    output = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stations": {},
        "zones": {},
        "station_history": {},
        # v16 (D137): the satellite tier is retired. This key is kept,
        # permanently empty, purely so any older frontend box that
        # still reads it gets an empty object rather than a crash.
        # It can be deleted once every embed is confirmed clean.
        "satellite_water_temp": {},
    }

    # v11 (risk R25) — run this FIRST, before any network work, so a
    # broken reference is visible at the very top of the Actions log
    # rather than buried under 50 fetch lines.
    config_warnings = validate_config()
    output["config_warnings"] = config_warnings
    if config_warnings:
        print("CONFIG WARNINGS — a pier references something that is not defined:")
        for warning in config_warnings:
            print("  ! %s" % warning)
        print("Continuing anyway: stale-but-correct data beats no data.\n")
    else:
        print("Config self-audit: every referenced codename resolves.\n")

    for station_id, meta in STATIONS.items():
        try:
            readings = fetch_station(station_id)
            summary = summarize_station(station_id, readings)
        except Exception as err:
            summary = {"available": False, "error": str(err)}
        summary["label"] = meta["label"]
        # v10: the station's real published position travels with its
        # reading, so "where did this come from" is answerable from the
        # data itself rather than from a descriptive string.
        summary["lat"] = meta.get("lat")
        summary["lon"] = meta.get("lon")
        summary["water_depth_ft"] = meta.get("water_depth_ft")
        # A single physical station can feed more than one pier (e.g. a
        # shared buoy) — write the same reading under every codename that
        # points to it, without fetching it twice.
        for codename in meta.get("codenames", [meta.get("codename", station_id)]):
            output["stations"][codename] = summary

    for station_id, meta in STATION_HISTORY.items():
        try:
            history = fetch_station_history(station_id)
        except Exception as err:
            history = {"available": False, "error": str(err)}
        history["label"] = meta["label"]
        history["lat"] = meta.get("lat")
        history["lon"] = meta.get("lon")
        for codename in meta.get("codenames", [meta.get("codename", station_id)]):
            output["station_history"][codename] = history

    for zone_id, meta in ZONES.items():
        zone_result = {"label": meta["label"]}
        try:
            zone_result["forecast"] = fetch_zone_forecast(zone_id)
        except Exception as err:
            zone_result["forecast"] = {"available": False, "error": str(err)}
        try:
            alert_result = fetch_zone_alerts(zone_id)
        except Exception as err:
            alert_result = {"active": False, "error": str(err), "alerts": [],
                             "beach_hazard": {"active": False}}
        zone_result["alert"] = {
            k: v for k, v in alert_result.items() if k not in ("alerts", "beach_hazard")
        }
        zone_result["alerts"] = alert_result.get("alerts", [])
        zone_result["beach_hazard"] = alert_result.get("beach_hazard", {"active": False})
        for codename in meta.get("codenames", [meta.get("codename", zone_id)]):
            output["zones"][codename] = zone_result

    # --- v11: nearshore water temperature. This is the last raw
    # section fetched and the first one the scoring engine reaches for.
    try:
        output["model_water_temp"] = fetch_lmhofs()
    except Exception as err:  # noqa: BLE001
        output["model_water_temp"] = {
            "available": False, "points": {},
            "error": "LMHOFS fetch failed outright: %s" % err,
        }
    model_status = output["model_water_temp"]
    if model_status.get("available"):
        good = [pid for pid, p in model_status["points"].items() if p.get("available")]
        print("LMHOFS: run %s (%.1f h old), %d of %d nodes read."
              % (model_status.get("run_time_utc"),
                 model_status.get("run_age_hours") or 0.0,
                 len(good), len(model_status["points"])))
    else:
        print("LMHOFS UNAVAILABLE: %s" % model_status.get("error"))
        print("Piers fall back to their existing water sources (D82).")

    # --- Finished per-pier scores + data-contract fields. Added
    # AFTER all raw sections so it works purely from data already
    # collected above (no extra network requests).
    output["schema_version"] = SCHEMA_VERSION
    output["stale_after_hours"] = STALE_AFTER_HOURS
    output["piers"] = build_piers(output)
    output["hot_piers_today"] = compute_hot_piers(output["piers"])
    output["open_lake_context"] = build_open_lake_context(output)

    with open("data.json", "w") as f:
        json.dump(output, f, indent=2)

    print("Wrote data.json:")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
