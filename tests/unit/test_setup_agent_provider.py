from __future__ import annotations

from pathlib import Path

import pytest

import agent_provider


@pytest.mark.parametrize(
    ("provider", "role", "model", "reasoning"),
    [
        ("codex", "setup_coordinator", "gpt-5.5", "medium"),
        ("codex", "source_discovery", "gpt-5.4-mini", "low"),
        ("codex", "preview_ranker", "gpt-5.4-mini", "low"),
        ("claude", "setup_coordinator", "sonnet", None),
        ("claude", "source_discovery", "claude-haiku-4-5", None),
        ("claude", "preview_ranker", "claude-haiku-4-5", None),
        ("gemini", "setup_coordinator", "gemini-3-pro-preview", None),
        ("gemini", "source_discovery", "gemini-3-flash-preview", None),
        ("gemini", "preview_ranker", "gemini-3-flash-preview", None),
    ],
)
def test_setup_policy_defaults_cover_exactly_three_roles(
    provider: str, role: str, model: str, reasoning: str | None
) -> None:
    policy = agent_provider.resolve_setup_policy(provider, role, env={})
    assert policy.model == model
    assert policy.reasoning == reasoning
    assert tuple(agent_provider.SETUP_MODEL_DEFAULTS[provider]) == agent_provider.SETUP_ROLES


def test_setup_policy_precedence_and_coordinator_compatibility_aliases() -> None:
    env = {
        "JOB_AGENT_CODEX_PREVIEW_RANKER_MODEL": "env-preview",
        "JOB_AGENT_CODEX_PREVIEW_RANKER_REASONING_EFFORT": "high",
    }
    policy = agent_provider.resolve_setup_policy("codex", "preview_ranker", env=env)
    assert (policy.model, policy.reasoning) == ("env-preview", "high")
    explicit = agent_provider.resolve_setup_policy(
        "codex", "preview_ranker", model="explicit-preview", reasoning="none", env=env
    )
    assert (explicit.model, explicit.reasoning) == ("explicit-preview", "none")

    coordinator = agent_provider.resolve_setup_policy(
        "codex",
        "setup_coordinator",
        env={"JOB_AGENT_CODEX_SETUP_MODEL": "legacy-model", "JOB_AGENT_CODEX_SETUP_REASONING_EFFORT": "xhigh"},
    )
    assert (coordinator.model, coordinator.reasoning) == ("legacy-model", "xhigh")
    claude = agent_provider.resolve_setup_policy(
        "claude", "setup_coordinator", env={"JOB_AGENT_CLAUDE_SETUP_MODEL": "claude-custom"}
    )
    gemini = agent_provider.resolve_setup_policy(
        "gemini", "setup_coordinator", env={"JOB_AGENT_GEMINI_SETUP_MODEL": "gemini-custom"}
    )
    assert claude.model == "claude-custom"
    assert gemini.model == "gemini-custom"


def test_setup_policy_rejects_invalid_overrides() -> None:
    with pytest.raises(ValueError, match="invalid model"):
        agent_provider.resolve_setup_policy("codex", "preview_ranker", model="bad model", env={})
    with pytest.raises(ValueError, match="only for codex"):
        agent_provider.resolve_setup_policy("claude", "preview_ranker", reasoning="low", env={})
    with pytest.raises(ValueError, match="setup role"):
        agent_provider.resolve_setup_policy("codex", "scheduled_ranker", env={})
    with pytest.raises(ValueError, match="invalid model"):
        agent_provider.resolve_setup_policy(
            "codex", "preview_ranker", env={"JOB_AGENT_CODEX_PREVIEW_RANKER_MODEL": ""}
        )


def test_codex_worker_commands_enforce_fresh_read_only_and_web_boundaries(tmp_path: Path) -> None:
    agent_bin = Path("/opt/bin/codex")
    source = agent_provider.resolve_setup_policy("codex", "source_discovery", env={})
    preview = agent_provider.resolve_setup_policy("codex", "preview_ranker", env={})
    source_command = agent_provider.build_setup_worker_command(
        source,
        tmp_path,
        agent_bin,
        final_output_path=tmp_path / "final.json",
        schema_path=tmp_path / "schema.json",
    )
    preview_command = agent_provider.build_setup_worker_command(
        preview,
        tmp_path,
        agent_bin,
        final_output_path=tmp_path / "final.json",
        schema_path=tmp_path / "schema.json",
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
    claude_source = agent_provider.resolve_setup_policy("claude", "source_discovery", env={})
    claude_preview = agent_provider.resolve_setup_policy("claude", "preview_ranker", env={})
    source_command = agent_provider.build_setup_worker_command(
        claude_source,
        tmp_path,
        Path("/opt/bin/claude"),
        final_output_path=tmp_path / "final.json",
        schema_path=tmp_path / "schema.json",
        env={},
    )
    preview_command = agent_provider.build_setup_worker_command(
        claude_preview,
        tmp_path,
        Path("/opt/bin/claude"),
        final_output_path=tmp_path / "final.json",
        schema_path=tmp_path / "schema.json",
        env={},
    )
    assert "--no-session-persistence" in source_command
    assert source_command[source_command.index("--allowedTools") + 1] == "WebSearch,WebFetch"
    assert preview_command[preview_command.index("--allowedTools") + 1] == ""
    assert not any(tool in preview_command for tool in ("WebSearch", "WebFetch", "Bash", "Write", "Edit"))

    for role in ("source_discovery", "preview_ranker"):
        policy = agent_provider.resolve_setup_policy("gemini", role, env={})
        command = agent_provider.build_setup_worker_command(
            policy,
            tmp_path,
            Path("/opt/bin/gemini"),
            final_output_path=tmp_path / "final.json",
            schema_path=tmp_path / "schema.json",
        )
        assert command[command.index("--approval-mode") + 1] == "plan"
        assert command[command.index("--output-format") + 1] == "json"


def test_setup_coordinator_does_not_receive_routine_web_flags(tmp_path: Path) -> None:
    codex = agent_provider.build_setup_coordinator_command(
        agent_provider.resolve_setup_policy("codex", "setup_coordinator", env={}),
        tmp_path,
        Path("/opt/bin/codex"),
        env={},
    )
    claude = agent_provider.build_setup_coordinator_command(
        agent_provider.resolve_setup_policy("claude", "setup_coordinator", env={}),
        tmp_path,
        Path("/opt/bin/claude"),
        env={},
    )
    assert "--search" not in codex
    assert "WebSearch" not in claude[claude.index("--allowedTools") + 1]
    assert "WebFetch" not in claude[claude.index("--allowedTools") + 1]


def test_existing_reviewer_and_coder_commands_keep_their_legacy_defaults(tmp_path: Path) -> None:
    reviewer = agent_provider.build_reviewer_command("codex", tmp_path, Path("/opt/bin/codex"))
    coder = agent_provider.build_coder_command(
        "codex", tmp_path, Path("/opt/bin/codex"), tmp_path / "last-message.txt"
    )
    assert 'model_reasoning_effort="low"' in reviewer
    assert "-m" not in reviewer
    assert "-m" not in coder
    assert "workspace-write" in coder
