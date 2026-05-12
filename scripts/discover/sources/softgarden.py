"""Softgarden static vacancy-page provider.

Supported discovery modes:
- `softgarden_html`

Expected source URL shape:
- `https://<tenant>.softgarden.io/<language>/vacancies`

Supported source filters:
- `jobcategory`
- `location`
- `company`
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import urljoin, urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


SOFTGARDEN_CARD_RE = re.compile(r'<div class="matchElement" id="job_id_(?P<id>\d+)">', flags=re.IGNORECASE)
SOFTGARDEN_LINK_RE = re.compile(r'<a\s+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>', flags=re.DOTALL | re.IGNORECASE)
SOFTGARDEN_CATEGORY_RE = re.compile(
    r'<div class="matchValue jobcategory">(?P<category>.*?)</div>',
    flags=re.DOTALL | re.IGNORECASE,
)
SOFTGARDEN_LOCATION_RE = re.compile(
    r'<span class="location-view-item">(?P<location>.*?)</span>',
    flags=re.DOTALL | re.IGNORECASE,
)
SOFTGARDEN_COMPANY_RE = re.compile(
    r'<div class="matchValue sg_company_id">(?P<company>.*?)</div>',
    flags=re.DOTALL | re.IGNORECASE,
)

SOFTGARDEN_TASK_HEADINGS = (
    "Ihr Aufgabenbereich",
    "Ihre Aufgaben",
    "Deine Aufgaben",
    "Aufgaben",
    "Your tasks",
    "Your responsibilities",
    "Responsibilities",
)
SOFTGARDEN_PROFILE_HEADINGS = (
    "Ihr Profil",
    "Dein Profil",
    "Anforderungen",
    "Qualifikationen",
    "Your profile",
    "Your qualifications",
    "Requirements",
    "Qualifications",
)
SOFTGARDEN_BENEFIT_HEADINGS = (
    "Ihre Vorteile",
    "Deine Vorteile",
    "Wir bieten",
    "Benefits",
    "Your benefits",
)
SOFTGARDEN_STOP_HEADINGS = (
    *SOFTGARDEN_TASK_HEADINGS,
    *SOFTGARDEN_PROFILE_HEADINGS,
    *SOFTGARDEN_BENEFIT_HEADINGS,
    "Jetzt bewerben",
    "Apply now",
    "Die Bundesdruckerei-Gruppe",
    "Bundesdruckerei GmbH",
    "Impressum",
    "Datenschutz",
)
SOFTGARDEN_RELEVANT_TITLE_MARKERS = (
    "security",
    "cyber",
    "devsecops",
    "sina",
    "kritischer infrastruktur",
    "hochsichere",
    "requirements engineer",
    "consultant",
    "operator",
)


@dataclass(frozen=True)
class SoftgardenJobCard:
    job_id: str
    title: str
    url: str
    category: str
    location: str
    company: str


def _strip(value: str) -> str:
    return helpers.normalize_whitespace(helpers.strip_html_fragment(value))


def _filter_values(source: SourceConfig, key: str) -> set[str]:
    return {helpers.normalize_for_matching(value) for value in source.filters.get(key, []) if value.strip()}


def _matches_configured_filters(card: SoftgardenJobCard, source: SourceConfig) -> bool:
    filters = {
        "jobcategory": card.category,
        "location": card.location,
        "company": card.company,
    }
    for key, raw_value in filters.items():
        allowed = _filter_values(source, key)
        if not allowed:
            continue
        normalized = helpers.normalize_for_matching(raw_value)
        if not any(value in normalized for value in allowed):
            return False
    return True


def extract_softgarden_job_cards(html: str, source_url: str) -> list[SoftgardenJobCard]:
    starts = list(SOFTGARDEN_CARD_RE.finditer(html))
    cards: list[SoftgardenJobCard] = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(html)
        body = html[match.start() : end]
        link_match = SOFTGARDEN_LINK_RE.search(body)
        if not link_match:
            continue
        href = unescape(link_match.group("href"))
        absolute_url = helpers.normalize_url_without_fragment(urljoin(source_url, href))
        if urlparse(absolute_url).scheme not in {"http", "https"}:
            continue
        category_match = SOFTGARDEN_CATEGORY_RE.search(body)
        company_match = SOFTGARDEN_COMPANY_RE.search(body)
        locations = [_strip(location.group("location")) for location in SOFTGARDEN_LOCATION_RE.finditer(body)]
        cards.append(
            SoftgardenJobCard(
                job_id=match.group("id"),
                title=_strip(link_match.group("title")) or "unknown",
                url=absolute_url,
                category=_strip(category_match.group("category")) if category_match else "unknown",
                location=", ".join(dict.fromkeys(location for location in locations if location)) or "unknown",
                company=_strip(company_match.group("company")) if company_match else "",
            )
        )
    return cards


def extract_softgarden_detail_sections(detail_html: str) -> dict[str, str]:
    detail_text = "\n".join(helpers.extract_visible_text_lines_from_html(detail_html))
    return {
        "tasks": helpers.extract_visible_text_section(
            detail_text,
            SOFTGARDEN_TASK_HEADINGS,
            SOFTGARDEN_STOP_HEADINGS,
        ),
        "qualifications": helpers.extract_visible_text_section(
            detail_text,
            SOFTGARDEN_PROFILE_HEADINGS,
            SOFTGARDEN_STOP_HEADINGS,
        ),
        "benefits": helpers.extract_visible_text_section(
            detail_text,
            SOFTGARDEN_BENEFIT_HEADINGS,
            SOFTGARDEN_STOP_HEADINGS,
        ),
    }


def apply_softgarden_detail_text(candidate: Candidate, detail_html: str, terms: list[str]) -> bool:
    sections = extract_softgarden_detail_sections(detail_html)
    detail_text_for_matching = " ".join(part for part in sections.values() if part)
    original_terms = list(candidate.matched_terms)
    if detail_text_for_matching:
        candidate.matched_terms = sorted(set(candidate.matched_terms + helpers.match_terms(detail_text_for_matching, terms)))

    original_notes = candidate.notes
    note_parts = [candidate.notes] if candidate.notes else []
    if sections["tasks"]:
        note_parts.append(f"Tasks: {helpers.truncate_text(sections['tasks'], 260)}")
    if sections["qualifications"]:
        note_parts.append(f"Qualifications: {helpers.truncate_text(sections['qualifications'], 260)}")
    if sections["benefits"]:
        note_parts.append(f"Benefits: {helpers.truncate_text(sections['benefits'], 180)}")
    candidate.notes = "; ".join(dict.fromkeys(part for part in note_parts if part))
    return candidate.notes != original_notes or candidate.matched_terms != original_terms


def _should_keep_softgarden_card(card: SoftgardenJobCard, matched_terms: list[str], searchable_text: str) -> bool:
    if helpers.should_keep_candidate(card.title, matched_terms, searchable_text):
        return True
    if not matched_terms:
        return False
    title_and_category = helpers.normalize_for_matching(f"{card.title} {card.category}")
    return any(marker in title_and_category for marker in SOFTGARDEN_RELEVANT_TITLE_MARKERS)


def discover_softgarden_html(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = http.fetch_text(source.url, timeout_seconds)
    cards = extract_softgarden_job_cards(html, source.url)
    candidates_by_url: dict[str, Candidate] = {}

    for card in cards:
        if not _matches_configured_filters(card, source):
            continue
        searchable_text = " ".join(
            part for part in [card.title, card.category, card.location, card.company, card.url] if part
        )
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not _should_keep_softgarden_card(card, matched_terms, searchable_text):
            continue
        notes = "Enumerated through Softgarden vacancy board"
        if card.category and card.category != "unknown":
            notes = f"{notes}; Category: {card.category}"
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
                notes=notes,
            ),
        )

    limitations: list[str] = []
    detail_pages_opened = 0
    detail_failures = 0
    for candidate in candidates_by_url.values():
        try:
            detail_html = http.fetch_text(candidate.url, timeout_seconds)
        except Exception as exc:
            detail_failures += 1
            if len(limitations) < 3:
                limitations.append(f"Could not read Softgarden detail page {candidate.url}: {type(exc).__name__}: {exc}")
            continue
        detail_pages_opened += 1
        apply_softgarden_detail_text(candidate, detail_html, terms)

    if cards and not candidates_by_url:
        limitations.append("Softgarden vacancy page exposed job cards, but none matched the configured track terms.")
    if detail_failures > 3:
        limitations.append(f"{detail_failures - 3} additional Softgarden detail pages could not be read.")

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="partial" if detail_failures else "complete",
        listing_pages_scanned=1,
        search_terms_tried=terms,
        result_pages_scanned=f"job_cards={len(cards)}",
        direct_job_pages_opened=detail_pages_opened,
        enumerated_jobs=len(cards),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("softgarden_html",), discover=discover_softgarden_html)
