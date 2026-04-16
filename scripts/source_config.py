#!/usr/bin/env python3
"""Shared helpers for track source configuration and state."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any


VALID_CADENCE_GROUPS = {"every_run", "every_3_runs", "every_month"}
VALID_SEARCH_TERM_MODES = {"append", "override"}


class SourceConfigError(ValueError):
    """Raised when a track source configuration is invalid."""


def slugify_source_id(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", normalized).strip("_").lower()
    return slug or "source"


def unique_source_id(name: str, used: set[str]) -> str:
    base = slugify_source_id(name)
    candidate = base
    index = 2
    while candidate in used:
        candidate = f"{base}_{index}"
        index += 1
    used.add(candidate)
    return candidate


def read_json_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise SourceConfigError(f"Missing required source config: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SourceConfigError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SourceConfigError(f"{path} must contain a JSON object")
    return payload


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    temp_path.replace(path)


def _expect_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceConfigError(f"{field} must be a non-empty string")
    return value.strip()


def _expect_optional_date(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SourceConfigError(f"{field} must be null or an ISO date string")
    stripped = value.strip()
    if not stripped:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", stripped):
        raise SourceConfigError(f"{field} must use YYYY-MM-DD")
    return stripped


def _expect_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise SourceConfigError(f"{field} must be a list")
    strings: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise SourceConfigError(f"{field}[{index}] must be a non-empty string")
        strings.append(item.strip())
    return strings


def _normalize_search_terms(value: Any, field: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise SourceConfigError(f"{field} must be an object")
    mode = value.get("mode", "append")
    if mode not in VALID_SEARCH_TERM_MODES:
        raise SourceConfigError(f"{field}.mode must be one of: append, override")
    terms = _expect_string_list(value.get("terms"), f"{field}.terms")
    return {"mode": mode, "terms": terms}


def _normalize_filters(value: Any, field: str) -> dict[str, list[str]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise SourceConfigError(f"{field} must be an object")
    filters: dict[str, list[str]] = {}
    for key, raw_values in value.items():
        if not isinstance(key, str) or not key.strip():
            raise SourceConfigError(f"{field} keys must be non-empty strings")
        values = _expect_string_list(raw_values, f"{field}.{key}")
        filters[key.strip()] = values
    return filters


def load_sources_config(path: Path, track: str) -> dict[str, Any]:
    payload = read_json_payload(path)
    if payload.get("schema_version") != 1:
        raise SourceConfigError(f"{path} schema_version must be 1")
    payload_track = _expect_string(payload.get("track"), f"{path}.track")
    if payload_track != track:
        raise SourceConfigError(f"{path} track must be {track!r}, got {payload_track!r}")
    track_terms = _expect_string_list(payload.get("track_terms"), f"{path}.track_terms")
    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list):
        raise SourceConfigError(f"{path}.sources must be a list")

    seen_ids: set[str] = set()
    sources: list[dict[str, Any]] = []
    for index, raw_source in enumerate(raw_sources):
        field = f"{path}.sources[{index}]"
        if not isinstance(raw_source, dict):
            raise SourceConfigError(f"{field} must be an object")
        source_id = _expect_string(raw_source.get("id"), f"{field}.id")
        if source_id in seen_ids:
            raise SourceConfigError(f"{field}.id duplicates source id {source_id!r}")
        seen_ids.add(source_id)
        cadence_group = _expect_string(raw_source.get("cadence_group"), f"{field}.cadence_group")
        if cadence_group not in VALID_CADENCE_GROUPS:
            raise SourceConfigError(f"{field}.cadence_group must be one of: {', '.join(sorted(VALID_CADENCE_GROUPS))}")
        source: dict[str, Any] = {
            "id": source_id,
            "name": _expect_string(raw_source.get("name"), f"{field}.name"),
            "url": _expect_string(raw_source.get("url"), f"{field}.url"),
            "discovery_mode": _expect_string(raw_source.get("discovery_mode"), f"{field}.discovery_mode"),
            "cadence_group": cadence_group,
            "filters": _normalize_filters(raw_source.get("filters"), f"{field}.filters"),
        }
        search_terms = _normalize_search_terms(raw_source.get("search_terms"), f"{field}.search_terms")
        if search_terms:
            source["search_terms"] = search_terms
        sources.append(source)

    return {
        "schema_version": 1,
        "track": track,
        "track_terms": track_terms,
        "sources": sources,
    }


def load_source_state(path: Path, track: str) -> dict[str, str | None]:
    if not path.exists():
        return {}
    payload = read_json_payload(path)
    if payload.get("schema_version") != 1:
        raise SourceConfigError(f"{path} schema_version must be 1")
    payload_track = _expect_string(payload.get("track"), f"{path}.track")
    if payload_track != track:
        raise SourceConfigError(f"{path} track must be {track!r}, got {payload_track!r}")
    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, dict):
        raise SourceConfigError(f"{path}.sources must be an object")
    state: dict[str, str | None] = {}
    for source_id, raw_state in raw_sources.items():
        if not isinstance(source_id, str) or not source_id.strip():
            raise SourceConfigError(f"{path}.sources keys must be non-empty strings")
        field = f"{path}.sources.{source_id}"
        if not isinstance(raw_state, dict):
            raise SourceConfigError(f"{field} must be an object")
        state[source_id] = _expect_optional_date(raw_state.get("last_checked"), f"{field}.last_checked")
    return state


def source_state_payload(track: str, source_ids: list[str], state: dict[str, str | None]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "track": track,
        "sources": {source_id: {"last_checked": state.get(source_id)} for source_id in source_ids},
    }


def _markdown_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").strip()


def _cadence_heading(cadence_group: str) -> str:
    return {
        "every_run": "Check every run",
        "every_3_runs": "Check every 3 runs",
        "every_month": "Check every month",
    }[cadence_group]


def render_sources_markdown(config: dict[str, Any]) -> str:
    track = str(config["track"])
    title = track.replace("_", " ").title()
    lines: list[str] = [
        f"# {title} sources",
        "",
        "> Generated read-only summary. Do not edit this file directly.",
        "> Source definitions live in `sources.json`; cadence state lives in `source_state.json`.",
        "> To change sources, invoke the set-up or source-curation agent.",
        "",
        "Only check the sources below for this track.",
        "",
        "Do not waste time on broad employer pages outside this list.",
        "",
        "Cadence note:",
        "- For `Check every 3 runs`, treat one scheduled day as one run.",
        "- For `Check every month`, recheck once the calendar month changes.",
        "- Manual same-day reruns do not advance cadence.",
        "- `discovery_mode` is used by `../../scripts/discover_jobs.py` for deterministic source coverage.",
        "",
    ]

    sources = list(config["sources"])
    for cadence_group in ("every_run", "every_3_runs", "every_month"):
        lines.extend([f"## {_cadence_heading(cadence_group)}", ""])
        lines.extend(["| source | url | discovery_mode |", "| --- | --- | --- |"])
        for source in sources:
            if source["cadence_group"] != cadence_group:
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_cell(source["name"]),
                        _markdown_cell(source["url"]),
                        _markdown_cell(source["discovery_mode"]),
                    ]
                )
                + " |"
            )
        lines.append("")

    lines.extend(
        [
            "## Search terms",
            "",
            "Use these terms on searchable sources unless a source-specific search-term override says otherwise.",
            "",
            "### Track-wide terms",
            "",
        ]
    )
    track_terms = list(config["track_terms"])
    if track_terms:
        lines.extend(f"- {term}" for term in track_terms)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "### Source-specific search terms",
            "",
            "Use these in addition to the track-wide terms when the source has native search and these terms are a better fit for that source's vocabulary.",
            "",
            "Add `[override]` after the source name to replace the track-wide terms for that source.",
            "",
        ]
    )
    source_term_lines = []
    for source in sources:
        search_terms = source.get("search_terms")
        if not search_terms:
            continue
        marker = " [override]" if search_terms.get("mode") == "override" else ""
        source_term_lines.append(f"- {source['name']}{marker} — {', '.join(search_terms['terms'])}")
    lines.extend(source_term_lines or ["- none"])

    lines.extend(
        [
            "",
            "### Source-specific filters",
            "",
            "Use these native filters on searchable sources when the source supports stable URL or API filters.",
            "",
        ]
    )
    filter_lines = []
    for source in sources:
        filters = source.get("filters") or {}
        if not filters:
            continue
        parts = [f"{key}: {'; '.join(values)}" for key, values in filters.items()]
        filter_lines.append(f"- {source['name']} — {' | '.join(parts)}")
    lines.extend(filter_lines or ["- none"])

    lines.extend(
        [
            "",
            "## Output discipline",
            "",
            "- If a source has no relevant role, omit it from the digest.",
            "- Never report a role already listed in ./seen_jobs.json",
            "- Prefer 3-8 strong matches over a long noisy list.",
            "- Include direct job links in the digest, not just the company careers page.",
            "",
        ]
    )
    return "\n".join(lines)
