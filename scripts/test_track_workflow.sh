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
TEST_ROOT="$TEST_DIR/root"
GRAPH_DIR="$TEST_ROOT/logseq"
RUN_LOG="$TEST_ROOT/logs/$TRACK-$TODAY.log"
ARTIFACT_DIR="$TEST_ROOT/artifacts/discovery/$TRACK"
STRUCTURED_DIGEST_DIR="$TEST_ROOT/artifacts/digests/$TRACK"
STRUCTURED_DIGEST_PATH="$STRUCTURED_DIGEST_DIR/$TODAY.json"
DIGEST_PATH="$TEST_ROOT/tracks/$TRACK/digests/$TODAY.md"
OVERVIEW_PATH="$TEST_ROOT/tracks/$TRACK/ranked_overview.md"
STATE_PATH="$TEST_ROOT/shared/ranked_jobs/$TRACK.json"
SOURCE_STATE_PATH="$TEST_ROOT/tracks/$TRACK/source_state.json"
DIGEST_PAGE="$GRAPH_DIR/pages/Test Workflow Job Digest $TODAY.md"
OVERVIEW_PAGE="$GRAPH_DIR/pages/Test Workflow Ranked Overview.md"
JOURNAL_PATH="$GRAPH_DIR/journals/$JOURNAL_DATE.md"
SOURCES_CONFIG_PATH="$TEST_ROOT/tracks/$TRACK/sources.json"

rm -rf "$TEST_ROOT"
mkdir -p "$TEST_ROOT/tracks" "$TEST_ROOT/shared" "$TEST_ROOT/logs"
cp -R "$ROOT/scripts" "$TEST_ROOT/scripts"
cp -R "$ROOT/tracks/$TRACK" "$TEST_ROOT/tracks/$TRACK"
cp "$ROOT/shared/digest_schema.md" "$TEST_ROOT/shared/digest_schema.md"
if [[ -d "$ROOT/.venv" ]]; then
  ln -s "$ROOT/.venv" "$TEST_ROOT/.venv"
fi
mkdir -p "$ARTIFACT_DIR" "$STRUCTURED_DIGEST_DIR" "$(dirname "$DIGEST_PATH")"
find "$ARTIFACT_DIR" -maxdepth 1 -type f -name '*.json' -delete
find "$STRUCTURED_DIGEST_DIR" -maxdepth 1 -type f -name '*.json' -delete
find "$(dirname "$DIGEST_PATH")" -maxdepth 1 -type f -name '*.md' -delete
rm -f "$RUN_LOG" "$OVERVIEW_PATH" "$STATE_PATH"
rm -rf "$GRAPH_DIR"

LOCAL_BOARD_URL="$(python3 - "$FIXTURE_DIR/test_workflow_board.html" <<'PY'
from pathlib import Path
import sys

print(Path(sys.argv[1]).resolve().as_uri())
PY
)"
python3 - "$SOURCES_CONFIG_PATH" "$LOCAL_BOARD_URL" <<'PY'
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
local_board_url = sys.argv[2]
payload = json.loads(path.read_text())
for source in payload["sources"]:
    if source["id"] == "local_test_board":
        source["url"] = local_board_url
path.write_text(json.dumps(payload, indent=2) + "\n")
PY
JOB_AGENT_ROOT="$TEST_ROOT" python3 "$TEST_ROOT/scripts/render_sources_md.py" --track "$TRACK"

PROVIDER="${JOB_AGENT_PROVIDER:-codex}"
FAKE_BIN="$ROOT/tests/e2e/fake_codex.sh"
if [[ "$PROVIDER" == "gemini" ]]; then
  FAKE_BIN="$ROOT/tests/e2e/fake_gemini.sh"
fi

JOB_AGENT_PROVIDER="$PROVIDER" \
JOB_AGENT_BIN="$FAKE_BIN" \
JOB_AGENT_ROOT="$TEST_ROOT" \
JOB_AGENT_TODAY="$TODAY" \
JOB_AGENT_JOURNAL_DATE="$JOURNAL_DATE" \
LOGSEQ_GRAPH_DIR="$GRAPH_DIR" \
/bin/bash "$TEST_ROOT/scripts/run_track.sh" --track "$TRACK" --delivery logseq --timeout-secs 120

for path in \
  "$ARTIFACT_DIR/$TODAY.json" \
  "$ARTIFACT_DIR/latest.json" \
  "$STRUCTURED_DIGEST_PATH" \
  "$STRUCTURED_DIGEST_DIR/latest.json" \
  "$DIGEST_PATH" \
  "$OVERVIEW_PATH" \
  "$STATE_PATH" \
  "$SOURCE_STATE_PATH" \
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
rg -q "\"last_checked\": \"$TODAY\"" "$SOURCE_STATE_PATH"
rg -q "Test Workflow Job Digest $TODAY" "$JOURNAL_PATH"
rg -q "Discovery phase started" "$RUN_LOG"
if [[ "$PROVIDER" == "gemini" ]]; then
  rg -q "Gemini phase started" "$RUN_LOG"
else
  rg -q "Codex phase started" "$RUN_LOG"
fi
rg -q "Delivery phase finished successfully: logseq" "$RUN_LOG"
rg -q "Finished $TRACK daily run" "$RUN_LOG"

echo "Generic track workflow test passed."
echo "Artifact: $ARTIFACT_DIR/$TODAY.json"
echo "Structured digest: $STRUCTURED_DIGEST_PATH"
echo "Digest: $DIGEST_PATH"
echo "Ranked overview: $OVERVIEW_PATH"
echo "Logseq digest page: $DIGEST_PAGE"
echo "Logseq overview page: $OVERVIEW_PAGE"
