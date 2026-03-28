#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TRACK="test_workflow"
TODAY="${JOB_AGENT_TODAY:-$(date +%F)}"
JOURNAL_DATE="${JOB_AGENT_JOURNAL_DATE:-$(date +%Y_%m_%d)}"
PORT="${TEST_WORKFLOW_PORT:-18765}"
FIXTURE_DIR="$ROOT/tests/fixtures/test_workflow"
TEST_DIR="$ROOT/tests/tmp/test_workflow"
GRAPH_DIR="$TEST_DIR/logseq"
SERVER_LOG="$TEST_DIR/http-server.log"
RUN_LOG="$ROOT/logs/$TRACK-$TODAY.log"
ARTIFACT_DIR="$ROOT/artifacts/discovery/$TRACK"
DIGEST_PATH="$ROOT/tracks/$TRACK/digests/$TODAY.md"
OVERVIEW_PATH="$ROOT/tracks/$TRACK/ranked_overview.md"
STATE_PATH="$ROOT/shared/ranked_jobs/$TRACK.json"
DIGEST_PAGE="$GRAPH_DIR/pages/Test Workflow Job Digest $TODAY.md"
OVERVIEW_PAGE="$GRAPH_DIR/pages/Test Workflow Ranked Overview.md"
JOURNAL_PATH="$GRAPH_DIR/journals/$JOURNAL_DATE.md"

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}

mkdir -p "$TEST_DIR"
rm -f "$RUN_LOG" "$DIGEST_PATH" "$OVERVIEW_PATH" "$STATE_PATH" \
  "$ARTIFACT_DIR/$TODAY.json" "$ARTIFACT_DIR/latest.json"
rm -rf "$GRAPH_DIR"

python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$FIXTURE_DIR" >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!
trap cleanup EXIT

for _ in $(seq 1 20); do
  if python3 - "$PORT" <<'PY'
import sys
from urllib.request import urlopen

port = sys.argv[1]
with urlopen(f"http://127.0.0.1:{port}/test_workflow_board.html", timeout=1) as response:
    raise SystemExit(0 if response.status == 200 else 1)
PY
  then
    break
  fi
  sleep 0.2
done

CODEX_BIN="$ROOT/tests/e2e/fake_codex.sh" \
JOB_AGENT_ROOT="$ROOT" \
JOB_AGENT_TODAY="$TODAY" \
JOB_AGENT_JOURNAL_DATE="$JOURNAL_DATE" \
LOGSEQ_GRAPH_DIR="$GRAPH_DIR" \
/bin/bash "$ROOT/scripts/run_track.sh" --track "$TRACK" --timeout-secs 120

for path in \
  "$ARTIFACT_DIR/$TODAY.json" \
  "$ARTIFACT_DIR/latest.json" \
  "$DIGEST_PATH" \
  "$OVERVIEW_PATH" \
  "$STATE_PATH" \
  "$DIGEST_PAGE" \
  "$OVERVIEW_PAGE" \
  "$JOURNAL_PATH"
do
  if [[ ! -f "$path" ]]; then
    echo "Missing expected output: $path" >&2
    exit 1
  fi
done

rg -q "Cryptography Advisor" "$DIGEST_PATH"
rg -q "Cryptography Advisor" "$OVERVIEW_PATH"
rg -q "Cryptography Advisor" "$DIGEST_PAGE"
rg -q "Test Workflow Job Digest $TODAY" "$JOURNAL_PATH"

echo "Generic track workflow test passed."
echo "Artifact: $ARTIFACT_DIR/$TODAY.json"
echo "Digest: $DIGEST_PATH"
echo "Ranked overview: $OVERVIEW_PATH"
echo "Logseq digest page: $DIGEST_PAGE"
echo "Logseq overview page: $OVERVIEW_PAGE"
