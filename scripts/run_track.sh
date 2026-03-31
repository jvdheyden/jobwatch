#!/bin/bash
set -euo pipefail

TRACK=""
TIMEOUT_SECS="${TIMEOUT_SECS:-2700}"
CODEX_BIN="${CODEX_BIN:-/opt/homebrew/bin/codex}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

usage() {
  echo "Usage: $0 --track <slug> [--timeout-secs <seconds>]" >&2
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
PROMPT_FILE="$(mktemp "${TMPDIR:-/tmp}/${TRACK}-prompt.XXXXXX")"

mkdir -p "$DIGEST_DIR" "$DISCOVERY_DIR" "$LOG_DIR"
trap 'rm -f "$PROMPT_FILE"' EXIT
exec >>"$LOG_FILE" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting $TRACK daily run"

if python3 "$ROOT/scripts/discover_jobs.py" \
  --track "$TRACK" \
  --today "$TODAY" \
  --due-only \
  --pretty \
  --output "$DISCOVERY_ARTIFACT" \
  --latest-output "$DISCOVERY_LATEST"; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Wrote discovery artifact to $DISCOVERY_ARTIFACT"
else
  DISCOVERY_STATUS=$?
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Discovery artifact generation failed with status $DISCOVERY_STATUS; Codex will fall back to live discovery as needed"
fi

cat >"$PROMPT_FILE" <<EOF
Run today's $TRACK workflow from the repository root in mode: track_run.
Follow the repository AGENTS.md for mode routing, then follow tracks/$TRACK/AGENTS.md for the workflow.
Use scripted discovery helpers when available.
A discovery artifact for today's scheduled run has already been written to ./artifacts/discovery/$TRACK/$TODAY.json and ./artifacts/discovery/$TRACK/latest.json.
Use those artifact files directly as the primary discovery input.
Do not rerun ./scripts/discover_jobs.py during this scheduled pass unless the artifact is missing, stale, or inconsistent with today's due sources.
This is a normal scheduled run, not a debugging session.
Do not inspect ./logs or downstream publication targets such as /Users/jvdh/Documents/logseq unless explicitly asked to debug the runner.
EOF

JOB_AGENT_ROOT="$ROOT" \
JOB_AGENT_TRACK="$TRACK" \
JOB_AGENT_TODAY="$TODAY" \
"$CODEX_BIN" --search -a never exec -C "$ROOT" -s workspace-write - <"$PROMPT_FILE" &
CODEX_PID=$!

(
  sleep "$TIMEOUT_SECS"
  if kill -0 "$CODEX_PID" 2>/dev/null; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Codex exceeded ${TIMEOUT_SECS}s; terminating"
    kill "$CODEX_PID" 2>/dev/null || true
    sleep 5
    if kill -0 "$CODEX_PID" 2>/dev/null; then
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] Codex still running after TERM; forcing kill"
      kill -9 "$CODEX_PID" 2>/dev/null || true
    fi
  fi
) &
WATCHDOG_PID=$!

set +e
wait "$CODEX_PID"
CODEX_STATUS=$?
set -e

kill "$WATCHDOG_PID" 2>/dev/null || true
wait "$WATCHDOG_PID" 2>/dev/null || true

if [[ $CODEX_STATUS -ne 0 ]]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Codex exited with status $CODEX_STATUS"
  exit "$CODEX_STATUS"
fi

if [[ -f "$DAILY_DIGEST" ]]; then
  /bin/bash "$ROOT/scripts/sync_to_logseq.sh" --track "$TRACK"
else
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] No digest at $DAILY_DIGEST; skipping Logseq sync"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Finished $TRACK daily run"
