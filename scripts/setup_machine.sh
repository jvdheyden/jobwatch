#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="${JOB_AGENT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
ENV_FILE="${JOB_AGENT_ENV_FILE:-$ROOT/.env.local}"
SCHEDULE_FILE="${JOB_AGENT_SCHEDULE_FILE:-$ROOT/.schedule.local}"
SCHEDULER_DIR="${JOB_AGENT_SCHEDULER_DIR:-$ROOT/.scheduler}"
PLIST_FILE="$SCHEDULER_DIR/com.jvdh.jobsearch.scheduler.plist"
CRON_FILE="$SCHEDULER_DIR/cron.entry"
PLATFORM="${JOB_AGENT_PLATFORM:-$(uname -s)}"
LOGSEQ_GRAPH_DIR_VALUE=""
CODEX_BIN_VALUE=""
ENV_CODEX_BIN_VALUE="${CODEX_BIN:-}"
ENV_LOGSEQ_GRAPH_DIR_VALUE="${LOGSEQ_GRAPH_DIR:-}"

usage() {
  cat <<EOF
Usage: $0 [--codex-bin <path>] [--logseq-graph-dir <path>]

Create or refresh machine-local scheduler config for this checkout.
In a terminal, the script prompts for any missing required values.
In non-interactive mode, CODEX_BIN must be supplied or discoverable.
This script does not install cron or launchd. After adding entries to
$SCHEDULE_FILE, run scripts/install_scheduler.sh.
EOF
}

shell_escape() {
  printf '%q' "$1"
}

is_interactive() {
  [[ -t 0 && -t 1 ]]
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

detect_codex_bin() {
  local detected=""

  if ! detected="$(resolve_command_path codex 2>/dev/null)"; then
    return 1
  fi

  canonicalize_linux_executable_path "$detected"
}

detect_logseq_graph_dir() {
  local home_dir="${HOME:-}"
  local candidate
  for candidate in \
    "$home_dir/Documents/logseq" \
    "$home_dir/Documents/Logseq"
  do
    if [[ -d "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

prompt_line() {
  local prompt="$1"
  local value
  printf '%s' "$prompt" >&2
  IFS= read -r value
  printf '%s\n' "$value"
}

prompt_for_codex_bin() {
  local default_value="${1:-}"
  local entered=""
  local candidate=""
  local resolved=""

  while true; do
    if [[ -n "$default_value" ]]; then
      entered="$(prompt_line "CODEX_BIN [$default_value]: ")"
      candidate="${entered:-$default_value}"
    else
      entered="$(prompt_line "CODEX_BIN (required): ")"
      candidate="$entered"
    fi

    if resolve_command_path "$candidate" >/dev/null 2>&1; then
      resolved="$(resolve_command_path "$candidate")"
      printf '%s\n' "$resolved"
      return 0
    fi

    echo "CODEX_BIN must point to an executable codex binary." >&2
  done
}

prompt_for_logseq_graph_dir() {
  local default_value="${1:-}"
  local entered=""

  if [[ -n "$default_value" ]]; then
    entered="$(prompt_line "LOGSEQ_GRAPH_DIR (optional, Enter to use $default_value, type skip to leave unset): ")"
    if [[ -z "$entered" ]]; then
      printf '%s\n' "$default_value"
      return 0
    fi
  else
    entered="$(prompt_line "LOGSEQ_GRAPH_DIR (optional, blank to skip): ")"
    if [[ -z "$entered" ]]; then
      printf '\n'
      return 0
    fi
  fi

  case "$entered" in
    skip|SKIP|none|NONE)
      printf '\n'
      ;;
    *)
      printf '%s\n' "$entered"
      ;;
  esac
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --codex-bin)
      CODEX_BIN_VALUE="${2:?missing value for --codex-bin}"
      shift 2
      ;;
    --logseq-graph-dir)
      LOGSEQ_GRAPH_DIR_VALUE="${2:?missing value for --logseq-graph-dir}"
      shift 2
      ;;
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

ORIGINAL_PATH="$PATH"
existing_path="$ORIGINAL_PATH"
existing_codex_bin=""
existing_logseq_graph_dir=""
detected_codex_bin=""
detected_logseq_graph_dir=""

if [[ -f "$ENV_FILE" ]]; then
  set +u
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set -u
  existing_path="${PATH:-$ORIGINAL_PATH}"
  existing_codex_bin="${CODEX_BIN:-}"
  existing_logseq_graph_dir="${LOGSEQ_GRAPH_DIR:-}"
  PATH="$ORIGINAL_PATH"
fi

if [[ -z "$CODEX_BIN_VALUE" ]]; then
  CODEX_BIN_VALUE="$ENV_CODEX_BIN_VALUE"
fi
if [[ -z "$CODEX_BIN_VALUE" ]]; then
  CODEX_BIN_VALUE="$existing_codex_bin"
fi
if detected_codex_bin="$(detect_codex_bin 2>/dev/null)"; then
  :
else
  detected_codex_bin=""
fi

if [[ -z "$LOGSEQ_GRAPH_DIR_VALUE" ]]; then
  LOGSEQ_GRAPH_DIR_VALUE="$ENV_LOGSEQ_GRAPH_DIR_VALUE"
fi
if [[ -z "$LOGSEQ_GRAPH_DIR_VALUE" ]]; then
  LOGSEQ_GRAPH_DIR_VALUE="$existing_logseq_graph_dir"
fi
if detected_logseq_graph_dir="$(detect_logseq_graph_dir 2>/dev/null)"; then
  :
else
  detected_logseq_graph_dir=""
fi

if [[ -z "$CODEX_BIN_VALUE" ]]; then
  if is_interactive; then
    CODEX_BIN_VALUE="$(prompt_for_codex_bin "$detected_codex_bin")"
  elif [[ -n "$detected_codex_bin" ]]; then
    CODEX_BIN_VALUE="$detected_codex_bin"
  else
    echo "CODEX_BIN is required in non-interactive mode; pass --codex-bin or add codex to PATH." >&2
    exit 1
  fi
fi

if resolve_command_path "$CODEX_BIN_VALUE" >/dev/null 2>&1; then
  CODEX_BIN_VALUE="$(resolve_command_path "$CODEX_BIN_VALUE")"
elif is_interactive; then
  CODEX_BIN_VALUE="$(prompt_for_codex_bin "$detected_codex_bin")"
else
  echo "CODEX_BIN '$CODEX_BIN_VALUE' is not executable or not found on PATH." >&2
  exit 1
fi

if [[ -z "$LOGSEQ_GRAPH_DIR_VALUE" && is_interactive ]]; then
  LOGSEQ_GRAPH_DIR_VALUE="$(prompt_for_logseq_graph_dir "$detected_logseq_graph_dir")"
fi

mkdir -p "$SCHEDULER_DIR/state" "$ROOT/logs"

{
  echo "# Machine-local configuration for this checkout."
  echo "# Generated by scripts/setup_machine.sh."
  printf 'export JOB_AGENT_ROOT=%s\n' "$(shell_escape "$ROOT")"
  printf 'export PATH=%s\n' "$(shell_escape "$existing_path")"
  echo "# Required: executable codex binary for scheduled runs."
  printf 'export CODEX_BIN=%s\n' "$(shell_escape "$CODEX_BIN_VALUE")"
  echo "# Optional: Logseq graph root for digest publication."
  if [[ -n "$LOGSEQ_GRAPH_DIR_VALUE" ]]; then
    printf 'export LOGSEQ_GRAPH_DIR=%s\n' "$(shell_escape "$LOGSEQ_GRAPH_DIR_VALUE")"
  else
    echo "# export LOGSEQ_GRAPH_DIR=/absolute/path/to/logseq"
  fi
} >"$ENV_FILE"

if [[ ! -f "$SCHEDULE_FILE" ]]; then
  cat >"$SCHEDULE_FILE" <<EOF
# Machine-local scheduler entries.
# Format: daily HH:MM track <track-slug>
# Example:
# daily 08:00 track core_crypto
EOF
fi

runner_path="$ROOT/scripts/run_scheduled_jobs.sh"
stdout_log="$ROOT/logs/scheduler.out"
stderr_log="$ROOT/logs/scheduler.err"

{
  echo "# BEGIN jobsearch scheduler"
  printf '* * * * * /bin/bash %s >>%s 2>>%s\n' \
    "$(shell_escape "$runner_path")" \
    "$(shell_escape "$stdout_log")" \
    "$(shell_escape "$stderr_log")"
  echo "# END jobsearch scheduler"
} >"$CRON_FILE"

cat >"$PLIST_FILE" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <!-- Generated by scripts/setup_machine.sh. -->
  <dict>
    <key>Label</key>
    <string>com.jvdh.jobsearch.scheduler</string>

    <key>ProgramArguments</key>
    <array>
      <string>/bin/bash</string>
      <string>$runner_path</string>
    </array>

    <key>EnvironmentVariables</key>
    <dict>
      <key>HOME</key>
      <string>${HOME:-$ROOT}</string>
      <key>PATH</key>
      <string>$existing_path</string>
    </dict>

    <key>WorkingDirectory</key>
    <string>$ROOT</string>

    <key>StartInterval</key>
    <integer>60</integer>

    <key>StandardOutPath</key>
    <string>$stdout_log</string>

    <key>StandardErrorPath</key>
    <string>$stderr_log</string>
  </dict>
</plist>
EOF

echo "Wrote $ENV_FILE"
echo "Prepared $SCHEDULE_FILE"
echo "Generated $CRON_FILE"
echo "Generated $PLIST_FILE"
echo "Add track entries to $SCHEDULE_FILE, then run scripts/install_scheduler.sh."
