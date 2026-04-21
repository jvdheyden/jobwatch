from __future__ import annotations

from pathlib import Path

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


def test_resolve_agent_provider_rejects_unknown(monkeypatch) -> None:
    monkeypatch.setenv("JOB_AGENT_PROVIDER", "llama")

    try:
        agent_provider.resolve_agent_provider()
    except ValueError as exc:
        assert "JOB_AGENT_PROVIDER must be one of" in str(exc)
    else:
        raise AssertionError("expected unknown provider to fail")
