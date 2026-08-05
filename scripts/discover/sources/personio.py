"""Personio page payload provider.

Supported discovery modes:
- `personio_page`

Expected source URL shape:
- `https://<subdomain>.jobs.personio.de/`
"""

from __future__ import annotations

import json
import re
from typing import Any
from xml.etree import ElementTree

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


PERSONIO_NEXT_F_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,"(?P<chunk>.*?)"\]\)', flags=re.DOTALL)

PERSONIO_TASK_HEADING_MARKERS = (
    "mission",
    "responsibil",
    "task",
    "aufgaben",
    "what you will do",
    "what you'll do",
    "your impact",
)
PERSONIO_QUALIFICATION_HEADING_MARKERS = (
    "profile",
    "profil",
    "qualification",
    "requirement",
    "anforderung",
    "what you bring",
    "experience",
    "skills",
)
PERSONIO_COMPENSATION_HEADING_MARKERS = (
    "compensation",
    "salary",
    "pay range",
    "gehalt",
    "vergutung",
)


def extract_personio_jobs_from_html(html: str) -> list[Any] | None:
    for match in PERSONIO_NEXT_F_CHUNK_RE.finditer(html):
        chunk = match.group("chunk")
        try:
            decoded = json.loads(f'"{chunk}"')
        except json.JSONDecodeError:
            continue
        jobs = helpers.extract_json_array_after_marker(decoded, '{"jobs":')
        if jobs is not None:
            return jobs
    return None


def _personio_xml_feed_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/xml"


def _personio_job_url_from_id(base_url: str, position_id: str) -> str:
    return base_url.rstrip("/") + f"/job/{position_id}"


def extract_personio_jobs_from_xml(xml_text: str, base_url: str) -> list[dict[str, Any]] | None:
    """Parse the canonical Personio /xml feed into job dicts compatible with the HTML path."""
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return None
    if root.tag != "workzag-jobs":
        return None
    jobs: list[dict[str, Any]] = []
    for position in root.findall("position"):
        job: dict[str, Any] = {}
        for child in position:
            if child.tag == "jobDescriptions":
                descriptions: list[dict[str, str]] = []
                for description in child.findall("jobDescription"):
                    heading = helpers.normalize_whitespace(description.findtext("name") or "")
                    value_html = description.findtext("value") or ""
                    value = helpers.visible_text_from_html(value_html)
                    if value:
                        descriptions.append({"name": heading, "value": value})
                if descriptions:
                    job[child.tag] = descriptions
                continue
            text = (child.text or "").strip()
            if text:
                job[child.tag] = text
        position_id = job.get("id")
        if position_id:
            job["url"] = _personio_job_url_from_id(base_url, position_id)
        if job.get("name") or job.get("id"):
            jobs.append(job)
    return jobs


def _fetch_personio_xml_jobs(base_url: str, timeout_seconds: int) -> list[dict[str, Any]] | None:
    try:
        xml_text = http.fetch_text(_personio_xml_feed_url(base_url), timeout_seconds)
    except Exception:
        return None
    return extract_personio_jobs_from_xml(xml_text, base_url)


def _personio_job_identity(job: dict[str, Any]) -> tuple[str, str]:
    position_id = helpers.normalize_whitespace(
        helpers.join_text(job.get("id") or job.get("positionId") or job.get("position_id"))
    )
    title = helpers.normalize_for_matching(
        helpers.normalize_whitespace(helpers.join_text(job.get("name") or job.get("title")))
    )
    return position_id, title


def _personio_xml_job_lookup(xml_jobs: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_title: dict[str, dict[str, Any]] = {}
    for job in xml_jobs:
        position_id, title = _personio_job_identity(job)
        if position_id:
            by_id[position_id] = job
        if title:
            by_title.setdefault(title, job)
    return by_id, by_title


def _personio_xml_job_for_listing(
    job: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    by_title: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    position_id, title = _personio_job_identity(job)
    if position_id and position_id in by_id:
        return by_id[position_id]
    if title:
        return by_title.get(title)
    return None


def _personio_description_parts(job: dict[str, Any]) -> list[tuple[str, str]]:
    descriptions = job.get("jobDescriptions")
    if not isinstance(descriptions, list):
        return []
    parts: list[tuple[str, str]] = []
    for description in descriptions:
        if not isinstance(description, dict):
            continue
        heading = helpers.normalize_whitespace(helpers.join_text(description.get("name")))
        value = helpers.normalize_whitespace(helpers.join_text(description.get("value")))
        if value:
            parts.append((heading, value))
    return parts


def _personio_detail_label(heading: str) -> str:
    normalized = helpers.normalize_for_matching(heading)
    if any(marker in normalized for marker in PERSONIO_TASK_HEADING_MARKERS):
        return "Tasks"
    if any(marker in normalized for marker in PERSONIO_QUALIFICATION_HEADING_MARKERS):
        return "Qualifications"
    if any(marker in normalized for marker in PERSONIO_COMPENSATION_HEADING_MARKERS):
        return "Compensation"
    return heading or "Details"


def _personio_candidate_notes(job: dict[str, Any], *, used_xml: bool) -> str:
    provenance = "Enumerated through Personio XML feed" if used_xml else "Enumerated through Personio page payload"
    parts = [provenance]
    for heading, value in _personio_description_parts(job):
        parts.append(f"{_personio_detail_label(heading)}: {helpers.truncate_text(value, 320)}")
    return "; ".join(parts)


def discover_personio_page(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    jobs: list[Any] | None = None
    xml_jobs: list[dict[str, Any]] | None = None
    limitations: list[str] = []
    html_fetch_error: Exception | None = None

    try:
        html = http.fetch_text(source.url, timeout_seconds)
    except Exception as exc:
        html_fetch_error = exc
        html = ""
    else:
        jobs = extract_personio_jobs_from_html(html)

    html_says_no_openings = (
        not html_fetch_error
        and ("Derzeit keine offenen Positionen" in html or "No open positions" in html)
    )

    if jobs is None and not html_says_no_openings:
        xml_jobs = _fetch_personio_xml_jobs(source.url, timeout_seconds)
        if xml_jobs is not None:
            jobs = xml_jobs
            if html_fetch_error is not None:
                limitations.append(f"Personio HTML page unavailable ({html_fetch_error}); used XML feed.")
            else:
                limitations.append("Personio HTML page payload missing; used XML feed.")

    if jobs is None:
        if html_says_no_openings:
            jobs = []
        else:
            if html_fetch_error is not None:
                failure_message = f"Personio page fetch failed ({html_fetch_error}); XML feed unavailable."
            else:
                failure_message = "Personio page did not expose a parseable jobs payload."
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
                limitations=[failure_message],
                candidates=[],
            )

    if xml_jobs is None and jobs:
        xml_jobs = _fetch_personio_xml_jobs(source.url, timeout_seconds)

    xml_jobs_by_id, xml_jobs_by_title = _personio_xml_job_lookup(xml_jobs or [])

    candidates_by_url: dict[str, Candidate] = {}
    for job in jobs:
        if not isinstance(job, dict):
            continue
        xml_job = _personio_xml_job_for_listing(job, xml_jobs_by_id, xml_jobs_by_title)
        detail_job = xml_job or job
        title = helpers.normalize_whitespace(helpers.join_text(job.get("name") or job.get("title"))) or "unknown"
        location = helpers.normalize_whitespace(
            helpers.join_text(
                job.get("office")
                or job.get("location")
                or job.get("locations")
                or detail_job.get("office")
                or detail_job.get("location")
                or detail_job.get("locations")
            )
        ) or "unknown"
        searchable_text = " ".join(
            part
            for part in [
                title,
                location,
                helpers.join_text(job.get("department")),
                helpers.join_text(job.get("employmentType") or job.get("employment_type")),
                helpers.join_text(job),
            ]
            if part
        )
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not matched_terms:
            continue
        job_url = helpers.normalize_url_without_fragment(
            helpers.join_text(
                job.get("url")
                or job.get("absoluteUrl")
                or detail_job.get("url")
                or detail_job.get("absoluteUrl")
                or source.url
            )
        )
        candidate = Candidate(
            employer=source.source,
            title=title,
            url=job_url,
            source_url=source.url,
            location=location,
            remote=helpers.infer_remote_status(location, searchable_text),
            matched_terms=matched_terms,
            notes=_personio_candidate_notes(detail_job, used_xml=xml_job is not None or jobs is xml_jobs),
        )
        description = " ".join(value for _heading, value in _personio_description_parts(detail_job))
        helpers.set_candidate_description(candidate, description)
        helpers.merge_candidate(
            candidates_by_url,
            candidate,
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
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("personio_page",), discover=discover_personio_page)
