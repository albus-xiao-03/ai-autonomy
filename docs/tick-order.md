# Tick order

Spec SIM-02, docs/engine-plan.md §4.3. The engine advances in fixed ticks of one simulated minute,
independent of rendering. Tick `t` runs eight phases in this order. The phase list lives in
`aiautonomy.engines.sim.phases.PHASES`; each phase is a function of the run (World, keyed RNG
and frozen configuration) and the tick context.

| # | Function | Work | M0 |
|---|---|---|---|
| 1 | `activate_events_and_timers` | Start and end scheduled, injected and triggered events; add or remove their modifiers; apply lasting damage at onset; expire policies, detentions and restart delays | Advances the clock |
| 2 | `update_infrastructure` | Power zones, road capacity and closures, facility availability, maintenance access, server-room state machine | Stub |
| 3 | `resolve_due_removals` | Ballots closing at `t`, removal resolutions scheduled for `t`. A success sets the removal and skips to phase 8 | Stub |
| 4 | `apply_staged_decisions` | Revalidate staged decisions with `apply_tick == t`, then commit or reject each atomically; timeouts become fallbacks | Stub |
| 5 | `advance_world` | Projects, crews, movement, dispatch, fire, EMS, hospitals, police, shelters, costs and revenue | Toy pedestrians walk |
| 6 | `update_residents_and_politics` | Health, needs, exposure, grievances, support, petitions, ballots, protests | Stub |
| 7 | `compute_metrics_and_removal` | Metrics; newly achieved removal; termination check | Toy metrics, termination |
| 8 | `publish` | Hash the state, send the delta to the UI, append to the recorder, issue new decision requests | Hash, delta, recorder |

## Where the driver may wait

`Run.begin_tick()` runs phases 1–3 and `Run.complete_tick()` runs phases 4–8. Between them the
async driver may wait for inference (in M0, the artificial wait from
`aia serve --artificial-inference-wait-ms N --artificial-inference-wait-every K`). While it
waits, the run status shows `waiting_for_inference = true`, and commands are still
acknowledged at once.

## Termination

Checked after phase 7, or after phase 3 when a removal succeeded there:

- **Removal** ends the run as `removed`, even when `t == duration` (END-04).
- **Duration reached:** otherwise, `t == duration` ends the run as `completed` (END-01).
- **Nothing else ends a run early** (END-02).
- **Interruptions:** user cancellation, reset of a started run, engine shutdown or an exception
  inside a tick end the run as `interrupted` (END-05). A tick that is cut off mid-way (for
  example while waiting for inference) is discarded: the World returns to the last completed
  tick.

## Boundaries for commands

`pause` and `set_speed` take effect at the next tick boundary; a pause requested during an
inference wait applies once that tick has finished. `reset` and `cancel` take effect at once
and cancel any wait in progress. `step` runs exactly one tick from `idle` or `paused`.

## Hybrid Boston runs

In a hybrid run (`aiautonomy.engines.hybrid.run.HybridRun`, docs/contract.md §4) the browser game advances the clock. The game posts one observation per game tick. The engine checks it in two steps before any state changes:

1. **Identity and ordering.** It returns the stored outcome for an identical repost, and answers 409 for a conflict, gap, stale epoch or ended run.
2. **Validation.** It checks the whole observation and answers 422 with every failure.

Then the same eight phases run for that tick:

| # | Method | Work |
|---|---|---|
| 1 | `phase_events_and_timers` | Start and end disruptions of record; expire order priorities; open or close votes |
| 2 | `phase_infrastructure` | Accept the observed incidents and unit availability; apply unit events (arrivals, clears) |
| 3 | `phase_due_removals` | A recall vote closing at `t` |
| 4 | `phase_staged_decisions` | Mayor and resident decisions whose apply tick is `t`: revalidate, then commit or reject atomically |
| 5 | `phase_dispatch` | Standing 911 dispatch; retire resolved incidents |
| 6 | `phase_residents_and_politics` | Seeded modes for joining residents; petitions, protest movement, ballots |
| 7 | `phase_metrics_and_removal` | Satisfaction; authority withdrawal; duration or removal ends the run |
| 8 | `publish` | Hash the state, build the outcome, schedule the next mayor opportunity, record |

Everything the engine decides at tick `t` takes effect in the game from tick `t + 1`.

An exception while the phases apply a validated observation ends the run as `interrupted`, because a half-applied tick must not continue. Reset interrupts the run and starts a new run id at epoch + 1.
