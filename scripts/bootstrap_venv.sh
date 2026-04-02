#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="$ROOT/.venv"
REQUIREMENTS_FILE="$ROOT/requirements-dev.txt"

if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
  echo "Missing requirements file: $REQUIREMENTS_FILE" >&2
  exit 1
fi

"$PYTHON_BIN" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$REQUIREMENTS_FILE"

echo "Bootstrapped repo-local virtualenv at $VENV_DIR"
echo "Python: $VENV_DIR/bin/python"
echo "Pytest: $VENV_DIR/bin/python -m pytest"
echo "If browser-backed discovery needs local browsers, run:"
echo "  $VENV_DIR/bin/python -m playwright install chromium"
