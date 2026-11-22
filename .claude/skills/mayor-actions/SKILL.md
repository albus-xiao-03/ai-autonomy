---
name: mayor-actions
description: Define or change what the AI mayor can do, its state summary, strict JSON output, validation, fallback, and logging. Use when editing mayor prompts, actions, backends, or the decision loop.
---

# Mayor actions and contract

Where it lives: the game builds the prompt and allowed orders in `game/sim.js` `decide`; the engine decides in `aiautonomy/engines/mayor/backends.py` via `POST /api/brain/mayor`.

Backends (Events tab "Mayor brain"): `local` = `qwen3:8b` via Ollama (default), `baseline` = rules, `api` = Anthropic (only when the engine runs with `AIA_ALLOW_PAID_API=1` and `ANTHROPIC_API_KEY`).

Output: strict JSON `{"order": <one allowed order>, "statement": "short public announcement"}`.

Orders implemented now: `dispatch`, `outreach`, `patrol`, and for incidents `mediate`, `repair`, `evacuate`, `monitor` (the game sends only the ones valid right now). The fuller target list is in `SPEC.md` Section 8; keep both in sync when adding one.

Prompt state: minute, district authority, satisfaction, crimes, police patrol, autonomous resident count, incident, response access, recent outcomes with score before/after.

Rules:
1. The engine validates the order against the allowed list. On invalid output or model error it returns the game's fallback with `fallback_used: true`.
2. Districts can refuse orders; record accepted or refused.
3. If the engine is unreachable, the game uses the civic controller and **labels it on screen** ("engine offline").
4. Never block the render loop on an LLM call (fetch is async; the sim clock holds while the mayor decides).
5. Satisfaction is logged before and one hour after each action (`scoreChecks` in `game/sim.js`, `/api/brain/mayor/outcome`).
6. Add a test in `tests/engines/unit/test_brain.py` for any new backend behaviour.
