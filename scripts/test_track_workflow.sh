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
RUN_LOG="$ROOT/logs/$TRACK-$TODAY.log"
ARTIFACT_DIR="$ROOT/artifacts/discovery/$TRACK"
STRUCTURED_DIGEST_DIR="$ROOT/artifacts/digests/$TRACK"
STRUCTURED_DIGEST_PATH="$STRUCTURED_DIGEST_DIR/$TODAY.json"
DIGEST_PATH="$ROOT/tracks/$TRACK/digests/$TODAY.md"
OVERVIEW_PATH="$ROOT/tracks/$TRACK/ranked_overview.md"
STATE_PATH="$ROOT/shared/ranked_jobs/$TRACK.json"
DIGEST_PAGE="$GRAPH_DIR/pages/Test Workflow Job Digest $TODAY.md"
OVERVIEW_PAGE="$GRAPH_DIR/pages/Test Workflow Ranked Overview.md"
JOURNAL_PATH="$GRAPH_DIR/journals/$JOURNAL_DATE.md"
SOURCES_PATH="$ROOT/tracks/$TRACK/sources.md"
SOURCES_BACKUP="$TEST_DIR/sources.md.backup"

cleanup() {
  if [[ -f "$SOURCES_BACKUP" ]]; then
    cp "$SOURCES_BACKUP" "$SOURCES_PATH"
    rm -f "$SOURCES_BACKUP"
  fi
}

mkdir -p "$TEST_DIR"
mkdir -p "$ARTIFACT_DIR" "$STRUCTURED_DIGEST_DIR" "$(dirname "$DIGEST_PATH")"
find "$ARTIFACT_DIR" -maxdepth 1 -type f -name '*.json' -delete
find "$STRUCTURED_DIGEST_DIR" -maxdepth 1 -type f -name '*.json' -delete
find "$(dirname "$DIGEST_PATH")" -maxdepth 1 -type f -name '*.md' -delete
rm -f "$RUN_LOG" "$OVERVIEW_PATH" "$STATE_PATH"
rm -rf "$GRAPH_DIR"

trap cleanup EXIT

cp "$SOURCES_PATH" "$SOURCES_BACKUP"
LOCAL_BOARD_URL="$(python3 - "$FIXTURE_DIR/test_workflow_board.html" <<'PY'
from pathlib import Path
import sys

print(Path(sys.argv[1]).resolve().as_uri())
PY
)"
python3 - "$SOURCES_PATH" "$LOCAL_BOARD_URL" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
local_board_url = sys.argv[2]
text = path.read_text()
text = text.replace("http://127.0.0.1:18765/test_workflow_board.html", local_board_url)
path.write_text(text)
PY

CODEX_BIN="$ROOT/tests/e2e/fake_codex.sh" \
JOB_AGENT_ROOT="$ROOT" \
JOB_AGENT_TODAY="$TODAY" \
JOB_AGENT_JOURNAL_DATE="$JOURNAL_DATE" \
LOGSEQ_GRAPH_DIR="$GRAPH_DIR" \
/bin/bash "$ROOT/scripts/run_track.sh" --track "$TRACK" --timeout-secs 120

for path in \
  "$ARTIFACT_DIR/$TODAY.json" \
  "$ARTIFACT_DIR/latest.json" \
  "$STRUCTURED_DIGEST_PATH" \
  "$STRUCTURED_DIGEST_DIR/latest.json" \
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
rg -q '"schema_version": 1' "$STRUCTURED_DIGEST_PATH"
rg -q "Test Workflow Job Digest $TODAY" "$JOURNAL_PATH"
rg -q "Discovery phase started" "$RUN_LOG"
rg -q "Codex phase started" "$RUN_LOG"
rg -q "Sync phase finished successfully" "$RUN_LOG"
rg -q "Finished $TRACK daily run" "$RUN_LOG"

echo "Generic track workflow test passed."
echo "Artifact: $ARTIFACT_DIR/$TODAY.json"
echo "Structured digest: $STRUCTURED_DIGEST_PATH"
echo "Digest: $DIGEST_PATH"
echo "Ranked overview: $OVERVIEW_PATH"
echo "Logseq digest page: $DIGEST_PAGE"
echo "Logseq overview page: $OVERVIEW_PAGE"
