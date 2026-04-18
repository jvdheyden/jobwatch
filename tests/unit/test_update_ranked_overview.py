from __future__ import annotations

import json
import sys
from datetime import date

import digest_json
import update_ranked_overview


def _write_digest_fixture(root, payload, date_stamp: str) -> None:
    digest_dir = root / "tracks" / "core_crypto" / "digests"
    artifact_dir = root / "artifacts" / "digests" / "core_crypto"
    digest_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (digest_dir / f"{date_stamp}.md").write_text("placeholder\n")
    (artifact_dir / f"{date_stamp}.json").write_text(json.dumps(payload, indent=2) + "\n")


def test_update_ranked_overview_builds_state_from_digest_json(tmp_job_agent_root, load_json_fixture, monkeypatch):
    payload = load_json_fixture("digests/core_crypto_minimal.json")
    _write_digest_fixture(tmp_job_agent_root, payload, "2026-03-29")

    monkeypatch.setattr(update_ranked_overview, "ROOT", tmp_job_agent_root)
    monkeypatch.setattr(
        update_ranked_overview,
        "digest_artifact_path",
        lambda track, stamp: tmp_job_agent_root / "artifacts" / "digests" / track / f"{stamp}.json",
    )
    monkeypatch.setattr(sys, "argv", ["update_ranked_overview.py", "--track", "core_crypto"])

    assert update_ranked_overview.main() == 0

    state_path = tmp_job_agent_root / "shared" / "ranked_jobs" / "core_crypto.json"
    overview_path = tmp_job_agent_root / "tracks" / "core_crypto" / "ranked_overview.md"
    state_payload = json.loads(state_path.read_text())

    assert state_path.exists()
    assert overview_path.exists()
    assert state_payload["track"] == "core_crypto"
    assert state_payload["jobs"][0]["company"] == "LayerZero Labs"
    assert state_payload["jobs"][0]["title"] == "Cryptographer"
    assert state_payload["jobs"][0]["fit_score"] == 9.0
    assert state_payload["jobs"][0]["date_seen_page"] == "Core Crypto Job Digest 2026-03-29"


def test_core_crypto_ranked_state_matches_digest(tmp_job_agent_root, load_json_fixture, monkeypatch):
    payload = load_json_fixture("digests/core_crypto_with_update.json")
    _write_digest_fixture(tmp_job_agent_root, payload, "2026-03-29")

    monkeypatch.setattr(update_ranked_overview, "ROOT", tmp_job_agent_root)
    monkeypatch.setattr(
        update_ranked_overview,
        "digest_artifact_path",
        lambda track, stamp: tmp_job_agent_root / "artifacts" / "digests" / track / f"{stamp}.json",
    )
    monkeypatch.setattr(sys, "argv", ["update_ranked_overview.py", "--track", "core_crypto"])

    assert update_ranked_overview.main() == 0

    expected_roles = digest_json.extract_ranked_roles(payload)
    expected = sorted(
        (
            role["company"],
            role["title"],
            role["url"],
            float(role["fit_score"]),
            "Core Crypto Job Digest 2026-03-29",
        )
        for role in expected_roles
    )

    state_payload = json.loads((tmp_job_agent_root / "shared" / "ranked_jobs" / "core_crypto.json").read_text())
    actual = sorted(
        (
            role["company"],
            role["title"],
            role["url"],
            float(role["fit_score"]),
            role["date_seen_page"],
        )
        for role in state_payload["jobs"]
    )

    assert actual == expected


def test_render_markdown_filters_stale_jobs_when_as_of_given(tmp_path):
    fresh = update_ranked_overview.RankedJob(
        job_key="fresh",
        company="Fresh Corp",
        title="Fresh Role",
        url="https://example.com/fresh",
        fit_score=9.0,
        date_seen="2026-04-10",
        date_seen_page="Core Crypto Job Digest 2026-04-10",
        last_seen="2026-04-10",
        times_seen=1,
    )
    stale = update_ranked_overview.RankedJob(
        job_key="stale",
        company="Stale Corp",
        title="Stale Role",
        url="https://example.com/stale",
        fit_score=8.0,
        date_seen="2026-03-01",
        date_seen_page="Core Crypto Job Digest 2026-03-01",
        last_seen="2026-03-01",
        times_seen=1,
    )
    state_path = tmp_path / "shared" / "ranked_jobs" / "core_crypto.json"
    state_path.parent.mkdir(parents=True)
    state_path.touch()

    try:
        original_root = update_ranked_overview.ROOT
        update_ranked_overview.ROOT = tmp_path
        rendered = update_ranked_overview.render_markdown(
            "core_crypto",
            [fresh, stale],
            state_path,
            as_of=date(2026, 4, 18),
        )
    finally:
        update_ranked_overview.ROOT = original_root

    assert "Fresh Role" in rendered
    assert "Stale Role" not in rendered
    assert "Jobs last seen within 30 days: 1 (of 2 in state)" in rendered
