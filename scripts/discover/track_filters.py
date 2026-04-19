"""Structured post-discovery track filtering rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from discover import helpers
from discover.core import Candidate, Coverage


DEFAULT_TRACKS_ROOT = Path(__file__).resolve().parents[2] / "tracks"


def candidate_searchable_text(candidate: Candidate) -> str:
    return helpers.normalize_for_matching(
        " ".join(
            part
            for part in [
                candidate.employer,
                candidate.title,
                candidate.location,
                candidate.notes,
                candidate.url,
                candidate.alternate_url,
            ]
            if part
        )
    )


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field}[{index}] must be a non-empty string")
        result.append(item.strip())
    return result


def load_track_match_rules(track: str, tracks_root: Path = DEFAULT_TRACKS_ROOT) -> list[dict[str, Any]]:
    path = tracks_root / track / "match_rules.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text())
    if payload.get("schema_version") != 1:
        raise ValueError(f"{path} schema_version must be 1")
    if payload.get("track") != track:
        raise ValueError(f"{path} track must be {track!r}")
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list):
        raise ValueError(f"{path}.rules must be a list")

    rules: list[dict[str, Any]] = []
    for index, raw_rule in enumerate(raw_rules):
        field = f"{path}.rules[{index}]"
        if not isinstance(raw_rule, dict):
            raise ValueError(f"{field} must be an object")
        rule_id = raw_rule.get("id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise ValueError(f"{field}.id must be a non-empty string")
        rule = {
            "id": rule_id.strip(),
            "source_ids": _string_list(raw_rule.get("source_ids", []), f"{field}.source_ids"),
            "source_names": _string_list(raw_rule.get("source_names", []), f"{field}.source_names"),
            "keep_if_any_text_term": _string_list(
                raw_rule.get("keep_if_any_text_term", []),
                f"{field}.keep_if_any_text_term",
            ),
        }
        if not rule["source_ids"] and not rule["source_names"]:
            raise ValueError(f"{field} must include source_ids or source_names")
        if not rule["keep_if_any_text_term"]:
            raise ValueError(f"{field}.keep_if_any_text_term must not be empty")
        limitation = raw_rule.get("limitation")
        if limitation is not None and not isinstance(limitation, str):
            raise ValueError(f"{field}.limitation must be a string")
        rule["limitation"] = limitation or "Track match rule {rule_id} removed {removed} candidate(s)."
        rules.append(rule)
    return rules


def _rule_applies(rule: dict[str, Any], coverage: Coverage) -> bool:
    source_ids = set(rule["source_ids"])
    source_names = set(rule["source_names"])
    if coverage.source_id and coverage.source_id in source_ids:
        return True
    return coverage.source in source_names


def _candidate_matches_rule(candidate: Candidate, rule: dict[str, Any]) -> bool:
    haystack = candidate_searchable_text(candidate)
    return any(helpers.normalize_for_matching(term) in haystack for term in rule["keep_if_any_text_term"])


def filter_coverage_for_track(
    track: str,
    coverage: Coverage,
    tracks_root: Path = DEFAULT_TRACKS_ROOT,
) -> Coverage:
    for rule in load_track_match_rules(track, tracks_root):
        if not _rule_applies(rule, coverage):
            continue
        kept_candidates = [candidate for candidate in coverage.candidates if _candidate_matches_rule(candidate, rule)]
        removed = len(coverage.candidates) - len(kept_candidates)
        if removed <= 0:
            continue
        coverage.candidates = kept_candidates
        coverage.matched_jobs = len(kept_candidates)
        limitation = rule["limitation"].format(removed=removed, rule_id=rule["id"])
        coverage.limitations = list(dict.fromkeys([*coverage.limitations, limitation]))
    return coverage
