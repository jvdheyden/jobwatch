"""Small SAP OData v2 helpers for deterministic job-source discovery."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode


TextFetcher = Callable[[str, int], str]
JsonFetcher = Callable[[str, int], Any]


@dataclass(frozen=True)
class SapODataScan:
    rows: list[dict[str, Any]]
    declared_total: int
    pages_scanned: int
    stopped_early: bool = False


def sap_odata_string_literal(value: str) -> str:
    return "'" + (value or "").replace("'", "''") + "'"


def build_sap_odata_url(service_root: str, resource_path: str, params: list[tuple[str, str]] | None = None) -> str:
    url = service_root.rstrip("/") + "/" + resource_path.lstrip("/")
    if not params:
        return url
    return url + "?" + urlencode(params, quote_via=quote)


def extract_sap_odata_results(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    value = payload.get("value")
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    data = payload.get("d")
    if isinstance(data, dict):
        results = data.get("results")
        if isinstance(results, list):
            return [item for item in results if isinstance(item, dict)]
    return []


def extract_sap_odata_entity(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("d")
    if isinstance(data, dict):
        if isinstance(data.get("results"), list):
            return {}
        return data
    return payload


def build_sap_odata_count_url(service_root: str, entity_set: str, filter_expression: str) -> str:
    return build_sap_odata_url(service_root, f"{entity_set}/$count", [("$filter", filter_expression)])


def build_sap_odata_list_url(
    service_root: str,
    entity_set: str,
    filter_expression: str,
    select_fields: tuple[str, ...],
    top: int,
    skip: int,
) -> str:
    return build_sap_odata_url(
        service_root,
        entity_set,
        [
            ("$filter", filter_expression),
            ("$select", ",".join(select_fields)),
            ("$top", str(top)),
            ("$skip", str(skip)),
            ("$format", "json"),
        ],
    )


def build_sap_odata_entity_url(
    service_root: str,
    entity_set: str,
    key_expression: str,
    select_fields: tuple[str, ...],
) -> str:
    return build_sap_odata_url(
        service_root,
        f"{entity_set}({key_expression})",
        [
            ("$select", ",".join(select_fields)),
            ("$format", "json"),
        ],
    )


def fetch_sap_odata_count(
    service_root: str,
    entity_set: str,
    filter_expression: str,
    timeout_seconds: int,
    text_fetcher: TextFetcher,
) -> int:
    count_text = text_fetcher(build_sap_odata_count_url(service_root, entity_set, filter_expression), timeout_seconds)
    return int(" ".join(count_text.split()))


def fetch_sap_odata_page(
    service_root: str,
    entity_set: str,
    filter_expression: str,
    select_fields: tuple[str, ...],
    top: int,
    skip: int,
    timeout_seconds: int,
    json_fetcher: JsonFetcher,
) -> list[dict[str, Any]]:
    payload = json_fetcher(
        build_sap_odata_list_url(service_root, entity_set, filter_expression, select_fields, top, skip),
        timeout_seconds,
    )
    return extract_sap_odata_results(payload)


def fetch_sap_odata_entity(
    service_root: str,
    entity_set: str,
    key_expression: str,
    select_fields: tuple[str, ...],
    timeout_seconds: int,
    json_fetcher: JsonFetcher,
) -> dict[str, Any]:
    payload = json_fetcher(
        build_sap_odata_entity_url(service_root, entity_set, key_expression, select_fields),
        timeout_seconds,
    )
    return extract_sap_odata_entity(payload)


def fetch_sap_odata_all(
    service_root: str,
    entity_set: str,
    filter_expression: str,
    select_fields: tuple[str, ...],
    page_size: int,
    timeout_seconds: int,
    text_fetcher: TextFetcher,
    json_fetcher: JsonFetcher,
) -> SapODataScan:
    declared_total = fetch_sap_odata_count(
        service_root,
        entity_set,
        filter_expression,
        timeout_seconds,
        text_fetcher,
    )
    rows: list[dict[str, Any]] = []
    pages_scanned = 0
    skip = 0
    while len(rows) < declared_total:
        page_rows = fetch_sap_odata_page(
            service_root,
            entity_set,
            filter_expression,
            select_fields,
            page_size,
            skip,
            timeout_seconds,
            json_fetcher,
        )
        pages_scanned += 1
        if not page_rows:
            return SapODataScan(rows=rows, declared_total=declared_total, pages_scanned=pages_scanned, stopped_early=True)
        rows.extend(page_rows)
        skip += len(page_rows)
    return SapODataScan(rows=rows, declared_total=declared_total, pages_scanned=pages_scanned)
