from __future__ import annotations

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
