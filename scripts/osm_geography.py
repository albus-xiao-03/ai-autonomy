"""Build game/boston-geography-osm.js (Boston land/water outline) from OpenStreetMap.

Output: window.BOSTON_GEOGRAPHY_OSM with the same schema as window.BOSTON_GEOGRAPHY in
game/geography.js (polygons = outer land rings, holes[i] = water rings inside polygons[i],
every ring closed by repeating its first point; game x = east, z = south, metres).

Pipeline (standard library + numpy only):
  1. Rasterise the map crop (the old bounds, 3290 x 2672 m centred on the origin) at ~1 m.
  2. Sea: the grid is cut along the OSM coastline; every connected piece is water when most
     coastline segments beside it have it on their right-hand side (OSM convention).
  3. Plus natural=water / waterway=riverbank areas (fountains, reflecting pools and covered
     water skipped).
  4. Plus fixed piers (man_made=pier areas). Floating docks, bridge supports, ruins, piers
     tagged narrower than 5 m and Community Boating docks are skipped, and pier parts
     narrower than ~5 m are removed with a morphological opening, so walkways and finger
     docks stay water.
  5. Marching squares -> rings; land specks and ponds under 150 m2 dropped; Douglas-Peucker
     1.5 m, redone with a smaller tolerance for any ring that would cross itself or another.

Input: Overpass JSON from this query (`out geom` keeps node ids and full way geometry):
  [out:json][timeout:180][bbox:42.3480,-71.0930,42.3840,-71.0370];
  (way["natural"="coastline"]; way["natural"="water"]; relation["natural"="water"];
   way["waterway"="riverbank"]; relation["waterway"="riverbank"];
   way["man_made"="pier"]; relation["man_made"="pier"];
   way["leisure"="marina"]; relation["leisure"="marina"];);
  out geom;
(leisure=marina is fetched for inspection only; this script does not use it.)
Usage: python3 -I scripts/osm_geography.py boston_water_osm.json game/boston-geography-osm.js
"""
import json, math, re, sys
import numpy as np

LON0, LAT0, MX, MZ = -71.065, 42.366, 82249.37752584313, 111320.0
WIDTH, HEIGHT = 3289.97510103307, 2671.6800000001012  # same bounds as game/geography.js
BOUNDS = (-1127, 1415, -1135, 1102)  # playable map (planner.js), for the report only
NX, NZ = round(WIDTH), round(HEIGHT)
DX, DZ = WIDTH / NX, HEIGHT / NZ
X0, Z0 = -WIDTH / 2, -HEIGHT / 2
MIN_AREA = 150.0      # m2: smaller islands and ponds are dropped
TOLERANCE = 1.5       # m: Douglas-Peucker
PIER_RADIUS = 2.5     # m: opening radius; thinner pier parts stay water
SKIP_WATER = {"fountain", "reflecting_pool"}


def xz(p):
    return ((p["lon"] - LON0) * MX, (LAT0 - p["lat"]) * MZ)


def merge_rings(chains):
    """Join open member ways of a multipolygon into closed rings (by shared end points)."""
    chains = [list(c) for c in chains if len(c) >= 2]
    rings, dropped = [], 0
    while chains:
        cur = chains.pop(0)
        grown = True
        while cur[0] != cur[-1] and grown:
            grown = False
            for i, w in enumerate(chains):
                if w[0] == cur[-1]: cur += w[1:]
                elif w[-1] == cur[-1]: cur += w[::-1][1:]
                elif w[-1] == cur[0]: cur = w[:-1] + cur
                elif w[0] == cur[0]: cur = w[::-1][:-1] + cur
                else: continue
                chains.pop(i); grown = True; break
        if cur[0] == cur[-1] and len(cur) >= 4: rings.append(cur)
        else: dropped += 1
    return rings, dropped


def element_rings(e):
    """Closed rings (lists of (x, z)) of a closed way or a multipolygon relation."""
    if e["type"] == "way":
        g = [(p["lon"], p["lat"]) for p in e.get("geometry") or [] if p]
        closed = e.get("nodes") and e["nodes"][0] == e["nodes"][-1]
        return ([[xz({"lon": a, "lat": b}) for a, b in g]] if closed and len(g) >= 4 else []), 0
    chains = [[(round(p["lon"], 7), round(p["lat"], 7)) for p in m.get("geometry") or [] if p]
              for m in e.get("members", []) if m.get("type") == "way"]
    rings, dropped = merge_rings(chains)
    return [[xz({"lon": a, "lat": b}) for a, b in r] for r in rings], dropped


def fill(target, rings):
    """OR the even-odd interior of `rings` (cell centres, same rule as planner.js inside())."""
    rows, cols = [], []
    for ring in rings:
        a = np.asarray(ring, float)
        x1, z1, x2, z2 = a[:-1, 0], a[:-1, 1], a[1:, 0], a[1:, 1]
        keep = z1 != z2
        x1, z1, x2, z2 = x1[keep], z1[keep], x2[keep], z2[keep]
        lo, hi = np.minimum(z1, z2), np.maximum(z1, z2)
        r0 = np.clip(np.ceil((lo - Z0) / DZ - 0.5), 0, NZ).astype(int)
        r1 = np.clip(np.ceil((hi - Z0) / DZ - 0.5), 0, NZ).astype(int)
        n = r1 - r0
        if n.sum() == 0: continue
        edge = np.repeat(np.arange(len(n)), n)
        r = r0[edge] + np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
        zc = Z0 + (r + 0.5) * DZ
        xc = x1[edge] + (zc - z1[edge]) * (x2[edge] - x1[edge]) / (z2[edge] - z1[edge])
        rows.append(r); cols.append(np.clip(np.ceil((xc - X0) / DX - 0.5), 0, NX).astype(int))
    if not rows: return
    rows, cols = np.concatenate(rows), np.concatenate(cols)
    ra, rb, ca, cb = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
    toggles = np.zeros((rb - ra, cb - ca + 1), np.int32)
    np.add.at(toggles, (rows - ra, cols - ca), 1)
    inside = (np.cumsum(toggles, axis=1)[:, :-1] & 1).astype(bool)
    cb = min(cb, NX)
    target[ra:rb, ca:cb] |= inside[:, :cb - ca]


def runs_of(mask):
    """Horizontal runs of True cells: row, start, end (exclusive), row-major order."""
    pad = np.zeros((mask.shape[0], mask.shape[1] + 2), np.int8)
    pad[:, 1:-1] = mask
    d = np.diff(pad, axis=1)
    sr, sc = np.nonzero(d == 1)
    er, ec = np.nonzero(d == -1)
    assert (sr == er).all()
    return sr, sc, ec


def label_runs(row, s, e, width):
    """4-connected components of runs (union-find); returns a component id per run."""
    K = width + 2
    skey, ekey = row * K + s, row * K + e
    has_above = row > 0
    q = np.nonzero(has_above)[0]
    first = np.searchsorted(ekey, (row[q] - 1) * K + s[q], side="right")
    last = np.searchsorted(skey, (row[q] - 1) * K + e[q], side="left") - 1
    ok = (first <= last) & (first < len(row))
    ok[ok] &= row[first[ok]] == row[q[ok]] - 1
    q, first, last = q[ok], first[ok], last[ok]
    cnt = last - first + 1
    a = np.repeat(q, cnt)
    b = np.repeat(first, cnt) + np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt)
    parent = list(range(len(row)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for i, j in zip(a.tolist(), b.tolist()):
        ri, rj = find(i), find(j)
        if ri != rj: parent[max(ri, rj)] = min(ri, rj)
    comp = np.array([find(i) for i in range(len(row))])
    return np.unique(comp, return_inverse=True)[1], skey, ekey


def sea_mask(coast_ways):
    """Water side of the coastline, by flood regions and right-hand-side votes."""
    best = np.full((NZ, NX), np.inf, np.float32)
    wet = np.zeros((NZ, NX), bool)
    segs = []
    for pts in coast_ways:
        a = np.asarray(pts, float)
        segs.append(np.column_stack([a[:-1], a[1:]]))
    segs = np.concatenate(segs)
    segs = segs[np.hypot(segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1]) > 1e-6]
    thr = 0.75 * max(DX, DZ)
    for ax, az, bx, bz in segs:
        c0 = max(int(math.floor((min(ax, bx) - thr - X0) / DX - 0.5)), 0)
        c1 = min(int(math.ceil((max(ax, bx) + thr - X0) / DX - 0.5)) + 1, NX)
        r0 = max(int(math.floor((min(az, bz) - thr - Z0) / DZ - 0.5)), 0)
        r1 = min(int(math.ceil((max(az, bz) + thr - Z0) / DZ - 0.5)) + 1, NZ)
        if c0 >= c1 or r0 >= r1: continue
        px = (X0 + (np.arange(c0, c1) + 0.5) * DX)[None, :]
        pz = (Z0 + (np.arange(r0, r1) + 0.5) * DZ)[:, None]
        dx, dz = bx - ax, bz - az
        t = np.clip(((px - ax) * dx + (pz - az) * dz) / (dx * dx + dz * dz), 0, 1)
        d = np.hypot(px - ax - t * dx, pz - az - t * dz)
        win = best[r0:r1, c0:c1]
        upd = (d <= thr) & (d < win)
        win[upd] = d[upd]
        # OSM coastline: land on the left, water on the right (x east, z south).
        wet[r0:r1, c0:c1][upd] = (dx * (pz - az) - dz * (px - ax))[upd] > 0
    barrier = np.isfinite(best)
    row, s, e = runs_of(~barrier)
    comp, skey, ekey = label_runs(row, s, e, NX)
    ncomp = comp.max() + 1
    votes = np.zeros((2, ncomp))
    L = np.hypot(segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1])
    n = np.maximum(1, (L / 1.0).astype(int))
    k = np.repeat(np.arange(len(segs)), n)
    t = (np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n) + 0.5) / n[k]
    sx, sz = segs[k, 0] + t * (segs[k, 2] - segs[k, 0]), segs[k, 1] + t * (segs[k, 3] - segs[k, 1])
    nxr, nzr = -(segs[k, 3] - segs[k, 1]) / L[k], (segs[k, 2] - segs[k, 0]) / L[k]
    K = NX + 2
    for side, sign in ((0, 1), (1, -1)):  # 0 = right (water), 1 = left (land)
        px, pz = sx + sign * 2.5 * nxr, sz + sign * 2.5 * nzr
        c = np.floor((px - X0) / DX).astype(int); r = np.floor((pz - Z0) / DZ).astype(int)
        ok = (c >= 0) & (c < NX) & (r >= 0) & (r < NZ)
        key = r[ok] * K + c[ok]
        idx = np.searchsorted(skey, key, side="right") - 1
        hit = (idx >= 0) & (ekey[np.maximum(idx, 0)] > key)
        np.add.at(votes[side], comp[idx[hit]], 1)
    water_comp = votes[0] > votes[1]
    cell_count = np.bincount(comp, weights=(e - s), minlength=ncomp)
    unvoted = (votes.sum(0) == 0)
    print(f"sea: {len(segs)} coastline segments, {ncomp} regions, {water_comp.sum()} water; "
          f"{unvoted.sum()} regions without votes ({cell_count[unvoted].sum() * DX * DZ:.0f} m2, kept as land); "
          f"contested regions: {int(((votes[0] > 0) & (votes[1] > 0)).sum())}")
    sel = water_comp[comp]
    D = np.zeros((NZ, NX + 1), np.int8)
    np.add.at(D, (row[sel], s[sel]), 1)
    np.add.at(D, (row[sel], e[sel]), -1)
    sea = np.cumsum(D, axis=1)[:, :NX] > 0
    return sea | (barrier & wet)


def disk_offsets(radius):
    R = int(math.floor(radius))
    return [(i, j) for i in range(-R, R + 1) for j in range(-R, R + 1) if i * i + j * j <= radius * radius]


def shifted(mask, i, j, fill_value):
    out = np.full_like(mask, fill_value)
    H, W = mask.shape
    out[max(i, 0):H + min(i, 0), max(j, 0):W + min(j, 0)] = mask[max(-i, 0):H + min(-i, 0), max(-j, 0):W + min(-j, 0)]
    return out


def opening(mask, radius):
    offs = disk_offsets(radius)
    er = mask.copy()
    for i, j in offs: er &= shifted(mask, i, j, False)
    out = er.copy()
    for i, j in offs: out |= shifted(er, i, j, False)
    return out


# Marching squares. Table pairs are (from, to) with land on the left in screen terms (x right,
# z down); contours() walks them backwards so outer rings get a positive x/z shoelace area like
# game/geography.js and holes a negative one.
# Corner code = TL*8 + TR*4 + BR*2 + BL; saddles join land diagonally.
CASES = {1: [("S", "W")], 2: [("E", "S")], 3: [("E", "W")], 4: [("N", "E")], 5: [("N", "W"), ("S", "E")],
         6: [("N", "S")], 7: [("N", "W")], 8: [("W", "N")], 9: [("S", "N")], 10: [("E", "N"), ("W", "S")],
         11: [("E", "N")], 12: [("W", "E")], 13: [("S", "E")], 14: [("W", "S")]}


def contours(land):
    B = np.zeros((NZ + 2, NX + 2), np.uint8)
    B[1:-1, 1:-1] = land
    W = NX + 2
    code = B[:-1, :-1] * 8 + B[:-1, 1:] * 4 + B[1:, 1:] * 2 + B[1:, :-1]
    def key(edge, r, c):
        if edge == "N": return 2 * (r * W + c)
        if edge == "S": return 2 * ((r + 1) * W + c)
        if edge == "W": return 2 * (r * W + c) + 1
        return 2 * (r * W + c + 1) + 1
    src, dst = [], []
    for k, segs in CASES.items():
        r, c = np.nonzero(code == k)
        for a, b in segs:
            src.append(key(b, r, c)); dst.append(key(a, r, c))
    src, dst = np.concatenate(src), np.concatenate(dst)
    nxt = dict(zip(src.tolist(), dst.tolist()))
    assert len(nxt) == len(src), "marching squares produced a branching contour"
    rings, seen = [], set()
    for start in src.tolist():
        if start in seen: continue
        ring, k = [], start
        while k not in seen:
            seen.add(k); ring.append(k); k = nxt[k]
        assert k == start
        ks = np.array(ring)
        cell, horiz = ks // 2, ks % 2 == 0
        r, c = cell // W, cell % W
        ci = np.where(horiz, c + 0.5, c); ri = np.where(horiz, r, r + 0.5)
        rings.append(np.column_stack([X0 + (ci - 0.5) * DX, Z0 + (ri - 0.5) * DZ]))
    return rings


def area(r):
    x, z = r[:, 0], r[:, 1]
    return 0.5 * float((x * np.roll(z, -1) - np.roll(x, -1) * z).sum())


def contains(ring, x, z):
    a, b = ring, np.roll(ring, -1, axis=0)
    cross = (a[:, 1] > z) != (b[:, 1] > z)
    with np.errstate(divide="ignore", invalid="ignore"):
        xs = (b[:, 0] - a[:, 0]) * (z - a[:, 1]) / (b[:, 1] - a[:, 1]) + a[:, 0]
    return bool(np.count_nonzero(cross & (x < xs)) & 1)


def dp_ring(ring, tol):
    """Douglas-Peucker on a closed ring (vertex 0 and the vertex farthest from it are kept)."""
    if tol <= 0 or len(ring) < 8: return ring
    far = int(np.argmax(np.hypot(*(ring - ring[0]).T)))
    pts = np.vstack([ring, ring[:1]])
    keep = np.zeros(len(pts), bool); keep[[0, far, len(pts) - 1]] = True
    stack = [(0, far), (far, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j - i < 2: continue
        a, b, p = pts[i], pts[j], pts[i + 1:j]
        d = b - a; L2 = float(d @ d)
        t = np.clip(((p - a) @ d) / L2, 0, 1) if L2 > 0 else np.zeros(len(p))
        dist = np.hypot(*(p - a - t[:, None] * d).T)
        m = int(np.argmax(dist))
        if dist[m] > tol:
            keep[i + 1 + m] = True; stack += [(i, i + 1 + m), (i + 1 + m, j)]
    out = pts[keep][:-1]
    return out if len(out) >= 3 else ring


def crossings(rings, cell=8.0):
    """Indices of rings with a segment touching/crossing another non-adjacent segment."""
    A, B, R, I, N = [], [], [], [], []
    for k, r in enumerate(rings):
        A.append(r); B.append(np.roll(r, -1, axis=0)); R.append(np.full(len(r), k)); I.append(np.arange(len(r))); N.append(np.full(len(r), len(r)))
    A, B, R, I, N = map(np.concatenate, (A, B, R, I, N))
    lo, hi = np.floor(np.minimum(A, B) / cell).astype(int), np.floor(np.maximum(A, B) / cell).astype(int)
    seg_ids, keys = [], []
    for ox in range(int((hi[:, 0] - lo[:, 0]).max()) + 1):
        for oz in range(int((hi[:, 1] - lo[:, 1]).max()) + 1):
            m = (lo[:, 0] + ox <= hi[:, 0]) & (lo[:, 1] + oz <= hi[:, 1])
            seg_ids.append(np.nonzero(m)[0]); keys.append((lo[m, 0] + ox) * 100003 + (lo[m, 1] + oz))
    seg_ids, keys = np.concatenate(seg_ids), np.concatenate(keys)
    order = np.argsort(keys, kind="stable"); seg_ids, keys = seg_ids[order], keys[order]
    bounds = np.flatnonzero(np.diff(keys)) + 1
    pa, pb = [], []
    for grp in np.split(seg_ids, bounds):
        if len(grp) < 2: continue
        i, j = np.triu_indices(len(grp), 1)
        pa.append(grp[i]); pb.append(grp[j])
    if not pa: return set()
    pa, pb = np.concatenate(pa), np.concatenate(pb)
    same = R[pa] == R[pb]
    adj = same & (((I[pa] - I[pb]) % N[pa] == 1) | ((I[pb] - I[pa]) % N[pa] == 1))
    pa, pb = pa[~adj], pb[~adj]
    def orient(p, q, r):
        return (q[:, 0] - p[:, 0]) * (r[:, 1] - p[:, 1]) - (q[:, 1] - p[:, 1]) * (r[:, 0] - p[:, 0])
    p1, p2, p3, p4 = A[pa], B[pa], A[pb], B[pb]
    d1, d2, d3, d4 = orient(p1, p2, p3), orient(p1, p2, p4), orient(p3, p4, p1), orient(p3, p4, p2)
    hit = (d1 * d2 <= 0) & (d3 * d4 <= 0)
    col = (d1 == 0) & (d2 == 0) & (d3 == 0) & (d4 == 0)
    if col.any():  # collinear: only overlapping intervals count
        lo1, hi1 = np.minimum(p1, p2), np.maximum(p1, p2); lo2, hi2 = np.minimum(p3, p4), np.maximum(p3, p4)
        overlap = (lo1 <= hi2).all(1) & (lo2 <= hi1).all(1)
        hit &= ~col | overlap
    return set(R[pa[hit]].tolist()) | set(R[pb[hit]].tolist())


def main(src, out):
    data = json.load(open(src))
    els = data["elements"]
    coast, water_rings, piers, skipped = [], [], [], {}
    for e in els:
        t = e.get("tags") or {}
        if t.get("natural") == "coastline" and e["type"] == "way":
            coast.append([xz(p) for p in e.get("geometry") or [] if p])
        elif t.get("natural") == "water" or t.get("waterway") == "riverbank":
            if t.get("water") in SKIP_WATER or t.get("covered") == "yes" or t.get("tunnel") == "culvert" or t.get("location") == "underground":
                continue
            rings, dropped = element_rings(e)
            if dropped: print(f"warning: {e['type']} {e['id']} has {dropped} unclosed ring(s)")
            if rings: water_rings.append(rings)
        elif t.get("man_made") == "pier":
            width = re.match(r"[\d.]+", t.get("width", "") or "")
            reason = ("floating" if t.get("floating") == "yes" else
                      "bridge support" if t.get("bridge:support") in ("yes", "pier") else
                      "ruin" if "yes" in (t.get("ruined"), t.get("abandoned"), t.get("ruins")) else
                      "Community Boating" if "community boating" in (t.get("operator", "") + t.get("name", "")).lower() else
                      "narrow" if width and float(width.group()) < 5 else None)
            rings, _ = element_rings(e)
            if not rings: continue  # pier lines (walkways) are not land
            if reason: skipped[reason] = skipped.get(reason, 0) + 1; continue
            piers.append(rings)
    print(f"input: {len(coast)} coastline ways, {len(water_rings)} water areas, {len(piers)} pier areas used, skipped piers: {skipped}")
    water = sea_mask(coast)
    for rings in water_rings: fill(water, rings)
    land = ~water
    pier = np.zeros_like(land)
    for rings in piers: fill(pier, rings)
    added = opening(land | pier, PIER_RADIUS / min(DX, DZ)) & pier & ~land
    print(f"piers: {(pier & ~land).sum() * DX * DZ:.0f} m2 over water, {added.sum() * DX * DZ:.0f} m2 kept after {PIER_RADIUS} m opening")
    land |= added
    rings = contours(land)
    areas = np.array([area(r) for r in rings])
    assert areas[np.argmax(np.abs(areas))] > 0, "orientation check failed"
    outers = [(a, r) for a, r in zip(areas, rings) if a >= MIN_AREA]
    holes = [(a, r) for a, r in zip(areas, rings) if a <= -MIN_AREA]
    print(f"rings: {len(rings)} traced, {len(outers)} land and {len(holes)} water rings >= {MIN_AREA:.0f} m2")
    outers.sort(key=lambda o: -o[0])
    obox = np.array([[r[:, 0].min(), r[:, 0].max(), r[:, 1].min(), r[:, 1].max()] for _, r in outers])
    parent = []
    for a, h in holes:
        x, z = h[0]
        best = None
        for k in np.nonzero((obox[:, 0] <= x) & (obox[:, 1] >= x) & (obox[:, 2] <= z) & (obox[:, 3] >= z))[0][::-1]:
            if contains(outers[k][1], x, z): best = k; break  # smallest container (sorted by area)
        parent.append(best)
    assert None not in parent, "hole without a containing land ring"
    base = [r for _, r in outers] + [h for _, h in holes]
    owner = list(range(len(outers))) + parent
    tol = [TOLERANCE] * len(base)
    simple = [np.round(dp_ring(r, TOLERANCE), 2) for r in base]
    for attempt in range(8):
        bad = crossings(simple)
        for i in range(len(outers), len(base)):  # holes must stay inside their land ring
            if not contains(simple[owner[i]], *simple[i][0]): bad |= {i, owner[i]}
        for i in range(len(base)):
            if area(simple[i]) * area(base[i]) <= 0: bad.add(i)
        if not bad: break
        for i in bad:
            tol[i] = tol[i] / 2 if tol[i] > 0.2 else 0
            simple[i] = np.round(dp_ring(base[i], tol[i]), 2)
        print(f"validity pass {attempt + 1}: {len(bad)} ring(s) re-simplified")
    else:
        raise SystemExit("could not make rings valid")
    close = lambda r: [[float(x), float(z)] for x, z in r] + [[float(r[0][0]), float(r[0][1])]]
    polygons = [close(simple[k]) for k in range(len(outers))]
    hole_groups = [[] for _ in outers]
    for i in range(len(outers), len(base)): hole_groups[owner[i]].append(close(simple[i]))
    geo = {"scale": 1, "bounds": {"width": WIDTH, "height": HEIGHT}, "polygons": polygons, "holes": hole_groups,
           "origin": {"lon": LON0, "lat": LAT0}, "metersPerDegree": {"x": MX, "z": MZ}}
    stamp = data.get("osm3s", {}).get("timestamp_osm_base", "unknown")
    with open(out, "w") as f:
        f.write("// Boston land/water outline generated from OpenStreetMap (coastline, water areas, fixed piers),\n"
                f"// data as of {stamp}. © OpenStreetMap contributors, ODbL (openstreetmap.org/copyright).\n"
                "// Regenerate with scripts/osm_geography.py; do not edit by hand. Same schema as BOSTON_GEOGRAPHY.\n")
        f.write("window.BOSTON_GEOGRAPHY_OSM=" + json.dumps(geo, separators=(",", ":")) + ";\n")
    cols = (X0 + (np.arange(NX) + 0.5) * DX); rws = (Z0 + (np.arange(NZ) + 0.5) * DZ)
    inb = ((rws >= BOUNDS[2]) & (rws <= BOUNDS[3]))[:, None] & ((cols >= BOUNDS[0]) & (cols <= BOUNDS[1]))[None, :]
    npts = sum(len(p) for p in polygons) + sum(len(h) for g in hole_groups for h in g)
    print(f"wrote {out}: {len(polygons)} polygons, {sum(map(len, hole_groups))} holes, {npts} points; "
          f"raster land inside BOUNDS {(land & inb).sum() * DX * DZ:.0f} m2")


if __name__ == "__main__":
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
