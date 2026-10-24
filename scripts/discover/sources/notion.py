"""Public Notion site provider for careers pages built from a Notion database.

Supported discovery modes:
- `notion_site`

Expected source URL shape:
- `https://<workspace>.notion.site/<Page-Title>-<32-hex-page-id>`

Notion renders these pages client-side and job cards are not links, so the
provider reads the page through the site's public `/api/v3` endpoints
(`loadPageChunk`, then `queryCollection` for each embedded database). These
endpoints are undocumented and may change.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


PAGE_ID_RE = re.compile(r"([0-9a-f]{32})(?:[/?#]|$)", re.IGNORECASE)
ROW_LIMIT = 200


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


def _collection_views(record_map: dict[str, Any]) -> list[tuple[str, str, str]]:
    views: list[tuple[str, str, str]] = []
    for record in (record_map.get("block") or {}).values():
        block = _record_value(record)
        if block.get("type") not in {"collection_view", "collection_view_page"}:
            continue
        view_ids = block.get("view_ids") or []
        if block.get("collection_id") and view_ids and block.get("space_id"):
            views.append((block["collection_id"], view_ids[0], block["space_id"]))
    return views


def discover_notion_site(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    parsed = urlparse(source.url)
    api_base = f"{parsed.scheme or 'https'}://{parsed.netloc}/api/v3"
    page_id = notion_page_id(source.url)
    page = http.post_json(
        f"{api_base}/loadPageChunk",
        {"pageId": page_id, "limit": 100, "cursor": {"stack": []}, "chunkNumber": 0, "verticalColumns": False},
        timeout_seconds,
    )
    page_record_map = page.get("recordMap") if isinstance(page, dict) else {}
    views = _collection_views(page_record_map or {})

    rows: list[tuple[dict[str, Any], dict[str, str]]] = []
    seen_row_ids: set[str] = set()
    limitations: list[str] = []
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
        if not isinstance(result, dict):
            continue
        record_map = result.get("recordMap") or {}
        collection = _record_value((record_map.get("collection") or {}).get(collection_id, {}))
        schema = {key: spec.get("name", key) for key, spec in (collection.get("schema") or {}).items() if isinstance(spec, dict)}
        group = ((result.get("result") or {}).get("reducerResults") or {}).get("collection_group_results") or {}
        block_ids = [block_id for block_id in group.get("blockIds") or [] if isinstance(block_id, str)]
        if len(block_ids) >= ROW_LIMIT:
            limitations.append(f"Notion collection {collection_id} returned the {ROW_LIMIT}-row query limit; later rows may be missing.")
        for block_id in block_ids:
            if block_id in seen_row_ids:
                continue
            seen_row_ids.add(block_id)
            row = _record_value((record_map.get("block") or {}).get(block_id, {}))
            if row:
                rows.append((row, schema))

    if not views:
        limitations.append("No Notion database was found on the page.")

    candidates_by_url: dict[str, Candidate] = {}
    for row, schema in rows:
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
                url=f"{parsed.scheme or 'https'}://{parsed.netloc}/{str(row.get('id', '')).replace('-', '')}",
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
