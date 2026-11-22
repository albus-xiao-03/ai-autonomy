# AGENTS.md

Project: **Boston AI Mayor** (three.js browser game). A local LLM mayor (qwen3:8b via Ollama) runs a Cities: Skylines-style Boston while the player builds it and triggers protests and disasters. A satisfaction score shows how well the mayor copes.

## Always do
1. Read `SPEC.md` before any work. Section 2 (hard rules) is non-negotiable.
2. Git: work on branch `utkarsh` only. Never push to `main`. Small commits; message says what changed and how it was verified.
3. One feature per task. Plan in a few lines, implement, then verify.
4. Never say "done" unless you ran the game and checked it. Follow `.claude/skills/verify-game/SKILL.md` (tools without skill support: open that file and follow it).
5. After a verified change, update the Status table in `SPEC.md` Section 12. Anything not re-tested stays "unverified".
6. Keep answers short. Do not paste or dump big files; search and open only what you need.

## Never do
- Remove or hide a tool or the building palette when changing another tool.
- Add pre-squared blocks or fixed road grids. The player places roads and buildings freely.
- Use a cloud LLM for the mayor. Mayor = local Ollama only; if unavailable, show the labeled fallback.
- Leave extra dev servers running. The game runs on port 8712; close temporary ports.
- Expand scope. If a request conflicts with SPEC.md, say so and ask.

## Commands
- Install: no package installation/build step. Python 3 serves the static `dist/` app; Three.js and polygon-clipping are vendored.
- Run game: `python3 -m http.server 8712 --bind 127.0.0.1 --directory dist` from the repository root (serves on http://127.0.0.1:8712). If already running, reuse that server.
- Tests: `node tests/highway-elevation.cjs` (Node 18+, built-in modules only) verifies the real I-93 corridor, imported heights, all four ramp-to-player-street connections, every level boundary, and player bridge/tunnel profiles. On this machine Node is `/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node`. Syntax check: `for file in dist/*.js; do node --check "$file" || exit; done`. Broader road/incident audit harnesses remain temporary in `/tmp`. Browser checks follow the supplied `/Users/utkarsh/Downloads/repo-kit/.claude/skills/verify-game/SKILL.md`.
- Ollama: `ollama serve` (default http://localhost:11434), model `qwen3:8b`

## Code map
- Game entry: `dist/index.html` loads scripts; `dist/app.js` initializes state/UI, `start`, `render`, `frame`; `dist/world.js` `CityWorld.mount` renders Three.js.
- Roads / junctions / traffic: `dist/planner.js`: `CityPlan.roadPath`, `buildGraph`, `route`, `roadSurfaces`, `controlPlacement`, `waitAt`, `heightAt`; `dist/world.js`: `drawRoads`, `drawControls`, `roadPreview`, input handlers; `dist/sim.js`: `travelTimeline`, `timedPosition`, `lanePosition`. Fixed source geometry: `dist/highway-data.js`.
- Buildings / palette: `dist/app.js`: `stock`, `drawPalette`, `choose`, `place`, `save`, Undo/startup load; `dist/planner.js`: `place`, `buildingError`, `access`, `remove`, `seedArcade`; `dist/world.js`: `drawBuilding`. Land/shoreline: `dist/geography.js`; fixed landmarks: `dist/planner.js` `landmarks`.
- Residents: `dist/sim.js`: `start`, `createHousehold`, `residentTick`, `addTrip`, `refreshNetwork`. Routine residents only; no autonomous resident model or mix slider.
- Mayor (prompt, parser, fallback): `dist/sim.js`: `decide`, `dispatch`, `outreach`, `record`; `dist/app.js`: `start` supplies local qwen3:8b endpoint, `history`/`render` display decisions. `decide` still allows generic nonlocal endpoints, pauses simulation while pending, and omits satisfaction from the prompt.
- Events: `dist/incidents.js`: `CityIncidents.types`, `create`, `spawn`, `tick`, `respond`, `updateNetwork`; `dist/planner.js`: `setClosures`, `roadBlocked`; `dist/world.js`: `drawIncidents`; `dist/app.js` Events tab handlers. Noon corruption remains in `dist/sim.js` `tick`. The previously audited incident implementation was checkpointed in commit `0b9fc39`.
- Satisfaction score + HUD: `dist/sim.js` `getState` computes one overall score; `dist/app.js` `render` writes `#happy` in `dist/index.html`. District scores, score graph, mayor prompt feedback, and before/after action score logs are missing.

## Style
- Low-poly diorama look, flat shading, simple low-poly cars.
- Keep 30+ FPS. LLM calls must never block the render loop.

## Playbooks (skills)
- `.claude/skills/spec-audit/`: audit repo against SPEC.md
- `.claude/skills/verify-game/`: run, screenshot, score, fix loop
- `.claude/skills/add-event/`: add a protest/disaster/corruption event
- `.claude/skills/mayor-actions/`: mayor action space, JSON contract, fallback
