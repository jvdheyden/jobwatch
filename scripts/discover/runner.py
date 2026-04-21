"""CLI orchestration for deterministic source discovery."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, TextIO

from discover.constants import DEFAULT_TIMEOUT_SECONDS
from discover.core import Coverage, SourceConfig, SourceTermRule, discover_source
from discover.track_filters import filter_coverage_for_track
from source_config import SourceConfigError, load_source_state, load_sources_config


ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic discovery helper for track job sources.")
    parser.add_argument("--track", default="core_crypto", help="Track directory name under tracks/")
    parser.add_argument("--today", default=date.today().isoformat(), help="Date used for cadence decisions")
    parser.add_argument("--source", action="append", default=[], help="Limit to one or more source names")
    parser.add_argument(
        "--cadence-group",
        choices=["every_run", "every_3_runs", "every_month"],
        action="append",
        default=[],
        help="Limit to one or more cadence groups",
    )
    parser.add_argument("--due-only", action="store_true", help="Only include sources due today")
    parser.add_argument("--list-sources", action="store_true", help="List parsed sources and exit")
    parser.add_argument("--output", help="Write JSON output to this path instead of stdout")
    parser.add_argument("--latest-output", help="Also write the same JSON to a stable latest-artifact path")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    parser.add_argument("--progress", action="store_true", help="Emit per-source progress lines to stderr")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="Network timeout")
    parser.add_argument("--plan-only", action="store_true", help="Parse config and compute due sources without fetching")
    return parser


def load_track_config(
    track: str,
    root: Path = ROOT,
) -> tuple[list[SourceConfig], list[str], dict[str, SourceTermRule]]:
    track_dir = root / "tracks" / track
    config = load_sources_config(track_dir / "sources.json", track)
    state = load_source_state(track_dir / "source_state.json", track)
    sources: list[SourceConfig] = []
    source_terms: dict[str, SourceTermRule] = {}
    for item in config["sources"]:
        source = SourceConfig(
            source=item["name"],
            url=item["url"],
            discovery_mode=item["discovery_mode"],
            last_checked=(state.get(item["id"]) or {}).get("last_checked"),
            cadence_group=item["cadence_group"],
            filters={key: list(values) for key, values in item.get("filters", {}).items()},
            source_id=item["id"],
        )
        sources.append(source)
        search_terms = item.get("search_terms")
        if search_terms:
            source_terms[item["id"]] = SourceTermRule(
                terms=list(search_terms["terms"]),
                mode=search_terms["mode"],
            )
    return sources, list(config["track_terms"]), source_terms


def source_due_today(source: SourceConfig, today: date) -> bool:
    if source.cadence_group == "every_run":
        return True
    if not source.last_checked:
        return True
    try:
        last_checked = date.fromisoformat(source.last_checked)
    except ValueError:
        return True
    if source.cadence_group == "every_month":
        return (today.year, today.month) != (last_checked.year, last_checked.month)
    return (today - last_checked).days >= 3


def normalize_terms(track_terms: list[str], source_rule: SourceTermRule | None) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    if source_rule and source_rule.mode == "override":
        combined_terms = list(source_rule.terms)
    else:
        combined_terms = list(track_terms)
        if source_rule:
            combined_terms.extend(source_rule.terms)
    for term in combined_terms:
        lowered = term.strip().lower()
        if not lowered or lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(term.strip())
    return normalized


def generated_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def emit_progress(enabled: bool, message: str, stream: TextIO = sys.stderr) -> None:
    if not enabled:
        return
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", file=stream, flush=True)


def source_to_dict(
    source: SourceConfig,
    today: date,
    track_terms: list[str],
    source_term_map: dict[str, SourceTermRule],
) -> dict[str, Any]:
    source_rule = source_term_map.get(source.source_id) or source_term_map.get(source.source)
    terms = normalize_terms(track_terms, source_rule)
    return {
        "source_id": source.source_id or source.source,
        "source": source.source,
        "url": source.url,
        "discovery_mode": source.discovery_mode,
        "last_checked": source.last_checked,
        "cadence_group": source.cadence_group,
        "due_today": source_due_today(source, today),
        "search_terms": terms,
        "filters": source.filters,
    }


def coverage_to_dict(coverage: Coverage) -> dict[str, Any]:
    payload = asdict(coverage)
    payload["candidates"] = [asdict(candidate) for candidate in coverage.candidates]
    return payload


def write_output_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(text)
    temp_path.replace(path)


def main(
    argv: list[str] | None = None,
    *,
    load_track_config_func: Callable[
        [str],
        tuple[list[SourceConfig], list[str], dict[str, SourceTermRule]],
    ]
    | None = None,
    discover_source_func: Callable[[SourceConfig, list[str], int], Coverage] | None = None,
    filter_coverage_func: Callable[[str, Coverage], Coverage] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    load_config = load_track_config_func or load_track_config
    discover = discover_source_func or discover_source
    filter_coverage = filter_coverage_func or filter_coverage_for_track
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr

    today = date.fromisoformat(args.today)
    try:
        sources, track_terms, source_term_map = load_config(args.track)
    except SourceConfigError as exc:
        print(f"discover_jobs.py: {exc}", file=stderr)
        return 2

    if args.source:
        wanted = {name.lower() for name in args.source}
        sources = [source for source in sources if source.source.lower() in wanted]

    if args.cadence_group:
        wanted_groups = set(args.cadence_group)
        sources = [source for source in sources if source.cadence_group in wanted_groups]

    if args.due_only:
        sources = [source for source in sources if source_due_today(source, today)]

    if args.list_sources:
        payload = {
            "schema_version": 1,
            "track": args.track,
            "today": args.today,
            "generated_at": generated_at(),
            "mode": "list_sources",
            "sources": [source_to_dict(source, today, track_terms, source_term_map) for source in sources],
        }
    elif args.plan_only:
        payload = {
            "schema_version": 1,
            "track": args.track,
            "today": args.today,
            "generated_at": generated_at(),
            "mode": "plan_only",
            "sources": [source_to_dict(source, today, track_terms, source_term_map) for source in sources],
        }
    else:
        coverages: list[Coverage] = []
        total_sources = len(sources)
        for index, source in enumerate(sources, start=1):
            source_rule = source_term_map.get(source.source_id) or source_term_map.get(source.source)
            terms = normalize_terms(track_terms, source_rule)
            emit_progress(
                args.progress,
                f"Discovering source {index}/{total_sources}: {source.source} (mode={source.discovery_mode})",
                stderr,
            )
            coverage = discover(source, terms, args.timeout_seconds)
            coverage = filter_coverage(args.track, coverage)
            coverage.due_today = source_due_today(source, today)
            emit_progress(
                args.progress,
                (
                    f"Completed source {index}/{total_sources}: {source.source} "
                    f"(status={coverage.status}, matched={coverage.matched_jobs}, candidates={len(coverage.candidates)})"
                ),
                stderr,
            )
            coverages.append(coverage)
        payload = {
            "schema_version": 1,
            "track": args.track,
            "today": args.today,
            "generated_at": generated_at(),
            "mode": "discover",
            "sources": [coverage_to_dict(coverage) for coverage in coverages],
        }

    json_text = json.dumps(payload, indent=2 if args.pretty else None, ensure_ascii=True)
    if args.output:
        serialized = json_text + ("\n" if args.pretty else "")
        write_output_text(Path(args.output), serialized)
        if args.latest_output:
            write_output_text(Path(args.latest_output), serialized)
    else:
        stdout.write(json_text)
        if args.pretty:
            stdout.write("\n")
    return 0
