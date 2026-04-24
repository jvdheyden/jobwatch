#!/usr/bin/env python3
"""Provider-neutral helpers for invoking coding agents."""

from __future__ import annotations

import os
import shutil
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
