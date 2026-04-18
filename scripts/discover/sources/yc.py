"""Y Combinator jobs board provider.

Supported discovery modes:
- `yc_jobs_board`

Expected source URL shape:
- `https://www.ycombinator.com/jobs/...`
"""

from __future__ import annotations

import json
from html import unescape
from urllib.parse import urljoin

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


def extract_yc_jobs_payload(html: str) -> dict[str, object] | None:
    parser = helpers.DataPageCollector()
    parser.feed(html)
    for payload_text in parser.payloads:
        try:
            payload = json.loads(unescape(payload_text))
        except json.JSONDecodeError:
            continue
        props = payload.get("props") or {}
        if payload.get("component") == "WaasJobListingsPage" and isinstance(props.get("jobPostings"), list):
            return payload
    return None


def discover_yc_jobs_board(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = http.fetch_text(source.url, timeout_seconds)
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
        title = helpers.normalize_whitespace(helpers.join_text(posting.get("title"))) or "unknown"
        employer = helpers.normalize_whitespace(helpers.join_text(posting.get("companyName"))) or source.source
        location = helpers.normalize_whitespace(helpers.join_text(posting.get("location"))) or "unknown"
        role_specific_type = helpers.normalize_whitespace(helpers.join_text(posting.get("roleSpecificType")))
        pretty_role = helpers.normalize_whitespace(helpers.join_text(posting.get("prettyRole")))
        employment_type = helpers.normalize_whitespace(helpers.join_text(posting.get("type")))
        salary_range = helpers.normalize_whitespace(helpers.join_text(posting.get("salaryRange")))
        equity_range = helpers.normalize_whitespace(helpers.join_text(posting.get("equityRange")))
        min_experience = helpers.normalize_whitespace(helpers.join_text(posting.get("minExperience")))
        visa = helpers.normalize_whitespace(helpers.join_text(posting.get("visa")))
        company_one_liner = helpers.normalize_whitespace(helpers.join_text(posting.get("companyOneLiner")))
        company_batch = helpers.normalize_whitespace(helpers.join_text(posting.get("companyBatchName")))
        created_at = helpers.normalize_whitespace(helpers.join_text(posting.get("createdAt")))
        last_active = helpers.normalize_whitespace(helpers.join_text(posting.get("lastActive")))
        job_url = helpers.normalize_url_without_fragment(urljoin(source.url, helpers.join_text(posting.get("url")) or source.url))
        apply_url_raw = helpers.join_text(posting.get("applyUrl"))
        apply_url = helpers.normalize_url_without_fragment(urljoin(source.url, apply_url_raw)) if apply_url_raw else ""
        remote = helpers.infer_remote_status(location, title, company_one_liner)

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
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not helpers.should_keep_candidate(title, matched_terms, searchable_text):
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

        helpers.merge_candidate(
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


SOURCE = SourceAdapter(modes=("yc_jobs_board",), discover=discover_yc_jobs_board)
