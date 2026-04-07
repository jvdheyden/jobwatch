from __future__ import annotations

import os


def _write_sync_inputs(root, date_stamp: str) -> None:
    digest_dir = root / "tracks" / "core_crypto" / "digests"
    digest_dir.mkdir(parents=True, exist_ok=True)
    (digest_dir / f"{date_stamp}.md").write_text("# Job Digest — 2026-03-29\nTags: [[job digest core_crypto]]\n")
    overview_path = root / "tracks" / "core_crypto" / "ranked_overview.md"
    overview_path.parent.mkdir(parents=True, exist_ok=True)
    overview_path.write_text("# Ranked Overview — Core Crypto\n")


def test_sync_to_logseq_copies_digest_and_overview_to_temp_graph(tmp_job_agent_root, tmp_graph_dir, repo_root, run_cmd):
    _write_sync_inputs(tmp_job_agent_root, "2026-03-29")
    env = os.environ | {
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_TODAY": "2026-03-29",
        "JOB_AGENT_JOURNAL_DATE": "2026_03_29",
        "LOGSEQ_GRAPH_DIR": str(tmp_graph_dir),
    }

    result = run_cmd(
        "bash",
        str(repo_root / "scripts" / "sync_to_logseq.sh"),
        "--track",
        "core_crypto",
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_graph_dir / "pages" / "Core Crypto Job Digest 2026-03-29.md").exists()
    assert (tmp_graph_dir / "pages" / "Core Crypto Ranked Overview.md").exists()
    journal_text = (tmp_graph_dir / "journals" / "2026_03_29.md").read_text()
    assert journal_text == "- New [[Core Crypto Job Digest 2026-03-29]]\n"


def test_sync_to_logseq_inserts_blank_line_before_entry_when_journal_not_empty(
    tmp_job_agent_root, tmp_graph_dir, repo_root, run_cmd
):
    _write_sync_inputs(tmp_job_agent_root, "2026-03-29")
    journal_path = tmp_graph_dir / "journals" / "2026_03_29.md"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.write_text("- Existing entry\n")
    env = os.environ | {
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_TODAY": "2026-03-29",
        "JOB_AGENT_JOURNAL_DATE": "2026_03_29",
        "LOGSEQ_GRAPH_DIR": str(tmp_graph_dir),
    }

    result = run_cmd(
        "bash",
        str(repo_root / "scripts" / "sync_to_logseq.sh"),
        "--track",
        "core_crypto",
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert journal_path.read_text() == "- Existing entry\n\n- New [[Core Crypto Job Digest 2026-03-29]]\n"


def test_sync_to_logseq_does_not_duplicate_journal_link(tmp_job_agent_root, tmp_graph_dir, repo_root, run_cmd):
    _write_sync_inputs(tmp_job_agent_root, "2026-03-29")
    env = os.environ | {
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_TODAY": "2026-03-29",
        "JOB_AGENT_JOURNAL_DATE": "2026_03_29",
        "LOGSEQ_GRAPH_DIR": str(tmp_graph_dir),
    }

    first = run_cmd("bash", str(repo_root / "scripts" / "sync_to_logseq.sh"), "--track", "core_crypto", env=env)
    second = run_cmd("bash", str(repo_root / "scripts" / "sync_to_logseq.sh"), "--track", "core_crypto", env=env)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    journal_text = (tmp_graph_dir / "journals" / "2026_03_29.md").read_text()
    assert journal_text.count("- New [[Core Crypto Job Digest 2026-03-29]]") == 1


def test_sync_to_logseq_skips_when_graph_dir_is_unset(tmp_job_agent_root, repo_root, run_cmd):
    _write_sync_inputs(tmp_job_agent_root, "2026-03-29")
    env = os.environ | {
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_TODAY": "2026-03-29",
        "JOB_AGENT_JOURNAL_DATE": "2026_03_29",
    }

    result = run_cmd(
        "bash",
        str(repo_root / "scripts" / "sync_to_logseq.sh"),
        "--track",
        "core_crypto",
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert "LOGSEQ_GRAPH_DIR is not set; skipping Logseq sync" in result.stderr
