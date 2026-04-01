from __future__ import annotations

import json
import sys

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
