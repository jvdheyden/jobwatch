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


def test_mutate_source_state_merges_on_fresh_state(tmp_path):
    from source_config import mutate_source_state

    state_path = tmp_path / "source_state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "track": "demo",
                "sources": {
                    "source_a": {"last_checked": "2026-04-01"},
                    "source_b": {
                        "last_checked": "2026-04-02",
                        "integration": {"status": "pending", "priority": 10},
                    },
                },
            }
        )
        + "\n"
    )

    def mutate(current):
        current["source_a"] = {"last_checked": "2026-04-14"}

    written = mutate_source_state(state_path, "demo", ["source_a", "source_b", "source_c"], mutate)

    on_disk = json.loads(state_path.read_text())["sources"]
    assert on_disk["source_a"]["last_checked"] == "2026-04-14"
    # Entries the mutation does not touch are preserved, including nested metadata.
    assert on_disk["source_b"]["integration"] == {"status": "pending", "priority": 10}
    # Configured sources missing from disk are initialized minimally.
    assert on_disk["source_c"] == {"last_checked": None}
    assert written["source_a"]["last_checked"] == "2026-04-14"


def test_mutate_source_state_raises_on_invalid_state(tmp_path):
    import pytest

    from source_config import SourceConfigError, mutate_source_state

    state_path = tmp_path / "source_state.json"
    state_path.write_text(json.dumps({"schema_version": 2, "track": "demo", "sources": {}}) + "\n")

    with pytest.raises(SourceConfigError):
        mutate_source_state(state_path, "demo", ["source_a"], lambda current: None)
    # The invalid file is left untouched rather than silently reset.
    assert json.loads(state_path.read_text())["schema_version"] == 2


def _mutate_source_state_writer(track_dir: str, source_id: str, date_value: str, delay_in_mutate: float) -> None:
    """Helper for ``test_mutate_source_state_serializes_concurrent_writers``.

    Must live at module scope so multiprocessing's spawn start method can pickle it.
    """
    import time
    from pathlib import Path

    from source_config import mutate_source_state

    def mutate(current):
        time.sleep(delay_in_mutate)
        current.setdefault(source_id, {})["last_checked"] = date_value

    mutate_source_state(
        Path(track_dir) / "source_state.json",
        "demo",
        ["source_a", "source_b"],
        mutate,
    )


def test_mutate_source_state_serializes_concurrent_writers(tmp_path):
    """Two processes doing read-modify-write through the helper both land their
    updates instead of the slower reader clobbering the faster writer."""
    import multiprocessing as mp
    import time

    p1 = mp.Process(target=_mutate_source_state_writer, args=(str(tmp_path), "source_a", "2026-04-14", 0.3))
    p2 = mp.Process(target=_mutate_source_state_writer, args=(str(tmp_path), "source_b", "2026-04-15", 0.0))
    p1.start()
    # Give p1 time to acquire the lock before p2 starts contending.
    time.sleep(0.05)
    p2.start()
    p1.join(timeout=5)
    p2.join(timeout=5)
    assert not p1.is_alive() and not p2.is_alive()

    state = json.loads((tmp_path / "source_state.json").read_text())
    assert state["sources"]["source_a"]["last_checked"] == "2026-04-14"
    assert state["sources"]["source_b"]["last_checked"] == "2026-04-15"


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
