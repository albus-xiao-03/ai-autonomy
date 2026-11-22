# AI Autonomy: top-level tasks (plans/R1.md §6). Run from the repository root.
# Layout (decision D3, plans/R1.checkpoint.md): engine code in aiautonomy/engines/, interface code in
# aiautonomy/interfaces/; the Python project (pyproject.toml, uv.lock) and the JS project
# (package.json, package-lock.json) are both rooted here.
# No target calls a paid API (D2). `test-live` uses the local Ollama model only.

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

UV  ?= uv
NPM ?= npm
RUN ?=

.PHONY: help setup dev check check-engines check-interfaces check-schema check-trace check-e2e \
        protocol fmt test-live bench demo replay

help:
	@echo "Targets:"
	@echo "  setup        install engine (uv) and interface (npm) dependencies"
	@echo "  dev          run the engine (127.0.0.1:8787) and the Vite dev server with a proxy"
	@echo "  check        lint, type checks, tests, schema-drift check, traceability check, e2e"
	@echo "  protocol     regenerate the protocol JSON Schema and the TypeScript types"
	@echo "  test-live    opt-in tests against the real local Ollama model"
	@echo "  bench        hardware benchmark (aia bench all)"
	@echo "  demo         run the default demonstration headless"
	@echo "  replay       replay a recorded run: make replay RUN=<run_id|path>"

setup:
	$(UV) sync --frozen
	$(NPM) ci

dev:
	./scripts/dev.sh

check: check-engines check-interfaces check-schema check-trace check-e2e

check-engines:
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy
	$(UV) run lint-imports
	$(UV) run pytest -q

check-interfaces:
	$(NPM) run lint
	$(NPM) run typecheck
	$(NPM) test
	$(NPM) run build

# The committed JSON Schema must match the pydantic models, and the committed
# TypeScript types must match the committed JSON Schema (plans/R1.md §4.8).
check-schema:
	$(UV) run python -m aiautonomy.engines.api.export_schema --check
	$(NPM) run check:protocol

# Report-only until M9 makes the gate blocking (`aia trace --strict`).
check-trace:
	$(UV) run aia trace

check-e2e:
	$(NPM) run e2e

protocol:
	$(UV) run python -m aiautonomy.engines.api.export_schema
	$(NPM) run gen:protocol

fmt:
	$(UV) run ruff format .
	$(UV) run ruff check --fix .
	$(NPM) run format

# pytest exits 5 when no live test is collected (none exist before M4).
test-live:
	$(UV) run pytest -q -m live tests/engines/live || [ $$? -eq 5 ]

bench:
	$(UV) run aia bench all

demo:
	$(UV) run aia run --headless --scenario default

replay:
	@test -n "$(RUN)" || { echo "usage: make replay RUN=<run_id|path>"; exit 2; }
	$(UV) run aia replay "$(RUN)"
