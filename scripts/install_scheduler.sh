#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="${JOB_AGENT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
SCHEDULER_DIR="${JOB_AGENT_SCHEDULER_DIR:-$ROOT/.scheduler}"
PLIST_FILE="$SCHEDULER_DIR/com.jvdh.jobsearch.scheduler.plist"
CRON_FILE="$SCHEDULER_DIR/cron.entry"
PLATFORM="${JOB_AGENT_PLATFORM:-$(uname -s)}"

usage() {
  cat <<EOF
Usage: $0

Install the machine-local scheduler for this checkout.
Run scripts/setup_machine.sh first or let this script refresh the generated files.
EOF
}

strip_block() {
  awk '
    $0 == "# BEGIN jobsearch scheduler" {skip = 1; next}
    $0 == "# END jobsearch scheduler" {skip = 0; next}
    !skip {print}
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

    tmp_existing="$(mktemp "${TMPDIR:-/tmp}/jobsearch-crontab-existing.XXXXXX")"
    tmp_cleaned="$(mktemp "${TMPDIR:-/tmp}/jobsearch-crontab-cleaned.XXXXXX")"
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
    DEST_PLIST="$LAUNCH_AGENTS_DIR/com.jvdh.jobsearch.scheduler.plist"
    GUI_DOMAIN="gui/$(id -u)"

    mkdir -p "$LAUNCH_AGENTS_DIR" "$ROOT/logs"
    cp "$PLIST_FILE" "$DEST_PLIST"

    "$LAUNCHCTL_BIN" bootout "$GUI_DOMAIN" "$DEST_PLIST" >/dev/null 2>&1 || true
    "$LAUNCHCTL_BIN" bootstrap "$GUI_DOMAIN" "$DEST_PLIST"
    "$LAUNCHCTL_BIN" kickstart -k "$GUI_DOMAIN/com.jvdh.jobsearch.scheduler" >/dev/null 2>&1 || true
    echo "Installed LaunchAgent at $DEST_PLIST"
    ;;
  *)
    echo "Unsupported platform: $PLATFORM" >&2
    exit 2
    ;;
esac
