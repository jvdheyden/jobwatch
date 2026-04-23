#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT="${JOB_AGENT_ROOT:-$REPO_ROOT}"
ENV_FILE="${JOB_AGENT_ENV_FILE:-$ROOT/.env.local}"
SCHEDULE_FILE="${JOB_AGENT_SCHEDULE_FILE:-$ROOT/.schedule.local}"
SCHEDULER_DIR="${JOB_AGENT_SCHEDULER_DIR:-$ROOT/.scheduler}"
PROFILE_DIR="${JOB_AGENT_PROFILE_DIR:-$ROOT/profile}"
PROFILE_TEMPLATE_DIR="$REPO_ROOT/.agents/skills/set-up/templates/profile"
PROFILE_CV_TEMPLATE="$PROFILE_TEMPLATE_DIR/cv.md"
PROFILE_PREFS_TEMPLATE="$PROFILE_TEMPLATE_DIR/prefs_global.md"
PROFILE_CV_FILE="$PROFILE_DIR/cv.md"
PROFILE_PREFS_FILE="$PROFILE_DIR/prefs_global.md"
CRON_FILE="$SCHEDULER_DIR/cron.entry"
APPARMOR_PROFILE_FILE="$SCHEDULER_DIR/bwrap-userns-restrict"
PLATFORM="${JOB_AGENT_PLATFORM:-$(uname -s)}"
LOGSEQ_GRAPH_DIR_VALUE=""
AGENT_PROVIDER_VALUE=""
AGENT_BIN_VALUE=""
ENV_AGENT_PROVIDER_VALUE="${JOB_AGENT_PROVIDER:-}"
ENV_AGENT_BIN_VALUE="${JOB_AGENT_BIN:-}"
ENV_LOGSEQ_GRAPH_DIR_VALUE="${LOGSEQ_GRAPH_DIR:-}"
EMAIL_PROVIDER_VALUE=""
EMAIL_ACCOUNT_VALUE=""
SMTP_HOST_VALUE=""
SMTP_PORT_VALUE=""
SMTP_FROM_VALUE=""
SMTP_TO_VALUE=""
SMTP_USERNAME_VALUE=""
SMTP_PASSWORD_CMD_VALUE=""
SMTP_TLS_VALUE=""
SECRETS_FILE_VALUE=""
SUGGESTED_SECRETS_FILE_VALUE=""
ENV_SMTP_HOST_VALUE="${JOB_AGENT_SMTP_HOST:-}"
ENV_SMTP_PORT_VALUE="${JOB_AGENT_SMTP_PORT:-}"
ENV_SMTP_FROM_VALUE="${JOB_AGENT_SMTP_FROM:-}"
ENV_SMTP_TO_VALUE="${JOB_AGENT_SMTP_TO:-}"
ENV_SMTP_USERNAME_VALUE="${JOB_AGENT_SMTP_USERNAME:-}"
ENV_SMTP_PASSWORD_VALUE="${JOB_AGENT_SMTP_PASSWORD:-}"
ENV_SMTP_PASSWORD_CMD_VALUE="${JOB_AGENT_SMTP_PASSWORD_CMD:-}"
ENV_SMTP_TLS_VALUE="${JOB_AGENT_SMTP_TLS:-}"
ENV_SECRETS_FILE_VALUE="${JOB_AGENT_SECRETS_FILE:-}"
ENV_EMAIL_PROVIDER_VALUE="${JOB_AGENT_EMAIL_PROVIDER:-}"
ENV_EMAIL_ACCOUNT_VALUE="${JOB_AGENT_EMAIL_ACCOUNT:-}"

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
Usage: $0 --agent codex|claude [--agent-bin <path>] [--logseq-graph-dir <path>]

Create or refresh machine-local scheduler config and profile placeholders for this checkout.
In a terminal, the script prompts for any missing required values.
In non-interactive mode, JOB_AGENT_BIN must be supplied or the selected provider binary must be discoverable.
This script does not install cron or launchd. After adding entries to
$SCHEDULE_FILE with scripts/configure_schedule.py or the setup agent, run
scripts/install_scheduler.sh.
EOF
}

agent_guidance() {
  local script_name
  local detected=""
  script_name="$(basename "$0")"
  if command -v claude >/dev/null 2>&1 && ! command -v codex >/dev/null 2>&1; then
    detected="claude"
  elif command -v codex >/dev/null 2>&1 && ! command -v claude >/dev/null 2>&1; then
    detected="codex"
  fi
  cat >&2 <<EOF
Choose an automation agent:
  bash scripts/$script_name --agent claude
  bash scripts/$script_name --agent codex
EOF
  if [[ -n "$detected" ]]; then
    echo "Detected '$detected' on PATH; likely command: bash scripts/$script_name --agent $detected" >&2
  fi
}

shell_escape() {
  printf '%q' "$1"
}

is_interactive() {
  [[ -t 0 && -t 1 ]]
}

suggested_secrets_file_path() {
  case "$PLATFORM" in
    Linux)
      if [[ -n "${XDG_CONFIG_HOME:-}" ]]; then
        printf '%s/jobwatch/secrets.sh\n' "$XDG_CONFIG_HOME"
        return 0
      fi
      if [[ -n "${HOME:-}" ]]; then
        printf '%s/.config/jobwatch/secrets.sh\n' "$HOME"
        return 0
      fi
      ;;
    Darwin)
      if [[ -n "${HOME:-}" ]]; then
        printf '%s/Library/Application Support/jobwatch/secrets.sh\n' "$HOME"
        return 0
      fi
      ;;
  esac
  return 1
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

validate_agent_provider() {
  case "${1:-}" in
    codex|claude)
      return 0
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

detect_agent_bin() {
  local provider="$1"
  local default_bin=""
  local detected=""

  default_bin="$(agent_default_binary_name "$provider")"
  if ! detected="$(resolve_command_path "$default_bin" 2>/dev/null)"; then
    return 1
  fi

  if [[ "$provider" == "codex" ]]; then
    canonicalize_linux_executable_path "$detected"
  else
    printf '%s\n' "$detected"
  fi
}

detect_bwrap_bin() {
  local detected=""

  if [[ "$PLATFORM" != "Linux" ]]; then
    return 1
  fi

  if ! detected="$(resolve_command_path bwrap 2>/dev/null)"; then
    return 1
  fi

  canonicalize_linux_executable_path "$detected"
}

write_bwrap_apparmor_profile() {
  local bwrap_bin="$1"

  cat >"$APPARMOR_PROFILE_FILE" <<EOF
# Generated by scripts/setup_machine.sh.
# Install this profile on Linux hosts that restrict unprivileged user
# namespaces via AppArmor before running Codex sandboxing through bwrap.
abi <abi/4.0>,

include <tunables/global>

$bwrap_bin flags=(unconfined) {
  userns create,

  # Site-specific additions and overrides.
  include if exists <local/bwrap-userns-restrict>
}
EOF
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

prompt_for_agent_bin() {
  local provider="${1:-codex}"
  local default_value="${2:-}"
  local entered=""
  local candidate=""
  local resolved=""
  local default_binary=""

  default_binary="$(agent_default_binary_name "$provider")"

  while true; do
    if [[ -n "$default_value" ]]; then
      entered="$(prompt_line "JOB_AGENT_BIN for $provider [$default_value]: ")"
      candidate="${entered:-$default_value}"
    else
      entered="$(prompt_line "JOB_AGENT_BIN for $provider (required): ")"
      candidate="$entered"
    fi

    if resolve_command_path "$candidate" >/dev/null 2>&1; then
      resolved="$(resolve_command_path "$candidate")"
      printf '%s\n' "$resolved"
      return 0
    fi

    echo "JOB_AGENT_BIN must point to an executable $default_binary binary." >&2
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
    --agent)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --agent" >&2
        usage >&2
        exit 2
      fi
      AGENT_PROVIDER_VALUE="$2"
      shift 2
      ;;
    --agent-bin)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --agent-bin" >&2
        usage >&2
        exit 2
      fi
      AGENT_BIN_VALUE="$2"
      shift 2
      ;;
    --logseq-graph-dir)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --logseq-graph-dir" >&2
        usage >&2
        exit 2
      fi
      LOGSEQ_GRAPH_DIR_VALUE="$2"
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
existing_agent_provider=""
existing_agent_bin=""
existing_logseq_graph_dir=""
existing_email_provider=""
existing_email_account=""
existing_smtp_host=""
existing_smtp_port=""
existing_smtp_from=""
existing_smtp_to=""
existing_smtp_username=""
existing_smtp_password=""
existing_smtp_password_cmd=""
existing_smtp_tls=""
existing_secrets_file=""
detected_agent_bin=""
detected_logseq_graph_dir=""
detected_bwrap_bin=""

if [[ -f "$ENV_FILE" ]]; then
  set +u
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set -u
  existing_path="${PATH:-$ORIGINAL_PATH}"
  existing_agent_provider="${JOB_AGENT_PROVIDER:-}"
  existing_agent_bin="${JOB_AGENT_BIN:-}"
  existing_logseq_graph_dir="${LOGSEQ_GRAPH_DIR:-}"
  existing_email_provider="${JOB_AGENT_EMAIL_PROVIDER:-}"
  existing_email_account="${JOB_AGENT_EMAIL_ACCOUNT:-}"
  existing_smtp_host="${JOB_AGENT_SMTP_HOST:-}"
  existing_smtp_port="${JOB_AGENT_SMTP_PORT:-}"
  existing_smtp_from="${JOB_AGENT_SMTP_FROM:-}"
  existing_smtp_to="${JOB_AGENT_SMTP_TO:-}"
  existing_smtp_username="${JOB_AGENT_SMTP_USERNAME:-}"
  existing_smtp_password="${JOB_AGENT_SMTP_PASSWORD:-}"
  existing_smtp_password_cmd="${JOB_AGENT_SMTP_PASSWORD_CMD:-}"
  existing_smtp_tls="${JOB_AGENT_SMTP_TLS:-}"
  existing_secrets_file="${JOB_AGENT_SECRETS_FILE:-}"
  PATH="$ORIGINAL_PATH"
fi

if [[ -z "$AGENT_PROVIDER_VALUE" ]]; then
  AGENT_PROVIDER_VALUE="$ENV_AGENT_PROVIDER_VALUE"
fi
if [[ -z "$AGENT_PROVIDER_VALUE" ]]; then
  AGENT_PROVIDER_VALUE="$existing_agent_provider"
fi
if [[ -z "$AGENT_PROVIDER_VALUE" ]]; then
  agent_guidance
  exit 2
fi
if ! validate_agent_provider "$AGENT_PROVIDER_VALUE"; then
  echo "Invalid --agent/JOB_AGENT_PROVIDER '$AGENT_PROVIDER_VALUE'; expected codex or claude." >&2
  agent_guidance
  exit 2
fi
if [[ -z "$AGENT_BIN_VALUE" ]]; then
  AGENT_BIN_VALUE="$ENV_AGENT_BIN_VALUE"
fi
if [[ -z "$AGENT_BIN_VALUE" ]]; then
  AGENT_BIN_VALUE="$existing_agent_bin"
fi
if detected_agent_bin="$(detect_agent_bin "$AGENT_PROVIDER_VALUE" 2>/dev/null)"; then
  :
else
  detected_agent_bin=""
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
if [[ "$AGENT_PROVIDER_VALUE" == "codex" ]] && detected_bwrap_bin="$(detect_bwrap_bin 2>/dev/null)"; then
  :
else
  detected_bwrap_bin=""
fi

EMAIL_PROVIDER_VALUE="${ENV_EMAIL_PROVIDER_VALUE:-$existing_email_provider}"
EMAIL_ACCOUNT_VALUE="${ENV_EMAIL_ACCOUNT_VALUE:-$existing_email_account}"
SMTP_HOST_VALUE="${ENV_SMTP_HOST_VALUE:-$existing_smtp_host}"
SMTP_PORT_VALUE="${ENV_SMTP_PORT_VALUE:-$existing_smtp_port}"
SMTP_FROM_VALUE="${ENV_SMTP_FROM_VALUE:-$existing_smtp_from}"
SMTP_TO_VALUE="${ENV_SMTP_TO_VALUE:-$existing_smtp_to}"
SMTP_USERNAME_VALUE="${ENV_SMTP_USERNAME_VALUE:-$existing_smtp_username}"
SMTP_PASSWORD_CMD_VALUE="${ENV_SMTP_PASSWORD_CMD_VALUE:-$existing_smtp_password_cmd}"
SMTP_TLS_VALUE="${ENV_SMTP_TLS_VALUE:-$existing_smtp_tls}"
SECRETS_FILE_VALUE="${ENV_SECRETS_FILE_VALUE:-$existing_secrets_file}"
if [[ -z "$SECRETS_FILE_VALUE" ]]; then
  if SUGGESTED_SECRETS_FILE_VALUE="$(suggested_secrets_file_path 2>/dev/null)"; then
    :
  else
    SUGGESTED_SECRETS_FILE_VALUE=""
  fi
fi
legacy_smtp_password_detected=0
if [[ -n "$ENV_SMTP_PASSWORD_VALUE" || -n "$existing_smtp_password" ]]; then
  legacy_smtp_password_detected=1
fi

if [[ -z "$AGENT_BIN_VALUE" ]]; then
  if is_interactive; then
    AGENT_BIN_VALUE="$(prompt_for_agent_bin "$AGENT_PROVIDER_VALUE" "$detected_agent_bin")"
  elif [[ -n "$detected_agent_bin" ]]; then
    AGENT_BIN_VALUE="$detected_agent_bin"
  else
    echo "JOB_AGENT_BIN is required in non-interactive mode; pass --agent-bin or add $(agent_default_binary_name "$AGENT_PROVIDER_VALUE") to PATH." >&2
    exit 1
  fi
fi

if resolve_command_path "$AGENT_BIN_VALUE" >/dev/null 2>&1; then
  AGENT_BIN_VALUE="$(resolve_command_path "$AGENT_BIN_VALUE")"
  if [[ "$AGENT_PROVIDER_VALUE" == "codex" ]]; then
    AGENT_BIN_VALUE="$(canonicalize_linux_executable_path "$AGENT_BIN_VALUE")"
  fi
elif is_interactive; then
  AGENT_BIN_VALUE="$(prompt_for_agent_bin "$AGENT_PROVIDER_VALUE" "$detected_agent_bin")"
else
  echo "JOB_AGENT_BIN '$AGENT_BIN_VALUE' is not executable or not found on PATH." >&2
  exit 1
fi

if [[ -z "$LOGSEQ_GRAPH_DIR_VALUE" && is_interactive ]]; then
  LOGSEQ_GRAPH_DIR_VALUE="$(prompt_for_logseq_graph_dir "$detected_logseq_graph_dir")"
fi

mkdir -p "$SCHEDULER_DIR/state" "$ROOT/logs" "$PROFILE_DIR"

profile_cv_status="preserved"
profile_prefs_status="preserved"

if [[ ! -f "$PROFILE_CV_FILE" ]]; then
  cp "$PROFILE_CV_TEMPLATE" "$PROFILE_CV_FILE"
  profile_cv_status="created"
fi

if [[ ! -f "$PROFILE_PREFS_FILE" ]]; then
  cp "$PROFILE_PREFS_TEMPLATE" "$PROFILE_PREFS_FILE"
  profile_prefs_status="created"
fi

{
  echo "# Machine-local configuration for this checkout."
  echo "# Generated by scripts/setup_machine.sh."
  printf 'export JOB_AGENT_ROOT=%s\n' "$(shell_escape "$ROOT")"
  printf 'export PATH=%s\n' "$(shell_escape "$existing_path")"
  echo "# Required: automation provider and executable agent binary for scheduled runs."
  printf 'export JOB_AGENT_PROVIDER=%s\n' "$(shell_escape "$AGENT_PROVIDER_VALUE")"
  printf 'export JOB_AGENT_BIN=%s\n' "$(shell_escape "$AGENT_BIN_VALUE")"
  echo "# Optional: Logseq graph root for digest publication."
  if [[ -n "$LOGSEQ_GRAPH_DIR_VALUE" ]]; then
    printf 'export LOGSEQ_GRAPH_DIR=%s\n' "$(shell_escape "$LOGSEQ_GRAPH_DIR_VALUE")"
  else
    echo "# export LOGSEQ_GRAPH_DIR=/absolute/path/to/logseq"
  fi
  echo "# Optional: SMTP settings for email delivery."
  echo "# Keep non-secret SMTP config here. Put the real app password or SMTP token outside the repo."
  echo "# Put JOB_AGENT_SMTP_PASSWORD_CMD in this file to fetch that secret from Keychain, secret-tool, or pass."
  echo "# Or put export JOB_AGENT_SMTP_PASSWORD=... only in the external file named by JOB_AGENT_SECRETS_FILE."
  echo "# Optional: shorthand for common SMTP-backed providers. Raw JOB_AGENT_SMTP_* settings override these defaults."
  echo "# Provider presets currently cover Gmail, Fastmail, Outlook.com/Hotmail, and Proton business SMTP."
  echo "# Gmail: turn on Google 2-Step Verification and create an app password."
  echo "# Fastmail: create an app password for a mail client."
  echo "# Outlook.com/Hotmail: use this only if your account has a working app password or SMTP credential."
  echo "# JOB_AGENT_EMAIL_PROVIDER=proton assumes Proton business SMTP with an SMTP token and a custom-domain address."
  echo "# Proton Mail Bridge is still out of scope here; keep Bridge-based local SMTP settings explicit via JOB_AGENT_SMTP_* if you ever use it manually."
  if [[ -n "$EMAIL_PROVIDER_VALUE" ]]; then
    printf 'export JOB_AGENT_EMAIL_PROVIDER=%s\n' "$(shell_escape "$EMAIL_PROVIDER_VALUE")"
  else
    echo "# export JOB_AGENT_EMAIL_PROVIDER=gmail"
  fi
  if [[ -n "$EMAIL_ACCOUNT_VALUE" ]]; then
    printf 'export JOB_AGENT_EMAIL_ACCOUNT=%s\n' "$(shell_escape "$EMAIL_ACCOUNT_VALUE")"
  else
    echo "# export JOB_AGENT_EMAIL_ACCOUNT=jobs@example.com"
  fi
  if [[ -n "$SECRETS_FILE_VALUE" ]]; then
    printf 'export JOB_AGENT_SECRETS_FILE=%s\n' "$(shell_escape "$SECRETS_FILE_VALUE")"
  elif [[ -n "$SUGGESTED_SECRETS_FILE_VALUE" ]]; then
    printf '# export JOB_AGENT_SECRETS_FILE=%s\n' "$(shell_escape "$SUGGESTED_SECRETS_FILE_VALUE")"
  else
    echo "# export JOB_AGENT_SECRETS_FILE=/absolute/path/outside/repo/jobwatch.secrets.sh"
  fi
  if [[ -n "$SMTP_HOST_VALUE" ]]; then
    printf 'export JOB_AGENT_SMTP_HOST=%s\n' "$(shell_escape "$SMTP_HOST_VALUE")"
  else
    echo "# export JOB_AGENT_SMTP_HOST=smtp.example.com"
  fi
  if [[ -n "$SMTP_PORT_VALUE" ]]; then
    printf 'export JOB_AGENT_SMTP_PORT=%s\n' "$(shell_escape "$SMTP_PORT_VALUE")"
  else
    echo "# export JOB_AGENT_SMTP_PORT=587"
  fi
  if [[ -n "$SMTP_FROM_VALUE" ]]; then
    printf 'export JOB_AGENT_SMTP_FROM=%s\n' "$(shell_escape "$SMTP_FROM_VALUE")"
  else
    echo "# export JOB_AGENT_SMTP_FROM=jobs@example.com"
  fi
  if [[ -n "$SMTP_TO_VALUE" ]]; then
    printf 'export JOB_AGENT_SMTP_TO=%s\n' "$(shell_escape "$SMTP_TO_VALUE")"
  else
    echo "# export JOB_AGENT_SMTP_TO=you@example.com"
  fi
  if [[ -n "$SMTP_USERNAME_VALUE" ]]; then
    printf 'export JOB_AGENT_SMTP_USERNAME=%s\n' "$(shell_escape "$SMTP_USERNAME_VALUE")"
  else
    echo "# export JOB_AGENT_SMTP_USERNAME=jobs@example.com"
  fi
  echo "# Preferred: retrieve the SMTP password only when a real email is sent."
  echo "# Keep the command here in .env.local; keep the actual app password or SMTP token in the password store it reads."
  echo "# Examples:"
  echo "# export JOB_AGENT_SMTP_PASSWORD_CMD='security find-generic-password -s jobwatch-smtp -a jobs@example.com -w'"
  echo "# export JOB_AGENT_SMTP_PASSWORD_CMD='secret-tool lookup service jobwatch-smtp account jobs@example.com'"
  echo "# export JOB_AGENT_SMTP_PASSWORD_CMD='pass show email/jobwatch-smtp'"
  if [[ -n "$SMTP_PASSWORD_CMD_VALUE" ]]; then
    printf 'export JOB_AGENT_SMTP_PASSWORD_CMD=%s\n' "$(shell_escape "$SMTP_PASSWORD_CMD_VALUE")"
  else
    echo "# export JOB_AGENT_SMTP_PASSWORD_CMD='pass show email/jobwatch-smtp'"
  fi
  echo "# Plaintext repo-local JOB_AGENT_SMTP_PASSWORD is no longer supported."
  if [[ -n "$SECRETS_FILE_VALUE" ]]; then
    printf '# If you prefer a static password, write export JOB_AGENT_SMTP_PASSWORD=... in %s.\n' "$(shell_escape "$SECRETS_FILE_VALUE")"
  elif [[ -n "$SUGGESTED_SECRETS_FILE_VALUE" ]]; then
    printf '# If you prefer a static password, write export JOB_AGENT_SMTP_PASSWORD=... in %s and uncomment JOB_AGENT_SECRETS_FILE above.\n' "$(shell_escape "$SUGGESTED_SECRETS_FILE_VALUE")"
  else
    echo "# If you prefer a static password over JOB_AGENT_SMTP_PASSWORD_CMD, put it only in the external file named by JOB_AGENT_SECRETS_FILE."
  fi
  echo "# export JOB_AGENT_SMTP_PASSWORD=app-password"
  if [[ -n "$SMTP_TLS_VALUE" ]]; then
    printf 'export JOB_AGENT_SMTP_TLS=%s\n' "$(shell_escape "$SMTP_TLS_VALUE")"
  else
    echo "# export JOB_AGENT_SMTP_TLS=starttls"
  fi
} >"$ENV_FILE"

if [[ -n "$detected_bwrap_bin" ]]; then
  write_bwrap_apparmor_profile "$detected_bwrap_bin"
else
  rm -f "$APPARMOR_PROFILE_FILE"
fi

if [[ ! -f "$SCHEDULE_FILE" ]]; then
  cat >"$SCHEDULE_FILE" <<EOF
# Machine-local scheduler entries.
# Prefer scripts/configure_schedule.py or the setup agent over hand-editing.
# Formats:
# daily HH:MM track <track-slug> [--delivery logseq|email]...
# weekly mon HH:MM track <track-slug> [--delivery logseq|email]...
# monthly 1 HH:MM track <track-slug> [--delivery logseq|email]...
# Example:
# daily 08:00 track core_crypto
# weekly mon 08:00 track core_crypto --delivery logseq --delivery email
EOF
fi

runner_path="$ROOT/scripts/run_scheduled_jobs.sh"
stdout_log="$ROOT/logs/scheduler.out"
stderr_log="$ROOT/logs/scheduler.err"

{
  echo "$CRON_BEGIN"
  printf '* * * * * /bin/bash %s >>%s 2>>%s\n' \
    "$(shell_escape "$runner_path")" \
    "$(shell_escape "$stdout_log")" \
    "$(shell_escape "$stderr_log")"
  echo "$CRON_END"
} >"$CRON_FILE"

cat >"$PLIST_FILE" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <!-- Generated by scripts/setup_machine.sh. -->
  <dict>
    <key>Label</key>
    <string>$SCHEDULER_LABEL</string>

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
if [[ "$legacy_smtp_password_detected" -eq 1 ]]; then
  echo "Removed legacy JOB_AGENT_SMTP_PASSWORD from $ENV_FILE. Move it into JOB_AGENT_SECRETS_FILE or use JOB_AGENT_SMTP_PASSWORD_CMD."
fi
echo "Keep non-secret SMTP config in $ENV_FILE. Put real secrets in JOB_AGENT_SECRETS_FILE outside the repo."

if [[ "$AGENT_PROVIDER_VALUE" == "codex" ]]; then
  CODEX_CONFIG_PYTHON="${JOB_AGENT_PYTHON:-python3}"
  if codex_config_status="$("$CODEX_CONFIG_PYTHON" "$SCRIPT_DIR/hooks/install_codex_project_config.py" --root "$ROOT" --base-path "$existing_path")"; then
    echo "Codex project config: $codex_config_status ($ROOT/.codex/config.toml)"
  else
    echo "Codex project config install failed" >&2
  fi
fi

if [[ "$AGENT_PROVIDER_VALUE" == "claude" ]]; then
  CLAUDE_HOOK_PYTHON="${JOB_AGENT_PYTHON:-python3}"
  if claude_hook_status="$("$CLAUDE_HOOK_PYTHON" "$SCRIPT_DIR/hooks/install_claude_session_hook.py" --root "$ROOT" 2>&1)"; then
    echo "Claude SessionStart hook: $claude_hook_status ($ROOT/.claude/settings.local.json)"
  else
    echo "Claude SessionStart hook install failed: $claude_hook_status" >&2
  fi
  if claude_gate_status="$("$CLAUDE_HOOK_PYTHON" "$SCRIPT_DIR/hooks/install_claude_coding_gate_hook.py" --root "$ROOT" 2>&1)"; then
    echo "Claude coding-gate hook: $claude_gate_status ($ROOT/.claude/settings.local.json)"
  else
    echo "Claude coding-gate hook install failed: $claude_gate_status" >&2
  fi
fi

echo "Prepared local profile directory at $PROFILE_DIR"
echo "$profile_cv_status $PROFILE_CV_FILE"
echo "$profile_prefs_status $PROFILE_PREFS_FILE"
echo "Fill profile/cv.md and profile/prefs_global.md locally; optionally place a PDF CV in profile/ for setup assistance."
echo "Prepared $SCHEDULE_FILE"
echo "Generated $CRON_FILE"
echo "Generated $PLIST_FILE"
if [[ -f "$APPARMOR_PROFILE_FILE" ]]; then
  echo "Generated $APPARMOR_PROFILE_FILE for $detected_bwrap_bin"
  echo "Run sudo bash scripts/install_bwrap_apparmor.sh if this Linux host enforces AppArmor userns restrictions."
fi
echo "Use scripts/configure_schedule.py or the setup agent to add track entries, then run scripts/install_scheduler.sh."
