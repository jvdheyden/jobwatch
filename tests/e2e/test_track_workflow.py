from __future__ import annotations

import os


def test_test_workflow_track_runs_end_to_end(repo_root, run_cmd):
    env = os.environ | {
        "JOB_AGENT_TODAY": "2030-01-15",
        "JOB_AGENT_JOURNAL_DATE": "2030_01_15",
    }

    result = run_cmd("bash", str(repo_root / "scripts" / "test_track_workflow.sh"), env=env, cwd=repo_root)

    assert result.returncode == 0, result.stderr
    assert "Generic track workflow test passed." in result.stdout
