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
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
# Some public career pages reject obviously scripted user agents with a 403.
# Use a stable browser-like agent so deterministic HTML discovery still works.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_BROWSER_TIMEOUT_MS = 60_000
MAX_BROWSER_PAGES = 10
GOOGLE_RESULTS_PAGE_SIZE = 20
GOOGLE_LOCATION_FILTERS = (
    "Munich, Germany",
    "Zurich, Switzerland",
    "London, UK",
    "New York, NY, USA",
)
IBM_RESULTS_PAGE_SIZE = 100
INFINEON_RESULTS_PAGE_SIZE = 10
WORKDAY_RESULTS_PAGE_SIZE = 20
THALES_RESULTS_PAGE_SIZE = 10
ENBW_RESULTS_PAGE_SIZE = 10
GETRO_RESULTS_PAGE_SIZE = 100
MAX_GETRO_PAGES = 50
MAX_RHEINMETALL_PAGES = 20
HTML_TAG_RE = re.compile(r"<[^>]+>")
IACR_POSTING_BLOCK_RE = re.compile(
    r'<h5>\s*<a href="(?P<href>[^"]+)" id="url-(?P<id>\d+)">\s*'
    r'<span id="position-(?P=id)">(?P<title>.*?)</span>\s*</a>\s*</h5>'
    r'(?P<body>.*?)(?=<hr\s*/?>|\Z)',
    flags=re.DOTALL,
)
IACR_PLACE_RE = re.compile(r'<h6 id="place-\d+"[^>]*>(?P<place>.*?)</h6>', flags=re.DOTALL)
IACR_DESCRIPTION_RE = re.compile(r'<div id="description-\d+">(?P<description>.*?)</div>', flags=re.DOTALL)
IACR_CONTACT_RE = re.compile(r'<span id="contact-\d+">(?P<contact>.*?)</span>', flags=re.DOTALL)
IACR_UPDATED_RE = re.compile(r"<strong>\s*Last updated:\s*</strong>\s*(?P<updated>[^<]+)", flags=re.DOTALL)
IACR_POSTED_RE = re.compile(r"<small[^>]*>posted on (?P<posted>[^<]+)</small>", flags=re.DOTALL)
HN_JOB_ROW_RE = re.compile(
    r'<tr class="athing submission" id="(?P<id>\d+)">.*?'
    r'<span class="titleline"><a href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?</tr>\s*'
    r"<tr><td colspan=\"2\"></td><td class=\"subtext\">.*?"
    r'<span class="age" title="[^"]+"><a href="item\?id=\d+">(?P<age>[^<]+)</a></span>',
    flags=re.DOTALL,
)
HN_MORE_LINK_RE = re.compile(
    r"""<a href=(?P<quote>['"])(?P<href>jobs\?next=[^'"]+)(?P=quote)\s+class=(?P<quote2>['"])morelink(?P=quote2)\s+rel=(?P<quote3>['"])next(?P=quote3)>More</a>"""
)
HN_WHOISHIRING_TITLE_RE = re.compile(r"^Ask HN:\s+Who is hiring\?", flags=re.IGNORECASE)
SERVICE_BUND_RESULT_RE = re.compile(
    r'<a[^>]+href="(?P<href>[^"]*IMPORTE/Stellenangebote[^"]*)"[^>]*>'
    r'.*?<h3>(?P<title>.*?)</h3>'
    r'.*?<p><em>Arbeitgeber</em>\s*(?P<employer>.*?)</p>'
    r'.*?<p><em>Veröffentlicht</em>\s*(?P<posted>[^<]+)</p>'
    r'.*?<p><em>Bewerbungsfrist</em>\s*(?P<deadline>[^<]+)</p>',
    flags=re.DOTALL | re.IGNORECASE,
)
SERVICE_BUND_NEXT_RE = re.compile(
    r'<li class="next"[^>]*>.*?<button[^>]+name="gtp"[^>]+value="(?P<gtp>[^"]+)"',
    flags=re.DOTALL | re.IGNORECASE,
)
SERVICE_BUND_DIRECT_LINK_RE = re.compile(
    r'<a[^>]+href="(?P<href>[^"]*service\.bund\.de/[^"]*IMPORTE/Stellenangebote[^"]*)"[^>]*>(?P<text>.*?)</a>',
    flags=re.DOTALL | re.IGNORECASE,
)
RECRUITEE_DATA_PROPS_RE = re.compile(r'data-props="(?P<props>[^"]+)"')
NEXT_DATA_SCRIPT_RE = re.compile(
    r'<script[^>]+id="__NEXT_DATA__"[^>]*>(?P<payload>.*?)</script>',
    flags=re.DOTALL | re.IGNORECASE,
)
PERSONIO_NEXT_F_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,"(?P<chunk>.*?)"\]\)', flags=re.DOTALL)
AUSWAERTIGES_AMT_ACTION_RE = re.compile(
    r'(?:action|dataUrl)="(?P<endpoint>/ajax/json-filterlist/[^"]+)"',
    flags=re.IGNORECASE,
)
BUNDESWEHR_JOB_TITLE_RE = re.compile(
    r'<a class="jobtitle" href="(?P<href>[^"]+)">(?P<title>.*?)</a>',
    flags=re.DOTALL | re.IGNORECASE,
)
BND_RESULT_RE = re.compile(
    r'<a[^>]+href="(?P<href>[^"]*SharedDocs/Stellenangebote/DE/Stellenangebote/[^"]*)"[^>]*class="c-career-item__link"[^>]*>'
    r'\s*<strong[^>]*class="c-career-item__title"[^>]*>(?P<title>.*?)</strong>'
    r'(?P<bubbles>.*?)</a>',
    flags=re.DOTALL | re.IGNORECASE,
)
BND_BUBBLE_RE = re.compile(r'<span[^>]*class="c-bubble"[^>]*>(?P<text>.*?)</span>', flags=re.DOTALL | re.IGNORECASE)
RHEINMETALL_CARD_START_RE = re.compile(r'<div class="flex gap-0\.5 group">', flags=re.IGNORECASE)
RHEINMETALL_CARD_URL_RE = re.compile(
    r'<a href="(?P<href>/de/job/[^"]+)"[^>]*class="print-avoid-page-break flex-grow pr-8"',
    flags=re.IGNORECASE,
)
RHEINMETALL_CARD_TITLE_RE = re.compile(
    r'<div class="text-sm font-bold md:text-xl mb-2">(?P<title>.*?)</div>',
    flags=re.DOTALL | re.IGNORECASE,
)
RHEINMETALL_CARD_META_RE = re.compile(
    r'<div class="flex flex-wrap mr-6">\s*(?P<meta>.*?)\s*</div>',
    flags=re.DOTALL | re.IGNORECASE,
)
RHEINMETALL_PAGE_NUMBER_RE = re.compile(
    r'<a class="[^"]*cursor-pointer[^"]*inline-flex[^"]*"[^>]*>\s*(?P<page>\d+)\s*</a>',
    flags=re.DOTALL | re.IGNORECASE,
)
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
ALIGNMENT_TECH_SECTOR_FILTER_SOURCES = {
    "YC Startups",
    "Spirit Tech Collective Jobs",
    "Hacker News Who Is Hiring",
}
ALIGNMENT_TECH_SECTOR_HINTS = (
    "ag tech",
    "agtech",
    "ag-tech",
    "agriculture",
    "agricultural",
    "farm",
    "farmer",
    "farmers",
    "dairy",
    "livestock",
    "coffee",
    "smallholder",
    "animal welfare",
    "animal health",
    "animal-health",
    "biodiversity",
    "wildlife",
    "wildtier",
    "conservation",
    "forest",
    "reforestation",
    "ecology",
    "sustainability",
    "sustainable",
    "deforestation",
    "meditation",
    "mindfulness",
    "wellness",
    "mental health",
    "mental-health",
    "spiritual",
    "conscious",
    "consciousness",
    "yoga",
)
ALIGNMENT_TECH_PRIORITY_EMPLOYERS = (
    "albert schweitzer stiftung",
    "bergwaldprojekt",
    "coefficient giving",
    "deutsche wildtier stiftung",
    "enveritas",
    "gaia",
    "half earth project",
    "headspace",
    "innovate animal ag",
    "jhourney",
    "mindvalley",
    "one acre fund",
    "spade agriculture",
    "waking up",
    "yoga international",
)
SERVICE_BUND_PUBLIC_INTEREST_HINTS = (
    "krypt",
    "it-sicherheit",
    "cyber",
    "cyber/it",
    "security",
    "attack surface",
    "biometr",
    "kritis",
    "digital",
    "informatik",
    "informationstechnik",
    "telekommunikation",
    "netz",
)
THALES_PAYLOAD_TERM_ALIASES = {
    "cryptography": (
        "kryptographie",
        "kryptografie",
    ),
    "multi-party computation": (
        "mehrparteienberechnung",
        "mehrparteien-berechnung",
        "sichere mehrparteienberechnung",
    ),
    "homomorphic encryption": (
        "homomorphe verschlüsselung",
        "homomorphe verschluesselung",
        "homomorpher verschlüsselung",
        "homomorpher verschluesselung",
    ),
}
VERFASSUNGSSCHUTZ_RSS_URL = "https://www.verfassungsschutz.de/SiteGlobals/Functions/RSSNewsFeed/Stellenangebote.xml"
BUNDESWEHR_JOBSUCHE_URL = "https://www.bundeswehrkarriere.de/entdecker/jobs/jobsuche"
BUNDESWEHR_TASK_HEADINGS = (
    "Ihre Aufgaben",
    "Aufgaben",
    "Was Sie bei uns bewegt",
    "Was du bei uns bewegst",
)
BUNDESWEHR_QUALIFICATION_HEADINGS = (
    "Was fuer uns zaehlt",
    "Ihr Profil",
    "Voraussetzungen",
    "Das bringen Sie mit",
    "Das bringst du mit",
    "Qualifikationen",
)
BUNDESWEHR_COMPENSATION_HEADINGS = (
    "Was fuer Sie zaehlt",
    "Verguetung",
    "Besoldung",
    "Gehalt",
)
BUNDESWEHR_DETAIL_STOP_HEADINGS = (
    *BUNDESWEHR_TASK_HEADINGS,
    *BUNDESWEHR_QUALIFICATION_HEADINGS,
    *BUNDESWEHR_COMPENSATION_HEADINGS,
    "Bewerbung & Kontakt",
    "Bewerbung",
    "Kontakt",
    "Karriereperspektiven",
    "Weitere Informationen",
)
BUNDESWEHR_COMPENSATION_MARKERS = (
    "besoldung",
    "verguetung",
    "gehalt",
    "entgelt",
    "sold",
)
PCD_TEAM_TASK_HEADINGS = (
    "The perks of this job are that the candidate would",
    "What you'll do",
    "What you will do",
    "What youll do",
    "Responsibilities",
)
PCD_TEAM_QUALIFICATION_HEADINGS = (
    "The platonic ideal candidate",
    "Qualifications",
    "Requirements",
    "Who you are",
    "What you'll need",
    "What you will need",
    "What you need",
    "What youll need",
)
PCD_TEAM_DETAIL_STOP_HEADINGS = (
    *PCD_TEAM_TASK_HEADINGS,
    *PCD_TEAM_QUALIFICATION_HEADINGS,
    "Compensation",
    "Benefits",
    "Apply",
    "Apply Here",
    "About PCD",
)


@dataclass
class SourceConfig:
    source: str
    url: str
    discovery_mode: str
    last_checked: str | None
    cadence_group: str


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
    )


def playwright_import_missing_coverage(source: SourceConfig, terms: list[str], detail: str) -> Coverage:
    return partial_browser_unavailable_coverage(source, terms, f"Playwright is not installed; {detail}")


def playwright_browsers_missing_coverage(source: SourceConfig, terms: list[str], exc: BaseException) -> Coverage | None:
    message = normalize_whitespace(str(exc))
    lowered = message.lower()
    if "executable doesn't exist" not in lowered:
        return None
    if "playwright install" not in lowered and "chromium" not in lowered and "chrome-headless-shell" not in lowered:
        return None
    return partial_browser_unavailable_coverage(
        source,
        terms,
        "Playwright browser binaries are not installed; run ./.venv/bin/python -m playwright install chromium",
    )


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


class DataPageCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.payloads: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "div":
            return
        attr_map = dict(attrs)
        payload = attr_map.get("data-page")
        if payload:
            self.payloads.append(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", default="core_crypto", help="Track directory name under tracks/")
    parser.add_argument("--today", default=date.today().isoformat(), help="Date used for cadence decisions")
    parser.add_argument("--source", action="append", default=[], help="Limit to one or more source names")
    parser.add_argument(
        "--cadence-group",
        choices=["every_run", "every_3_runs", "every_month"],
        action="append",
        default=[],
        help="Limit to one or more cadence groups",
    )
    parser.add_argument("--due-only", action="store_true", help="Only include sources due today")
    parser.add_argument("--list-sources", action="store_true", help="List parsed sources and exit")
    parser.add_argument("--output", help="Write JSON output to this path instead of stdout")
    parser.add_argument("--latest-output", help="Also write the same JSON to a stable latest-artifact path")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    parser.add_argument("--progress", action="store_true", help="Emit per-source progress lines to stderr")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="Network timeout")
    parser.add_argument("--plan-only", action="store_true", help="Parse config and compute due sources without fetching")
    return parser


def extract_section(text: str, heading: str) -> str:
    pattern = rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, text, flags=re.MULTILINE | re.DOTALL)
    if not match:
        raise ValueError(f"Missing section: {heading}")
    return match.group(1).strip()


def extract_section_optional(text: str, heading: str) -> str:
    pattern = rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, text, flags=re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


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
                discovery_mode=row.get("discovery_mode") or "html",
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


def parse_source_specific_terms(text: str) -> dict[str, SourceTermRule]:
    search_terms_section = extract_section(text, "Search terms")
    match = re.search(
        r"^### Source-specific search terms\n(.*?)(?=^### |\Z)",
        search_terms_section,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        return {}
    section = match.group(1).strip()
    mapping: dict[str, SourceTermRule] = {}
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
        source_name = source.strip()
        mode = "append"
        if source_name.endswith("[override]"):
            source_name = source_name[: -len("[override]")].strip()
            mode = "override"
        mapping[source_name] = SourceTermRule(
            terms=[term.strip() for term in terms.split(",") if term.strip()],
            mode=mode,
        )
    return mapping


def load_track_config(track: str) -> tuple[list[SourceConfig], list[str], dict[str, SourceTermRule]]:
    path = ROOT / "tracks" / track / "sources.md"
    text = path.read_text()
    every_run = parse_markdown_table(extract_section(text, "Check every run"), "every_run")
    every_3_runs = parse_markdown_table(extract_section(text, "Check every 3 runs"), "every_3_runs")
    every_month = parse_markdown_table(extract_section_optional(text, "Check every month"), "every_month")
    track_terms = parse_track_terms(text)
    source_terms = parse_source_specific_terms(text)
    return every_run + every_3_runs + every_month, track_terms, source_terms


def source_due_today(source: SourceConfig, today: date) -> bool:
    if source.cadence_group == "every_run":
        return True
    if not source.last_checked:
        return True
    try:
        last_checked = date.fromisoformat(source.last_checked)
    except ValueError:
        return True
    if source.cadence_group == "every_month":
        return (today.year, today.month) != (last_checked.year, last_checked.month)
    return (today - last_checked).days >= 3


def normalize_terms(track_terms: list[str], source_rule: SourceTermRule | None) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    if source_rule and source_rule.mode == "override":
        combined_terms = list(source_rule.terms)
    else:
        combined_terms = list(track_terms)
        if source_rule:
            combined_terms.extend(source_rule.terms)
    for term in combined_terms:
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
    haystack = normalize_for_matching(text)
    return [term for term in terms if normalize_for_matching(term) in haystack]


def normalize_for_matching(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text.lower()


def match_terms_with_aliases(
    text: str,
    terms: list[str],
    aliases: dict[str, tuple[str, ...]],
) -> list[str]:
    haystack = normalize_for_matching(text)
    matched: list[str] = []
    for term in terms:
        candidates = (term, *aliases.get(term.lower(), ()))
        if any(normalize_for_matching(candidate) in haystack for candidate in candidates):
            matched.append(term)
    return matched


def generated_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def emit_progress(enabled: bool, message: str) -> None:
    if not enabled:
        return
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", file=sys.stderr, flush=True)


def strip_html_fragment(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(HTML_TAG_RE.sub(" ", value or ""))).strip()


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def truncate_text(value: str, limit: int = 240) -> str:
    text = normalize_whitespace(value)
    if len(text) <= limit:
        return text
    boundary = text.rfind(" ", 0, limit - 3)
    if boundary == -1 or boundary < limit // 2:
        boundary = limit - 3
    return text[:boundary].rstrip() + "..."


def slugify_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"-{2,}", "-", re.sub(r"[^A-Za-z0-9]+", "-", ascii_text)).strip("-").lower()


def normalize_url_without_fragment(value: str) -> str:
    parsed = urlparse(value)
    path = parsed.path.rstrip("/") or "/"
    return parsed._replace(path=path, fragment="").geturl()


def build_bundeswehr_portal_candidate_url(source_url: str, detail_url: str) -> str:
    parsed_source = urlparse(source_url)
    detail_slug = Path(urlparse(detail_url).path).name
    query_pairs = [(key, value) for key, value in parse_qsl(parsed_source.query, keep_blank_values=True) if key != "job"]
    if detail_slug:
        query_pairs.append(("job", detail_slug))
    return normalize_url_without_fragment(parsed_source._replace(query=urlencode(query_pairs), fragment="").geturl())


def extract_visible_text_lines_from_html(html: str) -> list[str]:
    text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", html or "")
    text = re.sub(r"(?i)</?\s*(?:p|div|li|ul|ol|h[1-6]|section|article|tr|td|th|dl|dt|dd)\b[^>]*>", "\n", text)
    text = unescape(HTML_TAG_RE.sub(" ", text))
    return [normalize_whitespace(line) for line in text.splitlines() if normalize_whitespace(line)]


def extract_visible_text_marker_snippet(
    text: str,
    markers: tuple[str, ...],
    stop_headings: tuple[str, ...],
    *,
    max_lines: int = 3,
) -> str:
    lines = split_visible_lines(text)
    stop_heading_set = {normalize_heading_line(heading) for heading in stop_headings}
    normalized_markers = tuple(normalize_for_matching(marker) for marker in markers)
    for index, line in enumerate(lines):
        normalized_line = normalize_for_matching(line)
        if not any(marker in normalized_line for marker in normalized_markers):
            continue
        collected: list[str] = []
        for candidate_line in lines[index : index + max_lines]:
            if collected and normalize_heading_line(candidate_line) in stop_heading_set:
                break
            cleaned = normalize_whitespace(re.sub(r"^[•*-\u2022]+\s*", "", candidate_line))
            if cleaned:
                collected.append(cleaned)
        if collected:
            return normalize_whitespace(" ".join(collected))
    return ""


def extract_bundeswehr_detail_sections(detail_html: str) -> dict[str, str]:
    detail_text = "\n".join(extract_visible_text_lines_from_html(detail_html))
    tasks = extract_visible_text_section(detail_text, BUNDESWEHR_TASK_HEADINGS, BUNDESWEHR_DETAIL_STOP_HEADINGS)
    qualifications = extract_visible_text_section(
        detail_text,
        BUNDESWEHR_QUALIFICATION_HEADINGS,
        BUNDESWEHR_DETAIL_STOP_HEADINGS,
    )
    compensation = extract_visible_text_section(
        detail_text,
        BUNDESWEHR_COMPENSATION_HEADINGS,
        BUNDESWEHR_DETAIL_STOP_HEADINGS,
    )
    if not compensation:
        compensation = extract_visible_text_marker_snippet(
            detail_text,
            BUNDESWEHR_COMPENSATION_MARKERS,
            BUNDESWEHR_DETAIL_STOP_HEADINGS,
        )
    return {
        "tasks": tasks,
        "qualifications": qualifications,
        "compensation": compensation,
    }


def apply_bundeswehr_detail_text(candidate: Candidate, detail_html: str, terms: list[str]) -> bool:
    sections = extract_bundeswehr_detail_sections(detail_html)
    detail_text_for_matching = " ".join(part for part in sections.values() if part)
    original_terms = list(candidate.matched_terms)
    if detail_text_for_matching:
        candidate.matched_terms = sorted(set(candidate.matched_terms + match_terms(detail_text_for_matching, terms)))

    original_notes = candidate.notes
    note_parts = [candidate.notes] if candidate.notes else []
    for label, key in (
        ("Tasks", "tasks"),
        ("Qualifications", "qualifications"),
        ("Compensation", "compensation"),
    ):
        value = sections[key]
        if not value:
            continue
        detail_note = f"{label}: {truncate_text(value, 260)}"
        if detail_note not in note_parts:
            note_parts.append(detail_note)
    candidate.notes = "; ".join(dict.fromkeys(part for part in note_parts if part))
    return candidate.notes != original_notes or candidate.matched_terms != original_terms


def extract_pcd_team_detail_sections(detail_html: str) -> dict[str, str]:
    detail_text = "\n".join(extract_visible_text_lines_from_html(detail_html))
    return {
        "tasks": extract_visible_text_section(detail_text, PCD_TEAM_TASK_HEADINGS, PCD_TEAM_DETAIL_STOP_HEADINGS),
        "qualifications": extract_visible_text_section(
            detail_text,
            PCD_TEAM_QUALIFICATION_HEADINGS,
            PCD_TEAM_DETAIL_STOP_HEADINGS,
        ),
    }


def apply_pcd_team_detail_text(candidate: Candidate, detail_html: str, terms: list[str]) -> bool:
    sections = extract_pcd_team_detail_sections(detail_html)
    detail_text_for_matching = " ".join(part for part in sections.values() if part)
    original_terms = list(candidate.matched_terms)
    if detail_text_for_matching:
        candidate.matched_terms = sorted(set(candidate.matched_terms + match_terms(detail_text_for_matching, terms)))

    original_notes = candidate.notes
    note_parts = [candidate.notes] if candidate.notes else []
    if sections["tasks"]:
        note_parts.append(f"Tasks: {truncate_text(sections['tasks'], 260)}")
    if sections["qualifications"]:
        note_parts.append(f"Qualifications: {truncate_text(sections['qualifications'], 260)}")
    candidate.notes = "; ".join(dict.fromkeys(part for part in note_parts if part))
    return candidate.notes != original_notes or candidate.matched_terms != original_terms


def build_workday_job_url(source_url: str, external_path: str) -> str:
    if not external_path:
        return source_url
    parsed = urlparse(external_path)
    if parsed.scheme and parsed.netloc:
        return normalize_url_without_fragment(external_path)
    return normalize_url_without_fragment(source_url.rstrip("/") + "/" + external_path.lstrip("/"))


def build_workable_job_url(source_url: str, board_slug: str, shortcode: str) -> str:
    if not shortcode:
        return source_url
    parsed = urlparse(source_url)
    base_url = f"{parsed.scheme or 'https'}://{parsed.netloc}"
    return normalize_url_without_fragment(f"{base_url}/{board_slug}/j/{shortcode}")


def extract_verfassungsschutz_value(html: str, label: str) -> str:
    patterns = [
        rf'<strong[^>]*class="label"[^>]*>\s*{re.escape(label)}\s*</strong>\s*<span[^>]*class="value"[^>]*>(?P<value>.*?)</span>',
        rf'<span[^>]*class="label"[^>]*>\s*{re.escape(label)}\s*</span>\s*<span[^>]*class="value"[^>]*>(?P<value>.*?)</span>',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if match:
            return strip_html_fragment(match.group("value"))
    return ""


def extract_verfassungsschutz_section(html: str, *headings: str) -> str:
    for heading in headings:
        pattern = rf'<h2[^>]*>\s*{re.escape(heading)}\s*</h2>\s*(?P<body>.*?)(?=<h2[^>]*>|</main>)'
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if match:
            return strip_html_fragment(match.group("body"))
    return ""


def fetch_verfassungsschutz_job_details(url: str, timeout_seconds: int) -> dict[str, str]:
    html = fetch_text(url, timeout_seconds)

    description = ""
    meta_match = re.search(
        r'<meta[^>]+name="description"[^>]+content="(?P<value>[^"]+)"',
        html,
        re.IGNORECASE,
    )
    if meta_match:
        description = strip_html_fragment(meta_match.group("value"))

    apply_match = re.search(
        r'<a[^>]+href="(?P<href>[^"]+)"[^>]*class="application-link"',
        html,
        re.IGNORECASE,
    )
    apply_url = ""
    if apply_match:
        apply_url = normalize_url_without_fragment(urljoin(url, apply_match.group("href")))

    details = {
        "description": description,
        "deadline": extract_verfassungsschutz_value(html, "Bewerbungsfrist"),
        "career_track": extract_verfassungsschutz_value(html, "Laufbahn"),
        "working_time": extract_verfassungsschutz_value(html, "Arbeitszeit"),
        "location": extract_verfassungsschutz_value(html, "Arbeitsort"),
        "tasks": extract_verfassungsschutz_section(html, "Ihre Aufgaben", "Aufgaben"),
        "offer": extract_verfassungsschutz_section(html, "Wir bieten"),
        "profile": extract_verfassungsschutz_section(html, "Ihr Profil", "Anforderungen"),
        "apply_url": apply_url,
    }
    return details


def is_same_page_link(source_url: str, candidate_url: str) -> bool:
    return normalize_url_without_fragment(source_url) == normalize_url_without_fragment(candidate_url)


def split_visible_lines(value: str) -> list[str]:
    return [normalize_whitespace(part) for part in value.splitlines() if normalize_whitespace(part)]


def extract_yc_jobs_payload(html: str) -> dict[str, Any] | None:
    parser = DataPageCollector()
    parser.feed(html)
    for payload_text in parser.payloads:
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            continue
        props = payload.get("props") or {}
        if payload.get("component") == "WaasJobListingsPage" and isinstance(props.get("jobPostings"), list):
            return payload
    return None


def extract_next_data_payload(html: str) -> dict[str, Any] | None:
    match = NEXT_DATA_SCRIPT_RE.search(html)
    if not match:
        return None
    try:
        return json.loads(unescape(match.group("payload")))
    except json.JSONDecodeError:
        return None


def infer_hn_employer(title: str) -> str:
    title_text = strip_html_fragment(title)
    match = re.match(r"(?P<employer>.+?)\s+\(YC [^)]+\)", title_text, flags=re.IGNORECASE)
    if match:
        return normalize_whitespace(match.group("employer"))
    return "YC startup"


def extract_first_external_url_from_html(html_text: str, base_url: str) -> str:
    parser = LinkCollector()
    parser.feed(html_text or "")
    for link in parser.links:
        absolute_url = normalize_url_without_fragment(urljoin(base_url, link["href"]))
        parsed = urlparse(absolute_url)
        if parsed.scheme in {"http", "https"} and parsed.netloc and parsed.netloc != "news.ycombinator.com":
            return absolute_url
    return ""


def infer_hn_whoishiring_fields(clean_text: str, fallback_employer: str) -> tuple[str, str, str]:
    segments = [normalize_whitespace(segment) for segment in clean_text.split("|") if normalize_whitespace(segment)]
    if not segments:
        employer = fallback_employer or "HN employer"
        return employer, "Hiring post", "unknown"

    employer = segments[0]
    workplace_tokens = ("remote", "hybrid", "onsite", "on-site", "full-time", "part-time", "contract", "intern")

    title = "Hiring post"
    title_index = -1
    for index, segment in enumerate(segments[1:], start=1):
        lowered = normalize_for_matching(segment)
        if any(token in lowered for token in workplace_tokens):
            continue
        title = segment
        title_index = index
        break

    location = "unknown"
    for segment in segments[(title_index + 1) if title_index >= 0 else 1 :]:
        lowered = normalize_for_matching(segment)
        if any(token in lowered for token in workplace_tokens) or "," in segment or "(" in segment:
            location = segment
            break

    return employer or fallback_employer or "HN employer", title, location


def looks_like_non_job_link(text: str, href: str) -> bool:
    text_lower = normalize_whitespace(text).lower()
    href_lower = href.lower()
    if text_lower in {
        "",
        "skip to content",
        "jump to main content.",
        "top of this page",
        "top of page",
        "privacy",
        "privacy policy",
        "impressum",
        "report this content",
        "collapse this bar",
        "customize",
        "accept all",
        "accept selection",
        "decline non-essential cookies",
        "subscribe",
        "subscribed",
    }:
        return True
    return any(
        marker in href_lower
        for marker in (
            "/privacy",
            "/cookie",
            "/impressum",
            "/learn/",
            "/resources/",
            "/resource/",
            "/services/",
            "/abuse/",
        )
    )


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


def extract_json_array_after_marker(text: str, marker: str) -> list[Any] | None:
    marker_index = text.find(marker)
    if marker_index == -1:
        return None
    start = text.find("[", marker_index + len(marker))
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
        elif char == "[":
            depth += 1
        elif char == "]":
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


def extract_recruitee_app_config(html: str) -> dict[str, Any] | None:
    for match in RECRUITEE_DATA_PROPS_RE.finditer(html):
        try:
            payload = json.loads(unescape(match.group("props")))
        except json.JSONDecodeError:
            continue
        app_config = payload.get("appConfig")
        if isinstance(app_config, dict) and isinstance(app_config.get("offers"), list):
            return app_config
    return None


def build_enbw_search_url(source_url: str, term: str, offset: int) -> str:
    parsed = urlparse(source_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    params = {"keywords": term}
    if offset:
        params["from"] = str(offset)
    return f"{base}/de/de/search-results?{urlencode(params)}"


def build_enbw_job_url(source_url: str, job_id: str, title: str) -> str:
    parsed = urlparse(source_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    slug = slugify_title(title)
    if slug:
        return normalize_url_without_fragment(f"{base}/de/de/job/{job_id}/{slug}")
    return normalize_url_without_fragment(f"{base}/de/de/job/{job_id}")


def build_enbw_apply_url(source_url: str, job_seq_no: str) -> str:
    parsed = urlparse(source_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    return normalize_url_without_fragment(f"{base}/de/de/apply?{urlencode({'jobSeqNo': job_seq_no})}")


def build_bnd_search_url(source_url: str, term: str, page_num: int) -> str:
    parsed = urlparse(source_url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params["nn"] = params.get("nn") or "415896"
    params["queryResultId"] = "null"
    params["pageNo"] = str(max(page_num - 1, 0))
    params["templateQueryString"] = term
    return parsed._replace(query=urlencode(params), fragment="sprg415980").geturl()


def build_rheinmetall_page_url(source_url: str, page_num: int) -> str:
    parsed = urlparse(source_url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if page_num > 1:
        params["page"] = str(page_num)
    else:
        params.pop("page", None)
    return parsed._replace(query=urlencode(params)).geturl()


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


def candidate_searchable_text(candidate: Candidate) -> str:
    return normalize_for_matching(
        " ".join(
            part
            for part in [
                candidate.employer,
                candidate.title,
                candidate.location,
                candidate.notes,
                candidate.url,
                candidate.alternate_url,
            ]
            if part
        )
    )


def alignment_candidate_has_sector_evidence(candidate: Candidate) -> bool:
    haystack = candidate_searchable_text(candidate)
    if any(normalize_for_matching(hint) in haystack for hint in ALIGNMENT_TECH_SECTOR_HINTS):
        return True
    return any(normalize_for_matching(employer) in haystack for employer in ALIGNMENT_TECH_PRIORITY_EMPLOYERS)


def filter_coverage_for_track(track: str, coverage: Coverage) -> Coverage:
    if track != "alignment_tech" or coverage.source not in ALIGNMENT_TECH_SECTOR_FILTER_SOURCES:
        return coverage

    kept_candidates = [candidate for candidate in coverage.candidates if alignment_candidate_has_sector_evidence(candidate)]
    removed = len(coverage.candidates) - len(kept_candidates)
    if removed <= 0:
        return coverage

    coverage.candidates = kept_candidates
    coverage.matched_jobs = len(kept_candidates)
    coverage.limitations = list(
        dict.fromkeys(
            [
                *coverage.limitations,
                f"Alignment Tech filter removed {removed} candidate(s) from this broad source without explicit sector evidence.",
            ]
        )
    )
    return coverage


def extract_personio_jobs_from_html(html: str) -> list[Any] | None:
    for match in PERSONIO_NEXT_F_CHUNK_RE.finditer(html):
        chunk = match.group("chunk")
        try:
            decoded = json.loads(f'"{chunk}"')
        except json.JSONDecodeError:
            continue
        jobs = extract_json_array_after_marker(decoded, '{"jobs":')
        if jobs is not None:
            return jobs
    return None


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


def should_keep_service_bund_candidate(
    title: str,
    matched_terms: list[str],
    searchable_text: str,
    *,
    allow_curated_without_term: bool = False,
) -> bool:
    if should_keep_candidate(title, matched_terms, searchable_text):
        return True
    if any(token in title.lower() for token in NON_TECHNICAL_TITLE_HINTS):
        return False
    haystack = normalize_for_matching(searchable_text)
    has_public_interest_tech_hint = any(token in haystack for token in SERVICE_BUND_PUBLIC_INTEREST_HINTS)
    normalized_terms = {normalize_for_matching(term) for term in matched_terms}
    if normalized_terms == {"referent"}:
        return has_public_interest_tech_hint
    if normalized_terms:
        return has_public_interest_tech_hint
    return allow_curated_without_term and has_public_interest_tech_hint


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
        text = normalize_whitespace(link["text"])
        if href.startswith("#"):
            continue
        absolute_url = normalize_url_without_fragment(urljoin(source.url, href))
        if absolute_url in seen_urls:
            continue
        if urlparse(absolute_url).scheme not in {"file", "http", "https"}:
            continue
        if looks_like_non_job_link(text, absolute_url):
            continue
        if is_same_page_link(source.url, absolute_url):
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


def discover_yc_jobs_board(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = fetch_text(source.url, timeout_seconds)
    payload = extract_yc_jobs_payload(html)
    if not payload:
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
            limitations=["YC Startups page did not expose an embedded jobPostings payload."],
            candidates=[],
        )

    postings = payload.get("props", {}).get("jobPostings", [])
    candidates_by_url: dict[str, Candidate] = {}

    for posting in postings:
        title = normalize_whitespace(join_text(posting.get("title"))) or "unknown"
        employer = normalize_whitespace(join_text(posting.get("companyName"))) or source.source
        location = normalize_whitespace(join_text(posting.get("location"))) or "unknown"
        role_specific_type = normalize_whitespace(join_text(posting.get("roleSpecificType")))
        pretty_role = normalize_whitespace(join_text(posting.get("prettyRole")))
        employment_type = normalize_whitespace(join_text(posting.get("type")))
        salary_range = normalize_whitespace(join_text(posting.get("salaryRange")))
        equity_range = normalize_whitespace(join_text(posting.get("equityRange")))
        min_experience = normalize_whitespace(join_text(posting.get("minExperience")))
        visa = normalize_whitespace(join_text(posting.get("visa")))
        company_one_liner = normalize_whitespace(join_text(posting.get("companyOneLiner")))
        company_batch = normalize_whitespace(join_text(posting.get("companyBatchName")))
        created_at = normalize_whitespace(join_text(posting.get("createdAt")))
        last_active = normalize_whitespace(join_text(posting.get("lastActive")))
        job_url = normalize_url_without_fragment(urljoin(source.url, join_text(posting.get("url")) or source.url))
        apply_url_raw = join_text(posting.get("applyUrl"))
        apply_url = normalize_url_without_fragment(urljoin(source.url, apply_url_raw)) if apply_url_raw else ""
        remote = infer_remote_status(location, title, company_one_liner)

        searchable_text = " ".join(
            part
            for part in [
                title,
                employer,
                location,
                role_specific_type,
                pretty_role,
                employment_type,
                salary_range,
                equity_range,
                min_experience,
                visa,
                company_one_liner,
                company_batch,
                created_at,
                last_active,
                job_url,
            ]
            if part
        )
        matched_terms = sorted(set(match_terms(searchable_text, terms)))
        if not should_keep_candidate(title, matched_terms, searchable_text):
            continue

        note_parts = ["YC Startups job board listing"]
        if company_batch:
            note_parts.append(f"Batch: {company_batch}")
        if company_one_liner:
            note_parts.append(f"Company: {company_one_liner}")
        if role_specific_type or pretty_role:
            role_summary = " / ".join(part for part in [pretty_role, role_specific_type] if part)
            note_parts.append(f"Role: {role_summary}")
        if employment_type:
            note_parts.append(f"Type: {employment_type}")
        if salary_range or equity_range:
            comp_summary = " + ".join(part for part in [salary_range, equity_range] if part)
            note_parts.append(f"Comp: {comp_summary}")
        if min_experience:
            note_parts.append(f"Experience: {min_experience}")
        if visa:
            note_parts.append(f"Visa: {visa}")
        if created_at:
            note_parts.append(f"Created: {created_at}")
        if last_active:
            note_parts.append(f"Last active: {last_active}")

        merge_candidate(
            candidates_by_url,
            Candidate(
                employer=employer,
                title=title,
                url=job_url,
                source_url=source.url,
                alternate_url=apply_url if apply_url and apply_url != job_url else "",
                location=location,
                remote=remote,
                matched_terms=matched_terms,
                notes="; ".join(note_parts),
            ),
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
        result_pages_scanned=f"job_postings={len(postings)}",
        direct_job_pages_opened=0,
        enumerated_jobs=len(postings),
        matched_jobs=len(candidates_by_url),
        limitations=[],
        candidates=list(candidates_by_url.values()),
    )


def split_iacr_place(value: str) -> tuple[str, str]:
    place = normalize_whitespace(value)
    for separator in (" | ", " ; ", "; "):
        if separator in place:
            employer, location = place.split(separator, 1)
            return normalize_whitespace(employer), normalize_whitespace(location)
    return place or "unknown", "unknown"


def infer_remote_status(*values: str) -> str:
    haystack = normalize_for_matching(" ".join(value for value in values if value))
    if "hybrid" in haystack:
        return "hybrid"
    if "remote" in haystack:
        return "remote"
    if "on-site" in haystack or "onsite" in haystack:
        return "on-site"
    return "unknown"


def discover_iacr_jobs(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = fetch_text(source.url, timeout_seconds)
    candidates_by_url: dict[str, Candidate] = {}
    posting_count = 0

    for match in IACR_POSTING_BLOCK_RE.finditer(html):
        posting_count += 1
        posting_id = match.group("id")
        outbound_url = normalize_url_without_fragment(urljoin(source.url, unescape(match.group("href"))))
        item_url = normalize_url_without_fragment(urljoin(source.url, f"/jobs/item/{posting_id}"))
        title = strip_html_fragment(match.group("title")) or "unknown"
        body = match.group("body")

        place_match = IACR_PLACE_RE.search(body)
        description_match = IACR_DESCRIPTION_RE.search(body)
        contact_match = IACR_CONTACT_RE.search(body)
        updated_match = IACR_UPDATED_RE.search(body)
        posted_match = IACR_POSTED_RE.search(body)

        place = strip_html_fragment(place_match.group("place")) if place_match else ""
        employer, location = split_iacr_place(place)
        description = strip_html_fragment(description_match.group("description")) if description_match else ""
        contact = strip_html_fragment(contact_match.group("contact")) if contact_match else ""
        updated = normalize_whitespace(updated_match.group("updated")) if updated_match else ""
        posted = normalize_whitespace(posted_match.group("posted")) if posted_match else ""
        remote = infer_remote_status(place, description)

        searchable_text = " ".join(
            part
            for part in [
                title,
                employer,
                location,
                remote,
                description,
                contact,
                updated,
                posted,
                outbound_url,
            ]
            if part
        )
        matched_terms = match_terms(searchable_text, terms)
        if not should_keep_candidate(title, matched_terms, searchable_text):
            continue

        note_parts = ["IACR Jobs board listing"]
        if contact:
            note_parts.append(f"Contact: {contact}")
        if posted:
            note_parts.append(f"Posted: {posted}")
        if updated:
            note_parts.append(f"Updated: {updated}")
        if description:
            note_parts.append(f"Description: {description}")

        merge_candidate(
            candidates_by_url,
            Candidate(
                employer=employer,
                title=title,
                url=item_url,
                source_url=source.url,
                alternate_url=outbound_url if outbound_url != item_url else "",
                location=location,
                remote=remote,
                matched_terms=matched_terms,
                notes="; ".join(note_parts),
            ),
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
        result_pages_scanned=f"posting_blocks={posting_count}",
        direct_job_pages_opened=0,
        enumerated_jobs=posting_count,
        matched_jobs=len(candidates_by_url),
        limitations=[],
        candidates=list(candidates_by_url.values()),
    )


def discover_hackernews_jobs(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    candidates_by_url: dict[str, Candidate] = {}
    listing_pages_scanned = 0
    enumerated_jobs = 0
    next_url = source.url
    limitations: list[str] = []

    while next_url and listing_pages_scanned < MAX_BROWSER_PAGES:
        html = fetch_text(next_url, timeout_seconds)
        listing_pages_scanned += 1
        for match in HN_JOB_ROW_RE.finditer(html):
            enumerated_jobs += 1
            title = strip_html_fragment(match.group("title")) or "unknown"
            job_url = normalize_url_without_fragment(urljoin(next_url, unescape(match.group("href"))))
            age_text = normalize_whitespace(match.group("age"))
            employer = infer_hn_employer(title)
            searchable_text = " ".join(part for part in [title, employer, age_text, job_url] if part)
            matched_terms = sorted(set(match_terms(searchable_text, terms)))
            if not should_keep_candidate(title, matched_terms, searchable_text):
                continue
            merge_candidate(
                candidates_by_url,
                Candidate(
                    employer=employer,
                    title=title,
                    url=job_url,
                    source_url=source.url,
                    matched_terms=matched_terms,
                    notes=f"Hacker News jobs listing; Posted: {age_text}",
                ),
            )
        more_match = HN_MORE_LINK_RE.search(html)
        next_url = urljoin(next_url, unescape(more_match.group("href"))) if more_match else ""

    if next_url:
        limitations.append(f"Stopped after max_pages={MAX_BROWSER_PAGES}.")

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="complete",
        listing_pages_scanned=listing_pages_scanned,
        search_terms_tried=terms,
        result_pages_scanned=f"pages={listing_pages_scanned}",
        direct_job_pages_opened=0,
        enumerated_jobs=enumerated_jobs,
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_hackernews_whoishiring_api(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    parsed = urlparse(source.url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    username = params.get("id") or "whoishiring"
    user = fetch_json(f"https://hacker-news.firebaseio.com/v0/user/{username}.json", timeout_seconds)
    submitted_ids = user.get("submitted") or []

    story: dict[str, Any] | None = None
    story_title = ""
    for item_id in submitted_ids[:30]:
        item = fetch_json(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json", timeout_seconds)
        title = normalize_whitespace(join_text(item.get("title")))
        if item.get("type") == "story" and HN_WHOISHIRING_TITLE_RE.match(title):
            story = item
            story_title = title
            break

    if not story:
        return Coverage(
            source=source.source,
            source_url=source.url,
            discovery_mode=source.discovery_mode,
            cadence_group=source.cadence_group,
            last_checked=source.last_checked,
            due_today=False,
            status="failed",
            listing_pages_scanned=1,
            search_terms_tried=terms,
            result_pages_scanned="story_lookup=0",
            direct_job_pages_opened=0,
            enumerated_jobs=0,
            matched_jobs=0,
            limitations=[f"Could not resolve a recent 'Who is hiring?' story from HN user '{username}'."],
            candidates=[],
        )

    story_id = story["id"]
    story_url = normalize_url_without_fragment(f"https://news.ycombinator.com/item?id={story_id}")
    candidates_by_url: dict[str, Candidate] = {}
    enumerated_jobs = 0

    for comment_id in story.get("kids") or []:
        comment = fetch_json(f"https://hacker-news.firebaseio.com/v0/item/{comment_id}.json", timeout_seconds)
        if comment.get("dead") or comment.get("deleted") or not comment.get("text"):
            continue
        enumerated_jobs += 1
        text_html = join_text(comment.get("text"))
        clean_text = strip_html_fragment(text_html)
        employer, title, location = infer_hn_whoishiring_fields(clean_text, comment.get("by") or "HN employer")
        remote = infer_remote_status(location, clean_text)
        searchable_text = " ".join(part for part in [title, employer, location, clean_text] if part)
        matched_terms = sorted(set(match_terms(searchable_text, terms)))
        if not should_keep_candidate(title, matched_terms, searchable_text):
            continue

        comment_url = normalize_url_without_fragment(f"https://news.ycombinator.com/item?id={comment_id}")
        external_url = extract_first_external_url_from_html(text_html, story_url)
        note_parts = [
            f"HN Who is hiring thread: {story_title}",
            f"Story: {story_url}",
        ]
        excerpt = truncate_text(clean_text, 260)
        if excerpt:
            note_parts.append(f"Excerpt: {excerpt}")
        merge_candidate(
            candidates_by_url,
            Candidate(
                employer=employer,
                title=title,
                url=comment_url,
                source_url=source.url,
                alternate_url=external_url,
                location=location,
                remote=remote,
                matched_terms=matched_terms,
                notes="; ".join(note_parts),
            ),
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
        result_pages_scanned=f"story_id={story_id}; top_level_comments={enumerated_jobs}",
        direct_job_pages_opened=0,
        enumerated_jobs=enumerated_jobs,
        matched_jobs=len(candidates_by_url),
        limitations=[],
        candidates=list(candidates_by_url.values()),
    )


def discover_filtered_html_links(
    source: SourceConfig,
    terms: list[str],
    timeout_seconds: int,
    url_filter: Callable[[str], bool],
    notes: str,
    limitation_if_empty: str | None = None,
) -> Coverage:
    html = fetch_text(source.url, timeout_seconds)
    parser = LinkCollector()
    parser.feed(html)
    raw_urls: set[str] = set()
    candidates_by_url: dict[str, Candidate] = {}

    for link in parser.links:
        absolute_url = normalize_url_without_fragment(urljoin(source.url, link["href"]))
        if urlparse(absolute_url).scheme not in {"http", "https"}:
            continue
        if not url_filter(absolute_url):
            continue
        raw_urls.add(absolute_url)
        text = normalize_whitespace(link["text"]) or "unknown"
        title = split_visible_lines(link["text"])[0] if split_visible_lines(link["text"]) else text
        searchable_text = f"{title} {text} {absolute_url}"
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
                matched_terms=matched_terms,
                notes=notes,
            ),
        )

    limitations = [limitation_if_empty] if not raw_urls and limitation_if_empty else []
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
        result_pages_scanned="filtered_links=1",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_urls),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def build_service_bund_search_url(source_url: str, term: str, gtp: str | None = None) -> str:
    parsed = urlparse(source_url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params["templateQueryString"] = term
    params["resultsPerPage"] = "100"
    params["sortOrder"] = "dateOfIssue_dt desc"
    if gtp:
        params["gtp"] = gtp
    else:
        params.pop("gtp", None)
    query = urlencode(params)
    return parsed._replace(query=query, fragment="").geturl()


def discover_service_bund_search(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    candidates_by_url: dict[str, Candidate] = {}
    limitations: list[str] = []
    listing_pages_scanned = 0
    result_summaries: list[str] = []
    raw_seen_ids: set[str] = set()
    max_pages_per_term = 5

    for term in terms:
        page_num = 1
        gtp: str | None = None
        term_raw_count = 0

        while page_num <= max_pages_per_term:
            html = fetch_text(build_service_bund_search_url(source.url, term, gtp), timeout_seconds)
            listing_pages_scanned += 1

            page_matches = list(SERVICE_BUND_RESULT_RE.finditer(html))
            term_raw_count += len(page_matches)
            for match in page_matches:
                absolute_url = normalize_url_without_fragment(urljoin(source.url, unescape(match.group("href"))))
                raw_seen_ids.add(absolute_url)
                title = strip_html_fragment(match.group("title")) or "unknown"
                title = re.sub(r"^Stellenbezeichnung\s*", "", title, flags=re.IGNORECASE).strip() or "unknown"
                employer = strip_html_fragment(match.group("employer")) or source.source
                posted = normalize_whitespace(strip_html_fragment(match.group("posted")))
                deadline = normalize_whitespace(strip_html_fragment(match.group("deadline")))
                searchable_text = " ".join(part for part in [title, employer, posted, deadline, absolute_url, term] if part)
                matched_terms = sorted(set(match_terms(searchable_text, terms)))
                if not should_keep_service_bund_candidate(title, matched_terms, searchable_text):
                    continue
                notes = "service.bund native search"
                if posted:
                    notes = f"{notes}; posted={posted}"
                if deadline:
                    notes = f"{notes}; deadline={deadline}"
                merge_candidate(
                    candidates_by_url,
                    Candidate(
                        employer=employer,
                        title=title,
                        url=absolute_url,
                        source_url=source.url,
                        matched_terms=matched_terms,
                        notes=notes,
                    ),
                )

            next_match = SERVICE_BUND_NEXT_RE.search(html)
            next_gtp = unescape(next_match.group("gtp")) if next_match else None
            if not next_gtp:
                break
            gtp = next_gtp
            page_num += 1

        if gtp and page_num > max_pages_per_term:
            limitations.append(f"service.bund query '{term}' hit the page cap ({max_pages_per_term}x100 results)")
        result_summaries.append(f"{term}:{page_num}p/{term_raw_count}")

    status = "partial" if limitations else "complete"
    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status=status,
        listing_pages_scanned=listing_pages_scanned,
        search_terms_tried=terms,
        result_pages_scanned=", ".join(result_summaries) if result_summaries else "none",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_seen_ids),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_service_bund_links(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = fetch_text(source.url, timeout_seconds)
    candidates_by_url: dict[str, Candidate] = {}
    raw_urls: set[str] = set()

    for match in SERVICE_BUND_DIRECT_LINK_RE.finditer(html):
        absolute_url = normalize_url_without_fragment(unescape(match.group("href")))
        raw_urls.add(absolute_url)
        title = strip_html_fragment(match.group("text")) or "unknown"
        searchable_text = " ".join(part for part in [title, source.source, absolute_url] if part)
        matched_terms = sorted(set(match_terms(searchable_text, terms)))
        if not should_keep_service_bund_candidate(
            title,
            matched_terms,
            searchable_text,
            allow_curated_without_term=True,
        ):
            continue
        merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=absolute_url,
                source_url=source.url,
                matched_terms=matched_terms,
                notes="Direct service.bund job links on source page",
            ),
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
        enumerated_jobs=len(raw_urls),
        matched_jobs=len(candidates_by_url),
        limitations=[],
        candidates=list(candidates_by_url.values()),
    )


def discover_recruitee_inline(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = fetch_text(source.url, timeout_seconds)
    app_config = extract_recruitee_app_config(html)
    if not app_config:
        return Coverage(
            source=source.source,
            source_url=source.url,
            discovery_mode=source.discovery_mode,
            cadence_group=source.cadence_group,
            last_checked=source.last_checked,
            due_today=False,
            status="partial",
            listing_pages_scanned=1,
            search_terms_tried=terms,
            result_pages_scanned="inline_payload=0",
            direct_job_pages_opened=0,
            enumerated_jobs=0,
            matched_jobs=0,
            limitations=["Recruitee appConfig with offers was not found in the page HTML."],
            candidates=[],
        )

    departments: dict[int, str] = {}
    for department in app_config.get("departments") or []:
        if not isinstance(department, dict):
            continue
        name = join_text(department.get("translations") or {})
        if department.get("id") and name:
            departments[int(department["id"])] = normalize_whitespace(name)

    candidates_by_url: dict[str, Candidate] = {}
    published_offers = [offer for offer in app_config.get("offers") or [] if offer.get("status") == "published"]

    for offer in published_offers:
        if not isinstance(offer, dict):
            continue
        translations = offer.get("translations") or {}
        primary_lang = offer.get("primaryLangCode") or ""
        translation = translations.get(primary_lang) if isinstance(translations, dict) else None
        if not translation and isinstance(translations, dict) and translations:
            translation = next(iter(translations.values()))
        translation = translation or {}

        title = normalize_whitespace(join_text(translation.get("title"))) or "unknown"
        slug = normalize_whitespace(join_text(offer.get("slug")))
        job_url = (
            normalize_url_without_fragment(urljoin(source.url.rstrip("/") + "/", f"o/{slug}"))
            if slug
            else source.url
        )
        city = normalize_whitespace(join_text(offer.get("city")))
        state = normalize_whitespace(join_text(translation.get("state")))
        country = normalize_whitespace(join_text(translation.get("country")))
        location_parts: list[str] = []
        for part in (city, state, country):
            if part and part not in location_parts:
                location_parts.append(part)
        location = ", ".join(location_parts) or "unknown"
        department = departments.get(int(offer["departmentId"])) if offer.get("departmentId") else ""
        employment_type = normalize_whitespace(join_text(offer.get("employmentType"))).replace("_", " ")
        experience = normalize_whitespace(join_text(offer.get("experience"))).replace("_", " ")
        education = normalize_whitespace(join_text(offer.get("education"))).replace("_", " ")
        tags = ", ".join(normalize_whitespace(join_text(tag)) for tag in offer.get("tags") or [] if join_text(tag))
        description = strip_html_fragment(join_text(translation.get("descriptionHtml")))
        requirements = strip_html_fragment(join_text(translation.get("requirementsHtml")))

        remote = "unknown"
        if offer.get("hybrid"):
            remote = "hybrid"
        elif offer.get("remote"):
            remote = "remote"
        elif offer.get("onSite"):
            remote = "on-site"

        searchable_text = " ".join(
            part
            for part in [
                title,
                department,
                location,
                remote,
                employment_type,
                experience,
                education,
                tags,
                description,
                requirements,
            ]
            if part
        )
        matched_terms = sorted(set(match_terms(searchable_text, terms)))
        if not should_keep_candidate(title, matched_terms, searchable_text):
            continue

        note_parts = ["Recruitee inline offers payload"]
        if department:
            note_parts.append(f"Department: {department}")
        if employment_type:
            note_parts.append(f"Type: {employment_type}")
        if remote != "unknown":
            note_parts.append(f"Remote: {remote}")

        merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=job_url,
                source_url=source.url,
                location=location,
                remote=remote,
                matched_terms=matched_terms,
                notes="; ".join(note_parts),
            ),
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
        result_pages_scanned=f"offers={len(published_offers)}",
        direct_job_pages_opened=0,
        enumerated_jobs=len(published_offers),
        matched_jobs=len(candidates_by_url),
        limitations=[],
        candidates=list(candidates_by_url.values()),
    )


def discover_verfassungsschutz_rss(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    xml_text = fetch_text(VERFASSUNGSSCHUTZ_RSS_URL, timeout_seconds)
    root = ET.fromstring(xml_text)
    items = root.findall("./channel/item")
    candidates_by_url: dict[str, Candidate] = {}
    direct_job_pages_opened = 0
    detail_fetch_failures = 0

    for item in items:
        title = normalize_whitespace(item.findtext("title") or "") or "unknown"
        link = normalize_url_without_fragment(item.findtext("link") or source.url)
        description = strip_html_fragment(item.findtext("description") or "")
        published = normalize_whitespace(item.findtext("pubDate") or "")
        location = "unknown"
        alternate_url = ""
        note_parts = ["Verfassungsschutz RSS feed"]
        searchable_parts = [title, description, published, link]

        if published:
            note_parts.append(f"published={published}")

        direct_job_pages_opened += 1
        try:
            details = fetch_verfassungsschutz_job_details(link, timeout_seconds)
            if details["location"]:
                location = details["location"]
            if details["apply_url"]:
                alternate_url = details["apply_url"]
            searchable_parts.extend(
                part
                for part in (
                    details["description"],
                    details["deadline"],
                    details["career_track"],
                    details["working_time"],
                    details["location"],
                    details["tasks"],
                    details["offer"],
                    details["profile"],
                    details["apply_url"],
                )
                if part
            )
            if details["description"]:
                note_parts.append(f"Description: {truncate_text(details['description'], 180)}")
            if details["deadline"]:
                note_parts.append(f"Deadline: {details['deadline']}")
            if details["career_track"]:
                note_parts.append(f"Laufbahn: {details['career_track']}")
            if details["working_time"]:
                note_parts.append(f"Arbeitszeit: {details['working_time']}")
            if details["location"]:
                note_parts.append(f"Location: {details['location']}")
            if details["tasks"]:
                note_parts.append(f"Tasks: {truncate_text(details['tasks'], 260)}")
            if details["profile"]:
                note_parts.append(f"Profile: {truncate_text(details['profile'], 260)}")
        except Exception:
            detail_fetch_failures += 1

        searchable_text = " ".join(part for part in searchable_parts if part)
        matched_terms = sorted(set(match_terms(searchable_text, terms)))
        if not should_keep_service_bund_candidate(title, matched_terms, searchable_text):
            continue
        merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=link,
                source_url=source.url,
                alternate_url=alternate_url,
                location=location,
                matched_terms=matched_terms,
                notes="; ".join(note_parts),
            ),
        )

    limitations: list[str] = []
    status = "complete"
    if detail_fetch_failures:
        status = "partial"
        limitations.append(
            f"detail page enrichment failed for {detail_fetch_failures} of {len(items)} RSS items; affected roles fall back to feed metadata"
        )

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
        result_pages_scanned=f"rss_items={len(items)}",
        direct_job_pages_opened=direct_job_pages_opened,
        enumerated_jobs=len(items),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_auswaertiges_amt_json(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = fetch_text(source.url, timeout_seconds)
    match = AUSWAERTIGES_AMT_ACTION_RE.search(html)
    if not match:
        return Coverage(
            source=source.source,
            source_url=source.url,
            discovery_mode=source.discovery_mode,
            cadence_group=source.cadence_group,
            last_checked=source.last_checked,
            due_today=False,
            status="partial",
            listing_pages_scanned=1,
            search_terms_tried=terms,
            result_pages_scanned="json_feed=0",
            direct_job_pages_opened=0,
            enumerated_jobs=0,
            matched_jobs=0,
            limitations=["Auswärtiges Amt JSON job-list endpoint was not found in the page HTML."],
            candidates=[],
        )

    endpoint = normalize_url_without_fragment(urljoin(source.url, unescape(match.group("endpoint"))))
    payload = fetch_json(endpoint, timeout_seconds)
    items = payload.get("items") or []
    candidates_by_url: dict[str, Candidate] = {}

    for item in items:
        if not isinstance(item, dict):
            continue
        title = normalize_whitespace(join_text(item.get("headline"))) or "unknown"
        link = normalize_url_without_fragment(urljoin(source.url, join_text(item.get("link")) or source.url))
        description = strip_html_fragment(join_text(item.get("text")))
        location = "; ".join(normalize_whitespace(join_text(value)) for value in item.get("department") or [] if join_text(value))
        published = normalize_whitespace(join_text(item.get("date")))
        closing = normalize_whitespace(join_text(item.get("closingDate")))
        searchable_text = " ".join(part for part in [title, location, description, published, closing, link] if part)
        matched_terms = sorted(set(match_terms(searchable_text, terms)))
        if not should_keep_service_bund_candidate(title, matched_terms, searchable_text):
            continue
        note_parts = ["Auswärtiges Amt JSON listings"]
        if published:
            note_parts.append(f"Published: {published}")
        if closing:
            note_parts.append(f"Deadline: {closing}")
        merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=link,
                source_url=source.url,
                location=location or "unknown",
                matched_terms=matched_terms,
                notes="; ".join(note_parts),
            ),
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
        result_pages_scanned=f"json_items={len(items)}",
        direct_job_pages_opened=0,
        enumerated_jobs=len(items),
        matched_jobs=len(candidates_by_url),
        limitations=[],
        candidates=list(candidates_by_url.values()),
    )


def discover_enbw_phenom(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    candidates_by_url: dict[str, Candidate] = {}
    raw_seen_ids: set[str] = set()
    limitations: list[str] = []
    result_summaries: list[str] = []
    listing_pages_scanned = 0
    max_pages_per_term = 5

    for term in terms:
        offset = 0
        term_pages = 0
        term_seen = 0
        term_total: int | None = None
        while term_pages < max_pages_per_term:
            html = fetch_text(build_enbw_search_url(source.url, term, offset), timeout_seconds)
            ddo = extract_json_object_after_marker(html, "phApp.ddo = ")
            if not isinstance(ddo, dict):
                limitations.append(f"EnBW search payload for '{term}' was not found in the page HTML.")
                break
            payload = ddo.get("eagerLoadRefineSearch") or {}
            jobs = payload.get("data", {}).get("jobs") or []
            hits = int(payload.get("hits") or len(jobs))
            term_total = int(payload.get("totalHits") or len(jobs))
            term_pages += 1
            listing_pages_scanned += 1
            term_seen += len(jobs)

            for job in jobs:
                if not isinstance(job, dict):
                    continue
                job_id = normalize_whitespace(join_text(job.get("jobId") or job.get("reqId") or job.get("jobSeqNo")))
                if not job_id:
                    continue
                raw_seen_ids.add(job_id)
                title = normalize_whitespace(join_text(job.get("title"))) or "unknown"
                employer = normalize_whitespace(join_text(job.get("company"))) or source.source
                location = normalize_whitespace(
                    join_text(job.get("cityStateCountry") or job.get("location") or job.get("city"))
                ) or "unknown"
                description = strip_html_fragment(join_text(job.get("descriptionTeaser")))
                category = normalize_whitespace(join_text(job.get("category")))
                remote = normalize_whitespace(join_text(job.get("remote"))) or "unknown"
                job_seq_no = normalize_whitespace(join_text(job.get("jobSeqNo")))
                job_url = build_enbw_job_url(source.url, job_id, title)
                apply_url = build_enbw_apply_url(source.url, job_seq_no) if job_seq_no else ""
                searchable_text = " ".join(
                    part for part in [title, employer, location, category, remote, description] if part
                )
                matched_terms = sorted(set(match_terms(searchable_text, terms)))
                if not should_keep_candidate(title, matched_terms, searchable_text):
                    continue
                merge_candidate(
                    candidates_by_url,
                    Candidate(
                        employer=employer,
                        title=title,
                        url=job_url,
                        source_url=source.url,
                        alternate_url=apply_url if apply_url and apply_url != job_url else "",
                        location=location,
                        remote=remote,
                        matched_terms=matched_terms,
                        notes=f"EnBW Phenom search keyword='{term}'",
                    ),
                )

            if not jobs or term_total is None or term_seen >= term_total:
                break
            offset += hits or ENBW_RESULTS_PAGE_SIZE

        total_label = term_total if term_total is not None else term_seen
        result_summaries.append(f"{term}:{term_pages}p/{term_seen}of{total_label}")
        if term_total is not None and term_seen < term_total:
            limitations.append(f"EnBW search for '{term}' surfaced {term_seen} of {term_total} results")

    status = "partial" if limitations else "complete"
    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status=status,
        listing_pages_scanned=listing_pages_scanned,
        search_terms_tried=terms,
        result_pages_scanned=", ".join(result_summaries) if result_summaries else "none",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_seen_ids),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_bundeswehr_jobsuche(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = fetch_text(BUNDESWEHR_JOBSUCHE_URL, timeout_seconds)
    candidates_by_url: dict[str, Candidate] = {}
    raw_urls: set[str] = set()
    detail_pages_opened = 0

    for match in BUNDESWEHR_JOB_TITLE_RE.finditer(html):
        absolute_url = normalize_url_without_fragment(urljoin(BUNDESWEHR_JOBSUCHE_URL, unescape(match.group("href"))))
        raw_urls.add(absolute_url)
        title = strip_html_fragment(match.group("title")) or "unknown"
        searchable_text = " ".join(part for part in [title, absolute_url] if part)
        matched_terms = sorted(set(match_terms(searchable_text, terms)))
        if not should_keep_service_bund_candidate(title, matched_terms, searchable_text):
            continue
        candidate = Candidate(
            employer=source.source,
            title=title,
            url=build_bundeswehr_portal_candidate_url(source.url, absolute_url),
            source_url=source.url,
            alternate_url=absolute_url,
            matched_terms=matched_terms,
            notes="Bundeswehr jobsuche profile catalog fallback; Bewerbungsportal returned a generic error page in automation",
        )
        try:
            detail_html = fetch_text(absolute_url, timeout_seconds)
        except Exception:
            detail_html = ""
        else:
            detail_pages_opened += 1
            apply_bundeswehr_detail_text(candidate, detail_html, terms)
        merge_candidate(candidates_by_url, candidate)

    limitations = [
        "Bundeswehr Bewerbungsportal returned a generic error page in automation; using the public jobsuche profile catalog as a fallback."
    ]
    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="partial",
        listing_pages_scanned=1,
        search_terms_tried=terms,
        result_pages_scanned=f"profiles={len(raw_urls)}",
        direct_job_pages_opened=detail_pages_opened,
        enumerated_jobs=len(raw_urls),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_bnd_career_search(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    candidates_by_url: dict[str, Candidate] = {}
    raw_urls: set[str] = set()
    listing_pages_scanned = 0
    result_summaries: list[str] = []
    limitations: list[str] = []
    errored_terms: list[str] = []
    parsed_source = urlparse(source.url)
    base_url = f"{parsed_source.scheme}://{parsed_source.netloc}/"

    for term in terms:
        try:
            html = fetch_text(build_bnd_search_url(source.url, term, 1), timeout_seconds)
        except Exception:
            errored_terms.append(term)
            continue
        listing_pages_scanned += 1
        term_seen = 0
        for match in BND_RESULT_RE.finditer(html):
            absolute_url = normalize_url_without_fragment(urljoin(base_url, unescape(match.group("href"))))
            raw_urls.add(absolute_url)
            title = strip_html_fragment(match.group("title")) or "unknown"
            bubbles = [
                strip_html_fragment(bubble_match.group("text"))
                for bubble_match in BND_BUBBLE_RE.finditer(match.group("bubbles"))
                if strip_html_fragment(bubble_match.group("text"))
            ]
            location = bubbles[0] if bubbles else "unknown"
            searchable_text = " ".join(part for part in [title, *bubbles] if part)
            matched_terms = sorted(set(match_terms(searchable_text, terms)))
            if not should_keep_service_bund_candidate(title, matched_terms, searchable_text):
                continue
            term_seen += 1
            notes = f"BND native career search keyword='{term}'"
            if len(bubbles) > 1:
                notes = f"{notes}; tags={', '.join(bubbles[1:])}"
            merge_candidate(
                candidates_by_url,
                Candidate(
                    employer=source.source,
                    title=title,
                    url=absolute_url,
                    source_url=source.url,
                    location=location,
                    matched_terms=matched_terms,
                    notes=notes,
                ),
            )
        result_summaries.append(f"{term}:1p/{term_seen}")

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
        listing_pages_scanned=listing_pages_scanned,
        search_terms_tried=terms,
        result_pages_scanned=", ".join(result_summaries) if result_summaries else "none",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_urls),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_rheinmetall_html(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    first_page_html = fetch_text(source.url, timeout_seconds)
    page_numbers = [int(match.group("page")) for match in RHEINMETALL_PAGE_NUMBER_RE.finditer(first_page_html)]
    total_pages = max(page_numbers) if page_numbers else 1
    pages_to_scan = min(total_pages, MAX_RHEINMETALL_PAGES)
    candidates_by_url: dict[str, Candidate] = {}
    raw_urls: set[str] = set()
    listing_pages_scanned = 0
    result_summaries: list[str] = []
    limitations: list[str] = []

    if total_pages > pages_to_scan:
        limitations.append(
            f"Rheinmetall exposes {total_pages} paginated result pages; scanned the first {pages_to_scan} pages."
        )

    for page_num in range(1, pages_to_scan + 1):
        try:
            html = first_page_html if page_num == 1 else fetch_text(build_rheinmetall_page_url(source.url, page_num), timeout_seconds)
        except Exception as exc:
            limitations.append(f"page {page_num}: {exc}")
            continue
        listing_pages_scanned += 1
        card_starts = [match.start() for match in RHEINMETALL_CARD_START_RE.finditer(html)]
        result_summaries.append(f"{page_num}:{len(card_starts)}")
        if not card_starts:
            continue

        for index, start in enumerate(card_starts):
            end = card_starts[index + 1] if index + 1 < len(card_starts) else len(html)
            chunk = html[start:end]
            href_match = RHEINMETALL_CARD_URL_RE.search(chunk)
            title_match = RHEINMETALL_CARD_TITLE_RE.search(chunk)
            if not href_match or not title_match:
                continue

            absolute_url = normalize_url_without_fragment(urljoin(source.url, unescape(href_match.group("href"))))
            raw_urls.add(absolute_url)
            title = strip_html_fragment(title_match.group("title")) or "unknown"
            meta_match = RHEINMETALL_CARD_META_RE.search(chunk)
            meta = strip_html_fragment(meta_match.group("meta")) if meta_match else ""

            employer = source.source
            location = "unknown"
            if "|" in meta:
                employer_text, location_text = [normalize_whitespace(part) for part in meta.split("|", 1)]
                employer = employer_text or employer
                location = location_text or location
            elif meta:
                employer = meta

            searchable_text = " ".join(part for part in [title, employer, location] if part)
            matched_terms = sorted(set(match_terms(searchable_text, terms)))
            if not should_keep_service_bund_candidate(title, matched_terms, searchable_text):
                continue

            merge_candidate(
                candidates_by_url,
                Candidate(
                    employer=employer,
                    title=title,
                    url=absolute_url,
                    source_url=source.url,
                    location=location,
                    matched_terms=matched_terms,
                    notes=f"Rheinmetall SSR jobs page {page_num}/{total_pages}",
                ),
            )

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="partial" if limitations else "complete",
        listing_pages_scanned=listing_pages_scanned,
        search_terms_tried=terms,
        result_pages_scanned=", ".join(result_summaries) if result_summaries else "none",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_urls),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_pcd_team(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = fetch_text(source.url, timeout_seconds)
    searchable_text = strip_html_fragment(html)

    title_match = re.search(r"<h1>(?P<title>.*?)</h1>", html, flags=re.DOTALL | re.IGNORECASE)
    title = strip_html_fragment(title_match.group("title")) if title_match else "Software Engineer"
    if "·" in title:
        title = normalize_whitespace(title.split("·", 1)[0])
    title = re.sub(r"\s+JD$", "", title).strip() or "Software Engineer"

    apply_match = re.search(
        r'<a href="(?P<href>[^"]+)"[^>]*>\s*Apply Here\s*</a>',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    apply_url = normalize_url_without_fragment(apply_match.group("href")) if apply_match else ""
    matched_terms = sorted(set(match_terms(searchable_text, terms)))

    candidates: list[Candidate] = []
    if should_keep_candidate(title, matched_terms, searchable_text):
        candidate = Candidate(
            employer=source.source,
            title=title,
            url=source.url,
            source_url=source.url,
            alternate_url=apply_url,
            matched_terms=matched_terms,
            notes="PCD Team job description page",
        )
        apply_pcd_team_detail_text(candidate, html, terms)
        candidates.append(candidate)

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
        enumerated_jobs=1,
        matched_jobs=len(candidates),
        limitations=[],
        candidates=candidates,
    )


def discover_qedit_inline(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = fetch_text(source.url, timeout_seconds)
    body = strip_html_fragment(html)
    title = "Cryptography Engineer"
    candidates: list[Candidate] = []
    limitations: list[str] = []
    enumerated_jobs = 0

    match = re.search(r"Open Positions\s+Cryptography Engineer\s+\+\s+(.*?)(?:Please contact|QEDIT Office Life|$)", body)
    if match:
        enumerated_jobs = 1
        snippet = normalize_whitespace(f"{title} {match.group(1)}")
        matched_terms = sorted(set(match_terms(snippet, terms)))
        if should_keep_candidate(title, matched_terms, snippet):
            candidates.append(
                Candidate(
                    employer=source.source,
                    title=title,
                    url=source.url,
                    source_url=source.url,
                    matched_terms=matched_terms,
                    notes="Inline careers page posting",
                )
            )
    else:
        limitations.append("Expected inline 'Cryptography Engineer' role was not found on the careers page.")

    if "Cryptography Interns" in body:
        limitations.append("Page mentions biannual cryptography interns, but not as a direct current opening.")

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="complete" if enumerated_jobs else "partial",
        listing_pages_scanned=1,
        search_terms_tried=terms,
        result_pages_scanned="inline_roles=1",
        direct_job_pages_opened=0,
        enumerated_jobs=enumerated_jobs,
        matched_jobs=len(candidates),
        limitations=limitations,
        candidates=candidates,
    )


def discover_leastauthority_careers(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    del terms
    html = fetch_text(source.url, timeout_seconds)
    parser = LinkCollector()
    parser.feed(html)
    raw_urls: set[str] = set()
    for link in parser.links:
        absolute_url = normalize_url_without_fragment(urljoin(source.url, link["href"]))
        if any(host in absolute_url for host in ("boards.greenhouse.io", "jobs.lever.co", "apply.workable.com", "ashbyhq.com")):
            raw_urls.add(absolute_url)
    limitations = []
    if not raw_urls:
        limitations.append("Careers page exposes category filters and company sections, but no direct current job links.")
    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="complete",
        listing_pages_scanned=1,
        search_terms_tried=[],
        result_pages_scanned="career_page=1",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_urls),
        matched_jobs=0,
        limitations=limitations,
        candidates=[],
    )


def discover_cybernetica_teamdash(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    return discover_filtered_html_links(
        source,
        terms,
        timeout_seconds,
        lambda url: "cyber.teamdash.com/p/job/" in url,
        notes="Enumerated through Teamdash links on the Cybernetica careers page",
        limitation_if_empty="No Teamdash job links were visible on the Cybernetica careers page.",
    )


def discover_secunet_jobboard(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    pattern = re.compile(r"^https://jobs\.secunet\.com/.+-j\d+\.html$")
    return discover_filtered_html_links(
        source,
        terms,
        timeout_seconds,
        lambda url: bool(pattern.match(url)),
        notes="Enumerated through direct secunet job-detail links",
        limitation_if_empty="No secunet job-detail links matching the standard job pattern were visible.",
    )


def discover_neclab_jobs(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    return discover_filtered_html_links(
        source,
        terms,
        timeout_seconds,
        lambda url: "jobs.neclab.eu/jobs/get" in url and "jid=" in url,
        notes="Enumerated through NEC Laboratories Europe job-detail links",
        limitation_if_empty="No NEC Laboratories Europe job-detail links were visible on the jobs page.",
    )


def discover_qusecure_careers(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    del terms
    html = fetch_text(source.url, timeout_seconds)
    parser = LinkCollector()
    parser.feed(html)
    body = strip_html_fragment(html)
    raw_urls: set[str] = set()
    for link in parser.links:
        absolute_url = normalize_url_without_fragment(urljoin(source.url, link["href"]))
        if any(host in absolute_url for host in ("boards.greenhouse.io", "jobs.lever.co", "apply.workable.com", "ashbyhq.com")):
            raw_urls.add(absolute_url)
    limitations = []
    if "Please send cover letter and resume to Careers@qusecure.com." in body:
        limitations.append("Career page requests email applications and exposes no direct job listings.")
    elif not raw_urls:
        limitations.append("No direct job listings were visible on the QuSecure careers page.")
    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="complete",
        listing_pages_scanned=1,
        search_terms_tried=[],
        result_pages_scanned="career_page=1",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_urls),
        matched_jobs=0,
        limitations=limitations,
        candidates=[],
    )


def discover_partisia_site(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    del terms
    checked_urls = [source.url]
    if source.url != "https://partisiafoundation.com/":
        checked_urls.append("https://partisiafoundation.com/")

    found_jobish_links: set[str] = set()
    limitations: list[str] = []
    pages_scanned = 0
    for url in checked_urls:
        pages_scanned += 1
        try:
            html = fetch_text(url, timeout_seconds)
        except Exception as exc:
            limitations.append(f"Could not read {url}: {type(exc).__name__}: {exc}")
            continue
        parser = LinkCollector()
        parser.feed(html)
        for link in parser.links:
            absolute_url = normalize_url_without_fragment(urljoin(url, link["href"]))
            combined = f"{link['text']} {absolute_url}".lower()
            if any(token in combined for token in ("career", "careers", "jobs", "join us", "work with us")):
                found_jobish_links.add(absolute_url)

    if not found_jobish_links:
        limitations.append("Official Partisia sites exposed no careers page or direct job listings.")

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="complete",
        listing_pages_scanned=pages_scanned,
        search_terms_tried=[],
        result_pages_scanned="homepage_scan=1",
        direct_job_pages_opened=0,
        enumerated_jobs=len(found_jobish_links),
        matched_jobs=0,
        limitations=limitations,
        candidates=[],
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


def build_ibm_title_query(terms: list[str]) -> str:
    query_terms: list[str] = []
    for term in terms:
        normalized = term.strip()
        if not normalized:
            continue
        escaped = normalized.replace("\\", "\\\\").replace('"', '\\"')
        if " " in normalized or "-" in normalized:
            query_terms.append(f'"{escaped}"')
        else:
            query_terms.append(escaped)
    if not query_terms:
        return ""
    return "title:(" + " OR ".join(query_terms) + ")"


def build_ibm_search_payload(offset: int, size: int, title_query: str | None = None) -> dict[str, Any]:
    must_clauses: list[dict[str, Any]] = []
    if title_query:
        must_clauses.append({"query_string": {"query": title_query}})
    return {
        "appId": "careers",
        "scopes": ["careers2"],
        "query": {"bool": {"must": must_clauses}},
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


IBM_RESEARCH_GENERIC_MATCH_TERMS = frozenset({"research scientist", "postdoc", "postdoctoral"})


def should_keep_ibm_candidate(source: SourceConfig, title: str, matched_terms: list[str]) -> bool:
    if source.source != "IBM Research":
        return True

    title_lower = title.lower()
    if "postdoctoral" in title_lower or "postdoc" in title_lower:
        return True
    if "research scientist" not in title_lower:
        return False

    normalized_matches = {normalize_for_matching(term) for term in matched_terms}
    return any(term not in IBM_RESEARCH_GENERIC_MATCH_TERMS for term in normalized_matches)


def discover_ibm_api(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    candidates_by_url: dict[str, Candidate] = {}
    raw_seen_ids: set[str] = set()
    pages_scanned = 0
    total_hits = 0
    offset = 0
    title_query = build_ibm_title_query(terms)

    while True:
        payload = build_ibm_search_payload(offset, IBM_RESULTS_PAGE_SIZE, title_query=title_query)
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
            if not should_keep_ibm_candidate(source, title, matched_terms):
                continue
            note_parts = ["Enumerated through IBM careers search API with title-scoped server-side filtering"]
            if description:
                note_parts.append(f"Summary: {truncate_text(description, 220)}")
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
                    notes="; ".join(note_parts),
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
                matched_terms = sorted(
                    set(match_terms_with_aliases(searchable_text, terms, THALES_PAYLOAD_TERM_ALIASES))
                )
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
                absolute_url = build_workday_job_url(source.url, external_path)
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


def discover_workable_api(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    path_bits = [bit for bit in urlparse(source.url).path.split("/") if bit]
    if not path_bits:
        raise ValueError(f"Could not derive Workable board slug from {source.url}")
    board_slug = path_bits[0]
    parsed = urlparse(source.url)
    endpoint = f"{parsed.scheme or 'https'}://{parsed.netloc}/api/v3/accounts/{board_slug}/jobs"
    response = post_json(
        endpoint,
        {"query": ""},
        timeout_seconds,
        headers={"Referer": source.url, "X-Requested-With": "XMLHttpRequest"},
    )
    jobs = response.get("results") or []
    reported_total = int(response.get("total", len(jobs)) or 0)
    candidates_by_url: dict[str, Candidate] = {}

    for job in jobs:
        title = normalize_whitespace(join_text(job.get("title"))) or "unknown"
        location = normalize_whitespace(join_text(job.get("location"))) or normalize_whitespace(join_text(job.get("locations")))
        location = location or "unknown"
        workplace = normalize_whitespace(join_text(job.get("workplace")))
        department = normalize_whitespace(join_text(job.get("department")))
        employment_type = normalize_whitespace(join_text(job.get("type")))
        shortcode = normalize_whitespace(join_text(job.get("shortcode")))
        remote_flag = job.get("remote")
        if remote_flag is True:
            remote = "remote"
        elif remote_flag is False:
            remote = infer_remote_status(location, workplace)
        else:
            remote = infer_remote_status(location, workplace, join_text(remote_flag))

        searchable_text = " ".join(
            part
            for part in [
                title,
                location,
                workplace,
                department,
                employment_type,
                join_text(job.get("state")),
                join_text(job.get("published")),
            ]
            if part
        )
        matched_terms = sorted(set(match_terms(searchable_text, terms)))
        if not should_keep_candidate(title, matched_terms, searchable_text):
            continue

        note_parts = ["Enumerated through Workable jobs API"]
        if department:
            note_parts.append(f"Department: {department}")
        if workplace:
            note_parts.append(f"Workplace: {workplace}")
        if employment_type:
            note_parts.append(f"Type: {employment_type}")

        merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=build_workable_job_url(source.url, board_slug, shortcode),
                source_url=source.url,
                location=location,
                remote=remote,
                matched_terms=matched_terms,
                notes="; ".join(note_parts),
            ),
        )

    limitations: list[str] = []
    status = "complete"
    if reported_total > len(jobs):
        status = "partial"
        limitations.append(
            f"Workable reported {reported_total} openings but returned {len(jobs)} records in the board payload."
        )

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
        result_pages_scanned="local_filter=1",
        direct_job_pages_opened=0,
        enumerated_jobs=reported_total or len(jobs),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_getro_api(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = fetch_text(source.url, timeout_seconds)
    next_data = extract_next_data_payload(html)
    if not next_data:
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
            limitations=["Getro jobs page did not expose a __NEXT_DATA__ payload."],
            candidates=[],
        )

    page_props = next_data.get("props", {}).get("pageProps", {})
    collection_id = normalize_whitespace(join_text(page_props.get("network", {}).get("id")))
    if not collection_id:
        collection_id = normalize_whitespace(join_text(page_props.get("initialState", {}).get("network", {}).get("id")))
    if not collection_id:
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
            limitations=["Getro jobs page exposed __NEXT_DATA__ but no collection id."],
            candidates=[],
        )

    endpoint = f"https://api.getro.com/api/v2/collections/{collection_id}/search/jobs"
    candidates_by_url: dict[str, Candidate] = {}
    raw_seen_ids: set[str] = set()
    page_signatures: set[str] = set()
    reported_total = 0
    limitations: list[str] = []
    pages_scanned = 0
    status = "complete"
    reached_end = False
    observed_page_size = 0

    for page_num in range(MAX_GETRO_PAGES):
        response = post_json(
            endpoint,
            {"hitsPerPage": GETRO_RESULTS_PAGE_SIZE, "page": page_num, "filters": "", "query": ""},
            timeout_seconds,
            headers={"Referer": source.url},
        )
        results = response.get("results", {})
        jobs = results.get("jobs") or []
        reported_total = max(reported_total, int(results.get("count", reported_total or 0) or 0))
        if not jobs:
            reached_end = True
            break
        if not observed_page_size:
            observed_page_size = len(jobs)

        page_signature = ",".join(str(job.get("id") or job.get("slug") or job.get("url") or "") for job in jobs[:10])
        if page_signature and page_signature in page_signatures:
            status = "partial"
            limitations.append("Getro collection search repeated a page before exhausting the listing.")
            break
        if page_signature:
            page_signatures.add(page_signature)

        pages_scanned += 1
        for job in jobs:
            raw_id = str(job.get("id") or job.get("slug") or job.get("url") or f"{page_num}:{len(raw_seen_ids)}")
            raw_seen_ids.add(raw_id)
            title = normalize_whitespace(join_text(job.get("title"))) or "unknown"
            employer = normalize_whitespace(join_text(job.get("organization", {}).get("name"))) or source.source
            location_parts = [normalize_whitespace(join_text(item)) for item in (job.get("locations") or [])]
            location = "; ".join(part for part in location_parts if part) or "unknown"
            work_mode = normalize_whitespace(join_text(job.get("workMode") or job.get("work_mode")))
            seniority = normalize_whitespace(join_text(job.get("seniority")))
            topics = [normalize_whitespace(join_text(item)) for item in (job.get("organization", {}).get("topics") or [])]
            topics = [item for item in topics if item]
            industry_tags = [
                normalize_whitespace(join_text(item)) for item in (job.get("organization", {}).get("industryTags") or [])
            ]
            industry_tags = [item for item in industry_tags if item]
            job_url = normalize_url_without_fragment(join_text(job.get("url")) or source.url)
            searchable_text = " ".join(
                part
                for part in [
                    title,
                    employer,
                    location,
                    work_mode,
                    seniority,
                    join_text(job.get("skills")),
                    join_text(job.get("organization", {}).get("topics")),
                    join_text(job.get("organization", {}).get("industryTags")),
                ]
                if part
            )
            matched_terms = sorted(set(match_terms(searchable_text, terms)))
            if not should_keep_candidate(title, matched_terms, searchable_text):
                continue

            note_parts = ["Enumerated through Getro collection search API"]
            if work_mode:
                note_parts.append(f"Work mode: {work_mode}")
            if seniority:
                note_parts.append(f"Seniority: {seniority}")
            if topics:
                note_parts.append(f"Topics: {', '.join(topics)}")
            if industry_tags:
                note_parts.append(f"Industries: {', '.join(industry_tags)}")

            merge_candidate(
                candidates_by_url,
                Candidate(
                    employer=employer,
                    title=title,
                    url=job_url,
                    source_url=source.url,
                    location=location,
                    remote=infer_remote_status(location, work_mode, title),
                    matched_terms=matched_terms,
                    notes="; ".join(note_parts),
                ),
            )

        if reported_total and len(raw_seen_ids) >= reported_total:
            reached_end = True
            break
        if observed_page_size and len(jobs) < observed_page_size:
            reached_end = True
            break

    if not reached_end and status == "complete":
        status = "partial"
        limitations.append(f"Getro collection search hit the page cap ({MAX_GETRO_PAGES}).")

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
        result_pages_scanned=f"collection={pages_scanned}p/{len(raw_seen_ids)}of{reported_total or len(raw_seen_ids)}",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_seen_ids),
        matched_jobs=len(candidates_by_url),
        limitations=deduped_limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_personio_page(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = fetch_text(source.url, timeout_seconds)
    jobs = extract_personio_jobs_from_html(html)
    if jobs is None:
        if "Derzeit keine offenen Positionen" in html or "No open positions" in html:
            jobs = []
        else:
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
                limitations=["Personio page did not expose a parseable jobs payload."],
                candidates=[],
            )

    candidates_by_url: dict[str, Candidate] = {}
    for job in jobs:
        title = normalize_whitespace(join_text(job.get("name") or job.get("title"))) or "unknown"
        location = normalize_whitespace(join_text(job.get("office") or job.get("location") or job.get("locations"))) or "unknown"
        searchable_text = " ".join(
            part
            for part in [
                title,
                location,
                join_text(job.get("department")),
                join_text(job.get("employmentType") or job.get("employment_type")),
                join_text(job),
            ]
            if part
        )
        matched_terms = sorted(set(match_terms(searchable_text, terms)))
        if not should_keep_candidate(title, matched_terms, searchable_text):
            continue
        job_url = normalize_url_without_fragment(join_text(job.get("url") or job.get("absoluteUrl") or source.url))
        merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=job_url,
                source_url=source.url,
                location=location,
                remote=infer_remote_status(location, searchable_text),
                matched_terms=matched_terms,
                notes="Enumerated through Personio page payload",
            ),
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
        result_pages_scanned=f"jobs={len(jobs)}",
        direct_job_pages_opened=0,
        enumerated_jobs=len(jobs),
        matched_jobs=len(candidates_by_url),
        limitations=[],
        candidates=list(candidates_by_url.values()),
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
    params: list[tuple[str, str | int]] = [("q", term)]
    params.extend(("location", location) for location in GOOGLE_LOCATION_FILTERS)
    if page_num > 1:
        params.append(("page", page_num))
    return f"{source.url}?{urlencode(params)}"


def meta_search_url(source: SourceConfig, term: str, page_num: int) -> str:
    del page_num
    base = urljoin(source.url.rstrip("/") + "/", "/jobsearch")
    return f"{base}?{urlencode({'q': term})}"


META_TASK_HEADINGS = (
    "Responsibilities",
    "What You'll Do",
    "What You Will Do",
)
META_MINIMUM_QUALIFICATION_HEADINGS = (
    "Minimum Qualifications",
    "Qualifications",
    "Requirements",
)
META_PREFERRED_QUALIFICATION_HEADINGS = ("Preferred Qualifications",)
META_DETAIL_STOP_HEADINGS = (
    *META_TASK_HEADINGS,
    *META_MINIMUM_QUALIFICATION_HEADINGS,
    *META_PREFERRED_QUALIFICATION_HEADINGS,
    "Locations",
    "About Meta",
    "About Us",
    "Team",
    "Job Interviews",
    "Culture",
    "Benefits",
    "Compensation",
    "Equal Employment Opportunity",
)
META_DETAIL_IGNORED_LINES = {
    "Apply to Job",
    "Save Job",
    "Share Job",
    "See all jobs",
    "Show more",
    "Read more",
}


def normalize_heading_line(value: str) -> str:
    return normalize_for_matching(re.sub(r":\s*$", "", normalize_whitespace(value)))


def extract_visible_text_section(text: str, headings: tuple[str, ...], stop_headings: tuple[str, ...]) -> str:
    lines = split_visible_lines(text)
    target_headings = {normalize_heading_line(heading) for heading in headings}
    stop_heading_set = {normalize_heading_line(heading) for heading in stop_headings}
    collected: list[str] = []
    collecting = False

    for line in lines:
        normalized_line = normalize_heading_line(line)
        if not collecting:
            if normalized_line in target_headings:
                collecting = True
            continue
        if normalized_line in stop_heading_set:
            break
        cleaned = normalize_whitespace(re.sub(r"^[•*\-\u2022]+\s*", "", line))
        if not cleaned or cleaned in META_DETAIL_IGNORED_LINES:
            continue
        collected.append(cleaned)

    return normalize_whitespace(" ".join(collected))


def extract_meta_detail_sections(detail_text: str) -> dict[str, str]:
    tasks = extract_visible_text_section(detail_text, META_TASK_HEADINGS, META_DETAIL_STOP_HEADINGS)
    minimum_qualifications = extract_visible_text_section(
        detail_text,
        META_MINIMUM_QUALIFICATION_HEADINGS,
        META_DETAIL_STOP_HEADINGS,
    )
    preferred_qualifications = extract_visible_text_section(
        detail_text,
        META_PREFERRED_QUALIFICATION_HEADINGS,
        META_DETAIL_STOP_HEADINGS,
    )
    qualifications = "; ".join(
        part for part in [minimum_qualifications, preferred_qualifications] if part
    )
    return {
        "tasks": tasks,
        "qualifications": qualifications,
    }


def apply_meta_detail_text(candidate: Candidate, detail_text: str, terms: list[str]) -> bool:
    sections = extract_meta_detail_sections(detail_text)
    detail_text_for_matching = " ".join(part for part in sections.values() if part)
    original_terms = list(candidate.matched_terms)
    if detail_text_for_matching:
        candidate.matched_terms = sorted(set(candidate.matched_terms + match_terms(detail_text_for_matching, terms)))

    original_notes = candidate.notes
    note_parts = [candidate.notes] if candidate.notes else []
    if sections["tasks"]:
        task_note = f"Tasks: {truncate_text(sections['tasks'], 260)}"
        if not candidate.notes or task_note not in candidate.notes:
            note_parts.append(task_note)
    if sections["qualifications"]:
        qualifications_note = f"Qualifications: {truncate_text(sections['qualifications'], 260)}"
        if not candidate.notes or qualifications_note not in candidate.notes:
            note_parts.append(qualifications_note)

    updated_notes = "; ".join(dict.fromkeys(part for part in note_parts if part))
    candidate.notes = updated_notes
    return candidate.notes != original_notes or candidate.matched_terms != original_terms


def enrich_meta_candidates(page: Any, candidates_by_url: dict[str, Candidate], terms: list[str], timeout_ms: int) -> BrowserEnrichmentResult:
    if not candidates_by_url:
        return BrowserEnrichmentResult()

    context = page.context
    browser_attr = getattr(context, "browser", None)
    browser = browser_attr() if callable(browser_attr) else browser_attr
    if browser is not None:
        detail_page = browser.new_page(viewport={"width": 1440, "height": 2200})
    else:
        detail_page = context.new_page()
    opened_pages = 0
    missing_detail_urls: list[str] = []

    try:
        for candidate in sorted(candidates_by_url.values(), key=lambda item: item.url):
            detail_page.goto(candidate.url, wait_until="domcontentloaded", timeout=timeout_ms)
            opened_pages += 1
            try:
                detail_page.wait_for_function(
                    """
                    () => {
                      const text = (document.body && document.body.innerText || '').toLowerCase();
                      return text.includes('responsibilities')
                        || text.includes('minimum qualifications')
                        || text.includes('preferred qualifications')
                        || text.includes('not logged in');
                    }
                    """,
                    timeout=5000,
                )
            except Exception:
                detail_page.wait_for_timeout(1000)
            detail_text = detail_page.locator("body").inner_text(timeout=5000)
            if not apply_meta_detail_text(candidate, detail_text, terms):
                missing_detail_urls.append(candidate.url)
    finally:
        detail_page.close()

    limitations: list[str] = []
    if missing_detail_urls:
        limitations.append(
            f"Meta detail page enrichment yielded no substantive role detail for {len(missing_detail_urls)} of {len(candidates_by_url)} matched roles"
        )

    return BrowserEnrichmentResult(
        direct_job_pages_opened=opened_pages,
        limitations=limitations,
    )


def google_public_job_url(source: SourceConfig, job_id: str, title: str) -> str:
    base = source.url.rstrip("/")
    if not job_id or job_id == "unknown":
        return base
    slug = slugify_title(title)
    if slug:
        return f"{base}/{job_id}-{slug}"
    return f"{base}/{job_id}"


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
        apply_url = join_text(job[2]) or ""
        url = google_public_job_url(source, job_id, title) or apply_url or source.url
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
                alternate_url=apply_url if apply_url and apply_url != url else "",
                location=location,
                matched_terms=matched_terms,
                notes=(
                    f"Google browser search q='{term}' locations={', '.join(GOOGLE_LOCATION_FILTERS)} "
                    f"page={page_num}; public overview URL synthesized from Google ds:1 payload"
                ),
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


def extract_meta_jobs(page: Any, source: SourceConfig, term: str, terms: list[str], page_num: int) -> BrowserPageResult:
    links = page.locator('a[href^="/profile/job_details/"]')
    visible_count = links.count()
    raw_ids: list[str] = []
    candidates: list[Candidate] = []
    seen_urls: set[str] = set()

    for index in range(visible_count):
        element = links.nth(index)
        href = element.get_attribute("href") or ""
        absolute_url = urljoin(source.url, href)
        if not href or absolute_url in seen_urls:
            continue
        seen_urls.add(absolute_url)
        raw_ids.append(absolute_url)

        lines = [line for line in split_visible_lines(element.inner_text()) if line != "⋅"]
        title = lines[0] if lines else "unknown"
        location = next((line for line in lines[1:] if "," in line or "Multiple Locations" in line), "unknown")
        searchable_text = " ".join(lines)
        matched_terms = sorted(set(match_terms(searchable_text, terms)))
        if not should_keep_candidate(title, matched_terms, searchable_text):
            continue

        candidates.append(
            Candidate(
                employer=source.source,
                title=title,
                url=absolute_url,
                source_url=source.url,
                location=location,
                matched_terms=matched_terms,
                notes=f"Meta browser search q='{term}' page={page_num}",
            )
        )

    page_signature = f"{term}:{page_num}:{len(raw_ids)}:{','.join(raw_ids[:10])}" if raw_ids else f"{term}:{page_num}:empty"
    limitations: list[str] = []
    if not raw_ids:
        limitations.append(f"Meta browser search for '{term}' showed no visible job cards")
    return BrowserPageResult(
        candidates=candidates,
        raw_ids=raw_ids,
        visible_results=len(raw_ids),
        declared_total=None,
        page_signature=page_signature,
        limitations=limitations,
    )


def extract_helsing_jobs(page: Any, source: SourceConfig, term: str, terms: list[str], page_num: int) -> BrowserPageResult:
    del term
    links = page.locator('a[href^="/jobs/"]')
    visible_count = links.count()
    raw_ids: list[str] = []
    candidates: list[Candidate] = []
    seen_urls: set[str] = set()

    for index in range(visible_count):
        element = links.nth(index)
        href = element.get_attribute("href") or ""
        absolute_url = normalize_url_without_fragment(urljoin(source.url, href))
        if not href or absolute_url in seen_urls:
            continue
        seen_urls.add(absolute_url)
        raw_ids.append(absolute_url)

        lines = split_visible_lines(element.inner_text())
        title = lines[0] if lines else "unknown"
        team = lines[1] if len(lines) > 1 else ""
        employment_type = lines[2] if len(lines) > 2 else ""
        location = lines[3] if len(lines) > 3 else "unknown"
        searchable_text = " ".join(part for part in [title, team, employment_type, location] if part)
        matched_terms = sorted(set(match_terms(searchable_text, terms)))
        if not should_keep_candidate(title, matched_terms, searchable_text):
            continue

        note = f"Helsing jobs page browser enumeration page={page_num}"
        if team:
            note = f"{note}; team={team}"
        candidates.append(
            Candidate(
                employer=source.source,
                title=title,
                url=absolute_url,
                source_url=source.url,
                location=location,
                matched_terms=matched_terms,
                notes=note,
            )
        )

    page_signature = ",".join(raw_ids[:10]) if raw_ids else f"helsing:{page_num}:empty"
    limitations: list[str] = []
    if not raw_ids:
        limitations.append("Helsing jobs page showed no visible job cards")
    return BrowserPageResult(
        candidates=candidates,
        raw_ids=raw_ids,
        visible_results=len(raw_ids),
        declared_total=None,
        page_signature=page_signature,
        limitations=limitations,
    )


def extract_asml_jobs(page: Any, source: SourceConfig, terms: list[str], page_num: int) -> BrowserPageResult:
    links = page.locator("a.search-results__item")
    visible_count = links.count()
    raw_ids: list[str] = []
    candidates: list[Candidate] = []
    seen_urls: set[str] = set()

    for index in range(visible_count):
        element = links.nth(index)
        href = element.get_attribute("href") or ""
        absolute_url = normalize_url_without_fragment(urljoin(source.url, href))
        if not href or absolute_url in seen_urls:
            continue
        seen_urls.add(absolute_url)
        raw_ids.append(absolute_url)

        try:
            title = element.locator("h2").first.inner_text().strip() or "unknown"
            field_items = element.locator("ul.search-results__fields li")
            location = field_items.nth(0).inner_text().strip() if field_items.count() > 0 else "unknown"
            team = field_items.nth(1).inner_text().strip() if field_items.count() > 1 else ""
        except Exception:
            lines = [line for line in split_visible_lines(element.inner_text()) if line]
            while lines and lines[0].upper() == "NEW":
                lines.pop(0)
            title = lines[0] if lines else "unknown"
            location = lines[1] if len(lines) > 1 else "unknown"
            team = lines[2] if len(lines) > 2 else ""
        searchable_text = " ".join(part for part in [title, location, team] if part)
        matched_terms = sorted(set(match_terms(searchable_text, terms)))
        if not should_keep_candidate(title, matched_terms, searchable_text):
            continue

        note = f"ASML browser enumeration page={page_num}"
        if team:
            note = f"{note}; team={team}"
        candidates.append(
            Candidate(
                employer=source.source,
                title=title,
                url=absolute_url,
                source_url=source.url,
                location=location,
                matched_terms=matched_terms,
                notes=note,
            )
        )

    page_signature = ",".join(raw_ids[:10]) if raw_ids else f"asml:{page_num}:empty"
    limitations: list[str] = []
    if not raw_ids:
        limitations.append(f"ASML browser page {page_num} showed no visible job cards")
    return BrowserPageResult(
        candidates=candidates,
        raw_ids=raw_ids,
        visible_results=len(raw_ids),
        declared_total=None,
        page_signature=page_signature,
        limitations=limitations,
    )


def dismiss_onetrust_banner(page: Any) -> None:
    def wait_for_results() -> None:
        try:
            page.wait_for_function(
                "() => document.querySelectorAll('a.search-results__item').length > 0",
                timeout=5000,
            )
        except Exception:
            page.wait_for_timeout(1000)

    reject_button = page.locator("#onetrust-reject-all-handler").first
    if reject_button.count():
        try:
            reject_button.click(timeout=3000)
            wait_for_results()
            return
        except Exception:
            pass
    accept_button = page.locator("#onetrust-accept-btn-handler").first
    if accept_button.count():
        try:
            accept_button.click(timeout=3000)
            wait_for_results()
            return
        except Exception:
            pass
    try:
        page.evaluate(
            """
            () => {
              const root = document.querySelector('#onetrust-consent-sdk');
              if (root) root.remove();
              document.querySelectorAll('.onetrust-pc-dark-filter').forEach((node) => node.remove());
            }
            """
        )
    except Exception:
        pass


def advance_meta_results(page: Any, source: SourceConfig, term: str, page_num: int) -> bool:
    del source, term, page_num
    button = page.get_by_role("button", name="Show more").first
    if not button.count():
        return False
    before_count = page.locator('a[href^="/profile/job_details/"]').count()
    button.scroll_into_view_if_needed(timeout=5000)
    button.click(timeout=5000)
    for _ in range(16):
        page.wait_for_timeout(500)
        after_count = page.locator('a[href^="/profile/job_details/"]').count()
        if after_count > before_count:
            return True
    return False


def advance_asml_results(page: Any, source: SourceConfig, page_num: int) -> bool:
    del source
    dismiss_onetrust_banner(page)
    next_button = page.locator('nav[aria-label="Pagination"] li.pagination-next button[role="link"]').first
    if not next_button.count():
        return False
    try:
        disabled = next_button.evaluate("(element) => Boolean(element.disabled)")
    except Exception:
        disabled = False
    if disabled:
        return False
    active_page = page.locator('nav[aria-label="Pagination"] li.pagination-link.active button[role="link"]').first
    current_page = active_page.inner_text().strip() if active_page.count() else ""
    current_first = ""
    first_card = page.locator("a.search-results__item").first
    if first_card.count():
        current_first = first_card.get_attribute("href") or ""
    next_button.click(timeout=5000)
    for _ in range(20):
        page.wait_for_timeout(500)
        active_page = page.locator('nav[aria-label="Pagination"] li.pagination-link.active button[role="link"]').first
        active_label = active_page.inner_text().strip() if active_page.count() else ""
        first_card = page.locator("a.search-results__item").first
        next_first = first_card.get_attribute("href") if first_card.count() else ""
        if active_label == str(page_num) and next_first != current_first:
            return True
        if current_page != active_label and active_label == str(page_num):
            return True
    return False


def discover_asml_browser(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return playwright_import_missing_coverage(source, terms, "ASML browser discovery is scaffolded but inactive")

    candidates_by_url: dict[str, Candidate] = {}
    raw_seen_ids: set[str] = set()
    limitations: list[str] = []
    pages_scanned = 0
    declared_total: int | None = None
    timeout_ms = max(timeout_seconds * 1000, DEFAULT_BROWSER_TIMEOUT_MS)
    max_pages = 30

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 2200})
            page.goto(source.url, wait_until="networkidle", timeout=timeout_ms)
            page.wait_for_timeout(1000)
            dismiss_onetrust_banner(page)
            count_label = page.locator(".pagination-results strong").first
            if count_label.count():
                count_text = re.sub(r"[^0-9]", "", count_label.inner_text())
                if count_text:
                    declared_total = int(count_text)

            page_num = 1
            while page_num <= max_pages:
                result = extract_asml_jobs(page, source, terms, page_num)
                pages_scanned += 1
                limitations.extend(result.limitations)
                for raw_id in result.raw_ids:
                    raw_seen_ids.add(raw_id)
                for candidate in result.candidates:
                    merge_candidate(candidates_by_url, candidate)
                if result.visible_results == 0:
                    break
                next_page_num = page_num + 1
                if next_page_num > max_pages:
                    limitations.append(f"ASML browser enumeration hit the page cap ({max_pages})")
                    break
                if not advance_asml_results(page, source, next_page_num):
                    break
                page_num = next_page_num
            browser.close()
    except Exception as exc:  # pragma: no cover - defensive output for live runs
        setup_issue = playwright_browsers_missing_coverage(source, terms, exc)
        if setup_issue is not None:
            return setup_issue
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
            limitations=[f"ASML browser discovery failed: {exc}"],
            candidates=[],
        )

    result_summary = (
        f"all_jobs={pages_scanned}p/{len(raw_seen_ids)}of{declared_total}"
        if declared_total is not None
        else f"all_jobs={pages_scanned}p/{len(raw_seen_ids)}"
    )
    status = "complete"
    if declared_total is not None and len(raw_seen_ids) < declared_total:
        status = "partial"
        limitations.append(f"ASML browser enumeration surfaced {len(raw_seen_ids)} of {declared_total} jobs")
    elif any("page cap" in limitation.lower() for limitation in limitations):
        status = "partial"

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
        result_pages_scanned=result_summary,
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_seen_ids),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
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


def discover_trailofbits_browser(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return playwright_import_missing_coverage(source, terms, "Trail of Bits browser discovery is unavailable")

    timeout_ms = max(timeout_seconds * 1000, DEFAULT_BROWSER_TIMEOUT_MS)
    raw_urls: set[str] = set()
    candidates_by_url: dict[str, Candidate] = {}

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 2200})
            page.goto(source.url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(2000)
            links = page.locator('a[href*="apply.workable.com"]')
            count = links.count()
            for index in range(count):
                element = links.nth(index)
                href = normalize_url_without_fragment(element.get_attribute("href") or "")
                if not href or href in raw_urls:
                    continue
                raw_urls.add(href)
                lines = split_visible_lines(element.inner_text())
                title = lines[0] if lines else "unknown"
                searchable_text = " ".join(lines) or title
                matched_terms = sorted(set(match_terms(searchable_text, terms)))
                if not should_keep_candidate(title, matched_terms, searchable_text):
                    continue
                merge_candidate(
                    candidates_by_url,
                    Candidate(
                        employer=source.source,
                        title=title,
                        url=href,
                        source_url=source.url,
                        matched_terms=matched_terms,
                        notes="Enumerated through Trail of Bits career-page Workable links",
                    ),
                )
            browser.close()
    except Exception as exc:  # pragma: no cover - defensive output for live runs
        setup_issue = playwright_browsers_missing_coverage(source, terms, exc)
        if setup_issue is not None:
            return setup_issue
        raise

    limitations = []
    if not raw_urls:
        limitations.append("No Workable job links were visible on the Trail of Bits careers page.")
    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="complete" if raw_urls else "partial",
        listing_pages_scanned=1,
        search_terms_tried=terms,
        result_pages_scanned="career_page=1",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_urls),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_automattic_browser(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return playwright_import_missing_coverage(source, terms, "Automattic browser discovery is unavailable")

    timeout_ms = max(timeout_seconds * 1000, DEFAULT_BROWSER_TIMEOUT_MS)
    raw_urls: set[str] = set()
    candidates_by_url: dict[str, Candidate] = {}

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 2200})
            page.goto(source.url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(2000)
            links = page.locator('a[href*="/work-with-us/job/"]')
            count = links.count()
            for index in range(count):
                element = links.nth(index)
                href = normalize_url_without_fragment(element.get_attribute("href") or "")
                if not href or href in raw_urls:
                    continue
                raw_urls.add(href)
                lines = split_visible_lines(element.inner_text())
                title = lines[0] if lines else "unknown"
                searchable_text = " ".join(lines) or title
                matched_terms = sorted(set(match_terms(searchable_text, terms)))
                if not should_keep_candidate(title, matched_terms, searchable_text):
                    continue
                merge_candidate(
                    candidates_by_url,
                    Candidate(
                        employer=source.source,
                        title=title,
                        url=href,
                        source_url=source.url,
                        matched_terms=matched_terms,
                        notes="Enumerated through Automattic jobs-page cards",
                    ),
                )
            browser.close()
    except Exception as exc:  # pragma: no cover - defensive output for live runs
        setup_issue = playwright_browsers_missing_coverage(source, terms, exc)
        if setup_issue is not None:
            return setup_issue
        raise

    limitations = []
    if not raw_urls:
        limitations.append("No Automattic job-detail links were visible on the jobs page.")
    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="complete" if raw_urls else "partial",
        listing_pages_scanned=1,
        search_terms_tried=terms,
        result_pages_scanned="jobs_page=1",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_urls),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_coinbase_browser(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return playwright_import_missing_coverage(source, terms, "Coinbase browser discovery is unavailable")

    timeout_ms = max(timeout_seconds * 1000, DEFAULT_BROWSER_TIMEOUT_MS)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 2200})
            page.goto(source.url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(10000)
            title = page.title()
            body_text = normalize_whitespace(page.locator("body").inner_text())
            browser.close()
    except Exception as exc:  # pragma: no cover - defensive output for live runs
        setup_issue = playwright_browsers_missing_coverage(source, terms, exc)
        if setup_issue is not None:
            return setup_issue
        raise

    if "performing security verification" in body_text.lower() or title.lower() == "just a moment...":
        return Coverage(
            source=source.source,
            source_url=source.url,
            discovery_mode=source.discovery_mode,
            cadence_group=source.cadence_group,
            last_checked=source.last_checked,
            due_today=False,
            status="partial",
            listing_pages_scanned=1,
            search_terms_tried=terms,
            result_pages_scanned="challenge_page=1",
            direct_job_pages_opened=0,
            enumerated_jobs=0,
            matched_jobs=0,
            limitations=["Cloudflare challenge blocked automated access to Coinbase careers listings."],
            candidates=[],
        )

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="partial",
        listing_pages_scanned=1,
        search_terms_tried=terms,
        result_pages_scanned="browser_probe=1",
        direct_job_pages_opened=0,
        enumerated_jobs=0,
        matched_jobs=0,
        limitations=["Coinbase careers loaded, but no deterministic job-listing extraction path is implemented yet."],
        candidates=[],
    )


def discover_thales_browser(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return playwright_import_missing_coverage(source, terms, "Thales browser discovery is unavailable")

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
    try:
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
    except Exception as exc:  # pragma: no cover - defensive output for live runs
        setup_issue = playwright_browsers_missing_coverage(source, terms, exc)
        if setup_issue is not None:
            return setup_issue
        raise

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


def discover_helsing_browser(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return playwright_import_missing_coverage(source, terms, "Helsing browser discovery is unavailable")

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 2200})
            page.goto(source.url, wait_until="domcontentloaded", timeout=max(timeout_seconds * 1000, DEFAULT_BROWSER_TIMEOUT_MS))
            page.wait_for_timeout(3000)
            result = extract_helsing_jobs(page, source, "catalog", terms, 1)
            browser.close()
    except Exception as exc:  # pragma: no cover - defensive output for live runs
        setup_issue = playwright_browsers_missing_coverage(source, terms, exc)
        if setup_issue is not None:
            return setup_issue
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
            limitations=[f"Helsing browser discovery failed: {type(exc).__name__}: {exc}"],
            candidates=[],
        )

    status = "complete" if result.raw_ids else "partial"
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
        result_pages_scanned="catalog=1",
        direct_job_pages_opened=0,
        enumerated_jobs=len(result.raw_ids),
        matched_jobs=len(result.candidates),
        limitations=result.limitations,
        candidates=result.candidates,
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
        override_terms=("cryptography",),
        supports_pagination=True,
        page_size=GOOGLE_RESULTS_PAGE_SIZE,
        max_pages=MAX_BROWSER_PAGES,
    ),
    "Meta": BrowserStrategy(
        search_url_builder=meta_search_url,
        extract_page=extract_meta_jobs,
        advance_page=advance_meta_results,
        enrich_candidates=enrich_meta_candidates,
        supports_pagination=True,
        cumulative_results=True,
        max_pages=10,
    ),
}


def discover_browser(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return playwright_import_missing_coverage(source, terms, "browser-mode discovery is scaffolded but inactive")
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
    effective_terms = list(strategy.override_terms) if strategy.override_terms else terms
    direct_job_pages_opened = 0

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 2200})
            timeout_ms = max(timeout_seconds * 1000, DEFAULT_BROWSER_TIMEOUT_MS)
            for term in effective_terms:
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
            if strategy.enrich_candidates:
                enrichment = strategy.enrich_candidates(page, candidates_by_url, terms, timeout_ms)
                direct_job_pages_opened += enrichment.direct_job_pages_opened
                if enrichment.limitations:
                    limitations.extend(enrichment.limitations)
            browser.close()
    except Exception as exc:  # pragma: no cover - defensive output for live runs
        setup_issue = playwright_browsers_missing_coverage(source, effective_terms, exc)
        if setup_issue is not None:
            return setup_issue
        return Coverage(
            source=source.source,
            source_url=source.url,
            discovery_mode=source.discovery_mode,
            cadence_group=source.cadence_group,
            last_checked=source.last_checked,
            due_today=False,
            status="partial",
            listing_pages_scanned="unknown",
            search_terms_tried=effective_terms,
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
        search_terms_tried=effective_terms,
        result_pages_scanned=", ".join(result_summaries) if result_summaries else "none",
        direct_job_pages_opened=direct_job_pages_opened,
        enumerated_jobs=len(raw_seen_ids),
        matched_jobs=len(candidates_by_url),
        limitations=deduped_limitations,
        candidates=list(candidates_by_url.values()),
    )


DISCOVERY_HANDLERS = {
    "ashby_api": discover_ashby_api,
    "automattic_browser": discover_automattic_browser,
    "asml_browser": discover_asml_browser,
    "auswaertiges_amt_json": discover_auswaertiges_amt_json,
    "bnd_career_search": discover_bnd_career_search,
    "bosch_autocomplete": discover_bosch_autocomplete,
    "bundeswehr_jobsuche": discover_bundeswehr_jobsuche,
    "coinbase_browser": discover_coinbase_browser,
    "cybernetica_teamdash": discover_cybernetica_teamdash,
    "enbw_phenom": discover_enbw_phenom,
    "helsing_browser": discover_helsing_browser,
    "html": discover_html,
    "hackernews_jobs": discover_hackernews_jobs,
    "iacr_jobs": discover_iacr_jobs,
    "ibm_api": discover_ibm_api,
    "infineon_api": discover_infineon_api,
    "icims_html": discover_html,
    "leastauthority_careers": discover_leastauthority_careers,
    "lever_json": discover_lever_json,
    "greenhouse_api": discover_greenhouse_api,
    "getro_api": discover_getro_api,
    "ashby_html": discover_ashby_api,
    "hackernews_whoishiring_api": discover_hackernews_whoishiring_api,
    "neclab_jobs": discover_neclab_jobs,
    "partisia_site": discover_partisia_site,
    "pcd_team": discover_pcd_team,
    "personio_page": discover_personio_page,
    "qedit_inline": discover_qedit_inline,
    "qusecure_careers": discover_qusecure_careers,
    "recruitee_inline": discover_recruitee_inline,
    "rheinmetall_html": discover_rheinmetall_html,
    "service_bund_links": discover_service_bund_links,
    "service_bund_search": discover_service_bund_search,
    "secunet_jobboard": discover_secunet_jobboard,
    "thales_browser": discover_thales_browser,
    "thales_html": discover_thales_html,
    "trailofbits_browser": discover_trailofbits_browser,
    "verfassungsschutz_rss": discover_verfassungsschutz_rss,
    "workable_api": discover_workable_api,
    "workday_api": discover_workday_api,
    "yc_jobs_board": discover_yc_jobs_board,
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


def source_to_dict(source: SourceConfig, today: date, track_terms: list[str], source_term_map: dict[str, SourceTermRule]) -> dict[str, Any]:
    terms = normalize_terms(track_terms, source_term_map.get(source.source))
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
        total_sources = len(sources)
        for index, source in enumerate(sources, start=1):
            terms = normalize_terms(track_terms, source_term_map.get(source.source))
            emit_progress(
                args.progress,
                f"Discovering source {index}/{total_sources}: {source.source} (mode={source.discovery_mode})",
            )
            coverage = discover_source(source, terms, args.timeout_seconds)
            coverage = filter_coverage_for_track(args.track, coverage)
            coverage.due_today = source_due_today(source, today)
            emit_progress(
                args.progress,
                (
                    f"Completed source {index}/{total_sources}: {source.source} "
                    f"(status={coverage.status}, matched={coverage.matched_jobs}, candidates={len(coverage.candidates)})"
                ),
            )
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
