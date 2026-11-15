from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = str(REPO_ROOT / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
TESTS_DIR = str(Path(__file__).resolve().parent)
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)


def bash_quote(value: object) -> str:
    """Quote a value the way bash's `printf '%q'` does for paths used in tests.

    Keeps generated `.env.local` files source-able and lets assertions match
    setup_machine.sh output when the repo checkout lives at a path containing
    spaces.
    """
    text = str(value)
    return text.replace("\\", "\\\\").replace(" ", "\\ ")


@pytest.fixture(autouse=True)
def isolate_machine_local_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in list(os.environ):
        if name.startswith(("JOB_AGENT_", "XDG_", "AGENT_", "CODEX_", "CLAUDE_", "GEMINI_")):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("LOGSEQ_GRAPH_DIR", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    # XDG defaults now resolve beneath the isolated HOME. Tests exercising
    # explicit XDG overrides set them themselves.
    monkeypatch.setenv("PATH", f"{REPO_ROOT / '.venv' / 'bin'}:{os.environ['PATH']}")
    guard_dir = str(REPO_ROOT / "tests" / "offline")
    monkeypatch.setenv("PYTHONPATH", guard_dir + os.pathsep + os.environ.get("PYTHONPATH", ""))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    from offline.sitecustomize import deny_network, deny_network_ex
    import socket

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_network_ex)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.skipped and not item.get_closest_marker("optional"):
        report.outcome = "failed"
        report.longrepr = f"{item.nodeid}: required tests must not skip: {report.longrepr}"


@pytest.hookimpl(tryfirst=True)
def pytest_collectreport(report):
    if report.skipped:
        report.outcome = "failed"
        report.longrepr = f"{report.nodeid}: collection must not skip; move optional capability checks into marked tests: {report.longrepr}"


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def tmp_case_dir(tmp_path: Path) -> Path:
    path = tmp_path / "case"
    path.mkdir()
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
        child_env = dict(os.environ if env is None else env)
        child_env['PYTHONPATH'] = str(REPO_ROOT / 'tests/offline') + os.pathsep + child_env.get('PYTHONPATH', '')
        return subprocess.run(
            list(args),
            check=False,
            text=True,
            capture_output=True,
            env=child_env,
            cwd=cwd,
            timeout=45,
        )

    return _run


@pytest.fixture
def fake_codex_bin(repo_root: Path) -> Path:
    return repo_root / "tests" / "e2e" / "fake_codex.sh"
