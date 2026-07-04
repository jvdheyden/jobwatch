"""UltiPro / UKG Pro Recruiting job-board provider.

Supported discovery modes:
- `ultipro_api`

Expected source URL shape:
- A recruiting2.ultipro.com job-board URL containing the tenant and board id,
  e.g. `https://recruiting2.ultipro.com/<tenant>/JobBoard/<board-guid>/...`.
"""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


ULTIPRO_HOST = "recruiting2.ultipro.com"
ULTIPRO_BOARD_PATH_RE = re.compile(
    r"^/(?P<tenant>[^/]+)/JobBoard/(?P<board>[0-9a-fA-F-]+)/?",
)
ULTIPRO_PAGE_SIZE = 100
ULTIPRO_MAX_PAGES = 10


def _board_ids(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() != ULTIPRO_HOST:
        return None
    match = ULTIPRO_BOARD_PATH_RE.match(parsed.path or "")
    if not match:
        return None
    return match.group("tenant"), match.group("board")


def _job_location(opportunity: dict) -> str:
    parts: list[str] = []
    for entry in opportunity.get("Locations") or []:
        if not isinstance(entry, dict):
            continue
        name = helpers.normalize_whitespace(unescape(str(entry.get("LocalizedName") or "")))
        address = entry.get("Address") if isinstance(entry.get("Address"), dict) else None
        city = ""
        state = ""
        country = ""
        if address:
            city = helpers.normalize_whitespace(unescape(str(address.get("City") or "")))
            state_obj = address.get("State") if isinstance(address.get("State"), dict) else None
            country_obj = address.get("Country") if isinstance(address.get("Country"), dict) else None
            if state_obj:
                state = helpers.normalize_whitespace(unescape(str(state_obj.get("Code") or state_obj.get("Name") or "")))
            if country_obj:
                country = helpers.normalize_whitespace(unescape(str(country_obj.get("Code") or country_obj.get("Name") or "")))
        address_parts = ", ".join(part for part in (city, state, country) if part)
        if name and address_parts and name != address_parts:
            parts.append(f"{name} ({address_parts})")
        elif address_parts:
            parts.append(address_parts)
        elif name:
            parts.append(name)
    return "; ".join(parts) or "unknown"


def _notes(opportunity: dict) -> str:
    note_parts = ["Enumerated through UltiPro/UKG recruiting JSON API"]
    requisition = helpers.normalize_whitespace(unescape(str(opportunity.get("RequisitionNumber") or "")))
    if requisition:
        note_parts.append(f"Requisition: {requisition}")
    category = helpers.normalize_whitespace(unescape(str(opportunity.get("JobCategoryName") or "")))
    if category:
        note_parts.append(f"Category: {category}")
    full_time = opportunity.get("FullTime")
    if isinstance(full_time, bool):
        note_parts.append("Employment type: Full-time" if full_time else "Employment type: Part-time")
    posted = helpers.normalize_whitespace(str(opportunity.get("PostedDate") or ""))
    if posted:
        note_parts.append(f"Posted: {posted}")
    brief = helpers.normalize_whitespace(unescape(str(opportunity.get("BriefDescription") or "")))
    if brief:
        note_parts.append(f"Description: {helpers.truncate_text(brief, 320)}")
    return "; ".join(note_parts)


def discover_ultipro_jobs(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    board_ids = _board_ids(source.url)
    if not board_ids:
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
            limitations=[f"Could not parse UltiPro tenant/board from URL: {source.url}"],
            candidates=[],
        )
    tenant, board = board_ids
    base = f"https://{ULTIPRO_HOST}/{tenant}/JobBoard/{board}"
    search_endpoint = f"{base}/JobBoardView/LoadSearchResults"
    detail_root = f"{base}/OpportunityDetail"

    candidates_by_url: dict[str, Candidate] = {}
    enumerated = 0
    pages_scanned = 0
    limitations: list[str] = []

    for page_index in range(ULTIPRO_MAX_PAGES):
        payload = {
            "opportunitySearch": {
                "Top": ULTIPRO_PAGE_SIZE,
                "Skip": page_index * ULTIPRO_PAGE_SIZE,
                "QueryString": "",
                "OrderBy": [{"Value": "postedDateDesc"}],
            }
        }
        try:
            response = http.post_json(search_endpoint, payload, timeout_seconds)
            pages_scanned += 1
        except Exception as exc:
            limitations.append(f"LoadSearchResults failed at skip={page_index * ULTIPRO_PAGE_SIZE}: {type(exc).__name__}: {exc}")
            break
        opportunities = response.get("opportunities") if isinstance(response, dict) else None
        if not isinstance(opportunities, list) or not opportunities:
            break
        enumerated += len(opportunities)
        for opportunity in opportunities:
            if not isinstance(opportunity, dict):
                continue
            job_id = str(opportunity.get("Id") or "").strip()
            if not job_id:
                continue
            title = helpers.normalize_whitespace(unescape(str(opportunity.get("Title") or ""))) or "unknown"
            location = _job_location(opportunity)
            brief = helpers.normalize_whitespace(unescape(str(opportunity.get("BriefDescription") or "")))
            category = helpers.normalize_whitespace(unescape(str(opportunity.get("JobCategoryName") or "")))
            searchable_text = " ".join(part for part in (title, location, category, brief) if part)
            matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
            if not helpers.should_keep_candidate(title, matched_terms, searchable_text):
                continue
            detail_url = f"{detail_root}?opportunityId={job_id}"
            helpers.merge_candidate(
                candidates_by_url,
                Candidate(
                    employer=source.source,
                    title=title,
                    url=detail_url,
                    source_url=source.url,
                    location=location,
                    remote=helpers.infer_remote_status(title, location, brief),
                    matched_terms=matched_terms,
                    notes=_notes(opportunity),
                ),
            )
        total_count = response.get("totalCount") if isinstance(response, dict) else None
        if isinstance(total_count, int) and (page_index + 1) * ULTIPRO_PAGE_SIZE >= total_count:
            break
        if len(opportunities) < ULTIPRO_PAGE_SIZE:
            break

    status = "complete" if pages_scanned > 0 else "failed"
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
        result_pages_scanned=f"ultipro_pages={pages_scanned}",
        direct_job_pages_opened=0,
        enumerated_jobs=enumerated,
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("ultipro_api",), discover=discover_ultipro_jobs)
