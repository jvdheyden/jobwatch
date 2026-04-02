from __future__ import annotations

from datetime import date

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
