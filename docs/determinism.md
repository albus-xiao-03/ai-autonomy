# Determinism

Spec SIM-04 and EVAL-04, docs/engine-plan.md §4.2. A run is fully determined by its seeds, its frozen
configuration and data-file versions, its recorded decisions and its recorded interventions.

## Keyed randomness

`KeyedRng.u01(stream, *key)` (`aiautonomy.engines.core.rng`):

1. Encode the stream seed as 8 big-endian bytes and the key as compact JSON, for example
   `["medical_demand",12,"res-000001"]`. Key parts are `int` or `str` only.
2. Hash the concatenation with BLAKE2b (default 64-byte digest) and take the first 8 bytes.
3. Map the top 53 bits to a float in [0, 1).

A draw depends only on its stream seed and key, never on how many other draws happened.
`below(stream, n, *key)` uses exact integer arithmetic.

## Streams and seeds

Twelve streams, each with its own seed: `population`, `mode_assignment`, `schedules`,
`preferences`, `external_events`, `event_effects`, `medical_demand`, `fire`,
`traffic_background`, `services`, `politics`, `model_sampling`. A stream's seed is derived from
the run seed (first 8 bytes of BLAKE2b over a domain tag, the run seed and the stream name)
unless the scenario overrides it. The manifest records every stream seed, and replay uses the
recorded values. Only the event system reads `external_events` and `event_effects`.

## Arithmetic

- Money is integer cents (`aiautonomy.engines.core.money`); counts and time are integer ticks.
- Shares in basis points round half up: `(population × ratio_bp + 5000) // 10000`.
- Authoritative float updates use only `+ − × ÷`, `min`, `max`, `abs` and integer powers;
  never `exp`, `log`, `pow` or trigonometric functions.

## Ordering and identity

- Entities live in dicts keyed by id and are iterated in sorted id order; authoritative code
  never iterates over a `set`.
- Ids come from per-type counters stored in the World (`mover-000001`, …), never from
  `uuid4`. Zero padding makes sorted order equal allocation order.
- `run_id` is wall-clock based and is excluded from every hash.

## State hash

After each tick, `World.to_state()` is serialized to canonical JSON (sorted keys, no
whitespace, floats via `repr`, NaN and infinities rejected) and hashed with BLAKE2b
(32-byte digest). Each top-level key (`clock`, `ids`, `movers`, `metrics`, …) is a subsystem
with its own hash. `ticks.jsonl` records the state hash, the subsystem hashes and the metrics
of every tick from tick 0.

## Replay

`aia replay <run_id|path>` rebuilds the run from the manifest (frozen config, recorded
stream seeds), the interventions and the decision log, inside `no_inference_clients()`, which
fails if any inference client is created. It compares hashes, metrics and the terminal outcome
tick by tick, prints the first divergent tick and subsystem, and exits non-zero on divergence.
It warns when the engine version or a data file differs from the recording.
