#!/bin/bash
set -euo pipefail

INSTALL_CHROMIUM=1
QUIET_MODE=0
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="$ROOT/.venv"
REQUIREMENTS_FILE="$ROOT/requirements-dev.txt"

usage() {
  cat <<EOF
Usage: $0 [--no-chromium] [--quiet]

Bootstrap the repo-local virtualenv from requirements-dev.txt.

Options:
  --no-chromium  Skip Playwright Chromium browser installation.
  --quiet        Suppress installation output on success.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-chromium)
      INSTALL_CHROMIUM=0
      shift
      ;;
    --quiet)
      QUIET_MODE=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
  echo "Missing requirements file: $REQUIREMENTS_FILE" >&2
  exit 1
fi

"$PYTHON_BIN" -m venv "$VENV_DIR"

if [[ "$QUIET_MODE" -eq 1 ]]; then
  if ! output="$("$VENV_DIR/bin/python" -m pip install --upgrade pip -q --disable-pip-version-check 2>&1)"; then
    echo "pip upgrade failed:" >&2
    echo "$output" >&2
    exit 1
  fi
  if ! output="$("$VENV_DIR/bin/python" -m pip install -r "$REQUIREMENTS_FILE" -q --disable-pip-version-check 2>&1)"; then
    echo "pip install failed:" >&2
    echo "$output" >&2
    exit 1
  fi
  if [[ "$INSTALL_CHROMIUM" -eq 1 ]]; then
    if ! output="$("$VENV_DIR/bin/python" -m playwright install chromium 2>&1)"; then
      echo "playwright install failed:" >&2
      echo "$output" >&2
      exit 1
    fi
  fi
else
  "$VENV_DIR/bin/python" -m pip install --upgrade pip
  "$VENV_DIR/bin/python" -m pip install -r "$REQUIREMENTS_FILE"
  if [[ "$INSTALL_CHROMIUM" -eq 1 ]]; then
    "$VENV_DIR/bin/python" -m playwright install chromium
  fi
fi

if [[ "$QUIET_MODE" -eq 0 ]]; then
  echo "Bootstrapped repo-local virtualenv at $VENV_DIR"
  echo "Python: $VENV_DIR/bin/python"
  echo "Pytest: $VENV_DIR/bin/python -m pytest"
  if [[ "$INSTALL_CHROMIUM" -eq 1 ]]; then
    echo "Chromium: installed via Playwright"
  else
    echo "Chromium: skipped (--no-chromium)"
    echo "If browser-backed discovery needs local browsers, run:"
    echo "  $VENV_DIR/bin/python -m playwright install chromium"
  fi
else
  echo "Bootstrapped repo-local virtualenv at $VENV_DIR"
  echo "Python: $VENV_DIR/bin/python"
  if [[ "$INSTALL_CHROMIUM" -eq 1 ]]; then
    echo "Chromium: installed via Playwright"
  else
    echo "Chromium: skipped (--no-chromium)"
  fi
fi
