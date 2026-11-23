# Architecture

Spec ARCH-01, docs/engine-plan.md §3. The Python engine lives in `aiautonomy/engines/`; the
TypeScript frontend lives in `aiautonomy/interfaces/`.

## Components

| Spec component | Package | State in M0 |
|---|---|---|
| Three.js frontend | `aiautonomy/interfaces/` | Shell, playback panel |
| Simulation engine | `aiautonomy.engines.sim` (clock, phases, driver, termination), `aiautonomy.engines.world` (World state, toy world, Boston map catalog, validation, locks and store), `aiautonomy.engines.traffic`, `aiautonomy.engines.services`, `aiautonomy.engines.build`, `aiautonomy.engines.finance`, `aiautonomy.engines.residents`, `aiautonomy.engines.politics`, `aiautonomy.engines.host`, `aiautonomy.engines.metrics` | Tick pipeline, toy world and toy metrics |
| Action validator | `aiautonomy.engines.mayor` (validator, commit) | Placeholder (M5) |
| Agent scheduler | `aiautonomy.engines.agents` (scheduler) | Inference-client registry used by replay |
| Local resident adapter | `aiautonomy.engines.agents` (resident adapter) | Placeholder (M4) |
| Mayor adapter | `aiautonomy.engines.mayor` (backends) | Placeholder (M5) |
| Event system | `aiautonomy.engines.events` | Placeholder (M2, M8) |
| Recorder and replay | `aiautonomy.engines.record` | Recorder, startup relabel, replay |

Supporting packages: `aiautonomy.engines.core` (ids, keyed RNG, canonical JSON and hashes,
integer money, data-file loader, version stamp; imports no other engine package),
`aiautonomy.engines.contract` (pydantic models of the hybrid engine–game contract,
docs/contract.md; imports only `core`), `aiautonomy.engines.hybrid` (hybrid Boston runs driven by
the game: run store, tick pipeline, engine state, seeded resident modes),
`aiautonomy.engines.api` (FastAPI app, WebSocket session, protocol models and schema export),
`aiautonomy.engines.bench` (M4, M9), `aiautonomy.engines.cli` (`aia`) and
`aiautonomy.engines.trace` (`aia trace`).

Import layering, enforced by import-linter: `cli` → `api` → `record` → `hybrid` → `sim` →
`world` → `contract` → `core`.

## Runtime topology

```text
Browser (Vite/TS app, Three.js)
   |  WebSocket /ws and REST /api on 127.0.0.1:8787 (snapshots, deltas, commands)
Engine server: FastAPI + uvicorn, one asyncio loop
   |-- EngineSession: current Run + Driver, per-client send queues, immediate acks
   |-- Driver: wall-clock pacing (1x = 5 ticks/s, 2x, 4x, max), pause/step/reset/cancel,
   |           inference waits before phase 4 (artificial in M0)
   |-- Run: frozen RunConfig, KeyedRng, World, phases 1-8
   |-- Recorder -> runs/<run_id>/ (manifest, ticks.jsonl, logs, snapshots, final report)
   `-- (M4+) agent scheduler -> Ollama at 127.0.0.1:11434; (M5+) mayor backends
```

A tick runs synchronously and stays well under 20 ms; pacing sleeps and inference waits are
awaits, so command handling never blocks. `aia run --headless` runs the same `Run` at maximum
speed without the server; `aia replay` re-runs it without any inference client.

## Protocol

The pydantic models in `aiautonomy.engines.api.protocol` are the single source of truth. Their
JSON Schema, `aiautonomy/engines/api/protocol.schema.json`, is exported with
`uv run python -m aiautonomy.engines.api.export_schema` (`--check` detects drift), and the
frontend generates its TypeScript types from it.

## Configuration

`config/engine.yaml` (SIM-01 defaults) → `data/scenarios/<id>.v<N>.yaml` → run overrides
(`configure` command or CLI flags) → frozen `RunConfig`, recorded in the manifest with every
data file's id, version and sha256.
