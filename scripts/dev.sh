#!/usr/bin/env bash
# Start the API and the UI together. Ctrl+C stops both.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Run make install-backend first." >&2
  exit 1
fi
if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  echo "Run make install-frontend first." >&2
  exit 1
fi

"$ROOT/.venv/bin/python" "$ROOT/scripts/seed_demo.py"

cleanup() {
  if [[ -n "${BACK_PID:-}" ]]; then
    kill "$BACK_PID" 2>/dev/null || true
  fi
  if [[ -n "${FRONT_PID:-}" ]]; then
    kill "$FRONT_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

(
  cd "$ROOT/backend"
  PYTHONPATH="$ROOT/backend" "$ROOT/.venv/bin/python" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
) &
BACK_PID=$!

(
  cd "$ROOT/frontend"
  npm run dev -- --host 127.0.0.1 --port 5173
) &
FRONT_PID=$!

echo "API http://127.0.0.1:8000"
echo "UI  http://127.0.0.1:5173"

wait -n "$BACK_PID" "$FRONT_PID"
