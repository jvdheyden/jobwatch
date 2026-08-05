#!/usr/bin/env python3
"""Validated, bounded JSON contracts for guided track setup workers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import SplitResult, urlsplit, urlunsplit

from digest_json import normalize_digest_payload
from discover.helpers import match_terms
from discover.registry import load_registry
from discover.track_filters import normalize_track_match_rules_payload
from source_config import SourceConfigError, normalize_sources_payload
from update_seen_jobs import load_seen_jobs


SCHEMA_VERSION = 1
SETUP_KIND = "jobwatch_setup"
SOURCE_PACK_KIND = "jobwatch_source_pack"
PREVIEW_CONTEXT_KIND = "jobwatch_preview_context"
PREVIEW_RESULT_KIND = "jobwatch_preview_result"

SETUP_MAX_BYTES = 32 * 1024
SOURCE_PACK_MAX_BYTES = 128 * 1024
PREVIEW_CONTEXT_MAX_BYTES = 256 * 1024
PREVIEW_RESULT_MAX_BYTES = 128 * 1024
PROVIDER_RESPONSE_MAX_BYTES = 1024 * 1024

MAX_PRIMARY_SOURCES = 8
MAX_FOLLOW_UP_SOURCES = 4
MAX_URL_CORRECTIONS = 3
MAX_PREVIEW_CANDIDATES = 40
MAX_DESCRIPTION_BYTES = 12 * 1024

SETUP_ID_RE = re.compile(r"^\d{8}T\d{6}Z-[a-z0-9]{8}$")
TRACK_SLUG_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
IDENTIFIER_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
MODEL_OUTPUT_ID_RE = re.compile(r"^candidate_[a-f0-9]{16}$")
SECRET_KEY_RE = re.compile(r"(^|_)(api_?key|credential|password|passwd|secret|token)(_|$)")
FORBIDDEN_KEYS = {
    "conversation",
    "cv_text",
    "delivery_credentials",
    "env_dump",
    "environment_dump",
    "full_cv",
    "prompt",
    "prompts",
    "resume_text",
    "transcript",
}


class SetupContractError(ValueError):
    """Raised when a setup boundary artifact is invalid."""


def new_setup_id(now: datetime | None = None, *, entropy: str | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = entropy or os.urandom(4).hex()
    if not re.fullmatch(r"[a-z0-9]{8}", suffix):
        raise SetupContractError("setup id entropy must contain exactly eight lowercase letters or digits")
    return f"{stamp}-{suffix}"


def _reject_sensitive_keys(value: Any, field: str = "artifact") -> None:
    if isinstance(value, dict):
        for raw_key, nested in value.items():
            if not isinstance(raw_key, str):
                raise SetupContractError(f"{field} keys must be strings")
            key = raw_key.strip().lower().replace("-", "_")
            if key in FORBIDDEN_KEYS or SECRET_KEY_RE.search(key):
                raise SetupContractError(f"{field}.{raw_key} is forbidden in setup artifacts")
            _reject_sensitive_keys(nested, f"{field}.{raw_key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_sensitive_keys(nested, f"{field}[{index}]")


def _expect_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SetupContractError(f"{field} must be an object")
    return value


def _expect_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise SetupContractError(f"{field} must be a list")
    return value


def _expect_keys(value: Mapping[str, Any], allowed: set[str], field: str, *, required: set[str] | None = None) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise SetupContractError(f"{field} contains unknown fields: {', '.join(unknown)}")
    missing = sorted((required or allowed) - set(value))
    if missing:
        raise SetupContractError(f"{field} is missing required fields: {', '.join(missing)}")


def _text(value: Any, field: str, *, allow_empty: bool = False, max_chars: int = 2000) -> str:
    if not isinstance(value, str):
        raise SetupContractError(f"{field} must be a string")
    normalized = " ".join(value.split())
    if not allow_empty and not normalized:
        raise SetupContractError(f"{field} must be non-empty")
    if len(normalized) > max_chars:
        raise SetupContractError(f"{field} exceeds {max_chars} characters")
    return normalized


def _text_list(
    value: Any,
    field: str,
    *,
    max_items: int = 50,
    max_chars: int = 500,
) -> list[str]:
    items = _expect_list(value, field)
    if len(items) > max_items:
        raise SetupContractError(f"{field} exceeds {max_items} items")
    result: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        normalized = _text(item, f"{field}[{index}]", max_chars=max_chars)
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _setup_id(value: Any, field: str = "setup_id") -> str:
    candidate = _text(value, field, max_chars=40)
    if not SETUP_ID_RE.fullmatch(candidate):
        raise SetupContractError(f"{field} must use YYYYMMDDTHHMMSSZ-xxxxxxxx")
    return candidate


def normalize_track_slug(value: Any, field: str = "track.slug") -> str:
    candidate = _text(value, field, max_chars=64)
    if not TRACK_SLUG_RE.fullmatch(candidate):
        raise SetupContractError(f"{field} must be a lowercase underscore slug and a safe child of tracks/")
    return candidate


def _identifier(value: Any, field: str) -> str:
    candidate = _text(value, field, max_chars=80)
    if not IDENTIFIER_RE.fullmatch(candidate):
        raise SetupContractError(f"{field} must be a lowercase underscore identifier")
    return candidate


def normalize_url(value: Any, field: str) -> str:
    candidate = _text(value, field, max_chars=4096)
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SetupContractError(f"{field} must be an absolute http(s) URL")
    if parsed.username or parsed.password:
        raise SetupContractError(f"{field} must not contain credentials")
    host = parsed.hostname.lower()
    if parsed.scheme == "http" and host not in {"127.0.0.1", "localhost", "::1"}:
        raise SetupContractError(f"{field} must use https (http is allowed only for loopback fixtures)")
    try:
        port = parsed.port
    except ValueError as exc:
        raise SetupContractError(f"{field} contains an invalid port") from exc
    if port is None or (parsed.scheme == "https" and port == 443) or (parsed.scheme == "http" and port == 80):
        netloc = host
    else:
        netloc = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    normalized = SplitResult(parsed.scheme.lower(), netloc, path, parsed.query, "")
    return urlunsplit(normalized)


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def artifact_hash(payload: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _assert_size(payload: Any, max_bytes: int, field: str) -> None:
    size = len(_canonical_json_bytes(payload))
    if size > max_bytes:
        raise SetupContractError(f"{field} is {size} bytes; limit is {max_bytes} bytes")


def read_json_limited(path: Path, max_bytes: int, field: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SetupContractError(f"cannot read {path}: {exc}") from exc
    if len(raw) > max_bytes:
        raise SetupContractError(f"{field} is {len(raw)} bytes; limit is {max_bytes} bytes")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SetupContractError(f"{path} contains invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SetupContractError(f"{path} must contain a JSON object")
    return payload


def write_json_atomic(path: Path, payload: dict[str, Any], *, max_bytes: int) -> None:
    encoded = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    if len(encoded) > max_bytes:
        raise SetupContractError(f"{path.name} is {len(encoded)} bytes; limit is {max_bytes} bytes")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False) as handle:
            temp_name = handle.name
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if temp_name:
            try:
                Path(temp_name).unlink()
            except FileNotFoundError:
                pass


def _normalize_profile(value: Any, field: str = "profile") -> dict[str, Any]:
    raw = _expect_object(value, field)
    keys = {
        "user_name",
        "seniority",
        "skills",
        "experience_signals",
        "positive_signals",
        "borderline_signals",
        "current_or_recent_employers",
    }
    _expect_keys(raw, keys, field)
    return {
        "user_name": _text(raw["user_name"], f"{field}.user_name", max_chars=200),
        "seniority": _text_list(raw["seniority"], f"{field}.seniority", max_items=10),
        "skills": _text_list(raw["skills"], f"{field}.skills", max_items=40),
        "experience_signals": _text_list(raw["experience_signals"], f"{field}.experience_signals", max_items=30),
        "positive_signals": _text_list(raw["positive_signals"], f"{field}.positive_signals", max_items=30),
        "borderline_signals": _text_list(raw["borderline_signals"], f"{field}.borderline_signals", max_items=30),
        "current_or_recent_employers": _text_list(
            raw["current_or_recent_employers"], f"{field}.current_or_recent_employers", max_items=10
        ),
    }


def _normalize_track(value: Any, field: str = "track") -> dict[str, Any]:
    raw = _expect_object(value, field)
    keys = {
        "slug",
        "display_name",
        "search_area",
        "goals_or_role_types",
        "keep_only_keywords",
        "constraints_or_red_flags",
        "geography_or_remote_preferences",
        "fit_language",
    }
    _expect_keys(raw, keys, field)
    return {
        "slug": normalize_track_slug(raw["slug"], f"{field}.slug"),
        "display_name": _text(raw["display_name"], f"{field}.display_name", max_chars=200),
        "search_area": _text(raw["search_area"], f"{field}.search_area", max_chars=1000),
        "goals_or_role_types": _text_list(raw["goals_or_role_types"], f"{field}.goals_or_role_types", max_items=30),
        "keep_only_keywords": _text_list(raw["keep_only_keywords"], f"{field}.keep_only_keywords", max_items=50),
        "constraints_or_red_flags": _text_list(
            raw["constraints_or_red_flags"], f"{field}.constraints_or_red_flags", max_items=40
        ),
        "geography_or_remote_preferences": _text_list(
            raw["geography_or_remote_preferences"], f"{field}.geography_or_remote_preferences", max_items=30
        ),
        "fit_language": _text(raw["fit_language"], f"{field}.fit_language", max_chars=1500),
    }


def _normalize_source_seeds(value: Any, field: str = "source_seeds") -> dict[str, Any]:
    raw = _expect_object(value, field)
    keys = {"employers", "sectors_or_organizations", "career_pages_or_boards"}
    _expect_keys(raw, keys, field)
    urls = [normalize_url(item, f"{field}.career_pages_or_boards[{index}]") for index, item in enumerate(
        _expect_list(raw["career_pages_or_boards"], f"{field}.career_pages_or_boards")
    )]
    return {
        "employers": _text_list(raw["employers"], f"{field}.employers", max_items=30),
        "sectors_or_organizations": _text_list(
            raw["sectors_or_organizations"], f"{field}.sectors_or_organizations", max_items=30
        ),
        "career_pages_or_boards": list(dict.fromkeys(urls)),
    }


def _normalize_source_record(value: Any, field: str) -> dict[str, Any]:
    raw = _expect_object(value, field)
    allowed = {"id", "name", "url", "discovery_mode", "cadence_group", "search_terms", "filters"}
    required = {"id", "name", "url", "discovery_mode", "cadence_group"}
    _expect_keys(raw, allowed, field, required=required)
    source_id = _identifier(raw["id"], f"{field}.id")
    source_payload = {
        "schema_version": 1,
        "track": "setup_validation",
        "track_terms": [],
        "sources": [dict(raw, id=source_id, url=normalize_url(raw["url"], f"{field}.url"))],
    }
    try:
        normalized = normalize_sources_payload(source_payload, "setup_validation", field=field)["sources"][0]
    except SourceConfigError as exc:
        raise SetupContractError(str(exc)) from exc
    if normalized["discovery_mode"] not in load_registry():
        raise SetupContractError(f"{field}.discovery_mode is not supported: {normalized['discovery_mode']}")
    normalized["name"] = _text(normalized["name"], f"{field}.name", max_chars=200)
    normalized["url"] = normalize_url(normalized["url"], f"{field}.url")
    normalized["filters"] = {
        _text(key, f"{field}.filters key", max_chars=100): _text_list(values, f"{field}.filters.{key}", max_items=30)
        for key, values in normalized.get("filters", {}).items()
    }
    if search_terms := normalized.get("search_terms"):
        search_terms["terms"] = _text_list(search_terms["terms"], f"{field}.search_terms.terms", max_items=40)
    return normalized


def _normalize_match_rules(value: Any, track: str, field: str) -> list[dict[str, Any]]:
    raw_rules = _expect_list(value, field)
    seen_ids: set[str] = set()
    prepared: list[dict[str, Any]] = []
    allowed = {"id", "source_ids", "source_names", "keep_if_any_text_term", "limitation"}
    for index, item in enumerate(raw_rules):
        rule_field = f"{field}[{index}]"
        raw = _expect_object(item, rule_field)
        _expect_keys(raw, allowed, rule_field, required={"id", "source_ids", "source_names", "keep_if_any_text_term"})
        rule_id = _identifier(raw["id"], f"{rule_field}.id")
        if rule_id in seen_ids:
            raise SetupContractError(f"{rule_field}.id duplicates {rule_id!r}")
        seen_ids.add(rule_id)
        prepared.append(
            {
                "id": rule_id,
                "source_ids": [_identifier(item, f"{rule_field}.source_ids") for item in _text_list(raw["source_ids"], f"{rule_field}.source_ids")],
                "source_names": _text_list(raw["source_names"], f"{rule_field}.source_names"),
                "keep_if_any_text_term": _text_list(
                    raw["keep_if_any_text_term"], f"{rule_field}.keep_if_any_text_term", max_items=40
                ),
                **(
                    {"limitation": _text(raw["limitation"], f"{rule_field}.limitation", max_chars=500)}
                    if raw.get("limitation") is not None
                    else {}
                ),
            }
        )
    payload = {"schema_version": 1, "track": track, "rules": prepared}
    try:
        return normalize_track_match_rules_payload(payload, track, field=field)
    except ValueError as exc:
        raise SetupContractError(str(exc)) from exc


def _normalize_selected_sources(value: Any, track: str, field: str = "selected_sources") -> dict[str, Any]:
    raw = _expect_object(value, field)
    keys = {"track_terms", "sources", "match_rules"}
    _expect_keys(raw, keys, field)
    sources = [_normalize_source_record(item, f"{field}.sources[{index}]") for index, item in enumerate(
        _expect_list(raw["sources"], f"{field}.sources")
    )]
    source_ids = [source["id"] for source in sources]
    if len(source_ids) != len(set(source_ids)):
        raise SetupContractError(f"{field}.sources contains duplicate source ids")
    rules = _normalize_match_rules(raw["match_rules"], track, f"{field}.match_rules")
    known_ids = set(source_ids)
    for rule in rules:
        unknown = sorted(set(rule["source_ids"]) - known_ids)
        if unknown:
            raise SetupContractError(f"match rule {rule['id']!r} references unknown source ids: {', '.join(unknown)}")
    return {
        "track_terms": _text_list(raw["track_terms"], f"{field}.track_terms", max_items=60),
        "sources": sources,
        "match_rules": rules,
    }


def normalize_setup(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_sensitive_keys(payload)
    keys = {"schema_version", "kind", "setup_id", "profile", "track", "source_seeds", "selected_sources"}
    _expect_keys(payload, keys, "setup")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise SetupContractError(f"schema_version must be {SCHEMA_VERSION}")
    if payload["kind"] != SETUP_KIND:
        raise SetupContractError(f"kind must be {SETUP_KIND!r}")
    setup_id = _setup_id(payload["setup_id"])
    track = _normalize_track(payload["track"])
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": SETUP_KIND,
        "setup_id": setup_id,
        "profile": _normalize_profile(payload["profile"]),
        "track": track,
        "source_seeds": _normalize_source_seeds(payload["source_seeds"]),
        "selected_sources": _normalize_selected_sources(payload["selected_sources"], track["slug"]),
    }
    _assert_size(normalized, SETUP_MAX_BYTES, "setup")
    return normalized


def load_setup(path: Path) -> dict[str, Any]:
    return normalize_setup(read_json_limited(path, SETUP_MAX_BYTES, "setup"))


def write_setup(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_setup(payload)
    write_json_atomic(path, normalized, max_bytes=SETUP_MAX_BYTES)
    return normalized


def _normalize_pack_source(value: Any, field: str) -> dict[str, Any]:
    raw = _expect_object(value, field)
    extra = {"fit_reason", "confidence"}
    canonical = {"id", "name", "url", "discovery_mode", "cadence_group", "search_terms", "filters"}
    _expect_keys(raw, canonical | extra, field, required={"id", "name", "url", "discovery_mode", "cadence_group", *extra})
    source = _normalize_source_record({key: raw[key] for key in canonical if key in raw}, field)
    return {
        **source,
        "fit_reason": _text(raw["fit_reason"], f"{field}.fit_reason", max_chars=500),
        "confidence": _enum(raw["confidence"], f"{field}.confidence", {"high", "medium", "low"}),
    }


def _enum(value: Any, field: str, allowed: set[str]) -> str:
    candidate = _text(value, field, max_chars=100)
    if candidate not in allowed:
        raise SetupContractError(f"{field} must be one of: {', '.join(sorted(allowed))}")
    return candidate


def _looks_like_excluded_employer(source_name: str, employers: list[str]) -> bool:
    source_words = re.sub(r"[^a-z0-9]+", " ", source_name.casefold()).strip().split()
    for employer in employers:
        employer_words = re.sub(r"[^a-z0-9]+", " ", employer.casefold()).strip().split()
        if not employer_words:
            continue
        width = len(employer_words)
        if any(source_words[index : index + width] == employer_words for index in range(len(source_words) - width + 1)):
            return True
    return False


def normalize_source_pack(payload: dict[str, Any], setup: dict[str, Any]) -> dict[str, Any]:
    setup = normalize_setup(setup)
    _reject_sensitive_keys(payload)
    keys = {
        "schema_version",
        "kind",
        "setup_id",
        "input_hash",
        "track_terms",
        "recommended_sources",
        "follow_up_sources",
        "dropped_sources",
        "url_corrections",
        "match_rule_suggestions",
        "recommended_source_ids",
        "decisions_needed",
    }
    _expect_keys(payload, keys, "source_pack")
    if payload["schema_version"] != SCHEMA_VERSION or payload["kind"] != SOURCE_PACK_KIND:
        raise SetupContractError(f"source pack must use schema_version {SCHEMA_VERSION} and kind {SOURCE_PACK_KIND!r}")
    if _setup_id(payload["setup_id"]) != setup["setup_id"]:
        raise SetupContractError("source pack setup_id does not match setup")
    if payload["input_hash"] != artifact_hash(setup):
        raise SetupContractError("source pack input_hash does not match setup")
    recommended_raw = _expect_list(payload["recommended_sources"], "source_pack.recommended_sources")
    follow_up_raw = _expect_list(payload["follow_up_sources"], "source_pack.follow_up_sources")
    if len(recommended_raw) > MAX_PRIMARY_SOURCES:
        raise SetupContractError(f"recommended_sources exceeds {MAX_PRIMARY_SOURCES} sources")
    if len(follow_up_raw) > MAX_FOLLOW_UP_SOURCES:
        raise SetupContractError(f"follow_up_sources exceeds {MAX_FOLLOW_UP_SOURCES} sources")
    recommended = [_normalize_pack_source(item, f"source_pack.recommended_sources[{index}]") for index, item in enumerate(recommended_raw)]
    follow_up = [_normalize_pack_source(item, f"source_pack.follow_up_sources[{index}]") for index, item in enumerate(follow_up_raw)]
    all_sources = [*recommended, *follow_up]
    ids = [source["id"] for source in all_sources]
    if len(ids) != len(set(ids)):
        raise SetupContractError("source pack contains duplicate source ids")
    excluded = setup["profile"]["current_or_recent_employers"]
    for source in all_sources:
        if _looks_like_excluded_employer(source["name"], excluded):
            raise SetupContractError(f"source {source['name']!r} matches a current or recent employer")

    dropped: list[dict[str, Any]] = []
    for index, item in enumerate(_expect_list(payload["dropped_sources"], "source_pack.dropped_sources")):
        field = f"source_pack.dropped_sources[{index}]"
        raw = _expect_object(item, field)
        _expect_keys(raw, {"name", "url", "reason"}, field)
        dropped.append(
            {
                "name": _text(raw["name"], f"{field}.name", max_chars=200),
                "url": normalize_url(raw["url"], f"{field}.url") if raw["url"] is not None else None,
                "reason": _text(raw["reason"], f"{field}.reason", max_chars=500),
            }
        )
    if len(dropped) > 12:
        raise SetupContractError("dropped_sources exceeds 12 items")

    corrections_raw = _expect_list(payload["url_corrections"], "source_pack.url_corrections")
    if len(corrections_raw) > MAX_URL_CORRECTIONS:
        raise SetupContractError(f"url_corrections exceeds {MAX_URL_CORRECTIONS} items")
    corrections: list[dict[str, Any]] = []
    for index, item in enumerate(corrections_raw):
        field = f"source_pack.url_corrections[{index}]"
        raw = _expect_object(item, field)
        _expect_keys(raw, {"original_url", "corrected_url", "reason"}, field)
        corrections.append(
            {
                "original_url": normalize_url(raw["original_url"], f"{field}.original_url"),
                "corrected_url": normalize_url(raw["corrected_url"], f"{field}.corrected_url"),
                "reason": _text(raw["reason"], f"{field}.reason", max_chars=500),
            }
        )
    rules = _normalize_match_rules(
        payload["match_rule_suggestions"], setup["track"]["slug"], "source_pack.match_rule_suggestions"
    )
    known_ids = set(ids)
    for rule in rules:
        unknown = sorted(set(rule["source_ids"]) - known_ids)
        if unknown:
            raise SetupContractError(f"match rule {rule['id']!r} references unknown source ids: {', '.join(unknown)}")
    recommended_ids = [
        _identifier(item, "source_pack.recommended_source_ids")
        for item in _text_list(payload["recommended_source_ids"], "source_pack.recommended_source_ids", max_items=MAX_PRIMARY_SOURCES)
    ]
    recommended_known = {source["id"] for source in recommended}
    unknown_recommended = sorted(set(recommended_ids) - recommended_known)
    if unknown_recommended:
        raise SetupContractError(f"recommended_source_ids contains non-primary ids: {', '.join(unknown_recommended)}")
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": SOURCE_PACK_KIND,
        "setup_id": setup["setup_id"],
        "input_hash": artifact_hash(setup),
        "track_terms": _text_list(payload["track_terms"], "source_pack.track_terms", max_items=60),
        "recommended_sources": recommended,
        "follow_up_sources": follow_up,
        "dropped_sources": dropped,
        "url_corrections": corrections,
        "match_rule_suggestions": rules,
        "recommended_source_ids": recommended_ids,
        "decisions_needed": _text_list(payload["decisions_needed"], "source_pack.decisions_needed", max_items=8),
    }
    _assert_size(normalized, SOURCE_PACK_MAX_BYTES, "source pack")
    return normalized


def load_source_pack(path: Path, setup: dict[str, Any]) -> dict[str, Any]:
    return normalize_source_pack(read_json_limited(path, SOURCE_PACK_MAX_BYTES, "source pack"), setup)


def write_source_pack(path: Path, payload: dict[str, Any], setup: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_source_pack(payload, setup)
    write_json_atomic(path, normalized, max_bytes=SOURCE_PACK_MAX_BYTES)
    return normalized


def render_source_pack_summary(source_pack: dict[str, Any], setup: dict[str, Any]) -> str:
    pack = normalize_source_pack(source_pack, setup)
    lines = ["Recommended sources:"]
    if not pack["recommended_sources"]:
        lines.append("- No high-confidence official sources found.")
    for source in pack["recommended_sources"]:
        lines.append(
            f"- {source['name']} — {source['url']} "
            f"({source['discovery_mode']}, {source['cadence_group']}, {source['confidence']}): {source['fit_reason']}"
        )
    if pack["follow_up_sources"]:
        lines.append("Follow-up sources:")
        for source in pack["follow_up_sources"]:
            lines.append(f"- {source['name']} — {source['url']} ({source['confidence']}): {source['fit_reason']}")
    if pack["dropped_sources"]:
        lines.append("Dropped sources:")
        for source in pack["dropped_sources"]:
            lines.append(f"- {source['name']}: {source['reason']}")
    if pack["url_corrections"]:
        lines.append("URL corrections:")
        for correction in pack["url_corrections"]:
            lines.append(f"- {correction['original_url']} -> {correction['corrected_url']}: {correction['reason']}")
    if pack["decisions_needed"]:
        lines.append("Decisions needed:")
        lines.extend(f"- {decision}" for decision in pack["decisions_needed"])
    else:
        lines.append("Decisions needed: none; the recommended package is ready to confirm.")
    return "\n".join(lines) + "\n"


def apply_source_selection(
    setup: dict[str, Any],
    source_pack: dict[str, Any],
    *,
    source_ids: list[str] | None = None,
    match_rule_ids: list[str] | None = None,
) -> dict[str, Any]:
    setup = normalize_setup(setup)
    pack = normalize_source_pack(source_pack, setup)
    chosen_ids = source_ids if source_ids is not None else list(pack["recommended_source_ids"])
    if not chosen_ids:
        raise SetupContractError("source selection must include at least one source")
    source_map = {source["id"]: source for source in [*pack["recommended_sources"], *pack["follow_up_sources"]]}
    unknown = sorted(set(chosen_ids) - set(source_map))
    if unknown:
        raise SetupContractError(f"source selection contains unknown ids: {', '.join(unknown)}")
    rule_ids = match_rule_ids or []
    rule_map = {rule["id"]: rule for rule in pack["match_rule_suggestions"]}
    unknown_rules = sorted(set(rule_ids) - set(rule_map))
    if unknown_rules:
        raise SetupContractError(f"match-rule selection contains unknown ids: {', '.join(unknown_rules)}")
    canonical_keys = {"id", "name", "url", "discovery_mode", "cadence_group", "search_terms", "filters"}
    updated = json.loads(json.dumps(setup))
    updated["selected_sources"] = {
        "track_terms": list(pack["track_terms"]),
        "sources": [{key: source_map[source_id][key] for key in canonical_keys if key in source_map[source_id]} for source_id in chosen_ids],
        "match_rules": [rule_map[rule_id] for rule_id in rule_ids],
    }
    return normalize_setup(updated)


def _bounded_text(value: Any, field: str, *, max_bytes: int, allow_empty: bool = True) -> tuple[str, bool]:
    if not isinstance(value, str):
        raise SetupContractError(f"{field} must be a string")
    normalized = " ".join(value.split())
    if not allow_empty and not normalized:
        raise SetupContractError(f"{field} must be non-empty")
    encoded = normalized.encode("utf-8")
    if len(encoded) <= max_bytes:
        return normalized, False
    truncated = encoded[:max_bytes]
    while True:
        try:
            return truncated.decode("utf-8").rstrip(), True
        except UnicodeDecodeError:
            truncated = truncated[:-1]


def _candidate_id(url: str) -> str:
    return "candidate_" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _normalize_input_ref(value: Any, field: str) -> dict[str, str]:
    raw = _expect_object(value, field)
    _expect_keys(raw, {"path", "sha256"}, field)
    digest = _text(raw["sha256"], f"{field}.sha256", max_chars=64)
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise SetupContractError(f"{field}.sha256 must be a lowercase SHA-256 digest")
    return {"path": _text(raw["path"], f"{field}.path", max_chars=4096), "sha256": digest}


def _normalize_source_note(value: Any, field: str) -> dict[str, Any]:
    raw = _expect_object(value, field)
    keys = {
        "source",
        "discovery_mode",
        "status",
        "listing_pages_scanned",
        "search_terms_tried",
        "result_pages_summary",
        "direct_job_pages_opened",
        "limitations",
        "note",
    }
    _expect_keys(raw, keys, field)
    scalar_types = (str, int, float)
    listing = raw["listing_pages_scanned"]
    result_pages = raw["result_pages_summary"]
    direct_pages = raw["direct_job_pages_opened"]
    for scalar, name in [(listing, "listing_pages_scanned"), (result_pages, "result_pages_summary"), (direct_pages, "direct_job_pages_opened")]:
        if scalar is not None and (isinstance(scalar, bool) or not isinstance(scalar, scalar_types)):
            raise SetupContractError(f"{field}.{name} must be a string, number, or null")
    return {
        "source": _text(raw["source"], f"{field}.source", max_chars=200),
        "discovery_mode": _text(raw["discovery_mode"], f"{field}.discovery_mode", max_chars=100),
        "status": _enum(raw["status"], f"{field}.status", {"complete", "partial", "failed"}),
        "listing_pages_scanned": listing,
        "search_terms_tried": _text_list(raw["search_terms_tried"], f"{field}.search_terms_tried", max_items=60),
        "result_pages_summary": result_pages,
        "direct_job_pages_opened": direct_pages,
        "limitations": _text_list(raw["limitations"], f"{field}.limitations", max_items=20),
        "note": _text(raw["note"], f"{field}.note", allow_empty=True, max_chars=500) or None,
    }


def _normalize_preview_candidate(value: Any, field: str) -> dict[str, Any]:
    raw = _expect_object(value, field)
    keys = {
        "candidate_id",
        "employer",
        "title",
        "url",
        "source_url",
        "source",
        "location",
        "remote",
        "alternate_url",
        "matched_terms",
        "description",
        "description_truncated",
    }
    _expect_keys(raw, keys, field)
    candidate_id = _text(raw["candidate_id"], f"{field}.candidate_id", max_chars=40)
    if not MODEL_OUTPUT_ID_RE.fullmatch(candidate_id):
        raise SetupContractError(f"{field}.candidate_id is invalid")
    if not isinstance(raw["description_truncated"], bool):
        raise SetupContractError(f"{field}.description_truncated must be boolean")
    description, truncated_now = _bounded_text(raw["description"], f"{field}.description", max_bytes=MAX_DESCRIPTION_BYTES)
    alternate = raw["alternate_url"]
    return {
        "candidate_id": candidate_id,
        "employer": _text(raw["employer"], f"{field}.employer", max_chars=200),
        "title": _text(raw["title"], f"{field}.title", max_chars=500),
        "url": normalize_url(raw["url"], f"{field}.url"),
        "source_url": normalize_url(raw["source_url"], f"{field}.source_url"),
        "source": _text(raw["source"], f"{field}.source", max_chars=200),
        "location": _text(raw["location"], f"{field}.location", allow_empty=True, max_chars=300) or "unknown",
        "remote": _text(raw["remote"], f"{field}.remote", allow_empty=True, max_chars=200) or "unknown",
        "alternate_url": normalize_url(alternate, f"{field}.alternate_url") if alternate else None,
        "matched_terms": _text_list(raw["matched_terms"], f"{field}.matched_terms", max_items=60),
        "description": description,
        "description_truncated": raw["description_truncated"] or truncated_now,
    }


def normalize_preview_context(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_sensitive_keys(payload)
    keys = {
        "schema_version",
        "kind",
        "setup_id",
        "date",
        "inputs",
        "profile",
        "track",
        "source_notes",
        "candidates",
        "coverage_limitations",
        "omitted_candidate_count",
    }
    _expect_keys(payload, keys, "preview_context")
    if payload["schema_version"] != SCHEMA_VERSION or payload["kind"] != PREVIEW_CONTEXT_KIND:
        raise SetupContractError(
            f"preview context must use schema_version {SCHEMA_VERSION} and kind {PREVIEW_CONTEXT_KIND!r}"
        )
    try:
        stamp = date.fromisoformat(_text(payload["date"], "preview_context.date", max_chars=10)).isoformat()
    except ValueError as exc:
        raise SetupContractError("preview_context.date must use YYYY-MM-DD") from exc
    inputs = _expect_object(payload["inputs"], "preview_context.inputs")
    _expect_keys(inputs, {"setup", "discovery", "seen_jobs"}, "preview_context.inputs")
    candidates = [
        _normalize_preview_candidate(item, f"preview_context.candidates[{index}]")
        for index, item in enumerate(_expect_list(payload["candidates"], "preview_context.candidates"))
    ]
    if len(candidates) > MAX_PREVIEW_CANDIDATES:
        raise SetupContractError(f"preview context exceeds {MAX_PREVIEW_CANDIDATES} candidates")
    ids = [item["candidate_id"] for item in candidates]
    urls = [item["url"] for item in candidates]
    if len(ids) != len(set(ids)) or len(urls) != len(set(urls)):
        raise SetupContractError("preview context contains duplicate candidate ids or URLs")
    omitted = payload["omitted_candidate_count"]
    if isinstance(omitted, bool) or not isinstance(omitted, int) or omitted < 0:
        raise SetupContractError("preview_context.omitted_candidate_count must be a non-negative integer")
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": PREVIEW_CONTEXT_KIND,
        "setup_id": _setup_id(payload["setup_id"]),
        "date": stamp,
        "inputs": {key: _normalize_input_ref(inputs[key], f"preview_context.inputs.{key}") for key in ("setup", "discovery", "seen_jobs")},
        "profile": _normalize_profile(payload["profile"], "preview_context.profile"),
        "track": _normalize_track(payload["track"], "preview_context.track"),
        "source_notes": [
            _normalize_source_note(item, f"preview_context.source_notes[{index}]")
            for index, item in enumerate(_expect_list(payload["source_notes"], "preview_context.source_notes"))
        ],
        "candidates": candidates,
        "coverage_limitations": _text_list(
            payload["coverage_limitations"], "preview_context.coverage_limitations", max_items=30
        ),
        "omitted_candidate_count": omitted,
    }
    _assert_size(normalized, PREVIEW_CONTEXT_MAX_BYTES, "preview context")
    return normalized


def load_preview_context(path: Path) -> dict[str, Any]:
    return normalize_preview_context(read_json_limited(path, PREVIEW_CONTEXT_MAX_BYTES, "preview context"))


def write_preview_context(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_preview_context(payload)
    write_json_atomic(path, normalized, max_bytes=PREVIEW_CONTEXT_MAX_BYTES)
    return normalized


def build_preview_context(
    setup: dict[str, Any],
    discovery_path: Path,
    seen_jobs_path: Path,
    *,
    setup_path: Path,
    root: Path,
) -> dict[str, Any]:
    setup = normalize_setup(setup)
    discovery = read_json_limited(discovery_path, 16 * 1024 * 1024, "discovery artifact")
    track = setup["track"]["slug"]
    if discovery.get("schema_version") != 1 or discovery.get("track") != track or discovery.get("mode") != "discover":
        raise SetupContractError("discovery artifact schema, track, or mode does not match setup")
    try:
        stamp = date.fromisoformat(str(discovery.get("today"))).isoformat()
    except ValueError as exc:
        raise SetupContractError("discovery artifact today must use YYYY-MM-DD") from exc
    sources = _expect_list(discovery.get("sources"), "discovery.sources")
    if seen_jobs_path.exists():
        try:
            seen_jobs = load_seen_jobs(seen_jobs_path, track)
        except SourceConfigError as exc:
            raise SetupContractError(str(exc)) from exc
        seen_hash = file_hash(seen_jobs_path)
    else:
        seen_jobs = []
        seen_hash = artifact_hash({"schema_version": 1, "track": track, "jobs": []})
    seen_urls = {
        normalize_url(item.get("url"), "seen_jobs.jobs[].url")
        for item in seen_jobs
        if isinstance(item, dict) and item.get("url")
    }

    source_notes: list[dict[str, Any]] = []
    raw_candidates: list[tuple[int, dict[str, Any]]] = []
    discovery_index = 0
    for source_index, source_value in enumerate(sources):
        field = f"discovery.sources[{source_index}]"
        source = _expect_object(source_value, field)
        source_name = _text(source.get("source"), f"{field}.source", max_chars=200)
        source_url = normalize_url(source.get("source_url"), f"{field}.source_url")
        candidates = _expect_list(source.get("candidates"), f"{field}.candidates")
        limitations = _text_list(source.get("limitations", []), f"{field}.limitations", max_items=20)
        source_notes.append(
            _normalize_source_note(
                {
                    "source": source_name,
                    "discovery_mode": source.get("discovery_mode"),
                    "status": source.get("status"),
                    "listing_pages_scanned": source.get("listing_pages_scanned"),
                    "search_terms_tried": source.get("search_terms_tried", []),
                    "result_pages_summary": source.get("result_pages_scanned"),
                    "direct_job_pages_opened": source.get("direct_job_pages_opened"),
                    "limitations": limitations,
                    "note": f"Discovery enumerated {source.get('enumerated_jobs', len(candidates))} job(s) and retained {len(candidates)} candidate(s).",
                },
                f"preview_context.source_notes[{source_index}]",
            )
        )
        for candidate_index, candidate_value in enumerate(candidates):
            candidate_field = f"{field}.candidates[{candidate_index}]"
            candidate = _expect_object(candidate_value, candidate_field)
            direct_url = normalize_url(candidate.get("url"), f"{candidate_field}.url")
            if direct_url in seen_urls:
                discovery_index += 1
                continue
            description, truncated = _bounded_text(
                candidate.get("description", ""), f"{candidate_field}.description", max_bytes=MAX_DESCRIPTION_BYTES
            )
            matched_terms = _text_list(candidate.get("matched_terms", []), f"{candidate_field}.matched_terms", max_items=60)
            source_description_truncated = candidate.get("description_truncated", False)
            if not isinstance(source_description_truncated, bool):
                raise SetupContractError(f"{candidate_field}.description_truncated must be boolean")
            preview_candidate = {
                "candidate_id": _candidate_id(direct_url),
                "employer": _text(candidate.get("employer"), f"{candidate_field}.employer", max_chars=200),
                "title": _text(candidate.get("title"), f"{candidate_field}.title", max_chars=500),
                "url": direct_url,
                "source_url": normalize_url(candidate.get("source_url") or source_url, f"{candidate_field}.source_url"),
                "source": source_name,
                "location": _text(candidate.get("location", "unknown"), f"{candidate_field}.location", allow_empty=True, max_chars=300) or "unknown",
                "remote": _text(candidate.get("remote", "unknown"), f"{candidate_field}.remote", allow_empty=True, max_chars=200) or "unknown",
                "alternate_url": normalize_url(candidate["alternate_url"], f"{candidate_field}.alternate_url") if candidate.get("alternate_url") else None,
                "matched_terms": matched_terms,
                "description": description,
                "description_truncated": source_description_truncated or truncated,
            }
            raw_candidates.append((discovery_index, preview_candidate))
            discovery_index += 1

    deduplicated: list[tuple[int, dict[str, Any]]] = []
    seen_candidate_urls: set[str] = set()
    for original_index, candidate in raw_candidates:
        if candidate["url"] in seen_candidate_urls:
            continue
        seen_candidate_urls.add(candidate["url"])
        deduplicated.append((original_index, candidate))
    deduplicated.sort(
        key=lambda pair: (
            -len(match_terms(pair[1]["title"], pair[1]["matched_terms"])),
            -len(pair[1]["matched_terms"]),
            pair[0],
        )
    )
    total_unseen = len(deduplicated)
    limited = deduplicated[:MAX_PREVIEW_CANDIDATES]
    coverage_limitations: list[str] = []
    if total_unseen > len(limited):
        coverage_limitations.append(
            f"Preview context retained {len(limited)} of {total_unseen} unseen candidates by title evidence, matched-term count, and discovery order."
        )
    inputs = {
        "setup": {"path": _display_path(setup_path, root), "sha256": file_hash(setup_path)},
        "discovery": {"path": _display_path(discovery_path, root), "sha256": file_hash(discovery_path)},
        "seen_jobs": {"path": _display_path(seen_jobs_path, root), "sha256": seen_hash},
    }
    base = {
        "schema_version": SCHEMA_VERSION,
        "kind": PREVIEW_CONTEXT_KIND,
        "setup_id": setup["setup_id"],
        "date": stamp,
        "inputs": inputs,
        "profile": setup["profile"],
        "track": setup["track"],
        "source_notes": source_notes,
        "candidates": [],
        "coverage_limitations": coverage_limitations,
        "omitted_candidate_count": total_unseen,
    }
    retained: list[dict[str, Any]] = []
    for _, candidate in limited:
        prospective = [*retained, candidate]
        probe = dict(base, candidates=prospective, omitted_candidate_count=total_unseen - len(prospective))
        if len(_canonical_json_bytes(probe)) > PREVIEW_CONTEXT_MAX_BYTES:
            break
        retained = prospective
    omitted = total_unseen - len(retained)
    if omitted and not coverage_limitations:
        coverage_limitations.append(
            f"Preview context retained {len(retained)} of {total_unseen} unseen candidates within the total size limit."
        )
    base["candidates"] = retained
    base["coverage_limitations"] = coverage_limitations
    base["omitted_candidate_count"] = omitted
    return normalize_preview_context(base)


def _score(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SetupContractError(f"{field} must be numeric")
    score = float(value)
    if not 0 <= score <= 10:
        raise SetupContractError(f"{field} must be between 0 and 10")
    return score


def normalize_preview_result(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    context = normalize_preview_context(context)
    _reject_sensitive_keys(payload)
    keys = {"schema_version", "kind", "setup_id", "input_hash", "executive_summary", "recommended_actions", "judgments"}
    _expect_keys(payload, keys, "preview_result")
    if payload["schema_version"] != SCHEMA_VERSION or payload["kind"] != PREVIEW_RESULT_KIND:
        raise SetupContractError(
            f"preview result must use schema_version {SCHEMA_VERSION} and kind {PREVIEW_RESULT_KIND!r}"
        )
    if _setup_id(payload["setup_id"]) != context["setup_id"]:
        raise SetupContractError("preview result setup_id does not match context")
    if payload["input_hash"] != artifact_hash(context):
        raise SetupContractError("preview result input_hash does not match context")
    judgments: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    valid_ids = {candidate["candidate_id"] for candidate in context["candidates"]}
    for index, item in enumerate(_expect_list(payload["judgments"], "preview_result.judgments")):
        field = f"preview_result.judgments[{index}]"
        raw = _expect_object(item, field)
        disposition = _enum(raw.get("disposition"), f"{field}.disposition", {"top_match", "other_role", "filtered"})
        common = {"candidate_id", "disposition"}
        if disposition == "top_match":
            allowed = common | {"score", "recommendation", "match_reasons", "concerns"}
            _expect_keys(raw, allowed, field)
            normalized = {
                "candidate_id": _text(raw["candidate_id"], f"{field}.candidate_id", max_chars=40),
                "disposition": disposition,
                "score": _score(raw["score"], f"{field}.score"),
                "recommendation": _enum(raw["recommendation"], f"{field}.recommendation", {"apply_now", "watch", "skip"}),
                "match_reasons": _text_list(raw["match_reasons"], f"{field}.match_reasons", max_items=8),
                "concerns": _text_list(raw["concerns"], f"{field}.concerns", max_items=8),
            }
        elif disposition == "other_role":
            allowed = common | {"score", "recommendation", "short_note"}
            _expect_keys(raw, allowed, field)
            normalized = {
                "candidate_id": _text(raw["candidate_id"], f"{field}.candidate_id", max_chars=40),
                "disposition": disposition,
                "score": _score(raw["score"], f"{field}.score"),
                "recommendation": _enum(raw["recommendation"], f"{field}.recommendation", {"apply_now", "watch", "skip"}),
                "short_note": _text(raw["short_note"], f"{field}.short_note", max_chars=500),
            }
        else:
            allowed = common | {"reason"}
            _expect_keys(raw, allowed, field)
            normalized = {
                "candidate_id": _text(raw["candidate_id"], f"{field}.candidate_id", max_chars=40),
                "disposition": disposition,
                "reason": _text(raw["reason"], f"{field}.reason", max_chars=500),
            }
        candidate_id = normalized["candidate_id"]
        if candidate_id not in valid_ids:
            raise SetupContractError(f"{field}.candidate_id is not present in preview context")
        if candidate_id in seen_ids:
            raise SetupContractError(f"duplicate judgment for candidate {candidate_id}")
        seen_ids.add(candidate_id)
        judgments.append(normalized)
    missing = sorted(valid_ids - seen_ids)
    if missing:
        raise SetupContractError(f"preview result is missing judgments for: {', '.join(missing)}")
    normalized_result = {
        "schema_version": SCHEMA_VERSION,
        "kind": PREVIEW_RESULT_KIND,
        "setup_id": context["setup_id"],
        "input_hash": artifact_hash(context),
        "executive_summary": _text(
            payload["executive_summary"], "preview_result.executive_summary", allow_empty=True, max_chars=1500
        ),
        "recommended_actions": _text_list(
            payload["recommended_actions"], "preview_result.recommended_actions", max_items=8
        ),
        "judgments": judgments,
    }
    _assert_size(normalized_result, PREVIEW_RESULT_MAX_BYTES, "preview result")
    return normalized_result


def load_preview_result(path: Path, context: dict[str, Any]) -> dict[str, Any]:
    return normalize_preview_result(read_json_limited(path, PREVIEW_RESULT_MAX_BYTES, "preview result"), context)


def write_preview_result(path: Path, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_preview_result(payload, context)
    write_json_atomic(path, normalized, max_bytes=PREVIEW_RESULT_MAX_BYTES)
    return normalized


def assemble_preview_digest(
    context: dict[str, Any],
    result: dict[str, Any],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    context = normalize_preview_context(context)
    result = normalize_preview_result(result, context)
    by_id = {judgment["candidate_id"]: judgment for judgment in result["judgments"]}
    top_matches: list[dict[str, Any]] = []
    other_roles: list[dict[str, Any]] = []
    filtered: list[dict[str, Any]] = []
    for candidate in context["candidates"]:
        judgment = by_id[candidate["candidate_id"]]
        if judgment["disposition"] == "top_match":
            top_matches.append(
                {
                    "job_key": candidate["candidate_id"],
                    "company": candidate["employer"],
                    "title": candidate["title"],
                    "listing_url": candidate["url"],
                    "alternate_url": candidate["alternate_url"],
                    "location": candidate["location"],
                    "remote": candidate["remote"],
                    "team_or_domain": None,
                    "posted_date": None,
                    "updated_date": None,
                    "source": candidate["source"],
                    "source_url": candidate["source_url"],
                    "fit_score": judgment["score"],
                    "recommendation": judgment["recommendation"],
                    "why_match": judgment["match_reasons"],
                    "concerns": judgment["concerns"],
                }
            )
        elif judgment["disposition"] == "other_role":
            other_roles.append(
                {
                    "job_key": candidate["candidate_id"],
                    "company": candidate["employer"],
                    "title": candidate["title"],
                    "listing_url": candidate["url"],
                    "alternate_url": candidate["alternate_url"],
                    "location": candidate["location"],
                    "source": candidate["source"],
                    "fit_score": judgment["score"],
                    "recommendation": judgment["recommendation"],
                    "short_note": judgment["short_note"],
                }
            )
        else:
            filtered.append(
                {
                    "company": candidate["employer"],
                    "title": candidate["title"],
                    "listing_url": candidate["url"],
                    "reason_filtered_out": judgment["reason"],
                }
            )
    created_at = generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    payload = {
        "schema_version": 1,
        "track": context["track"]["slug"],
        "date": context["date"],
        "runs": [
            {
                "kind": "initial",
                "generated_at": created_at,
                "executive_summary": result["executive_summary"],
                "recommended_actions": result["recommended_actions"],
                "top_matches": top_matches,
                "other_new_roles": other_roles,
                "filtered_roles": filtered,
                "source_notes": context["source_notes"],
                "notes_for_next_run": context["coverage_limitations"],
                "discovery_artifacts": [context["inputs"]["discovery"]["path"]],
            }
        ],
    }
    try:
        return normalize_digest_payload(payload, expected_track=context["track"]["slug"], expected_date=context["date"])
    except ValueError as exc:
        raise SetupContractError(str(exc)) from exc


def worker_json_schema(role: str, input_payload: dict[str, Any]) -> dict[str, Any]:
    common = {
        "schema_version": {"const": 1},
        "setup_id": {"const": input_payload["setup_id"]},
        "input_hash": {"const": artifact_hash(input_payload)},
    }
    if role == "source_discovery":
        source = {
            "type": "object",
            "additionalProperties": False,
            "required": ["id", "name", "url", "discovery_mode", "cadence_group", "fit_reason", "confidence"],
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "url": {"type": "string"},
                "discovery_mode": {"type": "string"},
                "cadence_group": {"enum": ["every_run", "every_3_runs", "every_month"]},
                "search_terms": {"type": "object"},
                "filters": {"type": "object"},
                "fit_reason": {"type": "string"},
                "confidence": {"enum": ["high", "medium", "low"]},
            },
        }
        return {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version", "kind", "setup_id", "input_hash", "track_terms", "recommended_sources",
                "follow_up_sources", "dropped_sources", "url_corrections", "match_rule_suggestions",
                "recommended_source_ids", "decisions_needed",
            ],
            "properties": {
                **common,
                "kind": {"const": SOURCE_PACK_KIND},
                "track_terms": {"type": "array", "items": {"type": "string"}},
                "recommended_sources": {"type": "array", "maxItems": MAX_PRIMARY_SOURCES, "items": source},
                "follow_up_sources": {"type": "array", "maxItems": MAX_FOLLOW_UP_SOURCES, "items": source},
                "dropped_sources": {"type": "array"},
                "url_corrections": {"type": "array", "maxItems": MAX_URL_CORRECTIONS},
                "match_rule_suggestions": {"type": "array"},
                "recommended_source_ids": {"type": "array", "items": {"type": "string"}},
                "decisions_needed": {"type": "array", "items": {"type": "string"}},
            },
        }
    if role != "preview_ranker":
        raise SetupContractError("worker role must be source_discovery or preview_ranker")
    candidate_ids = [candidate["candidate_id"] for candidate in input_payload["candidates"]]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "kind", "setup_id", "input_hash", "executive_summary", "recommended_actions", "judgments"],
        "properties": {
            **common,
            "kind": {"const": PREVIEW_RESULT_KIND},
            "executive_summary": {"type": "string"},
            "recommended_actions": {"type": "array", "items": {"type": "string"}},
            "judgments": {
                "type": "array",
                "minItems": len(candidate_ids),
                "maxItems": len(candidate_ids),
                "items": {
                    "type": "object",
                    "required": ["candidate_id", "disposition"],
                    "properties": {
                        "candidate_id": {"enum": candidate_ids},
                        "disposition": {"enum": ["top_match", "other_role", "filtered"]},
                    },
                },
            },
        },
    }


def build_worker_prompt(role: str, input_payload: dict[str, Any]) -> str:
    compact_input = json.dumps(input_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    common = (
        "Return exactly one JSON object and no prose, Markdown fences, or commentary. "
        "Do not read other user files, invoke another model, or write files. "
        "Copy setup_id exactly and set input_hash to the SHA-256 supplied by the contract instructions.\n"
    )
    if role == "source_discovery":
        modes = ", ".join(sorted(load_registry()))
        return (
            "JOBWATCH_SETUP_WORKER_ROLE=source_discovery\n"
            + common
            + "Use web search/fetch only to find official employer career pages or clearly first-party hosted boards. "
            "Exclude current or recent employers. Recommend at most 8 primary and 4 follow-up sources, validate at most "
            "3 URLs, use only the supported discovery modes below, and prefer every_3_runs unless a source clearly warrants "
            "another cadence. Suggest match rules only for broad/noisy sources. Every source must already use the canonical "
            "sources.json fields plus fit_reason and confidence. Include concise track_terms and only genuinely unresolved "
            "decisions_needed.\n"
            f"Supported discovery modes: {modes}\n"
            f"Required kind: {SOURCE_PACK_KIND}\n"
            f"Required input_hash: {artifact_hash(input_payload)}\n"
            "BEGIN_INPUT_JSON\n"
            + compact_input
            + "\nEND_INPUT_JSON\n"
        )
    if role == "preview_ranker":
        return (
            "JOBWATCH_SETUP_WORKER_ROLE=preview_ranker\n"
            + common
            + "Do not use web search. Judge only the bounded profile, track, and candidates in the input. Give every "
            "candidate exactly one disposition. Use top_match with score, recommendation, match_reasons, and concerns; "
            "other_role with score, recommendation, and short_note; or filtered with a concrete reason. Treat hard "
            "constraints conservatively and do not invent evidence when descriptions are missing. Do not repeat URLs, "
            "descriptions, profile data, or source coverage.\n"
            f"Required kind: {PREVIEW_RESULT_KIND}\n"
            f"Required input_hash: {artifact_hash(input_payload)}\n"
            "BEGIN_INPUT_JSON\n"
            + compact_input
            + "\nEND_INPUT_JSON\n"
        )
    raise SetupContractError("worker role must be source_discovery or preview_ranker")


def _normalizer_for(kind: str, context: dict[str, Any] | None) -> tuple[Callable[[dict[str, Any]], dict[str, Any]], int]:
    if kind == "setup":
        return normalize_setup, SETUP_MAX_BYTES
    if kind == "source-pack":
        if context is None:
            raise SetupContractError("source-pack validation requires --context setup.json")
        return lambda payload: normalize_source_pack(payload, context), SOURCE_PACK_MAX_BYTES
    if kind == "preview-context":
        return normalize_preview_context, PREVIEW_CONTEXT_MAX_BYTES
    if kind == "preview-result":
        if context is None:
            raise SetupContractError("preview-result validation requires --context preview-context.json")
        return lambda payload: normalize_preview_result(payload, context), PREVIEW_RESULT_MAX_BYTES
    raise SetupContractError(f"unsupported artifact kind: {kind}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="validate and optionally atomically normalize an artifact")
    validate.add_argument("--kind", required=True, choices=["setup", "source-pack", "preview-context", "preview-result"])
    validate.add_argument("--input", required=True)
    validate.add_argument("--context")
    validate.add_argument("--output")
    select = subparsers.add_parser("select-sources", help="record confirmed source-pack choices in setup.json")
    select.add_argument("--setup", required=True)
    select.add_argument("--source-pack", required=True)
    select.add_argument("--source-id", action="append", default=[])
    select.add_argument("--match-rule-id", action="append", default=[])
    select.add_argument("--all-recommended", action="store_true")
    summary = subparsers.add_parser("summarize-source-pack", help="render the bounded deterministic coordinator summary")
    summary.add_argument("--setup", required=True)
    summary.add_argument("--source-pack", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            context: dict[str, Any] | None = None
            if args.context:
                if args.kind == "source-pack":
                    context = load_setup(Path(args.context))
                elif args.kind == "preview-result":
                    context = load_preview_context(Path(args.context))
            normalizer, max_bytes = _normalizer_for(args.kind, context)
            raw = read_json_limited(Path(args.input), max_bytes, args.kind)
            normalized = normalizer(raw)
            if args.output:
                write_json_atomic(Path(args.output), normalized, max_bytes=max_bytes)
            print(json.dumps({"status": "valid", "kind": args.kind, "setup_id": normalized["setup_id"]}))
            return 0
        setup_path = Path(args.setup)
        setup = load_setup(setup_path)
        pack = load_source_pack(Path(args.source_pack), setup)
        if args.command == "summarize-source-pack":
            print(render_source_pack_summary(pack, setup), end="")
            return 0
        if args.command == "select-sources":
            if args.source_id and args.all_recommended:
                raise SetupContractError("use either --source-id or --all-recommended")
            chosen = None if args.all_recommended or not args.source_id else args.source_id
            updated = apply_source_selection(setup, pack, source_ids=chosen, match_rule_ids=args.match_rule_id)
            write_setup(setup_path, updated)
            print(json.dumps({"status": "updated", "setup_id": updated["setup_id"], "sources": len(updated["selected_sources"]["sources"])}))
            return 0
    except (OSError, SetupContractError) as exc:
        print(f"setup_contracts.py: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
