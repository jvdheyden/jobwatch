"""service.bund.de provider.

Supported discovery modes:
- `service_bund_search`
- `service_bund_links`
"""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse

from discover import helpers, http
from discover.constants import NON_TECHNICAL_TITLE_HINTS
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


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
SERVICE_BUND_DETAIL_PATH_MARKER = "IMPORTE/Stellenangebote"
SERVICE_BUND_LOCATION_LABELS = ("Ort", "Dienstort", "Arbeitsort")
SERVICE_BUND_COMPENSATION_HEADINGS = (
    "Entgelt",
    "Vergütung",
    "Bezahlung",
    "Besoldung",
    "Besoldung / Entgelt",
    "Besoldungs-/Entgeltgruppe",
    "Entgeltgruppe",
    "Laufbahn / Entgeltgruppe",
    "DAS IST FINANZIELL FÜR DICH DRIN",
)
SERVICE_BUND_TASK_HEADINGS = (
    "Tätigkeitsprofil",
    "Aufgaben",
    "Ihre Aufgaben",
    "Ihr Aufgabenbereich",
    "Aufgabengebiet",
    "Das Aufgabengebiet",
    "Was sind Ihre Aufgabenschwerpunkte?",
    "DEINE AUFGABEN SIND U. A.",
)
SERVICE_BUND_QUALIFICATION_HEADINGS = (
    "Anforderungsprofil",
    "Ihr Profil",
    "Ihr Anforderungsprofil",
    "Voraussetzungen",
    "Qualifikationserfordernisse",
    "Fachliche Anforderungen",
    "Persönliche Anforderungen",
    "Was erwarten wir von Ihnen?",
    "Was bringen Sie mit?",
    "DIESE QUALIFIKATIONEN SIND EIN MUSS",
    "VON VORTEIL SIND",
)
SERVICE_BUND_DETAIL_STOP_HEADINGS = (
    *SERVICE_BUND_COMPENSATION_HEADINGS,
    *SERVICE_BUND_TASK_HEADINGS,
    *SERVICE_BUND_QUALIFICATION_HEADINGS,
    "Arbeitgeber",
    "Ort",
    "Dienstort",
    "Arbeitsort",
    "Stellenangebot",
    "Bewerbung",
    "Bewerbungsfrist",
    "Hinweise",
    "Kontakt",
    "Wir bieten",
    "Unser Angebot",
    "Weitere Informationen",
    "DARUM LOHNT SICH DEINE BEWERBUNG",
    "DEIN START BEI ZITIS",
    "SO GEHT ES WEITER",
    "Deine Ansprechpartnerin",
)


def clean_service_bund_text(value: str) -> str:
    cleaned = helpers.strip_html_fragment(value).replace("\u00ad", "")
    return helpers.normalize_whitespace(cleaned)


def normalize_service_bund_job_url(base_url: str, href: str) -> str:
    raw_href = unescape(href).strip()
    marker_index = raw_href.lower().find(SERVICE_BUND_DETAIL_PATH_MARKER.lower())
    if marker_index < 0:
        return helpers.normalize_url_without_fragment(urljoin(base_url, raw_href))

    parsed_base = urlparse(raw_href)
    if not parsed_base.scheme or not parsed_base.netloc:
        parsed_base = urlparse(base_url)

    detail_part = raw_href[marker_index:]
    parsed_detail = urlparse(f"/{detail_part.lstrip('/')}")
    canonical = parsed_base._replace(
        path=parsed_detail.path,
        params="",
        query="",
        fragment="",
    ).geturl()
    return helpers.normalize_url_without_fragment(canonical)


def _detail_lines(detail_html: str) -> list[str]:
    return [
        clean_service_bund_text(line)
        for line in helpers.extract_visible_text_lines_from_html(detail_html)
        if clean_service_bund_text(line)
    ]


def _detail_value_after_label(lines: list[str], labels: tuple[str, ...]) -> str:
    normalized_labels = {helpers.normalize_heading_line(label) for label in labels}
    normalized_label_prefixes = [
        helpers.normalize_for_matching(re.sub(r"\W+", " ", label)).strip() for label in labels
    ]
    for index, line in enumerate(lines):
        normalized_line = helpers.normalize_heading_line(line)
        if normalized_line in normalized_labels:
            for next_line in lines[index + 1 :]:
                if helpers.normalize_heading_line(next_line) not in normalized_labels:
                    return next_line
            return ""
        for label, normalized_prefix in zip(labels, normalized_label_prefixes, strict=True):
            inline_match = re.match(rf"^{re.escape(label)}\s*[:\-]?\s+(.+)$", line, flags=re.IGNORECASE)
            if inline_match:
                return clean_service_bund_text(inline_match.group(1))
            normalized_spaced_line = helpers.normalize_for_matching(re.sub(r"\W+", " ", line)).strip()
            if normalized_prefix and normalized_spaced_line.startswith(f"{normalized_prefix} "):
                return clean_service_bund_text(line[len(label) :].lstrip(" :-"))
    return ""


def extract_service_bund_detail_sections(detail_html: str) -> dict[str, str]:
    lines = _detail_lines(detail_html)
    detail_text = "\n".join(lines)
    compensation = _detail_value_after_label(lines, SERVICE_BUND_COMPENSATION_HEADINGS)
    if not compensation:
        compensation = helpers.extract_visible_text_section(
            detail_text,
            SERVICE_BUND_COMPENSATION_HEADINGS,
            SERVICE_BUND_DETAIL_STOP_HEADINGS,
        )
    return {
        "location": _detail_value_after_label(lines, SERVICE_BUND_LOCATION_LABELS),
        "tasks": helpers.extract_visible_text_section(
            detail_text,
            SERVICE_BUND_TASK_HEADINGS,
            SERVICE_BUND_DETAIL_STOP_HEADINGS,
        ),
        "qualifications": helpers.extract_visible_text_section(
            detail_text,
            SERVICE_BUND_QUALIFICATION_HEADINGS,
            SERVICE_BUND_DETAIL_STOP_HEADINGS,
        ),
        "compensation": compensation,
    }


def apply_service_bund_detail_text(candidate: Candidate, detail_html: str, terms: list[str]) -> bool:
    sections = extract_service_bund_detail_sections(detail_html)
    detail_text_for_matching = " ".join(part for part in sections.values() if part)

    original_location = candidate.location
    original_remote = candidate.remote
    original_terms = list(candidate.matched_terms)
    original_notes = candidate.notes

    if sections["location"]:
        candidate.location = sections["location"]
    if candidate.remote == "unknown":
        candidate.remote = helpers.infer_remote_status(candidate.location, detail_text_for_matching, candidate.title)
    if detail_text_for_matching:
        candidate.matched_terms = sorted(set(candidate.matched_terms + helpers.match_terms(detail_text_for_matching, terms)))

    note_parts = [candidate.notes] if candidate.notes else []
    for label, key, limit in (
        ("Tasks", "tasks", 260),
        ("Qualifications", "qualifications", 260),
        ("Compensation", "compensation", 180),
    ):
        value = sections[key]
        if not value:
            continue
        note_parts.append(f"{label}: {helpers.truncate_text(value, limit)}")
    candidate.notes = "; ".join(dict.fromkeys(part for part in note_parts if part))
    return (
        candidate.location != original_location
        or candidate.remote != original_remote
        or candidate.matched_terms != original_terms
        or candidate.notes != original_notes
    )


def should_keep_service_bund_candidate(
    title: str,
    matched_terms: list[str],
    searchable_text: str,
    *,
    allow_curated_without_term: bool = False,
) -> bool:
    if helpers.should_keep_candidate(title, matched_terms, searchable_text):
        return True
    if any(token in title.lower() for token in NON_TECHNICAL_TITLE_HINTS):
        return False
    haystack = helpers.normalize_for_matching(searchable_text)
    has_public_interest_tech_hint = any(token in haystack for token in SERVICE_BUND_PUBLIC_INTEREST_HINTS)
    normalized_terms = {helpers.normalize_for_matching(term) for term in matched_terms}
    if normalized_terms == {"referent"}:
        return has_public_interest_tech_hint
    if normalized_terms:
        return has_public_interest_tech_hint
    return allow_curated_without_term and has_public_interest_tech_hint


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
            html = http.fetch_text(build_service_bund_search_url(source.url, term, gtp), timeout_seconds)
            listing_pages_scanned += 1

            page_matches = list(SERVICE_BUND_RESULT_RE.finditer(html))
            term_raw_count += len(page_matches)
            for match in page_matches:
                absolute_url = normalize_service_bund_job_url(source.url, match.group("href"))
                raw_seen_ids.add(absolute_url)
                title = clean_service_bund_text(match.group("title")) or "unknown"
                title = re.sub(r"^Stellenbezeichnung\s*", "", title, flags=re.IGNORECASE).strip() or "unknown"
                employer = clean_service_bund_text(match.group("employer")) or source.source
                posted = clean_service_bund_text(match.group("posted"))
                deadline = clean_service_bund_text(match.group("deadline"))
                searchable_text = " ".join(part for part in [title, employer, posted, deadline, absolute_url, term] if part)
                matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
                if not should_keep_service_bund_candidate(title, matched_terms, searchable_text):
                    continue
                notes = "service.bund native search"
                if posted:
                    notes = f"{notes}; posted={posted}"
                if deadline:
                    notes = f"{notes}; deadline={deadline}"
                helpers.merge_candidate(
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

    detail_pages_opened = 0
    detail_failures = 0
    for candidate in candidates_by_url.values():
        try:
            detail_html = http.fetch_text(candidate.url, timeout_seconds)
        except Exception as exc:
            detail_failures += 1
            if len(limitations) < 3:
                limitations.append(f"Could not read service.bund detail page {candidate.url}: {type(exc).__name__}: {exc}")
            continue
        detail_pages_opened += 1
        apply_service_bund_detail_text(candidate, detail_html, terms)

    if detail_failures > 3:
        limitations.append(f"{detail_failures - 3} additional service.bund detail pages could not be read.")

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
        direct_job_pages_opened=detail_pages_opened,
        enumerated_jobs=len(raw_seen_ids),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_service_bund_links(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = http.fetch_text(source.url, timeout_seconds)
    candidates_by_url: dict[str, Candidate] = {}
    raw_urls: set[str] = set()

    for match in SERVICE_BUND_DIRECT_LINK_RE.finditer(html):
        absolute_url = normalize_service_bund_job_url(source.url, match.group("href"))
        raw_urls.add(absolute_url)
        title = helpers.strip_html_fragment(match.group("text")) or "unknown"
        searchable_text = " ".join(part for part in [title, source.source, absolute_url] if part)
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not should_keep_service_bund_candidate(
            title,
            matched_terms,
            searchable_text,
            allow_curated_without_term=True,
        ):
            continue
        helpers.merge_candidate(
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


SOURCES = [
    SourceAdapter(modes=("service_bund_search",), discover=discover_service_bund_search),
    SourceAdapter(modes=("service_bund_links",), discover=discover_service_bund_links),
]
