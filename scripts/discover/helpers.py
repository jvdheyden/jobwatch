"""Shared text, URL, HTML, and candidate helpers for discovery providers."""

from __future__ import annotations

import json
import re
import unicodedata
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from discover.constants import (
    NON_TECHNICAL_TITLE_HINTS,
    SPECIALIZED_SIGNAL_TERMS,
    TECHNICAL_TITLE_HINTS,
)
from discover.core import Candidate


HTML_TAG_RE = re.compile(r"<[^>]+>")


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


def normalize_for_matching(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text.lower()


def match_terms(text: str, terms: list[str]) -> list[str]:
    haystack = normalize_for_matching(text)
    return [term for term in terms if normalize_for_matching(term) in haystack]


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


def infer_remote_status(*values: str) -> str:
    haystack = normalize_for_matching(" ".join(value for value in values if value))
    if "hybrid" in haystack:
        return "hybrid"
    if "remote" in haystack:
        return "remote"
    if "on-site" in haystack or "onsite" in haystack:
        return "on-site"
    return "unknown"


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
