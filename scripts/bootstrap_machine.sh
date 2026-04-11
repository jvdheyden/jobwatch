#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="${JOB_AGENT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PLATFORM="${JOB_AGENT_PLATFORM:-$(uname -s)}"

usage() {
  cat <<EOF
Usage: $0

Bootstrap this checkout for first-time local use.

This script:
1. Generates machine-local config via scripts/setup_machine.sh
2. Bootstraps the repo-local virtualenv via scripts/bootstrap_venv.sh

It does not install the scheduler or the optional Linux AppArmor profile.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
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

/bin/bash "$SCRIPT_DIR/setup_machine.sh"
/bin/bash "$SCRIPT_DIR/bootstrap_venv.sh"

echo "Bootstrapped machine config and repo-local virtualenv for $ROOT"
echo "Next: ask Codex to set up a search track; the setup agent can configure delivery, scheduling, and scheduler install."
if [[ "$PLATFORM" == "Linux" ]]; then
  echo "Optional on Linux hosts that enforce AppArmor userns restrictions:"
  echo "  sudo bash scripts/install_bwrap_apparmor.sh"
fi
