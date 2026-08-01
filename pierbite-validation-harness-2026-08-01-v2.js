/* PIERBITE validation harness | 2026-08-01 | v2
   Runs every standing check on a Carrd Code Embed file, plus the new
   staleness checks that the 2026-08-01 Kewaunee incident exposed.

   Usage:  node validate-carrd-file.js <path-to-html-file>

   Checks run, in order:
     1. JS syntax          (node --check on the extracted <script> body)
     2. Curly-quote scan   (smart quotes silently break JS strings)
     3. Character count    (hard Carrd limit is 16,384)
     4. Render: real live data.json          — regression
     5. Render: one station 8h stale         — NEW, the Kewaunee case
     6. Render: one station 30h stale        — NEW, extreme lag
     7. Render: one station unavailable      — dormant-station case
     8. Render: all distances null           — prevents "null mi"
     9. Render: water temp null              — prevents "null degF"

   Checks 5 and 6 look for an age disclosure in the rendered output.
   If a file prints "NOW" or a bare hour count while a station is hours
   behind, and never says how old the reading is, that is a FAIL --
   the page is making a claim the data does not support.
*/

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const { JSDOM } = require('jsdom');

const TARGET = process.argv[2];
const CHAR_LIMIT = 16384;
const STALE_THRESHOLD_HOURS = 3;

if (!TARGET) {
  console.error('Usage: node validate-carrd-file.js <path-to-html-file>');
  process.exit(1);
}

const html = fs.readFileSync(TARGET, 'utf8');
const results = [];
function record(name, pass, detail) {
  results.push({ name, pass, detail });
  const tag = pass === true ? 'PASS' : pass === 'WARN' ? 'WARN' : 'FAIL';
  console.log(`[${tag}] ${name}${detail ? ' — ' + detail : ''}`);
}

/* ---------- 1. extract + syntax ---------- */
const scriptMatch = html.match(/<script>([\s\S]*)<\/script>/);
if (!scriptMatch) {
  record('Extract <script> body', false, 'no <script> block found');
  process.exit(1);
}
const jsBody = scriptMatch[1];
const tmpJs = path.join('/tmp', 'pb-extract-' + Date.now() + '.js');
fs.writeFileSync(tmpJs, jsBody);
try {
  execSync(`node --check ${tmpJs}`, { stdio: 'pipe' });
  record('JS syntax', true);
} catch (e) {
  record('JS syntax', false, e.stderr.toString().split('\n')[0]);
  process.exit(1);
}

/* ---------- 2. curly quotes ---------- */
const curly = [...html].filter(c => '\u2018\u2019\u201c\u201d'.includes(c));
record('Curly-quote scan', curly.length === 0,
  curly.length === 0 ? 'none found' : `${curly.length} smart quote(s) present`);

/* ---------- 3. size ---------- */
const bytes = Buffer.byteLength(html, 'utf8');
const margin = CHAR_LIMIT - bytes;
record('Character count', margin >= 300,
  `${bytes} chars, ${margin} under the ${CHAR_LIMIT} limit (${(bytes / CHAR_LIMIT * 100).toFixed(1)}%)`);

/* ---------- render helper ---------- */
function renderWith(data) {
  const ids = [...html.matchAll(/id="([^"]+)"/g)].map(m => m[1]);
  const stubs = ids.map(i => `<div id="${i}"></div>`).join('');
  const dom = new JSDOM(`<!DOCTYPE html><html><body>${stubs}</body></html>`);
  global.window = dom.window;
  global.document = dom.window.document;
  global.fetch = () => Promise.resolve({ json: () => Promise.resolve(data) });
  const indirectEval = eval;
  try {
    indirectEval(jsBody);
  } catch (e) {
    return { error: e.message, text: '', html: '' };
  }
  return new Promise(resolve => setTimeout(() => {
    const body = dom.window.document.body;
    resolve({ error: null, text: body.textContent, html: body.innerHTML });
  }, 1200));
}

/* ---------- mutators ---------- */
function clone(d) { return JSON.parse(JSON.stringify(d)); }

function makeStale(data, hours) {
  const d = clone(data);
  const gen = new Date(d.generated_at_utc);
  const keys = Object.keys(d.station_history || {})
    .filter(k => d.station_history[k].available);
  if (!keys.length) return d;
  const victim = keys[0];
  const st = d.station_history[victim];
  const newObs = new Date(gen.getTime() - hours * 3600 * 1000);
  st.observed_at_utc = newObs.toISOString();
  const keep = Math.max(1, 73 - hours);
  st.actual_hours_covered = keep - 1;
  st.hourly = (st.hourly || []).filter(x => x.hours_ago < keep);
  d.__staleStation = victim;
  d.__staleHours = hours;
  return d;
}

function makeUnavailable(data) {
  const d = clone(data);
  const keys = Object.keys(d.station_history || {})
    .filter(k => d.station_history[k].available);
  if (keys.length) {
    d.station_history[keys[0]] = { available: false };
    d.__downStation = keys[0];
  }
  return d;
}

function nullDistances(data) {
  const d = clone(data);
  Object.values(d.piers || {}).forEach(p => {
    const h = p.headline || {};
    h.water_temp_distance_mi = null;
    h.wind_distance_mi = null;
  });
  return d;
}

function nullWater(data) {
  const d = clone(data);
  Object.values(d.piers || {}).forEach(p => {
    const h = p.headline || {};
    h.water_temp_f = null;
    h.water_temp_source = 'UNKNOWN';
    h.water_change_72h_f = null;
  });
  return d;
}

/* ---------- staleness disclosure detector ---------- */
function disclosesAge(text) {
  return /(\d+\s*(hours?|hrs?)\s*(ago|old|behind))|last reading|reading is|not reporting|stale|delayed|no recent/i.test(text);
}

/* ---------- run ---------- */
(async () => {
  const realPath = path.join(__dirname, 'real-data.json');
  if (!fs.existsSync(realPath)) {
    console.error('\nMissing real-data.json next to this script. Fetch it first:');
    console.error('  curl -s "https://raw.githubusercontent.com/pbkfishstks/Live-buoy-and-weather-data-for-PierBite.com/main/data.json?nocache=$(date +%s)" -o real-data.json');
    process.exit(1);
  }
  const real = JSON.parse(fs.readFileSync(realPath, 'utf8'));

  const r1 = await renderWith(real);
  record('Render: real live data', !r1.error && r1.text.trim().length > 0,
    r1.error || `${r1.text.trim().length} chars rendered`);

  for (const hrs of [8, 30]) {
    const d = makeStale(real, hrs);
    const r = await renderWith(d);
    if (r.error) {
      record(`Render: station ${hrs}h stale`, false, r.error);
      continue;
    }
    const claimsNow = /\bNOW\b/.test(r.html);
    const discloses = disclosesAge(r.text);
    if (discloses) {
      record(`Staleness disclosed at ${hrs}h`, true, 'page states the reading age');
    } else if (claimsNow) {
      record(`Staleness disclosed at ${hrs}h`, false,
        `station "${d.__staleStation}" is ${hrs}h behind, page still labels data "NOW" with no age shown`);
    } else {
      record(`Staleness disclosed at ${hrs}h`, false,
        `station "${d.__staleStation}" is ${hrs}h behind, page shows no age anywhere`);
    }
  }

  // NEW: healthy data must NOT trigger a staleness warning (false-alarm guard).
  // Added 2026-08-01 after a 2h threshold was found to fire on all six piers
  // on a normal day. Healthy stations run ~1.1h behind and data.json rebuilds
  // hourly, so worst-case normal lag is ~2.3h.
  const rHealthy = await renderWith(real);
  const falseAlarms = (rHealthy.text.match(/Latest reading \d+ hours? ago/g) || []).length;
  const trulyStale = Object.values(real.station_history || {})
    .filter(s => s.available && s.observed_at_utc &&
      (Date.now() - new Date(s.observed_at_utc).getTime()) / 3600000 >= 3).length;
  record('No false staleness alarms on healthy data',
    trulyStale > 0 ? true : falseAlarms === 0,
    trulyStale > 0
      ? `${trulyStale} station(s) genuinely stale today, warnings expected`
      : (falseAlarms === 0 ? 'clean' : `${falseAlarms} warning(s) fired on healthy stations`));

  const rDown = await renderWith(makeUnavailable(real));
  record('Render: station unavailable', !rDown.error && !/undefined|NaN|null/i.test(rDown.text),
    rDown.error || (/undefined|NaN|null/i.test(rDown.text) ? 'leaked undefined/NaN/null to the page' : 'clean'));

  const rDist = await renderWith(nullDistances(real));
  record('Render: all distances null', !rDist.error && !/null\s*mi|undefined\s*mi|NaN/i.test(rDist.text),
    rDist.error || (/null\s*mi|undefined\s*mi|NaN/i.test(rDist.text) ? 'printed a null/NaN distance' : 'clean'));

  const rWater = await renderWith(nullWater(real));
  record('Render: water temp null', !rWater.error && !/null.?F|undefined.?F|NaN/i.test(rWater.text),
    rWater.error || (/null.?F|undefined.?F|NaN/i.test(rWater.text) ? 'printed a null/NaN temperature' : 'clean'));

  const failed = results.filter(r => r.pass !== true);
  console.log('\n' + '='.repeat(60));
  console.log(`${results.length - failed.length}/${results.length} checks passed on ${path.basename(TARGET)}`);
  if (failed.length) {
    console.log('\nFAILED:');
    failed.forEach(f => console.log(`  - ${f.name}: ${f.detail}`));
  }
  process.exit(failed.length ? 1 : 0);
})();
