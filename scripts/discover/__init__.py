"""Modular discovery package used by `scripts/discover_jobs.py`."""

from discover.core import (
    BrowserEnrichmentResult,
    BrowserPageResult,
    BrowserStrategy,
    Candidate,
    Coverage,
    SourceConfig,
    SourceTermRule,
    attach_source_identity,
    discover_source,
    failed_coverage,
    partial_browser_unavailable_coverage,
)

__all__ = [
    "BrowserEnrichmentResult",
    "BrowserPageResult",
    "BrowserStrategy",
    "Candidate",
    "Coverage",
    "SourceConfig",
    "SourceTermRule",
    "attach_source_identity",
    "discover_source",
    "failed_coverage",
    "partial_browser_unavailable_coverage",
]
