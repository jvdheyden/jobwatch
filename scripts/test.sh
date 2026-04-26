#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="$ROOT/.venv/bin/python"

cd "$ROOT"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing repo-local virtualenv at $ROOT/.venv." >&2
  echo "Run: bash scripts/bootstrap_venv.sh" >&2
  exit 1
fi

bash -n scripts/run_track.sh
bash -n scripts/bootstrap_machine.sh
bash -n scripts/setup_machine.sh
bash -n scripts/install_bwrap_apparmor.sh
bash -n scripts/install_scheduler.sh
bash -n scripts/run_scheduled_jobs.sh
bash -n scripts/sync_to_logseq.sh
bash -n scripts/test_track_workflow.sh
bash -n scripts/sync_claude_skills.sh
bash -n tests/e2e/fake_codex.sh
"$PYTHON_BIN" -m py_compile scripts/configure_schedule.py
"$PYTHON_BIN" -m py_compile scripts/source_config.py
"$PYTHON_BIN" -m py_compile scripts/render_discovery_modes_md.py
"$PYTHON_BIN" -m py_compile scripts/render_sources_md.py
"$PYTHON_BIN" -m py_compile scripts/send_digest_telegram.py
"$PYTHON_BIN" -m py_compile scripts/update_source_state.py
"$PYTHON_BIN" -m py_compile scripts/source_integration.py
"$PYTHON_BIN" -m py_compile scripts/integrate_next_source.py
"$PYTHON_BIN" -m py_compile scripts/start_source_integration.py
"$PYTHON_BIN" -m py_compile scripts/telegram_chat_id.py
"$PYTHON_BIN" -m py_compile scripts/discover/*.py scripts/discover/sources/*.py
bash scripts/sync_claude_skills.sh --check
"$PYTHON_BIN" scripts/render_discovery_modes_md.py --check

PYTEST_ARGS=("$@")
if [[ ${#PYTEST_ARGS[@]} -eq 0 ]]; then
  PYTEST_ARGS=(-q)
fi

"$PYTHON_BIN" -m pytest \
  tests/contract \
  tests/unit/test_discover_jobs_config.py \
  tests/unit/test_discover_jobs_progress.py \
  tests/unit/test_digest_email.py \
  tests/unit/test_digest_json.py \
  tests/unit/test_render_digest.py \
  tests/unit/test_send_digest_email.py \
  tests/unit/test_send_digest_telegram.py \
  tests/unit/test_source_config.py \
  tests/unit/test_agent_support.py \
  tests/unit/test_machine_resolution.py \
  tests/unit/test_integrate_next_source.py \
  tests/unit/test_probe_career_source.py \
  tests/unit/test_telegram_chat_id.py \
  tests/unit/test_source_quality.py \
  tests/unit/test_update_ranked_overview.py \
  tests/integration/test_machine_setup.py \
  tests/integration/test_run_track.py \
  tests/integration/test_eval_source_quality.py \
  tests/integration/test_source_integration.py \
  tests/integration/test_sync_to_logseq.py \
  tests/integration/test_discover_asml_browser.py \
  tests/integration/test_discover_iacr_jobs.py \
  tests/integration/test_discover_lever_json.py \
  tests/integration/test_discover_meta_browser.py \
  tests/integration/test_discover_pcd_team.py \
  tests/integration/test_discover_public_service_sources.py \
  tests/integration/test_discover_service_bund.py \
  tests/integration/test_discover_yc_and_hn_jobs.py \
  tests/e2e/test_track_workflow.py \
  "${PYTEST_ARGS[@]}"
