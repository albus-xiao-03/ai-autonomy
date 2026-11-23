"""Hybrid Boston runs: the game drives the clock, the engine owns everything it decides.

A `HybridRun` is pinned to one map revision and processes one game observation per tick
through the SIM-02 phases (docs/tick-order.md, docs/contract.md §4). The `RunStore` holds the
live runs, their epochs and per-run locks; records go to a `HybridSink` (the recorder).

REQ: SIM-02, SIM-03, SIM-05, ARCH-02
"""
