const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = process.env.BOROUGH_REPO || path.resolve(__dirname, '..');
const context = { console };
context.window = context;
vm.createContext(context);
for (const name of ['geography', 'highway-data', 'planner']) {
  vm.runInContext(fs.readFileSync(path.join(root, 'dist', name + '.js'), 'utf8'), context, { filename: name + '.js' });
}
const { CityPlan: plan, BOSTON_HIGHWAY_DATA: data, BOSTON_GEOGRAPHY: geo } = context;
for (let level = 1; level <= 4; level++) {
  plan.seedArcade(level);
  assert.equal(plan.highwayGates().length, 4, 'both carriageways must enter and exit Level ' + level);
}
const fixed = plan.plan.roads.filter(road => road.fixed);
const near = (actual, expected, message) => assert.ok(Math.abs(actual - expected) < 1e-6, `${message}: ${actual} instead of ${expected}`);
// Import heights must drive both graph connections and rendered road ribbons.
for (const road of fixed) {
  near(plan.heightAt(road.a, road), road.a.height, road.id + ' start height');
  near(plan.heightAt(road.b, road), road.b.height, road.id + ' end height');
  for (const t of [.25, .5, .75]) {
    const p = { x: road.a.x + (road.b.x - road.a.x) * t, z: road.a.z + (road.b.z - road.a.z) * t };
    near(plan.heightAt(p, road), road.a.height + (road.b.height - road.a.height) * t, road.id + ' interpolated height');
  }
}
for (const id of new Set(fixed.map(road => road.pathId))) {
  const chain = fixed.filter(road => road.pathId === id).sort((a, b) => a.pathStart - b.pathStart);
  for (let i = 1; i < chain.length; i++) {
    near(plan.dist(chain[i - 1].b, chain[i].a), 0, id + ' horizontal join');
    near(plan.heightAt(chain[i - 1].b, chain[i - 1]), plan.heightAt(chain[i].a, chain[i]), id + ' vertical join');
  }
}
const project = ([lon, lat, height = 0]) => ({ x: (lon - geo.origin.lon) * geo.metersPerDegree.x, z: (geo.origin.lat - lat) * geo.metersPerDegree.z, height });
for (const [id, line] of [['northbound', data.mainline], ['southbound', data.southbound]]) {
  const route = plan.route(project(line[0]), project(line.at(-1)));
  assert.ok(route, id + ' must be drivable from one map edge to the other');
  assert.ok(route.some(p => p.height < -10), id + ' route must enter the tunnel');
  assert.ok(route.some(p => p.height > 10), id + ' route must traverse the raised section');
}
for (const ramp of data.ramps) {
  const connection = ramp.mainlineConnection;
  const line = connection.carriageway === 'southbound' ? data.southbound : data.mainline;
  const index = line.findIndex(p => p[0] === connection.point[0] && p[1] === connection.point[1]);
  assert.ok(index >= 0, ramp.id + ' mainline connection must exist');
  const mainlinePoint = project(line[index + (ramp.flow === 'on' ? 1 : -1)]);
  const surface = project(ramp.surfaceEndpoint);
  const route = ramp.flow === 'on' ? plan.route(surface, mainlinePoint) : plan.route(mainlinePoint, surface);
  assert.ok(route, ramp.id + ' must connect surface to the correct directed carriageway');
  const rampRoad = fixed.find(road => road.pathId === ramp.id && (plan.dist(road.a, surface) < .01 || plan.dist(road.b, surface) < .01));
  near(plan.heightAt(surface, rampRoad), 0, ramp.id + ' surface endpoint');
  // A player-built ground street must attach to the actual surface ramp.
  let spur;
  for (let i = 0; i < 16; i++) {
    const angle = i * Math.PI / 8;
    const end = { x: surface.x + Math.cos(angle) * 60, z: surface.z + Math.sin(angle) * 60 };
    if (!plan.roadPath([surface, end], 'twoway')) { spur = end; break; }
  }
  assert.ok(spur, ramp.id + ' must accept a player ground-road connection');
  const localRoute = ramp.flow === 'on' ? plan.route(spur, mainlinePoint) : plan.route(mainlinePoint, spur);
  assert.ok(localRoute, ramp.id + ' must route between player street and mainline');
}
// User bridges/tunnels still rise/fall from ground with the normal ramp profile.
for (const [mode, expected] of [['bridge', 12], ['tunnel', -12]]) {
  const road = { a: { x: 0, z: 0 }, b: { x: 120, z: 0 }, type: 'twoway', [mode]: true };
  near(plan.heightAt(road.a, road), 0, mode + ' start');
  near(plan.heightAt({ x: 60, z: 0 }, road), expected, mode + ' midpoint');
  near(plan.heightAt(road.b, road), 0, mode + ' end');
}
console.log(`Passed ${fixed.length} real I-93/ramp segments: imported elevations, continuous joins, map-edge routes, all four directed ramps with player street connections, and player bridge/tunnel profiles.`);
