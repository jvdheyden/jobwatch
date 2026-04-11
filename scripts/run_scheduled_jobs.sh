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
CURRENT_WEEKDAY_RAW="${JOB_AGENT_SCHEDULE_WEEKDAY:-$(LC_ALL=C date +%a)}"
CURRENT_MONTH_DAY="${JOB_AGENT_SCHEDULE_MONTH_DAY:-$(date +%d)}"
STATUS=0

trim_line() {
  local value="$1"
  value="${value%$'\r'}"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s\n' "$value"
}

normalize_weekday() {
  local value="$1"
  value="$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')"
  case "$value" in
    mon|monday) printf 'mon\n' ;;
    tue|tues|tuesday) printf 'tue\n' ;;
    wed|wednesday) printf 'wed\n' ;;
    thu|thur|thurs|thursday) printf 'thu\n' ;;
    fri|friday) printf 'fri\n' ;;
    sat|saturday) printf 'sat\n' ;;
    sun|sunday) printf 'sun\n' ;;
    *) return 1 ;;
  esac
}

is_valid_month_day() {
  local value="$1"
  case "$value" in
    ""|*[!0-9]*)
      return 1
      ;;
  esac
  value="${value#0}"
  [[ -n "$value" && "$value" -ge 1 && "$value" -le 31 ]]
}

canonical_month_day() {
  local value="$1"
  value="${value#0}"
  printf '%s\n' "$value"
}

if ! CURRENT_WEEKDAY="$(normalize_weekday "$CURRENT_WEEKDAY_RAW")"; then
  echo "Invalid current weekday: $CURRENT_WEEKDAY_RAW" >&2
  exit 2
fi

if ! is_valid_month_day "$CURRENT_MONTH_DAY"; then
  echo "Invalid current month day: $CURRENT_MONTH_DAY" >&2
  exit 2
fi
CURRENT_MONTH_DAY="$(canonical_month_day "$CURRENT_MONTH_DAY")"

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

  fields=()
  read -r -a fields <<<"$line"

  if [[ ${#fields[@]} -lt 4 ]]; then
    echo "Invalid schedule entry: $line" >&2
    STATUS=1
    continue
  fi

  cadence="${fields[0]}"
  scheduled_time=""
  scheduled_weekday=""
  scheduled_month_day=""
  job_type=""
  job_arg=""
  delivery_args=()
  field_index=0
  valid_entry=1
  due_entry=0

  case "$cadence" in
    daily)
      if [[ ${#fields[@]} -lt 4 ]]; then
        valid_entry=0
      else
        scheduled_time="${fields[1]}"
        job_type="${fields[2]}"
        job_arg="${fields[3]}"
        field_index=4
        if [[ "$scheduled_time" == "$CURRENT_TIME" ]]; then
          due_entry=1
        fi
      fi
      ;;
    weekly)
      if [[ ${#fields[@]} -lt 5 ]]; then
        valid_entry=0
      else
        if scheduled_weekday="$(normalize_weekday "${fields[1]}")"; then
          scheduled_time="${fields[2]}"
          job_type="${fields[3]}"
          job_arg="${fields[4]}"
          field_index=5
          if [[ "$scheduled_weekday" == "$CURRENT_WEEKDAY" && "$scheduled_time" == "$CURRENT_TIME" ]]; then
            due_entry=1
          fi
        else
          valid_entry=0
        fi
      fi
      ;;
    monthly)
      if [[ ${#fields[@]} -lt 5 ]] || ! is_valid_month_day "${fields[1]}"; then
        valid_entry=0
      else
        scheduled_month_day="$(canonical_month_day "${fields[1]}")"
        scheduled_time="${fields[2]}"
        job_type="${fields[3]}"
        job_arg="${fields[4]}"
        field_index=5
        if [[ "$scheduled_month_day" == "$CURRENT_MONTH_DAY" && "$scheduled_time" == "$CURRENT_TIME" ]]; then
          due_entry=1
        fi
      fi
      ;;
    *)
      valid_entry=0
      ;;
  esac

  if [[ $valid_entry -eq 1 && ( ! "$scheduled_time" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ || -z "$job_type" || -z "$job_arg" ) ]]; then
    valid_entry=0
  fi

  while [[ $valid_entry -eq 1 && $field_index -lt ${#fields[@]} ]]; do
    if [[ "${fields[$field_index]}" != "--delivery" || $((field_index + 1)) -ge ${#fields[@]} ]]; then
      valid_entry=0
      break
    fi

    delivery_target="${fields[$((field_index + 1))]}"
    case "$delivery_target" in
      logseq|email)
        delivery_args+=("--delivery" "$delivery_target")
        ;;
      *)
        valid_entry=0
        ;;
    esac
    field_index=$((field_index + 2))
  done

  if [[ $valid_entry -ne 1 ]]; then
    echo "Invalid schedule entry: $line" >&2
    STATUS=1
    continue
  fi

  if [[ "$due_entry" -ne 1 ]]; then
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

  case "$cadence" in
    daily)
      state_key="$(printf '%s-%s-%s' "$job_type" "$job_arg" "${delivery_args[*]:-local}" | tr -cs 'A-Za-z0-9._-' '_')"
      ;;
    weekly)
      state_key="$(printf '%s-%s-%s-%s-%s' "$cadence" "$scheduled_weekday" "$job_type" "$job_arg" "${delivery_args[*]:-local}" | tr -cs 'A-Za-z0-9._-' '_')"
      ;;
    monthly)
      state_key="$(printf '%s-%s-%s-%s-%s' "$cadence" "$scheduled_month_day" "$job_type" "$job_arg" "${delivery_args[*]:-local}" | tr -cs 'A-Za-z0-9._-' '_')"
      ;;
  esac
  state_file="$STATE_DIR/$state_key.stamp"

  if [[ -f "$state_file" ]] && [[ "$(cat "$state_file")" == "$CURRENT_STAMP" ]]; then
    continue
  fi

  printf '%s\n' "$CURRENT_STAMP" >"$state_file"
  echo "Running scheduled track '$job_arg' for $CURRENT_STAMP"
  if /bin/bash "$ROOT/scripts/run_track.sh" --track "$job_arg" "${delivery_args[@]}"; then
    :
  else
    cmd_status=$?
    echo "Scheduled track '$job_arg' failed with status $cmd_status" >&2
    STATUS=$cmd_status
  fi
done <"$SCHEDULE_FILE"

exit "$STATUS"
