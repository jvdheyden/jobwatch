from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = str(REPO_ROOT / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def tmp_case_dir(repo_root: Path, request: pytest.FixtureRequest) -> Path:
    path = repo_root / "tests" / "tmp" / request.node.name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def tmp_graph_dir(tmp_case_dir: Path) -> Path:
    path = tmp_case_dir / "logseq"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def tmp_job_agent_root(tmp_case_dir: Path) -> Path:
    path = tmp_case_dir / "root"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def load_json_fixture(repo_root: Path):
    def _load(relative_path: str):
        return json.loads((repo_root / "tests" / "fixtures" / relative_path).read_text())

    return _load


@pytest.fixture
def read_text_fixture(repo_root: Path):
    def _read(relative_path: str) -> str:
        return (repo_root / "tests" / "fixtures" / relative_path).read_text()

    return _read


@pytest.fixture
def run_cmd():
    def _run(*args: str, env: dict[str, str] | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(args),
            check=False,
            text=True,
            capture_output=True,
            env=env,
            cwd=cwd,
        )

    return _run


@pytest.fixture
def fake_codex_bin(repo_root: Path) -> Path:
    return repo_root / "tests" / "e2e" / "fake_codex.sh"
