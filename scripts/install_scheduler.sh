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

canonical_root() {
  local root="$1"
  local resolved=""

  if resolved="$(cd "$root" 2>/dev/null && pwd -P)"; then
    printf '%s\n' "$resolved"
  else
    printf '%s\n' "$root"
  fi
}

shell_escape() {
  printf '%q' "$1"
}

file_references_current_root() {
  local file="$1"
  local runner_path="$ROOT/scripts/run_scheduled_jobs.sh"
  local canonical_runner_path="$ROOT_CANONICAL/scripts/run_scheduled_jobs.sh"

  [[ -f "$file" ]] || return 1

  if grep -F "$runner_path" "$file" >/dev/null 2>&1; then
    return 0
  fi
  if [[ "$canonical_runner_path" != "$runner_path" ]] && grep -F "$canonical_runner_path" "$file" >/dev/null 2>&1; then
    return 0
  fi

  return 1
}

ROOT_CANONICAL="$(canonical_root "$ROOT")"
SCHEDULER_INSTANCE_ID="$(scheduler_instance_id "$ROOT")"
SCHEDULER_LABEL="com.jvdh.jobsearch.scheduler.$SCHEDULER_INSTANCE_ID"
PLIST_FILE="$SCHEDULER_DIR/$SCHEDULER_LABEL.plist"
LEGACY_SCHEDULER_LABEL="com.jvdh.jobsearch.scheduler"
CRON_BEGIN="# BEGIN jobsearch scheduler $SCHEDULER_INSTANCE_ID"
CRON_END="# END jobsearch scheduler $SCHEDULER_INSTANCE_ID"

usage() {
  cat <<EOF
Usage: $0

Install the machine-local scheduler for this checkout.
Run scripts/setup_machine.sh --agent codex or --agent claude first. This script
refreshes generated files from the existing machine-local config.
EOF
}

strip_block() {
  local runner_path="$ROOT/scripts/run_scheduled_jobs.sh"
  local canonical_runner_path="$ROOT_CANONICAL/scripts/run_scheduled_jobs.sh"
  local runner_path_escaped=""
  local canonical_runner_path_escaped=""

  runner_path_escaped="$(shell_escape "$runner_path")"
  canonical_runner_path_escaped="$(shell_escape "$canonical_runner_path")"

  awk \
    -v begin="$CRON_BEGIN" \
    -v end="$CRON_END" \
    -v legacy_begin="# BEGIN jobsearch scheduler" \
    -v legacy_end="# END jobsearch scheduler" \
    -v runner_path="$runner_path" \
    -v canonical_runner_path="$canonical_runner_path" \
    -v runner_path_escaped="$runner_path_escaped" \
    -v canonical_runner_path_escaped="$canonical_runner_path_escaped" '
    function reset_legacy() {
      legacy_count = 0
      legacy_refs_current = 0
    }
    function print_legacy(    i) {
      for (i = 1; i <= legacy_count; i++) {
        print legacy_lines[i]
      }
    }
    in_current && $0 == end {
      in_current = 0
      next
    }
    in_current {
      next
    }
    in_legacy {
      legacy_lines[++legacy_count] = $0
      if (index($0, runner_path) || index($0, canonical_runner_path) || index($0, runner_path_escaped) || index($0, canonical_runner_path_escaped)) {
        legacy_refs_current = 1
      }
      if ($0 == legacy_end) {
        if (!legacy_refs_current) {
          print_legacy()
        }
        in_legacy = 0
        reset_legacy()
      }
      next
    }
    $0 == begin {
      in_current = 1
      next
    }
    $0 == legacy_begin {
      in_legacy = 1
      reset_legacy()
      legacy_lines[++legacy_count] = $0
      next
    }
    {
      print
    }
    END {
      if (in_legacy && !legacy_refs_current) {
        print_legacy()
      }
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
    DEST_PLIST="$LAUNCH_AGENTS_DIR/$SCHEDULER_LABEL.plist"
    LEGACY_DEST_PLIST="$LAUNCH_AGENTS_DIR/$LEGACY_SCHEDULER_LABEL.plist"
    GUI_DOMAIN="gui/$(id -u)"

    mkdir -p "$LAUNCH_AGENTS_DIR" "$ROOT/logs"
    cp "$PLIST_FILE" "$DEST_PLIST"

    if file_references_current_root "$LEGACY_DEST_PLIST"; then
      "$LAUNCHCTL_BIN" bootout "$GUI_DOMAIN" "$LEGACY_DEST_PLIST" >/dev/null 2>&1 || true
      rm -f "$LEGACY_DEST_PLIST"
    fi
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
