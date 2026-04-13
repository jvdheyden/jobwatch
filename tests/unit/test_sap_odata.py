from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import sap_odata


def test_sap_odata_url_encodes_filters_and_literals():
    literal = sap_odata.sap_odata_string_literal("O'Neil")
    assert literal == "'O''Neil'"

    url = sap_odata.build_sap_odata_list_url(
        "https://example.com/odata/",
        "Jobs",
        f"(Name eq {literal})",
        ("Title", "PinstGuid"),
        10,
        20,
    )

    assert "%24filter=" in url
    query = parse_qs(urlparse(url).query)
    assert query["$filter"] == ["(Name eq 'O''Neil')"]
    assert query["$select"] == ["Title,PinstGuid"]
    assert query["$top"] == ["10"]
    assert query["$skip"] == ["20"]
    assert query["$format"] == ["json"]


def test_sap_odata_extracts_v2_and_v4_json_shapes():
    assert sap_odata.extract_sap_odata_results({"d": {"results": [{"id": 1}, "ignored"]}}) == [{"id": 1}]
    assert sap_odata.extract_sap_odata_results({"value": [{"id": 2}]}) == [{"id": 2}]
    assert sap_odata.extract_sap_odata_entity({"d": {"id": 3}}) == {"id": 3}
    assert sap_odata.extract_sap_odata_entity({"id": 4}) == {"id": 4}


def test_fetch_sap_odata_all_paginates_until_count():
    rows = [{"id": 1}, {"id": 2}, {"id": 3}]
    requested_skips: list[int] = []

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        assert timeout_seconds == 5
        assert urlparse(url).path.endswith("/Jobs/$count")
        return " 3\n"

    def fake_fetch_json(url: str, timeout_seconds: int):
        assert timeout_seconds == 5
        query = parse_qs(urlparse(url).query)
        skip = int(query["$skip"][0])
        top = int(query["$top"][0])
        requested_skips.append(skip)
        return {"d": {"results": rows[skip : skip + top]}}

    scan = sap_odata.fetch_sap_odata_all(
        "https://example.com/odata/",
        "Jobs",
        "(Language eq 'D')",
        ("Title",),
        2,
        5,
        fake_fetch_text,
        fake_fetch_json,
    )

    assert scan.rows == rows
    assert scan.declared_total == 3
    assert scan.pages_scanned == 2
    assert not scan.stopped_early
    assert requested_skips == [0, 2]


def test_fetch_sap_odata_all_marks_empty_page_as_stopped_early():
    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        return "3"

    def fake_fetch_json(url: str, timeout_seconds: int):
        query = parse_qs(urlparse(url).query)
        if query["$skip"] == ["0"]:
            return {"d": {"results": [{"id": 1}]}}
        return {"d": {"results": []}}

    scan = sap_odata.fetch_sap_odata_all(
        "https://example.com/odata/",
        "Jobs",
        "(Language eq 'D')",
        ("Title",),
        2,
        5,
        fake_fetch_text,
        fake_fetch_json,
    )

    assert scan.rows == [{"id": 1}]
    assert scan.declared_total == 3
    assert scan.pages_scanned == 2
    assert scan.stopped_early
