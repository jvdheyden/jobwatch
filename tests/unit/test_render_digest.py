from __future__ import annotations

import json
from pathlib import Path


def test_render_digest_writes_markdown_and_latest_json(tmp_job_agent_root, load_json_fixture, read_text_fixture, repo_root, run_cmd):
    input_path = tmp_job_agent_root / "input.json"
    output_path = tmp_job_agent_root / "out.md"
    latest_output_path = tmp_job_agent_root / "latest.json"
    input_path.write_text(json.dumps(load_json_fixture("digests/core_crypto_minimal.json"), indent=2) + "\n")

    result = run_cmd(
        "python3",
        str(repo_root / "scripts" / "render_digest.py"),
        "--track",
        "core_crypto",
        "--date",
        "2026-03-29",
        "--input",
        str(input_path),
        "--output",
        str(output_path),
        "--latest-output",
        str(latest_output_path),
    )

    assert result.returncode == 0, result.stderr
    assert output_path.exists()
    assert latest_output_path.exists()
    assert output_path.read_text() == read_text_fixture("digests/core_crypto_minimal.md")
    assert latest_output_path.read_text() == input_path.read_text()
