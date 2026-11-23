"""Convert Overpass traffic_signals / stop nodes into game/boston-signals.js (game coordinates).

The game snaps each point to its real intersection at load (CityPlan.setRealSignals): signals become
one signal per junction; stop signs keep the approach they sit on.
Usage: python3 -I scripts/osm_signals.py signals.json game/boston-signals.js
"""
import json, sys
LON0, LAT0, MX, MZ = -71.065, 42.366, 82249.37752584313, 111320.0
src, out = sys.argv[1], sys.argv[2]
elements = json.load(open(src))["elements"]
xy = lambda e: [round((e["lon"] - LON0) * MX, 2), round((LAT0 - e["lat"]) * MZ, 2)]
data = {"attribution": "© OpenStreetMap contributors (ODbL)",
        "signals": [xy(e) for e in elements if e["tags"].get("highway") == "traffic_signals"],
        "stops": [xy(e) for e in elements if e["tags"].get("highway") == "stop"]}
with open(out, "w") as f:
    f.write("// Generated from OpenStreetMap traffic signals and stop signs. © OpenStreetMap contributors, ODbL.\n")
    f.write("window.BOSTON_SIGNALS=" + json.dumps(data, separators=(",", ":")) + ";\n")
print(len(data["signals"]), "signal points,", len(data["stops"]), "stop points")
