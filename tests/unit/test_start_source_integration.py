import json
from pathlib import Path
import pytest
from scripts import start_source_integration

from unittest.mock import patch

def test_get_eligible_sources_selects_pending_sources(tmp_path):
    tracks_dir = tmp_path / "tracks"
    track_dir = tracks_dir / "test_track"
    track_dir.mkdir(parents=True)
    
    sources_json = track_dir / "sources.json"
    sources_json.write_text(json.dumps({
        "schema_version": 1,
        "track": "test_track",
        "track_terms": [],
        "sources": [
            {"id": "eligible1", "name": "Eligible 1", "url": "url1", "cadence_group": "every_run", "discovery_mode": "html"},
            {"id": "eligible2", "name": "Eligible 2", "url": "url2", "cadence_group": "every_run", "discovery_mode": "html"},
            {"id": "ignored", "name": "Ignored", "url": "url3", "cadence_group": "every_run", "discovery_mode": "html"},
        ]
    }))
    
    source_state_json = track_dir / "source_state.json"
    source_state_json.write_text(json.dumps({
        "schema_version": 1,
        "track": "test_track",
        "sources": {
            "eligible1": {"integration": {"status": "pending", "priority": 10}},
            "eligible2": {"integration": {"status": "integration_needed", "priority": 5}},
            "ignored": {"integration": {"status": "pass"}},
        }
    }))
    
    with patch("scripts.start_source_integration.ROOT", tmp_path):
        # Test --all-eligible
        sources = start_source_integration.get_eligible_sources(
            "test_track", source_query=None, limit=None, all_eligible=True, today="2026-04-26"
        )
        assert sources == ["eligible1", "eligible2"]
        
        # Test --limit 1
        sources = start_source_integration.get_eligible_sources(
            "test_track", source_query=None, limit=1, all_eligible=False, today="2026-04-26"
        )
        assert sources == ["eligible1"]
        
        # Test --source
        sources = start_source_integration.get_eligible_sources(
            "test_track", source_query="Eligible 2", limit=None, all_eligible=False, today="2026-04-26"
        )
        assert sources == ["eligible2"]
