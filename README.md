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

Only one model is in memory at a time: the engine makes the mayor and residents take turns and unloads the other model before each call (switching costs a few seconds). Idle models unload after 5 minutes.

If the engine is down, the game keeps running and labels the "Civic controller · engine offline" fallback.

All requirements and status are in `SPEC.md` (Part B holds the teammate's R1 engine requirements). The engine plan is `docs/engine-plan.md`. The teammate's Vite frontend (`npm run dev`) is a separate skeleton.

## Play

The map is the real Boston area of the reference screenshot at 1:1 (no levels): North End, West End, Beacon Hill, Downtown, the Charles River edge and the I-93 corridor. Buildings come from OpenStreetMap (© OpenStreetMap contributors, ODbL). Historical and unique buildings use their real footprint and height and are permanently protected (gold outline). Fire, police and medical buildings have an author-set lock (dashed blue outline). Every other building can be bulldozed to make room for your own roads and buildings. About 27,700 residents are divided equally across residential buildings.

The map opens in a 3D view. Zoom in for more detail (porches, cornices, windows); zoom out to see the whole area. Editing only works in the top-down view: choosing a road, building or bulldoze tool switches to it, and the button under the map toggles between "Top-down (edit)" and "3D view".

Real Boston streets come from OpenStreetMap and can be bulldozed, upgraded or restored (City tab: Restore real Boston streets). Cars drive them when you zoom in (visual traffic, about one car per 18 residents at rush hour). Seven neighbourhoods (Beacon Hill, North End, Charlestown, West End, Financial District, Government Center, Waterfront) are anchored to real buildings whose residents and workers the simulation follows. Run a day and get every resident to work and home; completion also requires every placed site to have road access and every incident to be closed.

The City tab's **Map layout** switch chooses *Real Boston* (default) or the *Old arcade layout* (gold neighbourhood pads, hand-placed landmark circles). Old level saves are offered through **Import old level save** instead of loading automatically.

The Buildings tab restores player placement alongside the fixed Boston areas. Place residences, offices, shops, social venues, parks and parking freely on unlocked dry land. R or Rotate changes orientation by 45 degrees. Face the entrance toward a road and keep the driveway within 20 meters of the curb. Each type has a limited player inventory. Fixed neighborhood clusters do not consume that inventory.

Player buildings and bulldozed Boston buildings are saved. They can be added or bulldozed while the day runs. New residences add six residents, and new offices, leisure venues and reachable parking are used by the simulation. Bulldozing returns the building to inventory. Undo restores it and its household during the current session.

The mayor and the real Boston city remain the core game. The road-building and camera controls are being developed toward a city-builder interaction style.

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

It checks all 293 imported segments, continuous elevations, map-edge routes, the map-edge gates of the single Boston map, ramp-to-player-street connections, and the existing player bridge/tunnel profile. It is a numerical routing test. The browser check covered a Cross Street ground-road connection; it does not certify every moving-car visual or junction conflict.

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

The browser saves progress under borough-boston-v1. Older borough-levels-v1 saves are imported once: unlocked Boston buildings under their roads and buildings are cleared. Earlier free-placement and arcade saves remain under their previous keys. Timed building deliveries are pending. The Events tab can trigger flood, severe storm, earthquake, protest and building fire during a running day. Scheduled protests/weather and the noon authority-loss scenario are also implemented. These use arcade closures, damage and response rules, not physical disaster models.
