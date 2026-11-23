// The route table behind the Boston trace, computed by the game's own code (docs/contract.md §4).
// Built-in modules only.
//   node tests/boston-trace.cjs          check tests/engines/fixtures/boston-routes.json
//   node tests/boston-trace.cjs --write  regenerate it
//
// For boston-template r1 and boston-variant r1, every unit's route from its station to the
// trace sites is computed with CityPlan.route on the game's road graph. Travel ticks follow the
// game's responders (incidents.js: path length / 360 m per minute, at least 2 minutes); storm
// ticks divide the speed by the Storm speed multiplier from data/catalogs/disruptions.v1.yaml.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = process.env.BOROUGH_REPO || path.resolve(__dirname, '..');
const fixture = path.join(root, 'tests', 'engines', 'fixtures', 'boston-routes.json');
const SPEED = 360; // metres per minute (one tick), as incidents.js moves responders
const SITES = { A: { x: 360, z: 560 }, B: { x: -180, z: 585 } };
const COMMUTE = [['beacon', 'government'], ['government', 'beacon']];

function stormMultiplierBp() {
  const text = fs.readFileSync(path.join(root, 'data', 'catalogs', 'disruptions.v1.yaml'), 'utf8');
  const block = text.slice(text.indexOf('- id: storm'));
  const match = block.match(/speed_multiplier_bp:\s*(\d+)/);
  assert.ok(match, 'storm speed multiplier not found');
  return Number(match[1]);
}

function loadGame() {
  const context = { console };
  context.window = context;
  vm.createContext(context);
  for (const name of ['geography', 'highway-data', 'planner']) {
    vm.runInContext(fs.readFileSync(path.join(root, 'game', name + '.js'), 'utf8'), context, { filename: name + '.js' });
  }
  return context.CityPlan;
}

const dist = (a, b) => Math.hypot(a.x - b.x, a.z - b.z);
const r1 = value => Math.round(value * 10) / 10;

function table(mapId, storm) {
  const doc = JSON.parse(fs.readFileSync(path.join(root, 'data', 'maps', mapId, 'r1.json'), 'utf8'));
  const plan = loadGame();
  plan.seedArcade(doc.content.level);
  const nodes = Object.fromEntries(doc.content.nodes.map(n => [n.id, { x: n.x, z: n.z }]));
  for (const road of doc.content.roads) {
    plan.plan.roads.push({ id: road.id, a: { ...nodes[road.a] }, b: { ...nodes[road.b] }, type: road.type, bridge: road.bridge, tunnel: road.tunnel });
  }
  plan.subdividePlayerRoads();
  plan.changed();
  const length = (from, to) => {
    const points = plan.route(from, to);
    assert.ok(points, `${mapId}: no game route`);
    let total = 0;
    for (let i = 1; i < points.length; i++) total += dist(points[i - 1], points[i]);
    return total;
  };
  const routes = {};
  for (const [site, target] of Object.entries(SITES)) {
    routes[site] = {};
    for (const facility of doc.content.facilities) {
      const origin = facility.landmark
        ? plan.landmarks.find(l => dist(l, facility) < 0.01)
        : { x: facility.x, z: facility.z };
      const metres = length(origin, target);
      for (const unit of facility.units) {
        routes[site][unit.id] = {
          length_m: r1(metres),
          ticks: Math.max(2, Math.ceil(metres / SPEED)),
          storm_ticks: Math.max(2, Math.ceil(metres * 10000 / (SPEED * storm))),
        };
      }
    }
  }
  const areas = Object.fromEntries(plan.plan.buildings.filter(b => b.area).map(b => [b.id, b]));
  const commute = {};
  for (const [from, to] of COMMUTE) commute[`${from}->${to}`] = r1(length(areas[from], areas[to]));
  return { revision: doc.revision, sha256: doc.sha256, commute_m: commute, routes };
}

const storm = stormMultiplierBp();
const document = {
  description: 'Unit-to-site routes on the game road graph for the Boston trace (tests/boston-trace.cjs). ' +
    'ticks = max(2, ceil(length / 360 m)); storm_ticks divides the speed by the Storm multiplier.',
  speed_m_per_tick: SPEED,
  storm_speed_multiplier_bp: storm,
  sites: SITES,
  maps: { 'boston-template': table('boston-template', storm), 'boston-variant': table('boston-variant', storm) },
};
const text = JSON.stringify(document, null, 2) + '\n';
if (process.argv.includes('--write')) {
  fs.mkdirSync(path.dirname(fixture), { recursive: true });
  fs.writeFileSync(fixture, text);
  console.log('wrote ' + path.relative(root, fixture));
} else {
  assert.equal(fs.readFileSync(fixture, 'utf8'), text, 'boston-routes.json is stale: run with --write');
  const t = document.maps['boston-template'], v = document.maps['boston-variant'];
  console.log('boston trace: route table matches the game graph');
  console.log(`commute beacon->government ${t.commute_m['beacon->government']} m -> ${v.commute_m['beacon->government']} m without the shortcut`);
  for (const [site, unit] of [['A', 'fd-e4-engine'], ['B', 'pd-a1-1'], ['A', 'ems-mgh-1']]) {
    console.log(`${unit} -> ${site}: ${t.routes[site][unit].ticks} ticks (storm ${t.routes[site][unit].storm_ticks}) -> variant ${v.routes[site][unit].ticks} ticks`);
  }
}
