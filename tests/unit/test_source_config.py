from __future__ import annotations

import json
import sys

import update_source_state


def test_update_source_state_advances_only_complete_sources(tmp_path, monkeypatch):
    track_dir = tmp_path / "tracks" / "demo"
    artifact_dir = tmp_path / "artifacts" / "discovery" / "demo"
    track_dir.mkdir(parents=True)
    artifact_dir.mkdir(parents=True)
    (track_dir / "sources.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "track": "demo",
                "track_terms": ["cryptography"],
                "sources": [
                    {
                        "id": "complete_source",
                        "name": "Complete Source",
                        "url": "https://example.com/complete",
                        "discovery_mode": "html",
                        "cadence_group": "every_run",
                    },
                    {
                        "id": "partial_source",
                        "name": "Partial Source",
                        "url": "https://example.com/partial",
                        "discovery_mode": "html",
                        "cadence_group": "every_run",
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
                "track": "demo",
                "sources": {
                    "complete_source": {"last_checked": None},
                    "partial_source": {"last_checked": "2026-04-01"},
                },
            }
        )
        + "\n"
    )
    (artifact_dir / "2026-04-14.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "track": "demo",
                "today": "2026-04-14",
                "mode": "discover",
                "sources": [
                    {"source_id": "complete_source", "status": "complete"},
                    {"source_id": "partial_source", "status": "partial"},
                ],
            }
        )
        + "\n"
    )
    monkeypatch.setattr(update_source_state, "ROOT", tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["update_source_state.py", "--track", "demo", "--date", "2026-04-14"],
    )

    assert update_source_state.main() == 0

    state = json.loads((track_dir / "source_state.json").read_text())
    assert state["sources"]["complete_source"]["last_checked"] == "2026-04-14"
    assert state["sources"]["partial_source"]["last_checked"] == "2026-04-01"
