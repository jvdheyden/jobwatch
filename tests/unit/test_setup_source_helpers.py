from __future__ import annotations

import json
import subprocess

import probe_career_source
import update_source_canary


def test_probe_career_source_infers_board_family_and_canaries():
    html = """
    <html><body>
      <a href="/jobs/privacy-engineer">Senior Privacy Engineer</a>
      <a href="/about">About us</a>
    </body></html>
    """

    family, mode = probe_career_source.infer_board_family("https://boards.greenhouse.io/example", html)
    candidates = probe_career_source.extract_canary_candidates(html, "https://example.com/careers", ["privacy"])

    assert family == "greenhouse"
    assert mode == "greenhouse_api"
    assert candidates == [
        {"title": "Senior Privacy Engineer", "url": "https://example.com/jobs/privacy-engineer"}
    ]


def test_update_source_canary_refreshes_state_and_preserves_history(tmp_path, monkeypatch):
    track_dir = tmp_path / "tracks" / "demo"
    track_dir.mkdir(parents=True)
    (track_dir / "sources.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "track": "demo",
                "track_terms": ["privacy"],
                "sources": [
                    {
                        "id": "example",
                        "name": "Example",
                        "url": "https://jobs.example.com",
                        "discovery_mode": "html",
                        "cadence_group": "every_run",
                    }
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
                    "example": {
                        "last_checked": None,
                        "integration": {
                            "status": "pending",
                            "canary": {
                                "status": "selected",
                                "title": "Old Role",
                                "url": "https://jobs.example.com/jobs/old",
                            },
                        },
                    }
                },
            }
        )
        + "\n"
    )

    def fake_run_discovery(root, track, source_name, today, output):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "sources": [
                        {
                            "source": "Example",
                            "candidates": [
                                {
                                    "title": "Privacy Engineer",
                                    "url": "https://jobs.example.com/jobs/new",
                                    "notes": "Build privacy systems.",
                                }
                            ],
                        }
                    ]
                }
            )
            + "\n"
        )
        return subprocess.CompletedProcess(["discover"], 0, "", "")

    monkeypatch.setattr(update_source_canary, "run_discovery", fake_run_discovery)

    ok, payload = update_source_canary.refresh_canary(
        root=tmp_path,
        track="demo",
        source_query="Example",
        today="2026-04-22",
    )

    assert ok is True
    assert payload["canary"]["title"] == "Privacy Engineer"
    state = json.loads((track_dir / "source_state.json").read_text())
    integration = state["sources"]["example"]["integration"]
    assert integration["canary"]["url"] == "https://jobs.example.com/jobs/new"
    assert integration["canary_history"][0]["title"] == "Old Role"


def test_update_source_canary_marks_missing_when_no_candidate(tmp_path, monkeypatch):
    track_dir = tmp_path / "tracks" / "demo"
    track_dir.mkdir(parents=True)
    (track_dir / "sources.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "track": "demo",
                "track_terms": ["privacy"],
                "sources": [
                    {
                        "id": "example",
                        "name": "Example",
                        "url": "https://jobs.example.com",
                        "discovery_mode": "html",
                        "cadence_group": "every_run",
                    }
                ],
            }
        )
        + "\n"
    )
    (track_dir / "source_state.json").write_text(
        json.dumps({"schema_version": 1, "track": "demo", "sources": {"example": {"last_checked": None}}})
        + "\n"
    )

    def fake_run_discovery(root, track, source_name, today, output):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"sources": [{"source": "Example", "candidates": []}]}) + "\n")
        return subprocess.CompletedProcess(["discover"], 0, "", "")

    monkeypatch.setattr(update_source_canary, "run_discovery", fake_run_discovery)

    ok, payload = update_source_canary.refresh_canary(
        root=tmp_path,
        track="demo",
        source_query="example",
        today="2026-04-22",
    )

    assert ok is False
    assert payload["status"] == "missing"
    state = json.loads((track_dir / "source_state.json").read_text())
    assert state["sources"]["example"]["integration"]["canary"]["status"] == "missing"
