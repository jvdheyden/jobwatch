#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="${JOB_AGENT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PLATFORM="${JOB_AGENT_PLATFORM:-$(uname -s)}"
AGENT_VALUE=""
AGENT_BIN_VALUE=""
START_SETUP_AGENT=""

usage() {
  cat <<EOF
Usage: $0 --agent codex|claude|gemini [--agent-bin <path>] [--start-setup-agent|--no-start-setup-agent]

Bootstrap this checkout for first-time local use.

This script:
1. Generates machine-local config via scripts/setup_machine.sh
2. Creates local profile placeholders under profile/
3. Bootstraps the repo-local virtualenv via scripts/bootstrap_venv.sh

It does not install the scheduler or the optional Linux AppArmor profile.
In an interactive terminal, it asks whether to start the guided setup agent.
In non-interactive mode, it starts the setup agent only with --start-setup-agent.
EOF
}

agent_guidance() {
  local detected=""
  local detected_count=0
  local candidate=""
  for candidate in claude codex gemini; do
    if command -v "$candidate" >/dev/null 2>&1; then
      detected="$candidate"
      detected_count=$((detected_count + 1))
    fi
  done
  if [[ "$detected_count" -ne 1 ]]; then
    detected=""
  fi
  cat >&2 <<EOF
Choose an automation agent:
  bash scripts/bootstrap_machine.sh --agent claude
  bash scripts/bootstrap_machine.sh --agent codex
  bash scripts/bootstrap_machine.sh --agent gemini
EOF
  if [[ -n "$detected" ]]; then
    echo "Detected '$detected' on PATH; likely command: bash scripts/bootstrap_machine.sh --agent $detected" >&2
  fi
}

validate_agent() {
  case "${1:-}" in
    codex|claude|gemini)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_interactive() {
  [[ -t 0 && -t 1 ]]
}

prompt_start_setup_agent() {
  local entered=""
  printf 'Start guided setup now? [Y/n]: ' >&2
  IFS= read -r entered
  case "${entered,,}" in
    n|no)
      printf 'no\n'
      ;;
    *)
      printf 'yes\n'
      ;;
  esac
}

print_final_guidance() {
  local start_command="bash scripts/start_setup_agent.sh --agent $AGENT_VALUE"
  if [[ -n "$AGENT_BIN_VALUE" ]]; then
    start_command+=" --agent-bin $AGENT_BIN_VALUE"
  fi

  cat <<EOF
+------------------------------------------------------------+
| jobwatch bootstrap complete                                |
+------------------------------------------------------------+
Repo root:
  $ROOT

Next:
  1. Review local profile files:
     - profile/cv.md
     - profile/prefs_global.md
     Optional: place a PDF CV in profile/ and the setup agent can draft
     profile/cv.md while it is still the default placeholder.

  2. Start guided setup:
     $start_command

Do not edit:
  .agents/skills/set-up/templates/profile/*
EOF

  if [[ "$AGENT_VALUE" == "claude" ]]; then
    cat <<EOF

  3. Claude note:
     If Claude asks whether you trust this folder before setup starts,
     trust it and rerun the guided setup command above.
     If Claude opens without the guided setup contract, use the fallback
     prompt in docs/machine_setup.md.
EOF
  fi

  if [[ "$AGENT_VALUE" == "gemini" ]]; then
    cat <<EOF

  3. Gemini note:
     Authenticate Gemini CLI before scheduled runs if this machine has not
     already been configured:
     gemini -p 'Respond with exactly: ok'
EOF
  fi

  if [[ "$PLATFORM" == "Linux" && "$AGENT_VALUE" == "codex" ]]; then
    cat <<EOF

  3. Optional Linux/Codex AppArmor fix:
     Run this only if the host restricts bwrap user namespaces:
     sudo bash scripts/install_bwrap_apparmor.sh
EOF
  fi

  cat <<EOF
+------------------------------------------------------------+
EOF
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
    --start-setup-agent)
      START_SETUP_AGENT="yes"
      shift
      ;;
    --no-start-setup-agent)
      START_SETUP_AGENT="no"
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

if [[ -z "$AGENT_VALUE" ]]; then
  agent_guidance
  exit 2
fi
if ! validate_agent "$AGENT_VALUE"; then
  echo "Invalid --agent '$AGENT_VALUE'; expected codex, claude, or gemini." >&2
  agent_guidance
  exit 2
fi

SETUP_ARGS=(--agent "$AGENT_VALUE")
if [[ -n "$AGENT_BIN_VALUE" ]]; then
  SETUP_ARGS+=(--agent-bin "$AGENT_BIN_VALUE")
fi

/bin/bash "$SCRIPT_DIR/setup_machine.sh" "${SETUP_ARGS[@]}"
/bin/bash "$SCRIPT_DIR/bootstrap_venv.sh"

if [[ -z "$START_SETUP_AGENT" ]]; then
  if is_interactive; then
    START_SETUP_AGENT="$(prompt_start_setup_agent)"
  else
    START_SETUP_AGENT="no"
  fi
fi

print_final_guidance

if [[ "$START_SETUP_AGENT" == "yes" ]]; then
  START_ARGS=(--agent "$AGENT_VALUE")
  if [[ -n "$AGENT_BIN_VALUE" ]]; then
    START_ARGS+=(--agent-bin "$AGENT_BIN_VALUE")
  fi
  /bin/bash "$SCRIPT_DIR/start_setup_agent.sh" "${START_ARGS[@]}"
fi
