#!/usr/bin/env python3
"""Run deterministic discovery plus the bounded first-preview ranking pipeline."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

from runtime_env import RuntimeEnvError, apply_runtime_env
from run_setup_worker import DEFAULT_TIMEOUT_SECONDS, run_worker
from setup_contracts import (
    SetupContractError,
    assemble_preview_digest,
    build_preview_context,
    load_setup,
    write_json_atomic,
    write_preview_context,
)


SCRIPT_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--setup", required=True, help="Validated setup.json used to scaffold the track")
    parser.add_argument("--today", default=date.today().isoformat())
    parser.add_argument("--provider", choices=("codex", "claude", "gemini"))
    parser.add_argument("--agent-bin")
    parser.add_argument("--model", help="Explicit preview-ranker model override")
    parser.add_argument("--reasoning", help="Explicit Codex preview-ranker reasoning override")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--discovery-timeout-seconds", type=int, default=900)
    parser.add_argument("--root", help=argparse.SUPPRESS)
    parser.add_argument("--discovery-artifact", help=argparse.SUPPRESS)
    return parser


def _run(command: list[str], *, env: dict[str, str], timeout: int, label: str) -> None:
    try:
        completed = subprocess.run(
            command,
            cwd=SCRIPT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SetupContractError(f"{label} timed out after {timeout}s") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-3000:]
        raise SetupContractError(f"{label} failed with status {completed.returncode}: {detail}")


def run_first_preview(
    setup_path: Path,
    *,
    root: Path,
    today: str,
    provider: str | None,
    agent_bin: str | None,
    model: str | None,
    reasoning: str | None,
    worker_timeout_seconds: int,
    discovery_timeout_seconds: int,
    discovery_artifact: Path | None = None,
) -> dict[str, Any]:
    try:
        stamp = date.fromisoformat(today).isoformat()
    except ValueError as exc:
        raise SetupContractError("--today must use YYYY-MM-DD") from exc
    setup = load_setup(setup_path)
    track = setup["track"]["slug"]
    track_dir = root / "tracks" / track
    if not track_dir.is_dir():
        raise SetupContractError(f"scaffolded track does not exist: {track_dir}")
    discovery_path = discovery_artifact or root / "artifacts" / "discovery" / track / f"{stamp}.json"
    env = dict(os.environ)
    env["JOB_AGENT_ROOT"] = str(root)
    if discovery_artifact is None:
        discovery_latest = root / "artifacts" / "discovery" / track / "latest.json"
        _run(
            [
                sys.executable,
                str(SCRIPT_ROOT / "scripts" / "discover_jobs.py"),
                "--track",
                track,
                "--today",
                stamp,
                "--due-only",
                "--pretty",
                "--output",
                str(discovery_path),
                "--latest-output",
                str(discovery_latest),
            ],
            env=env,
            timeout=discovery_timeout_seconds,
            label="setup discovery",
        )
    if not discovery_path.is_file():
        raise SetupContractError(f"discovery artifact was not produced: {discovery_path}")

    artifact_dir = setup_path.parent
    context_path = artifact_dir / "preview-context.json"
    result_path = artifact_dir / "preview-result.json"
    seen_path = track_dir / "seen_jobs.json"
    context = build_preview_context(
        setup,
        discovery_path,
        seen_path,
        setup_path=setup_path,
        root=root,
    )
    if context["date"] != stamp:
        raise SetupContractError(
            f"discovery artifact date {context['date']} does not match requested preview date {stamp}"
        )
    write_preview_context(context_path, context)
    result, worker_status = run_worker(
        role="preview_ranker",
        input_path=context_path,
        output_path=result_path,
        provider=provider,
        agent_bin_value=agent_bin,
        model=model,
        reasoning=reasoning,
        timeout_seconds=worker_timeout_seconds,
    )
    digest = assemble_preview_digest(context, result)
    digest_path = root / "artifacts" / "digests" / track / f"{stamp}.json"
    write_json_atomic(digest_path, digest, max_bytes=2 * 1024 * 1024)

    post_commands = [
        [
            sys.executable,
            str(SCRIPT_ROOT / "scripts" / "update_source_state.py"),
            "--track",
            track,
            "--date",
            stamp,
            "--artifact",
            str(discovery_path),
        ],
        [sys.executable, str(SCRIPT_ROOT / "scripts" / "render_digest.py"), "--track", track, "--date", stamp],
        [sys.executable, str(SCRIPT_ROOT / "scripts" / "update_seen_jobs.py"), "--track", track, "--date", stamp],
        [sys.executable, str(SCRIPT_ROOT / "scripts" / "update_ranked_overview.py"), "--track", track],
    ]
    for command, label in zip(
        post_commands,
        ("source-state update", "digest rendering", "seen-jobs update", "ranked-overview update"),
        strict=True,
    ):
        _run(command, env=env, timeout=120, label=label)
    markdown_path = track_dir / "digests" / f"{stamp}.md"
    return {
        "status": "created",
        "track": track,
        "date": stamp,
        "preview_context": str(context_path),
        "preview_result": str(result_path),
        "digest_json": str(digest_path),
        "digest_markdown": str(markdown_path),
        "candidates_ranked": len(context["candidates"]),
        "candidates_omitted": context["omitted_candidate_count"],
        "worker": worker_status,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        apply_runtime_env(load_secrets=False)
        root = Path(args.root or os.environ.get("JOB_AGENT_ROOT", SCRIPT_ROOT)).resolve()
        result = run_first_preview(
            Path(args.setup).resolve(),
            root=root,
            today=args.today,
            provider=args.provider,
            agent_bin=args.agent_bin,
            model=args.model,
            reasoning=args.reasoning,
            worker_timeout_seconds=args.timeout_seconds,
            discovery_timeout_seconds=args.discovery_timeout_seconds,
            discovery_artifact=Path(args.discovery_artifact).resolve() if args.discovery_artifact else None,
        )
        print(json.dumps(result))
        return 0
    except (OSError, RuntimeEnvError, SetupContractError, ValueError) as exc:
        print(f"run_setup_preview.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
