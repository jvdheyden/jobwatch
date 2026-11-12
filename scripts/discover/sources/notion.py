"""Public Notion site provider for careers pages built from a Notion database.

Supported discovery modes:
- `notion_site`

Expected source URL shape:
- `https://<workspace>.notion.site/<Page-Title>-<32-hex-page-id>`

Notion renders these pages client-side and job cards are not links, so the
provider reads the page through the site's public `/api/v3` endpoints
(`loadPageChunk`, then `queryCollection` for each embedded database). Matched
postings get their descriptions from `fetch_notion_description`, which reads
each row's page through `loadPageChunk` during description enrichment. These
endpoints are undocumented and may change.
"""

from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, DescriptionBudgetExhausted, SourceConfig
from discover.registry import SourceAdapter


PAGE_ID_RE = re.compile(r"([0-9a-f]{32})(?:[/?#]|$)", re.IGNORECASE)
ROW_LIMIT = 200
MAX_PAGE_CHUNKS = 10
# Child pages and embedded databases inside a posting are separate documents.
NON_CONTENT_BLOCK_TYPES = {"page", "collection_view", "collection_view_page"}


def notion_page_id(source_url: str) -> str:
    match = PAGE_ID_RE.search(urlparse(source_url).path)
    if not match:
        raise ValueError(f"Could not derive Notion page id from {source_url}")
    raw = match.group(1).lower()
    return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"


def _record_value(record: Any) -> dict[str, Any]:
    # Records come as {"value": {...}} or, in newer responses, {"value": {"value": {...}, "role": ...}}.
    value = record.get("value") if isinstance(record, dict) else None
    if isinstance(value, dict) and isinstance(value.get("value"), dict):
        value = value["value"]
    return value if isinstance(value, dict) else {}


def notion_rich_text(value: Any) -> str:
    """Flatten Notion rich text such as [["Head of Growth"]] or a date mention."""
    parts: list[str] = []
    for segment in value if isinstance(value, list) else []:
        if not isinstance(segment, list) or not segment:
            continue
        text = segment[0] if isinstance(segment[0], str) else ""
        annotations = segment[1] if len(segment) > 1 and isinstance(segment[1], list) else []
        date = next(
            (
                annotation[1].get("start_date", "")
                for annotation in annotations
                if isinstance(annotation, list) and len(annotation) > 1 and annotation[0] == "d" and isinstance(annotation[1], dict)
            ),
            "",
        )
        parts.append(date or ("" if text == "‣" else text))
    return helpers.normalize_whitespace(" ".join(part for part in parts if part))


def _nested_dict(value: Any, *keys: str) -> dict[str, Any] | None:
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value if isinstance(value, dict) else None


def _collection_views(blocks: dict[str, dict[str, Any]]) -> list[tuple[str, str, str]]:
    views: list[tuple[str, str, str]] = []
    for block in blocks.values():
        if block.get("type") not in {"collection_view", "collection_view_page"}:
            continue
        view_ids = block.get("view_ids") or []
        if block.get("collection_id") and view_ids and block.get("space_id"):
            views.append((block["collection_id"], view_ids[0], block["space_id"]))
    return views


def load_notion_page_blocks(
    api_base: str, page_id: str, timeout_seconds: int, *, deadline: float | None = None
) -> tuple[dict[str, dict[str, Any]], bool]:
    """Load the blocks of one Notion page, following `loadPageChunk` cursors.

    Returns the blocks and whether a continuation cursor was left unread after
    `MAX_PAGE_CHUNKS` requests. With a `deadline` (a `time.monotonic()` value),
    raises `DescriptionBudgetExhausted` instead of starting a request after it.
    """
    blocks: dict[str, dict[str, Any]] = {}
    cursor: dict[str, Any] = {"stack": []}
    for chunk_number in range(MAX_PAGE_CHUNKS):
        if deadline is not None and time.monotonic() >= deadline:
            raise DescriptionBudgetExhausted(f"Notion page {page_id} was not fully loaded before the deadline")
        response = http.post_json(
            f"{api_base}/loadPageChunk",
            {"pageId": page_id, "limit": 100, "cursor": cursor, "chunkNumber": chunk_number, "verticalColumns": False},
            timeout_seconds,
        )
        if not isinstance(response, dict) or not isinstance(response.get("recordMap"), dict):
            raise ValueError("Notion loadPageChunk response did not contain a `recordMap`")
        for block_id, record in (response["recordMap"].get("block") or {}).items():
            block = _record_value(record)
            if block:
                blocks[block_id] = block
        next_cursor = response.get("cursor")
        if not isinstance(next_cursor, dict) or not next_cursor.get("stack"):
            return blocks, False
        cursor = next_cursor
    return blocks, True


def notion_page_text(blocks: dict[str, dict[str, Any]], page_id: str) -> str:
    """Extract a page's own content in document order.

    Walks only the page's child blocks (descending into nested lists, toggles
    and columns); the response also carries the parent careers page and
    database, and sub-pages or embedded databases inside the posting are not
    part of its description.
    """
    root = blocks.get(page_id)
    if root is None:
        raise ValueError(f"Notion page block {page_id} was not returned")
    lines: list[str] = []
    visited: set[str] = {page_id}

    def walk(block_ids: Any) -> None:
        for block_id in block_ids if isinstance(block_ids, list) else []:
            if not isinstance(block_id, str) or block_id in visited:
                continue
            visited.add(block_id)
            block = blocks.get(block_id)
            if block is None:
                raise ValueError(f"Notion block {block_id} referenced by page {page_id} was not returned")
            if block.get("type") in NON_CONTENT_BLOCK_TYPES:
                continue
            text = notion_rich_text((block.get("properties") or {}).get("title"))
            if text:
                lines.append(text)
            walk(block.get("content"))

    walk(root.get("content"))
    return "\n".join(lines)


def fetch_notion_description(url: str, timeout_seconds: int, *, deadline: float | None = None) -> str:
    """Return the text of the Notion page behind a `notion_site` candidate URL.

    Used by description enrichment in place of an HTML fetch: the public HTML
    of a notion.site page is only a JavaScript shell. `deadline` is the
    enrichment deadline, checked before each page chunk.
    """
    parsed = urlparse(url)
    api_base = f"{parsed.scheme or 'https'}://{parsed.netloc}/api/v3"
    page_id = notion_page_id(url)
    blocks, has_more = load_notion_page_blocks(api_base, page_id, timeout_seconds, deadline=deadline)
    if has_more:
        raise ValueError(f"Notion page {page_id} needed more than {MAX_PAGE_CHUNKS} loadPageChunk requests")
    text = notion_page_text(blocks, page_id)
    if not text:
        raise ValueError(f"Notion page {page_id} has no text content")
    return text


def discover_notion_site(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    parsed = urlparse(source.url)
    api_base = f"{parsed.scheme or 'https'}://{parsed.netloc}/api/v3"
    page_id = notion_page_id(source.url)
    # A database can sit past the first chunk of a long careers page.
    blocks, has_more = load_notion_page_blocks(api_base, page_id, timeout_seconds)
    views = _collection_views(blocks)

    rows: list[tuple[str, dict[str, Any], dict[str, str]]] = []
    seen_row_ids: set[str] = set()
    limitations: list[str] = []
    if has_more:
        limitations.append(
            f"Notion page {page_id} has more than {MAX_PAGE_CHUNKS} loadPageChunk chunks; databases on later chunks may be missing."
        )
    for collection_id, view_id, space_id in views:
        result = http.post_json(
            f"{api_base}/queryCollection",
            {
                "collection": {"id": collection_id, "spaceId": space_id},
                "collectionView": {"id": view_id, "spaceId": space_id},
                "loader": {
                    "type": "reducer",
                    "reducers": {"collection_group_results": {"type": "results", "limit": ROW_LIMIT}},
                    "searchQuery": "",
                    "userTimeZone": "UTC",
                },
            },
            timeout_seconds,
        )
        # A valid empty database still returns `blockIds: []`; a response without
        # that list is an unexpected shape and must not read as "no jobs".
        group = _nested_dict(result, "result", "reducerResults", "collection_group_results")
        block_ids = group.get("blockIds") if group is not None else None
        record_map = result.get("recordMap") if isinstance(result, dict) else None
        if not isinstance(block_ids, list) or not isinstance(record_map, dict):
            limitations.append(f"Notion collection {collection_id} returned an unexpected queryCollection response.")
            continue
        collection = _record_value((record_map.get("collection") or {}).get(collection_id, {}))
        schema = {key: spec.get("name", key) for key, spec in (collection.get("schema") or {}).items() if isinstance(spec, dict)}
        if len(block_ids) >= ROW_LIMIT:
            limitations.append(f"Notion collection {collection_id} returned the {ROW_LIMIT}-row query limit; later rows may be missing.")
        unresolved = 0
        for block_id in block_ids:
            if not isinstance(block_id, str) or block_id in seen_row_ids:
                continue
            seen_row_ids.add(block_id)
            row = _record_value((record_map.get("block") or {}).get(block_id, {}))
            if not isinstance(row.get("properties"), dict):
                unresolved += 1
                continue
            rows.append((block_id, row, schema))
        if unresolved:
            limitations.append(f"{unresolved} Notion row(s) in collection {collection_id} did not resolve to a readable record.")

    if not views:
        limitations.append("No Notion database was found on the page.")

    candidates_by_url: dict[str, Candidate] = {}
    for row_id, row, schema in rows:
        properties = row.get("properties") or {}
        title = notion_rich_text(properties.get("title")) or "unknown"
        fields = {
            schema.get(key, key).strip(): notion_rich_text(value)
            for key, value in properties.items()
            if key != "title" and notion_rich_text(value)
        }
        searchable_text = " ".join([title, *fields.values()])
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not matched_terms:
            continue
        location = fields.get("Location", "") or "unknown"
        notes = "; ".join(["Enumerated through Notion site database", *(f"{name}: {value}" for name, value in fields.items())])
        helpers.merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=f"{parsed.scheme or 'https'}://{parsed.netloc}/{row_id.replace('-', '')}",
                source_url=source.url,
                location=location,
                remote=helpers.infer_remote_status(location),
                matched_terms=matched_terms,
                notes=notes,
            ),
        )

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="partial" if limitations else "complete",
        listing_pages_scanned=1,
        search_terms_tried=terms,
        result_pages_scanned=f"collections={len(views)}",
        direct_job_pages_opened=0,
        enumerated_jobs=len(rows),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("notion_site",), discover=discover_notion_site)
