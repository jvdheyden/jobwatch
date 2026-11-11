from __future__ import annotations

import pytest

from discover import http
from discover.core import Candidate, Coverage, SourceConfig, enrich_candidate_descriptions
from discover.sources import notion

PAGE_ID = "a837ed49-48ec-466f-b9e1-082dbf13655c"

# Mirrors the real public notion.site responses: records nested as
# {"value": {"value": ..., "role": ...}}, a date mention in rich text, and
# schema keys that differ from the property display names.
PAGE_CHUNK = {
    "recordMap": {
        "block": {
            PAGE_ID: {"value": {"value": {"id": PAGE_ID, "type": "page"}, "role": "reader"}},
            "8e35ef25": {
                "value": {
                    "value": {
                        "id": "8e35ef25",
                        "type": "collection_view",
                        "space_id": "space-1",
                        "collection_id": "coll-1",
                        "view_ids": ["view-1", "view-2"],
                    },
                    "role": "reader",
                }
            },
        }
    }
}
QUERY_RESULT = {
    "result": {"reducerResults": {"collection_group_results": {"blockIds": ["3979f6bf-423f-80db-8cf6-edb1b2fbfc0f"]}}},
    "recordMap": {
        "collection": {
            "coll-1": {
                "value": {
                    "value": {
                        "schema": {
                            "title": {"name": "Name", "type": "title"},
                            "S4Uj": {"name": "Location", "type": "multi_select"},
                            "GrBl": {"name": "Deadline 1 ", "type": "date"},
                        }
                    }
                }
            }
        },
        "block": {
            "3979f6bf-423f-80db-8cf6-edb1b2fbfc0f": {
                "value": {
                    "value": {
                        "id": "3979f6bf-423f-80db-8cf6-edb1b2fbfc0f",
                        "properties": {
                            "title": [["Head of Venture Growth and Funding"]],
                            "S4Uj": [["London"]],
                            "GrBl": [["‣", [["d", {"type": "date", "start_date": "2026-07-31"}]]]],
                        },
                    },
                    "role": "reader",
                }
            }
        },
    },
}


def _source() -> SourceConfig:
    return SourceConfig(
        source="Zinc VC",
        url="https://zinc-hub.notion.site/Careers-at-Zinc-VC-a837ed4948ec466fb9e1082dbf13655c",
        discovery_mode="notion_site",
        last_checked=None,
        cadence_group="every_run",
    )


def test_reads_embedded_database_rows_with_property_notes(monkeypatch):
    calls: list[tuple[str, dict]] = []

    def fake_post_json(url: str, payload: dict, timeout_seconds: int, headers=None):
        del timeout_seconds, headers
        calls.append((url, payload))
        return PAGE_CHUNK if url.endswith("/loadPageChunk") else QUERY_RESULT

    monkeypatch.setattr(http, "post_json", fake_post_json)

    coverage = notion.discover_notion_site(_source(), ["venture"], 5)

    assert [url for url, _ in calls] == [
        "https://zinc-hub.notion.site/api/v3/loadPageChunk",
        "https://zinc-hub.notion.site/api/v3/queryCollection",
    ]
    assert calls[0][1]["pageId"] == PAGE_ID
    assert calls[1][1]["collectionView"] == {"id": "view-1", "spaceId": "space-1"}
    assert coverage.status == "complete"
    [candidate] = coverage.candidates
    assert candidate.title == "Head of Venture Growth and Funding"
    assert candidate.url == "https://zinc-hub.notion.site/3979f6bf423f80db8cf6edb1b2fbfc0f"
    assert candidate.location == "London"
    assert "Deadline 1: 2026-07-31" in candidate.notes


def test_rejects_url_without_page_id():
    with pytest.raises(ValueError):
        notion.notion_page_id("https://zinc-hub.notion.site/Careers")


def _install(monkeypatch, query_result):
    monkeypatch.setattr(
        http,
        "post_json",
        lambda url, payload, timeout_seconds, headers=None: PAGE_CHUNK if url.endswith("/loadPageChunk") else query_result,
    )


def test_page_chunk_without_record_map_raises(monkeypatch):
    monkeypatch.setattr(http, "post_json", lambda url, payload, timeout_seconds, headers=None: {"errorId": "x"})

    with pytest.raises(ValueError, match="recordMap"):
        notion.discover_notion_site(_source(), ["venture"], 5)


def test_query_without_block_ids_is_partial_not_an_empty_board(monkeypatch):
    _install(monkeypatch, {"result": {"reducerResults": {}}, "recordMap": {}})

    coverage = notion.discover_notion_site(_source(), ["venture"], 5)

    assert coverage.status == "partial"
    assert coverage.enumerated_jobs == 0
    assert coverage.limitations == ["Notion collection coll-1 returned an unexpected queryCollection response."]


def test_valid_empty_database_is_complete(monkeypatch):
    _install(monkeypatch, {"result": {"reducerResults": {"collection_group_results": {"blockIds": []}}}, "recordMap": {}})

    coverage = notion.discover_notion_site(_source(), ["venture"], 5)

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 0


def test_block_ids_without_readable_rows_are_flagged(monkeypatch):
    group = {"blockIds": ["3979f6bf-423f-80db-8cf6-edb1b2fbfc0f", "missing-row-id"]}
    _install(monkeypatch, QUERY_RESULT | {"result": {"reducerResults": {"collection_group_results": group}}})

    coverage = notion.discover_notion_site(_source(), ["venture"], 5)

    assert [candidate.title for candidate in coverage.candidates] == ["Head of Venture Growth and Funding"]
    assert coverage.status == "partial"
    assert coverage.limitations == ["1 Notion row(s) in collection coll-1 did not resolve to a readable record."]


ROW_ID = "3979f6bf-423f-80db-8cf6-edb1b2fbfc0f"
ROW_URL = "https://zinc-hub.notion.site/3979f6bf423f80db8cf6edb1b2fbfc0f"


def _block(block_id: str, block_type: str, title: str | None = None, content: list[str] | None = None) -> dict:
    value: dict = {"id": block_id, "type": block_type}
    if title is not None:
        value["properties"] = {"title": [[title, [["b"]]]] if block_type == "sub_header" else [[title]]}
    if content is not None:
        value["content"] = content
    return {"value": {"value": value, "role": "reader"}}


# Mirrors a real posting page chunk: the row page with nested list items, plus
# blocks that must not leak into the description (the parent careers page, its
# database view, and a sub-page linked from inside the posting).
ROW_CHUNK = {
    "cursor": {"stack": []},
    "recordMap": {
        "block": {
            ROW_ID: _block(ROW_ID, "page", "Head of Venture Growth and Funding", ["b1", "b2", "b3", "b4"]),
            "b1": _block("b1", "text", "About Zinc"),
            "b2": _block("b2", "sub_header", "The Role"),
            "b3": _block("b3", "bulleted_list", "Build the funder community", ["b3a"]),
            "b3a": _block("b3a", "bulleted_list", "Own co-investor relationships"),
            "b4": _block("b4", "page", "Unrelated sub-page", ["b4a"]),
            "b4a": _block("b4a", "text", "Sub-page body"),
            PAGE_ID: _block(PAGE_ID, "page", "Careers at Zinc VC", ["8e35ef25"]),
            "8e35ef25": _block("8e35ef25", "collection_view"),
        }
    },
}


def _notion_coverage(candidates: list) -> Coverage:
    return Coverage(
        source="Zinc VC",
        source_url=_source().url,
        discovery_mode="notion_site",
        cadence_group="every_run",
        last_checked=None,
        due_today=True,
        status="complete",
        listing_pages_scanned=1,
        search_terms_tried=["venture"],
        result_pages_scanned="collections=1",
        direct_job_pages_opened=0,
        enumerated_jobs=len(candidates),
        matched_jobs=len(candidates),
        limitations=[],
        candidates=candidates,
    )


def _row_candidate() -> Candidate:
    return Candidate(employer="Zinc VC", title="Head of Venture Growth and Funding", url=ROW_URL, source_url=_source().url)


def _forbid_html_fetch(monkeypatch):
    def fail(url, timeout_seconds, headers=None):
        raise AssertionError(f"Notion postings must not fall back to an HTML fetch: {url}")

    monkeypatch.setattr(http, "fetch_text", fail)


def test_enrichment_reads_posting_blocks_in_document_order(monkeypatch):
    _forbid_html_fetch(monkeypatch)
    payloads: list[dict] = []

    def fake_post_json(url, payload, timeout_seconds, headers=None):
        assert url == "https://zinc-hub.notion.site/api/v3/loadPageChunk"
        payloads.append(payload)
        return ROW_CHUNK

    monkeypatch.setattr(http, "post_json", fake_post_json)
    candidate = _row_candidate()
    coverage = _notion_coverage([candidate])

    enrich_candidate_descriptions(coverage, 5)

    assert payloads[0]["pageId"] == ROW_ID
    assert candidate.description == "About Zinc The Role Build the funder community Own co-investor relationships"
    assert "Sub-page body" not in candidate.description
    assert "Careers at Zinc VC" not in candidate.description
    assert coverage.limitations == []


def test_enrichment_follows_page_chunk_cursor(monkeypatch):
    _forbid_html_fetch(monkeypatch)
    first = {
        "cursor": {"stack": [[{"table": "block", "id": ROW_ID, "index": 1}]]},
        "recordMap": {"block": {ROW_ID: _block(ROW_ID, "page", "Role", ["c1", "c2"]), "c1": _block("c1", "text", "First chunk")}},
    }
    second = {"cursor": {"stack": []}, "recordMap": {"block": {"c2": _block("c2", "text", "Second chunk")}}}
    chunks: list[int] = []

    def fake_post_json(url, payload, timeout_seconds, headers=None):
        chunks.append(payload["chunkNumber"])
        return first if payload["chunkNumber"] == 0 else second

    monkeypatch.setattr(http, "post_json", fake_post_json)
    candidate = _row_candidate()

    enrich_candidate_descriptions(_notion_coverage([candidate]), 5)

    assert chunks == [0, 1]
    assert candidate.description == "First chunk Second chunk"


def test_enrichment_truncates_long_posting_text(monkeypatch):
    _forbid_html_fetch(monkeypatch)
    monkeypatch.setattr(http, "post_json", lambda url, payload, timeout_seconds, headers=None: ROW_CHUNK)
    candidate = _row_candidate()

    enrich_candidate_descriptions(_notion_coverage([candidate]), 5, char_budget=20)

    assert candidate.description_truncated is True
    assert len(candidate.description) <= 20


@pytest.mark.parametrize(
    "response",
    [
        {"errorId": "notion-error"},
        {"cursor": {"stack": []}, "recordMap": {"block": {}}},
        {"cursor": {"stack": []}, "recordMap": {"block": {ROW_ID: _block(ROW_ID, "page", "Role", ["gone"])}}},
        {"cursor": {"stack": []}, "recordMap": {"block": {ROW_ID: _block(ROW_ID, "page", "Role", [])}}},
    ],
    ids=["no-record-map", "row-missing", "child-missing", "empty-page"],
)
def test_enrichment_failures_leave_description_empty_and_record_a_limitation(monkeypatch, response):
    _forbid_html_fetch(monkeypatch)
    monkeypatch.setattr(http, "post_json", lambda url, payload, timeout_seconds, headers=None: response)
    candidate = _row_candidate()
    coverage = _notion_coverage([candidate])

    enrich_candidate_descriptions(coverage, 5)

    assert candidate.description == ""
    assert coverage.candidates == [candidate]
    assert coverage.limitations == ["JD fetch failed for 1 candidate(s)"]


def test_enrichment_request_error_does_not_fall_back_to_html(monkeypatch):
    _forbid_html_fetch(monkeypatch)

    def raise_url_error(url, payload, timeout_seconds, headers=None):
        raise OSError("network down")

    monkeypatch.setattr(http, "post_json", raise_url_error)
    candidate = _row_candidate()
    coverage = _notion_coverage([candidate])

    enrich_candidate_descriptions(coverage, 5)

    assert candidate.description == ""
    assert coverage.limitations == ["JD fetch failed for 1 candidate(s)"]
