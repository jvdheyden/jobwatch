"""Recruitee inline app-config provider."""

from __future__ import annotations

import json
import re
from html import unescape
from urllib.parse import urljoin

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


RECRUITEE_DATA_PROPS_RE = re.compile(r'data-props="(?P<props>[^"]+)"')


def extract_recruitee_app_config(html: str) -> dict[str, object] | None:
    for match in RECRUITEE_DATA_PROPS_RE.finditer(html):
        try:
            payload = json.loads(unescape(match.group("props")))
        except json.JSONDecodeError:
            continue
        app_config = payload.get("appConfig")
        if isinstance(app_config, dict) and isinstance(app_config.get("offers"), list):
            return app_config
    return None


def discover_recruitee_inline(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = http.fetch_text(source.url, timeout_seconds)
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
        name = helpers.join_text(department.get("translations") or {})
        if department.get("id") and name:
            departments[int(department["id"])] = helpers.normalize_whitespace(name)

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

        title = helpers.normalize_whitespace(helpers.join_text(translation.get("title"))) or "unknown"
        slug = helpers.normalize_whitespace(helpers.join_text(offer.get("slug")))
        job_url = (
            helpers.normalize_url_without_fragment(urljoin(source.url.rstrip("/") + "/", f"o/{slug}"))
            if slug
            else source.url
        )
        city = helpers.normalize_whitespace(helpers.join_text(offer.get("city")))
        state = helpers.normalize_whitespace(helpers.join_text(translation.get("state")))
        country = helpers.normalize_whitespace(helpers.join_text(translation.get("country")))
        location_parts: list[str] = []
        for part in (city, state, country):
            if part and part not in location_parts:
                location_parts.append(part)
        location = ", ".join(location_parts) or "unknown"
        department = departments.get(int(offer["departmentId"])) if offer.get("departmentId") else ""
        employment_type = helpers.normalize_whitespace(helpers.join_text(offer.get("employmentType"))).replace("_", " ")
        experience = helpers.normalize_whitespace(helpers.join_text(offer.get("experience"))).replace("_", " ")
        education = helpers.normalize_whitespace(helpers.join_text(offer.get("education"))).replace("_", " ")
        tags = ", ".join(helpers.normalize_whitespace(helpers.join_text(tag)) for tag in offer.get("tags") or [] if helpers.join_text(tag))
        description = helpers.strip_html_fragment(helpers.join_text(translation.get("descriptionHtml")))
        requirements = helpers.strip_html_fragment(helpers.join_text(translation.get("requirementsHtml")))

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
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not helpers.should_keep_candidate(title, matched_terms, searchable_text):
            continue

        note_parts = ["Recruitee inline offers payload"]
        if department:
            note_parts.append(f"Department: {department}")
        if employment_type:
            note_parts.append(f"Type: {employment_type}")
        if remote != "unknown":
            note_parts.append(f"Remote: {remote}")

        helpers.merge_candidate(
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


SOURCE = SourceAdapter(modes=("recruitee_inline",), discover=discover_recruitee_inline)
