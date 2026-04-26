#!/usr/bin/env python3
"""Integrate one queued source for a track."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

from source_config import (
    SourceConfigError,
    load_source_state,
    load_sources_config,
    source_state_payload,
    write_json_atomic,
)
from source_quality import DEFAULT_REVIEW_TIMEOUT_SECONDS, source_slug


ROOT = Path(os.environ.get("JOB_AGENT_ROOT", Path(__file__).resolve().parents[1]))
CONFIG_TUNING_STRATEGIES = {
    "config_url_correction",
    "config_terms_override",
    "config_terms_append",
    "config_native_filters",
}
PENDING_STATUSES = {"pending", "integration_needed", "deferred"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", required=True, help="Track directory name under tracks/")
    parser.add_argument("--today", default=date.today().isoformat(), help="Date stamp in YYYY-MM-DD format")
    parser.add_argument("--source", help="Limit integration to a source name or id")
    parser.add_argument("--force", action="store_true", help="Allow another attempt for a source already attempted today")
    parser.add_argument("--dry-run", action="store_true", help="Select the next source without discovery, eval, or state mutation beyond missing entry initialization")
    parser.add_argument(
        "--reviewer",
        choices=("auto", "off", "force"),
        default="auto",
        help="Whether to run the LLM reviewer during quality evaluation",
    )
    parser.add_argument("--reviewer-bin", help="Binary to invoke for the LLM reviewer")
    parser.add_argument("--coder-bin", help="Binary to invoke for the coding integration run")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_REVIEW_TIMEOUT_SECONDS,
        help="Timeout for discovery/evaluation fetches",
    )
    parser.add_argument("--max-attempts", type=int, default=2, help="Maximum coding integration attempts if code is needed")
    return parser


def resolve_repo_python() -> str:
    venv_python = ROOT / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def source_by_id(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {source["id"]: source for source in config["sources"]}


def ensure_source_state_entries(config: dict[str, Any], state: dict[str, dict[str, Any]]) -> bool:
    changed = False
    for source in config["sources"]:
        if source["id"] not in state:
            state[source["id"]] = {"last_checked": None}
            changed = True
    return changed


def _integration_state(state_entry: dict[str, Any]) -> dict[str, Any]:
    integration = state_entry.setdefault("integration", {})
    if not isinstance(integration, dict):
        integration = {}
        state_entry["integration"] = integration
    return integration


def _priority(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def select_next_source(
    config: dict[str, Any],
    state: dict[str, dict[str, Any]],
    *,
    today: str,
    requested_source: str | None = None,
    force: bool = False,
) -> tuple[dict[str, Any] | None, str]:
    requested = requested_source.lower() if requested_source else None
    candidates: list[tuple[int, str, dict[str, Any]]] = []
    for source in config["sources"]:
        state_entry = state.setdefault(source["id"], {"last_checked": None})
        integration = _integration_state(state_entry)
        if requested and requested not in {source["id"].lower(), source["name"].lower()}:
            continue
        status = str(integration.get("status", "") or "")
        if not requested and status not in PENDING_STATUSES:
            continue
        if requested and not status:
            integration["status"] = "pending"
            status = "pending"
        if integration.get("last_attempted") == today and not force:
            continue
        candidates.append((_priority(integration.get("priority")), source["name"], source))

    if not candidates:
        return None, "no queued source is pending or eligible today"
    candidates.sort(key=lambda item: (-item[0], item[1].lower()))
    return candidates[0][2], "selected"


def canary_from_state(integration: dict[str, Any]) -> tuple[str, str]:
    canary = integration.get("canary") if isinstance(integration.get("canary"), dict) else {}
    title = str(canary.get("title") or integration.get("canary_title") or "")
    url = str(canary.get("url") or integration.get("canary_url") or "")
    return title, url


def eval_dir(track: str, source_name: str) -> Path:
    return ROOT / "artifacts" / "evals" / track / source_slug(source_name)


def discovery_artifact_path(track: str, source_name: str, today: str, suffix: str = "integration") -> Path:
    return eval_dir(track, source_name) / f"{today}.{suffix}.discovery.json"


def eval_artifact_path(track: str, source_name: str, today: str, suffix: str = "integration") -> Path:
    return eval_dir(track, source_name) / f"{today}.{suffix}.json"


def loop_summary_path(track: str, source_name: str, today: str) -> Path:
    return eval_dir(track, source_name) / f"{today}.source_integration_loop.json"


def run_discovery(
    *,
    track: str,
    source_name: str,
    today: str,
    output: Path,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    command = [
        resolve_repo_python(),
        str(ROOT / "scripts" / "discover_jobs.py"),
        "--track",
        track,
        "--source",
        source_name,
        "--today",
        today,
        "--pretty",
        "--timeout-seconds",
        str(timeout_seconds),
        "--output",
        str(output),
    ]
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)


def run_eval(
    *,
    track: str,
    source_name: str,
    today: str,
    artifact_path: Path,
    output: Path,
    canary_title: str,
    canary_url: str,
    reviewer: str,
    reviewer_bin: str | None,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    command = [
        resolve_repo_python(),
        str(ROOT / "scripts" / "eval_source_quality.py"),
        "--track",
        track,
        "--source",
        source_name,
        "--today",
        today,
        "--artifact-path",
        str(artifact_path),
        "--output",
        str(output),
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
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)


def run_source_integration(
    *,
    track: str,
    source_name: str,
    today: str,
    artifact_path: Path,
    eval_output: Path,
    summary_output: Path,
    canary_title: str,
    canary_url: str,
    reviewer: str,
    reviewer_bin: str | None,
    coder_bin: str | None,
    timeout_seconds: int,
    max_attempts: int,
) -> subprocess.CompletedProcess[str]:
    command = [
        resolve_repo_python(),
        str(ROOT / "scripts" / "source_integration.py"),
        "--track",
        track,
        "--source",
        source_name,
        "--today",
        today,
        "--artifact-path",
        str(artifact_path),
        "--eval-output",
        str(eval_output),
        "--summary-output",
        str(summary_output),
        "--reviewer",
        reviewer,
        "--timeout-seconds",
        str(timeout_seconds),
        "--max-attempts",
        str(max_attempts),
    ]
    if canary_title:
        command.extend(["--canary-title", canary_title])
    if canary_url:
        command.extend(["--canary-url", canary_url])
    if reviewer_bin:
        command.extend(["--reviewer-bin", reviewer_bin])
    if coder_bin:
        command.extend(["--coder-bin", coder_bin])
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)


def _normalize_terms_payload(value: Any, strategy: str) -> dict[str, Any] | None:
    mode = "override" if strategy == "config_terms_override" else "append"
    terms: list[str] = []
    if isinstance(value, dict):
        mode = str(value.get("mode") or mode)
        raw_terms = value.get("terms")
    else:
        raw_terms = value
    if isinstance(raw_terms, list):
        for term in raw_terms:
            if isinstance(term, str) and term.strip() and term.strip() not in terms:
                terms.append(term.strip())
    if mode not in {"append", "override"} or not terms:
        return None
    return {"mode": mode, "terms": terms}


def _normalize_filters(value: Any) -> dict[str, list[str]] | None:
    if not isinstance(value, dict):
        return None
    filters: dict[str, list[str]] = {}
    for key, raw_values in value.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(raw_values, list):
            continue
        values = [item.strip() for item in raw_values if isinstance(item, str) and item.strip()]
        if values:
            filters[key.strip()] = values
    return filters or None


def apply_config_tuning(
    config: dict[str, Any],
    *,
    source_id: str,
    integration: dict[str, Any],
    ticket: dict[str, Any],
) -> tuple[bool, str]:
    strategy = str(ticket.get("suggested_strategy") or "")
    sources = source_by_id(config)
    source = sources.get(source_id)
    if source is None:
        return False, f"source id {source_id!r} not found in sources.json"

    if strategy in {"config_terms_override", "config_terms_append"}:
        terms_payload = (
            integration.get("search_terms")
            or integration.get("suggested_search_terms")
            or (ticket.get("config_suggestion") or {}).get("search_terms")
        )
        normalized = _normalize_terms_payload(terms_payload, strategy)
        if not normalized:
            return False, "integration ticket asks for search-term tuning but no usable terms were queued"
        source["search_terms"] = normalized
        return True, f"updated source search_terms using {strategy}"

    if strategy == "config_url_correction":
        suggestion = ticket.get("config_suggestion") or {}
        new_url = suggestion.get("source_url")
        if not new_url:
            return False, "integration ticket asks for config_url_correction but no URL was suggested"
        source["url"] = new_url
        if "discovery_mode" in suggestion:
            supported_modes = {"workday_api", "greenhouse_api", "lever_json", "ashby_api", "ashby_html"}
            if suggestion["discovery_mode"] in supported_modes:
                source["discovery_mode"] = suggestion["discovery_mode"]
        return True, f"updated source url to {new_url}"

    if strategy == "config_native_filters":
        filter_payload = integration.get("filters") or integration.get("suggested_filters")
        normalized_filters = _normalize_filters(filter_payload)
        if not normalized_filters:
            return False, "integration ticket asks for native filters but no usable filters were queued"
        current_filters = source.setdefault("filters", {})
        for key, values in normalized_filters.items():
            current_values = current_filters.setdefault(key, [])
            for value in values:
                if value not in current_values:
                    current_values.append(value)
        return True, "updated source native filters"

    return False, f"strategy {strategy!r} is not config tuning"


def update_integration_state(
    state_entry: dict[str, Any],
    *,
    today: str,
    status: str,
    discovery_path: Path | None = None,
    eval_path: Path | None = None,
    summary_path: Path | None = None,
    ticket: dict[str, Any] | None = None,
    note: str = "",
) -> None:
    integration = _integration_state(state_entry)
    integration["status"] = status
    integration["last_attempted"] = today
    integration["attempts"] = _priority(integration.get("attempts")) + 1
    if ticket:
        integration["next_action"] = ticket.get("suggested_strategy")
        integration["last_ticket_summary"] = ticket.get("summary")
    if note:
        integration["last_note"] = note
    artifacts = integration.setdefault("artifacts", {})
    if isinstance(artifacts, dict):
        if discovery_path:
            artifacts["last_discovery"] = str(discovery_path)
        if eval_path:
            artifacts["last_eval"] = str(eval_path)
        if summary_path:
            artifacts["last_loop_summary"] = str(summary_path)


def write_state(track: str, config: dict[str, Any], state: dict[str, dict[str, Any]]) -> None:
    track_dir = ROOT / "tracks" / track
    source_ids = [source["id"] for source in config["sources"]]
    write_json_atomic(track_dir / "source_state.json", source_state_payload(track, source_ids, state))


def read_eval_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise SourceConfigError(f"Could not read eval artifact {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SourceConfigError(f"{path} must contain a JSON object")
    return payload


def main() -> int:
    args = build_parser().parse_args()
    try:
        date.fromisoformat(args.today)
    except ValueError:
        print("integrate_next_source.py: --today must use YYYY-MM-DD", file=sys.stderr)
        return 2

    track_dir = ROOT / "tracks" / args.track
    state_path = track_dir / "source_state.json"
    sources_path = track_dir / "sources.json"
    try:
        config = load_sources_config(sources_path, args.track)
        state = load_source_state(state_path, args.track)
        ensure_source_state_entries(config, state)
        source, reason = select_next_source(
            config,
            state,
            today=args.today,
            requested_source=args.source,
            force=args.force,
        )
    except SourceConfigError as exc:
        print(f"integrate_next_source.py: {exc}", file=sys.stderr)
        return 2

    if source is None:
        write_state(args.track, config, state)
        print(f"No source selected: {reason}")
        return 0
    if args.dry_run:
        write_state(args.track, config, state)
        print(f"Selected source: {source['name']} ({source['id']})")
        return 0

    state_entry = state.setdefault(source["id"], {"last_checked": None})
    integration = _integration_state(state_entry)
    canary_title, canary_url = canary_from_state(integration)
    source_name = source["name"]
    discovery_path = discovery_artifact_path(args.track, source_name, args.today)
    eval_path = eval_artifact_path(args.track, source_name, args.today)
    summary_path = loop_summary_path(args.track, source_name, args.today)

    discovery = run_discovery(
        track=args.track,
        source_name=source_name,
        today=args.today,
        output=discovery_path,
        timeout_seconds=args.timeout_seconds,
    )
    if discovery.returncode != 0:
        update_integration_state(
            state_entry,
            today=args.today,
            status="blocked",
            discovery_path=discovery_path,
            note=discovery.stderr.strip() or f"discovery exited {discovery.returncode}",
        )
        write_state(args.track, config, state)
        print(f"Discovery failed for {source_name}", file=sys.stderr)
        return 1

    eval_result = run_eval(
        track=args.track,
        source_name=source_name,
        today=args.today,
        artifact_path=discovery_path,
        output=eval_path,
        canary_title=canary_title,
        canary_url=canary_url,
        reviewer=args.reviewer,
        reviewer_bin=args.reviewer_bin,
        timeout_seconds=args.timeout_seconds,
    )
    try:
        eval_payload = read_eval_payload(eval_path)
    except SourceConfigError as exc:
        print(f"integrate_next_source.py: {exc}", file=sys.stderr)
        return 2

    status = str(eval_payload.get("final_status") or "blocked")
    ticket = eval_payload.get("integration_ticket") if isinstance(eval_payload.get("integration_ticket"), dict) else None
    if status == "pass":
        update_integration_state(state_entry, today=args.today, status="pass", discovery_path=discovery_path, eval_path=eval_path)
        write_state(args.track, config, state)
        print(f"{source_name}: pass")
        return 0

    is_config_tuning = ticket and str(ticket.get("suggested_strategy")) in CONFIG_TUNING_STRATEGIES

    if status == "blocked" and not is_config_tuning:
        update_integration_state(state_entry, today=args.today, status="blocked", discovery_path=discovery_path, eval_path=eval_path)
        write_state(args.track, config, state)
        print(f"{source_name}: blocked")
        return 1
    if status not in {"integration_needed", "blocked"} or not ticket:
        update_integration_state(
            state_entry,
            today=args.today,
            status="blocked",
            discovery_path=discovery_path,
            eval_path=eval_path,
            note=f"unexpected eval status {status!r}",
        )
        write_state(args.track, config, state)
        return 1

    if is_config_tuning:
        applied, note = apply_config_tuning(config, source_id=source["id"], integration=integration, ticket=ticket)
        if not applied:
            update_integration_state(
                state_entry,
                today=args.today,
                status="deferred",
                discovery_path=discovery_path,
                eval_path=eval_path,
                ticket=ticket,
                note=note,
            )
            write_state(args.track, config, state)
            print(f"{source_name}: deferred ({note})")
            return 1

        write_json_atomic(sources_path, config)
        render = subprocess.run(
            [resolve_repo_python(), str(ROOT / "scripts" / "render_sources_md.py"), "--track", args.track],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if render.returncode != 0:
            update_integration_state(
                state_entry,
                today=args.today,
                status="blocked",
                discovery_path=discovery_path,
                eval_path=eval_path,
                ticket=ticket,
                note=render.stderr.strip() or "render_sources_md.py failed after config tuning",
            )
            write_state(args.track, config, state)
            return 1

        tuned_discovery_path = discovery_artifact_path(args.track, source_name, args.today, suffix="integration.tuned")
        tuned_eval_path = eval_artifact_path(args.track, source_name, args.today, suffix="integration.tuned")
        tuned_discovery = run_discovery(
            track=args.track,
            source_name=source_name,
            today=args.today,
            output=tuned_discovery_path,
            timeout_seconds=args.timeout_seconds,
        )
        if tuned_discovery.returncode != 0:
            update_integration_state(
                state_entry,
                today=args.today,
                status="blocked",
                discovery_path=tuned_discovery_path,
                eval_path=eval_path,
                ticket=ticket,
                note=tuned_discovery.stderr.strip() or "discovery failed after config tuning",
            )
            write_state(args.track, config, state)
            return 1
        tuned_eval = run_eval(
            track=args.track,
            source_name=source_name,
            today=args.today,
            artifact_path=tuned_discovery_path,
            output=tuned_eval_path,
            canary_title=canary_title,
            canary_url=canary_url,
            reviewer=args.reviewer,
            reviewer_bin=args.reviewer_bin,
            timeout_seconds=args.timeout_seconds,
        )
        eval_path = tuned_eval_path
        discovery_path = tuned_discovery_path
        eval_payload = read_eval_payload(eval_path)
        status = str(eval_payload.get("final_status") or "blocked")
        ticket = eval_payload.get("integration_ticket") if isinstance(eval_payload.get("integration_ticket"), dict) else None
        integration["last_config_tuning"] = note
        if tuned_eval.returncode == 0 and status == "pass":
            update_integration_state(
                state_entry,
                today=args.today,
                status="pass",
                discovery_path=discovery_path,
                eval_path=eval_path,
                ticket=ticket,
                note=note,
            )
            write_state(args.track, config, state)
            print(f"{source_name}: pass after config tuning")
            return 0
        if status == "blocked":
            update_integration_state(
                state_entry,
                today=args.today,
                status="blocked",
                discovery_path=discovery_path,
                eval_path=eval_path,
                ticket=ticket,
                note=note,
            )
            write_state(args.track, config, state)
            print(f"{source_name}: blocked after config tuning")
            return 1

    integration_result = run_source_integration(
        track=args.track,
        source_name=source_name,
        today=args.today,
        artifact_path=discovery_path,
        eval_output=eval_path,
        summary_output=summary_path,
        canary_title=canary_title,
        canary_url=canary_url,
        reviewer=args.reviewer,
        reviewer_bin=args.reviewer_bin,
        coder_bin=args.coder_bin,
        timeout_seconds=args.timeout_seconds,
        max_attempts=args.max_attempts,
    )
    loop_status = "blocked"
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text())
            loop_status = str(summary.get("final_status") or "blocked")
        except json.JSONDecodeError:
            loop_status = "blocked"
    state_status = "pass" if loop_status == "pass" else "integration_needed" if loop_status == "retry_limit" else "blocked"
    update_integration_state(
        state_entry,
        today=args.today,
        status=state_status,
        discovery_path=discovery_path,
        eval_path=eval_path,
        summary_path=summary_path,
        ticket=ticket,
        note=f"source_integration.py final_status={loop_status}",
    )
    write_state(args.track, config, state)
    print(f"{source_name}: {state_status}")
    return 0 if integration_result.returncode == 0 and state_status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
