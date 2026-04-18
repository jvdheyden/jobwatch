#!/usr/bin/env python3
"""Helpers for structured daily digest artifacts and markdown rendering."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import json
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
RECENT_CUTOFF_DAYS = 30


def filter_recent_ranked_jobs(
    jobs: list[dict[str, Any]],
    *,
    as_of: date | None,
    days: int = RECENT_CUTOFF_DAYS,
) -> list[dict[str, Any]]:
    """Return jobs whose `last_seen` is within `days` of `as_of`.

    When `as_of` is None, returns the list unchanged (no filter).
    Jobs with missing or non-date `last_seen` values sort above YYYY-MM-DD
    strings and are therefore kept.
    """
    if as_of is None:
        return list(jobs)
    cutoff = (as_of - timedelta(days=days)).isoformat()
    return [job for job in jobs if str(job.get("last_seen", "")) >= cutoff]


class DigestValidationError(ValueError):
    """Raised when a structured digest artifact is invalid."""


def track_display_name(track: str) -> str:
    return " ".join(part.capitalize() for part in re.split(r"[_-]+", track) if part)


def digest_page_name(track: str, stamp: str) -> str:
    return f"{track_display_name(track)} Job Digest {stamp}"


def digest_artifact_path(track: str, stamp: str, root: Path = ROOT) -> Path:
    return root / "artifacts" / "digests" / track / f"{stamp}.json"


def digest_latest_artifact_path(track: str, root: Path = ROOT) -> Path:
    return root / "artifacts" / "digests" / track / "latest.json"


def _expect_type(value: Any, expected: type | tuple[type, ...], field: str) -> Any:
    if not isinstance(value, expected):
        expected_name = (
            ", ".join(item.__name__ for item in expected)
            if isinstance(expected, tuple)
            else expected.__name__
        )
        raise DigestValidationError(f"{field} must be {expected_name}")
    return value


def _expect_string(value: Any, field: str, *, allow_empty: bool = False) -> str:
    text = _expect_type(value, str, field).strip()
    if not allow_empty and not text:
        raise DigestValidationError(f"{field} must be non-empty")
    return text


def _optional_string(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _expect_string(value, field, allow_empty=False)


def _string_list(value: Any, field: str) -> list[str]:
    items = _expect_type(value, list, field)
    return [_expect_string(item, f"{field}[]") for item in items]


def _optional_scalar(value: Any, field: str) -> str | int | float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise DigestValidationError(f"{field} must not be boolean")
    if isinstance(value, (str, int, float)):
        return value
    raise DigestValidationError(f"{field} must be string, int, float, or null")


def _optional_float(value: Any, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise DigestValidationError(f"{field} must not be boolean")
    if isinstance(value, (int, float)):
        return float(value)
    raise DigestValidationError(f"{field} must be numeric or null")


def _enum(value: Any, field: str, allowed: set[str]) -> str:
    text = _expect_string(value, field)
    if text not in allowed:
        allowed_str = ", ".join(sorted(allowed))
        raise DigestValidationError(f"{field} must be one of: {allowed_str}")
    return text


def _normalize_top_match(item: dict[str, Any], index: int) -> dict[str, Any]:
    field = f"runs[].top_matches[{index}]"
    return {
        "job_key": _optional_string(item.get("job_key"), f"{field}.job_key"),
        "company": _expect_string(item.get("company"), f"{field}.company"),
        "title": _expect_string(item.get("title"), f"{field}.title"),
        "listing_url": _expect_string(item.get("listing_url"), f"{field}.listing_url"),
        "alternate_url": _optional_string(item.get("alternate_url"), f"{field}.alternate_url"),
        "location": _optional_string(item.get("location"), f"{field}.location"),
        "remote": _optional_string(item.get("remote"), f"{field}.remote"),
        "team_or_domain": _optional_string(item.get("team_or_domain"), f"{field}.team_or_domain"),
        "posted_date": _optional_string(item.get("posted_date"), f"{field}.posted_date"),
        "updated_date": _optional_string(item.get("updated_date"), f"{field}.updated_date"),
        "source": _optional_string(item.get("source"), f"{field}.source"),
        "source_url": _optional_string(item.get("source_url"), f"{field}.source_url"),
        "fit_score": _optional_float(item.get("fit_score"), f"{field}.fit_score"),
        "recommendation": _enum(item.get("recommendation"), f"{field}.recommendation", {"apply_now", "watch", "skip"}),
        "why_match": _string_list(item.get("why_match", []), f"{field}.why_match"),
        "concerns": _string_list(item.get("concerns", []), f"{field}.concerns"),
    }


def _normalize_other_role(item: dict[str, Any], index: int) -> dict[str, Any]:
    field = f"runs[].other_new_roles[{index}]"
    return {
        "job_key": _optional_string(item.get("job_key"), f"{field}.job_key"),
        "company": _expect_string(item.get("company"), f"{field}.company"),
        "title": _expect_string(item.get("title"), f"{field}.title"),
        "listing_url": _expect_string(item.get("listing_url"), f"{field}.listing_url"),
        "alternate_url": _optional_string(item.get("alternate_url"), f"{field}.alternate_url"),
        "location": _optional_string(item.get("location"), f"{field}.location"),
        "source": _optional_string(item.get("source"), f"{field}.source"),
        "fit_score": _optional_float(item.get("fit_score"), f"{field}.fit_score"),
        "recommendation": _enum(item.get("recommendation"), f"{field}.recommendation", {"apply_now", "watch", "skip"}),
        "short_note": _expect_string(item.get("short_note"), f"{field}.short_note"),
    }


def _normalize_filtered_role(item: dict[str, Any], index: int) -> dict[str, Any]:
    field = f"runs[].filtered_roles[{index}]"
    return {
        "company": _expect_string(item.get("company"), f"{field}.company"),
        "title": _expect_string(item.get("title"), f"{field}.title"),
        "listing_url": _optional_string(item.get("listing_url"), f"{field}.listing_url"),
        "reason_filtered_out": _expect_string(item.get("reason_filtered_out"), f"{field}.reason_filtered_out"),
    }


def _normalize_source_note(item: dict[str, Any], index: int) -> dict[str, Any]:
    field = f"runs[].source_notes[{index}]"
    return {
        "source": _expect_string(item.get("source"), f"{field}.source"),
        "discovery_mode": _expect_string(item.get("discovery_mode"), f"{field}.discovery_mode"),
        "status": _enum(item.get("status"), f"{field}.status", {"complete", "partial", "failed"}),
        "listing_pages_scanned": _optional_scalar(item.get("listing_pages_scanned"), f"{field}.listing_pages_scanned"),
        "search_terms_tried": _string_list(item.get("search_terms_tried", []), f"{field}.search_terms_tried"),
        "result_pages_summary": _optional_scalar(item.get("result_pages_summary"), f"{field}.result_pages_summary"),
        "direct_job_pages_opened": _optional_scalar(item.get("direct_job_pages_opened"), f"{field}.direct_job_pages_opened"),
        "limitations": _string_list(item.get("limitations", []), f"{field}.limitations"),
        "note": _optional_string(item.get("note"), f"{field}.note"),
    }


def _normalize_run(run: dict[str, Any], index: int) -> dict[str, Any]:
    if not isinstance(run, dict):
        raise DigestValidationError(f"runs[{index}] must be an object")
    field = f"runs[{index}]"
    top_matches = [_normalize_top_match(item, i) for i, item in enumerate(_expect_type(run.get("top_matches", []), list, f"{field}.top_matches"))]
    other_roles = [_normalize_other_role(item, i) for i, item in enumerate(_expect_type(run.get("other_new_roles", []), list, f"{field}.other_new_roles"))]
    filtered_roles = [
        _normalize_filtered_role(item, i)
        for i, item in enumerate(_expect_type(run.get("filtered_roles", []), list, f"{field}.filtered_roles"))
    ]
    source_notes = [
        _normalize_source_note(item, i)
        for i, item in enumerate(_expect_type(run.get("source_notes", []), list, f"{field}.source_notes"))
    ]
    return {
        "kind": _enum(run.get("kind"), f"{field}.kind", {"initial", "update"}),
        "generated_at": _expect_string(run.get("generated_at"), f"{field}.generated_at"),
        "executive_summary": _optional_string(run.get("executive_summary"), f"{field}.executive_summary") or "",
        "recommended_actions": _string_list(run.get("recommended_actions", []), f"{field}.recommended_actions"),
        "top_matches": top_matches,
        "other_new_roles": other_roles,
        "filtered_roles": filtered_roles,
        "source_notes": source_notes,
        "notes_for_next_run": _string_list(run.get("notes_for_next_run", []), f"{field}.notes_for_next_run"),
        "discovery_artifacts": _string_list(run.get("discovery_artifacts", []), f"{field}.discovery_artifacts"),
    }


def normalize_digest_payload(payload: dict[str, Any], *, expected_track: str | None = None, expected_date: str | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise DigestValidationError("digest payload must be an object")
    schema_version = payload.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise DigestValidationError(f"schema_version must be {SCHEMA_VERSION}")
    track = _expect_string(payload.get("track"), "track")
    if expected_track and track != expected_track:
        raise DigestValidationError(f"track mismatch: expected {expected_track}, got {track}")
    date = _expect_string(payload.get("date"), "date")
    if expected_date and date != expected_date:
        raise DigestValidationError(f"date mismatch: expected {expected_date}, got {date}")
    runs = _expect_type(payload.get("runs"), list, "runs")
    if not runs:
        raise DigestValidationError("runs must not be empty")
    normalized_runs = [_normalize_run(run, index) for index, run in enumerate(runs)]
    if normalized_runs[0]["kind"] != "initial":
        raise DigestValidationError("runs[0].kind must be initial")
    return {
        "schema_version": SCHEMA_VERSION,
        "track": track,
        "date": date,
        "runs": normalized_runs,
    }


def load_digest_payload(path: Path, *, expected_track: str | None = None, expected_date: str | None = None) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise DigestValidationError(f"{path}: invalid JSON ({exc})") from exc
    return normalize_digest_payload(raw, expected_track=expected_track, expected_date=expected_date)


def _render_match(match: dict[str, Any], index: int) -> list[str]:
    posted = match["posted_date"] or "unknown"
    if match["updated_date"]:
        posted = f"{posted} (updated {match['updated_date']})"
    lines = [
        f"### {index}. {match['title']} — {match['company']}",
        f"Link: {match['listing_url']}",
        f"Location: {match['location'] or 'unknown'}",
        f"Remote: {match['remote'] or 'unknown'}",
        f"Team / domain: {match['team_or_domain'] or 'unknown'}",
        f"Posted: {posted}",
        f"Source: {match['source'] or 'unknown'}",
        "",
        "Why it matches:",
    ]
    why_match = match["why_match"] or ["No detailed rationale provided."]
    lines.extend(f"- {reason}" for reason in why_match)
    lines.extend(
        [
            "",
            "Possible concerns:",
        ]
    )
    concerns = match["concerns"] or ["None noted."]
    lines.extend(f"- {concern}" for concern in concerns)
    fit_score = match["fit_score"]
    score_text = "unknown" if fit_score is None else f"{fit_score:g}"
    lines.extend(
        [
            "",
            f"Fit score: {score_text}/10",
            f"Recommendation: {match['recommendation']}",
        ]
    )
    return lines


def _render_other_role(role: dict[str, Any]) -> list[str]:
    score_text = "unknown" if role["fit_score"] is None else f"{role['fit_score']:g}/10"
    lines = [
        f"- **{role['title']} — {role['company']}**",
        f"  Link: {role['listing_url']}",
        f"  Fit score: {score_text}",
        f"  Recommendation: {role['recommendation']}",
    ]
    if role["location"]:
        lines.append(f"  Location: {role['location']}")
    if role["source"]:
        lines.append(f"  Source: {role['source']}")
    lines.append(f"  Short note: {role['short_note']}")
    return lines


def _render_source_note(note: dict[str, Any]) -> str:
    listing_pages = note["listing_pages_scanned"]
    result_pages = note["result_pages_summary"]
    direct_pages = note["direct_job_pages_opened"]
    return (
        f"- {note['source']} — mode: `{note['discovery_mode']}`; "
        f"status: `{note['status']}`; "
        f"listing pages: `{listing_pages if listing_pages is not None else 'unknown'}`; "
        f"search terms: `{', '.join(note['search_terms_tried']) if note['search_terms_tried'] else 'none'}`; "
        f"result pages: `{result_pages if result_pages is not None else 'none'}`; "
        f"direct pages opened: `{direct_pages if direct_pages is not None else 'unknown'}`; "
        f"limitations: `{'; '.join(note['limitations']) if note['limitations'] else 'none'}`; "
        f"note: {note['note'] or 'none'}"
    )


def _run_counts(run: dict[str, Any]) -> tuple[int, int, int]:
    sources_checked = len(run["source_notes"])
    new_roles_found = len(run["top_matches"]) + len(run["other_new_roles"])
    high_signal_matches = len(run["top_matches"])
    return sources_checked, new_roles_found, high_signal_matches


def _seen_jobs_lines(run: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for role in [*run["top_matches"], *run["other_new_roles"]]:
        lines.append(
            f"- {role['company']} | {role['title']} | {role.get('location') or 'unknown'} | {role['listing_url']}"
        )
    return lines


def _render_run_sections(run: dict[str, Any], *, include_metadata_block: bool) -> list[str]:
    sources_checked, new_roles_found, high_signal_matches = _run_counts(run)
    lines: list[str] = []
    if include_metadata_block:
        lines.extend(
            [
                f"Run timestamp: {run['generated_at']}",
                f"Sources checked: {sources_checked}",
                f"New roles found: {new_roles_found}",
                f"High-signal matches: {high_signal_matches}",
                "",
            ]
        )
    else:
        lines.extend(
            [
                f"Run timestamp: {run['generated_at']}",
                f"Sources checked: {sources_checked}",
                f"New roles found: {new_roles_found}",
                f"High-signal matches: {high_signal_matches}",
                "",
            ]
        )

    lines.extend(["## Executive summary", "", run["executive_summary"] or "No summary provided.", ""])

    if run["recommended_actions"]:
        lines.extend(["## Recommended actions", ""])
        lines.extend(f"- {action}" for action in run["recommended_actions"])
        lines.append("")

    lines.extend(["## Top matches", ""])
    if run["top_matches"]:
        for index, match in enumerate(run["top_matches"], start=1):
            lines.extend(_render_match(match, index))
            lines.extend(["", "---", ""])
        # remove trailing separator
        lines = lines[:-2]
    else:
        lines.append("No strong matches today.")
        lines.append("")

    lines.extend(["## Other new roles worth noting", ""])
    if run["other_new_roles"]:
        for role in run["other_new_roles"]:
            lines.extend(_render_other_role(role))
            lines.append("")
    else:
        lines.append("No additional roles worth surfacing.")
        lines.append("")

    if run["filtered_roles"]:
        lines.extend(["## Roles filtered out", ""])
        lines.extend(
            f"- **{role['title']} — {role['company']}** — {role['reason_filtered_out']}"
            for role in run["filtered_roles"]
        )
        lines.append("")

    if run["source_notes"]:
        lines.extend(["## Source notes", ""])
        lines.extend(_render_source_note(note) for note in run["source_notes"])
        lines.append("")

    lines.extend(["## Seen jobs to append", ""])
    seen_jobs = _seen_jobs_lines(run)
    if seen_jobs:
        lines.extend(seen_jobs)
    else:
        lines.append("No new roles to append.")
    lines.append("")

    if run["notes_for_next_run"]:
        lines.extend(["## Notes for next run", ""])
        lines.extend(f"- {note}" for note in run["notes_for_next_run"])
        lines.append("")

    return lines


def render_digest_markdown(payload: dict[str, Any]) -> str:
    payload = normalize_digest_payload(payload)
    track = payload["track"]
    stamp = payload["date"]
    ranked_overview_page = f"{track_display_name(track)} Ranked Overview"

    lines: list[str] = [
        f"# Job Digest — {stamp}",
        f"Tags: [[job digest {track}]] [[{ranked_overview_page}]]",
        "",
        f"Track: {track}",
        "",
    ]
    lines.extend(_render_run_sections(payload["runs"][0], include_metadata_block=True))

    for run in payload["runs"][1:]:
        time_label = run["generated_at"]
        try:
            parsed = datetime.fromisoformat(time_label.replace("Z", "+00:00"))
            time_label = parsed.strftime("%H:%M")
        except ValueError:
            pass
        lines.extend([f"## Update {time_label}", ""])
        lines.extend(_render_run_sections(run, include_metadata_block=False))

    return "\n".join(lines).rstrip() + "\n"


def extract_ranked_roles(payload: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = normalize_digest_payload(payload)
    roles: list[dict[str, Any]] = []
    for run in normalized["runs"]:
        for role in [*run["top_matches"], *run["other_new_roles"]]:
            if role.get("fit_score") is None:
                continue
            roles.append(
                {
                    "company": role["company"],
                    "title": role["title"],
                    "url": role["listing_url"],
                    "fit_score": float(role["fit_score"]),
                    "location": role.get("location") or "unknown",
                }
            )
    return roles
