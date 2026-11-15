from __future__ import annotations

import copy
from datetime import date

import pytest

import digest_json


def test_valid_digest_payload_renders_required_sections(load_json_fixture):
    payload = load_json_fixture("digests/core_crypto_minimal.json")

    rendered = digest_json.render_digest_markdown(payload)

    assert "# Job Digest — 2026-03-29" in rendered
    assert "Tags: [[job digest core_crypto]] [[Core Crypto Ranked Overview]]" in rendered
    assert "## Executive summary" in rendered
    assert "## Top matches" in rendered
    assert "## Seen jobs to append" in rendered


def test_digest_payload_with_update_run_renders_update_section(load_json_fixture):
    payload = load_json_fixture("digests/core_crypto_with_update.json")

    rendered = digest_json.render_digest_markdown(payload)

    assert "## Update 14:35" in rendered
    assert "Privacy Engineer — Example Privacy Lab" in rendered


def test_invalid_digest_payload_is_rejected(load_json_fixture):
    payload = load_json_fixture("digests/core_crypto_minimal.json")
    payload["schema_version"] = 999

    with pytest.raises(digest_json.DigestValidationError):
        digest_json.normalize_digest_payload(payload)


@pytest.mark.parametrize("score", [0.9, 10.1])
def test_digest_payload_rejects_fit_score_outside_one_to_ten(load_json_fixture, score):
    payload = copy.deepcopy(load_json_fixture("digests/core_crypto_minimal.json"))
    payload["runs"][0]["top_matches"][0]["fit_score"] = score

    with pytest.raises(digest_json.DigestValidationError, match="between 1 and 10"):
        digest_json.normalize_digest_payload(payload)


def test_filter_recent_ranked_jobs_keeps_jobs_within_cutoff():
    jobs = [
        {"company": "Fresh", "last_seen": "2026-04-10"},
        {"company": "Edge", "last_seen": "2026-03-20"},
        {"company": "Stale", "last_seen": "2026-03-01"},
    ]

    kept = digest_json.filter_recent_ranked_jobs(jobs, as_of=date(2026, 4, 18), days=30)

    assert [job["company"] for job in kept] == ["Fresh", "Edge"]


def test_filter_recent_ranked_jobs_noop_when_as_of_none():
    jobs = [{"company": "Old", "last_seen": "2000-01-01"}]

    assert digest_json.filter_recent_ranked_jobs(jobs, as_of=None) == jobs


@pytest.mark.parametrize('mutation', [
    lambda p: p.update(track='another_track'),
    lambda p: p.update(date='2030-01-01'),
    lambda p: p.update(runs=[]),
    lambda p: p['runs'][0].update(kind='update'),
    lambda p: p['runs'][0]['top_matches'][0].update(recommendation='invented'),
    lambda p: p['runs'][0]['top_matches'][0].update(fit_score=True),
    lambda p: p['runs'][0]['top_matches'][0].update(fit_score=float('nan')),
    lambda p: p['runs'][0]['top_matches'][0].update(listing_url=''),
    lambda p: p['runs'][0]['source_notes'][0].update(status='success'),
], ids=['foreign-track', 'wrong-date', 'missing-runs', 'missing-initial', 'unknown-recommendation',
        'boolean-score', 'nan-score', 'missing-url', 'unknown-coverage-status'])
def test_agent_digest_boundary_rejects_invalid_artifacts(load_json_fixture, tmp_path, mutation):
    import json
    payload = load_json_fixture('digests/core_crypto_minimal.json')
    mutation(payload)
    path = tmp_path / 'digest.json'
    path.write_text(json.dumps(payload))
    with pytest.raises(digest_json.DigestValidationError):
        digest_json.load_digest_payload(path, expected_track='core_crypto', expected_date='2026-03-29')


def test_malformed_json_is_a_validation_error(tmp_path):
    path = tmp_path / 'digest.json'
    path.write_text('{truncated')
    with pytest.raises(digest_json.DigestValidationError, match='invalid JSON'):
        digest_json.load_digest_payload(path)
