"""Kula public job feed provider.

Supported discovery modes:
- `kula_rss`

Expected source URL shape:
- `https://careers.kula.ai/<company>`, the hosted careers page. The provider
  reads the company's public RSS feed at `https://careers.kula.ai/<company>/feed`.

The feed carries one item per job and office, so a job listed in two offices
appears twice; items are merged by the numeric job id in their link. Each item
includes the full posting HTML, which becomes the candidate description.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote, urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


KULA_NS = "{https://kula.ai/rss}"
# Item links look like `/<company>/<job-id>/apply`; job pages like `/<company>/<job-id>-<slug>`.
KULA_JOB_PATH_RE = re.compile(r"^/[^/]+/(?P<id>\d+)(?:[-/]|$)")
KULA_WORKPLACE_REMOTE = {"REMOTE": "remote", "HYBRID": "hybrid", "OFFICE": "on-site"}


def kula_company_slug(source_url: str) -> str:
    path_bits = [bit for bit in urlparse(source_url).path.split("/") if bit]
    if not path_bits:
        raise ValueError(f"Could not derive Kula company slug from {source_url}")
    return path_bits[0]


def _base_url(source_url: str) -> str:
    parsed = urlparse(source_url)
    return f"{parsed.scheme or 'https'}://{parsed.netloc}"


def kula_feed_url(source_url: str) -> str:
    return f"{_base_url(source_url)}/{quote(kula_company_slug(source_url))}/feed"


def _text(element: ET.Element, name: str) -> str:
    return helpers.normalize_whitespace(element.findtext(name) or "")


def _label(value: str) -> str:
    # FULL_TIME -> Full time
    return value.replace("_", " ").capitalize() if value else ""


def _location(item: ET.Element) -> str:
    location = item.find(f"{KULA_NS}location")
    if location is None:
        return ""
    parts = [_text(location, f"{KULA_NS}{field}") for field in ("city", "state", "country")]
    text = ", ".join(part for part in parts if part)
    return text or _text(location, f"{KULA_NS}officeName")


def _feed_jobs(xml_text: str) -> tuple[dict[str, dict[str, Any]], int]:
    """Return feed jobs keyed by job id, plus the number of items without one."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"Kula feed was not valid XML: {exc}") from exc
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise ValueError("Kula feed did not contain an RSS channel")

    jobs: dict[str, dict[str, Any]] = {}
    missing_id = 0
    for item in channel.findall("item"):
        link = _text(item, "link") or _text(item, "guid")
        match = KULA_JOB_PATH_RE.match(urlparse(link).path) if link else None
        if not match:
            missing_id += 1
            continue
        job = jobs.setdefault(
            match.group("id"),
            {
                "title": _text(item, "title"),
                "department": _text(item, "category"),
                "workplace": _text(item, f"{KULA_NS}workplace").upper(),
                "employment_type": _label(_text(item, f"{KULA_NS}employmentType")),
                "description": item.findtext("description") or "",
                "locations": [],
            },
        )
        location = _location(item)
        if location and location not in job["locations"]:
            job["locations"].append(location)
    return jobs, missing_id


def discover_kula_rss(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    feed_url = kula_feed_url(source.url)
    jobs, missing_id = _feed_jobs(http.fetch_text(feed_url, timeout_seconds))
    company_url = f"{_base_url(source.url)}/{quote(kula_company_slug(source.url))}"

    candidates_by_url: dict[str, Candidate] = {}
    for job_id, job in jobs.items():
        title = job["title"] or "unknown"
        location = "; ".join(job["locations"]) or "unknown"
        workplace = _label(job["workplace"])
        searchable_text = " ".join(
            part for part in [title, job["department"], location, workplace, job["employment_type"]] if part
        )
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not matched_terms:
            continue
        note_parts = ["Enumerated through Kula job feed"]
        if job["department"]:
            note_parts.append(f"Department: {job['department']}")
        if workplace:
            note_parts.append(f"Workplace: {workplace}")
        if job["employment_type"]:
            note_parts.append(f"Type: {job['employment_type']}")
        candidate = Candidate(
            employer=source.source,
            title=title,
            # `/<company>/<id>` redirects to the posting's current slug URL.
            url=f"{company_url}/{job_id}",
            source_url=source.url,
            location=location,
            remote=KULA_WORKPLACE_REMOTE.get(job["workplace"]) or helpers.infer_remote_status(location),
            matched_terms=matched_terms,
            notes="; ".join(note_parts),
        )
        helpers.set_candidate_description(candidate, helpers.visible_text_from_html(job["description"]))
        helpers.merge_candidate(candidates_by_url, candidate)

    limitations: list[str] = []
    if missing_id:
        limitations.append(f"{missing_id} Kula feed item(s) had no job id in their link and were skipped.")

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="partial" if limitations else "complete",
        listing_pages_scanned=1,
        search_terms_tried=terms,
        result_pages_scanned=f"rss={feed_url}",
        direct_job_pages_opened=0,
        enumerated_jobs=len(jobs),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("kula_rss",), discover=discover_kula_rss)
