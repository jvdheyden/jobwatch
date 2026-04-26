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
Usage: $0 [--agent codex|claude|gemini] [--agent-bin <path>]

Launch the guided jobwatch setup agent from the repo root.
If omitted, --agent and --agent-bin are read from .env.local or the environment.
EOF
}

validate_agent() {
  case "${1:-}" in
    codex|claude|gemini)
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
    gemini)
      printf 'gemini\n'
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
  echo "Invalid or missing setup agent provider; expected --agent codex, --agent claude, or --agent gemini." >&2
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
- For every missing preference or track field, propose a recommended answer grounded in the CV and current context; let the user override it.
- If the user replies with partial answers or delegation phrases such as `suggest`, `use your suggestions`, `pick whatever you think is best`, `default`, or `go ahead`, treat the remaining low-risk choices as delegated and continue automatically.
- Write local user data only under profile/ and tracks/. Never edit shared/templates/profile/*.
- First make profile/cv.md ready. If it is still the template, look for an existing Markdown CV or a PDF in profile/. If exactly one PDF exists and pdftotext is available, draft profile/cv.md from it and ask the user to review. If multiple PDFs exist, ask which one. If no PDF exists, use this wording: "If you want me to read a PDF, tell me the path or copy it into profile/ now; then I will extract it. Otherwise complete profile/cv.md now and tell me when ready."
- Then make profile/prefs_global.md ready. Infer only safe facts from the CV, then ask short questions for work mode, geography, seniority, contract type, compensation or practical constraints, authorization, dealbreakers, strong signals, and borderline signals. Write the reviewed answers.
- Collect the minimum track brief before source discovery: user name, track display name and slug, broad search area, goals or role types, keep-only keywords, constraints or red flags, and geography or remote preferences.
- After the minimum brief exists, propose a starter seed list, cadence defaults, track-wide terms, and native-filter posture instead of making the user invent them from scratch.
- If the known source list is sparse or missing, treat invoking $discover-sources as the recommended default next step rather than a neutral menu choice. Discovery will exclude the user's current or most recent employer by default.
- Keep the $discover-sources user-facing summary concise: recommended sources, dropped sources, URL corrections, caveats, recommended defaults to apply now, and only the truly necessary decisions.
- After discovery, continue automatically: present one recommended keep/drop/cadence/filter package, apply it unless the user objects, infer source-specific terms and native filters from profile and preferences, and auto-pick canaries where possible.
- Use scripts/probe_career_source.py for source probing when possible instead of guessing from WebFetch alone.
- Scaffold and validate the track. Setup aims for a **first-digest milestone**: a rendered digest from a valid scaffold that proves the track works. Do not let failed or complex secondary sources block this milestone.
- For sources that need code, tune config first. **Do not run synchronous scripts/source_integration.py** during interactive setup. Instead, use scripts/start_source_integration.py to start a background job for top sources and report the log path. Queue the rest in source_state.json and validate with scripts/integrate_next_source.py --dry-run.
- End guided setup by running a first local digest with bash scripts/run_track.sh --track <track> and pasting a preview of tracks/<track>/digests/YYYY-MM-DD.md into the conversation before moving on to delivery or scheduling. If run_track.sh fails, treat it as a blocker rather than skipping the preview.
- Only after the digest JSON exists, dry-run any requested delivery method first: scripts/send_digest_email.py --dry-run for email and scripts/send_digest_telegram.py --dry-run for Telegram.
- Guide delivery and scheduling last. Do not install the scheduler or send real email or Telegram messages unless the user explicitly confirms.
- Note on Ignored Files: Gemini/Claude may report that local profile/track files are gitignored. Always use shell commands (cat/grep) to read them when standard tools fail.
- Remove repo-development drift from final responses. Generated profile/track artifacts are local and gitignored; suggest a commit message only if repository files were changed.
EOF
)

SETUP_USER_PROMPT="Start guided setup now. Use the project skill \$set-up and keep following the repo's first-track setup flow until the first local digest preview is shown."

SETUP_FALLBACK_PROMPT=$(cat <<'EOF'
Use the project skill $set-up for a guided first-track setup in this repo.

Default behavior:
- Propose recommended answers for missing profile and track preferences; let me override them.
- If the source list is sparse, use $discover-sources as the recommended next step.
- After discovery, apply the recommended keep/drop/cadence/filter defaults unless I object.
- Continue automatically through canaries, probing, scaffolding, validation, and the first local digest preview.
- Do not move on to email or scheduling before the first digest preview.
EOF
)

print_claude_interactive_guidance() {
  local rerun_command="bash scripts/start_setup_agent.sh --agent claude"

  if [[ -n "$AGENT_BIN_VALUE" ]]; then
    rerun_command+=" --agent-bin $AGENT_BIN_VALUE"
  fi

  cat >&2 <<EOF
Claude interactive note:
- If Claude shows a workspace trust dialog before setup starts, trust this folder and rerun:
  $rerun_command
- If Claude opens without the guided setup contract, paste this prompt:

$SETUP_FALLBACK_PROMPT
EOF
}

print_gemini_interactive_guidance() {
  cat >&2 <<EOF
Gemini interactive note:
- This launch uses Gemini CLI prompt-interactive mode with the guided setup contract.
- If Gemini reports missing authentication, run 'gemini' once to authenticate and rerun this command.
- If Gemini opens without the guided setup contract, paste this prompt:

$SETUP_FALLBACK_PROMPT
EOF
}

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
    print_claude_interactive_guidance
    exec "$AGENT_BIN_VALUE" \
      --permission-mode acceptEdits \
      --allowedTools "Read,Write,Edit,MultiEdit,Bash,Glob,Grep,LS,WebSearch,WebFetch,TodoWrite" \
      --append-system-prompt "$SETUP_PROMPT" \
      "$SETUP_USER_PROMPT"
      ;;
  gemini)
    print_gemini_interactive_guidance
    exec "$AGENT_BIN_VALUE" \
      --skip-trust \
      --approval-mode "${JOB_AGENT_GEMINI_SETUP_APPROVAL_MODE:-${JOB_AGENT_GEMINI_APPROVAL_MODE:-yolo}}" \
      --prompt-interactive "$SETUP_PROMPT

$SETUP_USER_PROMPT"
      ;;
esac
