#!/usr/bin/env python3
"""Evaluate one source artifact for extraction quality and repair readiness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agent_provider import resolve_agent_bin, resolve_agent_provider
from source_quality import (
    DEFAULT_REVIEW_TIMEOUT_SECONDS,
    build_repair_ticket,
    generated_at,
    infer_repair_test_hint,
    load_source_coverage,
    review_source_with_llm,
    source_slug,
    validate_source_coverage,
)


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
    args = parser.parse_args()

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
        deterministic = validate_source_coverage(
            source,
            canary_title=args.canary_title,
            canary_url=args.canary_url,
            timeout_seconds=args.timeout_seconds,
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
            "repair_ticket": {
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
                "suggested_strategy": "fix parser field extraction or validator mismatch",
                "test_hint": infer_repair_test_hint({"source": args.source, "discovery_mode": ""}),
                "likely_file": "scripts/discover_jobs.py",
                "success_condition": "Source appears in today's discovery artifact and passes deterministic validation.",
                "non_goals": [
                    "Do not redesign multiple sources at once.",
                    "Do not broaden track search terms unless the defect explicitly requires it.",
                ],
            },
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2) + "\n")
        print(json.dumps(payload, indent=2))
        return 1

    repair_ticket = build_repair_ticket(
        args.track,
        source,
        deterministic,
        reviewer,
        canary_title=args.canary_title,
        canary_url=args.canary_url,
    )
    final_status = "pass"
    if repair_ticket:
        final_status = "repair_needed"
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
        "deterministic": deterministic,
        "reviewer": reviewer,
        "final_status": final_status,
        "repair_ticket": repair_ticket,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    return 0 if final_status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
