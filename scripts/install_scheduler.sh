#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="${JOB_AGENT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
SCHEDULER_DIR="${JOB_AGENT_SCHEDULER_DIR:-$ROOT/.scheduler}"
CRON_FILE="$SCHEDULER_DIR/cron.entry"
PLATFORM="${JOB_AGENT_PLATFORM:-$(uname -s)}"

scheduler_instance_id() {
  local root="$1"
  local canonical_root=""
  local base=""
  local safe_base=""
  local checksum=""

  if canonical_root="$(cd "$root" 2>/dev/null && pwd -P)"; then
    :
  else
    canonical_root="$root"
  fi

  base="$(basename "$canonical_root")"
  safe_base="$(printf '%s' "$base" | LC_ALL=C tr '[:upper:]' '[:lower:]' | LC_ALL=C sed 's/[^a-z0-9]/-/g; s/-\{1,\}/-/g; s/^-//; s/-$//')"
  safe_base="${safe_base:-checkout}"
  safe_base="${safe_base:0:48}"
  checksum="$(printf '%s' "$canonical_root" | cksum | awk '{print $1}')"

  printf '%s-%s\n' "$safe_base" "$checksum"
}

SCHEDULER_INSTANCE_ID="$(scheduler_instance_id "$ROOT")"
SCHEDULER_LABEL="com.jvdh.jobwatch.scheduler.$SCHEDULER_INSTANCE_ID"
PLIST_FILE="$SCHEDULER_DIR/$SCHEDULER_LABEL.plist"
CRON_BEGIN="# BEGIN jobwatch scheduler $SCHEDULER_INSTANCE_ID"
CRON_END="# END jobwatch scheduler $SCHEDULER_INSTANCE_ID"

usage() {
  cat <<EOF
Usage: $0

Install the machine-local scheduler for this checkout.
Run scripts/setup_machine.sh --agent codex, --agent claude, or --agent gemini first. This script
refreshes generated files from the existing machine-local config.
EOF
}

strip_block() {
  awk \
    -v begin="$CRON_BEGIN" \
    -v end="$CRON_END" '
    in_current && $0 == end {
      in_current = 0
      next
    }
    in_current {
      next
    }
    $0 == begin {
      in_current = 1
      next
    }
    {
      print
    }
  ' "$1"
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

case "$PLATFORM" in
  Linux)
    CRONTAB_BIN="${CRONTAB_BIN:-$(command -v crontab || true)}"
    if [[ -z "$CRONTAB_BIN" ]]; then
      echo "crontab not found; install cron first" >&2
      exit 127
    fi

    tmp_existing="$(mktemp "${TMPDIR:-/tmp}/jobwatch-crontab-existing.XXXXXX")"
    tmp_cleaned="$(mktemp "${TMPDIR:-/tmp}/jobwatch-crontab-cleaned.XXXXXX")"
    trap 'rm -f "$tmp_existing" "$tmp_cleaned"' EXIT

    if ! "$CRONTAB_BIN" -l >"$tmp_existing" 2>/dev/null; then
      : >"$tmp_existing"
    fi

    strip_block "$tmp_existing" >"$tmp_cleaned"
    if [[ -s "$tmp_cleaned" ]]; then
      echo >>"$tmp_cleaned"
    fi
    cat "$CRON_FILE" >>"$tmp_cleaned"

    "$CRONTAB_BIN" "$tmp_cleaned"
    echo "Installed cron entry from $CRON_FILE"
    ;;
  Darwin)
    LAUNCHCTL_BIN="${LAUNCHCTL_BIN:-$(command -v launchctl || true)}"
    if [[ -z "$LAUNCHCTL_BIN" ]]; then
      echo "launchctl not found" >&2
      exit 127
    fi

    LAUNCH_AGENTS_DIR="${JOB_AGENT_LAUNCH_AGENTS_DIR:-${HOME}/Library/LaunchAgents}"
    DEST_PLIST="$LAUNCH_AGENTS_DIR/$SCHEDULER_LABEL.plist"
    GUI_DOMAIN="gui/$(id -u)"

    mkdir -p "$LAUNCH_AGENTS_DIR" "$ROOT/logs"
    cp "$PLIST_FILE" "$DEST_PLIST"

    "$LAUNCHCTL_BIN" bootout "$GUI_DOMAIN" "$DEST_PLIST" >/dev/null 2>&1 || true
    "$LAUNCHCTL_BIN" bootstrap "$GUI_DOMAIN" "$DEST_PLIST"
    "$LAUNCHCTL_BIN" kickstart -k "$GUI_DOMAIN/$SCHEDULER_LABEL" >/dev/null 2>&1 || true
    echo "Installed LaunchAgent at $DEST_PLIST"
    ;;
  *)
    echo "Unsupported platform: $PLATFORM" >&2
    exit 2
    ;;
esac
