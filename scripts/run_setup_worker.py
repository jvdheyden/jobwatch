#!/usr/bin/env python3
"""Run one fresh, bounded setup worker and atomically persist validated JSON."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from agent_provider import (
    SETUP_ROLES,
    build_setup_worker_command,
    resolve_agent_bin,
    resolve_agent_provider,
    resolve_setup_policy,
)
from runtime_env import RuntimeEnvError, apply_runtime_env
from setup_contracts import (
    PROVIDER_RESPONSE_MAX_BYTES,
    SetupContractError,
    build_worker_prompt,
    load_preview_context,
    load_setup,
    normalize_preview_result,
    normalize_source_pack,
    render_source_pack_summary,
    worker_json_schema,
    write_preview_result,
    write_source_pack,
)


WORKER_ROLES = tuple(role for role in SETUP_ROLES if role != "setup_coordinator")
DEFAULT_TIMEOUT_SECONDS = 900


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", required=True, choices=WORKER_ROLES)
    parser.add_argument("--input", required=True, help="Validated setup or preview-context JSON")
    parser.add_argument("--output", required=True, help="Destination source-pack or preview-result JSON")
    parser.add_argument("--provider", choices=("codex", "claude", "gemini"))
    parser.add_argument("--agent-bin", help="Explicit provider executable")
    parser.add_argument("--model", help="Explicit model override for this invocation")
    parser.add_argument("--reasoning", help="Explicit Codex reasoning override")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    return parser


def _provider_payload(stdout: bytes) -> dict[str, Any]:
    if len(stdout) > PROVIDER_RESPONSE_MAX_BYTES:
        raise SetupContractError("provider response exceeds the 1 MiB limit")
    try:
        envelope = json.loads(stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SetupContractError("provider returned prose or malformed JSON") from exc
    if not isinstance(envelope, dict):
        raise SetupContractError("provider response must be a JSON object")
    if envelope.get("kind") in {"jobwatch_source_pack", "jobwatch_preview_result"}:
        return envelope
    for key in ("result", "response", "output", "text"):
        nested = envelope.get(key)
        if isinstance(nested, dict):
            return nested
        if isinstance(nested, str):
            try:
                payload = json.loads(nested)
            except json.JSONDecodeError as exc:
                raise SetupContractError(f"provider field {key!r} contained prose or malformed JSON") from exc
            if not isinstance(payload, dict):
                raise SetupContractError(f"provider field {key!r} must contain a JSON object")
            return payload
    raise SetupContractError("provider JSON envelope does not contain a final result")


def _read_final_message(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SetupContractError("Codex did not write its final JSON result") from exc
    return _provider_payload(raw)


def _worker_environment(provider: str) -> dict[str, str]:
    env = dict(os.environ)
    for key in (
        "CODEX_THREAD_ID",
        "CLAUDE_SESSION_ID",
        "CLAUDE_CODE_REMOTE_SESSION_ID",
        "JOB_AGENT_SMTP_PASSWORD",
        "JOB_AGENT_TELEGRAM_BOT_TOKEN",
    ):
        env.pop(key, None)
    if provider == "gemini":
        env["GEMINI_SANDBOX"] = "true"
    return env


def run_worker(
    *,
    role: str,
    input_path: Path,
    output_path: Path,
    provider: str | None,
    agent_bin_value: str | None,
    model: str | None,
    reasoning: str | None,
    timeout_seconds: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if timeout_seconds <= 0:
        raise SetupContractError("timeout must be positive")
    input_payload = load_setup(input_path) if role == "source_discovery" else load_preview_context(input_path)
    resolved_provider = resolve_agent_provider(provider)
    policy = resolve_setup_policy(
        resolved_provider,
        role,
        model=model,
        reasoning=reasoning,
    )
    agent_bin = resolve_agent_bin(agent_bin_value, provider=resolved_provider)
    if agent_bin is None:
        raise SetupContractError(f"could not find executable for {resolved_provider}")
    if not agent_bin.is_file() or not os.access(agent_bin, os.X_OK):
        raise SetupContractError(f"provider executable is not executable: {agent_bin}")
    agent_bin = agent_bin.resolve()

    prompt = build_worker_prompt(role, input_payload)
    with tempfile.TemporaryDirectory(prefix=f"jobwatch-{role}-") as temp_dir_value:
        temp_dir = Path(temp_dir_value)
        final_output_path = temp_dir / "final.json"
        schema_path = temp_dir / "output-schema.json"
        schema_path.write_text(json.dumps(worker_json_schema(role, input_payload), separators=(",", ":")) + "\n")
        command = build_setup_worker_command(
            policy,
            temp_dir,
            agent_bin,
            final_output_path=final_output_path,
            schema_path=schema_path,
        )
        try:
            completed = subprocess.run(
                command,
                input=prompt.encode("utf-8"),
                capture_output=True,
                cwd=temp_dir,
                env=_worker_environment(resolved_provider),
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise SetupContractError(f"{role} worker timed out after {timeout_seconds}s") from exc
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()[-2000:]
            raise SetupContractError(
                f"{resolved_provider} {role} worker exited with {completed.returncode}: {detail or 'no error output'}"
            )
        raw_payload = (
            _read_final_message(final_output_path)
            if resolved_provider == "codex"
            else _provider_payload(completed.stdout)
        )

    if role == "source_discovery":
        normalized = normalize_source_pack(raw_payload, input_payload)
        write_source_pack(output_path, normalized, input_payload)
    else:
        normalized = normalize_preview_result(raw_payload, input_payload)
        write_preview_result(output_path, normalized, input_payload)
    status = {
        "status": "written",
        "role": role,
        "provider": policy.provider,
        "model": policy.model,
        "reasoning": policy.reasoning,
        "output": str(output_path),
    }
    return normalized, status


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        apply_runtime_env(load_secrets=False)
        payload, status = run_worker(
            role=args.role,
            input_path=Path(args.input),
            output_path=Path(args.output),
            provider=args.provider,
            agent_bin_value=args.agent_bin,
            model=args.model,
            reasoning=args.reasoning,
            timeout_seconds=args.timeout_seconds,
        )
        if args.role == "source_discovery":
            setup = load_setup(Path(args.input))
            print(render_source_pack_summary(payload, setup), end="")
            print(json.dumps(status), file=sys.stderr)
        else:
            print(json.dumps(status))
        return 0
    except (OSError, RuntimeEnvError, SetupContractError, ValueError) as exc:
        print(f"run_setup_worker.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
