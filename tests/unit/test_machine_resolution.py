from __future__ import annotations

from pathlib import Path

import eval_source_quality
import repair_source


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(0o755)


def test_resolve_reviewer_bin_falls_back_to_codex_on_path(tmp_path, monkeypatch) -> None:
    fake_codex = tmp_path / "codex"
    _write_executable(fake_codex, "#!/bin/bash\nexit 0\n")

    monkeypatch.delenv("JOB_AGENT_REVIEWER_BIN", raising=False)
    monkeypatch.delenv("CODEX_BIN", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))

    assert eval_source_quality.resolve_reviewer_bin(None) == fake_codex


def test_resolve_coder_bin_falls_back_to_codex_on_path(tmp_path, monkeypatch) -> None:
    fake_codex = tmp_path / "codex"
    _write_executable(fake_codex, "#!/bin/bash\nexit 0\n")

    monkeypatch.delenv("CODEX_BIN", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))

    assert repair_source.resolve_coder_bin(None) == fake_codex
