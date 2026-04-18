"""Bundeswehr public jobsuche and SAP OData provider."""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse

from sap_odata import (
    fetch_sap_odata_all,
    fetch_sap_odata_entity,
    sap_odata_string_literal,
)

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter
from discover.sources.service_bund import should_keep_service_bund_candidate


BUNDESWEHR_JOBSUCHE_URL = "https://www.bundeswehrkarriere.de/entdecker/jobs/jobsuche"
BUNDESWEHR_ODATA_SERVICE_ROOT = "https://bewerbung.bundeswehr-karriere.de/erece/unreg/"
BUNDESWEHR_ODATA_ENTITY_SET = "Stellensuche_Set"
BUNDESWEHR_ODATA_LANGUAGE = "D"
BUNDESWEHR_ODATA_PAGE_SIZE = 100
BUNDESWEHR_ODATA_OPPORTUNITY_CATEGORIES = ("0021", "0026", "0022", "0027", "0023", "0028")
BUNDESWEHR_ODATA_LIST_SELECT = (
    "Arbeitszeit",
    "ApplicationEnd",
    "BesOrt",
    "Country",
    "ContractType",
    "Distance",
    "HotJob",
    "Langu",
    "NewJob",
    "PinstGuid",
    "PostingAge",
    "PostingTxt",
    "RefCode",
    "Region",
    "SearchCategory",
    "Title",
    "Tarifgruppe1",
    "Tarifgruppe2",
)
BUNDESWEHR_ODATA_DETAIL_SELECT = (
    "Arbeitszeit",
    "ApplicationEnd",
    "BesOrt",
    "ContractType",
    "PinstGuid",
    "RemarcDesc",
    "ContactDesc",
    "CompanyDesc",
    "JobDesc",
    "RequireDesc",
    "StartDate",
    "EndDate",
    "EmployeeFract",
    "SearchCategory",
    "ReqType",
    "RefCode",
    "Title",
    "Tarifgruppe1",
    "Tarifgruppe2",
    "NumberOfJobs",
)
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
BUNDESWEHR_JOB_TITLE_RE = re.compile(
    r'<a class="jobtitle" href="(?P<href>[^"]+)">(?P<title>.*?)</a>',
    flags=re.DOTALL | re.IGNORECASE,
)


def build_bundeswehr_portal_candidate_url(source_url: str, detail_url: str) -> str:
    parsed_source = urlparse(source_url)
    detail_slug = Path(urlparse(detail_url).path).name
    query_pairs = [(key, value) for key, value in parse_qsl(parsed_source.query, keep_blank_values=True) if key != "job"]
    if detail_slug:
        query_pairs.append(("job", detail_slug))
    return helpers.normalize_url_without_fragment(parsed_source._replace(query=urlencode(query_pairs), fragment="").geturl())


def build_bundeswehr_odata_candidate_url(source_url: str, pinst_guid: str) -> str:
    parsed_source = urlparse(source_url)
    query_pairs = [(key, value) for key, value in parse_qsl(parsed_source.query, keep_blank_values=True) if key != "job"]
    if pinst_guid:
        query_pairs.append(("job", pinst_guid))
    return helpers.normalize_url_without_fragment(parsed_source._replace(query=urlencode(query_pairs), fragment="").geturl())


def extract_bundeswehr_detail_sections(detail_html: str) -> dict[str, str]:
    detail_text = "\n".join(helpers.extract_visible_text_lines_from_html(detail_html))
    tasks = helpers.extract_visible_text_section(
        detail_text,
        BUNDESWEHR_TASK_HEADINGS,
        BUNDESWEHR_DETAIL_STOP_HEADINGS,
    )
    qualifications = helpers.extract_visible_text_section(
        detail_text,
        BUNDESWEHR_QUALIFICATION_HEADINGS,
        BUNDESWEHR_DETAIL_STOP_HEADINGS,
    )
    compensation = helpers.extract_visible_text_section(
        detail_text,
        BUNDESWEHR_COMPENSATION_HEADINGS,
        BUNDESWEHR_DETAIL_STOP_HEADINGS,
    )
    if not compensation:
        compensation = helpers.extract_visible_text_marker_snippet(
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
        candidate.matched_terms = sorted(set(candidate.matched_terms + helpers.match_terms(detail_text_for_matching, terms)))

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
        detail_note = f"{label}: {helpers.truncate_text(value, 260)}"
        if detail_note not in note_parts:
            note_parts.append(detail_note)
    candidate.notes = "; ".join(dict.fromkeys(part for part in note_parts if part))
    return candidate.notes != original_notes or candidate.matched_terms != original_terms


def bundeswehr_odata_filter_for_category(category: str) -> str:
    return (
        f"(SearchCategory eq {sap_odata_string_literal(category)} "
        f"and Langu eq {sap_odata_string_literal(BUNDESWEHR_ODATA_LANGUAGE)})"
    )


def bundeswehr_odata_category_filter_clause(categories: tuple[str, ...] = BUNDESWEHR_ODATA_OPPORTUNITY_CATEGORIES) -> str:
    return "(" + " or ".join(f"SearchCategory eq {sap_odata_string_literal(category)}" for category in categories) + ")"


def bundeswehr_odata_filter_for_keyword(term: str) -> str:
    return (
        f"({bundeswehr_odata_category_filter_clause()} "
        f"and Langu eq {sap_odata_string_literal(BUNDESWEHR_ODATA_LANGUAGE)} "
        f"and Keywords eq {sap_odata_string_literal(term)})"
    )


def bundeswehr_odata_detail_key(pinst_guid: str) -> str:
    return (
        f"Langu={sap_odata_string_literal(BUNDESWEHR_ODATA_LANGUAGE)},"
        f"PinstGuid={sap_odata_string_literal(pinst_guid)}"
    )


def clean_bundeswehr_odata_value(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return helpers.normalize_whitespace(helpers.strip_html_fragment(value))


def bundeswehr_odata_searchable_text(row: dict[str, Any]) -> str:
    fields = (
        "Title",
        "PostingTxt",
        "BesOrt",
        "Region",
        "Country",
        "ContractType",
        "Arbeitszeit",
        "ApplicationEnd",
        "RefCode",
        "SearchCategory",
        "Tarifgruppe1",
        "Tarifgruppe2",
        "JobDesc",
        "RequireDesc",
        "CompanyDesc",
        "RemarcDesc",
        "ContactDesc",
    )
    values = [clean_bundeswehr_odata_value(row.get(field)) for field in fields]
    return " ".join(value for value in values if value)


def build_bundeswehr_odata_candidate_notes(row: dict[str, Any]) -> str:
    note_parts: list[str] = []
    for label, field in (
        ("RefCode", "RefCode"),
        ("Category", "SearchCategory"),
        ("Deadline", "ApplicationEnd"),
        ("Contract", "ContractType"),
        ("Workload", "Arbeitszeit"),
    ):
        value = clean_bundeswehr_odata_value(row.get(field))
        if value:
            note_parts.append(f"{label}: {value}")
    return "; ".join(note_parts)


def build_bundeswehr_odata_candidate(
    source: SourceConfig,
    row: dict[str, Any],
    terms: list[str],
    forced_terms: tuple[str, ...] = (),
) -> tuple[Candidate, str, str]:
    title = clean_bundeswehr_odata_value(row.get("Title")) or "unknown"
    pinst_guid = clean_bundeswehr_odata_value(row.get("PinstGuid"))
    candidate_id = pinst_guid or clean_bundeswehr_odata_value(row.get("RefCode")) or helpers.slugify_title(title)
    location = (
        clean_bundeswehr_odata_value(row.get("BesOrt"))
        or clean_bundeswehr_odata_value(row.get("Region"))
        or clean_bundeswehr_odata_value(row.get("Country"))
        or "unknown"
    )
    searchable_text = bundeswehr_odata_searchable_text(row)
    matched_terms = sorted(set(helpers.match_terms(searchable_text, terms) + list(forced_terms)))
    candidate = Candidate(
        employer=source.source,
        title=title,
        url=build_bundeswehr_odata_candidate_url(source.url, candidate_id),
        source_url=source.url,
        location=location,
        matched_terms=matched_terms,
        notes=build_bundeswehr_odata_candidate_notes(row),
    )
    return candidate, pinst_guid, searchable_text


def apply_bundeswehr_odata_detail(candidate: Candidate, detail: dict[str, Any], terms: list[str]) -> bool:
    original_terms = list(candidate.matched_terms)
    original_notes = candidate.notes
    detail_text_for_matching = bundeswehr_odata_searchable_text(detail)
    if detail_text_for_matching:
        candidate.matched_terms = sorted(set(candidate.matched_terms + helpers.match_terms(detail_text_for_matching, terms)))

    note_parts = [candidate.notes] if candidate.notes else []
    for label, field in (
        ("Job", "JobDesc"),
        ("Requirements", "RequireDesc"),
        ("Remarks", "RemarcDesc"),
        ("Employer", "CompanyDesc"),
        ("Contact", "ContactDesc"),
    ):
        value = clean_bundeswehr_odata_value(detail.get(field))
        if value:
            note_parts.append(f"{label}: {helpers.truncate_text(value, 260)}")
    candidate.notes = "; ".join(dict.fromkeys(part for part in note_parts if part))
    return candidate.notes != original_notes or candidate.matched_terms != original_terms


def candidate_searchable_text(candidate: Candidate) -> str:
    return helpers.normalize_for_matching(
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


def discover_bundeswehr_profile_catalog_fallback(
    source: SourceConfig,
    terms: list[str],
    timeout_seconds: int,
    extra_limitations: list[str] | None = None,
) -> Coverage:
    html = http.fetch_text(BUNDESWEHR_JOBSUCHE_URL, timeout_seconds)
    candidates_by_url: dict[str, Candidate] = {}
    raw_urls: set[str] = set()
    detail_pages_opened = 0

    for match in BUNDESWEHR_JOB_TITLE_RE.finditer(html):
        absolute_url = helpers.normalize_url_without_fragment(urljoin(BUNDESWEHR_JOBSUCHE_URL, unescape(match.group("href"))))
        raw_urls.add(absolute_url)
        title = helpers.strip_html_fragment(match.group("title")) or "unknown"
        searchable_text = " ".join(part for part in [title, absolute_url] if part)
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
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
            detail_html = http.fetch_text(absolute_url, timeout_seconds)
        except Exception:
            detail_html = ""
        else:
            detail_pages_opened += 1
            apply_bundeswehr_detail_text(candidate, detail_html, terms)
        helpers.merge_candidate(candidates_by_url, candidate)

    limitations = list(extra_limitations or [])
    limitations.append(
        "Bundeswehr Bewerbungsportal returned a generic error page in automation; using the public jobsuche profile catalog as a fallback."
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
        result_pages_scanned=f"profiles={len(raw_urls)}",
        direct_job_pages_opened=detail_pages_opened,
        enumerated_jobs=len(raw_urls),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_bundeswehr_odata(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    candidates_by_url: dict[str, Candidate] = {}
    limitations: list[str] = []
    category_summaries: list[str] = []
    keyword_summaries: list[str] = []
    listing_pages_scanned = 0
    direct_job_pages_opened = 0
    enumerated_jobs = 0
    detail_failures = 0
    detail_cache: dict[str, dict[str, Any]] = {}
    detail_failed_guids: set[str] = set()

    def load_detail(pinst_guid: str) -> dict[str, Any]:
        nonlocal detail_failures, direct_job_pages_opened
        if not pinst_guid:
            return {}
        if pinst_guid in detail_cache:
            return detail_cache[pinst_guid]
        if pinst_guid in detail_failed_guids:
            return {}
        try:
            detail = fetch_sap_odata_entity(
                BUNDESWEHR_ODATA_SERVICE_ROOT,
                BUNDESWEHR_ODATA_ENTITY_SET,
                bundeswehr_odata_detail_key(pinst_guid),
                BUNDESWEHR_ODATA_DETAIL_SELECT,
                timeout_seconds,
                http.fetch_json,
            )
        except Exception:
            detail_failures += 1
            detail_failed_guids.add(pinst_guid)
            return {}
        direct_job_pages_opened += 1
        detail_cache[pinst_guid] = detail
        return detail

    for category in BUNDESWEHR_ODATA_OPPORTUNITY_CATEGORIES:
        filter_expression = bundeswehr_odata_filter_for_category(category)
        scan = fetch_sap_odata_all(
            BUNDESWEHR_ODATA_SERVICE_ROOT,
            BUNDESWEHR_ODATA_ENTITY_SET,
            filter_expression,
            BUNDESWEHR_ODATA_LIST_SELECT,
            BUNDESWEHR_ODATA_PAGE_SIZE,
            timeout_seconds,
            http.fetch_text,
            http.fetch_json,
        )
        listing_pages_scanned += scan.pages_scanned
        enumerated_jobs += len(scan.rows)
        category_summaries.append(f"{category}:{scan.pages_scanned}p/{len(scan.rows)}of{scan.declared_total}")
        if scan.stopped_early:
            limitations.append(
                f"Bundeswehr SAP OData category {category} surfaced {len(scan.rows)} of {scan.declared_total} rows."
            )

        for row in scan.rows:
            candidate, pinst_guid, searchable_text = build_bundeswehr_odata_candidate(source, row, terms)
            if not should_keep_service_bund_candidate(candidate.title, candidate.matched_terms, searchable_text):
                continue
            detail = load_detail(pinst_guid)
            if detail:
                apply_bundeswehr_odata_detail(candidate, detail, terms)
            helpers.merge_candidate(candidates_by_url, candidate)

    for term in terms:
        try:
            scan = fetch_sap_odata_all(
                BUNDESWEHR_ODATA_SERVICE_ROOT,
                BUNDESWEHR_ODATA_ENTITY_SET,
                bundeswehr_odata_filter_for_keyword(term),
                BUNDESWEHR_ODATA_LIST_SELECT,
                BUNDESWEHR_ODATA_PAGE_SIZE,
                timeout_seconds,
                http.fetch_text,
                http.fetch_json,
            )
        except Exception as exc:
            keyword_summaries.append(f"{term}:failed")
            limitations.append(
                f"Bundeswehr SAP OData keyword search for '{term}' failed "
                f"({type(exc).__name__}: {helpers.truncate_text(str(exc), 160)})."
            )
            continue

        listing_pages_scanned += scan.pages_scanned
        keyword_summaries.append(f"{term}:{scan.pages_scanned}p/{len(scan.rows)}of{scan.declared_total}")
        if scan.stopped_early:
            limitations.append(
                f"Bundeswehr SAP OData keyword search for '{term}' surfaced "
                f"{len(scan.rows)} of {scan.declared_total} rows."
            )

        for row in scan.rows:
            candidate, pinst_guid, _searchable_text = build_bundeswehr_odata_candidate(
                source,
                row,
                terms,
                forced_terms=(term,),
            )
            detail = load_detail(pinst_guid)
            if detail:
                apply_bundeswehr_odata_detail(candidate, detail, terms)
            if not should_keep_service_bund_candidate(
                candidate.title,
                candidate.matched_terms,
                candidate_searchable_text(candidate),
            ):
                continue
            helpers.merge_candidate(candidates_by_url, candidate)

    if detail_failures:
        limitations.append(f"Bundeswehr SAP OData detail enrichment failed for {detail_failures} matched candidate(s).")

    result_pages_scanned = f"categories[{', '.join(category_summaries)}]"
    if keyword_summaries:
        result_pages_scanned += f"; keywords[{', '.join(keyword_summaries)}]"

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
        result_pages_scanned=result_pages_scanned,
        direct_job_pages_opened=direct_job_pages_opened,
        enumerated_jobs=enumerated_jobs,
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_bundeswehr_jobsuche(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    try:
        return discover_bundeswehr_odata(source, terms, timeout_seconds)
    except Exception as exc:
        limitation = (
            f"Bundeswehr SAP OData discovery failed ({type(exc).__name__}: {helpers.truncate_text(str(exc), 160)}); "
            "using the public jobsuche profile catalog as a fallback."
        )
        return discover_bundeswehr_profile_catalog_fallback(source, terms, timeout_seconds, [limitation])


SOURCE = SourceAdapter(modes=("bundeswehr_jobsuche",), discover=discover_bundeswehr_jobsuche)
