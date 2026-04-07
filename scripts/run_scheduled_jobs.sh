#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="${JOB_AGENT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
ENV_FILE="${JOB_AGENT_ENV_FILE:-$ROOT/.env.local}"
SCHEDULE_FILE="${JOB_AGENT_SCHEDULE_FILE:-$ROOT/.schedule.local}"
SCHEDULER_DIR="${JOB_AGENT_SCHEDULER_DIR:-$ROOT/.scheduler}"

if [[ -f "$ENV_FILE" ]]; then
  set +u
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set -u
fi

ROOT="${JOB_AGENT_ROOT:-$ROOT}"
SCHEDULE_FILE="${JOB_AGENT_SCHEDULE_FILE:-$SCHEDULE_FILE}"
SCHEDULER_DIR="${JOB_AGENT_SCHEDULER_DIR:-$SCHEDULER_DIR}"
STATE_DIR="${JOB_AGENT_SCHEDULER_STATE_DIR:-$SCHEDULER_DIR/state}"
LOCK_DIR="$SCHEDULER_DIR/run.lock"
CURRENT_TIME="${JOB_AGENT_SCHEDULE_TIME:-$(date +%H:%M)}"
CURRENT_STAMP="${JOB_AGENT_SCHEDULE_STAMP:-$(date +%F-%H:%M)}"
STATUS=0

trim_line() {
  local value="$1"
  value="${value%$'\r'}"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s\n' "$value"
}

mkdir -p "$STATE_DIR" "$ROOT/logs"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "Scheduler already running; exiting" >&2
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

if [[ ! -f "$SCHEDULE_FILE" ]]; then
  exit 0
fi

while IFS= read -r raw_line || [[ -n "$raw_line" ]]; do
  line="$(trim_line "$raw_line")"
  if [[ -z "$line" || "${line:0:1}" == "#" ]]; then
    continue
  fi

  cadence=""
  scheduled_time=""
  job_type=""
  job_arg=""
  extra=""
  read -r cadence scheduled_time job_type job_arg extra <<<"$line"

  if [[ "$cadence" != "daily" || ! "$scheduled_time" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ || -z "$job_type" || -z "$job_arg" || -n "$extra" ]]; then
    echo "Invalid schedule entry: $line" >&2
    STATUS=1
    continue
  fi

  if [[ "$scheduled_time" != "$CURRENT_TIME" ]]; then
    continue
  fi

  case "$job_type" in
    track)
      ;;
    *)
      echo "Unsupported schedule job type '$job_type' in: $line" >&2
      STATUS=1
      continue
      ;;
  esac

  state_key="$(printf '%s-%s' "$job_type" "$job_arg" | tr -cs 'A-Za-z0-9._-' '_')"
  state_file="$STATE_DIR/$state_key.stamp"

  if [[ -f "$state_file" ]] && [[ "$(cat "$state_file")" == "$CURRENT_STAMP" ]]; then
    continue
  fi

  printf '%s\n' "$CURRENT_STAMP" >"$state_file"
  echo "Running scheduled track '$job_arg' for $CURRENT_STAMP"
  if /bin/bash "$ROOT/scripts/run_track.sh" --track "$job_arg"; then
    :
  else
    cmd_status=$?
    echo "Scheduled track '$job_arg' failed with status $cmd_status" >&2
    STATUS=$cmd_status
  fi
done <"$SCHEDULE_FILE"

exit "$STATUS"
