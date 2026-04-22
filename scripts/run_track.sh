#!/bin/bash
set -euo pipefail

TRACK=""
DELIVERY_TARGETS=()
TIMEOUT_SECS="${TIMEOUT_SECS:-2700}"
DISCOVERY_TIMEOUT_SECS="${DISCOVERY_TIMEOUT_SECS:-1800}"
DISCOVERY_HEARTBEAT_SECS="${DISCOVERY_HEARTBEAT_SECS:-60}"
AGENT_HEARTBEAT_SECS="${AGENT_HEARTBEAT_SECS:-300}"
AGENT_IDLE_TIMEOUT_SECS="${AGENT_IDLE_TIMEOUT_SECS:-900}"
JOB_AGENT_PROVIDER="${JOB_AGENT_PROVIDER:-codex}"
JOB_AGENT_BIN="${JOB_AGENT_BIN:-}"
PLATFORM="${JOB_AGENT_PLATFORM:-$(uname -s)}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

usage() {
  echo "Usage: $0 --track <slug> [--delivery logseq|email]... [--timeout-secs <seconds>] [--discovery-timeout-secs <seconds>]" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --track)
      if [[ $# -lt 2 ]]; then
        usage
      fi
      TRACK="${2:-}"
      shift 2
      ;;
    --delivery)
      if [[ $# -lt 2 ]]; then
        usage
      fi
      case "${2:-}" in
        logseq|email)
          DELIVERY_TARGETS+=("$2")
          ;;
        *)
          usage
          ;;
      esac
      shift 2
      ;;
    --timeout-secs)
      if [[ $# -lt 2 ]]; then
        usage
      fi
      TIMEOUT_SECS="${2:-}"
      shift 2
      ;;
    --discovery-timeout-secs)
      if [[ $# -lt 2 ]]; then
        usage
      fi
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
STRUCTURED_DIGEST="$ROOT/artifacts/digests/$TRACK/$TODAY.json"
LOG_FILE="$LOG_DIR/$TRACK-$TODAY.log"

mkdir -p "$DIGEST_DIR" "$DISCOVERY_DIR" "$LOG_DIR"
exec >>"$LOG_FILE" 2>&1

timestamp() {
  date '+%Y-%m-%d %H:%M:%S'
}

log() {
  echo "[$(timestamp)] $*"
}

resolve_command_path() {
  local candidate="${1:-}"
  if [[ -z "$candidate" ]]; then
    return 1
  fi
  if [[ "$candidate" == */* ]]; then
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
    return 1
  fi
  if command -v "$candidate" >/dev/null 2>&1; then
    command -v "$candidate"
    return 0
  fi
  return 1
}

resolve_python_bin() {
  local venv_python="$ROOT/.venv/bin/python"

  if [[ -x "$venv_python" ]]; then
    printf '%s\n' "$venv_python"
    return 0
  fi

  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi

  return 1
}

canonicalize_linux_executable_path() {
  local candidate="${1:-}"
  local resolved=""

  if [[ -z "$candidate" ]]; then
    return 1
  fi

  if [[ "$PLATFORM" != "Linux" ]] || ! command -v readlink >/dev/null 2>&1; then
    printf '%s\n' "$candidate"
    return 0
  fi

  resolved="$(readlink -f "$candidate" 2>/dev/null || true)"
  if [[ -n "$resolved" && -x "$resolved" ]]; then
    printf '%s\n' "$resolved"
    return 0
  fi

  printf '%s\n' "$candidate"
}

resolve_agent_provider() {
  local provider="${JOB_AGENT_PROVIDER:-codex}"
  case "$provider" in
    codex|claude)
      printf '%s\n' "$provider"
      ;;
    *)
      return 1
      ;;
  esac
}

agent_default_binary_name() {
  case "$1" in
    codex)
      printf 'codex\n'
      ;;
    claude)
      printf 'claude\n'
      ;;
    *)
      return 1
      ;;
  esac
}

agent_label() {
  case "$1" in
    codex)
      printf 'Codex\n'
      ;;
    claude)
      printf 'Claude\n'
      ;;
    *)
      printf 'Agent\n'
      ;;
  esac
}

resolve_agent_bin() {
  local provider="$1"
  local candidate=""
  local default_bin=""

  if [[ -n "$JOB_AGENT_BIN" ]]; then
    if ! candidate="$(resolve_command_path "$JOB_AGENT_BIN" 2>/dev/null)"; then
      return 1
    fi
    canonicalize_linux_executable_path "$candidate"
    return 0
  fi

  default_bin="$(agent_default_binary_name "$provider")"
  if candidate="$(resolve_command_path "$default_bin" 2>/dev/null)"; then
    canonicalize_linux_executable_path "$candidate"
    return 0
  fi
  return 1
}

if ! AGENT_PROVIDER="$(resolve_agent_provider)"; then
  log "invalid JOB_AGENT_PROVIDER '$JOB_AGENT_PROVIDER'; expected codex or claude"
  exit 2
fi
AGENT_LABEL="$(agent_label "$AGENT_PROVIDER")"

if ! AGENT_BIN="$(resolve_agent_bin "$AGENT_PROVIDER")"; then
  log "$AGENT_LABEL binary not found; set JOB_AGENT_BIN or add $(agent_default_binary_name "$AGENT_PROVIDER") to PATH"
  exit 127
fi

if ! PYTHON_BIN="$(resolve_python_bin)"; then
  log "python3 not found and repo-local virtualenv is missing"
  exit 127
fi

log "Using discovery Python interpreter: $PYTHON_BIN"
log "Using $AGENT_LABEL provider via $AGENT_BIN"

LAST_BG_PID=""

stop_helper() {
  local pid="${1:-}"
  if [[ -z "$pid" ]]; then
    return
  fi
  pkill -TERM -P "$pid" 2>/dev/null || true
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  pkill -KILL -P "$pid" 2>/dev/null || true
}

terminate_process() {
  local target_pid="$1"
  local label="$2"

  kill "$target_pid" 2>/dev/null || true
  sleep 5
  if kill -0 "$target_pid" 2>/dev/null; then
    log "$label still running after TERM; forcing kill"
    kill -9 "$target_pid" 2>/dev/null || true
  fi
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
      terminate_process "$target_pid" "$label"
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

start_idle_watchdog() {
  local target_pid="$1"
  local idle_timeout_secs="$2"
  local label="$3"
  local activity_file="$4"
  local flag_file="$5"
  local poll_secs=5

  if [[ "$idle_timeout_secs" -le 0 ]]; then
    LAST_BG_PID=""
    return
  fi

  if [[ "$idle_timeout_secs" -lt "$poll_secs" ]]; then
    poll_secs="$idle_timeout_secs"
  fi
  if [[ "$poll_secs" -lt 1 ]]; then
    poll_secs=1
  fi

  (
    while kill -0 "$target_pid" 2>/dev/null; do
      sleep "$poll_secs"
      if ! kill -0 "$target_pid" 2>/dev/null; then
        break
      fi

      local last_activity=""
      if [[ -f "$activity_file" ]]; then
        last_activity="$(cat "$activity_file" 2>/dev/null || true)"
      fi
      if [[ ! "$last_activity" =~ ^[0-9]+$ ]]; then
        continue
      fi

      local now
      now="$(date +%s)"
      if (( now - last_activity >= idle_timeout_secs )); then
        : >"$flag_file"
        log "$label went idle after ${idle_timeout_secs}s without new output; terminating"
        terminate_process "$target_pid" "$label"
        break
      fi
    done
  ) &

  LAST_BG_PID="$!"
}

if [[ -z "${JOB_AGENT_CAFFEINATED:-}" ]]; then
  if CAFFEINATE_BIN="$(command -v caffeinate 2>/dev/null)"; then
    REEXEC_ARGS=(--track "$TRACK" --timeout-secs "$TIMEOUT_SECS" --discovery-timeout-secs "$DISCOVERY_TIMEOUT_SECS")
    for delivery_target in "${DELIVERY_TARGETS[@]}"; do
      REEXEC_ARGS+=(--delivery "$delivery_target")
    done
    log "Re-executing $TRACK run under caffeinate via $CAFFEINATE_BIN"
    exec env JOB_AGENT_CAFFEINATED=1 "$CAFFEINATE_BIN" -dimsu /bin/bash "$0" "${REEXEC_ARGS[@]}"
  fi
  log "caffeinate unavailable; continuing without wake prevention"
else
  log "Wake prevention active via caffeinate"
fi

PROMPT_FILE="$(mktemp "${TMPDIR:-/tmp}/${TRACK}-prompt.XXXXXX")"
DISCOVERY_TIMEOUT_FLAG="${TMPDIR:-/tmp}/${TRACK}-discovery-timeout.$$"
AGENT_TIMEOUT_FLAG="${TMPDIR:-/tmp}/${TRACK}-${AGENT_PROVIDER}-timeout.$$"
AGENT_IDLE_FLAG="${TMPDIR:-/tmp}/${TRACK}-${AGENT_PROVIDER}-idle.$$"
AGENT_ACTIVITY_FILE="${TMPDIR:-/tmp}/${TRACK}-${AGENT_PROVIDER}-activity.$$"
AGENT_OUTPUT_PIPE="${TMPDIR:-/tmp}/${TRACK}-${AGENT_PROVIDER}-output.$$"
rm -f "$DISCOVERY_TIMEOUT_FLAG" "$AGENT_TIMEOUT_FLAG" "$AGENT_IDLE_FLAG" "$AGENT_ACTIVITY_FILE" "$AGENT_OUTPUT_PIPE"
trap 'rm -f "$PROMPT_FILE" "$DISCOVERY_TIMEOUT_FLAG" "$AGENT_TIMEOUT_FLAG" "$AGENT_IDLE_FLAG" "$AGENT_ACTIVITY_FILE" "$AGENT_OUTPUT_PIPE"' EXIT

log "Starting $TRACK daily run"
log "Discovery phase started"

"$PYTHON_BIN" "$ROOT/scripts/discover_jobs.py" \
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
  log "Discovery phase timed out after ${DISCOVERY_TIMEOUT_SECS}s; $AGENT_LABEL will fall back to live discovery as needed"
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
  log "Discovery artifact generation failed with status $DISCOVERY_STATUS; $AGENT_LABEL will fall back to live discovery as needed"
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
Follow tracks/$TRACK/AGENTS.md for the workflow.
$DISCOVERY_PROMPT_BLOCK
This is a normal scheduled run, not a debugging session.
Do not inspect ./logs or downstream publication targets such as the configured Logseq graph unless explicitly asked to debug the runner.
EOF

run_agent_command() {
  case "$AGENT_PROVIDER" in
    codex)
      "$AGENT_BIN" --search -a never exec -C "$ROOT" -s workspace-write - <"$PROMPT_FILE"
      ;;
    claude)
      (
        cd "$ROOT"
        "$AGENT_BIN" \
          -p \
          --no-session-persistence \
          --output-format stream-json \
          --permission-mode "${JOB_AGENT_CLAUDE_PERMISSION_MODE:-acceptEdits}" \
          --allowedTools "${JOB_AGENT_CLAUDE_SCHEDULED_ALLOWED_TOOLS:-Read,Write,Edit,MultiEdit,Bash,Glob,Grep,LS,TodoWrite}" \
          --verbose \
          <"$PROMPT_FILE"
      )
      ;;
    *)
      return 2
      ;;
  esac
}

log "$AGENT_LABEL phase started"
mkfifo "$AGENT_OUTPUT_PIPE"
printf '%s\n' "$(date +%s)" >"$AGENT_ACTIVITY_FILE"
(
  while IFS= read -r line || [[ -n "$line" ]]; do
    printf '%s\n' "$line"
    printf '%s\n' "$(date +%s)" >"$AGENT_ACTIVITY_FILE"
  done <"$AGENT_OUTPUT_PIPE"
) &
AGENT_READER_PID=$!

(
  export JOB_AGENT_ROOT="$ROOT"
  export JOB_AGENT_TRACK="$TRACK"
  export JOB_AGENT_TODAY="$TODAY"
  export JOB_AGENT_PROVIDER="$AGENT_PROVIDER"
  export JOB_AGENT_BIN="$AGENT_BIN"
  run_agent_command
) >"$AGENT_OUTPUT_PIPE" 2>&1 &
AGENT_PID=$!
start_timeout_watchdog "$AGENT_PID" "$TIMEOUT_SECS" "$AGENT_LABEL" "$AGENT_TIMEOUT_FLAG"
AGENT_WATCHDOG_PID="$LAST_BG_PID"
if [[ "$AGENT_HEARTBEAT_SECS" -gt 0 ]]; then
  start_heartbeat "$AGENT_PID" "$AGENT_HEARTBEAT_SECS" "$AGENT_LABEL"
  AGENT_HEARTBEAT_PID="$LAST_BG_PID"
else
  AGENT_HEARTBEAT_PID=""
fi
start_idle_watchdog "$AGENT_PID" "$AGENT_IDLE_TIMEOUT_SECS" "$AGENT_LABEL" "$AGENT_ACTIVITY_FILE" "$AGENT_IDLE_FLAG"
AGENT_IDLE_WATCHDOG_PID="$LAST_BG_PID"

set +e
wait "$AGENT_PID"
AGENT_STATUS=$?
set -e

stop_helper "$AGENT_WATCHDOG_PID"
stop_helper "$AGENT_HEARTBEAT_PID"
stop_helper "$AGENT_IDLE_WATCHDOG_PID"
wait "$AGENT_READER_PID" 2>/dev/null || true

if [[ -f "$AGENT_TIMEOUT_FLAG" ]]; then
  log "$AGENT_LABEL phase timed out after ${TIMEOUT_SECS}s"
  exit 124
fi

if [[ -f "$AGENT_IDLE_FLAG" ]]; then
  log "$AGENT_LABEL phase went idle after ${AGENT_IDLE_TIMEOUT_SECS}s without new output"
  exit 125
fi

if [[ $AGENT_STATUS -ne 0 ]]; then
  log "$AGENT_LABEL exited with status $AGENT_STATUS"
  exit "$AGENT_STATUS"
fi

log "$AGENT_LABEL phase finished successfully"

if [[ $DISCOVERY_STATUS -eq 0 && -f "$DISCOVERY_ARTIFACT" ]]; then
  log "Source state update started"
  if "$PYTHON_BIN" "$ROOT/scripts/update_source_state.py" --track "$TRACK" --date "$TODAY" --artifact "$DISCOVERY_ARTIFACT"; then
    log "Source state update finished successfully"
  else
    state_status=$?
    log "Source state update failed with status $state_status"
    exit "$state_status"
  fi
else
  log "Skipping source state update because no complete fresh discovery artifact is available"
fi

if [[ -f "$STRUCTURED_DIGEST" ]]; then
  log "Rendering markdown digest from $STRUCTURED_DIGEST"
  if "$PYTHON_BIN" "$ROOT/scripts/render_digest.py" --track "$TRACK" --date "$TODAY"; then
    log "Markdown digest rendered successfully"
  else
    render_status=$?
    log "Markdown digest rendering failed with status $render_status"
    exit "$render_status"
  fi
else
  log "No structured digest at $STRUCTURED_DIGEST; skipping markdown rendering"
fi

if [[ -f "$STRUCTURED_DIGEST" ]]; then
  log "Updating seen jobs for $TRACK from $STRUCTURED_DIGEST"
  if "$PYTHON_BIN" "$ROOT/scripts/update_seen_jobs.py" --track "$TRACK" --date "$TODAY"; then
    log "Seen jobs updated successfully"
  else
    seen_status=$?
    log "Seen jobs update failed with status $seen_status"
    exit "$seen_status"
  fi
else
  log "No structured digest at $STRUCTURED_DIGEST; skipping seen-jobs update"
fi

log "Rebuilding ranked overview for $TRACK"
if "$PYTHON_BIN" "$ROOT/scripts/update_ranked_overview.py" --track "$TRACK"; then
  log "Ranked overview rebuilt successfully"
else
  ranked_status=$?
  log "Ranked overview rebuild failed with status $ranked_status"
  exit "$ranked_status"
fi

if [[ ${#DELIVERY_TARGETS[@]} -eq 0 ]]; then
  log "No delivery targets requested; leaving local artifacts only"
else
  for delivery_target in "${DELIVERY_TARGETS[@]}"; do
    log "Delivery phase started: $delivery_target"
    case "$delivery_target" in
      logseq)
        if [[ -f "$DAILY_DIGEST" ]]; then
          if /bin/bash "$ROOT/scripts/sync_to_logseq.sh" --track "$TRACK"; then
            log "Delivery phase finished successfully: logseq"
          else
            delivery_status=$?
            log "Delivery phase failed: logseq status $delivery_status"
            exit "$delivery_status"
          fi
        else
          log "No digest at $DAILY_DIGEST; skipping logseq delivery"
        fi
        ;;
      email)
        if [[ -f "$STRUCTURED_DIGEST" ]]; then
          if JOB_AGENT_ROOT="$ROOT" "$PYTHON_BIN" "$ROOT/scripts/send_digest_email.py" --track "$TRACK" --date "$TODAY"; then
            log "Delivery phase finished successfully: email"
          else
            delivery_status=$?
            log "Delivery phase failed: email status $delivery_status"
            exit "$delivery_status"
          fi
        else
          log "No structured digest at $STRUCTURED_DIGEST; skipping email delivery"
        fi
        ;;
      *)
        log "Unsupported delivery target: $delivery_target"
        exit 2
        ;;
    esac
  done
fi

log "Finished $TRACK daily run"
