#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT="${JOB_AGENT_ROOT:-$REPO_ROOT}"
ENV_FILE="${JOB_AGENT_ENV_FILE:-$ROOT/.env.local}"
AGENT_VALUE=""
AGENT_BIN_VALUE=""
MODEL_VALUE=""
REASONING_VALUE=""

usage() {
  cat <<EOF
Usage: $0 [--agent codex|claude|gemini] [--agent-bin <path>] [--model <model>] [--reasoning <level>]

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
    --model)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --model" >&2
        usage >&2
        exit 2
      fi
      MODEL_VALUE="$2"
      shift 2
      ;;
    --reasoning)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --reasoning" >&2
        usage >&2
        exit 2
      fi
      REASONING_VALUE="$2"
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

if [[ -x "$SCRIPT_DIR/../.venv/bin/python" ]]; then
  PYTHON_BIN="$SCRIPT_DIR/../.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "Python is required to resolve setup model policy." >&2
  exit 1
fi

mapfile -d '' -t SETUP_COMMAND < <(
  "$PYTHON_BIN" - "$SCRIPT_DIR" "$AGENT_VALUE" "$AGENT_BIN_VALUE" "$ROOT" "$MODEL_VALUE" "$REASONING_VALUE" <<'PY'
import sys
from pathlib import Path

script_dir, provider, agent_bin, root, model, reasoning = sys.argv[1:]
sys.path.insert(0, script_dir)
from agent_provider import build_setup_coordinator_command, resolve_setup_policy

try:
    policy = resolve_setup_policy(
        provider,
        "setup_coordinator",
        model=model or None,
        reasoning=reasoning or None,
    )
    command = build_setup_coordinator_command(policy, Path(root), Path(agent_bin))
except ValueError as exc:
    print(f"start_setup_agent.sh: {exc}", file=sys.stderr)
    raise SystemExit(2)
sys.stdout.buffer.write(b"\0".join(item.encode() for item in command) + b"\0")
PY
)
if [[ ${#SETUP_COMMAND[@]} -eq 0 ]]; then
  echo "Could not resolve setup model policy." >&2
  exit 2
fi

# Never pass plaintext SMTP secrets into agent processes. Password commands are
# local retrieval recipes and may remain visible for setup guidance.
unset JOB_AGENT_SMTP_PASSWORD

IFS= read -r -d '' SETUP_PROMPT <<'EOF' || true
Use the project skill $set-up for a guided first-track setup.

Contract:
- Treat setup as a single guided onboarding flow, not a sequence the user has to discover.
- For every missing preference or track field, propose a recommended answer grounded in the CV and current context; let the user override it.
- If the user replies with partial answers or delegation phrases such as `suggest`, `use your suggestions`, `pick whatever you think is best`, `default`, or `go ahead`, treat the remaining low-risk choices as delegated and continue automatically.
- Treat the canonical $set-up skill as authoritative for profile readiness, setup.json creation, worker handoffs, deterministic scaffolding, compact first preview, delivery, and scheduling.
- Persist reviewed decisions under artifacts/setup/<setup-id>/setup.json; do not put transcripts, prompts, CV prose, credentials, or environment dumps in setup artifacts.
- Use scripts/run_setup_worker.py for source_discovery and scripts/run_setup_preview.py for preview_ranker. Do not do routine source browsing or consume the full discovery artifact in this coordinator session.
- Use scripts/scaffold_track.py for create-only track generation. Do not hand-render track files or invoke a model for scaffolding.
- Do not move on to delivery or scheduling until the compact first digest preview has been rendered and shown, unless the user explicitly defers it.
- Never send real email or Telegram messages or install scheduling without explicit confirmation.
EOF

SETUP_USER_PROMPT="Start guided setup now. Use the project skill \$set-up and keep following the repo's first-track setup flow until the first local digest preview is shown."

IFS= read -r -d '' SETUP_FALLBACK_PROMPT <<'EOF' || true
Use the project skill $set-up for a guided first-track setup in this repo.

Default behavior:
- Propose recommended answers for missing profile and track preferences; let me override them.
- Persist reviewed decisions in a bounded setup.json artifact.
- If the source list is sparse, run the fresh source_discovery worker and apply its recommended defaults unless I object.
- Use deterministic scaffolding and the compact preview_ranker path for the first digest.
- Do not move on to email or scheduling before the first digest preview.
EOF

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
    exec "${SETUP_COMMAND[@]}" "$SETUP_PROMPT"
      ;;
  claude)
    print_claude_interactive_guidance
    exec "${SETUP_COMMAND[@]}" \
      --append-system-prompt "$SETUP_PROMPT"
      ;;
  gemini)
    print_gemini_interactive_guidance
    exec "${SETUP_COMMAND[@]}" \
      --prompt-interactive "$SETUP_PROMPT

$SETUP_USER_PROMPT"
      ;;
esac
