from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

import scaffold_track
import setup_contracts
from digest_json import normalize_digest_payload
from discover.runner import load_track_config
from source_config import load_sources_config


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "setup"


def setup_payload() -> dict:
    return json.loads((FIXTURES / "setup.json").read_text())


def source_pack_payload(setup: dict) -> dict:
    payload = json.loads((FIXTURES / "source-pack.json").read_text())
    payload["input_hash"] = setup_contracts.artifact_hash(setup_contracts.normalize_setup(setup))
    return payload


def selected_setup() -> dict:
    setup = setup_contracts.normalize_setup(setup_payload())
    pack = setup_contracts.normalize_source_pack(source_pack_payload(setup), setup)
    return setup_contracts.apply_source_selection(setup, pack)


def test_setup_and_source_pack_round_trip_atomically(tmp_path: Path) -> None:
    payload = setup_payload()
    payload["profile"]["skills"].append(" rust ")
    payload["source_seeds"]["career_pages_or_boards"][0] += "#jobs"
    setup_path = tmp_path / "setup.json"

    normalized = setup_contracts.write_setup(setup_path, payload)

    assert setup_contracts.load_setup(setup_path) == normalized
    assert normalized["profile"]["skills"] == ["Rust", "protocol security"]
    assert normalized["source_seeds"]["career_pages_or_boards"] == ["https://jobs.example.test/careers"]
    assert not list(tmp_path.glob(".setup.json.*.tmp"))

    pack_path = tmp_path / "source-pack.json"
    pack = source_pack_payload(normalized)
    written = setup_contracts.write_source_pack(pack_path, pack, normalized)
    assert setup_contracts.load_source_pack(pack_path, normalized) == written
    assert "recommended package is ready" in setup_contracts.render_source_pack_summary(written, normalized)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update({"transcript": "private conversation"}), "forbidden"),
        (lambda value: value["track"].update({"slug": "../escape"}), "safe child"),
        (
            lambda value: value["selected_sources"]["sources"].append(
                {
                    "id": "bad",
                    "name": "Bad",
                    "url": "file:///etc/passwd",
                    "discovery_mode": "html",
                    "cadence_group": "every_run",
                }
            ),
            "absolute http",
        ),
        (
            lambda value: value["selected_sources"]["sources"].append(
                {
                    "id": "bad",
                    "name": "Bad",
                    "url": "https://example.test/jobs",
                    "discovery_mode": "invented_mode",
                    "cadence_group": "every_run",
                }
            ),
            "not supported",
        ),
    ],
)
def test_setup_rejects_sensitive_or_unsafe_fields(mutate, message: str) -> None:
    payload = setup_payload()
    mutate(payload)
    with pytest.raises(setup_contracts.SetupContractError, match=message):
        setup_contracts.normalize_setup(payload)


def test_setup_loader_rejects_oversized_artifact_before_parsing(tmp_path: Path) -> None:
    path = tmp_path / "setup.json"
    path.write_text("{" + " " * setup_contracts.SETUP_MAX_BYTES + "}")
    with pytest.raises(setup_contracts.SetupContractError, match="limit"):
        setup_contracts.load_setup(path)


def test_source_pack_rejects_budget_hash_employer_and_unknown_rule_ids() -> None:
    setup = setup_contracts.normalize_setup(setup_payload())
    pack = source_pack_payload(setup)

    wrong_hash = copy.deepcopy(pack)
    wrong_hash["input_hash"] = "0" * 64
    with pytest.raises(setup_contracts.SetupContractError, match="input_hash"):
        setup_contracts.normalize_source_pack(wrong_hash, setup)

    too_many = copy.deepcopy(pack)
    too_many["recommended_sources"] *= setup_contracts.MAX_PRIMARY_SOURCES + 1
    with pytest.raises(setup_contracts.SetupContractError, match="exceeds"):
        setup_contracts.normalize_source_pack(too_many, setup)

    excluded = copy.deepcopy(pack)
    excluded["recommended_sources"][0]["name"] = "Previous Employer Careers"
    with pytest.raises(setup_contracts.SetupContractError, match="current or recent employer"):
        setup_contracts.normalize_source_pack(excluded, setup)

    foreign_rule = copy.deepcopy(pack)
    foreign_rule["match_rule_suggestions"] = [
        {
            "id": "broad_filter",
            "source_ids": ["foreign"],
            "source_names": [],
            "keep_if_any_text_term": ["cryptography"],
        }
    ]
    with pytest.raises(setup_contracts.SetupContractError, match="unknown source ids"):
        setup_contracts.normalize_source_pack(foreign_rule, setup)


def _write_discovery(path: Path, *, track: str, candidates: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "track": track,
                "today": "2026-07-20",
                "generated_at": "2026-07-20T10:00:00Z",
                "mode": "discover",
                "sources": [
                    {
                        "source_id": "example_labs",
                        "source": "Example Labs",
                        "source_url": "https://jobs.example.test/careers",
                        "discovery_mode": "html",
                        "cadence_group": "every_3_runs",
                        "last_checked": None,
                        "due_today": True,
                        "status": "complete",
                        "listing_pages_scanned": 1,
                        "search_terms_tried": ["cryptography", "privacy"],
                        "result_pages_scanned": "1 listing page",
                        "direct_job_pages_opened": len(candidates),
                        "enumerated_jobs": len(candidates),
                        "matched_jobs": len(candidates),
                        "limitations": [],
                        "candidates": candidates,
                    }
                ],
            },
            indent=2,
        )
        + "\n"
    )


def _candidate(index: int, *, terms: int = 1, description: str = "A role description") -> dict:
    return {
        "employer": "Example Labs",
        "title": f"Cryptography Engineer {index}",
        "url": f"https://jobs.example.test/jobs/{index}",
        "source_url": "https://jobs.example.test/careers",
        "alternate_url": "",
        "location": "Remote Europe",
        "remote": "remote",
        "matched_terms": [f"term-{item}" for item in range(terms)],
        "notes": "This diagnostic note must not become description evidence.",
        "description": description,
        "description_truncated": False,
    }


def test_preview_context_is_bounded_stable_and_excludes_seen_jobs(tmp_path: Path) -> None:
    setup_path = tmp_path / "artifacts" / "setup" / "id" / "setup.json"
    setup = setup_contracts.write_setup(setup_path, selected_setup())
    discovery_path = tmp_path / "artifacts" / "discovery" / "applied_crypto" / "2026-07-20.json"
    candidates = [_candidate(index, terms=(index % 4) + 1, description="x" * 14000) for index in range(45)]
    candidates[-1]["title"] = "Product Manager"
    candidates[-1]["matched_terms"] = ["product manager"]
    candidates.append(copy.deepcopy(candidates[3]))
    _write_discovery(discovery_path, track="applied_crypto", candidates=candidates)
    seen_path = tmp_path / "tracks" / "applied_crypto" / "seen_jobs.json"
    seen_path.parent.mkdir(parents=True)
    seen_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "track": "applied_crypto",
                "jobs": [
                    {
                        "date_seen": "2026-07-19",
                        "company": "Example Labs",
                        "title": "Cryptography Engineer 0",
                        "location": "Remote Europe",
                        "url": "https://jobs.example.test/jobs/0",
                    }
                ],
            }
        )
        + "\n"
    )

    first = setup_contracts.build_preview_context(
        setup, discovery_path, seen_path, setup_path=setup_path, root=tmp_path
    )
    second = setup_contracts.build_preview_context(
        setup, discovery_path, seen_path, setup_path=setup_path, root=tmp_path
    )

    assert first == second
    assert len(first["candidates"]) <= setup_contracts.MAX_PREVIEW_CANDIDATES
    assert first["omitted_candidate_count"] > 0
    assert all(candidate["description_truncated"] for candidate in first["candidates"])
    assert all(len(candidate["description"].encode()) <= setup_contracts.MAX_DESCRIPTION_BYTES for candidate in first["candidates"])
    assert "diagnostic note" not in json.dumps(first["candidates"])
    assert "https://jobs.example.test/jobs/0" not in {candidate["url"] for candidate in first["candidates"]}
    assert "https://jobs.example.test/jobs/44" in {candidate["url"] for candidate in first["candidates"]}
    assert len(json.dumps(first, sort_keys=True, separators=(",", ":")).encode()) <= setup_contracts.PREVIEW_CONTEXT_MAX_BYTES


def test_preview_context_prioritizes_title_evidence_at_candidate_cap(tmp_path: Path) -> None:
    setup_path = tmp_path / "artifacts" / "setup" / "id" / "setup.json"
    setup = setup_contracts.write_setup(setup_path, selected_setup())
    discovery_path = tmp_path / "artifacts" / "discovery" / "applied_crypto" / "2026-07-20.json"
    candidates = [_candidate(index, description="Work on cryptography products.") for index in range(45)]
    for index, candidate in enumerate(candidates):
        candidate["title"] = f"Office Coordinator {index}"
        candidate["matched_terms"] = ["cryptography"]
    candidates[-1]["title"] = "Product Manager"
    candidates[-1]["matched_terms"] = ["product manager"]
    _write_discovery(discovery_path, track="applied_crypto", candidates=candidates)
    seen_path = tmp_path / "tracks" / "applied_crypto" / "seen_jobs.json"
    seen_path.parent.mkdir(parents=True)
    seen_path.write_text(json.dumps({"schema_version": 1, "track": "applied_crypto", "jobs": []}) + "\n")

    context = setup_contracts.build_preview_context(
        setup, discovery_path, seen_path, setup_path=setup_path, root=tmp_path
    )

    retained_urls = {candidate["url"] for candidate in context["candidates"]}
    assert len(context["candidates"]) == setup_contracts.MAX_PREVIEW_CANDIDATES
    assert context["omitted_candidate_count"] == 5
    assert "https://jobs.example.test/jobs/44" in retained_urls
    assert "https://jobs.example.test/jobs/39" not in retained_urls
    assert context["candidates"][0]["title"] == "Product Manager"


def test_preview_result_requires_one_identity_preserving_judgment_per_candidate(tmp_path: Path) -> None:
    setup_path = tmp_path / "setup.json"
    setup = setup_contracts.write_setup(setup_path, selected_setup())
    discovery_path = tmp_path / "discovery.json"
    _write_discovery(discovery_path, track="applied_crypto", candidates=[_candidate(1), _candidate(2), _candidate(3, description="")])
    seen_path = tmp_path / "seen_jobs.json"
    seen_path.write_text(json.dumps({"schema_version": 1, "track": "applied_crypto", "jobs": []}) + "\n")
    context = setup_contracts.build_preview_context(
        setup, discovery_path, seen_path, setup_path=setup_path, root=tmp_path
    )
    ids = [candidate["candidate_id"] for candidate in context["candidates"]]
    result = {
        "schema_version": 1,
        "kind": setup_contracts.PREVIEW_RESULT_KIND,
        "setup_id": setup["setup_id"],
        "input_hash": setup_contracts.artifact_hash(context),
        "executive_summary": "One strong, one borderline, and one excluded role.",
        "recommended_actions": ["Review the strongest role."],
        "judgments": [
            {
                "candidate_id": ids[0],
                "disposition": "top_match",
                "score": 9,
                "recommendation": "apply_now",
                "match_reasons": ["Direct hands-on cryptography fit."],
                "concerns": [],
            },
            {
                "candidate_id": ids[1],
                "disposition": "other_role",
                "score": 6,
                "recommendation": "watch",
                "short_note": "Borderline because the scope is broad.",
            },
            {
                "candidate_id": ids[2],
                "disposition": "filtered",
                "reason": "Missing description prevents evidence-based fit and location violates a hard constraint.",
            },
        ],
    }
    normalized = setup_contracts.normalize_preview_result(result, context)
    digest = setup_contracts.assemble_preview_digest(context, normalized, generated_at="2026-07-20T12:00:00Z")
    assert normalize_digest_payload(digest) == digest
    assert digest["runs"][0]["top_matches"][0]["listing_url"] == context["candidates"][0]["url"]
    assert len(digest["runs"][0]["filtered_roles"]) == 1

    missing = copy.deepcopy(result)
    missing["judgments"].pop()
    with pytest.raises(setup_contracts.SetupContractError, match="missing judgments"):
        setup_contracts.normalize_preview_result(missing, context)
    foreign = copy.deepcopy(result)
    foreign["judgments"][0]["candidate_id"] = "candidate_0000000000000000"
    with pytest.raises(setup_contracts.SetupContractError, match="not present"):
        setup_contracts.normalize_preview_result(foreign, context)
    duplicate = copy.deepcopy(result)
    duplicate["judgments"][1]["candidate_id"] = ids[0]
    with pytest.raises(setup_contracts.SetupContractError, match="duplicate judgment"):
        setup_contracts.normalize_preview_result(duplicate, context)


def test_scaffold_track_creates_complete_track_and_refuses_overwrite(tmp_path: Path) -> None:
    (tmp_path / "shared").mkdir()
    shutil.copytree(Path(__file__).resolve().parents[2] / "shared" / "templates", tmp_path / "shared" / "templates")
    setup_path = tmp_path / "artifacts" / "setup" / "fixture" / "setup.json"
    setup_contracts.write_setup(setup_path, selected_setup())

    result = scaffold_track.scaffold_track(setup_path, root=tmp_path)

    assert result["status"] == "created"
    track_dir = tmp_path / "tracks" / "applied_crypto"
    expected = {
        "prefs.md",
        "sources.json",
        "source_state.json",
        "sources.md",
        "AGENTS.md",
        "CLAUDE.md",
        "GEMINI.md",
        "seen_jobs.json",
        "digests",
        "ranked_overview.md",
    }
    assert expected <= {path.name for path in track_dir.iterdir()}
    assert load_sources_config(track_dir / "sources.json", "applied_crypto")["sources"][0]["id"] == "example_labs"
    sources, terms, _ = load_track_config("applied_crypto", root=tmp_path)
    assert len(sources) == 1
    assert terms == ["cryptography", "privacy engineering"]
    assert "{" not in (track_dir / "prefs.md").read_text()
    assert (track_dir / "CLAUDE.md").read_text() == "@AGENTS.md\n"
    assert (tmp_path / "shared" / "ranked_jobs" / "applied_crypto.json").is_file()

    before = (track_dir / "sources.json").read_bytes()
    with pytest.raises(setup_contracts.SetupContractError, match="refusing to overwrite"):
        scaffold_track.scaffold_track(setup_path, root=tmp_path)
    assert (track_dir / "sources.json").read_bytes() == before
