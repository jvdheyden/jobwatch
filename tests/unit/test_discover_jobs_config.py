from __future__ import annotations

from datetime import date
from urllib.parse import parse_qs, urlparse

import discover_jobs


def test_parse_source_specific_terms_reads_nested_search_terms_section():
    text = """
## Search terms

Use these terms on searchable sources unless a source-specific search-term override says otherwise.

### Track-wide terms
- cryptography

### Source-specific search terms
- Example Source — privacy, security
- Other Source [override] — mpc, garbled circuits
""".strip()

    mapping = discover_jobs.parse_source_specific_terms(text)

    assert mapping["Example Source"].mode == "append"
    assert mapping["Example Source"].terms == ["privacy", "security"]
    assert mapping["Other Source"].mode == "override"
    assert mapping["Other Source"].terms == ["mpc", "garbled circuits"]


def test_parse_source_specific_filters_reads_nested_filter_section():
    text = """
## Search terms

### Track-wide terms
- cryptography

### Source-specific search terms
- Google — cryptography

### Source-specific filters
- Google — location: San Francisco, CA, USA; New York, NY, USA | degree: Ph.D.
- Example Source - organization: Research | job_type: Internship; Full-time
""".strip()

    mapping = discover_jobs.parse_source_specific_filters(text)

    assert mapping["Google"] == {
        "location": ["San Francisco, CA, USA", "New York, NY, USA"],
        "degree": ["Ph.D."],
    }
    assert mapping["Example Source"] == {
        "organization": ["Research"],
        "job_type": ["Internship", "Full-time"],
    }


def test_load_track_config_reads_optional_monthly_section(tmp_path, monkeypatch):
    track_dir = tmp_path / "tracks" / "monthly_demo"
    track_dir.mkdir(parents=True)
    (track_dir / "sources.md").write_text(
        """
# Demo sources

## Check every run
| source | url | discovery_mode | last_checked |
| --- | --- | --- | --- |
| Daily | https://example.com/daily | html | 2026-04-01 |

## Check every 3 runs
| source | url | discovery_mode | last_checked |
| --- | --- | --- | --- |
| Three-day | https://example.com/three | html | 2026-04-01 |

## Check every month
| source | url | discovery_mode | last_checked |
| --- | --- | --- | --- |
| Monthly | https://example.com/monthly | html | 2026-03-15 |

## Search terms

### Track-wide terms
- cryptography

### Source-specific search terms
- Monthly [override] — privacy

### Source-specific filters
- Monthly — location: Berlin, Germany; Munich, Germany | degree: Ph.D.
""".strip()
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
    assert source_terms["Monthly"].mode == "override"
    assert source_terms["Monthly"].terms == ["privacy"]
    filters_by_source = {source.source: source.filters for source in sources}
    assert filters_by_source["Daily"] == {}
    assert filters_by_source["Monthly"] == {
        "location": ["Berlin, Germany", "Munich, Germany"],
        "degree": ["Ph.D."],
    }


def test_source_to_dict_includes_filters():
    source = discover_jobs.SourceConfig(
        source="Google",
        url="https://www.google.com/about/careers/applications/jobs/results",
        discovery_mode="browser",
        last_checked=None,
        cadence_group="every_3_runs",
        filters={"location": ["Munich, Germany"], "degree": ["Ph.D."]},
    )

    payload = discover_jobs.source_to_dict(
        source,
        date(2026, 4, 13),
        ["cryptography"],
        {},
    )

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
