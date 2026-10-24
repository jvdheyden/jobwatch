from __future__ import annotations

import pytest

from discover import http
from discover.core import SourceConfig
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
