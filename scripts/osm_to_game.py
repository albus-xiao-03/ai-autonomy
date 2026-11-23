"""Convert Overpass building JSON into game/boston-buildings.js (compact, game coordinates)."""
import json, math, re, sys

src, out = sys.argv[1], sys.argv[2]
LON0, LAT0, MX, MZ = -71.065, 42.366, 82249.37752584313, 111320.0
TOTAL_POP = 27700  # approx 2020 census for the screenshot area (see SPEC.md Section 4)
UNIQUE_NAMES = ["Massachusetts State House", "Old State House", "Faneuil Hall", "Quincy Market", "Old North Church", "Paul Revere House",
    "TD Garden", "North Station", "Museum of Science", "Bulfinch Building", "Boston City Hall", "Old City Hall",
    "Old State House", "Old West Church", "Otis House Museum", "The Vilna Shul", "Custom House Tower", "Custom House Block", "The Battle of Bunker Hill Museum",
    "Courthouse", "Parkman House", "Peter Faneuil", "Saint Leonard", "St. Leonard", "Christ Church",
    "Ether Dome", "Massachusetts General Hospital"]
UNIQUE_BUILDING = {"church", "cathedral", "chapel", "synagogue", "government", "stadium", "train_station",
    "public", "civic", "historic", "temple", "mosque"}
RES = {"apartments", "house", "residential", "semidetached_house", "terrace", "dormitory", "detached"}
OFFICE = {"office", "commercial", "hotel", "university", "college", "school", "industrial"}
SHOP = {"retail", "kiosk", "supermarket"}
SKIP = {"roof", "shed", "service", "garage", "garages", "boathouse", "construction", "bridge", "ruins"}

def xy(lon, lat):
    return ((lon - LON0) * MX, (LAT0 - lat) * MZ)

def ring_of(el):
    if el["type"] == "way":
        return [xy(p["lon"], p["lat"]) for p in el.get("geometry", [])]
    for m in el.get("members", []):
        if m.get("role") == "outer" and m.get("geometry"):
            return [xy(p["lon"], p["lat"]) for p in m["geometry"]]
    return []

def area_centroid(pts):
    a = cx = cz = 0.0
    for (x1, z1), (x2, z2) in zip(pts, pts[1:] + pts[:1]):
        c = x1 * z2 - x2 * z1
        a += c; cx += (x1 + x2) * c; cz += (z1 + z2) * c
    if abs(a) < 1e-6:
        return 0.0, sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    return abs(a) / 2, cx / (3 * a), cz / (3 * a)

def hull(pts):
    pts = sorted(set(pts))
    if len(pts) < 3: return pts
    def cross(o, a, b): return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0: lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0: up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]

def min_rect(pts):
    h = hull(pts); best = None
    for (x1, z1), (x2, z2) in zip(h, h[1:] + h[:1]):
        ang = math.atan2(z2 - z1, x2 - x1); c, s = math.cos(ang), math.sin(ang)
        us = [x * c + z * s for x, z in h]; vs = [-x * s + z * c for x, z in h]
        w, d = max(us) - min(us), max(vs) - min(vs)
        if best is None or w * d < best[0]: best = (w * d, w, d, ang)
    return best[1], best[2], best[3]

def num(v):
    m = re.match(r"\s*([0-9.]+)", v or "")
    return float(m.group(1)) if m else None

def simplify(pts, n=28):
    if len(pts) <= n: return pts
    step = len(pts) / n
    return [pts[int(i * step)] for i in range(n)]

els = json.load(open(src))["elements"]
rows, res_ids = [], []
for el in els:
    t = el.get("tags", {}); b = t.get("building", "yes")
    if b in SKIP or t.get("building:part"): continue
    ring = ring_of(el)
    if len(ring) < 4: continue
    if ring[0] == ring[-1]: ring = ring[:-1]
    area, cx, cz = area_centroid(ring)
    if area < 25: continue
    name = t.get("name", "")
    amen = t.get("amenity", "")
    if amen == "fire_station": kind = "fire"
    elif amen == "police": kind = "police"
    elif b == "hospital" or amen in ("hospital", "clinic"): kind = "medical"
    elif t.get("man_made") == "tower" or b == "tower": kind = "unique"  # bridge towers etc.: structures, no residents
    elif t.get("historic") or b in UNIQUE_BUILDING or amen in ("place_of_worship", "townhall", "courthouse") \
            or any(name.lower() == u.lower() or name.lower().startswith(u.lower() + " ") or name.lower().startswith("the " + u.lower()) for u in UNIQUE_NAMES) or "courthouse" in name.lower() or "church" in name.lower(): kind = "unique"
    elif b in RES: kind = "res"
    elif b in OFFICE: kind = "office"
    elif b in SHOP: kind = "shop"
    elif b == "parking": kind = "parking"
    else:
        levels = num(t.get("building:levels"))
        kind = "office" if area > 1400 or (levels and levels > 8) else "res"
    h = num(t.get("height"))
    if h is None:
        lv = num(t.get("building:levels"))
        h = lv * 3.3 + 1.5 if lv else {"res": 13, "office": 28, "shop": 7, "parking": 12}.get(kind, 16)
    w, d, rot = min_rect(ring)
    row = {"id": el["id"], "k": kind, "x": round(cx, 1), "z": round(cz, 1), "w": round(w, 1), "d": round(d, 1),
           "r": round(rot, 3), "h": round(min(h, 220), 1)}
    if name and kind in ("unique", "fire", "police", "medical"): row["n"] = name
    if kind in ("unique", "fire", "police", "medical"):
        row["fp"] = [[round(x - cx, 1), round(z - cz, 1)] for x, z in simplify(ring)]
    # Bridge structures get their own models: cable-stayed towers (Zakim) and stone towers (Longfellow).
    if t.get("building") == "tower" and t.get("man_made") == "pier" and h >= 60: row["st"] = "cable"
    elif t.get("man_made") == "tower" and t.get("tower:construction") == "stone": row["st"] = "stone"
    if kind == "res":
        row["s"] = (el["id"] * 2654435761) % 4  # one of four residential styles, stable per building
        res_ids.append(len(rows))
    rows.append(row)

per = TOTAL_POP / max(1, len(res_ids))
for i, idx in enumerate(res_ids):
    rows[idx]["p"] = int(per) + (1 if i < TOTAL_POP - int(per) * len(res_ids) else 0)
data = {"attribution": "© OpenStreetMap contributors (ODbL)", "source": "Overpass API, " + json.load(open(src))["osm3s"]["timestamp_osm_base"],
        "bbox": {"south": 42.3561, "west": -71.0787, "north": 42.3762, "east": -71.0478},
        "population": TOTAL_POP, "buildings": rows}
with open(out, "w") as f:
    f.write("// Generated from OpenStreetMap building footprints. © OpenStreetMap contributors, ODbL.\n")
    f.write("// Regenerate with the Overpass query in SPEC.md Section 4; do not edit by hand.\n")
    f.write("window.BOSTON_BUILDINGS=" + json.dumps(data, separators=(",", ":")) + ";\n")
from collections import Counter
print(len(rows), Counter(r["k"] for r in rows), "per-building residents", round(per, 2))
