# Engine–game contract (hybrid build)

The browser game (`game/`, port 8712) owns Boston's clock, traffic, incidents and physical outcomes. The Python engine (`aia serve`, `http://127.0.0.1:8787`) validates what the game observes and owns:

- 911 dispatch allocations
- mayor decisions and exceptional orders
- the political cost of orders (authority)
- political adjudication
- the disruption schedule of record
- every record needed to replay a run

This file is the contract between the engine owner and the interface agent. It covers these sections:

1. [Ground rules](#1-ground-rules)
2. [Maps](#2-maps)
3. [Launching a run](#3-launching-a-run)
4. [The tick loop](#4-the-tick-loop)
5. [911 dispatch](#5-911-dispatch)
6. [Mayor decisions and orders](#6-mayor-decisions-and-orders)
7. [Residents](#7-residents)
8. [Disruptions](#8-disruptions)
9. [Politics and endings](#9-politics-and-endings)
10. [Reset, cancel and degraded operation](#10-reset-cancel-and-degraded-operation)
11. [Records and replay](#11-records-and-replay)
12. [Legacy routes](#12-legacy-routes-transitional)
13. [Examples, schema and types](#13-examples-schema-and-types)
14. [Changelog](#14-changelog)

- **Source of truth:** the pydantic models in `aiautonomy/engines/contract/`.
- **Generated artifacts:** their JSON Schema, `aiautonomy/engines/api/protocol.schema.json` (root properties such as `tick_observation`), and the TypeScript types, `aiautonomy/interfaces/net/protocol.gen.ts`. `make protocol` regenerates both.
- **Examples:** in `docs/contract/examples/`. Tests keep them valid and complete.
- **Implementation status:** each section lands in the feature commit listed in `docs/engine-plan.md` Appendix B (table B.3). Until a section's row is done, its route answers 404.

Contract version: **1** (`RunHandle.contract_version`).

## 1. Ground rules

- **Encoding.** All bodies are JSON. Unknown fields are rejected (HTTP 422). Coordinates are game metres: x east, z south.
- **Errors.** Every 4xx body is an `ErrorResponse`:

  ```json
  {"error": {"code": "...", "entity_id": null, "message": "..."}, "failures": [...]}
  ```

  - 409 means the request conflicts with the run or map state.
  - 422 means the body is invalid. `failures` lists each problem.
- **Ticks.** One tick is one game minute. The game posts every tick it simulates, in order.
- **When effects apply.** An effect the engine decides while processing tick `t` applies in the game from tick `t + 1` (`effective_tick`). The game must not simulate tick `t + 1` before it has the outcome of tick `t`.
- **Waiting for the engine.** A tick request can block while the engine waits for a mayor decision that is due at that tick (§6). The wait is bounded by `inference.mayor_wait_s` in `config/engine.yaml`.
  - The game keeps rendering and shows "Mayor deciding…" during the wait.
  - Its fetch timeout must exceed `inference.mayor_wait_s` plus 5 s.

## 2. Maps

| Route | Body → answer |
|---|---|
| `GET /api/maps` | → `MapList` (templates and saved maps, with their revisions) |
| `GET /api/maps/{id}/revisions/{n}` | → `MapRevision` (reopen) |
| `POST /api/maps` | `MapCreateRequest` → 201 `MapRevision` (revision 1 of a new map; set `parent` when it derives from another revision) |
| `POST /api/maps/{id}/revisions` | `MapRevisionRequest` → 201 `MapRevision` (next revision; `base` must pin the latest revision, else 409 `base_not_latest`) |
| `POST /api/maps/validate` | `MapValidateRequest` → `MapValidationReport` (dry run) |

**Map documents**

- A map revision is immutable. Its `sha256` is the SHA-256 of the canonical JSON (sorted keys, no whitespace) of its `content`. Every run pins `{id, revision, sha256}`.
- Shipped revisions in `data/maps/` are read-only.
  - `boston-template` r1 is the playable, connected Level 1 template.
  - `boston-variant` r1 is a saved variant: the Cambridge St shortcut is removed and the author has designated a protected landmark.
- User saves go to `maps/` (git-ignored; `AIA_MAPS_DIR` overrides).

**Content**

- `nodes`: points.
- `roads`: segments between node ids (`a` → `b`; one-way roads run `a` → `b`).
- `buildings`: `area: true` marks a fixed famous district cluster.
- `facilities`: PD, FD and medical, each with units.
- `landmarks`.
- `fixed`: read-only game geometry. I-93 is pinned by the SHA-256 of `game/highway-data.js`.
- `mayor_office`.
- Buildings and facilities name the road their driveway joins (`access.road`).

**Validation before a save or a launch (codes in `failures`)**

| Area | Codes |
|---|---|
| References | `duplicate_id`, `unknown_node`, `unknown_access_road`, `unknown_landmark`, `unknown_mayor_office` |
| Roads | `degenerate_road` (endpoints under 10 m apart), `out_of_bounds` (outside the level), `unjoined_crossing` and `unjoined_junction` (the game joins crossings and T junctions itself, so the map must split roads at a shared node) |
| Driveways (as the game's `access`) | `access_too_far` (more than 20 m from the curb), `access_facing_away` (the road is not in front of the entrance) |
| Clearance | `landmark_overlap` (a site or road inside a landmark's grounds; tunnels may pass under with portals 50 m clear), `site_overlap`, `road_crosses_site` |
| Services | `missing_department` (no PD, FD or medical facility with at least one unit), `unreachable_site` (some department cannot reach a site by road), `no_workplace_route` (a home without a road to an office and back) |
| Canonical entities | `canonical_landmark_missing`, `canonical_landmark_changed`, `canonical_landmark_unknown`, `landmark_site_forbidden`, `canonical_area_missing`, `canonical_area_changed`, `canonical_area_unknown`, `fixed_geometry_missing`, `fixed_geometry_changed`, `fixed_geometry_unknown` |
| Facility sites | `facility_landmark_forbidden` (only a medical facility may occupy the hospital site), `facility_landmark_mismatch` |

Land and water are checked by the game. `node tests/boston-maps.cjs` runs the game's own validators on the shipped maps.

**Locks**

- The seven canonical landmarks (City Hall, TD Garden, Mass General, Old North Church, Quincy Market, Boston Common, State House), the fixed district clusters and the I-93 geometry can never change.
- Landmarks with `kind: "user"` are locked by default. The author unlocks one only by listing its id in the save request's `unlock` (a setup action, recorded in the revision's `unlocked`).
- A save is compared with its `base`. The engine rejects every indirect bypass:
  - removing, moving or re-identifying a locked landmark (`locked_landmark_changed`)
  - turning `locked` off inside `content` without `unlock` (`unlock_not_explicit`)
  - trying to unlock a canonical landmark (`canonical_unlock_forbidden`)
  - changing a landmark's kind (`landmark_kind_changed`)
- A derived map (`POST /api/maps` with `parent`) is checked against its parent's locks in the same way.
- Warnings: `unlock_unused` (listed in `unlock` but still locked).
- Store errors: `unknown_map` (404), and `map_exists`, `read_only_map`, `base_not_latest`, `map_sha_mismatch` or `map_corrupt` (all 409).
- No run, disruption or mayor order can edit a map.

## 3. Launching a run

`POST /api/runs` with a `RunLaunchRequest` returns 201 with a `RunHandle`. Each request field:

- `map`: the exact `MapRef` the game loaded. A mismatched sha256 answers 409 `map_sha_mismatch`.
- `population`: residents `0 … population-1`.
- `llm_ratio_bp`: the LLM share in basis points.
- `mayor_backend`: `baseline`, `local` (qwen3:8b via Ollama, the default) or `api` (refused unless the engine runs with `AIA_ALLOW_PAID_API=1` and `ANTHROPIC_API_KEY`).
- `disruptions`: `automatic` (seeded) plus a `scheduled` list.
- `seed` and `duration` are optional. The Boston scenario's defaults are one game day (960 ticks from 06:00).

The `RunHandle` returns:

- `run_id` and `run_epoch`: every later request carries both.
- The frozen `config`.
- The seeded resident modes: `residents.llm_ids`. `llm_count = (population × ratio_bp + 5000) // 10000`; for example, 6 residents at 5000 bp give exactly 3. The LLM set is the residents with the lowest seeded draws, so the sets nest as the ratio grows.
- The engine's `units`.
- Catalog references.
- The scheduled disruptions. Automatic ones stay hidden until they start.

The game must make exactly the residents in `llm_ids` autonomous.

## 4. The tick loop

After simulating tick `t`, the game posts a `TickObservation` to `POST /api/runs/{run_id}/ticks` and receives a `TickOutcome`.

**Observation**

- `run_epoch` and `tick`. `tick` must be the last processed tick + 1. Otherwise the engine answers 409 `tick_gap`, or 409 `stale_epoch` for an old epoch.
- `satisfaction`: the game's 0–100 score after the tick.
- `incidents`: every unresolved incident, plus each incident resolved during this tick with `status: "resolved"`. Report the resolved one once, then drop it. An incident that vanishes without being reported resolved is rejected (`incident_vanished`).
  - A disruption's incident uses the `incident_id` the engine gave it (`inc-…`).
  - Incidents the game creates itself (protests, crimes) use ids starting with `game-`.
- `routes`: the travel time on the **current game road graph** for every pair of an available unit and an unresolved incident. A unit counts as available when the previous outcome's `units` lists it as available, or when a `cleared` event in this same observation frees it. A freed unit can be dispatched again in the same tick.
  - Use `reachable: false` (and `travel_ticks: null`) when no route exists.
  - A missing pair makes that unit ineligible for that incident and is listed in the outcome's `warnings` (`route_not_reported`).
- `unit_events`: physical outcomes this tick.
  - `arrived`: the unit reached its incident.
  - `cleared`: its service there is finished.
  - Events are validated: the unit must be assigned to that incident, and `cleared` needs `arrived` first.
- `out_of_service`: units that cannot respond right now (for example, their station is flooded).
- `residents_joined`: new resident ids, for households created mid-run. Their modes come back in `resident_modes`.
- `resident_moods`: required on politics ticks (every `politics_interval_ticks`, default 15), optional otherwise.

**Retries**

- Reposting the identical observation for an already processed tick returns the stored outcome.
- A different body for that tick answers 409 `tick_conflict`.
- A tick after the run ended answers 409 `run_ended`.

**Outcome** (apply each field from `effective_tick`)

| Field | What the game does |
|---|---|
| `assignments` | Start moving the unit toward the incident. `eta_tick` = effective tick + travel ticks, for display |
| `releases` | The unit is free again (`cleared` or `incident_resolved`) |
| `units` | The engine's full unit view (available / assigned / on_scene / out_of_service) |
| `queue` | Unmet demand with a reason: show it on the incident |
| `orders` | Mayor orders applied or rejected at this tick, with units and authority effect |
| `decisions` | Mayor decision records that changed state this tick (requested, accepted, rejected, hold) |
| `resident_actions` | Resident decisions due now. Apply each action |
| `resident_modes` | Modes of residents who joined this tick |
| `disruptions_started` / `disruptions_ended` | Start or end the physical effects (§8) |
| `authority`, `politics` | Political authority (0–100) and the political status (§9) |
| `mayor` | Backend, controller label, and whether a decision is pending |
| `status`, `removal` | `running`, `completed` (duration reached) or `removed` (removal succeeded). Stop simulating when it is not `running` |
| `state_hash` | The engine state hash for this tick (replay evidence) |
| `warnings` | Non-fatal contract problems, such as missing route pairs |

## 5. 911 dispatch

Dispatch runs every tick without the mayor and without any model call. The engine processes a tick in this order:

1. Releases from `cleared` events and resolved incidents.
2. Mayor orders due at this tick (§6).
3. Routine dispatch:
   - Unresolved incidents are ordered by severity (highest first), then `opened_tick` (oldest first), then id.
   - For each incident, departments are taken in alphabetical order (fire, medical, police). Each department fills up to the incident kind's needs (`GET /api/catalogs/incidents`).
   - Each slot gets the available unit of that department with the shortest reported `travel_ticks`. Ties go to the lower unit id.
   - Unfilled slots are queued with a reason: `no_qualified_unit`, `all_units_busy`, `unreachable`, `route_not_reported` or `out_of_service`.

A unit serves one incident at a time. Routine dispatch never costs authority.

## 6. Mayor decisions and orders

**When the engine asks the mayor**

- Every `mayor_interval` ticks (default 30), and at once when an incident of severity 60 or more appears.
- At most one decision is in flight per run.
- The engine builds the observation itself from what it recorded. It never includes hidden or future disruptions.
- The permitted options are derived from recorded incidents, units and routes:
  - `dispatch(department, incident, n)`: send n available units with a route.
  - `prioritize(department, incident)`: serve this incident first for 30 ticks.
  - `hold`.
- No option can site, move or remove a facility.

**Apply tick**

- `apply_tick = observation_tick + 5`, fixed when the decision is requested.
- At that tick the engine waits for the reply, up to the deadline.
- The reply is revalidated (incident still unresolved, units still available and reachable, mayor online, authority not revoked), then committed atomically or rejected with a reason.
- A reply never applies at its wall-clock arrival.

**Hold**

- The decision is recorded as one `hold` with a `reason`:
  - the model failed or returned malformed output (`provider failure: …`);
  - the deadline passed (`no reply within N s`);
  - a simulated outage. An Outage disruption covering `mayor_office` yields one hold per outage episode: a decision in flight is cancelled and becomes that hold, and opportunities missed during the outage are counted in its `missed_opportunities`.
- A hold the model chooses (`HOLD`) is also recorded as `hold`, with the reason `the mayor chose to hold`. It keeps the backend's controller label.
- Standing dispatch never stops.
- While a decision is in flight, a due opportunity is skipped (at most one decision per run).

**Listings.** `GET /api/runs/{run_id}/decisions` returns every `MayorDecisionRecord` of the run, and `GET /api/runs/{run_id}/orders` every `OrderRecord`.

**Decision log.** Each decision appends lines to `decisions.jsonl`, with the event `requested` (with the observation), `applied` (with the provider's reply), `hold`, `cancelled`, `outcome` (satisfaction after) or `outage_ended`. Orders append `accepted`, `rejected` and `outcome` lines.

**Controller labels** (`ControllerLabel`, display strings in `CONTROLLER_DISPLAY`)

| Label | Shows |
|---|---|
| `baseline` | Rule-based mayor. An explicitly selected baseline keeps this label |
| `local` | Qwen 3 · 8B (local) |
| `api` | Claude API mayor |
| `hold` | Mayor holding · standing dispatch continues (after a failure, a timeout or during an outage) |
| `degraded` | Degraded operation · engine offline (game-only; see §10) |

**Political cost** (rules in `data/politics/rules.v1.yaml`)

- Accepted orders are counted in a rolling window: `window_ticks` 120 and `allowance` 2.
- Each counted order beyond the allowance costs `penalty` 5 authority points.
- These are proposed tuning defaults.
- A retry (same `decision_id`), a multi-unit order, or a repeat of the same order key (`kind:department:incident`) inside the window counts once.

**Measuring the outcome.** The engine binds the satisfaction observed at `observation_tick` and at `apply_tick + outcome_window_ticks` (default 60) to the decision record. It also fills the order's arrival, clear and resolution ticks from later observations.

## 7. Residents

**Modes**

- The engine fixes the modes at launch (`llm_ids`).
- For residents joining mid-run, the engine tops up to the exact target for the new population. Among the new residents it picks those with the lowest seeded draws. Existing residents never change mode.
- Routine residents never reach inference.

**Decisions**

- Post `POST /api/runs/{run_id}/residents` right after a tick, with that tick in the body. It takes a `ResidentDecisionRequest` (LLM residents only, at most `resident_batch_max`) and answers 202 with a `ResidentDecisionAccepted` holding one ticket per resident, each with `apply_tick = tick + 2`.
- The actions arrive in the outcome of that tick (`resident_actions`). Apply them then.
- Refusals:

  | Status | Codes |
  |---|---|
  | 409 | `tick_mismatch` (the body names an older tick), `queue_full` (a batch is in flight), `stale_epoch`, `run_ended` |
  | 422 | `not_llm_resident` (routine residents never reach inference), `unknown_resident`, `duplicate_resident`, `batch_too_large` |

- The offered actions follow the public political context: `sign_petition` only while a petition collects, and votes only while a vote is open by the apply tick.
- The resident model sees its own observation plus public context: incidents, available police, the petition and vote status, the protest size. It sees no hidden or future event.
- A fallback is `follow_routine` with `fallback: true` and a reason: no reply within the wait, a model failure, no decision for the resident, or an action that was not offered.

**Inference stays local**

- The resident model is chosen in `config/engine.yaml` (`inference.resident_model`, default `qwen3:1.7b`; `AIA_RESIDENT_MODEL` overrides the local tag on a machine whose Ollama names it differently). It runs on loopback Ollama only.
- Before using the model, the engine checks it is installed (`/api/tags`), and that it matches `inference.resident_model_digest` when one is pinned. A missing or mismatched model gives every resident the routine fallback with the reason. No remote provider is ever tried, even with the API mayor selected.
- `GET /api/brain/status` reports the configured mayor and resident models and whether each is installed.
- A model the game names on the legacy routes must equal the configured one (422 `model_not_configured`).
- The resident code cannot import the paid-API client or the mayor backends; an import-linter contract enforces it.

**Actions** (`ResidentActionName`)

| Kind | Actions |
|---|---|
| Lawful | `follow_routine`, `go_home`, `visit_venue`, `stay_put`, `peaceful_protest`, `sign_petition` (only while a petition is open), `vote_retain` / `vote_replace` (only while a vote is open) |
| Unlawful (LLM residents only) | `speeding`, `vandalism`, `road_blockade` |

## 8. Disruptions

There are exactly seven types: `traffic`, `outage`, `gas_leakage`, `flood`, `storm`, `snowstorm` and `heavy_rain`. `GET /api/catalogs/disruptions` lists each type's defaults, effects and recovery. The values are proposed and need the interface agent's confirmation.

**Sources**

- `automatic`: planned at launch from the run's external-event stream (type, site and the gap to the next one), and hidden until it is announced.
- `scheduled`: from the launch request. `at_tick` is required, between 2 and the duration.
- `injected`: `POST /api/runs/{run_id}/disruptions` with a `DisruptionInjectRequest`, answered by a `DisruptionInjectResponse`.
  - It starts at `last processed tick + 2`, the earliest start the outcome channel can announce, or at a later `at_tick`.
  - Reposting the same `request_id` with the same body returns the same record with `duplicate: true` (HTTP 200). A different body answers 409 `request_conflict`.
  - Post injections between ticks, never while a tick request is in flight.

Every disruption is recorded in `interventions.jsonl`: scheduled ones at launch, injected ones when accepted (with `accepted_after_tick` and the request), automatic ones when announced.

**Timing.** The outcome of tick `t` lists in `disruptions_started` every disruption whose `start_tick` is `t + 1`, and in `disruptions_ended` every disruption whose effects end at `t + 1`. The game applies both from `t + 1`.

**How the game applies a disruption.** From `start_tick`, the game:

- Spawns its incident with id `incident_id` (kind, severity and needs in `incident`). It reports that incident from then on.
  - The engine refuses an `inc-…` incident that no started disruption owns (`unknown_disruption_incident`), one of another kind (`incident_kind_mismatch`), and a wrong `disruption_id` (`disruption_mismatch`).
- Applies `effects` while the disruption is active:
  - The speed multiplier applies within `scope`: the radius around the location (`area`), or everywhere (`citywide`).
  - Closures, signals out and the one-time damage always apply within `radius_m`.
- Includes these effects in the travel times it reports in `routes`. For example, a storm lowers speed citywide, so EMS `travel_ticks` grow.

**Overlapping disruptions (CUSTOM-06).** Speed multipliers multiply, in start-tick then id order, and closures are a union. Ending one disruption removes only its own contributions.

**Recovery**

- `on_duration`: ends at `end_tick`.
- `on_clear`: ends as soon as its incident is resolved, or at `end_tick` at the latest.
- `gradual`: after `end_tick` the speed stays at `gradual_speed_multiplier_bp` for `gradual_ticks`; the disruption is `recovering` meanwhile.

Consequences listed in `recovery.lasting` (such as building damage) persist after the end. A disruption never removes, moves or relabels a landmark; damage changes condition only.

**Mayor-office outage.** An `outage` whose radius covers `mayor_office` takes the mayor offline while it is active (§6).

## 9. Politics and endings

The political rules live in `data/politics/rules.v1.yaml` (versioned and recorded). Every number is a proposed tuning default.

- **Authority** starts at 100 and is never computed from satisfaction.
  - It falls through order penalties (§6) and protest pressure: −1 every `pressure_interval_ticks` while the movement is active.
  - It recovers +1 after each `recovery_interval_ticks` without a loss.
- **Moods.** The game reports `resident_moods` on politics ticks (every `politics_interval_ticks`, default 15). Without them, routine residents take no political action that tick (warning `moods_missing`).
- **Routine residents** follow explicit rules on politics ticks:
  - sign the recall petition below mood 35;
  - vote `replace` below mood 45, else `retain`, while a vote is open;
  - join the protest movement below mood 25.
- **LLM residents** act through their decisions: `sign_petition`, `vote_retain` / `vote_replace`, and `peaceful_protest` or `road_blockade` to join the movement.
- **Petition and vote.**
  - When unique signers reach `threshold_bp` of the residents, a recall vote opens on the next tick for `window_ticks`.
  - Eligibility is fixed when it opens. Each eligible resident has one ballot; duplicates and ineligible or out-of-window ballots are ignored with a warning (`duplicate_ballot`, `ineligible_ballot`, `ballot_outside_vote`).
  - At the close the engine adjudicates: removal needs `replace > retain` and turnout at least `min_turnout_bp`. A failed vote starts a petition cooldown.
- **Movement.** A movement with at least `min_participants` is active. Participants stay `persistence_ticks` after their last act.
- **Withdrawal.** Authority held at 0 under an active movement for `withdrawal_ticks` withdraws it.
- **Removal** resolves in phase 3 of a tick, either because a recall vote closes successfully or because authority was withdrawn through the previous tick.
  - When both happen on the same tick, both are recorded and `removal_priority` gives the primary label.
  - Removal ends the run at once with `status: "removed"` and `removal` set: the mechanisms are recorded, the mayor's authority is revoked (mayor state `removed`), pending mayor and resident decisions are cancelled, and the clock freezes.
  - Removal beats scheduled completion on the same tick. Without removal the run completes at its configured duration.
- **Records.** Political events (`vote_scheduled`, `movement_active`, `movement_ended`, `vote_closed`, `removal`) are appended to `decisions.jsonl` with `kind: "politics"`. Political processes continue while the mayor is offline.

## 10. Reset, cancel and degraded operation

- `POST /api/runs/{run_id}/reset` with an `EpochRequest` returns a new `RunHandle`:
  - the old run is recorded as `interrupted`
  - the new run has a new `run_id`, `run_epoch` + 1, the same map and configuration, and restarts from tick 0
  - in-flight requests of the old run are cancelled, and their late replies are discarded
- `POST /api/runs/{run_id}/cancel` ends the run as `interrupted`.
- **Degraded operation.** When the game cannot reach the engine at all, it keeps playing with its own civic controller and labels this **"Degraded operation · engine offline"**. It does not post the ticks it simulated alone. When the engine is back, the game launches (or resets) a run.

## 11. Records and replay

Each run writes `runs/<run_id>/`:

- `manifest.json`: the pinned map, config, seeds, catalog hashes and engine version.
- `observations.jsonl`: every accepted observation.
- `decisions.jsonl`: mayor and resident decisions with their envelopes and outcomes.
- `interventions.jsonl`: every disruption with its application tick.
- `ticks.jsonl`: the state hash per tick.
- `final_report.json`.

`aia replay <run>` rebuilds the run from these files with inference disabled and checks every tick's hash. It also compares the assignments, arrival ticks and authority history.

## 12. Legacy routes (transitional)

`/api/brain/status`, `/api/brain/mayor`, `/api/brain/mayor/outcome`, `/api/brain/decisions` and `/api/brain/residents` keep serving the current game until it adopts §3–§9.

- Their records live in the app's run store, not in a process-global list. Decision ids count from 0 within each run.
- `/api/brain/mayor` takes an optional `run_id` and `run_epoch`:
  - When given, the decision is recorded with that live hybrid run (also in its `decisions.jsonl`). A stale epoch answers 409 `stale_epoch`, and an ended run 409 `run_ended`.
  - Without them, the decision goes to the app's `legacy` run.
- `/api/brain/mayor/outcome` takes `{id, score_after (0–100), run_id?}`. An unknown decision answers 404 `unknown_decision`. Reposting the same score is idempotent, and a different score answers 409 `outcome_conflict`.
- `/api/brain/decisions?run_id=…` lists the last 50 decisions of a run.
- These routes keep the old fallback-order behaviour on model failure. New work should use the run routes, where a failure is a hold.

## 13. Examples, schema and types

These examples are in `docs/contract/examples/`:

| File | Shows |
|---|---|
| `incident-observation.json` | A new disruption incident and the route table |
| `route-availability.json` | Unreachable units after a flood |
| `routine-dispatch.json` | Standing dispatch with a silent mayor |
| `direct-mayoral-order.json` | A decision applied at its apply tick and the resulting order |
| `queue.json` | Unmet demand with reasons |
| `authority-change.json` | An order beyond the allowance and the authority penalty |
| `recorded-outcome.json` | The decision and order after the outcome window |

Each file is `{"description", "examples": [{"type", "value"}]}`. The examples are generated by the engine from a scripted run (`tests/engines/contract_story.py`). A test fails if they drift; regenerate them with `uv run python -m tests.engines.contract_story --write`.

## 14. Changelog

| Version | Date | Change |
|---|---|---|
| 1 | 2026-11-22 | First version |
