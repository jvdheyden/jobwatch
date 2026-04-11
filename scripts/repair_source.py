#!/usr/bin/env python3
"""Run the source-quality repair loop for one source."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from source_quality import DEFAULT_REVIEW_TIMEOUT_SECONDS, generated_at, source_slug, truncate_text


REPO_ROOT = Path(__file__).resolve().parents[1]
WORK_ROOT = Path(os.environ.get("JOB_AGENT_ROOT", REPO_ROOT))
POLL_INTERVAL_SECONDS = 2.0
SNAPSHOT_IGNORED_PATH_PREFIXES = ("artifacts/evals/", ".git/")


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


def default_postmortem_path(track: str, source: str, stamp: str, attempt: int) -> Path:
    return WORK_ROOT / "artifacts" / "evals" / track / source_slug(source) / f"{stamp}.attempt{attempt}.postmortem.json"


def resolve_repo_python() -> str:
    venv_python = REPO_ROOT / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def resolve_coder_bin(explicit: str | None) -> Path | None:
    if explicit:
        return Path(explicit)
    env_bin = os.environ.get("CODEX_BIN")
    if env_bin:
        return Path(env_bin)
    which_codex = shutil.which("codex")
    if which_codex:
        return Path(which_codex)
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


def snapshot_workspace_files(root: Path) -> dict[str, int]:
    snapshot: dict[str, int] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative.startswith(SNAPSHOT_IGNORED_PATH_PREFIXES):
            continue
        if "/__pycache__/" in relative or relative.endswith(".pyc"):
            continue
        try:
            snapshot[relative] = path.stat().st_mtime_ns
        except FileNotFoundError:
            continue
    return snapshot


def detect_files_touched(before: dict[str, int], after: dict[str, int]) -> list[str]:
    touched: list[str] = []
    for relative in sorted(set(before) | set(after)):
        if before.get(relative) != after.get(relative):
            touched.append(relative)
    return touched


def iter_coder_events(stdout_log_path: Path) -> list[dict[str, Any]]:
    if not stdout_log_path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in stdout_log_path.read_text(errors="replace").splitlines():
        parsed = _maybe_parse_json_line(line.strip())
        if parsed is not None:
            events.append(parsed)
    return events


def iter_completed_command_events(stdout_log_path: Path) -> list[dict[str, Any]]:
    completed: list[dict[str, Any]] = []
    for event in iter_coder_events(stdout_log_path):
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if item.get("type") != "command_execution":
            continue
        if item.get("status") != "completed":
            continue
        completed.append(item)
    return completed


def extract_tests_touched_or_run(stdout_log_path: Path, files_touched: list[str]) -> list[str]:
    seen: list[str] = []
    for relative in files_touched:
        if relative.startswith("tests/"):
            seen.append(relative)

    for item in iter_completed_command_events(stdout_log_path):
        command = item.get("command")
        if not isinstance(command, str):
            continue
        if "pytest" in command or "scripts/test.sh" in command or "python3 -m py_compile" in command:
            seen.append(truncate_text(command, 200))

    deduped: list[str] = []
    for value in seen:
        if value not in deduped:
            deduped.append(value)
    return deduped


def detect_ready_for_rediscovery_signals(
    *,
    stdout_log_path: Path,
    files_touched: list[str],
    likely_file: str,
    track: str,
    source: str,
    today: str,
) -> dict[str, Any]:
    touched_likely_file = likely_file in files_touched
    source_discovery_commands: list[str] = []
    focused_test_commands: list[str] = []
    source_token = source.replace('"', '\\"')

    for item in iter_completed_command_events(stdout_log_path):
        command = item.get("command")
        exit_code = item.get("exit_code")
        if not isinstance(command, str) or exit_code != 0:
            continue
        if (
            "scripts/discover_jobs.py" in command
            and f"--track {track}" in command
            and today in command
            and (source in command or source_token in command)
        ):
            source_discovery_commands.append(truncate_text(command, 240))
        if "pytest" in command and (source.lower() in command.lower() or source_slug(source) in command):
            focused_test_commands.append(truncate_text(command, 240))

    return {
        "touched_likely_file": touched_likely_file,
        "source_scoped_discovery_commands": source_discovery_commands,
        "focused_test_commands": focused_test_commands,
        "ready_for_rediscovery": touched_likely_file and bool(source_discovery_commands),
    }


HANDOFF_PREFIX = "REPAIR_HANDOFF:"


def _extract_agent_messages(stdout_log_path: Path, last_message_path: Path) -> list[str]:
    messages: list[str] = []
    for event in iter_coder_events(stdout_log_path):
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "agent_message":
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                messages.append(text.strip())
            continue
        if event.get("type") == "agent_message":
            text = event.get("text")
            if isinstance(text, str) and text.strip():
                messages.append(text.strip())
    if last_message_path.exists():
        text = last_message_path.read_text(errors="replace").strip()
        if text:
            messages.append(text)
    return messages


def _normalize_handoff_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    evidence = payload.get("evidence", [])
    normalized_evidence: list[str] = []
    if isinstance(evidence, list):
        for value in evidence:
            if isinstance(value, str) and value.strip():
                normalized_evidence.append(truncate_text(value, 240))
    elif isinstance(evidence, str) and evidence.strip():
        normalized_evidence.append(truncate_text(evidence, 240))

    normalized = {
        "reason": truncate_text(str(payload.get("reason", "")).strip(), 240),
        "likely_file": truncate_text(str(payload.get("likely_file", "")).strip(), 240),
        "hypothesis": truncate_text(str(payload.get("hypothesis", "")).strip(), 240),
        "next_edit": truncate_text(str(payload.get("next_edit", "")).strip(), 240),
        "test_hint": truncate_text(str(payload.get("test_hint", "")).strip(), 240),
        "evidence": normalized_evidence[:3],
    }
    if not any([normalized["reason"], normalized["likely_file"], normalized["hypothesis"], normalized["next_edit"], normalized["test_hint"], normalized["evidence"]]):
        return None
    return normalized


def extract_structured_handoff(stdout_log_path: Path, last_message_path: Path) -> dict[str, Any] | None:
    for message in reversed(_extract_agent_messages(stdout_log_path, last_message_path)):
        if not message.startswith(HANDOFF_PREFIX):
            continue
        payload_text = message[len(HANDOFF_PREFIX) :].strip()
        try:
            parsed = json.loads(payload_text)
        except json.JSONDecodeError:
            return {
                "reason": truncate_text(payload_text, 240),
                "likely_file": "",
                "hypothesis": "",
                "next_edit": "",
                "test_hint": "",
                "evidence": [],
            }
        if isinstance(parsed, dict):
            return _normalize_handoff_payload(parsed)
    return None


RUNTIME_ERROR_PATTERNS = (
    re.compile(r"\b[A-Za-z_]+Error:\s+[^\n]+"),
    re.compile(r"\b[A-Za-z_]+Error\s+<[^>\n]+>"),
    re.compile(r"unexpected keyword argument '[^']+'"),
    re.compile(r"Please use browser\.new_context\(\)"),
)


def extract_runtime_error_signatures(attempt_record: dict[str, Any]) -> list[str]:
    text_fragments = [
        str(attempt_record.get("coding_error", "")),
        str(attempt_record.get("coding_last_stderr_excerpt", "")),
        str(attempt_record.get("coding_last_event_excerpt", "")),
        str(attempt_record.get("coding_last_message_excerpt", "")),
        str(attempt_record.get("rediscovery_stderr", "")),
    ]
    matches: list[str] = []
    for fragment in text_fragments:
        if not fragment:
            continue
        for pattern in RUNTIME_ERROR_PATTERNS:
            for match in pattern.findall(fragment):
                cleaned = truncate_text(match.strip(), 200)
                if cleaned not in matches:
                    matches.append(cleaned)
    return matches


def classify_failure(
    *,
    blocked_reason: str,
    runtime_error_signatures: list[str],
    files_touched: list[str],
    attempt_record: dict[str, Any],
) -> str:
    if attempt_record.get("coding_handoff"):
        return "needs_handoff"
    if "failed to launch coding repair run" in blocked_reason:
        return "blocked_launch"
    if attempt_record.get("rediscovery_exit_code") not in (None, 0) or "rediscovery failed" in blocked_reason:
        return "rediscovery_failure"
    if runtime_error_signatures:
        return "runtime_bug"
    if "idle" in blocked_reason:
        return "idle"
    if "timed out" in blocked_reason:
        return "timeout_after_patch" if files_touched else "timeout_without_patch"
    if attempt_record.get("coding_exit_code") not in (None, 0):
        return "nonzero_exit"
    return "blocked_unknown"


def select_primary_repair_file(files_touched: list[str], fallback: str) -> str:
    for path in files_touched:
        if path.startswith(("scripts/", "tests/", ".agents/")):
            return path
    for path in files_touched:
        if path.endswith((".py", ".sh", ".md", ".json")):
            return path
    return fallback


def build_coding_postmortem(
    *,
    track: str,
    source: str,
    today: str,
    attempt_number: int,
    repair_ticket: dict[str, Any],
    attempt_record: dict[str, Any],
    files_touched: list[str],
    tests_touched_or_run: list[str],
    runtime_error_signatures: list[str],
) -> dict[str, Any]:
    handoff = attempt_record.get("coding_handoff")
    blocked_reason = (
        handoff.get("reason") if isinstance(handoff, dict) and handoff.get("reason") else None
    ) or (
        attempt_record.get("coding_error")
        or attempt_record.get("error")
        or "repair attempt ended without a passing rediscovery/eval result"
    )
    failure_class = classify_failure(
        blocked_reason=blocked_reason,
        runtime_error_signatures=runtime_error_signatures,
        files_touched=files_touched,
        attempt_record=attempt_record,
    )
    likely_file = repair_ticket.get("likely_file") or "scripts/discover_jobs.py"
    primary_file = select_primary_repair_file(
        files_touched,
        (handoff.get("likely_file") if isinstance(handoff, dict) else "") or likely_file,
    )
    if failure_class == "needs_handoff":
        likely_next_step = (
            handoff.get("next_edit")
            if isinstance(handoff, dict) and handoff.get("next_edit")
            else f"Resume in {primary_file} using the structured handoff before broader investigation."
        )
    elif failure_class == "idle":
        likely_next_step = f"Resume in {primary_file} and make a focused patch or focused test update before more investigation."
    elif failure_class == "timeout_after_patch":
        likely_next_step = f"Continue from the existing patch in {primary_file}, run the most relevant focused validation earlier, and rerun source-scoped discovery."
    elif failure_class == "timeout_without_patch":
        likely_next_step = f"Start with a focused patch or focused test update in {likely_file} before broader investigation."
    elif failure_class == "runtime_bug":
        runtime_label = runtime_error_signatures[0] if runtime_error_signatures else "the runtime failure"
        likely_next_step = f"Fix {runtime_label} in {primary_file}, then rerun source-scoped discovery."
    elif failure_class == "rediscovery_failure":
        likely_next_step = f"Fix the rediscovery/runtime issue in {primary_file}, then rerun source-scoped discovery."
    elif failure_class == "blocked_launch":
        likely_next_step = "Fix the repair-run launch issue before retrying the source repair."
    elif failure_class == "nonzero_exit":
        likely_next_step = f"Fix the failing command path in {primary_file}, then rerun the focused validation and source-scoped discovery."
    else:
        likely_next_step = f"Continue from the last concrete in-repo step in {primary_file} and rerun focused validation before broader investigation."

    return {
        "schema_version": 1,
        "generated_at": generated_at(),
        "track": track,
        "source": source,
        "date": today,
        "attempt_number": attempt_number,
        "blocked_reason": blocked_reason,
        "repair_ticket_summary": repair_ticket.get("summary", ""),
        "failing_checks": repair_ticket.get("failing_checks", []),
        "failure_class": failure_class,
        "last_meaningful_action": attempt_record.get("coding_last_event_excerpt", ""),
        "last_event_type": attempt_record.get("coding_last_event_type", "unknown"),
        "last_message_excerpt": attempt_record.get("coding_last_message_excerpt", ""),
        "last_stderr_excerpt": attempt_record.get("coding_last_stderr_excerpt", ""),
        "coding_exit_code": attempt_record.get("coding_exit_code"),
        "rediscovery_exit_code": attempt_record.get("rediscovery_exit_code"),
        "files_touched": files_touched,
        "tests_touched_or_run": tests_touched_or_run,
        "runtime_error_signatures": runtime_error_signatures,
        "structured_handoff": handoff if isinstance(handoff, dict) else None,
        "likely_next_step": likely_next_step,
        "confidence": "medium" if attempt_record.get("coding_last_event_excerpt") else "low",
    }


def write_postmortem(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


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
        resolve_repo_python(),
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
        resolve_repo_python(),
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
    prior_postmortem: dict[str, Any] | None,
) -> str:
    failure_mode = str(repair_ticket.get("failure_mode", "unknown") or "unknown")
    target_outcome = str(repair_ticket.get("target_outcome", "") or repair_ticket.get("success_condition", ""))
    suggested_strategy = str(repair_ticket.get("suggested_strategy", "") or "inspect the likely file and make the narrowest fix")
    test_hint = str(repair_ticket.get("test_hint", "") or "")
    primary_evidence = repair_ticket.get("primary_evidence", [])
    lines = [
        f"Repair the {source} source integration from the repository root in mode: repo_dev.",
        "Follow the repository AGENTS.md for mode routing, then use the project skill `coding`.",
        "Aim for one focused repair attempt for this source only.",
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
    if prior_postmortem:
        lines.extend(
            [
                "Prior blocked attempt context:",
                json.dumps(prior_postmortem, ensure_ascii=False, indent=2),
                "Use the prior blocked attempt context to avoid repeating the same failed investigation path.",
            ]
        )
    lines.extend(
        [
            "Use this repair ticket as the source of truth:",
            json.dumps(repair_ticket, ensure_ascii=False, indent=2),
            "Execution modes:",
            "- quick_fix_mode: if the ticket points to a credible focused fix, inspect only the likely file and preferred focused test target, then patch immediately.",
            "- handoff_mode: if a focused quick fix is not credible after the first local pass, stop broad investigation and emit a structured handoff for the next repair child.",
            "Operational guidance:",
            f"- Failure mode: {failure_mode}",
            f"- Target outcome: {target_outcome}",
            f"- Suggested strategy: {suggested_strategy}",
            "Constraints:",
            "- Unless the repair ticket clearly indicates a validator bug, make the functional fix in scripts/discover_jobs.py.",
            "- Start by inspecting the source-specific parser path in scripts/discover_jobs.py and any existing source-specific tests before broader investigation.",
            f"- Start in scripts/discover_jobs.py and look first for source-specific functions or helpers named after {source} (for example discover/extract/advance helpers) or the relevant HTML/browser parser used by this source.",
            "- If a source-specific function or strategy already exists, patch that path instead of exploring unrelated files.",
            "- If no source-specific path exists yet, implement the minimal source-specific parser or strategy needed in scripts/discover_jobs.py and wire it into the existing discovery dispatch.",
            "- Within the first local pass, decide whether you are in quick_fix_mode or handoff_mode. Do not continue exploratory reading once you can state a credible patch hypothesis or a credible blocker.",
            "- Your first concrete step in quick_fix_mode must be either updating/adding a focused test for the source path or patching the source-specific parser/helper in scripts/discover_jobs.py.",
            "- Only change another file when required for a focused test, a directly related helper, or when the repair ticket clearly indicates a validator bug.",
            "- Do not use external web search or raw HTTP/network probes unless local code, existing tests, and the eval artifact are insufficient to design the first patch.",
            "- Do not modify unrelated sources or track configuration.",
            "- Do not broaden search terms unless the ticket explicitly requires it.",
            "- Do not edit discovery or eval artifacts directly.",
            "- Do not run bash scripts/test.sh or scripts/test_track_workflow.sh as part of this repair.",
            "- Do not debug unrelated e2e, workflow, or repo-wide test failures after the focused source validation succeeds.",
            f"- After your code change, validate with: ./.venv/bin/python scripts/discover_jobs.py --track {track} --source {json.dumps(source)} --today {today} --pretty",
            "- Use the repo-local virtualenv for Python tests and helper scripts; if it is missing, bootstrap it with `bash scripts/bootstrap_venv.sh` before Python test commands.",
            "- After your code change, check that the fresh source artifact meets the target outcome and success condition in the repair ticket.",
            "- Run only the most relevant focused tests for the changed code before finishing.",
            "- Stop as soon as the focused validation command completes; do not continue into broader verification after that point.",
            f"- The orchestrator owns rediscovery and final eval. It will regenerate {fresh_artifact_path} and rerun scripts/eval_source_quality.py after your fix.",
            "- If you switch to handoff_mode, do not keep exploring broadly. Gather only the minimum evidence needed to unblock the next repair child and then exit.",
            f'- End handoff_mode with a final assistant message exactly starting with {HANDOFF_PREFIX} followed by JSON.',
            '- Use this handoff JSON shape: {"reason":"why a quick fix is not credible now","likely_file":"path to resume in","hypothesis":"best current explanation","next_edit":"single narrow next edit","test_hint":"preferred focused test file","evidence":["most useful fact 1","most useful fact 2"]}.',
        ]
    )
    if isinstance(primary_evidence, list) and primary_evidence:
        lines.extend(
            [
                "Primary evidence:",
                json.dumps(primary_evidence, ensure_ascii=False, indent=2),
            ]
        )
    if test_hint:
        lines.append(f"- Preferred focused test target: {test_hint}")
    else:
        lines.append("- No focused test target was inferred. If you need a test, choose the closest existing source-family test file and explain that choice in a handoff if unsure.")
    if failure_mode == "missing_detail":
        lines.append("- This ticket is detail-oriented. Prefer enriching already-kept candidates with substantive role detail before considering broader filtering changes.")
    else:
        lines.append("- Do not add detail enrichment unless the ticket's target outcome explicitly requires it.")
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
    prior_postmortem: dict[str, Any] | None,
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
        prior_postmortem=prior_postmortem,
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
            "JOB_AGENT_PRIOR_POSTMORTEM": json.dumps(prior_postmortem) if prior_postmortem else "",
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
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_REVIEW_TIMEOUT_SECONDS,
        help="Timeout for reviewer/raw page fetches during eval",
    )
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
    prior_postmortem: dict[str, Any] | None = None

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
        pre_coder_snapshot = snapshot_workspace_files(WORK_ROOT)

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
                prior_postmortem=prior_postmortem,
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
        attempt_blocked = False
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
                attempt_blocked = True
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
                attempt_blocked = True
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

        files_touched = detect_files_touched(pre_coder_snapshot, snapshot_workspace_files(WORK_ROOT))
        tests_touched_or_run = extract_tests_touched_or_run(stdout_log_path, files_touched)
        structured_handoff = extract_structured_handoff(stdout_log_path, last_message_path)
        runtime_error_signatures = extract_runtime_error_signatures(attempt_record)
        ready_signals = detect_ready_for_rediscovery_signals(
            stdout_log_path=stdout_log_path,
            files_touched=files_touched,
            likely_file=repair_ticket.get("likely_file") or "scripts/discover_jobs.py",
            track=args.track,
            source=args.source,
            today=args.today,
        )
        attempt_record["files_touched"] = files_touched
        attempt_record["tests_touched_or_run"] = tests_touched_or_run
        if structured_handoff is not None:
            attempt_record["coding_handoff"] = structured_handoff
        attempt_record["runtime_error_signatures"] = runtime_error_signatures

        if completed_returncode not in (None, 0) and "coding_error" not in attempt_record:
            attempt_record["coding_error"] = f"repair run exited with code {completed_returncode}"
            attempt_blocked = True
        if structured_handoff is not None:
            attempt_record["coding_error"] = structured_handoff.get("reason") or "repair child exited with structured handoff for the next attempt"
            attempt_blocked = True

        ready_for_rediscovery = attempt_blocked and ready_signals["ready_for_rediscovery"] and structured_handoff is None

        if ready_for_rediscovery:
            attempt_record["coding_completion_state"] = (
                "ready_for_rediscovery_idle" if "idle" in str(attempt_record.get("coding_error", "")) else "ready_for_rediscovery_timeout"
            )
            attempt_record["coding_completion_reason"] = attempt_record.get("coding_error", "")
            attempt_record["coding_success_signals"] = ready_signals
            attempt_record.pop("coding_error", None)
            attempt_blocked = False
        elif structured_handoff is not None:
            attempt_record["coding_completion_state"] = "blocked_handoff"
        elif attempt_blocked:
            attempt_record["coding_completion_state"] = (
                "blocked_idle_no_progress" if "idle" in str(attempt_record.get("coding_error", "")) else "blocked_timeout_no_progress"
            )
        elif completed_returncode not in (None, 0):
            attempt_record["coding_completion_state"] = "blocked_nonzero_exit"
        else:
            attempt_record["coding_completion_state"] = "completed"

        if not ready_for_rediscovery and (attempt_blocked or completed_returncode not in (None, 0)):
            postmortem_path = default_postmortem_path(args.track, args.source, args.today, attempt_number)
            postmortem = build_coding_postmortem(
                track=args.track,
                source=args.source,
                today=args.today,
                attempt_number=attempt_number,
                repair_ticket=repair_ticket,
                attempt_record=attempt_record,
                files_touched=files_touched,
                tests_touched_or_run=tests_touched_or_run,
                runtime_error_signatures=runtime_error_signatures,
            )
            write_postmortem(postmortem_path, postmortem)
            attempt_record["coding_postmortem_path"] = str(postmortem_path)
            attempt_record["coding_postmortem_summary"] = postmortem["blocked_reason"]
            prior_postmortem = postmortem
            if repair_attempts >= args.max_attempts:
                final_status = "blocked"
                break
            continue

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
            attempt_record["error"] = "rediscovery failed after coding repair"
            files_touched = detect_files_touched(pre_coder_snapshot, snapshot_workspace_files(WORK_ROOT))
            tests_touched_or_run = extract_tests_touched_or_run(stdout_log_path, files_touched)
            runtime_error_signatures = extract_runtime_error_signatures(attempt_record)
            postmortem_path = default_postmortem_path(args.track, args.source, args.today, attempt_number)
            postmortem = build_coding_postmortem(
                track=args.track,
                source=args.source,
                today=args.today,
                attempt_number=attempt_number,
                repair_ticket=repair_ticket,
                attempt_record=attempt_record,
                files_touched=files_touched,
                tests_touched_or_run=tests_touched_or_run,
                runtime_error_signatures=runtime_error_signatures,
            )
            write_postmortem(postmortem_path, postmortem)
            attempt_record["coding_postmortem_path"] = str(postmortem_path)
            attempt_record["coding_postmortem_summary"] = postmortem["blocked_reason"]
            prior_postmortem = postmortem
            if repair_attempts >= args.max_attempts:
                final_status = "blocked"
                break
            continue

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
