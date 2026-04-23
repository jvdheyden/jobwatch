from __future__ import annotations

import os
from pathlib import Path

import pytest

import runtime_env


def test_resolve_runtime_env_loads_config_without_secrets_when_not_requested(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    env_file = root / ".env.local"
    secrets_file = tmp_path / "jobwatch.secrets.sh"
    env_file.write_text(
        "\n".join(
            [
                f"export JOB_AGENT_ROOT={root}",
                "export JOB_AGENT_PROVIDER=codex",
                f"export JOB_AGENT_SECRETS_FILE={secrets_file}",
                "",
            ]
        )
    )

    resolved = runtime_env.resolve_runtime_env(
        os.environ | {"JOB_AGENT_ENV_FILE": str(env_file)},
        load_secrets=False,
    )

    assert resolved["JOB_AGENT_ROOT"] == str(root)
    assert resolved["JOB_AGENT_PROVIDER"] == "codex"
    assert resolved["JOB_AGENT_SECRETS_FILE"] == str(secrets_file)
    assert "JOB_AGENT_RUNTIME_SECRETS_FILE_LOADED" not in resolved
    assert "JOB_AGENT_SMTP_PASSWORD" not in resolved


def test_resolve_runtime_env_loads_external_secrets_when_requested(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    env_file = root / ".env.local"
    secrets_file = tmp_path / "jobwatch.secrets.sh"
    env_file.write_text(
        "\n".join(
            [
                f"export JOB_AGENT_ROOT={root}",
                f"export JOB_AGENT_SECRETS_FILE={secrets_file}",
                "",
            ]
        )
    )
    secrets_file.write_text("export JOB_AGENT_SMTP_PASSWORD=secret\n")

    resolved = runtime_env.resolve_runtime_env(
        os.environ | {"JOB_AGENT_ENV_FILE": str(env_file)},
        load_secrets=True,
    )

    assert resolved["JOB_AGENT_ROOT"] == str(root)
    assert resolved["JOB_AGENT_SMTP_PASSWORD"] == "secret"
    assert resolved["JOB_AGENT_RUNTIME_SECRETS_FILE_LOADED"] == "1"


def test_resolve_runtime_env_rejects_missing_secrets_file_when_requested(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    env_file = root / ".env.local"
    secrets_file = tmp_path / "missing.secrets.sh"
    env_file.write_text(
        "\n".join(
            [
                f"export JOB_AGENT_ROOT={root}",
                f"export JOB_AGENT_SECRETS_FILE={secrets_file}",
                "",
            ]
        )
    )

    with pytest.raises(runtime_env.RuntimeEnvError, match="JOB_AGENT_SECRETS_FILE does not exist"):
        runtime_env.resolve_runtime_env(
            os.environ | {"JOB_AGENT_ENV_FILE": str(env_file)},
            load_secrets=True,
        )


def test_resolve_runtime_env_rejects_plaintext_password_in_env_file(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    env_file = root / ".env.local"
    env_file.write_text(
        "\n".join(
            [
                f"export JOB_AGENT_ROOT={root}",
                "export JOB_AGENT_SMTP_PASSWORD=secret",
                "",
            ]
        )
    )

    with pytest.raises(runtime_env.RuntimeEnvError, match="JOB_AGENT_SMTP_PASSWORD is no longer supported"):
        runtime_env.resolve_runtime_env(
            os.environ | {"JOB_AGENT_ENV_FILE": str(env_file)},
            load_secrets=False,
        )
