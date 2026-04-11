from __future__ import annotations

import os
import pty
import select
import subprocess
import sys
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
    profile_dir = tmp_job_agent_root / "profile"
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
    assert "# Optional: SMTP settings for email delivery." in env_text
    assert "# export JOB_AGENT_SMTP_HOST=smtp.example.com" in env_text
    assert "# export JOB_AGENT_SMTP_PORT=587" in env_text
    assert "# export JOB_AGENT_SMTP_FROM=jobs@example.com" in env_text
    assert "# export JOB_AGENT_SMTP_TO=you@example.com" in env_text
    assert "# export JOB_AGENT_SMTP_USERNAME=jobs@example.com" in env_text
    assert "# export JOB_AGENT_SMTP_PASSWORD=app-password" in env_text
    assert "# export JOB_AGENT_SMTP_TLS=starttls" in env_text
    assert (profile_dir / "cv.md").exists()
    assert (profile_dir / "prefs_global.md").exists()
    assert "JOB_AGENT_PROFILE_TEMPLATE: cv.md" in (profile_dir / "cv.md").read_text()
    assert "JOB_AGENT_PROFILE_TEMPLATE: prefs_global.md" in (profile_dir / "prefs_global.md").read_text()
    assert schedule_file.exists()
    schedule_text = schedule_file.read_text()
    assert "# daily HH:MM track <track-slug> [--delivery logseq|email]..." in schedule_text
    assert "# weekly mon HH:MM track <track-slug> [--delivery logseq|email]..." in schedule_text
    assert "# monthly 1 HH:MM track <track-slug> [--delivery logseq|email]..." in schedule_text
    cron_text = (scheduler_dir / "cron.entry").read_text()
    assert cron_text.startswith("# BEGIN jobsearch scheduler\n* * * * * /bin/bash ")
    assert (scheduler_dir / "com.jvdh.jobsearch.scheduler.plist").exists()

    schedule_file.write_text("daily 08:00 track demo\n")

    second = run_cmd("bash", str(repo_root / "scripts" / "setup_machine.sh"), env=env, cwd=repo_root)
    assert second.returncode == 0, second.stderr
    assert schedule_file.read_text() == "daily 08:00 track demo\n"


def test_setup_machine_preserves_existing_profile_files(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    env_file = tmp_job_agent_root / ".env.local"
    schedule_file = tmp_job_agent_root / ".schedule.local"
    scheduler_dir = tmp_job_agent_root / ".scheduler"
    profile_dir = tmp_job_agent_root / "profile"
    fake_bin_dir = tmp_job_agent_root / "bin"
    _write_executable(fake_bin_dir / "codex", "#!/bin/bash\nexit 0\n")
    profile_dir.mkdir(parents=True)
    (profile_dir / "cv.md").write_text("# Existing CV\n\nDo not replace.\n")
    (profile_dir / "prefs_global.md").write_text("# Existing Preferences\n\nDo not replace.\n")

    env = os.environ | {
        "HOME": str(tmp_job_agent_root / "home"),
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_ENV_FILE": str(env_file),
        "JOB_AGENT_SCHEDULE_FILE": str(schedule_file),
        "JOB_AGENT_SCHEDULER_DIR": str(scheduler_dir),
        "PATH": f"{fake_bin_dir}:{os.environ['PATH']}",
    }

    result = run_cmd("bash", str(repo_root / "scripts" / "setup_machine.sh"), env=env, cwd=repo_root)
    assert result.returncode == 0, result.stderr
    assert (profile_dir / "cv.md").read_text() == "# Existing CV\n\nDo not replace.\n"
    assert (profile_dir / "prefs_global.md").read_text() == "# Existing Preferences\n\nDo not replace.\n"


def test_setup_machine_preserves_existing_smtp_values(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    env_file = tmp_job_agent_root / ".env.local"
    schedule_file = tmp_job_agent_root / ".schedule.local"
    scheduler_dir = tmp_job_agent_root / ".scheduler"
    fake_bin_dir = tmp_job_agent_root / "bin"
    _write_executable(fake_bin_dir / "codex", "#!/bin/bash\nexit 0\n")
    env_file.write_text(
        "\n".join(
            [
                "export JOB_AGENT_SMTP_HOST=smtp.test.invalid",
                "export JOB_AGENT_SMTP_PORT=2525",
                "export JOB_AGENT_SMTP_FROM=jobs@test.invalid",
                "export JOB_AGENT_SMTP_TO=user@test.invalid",
                "export JOB_AGENT_SMTP_USERNAME=smtp-user",
                "export JOB_AGENT_SMTP_PASSWORD=smtp-secret",
                "export JOB_AGENT_SMTP_TLS=none",
                "",
            ]
        )
    )

    env = os.environ | {
        "HOME": str(tmp_job_agent_root / "home"),
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_ENV_FILE": str(env_file),
        "JOB_AGENT_SCHEDULE_FILE": str(schedule_file),
        "JOB_AGENT_SCHEDULER_DIR": str(scheduler_dir),
        "PATH": f"{fake_bin_dir}:{os.environ['PATH']}",
    }

    result = run_cmd("bash", str(repo_root / "scripts" / "setup_machine.sh"), env=env, cwd=repo_root)
    assert result.returncode == 0, result.stderr

    env_text = env_file.read_text()
    assert "export JOB_AGENT_SMTP_HOST=smtp.test.invalid" in env_text
    assert "export JOB_AGENT_SMTP_PORT=2525" in env_text
    assert "export JOB_AGENT_SMTP_FROM=jobs@test.invalid" in env_text
    assert "export JOB_AGENT_SMTP_TO=user@test.invalid" in env_text
    assert "export JOB_AGENT_SMTP_USERNAME=smtp-user" in env_text
    assert "export JOB_AGENT_SMTP_PASSWORD=smtp-secret" in env_text
    assert "export JOB_AGENT_SMTP_TLS=none" in env_text
    assert "# export JOB_AGENT_SMTP_HOST=smtp.example.com" not in env_text


def test_configure_schedule_creates_daily_entry(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    schedule_file = tmp_job_agent_root / ".schedule.local"

    result = run_cmd(
        sys.executable,
        str(repo_root / "scripts" / "configure_schedule.py"),
        "--track",
        "demo",
        "--cadence",
        "daily",
        "--time",
        "08:00",
        "--schedule-file",
        str(schedule_file),
        cwd=repo_root,
    )

    assert result.returncode == 0, result.stderr
    assert schedule_file.read_text().splitlines()[-1] == "daily 08:00 track demo"


def test_configure_schedule_replaces_track_and_preserves_others(
    tmp_job_agent_root: Path, repo_root: Path, run_cmd
) -> None:
    schedule_file = tmp_job_agent_root / ".schedule.local"
    schedule_file.write_text(
        "\n".join(
            [
                "# existing schedules",
                "daily 08:00 track demo",
                "daily 09:00 track other --delivery email",
                "weekly fri 10:00 track demo --delivery logseq",
                "",
            ]
        )
    )

    result = run_cmd(
        sys.executable,
        str(repo_root / "scripts" / "configure_schedule.py"),
        "--track",
        "demo",
        "--cadence",
        "monthly",
        "--month-day",
        "15",
        "--time",
        "07:30",
        "--delivery",
        "logseq",
        "--delivery",
        "email",
        "--schedule-file",
        str(schedule_file),
        cwd=repo_root,
    )

    assert result.returncode == 0, result.stderr
    assert schedule_file.read_text().splitlines() == [
        "# existing schedules",
        "daily 09:00 track other --delivery email",
        "",
        "monthly 15 07:30 track demo --delivery logseq --delivery email",
    ]


def test_configure_schedule_creates_weekly_entry_with_delivery(
    tmp_job_agent_root: Path, repo_root: Path, run_cmd
) -> None:
    schedule_file = tmp_job_agent_root / ".schedule.local"

    result = run_cmd(
        sys.executable,
        str(repo_root / "scripts" / "configure_schedule.py"),
        "--track",
        "demo",
        "--cadence",
        "weekly",
        "--weekday",
        "mon",
        "--time",
        "08:00",
        "--delivery",
        "email",
        "--schedule-file",
        str(schedule_file),
        cwd=repo_root,
    )

    assert result.returncode == 0, result.stderr
    assert "weekly mon 08:00 track demo --delivery email" in schedule_file.read_text()


def test_configure_schedule_rejects_invalid_weekly_schedule(
    tmp_job_agent_root: Path, repo_root: Path, run_cmd
) -> None:
    schedule_file = tmp_job_agent_root / ".schedule.local"

    result = run_cmd(
        sys.executable,
        str(repo_root / "scripts" / "configure_schedule.py"),
        "--track",
        "demo",
        "--cadence",
        "weekly",
        "--time",
        "08:00",
        "--schedule-file",
        str(schedule_file),
        cwd=repo_root,
    )

    assert result.returncode == 2
    assert "weekly schedules require --weekday" in result.stderr
    assert not schedule_file.exists()


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


def test_setup_machine_generates_bwrap_apparmor_profile_on_linux(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    env_file = tmp_job_agent_root / ".env.local"
    schedule_file = tmp_job_agent_root / ".schedule.local"
    scheduler_dir = tmp_job_agent_root / ".scheduler"
    fake_bin_dir = tmp_job_agent_root / "bin"
    apparmor_profile = scheduler_dir / "bwrap-userns-restrict"
    canonical_bwrap = tmp_job_agent_root / "tools" / "bubblewrap" / "bin" / "bwrap"
    _write_executable(fake_bin_dir / "codex", "#!/bin/bash\nexit 0\n")
    _write_executable(canonical_bwrap, "#!/bin/bash\nexit 0\n")
    _write_symlink(fake_bin_dir / "bwrap", canonical_bwrap)

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

    profile_text = apparmor_profile.read_text()
    assert "abi <abi/4.0>," in profile_text
    assert f"{canonical_bwrap} flags=(unconfined)" in profile_text
    assert "userns create," in profile_text


def test_setup_machine_skips_bwrap_apparmor_profile_on_non_linux(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    env_file = tmp_job_agent_root / ".env.local"
    schedule_file = tmp_job_agent_root / ".schedule.local"
    scheduler_dir = tmp_job_agent_root / ".scheduler"
    fake_bin_dir = tmp_job_agent_root / "bin"
    apparmor_profile = scheduler_dir / "bwrap-userns-restrict"
    _write_executable(fake_bin_dir / "codex", "#!/bin/bash\nexit 0\n")
    _write_executable(fake_bin_dir / "bwrap", "#!/bin/bash\nexit 0\n")

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
    assert not apparmor_profile.exists()


def test_bootstrap_venv_installs_playwright_browser_by_default(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    requirements_file = tmp_job_agent_root / "requirements-dev.txt"
    bootstrap_script = tmp_job_agent_root / "scripts" / "bootstrap_venv.sh"
    log_file = tmp_job_agent_root / "bootstrap.log"
    fake_python = tmp_job_agent_root / "bin" / "python3"

    requirements_file.write_text("pytest==9.0.2\nplaywright==1.58.0\n")
    _write_executable(bootstrap_script, (repo_root / "scripts" / "bootstrap_venv.sh").read_text())
    _write_executable(
        fake_python,
        """#!/bin/bash
set -euo pipefail
LOG="${BOOTSTRAP_LOG:?missing BOOTSTRAP_LOG}"
printf 'base_python %s\\n' "$*" >> "$LOG"
if [[ "${1:-}" == "-m" && "${2:-}" == "venv" ]]; then
  target="${3:?missing venv target}"
  mkdir -p "$target/bin"
  cat > "$target/bin/python" <<'EOF'
#!/bin/bash
set -euo pipefail
printf 'venv_python %s\\n' "$*" >> "${BOOTSTRAP_LOG:?missing BOOTSTRAP_LOG}"
EOF
  chmod +x "$target/bin/python"
fi
""",
    )

    env = os.environ | {
        "BOOTSTRAP_LOG": str(log_file),
        "PYTHON_BIN": str(fake_python),
    }

    result = run_cmd("bash", str(bootstrap_script), env=env, cwd=tmp_job_agent_root)
    assert result.returncode == 0, result.stderr
    assert log_file.read_text().splitlines() == [
        f"base_python -m venv {tmp_job_agent_root / '.venv'}",
        "venv_python -m pip install --upgrade pip",
        f"venv_python -m pip install -r {requirements_file}",
        "venv_python -m playwright install chromium",
    ]
    assert "Chromium: installed via Playwright" in result.stdout


def test_bootstrap_venv_no_chromium_skips_playwright_browser_install(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    requirements_file = tmp_job_agent_root / "requirements-dev.txt"
    bootstrap_script = tmp_job_agent_root / "scripts" / "bootstrap_venv.sh"
    log_file = tmp_job_agent_root / "bootstrap.log"
    fake_python = tmp_job_agent_root / "bin" / "python3"

    requirements_file.write_text("pytest==9.0.2\nplaywright==1.58.0\n")
    _write_executable(bootstrap_script, (repo_root / "scripts" / "bootstrap_venv.sh").read_text())
    _write_executable(
        fake_python,
        """#!/bin/bash
set -euo pipefail
LOG="${BOOTSTRAP_LOG:?missing BOOTSTRAP_LOG}"
printf 'base_python %s\\n' "$*" >> "$LOG"
if [[ "${1:-}" == "-m" && "${2:-}" == "venv" ]]; then
  target="${3:?missing venv target}"
  mkdir -p "$target/bin"
  cat > "$target/bin/python" <<'EOF'
#!/bin/bash
set -euo pipefail
printf 'venv_python %s\\n' "$*" >> "${BOOTSTRAP_LOG:?missing BOOTSTRAP_LOG}"
EOF
  chmod +x "$target/bin/python"
fi
""",
    )

    env = os.environ | {
        "BOOTSTRAP_LOG": str(log_file),
        "PYTHON_BIN": str(fake_python),
    }

    result = run_cmd("bash", str(bootstrap_script), "--no-chromium", env=env, cwd=tmp_job_agent_root)
    assert result.returncode == 0, result.stderr
    assert log_file.read_text().splitlines() == [
        f"base_python -m venv {tmp_job_agent_root / '.venv'}",
        "venv_python -m pip install --upgrade pip",
        f"venv_python -m pip install -r {requirements_file}",
    ]
    assert "Chromium: skipped (--no-chromium)" in result.stdout


def test_bootstrap_machine_runs_setup_and_bootstrap_then_prints_linux_followups(
    tmp_job_agent_root: Path, repo_root: Path, run_cmd
) -> None:
    bootstrap_script = tmp_job_agent_root / "scripts" / "bootstrap_machine.sh"
    setup_script = tmp_job_agent_root / "scripts" / "setup_machine.sh"
    bootstrap_venv_script = tmp_job_agent_root / "scripts" / "bootstrap_venv.sh"
    log_file = tmp_job_agent_root / "bootstrap-machine.log"

    _write_executable(bootstrap_script, (repo_root / "scripts" / "bootstrap_machine.sh").read_text())
    _write_executable(
        setup_script,
        """#!/bin/bash
set -euo pipefail
printf 'setup_machine\\n' >> "${BOOTSTRAP_MACHINE_LOG:?missing BOOTSTRAP_MACHINE_LOG}"
""",
    )
    _write_executable(
        bootstrap_venv_script,
        """#!/bin/bash
set -euo pipefail
printf 'bootstrap_venv\\n' >> "${BOOTSTRAP_MACHINE_LOG:?missing BOOTSTRAP_MACHINE_LOG}"
""",
    )

    env = os.environ | {
        "BOOTSTRAP_MACHINE_LOG": str(log_file),
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_PLATFORM": "Linux",
    }

    result = run_cmd("bash", str(bootstrap_script), env=env, cwd=tmp_job_agent_root)
    assert result.returncode == 0, result.stderr
    assert log_file.read_text().splitlines() == ["setup_machine", "bootstrap_venv"]
    assert (
        f"Bootstrapped machine config, local profile placeholders, and repo-local virtualenv for {tmp_job_agent_root}"
        in result.stdout
    )
    assert "Fill profile/cv.md and profile/prefs_global.md locally" in result.stdout
    assert "Next: ask Codex to set up a search track" in result.stdout
    assert "sudo bash scripts/install_bwrap_apparmor.sh" in result.stdout


def test_bootstrap_machine_omits_linux_only_followup_on_non_linux(
    tmp_job_agent_root: Path, repo_root: Path, run_cmd
) -> None:
    bootstrap_script = tmp_job_agent_root / "scripts" / "bootstrap_machine.sh"
    setup_script = tmp_job_agent_root / "scripts" / "setup_machine.sh"
    bootstrap_venv_script = tmp_job_agent_root / "scripts" / "bootstrap_venv.sh"

    _write_executable(bootstrap_script, (repo_root / "scripts" / "bootstrap_machine.sh").read_text())
    _write_executable(setup_script, "#!/bin/bash\nset -euo pipefail\n")
    _write_executable(bootstrap_venv_script, "#!/bin/bash\nset -euo pipefail\n")

    env = os.environ | {
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_PLATFORM": "Darwin",
    }

    result = run_cmd("bash", str(bootstrap_script), env=env, cwd=tmp_job_agent_root)
    assert result.returncode == 0, result.stderr
    assert "Next: ask Codex to set up a search track" in result.stdout
    assert "install_bwrap_apparmor" not in result.stdout


def test_bootstrap_machine_stops_if_setup_machine_fails(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    bootstrap_script = tmp_job_agent_root / "scripts" / "bootstrap_machine.sh"
    setup_script = tmp_job_agent_root / "scripts" / "setup_machine.sh"
    bootstrap_venv_script = tmp_job_agent_root / "scripts" / "bootstrap_venv.sh"
    log_file = tmp_job_agent_root / "bootstrap-machine.log"

    _write_executable(bootstrap_script, (repo_root / "scripts" / "bootstrap_machine.sh").read_text())
    _write_executable(
        setup_script,
        """#!/bin/bash
set -euo pipefail
printf 'setup_machine\\n' >> "${BOOTSTRAP_MACHINE_LOG:?missing BOOTSTRAP_MACHINE_LOG}"
exit 12
""",
    )
    _write_executable(
        bootstrap_venv_script,
        """#!/bin/bash
set -euo pipefail
printf 'bootstrap_venv\\n' >> "${BOOTSTRAP_MACHINE_LOG:?missing BOOTSTRAP_MACHINE_LOG}"
""",
    )

    env = os.environ | {
        "BOOTSTRAP_MACHINE_LOG": str(log_file),
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
    }

    result = run_cmd("bash", str(bootstrap_script), env=env, cwd=tmp_job_agent_root)
    assert result.returncode == 12
    assert log_file.read_text().splitlines() == ["setup_machine"]


def test_bootstrap_machine_stops_if_bootstrap_venv_fails(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    bootstrap_script = tmp_job_agent_root / "scripts" / "bootstrap_machine.sh"
    setup_script = tmp_job_agent_root / "scripts" / "setup_machine.sh"
    bootstrap_venv_script = tmp_job_agent_root / "scripts" / "bootstrap_venv.sh"
    log_file = tmp_job_agent_root / "bootstrap-machine.log"

    _write_executable(bootstrap_script, (repo_root / "scripts" / "bootstrap_machine.sh").read_text())
    _write_executable(
        setup_script,
        """#!/bin/bash
set -euo pipefail
printf 'setup_machine\\n' >> "${BOOTSTRAP_MACHINE_LOG:?missing BOOTSTRAP_MACHINE_LOG}"
""",
    )
    _write_executable(
        bootstrap_venv_script,
        """#!/bin/bash
set -euo pipefail
printf 'bootstrap_venv\\n' >> "${BOOTSTRAP_MACHINE_LOG:?missing BOOTSTRAP_MACHINE_LOG}"
exit 23
""",
    )

    env = os.environ | {
        "BOOTSTRAP_MACHINE_LOG": str(log_file),
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
    }

    result = run_cmd("bash", str(bootstrap_script), env=env, cwd=tmp_job_agent_root)
    assert result.returncode == 23
    assert log_file.read_text().splitlines() == ["setup_machine", "bootstrap_venv"]


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


def test_run_scheduled_jobs_passes_delivery_options(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    env_file = tmp_job_agent_root / ".env.local"
    schedule_file = tmp_job_agent_root / ".schedule.local"
    env_file.write_text(f"export JOB_AGENT_ROOT={tmp_job_agent_root}\n")
    schedule_file.write_text("daily 08:00 track demo --delivery email --delivery logseq\n")

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

    result = run_cmd("bash", str(repo_root / "scripts" / "run_scheduled_jobs.sh"), env=env, cwd=repo_root)
    assert result.returncode == 0, result.stderr
    assert (tmp_job_agent_root / "invocations.log").read_text().splitlines() == [
        "--track demo --delivery email --delivery logseq"
    ]


def test_run_scheduled_jobs_runs_weekly_only_on_matching_weekday(
    tmp_job_agent_root: Path, repo_root: Path, run_cmd
) -> None:
    env_file = tmp_job_agent_root / ".env.local"
    schedule_file = tmp_job_agent_root / ".schedule.local"
    env_file.write_text(f"export JOB_AGENT_ROOT={tmp_job_agent_root}\n")
    schedule_file.write_text("weekly mon 08:00 track demo --delivery email\n")

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
        "JOB_AGENT_SCHEDULE_WEEKDAY": "mon",
        "JOB_AGENT_SCHEDULE_STAMP": "2030-01-14-08:00",
    }

    first = run_cmd("bash", str(repo_root / "scripts" / "run_scheduled_jobs.sh"), env=env, cwd=repo_root)
    second = run_cmd(
        "bash",
        str(repo_root / "scripts" / "run_scheduled_jobs.sh"),
        env=env | {"JOB_AGENT_SCHEDULE_WEEKDAY": "tue", "JOB_AGENT_SCHEDULE_STAMP": "2030-01-15-08:00"},
        cwd=repo_root,
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert (tmp_job_agent_root / "invocations.log").read_text().splitlines() == ["--track demo --delivery email"]


def test_run_scheduled_jobs_runs_monthly_only_on_matching_day(
    tmp_job_agent_root: Path, repo_root: Path, run_cmd
) -> None:
    env_file = tmp_job_agent_root / ".env.local"
    schedule_file = tmp_job_agent_root / ".schedule.local"
    env_file.write_text(f"export JOB_AGENT_ROOT={tmp_job_agent_root}\n")
    schedule_file.write_text("monthly 15 08:00 track demo --delivery logseq\n")

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
        "JOB_AGENT_SCHEDULE_MONTH_DAY": "15",
        "JOB_AGENT_SCHEDULE_STAMP": "2030-01-15-08:00",
    }

    first = run_cmd("bash", str(repo_root / "scripts" / "run_scheduled_jobs.sh"), env=env, cwd=repo_root)
    second = run_cmd(
        "bash",
        str(repo_root / "scripts" / "run_scheduled_jobs.sh"),
        env=env | {"JOB_AGENT_SCHEDULE_MONTH_DAY": "16", "JOB_AGENT_SCHEDULE_STAMP": "2030-01-16-08:00"},
        cwd=repo_root,
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert (tmp_job_agent_root / "invocations.log").read_text().splitlines() == ["--track demo --delivery logseq"]


def test_run_scheduled_jobs_rejects_invalid_schedule_entry(
    tmp_job_agent_root: Path, repo_root: Path, run_cmd
) -> None:
    env_file = tmp_job_agent_root / ".env.local"
    schedule_file = tmp_job_agent_root / ".schedule.local"
    env_file.write_text(f"export JOB_AGENT_ROOT={tmp_job_agent_root}\n")
    schedule_file.write_text("weekly someday 08:00 track demo\n")

    env = os.environ | {
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_ENV_FILE": str(env_file),
        "JOB_AGENT_SCHEDULE_FILE": str(schedule_file),
        "JOB_AGENT_SCHEDULE_TIME": "08:00",
        "JOB_AGENT_SCHEDULE_WEEKDAY": "mon",
        "JOB_AGENT_SCHEDULE_STAMP": "2030-01-15-08:00",
    }

    result = run_cmd("bash", str(repo_root / "scripts" / "run_scheduled_jobs.sh"), env=env, cwd=repo_root)

    assert result.returncode == 1
    assert "Invalid schedule entry: weekly someday 08:00 track demo" in result.stderr
    assert not (tmp_job_agent_root / "invocations.log").exists()


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


def test_install_bwrap_apparmor_installs_generated_profile(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    env_file = tmp_job_agent_root / ".env.local"
    schedule_file = tmp_job_agent_root / ".schedule.local"
    scheduler_dir = tmp_job_agent_root / ".scheduler"
    fake_bin_dir = tmp_job_agent_root / "bin"
    apparmor_dir = tmp_job_agent_root / "etc" / "apparmor.d"
    parser_log = tmp_job_agent_root / "apparmor_parser.log"
    dest_profile = apparmor_dir / "bwrap-userns-restrict"
    canonical_bwrap = tmp_job_agent_root / "tools" / "bubblewrap" / "bin" / "bwrap"
    _write_executable(fake_bin_dir / "codex", "#!/bin/bash\nexit 0\n")
    _write_executable(canonical_bwrap, "#!/bin/bash\nexit 0\n")
    _write_symlink(fake_bin_dir / "bwrap", canonical_bwrap)
    _write_executable(
        fake_bin_dir / "apparmor_parser",
        f"""#!/bin/bash
set -euo pipefail
echo "$*" >> "{parser_log}"
""",
    )

    env = os.environ | {
        "HOME": str(tmp_job_agent_root / "home"),
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_ENV_FILE": str(env_file),
        "JOB_AGENT_SCHEDULE_FILE": str(schedule_file),
        "JOB_AGENT_SCHEDULER_DIR": str(scheduler_dir),
        "JOB_AGENT_PLATFORM": "Linux",
        "JOB_AGENT_BWRAP_APPARMOR_DEST": str(dest_profile),
        "JOB_AGENT_BWRAP_APPARMOR_REQUIRE_ROOT": "0",
        "APPARMOR_PARSER_BIN": str(fake_bin_dir / "apparmor_parser"),
        "PATH": f"{fake_bin_dir}:{os.environ['PATH']}",
    }

    setup_result = run_cmd("bash", str(repo_root / "scripts" / "setup_machine.sh"), env=env, cwd=repo_root)
    assert setup_result.returncode == 0, setup_result.stderr

    result = run_cmd("bash", str(repo_root / "scripts" / "install_bwrap_apparmor.sh"), env=env, cwd=repo_root)
    assert result.returncode == 0, result.stderr
    assert dest_profile.exists()

    profile_text = dest_profile.read_text()
    assert f"{canonical_bwrap} flags=(unconfined)" in profile_text
    assert "userns create," in profile_text
    assert parser_log.read_text().splitlines() == [f"-r {dest_profile}"]


def test_install_bwrap_apparmor_is_noop_on_non_linux(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    env_file = tmp_job_agent_root / ".env.local"
    schedule_file = tmp_job_agent_root / ".schedule.local"
    scheduler_dir = tmp_job_agent_root / ".scheduler"
    fake_bin_dir = tmp_job_agent_root / "bin"
    dest_profile = tmp_job_agent_root / "etc" / "apparmor.d" / "bwrap-userns-restrict"
    _write_executable(fake_bin_dir / "codex", "#!/bin/bash\nexit 0\n")

    env = os.environ | {
        "HOME": str(tmp_job_agent_root / "home"),
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_ENV_FILE": str(env_file),
        "JOB_AGENT_SCHEDULE_FILE": str(schedule_file),
        "JOB_AGENT_SCHEDULER_DIR": str(scheduler_dir),
        "JOB_AGENT_PLATFORM": "Darwin",
        "JOB_AGENT_BWRAP_APPARMOR_DEST": str(dest_profile),
        "PATH": f"{fake_bin_dir}:{os.environ['PATH']}",
    }

    result = run_cmd("bash", str(repo_root / "scripts" / "install_bwrap_apparmor.sh"), env=env, cwd=repo_root)
    assert result.returncode == 0, result.stderr
    assert "Skipping bwrap AppArmor install on non-Linux platform: Darwin" in result.stdout
    assert not dest_profile.exists()
