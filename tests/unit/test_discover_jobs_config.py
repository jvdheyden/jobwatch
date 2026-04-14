from __future__ import annotations

import json
from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest

import discover_jobs
from source_config import SourceConfigError


def test_load_track_config_reads_json_config_and_state(tmp_path, monkeypatch):
    track_dir = tmp_path / "tracks" / "monthly_demo"
    track_dir.mkdir(parents=True)
    (track_dir / "sources.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "track": "monthly_demo",
                "track_terms": ["cryptography"],
                "sources": [
                    {
                        "id": "daily",
                        "name": "Daily",
                        "url": "https://example.com/daily",
                        "discovery_mode": "html",
                        "cadence_group": "every_run",
                    },
                    {
                        "id": "three_day",
                        "name": "Three-day",
                        "url": "https://example.com/three",
                        "discovery_mode": "html",
                        "cadence_group": "every_3_runs",
                    },
                    {
                        "id": "monthly",
                        "name": "Monthly",
                        "url": "https://example.com/monthly",
                        "discovery_mode": "html",
                        "cadence_group": "every_month",
                        "search_terms": {"mode": "override", "terms": ["privacy"]},
                        "filters": {"location": ["Berlin, Germany", "Munich, Germany"], "degree": ["Ph.D."]},
                    },
                ],
            }
        )
        + "\n"
    )
    (track_dir / "source_state.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "track": "monthly_demo",
                "sources": {
                    "daily": {"last_checked": "2026-04-01"},
                    "three_day": {"last_checked": "2026-04-01"},
                    "monthly": {"last_checked": "2026-03-15"},
                },
            }
        )
        + "\n"
    )

    monkeypatch.setattr(discover_jobs, "ROOT", tmp_path)

    sources, track_terms, source_terms = discover_jobs.load_track_config("monthly_demo")

    cadence_by_source = {source.source: source.cadence_group for source in sources}
    assert cadence_by_source == {
        "Daily": "every_run",
        "Three-day": "every_3_runs",
        "Monthly": "every_month",
    }
    assert track_terms == ["cryptography"]
    assert source_terms["monthly"].mode == "override"
    assert source_terms["monthly"].terms == ["privacy"]
    last_checked_by_source = {source.source: source.last_checked for source in sources}
    assert last_checked_by_source["Daily"] == "2026-04-01"
    assert last_checked_by_source["Monthly"] == "2026-03-15"
    filters_by_source = {source.source: source.filters for source in sources}
    assert filters_by_source["Daily"] == {}
    assert filters_by_source["Monthly"] == {
        "location": ["Berlin, Germany", "Munich, Germany"],
        "degree": ["Ph.D."],
    }


def test_load_track_config_fails_without_json_config(tmp_path, monkeypatch):
    track_dir = tmp_path / "tracks" / "legacy_demo"
    track_dir.mkdir(parents=True)
    (track_dir / "sources.md").write_text("# Legacy only\n")
    monkeypatch.setattr(discover_jobs, "ROOT", tmp_path)

    with pytest.raises(SourceConfigError, match="sources.json"):
        discover_jobs.load_track_config("legacy_demo")


def test_source_to_dict_includes_filters():
    source = discover_jobs.SourceConfig(
        source="Google",
        url="https://www.google.com/about/careers/applications/jobs/results",
        discovery_mode="browser",
        last_checked=None,
        cadence_group="every_3_runs",
        filters={"location": ["Munich, Germany"], "degree": ["Ph.D."]},
        source_id="google",
    )

    payload = discover_jobs.source_to_dict(
        source,
        date(2026, 4, 13),
        ["cryptography"],
        {},
    )

    assert payload["source_id"] == "google"
    assert payload["filters"] == {
        "location": ["Munich, Germany"],
        "degree": ["Ph.D."],
    }


def test_google_search_url_uses_configured_location_and_degree_filters():
    source = discover_jobs.SourceConfig(
        source="Google",
        url="https://www.google.com/about/careers/applications/jobs/results",
        discovery_mode="browser",
        last_checked=None,
        cadence_group="every_3_runs",
        filters={
            "location": ["San Francisco, CA, USA", "New York, NY, USA"],
            "degree": ["Ph.D."],
        },
    )

    url = discover_jobs.google_search_url(source, "cryptography", 2)
    query = parse_qs(urlparse(url).query)

    assert query["q"] == ["cryptography"]
    assert query["location"] == ["San Francisco, CA, USA", "New York, NY, USA"]
    assert query["degree"] == ["DOCTORATE"]
    assert query["page"] == ["2"]
    assert "London, UK" not in query["location"]


def test_google_search_url_preserves_default_locations_without_configured_filters():
    source = discover_jobs.SourceConfig(
        source="Google",
        url="https://www.google.com/about/careers/applications/jobs/results",
        discovery_mode="browser",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    url = discover_jobs.google_search_url(source, "cryptography", 1)
    query = parse_qs(urlparse(url).query)

    assert query["location"] == list(discover_jobs.GOOGLE_LOCATION_FILTERS)
    assert "degree" not in query


def test_google_filter_note_reports_configured_filters():
    source = discover_jobs.SourceConfig(
        source="Google",
        url="https://www.google.com/about/careers/applications/jobs/results",
        discovery_mode="browser",
        last_checked=None,
        cadence_group="every_3_runs",
        filters={"location": ["Zurich, Switzerland"], "degree": ["Ph.D."]},
    )

    assert discover_jobs.google_filter_note(source) == "locations=Zurich, Switzerland degree=Ph.D."


def test_source_due_today_supports_monthly_cadence():
    source = discover_jobs.SourceConfig(
        source="Monthly",
        url="https://example.com/monthly",
        discovery_mode="html",
        last_checked="2026-04-01",
        cadence_group="every_month",
    )

    assert discover_jobs.source_due_today(source, date(2026, 4, 30)) is False
    assert discover_jobs.source_due_today(source, date(2026, 5, 1)) is True
