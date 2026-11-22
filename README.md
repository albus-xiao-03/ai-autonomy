# Borough

An arcade city builder in the browser, using the Boston area from the shared reference.

## Run locally

Three processes, from the repository root:

    ollama serve                      # models: qwen3:8b (mayor), qwen3:1.7b (residents)
    uv sync && uv run aia serve       # AI engine on 127.0.0.1:8787
    python3 -m http.server 8712 --bind 127.0.0.1 --directory game

Open http://127.0.0.1:8712. The browser game owns the city (map, roads, traffic, incidents). The Python engine (`aiautonomy/`) makes the decisions through `/api/brain/*`:

- **Mayor brain** (Events tab): local Qwen 3 8B (default), rule-based, or Claude API. The cloud option stays off unless the engine was started with `AIA_ALLOW_PAID_API=1` and `ANTHROPIC_API_KEY` set; it bills that API account. The game clock holds while the mayor decides.
- **Autonomous residents** slider (Events tab): the share of residents who think for themselves with local qwen3:1.7b. They can go home, visit venues, protest, or break a few laws (speeding, vandalism, road blockade). Police patrols stop them.
- **Satisfaction** is fed to the mayor, shown with a history graph, and logged before and one hour after each mayor action.

If the engine is down, the game keeps running and labels the "Civic controller · engine offline" fallback.

The teammate R1 engine plan and spec are in `plans/R1.md` and `specs/R1.md`; its Vite frontend (`npm run dev`) is a separate skeleton.

## Play

Level 1 starts near City Hall with Beacon Hill homes and Government Center offices. Their gold access points need local roads. Connect homes and offices, run a day, and get every resident to work and home. Level completion also requires all placed sites to have road access and all incidents to be resolved. The fixed I-93 ramps are available for connections; a highway connection is not required to finish a level. The Next level button unlocks a larger map when the day finishes successfully. Existing roads carry forward.

Level 2 adds the West End and North End. Level 3 opens the river crossing to Kendall Square, the Financial District and Waterfront. Level 4 opens Charlestown. Neighborhoods use fixed illustrative building clusters.

The Buildings tab restores player placement alongside the fixed Boston areas. Place residences, offices, shops, social venues, parks and parking freely on unlocked dry land. R or Rotate changes orientation by 45 degrees. Face the entrance toward a road and keep the driveway within 20 meters of the curb. Each type has a limited player inventory. Fixed neighborhood clusters do not consume that inventory.

Player buildings save and carry into later levels. They can be added or bulldozed while the day runs. New residences add six residents, and new offices, leisure venues and reachable parking are used by the simulation. Bulldozing returns the building to inventory. Undo restores it and its household during the current session.

The mayor, expanding levels and fixed Boston areas remain the core game. The road-building and camera controls are being developed toward a city-builder interaction style.

Select highway, one-way or two-way roads. Highways have two lanes in each direction. Two-way roads have one lane in each direction. One-way travel follows the drawing direction. Choose Straight or Curve under Road shape. Straight roads support Click points and Drag road. Curves use three clicks for start, bend and endpoint. The full-width preview turns red for invalid placement and shows length or the reason construction is blocked. Snapping prioritizes access points, road endpoints and road edges. The Snap roads & angles toggle also enables 15-degree angle increments.

Choose Upgrade under Action, then choose a road type and elevation and click a player road. Reverse one-way changes its direction. Curves are treated as whole drawn roads for upgrades, reversal and bulldozing. A failed construction or upgrade leaves the prior layout intact. Edits are available while the day runs, and active trips are recalculated when the network changes. Undo restores the prior road state and recalculates traffic. Click a selected tool again to deselect it. Move map also deselects tools. Drag the map with the Move map tool, or use right drag or Shift drag while constructing. WASD moves relative to the camera. Q/E rotates the view. Middle drag rotates and tilts the camera. The wheel zooms around the pointer. Right-click cancels the current road draft. Escape deselects tools. Space pauses or resumes, Ctrl/Cmd+Z undoes, and Page Up/Down cycles road elevation.

Road elevation supports ground, bridge/overpass and tunnel construction with all three road types. Structure endpoints must be on dry land. Bridges can cross water or land roads using continuous raised decks, ramps, railings and supports. Tunnels have portals and a dashed route guide. Underground vehicles are hidden until they emerge. Roads at different heights cross independently and connect at matching-height endpoints.

Ground-road surfaces merge into continuous junctions, with road markings opening at the connection. Road endpoints snap to neighborhood access points and other roads. Neighborhood access needs a clear connection within 20 meters of the road curb. Light driveways confirm access. Orange markers indicate missing access. Road access help explains the rule. Neighborhoods and landmarks are fixed. Bulldoze removes player roads, buildings and traffic controls. Undo reverses the latest edit.

Keyboard controls on the map use arrows for 25-meter cursor movement and Shift arrows for five-meter movement. Enter places the selected building or road endpoint. With Move map selected, arrows pan the view.

Regional through-traffic is inactive. Resident vehicles use the connected local road network, including I-93 when their route uses it. Cars have low-poly bodies, roofs and wheels. Animation follows directed routes, smooth turns, lane positions and actual bridge/tunnel elevations. Traffic lights alternate crossing directions. Stop signs stop the selected incoming approach, while yield signs slow it. Junction priority and citywide collision physics remain simplified.

The mayor's thought bubble opens the public explanations, orders and outcomes. Model-generated orders are labeled Qwen. Resident routines follow the directed player road network, including driveway access. Leisure trips occur only when a usable route exists.

## Highway verification

I-93 follows the imported MassGIS–MassDOT centerlines with four fixed surface ramps. Tunnel depths and bridge heights are illustrative. Adjacent segments now share the imported elevations; both directed carriageways and all four ramp connections pass routing checks. Regional through-traffic remains disabled.

Run the committed regression from the repository root with Node 18 or newer:

    node tests/highway-elevation.cjs

It checks all 293 imported segments, continuous elevations, map-edge routes, boundaries at all four levels, ramp-to-player-street connections, and the existing player bridge/tunnel profile. It is a numerical routing test. The browser check covered a Cross Street ground-road connection; it does not certify every moving-car visual or junction conflict.

## Geography

The map crop spans longitude -71.085 to -71.045 and latitude 42.354 to 42.378. The current requested scale is 1:1 in real-world meters, using a local equirectangular projection around 42.366 N, 71.065 W. The scale bar reports 100 meters.

Land comes from the Boston municipality boundary service, including Cambridge and Somerville. MassGIS hydrography supplies the water boundaries. Geometry has approximately 1.5-meter simplification tolerance at the original import scale. The source resolution generalizes some shore details.

Landmarks use geographic center coordinates with simplified low-poly models and approximate dimensions. Neighborhood clusters are arcade representations at real neighborhood locations. Exact surveyed building footprints and elevations remain a future accuracy pass.

Sources:
- https://services2.arcgis.com/d0NFID1O0ng4wccB/ArcGIS/rest/services/Boston_Municipality_Boundary/FeatureServer
- https://www.mass.gov/info-details/massgis-data-massdep-hydrography-125000
- https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/Massachusetts_Water_Features/FeatureServer

Traffic controls can be placed at connected junctions. Select Traffic lights and click the junction. For Stop sign or Yield sign, click the incoming street near that junction. The preview arrow points into the junction and shows the controlled direction. Placing another sign on the same approach replaces it. Bulldoze also removes signs. Controls persist with the plan and participate in Undo.

This prototype does not yet implement zoning, organic city growth, budgets, utilities or full service management. The mayor uses dispatch and outreach for the scripted district scenario. Incident responses add repairs, evacuation, mediation and monitoring. These are generic response actions; service capacities, hospital queues, autonomous residents, traffic-management orders and anti-corruption investigations are still missing.

The browser saves progress under borough-levels-v1. Earlier free-placement and arcade saves remain under their previous keys. Timed building deliveries are pending. The Events tab can trigger flood, severe storm, earthquake, protest and building fire during a running day. Scheduled protests/weather and the noon authority-loss scenario are also implemented. These use arcade closures, damage and response rules, not physical disaster models.
