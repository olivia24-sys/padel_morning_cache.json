// gh-fetch.js — Padel occupancy scraper for GitHub Actions
// Fetches Playtomic availability for all 6 venues across the next 7 days.
// Also fetches court info per venue so the dashboard can filter doubles-only
// without relying on browser localStorage.
// Writes results to data/padel_morning_cache.json (multi-date format).
// Run from the root of the padel_morning_cache.json repo.

const fs   = require('fs');
const path = require('path');

process.env.TZ = 'Europe/London';

const PT_VENUES = [
  { id: 'corsham',     name: 'Padel People — Corsham',        tenantId: '2d7685dc-cbb2-40ae-8fb9-13d4e73b2e00' },
  { id: 'boston',      name: 'Padel People — Boston',         tenantId: 'ae1d9547-c095-4932-8a0a-2c097946cae9' },
  { id: 'basingstoke', name: 'Padel People — Basingstoke',    tenantId: 'ec4aa02a-15a6-4dad-b49b-dd75178f2eec' },
  { id: 'shepton',     name: 'Padel People — Shepton Mallet', tenantId: '18d99acc-7bad-46c8-a52f-2ac911db3854' },
  { id: 'atc',         name: 'ATC Padel — Andover',           tenantId: '4feb9af7-79ce-4a44-b34e-f1b20336abac' },
  { id: 'worldham',    name: 'Worldham Padel — Alton',        tenantId: 'e6ec5602-4b8e-4758-99b6-b16b119ae894' },
];

// Fetch today + next 7 days — enough to capture advance booking signal
function getDateRange() {
  const today = new Date();
  return Array.from({ length: 8 }, (_, i) => {
    const d = new Date(today);
    d.setDate(today.getDate() + i);
    return d.toISOString().slice(0, 10);
  });
}

async function fetchVenueDate(tenantId, date) {
  const url = `https://api.playtomic.io/v1/availability?tenant_id=${tenantId}&sport_id=PADEL&start_min=${date}T00:00:00&start_max=${date}T23:59:59`;
  const r = await fetch(url, {
    signal: AbortSignal.timeout(15000),
    headers: { 'User-Agent': 'Mozilla/5.0 (compatible; padel-evidence-gatherer/1.0)' },
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json(); // returns raw Playtomic array: [{ resource_id, slots:[...] }]
}

// Fetches which courts are doubles vs singles for a venue.
// Returns an object matching the ptCourtCache format the dashboard expects.
async function fetchCourtInfo(tenantId) {
  const url = `https://api.playtomic.io/v1/tenants/${tenantId}/resources?sport_id=PADEL`;
  const r = await fetch(url, {
    signal: AbortSignal.timeout(15000),
    headers: { 'User-Agent': 'Mozilla/5.0 (compatible; padel-evidence-gatherer/1.0)' },
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const raw  = await r.json();
  const all  = raw.map(c => ({ id: c.resource_id, name: c.name, size: c.properties?.resource_size }));
  return {
    fetchedAt: new Date().toISOString(),
    all,
    doubleIds: all.filter(c => c.size !== 'single').map(c => c.id),
  };
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  const dates     = getDateRange();
  const fetchedAt = new Date().toISOString();

  console.log(`\n[${fetchedAt}] Fetching ${PT_VENUES.length} venues × ${dates.length} dates`);
  console.log(`Date range: ${dates[0]} → ${dates[dates.length - 1]}\n`);

  // ---- Court discovery (doubles vs singles) ----------------------------------
  console.log('Discovering courts…');
  const courtCache = {};
  for (const venue of PT_VENUES) {
    try {
      const info = await fetchCourtInfo(venue.tenantId);
      courtCache[venue.id] = info;
      const singles = info.all.length - info.doubleIds.length;
      console.log(`  ${venue.name}: ${info.doubleIds.length} doubles${singles ? `, ${singles} single(s) excluded` : ''}`);
    } catch (e) {
      console.error(`  ✗ Court fetch failed for ${venue.name}: ${e.message}`);
    }
    await sleep(300);
  }

  // ---- Availability data -----------------------------------------------------
  const venues = [];

  for (const venue of PT_VENUES) {
    const availability = {};
    let ok = 0, fail = 0;

    for (const date of dates) {
      try {
        availability[date] = await fetchVenueDate(venue.tenantId, date);
        ok++;
        process.stdout.write('.');
      } catch (e) {
        console.error(`\n  ✗ ${venue.name} ${date}: ${e.message}`);
        availability[date] = [];
        fail++;
      }
      await sleep(400); // be polite to the Playtomic API
    }

    venues.push({
      name:         venue.name, // dashboard resolveId() matches by substring (e.g. "corsham")
      id:           venue.id,
      fetch_status: fail === dates.length ? 'error' : 'ok',
      availability, // { "YYYY-MM-DD": [rawPlaytomicSlots], ... }
    });

    console.log(`\n  ✓ ${venue.name}: ${ok} ok, ${fail} failed`);
  }

  const output = {
    fetched_at:   fetchedAt,
    fetch_window: { from: dates[0], to: dates[dates.length - 1] },
    label:        `${dates.length}-day scrape`,
    court_cache:  courtCache, // dashboard seeds ptCourtCache from this — ensures doubles filtering works
    venues,
  };

  // Write main cache file (this is what the dashboard reads on every ghSync())
  // gh-fetch.js lives at the repo root; data/ is alongside it.
  const outDir = path.join(__dirname, 'data');
  fs.mkdirSync(outDir, { recursive: true });
  const mainPath = path.join(outDir, 'padel_morning_cache.json');
  fs.writeFileSync(mainPath, JSON.stringify(output, null, 2));
  console.log(`\nWrote ${mainPath}`);

  // Write timestamped snapshot so the dashboard can load historical fetches
  const snapDir = path.join(outDir, 'snapshots');
  fs.mkdirSync(snapDir, { recursive: true });
  const ts       = fetchedAt.slice(0, 16).replace('T', '_').replace(':', '-');
  const snapPath = path.join(snapDir, `${ts}.json`);
  fs.writeFileSync(snapPath, JSON.stringify(output));
  console.log(`Wrote ${snapPath}`);

  console.log(`\nDone. ${venues.filter(v => v.fetch_status === 'ok').length}/${venues.length} venues successful.`);
}

main().catch(e => {
  console.error('\nFatal:', e.message);
  process.exit(1);
});
