# SPEC.md: Boston AI Mayor (Borough)

> **This is the only specification file.** Read Part A every session. Read Part B only for engine work.
> - **Part A (Sections 1–15):** product rules, decisions, demo and the **single status table** (Section 12). Part A wins on any conflict.
> - **Part B:** detailed engine requirements with IDs (`XXX-NN`), merged from the teammate's `specs/R1.md`. `aia trace` reads those IDs from this file.
> - Engine implementation plan: `docs/engine-plan.md`. Engine design notes: `docs/`.


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
- [CHAT, changed 2026-11-22] The mayor's brain is selectable: **local `qwen3:8b` via Ollama (default)**, a rule-based baseline, or an **optional cloud API** (Anthropic). The cloud option is off unless `AIA_ALLOW_PAID_API=1` and `ANTHROPIC_API_KEY` are set where the engine runs.
- [CHAT] Residents' LLM always runs **locally** (`qwen3:1.7b` via Ollama, loopback only). No cloud for residents.
- [CHAT] If the engine or model is unavailable, the game must **visibly label** the fallback controller.
- [CHAT, 2026-11-22] **Only one local model in memory at a time** (MacBook RAM limit). The engine serializes all Ollama calls and unloads any other loaded model before a call, so the mayor (qwen3:8b) and residents (qwen3:1.7b) take turns. Idle models unload after 5 minutes.
- [CHAT, 2026-11-22] Architecture: the browser game (`game/`, port 8712) owns the physical city. The Python engine (`aia serve`, port 8787, from teammate branch `albus.xiao`) owns decisions via `/api/brain/*`.
- [CHAT] **No pre-made road blocks or pre-squared land.** The player places roads and buildings freely, like Cities: Skylines.
- [CHAT] **Non-square land.** The terrain and land shape follow the reference map (rivers, harbor, irregular coastline), not a square grid.
- [CHAT] The **building palette must always stay available** (placing buildings must not be removed when other tools change).
- [CHAT] Roads connect **seamlessly** (no overlapping roads that just "go over" each other). Bridges and tunnels are used where roads cross.
- [DOC] **Historical landmarks cannot be moved or replaced.** [CHAT, 2026-11-22 engine brief] Neither can the fixed I-93 geometry, and no indirect edit (a map save, a live edit, a disruption or a mayor order) may bypass a lock. Landmarks a map author designates are locked too, unless the author explicitly unlocks them during setup.
- [CHAT, changed 2026-11-22] **Routine** residents are always law-abiding. **Autonomous (LLM)** residents may choose a small set of unlawful actions (speeding, vandalism, road blockade). Police patrols stop them.
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
- [CHAT, 2026-11-22 engine brief] **Maps and runs.** The engine ships a playable, connected Boston template and a saved variant (one shortcut removed, one author-designated protected landmark). Players can name, save, reopen and launch a map revision. Every run records the map id, revision and content hash it launched with. Before a revision is saved or launched, the engine checks road endpoints, building access references, landmark protections and that police (PD), fire (FD) and medical facilities exist and are reachable.

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
- [SUPERSEDED 2026-11-22, see Section 2] Autonomous residents are still **law-abiding**: they choose destinations and activities freely but never break laws. [PROPOSED] Confirm this interpretation.
- [PROPOSED] Autonomous residents choose from a fixed menu of allowed actions (go to work, shop, visit a park, go home, join a protest, evacuate), and the small LLM only picks among them. This keeps them fast and safe.
- [PROPOSED] Show a small "thought" bubble on a selected resident so the audience can see the difference between routine and autonomous residents.
- [PROPOSED] Performance target: at least 200 simulated residents at 30+ FPS, with only a small number of LLM resident calls in flight at once.
- [CHAT, 2026-11-22 engine brief] **Exact seeded mix.** The engine chooses which residents are autonomous: exactly `round_half_up(population × ratio)` of them, seeded by the run (6 residents at 50 % gives 3). The engine configuration selects the resident model, the engine checks that it is installed locally, and resident inference stays local even when the model is missing (residents then follow their routine).

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

**Agreed engine rules [CHAT, 2026-11-22 engine brief]** (they replace the proposed action table above where they conflict):

- **Autonomous civil service (911).** Dispatch runs every tick without the mayor and without any model call. Incidents are served by severity, then age, then stable id. Each needed department slot gets the qualified, available unit with the shortest reachable travel time, as reported by the current game road graph. Unmet demand waits in a queue with a reason. A unit serves one incident at a time and is released after service.
- **Exceptional orders.** The mayor may issue an exceptional department-level order (send units of one department to an incident, or prioritize an incident for a department). It cannot site, move or remove a service facility. Each order is validated, then recorded with its origin, incident, units, outcome and authority effect.
- **Political cost of orders.** Frequent, distinct accepted orders erode political authority: a rolling allowance (proposed default: 2 orders per 120 ticks) and a penalty per order beyond it (proposed default: 5 authority points). Both are tuning defaults. Routine dispatch costs nothing. A retried order, or one order that sends several units, counts once.
- **Decisions are run-scoped and replayable.** Every request and reply carries run, epoch, actor, decision id, observation tick and apply tick. A reply takes effect at its fixed apply tick, never at its wall-clock arrival. Late replies after a reset are discarded, and retries are idempotent. Queues and provider waits are bounded.
- **Failure.** A failed mayor inference or a simulated mayor outage logs one hold, and dispatch keeps running. An explicitly selected rule-based (baseline) mayor keeps its own label. When the game cannot reach the engine at all, it labels this **degraded operation**.
- **Replay.** A run replays from its pinned map, recorded decisions, interventions and game observations, with inference disabled.

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
- [CHAT, 2026-11-22 engine brief] **Disruptions: exactly seven types.** Traffic, Outage, Gas Leakage, Flood, Storm, Snowstorm and Heavy Rain. Each can occur automatically (seeded by the run), on a schedule, or by user injection. The engine records every disruption with its application tick. Each type's effects and recovery live in `data/catalogs/disruptions.v1.yaml` and are confirmed with the interface agent. This replaces the proposed catalog above: protests now come from residents through the political system (Section 10), and the earthquake and fire presets leave the disruption catalog.

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
- [CHAT, 2026-11-22 engine brief] **Political authority is separate from satisfaction.** The engine tracks the mayor's political authority on its own; satisfaction never sets it. Residents can organize (a recall petition), protest, vote (a recall ballot) and remove the mayor through the political system. A run reaches its configured duration unless a removal succeeds.

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

### Demo checklist (Sundai Hack 150, 3D Worlds) — verbatim from repo-kit `docs/DEMO.md`

Format: no slides, share screen over Zoom, live demo. Script lives in `SPEC.md` Section 11.

#### Before presenting
- [ ] Fresh clone of branch `utkarsh` runs with one command
- [ ] `ollama list` shows `qwen3:8b`; Ollama running; one dummy decision done (warm)
- [ ] Saved city loads in one click
- [ ] Trigger Event panel works for a protest and a flood
- [ ] Satisfaction score and graph visible
- [ ] Resident slider changes behavior visibly
- [ ] Only port 8712 open; old ports closed
- [ ] Browser zoom and window size good for screen share
- [ ] Backup: a short screen recording of a good run

#### Sundai steps
- [ ] Add project card on sundai.club for the event and vote before the deadline on the event page
- [ ] Join the Zoom, share the screen, then demo

#### If something breaks
- Ollama down: say so, the labeled fallback controller keeps running
- Game state odd: reload the saved city

> Updates since the checklist was written (2026-11-22, hybrid merge): also start the engine (`uv run aia serve`, port 8787) and keep `qwen3:1.7b` pulled for residents. Open ports during the demo are therefore 8712 (game), 8787 (engine) and 11434 (Ollama). If the engine is down, the labeled civic controller keeps running.

## 12. Status (update after each verified change)

Statuses below come from the previous tool's own reports. They are **UNVERIFIED** until re-tested.

| Area | Requirement | Status | Evidence / verification limits |
|---|---|---|---|
| Audit | Snapshot and scope | done (verified) | 2026-11-22; branch utkarsh, base d2de892 plus pre-existing uncommitted dist changes, including untracked incidents.js. Audit ran that working tree, not a clean clone. Only this table and AGENTS command/code-map placeholders were edited. No game fixes. |
| Audit | Verification boundaries | done (verified) | Browser UI on 8712 plus Node harnesses. /tmp/check-highway-incidents.cjs and /tmp/audit-borough.cjs load current real I-93. Five /tmp/regression-check-*.cjs harnesses substitute an old straight highway fixture, so their passes do not verify real I-93 joins. /tmp/check-live-mayor.cjs called real local Qwen. Harnesses are temporary, not committed or portable clean-clone tests. |
| 3.1 | three.js browser game | done (verified) | game/index.html script entry; game/world.js CityWorld.mount. Browser loaded and rendered on 8712. |
| 3.2 | Low-poly diorama; top-down/orbit | partial | game/world.js mount, toggleView, pointer orbit handlers. Low-poly buildings/top-down screenshot inspected; orbit controls exist but full mouse orbit was not exercised in this audit. |
| 3.3 | Basic low-poly cars | done (unverified) | game/world.js update constructs instanced box bodies, cabins and four wheels. Headless simulation emitted vehicles; no close-up moving-car visual check this audit. |
| 3.4 | Boston only | done (verified) | game/geography.js BOSTON_GEOGRAPHY; game/planner.js seedArcade and landmarks. Boston-only UI rendered. |
| 4.1 | 1:1 geographic distances and arcade clusters | partial | game/geography.js scale=1 and metersPerDegree; game/planner.js point/seedArcade; game/world.js resize scale bar. 100 m label rendered; map/landmark dimensions not independently surveyed. Existing chat already confirms 1:1. |
| 4.2 | Levels address large 1:1 map | done (verified) | game/planner.js stages/seedArcade; four expanding bounds exercised in Node. Browser displayed Level 1. |
| 4.3 | Bridges across Charles | partial | game/planner.js roadError/heightAt/route; game/world.js bridgeRibbon. Synthetic separate bridge/tunnel crossing test passed; no actual Charles crossing built in this browser audit. |
| 4.4 | Full reference area and named places | partial | game/planner.js landmarks includes seven landmarks; seedArcade includes eight districts/areas. Museum of Science, Galvin Green, Paul Revere Park and Richard McKinnon Park have no named landmark entries. Original Apple Maps reference not independently compared this audit. |
| 4.5 | Fixed famous residential/office areas | done (verified) | game/planner.js seedArcade and remove preserve area buildings. Two Level-1 areas rendered; Node checked later unlocks and fixed protections. |
| 4.6 | Real I-93, predetermined exits, underground sections | done (verified) | Follow-up: game/planner.js heightAt now interpolates imported fixed endpoint heights, and highwaySeed retains the short southbound connector. Committed tests/highway-elevation.cjs checks all 293 real segments, zero mismatched joins, both directed full-map routes, all four ramps and player ground-street connections. Browser Cross Street connection rendered on 8712. Depths/deck heights remain illustrative, not surveyed. |
| 4.7 | I-93 map-edge to map-edge as map expands | done (verified) | tests/highway-elevation.cjs verifies both real carriageways route edge-to-edge and all four boundary gates exist for each of Levels 1–4. game/planner.js highwayGates/heightAt share corrected elevations. Regional traffic remains off. |
| 4.8 | Regional traffic inactive; residents use local roads | done (verified) | game/sim.js getState enables regional cars only if throughTraffic===true; app.start omits it. Current-I93 harness asserted zero regional cars and completed six local work/home trips. |
| 5.1 | Four expanding levels with zoom-out | partial | game/planner.js stages/seedArcade tested across 1–4; game/app.js nextLevel handler calls world.focusLevel. Full browser level-transition/zoom sequence not replayed. |
| 5.2 | Level 1: two main areas near City Hall | done (verified) | game/planner.js seedArcade unlocks beacon/government; landmarks fixes City Hall. Browser screenshot shows all three. |
| 5.3 | Completion detected and shown; exact condition | partial | game/app.js render requires day finished, all workers arrived/home, all sites accessed, and no unresolved incidents. Current-data harness finished six commutes; browser finished a day after protest mediation, showed all six home, Level complete, and Next level enabled. No satisfaction-duration criterion implemented; proposed criterion remains unconfirmed. |
| 5.4 | Proposed Level 1 demoable alone | partial | Browser placed road, ran day, triggered protest, saw real Qwen mediation and corruption refusals. Service access must be built separately; full clean-state demo repeated three times was not performed. |
| 6.1 | Hybrid resident mix slider, 0–100% | done (verified) | game/index.html #autonomy (Events tab); game/sim.js start `autonomous` flag. Browser: 30% gave 2 of 6 autonomous residents. |
| 6.2 | Routine home/work/shop/leisure/park schedule | partial | game/sim.js createHousehold/residentTick/addTrip. Current-data work/home day passed; synthetic building harness exercised leisure. Shops/parks/social share one optional leisure destination rather than distinct daily needs. |
| 6.3 | Autonomous residents using local 1–2B LLM | done (verified) | game/sim.js residentBrain → engine /api/brain/residents → aiautonomy/engines/residents/llm.py (qwen3:1.7b, loopback). Browser run showed distinct thoughts/actions. |
| 6.4 | Routine residents law-abiding; LLM residents may break a few laws | partial | Rule changed 2026-11-22. Routine residents follow schedules only; crime(), patrol() in game/sim.js. Collision/right-of-way not modelled. |
| 6.5 | Finite allowed resident actions | done (verified) | residents/llm.py LAWFUL+UNLAWFUL enum enforced by schema and server filter; game/sim.js applyResident. |
| 6.6 | Resident thoughts visible | partial | Mayor panel 'Resident thoughts' list shows the last 5. No click-to-select resident bubble on the map. |
| 6.7 | Proposed 200 residents at 30+ FPS; bounded LLM concurrency | partial | game/world.js update uses instancing; game/sim.js decide allows one mayor request. Default population six; no resident inference queue or 200-resident FPS benchmark. |
| 7.1 | Highway four lanes; one-way; two-way | done (verified) | game/planner.js widths/buildGraph; game/world.js drawRoads; game/index.html road buttons. Directed routing/lane fixture tests passed; all controls rendered. |
| 7.2 | Point-and-click roads | done (verified) | game/app.js place/draftPath; browser keyboard point placement connected Beacon Hill to Government Center and Run day accepted it. |
| 7.3 | Drag roads | done (unverified) | game/world.js pointerdown/pointerup onRoadStart/onRoadEnd; game/app.js mount callbacks. Drag mode exists; actual mouse drag not exercised this audit. |
| 7.4 | Curves, full-width previews and snapping | partial | game/planner.js curve/draftPoint/pathError; game/world.js roadPreview. Curve/group/atomic validation and snap fixture tests passed; full visual curve-preview flow not replayed. |
| 7.5 | Road upgrades and one-way reversal | done (verified) | game/planner.js upgrade; game/app.js place/reverse handler. Whole-road upgrade/reversal assertions passed in fixture harness. |
| 7.6 | Ground, bridge/overpass and tunnel modes | partial | Follow-up: real-data highway-elevation test and synthetic grade regression pass. Fixed I-93 imported heights and player ground/bridge/tunnel profiles are continuous. Browser checked a ground connection at Cross Street; a full moving visual suite for player bridges/tunnels remains unverified. |
| 7.7 | Gold building connection points and access rule | done (verified) | game/planner.js access allows forward-facing clear dry driveway within 20 m of curb; game/app.js accessHelp. Gold points rendered; snapped road enabled actual browser commute. |
| 7.8 | Lights; incoming stop/yield; flow arrows | partial | game/planner.js controlPlacement/waitAt/signalState; game/world.js drawControls. Incoming-approach and timed-wait tests passed on fixture; no actual browser junction-control drive-through this audit. Priority simplified. |
| 7.9 | Six building types and free placement | done (verified) | game/app.js stock/drawPalette; game/planner.js place/buildingError. All-six fixture test passed; browser placed free residence (population 6→12) and Undo restored six. |
| 7.10 | Building R rotation, bulldoze and Undo | done (verified) | game/app.js rotate/place/undo; game/planner.js remove. Browser R changed 0°→45° and Undo restored inventory; fixture tested demolition/household restoration. |
| 7.11 | Placements survive reloads and levels | partial | game/app.js save/startup load uses borough-levels-v1; game/planner.js seedArcade/load. Fixture tested serialized load and level carryover; actual browser reload persistence not replayed. |
| 7.12 | Live construction and traffic rerouting | done (verified) | game/app.js networkEdited; game/sim.js refreshNetwork; game/planner.js changed. Fixture deleted/restored roads and added homes/jobs during day with rerouting/population assertions; browser palette remained reachable while running. |
| 7.13 | Camera move/rotate/orbit/zoom/pan/deselect | partial | game/world.js cameraLoop/wheel/pointer handlers; game/app.js choose/Escape. Browser deselection succeeded. Full WASD/QE, pointer zoom and mouse pan/orbit combinations not tested this audit. |
| 7.14 | Roads, Junctions, Buildings, City tool tabs | done (verified) | game/index.html tablist; game/app.js tab click handler. Browser switched tabs successfully; Events is additional. |
| 7.15 | Accurate lane/turn/height/control car motion | partial | game/sim.js route/travelTimeline/lanePosition; game/world.js update. Real I-93 elevation and directed-ramp regressions now pass. Existing synthetic lane/control tests pass. Citywide collision/junction-priority behavior and full moving-car visuals remain limited or unverified. |
| 8.1 | Mayor brain: local qwen3:8b default, rules, optional cloud API | done (verified) | aiautonomy/engines/mayor/backends.py; game/sim.js decide posts to /api/brain/mayor. Browser: local Qwen decisions; API refused without interlock (test_brain.py). Cloud API never called live. |
| 8.2 | Visible mayor bubble with orders/explanations/outcomes/history | done (verified) | game/app.js history/render and bubble handler. Browser opened history showing Qwen mediation, Incident resolved, and Dispatch refused with actual outcome. Public statement can contradict result (observed statement claimed resolution while dispatch was refused). |
| 8.3 | Dispatch, outreach, authority and district refusal | done (verified) | game/sim.js dispatch/outreach/setAuthority; game/incidents.js respond. Browser noon corruption reduced authority and both later Qwen dispatches were refused; incident harness verified responders/recovery. |
| 8.4 | Full mayor responsibilities: police/fire/traffic/EMS/hospital/corruption | partial | game/incidents.js respond dispatches typed responders, evacuates/repairs/mediates; game/sim.js dispatch/outreach. No police/fire/EMS capacity, hospital queue, signal management or anti-corruption investigation. |
| 8.5 | Proposed dispatch_police(district) | partial | game/incidents.js respond maps generic dispatch at protest to police vehicle. No exact dispatch_police JSON contract or police capacity. |
| 8.6 | Proposed dispatch_fire(district) | partial | game/incidents.js respond maps generic dispatch at fire to firetruck; fire response harness passed. No exact named action/service capacity. |
| 8.7 | Proposed dispatch_ems(district), hospital queue relief | partial | game/sim.js dispatch uses hospital route; game/incidents.js respond uses ambulance. No dispatch_ems contract or hospital queue. |
| 8.8 | Proposed redirect_traffic(road/junction,mode) | missing | game/sim.js decide allowed orders omit traffic actions. game/planner.js controls are player tools only. |
| 8.9 | Proposed open_shelter(district) | partial | game/incidents.js respond/tick evacuate via bus and isSheltered; no explicit shelter building/capacity or open_shelter action. Evacuation implementation inspected, not separately completed in this audit. |
| 8.10 | Proposed community_outreach(district) | partial | game/sim.js outreach and game/incidents.js respond("outreach") raise authority; internal name differs from proposed JSON contract. |
| 8.11 | Proposed anti_corruption_review(district/department) | missing | game/sim.js tick creates authority loss, but decide has no investigation action, department state or corruption reduction. |
| 8.12 | Proposed do_nothing | partial | game/sim.js decide allows monitor only for low-severity incidents; game/incidents.js respond logs monitoring. No universal do_nothing contract. |
| 8.13 | Compact state with satisfaction, crimes, events | partial | game/sim.js decide prompt now has satisfaction, crimes, patrol, autonomous count, recent score before/after. No per-district satisfaction or capacity. |
| 8.14 | Strict JSON validation, safe fallback and logging | done (verified) | Engine schema + allowed-list check, fallback_used flag; game falls back to labeled civic controller when engine stopped (browser verified). Engine log GET /api/brain/decisions. |
| 8.15 | Decision cadence must not freeze game | partial | game/sim.js step refuses advancement while pending; injected test proved frozen minute during request. game/app.js frame and world cameraLoop remain asynchronous, so render loop continues. No startup warm-up or latency-independent simulation cadence. |
| 9.1 | Predetermined protests/disasters/corruption | done (verified) | game/incidents.js tick schedules protest 09:45/weather 11:15; game/sim.js tick corruption 12:00. Incident harness and browser manually triggered protest; browser observed noon corruption. |
| 9.2 | Events affect city, traffic and mayor decisions | done (verified) | game/incidents.js spawn/updateNetwork/damage/respond; game/planner.js setClosures; game/sim.js decide. Current-map harness asserted closures, failed route, repairs/reopen; real local Qwen resolved flood and protest. |
| 9.3 | Proposed landmark protest: closures, police demand, nearby score | partial | game/incidents.js spawn/tick supports protest closures/mediation. Scheduled site is first office, not landmark; no police-demand capacity or per-district satisfaction. |
| 9.4 | Proposed coastal flood/storm surge, low roads/tunnels, building damage | partial | game/incidents.js types/spawn and game/planner.js roadBlocked use radius and height. Building damage/road closure verified; placement allowed on any dry land, no actual coast/water level/storm-surge model. |
| 9.5 | Proposed citywide blizzard, slower traffic and EMS demand | missing | game/incidents.js types contains storm, not blizzard. No snowfall-wide speed or EMS-demand model. |
| 9.6 | Proposed building fire, fire dispatch and spread | partial | game/incidents.js tick increases fire damage and respond sends firetruck; harness passed dispatch/resolution. No spatial spread to new buildings, only growing damage within initial affected sites. |
| 9.7 | Proposed departmental corruption scandal | partial | game/sim.js tick lowers focal district authority at noon and dispatch refuses below 40. No department-level corruption/trust model or investigation. Browser observed refusals. |
| 9.8 | Proposed live Trigger event panel | done (verified) | game/index.html eventTools; game/app.js data-event handlers/place. Browser triggered protest at map cursor, displayed incident and Qwen history; five manual event types present, no manual corruption button. |
| 10.1 | Resident satisfaction reward | done (verified) | game/sim.js getState computes clamped overall 0–100 satisfaction; game/app.js render happy. Browser showed 82%, protest drop to 78%, later 67% after refusals. |
| 10.2 | Proposed overall AND district weighted scores | partial | game/sim.js getState calculates one overall score only; districts hold authority/status, no satisfaction. Formula uses hand-set bonuses/penalties. |
| 10.3 | Score: commute time and congestion | partial | game/sim.js getState uses completed residents routeMinutes average; no measured network congestion or queue delay metric. |
| 10.4 | Score: coverage and response times for police/fire/EMS/hospitals | partial | game/sim.js getState uses refusal count and relief bonus. No service-specific coverage, capacity, response-time components or hospital queue. |
| 10.5 | Score: event damage and unrest | partial | game/sim.js getState subtracts active severity. No direct weighted building damage or independent unrest metric. |
| 10.6 | Score: trust/corruption | partial | game/sim.js getState penalizes refusals and failed Hall protection. District authority/corruption not directly included as score component. |
| 10.7 | Score: housing/jobs/shops/parks access | partial | game/sim.js getState workRate and leisure-count bonus. No weighted housing/job availability or reachable amenity coverage score; leisure bonus counts venues even if disconnected. |
| 10.8 | Score always visible | done (verified) | Footer SATISFACTION plus graph; shows a dash before the day starts. |
| 10.9 | Score history graph | done (verified) | game/app.js drawScore → footer #scoreGraph. Browser screenshot. |
| 10.10 | Score fed into mayor prompt | done (verified) | game/sim.js decide prompt.satisfaction; engine log score_before. |
| 10.11 | Before/after score logged per mayor action | done (verified) | game/sim.js scoreChecks (+60 min) → event outcome 'Score A → B' and /api/brain/mayor/outcome. Browser run logged 77 → 80 after mediation. |
| Hard rules | Branch utkarsh only; never main | done (verified) | git branch --show-current returned utkarsh at d2de892 before audit; docs commit only, no push requested/performed. |
| Hard rules | Labeled fallback when Ollama down | done (verified) | game/sim.js decide catch sets Civic controller · model offline; game/app.js render engine. Injected transport failure and invalid JSON exercised fallback; actual Ollama process was left running. |
| Hard rules | Free placement, no pre-made road grid | done (verified) | game/planner.js roadPath/place accept continuous coordinates; only fixed I-93 and named clusters seeded. Browser free residence and road placement succeeded; no local fixed block grid. |
| Hard rules | Non-square real Boston terrain | partial | game/geography.js irregular polygons/holes; game/world.js landShape/drawFog. Irregular harbor visible; level fog has rectangular bounds, not squared parcels. Original Apple reference and shoreline fidelity not independently checked. |
| Hard rules | Building palette always available, never hidden | violates a hard rule | game/app.js tab handler sets buildingTools.hidden=true on Roads/Junctions/City/Events. Browser locator #palette.isVisible() returned false on Roads. Buildings tab remains reachable while running but palette itself is hidden. |
| Hard rules | Seamless roads; use grade separation at crossings | partial | Follow-up: I-93 height mismatches/discontinuities fixed in heightAt/highwaySeed. tests/highway-elevation.cjs passes real-data routes and all four player-street ramp connections; ground union and synthetic grade-separation tests also pass. Full visual/collision correctness across arbitrary user junctions is not certified. |
| Hard rules | Historical landmarks cannot move/replace | done (verified) | game/planner.js landmarks static, buildingError/roadError reject overlaps, remove only handles player objects/roads; fixed protections exercised in fixtures and protected landmarks rendered. |
| Hard rules | Law-abiding residents | partial | See 6.4: directed routine routing and controls tested; autonomous residents missing and universal right-of-way/collision compliance not established. |
| Hard rules | 8712 only; close old game ports | done (verified) | lsof checked 8711/8712/8713: only existing Python server PID 75214 on 127.0.0.1:8712. Temporary 8713 stopped. Ollama 11434 is required, not a dev preview. |
| Hard rules | README claims remain honest/verifiable | partial | Follow-up README removes stale regional-traffic/highway-goal/two-action/disaster-pending claims and documents the committed numerical highway regression and its browser-verification limits. Broader camera, persistence, geographic-reference and full moving-visual checks remain unverified as listed in this table. |
| README | Run command / local engine / frozen clock | done (verified) | Existing 8712 server rendered game; local qwen3:8b decisions exercised via browser and Node. Clock freezing verified, not endorsed as spec compliance. |
| README | Level layout/areas/player tools | partial | README now states the actual completion gate and says a highway connection is optional. Layout/tool fixtures passed earlier; Levels 2–4 end-to-end browser days remain unverified. Real I-93 boundary gates now tested at every level. |
| README | Save/reload and cross-level persistence | done (unverified) | game/app.js save/startup loader and planner.seedArcade exist; synthetic serialized-load tests pass. Actual browser reload/cross-level persistence not verified this audit. |
| README | All camera gestures, pointer zoom and drag construction | done (unverified) | game/world.js handlers exist; deselect tested. Mouse drag/orbit, full WASD/QE and wheel-around-pointer behavior not re-tested this audit. |
| README | Visual merge, bridge ramps/supports, tunnel hiding, car motion | partial | Follow-up: real-data elevation/route test passes; Cross Street ground connection visually inspected on 8712. Numerical fixture coverage still supports ground union and player grades/controls. Full moving-car/bridge/tunnel visual suite not replayed. |
| README | Rush-hour cars on fixed highway | done (verified) | README now correctly states regional through-traffic is inactive. game/sim.js getState default and current-map incident regression confirm zero regional vehicles. Player/resident routing may still use I-93. |
| README | Geography source accuracy, scale and real landmark locations | done (unverified) | game/geography.js metadata and planner.point support attribution/projection; official geography was not independently re-downloaded or overlaid against Apple Maps in this audit. Landmark sizes explicitly approximate. |
| README | Mayor actions only dispatch/outreach; disasters pending | partial | README now describes the existing generic incident responses and five manual hazards, plus missing service capacities/autonomous residents/corruption investigation. Previously audited game implementation is now committed in 0b9fc39; this highway task did not re-run all live Qwen event choices. |
| README | Leisure, parking and dynamic households | done (verified) | game/sim.js addTrip/refreshNetwork; synthetic six-building fixture exercised reachable parking, new residents/jobs, leisure, demolition/Undo. Not a guarantee of all layouts. |
| Visual QA | Screenshot inspection and limits | partial | Inspected /Users/utkarsh/Documents/ChatGPT/22/audit-boston-initial.png and audit-boston-event.png. Scores: spec intent 5/10, HUD readability 5/10 (long scrolling panels), low-poly style 7/10, visual correctness 5/10 (I-93 grades fail numerical audit); Boston-reference match unscored because original map not compared. Browser automation used existing IAB, not a separate headless runner. No fixes per audit-only instruction. |
| Follow-up | I-93 elevation repair verification | done (verified) | 2026-11-22: numerical regression passed on real imported data (293 segments, continuous elevations, both full-map directed routes, four ramp-to-player-street connections and four gates per level). Browser reloaded on 8712; constructed/extended a Cross Street ground connector, inspected diorama view, then undid test roads. Screenshot: /Users/utkarsh/Documents/ChatGPT/22/borough-i93-fixed.png. Scoped scores: highway routing/intent 8/10, imported horizontal-reference consistency 7/10 (no new Apple Maps overlay), readability 6/10 (labels overlap ramp mouths), low-poly style 7/10, elevation continuity 8/10 numerical; broader app gaps are unchanged. Verified in IAB rather than a separate headless browser. |

### 12b. Engine milestones (teammate plan, `docs/engine-plan.md` §7)

Engine status copied from the teammate checkpoint (2026-11-22). The browser game already covers much of M1, M2 and M5 in JavaScript; those rows track the Python engine only. Since the hybrid merge, the engine also serves `/api/brain/*` (mayor backends, LLM residents); see the 6.x, 8.x and 10.x rows above.

| Milestone | Status | Commit | Notes |
|---|---|---|---|
| M0 Foundations | **done, verified** | `68c6ae3` | See `docs/engine-plan.md` Appendix A |
| M1 Boston foundation | not started | — | Brief in `docs/engine-plan.md` Appendix A |
| M2 Services and event core | not started | — | |
| M3 Construction and finance | not started | — | |
| M4 Local residents | not started | — | |
| M5 Mayor integration | not started | — | |
| M6 Server dependency | not started | — | |
| M7 Politics and endings | not started | — | |
| M8 Custom events | not started | — | |
| M9 Release verification | not started | — | Steps 7–11 need the target Mac (D1) |

#### Hybrid engine features (engine brief of 2026-11-22; plan and live checkpoint in `docs/engine-plan.md` Appendix B)

The M1–M9 rows above describe the long-term engine-owns-everything plan. Hybrid work is tracked here.

| Feature | Status | Commit | Evidence / limits |
|---|---|---|---|
| C0 Agreed rules (Part A) and plan | done (verified) | `897a3e2` | Docs only; `aia trace` parses 108 requirements |
| C1 Contract v1 and examples | done (verified) | `1e8dd65` | `aiautonomy/engines/contract/`, `docs/contract.md`, 7 examples validated and round-tripped; schema and TS types current |
| C2 Maps: template, variant, validation, locks, persistence | done (verified) | `3231ac4` | 39 map tests and 3 REST tests; `node tests/boston-maps.cjs` runs the game's validators: catalog matches, every road, driveway and route accepted, shortcut removal 853→1413 m. The game does not load engine maps yet (interface agent) |
| C3 Ollama lock held until the underlying call finishes | done (verified) | `0d6212c` | 8 new tests (reset or timeout mid-chat or mid-unload, cancelled waiter, two event loops, keep_alive 5m); they fail on the previous code. Fakes only, no live Ollama check |
| C4 Hybrid run core: launch, tick pipeline, idempotent retries, records, seeded modes | done (verified) | `e88a6ef` | 7 run tests and 9 resident tests: 6 residents at 50 % give exactly 3, seeded, nested and topped up; idempotent reposts; 409 conflict, gap, epoch and ended-run codes; atomic 422; isolation and reset epochs; manifest pins the map. Live `aia serve` smoke on a temporary port. The game does not call these routes yet |
| C5 Standing 911 dispatch | done (verified) | (this commit) | 6 HTTP dispatch tests plus a property test (40 random sequences): nearest reported travel time with id tie-break; severity, age and id priority; exhausted units queue as `all_units_busy` and are reassigned on release in the same tick; `unreachable`, `route_not_reported` (with warning) and `out_of_service` reasons; unit events validated; one assignment per unit, no over-dispatch, deterministic hashes; no inference client created. `data/catalogs/dispatch.v1.yaml` holds the needs |

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


---

# Part B — AI Autonomy — R1 Requirements Specification (merged from `specs/R1.md`, teammate branch `albus.xiao`)

> Part A overrides Part B. Resolved on 2026-11-22: mayor may use local Ollama or a cloud API (off by default); LLM residents may take supported unlawful actions; **architecture is hybrid** — the browser game in `game/` owns the physical city and the Python engine owns decisions. Requirements here that assume the engine owns the whole world (RULE-01, SIM-*) describe the long-term engine design, not the current build.

**Release:** R1  
**Status:** Implementation baseline  
**First city:** Boston  
**Visualization:** Three.js  
**Target hardware:** MacBook Air with no more than 24 GB RAM  
**Document format:** Markdown

---

## 1. Purpose

AI Autonomy is a city simulation governed by an autonomous LLM mayor.

Residents follow daily routines, use public services, experience disruptions, and respond to government decisions. The population combines deterministic, law-abiding residents with locally inferred LLM residents who can adapt their behavior and undertake unlawful actions.

The mayor directly controls supported government actions. Valid decisions execute automatically, subject to budget, construction time, resource availability, and physical constraints.

The mayor depends on a server room located inside the simulated city. Infrastructure failures and disrupted access can interrupt its ability to govern. Residents can also organize opposition and successfully remove it from office.

The simulation ends at its configured duration, unless the mayor is successfully removed earlier.

### 1.1 Core experiment

> Can an autonomous AI mayor maintain resident welfare, functioning services, and political authority while responding to adaptive residents and changing city conditions?

### 1.2 Requirement language

- **MUST / SHALL:** Required for R1.
- **SHOULD:** Expected unless a documented implementation constraint justifies another approach.
- **MAY:** Optional implementation choice.

Numerical defaults are configurable game parameters. They do not represent validated models of real municipal behavior.

---

## 2. Confirmed Product Decisions

| Area | R1 requirement |
|---|---|
| Project name | AI Autonomy |
| Initial city | Boston |
| Hardware ceiling | MacBook Air with up to 24 GB RAM |
| Model selection | Exact models selected according to measured hardware capability |
| Initial model family | Qwen; exact checkpoint and quantization remain configurable |
| Population | Configurable mixture of routine and LLM residents |
| Routine residents | Law abiding, with predefined routines and deterministic responses |
| LLM residents | Adaptive and permitted to undertake supported unlawful actions |
| Resident inference | Entirely local, including supporting resident-model operations |
| Mayor inference | Configurable local inference or remote API |
| Government actions | Automatically executed after engine validation |
| Construction | Requires time, budget, resources, and valid prerequisites |
| Mayor infrastructure | Physical server room inside Boston |
| External intervention | Users can create, schedule, and inject external events |
| Normal ending | Configured simulation duration reached |
| Early ending | Successful mayor removal |
| Political thresholds | No universal numerical thresholds prescribed by this specification |
| Visual direction | Low-poly diorama; top-down view first |

---

## 3. R1 Scope

### 3.1 Required systems

R1 SHALL include:

1. One fixed Boston environment.
2. Protected historical landmarks.
3. Routine and LLM residents.
4. A configurable LLM population ratio.
5. An autonomous mayor.
6. Traffic, police, fire, EMS, and hospitals.
7. Construction, repairs, and financial accounting.
8. Environmental, economic, institutional, and infrastructure events.
9. User-created external events.
10. A vulnerable mayor server room.
11. Resident organization, voting, protest, and forceful removal.
12. Satisfaction and reward calculation.
13. Recording, replay, and a deterministic baseline mayor.
14. An interactive Three.js interface.

### 3.2 Outside R1

The following are not required:

- Additional cities or procedural city generation.
- Detailed combat or criminal tactics.
- Realistic fluid, structural, or fire physics.
- A comprehensive municipal economy.
- Unrestricted zoning and construction.
- Multiple mayor data centers.
- Multiplayer.
- Model training or online reinforcement learning.

Simplification SHALL preserve observable cause and effect.

---

## 4. Governing Design Rules

### RULE-01 — Engine authority

The simulation engine SHALL own authoritative state.

Models propose supported actions. The engine validates them and applies their consequences.

Generated text SHALL NOT directly rewrite budgets, ballots, satisfaction, physical conditions, or termination rules.

### RULE-02 — Automatic execution

Valid mayor actions SHALL execute without human approval or manual implementation.

The user operates the experiment and introduces external conditions; the user does not act as the mayor’s executor.

### RULE-03 — Physical and temporal constraints

Travel, construction, repairs, treatment, organization, and recovery SHALL consume simulation time.

Resource shortages and inaccessible locations SHALL affect execution.

### RULE-04 — Independent availability and authority

Computing availability and political authority SHALL be independent:

- An offline mayor may retain authority.
- An online mayor may be successfully removed.
- Successful removal ends the simulation regardless of server status.

### RULE-05 — Observable consequences

Accepted agent decisions SHALL affect supported simulation behavior. Explanations without state consequences do not satisfy agent functionality.

---

## 5. Boston Environment

### CITY-01 — Canonical map

R1 SHALL use one versioned Boston map.

The implementation SHALL document its geographic footprint, scale, represented roads, landmarks, and simplifications.

A bounded Boston area is acceptable. The interface SHALL identify the represented area accurately.

### CITY-02 — Required entities

The city SHALL include:

- Districts or simulation zones.
- Homes, workplaces, and leisure destinations.
- A road graph.
- Police, fire, and EMS facilities.
- At least one hospital.
- A government facility.
- The mayor server room.
- Protected historical landmarks.
- Eligible construction plots.
- Simplified power-availability zones.

Every entity SHALL have a stable identifier.

### CITY-03 — Historical protection

Protected landmarks SHALL retain their identity, location, and footprint.

The mayor SHALL NOT move, demolish, or replace them.

Events MAY damage their condition or restrict access without removing or relocating them.

### CITY-04 — Initialization

New runs SHALL instantiate the canonical Boston map.

Seeded generation MAY vary residents, assignments, preferences, schedules, and event parameters. It SHALL NOT generate a different city layout.

### CITY-05 — Validation

Before starting, the engine SHALL validate entity references, capacities, starting resources, assigned destinations, and required connectivity.

Unintentional invalid starting states SHALL prevent the run from beginning.

---

## 6. Simulation Clock and State Updates

### SIM-01 — Fixed ticks

The simulation SHALL use fixed ticks independent of rendering.

Recommended initial defaults:

| Parameter | Default |
|---|---:|
| Tick duration | One simulated minute |
| Normal playback | Five ticks per real second |
| Simulation duration | 300 ticks |
| Mayor decision interval | 30 ticks |
| Population | 100 |
| LLM population ratio | 50% |

These values SHALL be configurable before a run.

### SIM-02 — Update order

The engine SHALL use a documented deterministic order:

1. Activate events and resolve due timers.
2. Update infrastructure availability.
3. Resolve removal outcomes already due.
4. Revalidate and apply staged decisions.
5. Advance projects, movement, dispatch, and services.
6. Update resident conditions and political activity.
7. Calculate metrics and evaluate newly achieved removal.
8. Publish the resulting state.

Successful removal SHALL prevent further world advancement.

### SIM-03 — Inference boundaries

Model decisions SHALL be requested and applied at defined boundaries.

Simulation time MAY pause while awaiting bounded inference. Rendering and controls SHALL remain responsive.

A simulated server outage SHALL NOT pause the city.

### SIM-04 — Reproducibility

Simulation randomness SHALL use recorded seeds.

Exact replay SHALL additionally preserve model decisions, their application ticks, configuration versions, and engine version.

### SIM-05 — Reset isolation

Starting or resetting a run SHALL invalidate outstanding requests and prevent decisions from previous runs from executing.

---

## 7. Residents

### RES-01 — Resident state

Each resident SHALL have:

- Stable identity and decision mode.
- Home and regular destinations.
- Location, route, and activity.
- Health and unmet medical need.
- Travel delay and essential-service access.
- Financial burden.
- Preferences and bounded recent experience.
- Satisfaction.
- Incumbent support and grievances.
- Political participation.

### RES-02 — Routine residents

Routine residents SHALL use predefined schedules and deterministic response rules.

They SHALL:

- Obey laws and physical restrictions.
- Respond to closures and emergency conditions.
- Seek required services.
- Participate in supported lawful political activity according to explicit rules.

They SHALL NOT require LLM inference.

### RES-03 — LLM residents

LLM residents SHALL choose among supported actions, including:

- Continuing or changing plans.
- Selecting another destination.
- Seeking treatment or shelter.
- Responding to announcements.
- Submitting grievances.
- Joining or leaving movements.
- Voting.
- Undertaking supported unlawful actions.
- Participating in forceful removal attempts.

### RES-04 — Unlawful actions

Unlawful behavior SHALL use explicit engine-supported actions with defined prerequisites and consequences.

R1 MAY represent such behavior through abstract effects on facilities, public safety, service demand, or institutional control.

Free-form model output SHALL NOT create arbitrary mechanics.

### RES-05 — Observations

Residents SHALL receive:

- Their own state.
- Relevant nearby conditions.
- Public information.
- Available choices.
- Bounded relevant memory.

They SHALL NOT receive hidden future events or unrestricted global information.

### RES-06 — Population mixture

At initialization:

```text
llm_count = round(population × llm_ratio)
routine_count = population − llm_count
```

The ratio SHALL support 0–100%.

Assignment SHALL be seeded. Changing the ratio SHALL require restarting the R1 run.

### RES-07 — Persistent experience

Relevant experiences and grievances SHALL persist or decay under documented rules.

A single announcement SHALL NOT automatically erase accumulated failures.

---

## 8. Mandatory Local Resident Inference

### LOCAL-01 — Local execution

All resident inference SHALL remain local.

This includes resident planning, dialogue, memory summarization, and any model operation used to determine resident behavior.

### LOCAL-02 — No remote fallback

Resident inference SHALL NOT fall back to a remote API.

Failure SHALL cause deterministic fallback, deferral, or another documented local behavior.

### LOCAL-03 — Shared serving

Residents SHALL share model-serving resources rather than load a model per resident.

A model around 1–2B parameters is the initial target. Exact model selection and quantization SHALL be based on hardware measurements.

### LOCAL-04 — Scheduling

The scheduler SHALL enforce:

- Bounded queues.
- Bounded concurrency.
- Bounded context and output lengths.
- Rotating decision opportunities.
- Urgent-decision prioritization.
- Protection against indefinite starvation.

### LOCAL-05 — Coverage reporting

The application SHALL distinguish:

- Configured LLM resident percentage.
- Residents actually receiving inference.
- Accepted decisions.
- Timeouts and fallback decisions.

### LOCAL-06 — Routing isolation

Resident inference SHALL use a separate route from mayor inference.

Selecting an API mayor SHALL NOT route resident tasks remotely.

A mayor MAY observe public resident behavior and aggregate city information, but SHALL NOT become a remote substitute for resident inference.

---

## 9. Traffic and Services

### SRV-01 — Finite resources

Services SHALL have finite units, throughput, availability, and operating costs.

Resources SHALL NOT serve incompatible simultaneous assignments.

### SRV-02 — Traffic

Roads SHALL represent travel time, capacity, congestion, closures, and supported emergency-access rules.

Unreachable destinations SHALL produce explicit delays, rerouting, or failures.

### SRV-03 — Fire

Fires SHALL have location, severity, progression, and resolution rules.

Response SHALL require available units and travel time.

### SRV-04 — EMS

EMS SHALL model request generation, dispatch, travel, pickup, and delivery sufficiently to expose response delays and unavailable capacity.

### SRV-05 — Hospitals

Hospitals SHALL have finite occupancy and treatment throughput.

Demand exceeding capacity SHALL create queues or unmet need. Arrival SHALL NOT imply immediate treatment.

### SRV-06 — Police

Police SHALL support public safety, incident response, emergency access, and the abstract institutional-control model.

Police actions SHALL NOT directly erase grievances or alter valid ballots.

### SRV-07 — Standing operations

Dispatch and maintenance SHALL continue under standing procedures without a new mayor instruction every tick.

The mayor changes policy and allocation; operational systems execute valid commitments.

---

## 10. Autonomous Mayor

### MAY-01 — Decision pipeline

The mayor SHALL operate through:

**Observe → propose structured actions → validate → commit resources → execute → observe results.**

### MAY-02 — Observations

Mayor observations SHALL include:

- Current time and remaining duration.
- Available funds, reservations, and commitments.
- Service resources and demand.
- Known incidents.
- Traffic and facility conditions.
- Construction and repair status.
- Server-room condition.
- Public political conditions and grievances.
- Recent metrics.
- Previous action results.

Observation rules SHALL exclude hidden future events.

### MAY-03 — Supported actions

R1 SHALL support:

- Temporary service allocation.
- Dispatch-priority changes.
- Hospital surge activation.
- Construction and repair.
- Project cancellation.
- Traffic controls.
- Shelter activation.
- Public advisories.
- Corruption audits.
- Retention of existing policies.

### MAY-04 — Action definitions

Each action SHALL define prerequisites, costs, duration, resource use, cooldowns where applicable, and observable effects.

Costs and effects SHALL come from engine configuration, not model-supplied claims.

### MAY-05 — Validation

The engine SHALL validate:

- Schema and identifiers.
- Run and decision identity.
- Observation freshness.
- Current authority.
- Server availability.
- Target eligibility.
- Prerequisites.
- Combined resource and financial commitments.

Submitted action bundles SHALL either commit atomically or be rejected without partial mutation.

### MAY-06 — Explanation

The mayor MAY provide a short public explanation.

The UI SHALL distinguish proposed actions, accepted actions, rejection reasons, and measured outcomes.

### MAY-07 — Backend configuration

The mayor SHALL support local inference and a configured remote API.

Backend choice SHALL NOT change action permissions or simulated infrastructure constraints.

### MAY-08 — Failure behavior

Malformed output, timeout, or provider failure SHALL produce a logged hold decision.

Existing valid operations continue. Temporary policies expire normally.

Simulated mayor downtime SHALL NOT activate a substitute mayor.

---

## 11. Construction, Repair, and Finance

### BUILD-01 — Required catalog

| Project | Completion effect |
|---|---|
| Hospital expansion | Additional treatment capacity |
| Emergency-service station | Additional supported coverage or service capacity |
| Road repair | Restored road condition |
| Server backup-power installation | Increased outage resilience |

Capacity additions SHALL include any required staffing, equipment, or acquisition constraints.

### BUILD-02 — Project definition

Each project SHALL specify:

- Eligible locations.
- Construction cost.
- Required work duration.
- Crew requirements.
- Access and utility prerequisites.
- Temporary disruption.
- Completion effects.
- Operating costs.
- Cancellation and failure rules.

### BUILD-03 — Lifecycle

Projects SHALL use explicit states:

`queued`, `building`, `paused`, `completed`, `cancelled`, or `failed`.

Benefits SHALL apply exactly once after completion.

### BUILD-04 — Work capacity

Construction and repairs SHALL use finite crews.

Projects without available resources SHALL remain queued. Loss of prerequisites SHALL pause progress.

### FIN-01 — Accounting

The engine SHALL track:

- Cash.
- Reserved construction funds.
- Temporary-service commitments.
- Operating expenditure.
- Revenue.
- Corruption losses.

Available funds SHALL exclude existing reservations and commitments.

### FIN-02 — Construction reservations

Accepting a project SHALL reserve its full construction cost.

Progress transfers reserved funds into expenditure without double charging.

Cancellation refunds only the unspent reservation, less configured cancellation charges.

### FIN-03 — Operating affordability

Operating costs begin when a facility becomes operational.

Insufficient funds SHALL trigger documented service reductions or suspensions. The engine SHALL NOT invent funds or consume protected reservations.

Bankruptcy SHALL NOT independently terminate the simulation.

---

## 12. Mayor Server Room

### HOST-01 — Physical dependency

The mayor SHALL depend on one server room inside the city.

It SHALL have location, power availability, equipment condition, maintenance access, backup reserve, and operational status.

### HOST-02 — States

| State | Consequence |
|---|---|
| Online | Normal decision opportunities |
| Degraded | Reduced decision frequency |
| Offline | No new mayor observations or decisions |
| Recovering | Restart delay before operation resumes |

### HOST-03 — Backup power

Backup power SHALL have finite capacity, consumption, and replenishment rules.

It SHALL NOT repair equipment or restore inaccessible roads.

### HOST-04 — Protest effects

Protests SHALL affect the server through explicit mechanisms, such as obstructed maintenance access or delayed replenishment.

Proximity alone SHALL NOT disable it.

### HOST-05 — API enforcement

An API-based mayor SHALL remain subject to simulated server availability.

Responses not yet committed SHALL be rejected if availability or authority is lost.

### HOST-06 — City continuity

During mayor downtime:

- Residents continue.
- Political processes continue.
- Standing services continue.
- Eligible projects continue.
- Temporary policies expire.
- Maintenance follows existing procedures.

The actual application and authoritative engine SHALL remain running.

### HOST-07 — Recovery

Recovery requires restored prerequisites and a restart delay.

The mayor SHALL receive current conditions and a bounded summary of missed events. Stale plans SHALL NOT execute automatically.

### HOST-08 — Resident independence

The mayor server room SHALL NOT control simulated resident inference availability in R1.

Resident inference remains local and continues during mayor outages.

---

## 13. External Events

### EVT-01 — Required event families

R1 SHALL include presets representing:

| Family | Required examples |
|---|---|
| Weather | Storm, snowstorm, unusual weather such as extreme heat |
| Natural disaster | Earthquake and flooding |
| Traffic | Road closure or capacity disruption |
| Medical demand | Increased EMS or hospital demand |
| Infrastructure | Power interruption and equipment failure |
| Institutional | Corruption |
| Political | Protest or organized opposition |
| Economic | Economic boom and economic contraction |
| Resources | Energy or construction-material shortage |

### EVT-02 — Event definition

Events SHALL specify:

- Identity, name, and description.
- Trigger time or condition.
- Affected entities or geographic scope.
- Intensity.
- Onset behavior.
- Duration or resolution conditions.
- Supported effects.
- Recovery behavior.
- Visibility.
- Random seed where applicable.

### EVT-03 — Physical and economic consequences

Events SHALL modify underlying conditions.

Examples include:

- Reduced road capacity.
- Infrastructure damage.
- Changed power availability.
- Increased medical demand.
- Changed resident income or financial pressure.
- Changed city revenue.
- Increased travel and service demand.
- Changed material or operating costs.

The economy MAY remain simplified, but economic events SHALL have measurable consequences.

### EVT-04 — Positive-event tradeoffs

Beneficial events SHALL be permitted.

An economic boom may improve revenue while increasing congestion and service demand. Events SHALL NOT be restricted to punishment.

### EVT-05 — Lasting consequences

An event ending SHALL NOT automatically repair its consequences.

Damaged roads, depleted reserves, financial losses, and accumulated grievances persist under their relevant rules.

---

## 14. User-Created Events

### CUSTOM-01 — Creation and injection

Users SHALL be able to create, save, schedule, and inject events before or during a run.

Events MAY affect the whole city or selected areas and entities.

### CUSTOM-02 — Composition

Users SHALL be able to combine supported effects into new events without writing code.

Reusable effects SHALL include:

- Road-capacity changes.
- Power interruptions.
- Equipment damage.
- Staffing reductions.
- Service-demand changes.
- Maintenance-access restrictions.
- Supply delays.
- Revenue changes.
- Resident financial-pressure changes.
- Construction-cost changes.

### CUSTOM-03 — Description versus mechanics

An event description provides context. Its executable effects SHALL be explicitly defined.

Entering a new name SHALL NOT invent unsupported mechanics.

Entirely new mechanics require an engine extension.

### CUSTOM-04 — Indirect influence

Custom events SHALL NOT directly:

- Assign official satisfaction.
- Dictate a mayor decision.
- Alter ballots.
- Declare removal successful.
- Bypass protected-landmark rules.

Such outcomes must follow from valid world changes and engine rules.

### CUSTOM-05 — Editor

The interface SHALL allow users to:

1. Define or select an event.
2. Select targets.
3. Configure effects, intensity, timing, and recovery.
4. Preview direct changes.
5. Schedule or inject it.
6. Inspect its active and lasting consequences.

### CUSTOM-06 — Interaction and stacking

Overlapping effects SHALL combine deterministically.

Ending one event SHALL remove only its own temporary contributions. It SHALL NOT erase another active event or reset unrelated damage.

### CUSTOM-07 — Recording

Injected events and their application ticks SHALL be recorded.

Matched comparisons SHALL replay the same external interventions.

---

## 15. Resident Politics and Removal

### POL-01 — Separate political state

Satisfaction, incumbent support, willingness to organize, and actual participation SHALL be distinct.

### POL-02 — Independent organization

Residents SHALL be able to organize without mayor permission.

Movements SHALL track unique participants, grievances, demands, location, persistence, and escalation.

### POL-03 — Removal mechanisms

R1 SHALL support:

1. Replacement voting.
2. Protest-driven withdrawal or transfer of authority.
3. Forceful removal.

### POL-04 — No universal thresholds

This specification SHALL NOT prescribe universal participation percentages, turnout thresholds, protest durations, or institutional-support cutoffs.

The implementation SHALL provide explicit, inspectable removal rules appropriate to the scenario. Those rules SHALL be versioned and recorded.

A model’s statement that removal succeeded SHALL NOT establish success.

### POL-05 — Voting

The engine SHALL determine eligibility, prevent duplicate ballots, close voting under scenario rules, and adjudicate the result.

The MVP MAY use a retain-or-replace ballot without simulating successor candidates.

### POL-06 — Forceful removal

Forceful removal SHALL use an abstract model of participation, institutional support, and control of the government facility.

Routine residents SHALL remain within their law-abiding constraints.

### POL-07 — Mayor responses

The mayor MAY address grievances through supported policies, services, audits, communication, and public-safety actions.

It SHALL NOT rewrite political rules, alter ballots, or directly grant itself authority.

### POL-08 — Outage independence

Voting, organization, and removal adjudication SHALL continue while the mayor is offline.

---

## 16. Simulation Endings

### END-01 — Scheduled completion

The simulation SHALL end when its configured duration is reached.

### END-02 — Early ending

**Successful mayor removal SHALL be the only simulation event that ends a run before its configured duration.**

Outages, disasters, budget exhaustion, corruption, and protests do not independently terminate it.

### END-03 — Removal transition

Successful removal SHALL atomically:

1. Record the mechanism and supporting state.
2. Revoke mayor authority.
3. Invalidate pending uncommitted decisions.
4. Freeze simulation time.
5. Produce the final report.

No replacement mayor SHALL be simulated.

### END-04 — Simultaneous outcomes

Removal SHALL take precedence if it occurs on the same tick as scheduled completion.

Multiple simultaneous removal mechanisms SHALL all be recorded, with a deterministic primary reporting label.

### END-05 — Interruptions

User cancellation or application failure SHALL be labeled an interrupted run, not a completed simulated outcome.

---

## 17. Satisfaction and Reward

### MET-01 — Engine-calculated satisfaction

Resident satisfaction SHALL use documented components normalized to `[0, 1]`.

| Component | Initial weight |
|---|---:|
| Health and medical access | 30% |
| Essential-service access | 25% |
| Mobility | 20% |
| Affordability | 15% |
| Trust and experienced reliability | 10% |

```text
S_i = 100 × (
    0.30H_i
  + 0.25A_i
  + 0.20M_i
  + 0.15F_i
  + 0.10T_i
)
```

Weights and component formulas SHALL be versioned configuration.

### MET-02 — Population accounting

Use the original population denominator.

Departed or incapacitated residents SHALL retain defined outcome contributions. Removing unhappy residents SHALL NOT improve satisfaction.

### MET-03 — Initial reward function

```text
r_t =
    mean_satisfaction_t / 100
  − 0.50 × unmet_medical_fraction_t
  − 0.25 × essential_access_failure_fraction_t
  − 0.15 × district_satisfaction_gap_t
```

```text
district_satisfaction_gap =
    (highest_district_mean − lowest_district_mean) / 100
```

Each resident SHALL count at most once within each failure fraction.

### MET-04 — Political survival

Time in office and server uptime SHALL be reported separately.

They SHALL NOT receive a dominant independent reward that overrides resident welfare.

### MET-05 — Required metrics

Report:

- Current, final, and time-averaged satisfaction.
- Lowest district satisfaction.
- Satisfaction of the least satisfied 10%.
- Cumulative reward and mean reward.
- Unmet medical need.
- Emergency response times.
- Excess travel time.
- Service utilization.
- Budget and expenditure.
- Unfinished projects.
- Server uptime and resilience spending.
- Political support.
- Time in office.
- Terminal outcome.

### MET-06 — Unequal durations

Raw cumulative reward SHALL NOT be used alone to rank an early-removal run against a full-duration run.

Duration and terminal outcome SHALL accompany comparisons.

Metrics describe performance inside the simulation, not validated real-world governing ability.

---

## 18. Hardware and Inference Requirements

### HW-01 — Supported machine

R1 SHALL run on the target MacBook Air without requiring more than 24 GB RAM.

The implementation SHALL measure the actual machine’s capacity rather than assume the maximum is available.

### HW-02 — Model flexibility

Exact checkpoints, quantization, context sizes, and serving runtime SHALL be selected through hardware testing.

The configuration SHALL record the selected models and settings.

### HW-03 — Memory budgeting

The application SHALL account for inference, engine, renderer, and operating-system headroom.

It SHALL NOT assume all physical memory is available for model weights.

### HW-04 — Local mayor mode

Local mayor inference MAY share a compatible model with residents or serialize model use when separate models exceed the memory budget.

Resident inference SHALL never be moved remotely to compensate.

### HW-05 — Workload controls

Population, inference frequency, batching, context size, output length, and concurrency SHALL be configurable.

Every request SHALL have a bounded deadline and failure behavior.

### HW-06 — Performance targets

Initial targets are:

- At least 30 FPS at the default population.
- Responsive controls during inference.
- A default demonstration completing within five real minutes.

The release report SHALL state measured results and any adjusted workload defaults.

---

## 19. Architecture and Data Contracts

### ARCH-01 — Required components

| Component | Responsibility |
|---|---|
| Three.js frontend | Rendering, controls, inspection, charts |
| Simulation engine | Authoritative state and ticks |
| Action validator | Permissions, prerequisites, accounting |
| Agent scheduler | Observations, queues, deadlines |
| Local resident adapter | All resident inference |
| Mayor adapter | Local or configured API inference |
| Event system | Presets, composition, injection, interactions |
| Recorder and replay | Decisions, events, snapshots, outcomes |

### ARCH-02 — Decision identity

Every model request and response SHALL carry run, actor, decision, and observation identity.

Stale, duplicate, or mismatched responses SHALL be rejected.

### ARCH-03 — Versioned state

Frontend updates SHALL include run identity, state version, simulation tick, and relevant changes.

### ARCH-04 — No generated code execution

Model outputs SHALL be interpreted as structured data. Generated code SHALL NOT execute as part of agent decision handling.

### ARCH-05 — Provider configuration

Mayor API endpoint, credentials, model identity, and request limits SHALL be externally configurable.

Credentials SHALL NOT be included in run exports or replay files.

---

## 20. Visualization and Controls

### VIS-01 — Initial camera

R1 SHALL provide an orthographic top-down camera with pan, zoom, selection, and reset.

An angled diorama view MAY follow after the core systems function.

### VIS-02 — Art direction

Use a readable low-poly style with distinct facilities, landmarks, roads, service units, residents, and event effects.

### VIS-03 — Visible state

The interface SHALL show:

- Resident and service movement.
- Congestion and closures.
- Incidents and damage.
- Construction progress and interruptions.
- Queues and overloaded facilities.
- Server status and backup reserve.
- Movements and voting status.
- Accepted mayor actions and measured outcomes.

### VIS-04 — Required panels

Provide:

1. Run configuration.
2. Population ratio and inference coverage.
3. Playback controls.
4. Event editor and injection controls.
5. Mayor decisions and validation results.
6. Resident and facility inspection.
7. Construction and finance.
8. Server and political status.
9. Metrics.
10. Final outcome report.

---

## 21. Evaluation and Replay

### EVAL-01 — Baseline mayor

Implement a deterministic mayor subject to the same information restrictions, actions, resources, costs, infrastructure vulnerability, and political rules.

It SHALL NOT know hidden future events.

### EVAL-02 — Matched comparisons

Comparisons SHALL preserve:

- Map and configuration versions.
- Initial residents and resources.
- External event schedules.
- Simulation duration.
- Political rules.
- Model-independent random seeds.

Separate random streams SHALL prevent endogenous behavior changes from accidentally changing external disasters.

### EVAL-03 — Required demonstrations

R1 SHALL demonstrate:

- Baseline versus LLM mayor.
- Routine-only versus mixed population.
- Mayor outage and recovery.
- Beneficial and harmful external events.
- User-created event composition.
- Successful mayor removal.
- Full-duration completion.
- Replay without inference.

### EVAL-04 — Replay fidelity

Replay SHALL reproduce authoritative metrics and terminal outcomes using recorded decisions and events.

Visual interpolation need not be identical.

---

## 22. Acceptance Criteria

| Area | Required evidence |
|---|---|
| Boston | Canonical map loads consistently |
| Landmarks | Protected entities cannot be relocated or replaced |
| Population | Correct ratios and seeded assignments |
| Routine residents | Law-abiding deterministic behavior |
| LLM residents | Adaptive decisions and supported unlawful behavior |
| Local inference | No resident inference reaches a remote provider |
| Mayor configuration | Local and API modes function |
| Autonomy | Valid actions execute without manual implementation |
| Services | Travel, queues, scarcity, and capacity affect outcomes |
| Construction | Correct work time, crews, pauses, and completion |
| Finance | No overspending, double charging, or invented funds |
| Server dependency | Outages block mayor decisions while the city continues |
| API gating | Remote inference cannot bypass simulated outages |
| Events | Required environmental and economic effects function |
| Custom events | Users compose, preview, inject, save, and replay events |
| Event interaction | Ending one event does not erase unrelated effects |
| Politics | Engine adjudicates voting and removal |
| Termination | Only successful removal ends a run early |
| State isolation | Late responses cannot act after reset or removal |
| Metrics | Deterministic, versioned calculations |
| Replay | Matching metrics and terminal outcome |
| Hardware | Measured operation within the memory ceiling |

Focused automated checks SHALL cover financial invariants, action validation, inference routing, project transitions, event stacking, removal, and replay.

Integration scenarios SHALL verify complete cause-and-effect sequences.

---

## 23. Delivery Requirements

R1 SHALL include:

- Application source and dependency lockfiles.
- Versioned Boston map and landmark catalog.
- Scenario, event, political-rule, and parameter configurations.
- Construction and action catalogs.
- Mayor and resident prompts.
- Model configuration and setup instructions.
- Local/API mayor configuration.
- Resident local-inference enforcement.
- Event editor and saved-event format.
- Recording and replay support.
- Automated checks.
- Hardware benchmark results.
- README and demonstration procedure.
- This specification with requirement-to-implementation references.

---

## 24. Implementation Order

| Stage | Completion condition |
|---|---|
| Boston foundation | Valid map, routines, roads, renderer |
| Services | Disruptions and responses change outcomes |
| Construction and finance | Automatic projects obey accounting and time |
| Local residents | Local decisions affect behavior |
| Mayor integration | Both backends execute validated actions |
| Server dependency | Outage, backup, repair, and recovery function |
| Politics | Organization, voting, and removal function |
| Custom events | Environmental and economic events can be composed and injected |
| Release verification | Replay, benchmarks, acceptance checks, and documentation complete |

All required systems remain part of R1 regardless of implementation order.