#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT"

bash -n scripts/run_track.sh
bash -n scripts/sync_to_logseq.sh
bash -n scripts/test_track_workflow.sh
bash -n tests/e2e/fake_codex.sh

PYTEST_ARGS=("$@")
if [[ ${#PYTEST_ARGS[@]} -eq 0 ]]; then
  PYTEST_ARGS=(-q)
fi

pytest \
  tests/unit/test_digest_json.py \
  tests/unit/test_render_digest.py \
  tests/unit/test_update_ranked_overview.py \
  tests/integration/test_sync_to_logseq.py \
  tests/integration/test_discover_iacr_jobs.py \
  tests/integration/test_discover_meta_browser.py \
  tests/integration/test_discover_yc_and_hn_jobs.py \
  tests/e2e/test_track_workflow.py \
  "${PYTEST_ARGS[@]}"
