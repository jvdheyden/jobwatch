"""Avature careers search provider.

Supported discovery modes:
- `avature_html`
- `harman_html` (alias kept for existing Harman track configs)

Expected source URL shape:
- `https://<host>/[<locale>/]careers/SearchJobs`, an Avature-hosted search listing.
  Existing query parameters (for example a keyword search) are kept on every page.

Supported source filters:
- none

Known limitations:
- Pages through `jobOffset` until a page adds no new jobs, the reported result total is
  reached, or `AVATURE_MAX_PAGES` pages have been read.
- Reads listing cards only; job descriptions come from the shared description enrichment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


AVATURE_MAX_PAGES = 40
AVATURE_JOB_LINK_RE = re.compile(
    r"""<a\b[^>]*\bhref=(?P<quote>["'])(?P<href>[^"']*/careers/JobDetail/[^"'/?#]+/(?P<id>\d+))(?P=quote)[^>]*>(?P<text>.*?)</a>""",
    flags=re.DOTALL | re.IGNORECASE,
)
AVATURE_FIELD_RE = re.compile(
    r'<span class="list-item-(?P<field>location|department|workerType)">(?P<value>.*?)</span>',
    flags=re.DOTALL | re.IGNORECASE,
)
AVATURE_TOTAL_RE = re.compile(r'aria-label="(?P<total>[\d,.]+) results"', flags=re.IGNORECASE)
# Some sites prefix a field value with a label, e.g. `<strong> Location:</strong> Aarhus, Denmark`.
AVATURE_FIELD_LABEL_RE = re.compile(r"^\s*<strong\b[^>]*>[^<]*:\s*</strong>", flags=re.IGNORECASE)


@dataclass(frozen=True)
class AvatureJobCard:
    job_id: str
    title: str
    url: str
    location: str
    department: str
    worker_type: str


def _strip(value: str) -> str:
    return helpers.normalize_whitespace(helpers.strip_html_fragment(value))


def avature_page_url(source_url: str, offset: int) -> str:
    parsed = urlparse(source_url)
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "jobOffset"]
    if offset:
        query.append(("jobOffset", str(offset)))
    return urlunparse(parsed._replace(query=urlencode(query), fragment=""))


def extract_avature_total(html: str) -> int | None:
    match = AVATURE_TOTAL_RE.search(html)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group("total"))
    return int(digits) if digits else None


def extract_avature_job_cards(html: str, page_url: str) -> list[AvatureJobCard]:
    """Return one card per job id, in page order.

    Each card's metadata is read from the HTML between its first JobDetail link and the
    next job's first link, so repeated "More information" links for the same job are ignored.
    """
    first_links: list[tuple[str, str, str, int]] = []
    seen_ids: set[str] = set()
    for match in AVATURE_JOB_LINK_RE.finditer(html):
        job_id = match.group("id")
        if job_id in seen_ids:
            continue
        seen_ids.add(job_id)
        url = helpers.normalize_url_without_fragment(urljoin(page_url, unescape(match.group("href"))))
        first_links.append((job_id, url, _strip(match.group("text")), match.end()))

    cards: list[AvatureJobCard] = []
    for index, (job_id, url, title, start) in enumerate(first_links):
        if urlparse(url).scheme not in {"http", "https"}:
            continue
        end = first_links[index + 1][3] if index + 1 < len(first_links) else len(html)
        fields = {
            field_match.group("field").lower(): _strip(AVATURE_FIELD_LABEL_RE.sub("", field_match.group("value")))
            for field_match in AVATURE_FIELD_RE.finditer(html, start, end)
        }
        cards.append(
            AvatureJobCard(
                job_id=job_id,
                title=title or "unknown",
                url=url,
                location=fields.get("location") or "unknown",
                department=fields.get("department", ""),
                worker_type=fields.get("workertype", ""),
            )
        )
    return cards


def discover_avature_html(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    candidates_by_url: dict[str, Candidate] = {}
    limitations: list[str] = []
    seen_ids: set[str] = set()
    total: int | None = None
    pages_scanned = 0
    offset = 0
    status = "complete"

    while pages_scanned < AVATURE_MAX_PAGES:
        page_url = avature_page_url(source.url, offset)
        try:
            html = http.fetch_text(page_url, timeout_seconds)
        except Exception as exc:
            if not pages_scanned:
                raise
            status = "partial"
            limitations.append(f"Stopped Avature pagination at jobOffset={offset}: {type(exc).__name__}: {exc}")
            break
        pages_scanned += 1
        if total is None:
            total = extract_avature_total(html)

        cards = extract_avature_job_cards(html, page_url)
        new_cards = [card for card in cards if card.job_id not in seen_ids]
        if not new_cards:
            break
        for card in new_cards:
            seen_ids.add(card.job_id)
            searchable_text = " ".join(
                part for part in [card.title, card.department, card.location, card.worker_type] if part
            )
            matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
            if not matched_terms:
                continue
            note_parts = ["Enumerated through Avature search listing"]
            if card.department:
                note_parts.append(f"Department: {card.department}")
            if card.worker_type:
                note_parts.append(f"Type: {card.worker_type}")
            helpers.merge_candidate(
                candidates_by_url,
                Candidate(
                    employer=source.source,
                    title=card.title,
                    url=card.url,
                    source_url=source.url,
                    location=card.location,
                    remote=helpers.infer_remote_status(card.location, searchable_text),
                    matched_terms=matched_terms,
                    notes="; ".join(note_parts),
                ),
            )

        offset += len(cards)
        if total is not None and offset >= total:
            break
    else:
        status = "partial"
        limitations.append(f"Avature pagination stopped at the {AVATURE_MAX_PAGES}-page cap.")

    # A shortfall against the reported total, including zero parsed jobs, is a
    # failed extraction; only a listing that reports 0 results is a valid empty scan.
    if total is not None and len(seen_ids) < total:
        status = "partial"
        limitations.append(f"Avature listing reported {total} results but {len(seen_ids)} were enumerated.")
    elif not seen_ids and total is None:
        status = "partial"
        limitations.append("Avature listing showed neither a result count nor JobDetail links.")
    elif not seen_ids:
        limitations.append("No Avature JobDetail links were visible on the search listing.")

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status=status,
        listing_pages_scanned=pages_scanned,
        search_terms_tried=terms,
        result_pages_scanned=f"avature_pages={pages_scanned}",
        direct_job_pages_opened=0,
        enumerated_jobs=len(seen_ids),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("avature_html", "harman_html"), discover=discover_avature_html)
