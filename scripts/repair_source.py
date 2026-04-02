#!/usr/bin/env python3
"""Run the source-quality repair loop for one source."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from source_quality import generated_at, source_slug, truncate_text


ROOT = Path(__file__).resolve().parents[1]


def default_artifact_path(track: str, stamp: str) -> Path:
    return ROOT / "artifacts" / "discovery" / track / f"{stamp}.json"


def default_eval_output(track: str, source: str, stamp: str) -> Path:
    return ROOT / "artifacts" / "evals" / track / source_slug(source) / f"{stamp}.json"


def default_summary_output(track: str, source: str, stamp: str) -> Path:
    return ROOT / "artifacts" / "evals" / track / source_slug(source) / f"{stamp}.repair_loop.json"


def resolve_coder_bin(explicit: str | None) -> Path | None:
    if explicit:
        return Path(explicit)
    env_bin = os.environ.get("CODEX_BIN")
    if env_bin:
        return Path(env_bin)
    default_codex = Path("/opt/homebrew/bin/codex")
    if default_codex.exists():
        return default_codex
    return None


def run_eval(
    *,
    track: str,
    source: str,
    today: str,
    artifact_path: Path,
    eval_output: Path,
    canary_title: str,
    canary_url: str,
    reviewer: str,
    reviewer_bin: str | None,
    timeout_seconds: int,
) -> tuple[int, dict[str, Any]]:
    command = [
        "python3",
        str(ROOT / "scripts" / "eval_source_quality.py"),
        "--track",
        track,
        "--source",
        source,
        "--today",
        today,
        "--artifact-path",
        str(artifact_path),
        "--output",
        str(eval_output),
        "--reviewer",
        reviewer,
        "--timeout-seconds",
        str(timeout_seconds),
    ]
    if canary_title:
        command.extend(["--canary-title", canary_title])
    if canary_url:
        command.extend(["--canary-url", canary_url])
    if reviewer_bin:
        command.extend(["--reviewer-bin", reviewer_bin])

    completed = subprocess.run(
        command,
        check=False,
        text=True,
        capture_output=True,
        cwd=ROOT,
    )
    payload = json.loads(eval_output.read_text())
    return completed.returncode, payload


def build_coder_prompt(
    *,
    track: str,
    source: str,
    today: str,
    artifact_path: Path,
    eval_output: Path,
    repair_ticket: dict[str, Any],
    canary_title: str,
    canary_url: str,
) -> str:
    lines = [
        f"Repair the {source} source integration from the repository root in mode: repo_dev.",
        "Follow the repository AGENTS.md for mode routing, then follow .agents/skills/coding/SKILL.md.",
        "Make one focused fix for this source only.",
        f"Track: {track}",
        f"Source: {source}",
        f"Date: {today}",
        f"Discovery artifact: {artifact_path}",
        f"Current eval artifact: {eval_output}",
    ]
    if canary_title or canary_url:
        lines.extend(
            [
                "Canary:",
                json.dumps({"title": canary_title, "url": canary_url}, ensure_ascii=False, indent=2),
            ]
        )
    lines.extend(
        [
            "Use this repair ticket as the source of truth:",
            json.dumps(repair_ticket, ensure_ascii=False, indent=2),
            "Constraints:",
            "- Prefer the smallest change in scripts/discover_jobs.py or closely related tests/helpers.",
            "- Do not modify unrelated sources or track configuration.",
            "- Do not broaden search terms unless the ticket explicitly requires it.",
            "- Run the most relevant tests for the changed code before finishing.",
            "The orchestrator will rerun scripts/eval_source_quality.py after your fix.",
        ]
    )
    return "\n".join(lines) + "\n"


def run_coder(
    *,
    coder_bin: Path,
    track: str,
    source: str,
    today: str,
    artifact_path: Path,
    eval_output: Path,
    repair_ticket: dict[str, Any],
    canary_title: str,
    canary_url: str,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    prompt = build_coder_prompt(
        track=track,
        source=source,
        today=today,
        artifact_path=artifact_path,
        eval_output=eval_output,
        repair_ticket=repair_ticket,
        canary_title=canary_title,
        canary_url=canary_url,
    )
    env = os.environ.copy()
    env.update(
        {
            "JOB_AGENT_ROOT": str(ROOT),
            "JOB_AGENT_TRACK": track,
            "JOB_AGENT_SOURCE": source,
            "JOB_AGENT_TODAY": today,
            "JOB_AGENT_DISCOVERY_ARTIFACT": str(artifact_path),
            "JOB_AGENT_EVAL_ARTIFACT": str(eval_output),
            "JOB_AGENT_CANARY_TITLE": canary_title,
            "JOB_AGENT_CANARY_URL": canary_url,
            "JOB_AGENT_REPAIR_TICKET": json.dumps(repair_ticket),
        }
    )
    command = [
        str(coder_bin),
        "--search",
        "-a",
        "never",
        "exec",
        "-C",
        str(ROOT),
        "-s",
        "workspace-write",
        "-",
    ]
    return subprocess.run(
        command,
        input=prompt,
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT,
        env=env,
        timeout=timeout_seconds,
    )


def write_summary(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", required=True, help="Track slug, e.g. core_crypto")
    parser.add_argument("--source", required=True, help="Source name exactly as it appears in the discovery artifact")
    parser.add_argument("--today", required=True, help="Date stamp in YYYY-MM-DD format")
    parser.add_argument("--artifact-path", help="Path to the discovery artifact; defaults to today's track artifact")
    parser.add_argument("--eval-output", help="Path for the latest eval artifact")
    parser.add_argument("--summary-output", help="Path for the repair-loop summary artifact")
    parser.add_argument("--canary-title", default="", help="Expected canary title for this source")
    parser.add_argument("--canary-url", default="", help="Expected canary URL for this source")
    parser.add_argument(
        "--reviewer",
        choices=("auto", "off", "force"),
        default="auto",
        help="Whether to run the LLM reviewer during each eval pass",
    )
    parser.add_argument("--reviewer-bin", help="Binary to invoke for the LLM reviewer")
    parser.add_argument("--coder-bin", help="Binary to invoke for the coding repair run; defaults to CODEX_BIN/codex")
    parser.add_argument("--timeout-seconds", type=int, default=60, help="Timeout for reviewer/raw page fetches during eval")
    parser.add_argument("--repair-timeout-seconds", type=int, default=1200, help="Timeout for each coding repair run")
    parser.add_argument("--max-attempts", type=int, default=2, help="Maximum coding repair attempts")
    args = parser.parse_args()

    artifact_path = Path(args.artifact_path) if args.artifact_path else default_artifact_path(args.track, args.today)
    eval_output = Path(args.eval_output) if args.eval_output else default_eval_output(args.track, args.source, args.today)
    summary_output = Path(args.summary_output) if args.summary_output else default_summary_output(args.track, args.source, args.today)
    coder_bin = resolve_coder_bin(args.coder_bin)

    attempts: list[dict[str, Any]] = []
    repair_attempts = 0
    final_status = "blocked"
    final_eval: dict[str, Any] | None = None

    while True:
        eval_returncode, eval_payload = run_eval(
            track=args.track,
            source=args.source,
            today=args.today,
            artifact_path=artifact_path,
            eval_output=eval_output,
            canary_title=args.canary_title,
            canary_url=args.canary_url,
            reviewer=args.reviewer,
            reviewer_bin=args.reviewer_bin,
            timeout_seconds=args.timeout_seconds,
        )
        final_eval = eval_payload
        attempt_record: dict[str, Any] = {
            "eval_index": len(attempts) + 1,
            "eval_returncode": eval_returncode,
            "eval_output": str(eval_output),
            "eval_final_status": eval_payload.get("final_status", "blocked"),
            "deterministic_confidence": eval_payload.get("deterministic", {}).get("confidence", "failed"),
            "reviewer_status": eval_payload.get("reviewer", {}).get("status", "unknown"),
            "repair_ticket_summary": (eval_payload.get("repair_ticket") or {}).get("summary", ""),
            "coding_invoked": False,
        }

        status = eval_payload.get("final_status", "blocked")
        if status == "pass":
            final_status = "pass"
            attempts.append(attempt_record)
            break
        if status == "blocked":
            final_status = "blocked"
            attempts.append(attempt_record)
            break
        if status != "repair_needed":
            final_status = "blocked"
            attempt_record["error"] = f"unexpected eval final_status: {status}"
            attempts.append(attempt_record)
            break
        if repair_attempts >= args.max_attempts:
            final_status = "retry_limit"
            attempts.append(attempt_record)
            break
        if coder_bin is None or not coder_bin.exists():
            final_status = "blocked"
            attempt_record["error"] = "No coding binary available for repair."
            attempts.append(attempt_record)
            break

        repair_ticket = eval_payload.get("repair_ticket") or {}
        if not repair_ticket:
            final_status = "blocked"
            attempt_record["error"] = "Eval reported repair_needed but produced no repair_ticket."
            attempts.append(attempt_record)
            break

        try:
            completed = run_coder(
                coder_bin=coder_bin,
                track=args.track,
                source=args.source,
                today=args.today,
                artifact_path=artifact_path,
                eval_output=eval_output,
                repair_ticket=repair_ticket,
                canary_title=args.canary_title,
                canary_url=args.canary_url,
                timeout_seconds=args.repair_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            final_status = "blocked"
            attempt_record["coding_invoked"] = True
            attempt_record["coding_error"] = f"repair run timed out after {args.repair_timeout_seconds}s"
            attempt_record["coding_stdout"] = truncate_text(exc.stdout or "", 2000)
            attempt_record["coding_stderr"] = truncate_text(exc.stderr or "", 2000)
            attempts.append(attempt_record)
            break

        repair_attempts += 1
        attempt_record["coding_invoked"] = True
        attempt_record["coding_exit_code"] = completed.returncode
        attempt_record["coding_stdout"] = truncate_text(completed.stdout, 2000)
        attempt_record["coding_stderr"] = truncate_text(completed.stderr, 2000)
        attempts.append(attempt_record)

        if completed.returncode != 0:
            final_status = "blocked"
            break

    summary = {
        "schema_version": 1,
        "generated_at": generated_at(),
        "track": args.track,
        "source": args.source,
        "date": args.today,
        "artifact_path": str(artifact_path),
        "eval_output": str(eval_output),
        "canary": {"title": args.canary_title, "url": args.canary_url},
        "max_attempts": args.max_attempts,
        "repair_attempts_used": repair_attempts,
        "attempts": attempts,
        "final_status": final_status,
        "final_eval": final_eval,
    }
    write_summary(summary_output, summary)
    print(json.dumps(summary, indent=2))
    return 0 if final_status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
