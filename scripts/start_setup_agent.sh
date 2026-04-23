#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT="${JOB_AGENT_ROOT:-$REPO_ROOT}"
ENV_FILE="${JOB_AGENT_ENV_FILE:-$ROOT/.env.local}"
AGENT_VALUE=""
AGENT_BIN_VALUE=""

usage() {
  cat <<EOF
Usage: $0 [--agent codex|claude] [--agent-bin <path>]

Launch the guided jobwatch setup agent from the repo root.
If omitted, --agent and --agent-bin are read from .env.local or the environment.
EOF
}

validate_agent() {
  case "${1:-}" in
    codex|claude)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
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

default_binary_name() {
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

while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --agent" >&2
        usage >&2
        exit 2
      fi
      AGENT_VALUE="$2"
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
# shellcheck source=./load_runtime_env.sh
source "$SCRIPT_DIR/load_runtime_env.sh"
job_agent_load_runtime_env

PATH="${PATH:-$ORIGINAL_PATH}"
ROOT="${JOB_AGENT_ROOT:-$ROOT}"
ENV_FILE="${JOB_AGENT_ENV_FILE:-$ENV_FILE}"

if [[ -z "$AGENT_VALUE" ]]; then
  AGENT_VALUE="${JOB_AGENT_PROVIDER:-}"
fi
if [[ -z "$AGENT_BIN_VALUE" ]]; then
  AGENT_BIN_VALUE="${JOB_AGENT_BIN:-}"
fi

if ! validate_agent "$AGENT_VALUE"; then
  echo "Invalid or missing setup agent provider; expected --agent codex or --agent claude." >&2
  exit 2
fi

if [[ -z "$AGENT_BIN_VALUE" ]]; then
  AGENT_BIN_VALUE="$(default_binary_name "$AGENT_VALUE")"
fi
if ! AGENT_BIN_VALUE="$(resolve_command_path "$AGENT_BIN_VALUE")"; then
  echo "Could not find executable for $AGENT_VALUE; pass --agent-bin or rerun scripts/setup_machine.sh." >&2
  exit 1
fi

# Never pass plaintext SMTP secrets into agent processes. Password commands are
# local retrieval recipes and may remain visible for setup guidance.
unset JOB_AGENT_SMTP_PASSWORD

SETUP_PROMPT=$(cat <<'EOF'
Use the project skill $set-up for a guided first-track setup.

Contract:
- Treat setup as a single guided onboarding flow, not a sequence the user has to discover.
- Write local user data only under profile/ and tracks/. Never edit .agents/skills/set-up/templates/profile/*.
- First make profile/cv.md ready. If it is still the template, look for an existing Markdown CV or a PDF in profile/. If exactly one PDF exists and pdftotext is available, draft profile/cv.md from it and ask the user to review. If multiple PDFs exist, ask which one. If no PDF exists, ask whether the user wants to add one or fill profile/cv.md manually.
- Then make profile/prefs_global.md ready. Infer only safe facts from the CV, then ask short questions for work mode, geography, seniority, contract type, compensation or practical constraints, authorization, dealbreakers, strong signals, and borderline signals. Write the reviewed answers.
- Collect the minimum track brief before source discovery: user name, track display name and slug, broad search area, goals or role types, keep-only keywords, constraints or red flags, and geography or remote preferences.
- Ask for known companies, official career pages, job boards, sectors, labs, organizations, source cadences, track-wide terms, source-specific terms, and native filters.
- If the user wants help expanding sources, invoke $discover-sources after the minimum brief exists. Keep its user-facing summary concise: recommended sources, dropped sources, URL corrections, caveats, and decisions needed.
- After discovery, continue automatically: ask keep/drop/add, ask cadence changes, infer source-specific terms and native filters from profile and preferences, and auto-pick canaries where possible.
- Use scripts/probe_career_source.py for source probing when possible instead of guessing from WebFetch alone.
- Scaffold and validate the track, then run source-scoped discovery and scripts/eval_source_quality.py for canary-backed important sources. A source is ready only when final_status is pass.
- For sources that need code, tune config first. Then run scripts/source_integration.py for at most the top 2 sources, preferring reusable provider modules under scripts/discover/sources/ when a board family is shared. Queue the rest in source_state.json and validate with scripts/integrate_next_source.py --dry-run.
- End guided setup by running a first local digest with bash scripts/run_track.sh --track <track> and pasting a preview of tracks/<track>/digests/YYYY-MM-DD.md into the conversation before moving on to delivery or scheduling. If run_track.sh fails, treat it as a blocker rather than skipping the preview.
- Only after the digest JSON exists, dry-run email with scripts/send_digest_email.py --dry-run.
- Guide delivery and scheduling last. Do not install the scheduler or send real email unless the user explicitly confirms.
EOF
)

cd "$ROOT"

case "$AGENT_VALUE" in
  codex)
    exec "$AGENT_BIN_VALUE" \
      --search \
      -a never \
      -C "$ROOT" \
      -s workspace-write \
      "$SETUP_PROMPT"
      ;;
  claude)
    exec "$AGENT_BIN_VALUE" \
      --permission-mode acceptEdits \
      --allowedTools "Read,Write,Edit,MultiEdit,Bash,Glob,Grep,LS,WebSearch,WebFetch,TodoWrite" \
      "$SETUP_PROMPT"
      ;;
esac
