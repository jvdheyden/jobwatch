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
    )


def attach_source_identity(source: SourceConfig, coverage: Coverage) -> Coverage:
    coverage.source_id = coverage.source_id or source.source_id or source.source
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
