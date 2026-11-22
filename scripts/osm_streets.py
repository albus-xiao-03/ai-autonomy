"""Convert Overpass street JSON (`out geom` with node ids) into game/boston-streets.js.

Ways are split at shared nodes (intersections) so the game's road graph connects exactly
where OpenStreetMap streets meet, then simplified (Douglas-Peucker, 1.5 m). I-93 is not
included: it comes from game/highway-data.js.
Usage: python3 -I scripts/osm_streets.py streets.json game/boston-streets.js
"""
import json, re, sys
from collections import Counter

LON0, LAT0, MX, MZ = -71.065, 42.366, 82249.37752584313, 111320.0
BOUNDS = (-1127 - 60, 1415 + 60, -1135 - 60, 1102 + 60)
WIDTH = {"trunk": (12, 7.5), "trunk_link": (7, 5), "primary": (10, 6.5), "primary_link": (7, 5),
         "secondary": (9, 6), "secondary_link": (6.5, 5), "tertiary": (8, 5.5), "tertiary_link": (6, 4.5),
         "residential": (6.5, 4.5), "unclassified": (6.5, 4.5), "living_street": (5, 4)}

def xy(p):
    return ((p["lon"] - LON0) * MX, (LAT0 - p["lat"]) * MZ)

def dp(points, tol=1.5):
    if len(points) < 3: return points
    (x1, z1), (x2, z2) = points[0], points[-1]
    dx, dz = x2 - x1, z2 - z1; L = (dx * dx + dz * dz) ** .5 or 1e-9
    best, idx = 0, 0
    for i, (x, z) in enumerate(points[1:-1], 1):
        d = abs(dz * x - dx * z + x2 * z1 - z2 * x1) / L
        if d > best: best, idx = d, i
    if best <= tol: return [points[0], points[-1]]
    return dp(points[:idx + 1], tol)[:-1] + dp(points[idx:], tol)

src, out = sys.argv[1], sys.argv[2]
ways = [e for e in json.load(open(src))["elements"] if e["type"] == "way" and e.get("geometry")]
use = Counter(n for w in ways for n in set(w["nodes"]))
pieces = []
for w in ways:
    t = w["tags"]; hw = t.get("highway", "residential")
    oneway = t.get("oneway") in ("yes", "1", "true", "-1") or t.get("junction") == "roundabout"
    pts = [xy(p) for p in w["geometry"]]; nodes = w["nodes"]
    if t.get("oneway") == "-1": pts, nodes = pts[::-1], nodes[::-1]
    lanes = re.match(r"\d+", t.get("lanes", "") or "")
    two, one = WIDTH.get(hw, (6.5, 4.5))
    width = min(14, int(lanes.group()) * 3.2) if lanes else (one if oneway else two)
    if oneway: width = min(width, 9)
    start = 0
    for i in range(1, len(nodes)):
        if i == len(nodes) - 1 or use[nodes[i]] > 1:
            seg = dp(pts[start:i + 1])
            if any(BOUNDS[0] <= x <= BOUNDS[1] and BOUNDS[2] <= z <= BOUNDS[3] for x, z in seg) and len(seg) >= 2:
                piece = {"id": f"{w['id']}-{len(pieces)}", "t": "highway" if hw == "trunk" and not oneway and width >= 12 else ("oneway" if oneway else "twoway"),
                         "w": round(width, 1), "p": [[round(x, 2), round(z, 2)] for x, z in seg]}
                if t.get("name"): piece["n"] = t["name"]
                if t.get("bridge") and t.get("bridge") != "no": piece["b"] = 1
                if t.get("tunnel") and t.get("tunnel") != "no": piece["u"] = 1
                pieces.append(piece)
            start = i
data = {"attribution": "© OpenStreetMap contributors (ODbL)", "source": "Overpass API " + json.load(open(src))["osm3s"]["timestamp_osm_base"], "pieces": pieces}
with open(out, "w") as f:
    f.write("// Generated from OpenStreetMap streets. © OpenStreetMap contributors, ODbL.\n// Regenerate with scripts/osm_streets.py; do not edit by hand.\n")
    f.write("window.BOSTON_STREETS=" + json.dumps(data, separators=(",", ":")) + ";\n")
segs = sum(len(p["p"]) - 1 for p in pieces)
print(len(pieces), "pieces", segs, "segments", Counter(p["t"] for p in pieces), "bridges", sum("b" in p for p in pieces), "tunnels", sum("u" in p for p in pieces))
