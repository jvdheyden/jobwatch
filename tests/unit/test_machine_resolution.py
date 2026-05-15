from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import agent_provider
import eval_source_quality
import source_integration


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(0o755)


def test_resolve_reviewer_bin_falls_back_to_codex_on_path(tmp_path, monkeypatch) -> None:
    fake_codex = tmp_path / "codex"
    _write_executable(fake_codex, "#!/bin/bash\nexit 0\n")

    monkeypatch.delenv("JOB_AGENT_REVIEWER_BIN", raising=False)
    monkeypatch.delenv("JOB_AGENT_BIN", raising=False)
    monkeypatch.delenv("JOB_AGENT_PROVIDER", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))

    assert eval_source_quality.resolve_reviewer_bin(None) == fake_codex


def test_resolve_coder_bin_falls_back_to_codex_on_path(tmp_path, monkeypatch) -> None:
    fake_codex = tmp_path / "codex"
    _write_executable(fake_codex, "#!/bin/bash\nexit 0\n")

    monkeypatch.delenv("JOB_AGENT_CODER_BIN", raising=False)
    monkeypatch.delenv("JOB_AGENT_BIN", raising=False)
    monkeypatch.delenv("JOB_AGENT_PROVIDER", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))

    assert source_integration.resolve_coder_bin(None) == fake_codex


def test_resolve_agent_bin_uses_job_agent_bin_before_provider_default(tmp_path, monkeypatch) -> None:
    neutral_bin = tmp_path / "neutral-agent"
    default_codex = tmp_path / "codex"
    _write_executable(neutral_bin, "#!/bin/bash\nexit 0\n")
    _write_executable(default_codex, "#!/bin/bash\nexit 0\n")

    monkeypatch.setenv("JOB_AGENT_PROVIDER", "codex")
    monkeypatch.setenv("JOB_AGENT_BIN", str(neutral_bin))
    monkeypatch.setenv("PATH", str(tmp_path))

    assert agent_provider.resolve_agent_bin() == neutral_bin


def test_resolve_agent_bin_uses_claude_default_for_claude_provider(tmp_path, monkeypatch) -> None:
    fake_claude = tmp_path / "claude"
    _write_executable(fake_claude, "#!/bin/bash\nexit 0\n")

    monkeypatch.setenv("JOB_AGENT_PROVIDER", "claude")
    monkeypatch.delenv("JOB_AGENT_BIN", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))

    assert agent_provider.resolve_agent_bin() == fake_claude


def test_resolve_agent_bin_uses_gemini_default_for_gemini_provider(tmp_path, monkeypatch) -> None:
    fake_gemini = tmp_path / "gemini"
    _write_executable(fake_gemini, "#!/bin/bash\nexit 0\n")

    monkeypatch.setenv("JOB_AGENT_PROVIDER", "gemini")
    monkeypatch.delenv("JOB_AGENT_BIN", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))

    assert agent_provider.resolve_agent_bin() == fake_gemini


def test_resolve_agent_provider_rejects_unknown(monkeypatch) -> None:
    monkeypatch.setenv("JOB_AGENT_PROVIDER", "llama")

    try:
        agent_provider.resolve_agent_provider()
    except ValueError as exc:
        assert "JOB_AGENT_PROVIDER must be one of" in str(exc)
    else:
        raise AssertionError("expected unknown provider to fail")


def test_eval_source_quality_cli_loads_runtime_env_before_reviewer_resolution(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    fake_codex = tmp_path / "codex"
    _write_executable(
        fake_codex,
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "cat >/dev/null\n"
        "printf '{\"defects\": []}\\n'\n",
    )
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "\n".join(
            [
                f"export JOB_AGENT_ROOT={repo_root}",
                "export JOB_AGENT_PROVIDER=codex",
                f"export JOB_AGENT_BIN={fake_codex}",
                "",
            ]
        )
    )
    artifact_path = tmp_path / "artifact.json"
    output_path = tmp_path / "eval.json"
    artifact_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "track": "test",
                "today": "2026-05-15",
                "sources": [
                    {
                        "source": "Example",
                        "source_url": "https://jobs.example.com",
                        "discovery_mode": "html",
                        "cadence_group": "every_run",
                        "last_checked": None,
                        "due_today": True,
                        "status": "complete",
                        "listing_pages_scanned": 1,
                        "search_terms_tried": ["security"],
                        "result_pages_scanned": "fixture=1",
                        "direct_job_pages_opened": 0,
                        "enumerated_jobs": 1,
                        "matched_jobs": 1,
                        "limitations": [],
                        "candidates": [
                            {
                                "employer": "Example",
                                "title": "Security Engineer",
                                "url": "https://jobs.example.com/job/1",
                                "source_url": "https://jobs.example.com",
                                "alternate_url": "",
                                "location": "Remote",
                                "remote": "remote",
                                "matched_terms": ["security"],
                                "notes": "Responsibilities: Build security systems and cryptography services for production.",
                            }
                        ],
                    }
                ],
            }
        )
    )
    env = os.environ | {
        "JOB_AGENT_ENV_FILE": str(env_file),
        "PATH": "/usr/bin:/bin",
    }
    for key in ("JOB_AGENT_PROVIDER", "JOB_AGENT_BIN", "JOB_AGENT_REVIEWER_BIN", "JOB_AGENT_CODER_BIN"):
        env.pop(key, None)

    result = subprocess.run(
        [
            str(repo_root / ".venv" / "bin" / "python"),
            str(repo_root / "scripts" / "eval_source_quality.py"),
            "--track",
            "test",
            "--source",
            "Example",
            "--today",
            "2026-05-15",
            "--artifact-path",
            str(artifact_path),
            "--output",
            str(output_path),
            "--reviewer",
            "force",
        ],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output_path.read_text())
    assert payload["reviewer"]["status"] == "completed"
    assert payload["final_status"] == "pass"
