from __future__ import annotations

import integrate_next_source


def test_select_next_source_uses_priority_and_skips_attempted_today():
    config = {
        "sources": [
            {"id": "low", "name": "Low Priority"},
            {"id": "high", "name": "High Priority"},
            {"id": "attempted", "name": "Attempted Today"},
        ]
    }
    state = {
        "low": {"last_checked": None, "integration": {"status": "pending", "priority": 1}},
        "high": {"last_checked": None, "integration": {"status": "pending", "priority": 20}},
        "attempted": {
            "last_checked": None,
            "integration": {"status": "pending", "priority": 100, "last_attempted": "2026-04-21"},
        },
    }

    selected, reason = integrate_next_source.select_next_source(
        config,
        state,
        today="2026-04-21",
    )

    assert reason == "selected"
    assert selected["id"] == "high"


def test_select_next_source_force_allows_same_day_attempt():
    config = {"sources": [{"id": "attempted", "name": "Attempted Today"}]}
    state = {
        "attempted": {
            "last_checked": None,
            "integration": {"status": "pending", "priority": 100, "last_attempted": "2026-04-21"},
        }
    }

    selected, _reason = integrate_next_source.select_next_source(
        config,
        state,
        today="2026-04-21",
        force=True,
    )

    assert selected["id"] == "attempted"


def test_apply_config_tuning_updates_search_terms_before_code():
    config = {
        "sources": [
            {
                "id": "example",
                "name": "Example",
                "url": "https://jobs.example.com",
                "discovery_mode": "html",
                "cadence_group": "every_run",
            }
        ]
    }
    integration = {"suggested_search_terms": {"mode": "override", "terms": ["privacy engineering"]}}
    ticket = {"suggested_strategy": "config_terms_override"}

    changed, note = integrate_next_source.apply_config_tuning(
        config,
        source_id="example",
        integration=integration,
        ticket=ticket,
    )

    assert changed is True
    assert "config_terms_override" in note
    assert config["sources"][0]["search_terms"] == {
        "mode": "override",
        "terms": ["privacy engineering"],
    }


def test_apply_config_tuning_merges_native_filters():
    config = {
        "sources": [
            {
                "id": "example",
                "name": "Example",
                "url": "https://jobs.example.com",
                "discovery_mode": "browser",
                "cadence_group": "every_run",
                "filters": {"location": ["Berlin, Germany"]},
            }
        ]
    }
    integration = {"suggested_filters": {"location": ["Berlin, Germany", "Munich, Germany"], "degree": ["Ph.D."]}}
    ticket = {"suggested_strategy": "config_native_filters"}

    changed, _note = integrate_next_source.apply_config_tuning(
        config,
        source_id="example",
        integration=integration,
        ticket=ticket,
    )

    assert changed is True
    assert config["sources"][0]["filters"] == {
        "location": ["Berlin, Germany", "Munich, Germany"],
        "degree": ["Ph.D."],
    }
