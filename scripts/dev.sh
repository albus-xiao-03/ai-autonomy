#!/usr/bin/env bash
# Run the engine and the Vite dev server together (plans/R1.md §6, `make dev`).
# The engine listens on loopback only; Vite proxies /api and /ws to it.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE_PORT="${AIA_ENGINE_PORT:-8787}"
cd "$ROOT"

cleanup() {
  trap - EXIT INT TERM
  kill 0 2>/dev/null || true
}
trap cleanup EXIT INT TERM

uv run aia serve --host 127.0.0.1 --port "$ENGINE_PORT" &
AIA_ENGINE_PORT="$ENGINE_PORT" npm run dev &
wait
