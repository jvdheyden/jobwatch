from __future__ import annotations

import json
import sys

import discover_jobs


def test_main_progress_logs_to_stderr_without_changing_output(tmp_path, monkeypatch, capsys):
    source = discover_jobs.SourceConfig(
        source="Example Source",
        url="https://example.com/jobs",
        discovery_mode="html",
        last_checked=None,
        cadence_group="every_run",
        source_id="example_source",
    )
    coverage = discover_jobs.Coverage(
        source="Example Source",
        source_url="https://example.com/jobs",
        discovery_mode="html",
        cadence_group="every_run",
        last_checked=None,
        due_today=False,
        status="complete",
        listing_pages_scanned=1,
        search_terms_tried=["cryptography"],
        result_pages_scanned="local_filter=1",
        direct_job_pages_opened=0,
        enumerated_jobs=1,
        matched_jobs=1,
        source_id="example_source",
        candidates=[
            discover_jobs.Candidate(
                employer="Example Co",
                title="Cryptography Engineer",
                url="https://example.com/jobs/1",
                source_url="https://example.com/jobs",
            )
        ],
    )

    monkeypatch.setattr(discover_jobs, "load_track_config", lambda _track: ([source], ["cryptography"], {}))
    monkeypatch.setattr(discover_jobs, "discover_source", lambda *_args: coverage)

    output_path = tmp_path / "discovery.json"
    latest_output_path = tmp_path / "latest.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "discover_jobs.py",
            "--track",
            "demo",
            "--today",
            "2030-01-15",
            "--output",
            str(output_path),
            "--latest-output",
            str(latest_output_path),
            "--pretty",
            "--progress",
        ],
    )

    assert discover_jobs.main() == 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Discovering source 1/1: Example Source (mode=html)" in captured.err
    assert "Completed source 1/1: Example Source (status=complete, matched=1, candidates=1)" in captured.err

    payload = json.loads(output_path.read_text())
    latest_payload = json.loads(latest_output_path.read_text())
    assert payload == latest_payload
    assert payload["track"] == "demo"
    assert payload["mode"] == "discover"
    assert payload["sources"][0]["source_id"] == "example_source"
    assert payload["sources"][0]["source"] == "Example Source"
    assert payload["sources"][0]["matched_jobs"] == 1
