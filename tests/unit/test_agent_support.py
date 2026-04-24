from __future__ import annotations

import subprocess
from pathlib import Path


def test_agent_imports_exist_for_repo_agents(repo_root: Path) -> None:
    ignored_roots = {repo_root / ".git", repo_root / "tests" / "tmp"}
    agents_files = []
    for path in repo_root.rglob("AGENTS.md"):
        if any(path.is_relative_to(ignored_root) for ignored_root in ignored_roots):
            continue
        agents_files.append(path)

    assert agents_files
    for agents_path in agents_files:
        claude_path = agents_path.with_name("CLAUDE.md")
        assert claude_path.read_text(encoding="utf-8") == "@AGENTS.md\n"
        gemini_path = agents_path.with_name("GEMINI.md")
        assert gemini_path.read_text(encoding="utf-8") == "@AGENTS.md\n"


def test_claude_skill_mirrors_are_current(repo_root: Path) -> None:
    result = subprocess.run(
        [
            "bash",
            str(repo_root / "scripts" / "sync_claude_skills.sh"),
            "--check",
        ],
        check=False,
        text=True,
        capture_output=True,
        cwd=repo_root,
    )

    assert result.returncode == 0, result.stderr
