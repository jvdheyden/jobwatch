#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="${JOB_AGENT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
SCHEDULER_DIR="${JOB_AGENT_SCHEDULER_DIR:-$ROOT/.scheduler}"
SOURCE_PROFILE="${JOB_AGENT_BWRAP_APPARMOR_SOURCE:-$SCHEDULER_DIR/bwrap-userns-restrict}"
DEST_PROFILE="${JOB_AGENT_BWRAP_APPARMOR_DEST:-/etc/apparmor.d/bwrap-userns-restrict}"
PLATFORM="${JOB_AGENT_PLATFORM:-$(uname -s)}"
APPARMOR_PARSER_BIN="${APPARMOR_PARSER_BIN:-$(command -v apparmor_parser || true)}"
INSTALL_BIN="${INSTALL_BIN:-$(command -v install || true)}"
REQUIRE_ROOT="${JOB_AGENT_BWRAP_APPARMOR_REQUIRE_ROOT:-1}"

usage() {
  cat <<EOF
Usage: $0

Install the generated bwrap AppArmor profile on Linux and reload it.
Run scripts/setup_machine.sh first to generate the profile artifact.
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

if [[ "$PLATFORM" != "Linux" ]]; then
  echo "Skipping bwrap AppArmor install on non-Linux platform: $PLATFORM"
  exit 0
fi

if [[ ! -f "$SOURCE_PROFILE" ]]; then
  echo "No generated bwrap AppArmor profile found at $SOURCE_PROFILE." >&2
  echo "Run bash scripts/setup_machine.sh as your normal user first." >&2
  exit 1
fi

if [[ -z "$INSTALL_BIN" ]]; then
  echo "install command not found" >&2
  exit 127
fi

if [[ -z "$APPARMOR_PARSER_BIN" ]]; then
  echo "apparmor_parser not found; install AppArmor userspace tools first" >&2
  exit 127
fi

if [[ "$REQUIRE_ROOT" != "0" ]] && [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run this script as root, for example: sudo bash scripts/install_bwrap_apparmor.sh" >&2
  exit 1
fi

"$INSTALL_BIN" -D -m 644 "$SOURCE_PROFILE" "$DEST_PROFILE"
"$APPARMOR_PARSER_BIN" -r "$DEST_PROFILE"

echo "Installed bwrap AppArmor profile to $DEST_PROFILE"
echo "Reloaded AppArmor profile from $DEST_PROFILE"
