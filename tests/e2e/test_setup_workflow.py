from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import threading

import run_setup_preview
import run_setup_worker
import scaffold_track
import setup_contracts


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "setup"


class _CareersHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path == "/careers":
            body = b'<html><body><a href="/jobs/crypto">Senior Cryptography Engineer</a></body></html>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/jobs/crypto":
            body = (
                b"<html><body><main>Build production cryptographic protocols in Rust. "
                b"This role is remote within Europe.</main></body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


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
role = "source_discovery" if "JOBWATCH_SETUP_WORKER_ROLE=source_discovery" in prompt else "preview_ranker"
with Path(os.environ["FAKE_SETUP_LOG"]).open("a") as handle:
    handle.write(json.dumps({"role": role, "prompt": prompt, "args": sys.argv[1:]}) + "\\n")
if role == "source_discovery":
    payload = {
        "schema_version": 1,
        "kind": "jobwatch_source_pack",
        "setup_id": input_payload["setup_id"],
        "input_hash": input_hash,
        "track_terms": ["cryptography", "privacy engineering"],
        "recommended_sources": [{
            "id": "local_careers",
            "name": "Local Careers",
            "url": input_payload["source_seeds"]["career_pages_or_boards"][0],
            "discovery_mode": "html",
            "cadence_group": "every_run",
            "fit_reason": "Official synthetic careers fixture.",
            "confidence": "high"
        }],
        "follow_up_sources": [],
        "dropped_sources": [],
        "url_corrections": [],
        "match_rule_suggestions": [],
        "recommended_source_ids": ["local_careers"],
        "decisions_needed": []
    }
else:
    judgments = []
    for candidate in input_payload["candidates"]:
        judgments.append({
            "candidate_id": candidate["candidate_id"],
            "disposition": "top_match",
            "score": 9.2,
            "recommendation": "apply_now",
            "match_reasons": ["Direct cryptography, Rust, and Europe-remote evidence."],
            "concerns": []
        })
    payload = {
        "schema_version": 1,
        "kind": "jobwatch_preview_result",
        "setup_id": input_payload["setup_id"],
        "input_hash": input_hash,
        "executive_summary": "One strong synthetic match validates the compact setup preview.",
        "recommended_actions": ["Review the synthetic role."],
        "judgments": judgments
    }
serialized = json.dumps(payload)
output = Path(sys.argv[sys.argv.index("--output-last-message") + 1])
output.write_text(serialized)
"""
    )
    path.chmod(0o755)


def test_guided_setup_uses_two_bounded_workers_and_no_model_scaffolding(
    tmp_path: Path, monkeypatch
) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CareersHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        root = tmp_path / "root"
        (root / "shared").mkdir(parents=True)
        shutil.copytree(Path(__file__).resolve().parents[2] / "shared" / "templates", root / "shared" / "templates")
        setup_dir = root / "artifacts" / "setup" / "20260720T155600Z-a1b2c3d4"
        setup_path = setup_dir / "setup.json"
        setup = json.loads((FIXTURES / "setup.json").read_text())
        setup["source_seeds"]["career_pages_or_boards"] = [
            f"http://127.0.0.1:{server.server_port}/careers"
        ]
        setup_contracts.write_setup(setup_path, setup)
        fake = tmp_path / "fake-codex"
        log_path = tmp_path / "worker.log"
        _write_fake_provider(fake)
        monkeypatch.setenv("FAKE_SETUP_LOG", str(log_path))

        pack, _ = run_setup_worker.run_worker(
            role="source_discovery",
            input_path=setup_path,
            output_path=setup_dir / "source-pack.json",
            provider="codex",
            agent_bin_value=str(fake),
            model=None,
            reasoning=None,
            timeout_seconds=30,
        )
        confirmed = setup_contracts.apply_source_selection(setup_contracts.load_setup(setup_path), pack)
        setup_contracts.write_setup(setup_path, confirmed)
        assert [json.loads(line)["role"] for line in log_path.read_text().splitlines()] == ["source_discovery"]

        scaffold = scaffold_track.scaffold_track(setup_path, root=root)
        assert scaffold["status"] == "created"
        assert [json.loads(line)["role"] for line in log_path.read_text().splitlines()] == ["source_discovery"]

        preview = run_setup_preview.run_first_preview(
            setup_path,
            root=root,
            today="2026-07-20",
            provider="codex",
            agent_bin=str(fake),
            model=None,
            reasoning=None,
            worker_timeout_seconds=30,
            discovery_timeout_seconds=30,
        )

        invocations = [json.loads(line) for line in log_path.read_text().splitlines()]
        assert [item["role"] for item in invocations] == ["source_discovery", "preview_ranker"]
        assert "Static HTML enumeration" not in invocations[1]["prompt"]
        assert "BEGIN_INPUT_JSON" in invocations[1]["prompt"]
        assert preview["candidates_ranked"] == 1
        assert Path(preview["digest_json"]).is_file()
        markdown = Path(preview["digest_markdown"]).read_text()
        assert "Senior Cryptography Engineer" in markdown
        assert "One strong synthetic match" in markdown
        assert (root / "tracks" / "applied_crypto" / "seen_jobs.json").read_text().count("Senior Cryptography Engineer") == 1
        assert "run_setup_worker" not in (Path(__file__).resolve().parents[2] / "scripts" / "run_track.sh").read_text()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
