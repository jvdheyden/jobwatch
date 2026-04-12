#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="${JOB_AGENT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PLATFORM="${JOB_AGENT_PLATFORM:-$(uname -s)}"
AGENT_VALUE=""
AGENT_BIN_VALUE=""

usage() {
  cat <<EOF
Usage: $0 --agent codex|claude [--agent-bin <path>]

Bootstrap this checkout for first-time local use.

This script:
1. Generates machine-local config via scripts/setup_machine.sh
2. Creates local profile placeholders under profile/
3. Bootstraps the repo-local virtualenv via scripts/bootstrap_venv.sh

It does not install the scheduler or the optional Linux AppArmor profile.
EOF
}

agent_guidance() {
  local detected=""
  if command -v claude >/dev/null 2>&1 && ! command -v codex >/dev/null 2>&1; then
    detected="claude"
  elif command -v codex >/dev/null 2>&1 && ! command -v claude >/dev/null 2>&1; then
    detected="codex"
  fi
  cat >&2 <<EOF
Choose an automation agent:
  bash scripts/bootstrap_machine.sh --agent claude
  bash scripts/bootstrap_machine.sh --agent codex
EOF
  if [[ -n "$detected" ]]; then
    echo "Detected '$detected' on PATH; likely command: bash scripts/bootstrap_machine.sh --agent $detected" >&2
  fi
}

validate_agent() {
  case "${1:-}" in
    codex|claude)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --agent" >&2
        usage >&2
        exit 2
      fi
      AGENT_VALUE="$2"
      shift 2
      ;;
    --agent-bin)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --agent-bin" >&2
        usage >&2
        exit 2
      fi
      AGENT_BIN_VALUE="$2"
      shift 2
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

if [[ -z "$AGENT_VALUE" ]]; then
  agent_guidance
  exit 2
fi
if ! validate_agent "$AGENT_VALUE"; then
  echo "Invalid --agent '$AGENT_VALUE'; expected codex or claude." >&2
  agent_guidance
  exit 2
fi

SETUP_ARGS=(--agent "$AGENT_VALUE")
if [[ -n "$AGENT_BIN_VALUE" ]]; then
  SETUP_ARGS+=(--agent-bin "$AGENT_BIN_VALUE")
fi

/bin/bash "$SCRIPT_DIR/setup_machine.sh" "${SETUP_ARGS[@]}"
/bin/bash "$SCRIPT_DIR/bootstrap_venv.sh"

echo "Bootstrapped machine config, local profile placeholders, and repo-local virtualenv for $ROOT"
echo "Fill profile/cv.md and profile/prefs_global.md locally; optionally place a PDF CV in profile/."
echo "Next: ask your configured agent to set up a search track; the setup agent can configure delivery, scheduling, and scheduler install."
if [[ "$PLATFORM" == "Linux" ]]; then
  echo "Optional on Linux hosts that enforce AppArmor userns restrictions:"
  echo "  sudo bash scripts/install_bwrap_apparmor.sh"
fi
