#!/usr/bin/env python3
"""Render concise email digests from structured job-agent artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import json
import re
from typing import Any

from digest_json import (
    DigestValidationError,
    RECENT_CUTOFF_DAYS,
    filter_recent_ranked_jobs,
    normalize_digest_payload,
    track_display_name,
)


# None means "show every ranked job" (no cap). Callers may still pass an
# explicit positive integer to limit the rows shown.
DEFAULT_RANKED_LIMIT: int | None = None


class DigestEmailError(ValueError):
    """Raised when email digest inputs are invalid."""


@dataclass(frozen=True)
class RenderedDigestEmail:
    subject: str
    body: str
    html_body: str | None = None
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
    ranked_limit: int | None = DEFAULT_RANKED_LIMIT,
    as_of: date | None = None,
    recent_days: int = RECENT_CUTOFF_DAYS,
) -> RenderedDigestEmail:
    if ranked_limit is not None and ranked_limit < 1:
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

    html_body = _render_html_email(
        display_name=display_name,
        as_of=as_of,
        summary=_html_executive_summary(digest),
        actions_with_priority=_recommended_actions_with_priority(digest),
        new_roles=new_roles,
        ranked=ranked,
        ranked_limit=ranked_limit,
        status_counts=status_counts,
    )

    return RenderedDigestEmail(
        subject=subject,
        body="\n".join(lines).rstrip() + "\n",
        html_body=html_body,
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


def _render_ranked_overview(ranked: dict[str, Any] | None, *, limit: int | None) -> list[str]:
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


def _html_executive_summary(digest: dict[str, Any]) -> str:
    """Return only the initial run's summary for email display (avoids same-day update noise)."""
    for run in digest["runs"]:
        if run.get("kind") == "initial" and run.get("executive_summary"):
            return run["executive_summary"]
    # Fallback: first non-empty summary
    for run in digest["runs"]:
        if run.get("executive_summary"):
            return run["executive_summary"]
    return "No summary provided."


_ACTION_HIGH_WORDS = ("prioritize", "apply", "tailor an application", "submit", "reach out", "send")
_ACTION_LOW_WORDS = ("defer", "no new action", "flag ", "skip", "no action", "out of scope")


def _action_priority(action: str) -> str:
    lower = action.lower()
    if any(w in lower for w in _ACTION_HIGH_WORDS):
        return "high"
    if any(w in lower for w in _ACTION_LOW_WORDS):
        return "low"
    return "mid"


def _recommended_actions(digest: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    seen: set[str] = set()
    for run in digest["runs"]:
        for action in run["recommended_actions"]:
            if action not in seen:
                seen.add(action)
                actions.append(action)
    return actions


def _recommended_actions_with_priority(digest: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (action_text, priority) pairs, deduped, sorted high→mid→low."""
    seen: set[str] = set()
    items: list[tuple[str, str]] = []
    for run in digest["runs"]:
        for action in run["recommended_actions"]:
            if action not in seen:
                seen.add(action)
                items.append((action, _action_priority(action)))
    order = {"high": 0, "mid": 1, "low": 2}
    return sorted(items, key=lambda x: order[x[1]])


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


# ---------------------------------------------------------------------------
# HTML email renderer
# ---------------------------------------------------------------------------

_HTML_SCORE_COLORS = {
    "high": ("#16a34a", "#dcfce7"),    # green: score >= 8
    "mid": ("#c2410c", "#ffedd5"),     # orange: score >= 6
    "low": ("#6b7280", "#f3f4f6"),     # gray: score < 6
}

_HTML_REC_LABELS: dict[str, tuple[str, str]] = {
    "apply_now": ("#15803d", "Apply now"),
    "apply": ("#15803d", "Apply"),
    "watch": ("#b45309", "Watch"),
    "defer": ("#6b7280", "Defer"),
    "skip": ("#6b7280", "Skip"),
}


# Split on sentence-ending punctuation followed by whitespace and the start of
# the next sentence (capital letter or digit). The lookbehind/lookahead avoid
# breaking on decimals like "8.5" or mid-sentence abbreviations.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def _summary_sentences(text: str) -> list[str]:
    """Split a prose summary into trimmed sentences for bulleted display."""
    return [part.strip() for part in _SENTENCE_SPLIT_RE.split(text.strip()) if part.strip()]


def _h(text: Any) -> str:
    """HTML-escape a value."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _score_colors(score: float | None) -> tuple[str, str]:
    if score is None:
        return _HTML_SCORE_COLORS["low"]
    if score >= 8:
        return _HTML_SCORE_COLORS["high"]
    if score >= 6:
        return _HTML_SCORE_COLORS["mid"]
    return _HTML_SCORE_COLORS["low"]


def _rec_label(recommendation: str | None) -> tuple[str, str]:
    if recommendation and recommendation.lower() in _HTML_REC_LABELS:
        return _HTML_REC_LABELS[recommendation.lower()]
    return ("#6b7280", _h(recommendation or "unknown"))


def _render_html_role_card(role: dict[str, Any], index: int) -> str:
    score = role["fit_score"]
    score_fg, score_bg = _score_colors(score)
    score_text = _format_score(score)
    rec_color, rec_text = _rec_label(role.get("recommendation"))

    location_parts = []
    loc = _optional_text(role.get("location"))
    remote = _optional_text(role.get("remote"))
    if loc and loc != "unknown":
        location_parts.append(_h(loc))
    if remote and remote != "unknown":
        location_parts.append(_h(remote))
    location_line = " &nbsp;·&nbsp; ".join(location_parts) if location_parts else "Location unknown"

    why_html = ""
    if role.get("why_match"):
        items = "".join(f'<li style="margin-bottom:4px;">{_h(r)}</li>' for r in role["why_match"])
        why_html = f'<p style="margin:12px 0 4px;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.6px;color:#888;">Why it fits</p><ul style="margin:0;padding-left:18px;color:#374151;font-size:14px;line-height:1.6;">{items}</ul>'

    note_html = ""
    if role.get("short_note"):
        note_html = f'<p style="margin:10px 0 0;font-size:13px;color:#6b7280;font-style:italic;">{_h(role["short_note"])}</p>'

    concerns_html = ""
    if role.get("concerns"):
        items = "".join(f'<li style="margin-bottom:4px;">{_h(c)}</li>' for c in role["concerns"])
        concerns_html = f'<p style="margin:12px 0 4px;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.6px;color:#b45309;">Concerns</p><ul style="margin:0;padding-left:18px;color:#92400e;font-size:14px;line-height:1.6;">{items}</ul>'

    url = _optional_text(role.get("url")) or "#"

    return f"""
<div style="background:#fff;border:1px solid #e5e7eb;border-radius:8px;margin-bottom:16px;overflow:hidden;">
  <div style="padding:18px 20px 14px;">
    <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
      <td style="vertical-align:top;">
        <div style="font-size:16px;font-weight:700;color:#111827;line-height:1.3;">{_h(role["title"])}</div>
        <div style="font-size:14px;color:#6b7280;margin-top:2px;">{_h(role["company"])}</div>
      </td>
      <td style="vertical-align:top;text-align:right;white-space:nowrap;padding-left:12px;">
        <span style="display:inline-block;background:{score_bg};color:{score_fg};font-size:15px;font-weight:700;padding:3px 10px;border-radius:20px;">{score_text}</span>
      </td>
    </tr></table>
    <div style="margin-top:10px;font-size:13px;color:#6b7280;">
      📍 {location_line}
      &nbsp;&nbsp;
      <span style="color:{rec_color};font-weight:600;">{rec_text}</span>
    </div>
    {why_html}
    {note_html}
    {concerns_html}
    <div style="margin-top:16px;">
      <a href="{_h(url)}" style="display:inline-block;background:#1e293b;color:#fff;text-decoration:none;padding:7px 16px;border-radius:5px;font-size:13px;font-weight:600;">View listing →</a>
    </div>
  </div>
</div>"""


def _render_html_ranked_row(job: dict[str, Any], index: int) -> str:
    score_fg, _ = _score_colors(job.get("fit_score"))
    score_text = _format_score(job.get("fit_score"))
    url = _optional_text(job.get("url"))
    title_cell = f'<a href="{_h(url)}" style="color:#1e293b;text-decoration:none;font-weight:600;">{_h(job["title"])}</a>' if url else f'<strong>{_h(job["title"])}</strong>'
    bg = "#f9fafb" if index % 2 == 0 else "#ffffff"
    return (
        f'<tr style="background:{bg};">'
        f'<td style="padding:8px 12px;font-size:13px;color:{score_fg};font-weight:700;">{score_text}</td>'
        f'<td style="padding:8px 12px;font-size:13px;">{title_cell}</td>'
        f'<td style="padding:8px 12px;font-size:13px;color:#6b7280;">{_h(job["company"])}</td>'
        f'<td style="padding:8px 12px;font-size:13px;color:#9ca3af;white-space:nowrap;">{_h(job.get("date_seen",""))}</td>'
        f'</tr>'
    )


_PRIORITY_BADGE: dict[str, tuple[str, str, str]] = {
    # priority: (bg, text-color, label)
    "high": ("#fef2f2", "#b91c1c", "High"),
    "mid":  ("#fffbeb", "#92400e", "Mid"),
    "low":  ("#f9fafb", "#6b7280", "Low"),
}


def _render_html_email(
    *,
    display_name: str,
    as_of: date | None,
    summary: str,
    actions_with_priority: list[tuple[str, str]],
    new_roles: list[dict[str, Any]],
    ranked: dict[str, Any] | None,
    ranked_limit: int | None,
    status_counts: dict[str, int],
) -> str:
    date_str = as_of.isoformat() if as_of else date.today().isoformat()

    # --- executive summary ---
    summary_sentences = _summary_sentences(summary)
    if len(summary_sentences) > 1:
        summary_items = "".join(
            f'<li style="margin:0 0 8px;">{_h(sentence)}</li>' for sentence in summary_sentences
        )
        summary_html = (
            '<ul style="margin:0;padding-left:20px;font-size:14px;line-height:1.6;color:#374151;">'
            f"{summary_items}</ul>"
        )
    else:
        summary_html = f'<p style="margin:0;font-size:14px;line-height:1.7;color:#374151;">{_h(summary)}</p>'

    # --- recommended actions with priority badges ---
    actions_html = ""
    if actions_with_priority:
        rows = []
        for action_text, priority in actions_with_priority:
            bg, fg, label = _PRIORITY_BADGE[priority]
            badge = (
                f'<span style="display:inline-block;background:{bg};color:{fg};'
                f'font-size:11px;font-weight:700;padding:1px 7px;border-radius:10px;'
                f'margin-right:8px;white-space:nowrap;">{label}</span>'
            )
            rows.append(
                f'<li style="margin-bottom:8px;font-size:14px;line-height:1.5;color:#374151;list-style:none;">'
                f'{badge}{_h(action_text)}</li>'
            )
        items = "".join(rows)
        actions_html = f"""
<div style="margin-top:24px;">
  <h2 style="margin:0 0 10px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#9ca3af;">Recommended actions</h2>
  <ul style="margin:0;padding-left:0;">{items}</ul>
</div>"""

    # --- new roles ---
    if new_roles:
        role_cards = "".join(_render_html_role_card(r, i) for i, r in enumerate(new_roles, 1))
        roles_html = f"""
<div style="margin-top:28px;">
  <h2 style="margin:0 0 14px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#9ca3af;">New roles ({len(new_roles)})</h2>
  {role_cards}
</div>"""
    else:
        roles_html = """
<div style="margin-top:28px;">
  <h2 style="margin:0 0 10px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#9ca3af;">New roles</h2>
  <p style="margin:0;font-size:14px;color:#9ca3af;">No new roles found today.</p>
</div>"""

    # --- ranked overview ---
    ranked_html = ""
    if ranked:
        shown = ranked["jobs"][:ranked_limit]
        if shown:
            rows = "".join(_render_html_ranked_row(j, i) for i, j in enumerate(shown, 1))
            ranked_html = f"""
<div style="margin-top:28px;">
  <h2 style="margin:0 0 12px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#9ca3af;">Ranked overview (top {len(shown)} of {len(ranked["jobs"])})</h2>
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #e5e7eb;border-radius:6px;overflow:hidden;font-family:Arial,sans-serif;">
    <tr style="background:#f3f4f6;">
      <th style="padding:8px 12px;text-align:left;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#9ca3af;">Score</th>
      <th style="padding:8px 12px;text-align:left;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#9ca3af;">Role</th>
      <th style="padding:8px 12px;text-align:left;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#9ca3af;">Company</th>
      <th style="padding:8px 12px;text-align:left;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#9ca3af;">First seen</th>
    </tr>
    {rows}
  </table>
</div>"""

    # --- footer metadata ---
    meta_html = f"""
<div style="margin-top:28px;padding-top:16px;border-top:1px solid #e5e7eb;font-size:12px;color:#9ca3af;">
  Sources: {status_counts["complete"]} complete &nbsp;·&nbsp; {status_counts["partial"]} partial &nbsp;·&nbsp; {status_counts["failed"]} failed
</div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_h(display_name)} job digest</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;-webkit-text-size-adjust:100%;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f1f5f9;">
<tr><td align="center" style="padding:24px 16px;">
<table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;">

  <!-- Header -->
  <tr><td style="background:#0f172a;border-radius:8px 8px 0 0;padding:24px 28px;">
    <div style="color:#fff;font-size:20px;font-weight:700;">{_h(display_name)}</div>
    <div style="color:#94a3b8;font-size:13px;margin-top:4px;">Job digest &nbsp;·&nbsp; {_h(date_str)}</div>
  </td></tr>

  <!-- Body -->
  <tr><td style="background:#ffffff;border-radius:0 0 8px 8px;padding:24px 28px 28px;">
    <h2 style="margin:0 0 10px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#9ca3af;">Executive summary</h2>
    {summary_html}
    {actions_html}
    {roles_html}
    {ranked_html}
    {meta_html}
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""
