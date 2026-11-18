from __future__ import annotations

from pathlib import Path
import tomllib

from hooks import install_codex_project_config as config


def test_clean_install_writes_shell_environment_policy(tmp_case_dir: Path) -> None:
    root = tmp_case_dir
    target = root / ".codex" / "config.toml"

    status = config.install(target, root, "/usr/bin:/bin")

    assert status == config.STATUS_INSTALLED
    text = target.read_text(encoding="utf-8")
    assert config.BEGIN_MARKER in text
    policy = tomllib.loads(text)["shell_environment_policy"]
    assert policy["inherit"] == "all"
    assert policy["set"]["PATH"] == f"{root / '.venv' / 'bin'}:/usr/bin:/bin"


def test_idempotent_second_run(tmp_case_dir: Path) -> None:
    root = tmp_case_dir
    target = root / ".codex" / "config.toml"

    config.install(target, root, "/usr/bin:/bin")
    before = target.read_text(encoding="utf-8")

    status = config.install(target, root, "/usr/bin:/bin")

    assert status == config.STATUS_ALREADY_PRESENT
    assert target.read_text(encoding="utf-8") == before


def test_preserves_existing_unrelated_config(tmp_case_dir: Path) -> None:
    root = tmp_case_dir
    target = root / ".codex" / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('model = "gpt-5.4"\n\n[profiles.default]\napproval_policy = "on-request"\n')

    status = config.install(target, root, "/usr/bin:/bin")

    text = target.read_text(encoding="utf-8")
    assert status == config.STATUS_UPDATED
    parsed = tomllib.loads(text)
    assert parsed["model"] == "gpt-5.4"
    assert parsed["profiles"]["default"]["approval_policy"] == "on-request"
    assert parsed["shell_environment_policy"]["inherit"] == "all"


def test_updates_managed_block_when_path_changes(tmp_case_dir: Path) -> None:
    root = tmp_case_dir
    target = root / ".codex" / "config.toml"

    config.install(target, root, "/usr/bin:/bin")

    status = config.install(target, root, "/opt/bin:/usr/bin:/bin")

    text = target.read_text(encoding="utf-8")
    assert status == config.STATUS_UPDATED
    assert tomllib.loads(text)["shell_environment_policy"]["set"]["PATH"] == f"{root / '.venv' / 'bin'}:/opt/bin:/usr/bin:/bin"
    assert text.count(config.BEGIN_MARKER) == 1


def test_unmanaged_shell_environment_policy_is_not_overwritten(tmp_case_dir: Path) -> None:
    root = tmp_case_dir
    target = root / ".codex" / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('[shell_environment_policy]\ninherit = "all"\n')
    before = target.read_text(encoding="utf-8")

    status = config.install(target, root, "/usr/bin:/bin")

    assert status == config.STATUS_CONFLICT
    assert target.read_text(encoding="utf-8") == before


def test_build_path_prepends_and_deduplicates_venv_bin(tmp_case_dir: Path) -> None:
    root = tmp_case_dir
    venv_bin = root / ".venv" / "bin"

    path = config.build_path(root, f"/usr/bin:{venv_bin}:/bin:/usr/bin")

    assert path == f"{venv_bin}:/usr/bin:/bin"
