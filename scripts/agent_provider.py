#!/usr/bin/env python3
"""Provider-neutral helpers for invoking coding agents."""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


SUPPORTED_PROVIDERS = ("codex", "claude", "gemini")
DEFAULT_PROVIDER = "codex"

DEFAULT_CLAUDE_REVIEWER_ALLOWED_TOOLS = "Read,Glob,Grep,LS"
DEFAULT_CLAUDE_CODER_ALLOWED_TOOLS = "Read,Write,Edit,MultiEdit,Bash,Glob,Grep,LS,TodoWrite"
DEFAULT_CLAUDE_SCHEDULED_ALLOWED_TOOLS = DEFAULT_CLAUDE_CODER_ALLOWED_TOOLS
DEFAULT_CLAUDE_PERMISSION_MODE = "acceptEdits"
DEFAULT_GEMINI_CODER_APPROVAL_MODE = "yolo"
DEFAULT_GEMINI_SCHEDULED_APPROVAL_MODE = DEFAULT_GEMINI_CODER_APPROVAL_MODE
DEFAULT_GEMINI_SETUP_APPROVAL_MODE = "auto_edit"

SETUP_ROLES = ("setup_coordinator", "source_discovery", "preview_ranker")
CODEX_SETUP_REASONING_LEVELS = ("none", "low", "medium", "high", "xhigh")
DEFAULT_CLAUDE_SETUP_ALLOWED_TOOLS = "Read,Write,Edit,MultiEdit,Bash,Glob,Grep,LS,TodoWrite"
DEFAULT_CLAUDE_SOURCE_DISCOVERY_ALLOWED_TOOLS = "WebSearch,WebFetch"
DEFAULT_CLAUDE_PREVIEW_RANKER_ALLOWED_TOOLS = ""
_MODEL_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


@dataclass(frozen=True)
class SetupModelPolicy:
    provider: str
    role: str
    model: str
    reasoning: str | None = None


# Setup-only policy. Reviewer, coder, and scheduled ranking defaults remain on
# their existing paths below.
SETUP_MODEL_DEFAULTS: dict[str, dict[str, tuple[str, str | None]]] = {
    "codex": {
        "setup_coordinator": ("gpt-5.5", "medium"),
        "source_discovery": ("gpt-5.4-mini", "low"),
        "preview_ranker": ("gpt-5.4-mini", "low"),
    },
    "claude": {
        "setup_coordinator": ("sonnet", None),
        "source_discovery": ("claude-haiku-4-5", None),
        "preview_ranker": ("claude-haiku-4-5", None),
    },
    "gemini": {
        "setup_coordinator": ("gemini-3-pro-preview", None),
        "source_discovery": ("gemini-3-flash-preview", None),
        "preview_ranker": ("gemini-3-flash-preview", None),
    },
}


def _validate_setup_role(role: str) -> str:
    candidate = role.strip().lower()
    if candidate not in SETUP_ROLES:
        raise ValueError(f"setup role must be one of: {', '.join(SETUP_ROLES)}")
    return candidate


def _validate_model_identifier(model: str, field: str) -> str:
    candidate = model.strip()
    if not _MODEL_IDENTIFIER_RE.fullmatch(candidate):
        raise ValueError(f"{field} contains an invalid model identifier")
    return candidate


def resolve_setup_policy(
    provider: str,
    role: str,
    *,
    model: str | None = None,
    reasoning: str | None = None,
    env: Mapping[str, str] | None = None,
) -> SetupModelPolicy:
    """Resolve explicit args, provider/role env overrides, aliases, then defaults."""

    values = os.environ if env is None else env
    resolved_provider = resolve_agent_provider(provider, values)
    resolved_role = _validate_setup_role(role)
    default_model, default_reasoning = SETUP_MODEL_DEFAULTS[resolved_provider][resolved_role]
    prefix = f"JOB_AGENT_{resolved_provider.upper()}_{resolved_role.upper()}"
    model_key = f"{prefix}_MODEL"
    reasoning_key = f"{prefix}_REASONING_EFFORT"
    configured_model = values[model_key] if model_key in values else None
    configured_reasoning = values[reasoning_key] if reasoning_key in values else None
    if resolved_role == "setup_coordinator" and configured_model is None:
        alias_key = f"JOB_AGENT_{resolved_provider.upper()}_SETUP_MODEL"
        configured_model = values[alias_key] if alias_key in values else None
    if resolved_provider == "codex" and resolved_role == "setup_coordinator" and configured_reasoning is None:
        alias_key = "JOB_AGENT_CODEX_SETUP_REASONING_EFFORT"
        configured_reasoning = values[alias_key] if alias_key in values else None
    selected_model_value = model if model is not None else configured_model if configured_model is not None else default_model
    selected_model = _validate_model_identifier(
        selected_model_value,
        "--model" if model else f"{prefix}_MODEL",
    )
    selected_reasoning = (
        reasoning if reasoning is not None else configured_reasoning if configured_reasoning is not None else default_reasoning
    )
    if selected_reasoning is not None:
        selected_reasoning = selected_reasoning.strip().lower()
        if resolved_provider != "codex":
            raise ValueError("--reasoning and setup reasoning overrides are supported only for codex")
        if selected_reasoning not in CODEX_SETUP_REASONING_LEVELS:
            raise ValueError(
                f"codex setup reasoning must be one of: {', '.join(CODEX_SETUP_REASONING_LEVELS)}"
            )
    return SetupModelPolicy(resolved_provider, resolved_role, selected_model, selected_reasoning)


def resolve_agent_provider(explicit: str | None = None, env: Mapping[str, str] | None = None) -> str:
    values = os.environ if env is None else env
    provider = (explicit or values.get("JOB_AGENT_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        supported = ", ".join(SUPPORTED_PROVIDERS)
        raise ValueError(f"JOB_AGENT_PROVIDER must be one of: {supported}")
    return provider


def default_binary_name(provider: str) -> str:
    if provider == "codex":
        return "codex"
    if provider == "claude":
        return "claude"
    if provider == "gemini":
        return "gemini"
    raise ValueError(f"unsupported agent provider: {provider}")


def _role_env_key(role: str | None) -> str | None:
    if role == "reviewer":
        return "JOB_AGENT_REVIEWER_BIN"
    if role == "coder":
        return "JOB_AGENT_CODER_BIN"
    return None


def resolve_agent_bin(
    explicit: str | None = None,
    *,
    provider: str | None = None,
    role: str | None = None,
    env: Mapping[str, str] | None = None,
) -> Path | None:
    values = os.environ if env is None else env
    resolved_provider = resolve_agent_provider(provider, values)

    if explicit:
        return Path(explicit)

    role_key = _role_env_key(role)
    if role_key:
        role_bin = values.get(role_key)
        if role_bin:
            return Path(role_bin)

    agent_bin = values.get("JOB_AGENT_BIN")
    if agent_bin:
        return Path(agent_bin)

    default_bin = shutil.which(default_binary_name(resolved_provider), path=values.get("PATH"))
    if default_bin:
        return Path(default_bin)
    return None


def claude_permission_mode(env: Mapping[str, str] | None = None) -> str:
    values = os.environ if env is None else env
    return values.get("JOB_AGENT_CLAUDE_PERMISSION_MODE", DEFAULT_CLAUDE_PERMISSION_MODE)


def claude_allowed_tools(role: str, env: Mapping[str, str] | None = None) -> str:
    values = os.environ if env is None else env
    if role == "reviewer":
        return values.get("JOB_AGENT_CLAUDE_REVIEWER_ALLOWED_TOOLS", DEFAULT_CLAUDE_REVIEWER_ALLOWED_TOOLS)
    if role == "scheduled":
        return values.get("JOB_AGENT_CLAUDE_SCHEDULED_ALLOWED_TOOLS", DEFAULT_CLAUDE_SCHEDULED_ALLOWED_TOOLS)
    return values.get("JOB_AGENT_CLAUDE_CODER_ALLOWED_TOOLS", DEFAULT_CLAUDE_CODER_ALLOWED_TOOLS)


def gemini_approval_mode(role: str, env: Mapping[str, str] | None = None) -> str:
    values = os.environ if env is None else env
    if role == "reviewer":
        return values.get("JOB_AGENT_GEMINI_REVIEWER_APPROVAL_MODE", "")
    if role == "scheduled":
        return values.get(
            "JOB_AGENT_GEMINI_SCHEDULED_APPROVAL_MODE",
            values.get("JOB_AGENT_GEMINI_APPROVAL_MODE", DEFAULT_GEMINI_SCHEDULED_APPROVAL_MODE),
        )
    if role == "setup":
        return values.get(
            "JOB_AGENT_GEMINI_SETUP_APPROVAL_MODE",
            values.get("JOB_AGENT_GEMINI_APPROVAL_MODE", DEFAULT_GEMINI_SETUP_APPROVAL_MODE),
        )
    return values.get(
        "JOB_AGENT_GEMINI_CODER_APPROVAL_MODE",
        values.get("JOB_AGENT_GEMINI_APPROVAL_MODE", DEFAULT_GEMINI_CODER_APPROVAL_MODE),
    )


def build_codex_reviewer_command(root: Path, agent_bin: Path) -> list[str]:
    return [
        str(agent_bin),
        "--search",
        "-a",
        "never",
        "exec",
        "-c",
        'model_reasoning_effort="low"',
        "-C",
        str(root),
        "-s",
        "read-only",
        "-",
    ]


def build_codex_coder_command(root: Path, agent_bin: Path, last_message_path: Path) -> list[str]:
    return [
        str(agent_bin),
        "--search",
        "-a",
        "never",
        "exec",
        "-C",
        str(root),
        "-s",
        "workspace-write",
        "--json",
        "--output-last-message",
        str(last_message_path),
        "-",
    ]


def build_claude_print_command(
    agent_bin: Path,
    *,
    role: str,
    output_format: str,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    command = [
        str(agent_bin),
        "-p",
        "--no-session-persistence",
        "--output-format",
        output_format,
        "--permission-mode",
        claude_permission_mode(env),
        "--allowedTools",
        claude_allowed_tools(role, env),
    ]
    if output_format == "stream-json":
        command.append("--verbose")
    return command


def build_gemini_command(
    agent_bin: Path,
    *,
    role: str,
    output_format: str,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    command = [
        str(agent_bin),
        "--skip-trust",
        "--output-format",
        output_format,
    ]
    approval_mode = gemini_approval_mode(role, env).strip()
    if approval_mode:
        command.extend(["--approval-mode", approval_mode])
    return command


def build_reviewer_command(provider: str, root: Path, agent_bin: Path) -> list[str]:
    if provider == "codex":
        return build_codex_reviewer_command(root, agent_bin)
    if provider == "claude":
        return build_claude_print_command(agent_bin, role="reviewer", output_format="text")
    if provider == "gemini":
        return build_gemini_command(agent_bin, role="reviewer", output_format="text")
    raise ValueError(f"unsupported agent provider: {provider}")


def build_coder_command(provider: str, root: Path, agent_bin: Path, last_message_path: Path) -> list[str]:
    if provider == "codex":
        return build_codex_coder_command(root, agent_bin, last_message_path)
    if provider == "claude":
        return build_claude_print_command(agent_bin, role="coder", output_format="stream-json")
    if provider == "gemini":
        return build_gemini_command(agent_bin, role="coder", output_format="stream-json")
    raise ValueError(f"unsupported agent provider: {provider}")


def build_codex_setup_worker_command(
    policy: SetupModelPolicy,
    workdir: Path,
    agent_bin: Path,
    *,
    final_output_path: Path,
    schema_path: Path,
) -> list[str]:
    command = [str(agent_bin)]
    if policy.role == "source_discovery":
        command.append("--search")
    command.extend(["-a", "never", "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules"])
    command.extend(["-m", policy.model])
    if policy.reasoning:
        command.extend(["-c", f'model_reasoning_effort="{policy.reasoning}"'])
    command.extend(
        [
            "-C",
            str(workdir),
            "--skip-git-repo-check",
            "-s",
            "read-only",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(final_output_path),
            "-",
        ]
    )
    return command


def build_claude_setup_worker_command(
    policy: SetupModelPolicy,
    agent_bin: Path,
    *,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    _ = env
    allowed_tools = (
        DEFAULT_CLAUDE_SOURCE_DISCOVERY_ALLOWED_TOOLS
        if policy.role == "source_discovery"
        else DEFAULT_CLAUDE_PREVIEW_RANKER_ALLOWED_TOOLS
    )
    return [
        str(agent_bin),
        "-p",
        "--no-session-persistence",
        "--model",
        policy.model,
        "--output-format",
        "json",
        "--permission-mode",
        "default",
        "--allowedTools",
        allowed_tools,
    ]


def build_gemini_setup_worker_command(policy: SetupModelPolicy, agent_bin: Path) -> list[str]:
    return [
        str(agent_bin),
        "--skip-trust",
        "--model",
        policy.model,
        "--output-format",
        "json",
        "--approval-mode",
        "plan",
    ]


def build_setup_worker_command(
    policy: SetupModelPolicy,
    workdir: Path,
    agent_bin: Path,
    *,
    final_output_path: Path,
    schema_path: Path,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    if policy.role not in {"source_discovery", "preview_ranker"}:
        raise ValueError("setup worker command requires source_discovery or preview_ranker")
    if policy.provider == "codex":
        return build_codex_setup_worker_command(
            policy,
            workdir,
            agent_bin,
            final_output_path=final_output_path,
            schema_path=schema_path,
        )
    if policy.provider == "claude":
        return build_claude_setup_worker_command(policy, agent_bin, env=env)
    if policy.provider == "gemini":
        return build_gemini_setup_worker_command(policy, agent_bin)
    raise ValueError(f"unsupported agent provider: {policy.provider}")


def build_setup_coordinator_command(
    policy: SetupModelPolicy,
    root: Path,
    agent_bin: Path,
    *,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    if policy.role != "setup_coordinator":
        raise ValueError("setup coordinator command requires setup_coordinator role")
    values = os.environ if env is None else env
    if policy.provider == "codex":
        command = [str(agent_bin), "-a", "never", "-m", policy.model]
        if policy.reasoning:
            command.extend(["-c", f'model_reasoning_effort="{policy.reasoning}"'])
        command.extend(["-C", str(root), "-s", "workspace-write"])
        return command
    if policy.provider == "claude":
        return [
            str(agent_bin),
            "--model",
            policy.model,
            "--permission-mode",
            values.get("JOB_AGENT_CLAUDE_PERMISSION_MODE", DEFAULT_CLAUDE_PERMISSION_MODE),
            "--allowedTools",
            values.get("JOB_AGENT_CLAUDE_SETUP_ALLOWED_TOOLS", DEFAULT_CLAUDE_SETUP_ALLOWED_TOOLS),
        ]
    if policy.provider == "gemini":
        return [
            str(agent_bin),
            "--skip-trust",
            "--model",
            policy.model,
            "--approval-mode",
            values.get(
                "JOB_AGENT_GEMINI_SETUP_APPROVAL_MODE",
                values.get("JOB_AGENT_GEMINI_APPROVAL_MODE", "yolo"),
            ),
        ]
    raise ValueError(f"unsupported agent provider: {policy.provider}")
