#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="${JOB_AGENT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
ENV_FILE="${JOB_AGENT_ENV_FILE:-$ROOT/.env.local}"
SCHEDULE_FILE="${JOB_AGENT_SCHEDULE_FILE:-$ROOT/.schedule.local}"
SCHEDULER_DIR="${JOB_AGENT_SCHEDULER_DIR:-$ROOT/.scheduler}"
# shellcheck source=./load_runtime_env.sh
source "$SCRIPT_DIR/load_runtime_env.sh"
job_agent_load_runtime_env

ROOT="${JOB_AGENT_ROOT:-$ROOT}"
ENV_FILE="${JOB_AGENT_ENV_FILE:-$ROOT/.env.local}"
SCHEDULE_FILE="${JOB_AGENT_SCHEDULE_FILE:-$ROOT/.schedule.local}"
SCHEDULER_DIR="${JOB_AGENT_SCHEDULER_DIR:-$ROOT/.scheduler}"
STATE_DIR="${JOB_AGENT_SCHEDULER_STATE_DIR:-$SCHEDULER_DIR/state}"
LOCK_DIR="$SCHEDULER_DIR/run.lock"
CURRENT_TIME="${JOB_AGENT_SCHEDULE_TIME:-$(date +%H:%M)}"
CURRENT_STAMP="${JOB_AGENT_SCHEDULE_STAMP:-$(date +%F-%H:%M)}"
CURRENT_DATE="${JOB_AGENT_SCHEDULE_DATE:-${CURRENT_STAMP:0:10}}"
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

# Succeeds when HH:MM "$1" (now) is at or after HH:MM "$2" (scheduled).
# Returns non-zero on malformed input so a bad time never marks an entry due.
time_at_or_after() {
  local now="$1" target="$2"
  [[ "$now" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]] || return 1
  [[ "$target" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]] || return 1
  local now_min=$((10#${now%%:*} * 60 + 10#${now#*:}))
  local target_min=$((10#${target%%:*} * 60 + 10#${target#*:}))
  [[ "$now_min" -ge "$target_min" ]]
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

# CURRENT_DATE is the per-day dedup key; validate it like the other current
# values so a malformed stamp/date override fails loudly instead of silently
# corrupting dedup.
if [[ ! "$CURRENT_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "Invalid current date: $CURRENT_DATE" >&2
  exit 2
fi

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
        if time_at_or_after "$CURRENT_TIME" "$scheduled_time"; then
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
          if [[ "$scheduled_weekday" == "$CURRENT_WEEKDAY" ]] && time_at_or_after "$CURRENT_TIME" "$scheduled_time"; then
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
        if [[ "$scheduled_month_day" == "$CURRENT_MONTH_DAY" ]] && time_at_or_after "$CURRENT_TIME" "$scheduled_time"; then
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
      logseq|email|telegram)
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

  # Dedup per day, not per minute: with the catch-up window an entry is due on
  # every tick from its scheduled time onward, so it must run at most once per
  # scheduled day. The stamp file is keyed by state_key (cadence/day-spec/track/
  # delivery), not by scheduled time, so two entries for the same track+delivery
  # on one day would share a stamp and run once; configure_schedule.py keeps a
  # single entry per track, so that case does not arise via supported tooling.
  # Older state files stored the full YYYY-MM-DD-HH:MM stamp; the date-prefix
  # match keeps them recognized as "already ran today". A failed read must not
  # abort the loop (it would silently skip every later entry), so treat an
  # unreadable stamp as not-yet-run and let the job run.
  if [[ -f "$state_file" ]]; then
    if ! last_stamp="$(cat "$state_file" 2>/dev/null)"; then
      last_stamp=""
    fi
    if [[ "$last_stamp" == "$CURRENT_DATE" || "$last_stamp" == "$CURRENT_DATE"-* ]]; then
      continue
    fi
  fi

  printf '%s\n' "$CURRENT_DATE" >"$state_file"
  echo "Running scheduled track '$job_arg' for $CURRENT_STAMP"
  if /bin/bash "$ROOT/scripts/run_track.sh" --track "$job_arg" ${delivery_args[@]+"${delivery_args[@]}"}; then
    :
  else
    cmd_status=$?
    echo "Scheduled track '$job_arg' failed with status $cmd_status" >&2
    STATUS=$cmd_status
  fi
done <"$SCHEDULE_FILE"

exit "$STATUS"
