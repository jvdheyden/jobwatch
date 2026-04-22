#!/usr/bin/env python3
"""Probe a career source during setup and suggest canaries/config."""

from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from discover.http import USER_AGENT


JOBLIKE_RE = re.compile(
    r"(job|jobs|career|careers|position|positions|opening|openings|requisition|vacancy|vacancies|apply)",
    re.IGNORECASE,
)
TITLE_HINT_RE = re.compile(
    r"(engineer|developer|research|scientist|security|privacy|crypt|software|product|designer|manager|analyst|"
    r"lead|principal|senior|staff|postdoc|phd|intern)",
    re.IGNORECASE,
)
JS_HEAVY_HINTS = (
    "enable javascript",
    "requires javascript",
    "__next_data__",
    "window.__INITIAL_STATE__",
    "id=\"root\"",
    "id=\"app\"",
)


@dataclass(frozen=True)
class LinkCandidate:
    title: str
    url: str


class LinkCollector(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self._current_href: str | None = None
        self._current_text: list[str] = []
        self.links: list[LinkCandidate] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        href = attrs_dict.get("href", "").strip()
        if not href:
            return
        self._current_href = href
        self._current_text = []
        aria = attrs_dict.get("aria-label", "").strip()
        title = attrs_dict.get("title", "").strip()
        if aria:
            self._current_text.append(aria)
        if title:
            self._current_text.append(title)

    def handle_data(self, data: str) -> None:
        if self._current_href:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._current_href:
            return
        text = normalize_space(" ".join(self._current_text))
        absolute_url = urljoin(self.base_url, self._current_href)
        if text:
            self.links.append(LinkCandidate(title=text, url=absolute_url))
        self._current_href = None
        self._current_text = []


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def infer_board_family(url: str, html: str = "") -> tuple[str, str]:
    haystack = f"{url}\n{html[:5000]}".lower()
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if "greenhouse.io" in host:
        return "greenhouse", "greenhouse_api"
    if "lever.co" in host:
        return "lever", "lever_json"
    if "ashbyhq.com" in host or "ashby" in host:
        return "ashby", "ashby_api"
    if "workable.com" in host:
        return "workable", "workable_api"
    if "myworkdayjobs.com" in host:
        return "workday", "workday_api"
    if "personio" in host or "personio" in path:
        return "personio", "personio_page"
    if "recruitee" in host:
        return "recruitee", "recruitee_inline"
    if "getro.com" in host or "jobs.ashbyhq.com" in haystack:
        return "getro", "getro_api"
    if "service.bund.de" in host:
        return "service_bund", "service_bund_search"
    if "news.ycombinator.com" in host:
        return "hackernews", "hackernews_jobs"
    if "ycombinator.com/jobs" in haystack:
        return "yc", "yc_jobs_board"
    if "greenhouse" in haystack:
        return "greenhouse", "greenhouse_api"
    if "lever" in haystack:
        return "lever", "lever_json"
    if "workday" in haystack:
        return "workday", "workday_api"
    if "workable" in haystack:
        return "workable", "workable_api"
    return "unknown", "html"


def looks_js_heavy(html: str) -> bool:
    lowered = html.lower()
    if any(hint in lowered for hint in JS_HEAVY_HINTS):
        visible_text = re.sub(r"<[^>]+>", " ", html)
        return len(normalize_space(visible_text)) < 5000
    return False


def extract_canary_candidates(html: str, base_url: str, terms: list[str]) -> list[dict[str, str]]:
    collector = LinkCollector(base_url)
    collector.feed(html)
    wanted_terms = [term.lower() for term in terms if term.strip()]
    seen: set[tuple[str, str]] = set()
    ranked: list[tuple[int, LinkCandidate]] = []
    for link in collector.links:
        title = normalize_space(link.title)
        if len(title) < 4:
            continue
        haystack = f"{title} {link.url}".lower()
        score = 0
        if JOBLIKE_RE.search(link.url):
            score += 3
        if JOBLIKE_RE.search(title):
            score += 2
        if TITLE_HINT_RE.search(title):
            score += 2
        if wanted_terms and any(term in haystack for term in wanted_terms):
            score += 2
        if score == 0:
            continue
        key = (title.lower(), link.url)
        if key in seen:
            continue
        seen.add(key)
        ranked.append((score, link))
    ranked.sort(key=lambda item: (-item[0], item[1].title.lower(), item[1].url))
    return [{"title": item.title, "url": item.url} for _score, item in ranked[:10]]


def fetch_http(url: str, timeout: int) -> tuple[str, str, int, list[str]]:
    hints: list[str] = []
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    context = ssl.create_default_context()
    try:
        with urlopen(request, timeout=timeout, context=context) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            body = response.read()
            final_url = response.geturl()
            return body.decode(charset, errors="replace"), final_url, int(response.status), hints
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code == 403:
            hints.append("HTTP 403; source may block scripted requests")
        return body, exc.geturl() or url, int(exc.code), hints
    except URLError as exc:
        hints.append(f"HTTP fetch failed: {exc.reason}")
        return "", url, 0, hints


def fetch_playwright(url: str, timeout: int) -> tuple[str, str, list[str]]:
    hints: list[str] = []
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:
        return "", url, [f"Playwright unavailable: {exc}"]
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            html = page.content()
            final_url = page.url
            browser.close()
            return html, final_url, hints
    except Exception as exc:
        return "", url, [f"Playwright fetch failed: {exc}"]


def probe(url: str, *, source_name: str = "", terms: list[str] | None = None, timeout: int = 15) -> dict[str, Any]:
    terms = terms or []
    html, final_url, status, hints = fetch_http(url, timeout)
    playwright_needed = status == 403 or (bool(html) and looks_js_heavy(html))
    playwright_used = False
    if playwright_needed:
        rendered_html, rendered_url, rendered_hints = fetch_playwright(final_url or url, timeout)
        hints.extend(rendered_hints)
        if rendered_html:
            html = rendered_html
            final_url = rendered_url
            playwright_used = True
    if html and looks_js_heavy(html):
        hints.append("Page appears JavaScript-heavy; verify with source-quality checks before treating as ready")
    family, mode = infer_board_family(final_url or url, html)
    return {
        "source_name": source_name,
        "input_url": url,
        "final_url": final_url or url,
        "likely_board_family": family,
        "suggested_discovery_mode": mode,
        "fetch_status": status,
        "hints": hints,
        "candidate_canaries": extract_canary_candidates(html, final_url or url, terms) if html else [],
        "playwright_needed": playwright_needed,
        "playwright_used": playwright_used,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Career source URL to probe")
    parser.add_argument("--name", default="", help="Optional source display name")
    parser.add_argument("--term", action="append", default=[], help="Optional track/source term; may be repeated")
    parser.add_argument("--timeout", type=int, default=15, help="Fetch timeout in seconds")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = probe(args.url, source_name=args.name, terms=args.term, timeout=args.timeout)
    print(json.dumps(payload, indent=2 if args.pretty else None, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
