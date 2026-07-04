"""Harman careers (Avature) provider.

Supported discovery modes:
- `harman_html`

Expected source URL shape:
- A jobsearch.harman.com listing page exposing direct JobDetail links.
"""

from __future__ import annotations

import re

from discover.core import Coverage, SourceConfig
from discover.registry import SourceAdapter
from discover.sources.generic_html import discover_filtered_html_links


HARMAN_JOBSEARCH_JOBDETAIL_RE = re.compile(
    r"^https://jobsearch\.harman\.com/[^/]+/careers/JobDetail/[^/]+/\d+$"
)


def discover_harman_jobsearch_jobs(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    return discover_filtered_html_links(
        source,
        terms,
        timeout_seconds,
        lambda url: bool(HARMAN_JOBSEARCH_JOBDETAIL_RE.match(url)),
        notes="Enumerated through direct Harman careers (Avature) JobDetail links",
        limitation_if_empty="No Harman careers JobDetail links matching the standard Avature pattern were visible.",
    )


SOURCE = SourceAdapter(modes=("harman_html",), discover=discover_harman_jobsearch_jobs)
