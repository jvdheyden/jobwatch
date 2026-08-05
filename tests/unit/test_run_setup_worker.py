from __future__ import annotations

import json
from pathlib import Path

import pytest

import run_setup_worker
import setup_contracts


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "setup"


def _write_fake_provider(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import sys

prompt = sys.stdin.read()
begin = prompt.index("BEGIN_INPUT_JSON\\n") + len("BEGIN_INPUT_JSON\\n")
end = prompt.index("\\nEND_INPUT_JSON", begin)
input_payload = json.loads(prompt[begin:end])
input_hash = hashlib.sha256(json.dumps(input_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
log_path = Path(os.environ["FAKE_SETUP_WORKER_LOG"])
log_path.write_text(json.dumps({"args": sys.argv[1:], "prompt": prompt, "cwd": os.getcwd(), "files": sorted(os.listdir())}))
seed_url = input_payload["source_seeds"]["career_pages_or_boards"][0]
payload = {
    "schema_version": 1,
    "kind": "jobwatch_source_pack",
    "setup_id": input_payload["setup_id"],
    "input_hash": input_hash,
    "track_terms": input_payload["track"]["keep_only_keywords"],
    "recommended_sources": [{
        "id": "example_labs",
        "name": "Example Labs",
        "url": seed_url,
        "discovery_mode": "html",
        "cadence_group": "every_3_runs",
        "fit_reason": "Official seeded careers page.",
        "confidence": "high"
    }],
    "follow_up_sources": [],
    "dropped_sources": [],
    "url_corrections": [],
    "match_rule_suggestions": [],
    "recommended_source_ids": ["example_labs"],
    "decisions_needed": []
}
serialized = json.dumps(payload)
if "--output-last-message" in sys.argv:
    output = Path(sys.argv[sys.argv.index("--output-last-message") + 1])
    output.write_text(serialized)
else:
    print(json.dumps({"result": serialized}))
"""
    )
    path.chmod(0o755)


@pytest.mark.parametrize("provider", ["codex", "claude", "gemini"])
def test_source_worker_uses_fresh_artifact_only_process_and_validates_output(
    tmp_path: Path, monkeypatch, provider: str
) -> None:
    setup_path = tmp_path / "setup.json"
    setup = json.loads((FIXTURES / "setup.json").read_text())
    setup_contracts.write_setup(setup_path, setup)
    output_path = tmp_path / "source-pack.json"
    fake = tmp_path / f"fake-{provider}"
    log_path = tmp_path / f"{provider}.log"
    _write_fake_provider(fake)
    monkeypatch.setenv("FAKE_SETUP_WORKER_LOG", str(log_path))

    payload, status = run_setup_worker.run_worker(
        role="source_discovery",
        input_path=setup_path,
        output_path=output_path,
        provider=provider,
        agent_bin_value=str(fake),
        model=None,
        reasoning=None,
        timeout_seconds=30,
    )

    assert status["role"] == "source_discovery"
    assert payload == setup_contracts.load_source_pack(output_path, setup_contracts.load_setup(setup_path))
    invocation = json.loads(log_path.read_text())
    assert "JOBWATCH_SETUP_WORKER_ROLE=source_discovery" in invocation["prompt"]
    assert str(setup_path) not in invocation["prompt"]
    assert "transcript" not in invocation["prompt"].lower()
    assert invocation["cwd"] != str(tmp_path)
    assert invocation["files"] == ["output-schema.json"]
    if provider == "codex":
        assert "--ephemeral" in invocation["args"]
        assert "--search" in invocation["args"]
    elif provider == "claude":
        assert "--no-session-persistence" in invocation["args"]
    else:
        assert invocation["args"][invocation["args"].index("--approval-mode") + 1] == "plan"


def test_worker_rejects_prose_without_writing_output(tmp_path: Path) -> None:
    setup_path = tmp_path / "setup.json"
    setup_contracts.write_setup(setup_path, json.loads((FIXTURES / "setup.json").read_text()))
    output_path = tmp_path / "source-pack.json"
    fake = tmp_path / "fake-codex"
    fake.write_text(
        """#!/usr/bin/env python3
from pathlib import Path
import sys
sys.stdin.read()
output = Path(sys.argv[sys.argv.index("--output-last-message") + 1])
output.write_text("Here is the JSON you requested: {}")
"""
    )
    fake.chmod(0o755)

    with pytest.raises(setup_contracts.SetupContractError, match="prose or malformed JSON"):
        run_setup_worker.run_worker(
            role="source_discovery",
            input_path=setup_path,
            output_path=output_path,
            provider="codex",
            agent_bin_value=str(fake),
            model=None,
            reasoning=None,
            timeout_seconds=30,
        )
    assert not output_path.exists()
