from __future__ import annotations

import os
import pty
import select
import subprocess
from pathlib import Path


def _write_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o755)


def _write_symlink(path: Path, target: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        path.unlink()
    path.symlink_to(target)


def _run_interactive(*args: str, input_text: str, env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    master_fd, slave_fd = pty.openpty()
    process = subprocess.Popen(
        list(args),
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=env,
        cwd=cwd,
        text=False,
    )
    os.close(slave_fd)

    output = bytearray()
    try:
        if input_text:
            os.write(master_fd, input_text.encode())

        while True:
            ready, _, _ = select.select([master_fd], [], [], 0.1)
            if ready:
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError:
                    chunk = b""
                if chunk:
                    output.extend(chunk)
                elif process.poll() is not None:
                    break
            elif process.poll() is not None:
                break
    finally:
        try:
            os.close(master_fd)
        except OSError:
            pass

    return subprocess.CompletedProcess(list(args), process.wait(), output.decode(errors="replace"), "")


def test_setup_machine_creates_local_files_and_preserves_schedule(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    env_file = tmp_job_agent_root / ".env.local"
    schedule_file = tmp_job_agent_root / ".schedule.local"
    scheduler_dir = tmp_job_agent_root / ".scheduler"
    fake_bin_dir = tmp_job_agent_root / "bin"
    _write_executable(fake_bin_dir / "codex", "#!/bin/bash\nexit 0\n")

    env = os.environ | {
        "HOME": str(tmp_job_agent_root / "home"),
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_ENV_FILE": str(env_file),
        "JOB_AGENT_SCHEDULE_FILE": str(schedule_file),
        "JOB_AGENT_SCHEDULER_DIR": str(scheduler_dir),
        "PATH": f"{fake_bin_dir}:{os.environ['PATH']}",
    }

    first = run_cmd("bash", str(repo_root / "scripts" / "setup_machine.sh"), env=env, cwd=repo_root)
    assert first.returncode == 0, first.stderr

    env_text = env_file.read_text()
    assert f"export JOB_AGENT_ROOT={str(tmp_job_agent_root)}" in env_text
    assert f"export CODEX_BIN={str(fake_bin_dir / 'codex')}" in env_text
    assert "# Optional: Logseq graph root for digest publication." in env_text
    assert schedule_file.exists()
    assert "daily 08:00 track core_crypto" in schedule_file.read_text()
    cron_text = (scheduler_dir / "cron.entry").read_text()
    assert cron_text.startswith("# BEGIN jobsearch scheduler\n* * * * * /bin/bash ")
    assert (scheduler_dir / "com.jvdh.jobsearch.scheduler.plist").exists()

    schedule_file.write_text("daily 08:00 track demo\n")

    second = run_cmd("bash", str(repo_root / "scripts" / "setup_machine.sh"), env=env, cwd=repo_root)
    assert second.returncode == 0, second.stderr
    assert schedule_file.read_text() == "daily 08:00 track demo\n"


def test_setup_machine_fails_noninteractive_without_codex(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    env_file = tmp_job_agent_root / ".env.local"
    schedule_file = tmp_job_agent_root / ".schedule.local"
    scheduler_dir = tmp_job_agent_root / ".scheduler"
    empty_bin_dir = tmp_job_agent_root / "empty-bin"
    empty_bin_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ | {
        "HOME": str(tmp_job_agent_root / "home"),
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_ENV_FILE": str(env_file),
        "JOB_AGENT_SCHEDULE_FILE": str(schedule_file),
        "JOB_AGENT_SCHEDULER_DIR": str(scheduler_dir),
        "PATH": f"{empty_bin_dir}:/usr/bin:/bin:/usr/sbin:/sbin",
    }

    result = run_cmd("bash", str(repo_root / "scripts" / "setup_machine.sh"), env=env, cwd=repo_root)
    assert result.returncode == 1
    assert "CODEX_BIN is required in non-interactive mode" in result.stderr
    assert not env_file.exists()


def test_setup_machine_interactively_prompts_for_missing_codex(tmp_job_agent_root: Path, repo_root: Path) -> None:
    env_file = tmp_job_agent_root / ".env.local"
    schedule_file = tmp_job_agent_root / ".schedule.local"
    scheduler_dir = tmp_job_agent_root / ".scheduler"
    fake_codex = tmp_job_agent_root / "tools" / "codex"
    empty_bin_dir = tmp_job_agent_root / "empty-bin"
    empty_bin_dir.mkdir(parents=True, exist_ok=True)
    _write_executable(fake_codex, "#!/bin/bash\nexit 0\n")

    env = os.environ | {
        "HOME": str(tmp_job_agent_root / "home"),
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_ENV_FILE": str(env_file),
        "JOB_AGENT_SCHEDULE_FILE": str(schedule_file),
        "JOB_AGENT_SCHEDULER_DIR": str(scheduler_dir),
        "PATH": f"{empty_bin_dir}:/usr/bin:/bin:/usr/sbin:/sbin",
    }

    result = _run_interactive(
        "bash",
        str(repo_root / "scripts" / "setup_machine.sh"),
        input_text=f"{fake_codex}\n\n",
        env=env,
        cwd=repo_root,
    )

    assert result.returncode == 0, result.stdout
    assert "CODEX_BIN (required):" in result.stdout
    assert "LOGSEQ_GRAPH_DIR (optional, blank to skip):" in result.stdout
    env_text = env_file.read_text()
    assert f"export CODEX_BIN={str(fake_codex)}" in env_text
    assert "# export LOGSEQ_GRAPH_DIR=/absolute/path/to/logseq" in env_text


def test_setup_machine_interactively_accepts_detected_defaults(tmp_job_agent_root: Path, repo_root: Path) -> None:
    env_file = tmp_job_agent_root / ".env.local"
    schedule_file = tmp_job_agent_root / ".schedule.local"
    scheduler_dir = tmp_job_agent_root / ".scheduler"
    fake_bin_dir = tmp_job_agent_root / "bin"
    home_dir = tmp_job_agent_root / "home"
    detected_graph_dir = home_dir / "Documents" / "logseq"
    detected_graph_dir.mkdir(parents=True, exist_ok=True)
    _write_executable(fake_bin_dir / "codex", "#!/bin/bash\nexit 0\n")

    env = os.environ | {
        "HOME": str(home_dir),
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_ENV_FILE": str(env_file),
        "JOB_AGENT_SCHEDULE_FILE": str(schedule_file),
        "JOB_AGENT_SCHEDULER_DIR": str(scheduler_dir),
        "PATH": f"{fake_bin_dir}:{os.environ['PATH']}",
    }

    result = _run_interactive(
        "bash",
        str(repo_root / "scripts" / "setup_machine.sh"),
        input_text="\n\n",
        env=env,
        cwd=repo_root,
    )

    assert result.returncode == 0, result.stdout
    assert f"CODEX_BIN [{fake_bin_dir / 'codex'}]:" in result.stdout
    assert f"LOGSEQ_GRAPH_DIR (optional, Enter to use {detected_graph_dir}, type skip to leave unset):" in result.stdout
    env_text = env_file.read_text()
    assert f"export CODEX_BIN={str(fake_bin_dir / 'codex')}" in env_text
    assert f"export LOGSEQ_GRAPH_DIR={str(detected_graph_dir)}" in env_text


def test_setup_machine_prefers_canonical_codex_path_on_linux(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    env_file = tmp_job_agent_root / ".env.local"
    schedule_file = tmp_job_agent_root / ".schedule.local"
    scheduler_dir = tmp_job_agent_root / ".scheduler"
    fake_bin_dir = tmp_job_agent_root / "bin"
    canonical_codex = tmp_job_agent_root / "tools" / "codex" / "bin" / "codex.js"
    _write_executable(canonical_codex, "#!/bin/bash\nexit 0\n")
    _write_symlink(fake_bin_dir / "codex", canonical_codex)

    env = os.environ | {
        "HOME": str(tmp_job_agent_root / "home"),
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_ENV_FILE": str(env_file),
        "JOB_AGENT_SCHEDULE_FILE": str(schedule_file),
        "JOB_AGENT_SCHEDULER_DIR": str(scheduler_dir),
        "JOB_AGENT_PLATFORM": "Linux",
        "PATH": f"{fake_bin_dir}:{os.environ['PATH']}",
    }

    result = run_cmd("bash", str(repo_root / "scripts" / "setup_machine.sh"), env=env, cwd=repo_root)
    assert result.returncode == 0, result.stderr

    env_text = env_file.read_text()
    assert f"export CODEX_BIN={str(canonical_codex)}" in env_text


def test_setup_machine_keeps_detected_codex_path_on_non_linux(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    env_file = tmp_job_agent_root / ".env.local"
    schedule_file = tmp_job_agent_root / ".schedule.local"
    scheduler_dir = tmp_job_agent_root / ".scheduler"
    fake_bin_dir = tmp_job_agent_root / "bin"
    canonical_codex = tmp_job_agent_root / "tools" / "codex" / "bin" / "codex.js"
    symlink_codex = fake_bin_dir / "codex"
    _write_executable(canonical_codex, "#!/bin/bash\nexit 0\n")
    _write_symlink(symlink_codex, canonical_codex)

    env = os.environ | {
        "HOME": str(tmp_job_agent_root / "home"),
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_ENV_FILE": str(env_file),
        "JOB_AGENT_SCHEDULE_FILE": str(schedule_file),
        "JOB_AGENT_SCHEDULER_DIR": str(scheduler_dir),
        "JOB_AGENT_PLATFORM": "Darwin",
        "PATH": f"{fake_bin_dir}:{os.environ['PATH']}",
    }

    result = run_cmd("bash", str(repo_root / "scripts" / "setup_machine.sh"), env=env, cwd=repo_root)
    assert result.returncode == 0, result.stderr

    env_text = env_file.read_text()
    assert f"export CODEX_BIN={str(symlink_codex)}" in env_text


def test_setup_machine_interactively_uses_canonical_codex_default_on_linux(tmp_job_agent_root: Path, repo_root: Path) -> None:
    env_file = tmp_job_agent_root / ".env.local"
    schedule_file = tmp_job_agent_root / ".schedule.local"
    scheduler_dir = tmp_job_agent_root / ".scheduler"
    fake_bin_dir = tmp_job_agent_root / "bin"
    canonical_codex = tmp_job_agent_root / "tools" / "codex" / "bin" / "codex.js"
    _write_executable(canonical_codex, "#!/bin/bash\nexit 0\n")
    _write_symlink(fake_bin_dir / "codex", canonical_codex)

    env = os.environ | {
        "HOME": str(tmp_job_agent_root / "home"),
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_ENV_FILE": str(env_file),
        "JOB_AGENT_SCHEDULE_FILE": str(schedule_file),
        "JOB_AGENT_SCHEDULER_DIR": str(scheduler_dir),
        "JOB_AGENT_PLATFORM": "Linux",
        "PATH": f"{fake_bin_dir}:{os.environ['PATH']}",
    }

    result = _run_interactive(
        "bash",
        str(repo_root / "scripts" / "setup_machine.sh"),
        input_text="\n\n",
        env=env,
        cwd=repo_root,
    )

    assert result.returncode == 0, result.stdout
    assert f"CODEX_BIN [{canonical_codex}]:" in result.stdout
    env_text = env_file.read_text()
    assert f"export CODEX_BIN={str(canonical_codex)}" in env_text


def test_run_scheduled_jobs_runs_due_tracks_once_per_stamp(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    env_file = tmp_job_agent_root / ".env.local"
    schedule_file = tmp_job_agent_root / ".schedule.local"
    env_file.write_text(f"export JOB_AGENT_ROOT={tmp_job_agent_root}\n")
    schedule_file.write_text("daily 08:00 track demo\n")

    _write_executable(
        tmp_job_agent_root / "scripts" / "run_track.sh",
        """#!/bin/bash
set -euo pipefail
ROOT="${JOB_AGENT_ROOT:?missing JOB_AGENT_ROOT}"
echo "$*" >> "$ROOT/invocations.log"
""",
    )

    env = os.environ | {
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_ENV_FILE": str(env_file),
        "JOB_AGENT_SCHEDULE_FILE": str(schedule_file),
        "JOB_AGENT_SCHEDULE_TIME": "08:00",
        "JOB_AGENT_SCHEDULE_STAMP": "2030-01-15-08:00",
    }

    first = run_cmd("bash", str(repo_root / "scripts" / "run_scheduled_jobs.sh"), env=env, cwd=repo_root)
    second = run_cmd("bash", str(repo_root / "scripts" / "run_scheduled_jobs.sh"), env=env, cwd=repo_root)
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert (tmp_job_agent_root / "invocations.log").read_text().splitlines() == ["--track demo"]

    third_env = env | {"JOB_AGENT_SCHEDULE_STAMP": "2030-01-16-08:00"}
    third = run_cmd("bash", str(repo_root / "scripts" / "run_scheduled_jobs.sh"), env=third_env, cwd=repo_root)
    assert third.returncode == 0, third.stderr
    assert (tmp_job_agent_root / "invocations.log").read_text().splitlines() == ["--track demo", "--track demo"]


def test_run_scheduled_jobs_is_noop_with_empty_schedule(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    env_file = tmp_job_agent_root / ".env.local"
    schedule_file = tmp_job_agent_root / ".schedule.local"
    env_file.write_text(f"export JOB_AGENT_ROOT={tmp_job_agent_root}\n")
    schedule_file.write_text("# no jobs yet\n")

    env = os.environ | {
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_ENV_FILE": str(env_file),
        "JOB_AGENT_SCHEDULE_FILE": str(schedule_file),
        "JOB_AGENT_SCHEDULE_TIME": "08:00",
        "JOB_AGENT_SCHEDULE_STAMP": "2030-01-15-08:00",
    }

    result = run_cmd("bash", str(repo_root / "scripts" / "run_scheduled_jobs.sh"), env=env, cwd=repo_root)
    assert result.returncode == 0, result.stderr
    assert not (tmp_job_agent_root / "invocations.log").exists()


def test_install_scheduler_updates_crontab_without_duplicates(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    env_file = tmp_job_agent_root / ".env.local"
    schedule_file = tmp_job_agent_root / ".schedule.local"
    scheduler_dir = tmp_job_agent_root / ".scheduler"
    crontab_store = tmp_job_agent_root / "crontab.txt"
    fake_bin_dir = tmp_job_agent_root / "bin"
    _write_executable(fake_bin_dir / "codex", "#!/bin/bash\nexit 0\n")

    _write_executable(
        fake_bin_dir / "crontab",
        """#!/bin/bash
set -euo pipefail
STORE="${FAKE_CRONTAB_STORE:?missing FAKE_CRONTAB_STORE}"
if [[ "${1:-}" == "-l" ]]; then
  if [[ -f "$STORE" ]]; then
    cat "$STORE"
    exit 0
  fi
  exit 1
fi
cp "$1" "$STORE"
""",
    )

    env = os.environ | {
        "HOME": str(tmp_job_agent_root / "home"),
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_ENV_FILE": str(env_file),
        "JOB_AGENT_SCHEDULE_FILE": str(schedule_file),
        "JOB_AGENT_SCHEDULER_DIR": str(scheduler_dir),
        "CRONTAB_BIN": str(fake_bin_dir / "crontab"),
        "FAKE_CRONTAB_STORE": str(crontab_store),
        "PATH": f"{fake_bin_dir}:{os.environ['PATH']}",
    }

    first = run_cmd("bash", str(repo_root / "scripts" / "install_scheduler.sh"), env=env, cwd=repo_root)
    second = run_cmd("bash", str(repo_root / "scripts" / "install_scheduler.sh"), env=env, cwd=repo_root)
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr

    cron_text = crontab_store.read_text()
    assert cron_text.count("# BEGIN jobsearch scheduler") == 1
    assert cron_text.count("/scripts/run_scheduled_jobs.sh") == 1
