from __future__ import annotations

from collections.abc import Mapping, MutableMapping
import os
from pathlib import Path
import subprocess


class RuntimeEnvError(RuntimeError):
    """Raised when runtime env loading fails."""


def resolve_runtime_env(
    base_env: Mapping[str, str] | None = None,
    *,
    load_secrets: bool = False,
) -> dict[str, str]:
    env = dict(os.environ if base_env is None else base_env)
    loader_path = Path(__file__).with_name("load_runtime_env.sh")
    command = ['source "$1"', "shift", 'job_agent_emit_runtime_env "$@"']
    args = ["/bin/bash", "-lc", "; ".join(command), "bash", str(loader_path)]
    if load_secrets:
        args.append("--with-secrets")

    completed = subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=False,
        env=env,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        if not detail:
            detail = "failed to load runtime environment"
        raise RuntimeEnvError(detail)
    return _parse_env_output(completed.stdout)


def apply_runtime_env(
    env: MutableMapping[str, str] | None = None,
    *,
    load_secrets: bool = False,
) -> dict[str, str]:
    target = os.environ if env is None else env
    resolved = resolve_runtime_env(target, load_secrets=load_secrets)
    target.clear()
    target.update(resolved)
    return resolved


def _parse_env_output(raw: bytes) -> dict[str, str]:
    env: dict[str, str] = {}
    for item in raw.split(b"\0"):
        if not item:
            continue
        name, separator, value = item.partition(b"=")
        if not separator:
            continue
        env[name.decode("utf-8", errors="replace")] = value.decode("utf-8", errors="replace")
    return env
