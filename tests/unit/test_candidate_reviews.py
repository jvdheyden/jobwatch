import json
from dataclasses import asdict

import pytest

from candidate_reviews import commit, prepare, review_paths
from discover import http
from discover.core import SourceConfig
from discover.sources.thales import discover_thales_html
from source_config import write_json_atomic


DATE = "2030-01-15"
BOARD = "https://example.com/jobs"


def posting(url=f"{BOARD}?req=123", **changes):
    return {"employer": "Example Co", "title": "Engineer", "location": "Berlin", "remote": "hybrid",
            "description": "Build secure libraries.", "description_truncated": False, "url": url, **changes}


def prepare_review(root, candidates):
    discovery = root / "discovery.json"
    write_json_atomic(discovery, {
        "schema_version": 1, "track": "demo", "today": DATE, "mode": "discover",
        "sources": [{"source_id": "example", "source_url": BOARD, "discovery_mode": "html",
                     "matched_jobs": len(candidates), "candidates": candidates}],
    })
    run_id, fingerprint = prepare(root, "demo", DATE, discovery)
    path, _ = review_paths(root, "demo", run_id)
    return json.loads(path.read_text()), fingerprint


def acknowledge(root, review, fingerprint, *, unchanged=False):
    run_id = review["run_id"]
    review_path, receipt_path = review_paths(root, "demo", run_id)
    if not unchanged:
        write_json_atomic(review_path.with_suffix(".digest.json"), {
            "schema_version": 1, "track": "demo", "date": DATE,
            "runs": [{"kind": "initial", "generated_at": f"{DATE}T00:00:00Z"}],
        })
    write_json_atomic(receipt_path, {"run_id": run_id, "digest_unchanged": unchanged,
                                    "batches": [{"source_id": "example", "complete": True}]})
    commit(root, "demo", DATE, run_id, fingerprint)


def queued(review):
    return review["sources"][0]["candidates"]


def test_tracking_variants_skip_but_distinct_requisitions_and_board_links_queue(tmp_path):
    first, fingerprint = prepare_review(tmp_path, [posting(f"{BOARD}?req=123&utm_source=first"), posting(BOARD)])
    acknowledge(tmp_path, first, fingerprint)

    another_requisition = f"{BOARD}?req=456"
    second, _ = prepare_review(tmp_path, [
        posting(f"{BOARD}?fbclid=1&req=123"), posting(another_requisition), posting(f"{BOARD}?gclid=2"),
    ])
    assert [c["url"] for c in queued(second)] == [another_requisition, f"{BOARD}?gclid=2"]
    assert queued(second)[0]["candidate_id"] != queued(first)[0]["candidate_id"]


def test_native_identity_survives_url_changes_and_colliding_identities_are_retried(tmp_path):
    first, fingerprint = prepare_review(tmp_path, [posting(posting_id="123"), posting(f"{BOARD}/shared")])
    acknowledge(tmp_path, first, fingerprint)
    first_shared_id = queued(first)[1]["candidate_id"]

    second, fingerprint = prepare_review(tmp_path, [
        posting(f"{BOARD}/renamed", posting_id="123"),
        posting(f"{BOARD}/shared?utm_source=abc"), posting(f"{BOARD}/shared?utm_source=def", title="Writer"),
    ])
    assert [c["title"] for c in queued(second)] == ["Engineer", "Writer"]
    ids = {c["candidate_id"] for c in queued(second)}
    assert len(ids) == 2
    assert first_shared_id not in ids
    acknowledge(tmp_path, second, fingerprint, unchanged=True)
    third, _ = prepare_review(tmp_path, queued(second))
    assert len(queued(third)) == 2


@pytest.mark.parametrize("changes", [
    {"employer": "Other Co"}, {"title": "Architect"}, {"location": "Paris"}, {"remote": "remote"},
    {"description": "Build secure applications."}, {"description_truncated": True},
])
def test_posting_evidence_changes_reopen_review(tmp_path, changes):
    first, fingerprint = prepare_review(tmp_path, [posting()])
    acknowledge(tmp_path, first, fingerprint)
    second, _ = prepare_review(tmp_path, [posting(**changes)])
    assert queued(second)[0]["candidate_id"] == queued(first)[0]["candidate_id"]


def test_whitespace_and_diagnostics_do_not_reopen_review(tmp_path):
    first, fingerprint = prepare_review(tmp_path, [posting()])
    acknowledge(tmp_path, first, fingerprint)
    second, _ = prepare_review(tmp_path, [posting(description=" Build secure\n\tlibraries.  ", notes="New diagnostic",
                                                 matched_terms=["new term"], updated_at="2030-01-16")])
    assert queued(second) == []
    assert second["review_counts"]["skipped"] == 1


def test_thales_page_token_is_ignored_but_role_edits_reopen_review(tmp_path, monkeypatch, read_text_fixture):
    source = SourceConfig("Thales", "https://careers.thalesgroup.com/global/en/search-results", "thales_html",
                          None, "every_run")
    listing = read_text_fixture("sources/thales_html/response.html")
    legitimate_hex = "a13ef47d6df64c1ebae13efb26fc781b"

    def discover(description, token):
        def fetch(url, timeout_seconds):
            if "/search-results" in url:
                return listing
            return (f"<html><body><h2>Responsibilities</h2><p>{description}</p>"
                    f"<p>Project reference {legitimate_hex}</p></body></html>"
                    f"<div id='csrfToken' style='display:none'>{token}</div>")

        monkeypatch.setattr(http, "fetch_text", fetch)
        coverage = discover_thales_html(source, ["security"], timeout_seconds=5)
        [candidate] = coverage.candidates
        assert candidate.title == "Security Engineer"
        assert f"Project reference {legitimate_hex}" in candidate.description
        return asdict(candidate)

    first_token = "0e1c4f27f012441cbc64068c51ecf4bb"
    next_token = "82d0493428bc47b08fcaa555de97c060"
    first, fingerprint = prepare_review(tmp_path, [discover("Build secure libraries.", first_token)])
    acknowledge(tmp_path, first, fingerprint)

    second, _ = prepare_review(tmp_path, [discover("Build secure libraries.", next_token)])
    assert queued(second) == []

    third, _ = prepare_review(tmp_path, [discover("Build secure applications.", next_token)])
    [edited] = queued(third)
    assert edited["candidate_id"] == queued(first)[0]["candidate_id"]
    assert "Build secure applications." in edited["description"]
    assert next_token not in edited["description"]


@pytest.mark.parametrize("context_path", [
    "tracks/demo/AGENTS.md", "tracks/demo/prefs.md", "tracks/demo/reference_jobs.json", "profile/prefs_global.md",
    "profile/cv.md", ".agents/skills/find-jobs/SKILL.md", ".agents/skills/rank-jobs/SKILL.md",
])
def test_criteria_changes_reopen_review(tmp_path, context_path):
    first, fingerprint = prepare_review(tmp_path, [posting()])
    acknowledge(tmp_path, first, fingerprint)
    context = tmp_path / context_path
    context.parent.mkdir(parents=True, exist_ok=True)
    context.write_text("changed criteria")
    second, _ = prepare_review(tmp_path, [posting()])
    assert queued(second)[0]["candidate_id"] == queued(first)[0]["candidate_id"]


def test_tampering_with_review_artifact_prevents_acknowledgment(tmp_path):
    first, fingerprint = prepare_review(tmp_path, [posting()])
    review_path, _ = review_paths(tmp_path, "demo", first["run_id"])
    write_json_atomic(review_path, {**first, "sources": []})
    with pytest.raises(ValueError, match="artifact changed"):
        acknowledge(tmp_path, first, fingerprint)
    second, _ = prepare_review(tmp_path, [posting()])
    assert len(queued(second)) == 1


def test_late_receipt_keeps_newer_evidence_and_merges_other_acknowledgments(tmp_path):
    old_only = posting(f"{BOARD}?req=old-only")
    new_only = posting(f"{BOARD}?req=new-only")
    revised = posting(location="Munich")
    older, old_fingerprint = prepare_review(tmp_path, [posting(), old_only])
    newer, new_fingerprint = prepare_review(tmp_path, [revised, new_only])
    acknowledge(tmp_path, newer, new_fingerprint)
    acknowledge(tmp_path, older, old_fingerprint)

    following, _ = prepare_review(tmp_path, [revised, new_only, old_only])
    assert following["review_counts"] == {"queued": 0, "skipped": 3, "deferred": 0}
