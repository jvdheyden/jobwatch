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
                    "partial_source": {
                        "last_checked": "2026-04-01",
                        "integration": {
                            "status": "pending",
                            "priority": 10,
                            "last_attempted": "2026-04-13",
                        },
                    },
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
    assert state["sources"]["partial_source"]["integration"] == {
        "status": "pending",
        "priority": 10,
        "last_attempted": "2026-04-13",
    }


def _file_lock_writer(target_path: str, key: str, value: str, delay_after_read: float) -> None:
    """Helper for ``test_file_lock_serializes_concurrent_writers`` run in a child process.

    Must live at module scope so multiprocessing's spawn start method can pickle it.
    """
    import json
    import time
    from pathlib import Path

    from source_config import file_lock, write_json_atomic

    path = Path(target_path)
    with file_lock(path):
        current = json.loads(path.read_text())
        time.sleep(delay_after_read)
        current["entries"][key] = value
        write_json_atomic(path, current)


def test_file_lock_serializes_concurrent_writers(tmp_path):
    """Two processes that lock the same path block each other, preserving
    both their updates instead of clobbering."""
    import multiprocessing as mp
    import time

    from source_config import write_json_atomic

    target = tmp_path / "state.json"
    write_json_atomic(target, {"entries": {}})

    # Without locking, p1 reading first then p2 writing while p1 sleeps
    # would have p1 clobber p2 on its later write. With the lock, p2 blocks
    # until p1 releases, so both updates land.
    p1 = mp.Process(target=_file_lock_writer, args=(str(target), "a", "1", 0.3))
    p2 = mp.Process(target=_file_lock_writer, args=(str(target), "b", "2", 0.0))
    p1.start()
    # Give p1 time to acquire the lock before p2 starts contending.
    time.sleep(0.05)
    p2.start()
    p1.join(timeout=5)
    p2.join(timeout=5)
    assert not p1.is_alive() and not p2.is_alive()

    result = json.loads(target.read_text())
    assert result["entries"] == {"a": "1", "b": "2"}
