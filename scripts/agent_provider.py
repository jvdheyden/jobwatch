#!/usr/bin/env python3
"""Provider-neutral helpers for invoking coding agents."""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


SUPPORTED_PROVIDERS = ("codex", "claude", "gemini")
DEFAULT_PROVIDER = "codex"

DEFAULT_CLAUDE_REVIEWER_ALLOWED_TOOLS = "Read,Glob,Grep,LS"
DEFAULT_CLAUDE_CODER_ALLOWED_TOOLS = "Read,Write,Edit,MultiEdit,Bash,Glob,Grep,LS,TodoWrite"
DEFAULT_CLAUDE_SCHEDULED_ALLOWED_TOOLS = DEFAULT_CLAUDE_CODER_ALLOWED_TOOLS
DEFAULT_CLAUDE_PERMISSION_MODE = "acceptEdits"
DEFAULT_GEMINI_CODER_APPROVAL_MODE = "yolo"
DEFAULT_GEMINI_SCHEDULED_APPROVAL_MODE = DEFAULT_GEMINI_CODER_APPROVAL_MODE
DEFAULT_GEMINI_SETUP_APPROVAL_MODE = "auto_edit"

DEFAULT_CLAUDE_SETUP_ALLOWED_TOOLS = "Read,Write,Edit,MultiEdit,Bash,Glob,Grep,LS,TodoWrite"
DEFAULT_CLAUDE_SOURCE_DISCOVERY_ALLOWED_TOOLS = "WebSearch,WebFetch"
DEFAULT_CLAUDE_PREVIEW_RANKER_ALLOWED_TOOLS = ""
_MODEL_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$")

ROLE_MODEL_TIERS = {
    "setup_coordinator": "workhorse-latest",
    "source_discovery": "workhorse-latest",
    "preview_ranker": "workhorse-latest",
    "scheduled": "workhorse-latest",
    "reviewer": "frontier-latest",
    "coder": "workhorse-latest",
}

# Keep concrete Codex model IDs here. Claude and Gemini resolve their own aliases.
TIER_MODELS = {
    "frontier-latest": {"codex": "gpt-6.2-astra", "claude": "opus", "gemini": "pro"},
    "workhorse-latest": {"codex": "gpt-6.2-sol", "claude": "sonnet", "gemini": "flash"},
    "cheapo-latest": {"codex": "gpt-6-luna", "claude": "haiku", "gemini": "flash-lite"},
}

REASONING_LEVELS = {
    "codex": ("none", "low", "medium", "high", "xhigh"),
    "claude": ("low", "medium", "high", "xhigh", "max"),
}


@dataclass(frozen=True)
class AgentModelPolicy:
    provider: str
    role: str
    tier: str | None
    model: str
    reasoning: str | None

    def describe(self) -> str:
        tier = self.tier or "explicit override"
        reasoning = self.reasoning or "provider-managed"
        return f"Using {self.provider} {self.role} model {self.model} (tier={tier}, reasoning effort={reasoning})"


def resolve_model_policy(
    provider: str | None,
    role: str,
    *,
    model: str | None = None,
    reasoning: str | None = None,
    env: Mapping[str, str] | None = None,
) -> AgentModelPolicy:
    """Resolve a deterministic launch's model and independent reasoning effort."""
    values = os.environ if env is None else env
    provider = resolve_agent_provider(provider, values)
    role = role.strip().lower()
    if role not in ROLE_MODEL_TIERS:
        raise ValueError(f"agent role must be one of: {', '.join(ROLE_MODEL_TIERS)}")

    prefix = f"JOB_AGENT_{provider.upper()}_{role.upper()}"
    model_keys = [f"{prefix}_MODEL"]
    if role == "setup_coordinator":
        model_keys.append(f"JOB_AGENT_{provider.upper()}_SETUP_MODEL")
    if role in {"scheduled", "reviewer", "coder"}:
        # These launches previously inherited explicit provider environment defaults.
        if provider == "claude" and values.get("ANTHROPIC_MODEL"):
            model_keys.append("ANTHROPIC_MODEL")
        elif provider == "gemini" and values.get("GEMINI_MODEL"):
            model_keys.append("GEMINI_MODEL")

    tier = None
    model_key = "--model"
    if model is None:
        model_key = next((key for key in model_keys if key in values), model_keys[0])
        model = values.get(model_key)
    if model is None:
        tier_key = f"JOB_AGENT_{role.upper()}_TIER"
        tier = values.get(tier_key, ROLE_MODEL_TIERS[role]).strip().lower()
        if tier not in TIER_MODELS:
            raise ValueError(f"{tier_key} must be one of: {', '.join(TIER_MODELS)}")
        model = TIER_MODELS[tier].get(provider)
        if model is None:
            raise ValueError(f"no {provider} model configured for tier {tier}")
        model_key = f"{provider} mapping for {tier}"
    model = model.strip()
    identifier = model.removesuffix("[1m]") if provider == "claude" else model
    if not _MODEL_IDENTIFIER_RE.fullmatch(identifier) or identifier.lower() in TIER_MODELS:
        raise ValueError(f"{model_key} contains an invalid model identifier")

    reasoning_keys = [f"{prefix}_REASONING_EFFORT"]
    if provider == "codex" and role == "setup_coordinator":
        reasoning_keys.append("JOB_AGENT_CODEX_SETUP_REASONING_EFFORT")
    reasoning_key = "--reasoning"
    if reasoning is None:
        reasoning_key = next((key for key in reasoning_keys if key in values), reasoning_keys[0])
        reasoning = values.get(reasoning_key)
    if provider == "claude" and values.get("CLAUDE_CODE_EFFORT_LEVEL"):
        # Claude applies its native environment override ahead of --effort.
        reasoning_key = "CLAUDE_CODE_EFFORT_LEVEL"
        reasoning = values[reasoning_key]

    levels = REASONING_LEVELS.get(provider)
    if reasoning is not None:
        if levels is None:
            raise ValueError(f"{reasoning_key} is unsupported for {provider}; configure thinking in the CLI settings")
        reasoning = reasoning.strip().lower()
        if reasoning_key == "CLAUDE_CODE_EFFORT_LEVEL":
            levels += ("auto", "unset")
        if reasoning not in levels:
            raise ValueError(f"{reasoning_key} must be one of: {', '.join(levels)}")
    elif levels is not None:
        reasoning = "high" if role == "reviewer" else "medium"

    return AgentModelPolicy(provider, role, tier, model, reasoning)


def model_args(policy: AgentModelPolicy) -> list[str]:
    if policy.provider == "codex":
        args = ["-m", policy.model]
        if policy.reasoning is not None:
            args.extend(["-c", f'model_reasoning_effort="{policy.reasoning}"'])
        return args
    args = ["--model", policy.model]
    if policy.provider == "claude" and policy.reasoning in REASONING_LEVELS["claude"]:
        args.extend(["--effort", policy.reasoning])
    return args


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


def build_codex_reviewer_command(policy: AgentModelPolicy, root: Path, agent_bin: Path) -> list[str]:
    return [
        str(agent_bin),
        "--search",
        "-a",
        "never",
        "exec",
        *model_args(policy),
        "-C",
        str(root),
        "-s",
        "read-only",
        "-",
    ]


def build_codex_coder_command(
    policy: AgentModelPolicy, root: Path, agent_bin: Path, last_message_path: Path
) -> list[str]:
    return [
        str(agent_bin),
        "--search",
        "-a",
        "never",
        "exec",
        *model_args(policy),
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
    policy: AgentModelPolicy,
    agent_bin: Path,
    *,
    output_format: str,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    command = [
        str(agent_bin),
        "-p",
        "--no-session-persistence",
        *model_args(policy),
        "--output-format",
        output_format,
        "--permission-mode",
        claude_permission_mode(env),
        "--allowedTools",
        claude_allowed_tools(policy.role, env),
    ]
    if output_format == "stream-json":
        command.append("--verbose")
    return command


def build_gemini_command(
    policy: AgentModelPolicy,
    agent_bin: Path,
    *,
    output_format: str,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    command = [
        str(agent_bin),
        "--skip-trust",
        *model_args(policy),
        "--output-format",
        output_format,
    ]
    approval_mode = gemini_approval_mode(policy.role, env).strip()
    if approval_mode:
        command.extend(["--approval-mode", approval_mode])
    return command


def build_reviewer_command(policy: AgentModelPolicy, root: Path, agent_bin: Path) -> list[str]:
    if policy.provider == "codex":
        return build_codex_reviewer_command(policy, root, agent_bin)
    if policy.provider == "claude":
        return build_claude_print_command(policy, agent_bin, output_format="text")
    if policy.provider == "gemini":
        return build_gemini_command(policy, agent_bin, output_format="text")
    raise ValueError(f"unsupported agent provider: {policy.provider}")


def build_coder_command(
    policy: AgentModelPolicy, root: Path, agent_bin: Path, last_message_path: Path
) -> list[str]:
    if policy.provider == "codex":
        return build_codex_coder_command(policy, root, agent_bin, last_message_path)
    if policy.provider == "claude":
        return build_claude_print_command(policy, agent_bin, output_format="stream-json")
    if policy.provider == "gemini":
        return build_gemini_command(policy, agent_bin, output_format="stream-json")
    raise ValueError(f"unsupported agent provider: {policy.provider}")


def build_codex_setup_worker_command(
    policy: AgentModelPolicy,
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
    command.extend(model_args(policy))
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
    policy: AgentModelPolicy,
    agent_bin: Path,
    *,
    schema: Mapping[str, Any],
    env: Mapping[str, str] | None = None,
) -> list[str]:
    _ = env
    allowed_tools = (
        DEFAULT_CLAUDE_SOURCE_DISCOVERY_ALLOWED_TOOLS
        if policy.role == "source_discovery"
        else DEFAULT_CLAUDE_PREVIEW_RANKER_ALLOWED_TOOLS
    )
    # `claude --json-schema` takes the schema inline and returns the validated
    # object under `structured_output` in the JSON result envelope.
    return [
        str(agent_bin),
        "-p",
        "--no-session-persistence",
        *model_args(policy),
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(schema, separators=(",", ":")),
        "--permission-mode",
        "default",
        "--allowedTools",
        allowed_tools,
    ]


def build_gemini_setup_worker_command(policy: AgentModelPolicy, agent_bin: Path) -> list[str]:
    return [
        str(agent_bin),
        "--skip-trust",
        *model_args(policy),
        "--output-format",
        "json",
        "--approval-mode",
        "plan",
    ]


def build_setup_worker_command(
    policy: AgentModelPolicy,
    workdir: Path,
    agent_bin: Path,
    *,
    final_output_path: Path,
    schema_path: Path,
    schema: Mapping[str, Any],
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
        return build_claude_setup_worker_command(policy, agent_bin, schema=schema, env=env)
    if policy.provider == "gemini":
        return build_gemini_setup_worker_command(policy, agent_bin)
    raise ValueError(f"unsupported agent provider: {policy.provider}")


def build_setup_coordinator_command(
    policy: AgentModelPolicy,
    root: Path,
    agent_bin: Path,
    *,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    if policy.role != "setup_coordinator":
        raise ValueError("setup coordinator command requires setup_coordinator role")
    values = os.environ if env is None else env
    if policy.provider == "codex":
        command = [str(agent_bin), "-a", "never", *model_args(policy)]
        command.extend(["-C", str(root), "-s", "workspace-write"])
        return command
    if policy.provider == "claude":
        return [
            str(agent_bin),
            *model_args(policy),
            "--permission-mode",
            values.get("JOB_AGENT_CLAUDE_PERMISSION_MODE", DEFAULT_CLAUDE_PERMISSION_MODE),
            "--allowedTools",
            values.get("JOB_AGENT_CLAUDE_SETUP_ALLOWED_TOOLS", DEFAULT_CLAUDE_SETUP_ALLOWED_TOOLS),
        ]
    if policy.provider == "gemini":
        return [
            str(agent_bin),
            "--skip-trust",
            *model_args(policy),
            "--approval-mode",
            values.get(
                "JOB_AGENT_GEMINI_SETUP_APPROVAL_MODE",
                values.get("JOB_AGENT_GEMINI_APPROVAL_MODE", "yolo"),
            ),
        ]
    raise ValueError(f"unsupported agent provider: {policy.provider}")
