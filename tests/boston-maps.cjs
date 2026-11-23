// Checks the engine's map fixtures against the game's own geometry code (docs/contract.md §2).
// Built-in modules only: `node tests/boston-maps.cjs`.
//
// 1. data/catalogs/canonical.v1.json matches game/planner.js (landmarks, fixed districts,
//    level bounds) and the SHA-256 of game/highway-data.js.
// 2. Every road of boston-template r1 and boston-variant r1 passes CityPlan.roadError, every
//    site's driveway is accepted by CityPlan.access on the road the map declares, and every
//    commute and responder route exists in the game's road graph.
// 3. Removing the Cambridge St shortcut (the variant) lengthens commuter and responder routes.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = process.env.BOROUGH_REPO || path.resolve(__dirname, '..');
const read = file => JSON.parse(fs.readFileSync(path.join(root, file), 'utf8'));
const catalog = read('data/catalogs/canonical.v1.json');
const maps = {
  template: read('data/maps/boston-template/r1.json'),
  variant: read('data/maps/boston-variant/r1.json'),
};

function loadGame() {
  const context = { console };
  context.window = context;
  vm.createContext(context);
  for (const name of ['geography', 'highway-data', 'planner']) {
    const file = path.join(root, 'game', name + '.js');
    vm.runInContext(fs.readFileSync(file, 'utf8'), context, { filename: name + '.js' });
  }
  return context;
}

const near = (a, b, tolerance, message) =>
  assert.ok(Math.abs(a - b) <= tolerance, `${message}: ${a} vs ${b}`);
const dist = (a, b) => Math.hypot(a.x - b.x, a.z - b.z);
function segmentDistance(p, a, b) {
  const dx = b.x - a.x, dz = b.z - a.z;
  const t = Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.z - a.z) * dz) / (dx * dx + dz * dz || 1)));
  return Math.hypot(p.x - (a.x + dx * t), p.z - (a.z + dz * t));
}

// 1. Canonical catalog against the game.
{
  const game = loadGame();
  const plan = game.CityPlan;
  const slug = name => 'lm-' + name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
  assert.equal(catalog.landmarks.length, plan.landmarks.length, 'canonical landmark count');
  for (const landmark of plan.landmarks) {
    const entry = catalog.landmarks.find(item => item.id === slug(landmark.name));
    assert.ok(entry, 'catalog lacks ' + landmark.name);
    assert.equal(entry.site, landmark.site, landmark.name + ' site');
    assert.equal(entry.radius, landmark.radius, landmark.name + ' radius');
    near(entry.x, landmark.x, 0.01, landmark.name + ' x');
    near(entry.z, landmark.z, 0.01, landmark.name + ' z');
  }
  for (let level = 1; level <= 4; level++) {
    plan.seedArcade(level);
    const bounds = plan.activeBounds;
    const entry = catalog.levels.find(item => item.level === level);
    assert.deepEqual([entry.min_x, entry.max_x, entry.min_z, entry.max_z],
      [bounds.minX, bounds.maxX, bounds.minZ, bounds.maxZ], 'level ' + level + ' bounds');
    const gameAreas = Array.from(plan.plan.buildings.filter(b => b.area), b => b.id).sort();
    const catalogAreas = catalog.areas.filter(a => a.level <= level).map(a => a.id).sort();
    assert.deepEqual(catalogAreas, gameAreas, 'level ' + level + ' fixed districts');
    for (const area of plan.plan.buildings.filter(b => b.area)) {
      const entry = catalog.areas.find(item => item.id === area.id);
      near(entry.x, area.x, 0.01, area.id + ' x');
      near(entry.z, area.z, 0.01, area.id + ' z');
      assert.equal(entry.rotation, area.rotation, area.id + ' rotation');
      assert.equal(entry.radius, area.radius, area.id + ' radius');
    }
  }
  const sha = crypto.createHash('sha256')
    .update(fs.readFileSync(path.join(root, 'game', 'highway-data.js'))).digest('hex');
  assert.equal(catalog.fixed.find(item => item.id === 'i93').sha256, sha, 'I-93 geometry hash');
}

// 2. Each map in the game.
function routeLength(points) {
  let total = 0;
  for (let i = 1; i < points.length; i++) total += dist(points[i - 1], points[i]);
  return total;
}

function check(name, doc) {
  const game = loadGame();
  const plan = game.CityPlan;
  const content = doc.content;
  plan.seedArcade(content.level);
  const nodes = Object.fromEntries(content.nodes.map(n => [n.id, { x: n.x, z: n.z }]));
  const roads = Object.fromEntries(content.roads.map(r => [r.id, r]));
  for (const road of content.roads) {
    const a = nodes[road.a], b = nodes[road.b];
    const error = plan.roadError(a, b, road.type, road.bridge, road.tunnel);
    assert.equal(error, '', `${name}: game rejects ${road.id}: ${error}`);
    plan.plan.roads.push({ id: road.id, a: { ...a }, b: { ...b }, type: road.type, bridge: road.bridge, tunnel: road.tunnel });
    plan.changed();
  }
  plan.subdividePlayerRoads();
  plan.changed();
  for (const building of content.buildings.filter(b => !b.area)) {
    const error = plan.buildingError(building);
    assert.equal(error, '', `${name}: game rejects ${building.id}: ${error}`);
    plan.plan.buildings.push({ ...building });
  }
  plan.changed();
  const declared = (site, road) => {
    const segment = roads[road];
    return segmentDistance(site, nodes[segment.a], nodes[segment.b]) < 0.05;
  };
  const sites = {};
  for (const building of content.buildings) {
    const game_building = plan.plan.buildings.find(b => b.id === building.id);
    assert.ok(game_building, `${name}: ${building.id} missing in the game`);
    const access = plan.access(game_building);
    assert.ok(access, `${name}: no game access for ${building.id}`);
    assert.ok(declared(access.p, building.access.road), `${name}: ${building.id} joins another road`);
    sites[building.id] = game_building;
  }
  for (const facility of content.facilities) {
    const landmark = facility.landmark && plan.landmarks.find(l => dist(l, facility) < 0.01);
    const site = landmark || { x: facility.x, z: facility.z, rotation: facility.rotation, radius: facility.radius, type: 'office' };
    const access = plan.access(site);
    assert.ok(access, `${name}: no game access for ${facility.id}`);
    assert.ok(declared(access.p, facility.access.road), `${name}: ${facility.id} joins another road`);
    sites[facility.id] = landmark || { x: facility.x, z: facility.z };
  }
  const lengths = {};
  const route = (from, to) => {
    const points = plan.route(sites[from], sites[to]);
    assert.ok(points, `${name}: no game route ${from} -> ${to}`);
    return routeLength(points);
  };
  for (const home of content.buildings.filter(b => b.type === 'residential')) {
    for (const office of content.buildings.filter(b => b.type === 'office')) {
      lengths[`${home.id}->${office.id}`] = route(home.id, office.id);
      lengths[`${office.id}->${home.id}`] = route(office.id, home.id);
    }
  }
  for (const facility of content.facilities) {
    for (const building of content.buildings) {
      lengths[`${facility.id}->${building.id}`] = route(facility.id, building.id);
    }
  }
  const user = content.landmarks.filter(l => l.kind === 'user');
  for (const landmark of user) {
    assert.equal(plan.buildingError({ x: landmark.x, z: landmark.z, type: 'residential' }), '',
      `${name}: ${landmark.id} must sit on free dry land`);
  }
  return lengths;
}

const template = check('boston-template', maps.template);
const variant = check('boston-variant', maps.variant);

// 3. The variant removes the shortcut, so commuter and responder routes get longer.
assert.equal(maps.variant.parent.id, 'boston-template');
assert.equal(maps.variant.parent.sha256, maps.template.sha256);
assert.ok(maps.template.content.roads.some(r => r.id === 'rd-cambridge-mid'));
assert.ok(!maps.variant.content.roads.some(r => r.id === 'rd-cambridge-mid'));
const longer = key => assert.ok(variant[key] > template[key] + 50,
  `${key} should be longer without the shortcut: ${template[key].toFixed(1)} -> ${variant[key].toFixed(1)}`);
for (const key of ['beacon->government', 'government->beacon', 'fac-fd-e4->government',
  'fac-pd-a1->beacon', 'fac-mgh-ems->government']) longer(key);
const rows = Object.keys(template).sort().map(key =>
  `${key.padEnd(30)} ${template[key].toFixed(1).padStart(8)} m -> ${variant[key].toFixed(1).padStart(8)} m`);
console.log('boston maps: catalog matches the game; both maps pass the game validators');
console.log(rows.join('\n'));
