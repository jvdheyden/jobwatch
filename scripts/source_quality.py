#!/usr/bin/env python3
"""Helpers for source-integration quality evaluation."""

from __future__ import annotations

import json
import re
import ssl
import subprocess
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from agent_provider import build_reviewer_command as build_provider_reviewer_command
from agent_provider import resolve_agent_provider


USER_AGENT = "job-agent-source-quality/0.1"
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_REVIEW_TIMEOUT_SECONDS = 120
REVIEWER_MAX_CANDIDATES = 10
REVIEWER_REASONING_EFFORT = "low"
HTML_TAG_RE = re.compile(r"<[^>]+>")
NON_JOB_TITLE_MARKERS = (
    "open positions",
    "open jobs",
    "search results",
    "rss",
    "twitter",
    "join us",
    "karrieremessen",
    "offene stellen",
    "newsletter",
    "feed",
)
NON_JOB_URL_MARKERS = (
    "/rss",
    "/feed",
    "twitter.com",
    "/newsletter",
    "/impressum",
    "mailto:",
)
DETAIL_FIELD_KEYS = (
    "tasks",
    "responsibilities",
    "qualifications",
    "requirements",
    "profile",
    "compensation",
    "salary",
    "salary_range",
    "equity_range",
)
DETAIL_NOTE_MARKERS = (
    "tasks:",
    "task:",
    "responsibilities",
    "responsibility",
    "requirements:",
    "qualifications:",
    "profile:",
    "deadline:",
    "bewerbungsfrist",
    "minimum qualifications",
    "preferred qualifications",
    "what you'll do",
    "what you will do",
    "your profile",
    "ihr profil",
    "anforderungen",
    "aufgaben",
    "salary:",
    "compensation:",
    "pay range",
    "salary range",
)
PROVENANCE_NOTE_MARKERS = (
    "enumerated through",
    "static html enumeration",
    "browser search q=",
    "meta browser search",
    "hacker news jobs listing",
    "posted:",
)
RAW_DETAIL_MARKERS = {
    "tasks": (
        "responsibilities",
        "responsibility",
        "what you'll do",
        "what you will do",
        "your tasks",
        "aufgaben",
        "ihre aufgaben",
        "job description",
    ),
    "qualifications": (
        "qualifications",
        "required qualifications",
        "minimum qualifications",
        "preferred qualifications",
        "requirements",
        "your profile",
        "ihr profil",
        "anforderungen",
        "what you'll need",
        "what you need",
    ),
    "compensation": (
        "salary",
        "compensation",
        "pay range",
        "salary range",
        "equity",
        "vergutung",
        "entgelt",
        "besoldung",
    ),
}


@dataclass(frozen=True)
class ValidatorResult:
    name: str
    status: str
    severity: str
    details: str


def generated_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def strip_html_fragment(value: str) -> str:
    return normalize_whitespace(unescape(HTML_TAG_RE.sub(" ", value or "")))


def truncate_text(value: str, limit: int = 400) -> str:
    text = normalize_whitespace(value)
    if len(text) <= limit:
        return text
    boundary = text.rfind(" ", 0, limit - 3)
    if boundary == -1 or boundary < limit // 2:
        boundary = limit - 3
    return text[:boundary].rstrip() + "..."


def normalize_for_matching(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text.lower()


def normalize_url_without_fragment(value: str) -> str:
    parsed = urlparse(value or "")
    path = parsed.path.rstrip("/") or "/"
    return parsed._replace(path=path, fragment="").geturl()


def source_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def fetch_text(url: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    context = ssl.create_default_context()
    with urlopen(request, timeout=timeout_seconds, context=context) as response:
        content_type = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(content_type, errors="replace")


def registrable_domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().strip(".")
    if not host:
        return ""
    if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", host):
        return host
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    return ".".join(parts[-2:])


def is_allowed_candidate_domain(source_url: str, candidate_url: str) -> bool:
    source_host = (urlparse(source_url).hostname or "").lower()
    candidate_host = (urlparse(candidate_url).hostname or "").lower()
    if not candidate_host:
        return False
    if candidate_host == source_host or candidate_host.endswith("." + source_host):
        return True
    return registrable_domain(source_url) == registrable_domain(candidate_url)


def extract_json_from_text(text: str) -> Any:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            value, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        remainder = text[index + end :].strip()
        if not remainder:
            return value
    raise ValueError("no JSON object found in reviewer output")


def load_source_coverage(artifact_path: Path, source_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = json.loads(artifact_path.read_text())
    for source in payload.get("sources", []):
        if source.get("source") == source_name:
            return payload, source
    raise KeyError(f"source {source_name!r} not found in {artifact_path}")


def _missing_core_field(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    return normalize_whitespace(value) == ""


def _suspicious_candidate(candidate: dict[str, Any]) -> list[str]:
    title = normalize_for_matching(candidate.get("title", ""))
    url = normalize_for_matching(candidate.get("url", ""))
    reasons: list[str] = []
    if any(marker in title for marker in NON_JOB_TITLE_MARKERS):
        reasons.append("title looks like navigation or category text")
    if any(marker in url for marker in NON_JOB_URL_MARKERS):
        reasons.append("url looks like feed or navigation page")
    if re.fullmatch(r"\d+\s+offene\s+stellen", title):
        reasons.append("title is only a result count")
    return reasons


def _has_meaningful_detail_value(value: Any) -> bool:
    if value is None:
        return False
    if not isinstance(value, str):
        return True
    return normalize_whitespace(value).lower() not in {"", "unknown", "n/a"}


def _has_substantive_notes(candidate: dict[str, Any]) -> bool:
    notes = normalize_whitespace(str(candidate.get("notes", "")))
    if not notes:
        return False
    normalized = normalize_for_matching(notes)
    if any(marker in normalized for marker in DETAIL_NOTE_MARKERS):
        return True
    if any(marker in normalized for marker in PROVENANCE_NOTE_MARKERS):
        return False
    return len(notes) >= 120 or len(notes.split()) >= 20


def _candidate_has_detail(candidate: dict[str, Any]) -> bool:
    if any(_has_meaningful_detail_value(candidate.get(field)) for field in DETAIL_FIELD_KEYS):
        return True
    return _has_substantive_notes(candidate)


def _raw_detail_categories(raw_text: str) -> set[str]:
    normalized = normalize_for_matching(strip_html_fragment(raw_text))
    categories: set[str] = set()
    for category, markers in RAW_DETAIL_MARKERS.items():
        if any(marker in normalized for marker in markers):
            categories.add(category)
    return categories


def _candidate_matches_canary(candidate: dict[str, Any], canary_title: str, canary_url: str) -> bool:
    normalized_canary_url = normalize_url_without_fragment(canary_url) if canary_url else ""
    if normalized_canary_url and normalize_url_without_fragment(candidate.get("url", "")) == normalized_canary_url:
        return True
    normalized_canary_title = normalize_for_matching(canary_title) if canary_title else ""
    return bool(normalized_canary_title) and normalize_for_matching(candidate.get("title", "")) == normalized_canary_title


def _select_reviewer_candidates(
    candidates: list[dict[str, Any]],
    *,
    canary_title: str,
    canary_url: str,
    limit: int = REVIEWER_MAX_CANDIDATES,
) -> list[dict[str, Any]]:
    if len(candidates) <= limit:
        return list(candidates)

    selected = list(candidates[:limit])
    canary_candidate = next(
        (candidate for candidate in candidates if _candidate_matches_canary(candidate, canary_title, canary_url)),
        None,
    )
    if canary_candidate is None or any(
        _candidate_matches_canary(candidate, canary_title, canary_url) for candidate in selected
    ):
        return selected

    for index in range(len(selected) - 1, -1, -1):
        if not _candidate_matches_canary(selected[index], canary_title, canary_url):
            selected[index] = canary_candidate
            break
    return selected


def validate_source_coverage(
    source: dict[str, Any],
    *,
    canary_title: str = "",
    canary_url: str = "",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    raw_text_fetcher: Callable[[str, int], str] = fetch_text,
) -> dict[str, Any]:
    candidates = source.get("candidates", [])
    source_url = source.get("source_url", "")
    results: list[ValidatorResult] = []
    warnings: list[str] = []

    if source.get("enumerated_jobs", 0) or candidates:
        results.append(ValidatorResult("artifact_nonempty", "pass", "info", "Source enumerated at least one posting or candidate."))
    else:
        results.append(ValidatorResult("artifact_nonempty", "fail", "blocking", "Source artifact enumerated no postings and produced no candidates."))

    missing_fields: list[str] = []
    for index, candidate in enumerate(candidates):
        for field in ("title", "url", "source_url", "employer"):
            if _missing_core_field(candidate.get(field)):
                missing_fields.append(f"candidate[{index}].{field}")
    if missing_fields:
        results.append(
            ValidatorResult(
                "required_fields",
                "fail",
                "blocking",
                "Missing core fields: " + ", ".join(missing_fields[:8]),
            )
        )
    else:
        results.append(ValidatorResult("required_fields", "pass", "info", "All candidates have title, url, source_url, and employer."))

    empty_fields: list[str] = []
    for index, candidate in enumerate(candidates):
        for field in ("title", "url", "source_url", "employer"):
            value = candidate.get(field)
            if isinstance(value, str) and value.strip() == "":
                empty_fields.append(f"candidate[{index}].{field}")
    if empty_fields:
        warnings.append("Some extracted fields are empty: " + ", ".join(empty_fields[:8]))
        results.append(
            ValidatorResult(
                "no_empty_fields",
                "warn",
                "major",
                "Empty extracted fields: " + ", ".join(empty_fields[:8]),
            )
        )
    else:
        results.append(ValidatorResult("no_empty_fields", "pass", "info", "No empty extracted fields among checked candidate fields."))

    disallowed_urls = [
        candidate.get("url", "")
        for candidate in candidates
        if candidate.get("url") and not is_allowed_candidate_domain(source_url, candidate["url"])
    ]
    if disallowed_urls:
        results.append(
            ValidatorResult(
                "url_allowlist",
                "fail",
                "blocking",
                "Candidate URLs fall outside the source domain allowlist: " + ", ".join(disallowed_urls[:5]),
            )
        )
    else:
        results.append(ValidatorResult("url_allowlist", "pass", "info", "Candidate URLs stay within the source/domain allowlist."))

    normalized_urls: dict[str, int] = {}
    normalized_triples: dict[str, int] = {}
    duplicate_urls: list[str] = []
    duplicate_role_triples: list[str] = []
    for candidate in candidates:
        normalized_url = normalize_url_without_fragment(candidate.get("url", ""))
        if normalized_url:
            normalized_urls[normalized_url] = normalized_urls.get(normalized_url, 0) + 1
        triple_key = "|".join(
            [
                normalize_for_matching(candidate.get("employer", "")),
                normalize_for_matching(candidate.get("title", "")),
                normalize_for_matching(candidate.get("location", "")),
            ]
        )
        normalized_triples[triple_key] = normalized_triples.get(triple_key, 0) + 1
    duplicate_urls.extend(url for url, count in normalized_urls.items() if count > 1)
    duplicate_role_triples.extend(triple for triple, count in normalized_triples.items() if count > 1)
    if duplicate_urls:
        results.append(
            ValidatorResult(
                "duplicate_jobs",
                "fail",
                "blocking",
                "Duplicate candidate URLs detected: " + ", ".join(duplicate_urls[:6]),
            )
        )
    elif duplicate_role_triples:
        warnings.append("Possible duplicate roles share employer, title, and location.")
        results.append(
            ValidatorResult(
                "duplicate_jobs",
                "warn",
                "major",
                "Possible duplicate roles share employer/title/location: " + ", ".join(duplicate_role_triples[:6]),
            )
        )
    else:
        results.append(
            ValidatorResult(
                "duplicate_jobs",
                "pass",
                "info",
                "No duplicate candidate URLs detected; role/title/location combinations are unique.",
            )
        )

    suspicious: list[str] = []
    for candidate in candidates:
        reasons = _suspicious_candidate(candidate)
        if reasons:
            suspicious.append(f"{candidate.get('title', 'unknown')}: {', '.join(reasons)}")
    if suspicious and len(suspicious) == len(candidates):
        results.append(
            ValidatorResult(
                "listing_kind",
                "fail",
                "blocking",
                "All surfaced candidates look like navigation or non-job content: " + "; ".join(suspicious[:4]),
            )
        )
    elif suspicious:
        warnings.append("Some candidates look suspiciously non-job-like.")
        results.append(
            ValidatorResult(
                "listing_kind",
                "warn",
                "major",
                "Some candidates look suspicious: " + "; ".join(suspicious[:4]),
            )
        )
    else:
        results.append(ValidatorResult("listing_kind", "pass", "info", "Surfaced candidates look like job listings."))

    if canary_title or canary_url:
        normalized_canary_title = normalize_for_matching(canary_title)
        normalized_canary_url = normalize_url_without_fragment(canary_url) if canary_url else ""
        canary_found = False
        for candidate in candidates:
            if normalized_canary_url and normalize_url_without_fragment(candidate.get("url", "")) == normalized_canary_url:
                canary_found = True
                break
            if normalized_canary_title and normalize_for_matching(candidate.get("title", "")) == normalized_canary_title:
                canary_found = True
                break
        if canary_found:
            results.append(ValidatorResult("canary_present", "pass", "info", "Canary was found in the extracted candidates."))
        else:
            results.append(
                ValidatorResult(
                    "canary_present",
                    "fail",
                    "blocking",
                    "Canary was not found in the extracted candidates.",
                )
            )
    else:
        results.append(ValidatorResult("canary_present", "skip", "info", "No canary provided."))

    if not candidates:
        results.append(ValidatorResult("detail_depth", "skip", "info", "No candidates to evaluate for role-detail depth."))
    elif any(_candidate_has_detail(candidate) for candidate in candidates):
        results.append(
            ValidatorResult(
                "detail_depth",
                "pass",
                "info",
                "At least one candidate carries substantive role detail beyond title-level metadata.",
            )
        )
    else:
        sampled_pages: list[str] = []
        seen_urls: set[str] = set()
        for candidate in candidates:
            normalized_url = normalize_url_without_fragment(candidate.get("url", ""))
            if not normalized_url or normalized_url in seen_urls:
                continue
            seen_urls.add(normalized_url)
            try:
                raw_text = raw_text_fetcher(normalized_url, timeout_seconds)
            except Exception:
                continue
            categories = sorted(_raw_detail_categories(raw_text))
            if categories:
                sampled_pages.append(f"{normalized_url} ({', '.join(categories)})")
            if len(seen_urls) >= 3:
                break
        if sampled_pages:
            results.append(
                ValidatorResult(
                    "detail_depth",
                    "fail",
                    "blocking",
                    "Sampled job pages expose detail sections, but extracted candidates still lack substantive role detail: "
                    + "; ".join(sampled_pages[:3]),
                )
            )
        else:
            warnings.append("Candidates only contain title/card-level metadata without substantive role detail.")
            results.append(
                ValidatorResult(
                    "detail_depth",
                    "warn",
                    "major",
                    "Candidates only contain title/card-level metadata; no tasks, qualifications, compensation, or substantive notes were extracted.",
                )
            )

    sparse_optional = [
        candidate
        for candidate in candidates
        if normalize_whitespace(candidate.get("location", "")) in ("", "unknown")
        and normalize_whitespace(candidate.get("notes", "")) == ""
    ]
    if candidates and len(sparse_optional) == len(candidates):
        warnings.append("All candidates are sparse: missing location and notes.")
        results.append(
            ValidatorResult(
                "sparse_extraction",
                "warn",
                "major",
                "All candidates are missing both location and notes; extraction quality looks low.",
            )
        )
    else:
        results.append(ValidatorResult("sparse_extraction", "pass", "info", "At least one candidate carries extracted detail beyond title and URL."))

    blocking = [result for result in results if result.status == "fail"]
    warns = [result for result in results if result.status == "warn"]
    if blocking:
        confidence = "failed"
    elif warns:
        confidence = "low"
    else:
        confidence = "high"

    return {
        "confidence": confidence,
        "checks": [result.__dict__ for result in results],
        "warnings": warnings,
    }


def _build_reviewer_context(
    artifact_path: Path,
    source: dict[str, Any],
    canary_title: str,
    canary_url: str,
    timeout_seconds: int,
    raw_text_fetcher: Callable[[str, int], str] = fetch_text,
) -> dict[str, Any]:
    candidates = list(source.get("candidates", []))
    reviewer_candidates = _select_reviewer_candidates(
        candidates,
        canary_title=canary_title,
        canary_url=canary_url,
    )
    samples: list[dict[str, str]] = []
    sample_urls: list[str] = []
    if canary_url:
        sample_urls.append(canary_url)
    sample_urls.extend(candidate.get("url", "") for candidate in reviewer_candidates[:3])

    seen_urls: set[str] = set()
    for url in sample_urls:
        normalized = normalize_url_without_fragment(url)
        if not normalized or normalized in seen_urls:
            continue
        seen_urls.add(normalized)
        try:
            raw_text = truncate_text(strip_html_fragment(raw_text_fetcher(normalized, timeout_seconds)), 2000)
        except Exception as exc:
            raw_text = f"FETCH_FAILED: {exc}"
        samples.append({"url": normalized, "raw_text": raw_text})

    return {
        "artifact_path": str(artifact_path),
        "source": {
            "source": source.get("source"),
            "source_url": source.get("source_url"),
            "discovery_mode": source.get("discovery_mode"),
            "status": source.get("status"),
            "search_terms_tried": source.get("search_terms_tried", []),
            "candidate_count_total": len(candidates),
            "candidate_count_shared": len(reviewer_candidates),
            "candidate_context_truncated": len(reviewer_candidates) < len(candidates),
            "candidates": reviewer_candidates,
        },
        "canary": {"title": canary_title, "url": canary_url},
        "raw_samples": samples,
    }


def build_reviewer_command(root: Path, reviewer_bin: Path, provider: str | None = None) -> list[str]:
    return build_provider_reviewer_command(resolve_agent_provider(provider or "codex"), root, reviewer_bin)


def review_source_with_llm(
    root: Path,
    artifact_path: Path,
    source: dict[str, Any],
    *,
    canary_title: str,
    canary_url: str,
    reviewer_bin: Path | None,
    timeout_seconds: int,
    provider: str | None = None,
) -> dict[str, Any]:
    if reviewer_bin is None or not reviewer_bin.exists():
        return {
            "status": "blocked",
            "defects": [],
            "error": "No reviewer binary available.",
        }

    context = _build_reviewer_context(artifact_path, source, canary_title, canary_url, timeout_seconds)
    canary_instruction = (
        "If canary.title and canary.url are both empty, treat the canary as not provided and do not emit canary_missing.\n"
    )
    prompt = (
        "Review this job-source extraction and return JSON only.\n"
        "Allowed defect types: missing_field, wrong_content, navigation_noise, partial_description, canary_missing, bad_url, duplication, other.\n"
        "Allowed severities: blocking, major, minor.\n"
        "Return exactly: {\"defects\": [...]}.\n"
        "If no issues, return {\"defects\": []}.\n\n"
        + canary_instruction
        + json.dumps(context, ensure_ascii=False, indent=2)
    )
    try:
        command = build_reviewer_command(root, reviewer_bin, provider)
    except Exception as exc:
        return {"status": "blocked", "defects": [], "error": str(exc)}
    try:
        completed = subprocess.run(
            command,
            input=prompt,
            text=True,
            capture_output=True,
            check=False,
            cwd=root,
            timeout=timeout_seconds,
        )
    except Exception as exc:
        return {"status": "blocked", "defects": [], "error": str(exc)}

    if completed.returncode != 0:
        return {
            "status": "blocked",
            "defects": [],
            "error": completed.stderr.strip() or f"reviewer exited with status {completed.returncode}",
        }

    try:
        parsed = extract_json_from_text(completed.stdout)
    except Exception as exc:
        return {
            "status": "blocked",
            "defects": [],
            "error": f"reviewer output was not parseable JSON: {exc}",
            "raw_output": completed.stdout.strip(),
        }

    defects = parsed.get("defects", []) if isinstance(parsed, dict) else []
    if not isinstance(defects, list):
        return {
            "status": "blocked",
            "defects": [],
            "error": "reviewer output did not contain a defects list",
            "raw_output": completed.stdout.strip(),
        }

    normalized_defects: list[dict[str, str]] = []
    for defect in defects:
        if not isinstance(defect, dict):
            continue
        normalized_defect = {
            "type": str(defect.get("type", "other")),
            "severity": str(defect.get("severity", "minor")),
            "source": str(defect.get("source", source.get("source", ""))),
            "candidate_url": str(defect.get("candidate_url", defect.get("url", ""))),
            "canary_title": str(defect.get("canary_title", canary_title)),
            "observed": normalize_whitespace(str(defect.get("observed", defect.get("message", "")))),
            "expected": normalize_whitespace(str(defect.get("expected", ""))),
            "repair_hint": normalize_whitespace(str(defect.get("repair_hint", defect.get("hint", "")))),
            "repro_step": normalize_whitespace(str(defect.get("repro_step", defect.get("path", "")))),
        }
        if not canary_title and not canary_url and normalized_defect["type"] == "canary_missing":
            continue
        normalized_defects.append(normalized_defect)

    return {
        "status": "completed",
        "defects": normalized_defects,
    }


REPAIR_TEST_HINTS_BY_SOURCE = {
    "IBM Research": "tests/integration/test_discover_followup_sources.py",
}

REPAIR_TEST_HINTS_BY_DISCOVERY_MODE = {
    "ashby_api": "tests/integration/test_discover_followup_sources.py",
    "ashby_html": "tests/integration/test_discover_followup_sources.py",
    "asml_browser": "tests/integration/test_discover_asml_browser.py",
    "automattic_browser": "tests/contract/test_source_contract.py",
    "auswaertiges_amt_json": "tests/integration/test_discover_public_service_sources.py",
    "bnd_career_search": "tests/integration/test_discover_public_service_sources.py",
    "bosch_autocomplete": "tests/contract/test_source_contract.py",
    "browser": "tests/integration/test_discover_meta_browser.py",
    "bundeswehr_jobsuche": "tests/integration/test_discover_public_service_sources.py",
    "coinbase_browser": "tests/contract/test_source_contract.py",
    "cybernetica_teamdash": "tests/contract/test_source_contract.py",
    "eightfold_api": "tests/integration/test_discover_followup_sources.py",
    "enbw_phenom": "tests/integration/test_discover_public_service_sources.py",
    "getro_api": "tests/integration/test_discover_followup_sources.py",
    "greenhouse_api": "tests/integration/test_discover_followup_sources.py",
    "hackernews_jobs": "tests/integration/test_discover_yc_and_hn_jobs.py",
    "hackernews_whoishiring_api": "tests/integration/test_discover_yc_and_hn_jobs.py",
    "helsing_browser": "tests/integration/test_discover_public_service_sources.py",
    "ibm_api": "tests/integration/test_discover_followup_sources.py",
    "icims_html": "tests/contract/test_source_contract.py",
    "infineon_api": "tests/integration/test_discover_followup_sources.py",
    "leastauthority_careers": "tests/integration/test_discover_pcd_team.py",
    "neclab_jobs": "tests/contract/test_source_contract.py",
    "partisia_site": "tests/contract/test_source_contract.py",
    "pcd_team": "tests/integration/test_discover_pcd_team.py",
    "personio_page": "tests/integration/test_discover_followup_sources.py",
    "qedit_inline": "tests/contract/test_source_contract.py",
    "qusecure_careers": "tests/contract/test_source_contract.py",
    "recruitee_inline": "tests/integration/test_discover_public_service_sources.py",
    "rheinmetall_html": "tests/integration/test_discover_public_service_sources.py",
    "service_bund_links": "tests/integration/test_discover_service_bund.py",
    "service_bund_search": "tests/integration/test_discover_service_bund.py",
    "secunet_jobboard": "tests/contract/test_source_contract.py",
    "thales_browser": "tests/contract/test_source_contract.py",
    "thales_html": "tests/contract/test_source_contract.py",
    "trailofbits_browser": "tests/integration/test_discover_asml_browser.py",
    "workable_api": "tests/integration/test_discover_followup_sources.py",
    "workday_api": "tests/integration/test_discover_followup_sources.py",
    "iacr_jobs": "tests/integration/test_discover_iacr_jobs.py",
    "verfassungsschutz_rss": "tests/integration/test_discover_public_service_sources.py",
    "yc_jobs_board": "tests/integration/test_discover_yc_and_hn_jobs.py",
}


REPAIR_FILES_BY_DISCOVERY_MODE = {
    "ashby_api": "scripts/discover/sources/ashby.py",
    "ashby_html": "scripts/discover/sources/ashby.py",
    "asml_browser": "scripts/discover/sources/browser.py",
    "automattic_browser": "scripts/discover/sources/browser.py",
    "auswaertiges_amt_json": "scripts/discover/sources/public_service.py",
    "bnd_career_search": "scripts/discover/sources/public_service.py",
    "bosch_autocomplete": "scripts/discover/sources/public_service.py",
    "browser": "scripts/discover/sources/browser.py",
    "bundeswehr_jobsuche": "scripts/discover/sources/bundeswehr.py",
    "coinbase_browser": "scripts/discover/sources/browser.py",
    "cybernetica_teamdash": "scripts/discover/sources/generic_html.py",
    "eightfold_api": "scripts/discover/sources/eightfold.py",
    "enbw_phenom": "scripts/discover/sources/enbw.py",
    "getro_api": "scripts/discover/sources/getro.py",
    "greenhouse_api": "scripts/discover/sources/greenhouse.py",
    "hackernews_jobs": "scripts/discover/sources/hackernews.py",
    "hackernews_whoishiring_api": "scripts/discover/sources/hackernews.py",
    "helsing_browser": "scripts/discover/sources/browser.py",
    "html": "scripts/discover/sources/generic_html.py",
    "iacr_jobs": "scripts/discover/sources/iacr.py",
    "ibm_api": "scripts/discover/sources/ibm.py",
    "icims_html": "scripts/discover/sources/generic_html.py",
    "infineon_api": "scripts/discover/sources/eightfold.py",
    "leastauthority_careers": "scripts/discover/sources/static_pages.py",
    "lever_json": "scripts/discover/sources/lever.py",
    "neclab_jobs": "scripts/discover/sources/static_pages.py",
    "partisia_site": "scripts/discover/sources/static_pages.py",
    "pcd_team": "scripts/discover/sources/static_pages.py",
    "personio_page": "scripts/discover/sources/personio.py",
    "qedit_inline": "scripts/discover/sources/static_pages.py",
    "qusecure_careers": "scripts/discover/sources/static_pages.py",
    "recruitee_inline": "scripts/discover/sources/recruitee.py",
    "rheinmetall_html": "scripts/discover/sources/rheinmetall.py",
    "service_bund_links": "scripts/discover/sources/service_bund.py",
    "service_bund_search": "scripts/discover/sources/service_bund.py",
    "secunet_jobboard": "scripts/discover/sources/generic_html.py",
    "thales_browser": "scripts/discover/sources/browser.py",
    "thales_html": "scripts/discover/sources/thales.py",
    "trailofbits_browser": "scripts/discover/sources/browser.py",
    "workable_api": "scripts/discover/sources/workable.py",
    "workday_api": "scripts/discover/sources/workday.py",
    "verfassungsschutz_rss": "scripts/discover/sources/public_service.py",
    "yc_jobs_board": "scripts/discover/sources/yc.py",
}


def infer_repair_test_hint(source: dict[str, Any]) -> str:
    source_name = normalize_whitespace(str(source.get("source", "")))
    if source_name in REPAIR_TEST_HINTS_BY_SOURCE:
        return REPAIR_TEST_HINTS_BY_SOURCE[source_name]
    discovery_mode = normalize_whitespace(str(source.get("discovery_mode", "")))
    return REPAIR_TEST_HINTS_BY_DISCOVERY_MODE.get(discovery_mode, "")


def infer_repair_likely_file(source: dict[str, Any]) -> str:
    discovery_mode = normalize_whitespace(str(source.get("discovery_mode", "")))
    return REPAIR_FILES_BY_DISCOVERY_MODE.get(discovery_mode, "scripts/discover_jobs.py")


def _reviewer_defect_text(defect: dict[str, Any]) -> str:
    return normalize_whitespace(
        str(defect.get("observed") or defect.get("repair_hint") or defect.get("expected") or defect.get("type", ""))
    )


def _failure_mode_from_check(check: dict[str, Any]) -> str:
    return {
        "canary_present": "missing_canary",
        "detail_depth": "missing_detail",
        "duplicate_jobs": "duplication",
        "listing_kind": "candidate_noise",
        "url_allowlist": "bad_url",
    }.get(str(check.get("name", "")), "validator_failure")


def _failure_mode_from_defect(defect: dict[str, Any]) -> str:
    defect_type = normalize_for_matching(str(defect.get("type", "")))
    if defect_type == "bad_url":
        return "bad_url"
    if defect_type == "canary_missing":
        return "missing_canary"
    if defect_type == "duplication":
        return "duplication"
    if defect_type == "partial_description":
        return "missing_detail"
    if defect_type in {"navigation_noise", "wrong_content"}:
        return "candidate_noise"
    if defect_type == "missing_field":
        return "validator_failure"

    observed = normalize_for_matching(_reviewer_defect_text(defect))
    if any(
        marker in observed
        for marker in ("no descriptive notes", "raw sample text is empty", "cannot be spot-checked", "no substantive", "no detail")
    ):
        return "missing_detail"
    if any(
        marker in observed
        for marker in ("not plausibly aligned", "not aligned with", "not a postdoctoral", "not a research role", "not a job", "navigation", "noise")
    ):
        return "candidate_noise"
    if "duplicate" in observed:
        return "duplication"
    if "canary" in observed and "missing" in observed:
        return "missing_canary"
    if "url" in observed and any(marker in observed for marker in ("bad", "wrong", "invalid", "off-domain")):
        return "bad_url"
    return "unknown"


def _determine_failure_mode(failing_checks: list[dict[str, Any]], blocking_defects: list[dict[str, Any]]) -> str:
    if failing_checks:
        return _failure_mode_from_check(failing_checks[0])
    for defect in blocking_defects:
        failure_mode = _failure_mode_from_defect(defect)
        if failure_mode != "unknown":
            return failure_mode
    return "unknown"


def _collect_primary_evidence(failing_checks: list[dict[str, Any]], blocking_defects: list[dict[str, Any]]) -> list[str]:
    evidence: list[str] = []
    for check in failing_checks[:2]:
        details = truncate_text(str(check.get("details", "")), 180)
        if details:
            evidence.append(f"{check.get('name', 'validator')}: {details}")
    for defect in blocking_defects[:3]:
        details = truncate_text(_reviewer_defect_text(defect), 180)
        if details:
            evidence.append(f"{defect.get('type', 'other')}: {details}")

    deduped: list[str] = []
    for item in evidence:
        if item not in deduped:
            deduped.append(item)
    return deduped[:3]


def _build_target_outcome(failure_mode: str, *, canary_title: str, canary_url: str) -> str:
    canary_clause = " Preserve the canary in the extracted candidates." if canary_title or canary_url else ""
    if failure_mode == "candidate_noise":
        return "Fresh discovery artifact removes implausible candidates for this source while keeping only plausible track matches." + canary_clause
    if failure_mode == "missing_detail":
        return "Fresh discovery artifact keeps the relevant candidates and adds substantive extracted role detail in notes or detail fields." + canary_clause
    if failure_mode == "missing_canary":
        return "Fresh discovery artifact includes the canary candidate with the expected title or URL."
    if failure_mode == "bad_url":
        return "Fresh discovery artifact emits candidate URLs that point to the correct job detail pages for this source." + canary_clause
    if failure_mode == "duplication":
        return "Fresh discovery artifact contains each job at most once after source-specific deduplication and merge handling." + canary_clause
    if failure_mode == "validator_failure":
        return "Fresh discovery artifact satisfies the failing deterministic validator for this source." + canary_clause
    return "Fresh discovery artifact addresses the primary evidence in the repair ticket with the narrowest source-specific fix." + canary_clause


def _suggested_strategy_for_failure_mode(failure_mode: str) -> str:
    if failure_mode == "candidate_noise":
        return "tighten source-specific keep filter"
    if failure_mode == "missing_detail":
        return "enrich kept candidates"
    if failure_mode == "missing_canary":
        return "fix source-specific enumeration or keep logic"
    if failure_mode == "bad_url":
        return "fix source-specific URL extraction"
    if failure_mode == "duplication":
        return "fix candidate deduplication or merge logic"
    if failure_mode == "validator_failure":
        return "fix parser field extraction or validator mismatch"
    return "inspect likely file and make the narrowest source-specific fix consistent with the primary evidence"


def build_repair_ticket(
    track: str,
    source: dict[str, Any],
    deterministic: dict[str, Any],
    reviewer: dict[str, Any],
    *,
    canary_title: str,
    canary_url: str,
) -> dict[str, Any] | None:
    failing_checks = [check for check in deterministic["checks"] if check["status"] == "fail"]
    blocking_defects = [
        defect
        for defect in reviewer.get("defects", [])
        if defect.get("severity") in {"blocking", "major"}
    ]
    if not failing_checks and not blocking_defects:
        return None

    failure_mode = _determine_failure_mode(failing_checks, blocking_defects)
    primary_evidence = _collect_primary_evidence(failing_checks, blocking_defects)
    summary = ""
    defect_types: list[str] = []
    if failing_checks:
        primary = failing_checks[0]
        summary = primary["details"]
        defect_types.append(primary["name"])
    elif blocking_defects:
        primary = blocking_defects[0]
        summary = primary.get("observed") or primary.get("repair_hint") or primary.get("type", "reviewer defect")
        defect_types.append(primary.get("type", "other"))

    success_condition = "Deterministic validators all pass"
    if canary_title or canary_url:
        success_condition += " and the canary is present in the extracted candidates"
    success_condition += "."

    return {
        "status": "open",
        "track": track,
        "source": source.get("source", ""),
        "discovery_mode": source.get("discovery_mode", ""),
        "canary_title": canary_title,
        "canary_url": canary_url,
        "summary": summary,
        "defect_types": defect_types,
        "failing_checks": [check["name"] for check in failing_checks],
        "reviewer_defects": blocking_defects,
        "failure_mode": failure_mode,
        "primary_evidence": primary_evidence,
        "target_outcome": _build_target_outcome(
            failure_mode,
            canary_title=canary_title,
            canary_url=canary_url,
        ),
        "suggested_strategy": _suggested_strategy_for_failure_mode(failure_mode),
        "test_hint": infer_repair_test_hint(source),
        "likely_file": infer_repair_likely_file(source),
        "success_condition": success_condition,
        "non_goals": [
            "Do not redesign multiple sources at once.",
            "Do not broaden track search terms unless the defect explicitly requires it.",
        ],
    }
