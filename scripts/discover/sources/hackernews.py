"""Hacker News jobs providers.

Supported discovery modes:
- `hackernews_jobs`
- `hackernews_whoishiring_api`

Expected source URL shapes:
- `https://news.ycombinator.com/jobs`
- `https://news.ycombinator.com/user?id=whoishiring`
"""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import parse_qsl, urljoin, urlparse

from discover import helpers, http
from discover.constants import MAX_BROWSER_PAGES
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


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


def infer_hn_employer(title: str) -> str:
    title_text = helpers.strip_html_fragment(title)
    match = re.match(r"(?P<employer>.+?)\s+\(YC [^)]+\)", title_text, flags=re.IGNORECASE)
    if match:
        return helpers.normalize_whitespace(match.group("employer"))
    return "YC startup"


def extract_first_external_url_from_html(html_text: str, base_url: str) -> str:
    parser = helpers.LinkCollector()
    parser.feed(html_text or "")
    for link in parser.links:
        absolute_url = helpers.normalize_url_without_fragment(urljoin(base_url, link["href"]))
        parsed = urlparse(absolute_url)
        if parsed.scheme in {"http", "https"} and parsed.netloc and parsed.netloc != "news.ycombinator.com":
            return absolute_url
    return ""


def infer_hn_whoishiring_fields(clean_text: str, fallback_employer: str) -> tuple[str, str, str]:
    segments = [helpers.normalize_whitespace(segment) for segment in clean_text.split("|") if helpers.normalize_whitespace(segment)]
    if not segments:
        employer = fallback_employer or "HN employer"
        return employer, "Hiring post", "unknown"

    employer = segments[0]
    workplace_tokens = ("remote", "hybrid", "onsite", "on-site", "full-time", "part-time", "contract", "intern")

    title = "Hiring post"
    title_index = -1
    for index, segment in enumerate(segments[1:], start=1):
        lowered = helpers.normalize_for_matching(segment)
        if any(token in lowered for token in workplace_tokens):
            continue
        title = segment
        title_index = index
        break

    location = "unknown"
    for segment in segments[(title_index + 1) if title_index >= 0 else 1 :]:
        lowered = helpers.normalize_for_matching(segment)
        if any(token in lowered for token in workplace_tokens) or "," in segment or "(" in segment:
            location = segment
            break

    return employer or fallback_employer or "HN employer", title, location


def discover_hackernews_jobs(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    candidates_by_url: dict[str, Candidate] = {}
    listing_pages_scanned = 0
    enumerated_jobs = 0
    next_url = source.url
    limitations: list[str] = []

    while next_url and listing_pages_scanned < MAX_BROWSER_PAGES:
        html = http.fetch_text(next_url, timeout_seconds)
        listing_pages_scanned += 1
        for match in HN_JOB_ROW_RE.finditer(html):
            enumerated_jobs += 1
            title = helpers.strip_html_fragment(match.group("title")) or "unknown"
            job_url = helpers.normalize_url_without_fragment(urljoin(next_url, unescape(match.group("href"))))
            age_text = helpers.normalize_whitespace(match.group("age"))
            employer = infer_hn_employer(title)
            searchable_text = " ".join(part for part in [title, employer, age_text, job_url] if part)
            matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
            if not helpers.should_keep_candidate(title, matched_terms, searchable_text):
                continue
            helpers.merge_candidate(
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
    user = http.fetch_json(f"https://hacker-news.firebaseio.com/v0/user/{username}.json", timeout_seconds)
    submitted_ids = user.get("submitted") or []

    story: dict[str, object] | None = None
    story_title = ""
    for item_id in submitted_ids[:30]:
        item = http.fetch_json(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json", timeout_seconds)
        title = helpers.normalize_whitespace(helpers.join_text(item.get("title")))
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
    story_url = helpers.normalize_url_without_fragment(f"https://news.ycombinator.com/item?id={story_id}")
    candidates_by_url: dict[str, Candidate] = {}
    enumerated_jobs = 0

    for comment_id in story.get("kids") or []:
        comment = http.fetch_json(f"https://hacker-news.firebaseio.com/v0/item/{comment_id}.json", timeout_seconds)
        if comment.get("dead") or comment.get("deleted") or not comment.get("text"):
            continue
        enumerated_jobs += 1
        text_html = helpers.join_text(comment.get("text"))
        clean_text = helpers.strip_html_fragment(text_html)
        employer, title, location = infer_hn_whoishiring_fields(clean_text, comment.get("by") or "HN employer")
        remote = helpers.infer_remote_status(location, clean_text)
        searchable_text = " ".join(part for part in [title, employer, location, clean_text] if part)
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not helpers.should_keep_candidate(title, matched_terms, searchable_text):
            continue

        comment_url = helpers.normalize_url_without_fragment(f"https://news.ycombinator.com/item?id={comment_id}")
        external_url = extract_first_external_url_from_html(text_html, story_url)
        note_parts = [
            f"HN Who is hiring thread: {story_title}",
            f"Story: {story_url}",
        ]
        excerpt = helpers.truncate_text(clean_text, 260)
        if excerpt:
            note_parts.append(f"Excerpt: {excerpt}")
        helpers.merge_candidate(
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


SOURCES = [
    SourceAdapter(modes=("hackernews_jobs",), discover=discover_hackernews_jobs),
    SourceAdapter(modes=("hackernews_whoishiring_api",), discover=discover_hackernews_whoishiring_api),
]
