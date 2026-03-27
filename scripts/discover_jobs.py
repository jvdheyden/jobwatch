#!/usr/bin/env python3
"""Deterministic discovery helper for track job sources.

This script turns the track source list into a machine-readable discovery plan
and, where possible, enumerates jobs through static HTML or stable board APIs.
It is intended to give the agent auditable coverage records for sources that
are brittle in prompt-only browsing.
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "job-agent-discovery/0.1"
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_BROWSER_TIMEOUT_MS = 60_000
MAX_BROWSER_PAGES = 10
GOOGLE_RESULTS_PAGE_SIZE = 20
IBM_RESULTS_PAGE_SIZE = 100
INFINEON_RESULTS_PAGE_SIZE = 10
WORKDAY_RESULTS_PAGE_SIZE = 20
THALES_RESULTS_PAGE_SIZE = 10
HTML_TAG_RE = re.compile(r"<[^>]+>")
IBM_SEARCH_API_URL = "https://www-api.ibm.com/search/api/v2"
ASHBY_JOB_BOARD_QUERY = """query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {
  jobBoard: jobBoardWithTeams(
    organizationHostedJobsPageName: $organizationHostedJobsPageName
  ) {
    teams {
      id
      name
      externalName
      parentTeamId
      __typename
    }
    jobPostings {
      id
      title
      teamId
      locationId
      locationName
      workplaceType
      employmentType
      secondaryLocations {
        ...JobPostingSecondaryLocationParts
        __typename
      }
      compensationTierSummary
      __typename
    }
    __typename
  }
}

fragment JobPostingSecondaryLocationParts on JobPostingSecondaryLocation {
  locationId
  locationName
  __typename
}"""
TECHNICAL_TITLE_HINTS = (
    "engineer",
    "engineering",
    "developer",
    "research",
    "researcher",
    "scientist",
    "software",
    "hardware",
    "architect",
    "specialist",
    "crypt",
    "protocol",
    "verification",
)
NON_TECHNICAL_TITLE_HINTS = (
    "manager",
    "account executive",
    "recruit",
    "sales",
    "marketing",
    "finance",
    "people",
    "operations",
    "counsel",
    "legal",
    "workplace",
    "talent",
    "procurement",
    "facilities",
    "campus",
    "policy",
    "grc",
    "executive assistant",
)
SPECIALIZED_SIGNAL_TERMS = {
    "cryptography",
    "cryptographer",
    "applied cryptography",
    "privacy engineering",
    "privacy-preserving",
    "privacy-enhancing technologies",
    "pets",
    "security research",
    "protocol security",
    "digital identity",
    "key management",
    "post-quantum",
    "post-quantum cryptography",
    "pqc",
    "mpc",
    "multi-party computation",
    "zero-knowledge",
    "zk",
    "fhe",
    "homomorphic encryption",
    "smart card",
    "embedded security",
    "secure hardware",
    "hsm",
}


@dataclass
class SourceConfig:
    source: str
    url: str
    discovery_mode: str
    last_checked: str | None
    cadence_group: str


@dataclass
class Candidate:
    employer: str
    title: str
    url: str
    source_url: str
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


@dataclass
class BrowserPageResult:
    candidates: list[Candidate]
    raw_ids: list[str]
    visible_results: int
    declared_total: int | None
    page_signature: str
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BrowserStrategy:
    search_url_builder: Callable[[SourceConfig, str, int], str]
    extract_page: Callable[[Any, SourceConfig, str, list[str], int], BrowserPageResult]
    prepare_page: Callable[[Any], None] | None = None
    advance_page: Callable[[Any, SourceConfig, str, int], bool] | None = None
    supports_pagination: bool = False
    cumulative_results: bool = False
    page_size: int | None = None
    max_pages: int = 1


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._current_href: str | None = None
        self._current_text: list[str] = []
        self.links: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr_map = dict(attrs)
        href = attr_map.get("href")
        if href:
            self._current_href = href
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            text = data.strip()
            if text:
                self._current_text.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._current_href is None:
            return
        text = " ".join(self._current_text).strip()
        self.links.append({"href": self._current_href, "text": text})
        self._current_href = None
        self._current_text = []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", default="core_crypto", help="Track directory name under tracks/")
    parser.add_argument("--today", default=date.today().isoformat(), help="Date used for cadence decisions")
    parser.add_argument("--source", action="append", default=[], help="Limit to one or more source names")
    parser.add_argument(
        "--cadence-group",
        choices=["every_run", "every_3_runs"],
        action="append",
        default=[],
        help="Limit to one or more cadence groups",
    )
    parser.add_argument("--due-only", action="store_true", help="Only include sources due today")
    parser.add_argument("--list-sources", action="store_true", help="List parsed sources and exit")
    parser.add_argument("--output", help="Write JSON output to this path instead of stdout")
    parser.add_argument("--latest-output", help="Also write the same JSON to a stable latest-artifact path")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="Network timeout")
    parser.add_argument("--plan-only", action="store_true", help="Parse config and compute due sources without fetching")
    return parser


def extract_section(text: str, heading: str) -> str:
    pattern = rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, text, flags=re.MULTILINE | re.DOTALL)
    if not match:
        raise ValueError(f"Missing section: {heading}")
    return match.group(1).strip()


def parse_markdown_table(section: str, cadence_group: str) -> list[SourceConfig]:
    lines = [line.rstrip() for line in section.splitlines() if line.strip()]
    if len(lines) < 3:
        return []
    headers = [part.strip() for part in lines[0].strip("|").split("|")]
    sources: list[SourceConfig] = []
    for line in lines[2:]:
        if not line.startswith("|"):
            continue
        values = [part.strip() for part in line.strip("|").split("|")]
        row = dict(zip(headers, values))
        sources.append(
            SourceConfig(
                source=row["source"],
                url=row["url"],
                discovery_mode=row.get("discovery_mode", "html"),
                last_checked=row.get("last_checked") or None,
                cadence_group=cadence_group,
            )
        )
    return sources


def parse_bullets(section: str) -> list[str]:
    bullets: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
    return bullets


def parse_track_terms(text: str) -> list[str]:
    section = extract_section(text, "Search terms")
    match = re.search(r"^### Track-wide terms\n(.*?)(?=^### |\Z)", section, flags=re.MULTILINE | re.DOTALL)
    if not match:
        return []
    return parse_bullets(match.group(1))


def parse_source_specific_terms(text: str) -> dict[str, list[str]]:
    section = extract_section(text, "Source-specific search terms")
    mapping: dict[str, list[str]] = {}
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        content = stripped[2:]
        if "\u2014" in content:
            source, terms = content.split("\u2014", 1)
        elif " - " in content:
            source, terms = content.split(" - ", 1)
        else:
            continue
        mapping[source.strip()] = [term.strip() for term in terms.split(",") if term.strip()]
    return mapping


def load_track_config(track: str) -> tuple[list[SourceConfig], list[str], dict[str, list[str]]]:
    path = ROOT / "tracks" / track / "sources.md"
    text = path.read_text()
    every_run = parse_markdown_table(extract_section(text, "Check every run"), "every_run")
    every_3_runs = parse_markdown_table(extract_section(text, "Check every 3 runs"), "every_3_runs")
    track_terms = parse_track_terms(text)
    source_terms = parse_source_specific_terms(text)
    return every_run + every_3_runs, track_terms, source_terms


def source_due_today(source: SourceConfig, today: date) -> bool:
    if source.cadence_group == "every_run":
        return True
    if not source.last_checked:
        return True
    try:
        last_checked = date.fromisoformat(source.last_checked)
    except ValueError:
        return True
    return (today - last_checked).days >= 3


def normalize_terms(track_terms: list[str], source_terms: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for term in track_terms + source_terms:
        lowered = term.strip().lower()
        if not lowered or lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(term.strip())
    return normalized


def fetch_text(url: str, timeout_seconds: int) -> str:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            context = ssl.create_default_context()
            with urlopen(request, timeout=timeout_seconds, context=context) as response:
                content_type = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(content_type, errors="replace")
        except Exception as exc:
            last_error = exc
            if attempt == 2:
                break
            time.sleep(0.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def fetch_json(url: str, timeout_seconds: int) -> Any:
    return json.loads(fetch_text(url, timeout_seconds))


def post_json(url: str, payload: Any, timeout_seconds: int, headers: dict[str, str] | None = None) -> Any:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request_headers = {"User-Agent": USER_AGENT, "Content-Type": "application/json", "Accept": "application/json"}
            if headers:
                request_headers.update(headers)
            request = Request(url, data=json.dumps(payload).encode(), headers=request_headers)
            context = ssl.create_default_context()
            with urlopen(request, timeout=timeout_seconds, context=context) as response:
                content_type = response.headers.get_content_charset() or "utf-8"
                return json.loads(response.read().decode(content_type, errors="replace"))
        except Exception as exc:
            last_error = exc
            if attempt == 2:
                break
            time.sleep(0.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def match_terms(text: str, terms: list[str]) -> list[str]:
    haystack = text.lower()
    return [term for term in terms if term.lower() in haystack]


def generated_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def strip_html_fragment(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(HTML_TAG_RE.sub(" ", value or ""))).strip()


def extract_json_object_after_marker(text: str, marker: str) -> dict[str, Any] | None:
    marker_index = text.find(marker)
    if marker_index == -1:
        return None
    start = text.find("{", marker_index + len(marker))
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : index + 1])
    return None


def join_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(join_text(item) for item in value if join_text(item))
    if isinstance(value, dict):
        return " ".join(join_text(item) for item in value.values() if join_text(item))
    return str(value)


def should_keep_candidate(title: str, matched_terms: list[str], searchable_text: str) -> bool:
    title_lower = title.lower()
    if any(token in title_lower for token in NON_TECHNICAL_TITLE_HINTS):
        return False
    if not matched_terms:
        return False
    title_term_matches = match_terms(title, matched_terms)
    title_is_technical = any(token in title_lower for token in TECHNICAL_TITLE_HINTS)
    specialized_matches = [term for term in matched_terms if term.lower() in SPECIALIZED_SIGNAL_TERMS]
    if title_term_matches and title_is_technical:
        return True
    if title_is_technical and specialized_matches:
        return True
    body_specialized_matches = [
        term for term in match_terms(searchable_text, matched_terms) if term.lower() in SPECIALIZED_SIGNAL_TERMS
    ]
    return title_is_technical and bool(body_specialized_matches)


def looks_like_job_link(text: str, href: str) -> bool:
    combined = f"{text} {href}".lower()
    patterns = (
        "job",
        "career",
        "opening",
        "position",
        "apply",
        "vacanc",
        "role",
        "engineer",
        "research",
        "security",
        "privacy",
        "crypt",
    )
    return any(pattern in combined for pattern in patterns)


def merge_candidate(candidates_by_url: dict[str, Candidate], candidate: Candidate) -> None:
    existing = candidates_by_url.get(candidate.url)
    if not existing:
        candidates_by_url[candidate.url] = candidate
        return
    existing.matched_terms = sorted(set(existing.matched_terms + candidate.matched_terms))
    if existing.location == "unknown" and candidate.location != "unknown":
        existing.location = candidate.location
    if existing.remote == "unknown" and candidate.remote != "unknown":
        existing.remote = candidate.remote
    if candidate.notes and candidate.notes not in existing.notes:
        existing.notes = "; ".join(part for part in [existing.notes, candidate.notes] if part)


def collect_job_links(html: str, base_url: str, path_fragment: str) -> dict[str, str]:
    parser = LinkCollector()
    parser.feed(html)
    links: dict[str, str] = {}
    for link in parser.links:
        absolute_url = urljoin(base_url, link["href"])
        if path_fragment not in absolute_url:
            continue
        links[absolute_url] = link["text"]
    return links


def discover_html(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = fetch_text(source.url, timeout_seconds)
    parser = LinkCollector()
    parser.feed(html)
    candidates: list[Candidate] = []
    seen_urls: set[str] = set()
    for link in parser.links:
        href = link["href"]
        text = link["text"]
        absolute_url = urljoin(source.url, href)
        if absolute_url in seen_urls:
            continue
        if urlparse(absolute_url).scheme not in {"http", "https"}:
            continue
        matched_terms = match_terms(f"{text} {absolute_url}", terms)
        if not matched_terms and not looks_like_job_link(text, absolute_url):
            continue
        if matched_terms and not should_keep_candidate(text or "unknown", matched_terms, f"{text} {absolute_url}"):
            continue
        seen_urls.add(absolute_url)
        candidates.append(
            Candidate(
                employer=source.source,
                title=text or "unknown",
                url=absolute_url,
                source_url=source.url,
                matched_terms=matched_terms,
                notes="Static HTML enumeration",
            )
        )
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
        matched_jobs=len(candidates),
        limitations=[],
        candidates=candidates,
    )


def discover_lever_json(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    path_bits = [bit for bit in urlparse(source.url).path.split("/") if bit]
    if not path_bits:
        raise ValueError(f"Could not derive Lever board token from {source.url}")
    token = path_bits[0]
    parsed = urlparse(source.url)
    if parsed.netloc == "jobs.lever.co":
        api_host = "api.lever.co"
    elif parsed.netloc.startswith("jobs.") and parsed.netloc.endswith(".lever.co"):
        api_host = "api." + parsed.netloc[len("jobs.") :]
    else:
        api_host = "api.lever.co"
    url = f"{parsed.scheme or 'https'}://{api_host}/v0/postings/{token}?mode=json"
    postings = fetch_json(url, timeout_seconds)
    candidates: list[Candidate] = []
    for posting in postings:
        title = posting.get("text", "unknown")
        location = posting.get("categories", {}).get("location") or "unknown"
        payload = " ".join(
            filter(
                None,
                [
                    title,
                    posting.get("descriptionPlain", ""),
                    posting.get("categories", {}).get("team", ""),
                    location,
                ],
            )
        )
        matched = match_terms(payload, terms)
        if not should_keep_candidate(title, matched, payload):
            continue
        candidates.append(
            Candidate(
                employer=source.source,
                title=title,
                url=posting.get("hostedUrl") or posting.get("applyUrl") or source.url,
                source_url=source.url,
                location=location,
                matched_terms=matched,
                notes="Enumerated through Lever JSON",
            )
        )
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
        enumerated_jobs=len(postings),
        matched_jobs=len(candidates),
        limitations=[],
        candidates=candidates,
    )


def discover_greenhouse_api(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    path_bits = [bit for bit in urlparse(source.url).path.split("/") if bit]
    if not path_bits:
        raise ValueError(f"Could not derive Greenhouse board token from {source.url}")
    token = path_bits[0]
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
    payload = fetch_json(api_url, timeout_seconds)
    jobs = payload.get("jobs", [])
    candidates: list[Candidate] = []
    for job in jobs:
        title = job.get("title", "unknown")
        location = job.get("location", {}).get("name") or "unknown"
        content = job.get("content", "")
        payload = f"{title} {location} {content}"
        matched = match_terms(payload, terms)
        if not should_keep_candidate(title, matched, payload):
            continue
        candidates.append(
            Candidate(
                employer=source.source,
                title=title,
                url=job.get("absolute_url") or source.url,
                source_url=source.url,
                location=location,
                matched_terms=matched,
                notes="Enumerated through Greenhouse board API",
            )
        )
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
        enumerated_jobs=len(jobs),
        matched_jobs=len(candidates),
        limitations=[],
        candidates=candidates,
    )


def build_ibm_search_payload(offset: int, size: int) -> dict[str, Any]:
    return {
        "appId": "careers",
        "scopes": ["careers2"],
        "query": {"bool": {"must": []}},
        "aggs": {
            "field_keyword_172": {
                "filter": {"match_all": {}},
                "aggs": {
                    "field_keyword_17": {"terms": {"field": "field_keyword_17", "size": 6}},
                    "field_keyword_17_count": {"cardinality": {"field": "field_keyword_17"}},
                },
            },
            "field_keyword_083": {
                "filter": {"match_all": {}},
                "aggs": {
                    "field_keyword_08": {"terms": {"field": "field_keyword_08", "size": 6}},
                    "field_keyword_08_count": {"cardinality": {"field": "field_keyword_08"}},
                },
            },
            "field_keyword_184": {
                "filter": {"match_all": {}},
                "aggs": {
                    "field_keyword_18": {"terms": {"field": "field_keyword_18", "size": 6}},
                    "field_keyword_18_count": {"cardinality": {"field": "field_keyword_18"}},
                },
            },
            "field_keyword_055": {
                "filter": {"match_all": {}},
                "aggs": {
                    "field_keyword_05": {"terms": {"field": "field_keyword_05", "size": 1000}},
                    "field_keyword_05_count": {"cardinality": {"field": "field_keyword_05"}},
                },
            },
        },
        "size": size,
        "from": offset,
        "sort": [{"_score": "desc"}, {"pageviews": "desc"}],
        "lang": "zz",
        "localeSelector": {},
        "sm": {"query": "", "lang": "zz"},
        "_source": [
            "_id",
            "title",
            "url",
            "description",
            "language",
            "entitled",
            "field_keyword_17",
            "field_keyword_08",
            "field_keyword_18",
            "field_keyword_19",
        ],
    }


def discover_ibm_api(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    candidates_by_url: dict[str, Candidate] = {}
    raw_seen_ids: set[str] = set()
    pages_scanned = 0
    total_hits = 0
    offset = 0

    while True:
        payload = build_ibm_search_payload(offset, IBM_RESULTS_PAGE_SIZE)
        response = post_json(
            IBM_SEARCH_API_URL,
            payload,
            timeout_seconds,
            headers={"Referer": "https://www.ibm.com/"},
        )
        hits = response.get("hits", {})
        total = hits.get("total", {})
        total_hits = int(total.get("value", total_hits or 0) or 0)
        page_hits = hits.get("hits", [])
        if not page_hits:
            break

        pages_scanned += 1
        for hit in page_hits:
            source_payload = hit.get("_source", {})
            job_id = hit.get("_id") or source_payload.get("url") or ""
            if job_id:
                raw_seen_ids.add(job_id)
            title = source_payload.get("title") or "unknown"
            url = source_payload.get("url") or source.url
            description = strip_html_fragment(source_payload.get("description", ""))
            location = source_payload.get("field_keyword_19") or "unknown"
            remote = source_payload.get("field_keyword_17") or "unknown"
            team = source_payload.get("field_keyword_08") or ""
            level = source_payload.get("field_keyword_18") or ""
            searchable_text = " ".join(part for part in [title, description, location, remote, team, level] if part)
            matched_terms = sorted(set(match_terms(searchable_text, terms)))
            if not should_keep_candidate(title, matched_terms, searchable_text):
                continue
            merge_candidate(
                candidates_by_url,
                Candidate(
                    employer=source.source,
                    title=title,
                    url=url,
                    source_url=source.url,
                    location=location,
                    remote=remote,
                    matched_terms=matched_terms,
                    notes="Enumerated through IBM careers search API with local term filtering",
                ),
            )

        offset += len(page_hits)
        if len(page_hits) < IBM_RESULTS_PAGE_SIZE:
            break
        if total_hits and offset >= total_hits:
            break

    limitations: list[str] = []
    status = "complete"
    unique_hits = len(raw_seen_ids)
    if total_hits and unique_hits < total_hits:
        status = "partial"
        limitations.append(
            f"IBM API reported {total_hits} hits but only {unique_hits} unique records were observed across paged results"
        )

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
        result_pages_scanned=f"full_index={pages_scanned}p/{unique_hits or total_hits}of{total_hits or unique_hits}",
        direct_job_pages_opened=0,
        enumerated_jobs=unique_hits or total_hits,
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_infineon_api(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    candidates_by_url: dict[str, Candidate] = {}
    raw_seen_ids: set[str] = set()
    limitations: list[str] = []
    term_summaries: list[str] = []
    errored_terms: list[str] = []
    total_pages_scanned = 0
    parsed_source = urlparse(source.url)
    base_url = f"{parsed_source.scheme}://{parsed_source.netloc}"

    for term in terms:
        term_pages_scanned = 0
        term_total = 0
        start = 0
        while True:
            query = urlencode(
                {
                    "domain": "infineon.com",
                    "query": term,
                    "location": "",
                    "start": start,
                    "sort_by": "timestamp",
                }
            )
            endpoint = f"{base_url}/api/pcsx/search?{query}&"
            try:
                payload = fetch_json(endpoint, timeout_seconds)
            except Exception:
                errored_terms.append(term)
                break

            data = payload.get("data", {})
            positions = data.get("positions", [])
            term_total = int(data.get("count", term_total or 0) or 0)
            if not positions:
                break

            term_pages_scanned += 1
            total_pages_scanned += 1
            for position in positions:
                job_id = str(position.get("id") or position.get("atsJobId") or "")
                if job_id:
                    raw_seen_ids.add(job_id)
                title = position.get("name") or "unknown"
                url = urljoin(source.url, position.get("positionUrl") or "")
                location = "; ".join(position.get("locations") or position.get("standardizedLocations") or []) or "unknown"
                workplace_values = position.get("efcustomTextWorkplaceType") or []
                remote = workplace_values[0] if workplace_values else (position.get("workLocationOption") or "unknown")
                department = position.get("department") or ""
                searchable_text = " ".join(
                    part
                    for part in [title, location, remote, department, position.get("displayJobId") or ""]
                    if part
                )
                matched_terms = sorted(set(match_terms(searchable_text, terms)))
                if not should_keep_candidate(title, matched_terms, searchable_text):
                    continue
                merge_candidate(
                    candidates_by_url,
                    Candidate(
                        employer=source.source,
                        title=title,
                        url=url or source.url,
                        source_url=source.url,
                        location=location,
                        remote=remote,
                        matched_terms=matched_terms,
                        notes=f"Enumerated through Infineon PCSx search for '{term}'",
                    ),
                )

            start += len(positions)
            if len(positions) < INFINEON_RESULTS_PAGE_SIZE:
                break
            if term_total and start >= term_total:
                break

        term_summaries.append(f"{term}={term_pages_scanned}p/{term_total}")

    if errored_terms:
        limitations.append("Errored terms: " + ", ".join(sorted(set(errored_terms))))

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="partial" if limitations else "complete",
        listing_pages_scanned=total_pages_scanned,
        search_terms_tried=terms,
        result_pages_scanned=", ".join(term_summaries) if term_summaries else "none",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_seen_ids),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_workday_api(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    parsed_source = urlparse(source.url)
    if "myworkdayjobs.com" not in parsed_source.netloc:
        raise ValueError(f"Workday discovery requires a Workday board URL, got {source.url}")
    path_bits = [bit for bit in parsed_source.path.split("/") if bit]
    if not path_bits:
        raise ValueError(f"Could not derive Workday site token from {source.url}")
    tenant = parsed_source.netloc.split(".")[0]
    site = path_bits[0]
    endpoint = f"{parsed_source.scheme}://{parsed_source.netloc}/wday/cxs/{tenant}/{site}/jobs"
    base_url = f"{parsed_source.scheme}://{parsed_source.netloc}"

    candidates_by_url: dict[str, Candidate] = {}
    raw_seen_ids: set[str] = set()
    limitations: list[str] = []
    term_summaries: list[str] = []
    errored_terms: list[str] = []
    total_pages_scanned = 0

    for term in terms:
        term_pages_scanned = 0
        term_total = 0
        offset = 0
        page_signatures: set[str] = set()
        while True:
            payload = {"limit": WORKDAY_RESULTS_PAGE_SIZE, "offset": offset, "searchText": term}
            try:
                response = post_json(endpoint, payload, timeout_seconds, headers={"Referer": source.url})
            except Exception:
                errored_terms.append(term)
                break

            postings = response.get("jobPostings", [])
            if term_total == 0:
                term_total = int(response.get("total", 0) or 0)
            if not postings:
                break

            page_signature = ",".join(str(posting.get("externalPath") or posting.get("title") or "") for posting in postings[:10])
            if not page_signature or page_signature in page_signatures:
                break
            page_signatures.add(page_signature)

            term_pages_scanned += 1
            total_pages_scanned += 1
            for posting in postings:
                external_path = posting.get("externalPath") or ""
                title = posting.get("title") or "unknown"
                absolute_url = urljoin(base_url, external_path) if external_path else source.url
                raw_id = external_path or title
                raw_seen_ids.add(raw_id)
                location = posting.get("locationsText") or "unknown"
                searchable_text = " ".join(
                    part
                    for part in [
                        title,
                        location,
                        posting.get("postedOn") or "",
                        join_text(posting.get("bulletFields")),
                    ]
                    if part
                )
                matched_terms = sorted(set(match_terms(searchable_text, terms)))
                if not should_keep_candidate(title, matched_terms, searchable_text):
                    continue
                merge_candidate(
                    candidates_by_url,
                    Candidate(
                        employer=source.source,
                        title=title,
                        url=absolute_url,
                        source_url=source.url,
                        location=location,
                        matched_terms=matched_terms,
                        notes=f"Enumerated through Workday jobs API for '{term}'",
                    ),
                )

            offset += len(postings)
            if len(postings) < WORKDAY_RESULTS_PAGE_SIZE:
                break
            if term_total and offset >= term_total:
                break

        term_summaries.append(f"{term}={term_pages_scanned}p/{term_total}")

    if errored_terms:
        limitations.append("Errored terms: " + ", ".join(sorted(set(errored_terms))))

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="partial" if limitations else "complete",
        listing_pages_scanned=total_pages_scanned,
        search_terms_tried=terms,
        result_pages_scanned=", ".join(term_summaries) if term_summaries else "none",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_seen_ids),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_ashby_api(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    path_bits = [bit for bit in urlparse(source.url).path.split("/") if bit]
    if not path_bits:
        raise ValueError(f"Could not derive Ashby board slug from {source.url}")
    board_slug = path_bits[0]
    endpoint = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams"
    payload = {
        "operationName": "ApiJobBoardWithTeams",
        "variables": {"organizationHostedJobsPageName": board_slug},
        "query": ASHBY_JOB_BOARD_QUERY,
    }
    response = post_json(endpoint, payload, timeout_seconds, headers={"Referer": source.url})
    job_board = response.get("data", {}).get("jobBoard", {})
    postings = job_board.get("jobPostings", [])
    teams = {
        team.get("id"): team.get("externalName") or team.get("name") or ""
        for team in job_board.get("teams", [])
        if team.get("id")
    }
    candidates: list[Candidate] = []
    for posting in postings:
        title = posting.get("title") or "unknown"
        primary_location = posting.get("locationName") or "unknown"
        secondary_locations = [item.get("locationName") or "" for item in posting.get("secondaryLocations") or []]
        location = "; ".join(part for part in [primary_location, *secondary_locations] if part) or "unknown"
        team_name = teams.get(posting.get("teamId"), "")
        searchable_text = " ".join(
            part
            for part in [
                title,
                team_name,
                location,
                posting.get("workplaceType") or "",
                posting.get("employmentType") or "",
                posting.get("compensationTierSummary") or "",
            ]
            if part
        )
        matched_terms = sorted(set(match_terms(searchable_text, terms)))
        if not should_keep_candidate(title, matched_terms, searchable_text):
            continue
        candidates.append(
            Candidate(
                employer=source.source,
                title=title,
                url=f"{source.url.rstrip('/')}/{posting.get('id')}",
                source_url=source.url,
                location=location,
                remote=posting.get("workplaceType") or "unknown",
                matched_terms=matched_terms,
                notes="Enumerated through Ashby non-user GraphQL API",
            )
        )
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
        enumerated_jobs=len(postings),
        matched_jobs=len(candidates),
        limitations=[],
        candidates=candidates,
    )


def discover_thales_html(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    candidates_by_url: dict[str, Candidate] = {}
    raw_seen_ids: set[str] = set()
    limitations: list[str] = []
    term_summaries: list[str] = []
    errored_terms: list[str] = []
    total_pages_scanned = 0

    for term in terms:
        term_pages_scanned = 0
        term_total = 0
        term_visible_total = 0
        offset = 0
        page_signatures: set[str] = set()
        while True:
            params = {"keywords": term}
            if offset:
                params["from"] = str(offset)
                params["s"] = "1"
            search_url = f"{source.url}?{urlencode(params)}"
            try:
                html = fetch_text(search_url, timeout_seconds)
            except Exception:
                errored_terms.append(term)
                break

            payload = extract_json_object_after_marker(html, '"eagerLoadRefineSearch":')
            if not payload:
                errored_terms.append(term)
                break

            jobs = payload.get("data", {}).get("jobs", [])
            hits = int(payload.get("hits", 0) or 0)
            if term_total == 0:
                term_total = int(payload.get("totalHits", 0) or 0)
            if not jobs:
                break

            page_signature = ",".join(str(job.get("jobSeqNo") or job.get("reqId") or "") for job in jobs[:10])
            if not page_signature or page_signature in page_signatures:
                break
            page_signatures.add(page_signature)

            term_pages_scanned += 1
            total_pages_scanned += 1
            term_visible_total += hits or len(jobs)
            link_map = collect_job_links(html, source.url, "/global/en/job/")
            for job in jobs:
                req_id = job.get("reqId") or job.get("jobId") or ""
                job_url = next((url for url in link_map if f"/job/{req_id}/" in url), None)
                if not job_url:
                    title_slug = re.sub(r"-{2,}", "-", re.sub(r"[^A-Za-z0-9]+", "-", job.get("title") or "")).strip("-")
                    job_url = f"{urlparse(source.url).scheme}://{urlparse(source.url).netloc}/global/en/job/{req_id}/{title_slug}" if req_id else source.url
                raw_id = job.get("jobSeqNo") or req_id or job_url
                raw_seen_ids.add(str(raw_id))
                title = job.get("title") or "unknown"
                location = job.get("cityStateCountry") or job.get("location") or job.get("workLocation") or "unknown"
                searchable_text = " ".join(
                    part
                    for part in [
                        title,
                        job.get("descriptionTeaser") or "",
                        join_text(job.get("ml_skills")),
                        job.get("category") or "",
                        location,
                        job.get("workLocation") or "",
                    ]
                    if part
                )
                matched_terms = sorted(set(match_terms(searchable_text, terms)))
                if not should_keep_candidate(title, matched_terms, searchable_text):
                    continue
                merge_candidate(
                    candidates_by_url,
                    Candidate(
                        employer=source.source,
                        title=title,
                        url=job_url,
                        source_url=source.url,
                        location=location,
                        matched_terms=matched_terms,
                        notes=f"Enumerated through Thales search-results HTML for '{term}'",
                    ),
                )

            offset += hits or len(jobs)
            if (hits or len(jobs)) < THALES_RESULTS_PAGE_SIZE:
                break
            if term_total and offset >= term_total:
                break

        term_summaries.append(f"{term}={term_pages_scanned}p/{term_visible_total}of{term_total}")

    if errored_terms:
        limitations.append("Errored terms: " + ", ".join(sorted(set(errored_terms))))

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="partial" if limitations else "complete",
        listing_pages_scanned=total_pages_scanned,
        search_terms_tried=terms,
        result_pages_scanned=", ".join(term_summaries) if term_summaries else "none",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_seen_ids),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_bosch_autocomplete(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    candidates_by_url: dict[str, Candidate] = {}
    raw_hit_urls: set[str] = set()
    truncated_terms: list[str] = []
    errored_terms: list[str] = []
    term_summaries: list[str] = []

    for term in terms:
        query = urlencode({"query": term, "locale": "de"})
        endpoint = f"{source.url.rstrip('/')}/api/filter/autocomplete?{query}"
        try:
            payload = fetch_json(endpoint, timeout_seconds)
        except Exception as exc:
            errored_terms.append(term)
            term_summaries.append(f"{term}=error")
            continue

        hits = payload.get("hits", [])
        found = int(payload.get("found", 0) or 0)
        term_summaries.append(f"{term}={len(hits)}/{found}")
        if found > len(hits):
            truncated_terms.append(term)

        for hit in hits:
            document = hit.get("document", {})
            data = document.get("data", {})
            content = document.get("content", {})

            title = data.get("title") or "unknown"
            application_url = data.get("applicationUrl") or data.get("jobBoard_link") or source.url
            raw_hit_urls.add(application_url)
            location = ", ".join(part for part in [data.get("city"), data.get("country")] if part) or "unknown"
            remote = data.get("remote") or "unknown"

            searchable_text = " ".join(
                part
                for part in [
                    title,
                    data.get("company"),
                    location,
                    join_text(data.get("jobField")),
                    join_text(data.get("entryLevel")),
                    join_text(data.get("employmentType")),
                    join_text(content.get("task")),
                    join_text(content.get("profile")),
                    join_text(content.get("offer")),
                    join_text(content.get("business")),
                ]
                if part
            )
            matched_terms = sorted(set(match_terms(searchable_text, terms)))
            if not should_keep_candidate(title, matched_terms, searchable_text):
                continue

            existing = candidates_by_url.get(application_url)
            notes = f"Bosch autocomplete hit for '{term}'"
            candidate = Candidate(
                employer=data.get("company") or source.source,
                title=title,
                url=application_url,
                source_url=source.url,
                location=location,
                remote=remote,
                matched_terms=matched_terms,
                notes=notes,
            )
            if not existing:
                candidates_by_url[application_url] = candidate
                continue
            merge_candidate(candidates_by_url, candidate)

    limitations: list[str] = []
    if truncated_terms:
        limitations.append(
            "Autocomplete is capped at 10 hits per term; truncated terms: " + ", ".join(truncated_terms)
        )
    if errored_terms:
        limitations.append("Errored terms: " + ", ".join(errored_terms))

    status = "complete"
    if errored_terms or truncated_terms:
        status = "partial"

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status=status,
        listing_pages_scanned=1,
        search_terms_tried=terms,
        result_pages_scanned=", ".join(term_summaries) if term_summaries else "none",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_hit_urls),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def google_search_url(source: SourceConfig, term: str, page_num: int) -> str:
    params = {"q": term}
    if page_num > 1:
        params["page"] = page_num
    return f"{source.url}?{urlencode(params)}"


def bosch_search_url(source: SourceConfig, term: str, page_num: int) -> str:
    del page_num
    return f"{source.url.rstrip('/')}/?{urlencode({'search': term})}"


def accept_bosch_cookies(page: Any) -> None:
    host = page.locator("dock-privacy-settings").first
    if not host.count():
        return
    host.evaluate(
        """
(el) => {
  const root = el.shadowRoot;
  const button = root && Array.from(root.querySelectorAll('button')).find(
    (candidate) => (candidate.innerText || '').includes('Alles akzeptieren')
  );
  if (button) button.click();
}
"""
    )
    page.wait_for_timeout(500)
    page.locator("dock-privacy-settings").evaluate_all(
        """
(elements) => {
  for (const element of elements) {
    element.remove();
  }
}
"""
    )
    page.wait_for_timeout(250)


def advance_bosch_results(page: Any, source: SourceConfig, term: str, page_num: int) -> bool:
    del source, term, page_num
    button = page.locator('button:has-text("Weitere Ergebnisse laden"), button:has-text("Load more results")').first
    if not button.count():
        return False
    before_count = page.locator('a[href*="/job/"][href*="searchTerm="]').count()
    button.scroll_into_view_if_needed(timeout=5000)
    button.evaluate("(element) => element.click()")
    for _ in range(12):
        page.wait_for_timeout(500)
        after_count = page.locator('a[href*="/job/"][href*="searchTerm="]').count()
        if after_count > before_count:
            return True
    return False


def accept_thales_cookies(page: Any) -> None:
    accept = page.get_by_role("button", name="Accept").first
    if accept.count():
        accept.click(timeout=5000)
        page.wait_for_timeout(500)
    page.locator('[ph-module="gdpr"]').evaluate_all(
        """
(elements) => {
  for (const element of elements) {
    element.remove();
  }
}
"""
    )
    page.wait_for_timeout(250)


def extract_google_jobs(page: Any, source: SourceConfig, term: str, terms: list[str], page_num: int) -> BrowserPageResult:
    scripts = page.locator("script").all_inner_texts()
    target = next((script for script in scripts if "key: 'ds:1'" in script and "data:" in script), None)
    if not target:
        return BrowserPageResult(
            candidates=[],
            raw_ids=[],
            visible_results=0,
            declared_total=None,
            page_signature=f"{term}:{page_num}:missing-ds1",
            limitations=["Google ds:1 payload not found in rendered page"],
        )
    match = re.search(r"data:(\[.*\]),\s*sideChannel:", target, re.DOTALL)
    if not match:
        return BrowserPageResult(
            candidates=[],
            raw_ids=[],
            visible_results=0,
            declared_total=None,
            page_signature=f"{term}:{page_num}:unparseable-ds1",
            limitations=["Google ds:1 payload could not be parsed"],
        )

    payload = json.loads(match.group(1))
    jobs = payload[0] if payload and isinstance(payload[0], list) else []
    candidates: list[Candidate] = []
    raw_ids: list[str] = []
    for job in jobs:
        if not isinstance(job, list) or len(job) < 10:
            continue
        job_id = join_text(job[0]) or join_text(job[2]) or "unknown"
        title = join_text(job[1]) or "unknown"
        url = join_text(job[2]) or source.url
        responsibilities = strip_html_fragment(
            join_text(job[3][1] if len(job) > 3 and isinstance(job[3], list) and len(job[3]) > 1 else "")
        )
        requirements = strip_html_fragment(
            join_text(job[4][1] if len(job) > 4 and isinstance(job[4], list) and len(job[4]) > 1 else "")
        )
        employer = join_text(job[7] if len(job) > 7 else "") or source.source
        location_entries = job[9] if len(job) > 9 and isinstance(job[9], list) else []
        location = "; ".join(
            join_text(entry[0]) for entry in location_entries if isinstance(entry, list) and entry and join_text(entry[0])
        ) or "unknown"
        summary = strip_html_fragment(
            join_text(job[10][1] if len(job) > 10 and isinstance(job[10], list) and len(job[10]) > 1 else "")
        )
        working_location = strip_html_fragment(
            join_text(job[18][1] if len(job) > 18 and isinstance(job[18], list) and len(job[18]) > 1 else "")
        )
        searchable_text = " ".join(
            part for part in [title, employer, location, summary, responsibilities, requirements, working_location] if part
        )
        matched_terms = sorted(set(match_terms(searchable_text, terms)))
        raw_ids.append(job_id)
        if not should_keep_candidate(title, matched_terms, searchable_text):
            continue
        candidates.append(
            Candidate(
                employer=employer,
                title=title,
                url=url,
                source_url=source.url,
                location=location,
                matched_terms=matched_terms,
                notes=f"Google browser search q='{term}' page={page_num}",
            )
        )
    page_signature = ",".join(raw_ids[:10]) if raw_ids else f"{term}:{page_num}:empty"
    return BrowserPageResult(
        candidates=candidates,
        raw_ids=raw_ids,
        visible_results=len(raw_ids),
        declared_total=None,
        page_signature=page_signature,
    )


def extract_bosch_jobs(page: Any, source: SourceConfig, term: str, terms: list[str], page_num: int) -> BrowserPageResult:
    del page_num
    body_text = page.locator("body").inner_text()
    count_match = re.search(r"(\d+)\s+passende Jobs gefunden", body_text)
    declared_total = int(count_match.group(1)) if count_match else None
    links = page.locator('a[href*="/job/"][href*="searchTerm="]')
    visible_count = links.count()
    raw_ids: list[str] = []
    candidates: list[Candidate] = []
    seen_urls: set[str] = set()

    for index in range(visible_count):
        element = links.nth(index)
        href = element.get_attribute("href") or ""
        absolute_url = urljoin(source.url, href)
        if absolute_url in seen_urls:
            continue
        seen_urls.add(absolute_url)
        raw_ids.append(absolute_url)
        text = element.inner_text().strip()
        title = re.split(r"\s+(?:Standort|Location):", text, maxsplit=1)[0].strip() or "unknown"
        location_match = re.search(r"(?:Standort|Location):\s*(.*?)(?:\s+Arbeitsbereich:|\s+Job veröffentlicht|\s+Job posted|$)", text)
        location = location_match.group(1).strip() if location_match else "unknown"
        matched_terms = sorted(set(match_terms(text, terms)))
        if not should_keep_candidate(title, matched_terms, text):
            continue
        candidates.append(
            Candidate(
                employer=source.source,
                title=title,
                url=absolute_url,
                source_url=source.url,
                location=location,
                matched_terms=matched_terms,
                notes=f"Bosch browser search q='{term}'",
            )
        )

    page_signature = f"{len(raw_ids)}:{','.join(raw_ids[-10:])}" if raw_ids else f"{term}:empty"
    return BrowserPageResult(
        candidates=candidates,
        raw_ids=raw_ids,
        visible_results=len(raw_ids),
        declared_total=declared_total,
        page_signature=page_signature,
    )


def discover_thales_browser(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
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
            limitations=["Playwright is not installed; Thales browser discovery is unavailable"],
            candidates=[],
        )

    candidates_by_url: dict[str, Candidate] = {}
    raw_seen_ids: set[str] = set()
    limitations: list[str] = []
    term_summaries: list[str] = []
    total_pages_scanned = 0

    def extract_page(page: Any, term: str) -> BrowserPageResult:
        body_text = page.locator("body").inner_text()
        count_match = re.search(r"Showing\s+\d+\s*-\s*\d+\s+of\s+(\d+)\s+results?", body_text)
        declared_total = int(count_match.group(1)) if count_match else None
        links = page.locator('a[href*="/global/en/job/"]')
        visible_count = links.count()
        raw_ids: list[str] = []
        candidates: list[Candidate] = []
        seen_urls: set[str] = set()

        for index in range(visible_count):
            element = links.nth(index)
            href = element.get_attribute("href") or ""
            absolute_url = urljoin(source.url, href)
            if absolute_url in seen_urls:
                continue
            seen_urls.add(absolute_url)
            raw_ids.append(absolute_url)
            title = element.inner_text().strip() or "unknown"
            card_text = element.evaluate(
                """
(el) => {
  let node = el;
  while (node && node.parentElement && (!node.innerText || node.innerText.length < 220)) {
    node = node.parentElement;
  }
  return (node && node.innerText) ? node.innerText : (el.innerText || '');
}
"""
            )
            matched_terms = sorted(set(match_terms(card_text, terms)))
            if not should_keep_candidate(title, matched_terms, card_text):
                continue
            location_match = re.search(r"Work Location\\s+(.+?)(?:\\s+Join our team|\\s+Save|$)", card_text, flags=re.DOTALL)
            location = re.sub(r"\\s+", " ", location_match.group(1)).strip() if location_match else "unknown"
            candidates.append(
                Candidate(
                    employer=source.source,
                    title=title,
                    url=absolute_url,
                    source_url=source.url,
                    location=location,
                    matched_terms=matched_terms,
                    notes=f"Enumerated through Thales browser pagination for '{term}'",
                )
            )

        page_signature = ",".join(raw_ids[:10]) if raw_ids else f"{term}:empty"
        return BrowserPageResult(
            candidates=candidates,
            raw_ids=raw_ids,
            visible_results=len(raw_ids),
            declared_total=declared_total,
            page_signature=page_signature,
        )

    timeout_ms = max(timeout_seconds * 1000, DEFAULT_BROWSER_TIMEOUT_MS)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 2200})
        for term in terms:
            search_url = f"{source.url}?{urlencode({'keywords': term})}"
            page.goto(search_url, wait_until="domcontentloaded", timeout=timeout_ms)
            accept_thales_cookies(page)
            page.wait_for_timeout(1000)

            term_pages_scanned = 0
            term_visible_total = 0
            term_declared_total: int | None = None
            term_page_signatures: set[str] = set()

            while True:
                result = extract_page(page, term)
                if not result.page_signature or result.page_signature in term_page_signatures:
                    break
                term_page_signatures.add(result.page_signature)
                total_pages_scanned += 1
                term_pages_scanned += 1
                term_visible_total += result.visible_results
                if term_declared_total is None and result.declared_total is not None:
                    term_declared_total = result.declared_total
                for raw_id in result.raw_ids:
                    raw_seen_ids.add(raw_id)
                for candidate in result.candidates:
                    merge_candidate(candidates_by_url, candidate)
                if result.visible_results == 0:
                    break
                if term_declared_total is not None and term_visible_total >= term_declared_total:
                    break
                next_link = page.locator('a[data-ph-at-id="pagination-next-link"]').first
                if not next_link.count():
                    break
                next_href = next_link.get_attribute("href")
                if not next_href:
                    break
                page.goto(next_href, wait_until="domcontentloaded", timeout=timeout_ms)
                accept_thales_cookies(page)
                page.wait_for_timeout(1000)

            term_summaries.append(f"{term}={term_pages_scanned}p/{term_visible_total}of{term_declared_total or 0}")
            if term_declared_total is not None and term_visible_total < term_declared_total:
                limitations.append(
                    f"Thales browser search for '{term}' surfaced {term_visible_total} of {term_declared_total} results"
                )

        browser.close()

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="partial" if limitations else "complete",
        listing_pages_scanned=total_pages_scanned,
        search_terms_tried=terms,
        result_pages_scanned=", ".join(term_summaries) if term_summaries else "none",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_seen_ids),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


BROWSER_STRATEGIES = {
    "Bosch": BrowserStrategy(
        search_url_builder=bosch_search_url,
        extract_page=extract_bosch_jobs,
        prepare_page=accept_bosch_cookies,
        advance_page=advance_bosch_results,
        supports_pagination=True,
        cumulative_results=True,
        max_pages=30,
    ),
    "Google": BrowserStrategy(
        search_url_builder=google_search_url,
        extract_page=extract_google_jobs,
        supports_pagination=True,
        page_size=GOOGLE_RESULTS_PAGE_SIZE,
        max_pages=MAX_BROWSER_PAGES,
    ),
}


def discover_browser(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
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
            limitations=["Playwright is not installed; browser-mode discovery is scaffolded but inactive"],
            candidates=[],
        )
    strategy = BROWSER_STRATEGIES.get(source.source)
    if not strategy:
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
            limitations=[f"No browser strategy is implemented yet for {source.source}"],
            candidates=[],
        )

    candidates_by_url: dict[str, Candidate] = {}
    raw_seen_ids: set[str] = set()
    limitations: list[str] = []
    result_summaries: list[str] = []
    pages_scanned = 0
    status = "complete"

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 2200})
            timeout_ms = max(timeout_seconds * 1000, DEFAULT_BROWSER_TIMEOUT_MS)
            for term in terms:
                search_url = strategy.search_url_builder(source, term, 1)
                page.goto(search_url, wait_until="domcontentloaded", timeout=timeout_ms)
                if strategy.prepare_page:
                    strategy.prepare_page(page)
                page.wait_for_timeout(1000)
                term_page_signatures: set[str] = set()
                term_pages_scanned = 0
                term_visible_total = 0
                term_declared_total: int | None = None
                term_hit_page_cap = False
                page_num = 1
                while page_num <= strategy.max_pages:
                    result = strategy.extract_page(page, source, term, terms, page_num)
                    if not result.page_signature or result.page_signature in term_page_signatures:
                        break
                    term_pages_scanned += 1
                    pages_scanned += 1
                    if strategy.cumulative_results:
                        term_visible_total = max(term_visible_total, result.visible_results)
                    else:
                        term_visible_total += result.visible_results
                    if term_declared_total is None and result.declared_total is not None:
                        term_declared_total = result.declared_total
                    limitations.extend(result.limitations)
                    for raw_id in result.raw_ids:
                        raw_seen_ids.add(raw_id)
                    for candidate in result.candidates:
                        merge_candidate(candidates_by_url, candidate)
                    term_page_signatures.add(result.page_signature)
                    if result.visible_results == 0:
                        break
                    if term_declared_total is not None and term_visible_total >= term_declared_total:
                        break
                    if not strategy.supports_pagination:
                        break
                    if strategy.page_size is not None and not strategy.cumulative_results and result.visible_results < strategy.page_size:
                        break
                    next_page_num = page_num + 1
                    if next_page_num > strategy.max_pages:
                        term_hit_page_cap = True
                        break
                    if strategy.advance_page:
                        if not strategy.advance_page(page, source, term, next_page_num):
                            break
                    else:
                        next_url = strategy.search_url_builder(source, term, next_page_num)
                        page.goto(next_url, wait_until="domcontentloaded", timeout=timeout_ms)
                        if strategy.prepare_page:
                            strategy.prepare_page(page)
                        page.wait_for_timeout(1000)
                    page_num = next_page_num
                if term_declared_total is not None:
                    result_summaries.append(f"{term}={term_pages_scanned}p/{term_visible_total}of{term_declared_total}")
                    if term_visible_total < term_declared_total:
                        status = "partial"
                        limitations.append(
                            f"{source.source} browser search for '{term}' surfaced {term_visible_total} of {term_declared_total} results"
                        )
                else:
                    result_summaries.append(f"{term}={term_pages_scanned}p/{term_visible_total}")
                if term_hit_page_cap and (term_declared_total is None or term_visible_total < term_declared_total):
                    status = "partial"
                    limitations.append(
                        f"{source.source} browser search for '{term}' hit the page cap ({strategy.max_pages})"
                    )
            browser.close()
    except Exception as exc:  # pragma: no cover - defensive output for live runs
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
            limitations=[f"Browser discovery failed: {type(exc).__name__}: {exc}"],
            candidates=[],
        )

    deduped_limitations = list(dict.fromkeys(limitations))
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
        result_pages_scanned=", ".join(result_summaries) if result_summaries else "none",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_seen_ids),
        matched_jobs=len(candidates_by_url),
        limitations=deduped_limitations,
        candidates=list(candidates_by_url.values()),
    )


DISCOVERY_HANDLERS = {
    "ashby_api": discover_ashby_api,
    "bosch_autocomplete": discover_bosch_autocomplete,
    "html": discover_html,
    "ibm_api": discover_ibm_api,
    "infineon_api": discover_infineon_api,
    "icims_html": discover_html,
    "lever_json": discover_lever_json,
    "greenhouse_api": discover_greenhouse_api,
    "ashby_html": discover_ashby_api,
    "thales_browser": discover_thales_browser,
    "workday_api": discover_workday_api,
    "browser": discover_browser,
}


def discover_source(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    handler = DISCOVERY_HANDLERS.get(source.discovery_mode)
    if not handler:
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
            limitations=[f"Unsupported discovery_mode: {source.discovery_mode}"],
            candidates=[],
        )
    try:
        return handler(source, terms, timeout_seconds)
    except Exception as exc:  # pragma: no cover - defensive output for live runs
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
            limitations=[f"{type(exc).__name__}: {exc}"],
            candidates=[],
        )


def source_to_dict(source: SourceConfig, today: date, track_terms: list[str], source_term_map: dict[str, list[str]]) -> dict[str, Any]:
    terms = normalize_terms(track_terms, source_term_map.get(source.source, []))
    return {
        "source": source.source,
        "url": source.url,
        "discovery_mode": source.discovery_mode,
        "last_checked": source.last_checked,
        "cadence_group": source.cadence_group,
        "due_today": source_due_today(source, today),
        "search_terms": terms,
    }


def coverage_to_dict(coverage: Coverage) -> dict[str, Any]:
    payload = asdict(coverage)
    payload["candidates"] = [asdict(candidate) for candidate in coverage.candidates]
    return payload


def write_output_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(text)
    temp_path.replace(path)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    today = date.fromisoformat(args.today)
    sources, track_terms, source_term_map = load_track_config(args.track)

    if args.source:
        wanted = {name.lower() for name in args.source}
        sources = [source for source in sources if source.source.lower() in wanted]

    if args.cadence_group:
        wanted_groups = set(args.cadence_group)
        sources = [source for source in sources if source.cadence_group in wanted_groups]

    if args.due_only:
        sources = [source for source in sources if source_due_today(source, today)]

    if args.list_sources:
        payload = {
            "schema_version": 1,
            "track": args.track,
            "today": args.today,
            "generated_at": generated_at(),
            "mode": "list_sources",
            "sources": [source_to_dict(source, today, track_terms, source_term_map) for source in sources],
        }
    elif args.plan_only:
        payload = {
            "schema_version": 1,
            "track": args.track,
            "today": args.today,
            "generated_at": generated_at(),
            "mode": "plan_only",
            "sources": [source_to_dict(source, today, track_terms, source_term_map) for source in sources],
        }
    else:
        coverages: list[Coverage] = []
        for source in sources:
            terms = normalize_terms(track_terms, source_term_map.get(source.source, []))
            coverage = discover_source(source, terms, args.timeout_seconds)
            coverage.due_today = source_due_today(source, today)
            coverages.append(coverage)
        payload = {
            "schema_version": 1,
            "track": args.track,
            "today": args.today,
            "generated_at": generated_at(),
            "mode": "discover",
            "sources": [coverage_to_dict(coverage) for coverage in coverages],
        }

    json_text = json.dumps(payload, indent=2 if args.pretty else None, ensure_ascii=True)
    if args.output:
        serialized = json_text + ("\n" if args.pretty else "")
        write_output_text(Path(args.output), serialized)
        if args.latest_output:
            write_output_text(Path(args.latest_output), serialized)
    else:
        sys.stdout.write(json_text)
        if args.pretty:
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
