"""AlphaTheta (Pioneer DJ) careers-page provider.

Supported discovery modes:
- `alphatheta_html`

Expected source URL shape:
- The alphatheta.com careers page. The page frequently reports "no open
  positions"; that marker is recognized as a complete-and-empty result
  instead of noise link enumeration. Otherwise discovery falls through to
  the generic static-HTML link enumeration.
"""

from __future__ import annotations

from discover import helpers, http
from discover.core import Coverage, SourceConfig
from discover.registry import SourceAdapter
from discover.sources.generic_html import discover_html


ALPHATHETA_NO_OPENINGS_MARKERS = (
    "no open positions",
    "no positions available",
)


def discover_alphatheta_jobs(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = http.fetch_text(source.url, timeout_seconds)
    visible_text = " ".join(helpers.extract_visible_text_lines_from_html(html)).lower()
    if any(marker in visible_text for marker in ALPHATHETA_NO_OPENINGS_MARKERS):
        parser = helpers.LinkCollector()
        parser.feed(html)
        return Coverage(
            source=source.source,
            source_url=source.url,
            discovery_mode=source.discovery_mode,
            cadence_group=source.cadence_group,
            last_checked=source.last_checked,
            due_today=False,
            status="complete",
            listing_pages_scanned=1,
            search_terms_tried=terms,
            result_pages_scanned="local_filter=1",
            direct_job_pages_opened=0,
            enumerated_jobs=len(parser.links),
            matched_jobs=0,
            limitations=["AlphaTheta career page reports no open positions"],
            candidates=[],
        )
    return discover_html(source, terms, timeout_seconds)


SOURCE = SourceAdapter(modes=("alphatheta_html",), discover=discover_alphatheta_jobs)
