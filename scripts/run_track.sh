#!/bin/bash
set -euo pipefail

TRACK=""
TIMEOUT_SECS="${TIMEOUT_SECS:-2700}"
DISCOVERY_TIMEOUT_SECS="${DISCOVERY_TIMEOUT_SECS:-1800}"
DISCOVERY_HEARTBEAT_SECS="${DISCOVERY_HEARTBEAT_SECS:-60}"
CODEX_BIN="${CODEX_BIN:-/opt/homebrew/bin/codex}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

usage() {
  echo "Usage: $0 --track <slug> [--timeout-secs <seconds>] [--discovery-timeout-secs <seconds>]" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --track)
      TRACK="${2:-}"
      shift 2
      ;;
    --timeout-secs)
      TIMEOUT_SECS="${2:-}"
      shift 2
      ;;
    --discovery-timeout-secs)
      DISCOVERY_TIMEOUT_SECS="${2:-}"
      shift 2
      ;;
    *)
      usage
      ;;
  esac
done

if [[ -z "$TRACK" ]]; then
  usage
fi

ROOT="${JOB_AGENT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
DIGEST_DIR="$ROOT/tracks/$TRACK/digests"
LOG_DIR="$ROOT/logs"
TODAY="${JOB_AGENT_TODAY:-$(date +%F)}"
DISCOVERY_DIR="$ROOT/artifacts/discovery/$TRACK"
DISCOVERY_ARTIFACT="$DISCOVERY_DIR/$TODAY.json"
DISCOVERY_LATEST="$DISCOVERY_DIR/latest.json"
DAILY_DIGEST="$DIGEST_DIR/$TODAY.md"
LOG_FILE="$LOG_DIR/$TRACK-$TODAY.log"

mkdir -p "$DIGEST_DIR" "$DISCOVERY_DIR" "$LOG_DIR"
exec >>"$LOG_FILE" 2>&1

timestamp() {
  date '+%Y-%m-%d %H:%M:%S'
}

log() {
  echo "[$(timestamp)] $*"
}

LAST_BG_PID=""

stop_helper() {
  local pid="${1:-}"
  if [[ -z "$pid" ]]; then
    return
  fi
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}

start_timeout_watchdog() {
  local target_pid="$1"
  local timeout_secs="$2"
  local label="$3"
  local flag_file="$4"

  (
    sleep "$timeout_secs"
    if kill -0 "$target_pid" 2>/dev/null; then
      : >"$flag_file"
      log "$label exceeded ${timeout_secs}s; terminating"
      kill "$target_pid" 2>/dev/null || true
      sleep 5
      if kill -0 "$target_pid" 2>/dev/null; then
        log "$label still running after TERM; forcing kill"
        kill -9 "$target_pid" 2>/dev/null || true
      fi
    fi
  ) &

  LAST_BG_PID="$!"
}

start_heartbeat() {
  local target_pid="$1"
  local interval_secs="$2"
  local label="$3"
  local started_at
  started_at="$(date +%s)"

  (
    while kill -0 "$target_pid" 2>/dev/null; do
      sleep "$interval_secs"
      if kill -0 "$target_pid" 2>/dev/null; then
        now="$(date +%s)"
        log "$label still running after $((now - started_at))s"
      fi
    done
  ) &

  LAST_BG_PID="$!"
}

if [[ -z "${JOB_AGENT_CAFFEINATED:-}" ]]; then
  if CAFFEINATE_BIN="$(command -v caffeinate 2>/dev/null)"; then
    log "Re-executing $TRACK run under caffeinate via $CAFFEINATE_BIN"
    exec env JOB_AGENT_CAFFEINATED=1 "$CAFFEINATE_BIN" -dimsu /bin/bash "$0" \
      --track "$TRACK" \
      --timeout-secs "$TIMEOUT_SECS" \
      --discovery-timeout-secs "$DISCOVERY_TIMEOUT_SECS"
  fi
  log "caffeinate unavailable; continuing without wake prevention"
else
  log "Wake prevention active via caffeinate"
fi

PROMPT_FILE="$(mktemp "${TMPDIR:-/tmp}/${TRACK}-prompt.XXXXXX")"
DISCOVERY_TIMEOUT_FLAG="${TMPDIR:-/tmp}/${TRACK}-discovery-timeout.$$"
CODEX_TIMEOUT_FLAG="${TMPDIR:-/tmp}/${TRACK}-codex-timeout.$$"
rm -f "$DISCOVERY_TIMEOUT_FLAG" "$CODEX_TIMEOUT_FLAG"
trap 'rm -f "$PROMPT_FILE" "$DISCOVERY_TIMEOUT_FLAG" "$CODEX_TIMEOUT_FLAG"' EXIT

log "Starting $TRACK daily run"
log "Discovery phase started"

python3 "$ROOT/scripts/discover_jobs.py" \
  --track "$TRACK" \
  --today "$TODAY" \
  --due-only \
  --pretty \
  --progress \
  --output "$DISCOVERY_ARTIFACT" \
  --latest-output "$DISCOVERY_LATEST" &
DISCOVERY_PID=$!
start_timeout_watchdog "$DISCOVERY_PID" "$DISCOVERY_TIMEOUT_SECS" "Discovery" "$DISCOVERY_TIMEOUT_FLAG"
DISCOVERY_WATCHDOG_PID="$LAST_BG_PID"
start_heartbeat "$DISCOVERY_PID" "$DISCOVERY_HEARTBEAT_SECS" "Discovery"
DISCOVERY_HEARTBEAT_PID="$LAST_BG_PID"

set +e
wait "$DISCOVERY_PID"
DISCOVERY_STATUS=$?
set -e

stop_helper "$DISCOVERY_WATCHDOG_PID"
stop_helper "$DISCOVERY_HEARTBEAT_PID"

DISCOVERY_PROMPT_BLOCK=""
if [[ $DISCOVERY_STATUS -eq 0 ]]; then
  log "Discovery phase finished successfully"
  if [[ -f "$DISCOVERY_ARTIFACT" ]]; then
    log "Wrote discovery artifact to $DISCOVERY_ARTIFACT"
  fi
  DISCOVERY_PROMPT_BLOCK=$(cat <<EOF
A discovery artifact for today's scheduled run has already been written to ./artifacts/discovery/$TRACK/$TODAY.json and ./artifacts/discovery/$TRACK/latest.json.
Use those artifact files directly as the primary discovery input.
Do not rerun ./scripts/discover_jobs.py during this scheduled pass unless the artifact is missing, stale, or inconsistent with today's due sources.
EOF
)
elif [[ -f "$DISCOVERY_TIMEOUT_FLAG" ]]; then
  log "Discovery phase timed out after ${DISCOVERY_TIMEOUT_SECS}s; Codex will fall back to live discovery as needed"
  if [[ -f "$DISCOVERY_ARTIFACT" ]]; then
    DISCOVERY_PROMPT_BLOCK=$(cat <<EOF
Today's discovery artifact already exists at ./artifacts/discovery/$TRACK/$TODAY.json, but the fresh scheduled regeneration timed out.
Use the existing artifact only if it is still fresh and consistent with today's due sources; otherwise fall back to live discovery for affected sources.
EOF
)
  else
    DISCOVERY_PROMPT_BLOCK=$(cat <<EOF
No fresh discovery artifact is available for today's scheduled run because artifact generation timed out.
Fall back to live discovery only as needed for today's due sources.
EOF
)
  fi
else
  log "Discovery artifact generation failed with status $DISCOVERY_STATUS; Codex will fall back to live discovery as needed"
  if [[ -f "$DISCOVERY_ARTIFACT" ]]; then
    DISCOVERY_PROMPT_BLOCK=$(cat <<EOF
Today's discovery artifact already exists at ./artifacts/discovery/$TRACK/$TODAY.json, but the fresh scheduled regeneration failed.
Use the existing artifact only if it is still fresh and consistent with today's due sources; otherwise fall back to live discovery for affected sources.
EOF
)
  else
    DISCOVERY_PROMPT_BLOCK=$(cat <<EOF
No fresh discovery artifact is available for today's scheduled run because artifact generation failed.
Fall back to live discovery only as needed for today's due sources.
EOF
)
  fi
fi

cat >"$PROMPT_FILE" <<EOF
Run today's $TRACK workflow from the repository root in mode: track_run.
Follow the repository AGENTS.md for mode routing, then follow tracks/$TRACK/AGENTS.md for the workflow.
Use scripted discovery helpers when available.
$DISCOVERY_PROMPT_BLOCK
This is a normal scheduled run, not a debugging session.
Do not inspect ./logs or downstream publication targets such as /Users/jvdh/Documents/logseq unless explicitly asked to debug the runner.
EOF

log "Codex phase started"
JOB_AGENT_ROOT="$ROOT" \
JOB_AGENT_TRACK="$TRACK" \
JOB_AGENT_TODAY="$TODAY" \
"$CODEX_BIN" --search -a never exec -C "$ROOT" -s workspace-write - <"$PROMPT_FILE" &
CODEX_PID=$!
start_timeout_watchdog "$CODEX_PID" "$TIMEOUT_SECS" "Codex" "$CODEX_TIMEOUT_FLAG"
WATCHDOG_PID="$LAST_BG_PID"

set +e
wait "$CODEX_PID"
CODEX_STATUS=$?
set -e

stop_helper "$WATCHDOG_PID"

if [[ $CODEX_STATUS -ne 0 ]]; then
  if [[ -f "$CODEX_TIMEOUT_FLAG" ]]; then
    log "Codex phase timed out after ${TIMEOUT_SECS}s"
  fi
  log "Codex exited with status $CODEX_STATUS"
  exit "$CODEX_STATUS"
fi

log "Codex phase finished successfully"

if [[ -f "$DAILY_DIGEST" ]]; then
  log "Sync phase started"
  /bin/bash "$ROOT/scripts/sync_to_logseq.sh" --track "$TRACK"
  log "Sync phase finished successfully"
else
  log "No digest at $DAILY_DIGEST; skipping Logseq sync"
fi

log "Finished $TRACK daily run"
