from __future__ import annotations

import json
from pathlib import Path

import pytest

from update_seen_jobs import (
    extract_new_roles,
    job_key,
    load_seen_jobs,
    normalize_text,
    seen_jobs_payload,
)


def test_normalize_text_strips_diacritics_and_punctuation() -> None:
    assert normalize_text("Zürich") == "zurich"
    assert normalize_text("Foo--Bar  Baz") == "foo bar baz"
    assert normalize_text("") == ""


def test_job_key_is_deterministic() -> None:
    k1 = job_key("Acme Corp", "Engineer", "https://example.com/jobs/1/")
    k2 = job_key("acme corp", "Engineer", "https://example.com/jobs/1")
    assert k1 == k2


def test_extract_new_roles_from_digest_artifact() -> None:
    artifact = {
        "runs": [
            {
                "top_matches": [
                    {
                        "company": "Acme",
                        "title": "Engineer",
                        "location": "Remote",
                        "listing_url": "https://acme.com/1",
                    }
                ],
                "other_new_roles": [
                    {
                        "company": "Beta",
                        "title": "Analyst",
                        "listing_url": "https://beta.com/2",
                    }
                ],
            }
        ]
    }
    roles = extract_new_roles(artifact, "2026-04-16")
    assert len(roles) == 2
    assert roles[0]["company"] == "Acme"
    assert roles[0]["date_seen"] == "2026-04-16"
    assert roles[1]["company"] == "Beta"
    assert roles[1]["location"] == "unknown"


def test_extract_new_roles_empty_runs() -> None:
    assert extract_new_roles({"runs": []}, "2026-04-16") == []
    assert extract_new_roles({}, "2026-04-16") == []


def test_load_seen_jobs_fresh_file(tmp_path: Path) -> None:
    assert load_seen_jobs(tmp_path / "missing.json", "demo") == []


def test_load_seen_jobs_valid(tmp_path: Path) -> None:
    path = tmp_path / "seen_jobs.json"
    path.write_text(json.dumps(seen_jobs_payload("demo", [{"date_seen": "2026-04-16", "company": "X", "title": "Y", "location": "Z", "url": "https://x.com"}])))
    jobs = load_seen_jobs(path, "demo")
    assert len(jobs) == 1
    assert jobs[0]["company"] == "X"


def test_load_seen_jobs_wrong_track(tmp_path: Path) -> None:
    path = tmp_path / "seen_jobs.json"
    path.write_text(json.dumps(seen_jobs_payload("other", [])))
    with pytest.raises(Exception, match="track must be"):
        load_seen_jobs(path, "demo")


def test_load_seen_jobs_wrong_schema(tmp_path: Path) -> None:
    path = tmp_path / "seen_jobs.json"
    path.write_text(json.dumps({"schema_version": 99, "track": "demo", "jobs": []}))
    with pytest.raises(Exception, match="schema_version"):
        load_seen_jobs(path, "demo")


def test_seen_jobs_payload_roundtrip() -> None:
    jobs = [{"date_seen": "2026-04-16", "company": "X", "title": "Y", "location": "Z", "url": "u"}]
    payload = seen_jobs_payload("demo", jobs)
    assert payload["schema_version"] == 1
    assert payload["track"] == "demo"
    assert payload["jobs"] is jobs


class TestMainIntegration:
    """End-to-end tests for the main() function via subprocess-like invocation."""

    def _run_main(self, tmp_path: Path, track: str, date: str, artifact: dict | None = None) -> int:
        import sys

        root = tmp_path / "root"
        (root / "artifacts" / "digests" / track).mkdir(parents=True, exist_ok=True)
        (root / "tracks" / track).mkdir(parents=True, exist_ok=True)

        if artifact is not None:
            artifact_path = root / "artifacts" / "digests" / track / f"{date}.json"
            artifact_path.write_text(json.dumps(artifact))

        import os
        old_root = os.environ.get("JOB_AGENT_ROOT")
        os.environ["JOB_AGENT_ROOT"] = str(root)
        old_argv = sys.argv
        sys.argv = ["update_seen_jobs.py", "--track", track, "--date", date]
        try:
            from update_seen_jobs import main
            return main()
        finally:
            sys.argv = old_argv
            if old_root is not None:
                os.environ["JOB_AGENT_ROOT"] = old_root
            else:
                os.environ.pop("JOB_AGENT_ROOT", None)

    def _seen_path(self, tmp_path: Path, track: str) -> Path:
        return tmp_path / "root" / "tracks" / track / "seen_jobs.json"

    def test_creates_fresh_seen_jobs(self, tmp_path: Path) -> None:
        artifact = {
            "runs": [{
                "top_matches": [{"company": "A", "title": "T", "listing_url": "https://a.com/1", "location": "Remote"}],
                "other_new_roles": [],
            }]
        }
        rc = self._run_main(tmp_path, "demo", "2026-04-16", artifact)
        assert rc == 0
        data = json.loads(self._seen_path(tmp_path, "demo").read_text())
        assert data["schema_version"] == 1
        assert data["track"] == "demo"
        assert len(data["jobs"]) == 1
        assert data["jobs"][0]["company"] == "A"

    def test_appends_and_deduplicates(self, tmp_path: Path) -> None:
        artifact = {
            "runs": [{
                "top_matches": [
                    {"company": "A", "title": "T", "listing_url": "https://a.com/1", "location": "Remote"},
                    {"company": "B", "title": "U", "listing_url": "https://b.com/2", "location": "Berlin"},
                ],
                "other_new_roles": [],
            }]
        }
        # First run
        self._run_main(tmp_path, "demo", "2026-04-16", artifact)
        # Second run with same artifact — should not add duplicates
        rc = self._run_main(tmp_path, "demo", "2026-04-16", artifact)
        assert rc == 0
        data = json.loads(self._seen_path(tmp_path, "demo").read_text())
        assert len(data["jobs"]) == 2

    def test_skips_when_no_artifact(self, tmp_path: Path) -> None:
        rc = self._run_main(tmp_path, "demo", "2026-04-16", artifact=None)
        assert rc == 0
        assert not self._seen_path(tmp_path, "demo").exists()
