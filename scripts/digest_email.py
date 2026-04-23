#!/usr/bin/env python3
"""Render concise email digests from structured job-agent artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import json
from typing import Any

from digest_json import (
    DigestValidationError,
    RECENT_CUTOFF_DAYS,
    filter_recent_ranked_jobs,
    normalize_digest_payload,
    track_display_name,
)


DEFAULT_RANKED_LIMIT = 10


class DigestEmailError(ValueError):
    """Raised when email digest inputs are invalid."""


@dataclass(frozen=True)
class RenderedDigestEmail:
    subject: str
    body: str
    attachment_filename: str | None = None
    attachment_text: str | None = None


def load_json_payload(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text())
    except OSError as exc:
        raise DigestEmailError(f"{path}: cannot read JSON ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise DigestEmailError(f"{path}: invalid JSON ({exc})") from exc
    if not isinstance(raw, dict):
        raise DigestEmailError(f"{path}: JSON root must be an object")
    return raw


def normalize_ranked_payload(payload: dict[str, Any] | None, *, expected_track: str) -> dict[str, Any] | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise DigestEmailError("ranked overview payload must be an object")
    track = payload.get("track")
    if track != expected_track:
        raise DigestEmailError(f"ranked overview track mismatch: expected {expected_track}, got {track}")
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        raise DigestEmailError("ranked overview jobs must be a list")

    normalized_jobs: list[dict[str, Any]] = []
    for index, job in enumerate(jobs):
        if not isinstance(job, dict):
            raise DigestEmailError(f"ranked overview jobs[{index}] must be an object")
        company = _optional_text(job.get("company")) or "unknown"
        title = _optional_text(job.get("title")) or "unknown"
        normalized_jobs.append(
            {
                "company": company,
                "title": title,
                "url": _optional_text(job.get("url")),
                "fit_score": _optional_score(job.get("fit_score"), f"ranked overview jobs[{index}].fit_score"),
                "date_seen": _optional_text(job.get("date_seen")) or "unknown",
                "last_seen": _optional_text(job.get("last_seen")) or "unknown",
                "times_seen": _optional_int(job.get("times_seen"), f"ranked overview jobs[{index}].times_seen"),
            }
        )

    return {
        "track": expected_track,
        "generated_at": _optional_text(payload.get("generated_at")) or "unknown",
        "jobs": sorted(normalized_jobs, key=_ranked_sort_key),
    }


def render_digest_email(
    digest_payload: dict[str, Any],
    ranked_payload: dict[str, Any] | None = None,
    *,
    ranked_limit: int = DEFAULT_RANKED_LIMIT,
    as_of: date | None = None,
    recent_days: int = RECENT_CUTOFF_DAYS,
) -> RenderedDigestEmail:
    if ranked_limit < 1:
        raise DigestEmailError("ranked_limit must be at least 1")

    try:
        digest = normalize_digest_payload(digest_payload)
    except DigestValidationError as exc:
        raise DigestEmailError(str(exc)) from exc

    track = digest["track"]
    display_name = track_display_name(track)
    ranked = normalize_ranked_payload(ranked_payload, expected_track=track)
    if ranked is not None:
        ranked = {
            **ranked,
            "jobs": filter_recent_ranked_jobs(ranked["jobs"], as_of=as_of, days=recent_days),
        }
    new_roles = _new_roles(digest)
    status_counts = _source_status_counts(digest)
    subject = _render_subject(display_name, new_roles)

    lines: list[str] = [
        "Executive summary",
        _executive_summary(digest),
        "",
    ]
    actions = _recommended_actions(digest)
    if actions:
        lines.extend(["Recommended actions"])
        lines.extend(f"- {action}" for action in actions)
        lines.append("")

    lines.extend(["New jobs"])
    if new_roles:
        for index, role in enumerate(new_roles, start=1):
            lines.extend(_render_new_role(role, index))
            lines.append("")
    else:
        lines.append("No new roles found today.")
        lines.append("")

    lines.extend(_render_ranked_overview(ranked, limit=ranked_limit))
    lines.append("")
    lines.extend(
        [
            "Run metadata",
            f"Sources checked: {status_counts['complete']} complete, {status_counts['partial']} partial, {status_counts['failed']} failed.",
        ]
    )

    return RenderedDigestEmail(
        subject=subject,
        body="\n".join(lines).rstrip() + "\n",
    )


def render_ranked_overview_attachment(ranked_payload: dict[str, Any]) -> str:
    track = _optional_text(ranked_payload.get("track"))
    if track is None:
        raise DigestEmailError("ranked overview track must be non-empty")
    ranked = normalize_ranked_payload(ranked_payload, expected_track=track)
    if ranked is None:
        raise DigestEmailError("ranked overview payload is required")

    lines = [
        f"# Ranked Overview - {track_display_name(ranked['track'])}",
        "",
        f"Generated: {ranked['generated_at']}",
        f"Total jobs: {len(ranked['jobs'])}",
        "",
    ]
    lines.extend(_render_ranked_overview(ranked, limit=max(1, len(ranked["jobs"]))))
    return "\n".join(lines).rstrip() + "\n"


def _new_roles(digest: dict[str, Any]) -> list[dict[str, Any]]:
    roles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for run in digest["runs"]:
        for role in run["top_matches"]:
            normalized = _normalize_new_role(role, detailed=True)
            key = _role_key(normalized)
            if key not in seen:
                seen.add(key)
                roles.append(normalized)
        for role in run["other_new_roles"]:
            normalized = _normalize_new_role(role, detailed=False)
            key = _role_key(normalized)
            if key not in seen:
                seen.add(key)
                roles.append(normalized)
    return sorted(roles, key=_new_role_sort_key)


def _normalize_new_role(role: dict[str, Any], *, detailed: bool) -> dict[str, Any]:
    return {
        "job_key": role.get("job_key"),
        "company": role["company"],
        "title": role["title"],
        "url": role["listing_url"],
        "fit_score": role["fit_score"],
        "recommendation": role["recommendation"],
        "location": role.get("location") or "unknown",
        "remote": role.get("remote") or "unknown",
        "source": role.get("source") or "unknown",
        "why_match": role.get("why_match", []) if detailed else [],
        "concerns": role.get("concerns", []) if detailed else [],
        "short_note": role.get("short_note") if not detailed else None,
    }


def _render_new_role(role: dict[str, Any], index: int) -> list[str]:
    lines = [
        f"{index}. {role['title']} - {role['company']}",
        f"   Fit: {_format_score(role['fit_score'])}/10 | Recommendation: {role['recommendation']}",
        f"   Location: {role['location']} | Remote: {role['remote']}",
        f"   Source: {role['source']}",
        f"   Link: {role['url']}",
    ]
    if role["why_match"]:
        lines.append("")
        lines.append("   Why:")
        lines.extend(f"   - {reason}" for reason in role["why_match"])
    if role["short_note"]:
        lines.append("")
        lines.append(f"   Note: {role['short_note']}")
    if role["concerns"]:
        lines.append("")
        lines.append("   Concerns:")
        lines.extend(f"   - {concern}" for concern in role["concerns"])
    return lines


def _render_ranked_overview(ranked: dict[str, Any] | None, *, limit: int) -> list[str]:
    if ranked is None:
        return [
            "Ranked overview",
            "Ranked overview unavailable.",
        ]

    jobs = ranked["jobs"]
    shown_jobs = jobs[:limit]
    lines = [
        f"Ranked overview (top {len(shown_jobs)} of {len(jobs)})",
    ]
    if not shown_jobs:
        lines.append("No ranked jobs yet.")
        return lines

    for index, job in enumerate(shown_jobs, start=1):
        date_line = f"   Date seen: {job['date_seen']}"
        if job["last_seen"] != job["date_seen"]:
            date_line = f"{date_line} | Last seen: {job['last_seen']}"
        lines.extend(
            [
                f"{index}. {_format_score(job['fit_score'])}/10 - {job['title']} - {job['company']}",
                date_line,
            ]
        )
        if job["url"]:
            lines.append(f"   Link: {job['url']}")
    return lines


def _render_subject(display_name: str, new_roles: list[dict[str, Any]]) -> str:
    if not new_roles:
        return f"{display_name} job digest: no new roles"
    top_score = max((role["fit_score"] for role in new_roles if role["fit_score"] is not None), default=None)
    score_suffix = "" if top_score is None else f", top score {_format_score(top_score)}"
    role_label = "role" if len(new_roles) == 1 else "roles"
    return f"{display_name} job digest: {len(new_roles)} new {role_label}{score_suffix}"


def _executive_summary(digest: dict[str, Any]) -> str:
    summaries = [run["executive_summary"] for run in digest["runs"] if run["executive_summary"]]
    if not summaries:
        return "No summary provided."
    return " ".join(summaries)


def _recommended_actions(digest: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    seen: set[str] = set()
    for run in digest["runs"]:
        for action in run["recommended_actions"]:
            if action not in seen:
                seen.add(action)
                actions.append(action)
    return actions


def _source_status_counts(digest: dict[str, Any]) -> dict[str, int]:
    counts = {"complete": 0, "partial": 0, "failed": 0}
    for run in digest["runs"]:
        for note in run["source_notes"]:
            counts[note["status"]] += 1
    return counts


def _role_key(role: dict[str, Any]) -> str:
    key = _optional_text(role.get("job_key")) or _optional_text(role.get("url"))
    if key:
        return key.lower()
    return f"{role['company']}|{role['title']}".lower()


def _new_role_sort_key(role: dict[str, Any]) -> tuple[float, str, str]:
    score = role["fit_score"] if role["fit_score"] is not None else -1.0
    return (-float(score), role["company"].lower(), role["title"].lower())


def _ranked_sort_key(job: dict[str, Any]) -> tuple[float, str, str, str]:
    score = job["fit_score"] if job["fit_score"] is not None else -1.0
    return (-float(score), job["date_seen"], job["company"].lower(), job["title"].lower())


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_score(value: Any, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DigestEmailError(f"{field} must be numeric or null")
    return float(value)


def _optional_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise DigestEmailError(f"{field} must be integer or null")
    return value


def _format_score(value: float | int | None) -> str:
    if value is None:
        return "unknown"
    return f"{float(value):g}"
