#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="$ROOT/.venv/bin/python"

cd "$ROOT"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing repo-local virtualenv at $ROOT/.venv." >&2
  echo "Run: bash scripts/bootstrap_venv.sh" >&2
  exit 1
fi

# Discover maintained scripts and tests; adding a file needs no runner edit.
while IFS= read -r script; do
  bash -n "$script"
done < <("$PYTHON_BIN" - <<'PY'
from pathlib import Path

for root in (Path('scripts'), Path('tests')):
    for path in sorted(root.rglob('*.sh')):
        if 'local' not in path.parts and 'tmp' not in path.parts:
            print(path)
PY
)
"$PYTHON_BIN" -m compileall -q -x '/(local|tmp)/' scripts tests
bash scripts/sync_claude_skills.sh --check
"$PYTHON_BIN" scripts/render_discovery_modes_md.py --check

# Fast: deterministic logic and provider contracts. Full (default): every test,
# including shell subprocess integration and complete workflow execution.
if [[ "${1:-}" == "--fast" ]]; then
  shift
  exec "$PYTHON_BIN" -m pytest tests/unit tests/contract -q "$@"
fi
exec "$PYTHON_BIN" -m pytest -q "$@"
