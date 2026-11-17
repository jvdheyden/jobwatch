#!/usr/bin/env python3
"""Evaluate one source artifact for extraction quality and integration readiness."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
import os
import sys
from pathlib import Path
from typing import Any

from agent_provider import resolve_agent_bin, resolve_agent_provider
from runtime_env import RuntimeEnvError, apply_runtime_env
from source_quality import (
    DEFAULT_REVIEW_TIMEOUT_SECONDS,
    build_integration_ticket,
    generated_at,
    infer_integration_test_hint,
    load_source_coverage,
    review_source_with_llm,
    source_slug,
    validate_source_coverage,
)
from source_config import load_source_state, load_sources_config
from source_evidence import stored_canaries, effective_canaries, matches_posting, PROVENANCES
from setup_contracts import write_json_atomic, normalize_track_slug

ROOT = Path(__file__).resolve().parents[1]


def default_artifact_path(track: str, stamp: str) -> Path:
    return ROOT / "artifacts" / "discovery" / track / f"{stamp}.json"


def default_output_path(track: str, source: str, stamp: str) -> Path:
    return ROOT / "artifacts" / "evals" / track / source_slug(source) / f"{stamp}.json"


def resolve_reviewer_bin(explicit: str | None) -> Path | None:
    return resolve_agent_bin(explicit, role="reviewer")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", required=True, help="Track slug, e.g. core_crypto")
    parser.add_argument("--source", required=True, help="Source name exactly as it appears in the discovery artifact")
    parser.add_argument("--today", required=True, help="Date stamp in YYYY-MM-DD format")
    parser.add_argument("--artifact-path", help="Path to the discovery artifact; defaults to today's track artifact")
    parser.add_argument("--output", help="Write the evaluation JSON here")
    parser.add_argument("--canary-title", default="", help="Expected canary title for this source")
    parser.add_argument("--canary-url", default="", help="Expected canary URL for this source")
    parser.add_argument("--canary-provenance", choices=sorted(PROVENANCES), default="legacy",
                        help="Acquisition provenance; legacy flags alone do not certify independent coverage")
    parser.add_argument(
        "--reviewer",
        choices=("auto", "off", "force"),
        default="auto",
        help="Whether to run the LLM reviewer",
    )
    parser.add_argument(
        "--reviewer-bin",
        help="Binary to invoke for the LLM reviewer; defaults to JOB_AGENT_REVIEWER_BIN/JOB_AGENT_BIN/provider default",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_REVIEW_TIMEOUT_SECONDS,
        help="Timeout for reviewer/raw page fetches",
    )
    parser.add_argument("--canary-expires-on", help="Canary review deadline; past deadlines trigger independent rechecking, not assumed closure")
    parser.add_argument("--min-candidates", type=int, help="Independently reviewed candidate floor for this configured search")
    parser.add_argument("--min-enumerated", type=int, help="Independently reviewed board enumeration floor")
    parser.add_argument("--min-detail-fraction", type=float, help="Reviewed minimum fraction of candidates with substantive role detail (0 to 1)")
    args = parser.parse_args()
    canary_review = None
    try:
        normalize_track_slug(args.track)
        date.fromisoformat(args.today)
        if args.canary_expires_on and date.fromisoformat(args.canary_expires_on) < date.fromisoformat(args.today):
            canary_review = {"status": "review_due", "expires_on": args.canary_expires_on,
                             "title": args.canary_title, "url": args.canary_url,
                             "action": "Review the official vacancy before renewing this canary."}
        if any(value is not None and value < 0 for value in (args.min_candidates, args.min_enumerated)):
            raise ValueError("minimum counts must be nonnegative")
        if args.min_detail_fraction is not None and not 0 <= args.min_detail_fraction <= 1:
            raise ValueError("minimum detail fraction must be between 0 and 1")
    except ValueError as exc:
        parser.error(str(exc))

    try:
        apply_runtime_env(load_secrets=False)
    except RuntimeEnvError as exc:
        print(f"eval_source_quality.py: {exc}", file=sys.stderr)
        return 1

    global ROOT
    ROOT = Path(os.environ.get("JOB_AGENT_ROOT", Path(__file__).resolve().parents[1]))

    artifact_path = Path(args.artifact_path) if args.artifact_path else default_artifact_path(args.track, args.today)
    output_path = Path(args.output) if args.output else default_output_path(args.track, args.source, args.today)

    try:
        reviewer_provider = resolve_agent_provider()
        reviewer_bin = resolve_reviewer_bin(args.reviewer_bin)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        _, source = load_source_coverage(artifact_path, args.source)
        state = load_source_state(ROOT / "tracks" / args.track / "source_state.json", args.track)
        source_id = source.get("source_id")
        config_path = ROOT / "tracks" / args.track / "sources.json"
        if config_path.exists():
            config = load_sources_config(config_path, args.track)
            configured_source = next((s for s in config["sources"] if s["name"].casefold() == args.source.casefold()), None)
            if configured_source:
                source_id = configured_source["id"]
        canaries = stored_canaries(state.get(source_id, {}).get("integration", {}), source_id or "explicit_source")
        if args.canary_title or args.canary_url:
            explicit = {"id": "explicit_canary", "source_id": source_id, "title": args.canary_title, "url": args.canary_url,
                        "provenance": args.canary_provenance, "availability": "live", "scope": "in_scope",
                        "checked_on": args.today, "expires_on": args.canary_expires_on or (date.fromisoformat(args.today) + timedelta(days=14)).isoformat()}
            # Stored evidence is authoritative: old integration invocations may
            # forward one canary, but must not downgrade provenance or renew it.
            if not any(matches_posting(explicit, c) for c in canaries):
                canaries.append(explicit)
        resolved = effective_canaries(canaries, source.get("candidates", []), today=args.today, timeout=args.timeout_seconds)
        active = [c for c in resolved if c.get("availability") == "live" and c.get("scope") == "in_scope"]
        active.sort(key=lambda c: any(matches_posting(candidate, c) for candidate in source.get("candidates", [])))
        args.canary_title = active[0].get("title", "") if active else ""
        args.canary_url = active[0].get("url", "") if active else ""
        deterministic = validate_source_coverage(
            source,
            canary_title=args.canary_title,
            canary_url=args.canary_url,
            canaries=resolved,
            timeout_seconds=args.timeout_seconds,
            minimum_candidates=args.min_candidates,
            minimum_enumerated=args.min_enumerated,
            minimum_detail_fraction=args.min_detail_fraction,
        )
        reviewer_needed = args.reviewer == "force" or (
            args.reviewer == "auto" and deterministic["confidence"] != "high"
        )
        if args.reviewer == "off":
            reviewer = {
                "status": "skipped",
                "defects": [],
                "reason": "reviewer disabled",
            }
        elif reviewer_needed:
            reviewer = review_source_with_llm(
                ROOT,
                artifact_path,
                source,
                canary_title=args.canary_title,
                canary_url=args.canary_url,
                reviewer_bin=reviewer_bin,
                timeout_seconds=args.timeout_seconds,
                provider=reviewer_provider,
            )
        else:
            reviewer = {
                "status": "skipped",
                "defects": [],
                "reason": "deterministic confidence high",
            }
    except Exception as exc:
        payload: dict[str, Any] = {
            "schema_version": 1,
            "generated_at": generated_at(),
            "track": args.track,
            "source": args.source,
            "date": args.today,
            "artifact_path": str(artifact_path),
            "canary": {"title": args.canary_title, "url": args.canary_url},
            "deterministic": {
                "confidence": "failed",
                "checks": [
                    {
                        "name": "source_coverage_present",
                        "status": "fail",
                        "severity": "blocking",
                        "details": str(exc),
                    }
                ],
                "warnings": [],
            },
            "reviewer": {"status": "skipped", "defects": [], "reason": "source loading failed"},
            "final_status": "blocked",
            "integration_ticket": {
                "status": "open",
                "track": args.track,
                "source": args.source,
                "discovery_mode": "",
                "canary_title": args.canary_title,
                "canary_url": args.canary_url,
                "summary": str(exc),
                "defect_types": ["source_coverage_present"],
                "failing_checks": ["source_coverage_present"],
                "reviewer_defects": [],
                "failure_mode": "validator_failure",
                "primary_evidence": [str(exc)],
                "target_outcome": "Fresh discovery artifact includes this source and satisfies deterministic validation.",
                "suggested_strategy": "dedicated_provider_logic",
                "suggested_strategy_label": "add or fix provider parsing/enumeration logic",
                "config_suggestion": {},
                "test_hint": infer_integration_test_hint({"source": args.source, "discovery_mode": ""}),
                "likely_file": "scripts/discover_jobs.py",
                "success_condition": "Source appears in today's discovery artifact and passes deterministic validation.",
                "non_goals": [
                    "Do not redesign multiple sources at once.",
                    "Do not broaden track search terms unless the defect explicitly requires it.",
                ],
            },
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(output_path, payload, max_bytes=1024 * 1024)
        print(json.dumps(payload, indent=2))
        return 1

    integration_ticket = build_integration_ticket(
        args.track,
        source,
        deterministic,
        reviewer,
        canary_title=args.canary_title,
        canary_url=args.canary_url,
    )
    final_status = "inconclusive" if deterministic["verification"] == "inconclusive" else "pass"
    if integration_ticket:
        final_status = "integration_needed"
    if deterministic["confidence"] == "failed" and reviewer.get("status") == "blocked":
        final_status = "blocked"

    payload = {
        "schema_version": 1,
        "generated_at": generated_at(),
        "track": args.track,
        "source": args.source,
        "date": args.today,
        "artifact_path": str(artifact_path),
        "canary": {"title": args.canary_title, "url": args.canary_url},
        "canary_review": canary_review,
        "canaries": resolved,
        "verification": deterministic["verification"],
        "quality_level": "configured" if integration_ticket else deterministic["quality_level"],
        "deterministic": deterministic,
        "reviewer": reviewer,
        "final_status": final_status,
        "integration_ticket": integration_ticket,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(output_path, payload, max_bytes=1024 * 1024)
    print(json.dumps(payload, indent=2))
    return 0 if final_status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
