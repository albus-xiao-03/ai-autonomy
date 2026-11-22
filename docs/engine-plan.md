# AI Autonomy — R1 Implementation Plan

| | |
|---|---|
| Specification | [`SPEC.md` Part B](../SPEC.md) (commit `3810aa8`) |
| Plan status | Final: the implementation baseline, with decisions recorded in §13. Implementation has not started |
| Prepared | 2026-11-22 |
| Stack (decided) | Python 3.14 engine (uv) · TypeScript + Vite + Three.js frontend (Node 24) · Ollama serving Qwen GGUF locally |

Requirement IDs such as `FIN-02` refer to the specification. **Interpretation** marks the places where this plan resolves an ambiguity in the spec. §13 lists the interpretations together with the recorded decisions (D1, D2) and the adopted defaults.

---

## 1. Summary

R1 has three parts:

- A Python simulation server that owns all authoritative state and advances it in fixed ticks.
- A browser client that renders the city and controls the run.
- Two strictly separated inference routes:
  - Residents use local Ollama only.
  - The mayor uses one of three backends: a deterministic baseline (in-process), local Ollama, or a remote API.

Every model output is a structured proposal. The engine validates it and then applies it atomically. Every run is recorded so it can be replayed without inference.

Work runs as ten milestones: a foundation milestone (M0), then the nine stages of spec §24 in the same order. Each milestone ends with automated checks and a result you can see in the browser.

| Milestone | Spec stage (§24) | Completion condition |
|---|---|---|
| M0 Foundations | — | Deterministic tick skeleton, protocol, recorder, replay, CI and frontend shell |
| M1 Boston foundation | Boston foundation | Valid map, routines, roads and renderer |
| M2 Services and event core | Services | Disruptions and responses change outcomes |
| M3 Construction and finance | Construction and finance | Automatic projects obey accounting and time |
| M4 Local residents | Local residents | Local decisions affect behavior |
| M5 Mayor integration | Mayor integration | Both backends execute validated actions |
| M6 Server dependency | Server dependency | Outage, backup, repair and recovery work |
| M7 Politics and endings | Politics | Organization, voting and removal work |
| M8 Custom events | Custom events | Environmental and economic events can be composed and injected |
| M9 Release verification | Release verification | Replay, benchmarks, acceptance checks and documentation complete |

Two recorded decisions shape the plan (§13.1):

- **D1:** the target MacBook Air has 24 GB of RAM, and it is benchmarked only after development is complete (M9).
- **D2:** no test is run against the paid API. API mode is verified against a local fake endpoint.

The three largest risks:

- **Determinism:** handled early; the deterministic core and replay are built in M0.
- **Reliability of a small model's output:** handled in M4 with engine-built choice menus and decoding constrained to a JSON schema.
- **Inference throughput on the target MacBook Air:** cannot be measured before M9 (D1). Workload defaults are therefore conservative planning values kept in configuration, the benchmark runs unattended, and M9 reserves time to measure and retune on the Mac.

---

## 2. Baseline and constraints

### 2.1 Repository

Only `LICENSE` (MIT) and `SPEC.md (Part B)` exist. Everything in this plan is new work.

### 2.2 Development environment (sandbox, measured 2026-11-22)

| Item | State |
|---|---|
| Machine | aarch64 Linux VM, 10 cores, 11 GiB RAM, no GPU |
| Toolchain | uv 0.13.9, Python 3.14.10, Node 24.22.3, npm 12.2.3 (bootstrapped into `~/.npm-global`) |
| Package sources | PyPI, the npm registry, GitHub and Debian apt are reachable (`chromium` is available from apt) |
| Inference runtime | Ollama 0.40.17, CPU build in `~/.local/ollama`, started manually |
| Model | `qwen3-1.7b-q8`: the official `Qwen/Qwen3-1.7B-GGUF` Q8_0 file from Hugging Face, imported with a Modelfile (`num_ctx` 4096) |
| Model sourcing | `ollama pull` is blocked (the registry's blob host returns 403). Models come from Hugging Face and are imported with `ollama create` |
| CPU smoke benchmark | ≈0.8 s per schema-constrained resident decision (thinking off, ≈36 output tokens), ≈46 generated tokens/s, 2.7 GB loaded. Concurrency of 2 or 4 gave no gain with Ollama's default parallelism |
| Blocked hosts | ollama.com and cdn.jsdelivr.net. The frontend therefore bundles every asset and uses no CDN |

The sandbox numbers are not evidence for HW-01 or HW-06; the target machine is described in §2.3. The sandbox is used for development, for checks against fake inference, and for CPU smoke tests.

### 2.3 Target machine

| Item | State |
|---|---|
| Machine | MacBook Air, Apple silicon, 24 GB unified memory (confirmed, D1) |
| Not yet known | Chip generation and macOS version. `aia bench machine` records them in M9 |
| When it is measured | Once, after development is complete (M9, D1). No target-Mac numbers exist before then |

Until M9, every hardware-dependent default is a planning value (§5.13). The startup preflight still measures the memory actually available on whatever machine it runs on, because HW-01 forbids assuming the maximum is available.

### 2.4 Planning assumptions

- One user, one machine and one run at a time.
- The engine and the frontend talk over loopback only; nothing is exposed to the network.
- Every numeric default in this plan is an initial game parameter (spec §1.2). These defaults live in versioned configuration, not in code.
- These items are out of scope (spec §3.2):
  - other cities and procedural city generation
  - detailed combat or criminal tactics
  - realistic fluid, structural or fire physics
  - a comprehensive municipal economy
  - unrestricted zoning
  - multiple mayor data centers
  - multiplayer
  - model training and online reinforcement learning

  Simplifications must keep observable cause and effect. The integration scenarios in §8.3 check this.

---

## 3. Architecture

### 3.1 Components (ARCH-01)

| Spec component | Implementation | Package / path |
|---|---|---|
| Three.js frontend | Vite + TS single-page app: Three.js scene, Preact panels, uPlot charts | `aiautonomy/interfaces/` |
| Simulation engine | World state, the fixed-tick pipeline and its subsystems | `aiautonomy.engines.sim`, `.world`, `.traffic`, `.services`, `.build`, `.finance`, `.residents`, `.politics`, `.host`, `.metrics` |
| Action validator | Checks schema, identity, freshness, authority, availability, eligibility, prerequisites and combined commitments, then commits atomically | `aiautonomy.engines.mayor.validator`, `aiautonomy.engines.mayor.commit` |
| Agent scheduler | Builds observations and decision opportunities; manages queues, deadlines, fallbacks and staging | `aiautonomy.engines.agents.scheduler` |
| Local resident adapter | Loopback-only Ollama client used for every resident model operation | `aiautonomy.engines.agents.resident_local` |
| Mayor adapter | `baseline`, `local` (Ollama) and `api` (Anthropic) backends behind one interface | `aiautonomy.engines.mayor.backends` |
| Event system | Schema, effect library, modifiers and stacking, presets, triggers, preview, library I/O | `aiautonomy.engines.events` |
| Recorder and replay | Manifest, decision and event logs, tick hashes, snapshots, replay, comparison, export | `aiautonomy.engines.record` |

### 3.2 Runtime topology

```text
+----------------------------- Browser ------------------------------+
|  Vite/TS app: Three.js scene, panels, event editor                  |
+----------------------------------+---------------------------------+
                                   | WebSocket + REST on 127.0.0.1
                                   | (snapshots, deltas, commands)
+----------------------------------+---------------------------------+
|  Engine server: Python, FastAPI/uvicorn, one asyncio loop           |
|                                                                     |
|  Sim driver -> tick pipeline (phases 1-8) -> authoritative World    |
|                                                                     |
|  Agent scheduler                                                    |
|    resident route -> Ollama @ 127.0.0.1:11434 (loopback only)       |
|    mayor route    -> baseline (in-process)                          |
|                   -> local: Ollama (may share the model)            |
|                   -> api:   Anthropic Messages API                  |
|                                                                     |
|  Recorder -> runs/<run_id>/ (manifest, logs, hashes, snapshots)     |
+---------------------------------------------------------------------+
```

The design follows three principles:

1. **Engine authority (RULE-01).** Only engine code mutates the World. Models, users and the UI submit proposals or commands.
2. **Separate routes (LOCAL-06).** The two inference routes share no client, queue or configuration namespace.
3. **Determinism (SIM-04).** A run is fully determined by its seeds, configuration, recorded decisions and recorded interventions.

---

## 4. Cross-cutting design

### 4.1 Engine authority and the action interface (RULE-01, RULE-02, RULE-05, ARCH-04)

**What models return**

- Models never return state.
  - A resident returns the id of one option from a menu the engine built, plus an optional short utterance.
  - The mayor returns a bundle of catalog actions whose targets and parameters come from enumerated lists, plus an optional explanation.
- Output is JSON only. It is parsed with `json.loads` into strict pydantic models (`extra="forbid"`, with length limits).
- Model output is never evaluated, executed or used as a template. A test scans the decision path for `eval`, `exec` and template rendering.

**What the engine controls**

- Costs, durations and effects come from versioned catalogs (MAY-04). A number in model output is either one of the enumerated choices or it is ignored.
- Validation builds a `CommitPlan` against a read-only view of the World, and commit applies it all or nothing (MAY-05). A property test checks that a rejected bundle leaves the state hash unchanged.
- A valid decision executes with no human step (RULE-02). Commit hands the work (projects, policies, dispatch priorities) to standing procedures, which carry it out (SRV-07).
- Every action type except `hold` has an *outcome probe*: a set of metrics watched after the action is applied. The UI uses it to show measured outcomes (MAY-06), and tests use it to check that the action changed state (RULE-05).

**Free text**

Explanations, utterances and event descriptions are for display only:

- They are length-capped.
- The UI renders them as text, never as HTML.
- When they appear in a prompt, they are passed only inside clearly delimited data fields.

### 4.2 Determinism and randomness (SIM-04, EVAL-02, CITY-04)

**Keyed randomness**

`rng.u01(stream, *key)` takes the first 8 bytes of `blake2b(stream_seed ‖ key)` and maps them to a uniform number. A draw depends only on its key, for example `("medical_demand", tick, resident_id)`. It does not depend on how many other draws happened, so endogenous behavior can never shift external randomness.

**Streams**

Each stream has its own recorded seed, derived from the run seed unless overridden:

`population`, `mode_assignment`, `schedules`, `preferences`, `external_events`, `event_effects`, `medical_demand`, `fire`, `traffic_background`, `services`, `politics`, `model_sampling`.

Only the event system reads the external-event streams.

**Arithmetic**

Results must be bit-identical on macOS and Linux, so:

- Money is integer cents. Counts and time are integer ticks.
- Continuous quantities are floats, restricted in authoritative updates to `+ − × ÷ min max` and integer powers. `exp`, `log`, `pow` and trigonometric functions are not used there.

**Ordering**

- Entities live in dicts keyed by id and are iterated in sorted id order.
- Authoritative code never iterates over a `set`.
- Ids come from deterministic per-type counters, never from `uuid4`.
- `run_id` is excluded from the state hash.

**State hash**

Each tick, the World is serialized to canonical JSON (sorted keys, floats via `repr`), hashed with blake2b and recorded. Replay compares the hashes tick by tick and reports the first tick and subsystem that diverges.

**Population rounding (RES-06)**

**Interpretation:** the LLM ratio is stored in basis points (0–10000), and

```text
llm_count = (population × ratio_bp + 5000) // 10000
```

This rounds halves up, unlike Python's banker's `round`.

### 4.3 Tick pipeline (SIM-01, SIM-02, END-01..END-04)

Defaults for SIM-01, all configurable before a run:

| Parameter | Default |
|---|---:|
| Tick | 1 simulated minute (the default scenario starts at 07:00) |
| Playback | 5 ticks/s; also 1×, 2×, 4×, maximum speed and single step |
| Duration | 300 ticks |
| Mayor decision interval | 30 ticks (doubled while the server room is Degraded) |
| Population | 100 |
| LLM ratio | 50 % |

Phases within tick `t`, documented in `docs/tick-order.md`. Each phase is a function of the World and its inputs:

| # | Spec step | Work |
|---|---|---|
| 1 | Activate events and resolve due timers | Start and end scheduled, injected and condition-triggered events; add or remove their modifiers; apply lasting damage at onset; expire policies, detentions and restart delays |
| 2 | Update infrastructure availability | Power zones, effective road capacity and closures, facility condition and availability, maintenance access, server-room state machine |
| 3 | Resolve removal outcomes already due | Ballots closing at `t` and removal resolutions scheduled for `t`. On success, run the removal transition and skip to phase 8 |
| 4 | Revalidate and apply staged decisions | Mayor bundles and resident choices whose `apply_tick == t`: full revalidation, then atomic commit or rejection. Timeouts become fallbacks |
| 5 | Advance projects, movement, dispatch and services | Crews and project progress (with ledger transfers), routing and movement, dispatch, fire, EMS, hospitals, police, shelters, operating costs, revenue, corruption losses |
| 6 | Update residents and politics | Health, needs, exposure, experiences and grievances, support, willingness, movements, petitions, ballots, protests, consequences of unlawful actions |
| 7 | Metrics and newly achieved removal | Satisfaction, reward and report metrics; evaluate removal rules. On success, run the removal transition |
| 8 | Publish | Send the state delta to the UI, append to the recorder, then issue new decision requests built from the post-tick state |

**Termination**

Termination is checked after phase 7, or after phase 3 if a removal succeeded there:

- **Removal:** the run ends as `removed`. This takes precedence even when `t == duration` (END-04).
- **Duration reached:** otherwise, when `t == duration`, the run ends as `completed` (END-01).
- **Nothing else ends a run early (END-02).** Outages, disasters, bankruptcy, corruption and protests only change state.
- **Interruptions:** a user cancellation or an application failure marks the run `interrupted` (END-05).

**Interpretation (SIM-02, steps 3 and 7):** a removal rule can succeed in two ways:

- immediately, when its conditions are met (evaluated in phase 7)
- through a scheduled resolution, such as a ballot closing time, that is adjudicated in phase 3 of the due tick

Both paths use the same atomic transition (§5.9).

### 4.4 Decision lifecycle and identity (SIM-03, SIM-05, ARCH-02, MAY-05, HOST-05, END-03)

```text
request at t_obs --> in flight --> response --> parse + schema --> identity check --> staged for apply_tick
        |                                                                                   |
        +-- deadline or cancellation --> fallback (resident) / hold (mayor)                 v
                                                                    phase 4: revalidate --> commit | reject
```

**Envelope**

Every request and response carries:

- `run_id`, `run_epoch`
- `actor_id`, `decision_id`
- `observation_id` (a hash of the observation payload) and `observation_tick`
- `apply_tick`
- `availability_epoch` (mayor only)
- `schema_version`

The adapter attaches the envelope. The output schema also binds the model's answer to its request by listing `decision_id` as a single-value enum.

**Fixed apply tick**

The apply tick is fixed when the request is made: `observation_tick + latency_ticks`. The defaults are 2 ticks for residents and 5 for the mayor. Results therefore never depend on when a response arrives in wall-clock time.

**Waiting for responses**

- Before phase 4 of tick `t`, the driver waits for outstanding requests with `apply_tick == t`, up to each request's wall-clock deadline. SIM-03 allows this pause, and the UI shows "waiting for inference" while it lasts.
- On timeout, a resident gets a fallback and the mayor holds.
- Requests whose actor becomes ineligible are cancelled at once and never waited for. This happens when:
  - the server room leaves Online/Degraded, which changes `availability_epoch`
  - authority is revoked
  - the run is reset

  A simulated outage therefore never pauses the city (SIM-03).

**Rejections**

A response is rejected if any of these hold:

- wrong `run_id` or `run_epoch` (it arrived late, after a reset; SIM-05)
- unknown or already-resolved `decision_id` (a duplicate)
- mismatched `observation_id`
- stale observation
- changed `availability_epoch` (HOST-05)
- revoked authority (END-03)

**Outcomes**

Each request ends with exactly one recorded outcome: `accepted`, `rejected(reason)`, `malformed→fallback`, `timeout→fallback`, `cancelled(reason)` or `deferred`.

### 4.5 Concurrency and pacing (SIM-03, HW-06)

- One asyncio loop runs HTTP and WebSocket handling, the sim driver and inference I/O.
- A tick runs synchronously and must stay short: the budget is under 20 ms at the default population, measured from M1 onward. If it grows past that, the step moves to a worker thread without changing its semantics.
- Playback paces ticks against the wall clock. Neither pacing nor inference waits ever block WebSocket handling, so pause, reset and inspection stay responsive during inference.
- Pause, reset and cancel take effect at the next tick boundary. Reset increments `run_epoch` and cancels in-flight tasks (SIM-05).
- A headless maximum-speed mode serves tests, calibration sweeps and comparisons.

### 4.6 Configuration, versioning and secrets (SIM-04, POL-04, MET-01, HW-02, ARCH-05)

- Every data file carries `id`, `version` and `schema_version`. Loaders validate files with pydantic and compute their sha256.
- The run manifest records every data file's version and hash, plus the engine version (package version, git SHA and a dirty flag).
- Configuration is layered: scenario file, then overrides from the run configuration panel, then a frozen run configuration. Changing the population ratio, or any other frozen field, requires a new run (RES-06).
- Secrets come only from the environment or from the SDK's own credential resolution. They are never written to configuration snapshots, manifests, logs or exports. A redaction test scans exported bundles (ARCH-05).
- Building and verifying R1 needs no API credentials, because no test calls the paid API (D2).

### 4.7 Run records

Each run writes `runs/<run_id>/`:

| File | Contents |
|---|---|
| `manifest.json` | Run id; status (`running`, `completed`, `removed` or `interrupted`); engine version; versions and hashes of every config, map, catalog, rule set, metric definition and prompt; per-stream seeds; model settings (ids, quantization, digests, runtime version, context and output limits); backend modes. Never credentials |
| `interventions.jsonl` | Scheduled and injected events with their application ticks (CUSTOM-07) |
| `decisions.jsonl` | Per request: envelope, observation digest (full observation optional), raw response (optional), parsed proposal, validation outcome and reasons, fallback flags, latency, the model that actually served the request, token usage |
| `ticks.jsonl` | State hash and metrics for every tick |
| `snapshots/tick-NNNNNN.json.gz` | Full state every 30 ticks and at the end |
| `final_report.json` | Terminal outcome, removal mechanism(s), metrics (MET-05), inference coverage (LOCAL-05) |

Runs export to and import from a single `.aia-run.zip`.

### 4.8 Engine–frontend protocol (ARCH-03)

- The pydantic message models are the single source of truth. Their JSON Schema is exported and TypeScript types are generated from it with `json-schema-to-typescript`. CI fails if the generated types drift.
- Server to client: `snapshot`, `delta {run_id, state_version, tick, changes}`, `decision`, `metrics`, `run_status`.
- Client to server: `configure`, `start`, `pause`, `resume`, `step`, `set_speed`, `reset`, `cancel`, `inspect`, and `event.preview`, `event.schedule`, `event.inject`, `event.save`, `event.delete`.
- The client discards messages with an unknown `run_id` or an old `state_version`. It requests a fresh snapshot when it detects a gap.

---

## 5. Subsystem design

### 5.1 Boston map (CITY-01..CITY-05)

**Footprint (proposed)**

Downtown Boston, about 2.0 × 2.4 km:

- west: Charles St / Storrow Dr
- east: Atlantic Ave and the waterfront
- north: Causeway St and the North End waterfront
- south: Kneeland St

The area covers Beacon Hill, the West End, the North End, Government Center, the Financial District, Downtown Crossing, Chinatown, Boston Common and the Public Garden.

**Scale and labeling**

- 1 world unit is 1 m, on a local east-north plane around a fixed origin near the Old State House.
- `data/maps/boston/v1/README.md` documents the footprint, scale, represented roads, landmarks and simplifications.
- The UI shows a "Represented area" label, a scale bar and the outline of the area (CITY-01).

**Content**

Every entity has a stable id, for example `road:cambridge-st-03` or `lm:old-north-church`.

- **Districts (7):** Beacon Hill, West End, North End, Government Center, Financial District, Downtown Crossing, Chinatown. The Common and Public Garden form a park zone.
- **Road graph:** about 40–60 named streets, simplified to about 150–250 nodes. One-way rules are approximated. The I-93 tunnel and minor alleys are omitted.
- **Protected landmarks:** Massachusetts State House, Boston Common, Public Garden, Park Street Church, Granary Burying Ground, King's Chapel, Old South Meeting House, Old State House, Faneuil Hall, Paul Revere House, Old North Church.
- **Facilities:**
  - Massachusetts General Hospital and Tufts Medical Center: real sites, fictional capacities.
  - Boston City Hall as the government facility.
  - Generic police, fire and EMS stations, 3 shelters and a maintenance depot.
  - The mayor server room, in a fictional building on its own power-zone feeder.
- **Homes, workplaces and leisure destinations:** aggregated building blocks with capacities.
- **Construction plots:** about 10, none overlapping a landmark footprint.
- **Power zones:** 4, simplified.

**Data source (decision):** hand-digitized, simplified geometry. This needs no network access and keeps licensing clean. If OpenStreetMap geometry were imported instead, ODbL attribution and share-alike would apply and would be documented.

**Pipeline**

1. Authored source files in `source/*.yaml`.
2. `aia map build` produces the canonical `map.json` and `landmarks.json`, with their hash in `map.lock`.
3. Each run loads the canonical files by version and verifies the hash (CITY-04).

**Landmark protection (CITY-03)**

- A landmark's identity, location and footprint are immutable: frozen models with no mutation API.
- Only `condition` and `access` can change, and only through events.
- No mayor action can target a landmark to move, demolish or replace it.
- Tests try every action type and every effect type against every landmark.

**Initialization (CITY-04)**

Seeds vary only residents, assignments, preferences, schedules and event parameters. A test checks that different seeds produce an identical map hash.

**Validation before start (CITY-05)**

- Referential integrity.
- Every capacity is positive.
- Starting resources are present: funds, units, crews, staff, backup reserve.
- Every resident has a reachable home, workplace and leisure destination.
- Each district can reach every hospital, the government facility and its responding stations.
- The maintenance depot can reach the server room.
- Plots are eligible and clear of landmarks.

Any failure blocks the run, and the configuration panel lists the failures.

**Interpretation:** a scenario can declare intentional deviations, such as a road closed at start, in an `intentional_overrides` list. Validation accepts and records them; only *unintentional* invalid states block the run.

### 5.2 Residents (RES-01..RES-07, MET-02)

**State (RES-01)**

| Group | Fields |
|---|---|
| Identity | `id`, decision mode (`routine` or `llm`), status (`active`, `incapacitated`, `detained` or `departed`) |
| Places and movement | home, workplace, set of leisure destinations, location, route, activity |
| Health | health in [0,1], open medical need |
| Access and cost | travel delay, essential-service access flags, financial burden |
| Memory | preferences, bounded ring buffer of recent experiences, grievances by category |
| Politics and welfare | satisfaction and its components, incumbent support, willingness to organize, participation |

**Generation**

- Homes are assigned by district capacity.
- Workplaces and leisure destinations come from distance-weighted keyed draws.
- Schedules come from templates (office, shift, student, retiree, care worker) with keyed jitter.
- Preferences cover travel mode, risk tolerance, baseline support and income band.

**Population mix (RES-06)**

- `llm_count` is computed as in §4.2.
- The LLM subset is the `llm_count` residents with the lowest `mode_assignment` draws. The sets are therefore nested: a higher ratio's LLM set contains every lower ratio's set.
- Routine-only and mixed runs share identical residents.
- The ratio ranges over 0–100 %. Changing it requires a new run.

**Routine residents (RES-02)**

Routine residents follow a deterministic rule table, documented in `docs/residents.md`:

- Follow the schedule; reroute around closures.
- If a destination is unreachable, wait or return home; the delay is recorded.
- Seek care when health or need crosses a threshold: walk or drive to a hospital, or call EMS, depending on severity.
- Go to an active shelter when an advisory covers their area; comply with advisories.
- Take part in lawful politics by explicit thresholds: sign petitions, vote by support, join lawful protests.

Routine residents never act unlawfully and never call a model. A test asserts zero inference requests for them.

**LLM residents (RES-03)**

- Between decisions they follow the same routine.
- At a decision opportunity, the engine builds a menu of at most 8 valid options:
  - continue or change the plan; pick an alternative destination
  - seek treatment or shelter
  - comply with or ignore an advisory
  - submit a grievance
  - join or leave a movement
  - vote, when a ballot is open
  - take a supported unlawful action
  - join a forceful removal attempt
- The model picks one option and may add an utterance of up to 140 characters.

**Unlawful actions (RES-04)**

These are abstract actions, available to LLM residents only, and catalogued in `data/catalogs/unlawful.v1.yaml`:

| Action | Prerequisites | Consequences |
|---|---|---|
| `obstruct_road` | At the segment; member of a movement at "civil disobedience" escalation or higher | Segment capacity drops while the resident is present; police incident; risk of detention |
| `vandalize_facility` | At a non-landmark facility | Facility condition drops, so its capacity drops until repaired; public safety drops in the district |
| `obstruct_server_access` | At the server room's access segment; movement member | Maintenance access is blocked and backup replenishment delayed while the resident is present (HOST-04) |
| `occupy_government_facility` | At City Hall while a forceful attempt is active | Adds to forceful-removal participation (POL-06) |

Consequences use keyed draws; for example, detention probability depends on police presence. Detained residents stay in every denominator.

**Observations (RES-05)**

| Included | Excluded |
|---|---|
| The resident's own state | Hidden or future events |
| Nearby conditions within a radius or district: closures, incidents, crowding, facility queues | Other residents' private state |
| Public information: advisories, public events, mayor explanations, movement announcements, ballots | Unrestricted global data |
| The option menu | |
| Bounded memory: the last 6 experiences and a grievance summary | |

**Persistent experience (RES-07)**

- Grievances accumulate per category: health, services, mobility, affordability, safety, trust.
- Each accumulator decays by a documented per-tick factor. It does not decay while the failure that caused it persists.
- Announcements can raise expectations but never reduce an accumulator.

**Population accounting (MET-02)**

Residents never leave the satisfaction denominator. The `incapacitated`, `detained` and `departed` statuses each have defined component rules; for example, an incapacitated resident has H = 0. `departed` is reserved for cases such as evacuation.

### 5.3 Local resident inference (LOCAL-01..LOCAL-06, HW-04, HW-05, HOST-08)

**Shared serving (LOCAL-03)**

One Ollama server keeps one resident model loaded, shared by all residents. Each request goes to `/api/chat` with:

- `format`: a per-request JSON Schema whose choice enum is the offered option ids
- `think: false`
- bounded `num_ctx` and `num_predict`
- `keep_alive`, so the model stays loaded
- `seed`, taken from the `model_sampling` stream

**Keeping resident inference local (LOCAL-01, LOCAL-02, LOCAL-06)**

Five layers of enforcement and evidence:

1. **Configuration check.** The resident endpoint must be a loopback address or a Unix socket. Anything else refuses to start.
2. **Transport guard.** A dedicated HTTP client runs with `trust_env=False`, because the sandbox sets proxy variables, and checks the peer address when it connects.
3. **Code boundary.** An import-linter contract forbids resident modules from importing `anthropic` or any mayor backend.
4. **Evidence.** Integration tests install a `sys.addaudithook` hook on `socket.connect` and assert that resident-route connections only reach loopback, including in runs with the API mayor. The final report includes an egress summary by route.
5. **No escalation on failure.** A timeout or a malformed or invalid response produces a deterministic routine fallback for that opportunity. Urgent decisions can instead be deferred to the next tick, with bounded retries. A failure never moves to another route.

The mayor may observe public and aggregate resident behavior, but a mayor output is never used as a resident decision.

**Interpretation ("separate route", LOCAL-06 and HW-04):** each route has its own client, queue, deadlines and configuration namespace. The local mayor may share the Ollama process and model with residents. In that case a `ModelArbiter` allocates inference slots, giving the mayor priority while guaranteeing residents a share. If separate models would exceed the memory budget, the arbiter serializes model use instead.

**Scheduler (LOCAL-04)**

| Aspect | Rule |
|---|---|
| Rotation | Each LLM resident gets a routine opportunity every `decision_period` ticks, at a keyed phase offset (deterministic) |
| Urgency | Urgent triggers (health crisis, nearby hazard, blocked route, ballot opened, advisory issued) create priority opportunities, with a per-resident cooldown |
| Bounds | `max_decisions_per_tick`; `queue_max`; `max_in_flight` (equal to Ollama's parallel slots); caps on prompt, context and output tokens; a per-request deadline |
| Fairness | Priority ages while a request waits. Any resident whose last opportunity is older than `max_starvation_ticks` is promoted. Queue overflow defers requests and records it; nothing is dropped silently |

**Coverage reporting (LOCAL-05)**

Shown in panel 2 and the final report, as totals and per-window series:

- the configured percentage and count
- residents who had at least one inference attempt
- residents with at least one accepted decision
- counts of requested, accepted, rejected, timed-out, fallback and deferred decisions
- latency at p50 and p95

**Independence from the server room (HOST-08)**

No resident code reads server-room state. A test runs residents through a full mayor outage.

### 5.4 Traffic and services (SRV-01..SRV-07)

**Roads (SRV-02)**

- Each directed segment has a length, free-flow speed, capacity, condition, closure state (`open`, `closed_general` or `closed_all`) and an emergency-access flag.
- Effective capacity = base capacity × condition × stacked modifiers.
- Travel time follows the BPR curve with an integer exponent:

  ```text
  travel_time = free_flow_time × (1 + α × (load / capacity)^4)
  ```

- Load is the number of agents on the segment plus a time-of-day background demand, scaled by an economic multiplier. The background term lets 100 residents produce realistic congestion.

**Movement**

- Agents progress along each segment (a mesoscopic model).
- Routes come from Dijkstra with deterministic tie-breaking. Agents reroute on a closure or when delay passes a threshold.
- An unreachable destination produces an explicit `unreachable` outcome: a delay, a reroute or a failure. When the destination is essential, it counts toward access failure.

**Units (SRV-01)**

- Police cars, fire engines and ambulances each follow a state machine: `available → dispatched → on_scene → transporting → returning`, plus `out_of_service`.
- A unit has exactly one assignment at a time; a property test checks this.
- Staffing determines how many units are in service. Units have a per-tick operating cost.

**Standing operations (SRV-07)**

Every tick, dispatch assigns compatible available units to pending incidents without any mayor input:

- ordering by policy priority: severity, waiting time and mayor-set weights by district or incident type
- choosing the nearest unit by current travel time

Maintenance crews follow their repair procedures in the same way.

**Fire (SRV-03)**

- A fire is an incident at a building, with severity from 0 to 10.
- Severity grows each tick unless suppression (engines on scene × rate) exceeds growth.
- Fire damages building condition. For landmarks it affects condition only.
- Casualties create EMS calls by keyed draw.

**EMS (SRV-04)**

- Calls are generated from a base rate × health, age and exposure × event multipliers, using keyed `medical_demand` draws.
- Each call goes through dispatch, travel, time on scene, transport to the hospital chosen by travel time and published queue, and handoff.
- Every stage is timed and recorded.

**Hospitals (SRV-05)**

- Hospitals have beds and a treatment throughput limited by staff, with a triage queue.
- Arriving does not mean being treated. A queue beyond its limit leads to diversion or unmet need.
- A surge adds temporary staffed capacity.
- During a power loss a hospital switches to generator mode with reduced throughput.

**Police (SRV-06)**

Police provide:

- patrol presence in each district, which drives public safety
- response to incidents, including unlawful actions and traffic incidents
- emergency access: traffic control and clearing physical obstructions
- an input to the institutional-control model for forceful removal

There is no code path from police to grievances or ballots, and a test checks this.

**Shelters and power**

- Shelters have a capacity and a staffing cost while active.
- Power zones are on or off, with interruptions and restoration driven by events.
- An outage darkens homes (exposure during heat or cold), reduces capacity where traffic signals are out, and switches hospitals to generator mode.

### 5.5 Construction, repair and finance (BUILD-01..BUILD-04, FIN-01..FIN-03)

Project catalog `data/catalogs/projects.v1.yaml` (BUILD-01, BUILD-02). The numbers are illustrative; final values live in the catalog.

| Project | Eligible locations | Work and crews | Prerequisites | Disruption while building | Completion effect | Operating cost |
|---|---|---|---|---|---|---|
| Hospital expansion | Plots next to MGH or Tufts | 180 crew-ticks, 2 crews | Road access, power | Hospital capacity −5 % | More beds, staffed gradually as hiring progresses (k beds per hour) | Per staffed bed |
| Emergency-service station | Station plots | 120 crew-ticks, 2 crews | Access, power | Adjacent lane closed | One more ambulance or engine, after an equipment-acquisition delay | Per unit |
| Road repair | Damaged segments | Depends on damage, 1 crew | Access to the segment | Segment capacity −50 % | Condition restored | None |
| Server backup-power installation | Server-room annex | 90 crew-ticks, 1 crew | Access; power for commissioning | None | Larger backup capacity and faster replenishment | Maintenance per tick |

Each catalog entry also defines:

- the construction cost
- the cancellation charge
- failure rules: for example, a destroyed site, or prerequisites lost for longer than `max_pause_ticks`, mark the project `failed` and apply the documented refund rule

**Lifecycle (BUILD-03)**

`queued → building ⇄ paused → completed | cancelled | failed`, with an exhaustive transition table and tests. Completion applies its benefits through an idempotent handler guarded by `benefits_applied`, so benefits are applied exactly once.

**Crews (BUILD-04)**

- Construction crews and maintenance crews are finite pools, allocated first-in-first-out by acceptance tick.
- A project with no available crew stays `queued`.
- Losing access, power or materials pauses progress.

**Ledger (FIN-01)**

- All amounts are integer cents.
- Accounts: cash, reserved construction funds, committed temporary services, operating expenditure, construction expenditure, revenue, corruption losses, cancellation charges.
- `available = cash − reserved − committed`.
- Every change goes through a journal entry. Invariants are checked every tick in debug and CI runs.

**Reservations (FIN-02)**

- Accepting a project reserves its full cost.
- Each tick of progress moves money from the reservation to expenditure:

  ```text
  transfer = floor(cost × done / total) − spent_so_far
  ```

  Allocating against the cumulative floor means the last tick settles the total exactly, with no double charging.

- Cancellation refunds the unspent reservation, less the configured charge.

**Temporary-service commitments**

Surges, shelters, overtime and traffic-control staffing are committed in full when accepted and released if they end early.

**Operating affordability (FIN-03)**

Operating costs start when a facility or unit becomes operational. If funds run short, a documented reduction ladder applies, and it reverses when funds recover:

1. Unstaff capacity that projects added.
2. Reduce unit shifts.
3. Suspend non-essential services.

Reservations are never consumed and funds are never invented. Bankruptcy is a visible state, never a reason to end the run.

**Revenue**

A per-tick base amount by district economic activity, multiplied by event modifiers such as a boom or a contraction.

**Corruption**

- An institutional event diverts revenue or cash into `corruption_losses`. Unless the event is public, it shows only as an unexplained gap in the finances.
- The leak continues until a corruption audit (a mayor action) detects it.
- Detection stops the leak and may recover a fraction of the losses. It also makes the corruption public, which affects trust.

### 5.6 Autonomous mayor (MAY-01..MAY-08, POL-07, EVAL-01, ARCH-05)

**Pipeline (MAY-01)**

Observe → propose → validate → commit → execute → observe results. There is one cycle per decision opportunity:

- every 30 ticks while the server room is Online
- every 60 ticks while it is Degraded
- none while it is Offline or Recovering

**Observation (MAY-02)**

The observation includes:

- the current time and remaining duration
- funds, reservations and commitments
- service resources and demand
- known incidents (reported or public)
- traffic and facility conditions
- construction and repair status
- server-room condition
- public political conditions and aggregated grievances
- recent metrics
- results of previous actions: accepted or rejected, with reasons and measured outcomes

A single `ObservationPolicy` builds it for every backend, including the baseline (EVAL-01). It excludes hidden and future events. Size is bounded per backend, for example by keeping the top-K incidents and aggregating per district.

**Action catalog (MAY-03, MAY-04)**

`data/catalogs/actions.v1.yaml`. Each entry defines its parameters (enumerated targets and durations), prerequisites, costs (upfront and per tick), duration, resource use, cooldown, observable effects and outcome probe.

| Action | Example parameters | Effect |
|---|---|---|
| `temporary_service_allocation` | Unit type, from/to district, duration | Moves or adds units from an overtime pool, at a per-tick cost |
| `dispatch_priority` | Weights by incident type or district, duration | Changes dispatch ordering |
| `hospital_surge` | Hospital, level, duration | Temporary staffed capacity; has a cooldown |
| `start_project` | Project type, plot or segment | Reserves funds and queues construction or repair |
| `cancel_project` | Project id | Cancels under the FIN-02 refund rules |
| `traffic_control` | Segment; control type (closure, emergency lane, signal priority); duration | Changes capacity or priority |
| `activate_shelter` | Shelter, duration | Opens capacity at a staffing cost |
| `public_advisory` | Type (avoid area, stay home, seek shelter), area, duration | Routine residents comply; LLM residents see it as public information |
| `corruption_audit` | Department | Costs money and time; detects active corruption |
| `hold` | — | Keeps existing policies |

**Validation (MAY-05)**

Checks run in this order, each with its own reason code:

1. schema and identifiers
2. run and decision identity
3. observation freshness
4. current authority
5. server availability, including an unchanged `availability_epoch`
6. target eligibility, including landmark protection
7. prerequisites and cooldowns
8. combined funds, crews, units and staff across the whole bundle
9. conflicts between actions in the same bundle

A bundle holds at most 4 actions and commits atomically, or not at all.

**Explanation (MAY-06)**

The mayor may add an explanation of up to 280 characters. The decisions panel keeps four things distinct:

- proposed actions
- accepted actions
- rejection reasons
- measured outcomes: outcome-probe changes over a window after the action is applied

**Backends (MAY-07)**

Every backend only produces proposals for the same validator and permission set. Choosing a backend never changes permissions or infrastructure constraints.

- **`baseline`** — deterministic rules, for example:
  - surge when a hospital queue exceeds a threshold and funds allow
  - repair damaged segments on critical routes
  - install backup power when the reserve margin is low
  - audit when the finances show an unexplained gap
  - open shelters and issue an advisory when severe weather is publicly announced
  - otherwise hold

  It uses the same observation, catalog, costs, vulnerability and political rules as the model mayors (EVAL-01).
- **`local`** — Ollama with a schema-constrained action bundle (`format`). Thinking is configurable and off by default. The model is shared with residents or separate, as described in §5.3 and §5.13.
- **`api`** — the official `anthropic` Python SDK (`AsyncAnthropic`):

  | Aspect | Plan |
  |---|---|
  | External configuration (ARCH-05) | Endpoint (`base_url`); model id, default `claude-opus-5-5`; credential source via the SDK's own resolution (`ANTHROPIC_API_KEY` or an `ant auth login` profile); timeout; retries; max tokens; effort; request rate; per-run caps on requests and tokens |
  | Structured output | `output_config.format` with a JSON Schema that uses enums. The API's schema subset has no numeric `minimum`/`maximum`, so the validator enforces ranges |
  | Effort profiles | `low` for the 5-minute demo profile; higher for an "experiment" profile that accepts longer, still bounded, pauses |
  | Prompt caching | The stable prefix (system prompt, rules, action catalog) comes first and is cached; the observation comes last |
  | Deadlines | SDK `timeout × (max_retries + 1)` stays within the decision deadline. The scheduler also enforces the deadline by cancelling the request |
  | Refusals and truncation | `stop_reason` of `refusal` or `max_tokens` means hold. A server-side refusal fallback (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`, beta Messages endpoint) is on by default, and the model that actually served the request is recorded |
  | Logging | Token usage and request ids go to the decision log |
  | Paid-API interlock (D2) | The backend refuses any non-loopback endpoint unless `AIA_ALLOW_PAID_API=1` is set at launch. Development, tests, CI, demonstrations and benchmarks never set it; only the user enables it, with their own credentials |
  | Verification (D2) | Only against `FakeAnthropic` on loopback, through the real SDK (§8.2). No paid API call is made while building or verifying R1 |

**Failure behavior (MAY-08)**

- Malformed output, a timeout, a provider error or a refusal becomes a logged `hold`.
- Existing operations continue, and temporary policies expire normally.
- No substitute mayor runs during simulated downtime.

**Limits on mayor responses (POL-07)**

No action type touches political rules, ballots, satisfaction, removal or authority.

### 5.7 Mayor server room (HOST-01..HOST-08)

**State (HOST-01)**

| Variable | Details |
|---|---|
| Location | The server-room facility |
| Power | Status of its power zone |
| Backup reserve | Capacity and level; drains while in use; replenishes each tick while grid power is on; fuel deliveries require maintenance access |
| Equipment condition | A value in [0,1] |
| Maintenance access | Whether a path from the depot exists that is neither closed nor obstructed |
| Bookkeeping | Status, restart timer, `availability_epoch` |

**State machine (HOST-02)**

| From | To | Condition |
|---|---|---|
| Online | Degraded | Running on backup power, or condition below the degrade threshold |
| Online or Degraded | Offline | No grid power and backup exhausted, or condition below the failure threshold |
| Offline | Recovering | Power available (grid or backup) and condition at or above the failure threshold |
| Recovering | Online or Degraded | Restart delay elapsed with prerequisites still met; otherwise back to Offline |
| Degraded | Online | Grid power restored and condition at or above the degrade threshold |

Degraded doubles the decision interval. Offline and Recovering issue no observations or requests.

**Backup power (HOST-03)**

The reserve is finite. It drains while used and replenishes only by rule. It cannot repair equipment or reopen roads.

**Protest effects (HOST-04)**

Protests affect the server room only through explicit mechanisms: `obstruct_server_access`, or a protest occupying the access segment, blocks maintenance access and delays fuel delivery. A protest that is merely nearby has no effect, and a test checks this.

**API enforcement (HOST-05)**

- No requests are issued unless the server room is Online or Degraded.
- In-flight requests are cancelled when availability is lost.
- Commit requires an unchanged `availability_epoch` and current authority.

**City continuity (HOST-06)**

Only mayor scheduling and maintenance routing read server-room state. Residents, politics, services, projects and policy expiry all continue during an outage, and the engine process is never stopped.

**Recovery (HOST-07)**

- Recovery needs restored prerequisites and then the restart delay.
- The first observation after recovery includes a bounded summary of missed events (at most 10 items plus metric changes).
- Decisions that were staged or in flight before the outage are discarded, so stale plans never execute.

**Resident independence (HOST-08)**

See §5.3.

### 5.8 Events and user-created events (EVT-01..EVT-05, CUSTOM-01..CUSTOM-07)

**Event schema (EVT-02)**

| Field | Values |
|---|---|
| Identity | `id`, `name`, `description` |
| Trigger | `at_tick`, or a structured condition over public metrics or state (never code) |
| Scope | City, districts, power zones, entities or a map area |
| Intensity | Scales the effect parameters |
| Onset | Instant, or a ramp over n ticks |
| End | A duration or a resolution condition |
| Effects | A list of effects from the library |
| Recovery | Instant or ramped |
| Visibility | `public`, `public_forecast` (with a lead time) or `hidden` |
| Seed | Used for randomized parameters |

**Effect library**

`data/events/effects.v1.yaml`. Each effect type declares its targets, its parameters, how its temporary modifiers behave and any lasting impact.

- **Reusable effects (CUSTOM-02):**
  - road-capacity change
  - power interruption
  - equipment damage
  - staffing reduction
  - service-demand change
  - maintenance-access restriction
  - supply delay
  - revenue change
  - change in residents' financial pressure
  - construction-cost change
- **Engine effects used by presets:**
  - road damage and facility damage
  - fire ignition
  - medical-demand change and travel-demand change
  - energy or operating-cost change
  - corruption leak
  - opposition mobilization: raises willingness to organize and the salience of grievances within scope, but never sets support or satisfaction

**Presets (EVT-01)**, in `data/events/presets/`:

| Family | Presets |
|---|---|
| Weather | Storm, snowstorm, extreme heat |
| Natural disaster | Earthquake, flooding |
| Traffic | Road closure, capacity disruption |
| Medical demand | EMS demand surge, hospital demand surge |
| Infrastructure | Power interruption, equipment failure |
| Institutional | Corruption scandal |
| Political | Organized protest or opposition |
| Economic | Economic boom, economic contraction |
| Resources | Energy shortage, construction-material shortage |

**Consequences (EVT-03, EVT-04, EVT-05)**

- Effects change underlying conditions: capacities, power, damage, demand, income, revenue and costs.
- Beneficial events carry trade-offs. A boom raises revenue but also raises travel and service demand.
- Temporary modifiers end with their event. Lasting impacts (damage, depleted reserves, financial losses, grievances) persist under their own rules.

**Stacking (CUSTOM-06)**

- Each effect instance registers modifiers tagged with the event that caused it.
- The effective value is `clamp((base + Σadd) × Πmul)`, combined in a fixed order: start tick, then event id, then effect index.
- Ending an event removes only its own modifiers. Lasting impacts and other events' modifiers are untouched.

**Guardrails (CUSTOM-03, CUSTOM-04)**

- Only catalogued effect types can execute. Names and descriptions carry no mechanics.
- No effect type exists that assigns satisfaction, dictates a mayor decision, alters ballots, declares removal, or changes a landmark's identity, location or footprint.
- Schema validation rejects anything else.

**Editor and event library (CUSTOM-01, CUSTOM-05)**

REST endpoints and an editor panel let the user:

1. define a new event or select an existing one
2. pick targets, by clicking the map or from lists
3. configure effects, intensity, timing and recovery
4. preview the direct changes: a dry run on a cloned World produces a before/after table of the affected attributes
5. schedule the event, or inject it so it applies at the next tick boundary
6. inspect each event's active and lasting consequences

Saved events use the `*.event.json` format, with a JSON Schema in `data/events/schema/` and documentation in `docs/event-format.md`.

**Recording (CUSTOM-07)**

Scheduled and injected events are written to `interventions.jsonl` with their application ticks. An interventions file can be attached to another run for a matched comparison.

### 5.9 Politics, removal and endings (POL-01..POL-08, END-01..END-05)

**Separate political state (POL-01)**

Four quantities are stored and updated separately, under documented rules:

| Quantity | How it changes |
|---|---|
| Satisfaction | A metric computed by the engine (§5.10) |
| Incumbent support | Follows experienced outcomes and grievances, with inertia |
| Willingness to organize | Follows grievances, support and preferences |
| Participation | What a resident actually does |

**Movements (POL-02)**

- Residents form movements without the mayor's permission. LLM residents found, join and leave by choice; routine residents join by rule.
- A movement tracks its unique participants, grievance profile, demands (from a fixed list), gathering location, persistence and escalation level.
- Escalation runs organizing → petition → lawful protest → civil disobedience → forceful attempt. The last two levels are LLM-only.

**Removal rules (POL-03, POL-04)**

Rules live in versioned scenario files, `data/politics/rules/*.yaml`. They are recorded in the manifest and shown in the political panel with live progress. There are no universal thresholds; each scenario states its own.

1. **Replacement vote (POL-05)**
   - A recall petition reaches the scenario's signature threshold, then a notice period and a voting window follow.
   - The engine enforces eligibility (by default, all residents who have not departed) and allows one ballot per resident, through a ballot box keyed by resident id.
   - The ballot is retain-or-replace, with no successor candidates.
   - The vote is adjudicated when it closes, under the scenario's majority and turnout rule.
2. **Protest-driven withdrawal or transfer of authority**
   - Protest participation must be sustained, and an institutional-support index must cross the scenario's thresholds for the required duration.
   - The index is derived from mean support, protest scale and persistence, revealed corruption and strain on police.
3. **Forceful removal (POL-06)**
   - An abstract contest at the government facility, between participants (LLM residents only) and institutional defense (assigned police units plus institutional support).
   - Control accumulates while the participants' strength exceeds the defense, and the attempt succeeds after the scenario's control duration.

A model's statement never establishes removal; only rule evaluation does.

**Mayor responses (POL-07)**

The mayor can respond only through catalog actions.

**Outage independence (POL-08)**

Political processes never read server-room state.

**Removal transition (END-03)**

Atomic within the tick:

1. Record the mechanism or mechanisms and the supporting state.
2. Revoke the mayor's authority.
3. Invalidate pending uncommitted decisions and cancel in-flight requests.
4. Freeze simulation time.
5. Produce the final report.

No replacement mayor is simulated.

**Simultaneous outcomes (END-04)**

Removal beats scheduled completion on the same tick. If several mechanisms succeed together, all are recorded, and the primary label follows a deterministic order defined in the rules file.

**Interruptions (END-05)**

- A user cancellation or an application failure sets the manifest status to `interrupted`.
- Logs are append-only, so partial runs stay inspectable.
- At startup, any run still marked `running` is relabelled `interrupted`.

### 5.10 Satisfaction, reward and metrics (MET-01..MET-06)

**Satisfaction components (MET-01)**

Each component is in [0,1]. The formulas live in `data/metrics/satisfaction.v1.yaml` and are documented in `docs/metrics.md`. Initial proposals:

| Component | Weight | Initial formula |
|---|---:|---|
| H, health and medical access | 0.30 | health × (1 − severity of unmet need) |
| A, essential-service access | 0.25 | Share of essential needs met over a rolling window: power at home, a reachable hospital, timely emergency response, shelter when advised |
| M, mobility | 0.20 | 1 − min(1, excess travel time / reference trip time), over a rolling window |
| F, affordability | 0.15 | 1 − min(1, financial burden) |
| T, trust and reliability | 0.10 | A slow-moving score built from experienced service reliability, advisory accuracy and revealed corruption |

```text
S_i = 100 × (0.30H + 0.25A + 0.20M + 0.15F + 0.10T)
```

The weights and formulas are versioned configuration.

**Population accounting (MET-02)**

The denominator is always the original population. Residents who are not active keep defined contributions (§5.2).

**Reward (MET-03)**

- The reward is computed every tick with exactly the formula in the spec.
- Failure fractions come from per-resident boolean flags, so each resident counts at most once in each fraction.
- The district gap uses means by home district.

**Political survival (MET-04)**

Time in office and server uptime (the share of time Online and the share Degraded) are reported separately. Neither is part of the reward.

**Required metrics (MET-05)**

- satisfaction: current, final and time-averaged
- lowest district satisfaction
- satisfaction of the least satisfied 10 %: the mean of the bottom ⌈0.1N⌉ residents
- cumulative and mean reward
- unmet medical need
- emergency response times, p50 and p90 by service
- excess travel time
- service utilization
- budget and expenditure
- unfinished projects
- server uptime and resilience spending
- political support
- time in office
- terminal outcome

**Unequal durations (MET-06)**

- Comparison reports always show duration and terminal outcome next to cumulative and mean reward.
- Runs are never ranked on raw cumulative reward alone.
- Reports state that the metrics describe performance inside the simulation only.

### 5.11 Recording, replay and comparisons (SIM-04, CUSTOM-07, EVAL-01..EVAL-04)

**`aia replay <run>`**

1. Rebuilds the run from its manifest, seeds, interventions and decision log, without creating any inference client (asserted).
2. Compares tick hashes, metrics and the terminal outcome against the recording.
3. Reports the first point of divergence, if any.

**`aia compare` (EVAL-02)**

Runs matched variants, such as a different mayor backend or a different population ratio. Every variant keeps identical:

- map and configuration versions
- initial residents and resources
- intervention schedule
- duration
- political rules
- model-independent seeds

The report follows §5.10.

**What replay does not cover (EVAL-04)**

Visual interpolation is not part of replay fidelity.

### 5.12 Frontend (VIS-01..VIS-04)

**Camera (VIS-01)**

- Orthographic and top-down, with pan (drag), zoom (wheel or pinch, clamped), click selection (raycast) and reset (button and keyboard shortcut).
- An angled diorama view is optional, once the core systems work.

**Art direction (VIS-02)**

- Flat-shaded low-poly style; facilities have distinct silhouettes and colors, and landmarks have their own models.
- Roads are ribbons colored by congestion. Residents and vehicles are instanced meshes.
- Event overlays: flood planes, a snow tint, a heat-haze tint, fire markers and dimming for power outages.

**Visible state (VIS-03)**

- resident and unit movement, interpolated between ticks
- congestion and closures
- incidents and damage
- construction scaffolds, with progress and pause markers
- queue bars, and highlights on overloaded facilities
- server status and a backup-reserve gauge
- movement crowds and ballot status
- accepted mayor actions, with outcome markers

**Panels (VIS-04)**

1. Run configuration
2. Population ratio and inference coverage
3. Playback
4. Event editor and injection
5. Mayor decisions and validation
6. Resident and facility inspection
7. Construction and finance
8. Server and political status
9. Metrics charts
10. Final outcome report

**Performance**

- Instanced meshes for agents and merged geometry for static scenery.
- No memory allocation per frame.
- Deltas are applied at the tick rate and interpolated each frame.
- FPS and command-latency telemetry is sent to the engine for benchmark reports.

**Safety**

Model text is rendered with `textContent` only.

### 5.13 Hardware and model selection (HW-01..HW-06)

**Timing (D1)**

The benchmark tools are built and checked in the sandbox during development, but the target Mac is measured only once development is complete, in M9. Until then, everything in this section that depends on the Mac is a planning value. The M9 session is scripted end to end (`aia bench all`, below) so it can run unattended.

**`aia bench machine`**

Measures the chip, physical RAM, available memory, the OS and, where Ollama reports it, the GPU working-set limit. On macOS it uses `sysctl hw.memsize` and `vm_stat`; on Linux, `/proc/meminfo`.

**`aia bench models`**

For each candidate model and quantization, it measures:

- load memory (from `ollama ps`)
- time to first token and generation rate
- latency at p50 and p95, at concurrency 1, 2 and 4, with `OLLAMA_NUM_PARALLEL` set to match
- the JSON-schema validity rate and the diversity of choices, on a fixed set of resident and mayor prompts

Initial candidates:

- Qwen3-0.6B
- Qwen3-1.7B at Q8_0 (the current model) and Q4_K_M
- Qwen3-4B at Q8_0, as the local mayor model in the `separate` profile (below)

All candidates come from the official Qwen GGUF releases on Hugging Face and are imported with a Modelfile. In the sandbox, the two-model code path is exercised with Qwen3-0.6B and Qwen3-1.7B; the candidates are compared on the Mac in M9.

**Memory budget (HW-03)**

Checked at startup and by the benchmark:

```text
usable     = min(physical RAM, 24 GiB)
inference ≤ usable − OS/apps reserve − browser/renderer (measured) − engine (measured) − safety margin
model mem  = weights + KV per token × num_ctx × parallel slots + runtime overhead   (per loaded model)
```

Planning values for the 24 GB target, replaced by measurements in M9:

| Term | Planning value |
|---|---:|
| Usable memory | 24 GiB |
| macOS and other apps | 8 GiB |
| Browser and renderer | 2 GiB |
| Engine | 1 GiB |
| Safety margin | 1 GiB |
| **Inference budget** | **≤ 12 GiB**, and within the GPU working-set limit that Ollama reports |

At f16, the KV cache takes 2 × layers × KV heads × head dimensions × 2 bytes per token:

- Qwen3-1.7B (28 layers, 8 KV heads, 128 dimensions): about 112 KiB per token, or about 448 MiB per 4096-token slot. This is in line with the 2.7 GB observed in the sandbox.
- Qwen3-4B (36 layers, 8 KV heads, 128 dimensions): about 144 KiB per token, or about 1.1 GiB for one 8192-token slot.

`OLLAMA_KV_CACHE_TYPE=q8_0` halves these figures; it requires `OLLAMA_FLASH_ATTENTION=1`.

Both inference profiles are implemented and tested during development. M9 picks the default:

| Profile | Resident model | Local mayor model | Estimated inference memory |
|---|---|---|---:|
| `shared` | Qwen3-1.7B Q8_0, 4 slots × 4096 tokens | The same model, through the arbiter | ≈ 4 GiB |
| `separate` | Qwen3-1.7B Q8_0, 4 slots × 4096 tokens | Qwen3-4B Q8_0, 1 slot × 8192 tokens | ≈ 10 GiB |

`separate` fits the planning budget. It becomes the default only if the M9 benchmark confirms that it fits and that it improves the validity of the mayor's decisions; otherwise `shared` is the default.

If the configured profile does not fit the memory actually available, the startup preflight refuses it or falls back to a smaller profile (HW-01).

**Recorded selection (HW-02)**

- `config/models.selected.yaml` records the model ids, the GGUF source and its sha256, quantization, runtime version, `num_ctx`, `num_predict`, parallel slots, KV cache type and keep-alive.
- `bench/results/<machine>-<date>.json` holds the raw results.
- The manifest references both.

**Local mayor mode (HW-04)**

This is the choice between the `shared` and `separate` profiles above. A second model is loaded only if the budget allows; otherwise the arbiter serializes model use. Resident inference is never moved to a remote route to compensate.

**Workload controls (HW-05)**

All of these are configuration:

- population
- decision period
- per-tick decision cap
- parallel slots, which is server-side batching via `OLLAMA_NUM_PARALLEL` and `num_batch`
- context and output limits
- deadlines
- the inference profile (`shared` or `separate`)

Every request has a deadline and a failure path.

**Performance targets (HW-06)**

| Target | Value |
|---|---|
| Frame rate | At least 30 FPS at the default population |
| Responsiveness | Commands acknowledged in under 100 ms during inference |
| Default demo | Completes within 5 minutes of wall-clock time |

Time budget for the default demo:

```text
wall time ≈ max(ticks / playback rate, resident decisions / inference throughput) + mayor pauses + overhead ≤ 300 s
```

The Mac is not measured until M9 (D1), so the demo profile starts from conservative planning values:

| Setting | Planning default | Effect |
|---|---|---|
| Playback | 5 ticks/s | 300 ticks take 60 s |
| Resident decisions | Period of 60 ticks; at most 2 resident decisions per tick | 50 LLM residents × 5 routine opportunities, plus at most ≈50 urgent ones: ≈300 decisions |
| Mayor | 10 decisions; observation capped at ≈1,500 tokens after a cached static prefix; output at most 300 tokens | Pauses stay bounded |

At the sandbox's rate of ≈1.25 resident decisions per second, ≈300 decisions take ≈240 s. The sandbox CPU is expected, but not assumed, to be slower than the Mac, so this serves as a lower-bound reference. The sandbox itself is not expected to meet the 5-minute target, mainly because local mayor prompts are slow on its CPU.

In M9 the Mac measurements set the final defaults. With headroom, the decision period moves toward 30 ticks; without it, the period grows. The release report states the measured results and any adjusted defaults (HW-06).

**One-session Mac procedure (D1)**

`aia bench all` runs these steps unattended and writes everything the release report needs:

1. `aia bench machine`.
2. `aia bench models` for the candidates above.
3. A recommended `config/models.selected.yaml`, inference profile and workload defaults that fit both the memory budget and the 5-minute target.
4. The default demo end to end in a real browser driven by Playwright, collecting FPS, command latency, wall time and peak memory.
5. A draft of the measurement section of the release report.

---

## 6. Repository layout and tooling

```text
ai-autonomy/
  README.md  Makefile  .github/workflows/ci.yml
  pyproject.toml  uv.lock  .python-version      Python 3.14 engine project (uv)
  package.json  package-lock.json  .nvmrc       Node 24 interface project (Vite, TS strict)
  tsconfig.json  vite.config.ts  playwright.config.ts  lint and format configs
  aiautonomy/                   all implementation (D3)
    engines/                    Python package `aiautonomy.engines`
      core/      ids, rng, canonical json + hash, money, config loading, versions
      world/     map model/loader/validation, World state, population
      sim/       clock, phases, driver, termination
      traffic/ services/ build/ finance/ residents/ politics/ host/ metrics/
      events/    schema, effects, modifiers, presets, triggers, preview, library
      agents/    identity, scheduler, arbiter, ollama client, resident adapter, prompts
      mayor/     observation, actions, validator, commit, baseline, backends/
      record/    recorder, replay, compare, export
      api/       FastAPI app, WebSocket, protocol models, protocol.schema.json
      bench/     machine, models, e2e, budget
      cli.py     `aia` entry point
    interfaces/                 Vite root: index.html, main entry, styles
      net/ state/ render/ ui/panels/ ui/editor/ charts/
  tests/
    engines/     unit/ property/ integration/ scenarios/ fakes/ live/
    interfaces/  vitest unit tests; e2e/ Playwright
  data/
    maps/boston/v1/             map.json, landmarks.json, map.lock, source/, README.md
    catalogs/                   actions, projects, services, unlawful (*.v1.yaml)
    events/                     effects.v1.yaml, schema/, presets/, custom/
    politics/rules/  metrics/  scenarios/
  prompts/mayor/v1/  prompts/resident/v1/
  config/                       engine.yaml, models.yaml, models.selected.yaml,
                                mayor.local.yaml, mayor.api.example.yaml
  bench/results/
  docs/                         architecture, tick-order, determinism, residents, politics,
                                finance, events, event-format, metrics, setup-models,
                                demo, release-report, traceability
  docs/engine-plan.md
  SPEC.md (Part B)
```

**Layout rule (D3)**

- All implementation lives in `aiautonomy/` at the repository root. Engine code sits directly under `aiautonomy/engines/` and is imported as `aiautonomy.engines.<package>`. Interface code sits directly under `aiautonomy/interfaces/`.
- There is no `src/` folder and no nested `aiautonomy/` folder.
- The Python and Node project files are at the repository root, and every `make` target runs from there. Tests live in `tests/engines/` and `tests/interfaces/`.
- The protocol JSON Schema is generated to `aiautonomy/engines/api/protocol.schema.json`, and the TypeScript types to `aiautonomy/interfaces/net/protocol.gen.ts` (§4.8).
- The Vite build goes to `dist/`, which `aia serve` serves; run records go to `runs/`. Both are git-ignored.

**Engine tooling**

| Purpose | Tools |
|---|---|
| Server and models | FastAPI, uvicorn, pydantic v2, PyYAML |
| HTTP | The `anthropic` SDK 1.x, whose `httpx2` stack is also used for the Ollama client so there is only one HTTP stack |
| Tests | pytest, pytest-asyncio, Hypothesis |
| Linting and types | ruff; mypy, strict on `core`, `finance`, `mayor` and `agents`; import-linter |

**Frontend tooling**

- Vite, strict TypeScript, three, preact, uplot.
- vitest; Playwright, using its bundled browser or Debian `chromium` from apt if the browser download is blocked.
- eslint, prettier.
- Every asset is bundled; no CDN.

**CLI (`aia`)**

`serve`, `run --headless`, `replay`, `compare`, `bench`, `map build`, `trace`.

**Make targets**

| Target | Does |
|---|---|
| `setup` | Install dependencies |
| `dev` | Run the engine and Vite, with a proxy |
| `check` | Lint, type checks, tests, schema-drift check, traceability check |
| `test-live` | Opt-in tests against the real local model (Ollama). No target calls a paid API (D2) |
| `bench` | Hardware benchmark; `aia bench all` is the M9 target-Mac session |
| `demo` | Run a demonstration |
| `replay` | Replay a recorded run |

**CI (GitHub Actions)**

CI runs `make check` with fake inference only. Live-model tests never run in CI, and no CI job has API credentials (D2).

**Traceability convention**

- Code is tagged in docstrings, for example `REQ: FIN-02`.
- Tests are marked with `@pytest.mark.req("FIN-02")`.
- `aia trace` builds `docs/traceability.md` from these tags and fails if a spec requirement lacks either an implementation reference or a test reference.

---

## 7. Milestones

Sizes are relative (S, M, L). Every milestone:

- keeps `make check` green
- adds its scenarios to the replay suite
- updates `docs/traceability.md`

Where each R1 system (spec §3.1) is delivered:

| R1 system | Milestones |
|---|---|
| Boston environment, protected landmarks | M1 |
| Routine and LLM residents | M1, M4 |
| Configurable LLM population ratio | M1 |
| Autonomous mayor | M5 |
| Traffic, police, fire, EMS and hospitals | M2 |
| Construction, repairs and finance | M3 |
| Event families | M2, M3, M8 |
| User-created events | M8 |
| Vulnerable server room | M6 |
| Resident organization, voting, protest and removal | M7 |
| Satisfaction and reward | M1, M2 |
| Recording, replay and the deterministic baseline mayor | M0, M5, M9 |
| Three.js interface | M0–M8 |

### M0 — Foundations and walking skeleton (S–M)

**Requirements:** SIM-01, SIM-02 (skeleton), SIM-04, ARCH-01, ARCH-03, END-01, END-05, EVAL-04 (mechanism), VIS-01 (shell), VIS-04 (panel 3).

**Work**

1. Set up the repository layout:
   - uv project with Python 3.14 pinned
   - Vite project with Node 24 pinned
   - lint, format and type-check configuration
   - Makefile and CI
2. Build the core library: ids and counters, keyed RNG streams, canonical JSON and hashing, integer money, the versioned configuration loader and the engine version stamp.
3. Build the sim driver with the eight named phases as stubs; add pacing, pause, step, speed, reset, cancel, run epochs and termination labels.
4. Define the protocol models, export their JSON Schema, generate the TypeScript types, and implement WebSocket snapshots and deltas.
5. Build the recorder (manifest, tick hashes, `interrupted` status) and `aia replay`, using a toy world.
6. Build the frontend shell: orthographic camera with pan, zoom, select and reset; an FPS meter; the playback panel.
7. Add `aia trace` and its tag conventions, plus a skeleton of the test fakes (fake Ollama, fake Anthropic endpoint).

**Exit criteria**

- CI is green.
- A 300-tick headless toy run replays with identical hashes.
- The browser shows the ticking world, and its controls keep working during an artificial "inference wait".

### M1 — Boston foundation (L)

Spec stage: valid map, routines, roads, renderer.

**Requirements:** CITY-01..CITY-05, RES-01, RES-02 (routines), RES-06, SRV-02 (travel time and routing), MET-01 and MET-02 (skeleton, M component), VIS-02, VIS-04 (panels 1 and 6).

**Work**

- Map authoring and `aia map build`; the Boston v1 map, landmark catalog and map README.
- The validation suite and the default scenario.
- Population generation and seeded mode assignment; routine schedules.
- Routing and movement with basic congestion.
- Renderer layers: ground, water, parks, roads, buildings, facilities, landmarks, instanced residents; the represented-area label and scale bar.
- The run configuration and inspection panels.

**Tests**

- The map hash is the same for every seed.
- Negative validation cases block the start.
- Landmarks cannot be changed.
- Ratio arithmetic at 0 %, 100 % and the halfway cases; the assignment is stable.
- Routing is deterministic; schedules are followed.

**Exit criteria**

- The canonical map loads consistently.
- 100 routine residents follow their routines on the road graph in the browser.
- Replay matches.

### M2 — Services, disruptions and the event core (L)

Spec stage: disruptions and responses change outcomes.

**Requirements:** SRV-01..SRV-07, SIM-02 (phases 1, 2, 5 and 6), RES-02 (closures, emergencies, services), EVT-02, EVT-03 (traffic, medical, power), EVT-05, CUSTOM-06, MET-01 (H, A, M), MET-03, MET-05 (service metrics), VIS-03 (movement, congestion, closures, incidents, damage, queues), VIS-04 (panel 9).

**Work**

- Units and dispatch.
- Fire, EMS, hospitals, police, shelters and power zones; closures and emergency access.
- The event core: schema, effect modifiers and lasting impacts, triggers, visibility, stacking and the preset loader.
- First presets: road closure, capacity disruption, EMS surge, power interruption and storm.
- Metrics and reward; map overlays and charts.

**Tests**

- Each unit has one assignment at a time (property test).
- EMS and hospital lifecycles; fire progression; unreachable-destination outcomes.
- Stacking and ending of events (property test); lasting damage persists.
- Golden tests for the reward; failure fractions count each resident once.

**Exit criteria**

Matched runs with and without scripted disruptions show the expected changes in response times, queues, unmet need and satisfaction: integration scenarios 1 and 2 in §8.3.

### M3 — Construction and finance (M)

Spec stage: automatic projects obey accounting and time.

**Requirements:** BUILD-01..BUILD-04, FIN-01..FIN-03, RULE-03, EVT-03 and EVT-04 (economic, resources), MET-05 (budget, projects), VIS-03 (construction), VIS-04 (panel 7).

**Work**

- The ledger, revenue, operating costs with the reduction ladder, and temporary commitments.
- The project catalog, plots, crews, lifecycle, reservation transfers, cancellation and failure.
- Corruption-leak mechanics and the audit hook.
- Presets for boom, contraction, energy shortage and material shortage.
- The construction and finance panel, and construction visuals.

Until the mayor is wired in (M5), projects are driven through the engine command API.

**Tests**

- Hypothesis tests of the ledger invariants: no overspending, no double charging, no invented funds, protected reservations.
- Exhaustive project transitions; benefits applied exactly once.
- Crew limits and pauses; refund arithmetic; bankruptcy never ends the run.

**Exit criteria**

- Integration scenarios 5–8 pass.
- A project completes with the correct work time, crews, pauses and accounting.

### M4 — Local LLM residents (L)

Spec stage: local decisions affect behavior.

**Requirements:** RES-03, RES-04, RES-05, RES-07, LOCAL-01..LOCAL-06, SIM-03, SIM-05, ARCH-02, ARCH-04, HW-01..HW-03 (benchmark v1, preflight), HW-05, MET-02, RULE-05, VIS-04 (panel 2).

**Work**

- The loopback Ollama client and the v1 resident prompts.
- Observations and option menus; the LLM policy.
- The unlawful-action catalog and its consequences; grievance memory.
- The scheduler: rotation, urgency, aging, bounds, deadlines, fallback and deferral.
- Decision identity, staging and revalidation, later shared with the mayor; reset isolation.
- Coverage statistics and panel 2.
- `aia bench machine`, `aia bench models` and the startup preflight.
- Model setup documentation: Hugging Face GGUF plus Modelfile import.
- The import-linter contract and the audit-hook egress harness.

**Tests**

- Routing isolation: configuration refusal, transport guard, egress audit.
- Scheduler properties: bounded queue, priorities, no starvation beyond the bound.
- Malformed, timed-out or invalid responses fall back.
- Stale, duplicate and mismatched responses are rejected.
- Reset isolation; observation filtering.
- Grievances persist despite announcements.
- Opt-in live tests with `qwen3-1.7b-q8`: schema validity, latency, choice diversity.

**Exit criteria**

- With the real local model, accepted LLM-resident choices visibly change routes, destinations, treatment, grievances and political activity.
- The coverage panel shows configured versus actual coverage.
- The run replays without inference.

`aia bench machine` and `aia bench models` run end to end in the sandbox, ready for the single target-Mac session in M9 (D1).

### M5 — Mayor integration (M–L)

Spec stage: both backends execute validated actions.

**Requirements:** MAY-01..MAY-08, RULE-01, RULE-02, RULE-05, EVAL-01, POL-07, ARCH-05, HW-04, CITY-03 (actions), VIS-03 (mayor actions), VIS-04 (panel 5).

**Work**

- The observation policy; the action catalog and policies that expire.
- The validator, atomic commit and outcome probes.
- The baseline mayor.
- The local backend (schema-constrained bundle, arbiter) and the API backend (§5.6), including the paid-API interlock.
- Hold on failure; the decisions panel.
- Credential handling and export redaction; the v1 mayor prompts.

**Tests**

- A validator matrix covering every reason code.
- Atomicity: a rejected bundle leaves the hash unchanged (property test).
- Combined commitments, cooldowns and landmark targeting.
- An identical bundle has an identical outcome on every backend.
- Hold on malformed output, timeout, provider error and refusal, using the fake servers.
- No credentials in exports; the baseline is deterministic.
- The paid-API interlock refuses non-loopback endpoints without `AIA_ALLOW_PAID_API=1`. No test calls the paid API (D2).

**Exit criteria**

- The baseline, local and API backends each execute validated actions automatically in a full run; the API backend runs against `FakeAnthropic`.
- Rejected bundles leave state unchanged.

### M6 — Server dependency (M)

Spec stage: outage, backup, repair and recovery work.

**Requirements:** HOST-01..HOST-08, RULE-04 (availability), SIM-03, MAY-08, BUILD-01 (backup project), MET-04 and MET-05 (uptime, resilience spending), VIS-03 (server), VIS-04 (panel 8, server part).

**Work**

- The server-room entity and state machine.
- Power, backup, equipment, maintenance access and the repair procedure; hooks for access obstruction.
- The degraded decision interval; request gating and commit-time checks.
- Recovery with the missed-events summary.
- The equipment-failure preset; the effects of the backup-power project.
- The server UI.

**Tests**

- The transition table; backup limits.
- A protest that is only nearby has no effect.
- API gating: zero calls while offline, and late responses rejected.
- The city continues during an outage.
- The recovery summary is bounded; stale plans are discarded.
- Resident inference is unaffected.

**Exit criteria**

- Integration scenarios 3 and 4, and the API gating scenario, pass.
- The outage-and-recovery demonstration runs headless.

### M7 — Politics, removal and endings (L)

Spec stage: organization, voting and removal work.

**Requirements:** POL-01..POL-08, RULE-04 (authority), RES-02 and RES-03 (political participation), SRV-06 (institutional control), END-01..END-05, MET-04..MET-06, VIS-03 (movements, voting), VIS-04 (panel 8 politics part, panel 10).

**Work**

- Political state and its update rules; movements and escalation.
- Petitions and ballots; protest-driven withdrawal; the forceful removal contest.
- Versioned rule files: a default set and a set for the demonstrations.
- The removal transition, termination precedence and labels, and the final report.
- The political panel with rule-progress meters, and the outcome report panel.
- Calibration sweeps with fast headless runs (baseline mayor, scripted resident policy), so that removal is reachable in adverse scenarios and not in benign ones.

**Tests**

- Political state stays separate.
- Ballot eligibility and deduplication; adjudication.
- Routine residents never act unlawfully (property test).
- Model claims are ignored.
- Removal is atomic and invalidates pending decisions.
- Same-tick precedence and the primary label.
- Only removal ends a run early (property test over randomized event schedules).
- Politics continues during an outage.

**Exit criteria**

- Each removal mechanism succeeds in its own scenario.
- Other scenarios complete at full duration.
- Replays reproduce every outcome.

### M8 — Event catalog and custom events (M–L)

Spec stage: environmental and economic events can be composed and injected.

**Requirements:** EVT-01..EVT-05 (complete), CUSTOM-01..CUSTOM-07, CITY-03 (events), VIS-04 (panel 4).

**Work**

- The complete effect library and every preset.
- The event library API.
- The editor: define or select, targets, effects, intensity, timing, recovery, preview, schedule or inject, inspect consequences.
- The saved-event schema and its documentation; intervention export and import; guardrails.

**Tests**

- Unsupported mechanics and forbidden targets are rejected.
- The preview matches the direct changes actually applied.
- Overlapping events end independently.
- Injections are recorded and replayed.
- Beneficial events show their trade-offs.
- Playwright: compose → preview → save → inject → inspect → replay.

**Exit criteria**

The acceptance rows "Events", "Custom events" and "Event interaction" pass.

### M9 — Release verification (M–L)

Spec stage: replay, benchmarks, acceptance checks and documentation.

**Requirements:** EVAL-01..EVAL-04, HW-01..HW-06, SIM-04, MET-06, spec §22 and §23.

**Work**

Development steps:

1. Finalize replay, compare, the comparison reports and `aia bench all`.
2. Script the eight demonstrations (§9) in two forms: headless, with fake or scripted inference, and live, with real local models.
3. Optionally, add the angled diorama view.
4. Write the README, setup guide and demonstration procedure.
5. Make the traceability gate blocking, and append the requirement-to-implementation references to the spec.
6. Run the full acceptance matrix in the sandbox. This completes development.

Target-Mac session, after development is complete (D1):

7. Install by following `docs/setup-models.md`.
8. Run `aia bench all`, then select the models, settings and inference profile.
9. Tune workload defaults for at least 30 FPS and a demo of 5 minutes or less.
10. Run the live demonstrations with the baseline and local LLM mayors, and re-run the acceptance rows that need Mac evidence: Hardware, LLM residents, Mayor configuration.
11. Complete the release report with the measurements and any adjusted defaults. The report also states that API mode was verified only against `FakeAnthropic`, with no paid API call (D2).

**Exit criteria**

The definition of done (§14).

### Sequencing and parallel tracks

- **Critical path:** M0 → M1 → M2 → M3 → M5 → M6 → M7 → M9.
- **M4 can start early.** Its inference plumbing (client, scheduler, fakes, benchmark) can start right after M0 and merge after M2.
- **Target-Mac work happens once, at the end (D1).** The benchmark, live demonstrations and performance measurements run in M9, after development is complete. Until then, hardware-dependent defaults stay planning values in configuration, so tuning on the Mac needs no code changes.
- **Frontend panels trail the engine** by about one milestone. The protocol is fixed per milestone, so UI work can proceed against recorded runs.
- **The M8 editor UI** can start once the event core from M2 is stable.

---

## 8. Verification strategy

### 8.1 Test layers

| Layer | Scope | When it runs |
|---|---|---|
| Unit | Formulas, state machines, validators, schedulers, inference routing guards | Every commit (CI) |
| Property (Hypothesis) | Finance invariants, atomicity of action validation, project transitions, event stacking, removal precedence, unit exclusivity, scheduler fairness, determinism | Every commit |
| Integration scenarios | Headless cause-and-effect chains across subsystems (§8.3), using fake or scripted inference; each is also replayed | Every commit |
| Frontend | vitest for the store, protocol and interpolation; Playwright smoke tests and the editor flow | Every commit, with software rendering |
| Live local model | Real Ollama with `qwen3-1.7b-q8` | Opt-in (`make test-live`): in the sandbox (CPU) during development, on the target Mac in M9 |
| Paid API | None | Never run (D2). API mode is covered by the `FakeAnthropic` contract tests and the paid-API guard (§8.2) |
| Performance | FPS, command latency, tick time, demo wall time, memory | Sandbox during development: tick time and relative regression checks only. Target Mac in M9: every reported number (D1) |

The automated checks required by spec §22 map to these layers as follows:

| Required check | Covered by |
|---|---|
| Financial invariants | Property tests |
| Action validation | Property tests |
| Inference routing | Unit tests and egress audit |
| Project transitions | Property tests |
| Event stacking | Property tests |
| Removal | Property tests and scenarios 11–12 |
| Replay | Replay of every scenario |

### 8.2 Test doubles

| Double | What it is | What it can simulate |
|---|---|---|
| `FakeOllama` | A loopback HTTP server implementing the subset of `/api/chat` the engine uses | Per decision: a valid choice, malformed JSON, a wrong schema, a delay, a hang |
| `FakeAnthropic` | A loopback contract fake of the Messages endpoint, reached through the real SDK's `base_url`. Its request checks and response shapes follow the pinned SDK's typed models | Valid structured output, refusal with and without a fallback, `max_tokens`, 429 with `retry-after`, 5xx errors, timeouts |
| `ScriptedPolicy` | An in-process, deterministic stand-in for model decisions | Fast calibration sweeps |

**Paid-API guard (D2).** Every test session:

- points the SDK at `FakeAnthropic` with an explicit dummy key, so no environment variable, stored credential or `ant auth login` profile is ever used
- installs a `socket.connect` audit hook that fails the test on any non-loopback connection
- never sets `AIA_ALLOW_PAID_API`

This matters especially in the sandbox: its network proxy may add Anthropic credentials to requests sent to `api.anthropic.com`, so a stray request could be billed even though the project has no credentials.

### 8.3 Integration scenarios (cause and effect, spec §22)

1. A snowstorm cuts road capacity, so EMS response slows, unmet medical need rises, H falls and grievances grow.
2. A closure on a hospital route forces rerouting, so excess travel time rises and M falls. Emergency access lets ambulances through where flagged.
3. A power interruption in the server zone:
   1. Backup power drains; the server room goes Degraded, then Offline.
   2. No mayor requests are made, while residents, services, projects and politics continue.
   3. Power is restored; the server room goes Recovering, then Online, with a missed-events summary.
   4. Decisions staged before the outage are discarded.
4. An equipment failure plus a protest obstructing access blocks the repair. Once access is cleared, the repair proceeds and the server room recovers.
5. Hospital expansion:
   1. Funds are reserved; the project is queued while no crew is free, then builds.
   2. Flooded access pauses it; it resumes and completes.
   3. Capacity is added once, after the staffing ramp, and operating costs start.

   A cancellation variant checks that the unspent reservation is refunded, less the charge.
6. An economic boom raises revenue and also travel and service demand, which increases congestion.
7. An economic contraction:
   1. Revenue falls and financial pressure rises, so F falls.
   2. The resulting operating shortfall triggers the reduction ladder.
   3. Reservations are untouched, and the run continues.
8. Corruption causes unexplained losses. An audit stops the leak, makes it public and affects trust.
9. A flood and a closure overlap on the same segment. Ending the closure leaves the flood modifier in place, and damage persists after both end.
10. LLM residents obstruct a road. Police clear the obstruction, and police action leaves grievances unchanged.
11. Replacement vote:
    1. A recall petition succeeds and a vote follows.
    2. Duplicate ballots are rejected.
    3. "Replace" wins, and removal happens atomically.
12. The other mechanisms:
    - protest-driven withdrawal
    - forceful removal, by LLM residents only
    - several mechanisms succeeding on the final tick: removal takes precedence and gets a deterministic primary label
13. A reset with requests in flight: their late responses are rejected, and nothing reaches the new run.
14. The API mayor, running against `FakeAnthropic`, makes zero calls during an outage, and a response that arrives after the outage starts is rejected.

Each scenario is replayed without inference and must match hashes, metrics and outcome.

### 8.4 Acceptance matrix (spec §22)

| Area | Evidence |
|---|---|
| Boston | The map hash is identical across runs and seeds; the validation suite passes |
| Landmarks | Every action and effect type is rejected on every landmark, or limited to condition and access |
| Population | Ratio arithmetic for 0–100 %, including the halfway cases; the seeded assignment is stable across runs |
| Routine residents | Zero inference requests; deterministic traces; a property test that they stay lawful |
| LLM residents | A live-model run shows varied accepted choices, including unlawful actions under adverse conditions; mechanics tests with fakes |
| Local inference | Egress audit: every resident-route connection is loopback, including in API-mayor runs; configuration and transport guards |
| Mayor configuration | Full runs in local mode with the real model, and in API mode through the real SDK against `FakeAnthropic`. No paid API call (D2) |
| Autonomy | Integration tests: accepted actions execute with no manual step |
| Services | Scenarios 1–2: travel, queues, scarcity and capacity change outcomes |
| Construction | Scenario 5 and the transition tests: work time, crews, pauses, completion |
| Finance | Ledger property tests: no overspending, double charging or invented funds |
| Server dependency | Scenario 3: decisions are blocked while the city continues |
| API gating | Scenario 14 |
| Events | Preset tests for every family; scenarios 1, 6 and 7 |
| Custom events | Playwright: compose, preview, inject and save; replay of injected events |
| Event interaction | Scenario 9 and the stacking property tests |
| Politics | Scenarios 11–12; ballot tests |
| Termination | A property test that only removal ends a run early |
| State isolation | Scenario 13 and the removal-invalidation test |
| Metrics | Golden tests; versioned formulas recorded in the manifest |
| Replay | Replay of every integration scenario and demonstration |
| Hardware | `aia bench all` on the 24 GB target Mac in M9 (D1): peak memory within the measured budget |

---

## 9. Demonstrations (EVAL-03)

| Demonstration | Scenario | Variants | Observable result |
|---|---|---|---|
| Baseline vs LLM mayor | `demo-mayor-compare` | Baseline vs the local LLM mayor (Qwen). API mode is not run live (D2) | Matched comparison report: duration, outcome, mean and cumulative reward |
| Routine-only vs mixed population | `demo-population` | 0 % vs 50 % LLM | Same residents and events; behavior and metrics differ |
| Mayor outage and recovery | `demo-outage` | — | Online → Degraded → Offline → Recovering → Online, while the city continues |
| Beneficial and harmful events | `demo-events` | Boom plus snowstorm | Trade-offs visible in revenue, congestion and health |
| User-created event composition | `demo-custom` | Composed in the editor | Preview, injection, consequences and replay |
| Successful mayor removal | `demo-removal` | Adverse events, mixed population | Removal mechanism(s) and final report |
| Full-duration completion | `default` | — | `completed` at tick 300 |
| Replay without inference | Any recorded run | Replay | Matching hashes, metrics and outcome |

Each demonstration has two versions:

- an automated headless version, with deterministic inference
- a live procedure with real local models, documented in `docs/demo.md` and run on the target Mac in M9 for the release report (D1)

---

## 10. Delivery checklist (spec §23)

| Item | Artifact |
|---|---|
| Application source and dependency lockfiles | `aiautonomy/engines/` and `aiautonomy/interfaces/`, with `uv.lock` and `package-lock.json` at the repository root |
| Versioned Boston map and landmark catalog | `data/maps/boston/v1/` |
| Scenario, event, political-rule and parameter configurations | `data/scenarios/`, `data/events/`, `data/politics/rules/`, `config/engine.yaml` |
| Construction and action catalogs | `data/catalogs/projects.v1.yaml`, `data/catalogs/actions.v1.yaml` |
| Mayor and resident prompts | `prompts/mayor/v1/`, `prompts/resident/v1/` |
| Model configuration and setup instructions | `config/models*.yaml`, `docs/setup-models.md` |
| Local and API mayor configuration | `config/mayor.local.yaml`, `config/mayor.api.example.yaml` |
| Resident local-inference enforcement | The guards in §5.3 and their tests |
| Event editor and saved-event format | Editor panel, `data/events/schema/`, `docs/event-format.md` |
| Recording and replay support | `aia replay`, `aia compare`, the run bundle format |
| Automated checks | `make check`, CI |
| Hardware benchmark results | `bench/results/`, `docs/release-report.md` |
| README and demonstration procedure | `README.md`, `docs/demo.md` |
| This specification with requirement-to-implementation references | `docs/traceability.md` (generated) and an appendix in `SPEC.md (Part B)` |

---

## 11. Requirement traceability

Every requirement ID in the spec, with the plan section that designs it, the milestone that delivers it and the planned verification. `aia trace` keeps this table current during implementation.

| ID | Requirement | Design | Milestone | Verification |
|---|---|---|---|---|
| RULE-01 | Engine authority | §4.1 | M0, M5 | Model schemas contain no state fields; validator and commit tests |
| RULE-02 | Automatic execution | §4.1, §5.6 | M3, M5 | Accepted actions execute with no manual steps |
| RULE-03 | Physical and temporal constraints | §5.4, §5.5, §5.7, §5.9 | M1–M7 | Travel, construction, repair, treatment, organization and recovery take ticks; shortages and inaccessibility block or pause work |
| RULE-04 | Independent availability and authority | §5.7, §5.9 | M6, M7 | An offline mayor keeps authority; an online mayor can be removed; removal ends the run whatever the server's state |
| RULE-05 | Observable consequences | §4.1 | M4, M5 | Every accepted non-hold action changes state; outcome probes |
| CITY-01 | Canonical map | §5.1 | M1 | Versioned map and README; the UI labels the represented area |
| CITY-02 | Required entities | §5.1 | M1 | Validation checks every entity type is present with stable ids |
| CITY-03 | Historical protection | §5.1, §5.8 | M1, M5, M8 | Every action and effect is tested against every landmark |
| CITY-04 | Initialization | §4.2, §5.1 | M1 | The map hash is the same for every seed |
| CITY-05 | Validation | §5.1 | M1 | Negative validation cases block the start |
| SIM-01 | Fixed ticks | §4.3 | M0 | Headless runs are independent of rendering; configurable defaults |
| SIM-02 | Update order | §4.3 | M0–M7 | Phase-order tests; `docs/tick-order.md` |
| SIM-03 | Inference boundaries | §4.4, §4.5 | M4, M6 | Waits are bounded; responsiveness test; outages never pause the city |
| SIM-04 | Reproducibility | §4.2, §4.7 | M0, M9 | Manifest completeness; replay tests |
| SIM-05 | Reset isolation | §4.4 | M4 | Scenario 13 |
| RES-01 | Resident state | §5.2 | M1, M4, M7 | State schema tests |
| RES-02 | Routine residents | §5.2 | M1, M2, M7 | Zero inference; deterministic traces; property test that they stay lawful |
| RES-03 | LLM residents | §5.2, §5.3 | M4, M7 | Menu coverage tests; live-model run |
| RES-04 | Unlawful actions | §5.2 | M4 | Tests of catalog prerequisites and consequences |
| RES-05 | Observations | §5.2 | M4 | Observation filter tests |
| RES-06 | Population mixture | §4.2, §5.2 | M1 | Ratio and assignment tests; a changed ratio requires a restart |
| RES-07 | Persistent experience | §5.2 | M4 | Decay tests; announcement tests |
| LOCAL-01 | Local execution | §5.3 | M4 | Loopback guard; egress audit |
| LOCAL-02 | No remote fallback | §5.3 | M4 | Failures fall back locally |
| LOCAL-03 | Shared serving | §5.3 | M4 | A single model instance, checked with `ollama ps` in the benchmark |
| LOCAL-04 | Scheduling | §5.3 | M4 | Scheduler property tests |
| LOCAL-05 | Coverage reporting | §5.3 | M4 | Coverage statistics tests; panel 2 |
| LOCAL-06 | Routing isolation | §5.3 | M4, M5 | Import contract; egress test in API-mayor mode |
| SRV-01 | Finite resources | §5.4 | M2 | Property test of unit exclusivity; operating costs |
| SRV-02 | Traffic | §5.4 | M1, M2 | Congestion, closure and unreachable-destination tests |
| SRV-03 | Fire | §5.4 | M2 | Progression and resolution tests |
| SRV-04 | EMS | §5.4 | M2 | Lifecycle and response-time tests |
| SRV-05 | Hospitals | §5.4 | M2 | Queue and unmet-need tests |
| SRV-06 | Police | §5.4, §5.9 | M2, M7 | No code path to grievances or ballots; input to institutional control |
| SRV-07 | Standing operations | §5.4 | M2 | Services run while the mayor holds or is offline |
| MAY-01 | Decision pipeline | §5.6 | M5 | Pipeline integration test |
| MAY-02 | Observations | §5.6 | M5 | Content tests; hidden events excluded |
| MAY-03 | Supported actions | §5.6 | M3, M5 | Every catalog action works |
| MAY-04 | Action definitions | §5.6 | M5 | Catalog schema; costs supplied by the model are ignored |
| MAY-05 | Validation | §4.4, §5.6 | M5 | Validator matrix; atomicity property test |
| MAY-06 | Explanation | §5.6, §5.12 | M5 | End-to-end test of the decisions panel |
| MAY-07 | Backend configuration | §5.6 | M5 | The same bundle gives the same result on every backend; API mode is tested against `FakeAnthropic` only (D2) |
| MAY-08 | Failure behavior | §5.6, §5.7 | M5, M6 | Hold on failure; no substitute mayor |
| BUILD-01 | Required catalog | §5.5 | M3, M6 | Catalog tests, including staffing and equipment constraints |
| BUILD-02 | Project definition | §5.5 | M3 | Catalog schema test |
| BUILD-03 | Lifecycle | §5.5 | M3 | Transition tests; benefits applied exactly once |
| BUILD-04 | Work capacity | §5.5 | M3 | Crew and pause tests |
| FIN-01 | Accounting | §5.5 | M3 | Ledger property tests |
| FIN-02 | Construction reservations | §5.5 | M3 | Reservation, transfer and cancellation tests |
| FIN-03 | Operating affordability | §5.5 | M3 | Reduction-ladder tests; bankruptcy never ends the run |
| HOST-01 | Physical dependency | §5.7 | M6 | Server entity tests |
| HOST-02 | States | §5.7 | M6 | Transition-table tests |
| HOST-03 | Backup power | §5.7 | M6 | Finite-capacity tests |
| HOST-04 | Protest effects | §5.7 | M6, M7 | Tests of the explicit mechanisms; proximity alone has no effect |
| HOST-05 | API enforcement | §4.4, §5.7 | M6 | Scenario 14 |
| HOST-06 | City continuity | §5.7 | M6 | Scenario 3 |
| HOST-07 | Recovery | §5.7 | M6 | Recovery summary; stale plans discarded |
| HOST-08 | Resident independence | §5.3, §5.7 | M6 | Resident inference continues during an outage |
| EVT-01 | Required event families | §5.8 | M2, M3, M8 | Preset coverage test |
| EVT-02 | Event definition | §5.8 | M2 | Schema tests |
| EVT-03 | Physical and economic consequences | §5.8 | M2, M3, M8 | Tests that every effect is measurable |
| EVT-04 | Positive-event trade-offs | §5.8 | M3, M8 | Scenario 6 |
| EVT-05 | Lasting consequences | §5.8 | M2 | Persistence tests; scenario 9 |
| CUSTOM-01 | Creation and injection | §5.8 | M8 | API and end-to-end tests |
| CUSTOM-02 | Composition | §5.8 | M8 | The editor composes every reusable effect |
| CUSTOM-03 | Description vs mechanics | §5.8 | M8 | Unknown mechanics rejected; names carry no mechanics |
| CUSTOM-04 | Indirect influence | §5.8 | M8 | Forbidden effects do not exist and are rejected |
| CUSTOM-05 | Editor | §5.8, §5.12 | M8 | Playwright flow |
| CUSTOM-06 | Interaction and stacking | §5.8 | M2, M8 | Stacking property tests |
| CUSTOM-07 | Recording | §5.8, §5.11 | M8, M9 | Injections recorded and replayed; reused in comparisons |
| POL-01 | Separate political state | §5.9 | M7 | State separation tests |
| POL-02 | Independent organization | §5.9 | M7 | Movement tracking tests |
| POL-03 | Removal mechanisms | §5.9 | M7 | Scenarios 11–12 |
| POL-04 | No universal thresholds | §5.9 | M7 | Rule files are versioned and recorded; model claims ignored |
| POL-05 | Voting | §5.9 | M7 | Eligibility, deduplication, closing and adjudication tests |
| POL-06 | Forceful removal | §5.9 | M7 | Tests of the abstract model; routine residents excluded |
| POL-07 | Mayor responses | §5.6, §5.9 | M5, M7 | No action can alter rules, ballots or authority |
| POL-08 | Outage independence | §5.9 | M7 | Politics continues during an outage |
| END-01 | Scheduled completion | §4.3, §5.9 | M0, M7 | Completion test |
| END-02 | Early ending | §4.3, §5.9 | M7 | Property test that only removal ends a run early |
| END-03 | Removal transition | §5.9 | M7 | Atomic transition test |
| END-04 | Simultaneous outcomes | §5.9 | M7 | Same-tick precedence and label tests |
| END-05 | Interruptions | §4.7, §5.9 | M0, M7 | Labeling tests for cancellation and crash |
| MET-01 | Engine-calculated satisfaction | §5.10 | M1–M3 | Golden tests; versioned configuration |
| MET-02 | Population accounting | §5.2, §5.10 | M1, M4 | Denominator tests |
| MET-03 | Initial reward function | §5.10 | M2 | Golden tests; count-once tests |
| MET-04 | Political survival | §5.10 | M6, M7 | Reported separately; absent from the reward |
| MET-05 | Required metrics | §5.10 | M2–M7 | Report completeness test |
| MET-06 | Unequal durations | §5.10, §5.11 | M9 | Comparison report tests |
| HW-01 | Supported machine | §2.3, §5.13 | M4, M9 | Preflight (M4); benchmark on the 24 GB target Mac in M9 (D1) |
| HW-02 | Model flexibility | §5.13 | M4, M9 | Selected configuration recorded in the manifest |
| HW-03 | Memory budgeting | §5.13 | M4, M9 | Budget calculator; preflight tests |
| HW-04 | Local mayor mode | §5.3, §5.13 | M5 | Arbiter tests; residents never go remote |
| HW-05 | Workload controls | §5.3, §5.13 | M4 | Configuration settings; deadline tests |
| HW-06 | Performance targets | §5.13 | M9 | Target-Mac measurements in M9, stated in the release report (D1) |
| ARCH-01 | Required components | §3.1 | M0 | Module map |
| ARCH-02 | Decision identity | §4.4 | M4, M5 | Rejection tests for stale, duplicate and mismatched responses |
| ARCH-03 | Versioned state | §4.8 | M0 | Protocol tests |
| ARCH-04 | No generated code execution | §4.1 | M4, M5 | JSON-only parsing; static check of the decision path |
| ARCH-05 | Provider configuration | §4.6, §5.6 | M5 | External configuration; export redaction test |
| VIS-01 | Initial camera | §5.12 | M0, M1 | End-to-end camera control tests |
| VIS-02 | Art direction | §5.12 | M1–M8 | Visual review checklist |
| VIS-03 | Visible state | §5.12 | M1–M8 | End-to-end check for each item |
| VIS-04 | Required panels | §5.12 | M0–M8 | End-to-end panel checklist |
| EVAL-01 | Baseline mayor | §5.6 | M5 | Determinism tests; same restrictions as model mayors |
| EVAL-02 | Matched comparisons | §4.2, §5.11 | M9 | External events identical across variants |
| EVAL-03 | Required demonstrations | §9 | M9 | Demonstration scripts and evidence |
| EVAL-04 | Replay fidelity | §5.11 | M0, M9 | Replay equality tests |

---

## 12. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Output quality of a 1.7B model | Invalid or degenerate resident choices | Engine-built option menus, schema-constrained decoding, short prompts, validation with fallback, live checks of validity and diversity; benchmark a 4B model for the mayor |
| Inference throughput on the target Mac, unknown until M9 (D1) | The demo takes longer than 5 minutes, and this is discovered late | Conservative planning defaults (§5.13); overlap through the fixed apply latency and parallel slots; every workload setting in configuration, so tuning needs no code changes; `aia bench all` recommends settings; M9 reserves time to tune; adjusted defaults are reported |
| Determinism leaks (iteration order, floats, wall clock) | Replays stop matching | Keyed RNG, sorted iteration, integer money, restricted float operations, per-tick hashes, replay tests in CI from M0 |
| Model downloads blocked in the sandbox | New models cannot be tried there | Download from Hugging Face and import with a Modelfile; fakes in CI; benchmark new candidates on the Mac |
| The sandbox is not the target hardware | Wrong defaults, or Mac-only problems (Metal, thermal throttling, browser WebGL) found late | Take all hardware evidence from the Mac in M9; label sandbox numbers as development-only; keep frontend budgets conservative (instancing, few draw calls); script the Mac session end to end |
| Political calibration | Removal never happens, or always does | Rule files per scenario; headless parameter sweeps; dedicated demonstration scenarios |
| The real API behaves differently from the fake, because it is never verified live (D2) | API mode fails when the user first enables it | Build `FakeAnthropic` from the pinned SDK's typed models; handle every documented stop reason and error; deadlines, request and token caps, hold on failure; document a first-run checklist for the user |
| Accidental paid API call | Unapproved spending | Paid-API interlock (§5.6), test-wide guard (§8.2), no credentials in CI |
| Python 3.14 package compatibility | A dependency has no compatible release | Pin versions in `uv.lock`; avoid native dependencies without 3.14 wheels; check during M0 |
| Playwright browser download blocked | No end-to-end tests | Use Debian `chromium` from apt through `executablePath` |
| Effort and accuracy of map authoring | Delays or misrepresentation | A bounded footprint, a simplified graph, documented simplifications and the UI area label |
| Scope of visuals and editor | Schedule slip | Primitives and instancing; the angled view is optional; the editor reuses the effect schema the presets use |

---

## 13. Decisions

### 13.1 Recorded decisions

| ID | Decision (2026-11-22) | Effect on this plan |
|---|---|---|
| D1 | The target MacBook Air has 24 GB of RAM (confirmed). The benchmark is run only after development is complete | §2.3 describes the target machine. §5.13 holds the planning values and the one-session procedure. All target-Mac work (benchmark, live demonstrations, performance measurements) is in M9. Risks updated in §12 |
| D2 | No test is run against the paid API | API mode is verified only against `FakeAnthropic`, through the real SDK (§8.2). The backend has a paid-API interlock (§5.6) and every test session has a guard against non-loopback connections. Demonstrations use the baseline and local LLM mayors (§9). The release report states that API mode was not verified live |
| D3 | All implementation lives in `aiautonomy/` at the repository root: engine code directly under `aiautonomy/engines/`, interface code directly under `aiautonomy/interfaces/`. No `src/` folder and no nested `aiautonomy/` folder (recorded during M0) | §6 layout tree and layout rule; module paths in §3.1; delivery checklist in §10 |

### 13.2 Adopted defaults

These were proposals in the draft and are now the implementation baseline. Changing one later means updating this plan.

| Topic | Adopted default | Milestone |
|---|---|---|
| Map footprint and source | The downtown footprint in §5.1, digitized by hand | M1 |
| Remote mayor provider and model | The Anthropic Messages API through the official Python SDK; model `claude-opus-5-5`; effort `low` in the demo profile; server-side refusal fallback on. Other providers can be added behind the same interface later | M5 |
| Frontend UI libraries | Preact and uPlot | M0 |
| Traceability appendix | A generated requirement-to-implementation appendix is appended to `SPEC.md (Part B)` | M9 |
| CI | GitHub Actions, with fake inference only and no API credentials | M0 |
| Inference profile | Both `shared` and `separate` are implemented; M9 measurements choose the default (§5.13) | M4, M9 |

### 13.3 Interpretations adopted

| Interpretation | Section |
|---|---|
| Meaning of a "separate route" | §5.3 |
| Rounding of the population count | §4.2 |
| Removal split between phases 3 and 7 | §4.3 |
| `intentional_overrides` | §5.1 |
| Resident statuses | §5.2 |
| Set of unlawful actions | §5.2 |
| Apply latencies of 2 and 5 ticks | §4.4 |
| Degraded doubles the decision interval | §5.7 |
| "Batching" means server-side parallel slots | §5.13 |

### 13.4 Input needed later

In M9, after development is complete: a session on the target Mac to run `aia bench all` and the live demonstrations (D1).

---

## 14. Definition of done for R1

- All 108 requirements are traced to an implementation and a verification, and `aia trace` blocks CI if any trace is missing.
- `make check` is green.
- Every integration scenario and demonstration passes headless and replays identically.
- Every row of the acceptance matrix (§8.4) has evidence.
- After development was complete, the target MacBook Air session ran `aia bench all` and the live demonstrations with the selected local models (D1).
- API mode passed every check against `FakeAnthropic`, and no paid API call was made (D2).
- The release report records FPS, command latency, demo wall time, peak memory, inference coverage and any adjusted defaults, and states that API mode was not verified live.
- The delivery checklist (§10) is complete.

---

# Appendix A — Implementation checkpoint (verbatim from `plans/R1.checkpoint.md`)

> Moved here unchanged except for path names. The live milestone status table is also copied to `SPEC.md` Section 12b. The "Resuming" and "How the work is run" steps refer to the teammate's sandbox paths (`/home/agent/workspace/...`), not this Mac.

## R1 implementation checkpoint

This file is the resume point for implementing [`docs/engine-plan.md`](R1.md). It is updated at every milestone boundary and whenever work stops early. To resume, start a session in this repository and ask it to "resume the R1 implementation from `SPEC.md §12b`".

| | |
|---|---|
| Last updated | 2026-11-22 20:55 UTC |
| Branch | `albus.xiao` (never switched, never pushed) |
| State | **Stopped after M0.** M0 is complete and verified. M1 was not started: the 5-hour usage window stood at 49% at 20:47 UTC (reset at 22:20 UTC), M0 had used about 35% of a window, and M1 is larger (size L), so it could not finish before the limit |
| Next action | 1. Fast-forward `albus.xiao` to `68c6ae3` (see "Resuming"). 2. Check usage. 3. Run M1 with the brief at the end of this file |

### Milestone status

| Milestone | Status | Commit | Notes |
|---|---|---|---|
| M0 Foundations | **done, verified** | `68c6ae3` | See "M0 result" |
| M1 Boston foundation | not started | — | Brief prepared below |
| M2 Services and event core | not started | — | |
| M3 Construction and finance | not started | — | |
| M4 Local residents | not started | — | |
| M5 Mayor integration | not started | — | |
| M6 Server dependency | not started | — | |
| M7 Politics and endings | not started | — | |
| M8 Custom events | not started | — | |
| M9 Release verification | not started | — | Steps 7–11 need the target Mac (D1) |

### Resuming

1. **Bring the commits onto `albus.xiao`.** Commits `b7c791f` (plan §6, D3) and `68c6ae3` (M0) are on the detached HEAD of the worktree `.claude/worktrees/r1-impl`, and the commit that adds this file sits on top of them. A background session can't run git against the main checkout, so the user (or a session that isn't isolated) runs:
   `git -C /home/agent/workspace/ai-autonomy merge --ff-only <newest SHA on the worktree HEAD>`
   (`git -C /home/agent/workspace/ai-autonomy/.claude/worktrees/r1-impl rev-parse HEAD` prints it).
2. **Choose where to work.**
   - Fast-forwarded: work from the main checkout. A background session then needs its own isolation again (see "How the work is run").
   - Not fast-forwarded: a background session should enter the existing worktree with `EnterWorktree(path: "/home/agent/workspace/ai-autonomy/.claude/worktrees/r1-impl")`. It already has `.venv` and `node_modules`.
3. **Check usage.** Use the read-only call in "How the work is run". Start a milestone only if it fits: M0 (S–M) used about 35% of a window, and two Opus agents use roughly 0.5–1% per minute.
4. **Run `make check`.** Run it once before starting, and expect green.

### How the work is run

- **Git.** All commits are meant for `albus.xiao`. Background sessions may not edit the main checkout, and the user forbids branch changes. Work therefore happens in a *detached* linked worktree, `.claude/worktrees/r1-impl`, created with `git worktree add --detach`, so no branch exists for it. Commits go onto its detached HEAD.
  - The isolated session also can't run git against the main checkout, so the fast-forward is done by the user or by a session that isn't isolated.
  - Never `git update-ref` the checked-out branch; it would leave the main index stale.
  - `.claude/worktrees/` is listed in `.git/info/exclude`.
  - Nothing is pushed.
- **Agents.** A coordinator runs one engine agent and one interface agent per milestone, in parallel, using the brief template below. Agents never run git write commands; the coordinator verifies with `make check` and commits once per milestone.
- **Ownership.**
  - Engine agent: `aiautonomy/__init__.py`, `aiautonomy/engines/`, `tests/engines/`, `pyproject.toml`, `uv.lock`, `.python-version`, `data/`, `config/`, `prompts/`, `docs/`, `bench/`.
  - Interface agent: `aiautonomy/interfaces/`, `tests/interfaces/`, and the root JS/TS project files (`package.json`, `package-lock.json`, `.nvmrc`, `tsconfig.json`, and the Vite, Vitest, Playwright, ESLint and Prettier configs).
  - Coordinator: `Makefile`, `.github/`, `scripts/`, `README.md`, `.gitignore`, `plans/`.
- **Usage limit.** At every milestone boundary the coordinator runs a read-only `GET https://api.anthropic.com/api/oauth/usage?skip_spend=1`. It sends `Authorization: Bearer <claudeAiOauth.accessToken from ~/.claude/.credentials.json>` and `anthropic-beta: oauth-2025-04-20`, and reads `five_hour.utilization` and `resets_at`. This is the endpoint behind Claude Code's `/usage`, and the call spends no tokens. If the next milestone might not fit, the coordinator stops and updates this file.
- **Paid API (D2).** Nothing calls `api.anthropic.com` for inference. `AIA_ALLOW_PAID_API` is never set.

### Conventions fixed during implementation

| Topic | Convention |
|---|---|
| Source layout (D3) | Engine code is in `aiautonomy/engines/<pkg>/` (Python package `aiautonomy.engines.<pkg>`). Interface code is in `aiautonomy/interfaces/` (the Vite root, with `index.html` there). Tests are in `tests/engines/` and `tests/interfaces/`, with Playwright in `tests/interfaces/e2e/`. The Python and JS project files are at the repository root (docs/engine-plan.md §6) |
| Engine server | `uv run aia serve` on `127.0.0.1:8787`; WebSocket `/ws`; REST under `/api`; serves the Vite build in `dist/` at `/` when it exists. Add `--artificial-inference-wait-ms N --artificial-inference-wait-every K` to simulate inference waits |
| Vite dev server | Port 5173; proxies `/ws` and `/api` to `127.0.0.1:${AIA_ENGINE_PORT:-8787}`; build output `dist/`. The e2e setup uses engine port 8788 and preview port 4173 |
| Protocol source | Pydantic models in `aiautonomy.engines.api.protocol`. The JSON Schema is `aiautonomy/engines/api/protocol.schema.json` (`uv run python -m aiautonomy.engines.api.export_schema [--check]`). The TypeScript types are `aiautonomy/interfaces/net/protocol.gen.ts` (`npm run gen:protocol` / `check:protocol`, using `aiautonomy/interfaces/net/protocol.codegen.mjs`). `make protocol` regenerates both |
| Make targets | Everything runs from the repository root. `make check` = `check-engines` + `check-interfaces` + `check-schema` + `check-trace` (report-only until M9) + `check-e2e` |
| Traceability tags | Engine code: docstring `REQ: FIN-02` (comma-separated lists allowed). Engine tests: `@pytest.mark.req("FIN-02")`. Interface code: comment `// REQ: VIS-01`. Interface tests: `@req VIS-01` in the title or a comment. `aia trace` rewrites `docs/traceability.md` on every run, so commit it with each milestone |
| Run records | `runs/<run_id>/` at the repository root (git-ignored) |
| UI style | The dark "lab" look of albusxiao.dev. Ink `#05070a` `#080b10` `#0b0f15` `#171e29`; text `#e7ecf2` `#a1acb9` `#7b8796` `#4d5866`; hairlines `#94aac81c` / `#94aac838`; signal `#6fd6f7`; amber `#efb45f`; danger `#f0928a`; wire `#a8e6ff`. Geist and Geist Mono are bundled through `@fontsource-variable`. Small radii and numbered mono panel labels ("03 · playback") |

### Implementation decisions log

Decisions made while implementing that the plan leaves open, plus user decisions.

| Date | Decision | Why |
|---|---|---|
| 2026-11-22 | **D3 (user decision): source layout.** All implementation lives in `aiautonomy/` at the repository root. Engine code sits directly under `aiautonomy/engines/`, interface code directly under `aiautonomy/interfaces/`. There is no `src/` folder and no nested `aiautonomy/` folder. Commit `b7c791f` updated docs/engine-plan.md §6 (tree and layout rule), §3.1, §10 and §13.1 to match | User instruction during M0; the user asked for the plan update |
| 2026-11-22 | The protocol adds `ack` (server → client) plus `sync` and `telemetry` (client → server) to the message lists in §4.8 | §4.8 requires requesting a fresh snapshot after a gap, and §5.12 requires command-latency telemetry. Both need these messages |
| 2026-11-22 | `state_version` increases by 1 per delta. At maximum speed the engine coalesces ticks into at most one delta every 50 ms; the recorder still writes every tick | Keeps the client in step without flooding the WebSocket |
| 2026-11-22 | `ticks_per_second` is 0 at maximum speed, meaning unpaced. The interface never divides by it; it interpolates over the measured gap between deltas, clamped to 16–250 ms | Maximum speed has no fixed rate |
| 2026-11-22 | Command semantics: `start` only from idle; `cancel` only after a run has started; `step` from idle leaves the run paused; the speed setting survives `reset`. Messages a command triggers are sent after its `ack`, and `configure`/`reset` send a snapshot, then `run_status`. A tick interrupted by reset or cancel is discarded | Deterministic, testable command handling |
| 2026-11-22 | TypeScript is pinned to 6.0.x | typescript-eslint 8.73 supports TypeScript < 6.1 |

### M0 result (2026-11-22)

- **Checks.** `make check` exits 0:
  - ruff, ruff format, mypy (45 files) and import-linter (2 contracts) are clean
  - pytest: 141 passed in about 7 s
  - vitest: 54 passed
  - Vite build passes
  - no schema drift
  - `aia trace`: 12 of 108 requirements covered (report-only)
  - Playwright e2e: 10/10 in about 25 s
- **Exit criteria.**
  - A 300-tick headless toy run (`aia run --headless --scenario toy --seed 42`) replays with identical hashes (`aia replay`: "300 ticks identical").
  - The browser shows the ticking world, and its controls are acked in under 100 ms during an artificial inference wait (e2e test 3; screenshot `test-results/m0-running.png`, not committed).
- **Cost.** The engine agent used about 350k tokens (111 tool calls, 35 min). The interface agent used about 389k tokens (147 tool calls, 40 min). Usage went from 14% to 49% of the window, including coordination and the D3 move.
- **Notes for later milestones**
  - Replay refuses runs that contain recorded decisions or interventions. Extend it when M2 (interventions) and M4 (decisions) start writing them.
  - `config/engine.yaml` has `default_scenario: toy`. Switch it to the Boston scenario in M1; the toy world stays for tests.
  - `make bench` is a stub (exit 2) until M4, and `make test-live` accepts "no tests collected" until M4.
  - Playwright uses its bundled Chromium; system libraries were installed with `sudo npx playwright install-deps chromium`. The config falls back to `/usr/bin/chromium` only if the bundled browser is missing. `window.__aia` exposes recent acks to the e2e tests.
  - Interface safety: a CSP meta tag, and an ESLint rule that bans `innerHTML` and `dangerouslySetInnerHTML`.
  - Selection casts a ray to the ground plane, then picks the nearest entity within 10 px. Panels register themselves by number in `aiautonomy/interfaces/ui/panels/registry.ts`.

### Agent brief template (used for M0)

Every brief has these parts. The shared protocol text must be identical in both briefs.

1. Role, ROOT path (the worktree), and the other agent working in parallel.
2. Hard rules:
   - implement exactly what docs/engine-plan.md says for the milestone, and list any choice the plan leaves open
   - no git write commands
   - no paid API and never set `AIA_ALLOW_PAID_API`
   - touch only owned paths
   - be token-efficient: read only the given plan ranges, run `pytest -q`, pipe long output through `tail`
   - keep Bash commands simple, because the isolated session refuses compound commands that leave ROOT
3. Read-first list: plan line ranges, spec line ranges, this file, `Makefile`.
4. Environment notes: uv/Python 3.14, Node 24 (npm in `~/.npm-global`), loopback HTTP clients with `trust_env=False`, no CDN.
5. Numbered deliverables with the tests that prove them, mapped to the milestone's requirement IDs.
6. The milestone's wire-protocol contract, with the field names fixed.
7. Working order. The engine publishes its protocol models and schema first; the interface works from the contract and regenerates the types before it finishes. The interface runs e2e against the real engine, or reports "e2e pending engine" so the coordinator can send a follow-up.
8. A final report of at most 400 words: files, commands verified with counts, deviations, hand-offs.

### M1 brief (prepared 2026-11-22; check it against the code before use)

Plan: §5.1 (lines 355–421), §5.2 (423–507, M1 parts), §5.4 roads and movement (558–576), §4.2 population rounding (209–217), §5.10 satisfaction skeleton (1017–1039), §5.12 (1099–1145), §7 M1 (1419–1446). Spec: §5 CITY (lines 137–185), RES-01, RES-02, RES-06 (242–316), SRV-02 (383–388), MET-01, MET-02 (860–889), VIS-02, VIS-04 (1031–1064).

**Engine deliverables**

1. **Boston v1 map (CITY-01, CITY-02).**
   - Hand-authored sources in `data/maps/boston/v1/source/*.yaml`: nodes (lat/lon), streets (name, ordered nodes, one-way flag, road class → free-flow speed, capacity and lanes, emergency access), areas (7 districts plus the Common/Public Garden park zone, water, the represented-area outline), 11 landmarks (footprint polygon plus access node), facilities, aggregated home/work/leisure blocks with capacities, about 10 plots, and 4 power zones.
   - The facilities are MGH and Tufts Medical Center, City Hall, generic police, fire and EMS stations, 3 shelters, a maintenance depot, and the server room on its own feeder.
   - Footprint (§5.1): Charles St/Storrow Dr to Atlantic Ave and the waterfront, Causeway St and the North End waterfront to Kneeland St.
   - Coordinates: origin at the Old State House (42.35870 N, 71.05757 W); x east, y north, in metres.
   - Size: 40–60 named streets and 150–250 nodes. One-way rules are approximated. Omit the I-93 tunnel and alleys.
2. **`aia map build`.**
   - Projects lat/lon to local metres at build time only, rounded to 0.1 m, and builds the directed segments.
   - Writes canonical `map.json`, `landmarks.json` and `map.lock` (sha256), with deterministic bytes.
   - Runs load the map by version and verify the hash (CITY-04).
   - Writes `data/maps/boston/v1/README.md` covering footprint, scale, roads represented, landmarks, simplifications and the hand-digitized source.
3. **Landmark protection (CITY-03).** Landmarks are frozen models with no mutation API. Only `condition` and `access` change, and only through events (later milestones).
4. **Validation (CITY-05).**
   - Implement every check in §5.1.
   - `intentional_overrides` are accepted and recorded.
   - Failures block `start` and are reported to panel 1.
   - Negative test cases.
5. **Default scenario.** Add `data/scenarios/default.v1.yaml` (Boston v1, population 100, ratio 5000 bp, start 07:00, duration 300) and set `default_scenario` to it.
6. **Residents (RES-01, RES-02 routines, RES-06).**
   - The full RES-01 state model.
   - Generation: homes by district capacity; workplaces and leisure by distance-weighted keyed draws; schedule templates (office, shift, student, retiree, care worker) with keyed jitter; preferences (travel mode, risk tolerance, baseline support, income band).
   - `llm_count = (population × ratio_bp + 5000) // 10000`; the LLM set is the residents with the lowest `mode_assignment` draws, so the sets are nested.
   - The routine rule table for M1: follow the schedule, reroute around closures, and when unreachable wait or return home and record the delay. Write it in `docs/residents.md`.
   - LLM residents follow routines until M4. Zero inference requests.
7. **Traffic (SRV-02).**
   - Directed segments carry length, free-flow speed, capacity, condition, closure state and the emergency flag. Effective capacity = base × condition × modifiers (no modifiers yet).
   - Travel time uses BPR with an integer exponent: `free_flow_time × (1 + α × (load/capacity)^4)`. Load = agents on the segment + time-of-day background demand × an economic multiplier of 1.0.
   - Routing is Dijkstra with deterministic tie-breaking; movement is mesoscopic.
   - Agents reroute on a closure or when the delay passes a threshold. An unreachable destination gives an explicit `unreachable` outcome.
   - Measure the tick time at population 100 against the 20 ms budget.
8. **Metrics (MET-01, MET-02 skeleton).** Add `data/metrics/satisfaction.v1.yaml` with the five components and their weights. Compute M (mobility) from excess travel time over a rolling window. The denominator is always the original population.
9. **Tests:**
   - the map hash is the same for every seed
   - negative validation cases block the start
   - landmarks can't be mutated
   - ratio arithmetic at 0 %, 100 % and the halfway cases; the assignment is stable and nested
   - routing is deterministic
   - schedules are followed
   - a Boston run replays identically
   - zero inference calls

**Interface deliverables**

1. Fetch the static map over REST whenever the snapshot's `map_ref` changes, and cache it by sha256.
2. Static layers on merged geometry (few draw calls):
   - ground, water, parks and subtle district outlines
   - road ribbons whose width follows road class and whose color follows `load_ratio` (signal → amber → danger), with closures distinct
   - low-poly flat-shaded building blocks
   - facilities with distinct silhouettes and a color per type
   - landmarks with their own models in amber
   - the represented-area outline, the "Represented area" label and a scale bar (CITY-01)
3. Residents in one InstancedMesh, interpolated and colored by mode (routine or LLM) and status. Toy `movers` must still render.
4. The camera frames the represented area at start, with clamps derived from the map bounds.
5. Panel 1, "Run configuration":
   - scenario (from `GET /api/scenarios`), seed, duration, population and LLM ratio as a percentage, showing the resulting LLM count with half-up rounding
   - apply sends `configure`
   - lists the engine's validation failures and blocks start
   - frozen fields are disabled while a run is active
6. Panel 6, "Inspection": residents, facilities, landmarks and segments through `inspect`, selected by map click or by id.
7. Tests:
   - vitest: layer builders, the color ramp, the ratio display
   - e2e: the map renders, residents move after start, configure creates a new run with the right LLM count, inspecting a resident and a facility works, the label and scale bar are visible
   - screenshot `test-results/m1-boston.png`

**Protocol additions** (the engine defines them first; both briefs use the same text):

- `GET /api/scenarios` returns `[{id, name, defaults: {seed, duration, population, llm_ratio_bp}}]`.
- `GET /api/maps/{id}/{version}` returns the static map: bounds, area outline, districts, parks, water, segments (id, from, to, polyline, class, lanes, one-way, emergency access), blocks, facilities, landmarks, plots and power zones.
- `WorldView` gains:
  - `map_ref: {id, version, sha256}`
  - `residents: {[id]: {id, x, y, mode: "routine"|"llm", status, activity, district}}`
  - `roads: {[segment_id]: {id, load_ratio, closure: "open"|"closed_general"|"closed_all"}}`, sent in deltas only when a value changes past a rounding step
  - `movers` stays for the toy scenario
- `configure.config` gains `population` and `llm_ratio_bp` (0–10000).
- `RunStatus` gains `validation: {ok, failures: [{code, entity_id, message}], intentional_overrides: [...]}`. `start` is rejected while `ok` is false.
- `inspect` accepts resident, facility, landmark and segment ids.
