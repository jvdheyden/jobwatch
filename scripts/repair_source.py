#!/usr/bin/env python3
"""Run the source-quality repair loop for one source."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from source_quality import generated_at, source_slug, truncate_text


REPO_ROOT = Path(__file__).resolve().parents[1]
WORK_ROOT = Path(os.environ.get("JOB_AGENT_ROOT", REPO_ROOT))
POLL_INTERVAL_SECONDS = 2.0


def default_artifact_path(track: str, stamp: str) -> Path:
    return WORK_ROOT / "artifacts" / "discovery" / track / f"{stamp}.json"


def default_eval_output(track: str, source: str, stamp: str) -> Path:
    return WORK_ROOT / "artifacts" / "evals" / track / source_slug(source) / f"{stamp}.json"


def default_summary_output(track: str, source: str, stamp: str) -> Path:
    return WORK_ROOT / "artifacts" / "evals" / track / source_slug(source) / f"{stamp}.repair_loop.json"


def default_fresh_artifact_path(track: str, source: str, stamp: str) -> Path:
    return WORK_ROOT / "artifacts" / "evals" / track / source_slug(source) / f"{stamp}.discovery.json"


def default_coder_stdout_log_path(track: str, source: str, stamp: str, attempt: int) -> Path:
    return WORK_ROOT / "artifacts" / "evals" / track / source_slug(source) / f"{stamp}.attempt{attempt}.coder.stdout.jsonl"


def default_coder_stderr_log_path(track: str, source: str, stamp: str, attempt: int) -> Path:
    return WORK_ROOT / "artifacts" / "evals" / track / source_slug(source) / f"{stamp}.attempt{attempt}.coder.stderr.log"


def default_coder_last_message_path(track: str, source: str, stamp: str, attempt: int) -> Path:
    return WORK_ROOT / "artifacts" / "evals" / track / source_slug(source) / f"{stamp}.attempt{attempt}.coder.last_message.txt"


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


def write_summary(
    path: Path,
    *,
    track: str,
    source: str,
    today: str,
    artifact_path: Path,
    active_artifact_path: Path,
    eval_output: Path,
    canary_title: str,
    canary_url: str,
    max_attempts: int,
    repair_attempts: int,
    attempts: list[dict[str, Any]],
    final_status: str,
    final_eval: dict[str, Any] | None,
    phase: str,
) -> None:
    payload = {
        "schema_version": 1,
        "generated_at": generated_at(),
        "track": track,
        "source": source,
        "date": today,
        "artifact_path": str(artifact_path),
        "active_artifact_path": str(active_artifact_path),
        "eval_output": str(eval_output),
        "canary": {"title": canary_title, "url": canary_url},
        "max_attempts": max_attempts,
        "repair_attempts_used": repair_attempts,
        "attempts": attempts,
        "phase": phase,
        "final_status": final_status,
        "final_eval": final_eval,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _maybe_parse_json_line(line: str) -> dict[str, Any] | None:
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _event_excerpt(event: dict[str, Any], fallback: str) -> str:
    for key in ("message", "text", "content", "output", "summary", "status"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return truncate_text(value, 400)
    return truncate_text(fallback, 400)


def _event_type(event: dict[str, Any]) -> str:
    for key in ("type", "event", "kind"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return "json_event"


def _read_new_text(path: Path, offset: int) -> tuple[int, str]:
    if not path.exists():
        return offset, ""
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        handle.seek(offset)
        chunk = handle.read()
        return handle.tell(), chunk


def update_attempt_from_logs(
    attempt_record: dict[str, Any],
    stdout_path: Path,
    stderr_path: Path,
    last_message_path: Path,
    stdout_offset: int,
    stderr_offset: int,
    last_message_mtime: float | None,
) -> tuple[int, int, float | None, bool]:
    activity = False
    stdout_offset, stdout_chunk = _read_new_text(stdout_path, stdout_offset)
    stderr_offset, stderr_chunk = _read_new_text(stderr_path, stderr_offset)

    for line in stdout_chunk.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        activity = True
        attempt_record["coding_last_activity_at"] = generated_at()
        attempt_record["coding_stdout_bytes"] = stdout_path.stat().st_size if stdout_path.exists() else 0
        parsed = _maybe_parse_json_line(stripped)
        if parsed is not None:
            attempt_record["coding_last_event_type"] = _event_type(parsed)
            attempt_record["coding_last_event_excerpt"] = _event_excerpt(parsed, stripped)
        else:
            attempt_record["coding_last_event_type"] = "stdout"
            attempt_record["coding_last_event_excerpt"] = truncate_text(stripped, 400)

    for line in stderr_chunk.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        activity = True
        attempt_record["coding_last_activity_at"] = generated_at()
        attempt_record["coding_stderr_bytes"] = stderr_path.stat().st_size if stderr_path.exists() else 0
        attempt_record["coding_last_stderr_excerpt"] = truncate_text(stripped, 400)

    if last_message_path.exists():
        mtime = last_message_path.stat().st_mtime
        if last_message_mtime is None or mtime > last_message_mtime:
            activity = True
            attempt_record["coding_last_activity_at"] = generated_at()
            attempt_record["coding_last_message_excerpt"] = truncate_text(last_message_path.read_text(errors="replace"), 400)
            last_message_mtime = mtime

    return stdout_offset, stderr_offset, last_message_mtime, activity


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
        str(REPO_ROOT / "scripts" / "eval_source_quality.py"),
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
        cwd=WORK_ROOT,
    )
    payload = json.loads(eval_output.read_text())
    return completed.returncode, payload


def run_discovery(
    *,
    track: str,
    source: str,
    today: str,
    artifact_path: Path,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    command = [
        "python3",
        str(WORK_ROOT / "scripts" / "discover_jobs.py"),
        "--track",
        track,
        "--source",
        source,
        "--today",
        today,
        "--pretty",
        "--timeout-seconds",
        str(timeout_seconds),
        "--output",
        str(artifact_path),
    ]
    return subprocess.run(
        command,
        check=False,
        text=True,
        capture_output=True,
        cwd=WORK_ROOT,
    )


def build_coder_prompt(
    *,
    track: str,
    source: str,
    today: str,
    artifact_path: Path,
    fresh_artifact_path: Path,
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
        f"Previous discovery artifact: {artifact_path}",
        f"Fresh discovery artifact target: {fresh_artifact_path}",
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
            "- Unless the repair ticket clearly indicates a validator bug, make the functional fix in scripts/discover_jobs.py.",
            "- Start by inspecting the source-specific parser path in scripts/discover_jobs.py and any existing source-specific tests before broader investigation.",
            f"- Start in scripts/discover_jobs.py and look first for source-specific functions or helpers named after {source} (for example discover/extract/advance helpers) or the relevant HTML/browser parser used by this source.",
            "- If a source-specific function or strategy already exists, patch that path instead of exploring unrelated files.",
            "- If no source-specific path exists yet, implement the minimal source-specific parser or strategy needed in scripts/discover_jobs.py and wire it into the existing discovery dispatch.",
            "- Your first concrete step must be either updating/adding a focused test for the source path or patching the source-specific parser/helper in scripts/discover_jobs.py.",
            "- Only change another file when required for a focused test, a directly related helper, or when the repair ticket clearly indicates a validator bug.",
            "- Do not use external web search or raw HTTP/network probes unless local code, existing tests, and the eval artifact are insufficient to design the first patch.",
            "- If the failing check is detail_depth, prefer source-specific detail-page enrichment for already-kept candidates and append substantive role detail to existing extracted notes or fields.",
            "- Do not modify unrelated sources or track configuration.",
            "- Do not broaden search terms unless the ticket explicitly requires it.",
            "- Do not edit discovery or eval artifacts directly.",
            f"- After your code change, validate with: python3 scripts/discover_jobs.py --track {track} --source {json.dumps(source)} --today {today} --pretty",
            f"- Check that the fresh source artifact includes the detail missing from the repair ticket for the canary {json.dumps(canary_title)}.",
            "- Run the most relevant tests for the changed code before finishing.",
            f"- The orchestrator will regenerate {fresh_artifact_path} and rerun scripts/eval_source_quality.py after your fix.",
            "- If you cannot get to a pass with one focused fix, stop with a concrete blocker rather than exploring broadly.",
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
    fresh_artifact_path: Path,
    eval_output: Path,
    repair_ticket: dict[str, Any],
    canary_title: str,
    canary_url: str,
    timeout_seconds: int,
    stdout_log_path: Path,
    stderr_log_path: Path,
    last_message_path: Path,
) -> subprocess.Popen[str]:
    prompt = build_coder_prompt(
        track=track,
        source=source,
        today=today,
        artifact_path=artifact_path,
        fresh_artifact_path=fresh_artifact_path,
        eval_output=eval_output,
        repair_ticket=repair_ticket,
        canary_title=canary_title,
        canary_url=canary_url,
    )
    env = os.environ.copy()
    env.update(
        {
            "JOB_AGENT_ROOT": str(WORK_ROOT),
            "JOB_AGENT_TRACK": track,
            "JOB_AGENT_SOURCE": source,
            "JOB_AGENT_TODAY": today,
            "JOB_AGENT_DISCOVERY_ARTIFACT": str(artifact_path),
            "JOB_AGENT_REDISCOVERY_ARTIFACT": str(fresh_artifact_path),
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
        str(WORK_ROOT),
        "-s",
        "workspace-write",
        "--json",
        "--output-last-message",
        str(last_message_path),
        "-",
    ]
    stdout_log_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_log_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_handle = stdout_log_path.open("w", encoding="utf-8")
    stderr_handle = stderr_log_path.open("w", encoding="utf-8")
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
            cwd=WORK_ROOT,
            env=env,
        )
    except Exception:
        stdout_handle.close()
        stderr_handle.close()
        raise

    assert process.stdin is not None
    process.stdin.write(prompt)
    process.stdin.close()
    return process


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
    parser.add_argument("--repair-timeout-seconds", type=int, default=600, help="Timeout for each coding repair run")
    parser.add_argument("--idle-timeout-seconds", type=int, default=90, help="Abort a coding repair attempt if it produces no new output for this many seconds")
    parser.add_argument("--max-attempts", type=int, default=2, help="Maximum coding repair attempts")
    args = parser.parse_args()

    artifact_path = Path(args.artifact_path) if args.artifact_path else default_artifact_path(args.track, args.today)
    fresh_artifact_path = default_fresh_artifact_path(args.track, args.source, args.today)
    eval_output = Path(args.eval_output) if args.eval_output else default_eval_output(args.track, args.source, args.today)
    summary_output = Path(args.summary_output) if args.summary_output else default_summary_output(args.track, args.source, args.today)
    coder_bin = resolve_coder_bin(args.coder_bin)

    attempts: list[dict[str, Any]] = []
    repair_attempts = 0
    final_status = "running"
    final_eval: dict[str, Any] | None = None
    phase = "starting"
    active_artifact_path = artifact_path

    write_summary(
        summary_output,
        track=args.track,
        source=args.source,
        today=args.today,
        artifact_path=artifact_path,
        active_artifact_path=active_artifact_path,
        eval_output=eval_output,
        canary_title=args.canary_title,
        canary_url=args.canary_url,
        max_attempts=args.max_attempts,
        repair_attempts=repair_attempts,
        attempts=attempts,
        final_status="running",
        final_eval=final_eval,
        phase=phase,
    )

    while True:
        phase = "evaluating"
        eval_returncode, eval_payload = run_eval(
            track=args.track,
            source=args.source,
            today=args.today,
            artifact_path=active_artifact_path,
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
            "artifact_path": str(active_artifact_path),
            "eval_output": str(eval_output),
            "eval_final_status": eval_payload.get("final_status", "blocked"),
            "deterministic_confidence": eval_payload.get("deterministic", {}).get("confidence", "failed"),
            "reviewer_status": eval_payload.get("reviewer", {}).get("status", "unknown"),
            "repair_ticket_summary": (eval_payload.get("repair_ticket") or {}).get("summary", ""),
            "coding_invoked": False,
            "rediscovery_invoked": False,
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

        attempt_number = repair_attempts + 1
        stdout_log_path = default_coder_stdout_log_path(args.track, args.source, args.today, attempt_number)
        stderr_log_path = default_coder_stderr_log_path(args.track, args.source, args.today, attempt_number)
        last_message_path = default_coder_last_message_path(args.track, args.source, args.today, attempt_number)
        attempt_record["coding_invoked"] = True
        attempt_record["coding_stdout_log"] = str(stdout_log_path)
        attempt_record["coding_stderr_log"] = str(stderr_log_path)
        attempt_record["coding_last_message_path"] = str(last_message_path)
        attempt_record["coding_started_at"] = generated_at()
        attempt_record["coding_last_event_type"] = "launched"
        attempt_record["coding_last_event_excerpt"] = "repair child launched"
        attempt_record["coding_idle_timeout_seconds"] = args.idle_timeout_seconds

        try:
            phase = "repairing"
            write_summary(
                summary_output,
                track=args.track,
                source=args.source,
                today=args.today,
                artifact_path=artifact_path,
                active_artifact_path=active_artifact_path,
                eval_output=eval_output,
                canary_title=args.canary_title,
                canary_url=args.canary_url,
                max_attempts=args.max_attempts,
                repair_attempts=repair_attempts,
                attempts=attempts + [attempt_record],
                final_status="running",
                final_eval=final_eval,
                phase=phase,
            )
            process = run_coder(
                coder_bin=coder_bin,
                track=args.track,
                source=args.source,
                today=args.today,
                artifact_path=artifact_path,
                fresh_artifact_path=fresh_artifact_path,
                eval_output=eval_output,
                repair_ticket=repair_ticket,
                canary_title=args.canary_title,
                canary_url=args.canary_url,
                timeout_seconds=args.repair_timeout_seconds,
                stdout_log_path=stdout_log_path,
                stderr_log_path=stderr_log_path,
                last_message_path=last_message_path,
            )
        except Exception as exc:
            final_status = "blocked"
            attempt_record["coding_error"] = f"failed to launch coding repair run: {exc}"
            attempts.append(attempt_record)
            break

        attempt_record["coding_pid"] = process.pid
        start_time = time.monotonic()
        last_activity_time = start_time
        stdout_offset = 0
        stderr_offset = 0
        last_message_mtime: float | None = None
        completed_returncode: int | None = None
        while True:
            stdout_offset, stderr_offset, last_message_mtime, activity = update_attempt_from_logs(
                attempt_record,
                stdout_log_path,
                stderr_log_path,
                last_message_path,
                stdout_offset,
                stderr_offset,
                last_message_mtime,
            )
            if activity:
                last_activity_time = time.monotonic()

            returncode = process.poll()
            idle_seconds = int(time.monotonic() - last_activity_time)
            attempt_record["coding_idle_seconds"] = idle_seconds
            elapsed_seconds = int(time.monotonic() - start_time)
            attempt_record["coding_elapsed_seconds"] = elapsed_seconds
            write_summary(
                summary_output,
                track=args.track,
                source=args.source,
                today=args.today,
                artifact_path=artifact_path,
                active_artifact_path=active_artifact_path,
                eval_output=eval_output,
                canary_title=args.canary_title,
                canary_url=args.canary_url,
                max_attempts=args.max_attempts,
                repair_attempts=repair_attempts,
                attempts=attempts + [attempt_record],
                final_status="running",
                final_eval=final_eval,
                phase=phase,
            )

            if returncode is not None:
                completed_returncode = returncode
                break
            if elapsed_seconds >= args.repair_timeout_seconds:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                final_status = "blocked"
                attempt_record["coding_error"] = f"repair run timed out after {args.repair_timeout_seconds}s"
                completed_returncode = process.returncode
                break
            if idle_seconds >= args.idle_timeout_seconds:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                final_status = "blocked"
                attempt_record["coding_error"] = f"repair run went idle after {args.idle_timeout_seconds}s without new output"
                completed_returncode = process.returncode
                attempt_record["coding_last_event_type"] = "idle_timeout"
                break
            time.sleep(POLL_INTERVAL_SECONDS)

        repair_attempts += 1
        stdout_offset, stderr_offset, last_message_mtime, _ = update_attempt_from_logs(
            attempt_record,
            stdout_log_path,
            stderr_log_path,
            last_message_path,
            stdout_offset,
            stderr_offset,
            last_message_mtime,
        )
        attempt_record["coding_exit_code"] = completed_returncode
        attempts.append(attempt_record)

        if completed_returncode != 0 or final_status == "blocked":
            break

        phase = "rediscovering"
        rediscovery = run_discovery(
            track=args.track,
            source=args.source,
            today=args.today,
            artifact_path=fresh_artifact_path,
            timeout_seconds=args.timeout_seconds,
        )
        attempt_record["rediscovery_invoked"] = True
        attempt_record["rediscovery_exit_code"] = rediscovery.returncode
        attempt_record["rediscovery_artifact"] = str(fresh_artifact_path)
        attempt_record["rediscovery_stdout"] = truncate_text(rediscovery.stdout, 2000)
        attempt_record["rediscovery_stderr"] = truncate_text(rediscovery.stderr, 2000)

        if rediscovery.returncode != 0:
            final_status = "blocked"
            attempt_record["error"] = "rediscovery failed after coding repair"
            break

        active_artifact_path = fresh_artifact_path

    write_summary(
        summary_output,
        track=args.track,
        source=args.source,
        today=args.today,
        artifact_path=artifact_path,
        active_artifact_path=active_artifact_path,
        eval_output=eval_output,
        canary_title=args.canary_title,
        canary_url=args.canary_url,
        max_attempts=args.max_attempts,
        repair_attempts=repair_attempts,
        attempts=attempts,
        final_status=final_status,
        final_eval=final_eval,
        phase="finished",
    )
    print(summary_output.read_text().rstrip())
    return 0 if final_status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
