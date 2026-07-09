"""Core models and dispatch helpers for deterministic job discovery."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceConfig:
    source: str
    url: str
    discovery_mode: str
    last_checked: str | None
    cadence_group: str
    filters: dict[str, list[str]] = field(default_factory=dict)
    source_id: str = ""


@dataclass
class SourceTermRule:
    terms: list[str]
    mode: str = "append"


@dataclass
class Candidate:
    employer: str
    title: str
    url: str
    source_url: str
    alternate_url: str = ""
    location: str = "unknown"
    remote: str = "unknown"
    matched_terms: list[str] = field(default_factory=list)
    notes: str = ""
    description: str = ""
    description_truncated: bool = False


@dataclass
class Coverage:
    source: str
    source_url: str
    discovery_mode: str
    cadence_group: str
    last_checked: str | None
    due_today: bool
    status: str
    listing_pages_scanned: int | str
    search_terms_tried: list[str]
    result_pages_scanned: str
    direct_job_pages_opened: int
    enumerated_jobs: int
    matched_jobs: int
    limitations: list[str] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    source_id: str = ""
    filters: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class BrowserPageResult:
    candidates: list[Candidate]
    raw_ids: list[str]
    visible_results: int
    declared_total: int | None
    page_signature: str
    limitations: list[str] = field(default_factory=list)


@dataclass
class BrowserEnrichmentResult:
    direct_job_pages_opened: int = 0
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BrowserStrategy:
    search_url_builder: Callable[[SourceConfig, str, int], str]
    extract_page: Callable[[Any, SourceConfig, str, list[str], int], BrowserPageResult]
    prepare_page: Callable[[Any], None] | None = None
    advance_page: Callable[[Any, SourceConfig, str, int], bool] | None = None
    enrich_candidates: Callable[[Any, dict[str, Candidate], list[str], int], BrowserEnrichmentResult] | None = None
    override_terms: tuple[str, ...] | None = None
    supports_pagination: bool = False
    cumulative_results: bool = False
    page_size: int | None = None
    max_pages: int = 1


def partial_browser_unavailable_coverage(source: SourceConfig, terms: list[str], limitation: str) -> Coverage:
    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="partial",
        listing_pages_scanned="unknown",
        search_terms_tried=terms,
        result_pages_scanned="unknown",
        direct_job_pages_opened=0,
        enumerated_jobs=0,
        matched_jobs=0,
        limitations=[limitation],
        candidates=[],
        source_id=source.source_id,
        filters={key: list(values) for key, values in source.filters.items()},
    )


def attach_source_identity(source: SourceConfig, coverage: Coverage) -> Coverage:
    coverage.source_id = coverage.source_id or source.source_id or source.source
    coverage.filters = {key: list(values) for key, values in source.filters.items()}
    return coverage


def failed_coverage(source: SourceConfig, terms: list[str], limitation: str) -> Coverage:
    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="failed",
        listing_pages_scanned="unknown",
        search_terms_tried=terms,
        result_pages_scanned="unknown",
        direct_job_pages_opened=0,
        enumerated_jobs=0,
        matched_jobs=0,
        limitations=[limitation],
        candidates=[],
        source_id=source.source_id,
        filters={key: list(values) for key, values in source.filters.items()},
    )


def enrich_candidate_descriptions(
    coverage: Coverage,
    timeout_seconds: int,
    *,
    char_budget: int | None = None,
    max_seconds: float | None = None,
    max_fetches: int | None = None,
) -> None:
    """Fetch each matched candidate's URL and store the JD body in `description`.

    The runner calls this after track filtering, so only candidates that
    survived both term matching and track filters trigger a fetch. Candidates a
    provider already populated are skipped. Fetches continue until the wall-clock budget
    (`max_seconds`) is exhausted, or the hard ceiling (`max_fetches`) is reached
    as a runaway-protection safety net. Per-candidate fetch failures are recorded
    as a single coverage limitation rather than aborting; budget exhaustion is
    recorded separately so coverage truncation stays visible.
    """

    import time

    from discover import helpers, http
    from discover.constants import (
        JD_DESCRIPTION_CHAR_BUDGET,
        JD_FETCH_HARD_CEILING,
        JD_FETCH_WALL_CLOCK_BUDGET_SECONDS,
    )

    if char_budget is None:
        char_budget = JD_DESCRIPTION_CHAR_BUDGET
    if max_seconds is None:
        max_seconds = JD_FETCH_WALL_CLOCK_BUDGET_SECONDS
    if max_fetches is None:
        max_fetches = JD_FETCH_HARD_CEILING

    attempts = 0
    failures = 0
    budget_exhausted_at: int | None = None
    started_at = time.monotonic()
    for candidate in coverage.candidates:
        if candidate.description:
            continue
        if attempts >= max_fetches or time.monotonic() - started_at >= max_seconds:
            budget_exhausted_at = attempts
            break
        url = candidate.url
        if not url or not url.lower().startswith(("http://", "https://")):
            continue
        # Failed fetches count toward the hard ceiling too, so a source full of
        # dead links cannot spin through unbounded fetch attempts.
        attempts += 1
        try:
            html = http.fetch_text(url, timeout_seconds)
        except Exception:
            failures += 1
            continue
        helpers.set_candidate_description(
            candidate, helpers.visible_text_from_html(html), char_budget=char_budget
        )
    if failures:
        coverage.limitations.append(f"JD fetch failed for {failures} candidate(s)")
    if budget_exhausted_at is not None:
        unfilled = sum(1 for c in coverage.candidates if not c.description)
        coverage.limitations.append(
            f"JD fetch budget exhausted after {budget_exhausted_at} fetch attempt(s); "
            f"{unfilled} candidate(s) left without description"
        )


def discover_source(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    """Dispatch a source through the provider registry with legacy failure semantics."""

    from discover.registry import load_registry

    adapter = load_registry().get(source.discovery_mode)
    if not adapter:
        return failed_coverage(source, terms, f"Unsupported discovery_mode: {source.discovery_mode}")
    try:
        return attach_source_identity(source, adapter.discover(source, terms, timeout_seconds))
    except Exception as exc:  # pragma: no cover - defensive output for live runs
        return failed_coverage(source, terms, f"{type(exc).__name__}: {exc}")
