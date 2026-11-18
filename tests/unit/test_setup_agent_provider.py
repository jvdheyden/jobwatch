from __future__ import annotations

import json
from pathlib import Path

import pytest

import agent_provider


@pytest.mark.parametrize("provider", ["codex", "claude", "gemini"])
@pytest.mark.parametrize(
    ("role", "tier", "effort"),
    [
        ("setup_coordinator", "workhorse-latest", "medium"),
        ("source_discovery", "workhorse-latest", "medium"),
        ("preview_ranker", "workhorse-latest", "medium"),
        ("scheduled", "workhorse-latest", "medium"),
        ("reviewer", "frontier-latest", "high"),
        ("coder", "workhorse-latest", "medium"),
    ],
)
def test_default_model_tier_and_reasoning_by_role(provider, role, tier, effort):
    policy = agent_provider.resolve_model_policy(provider, role, env={})
    assert policy.tier == tier
    assert policy.reasoning == (None if provider == "gemini" else effort)


@pytest.mark.parametrize(
    ("provider", "frontier", "workhorse", "cheapo"),
    [
        ("codex", "gpt-6.2-astra", "gpt-6.2-sol", "gpt-6-luna"),
        ("claude", "opus", "sonnet", "haiku"),
        ("gemini", "pro", "flash", "flash-lite"),
    ],
)
def test_tier_overrides_resolve_models_and_preserve_role_reasoning(provider, frontier, workhorse, cheapo):
    for tier, expected in (
        ("frontier-latest", frontier),
        ("workhorse-latest", workhorse),
        ("cheapo-latest", cheapo),
    ):
        policy = agent_provider.resolve_model_policy(
            provider, "reviewer", env={"JOB_AGENT_REVIEWER_TIER": tier}
        )
        assert (policy.tier, policy.model) == (tier, expected)
        assert policy.reasoning == (None if provider == "gemini" else "high")


def test_explicit_model_and_reasoning_overrides_take_precedence():
    env = {
        "JOB_AGENT_PREVIEW_RANKER_TIER": "cheapo-latest",
        "JOB_AGENT_CODEX_PREVIEW_RANKER_MODEL": "env-preview",
        "JOB_AGENT_CODEX_PREVIEW_RANKER_REASONING_EFFORT": "high",
    }
    policy = agent_provider.resolve_model_policy("codex", "preview_ranker", env=env)
    assert (policy.tier, policy.model, policy.reasoning) == (None, "env-preview", "high")
    explicit = agent_provider.resolve_model_policy(
        "codex", "preview_ranker", model="explicit-preview", reasoning="none", env=env
    )
    assert (explicit.tier, explicit.model, explicit.reasoning) == (None, "explicit-preview", "none")


@pytest.mark.parametrize("provider", ["codex", "claude", "gemini"])
def test_setup_coordinator_legacy_model_alias(provider):
    prefix = f"JOB_AGENT_{provider.upper()}_SETUP"
    env = {
        "JOB_AGENT_SETUP_COORDINATOR_TIER": "cheapo-latest",
        f"{prefix}_MODEL": "legacy-model",
    }
    policy = agent_provider.resolve_model_policy(provider, "setup_coordinator", env=env)
    assert (policy.tier, policy.model) == (None, "legacy-model")
    env[f"{prefix}_COORDINATOR_MODEL"] = "role-specific-model"
    policy = agent_provider.resolve_model_policy(provider, "setup_coordinator", env=env)
    assert policy.model == "role-specific-model"


def test_codex_coordinator_legacy_reasoning_alias():
    env = {"JOB_AGENT_CODEX_SETUP_REASONING_EFFORT": " xhigh "}
    policy = agent_provider.resolve_model_policy("codex", "setup_coordinator", env=env)
    assert policy.reasoning == "xhigh"
    env["JOB_AGENT_CODEX_SETUP_COORDINATOR_REASONING_EFFORT"] = "low"
    policy = agent_provider.resolve_model_policy("codex", "setup_coordinator", env=env)
    assert policy.reasoning == "low"


@pytest.mark.parametrize(("provider", "variable"), [("claude", "ANTHROPIC_MODEL"), ("gemini", "GEMINI_MODEL")])
def test_native_explicit_model_environment_for_previously_implicit_roles(provider, variable):
    env = {variable: "custom-model", "JOB_AGENT_SCHEDULED_TIER": "cheapo-latest"}
    policy = agent_provider.resolve_model_policy(provider, "scheduled", env=env)
    assert (policy.tier, policy.model) == (None, "custom-model")
    policy = agent_provider.resolve_model_policy(provider, "preview_ranker", env=env)
    assert policy.tier == "workhorse-latest"


def test_claude_reasoning_preserves_native_precedence():
    policy = agent_provider.resolve_model_policy(
        "claude", "coder", reasoning="low", env={"CLAUDE_CODE_EFFORT_LEVEL": "auto"}
    )
    assert policy.reasoning == "auto"
    assert "--effort" not in agent_provider.model_args(policy)
    policy = agent_provider.resolve_model_policy(
        "claude", "coder", env={"JOB_AGENT_CLAUDE_CODER_REASONING_EFFORT": "xhigh"}
    )
    assert agent_provider.model_args(policy) == ["--model", "sonnet", "--effort", "xhigh"]


@pytest.mark.parametrize(
    ("provider", "key", "value"),
    [
        ("codex", "JOB_AGENT_PREVIEW_RANKER_TIER", "cheap"),
        ("gemini", "JOB_AGENT_PREVIEW_RANKER_TIER", ""),
        ("codex", "JOB_AGENT_CODEX_PREVIEW_RANKER_MODEL", ""),
        ("codex", "JOB_AGENT_CODEX_PREVIEW_RANKER_MODEL", "bad model"),
        ("claude", "JOB_AGENT_CLAUDE_PREVIEW_RANKER_MODEL", "cheapo-latest"),
        ("codex", "JOB_AGENT_CODEX_PREVIEW_RANKER_REASONING_EFFORT", "maximum"),
        ("claude", "JOB_AGENT_CLAUDE_PREVIEW_RANKER_REASONING_EFFORT", "none"),
        ("gemini", "JOB_AGENT_GEMINI_PREVIEW_RANKER_REASONING_EFFORT", "low"),
    ],
)
def test_invalid_agent_model_configuration_names_the_setting(provider, key, value):
    with pytest.raises(ValueError, match=key):
        agent_provider.resolve_model_policy(provider, "preview_ranker", env={key: value})


def test_codex_worker_commands_enforce_fresh_read_only_and_web_boundaries(tmp_path: Path) -> None:
    agent_bin = Path("/opt/bin/codex")
    source = agent_provider.resolve_model_policy("codex", "source_discovery", env={})
    preview = agent_provider.resolve_model_policy("codex", "preview_ranker", env={})
    source_command = agent_provider.build_setup_worker_command(
        source,
        tmp_path,
        agent_bin,
        final_output_path=tmp_path / "final.json",
        schema_path=tmp_path / "schema.json",
        schema={"type": "object"},
    )
    preview_command = agent_provider.build_setup_worker_command(
        preview,
        tmp_path,
        agent_bin,
        final_output_path=tmp_path / "final.json",
        schema_path=tmp_path / "schema.json",
        schema={"type": "object"},
    )
    assert "--search" in source_command
    assert "--search" not in preview_command
    for command in (source_command, preview_command):
        assert "--ephemeral" in command
        assert "--ignore-user-config" in command
        assert command[command.index("-s") + 1] == "read-only"
        assert "--output-schema" in command
        assert "--output-last-message" in command


def test_claude_and_gemini_worker_commands_are_read_only_and_role_scoped(tmp_path: Path) -> None:
    claude_source = agent_provider.resolve_model_policy("claude", "source_discovery", env={})
    claude_preview = agent_provider.resolve_model_policy("claude", "preview_ranker", env={})
    schema = {"type": "object", "required": ["recommended_sources"]}
    source_command = agent_provider.build_setup_worker_command(
        claude_source,
        tmp_path,
        Path("/opt/bin/claude"),
        final_output_path=tmp_path / "final.json",
        schema_path=tmp_path / "schema.json",
        schema=schema,
        env={},
    )
    preview_command = agent_provider.build_setup_worker_command(
        claude_preview,
        tmp_path,
        Path("/opt/bin/claude"),
        final_output_path=tmp_path / "final.json",
        schema_path=tmp_path / "schema.json",
        schema=schema,
        env={},
    )
    assert "--no-session-persistence" in source_command
    for command in (source_command, preview_command):
        assert json.loads(command[command.index("--json-schema") + 1]) == schema
    assert source_command[source_command.index("--allowedTools") + 1] == "WebSearch,WebFetch"
    assert preview_command[preview_command.index("--allowedTools") + 1] == ""
    assert not any(tool in preview_command for tool in ("WebSearch", "WebFetch", "Bash", "Write", "Edit"))

    for role in ("source_discovery", "preview_ranker"):
        policy = agent_provider.resolve_model_policy("gemini", role, env={})
        command = agent_provider.build_setup_worker_command(
            policy,
            tmp_path,
            Path("/opt/bin/gemini"),
            final_output_path=tmp_path / "final.json",
            schema_path=tmp_path / "schema.json",
            schema={"type": "object"},
        )
        assert command[command.index("--approval-mode") + 1] == "plan"
        assert command[command.index("--output-format") + 1] == "json"


def test_setup_coordinator_does_not_receive_routine_web_flags(tmp_path: Path) -> None:
    codex = agent_provider.build_setup_coordinator_command(
        agent_provider.resolve_model_policy("codex", "setup_coordinator", env={}),
        tmp_path,
        Path("/opt/bin/codex"),
        env={},
    )
    claude = agent_provider.build_setup_coordinator_command(
        agent_provider.resolve_model_policy("claude", "setup_coordinator", env={}),
        tmp_path,
        Path("/opt/bin/claude"),
        env={},
    )
    assert "--search" not in codex
    assert "WebSearch" not in claude[claude.index("--allowedTools") + 1]
    assert "WebFetch" not in claude[claude.index("--allowedTools") + 1]
