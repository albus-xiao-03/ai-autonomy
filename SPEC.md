# SPEC.md: Boston AI Mayor (Borough)

> **For any AI coding tool (read first):**
> 1. Read this whole file before writing code.
> 2. Section 2 (Hard rules) is never negotiable. Do not change these without being asked.
> 3. Do not say something is "done" unless you ran the game and verified it. Update the Status column in Section 12 with what you actually verified.
> 4. One feature per task. After each task, run the game, take a screenshot, and compare it to the intent in this file.
> 5. Work on branch `utkarsh` only. Never push to `main`.

Legend for sources: **[DOC]** = from the original Google Doc. **[CHAT]** = stated by the developer in conversation. **[PROPOSED]** = suggested addition, not yet confirmed by the developer. Confirm or delete these.

---

## 1. One-line pitch

A Cities: Skylines-style sandbox of downtown Boston where a **local-LLM AI mayor** runs the city while the player builds it and throws protests and disasters at it. A **reward function** measures resident satisfaction, so we can see whether the mayor adapts and stabilizes the city. [DOC][CHAT]

The demo question: *Can an AI mayor keep a city stable under pressure?*

## 2. Hard rules (never break)

- [CHAT] Git: work on branch `utkarsh`. Never push to `main`. When told to "push", push the `utkarsh` branch.
- [CHAT] The mayor uses the **local model** `qwen3:8b` through **Ollama**. No cloud LLM for the mayor.
- [CHAT] If Ollama is unavailable, the game must **visibly label** the fallback controller.
- [CHAT] **No pre-made road blocks or pre-squared land.** The player places roads and buildings freely, like Cities: Skylines.
- [CHAT] **Non-square land.** The terrain and land shape follow the reference map (rivers, harbor, irregular coastline), not a square grid.
- [CHAT] The **building palette must always stay available** (placing buildings must not be removed when other tools change).
- [CHAT] Roads connect **seamlessly** (no overlapping roads that just "go over" each other). Bridges and tunnels are used where roads cross.
- [DOC] **Historical landmarks cannot be moved or replaced.**
- [DOC] Residents are **law-abiding** (they never break laws). See Section 6 for what "going their own way" means.
- [CHAT] Close unused dev ports. The game currently runs on port 8712 (8711 is retired).
- [CHAT] Claims must be verifiable. Keep the README honest about limits so another model can fact-check.

## 3. Platform and art style

- [DOC] three.js, runs in the browser.
- [DOC] Art style: **diorama to low-poly**. Top-down/orbit view first.
- [CHAT] Cars are very basic low-poly cars.
- [DOC] Focus on **one city only** (Boston) before generating any other city ideas.

## 4. The map and scale

- [CHAT] Real-scale Boston. The developer said "1.1 scale" and later "one to one scale"; the current build uses **1:1 geographic distances** with simplified arcade building clusters. **Open question: confirm 1:1.**
- [CHAT] Because 1:1 is large and buildings end up far apart, play is split into **levels** (Section 5).
- [CHAT] Because the Charles River divides the city, **bridges** are required.
- Reference area (from the Apple Maps screenshot in the Google Doc): North End, West End, Downtown, Beacon Hill, Boston Common, TD Garden, Massachusetts General Hospital, Massachusetts State House, Faneuil Hall Marketplace, Museum of Science, Galvin Green, Paul Revere Park, Richard McKinnon Park, Cambridge St, Congress St, Nashua St, Edwin H. Land Blvd.
- [CHAT] **Predetermined, famous office and residential areas** are placed on the map. The player connects them with roads and watches the city run. These are fixed (see landmark rule).
- [CHAT] **Fixed highway:** I-93 (Central Artery / Thomas P. O'Neill Jr. Tunnel) with **predetermined exits** and **underground tunnel sections**. It runs from one edge of the map to the other. As levels expand, it continues through the newly visible area.
- [CHAT] Regional through-traffic (cars entering and leaving at the map edges) is **inactive for now**. Resident cars use local roads.

## 5. Levels and progression

- [CHAT] Four levels. The map starts small and **expands each level** (with a zoom-out).
- [CHAT] **Level 1:** two main areas near City Hall.
- [CHAT] Level completion is detected and shown. [PROPOSED] Define the exact completion condition per level (for example, satisfaction above X for Y in-game days).
- [PROPOSED] Level 1 should be fully playable and demoable on its own, even if levels 2 to 4 are rough.

## 6. Residents

- [DOC] Hybrid population. [CHAT] **A slider controls the mix:**
  - **Routine residents** follow a scripted daily schedule (home, work, shops, leisure, parks).
  - **Autonomous residents** go their own way, driven by their own "thoughts" (a small local LLM, 1 to 2B parameters). [DOC]
  - Slider at 0% means all routine. At 100% means all autonomous.
- [DOC] Autonomous residents are still **law-abiding**: they choose destinations and activities freely but never break laws. [PROPOSED] Confirm this interpretation.
- [PROPOSED] Autonomous residents choose from a fixed menu of allowed actions (go to work, shop, visit a park, go home, join a protest, evacuate), and the small LLM only picks among them. This keeps them fast and safe.
- [PROPOSED] Show a small "thought" bubble on a selected resident so the audience can see the difference between routine and autonomous residents.
- [PROPOSED] Performance target: at least 200 simulated residents at 30+ FPS, with only a small number of LLM resident calls in flight at once.

## 7. Building and roads (player tools)

- [CHAT] **Road types:** highway (2 lanes each direction), one-way, two-way.
- [CHAT] Point-and-click roads **and** drag roads. Curved roads with full-width previews and snapping. Road upgrades. One-way reversal.
- [CHAT] **Elevation modes:** ground, bridge/overpass, tunnel.
- [CHAT] Gold access points show where roads connect to buildings (clear rule for how buildings connect to roads).
- [CHAT] **Junction controls:** traffic lights (inspired by Mini Motorways style), stop signs, and yield signs. Stop and yield signs apply to the selected incoming approach and show an arrow of traffic flow.
- [CHAT] **Buildings:** six placeable types, rotate with R, bulldoze, undo. Placements are saved across reloads and levels.
- [CHAT] Construction can happen **while the simulation runs**, and traffic reroutes.
- [CHAT] **Camera:** WASD move, Q/E rotate, mouse orbit, zoom, drag to pan. The player can **deselect** a tool to move the map.
- [CHAT] Tool tabs: Roads, Junctions, Buildings, City.
- [CHAT] Cars follow lanes, turns, road heights, and traffic controls. They move accurately.

## 8. The AI mayor

- [CHAT] Model: `qwen3:8b` via Ollama (local).
- [CHAT] Visible **thought bubble**: click it to see the mayor's orders, explanations, and what actually happened.
- [CHAT] Existing actions: dispatch services (for example ambulance to a district) and community outreach (raises district authority). Districts can **refuse** orders.
- [DOC] Mayor responsibilities: protests, natural disasters, corruption, police, fire, traffic, EMS, hospitals.
- [PROPOSED] **Action space (define fully so the LLM output is parseable):**

| Action | Parameters | Effect |
|---|---|---|
| dispatch_police | district | reduces unrest, uses police capacity |
| dispatch_fire | district | extinguishes fire/disaster damage |
| dispatch_ems | district | sends ambulances, relieves hospital queue |
| redirect_traffic | road/junction, mode | changes signal timing or closes a road |
| open_shelter | district | protects residents during disasters |
| community_outreach | district | raises district authority/trust |
| anti_corruption_review | district/department | reduces corruption level |
| do_nothing | none | explicit no-op |

- [PROPOSED] The mayor receives a compact state summary each decision (satisfaction per district, active events, service capacity, traffic congestion) and returns **strict JSON**. Invalid output falls back safely and is logged.
- [PROPOSED] Decision cadence: one decision per N in-game minutes (set N so Qwen's latency never freezes the game).

## 9. Events (the "making its life tough" part)

- [DOC] Predetermined **protests, natural disasters, corruption**.
- [CHAT] Disasters and protests must **affect the city, traffic, and the mayor's decisions**.
- [PROPOSED] **Event catalog (start small):**

| Event | Example trigger | Effects |
|---|---|---|
| Protest | scripted at a landmark (for example State House, City Hall) | road closures, police demand, satisfaction drop nearby |
| Flood / storm surge | near the harbor or river | closes low roads and tunnels, damages buildings |
| Blizzard | citywide | slows traffic, raises EMS demand |
| Fire | a building | needs fire dispatch, spreads if ignored |
| Corruption scandal | a department | lowers trust, makes some orders get refused |

- [PROPOSED] A **"Trigger event" panel** so the presenter can fire events on demand during the demo.

## 10. Reward function (resident satisfaction)

- [DOC] A reward function gives an idea of how satisfied residents are.
- [PROPOSED] Satisfaction score 0 to 100 per district and overall, built from weighted parts:
  - commute time and congestion
  - service coverage and response time (police, fire, EMS, hospitals)
  - event damage and unrest
  - trust/corruption level
  - access to housing, jobs, shops, and parks
- [PROPOSED] The score is **always visible on screen**, with a small history graph. It is also fed into the mayor's prompt so the mayor can see the effect of its choices.
- [PROPOSED] Log score before and after each mayor action so we can show "the mayor's decision improved the city by X."

## 11. Demo requirements (Sundai Hack 150, 3D Worlds)

- Demos are at **8pm**. **No slides allowed.** Share screen over Zoom and show the live game.
- Add the project card on sundai.club and vote. Top 5 get **5 minutes** to pitch.
- [PROPOSED] **5-minute demo script:**
  1. (0:00) One-sentence pitch and show the Boston map.
  2. (0:30) Place a few roads and buildings live; show cars moving.
  3. (1:30) Show the slider: routine versus autonomous residents.
  4. (2:15) Trigger a protest or flood. Show the satisfaction score drop.
  5. (3:00) Open the mayor's thought bubble: orders, reasoning, outcome.
  6. (4:00) Show the score recover (or show a different mayor choice).
  7. (4:30) Close: what is next (more events, more cities).
- [PROPOSED] **Safety net:** keep a saved city state that loads in one click, so the demo does not depend on building from scratch. Keep Ollama warmed up (run one dummy decision before presenting).
- [PROPOSED] Definition of done for the demo: the build runs from a clean clone with one command, and the demo script above works end to end three times in a row.

## 12. Status (update after each verified change)

Statuses below come from the previous tool's own reports. They are **UNVERIFIED** until re-tested.

| Area | Requirement | Status | Evidence / verification limits |
|---|---|---|---|
| Audit | Snapshot and scope | done (verified) | 2026-11-22; branch utkarsh, base d2de892 plus pre-existing uncommitted dist changes, including untracked incidents.js. Audit ran that working tree, not a clean clone. Only this table and AGENTS command/code-map placeholders were edited. No game fixes. |
| Audit | Verification boundaries | done (verified) | Browser UI on 8712 plus Node harnesses. /tmp/check-highway-incidents.cjs and /tmp/audit-borough.cjs load current real I-93. Five /tmp/regression-check-*.cjs harnesses substitute an old straight highway fixture, so their passes do not verify real I-93 joins. /tmp/check-live-mayor.cjs called real local Qwen. Harnesses are temporary, not committed or portable clean-clone tests. |
| 3.1 | three.js browser game | done (verified) | dist/index.html script entry; dist/world.js CityWorld.mount. Browser loaded and rendered on 8712. |
| 3.2 | Low-poly diorama; top-down/orbit | partial | dist/world.js mount, toggleView, pointer orbit handlers. Low-poly buildings/top-down screenshot inspected; orbit controls exist but full mouse orbit was not exercised in this audit. |
| 3.3 | Basic low-poly cars | done (unverified) | dist/world.js update constructs instanced box bodies, cabins and four wheels. Headless simulation emitted vehicles; no close-up moving-car visual check this audit. |
| 3.4 | Boston only | done (verified) | dist/geography.js BOSTON_GEOGRAPHY; dist/planner.js seedArcade and landmarks. Boston-only UI rendered. |
| 4.1 | 1:1 geographic distances and arcade clusters | partial | dist/geography.js scale=1 and metersPerDegree; dist/planner.js point/seedArcade; dist/world.js resize scale bar. 100 m label rendered; map/landmark dimensions not independently surveyed. Existing chat already confirms 1:1. |
| 4.2 | Levels address large 1:1 map | done (verified) | dist/planner.js stages/seedArcade; four expanding bounds exercised in Node. Browser displayed Level 1. |
| 4.3 | Bridges across Charles | partial | dist/planner.js roadError/heightAt/route; dist/world.js bridgeRibbon. Synthetic separate bridge/tunnel crossing test passed; no actual Charles crossing built in this browser audit. |
| 4.4 | Full reference area and named places | partial | dist/planner.js landmarks includes seven landmarks; seedArcade includes eight districts/areas. Museum of Science, Galvin Green, Paul Revere Park and Richard McKinnon Park have no named landmark entries. Original Apple Maps reference not independently compared this audit. |
| 4.5 | Fixed famous residential/office areas | done (verified) | dist/planner.js seedArcade and remove preserve area buildings. Two Level-1 areas rendered; Node checked later unlocks and fixed protections. |
| 4.6 | Real I-93, predetermined exits, underground sections | violates a hard rule | dist/highway-data.js linework and four ramps exist; dist/planner.js highwaySeed imports endpoint heights but heightAt ignores them. Current-data audit found 76 endpoint-height mismatches and eight adjacent-segment vertical discontinuities (up to 12 m). Seamless connection hard rule fails. |
| 4.7 | I-93 map-edge to map-edge as map expands | partial | dist/highway-data.js endpoints match latitudes 42.354/42.378; dist/planner.js highwayGates checks four Level-1 boundary gates. Full geographic line exists but height discontinuities prevent claiming continuous drivable highway. |
| 4.8 | Regional traffic inactive; residents use local roads | done (verified) | dist/sim.js getState enables regional cars only if throughTraffic===true; app.start omits it. Current-I93 harness asserted zero regional cars and completed six local work/home trips. |
| 5.1 | Four expanding levels with zoom-out | partial | dist/planner.js stages/seedArcade tested across 1–4; dist/app.js nextLevel handler calls world.focusLevel. Full browser level-transition/zoom sequence not replayed. |
| 5.2 | Level 1: two main areas near City Hall | done (verified) | dist/planner.js seedArcade unlocks beacon/government; landmarks fixes City Hall. Browser screenshot shows all three. |
| 5.3 | Completion detected and shown; exact condition | partial | dist/app.js render requires day finished, all workers arrived/home, all sites accessed, and no unresolved incidents. Current-data harness finished six commutes; browser finished a day after protest mediation, showed all six home, Level complete, and Next level enabled. No satisfaction-duration criterion implemented; proposed criterion remains unconfirmed. |
| 5.4 | Proposed Level 1 demoable alone | partial | Browser placed road, ran day, triggered protest, saw real Qwen mediation and corruption refusals. Service access must be built separately; full clean-state demo repeated three times was not performed. |
| 6.1 | Hybrid resident mix slider, 0–100% | missing | dist/index.html has no population-mix input; dist/sim.js start/createHousehold creates only scheduled residents. |
| 6.2 | Routine home/work/shop/leisure/park schedule | partial | dist/sim.js createHousehold/residentTick/addTrip. Current-data work/home day passed; synthetic building harness exercised leisure. Shops/parks/social share one optional leisure destination rather than distinct daily needs. |
| 6.3 | Autonomous residents using local 1–2B LLM | missing | dist/sim.js residentTick is scripted; only mayor decide calls a model. Local model list contains no configured resident model. |
| 6.4 | Residents always law-abiding | partial | dist/planner.js directed buildGraph/route and waitAt enforce direction and timed controls in tests. No autonomous policy or conflict-aware collision/right-of-way system; universal law compliance not verified. |
| 6.5 | Proposed finite allowed resident actions | missing | dist/sim.js residentTick uses fixed schedule states; no resident LLM action menu/parser. |
| 6.6 | Proposed selected-resident thought bubble | missing | dist/index.html bubble is mayor-only; dist/world.js has no selectable resident thought UI. |
| 6.7 | Proposed 200 residents at 30+ FPS; bounded LLM concurrency | partial | dist/world.js update uses instancing; dist/sim.js decide allows one mayor request. Default population six; no resident inference queue or 200-resident FPS benchmark. |
| 7.1 | Highway four lanes; one-way; two-way | done (verified) | dist/planner.js widths/buildGraph; dist/world.js drawRoads; dist/index.html road buttons. Directed routing/lane fixture tests passed; all controls rendered. |
| 7.2 | Point-and-click roads | done (verified) | dist/app.js place/draftPath; browser keyboard point placement connected Beacon Hill to Government Center and Run day accepted it. |
| 7.3 | Drag roads | done (unverified) | dist/world.js pointerdown/pointerup onRoadStart/onRoadEnd; dist/app.js mount callbacks. Drag mode exists; actual mouse drag not exercised this audit. |
| 7.4 | Curves, full-width previews and snapping | partial | dist/planner.js curve/draftPoint/pathError; dist/world.js roadPreview. Curve/group/atomic validation and snap fixture tests passed; full visual curve-preview flow not replayed. |
| 7.5 | Road upgrades and one-way reversal | done (verified) | dist/planner.js upgrade; dist/app.js place/reverse handler. Whole-road upgrade/reversal assertions passed in fixture harness. |
| 7.6 | Ground, bridge/overpass and tunnel modes | partial | dist/planner.js heightAt/buildGraph; dist/world.js bridgeRibbon/drawRoads. Synthetic grade-separation assertions passed; real fixed I-93 vertical joins fail (4.6). |
| 7.7 | Gold building connection points and access rule | done (verified) | dist/planner.js access allows forward-facing clear dry driveway within 20 m of curb; dist/app.js accessHelp. Gold points rendered; snapped road enabled actual browser commute. |
| 7.8 | Lights; incoming stop/yield; flow arrows | partial | dist/planner.js controlPlacement/waitAt/signalState; dist/world.js drawControls. Incoming-approach and timed-wait tests passed on fixture; no actual browser junction-control drive-through this audit. Priority simplified. |
| 7.9 | Six building types and free placement | done (verified) | dist/app.js stock/drawPalette; dist/planner.js place/buildingError. All-six fixture test passed; browser placed free residence (population 6→12) and Undo restored six. |
| 7.10 | Building R rotation, bulldoze and Undo | done (verified) | dist/app.js rotate/place/undo; dist/planner.js remove. Browser R changed 0°→45° and Undo restored inventory; fixture tested demolition/household restoration. |
| 7.11 | Placements survive reloads and levels | partial | dist/app.js save/startup load uses borough-levels-v1; dist/planner.js seedArcade/load. Fixture tested serialized load and level carryover; actual browser reload persistence not replayed. |
| 7.12 | Live construction and traffic rerouting | done (verified) | dist/app.js networkEdited; dist/sim.js refreshNetwork; dist/planner.js changed. Fixture deleted/restored roads and added homes/jobs during day with rerouting/population assertions; browser palette remained reachable while running. |
| 7.13 | Camera move/rotate/orbit/zoom/pan/deselect | partial | dist/world.js cameraLoop/wheel/pointer handlers; dist/app.js choose/Escape. Browser deselection succeeded. Full WASD/QE, pointer zoom and mouse pan/orbit combinations not tested this audit. |
| 7.14 | Roads, Junctions, Buildings, City tool tabs | done (verified) | dist/index.html tablist; dist/app.js tab click handler. Browser switched tabs successfully; Events is additional. |
| 7.15 | Accurate lane/turn/height/control car motion | partial | dist/sim.js route/travelTimeline/lanePosition; dist/world.js update. Numerical fixture tests pass. No citywide vehicle collision/junction priority, I-93 grade discontinuities, and no moving-car visual certification. |
| 8.1 | Local qwen3:8b via Ollama only | violates a hard rule | dist/app.js start supplies local Ollama; real Qwen flood/protest responses passed. dist/sim.js decide also accepts arbitrary http/https endpoints and config.model. Mock-only remote endpoint accepted and labeled Qwen, so local-only hard rule is not enforced. No real remote request was made. |
| 8.2 | Visible mayor bubble with orders/explanations/outcomes/history | done (verified) | dist/app.js history/render and bubble handler. Browser opened history showing Qwen mediation, Incident resolved, and Dispatch refused with actual outcome. Public statement can contradict result (observed statement claimed resolution while dispatch was refused). |
| 8.3 | Dispatch, outreach, authority and district refusal | done (verified) | dist/sim.js dispatch/outreach/setAuthority; dist/incidents.js respond. Browser noon corruption reduced authority and both later Qwen dispatches were refused; incident harness verified responders/recovery. |
| 8.4 | Full mayor responsibilities: police/fire/traffic/EMS/hospital/corruption | partial | dist/incidents.js respond dispatches typed responders, evacuates/repairs/mediates; dist/sim.js dispatch/outreach. No police/fire/EMS capacity, hospital queue, signal management or anti-corruption investigation. |
| 8.5 | Proposed dispatch_police(district) | partial | dist/incidents.js respond maps generic dispatch at protest to police vehicle. No exact dispatch_police JSON contract or police capacity. |
| 8.6 | Proposed dispatch_fire(district) | partial | dist/incidents.js respond maps generic dispatch at fire to firetruck; fire response harness passed. No exact named action/service capacity. |
| 8.7 | Proposed dispatch_ems(district), hospital queue relief | partial | dist/sim.js dispatch uses hospital route; dist/incidents.js respond uses ambulance. No dispatch_ems contract or hospital queue. |
| 8.8 | Proposed redirect_traffic(road/junction,mode) | missing | dist/sim.js decide allowed orders omit traffic actions. dist/planner.js controls are player tools only. |
| 8.9 | Proposed open_shelter(district) | partial | dist/incidents.js respond/tick evacuate via bus and isSheltered; no explicit shelter building/capacity or open_shelter action. Evacuation implementation inspected, not separately completed in this audit. |
| 8.10 | Proposed community_outreach(district) | partial | dist/sim.js outreach and dist/incidents.js respond("outreach") raise authority; internal name differs from proposed JSON contract. |
| 8.11 | Proposed anti_corruption_review(district/department) | missing | dist/sim.js tick creates authority loss, but decide has no investigation action, department state or corruption reduction. |
| 8.12 | Proposed do_nothing | partial | dist/sim.js decide allows monitor only for low-severity incidents; dist/incidents.js respond logs monitoring. No universal do_nothing contract. |
| 8.13 | Compact state with district satisfaction, events, capacity, congestion | partial | dist/sim.js decide prompt has authority, current incident, response-route access and recent outcomes. Satisfaction, capacity, queues and measured congestion absent. |
| 8.14 | Strict JSON validation, safe fallback and logging | partial | dist/sim.js decide parses JSON and validates allowed order; offline/invalid-order injected tests reached Civic controller · model offline. Raw invalid-output reason is not logged; other schema fields not strictly validated, contract differs from proposed action/district/reason. |
| 8.15 | Decision cadence must not freeze game | partial | dist/sim.js step refuses advancement while pending; injected test proved frozen minute during request. dist/app.js frame and world cameraLoop remain asynchronous, so render loop continues. No startup warm-up or latency-independent simulation cadence. |
| 9.1 | Predetermined protests/disasters/corruption | done (verified) | dist/incidents.js tick schedules protest 09:45/weather 11:15; dist/sim.js tick corruption 12:00. Incident harness and browser manually triggered protest; browser observed noon corruption. |
| 9.2 | Events affect city, traffic and mayor decisions | done (verified) | dist/incidents.js spawn/updateNetwork/damage/respond; dist/planner.js setClosures; dist/sim.js decide. Current-map harness asserted closures, failed route, repairs/reopen; real local Qwen resolved flood and protest. |
| 9.3 | Proposed landmark protest: closures, police demand, nearby score | partial | dist/incidents.js spawn/tick supports protest closures/mediation. Scheduled site is first office, not landmark; no police-demand capacity or per-district satisfaction. |
| 9.4 | Proposed coastal flood/storm surge, low roads/tunnels, building damage | partial | dist/incidents.js types/spawn and dist/planner.js roadBlocked use radius and height. Building damage/road closure verified; placement allowed on any dry land, no actual coast/water level/storm-surge model. |
| 9.5 | Proposed citywide blizzard, slower traffic and EMS demand | missing | dist/incidents.js types contains storm, not blizzard. No snowfall-wide speed or EMS-demand model. |
| 9.6 | Proposed building fire, fire dispatch and spread | partial | dist/incidents.js tick increases fire damage and respond sends firetruck; harness passed dispatch/resolution. No spatial spread to new buildings, only growing damage within initial affected sites. |
| 9.7 | Proposed departmental corruption scandal | partial | dist/sim.js tick lowers focal district authority at noon and dispatch refuses below 40. No department-level corruption/trust model or investigation. Browser observed refusals. |
| 9.8 | Proposed live Trigger event panel | done (verified) | dist/index.html eventTools; dist/app.js data-event handlers/place. Browser triggered protest at map cursor, displayed incident and Qwen history; five manual event types present, no manual corruption button. |
| 10.1 | Resident satisfaction reward | done (verified) | dist/sim.js getState computes clamped overall 0–100 satisfaction; dist/app.js render happy. Browser showed 82%, protest drop to 78%, later 67% after refusals. |
| 10.2 | Proposed overall AND district weighted scores | partial | dist/sim.js getState calculates one overall score only; districts hold authority/status, no satisfaction. Formula uses hand-set bonuses/penalties. |
| 10.3 | Score: commute time and congestion | partial | dist/sim.js getState uses completed residents routeMinutes average; no measured network congestion or queue delay metric. |
| 10.4 | Score: coverage and response times for police/fire/EMS/hospitals | partial | dist/sim.js getState uses refusal count and relief bonus. No service-specific coverage, capacity, response-time components or hospital queue. |
| 10.5 | Score: event damage and unrest | partial | dist/sim.js getState subtracts active severity. No direct weighted building damage or independent unrest metric. |
| 10.6 | Score: trust/corruption | partial | dist/sim.js getState penalizes refusals and failed Hall protection. District authority/corruption not directly included as score component. |
| 10.7 | Score: housing/jobs/shops/parks access | partial | dist/sim.js getState workRate and leisure-count bonus. No weighted housing/job availability or reachable amenity coverage score; leisure bonus counts venues even if disconnected. |
| 10.8 | Score always visible | partial | dist/index.html footer happy; dist/app.js render. Visible percentage during run, dash during planning. No useful planning score. |
| 10.9 | Proposed score history graph | missing | dist/index.html footer has numeric happy only; dist/app.js render has no score-history array/chart. |
| 10.10 | Score fed into mayor prompt | missing | dist/sim.js decide prompt omits satisfaction entirely. |
| 10.11 | Before/after score logged per mayor action | missing | dist/sim.js record stores minute/thought/action/status/outcome/district only; no score snapshots or attribution. |
| Hard rules | Branch utkarsh only; never main | done (verified) | git branch --show-current returned utkarsh at d2de892 before audit; docs commit only, no push requested/performed. |
| Hard rules | Labeled fallback when Ollama down | done (verified) | dist/sim.js decide catch sets Civic controller · model offline; dist/app.js render engine. Injected transport failure and invalid JSON exercised fallback; actual Ollama process was left running. |
| Hard rules | Free placement, no pre-made road grid | done (verified) | dist/planner.js roadPath/place accept continuous coordinates; only fixed I-93 and named clusters seeded. Browser free residence and road placement succeeded; no local fixed block grid. |
| Hard rules | Non-square real Boston terrain | partial | dist/geography.js irregular polygons/holes; dist/world.js landShape/drawFog. Irregular harbor visible; level fog has rectangular bounds, not squared parcels. Original Apple reference and shoreline fidelity not independently checked. |
| Hard rules | Building palette always available, never hidden | violates a hard rule | dist/app.js tab handler sets buildingTools.hidden=true on Roads/Junctions/City/Events. Browser locator #palette.isVisible() returned false on Roads. Buildings tab remains reachable while running but palette itself is hidden. |
| Hard rules | Seamless roads; use grade separation at crossings | violates a hard rule | dist/planner.js roadSurfaces unions ground and buildGraph separates differing heights; fixture assertions passed. Current fixed I-93 has eight vertical discontinuities (4.6); cannot certify seamless network. |
| Hard rules | Historical landmarks cannot move/replace | done (verified) | dist/planner.js landmarks static, buildingError/roadError reject overlaps, remove only handles player objects/roads; fixed protections exercised in fixtures and protected landmarks rendered. |
| Hard rules | Law-abiding residents | partial | See 6.4: directed routine routing and controls tested; autonomous residents missing and universal right-of-way/collision compliance not established. |
| Hard rules | 8712 only; close old game ports | done (verified) | lsof checked 8711/8712/8713: only existing Python server PID 75214 on 127.0.0.1:8712. Temporary 8713 stopped. Ollama 11434 is required, not a dev preview. |
| Hard rules | README claims remain honest/verifiable | violates a hard rule | README still claims rush-hour through traffic, highway connection as a goal, only dispatch/outreach, and pending disasters. Current app disables regional cars, changed goal, and contains uncommitted incident actions. README was intentionally left unchanged by audit scope. |
| README | Run command / local engine / frozen clock | done (verified) | Existing 8712 server rendered game; local qwen3:8b decisions exercised via browser and Node. Clock freezing verified, not endorsed as spec compliance. |
| README | Level layout/areas/player tools | partial | Code and fixture tests support descriptions. Full browser transitions through Levels 2–4 and repeated end-to-end days were not verified. Claim that fixed highway connection is required is stale (app.render completion omits it). |
| README | Save/reload and cross-level persistence | done (unverified) | dist/app.js save/startup loader and planner.seedArcade exist; synthetic serialized-load tests pass. Actual browser reload/cross-level persistence not verified this audit. |
| README | All camera gestures, pointer zoom and drag construction | done (unverified) | dist/world.js handlers exist; deselect tested. Mouse drag/orbit, full WASD/QE and wheel-around-pointer behavior not re-tested this audit. |
| README | Visual merge, bridge ramps/supports, tunnel hiding, car motion | partial | Numerical fixture coverage supports ground union, grades/controls, direction and lane offsets. Full moving visual suite not replayed; real I-93 heights demonstrably inconsistent. |
| README | Rush-hour cars on fixed highway | partial | Claim contradicted by dist/sim.js getState default throughTraffic false and app.start omitting opt-in. Fixture testing enables artificial straight-highway traffic only, not the real I-93 corridor. |
| README | Geography source accuracy, scale and real landmark locations | done (unverified) | dist/geography.js metadata and planner.point support attribution/projection; official geography was not independently re-downloaded or overlaid against Apple Maps in this audit. Landmark sizes explicitly approximate. |
| README | Mayor actions only dispatch/outreach; disasters pending | partial | Stale relative to audited working tree: dist/incidents.js implements five hazards and six generic responses; live Qwen flood/protest tests passed. These game changes remain uncommitted and a clean clone lacks them. |
| README | Leisure, parking and dynamic households | done (verified) | dist/sim.js addTrip/refreshNetwork; synthetic six-building fixture exercised reachable parking, new residents/jobs, leisure, demolition/Undo. Not a guarantee of all layouts. |
| Visual QA | Screenshot inspection and limits | partial | Inspected /Users/utkarsh/Documents/ChatGPT/22/audit-boston-initial.png and audit-boston-event.png. Scores: spec intent 5/10, HUD readability 5/10 (long scrolling panels), low-poly style 7/10, visual correctness 5/10 (I-93 grades fail numerical audit); Boston-reference match unscored because original map not compared. Browser automation used existing IAB, not a separate headless runner. No fixes per audit-only instruction. |

## 13. Known limits (keep honest)

- Traffic physics and collisions are simplified for arcade feel.
- Building clusters are simplified representations, not exact real buildings.
- Curves are edited as whole drawn roads, not per-segment.
- Regional through-traffic on I-93 is disabled for now.

## 14. Open questions (answer these)

1. Scale: confirm 1:1 versus another ratio.
2. Do autonomous residents ever join protests or evacuate, and is that still "law-abiding"?
3. What are the exact level completion conditions?
4. Which six building types ship in the palette?
5. Which model runs the small-LLM residents (for example a 1 to 2B Qwen), and does it run through the same Ollama?
6. Should the player ever control the mayor, or is the mayor always autonomous?

## 15. Later (not for the demo)

- More natural disasters and more events.
- Regional I-93 through-traffic at map edges.
- Other cities beyond Boston.
- Larger resident populations.